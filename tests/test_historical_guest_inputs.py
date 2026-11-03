"""Historical source restoration preserves bytes and cannot replace guest OS files."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("historical_guest", ROOT / "tools/prepare-guest.py")
guest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guest)


class HistoricalGuestInputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        shutil.copytree(ROOT / "runtime", self.root / "runtime")
        cache = self.root / ".local/guest-cache"
        cache.mkdir(parents=True)
        self.archive = cache / "ubuntu-base-24.04.5-base-arm64.tar.gz"
        with tarfile.open(self.archive, "w:gz") as out:
            for name in ("etc/", "usr/", "usr/bin/", "usr/share/"):
                member = tarfile.TarInfo(name)
                member.type = tarfile.DIRTYPE
                member.mode = 0o755
                out.addfile(member)
            for name, data in (("usr/bin/bash", b"fixture-bash"), ("usr/bin/env", b"fixture-env"),
                               ("usr/share/license", b"OS copyright notice: must remain unchanged")):
                member = tarfile.TarInfo(name)
                member.mode = 0o644
                member.size = len(data)
                out.addfile(member, io.BytesIO(data))
        self.lock = json.loads((self.root / "runtime/guest/image.lock.json").read_text())
        self.lock["source"]["sha256"] = guest.sha256(self.archive)
        sums = cache / "SHA256SUMS"
        sums.write_text(self.lock["source"]["sha256"] + " *" + self.archive.name + "\n")
        self.lock["source"]["sha256SumsSha256"] = guest.sha256(sums)
        self.lock_path = self.root / "runtime/guest/image.lock.json"
        self.lock_path.write_text(json.dumps(self.lock))
        self.patch_root = mock.patch.object(guest, "ROOT", self.root)
        self.patch_lock = mock.patch.object(guest, "LOCK_PATH", self.lock_path)
        self.patch_root.start()
        self.patch_lock.start()
        self.addCleanup(self.patch_root.stop)
        self.addCleanup(self.patch_lock.stop)
        self.normalized = guest.normalize(self.archive)
        self.capture = self.root / "capture"
        self.manifest_path = self.capture / "manifest.json"
        self.host_sentinel = self.root / "MUST_NOT_EXECUTE"
        self.historical_text = ("#!/bin/sh\ntouch '" + str(self.host_sentinel) + "'\n").encode()
        self.data = {
            "schemaVersion": 1, "kind": "z8-historical-guest-managed-source",
            "guestArchiveSha256": "0" * 64, "guestManifestSha256": "0" * 64,
            "referenceCurrentSourceInputSha256": "1" * 64,
            "guestSource": self.lock["source"], "files": [],
            "absentFromHistoricalGuest": sorted(guest.HISTORICAL_LATER_ADDITIONS),
        }
        for name in sorted(guest.HISTORICAL_MANAGED_FILES):
            content = self.historical_text if name.endswith("/shellrc") else self.normalized[name]["data"]
            path = self.capture / "files" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            self.data["files"].append({"guestPath": name, "path": "files/" + name,
                "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content), "guestMode": 0o644})
        self.write_manifest()

    def write_manifest(self, data=None):
        self.manifest_path.write_text(json.dumps(self.data if data is None else data, indent=2) + "\n")

    def read(self):
        return guest.read_historical_managed_inputs(self.manifest_path, self.lock)

    def test_restores_historical_source_as_data_and_preserves_os_content(self):
        actual = guest.apply_historical_managed_inputs(self.normalized, self.read())
        self.assertEqual(actual["etc/z8/shellrc"]["data"], self.historical_text)
        self.assertEqual(actual["usr/share/license"], self.normalized["usr/share/license"])
        self.assertEqual(actual["SYMLINKS.txt"], self.normalized["SYMLINKS.txt"])
        self.assertFalse(any(name in actual for name in guest.HISTORICAL_LATER_ADDITIONS))
        self.assertTrue(guest.HISTORICAL_LATER_ADDITIONS.issubset(self.normalized))
        self.assertFalse(self.host_sentinel.exists())

    def test_rejects_wrong_manifest_kind_source_and_malformed_digests(self):
        cases = [("kind", "untrusted-rootfs"), ("schemaVersion", True),
                 ("guestSource", {**self.lock["source"], "sha256": "2" * 64}),
                 ("guestArchiveSha256", "123"), ("guestManifestSha256", "G" * 64),
                 ("referenceCurrentSourceInputSha256", None)]
        for key, value in cases:
            with self.subTest(key=key):
                data = copy.deepcopy(self.data)
                data[key] = value
                self.write_manifest(data)
                with self.assertRaises(guest.GuestError):
                    self.read()

    def test_rejects_missing_duplicate_os_escape_and_privileged_file_records(self):
        cases = []
        missing = copy.deepcopy(self.data)
        missing["files"].pop()
        cases.append(missing)
        duplicate = copy.deepcopy(self.data)
        duplicate["files"][0] = duplicate["files"][1]
        cases.append(duplicate)
        for key, value in (("guestPath", "usr/bin/bash"), ("path", "../outside"),
                           ("path", "/etc/passwd"), ("guestMode", 0o4755),
                           ("guestMode", True), ("bytes", True)):
            data = copy.deepcopy(self.data)
            data["files"][0][key] = value
            cases.append(data)
        for data in cases:
            with self.subTest(record=data["files"][0]):
                self.write_manifest(data)
                with self.assertRaises(guest.GuestError):
                    self.read()

    def test_rejects_content_tampering_and_binary_source_even_with_matching_hash(self):
        record = self.data["files"][0]
        path = self.capture / record["path"]
        path.write_bytes(b"changed")
        with self.assertRaises(guest.GuestError):
            self.read()
        content = b"\xff\xfe"
        path.write_bytes(content)
        record.update(bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
        self.write_manifest()
        with self.assertRaisesRegex(guest.GuestError, "UTF-8"):
            self.read()

    def test_rejects_symlink_manifest_source_and_source_parent(self):
        link = self.root / "manifest-link.json"
        link.symlink_to(self.manifest_path)
        with self.assertRaisesRegex(guest.GuestError, "symlink"):
            guest.read_historical_managed_inputs(link, self.lock)
        path = self.capture / self.data["files"][0]["path"]
        outside = self.root / "outside.txt"
        path.rename(outside)
        path.symlink_to(outside)
        with self.assertRaisesRegex(guest.GuestError, "symlink"):
            self.read()
        path.unlink()
        outside.rename(path)
        files = self.capture / "files"
        actual = self.root / "actual-files"
        files.rename(actual)
        files.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(guest.GuestError, "symlink"):
            self.read()

    def test_rejects_duplicate_json_keys_and_unscoped_removals(self):
        text = self.manifest_path.read_text().replace('"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1')
        self.manifest_path.write_text(text)
        with self.assertRaisesRegex(guest.GuestError, "Duplicate"):
            self.read()
        self.data["absentFromHistoricalGuest"][0] = "usr/bin/bash"
        self.write_manifest()
        with self.assertRaises(guest.GuestError):
            self.read()

    def test_new_unrecognized_child_is_preserved_by_refusing_reconstruction(self):
        altered = dict(self.normalized)
        altered["usr/local/lib/z8/browser/new-helper"] = {"type": "file", "mode": 0o644, "data": b"new"}
        with self.assertRaisesRegex(guest.GuestError, "nonempty"):
            guest.apply_historical_managed_inputs(altered, self.read())
        self.assertIn("usr/local/lib/z8/browser/new-helper", altered)

    def test_wrong_final_hash_publishes_nothing_and_preserves_existing_default(self):
        default = guest.build()
        default_path = Path(default["manifest"])
        before = guest.sha256(default_path.parent / "rootfs.zip")
        self.assertNotIn("exactHistoricalGuestReconstruction", default)
        with self.assertRaisesRegex(guest.GuestError, "exact recorded guest archive"):
            guest.build(self.manifest_path)
        self.assertEqual(guest.sha256(default_path.parent / "rootfs.zip"), before)
        self.assertEqual(list(default_path.parent.parent.glob("*/manifest.json")), [default_path])
        self.assertFalse(self.host_sentinel.exists())

    def reference_archive(self):
        # Derive the historical fixture from a normal produced ZIP, using its
        # original entry metadata. This independently checks the public builder.
        default = guest.build()
        default_path = Path(default["manifest"])
        reference = self.root / "reference.zip"
        records = {record["guestPath"]: record for record in self.data["files"]}
        with zipfile.ZipFile(default_path.parent / "rootfs.zip") as source, zipfile.ZipFile(reference, "w") as output:
            for info in source.infolist():
                if info.filename in guest.HISTORICAL_LATER_ADDITIONS:
                    continue
                content = (self.capture / records[info.filename]["path"]).read_bytes() if info.filename in records else source.read(info)
                output.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        metadata = json.loads(default_path.read_text())
        metadata["archiveSha256"] = guest.sha256(reference)
        metadata["archiveBytes"] = reference.stat().st_size
        metadata["files"] = [record for record in metadata["files"] if record["path"] not in guest.HISTORICAL_LATER_ADDITIONS]
        for record in metadata["files"]:
            if record["path"] in records:
                record["size"] = records[record["path"]]["bytes"]
        metadata["entryCount"] = len(metadata["files"])
        metadata["totalUncompressedBytes"] = sum(record["size"] for record in metadata["files"])
        self.data["guestArchiveSha256"] = guest.sha256(reference)
        self.data["guestManifestSha256"] = hashlib.sha256((json.dumps(metadata, indent=2) + "\n").encode()).hexdigest()
        self.write_manifest()
        return reference

    def test_build_reconstructs_exact_reference_and_validates_manifest(self):
        reference = self.reference_archive()
        result = guest.build(self.manifest_path)
        self.assertTrue(result["exactHistoricalGuestReconstruction"])
        path = Path(result["manifest"])
        self.assertEqual((path.parent / "rootfs.zip").read_bytes(), reference.read_bytes())
        self.assertEqual(guest.sha256(path), self.data["guestManifestSha256"])
        self.assertEqual(result["historicalManagedInputsSha256"], guest.sha256(self.manifest_path))
        self.assertFalse(self.host_sentinel.exists())

    def test_wrong_final_manifest_hash_also_blocks_publication(self):
        self.reference_archive()
        self.data["guestManifestSha256"] = "0" * 64
        self.write_manifest()
        with self.assertRaisesRegex(guest.GuestError, "manifest differs"):
            guest.build(self.manifest_path)
        target = self.root / "artifacts/guest/ubuntu-24.04.5-arm64" / self.data["guestArchiveSha256"]
        self.assertFalse(target.exists())

    def test_cli_rejects_historical_option_without_build(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools/prepare-guest.py"),
            "--historical-managed-inputs", str(self.manifest_path)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires --build", result.stderr)


if __name__ == "__main__":
    unittest.main()
