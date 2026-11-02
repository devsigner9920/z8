"""Native installer safety tests with temporary files; no public binary execution or login."""
import hashlib
import io
import json
import contextlib
from pathlib import Path
import subprocess
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "runtime/guest/install-ai.sh"
LOCK = ROOT / "runtime/guest/ai-tools.lock.json"
SOURCE = SCRIPT.read_text().split("<<'Z8_AI_PYTHON'\n", 1)[1].rsplit("\nZ8_AI_PYTHON", 1)[0]


def module():
    value = types.ModuleType("z8_ai_installer_test")
    exec(compile(SOURCE, str(SCRIPT), "exec"), value.__dict__)
    return value


def arm64_elf():
    data = bytearray(64)
    data[:6] = b"\x7fELF\x02\x01"
    data[18:20] = b"\xb7\x00"
    return bytes(data)


def package_fixture():
    """Keep the real complete graph while replacing large binaries with fixtures."""
    pin = json.loads(LOCK.read_text())["tools"]["codex"]
    payloads = {}
    for member in pin["members"]:
        if member["type"] == "directory":
            continue
        name = member["path"]
        if name == "codex-package.json":
            data = json.dumps(pin["packageManifest"]).encode()
        elif name in pin["binaries"] or member["mode"] == 0o555:
            data = arm64_elf()
        else:
            data = ("fixture: " + name).encode()
        member.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
        payloads[name] = data
    return pin, payloads


def package_tar(pin, payloads, mutate=None):
    result = io.BytesIO()
    records = [dict(member) for member in pin["members"]]
    if mutate:
        mutate(records)
    with tarfile.open(fileobj=result, mode="w:gz") as archive:
        for member in records:
            item = tarfile.TarInfo(member["path"])
            item.mode = member["mode"]
            item.type = member.get("tarType", tarfile.DIRTYPE if member["type"] == "directory" else tarfile.REGTYPE)
            if item.issym() or item.islnk():
                item.linkname = "../../escape"
                archive.addfile(item)
            elif item.isfile():
                content = payloads.get(member["path"], b"extra")
                item.size = len(content)
                archive.addfile(item, io.BytesIO(content))
            else:
                archive.addfile(item)
    return result.getvalue()


class AIInstallerTests(unittest.TestCase):
    def test_default_dry_run_and_host_guard(self):
        result = subprocess.run(["sh", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No download, installation, login", result.stdout)
        result = subprocess.run(["sh", str(SCRIPT), "--apply", "codex"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stderr, r"Linux guest|ARM64|HOME must|image marker")

    def test_lock_and_official_url_validation(self):
        code = module()
        lock = json.loads(LOCK.read_text())
        code.validate_lock(lock)
        for url in ("http://github.com/x", "https://github.com.evil.invalid/x", "https://user:secret@github.com/x", "file:///tmp/x"):
            with self.assertRaises(RuntimeError):
                code.safe_url(url)
        lock["tools"]["codex"]["version"] = "latest"
        with self.assertRaises(RuntimeError):
            code.validate_lock(lock)

    def test_bounded_hash_checked_download(self):
        code = module()
        content = b"verified artifact"
        class Response(io.BytesIO):
            def geturl(self):
                return "https://downloads.claude.ai/example"
        opener = types.SimpleNamespace(open=lambda *_args, **_kwargs: Response(content))
        with tempfile.TemporaryDirectory() as tmp, patch.object(code.urllib.request, "build_opener", return_value=opener):
            path = Path(tmp) / "artifact"
            code.download("https://downloads.claude.ai/example", path, hashlib.sha256(content).hexdigest(), len(content))
            self.assertEqual(path.read_bytes(), content)
            with self.assertRaises(RuntimeError):
                code.download("https://downloads.claude.ai/example", Path(tmp) / "wrong", "0" * 64, len(content))
            with self.assertRaises(RuntimeError):
                code.download("https://downloads.claude.ai/example", Path(tmp) / "large", hashlib.sha256(content).hexdigest(), 1)

    def test_tar_and_elf_guards(self):
        code = module()
        pin, payloads = package_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive"
            archive.write_bytes(package_tar(pin, payloads))
            destination = root / "complete"
            destination.mkdir()
            members = code.extract_codex_package(archive, destination, pin)
            self.assertEqual(len(members), 54)
            self.assertEqual(json.loads((destination / "codex-package.json").read_text()), pin["packageManifest"])
            for name in pin["binaries"]:
                code.validate_elf(destination / name)
            mutations = (
                lambda records: records.pop(),
                lambda records: records.append(dict(records[0])),
                lambda records: records.append(dict(path="../escape", type="file", mode=0o644)),
                lambda records: records[1].update(tarType=tarfile.SYMTYPE),
                lambda records: records[1].update(tarType=tarfile.LNKTYPE),
                lambda records: records[1].update(mode=0o4755),
            )
            for index, mutation in enumerate(mutations):
                archive.write_bytes(package_tar(pin, payloads, mutation))
                target = root / ("bad-" + str(index))
                target.mkdir()
                with self.assertRaises(RuntimeError):
                    code.extract_codex_package(archive, target, pin)
            (root / "not-arm").write_bytes(b"#!/bin/sh\n")
            with self.assertRaises(RuntimeError):
                code.validate_elf(root / "not-arm")

    def test_package_file_hash_and_wrong_architecture_fail_before_publication(self):
        code = module()
        for kind in ("hash", "architecture", "manifest"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                pin, payloads = package_fixture()
                name = "bin/codex-code-mode-host"
                if kind == "manifest":
                    name = "codex-package.json"
                    payloads[name] = json.dumps(dict(pin["packageManifest"], target="x86_64-unknown-linux-musl")).encode()
                else:
                    bad_elf = bytearray(arm64_elf())
                    bad_elf[18:20] = b"\x3e\x00"
                    payloads[name] = bytes(bad_elf)
                if kind != "hash":
                    record = next(member for member in pin["members"] if member["path"] == name)
                    record.update(size=len(payloads[name]), sha256=hashlib.sha256(payloads[name]).hexdigest())
                archive = Path(tmp) / "archive"
                archive.write_bytes(package_tar(pin, payloads))
                destination = Path(tmp) / "private-staging"
                destination.mkdir()
                with self.assertRaises(RuntimeError):
                    code.extract_codex_package(archive, destination, pin)
                self.assertFalse((destination / "receipt.json").exists())

    def test_managed_publish_preserves_unowned_files_and_versions(self):
        code = module()
        pin, payloads = package_fixture()
        payload = package_tar(pin, payloads)
        def fake_download(_url, path, _hash, _size):
            path.write_bytes(payload)
        def fake_version(_binary, version, _staging):
            return "codex-cli " + version
        with tempfile.TemporaryDirectory() as tmp, patch.object(code, "download", side_effect=fake_download), patch.object(code, "version_check", side_effect=fake_version), contextlib.redirect_stdout(io.StringIO()):
            home = Path(tmp)
            bin_dir = home / ".local/bin"
            bin_dir.mkdir(parents=True)
            launcher = bin_dir / "codex"
            launcher.write_text("user-owned")
            with self.assertRaises(RuntimeError):
                code.install_tool(home, "codex", pin)
            self.assertEqual(launcher.read_text(), "user-owned")
            launcher.unlink()
            code.install_tool(home, "codex", pin)
            self.assertTrue(launcher.is_symlink())
            original = launcher.resolve()
            self.assertEqual(original.read_bytes(), arm64_elf())
            self.assertEqual(original.relative_to((home / ".local/share/z8/ai/codex").resolve()).as_posix(), "0.160.0-package-v1/bin/codex")
            code.install_tool(home, "codex", pin)
            self.assertEqual(launcher.resolve(), original)
            original.write_bytes(b"edited by user")
            with self.assertRaises(RuntimeError):
                code.install_tool(home, "codex", pin)
            self.assertEqual(original.read_bytes(), b"edited by user")

    def test_raw_binary_migrates_to_complete_sibling_without_changing_existing_data(self):
        code = module()
        pin, payloads = package_fixture()
        payload = package_tar(pin, payloads)
        def fake_download(_url, path, _hash, _size):
            path.write_bytes(payload)
        with tempfile.TemporaryDirectory() as tmp, patch.object(code, "download", side_effect=fake_download), \
                patch.object(code, "version_check", return_value="codex-cli 0.160.0"), contextlib.redirect_stdout(io.StringIO()):
            home = Path(tmp)
            old = home / ".local/share/z8/ai/codex/0.160.0"
            old.mkdir(parents=True)
            (old / "codex").write_bytes(arm64_elf())
            receipt = json.dumps({"manager": "z8-ai-v1", "tool": "codex", "version": "0.160.0",
                "artifactSha256": "883620139925f677e5a12c95ba87a1d7f421388ebb797b1c10aba42a04ede9d7",
                "binarySha256": hashlib.sha256(arm64_elf()).hexdigest()})
            (old / "receipt.json").write_text(receipt)
            (old / "user-note").write_text("keep old version data")
            config = home / ".codex/config.toml"
            config.parent.mkdir()
            config.write_text('approval_policy = "untrusted"\n')
            launcher = home / ".local/bin/codex"
            launcher.parent.mkdir(parents=True)
            launcher.symlink_to(old / "codex")
            code.install_tool(home, "codex", pin)
            self.assertEqual(launcher.resolve(), (old.parent / "0.160.0-package-v1/bin/codex").resolve())
            self.assertEqual((old / "codex").read_bytes(), arm64_elf())
            self.assertEqual((old / "receipt.json").read_text(), receipt)
            self.assertEqual((old / "user-note").read_text(), "keep old version data")
            self.assertEqual(config.read_text(), 'approval_policy = "untrusted"\n')

    def test_companion_tampering_and_unowned_package_paths_are_preserved(self):
        code = module()
        pin, payloads = package_fixture()
        payload = package_tar(pin, payloads)
        def fake_download(_url, path, _hash, _size):
            path.write_bytes(payload)
        with tempfile.TemporaryDirectory() as tmp, patch.object(code, "download", side_effect=fake_download), \
                patch.object(code, "version_check", return_value="codex-cli 0.160.0"), contextlib.redirect_stdout(io.StringIO()):
            home = Path(tmp)
            version = home / ".local/share/z8/ai/codex/0.160.0-package-v1"
            version.mkdir(parents=True)
            note = version / "user-note"
            note.write_text("unowned version")
            with self.assertRaises(RuntimeError):
                code.install_tool(home, "codex", pin)
            self.assertEqual(note.read_text(), "unowned version")
            note.unlink()
            version.rmdir()
            code.install_tool(home, "codex", pin)
            companion = version / "bin/codex-code-mode-host"
            companion.write_bytes(b"user-modified companion")
            with self.assertRaises(RuntimeError):
                code.install_tool(home, "codex", pin)
            self.assertEqual(companion.read_bytes(), b"user-modified companion")

    def test_private_directory_and_version_probe(self):
        code = module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".local").symlink_to(root / "elsewhere")
            with self.assertRaises(RuntimeError):
                code.private_directory(root, ".local/bin")
            (root / ".local").unlink()
            def version(argv, **kwargs):
                self.assertEqual(argv, [str(root / "codex"), "--version"])
                self.assertNotIn("LD_PRELOAD", kwargs["env"])
                kwargs["stdout"].write(b"codex-cli 0.160.0\n")
                return types.SimpleNamespace(returncode=0)
            with patch.object(code.subprocess, "run", side_effect=version):
                self.assertEqual(code.version_check(root / "codex", "0.160.0", root), "codex-cli 0.160.0")
                with self.assertRaises(RuntimeError):
                    code.version_check(root / "codex", "0.160.1", root)


if __name__ == "__main__":
    unittest.main()
