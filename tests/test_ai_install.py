"""Native installer safety tests with temporary files; no public binary execution or login."""
import base64
import copy
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


def claude_fixture():
    pin = json.loads(LOCK.read_text())["tools"]["claude"]
    binary = arm64_elf()
    pin.update(sha256=hashlib.sha256(binary).hexdigest(), bytes=len(binary))
    manifest = json.dumps({"version": pin["version"], "platforms": {
        "linux-arm64": {"checksum": pin["sha256"], "size": pin["bytes"]}}}).encode()
    key = b"-----BEGIN PGP PUBLIC KEY BLOCK-----\n\n" + base64.b64encode(b"test key transport") + b"\n=AAAA\n-----END PGP PUBLIC KEY BLOCK-----\n"
    signature = b"test signature transport"
    pin.update(manifestSha256=hashlib.sha256(manifest).hexdigest(), manifestBytes=len(manifest))
    pin["manifestSignature"].update(sha256=hashlib.sha256(signature).hexdigest(), bytes=len(signature))
    pin["manifestSignature"]["signingKey"].update(sha256=hashlib.sha256(key).hexdigest(), bytes=len(key))
    return pin, {pin["url"]: binary, pin["manifestUrl"]: manifest,
        pin["manifestSignature"]["url"]: signature, pin["manifestSignature"]["signingKey"]["url"]: key}


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

    def test_claude_signature_lock_rejects_missing_or_unbounded_trust_metadata(self):
        code = module()
        original = json.loads(LOCK.read_text())
        mutations = (
            lambda pin: pin.pop("manifestSignature"),
            lambda pin: pin.update(manifestBytes=True),
            lambda pin: pin["manifestSignature"].update(bytes=65537),
            lambda pin: pin["manifestSignature"].update(sha256=""),
            lambda pin: pin["manifestSignature"].update(url="https://github.com/fake.sig"),
            lambda pin: pin["manifestSignature"]["signingKey"].update(fingerprint="BAA929FF1A7ECACE"),
            lambda pin: pin["manifestSignature"]["signingKey"].update(url="https://github.com/fake.asc"),
        )
        for mutation in mutations:
            lock = copy.deepcopy(original)
            mutation(lock["tools"]["claude"])
            with self.assertRaises(RuntimeError):
                code.validate_lock(lock)

    def test_claude_signature_verifier_isolated_keyring_and_identity(self):
        code = module()
        pin, payloads = claude_fixture()
        fingerprint = pin["manifestSignature"]["signingKey"]["fingerprint"]
        valid = "[GNUPG:] VALIDSIG " + fingerprint + " 2026-09-29 1790646440 0 4 0 1 10 00 " + fingerprint + "\n"
        cases = [(0, valid, True), (1, valid, False), (0, "[GNUPG:] GOODSIG unused\n", False),
            (0, valid + valid, False), (0, valid + "[GNUPG:] BADSIG unused\n", False),
            (0, valid.replace(fingerprint, "A" * 40), False), (0, valid.replace("1 10 00", "1 2 00"), False),
            (0, valid + "[GNUPG:] EXPKEYSIG unused\n", False), (0, valid + "unexpected output\n", False)]
        for returncode, status, success in cases:
            with self.subTest(status=status, returncode=returncode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                manifest, signature, key = (root / name for name in ("manifest.json", "manifest.json.sig", "key.asc"))
                manifest.write_bytes(payloads[pin["manifestUrl"]])
                signature.write_bytes(payloads[pin["manifestSignature"]["url"]])
                key.write_bytes(payloads[pin["manifestSignature"]["signingKey"]["url"]])
                def verify(argv, **kwargs):
                    self.assertEqual(argv, ["/usr/bin/gpgv", "--homedir", str((root / "gnupg").resolve()),
                        "--keyring", str((root / "claude-keyring.gpg").resolve()), "--status-fd", "1",
                        str(signature.resolve()), str(manifest.resolve())])
                    self.assertEqual((root / "claude-keyring.gpg").read_bytes(), b"test key transport")
                    self.assertEqual(kwargs["env"], {"PATH": "/usr/bin:/bin", "HOME": str((root / "gnupg").resolve()),
                        "GNUPGHOME": str((root / "gnupg").resolve()), "LANG": "C", "LC_ALL": "C"})
                    self.assertEqual(kwargs["timeout"], 45)
                    self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
                    kwargs["stdout"].write(status.encode())
                    return types.SimpleNamespace(returncode=returncode)
                with patch.object(Path, "is_file", return_value=True), patch.object(code.os, "access", return_value=True), \
                        patch.object(code.subprocess, "run", side_effect=verify):
                    if success:
                        self.assertEqual(code.verify_claude_signature(manifest, signature, key, root, fingerprint), fingerprint)
                    else:
                        with self.assertRaises(RuntimeError):
                            code.verify_claude_signature(manifest, signature, key, root, fingerprint)

    def test_claude_missing_verifier_or_timeout_has_no_fallback(self):
        code = module()
        pin, payloads = claude_fixture()
        for available in (False, True):
            with self.subTest(available=available), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                key = root / "key.asc"
                key.write_bytes(payloads[pin["manifestSignature"]["signingKey"]["url"]])
                with patch.object(Path, "is_file", return_value=available), patch.object(code.os, "access", return_value=available), \
                        patch.object(code.subprocess, "run", side_effect=subprocess.TimeoutExpired("gpgv", 45)) as run:
                    with self.assertRaises((RuntimeError, subprocess.TimeoutExpired)):
                        code.verify_claude_signature(root / "manifest", root / "signature", key, root,
                            pin["manifestSignature"]["signingKey"]["fingerprint"])
                    self.assertEqual(run.call_count, int(available))

    def test_claude_metadata_hashes_fail_before_verifier_binary_or_publication(self):
        for part in ("manifest", "signature", "key"):
            with self.subTest(part=part), tempfile.TemporaryDirectory() as tmp:
                code = module()
                pin, payloads = claude_fixture()
                target = {"manifest": pin["manifestUrl"], "signature": pin["manifestSignature"]["url"],
                    "key": pin["manifestSignature"]["signingKey"]["url"]}[part]
                payloads[target] += b"tampered"
                requests = []
                class Response(io.BytesIO):
                    def geturl(self):
                        return self.url
                def open_response(request, **_kwargs):
                    requests.append(request.full_url)
                    response = Response(payloads[request.full_url]); response.url = request.full_url
                    return response
                opener = types.SimpleNamespace(open=open_response)
                with patch.object(code.urllib.request, "build_opener", return_value=opener), \
                        patch.object(code, "verify_claude_signature") as verify, patch.object(code, "version_check") as version:
                    with self.assertRaises(RuntimeError):
                        code.install_tool(Path(tmp), "claude", pin)
                    verify.assert_not_called(); version.assert_not_called()
                    self.assertNotIn(pin["url"], requests)
                    self.assertFalse((Path(tmp) / ".local/bin/claude").exists())
                    self.assertEqual(list((Path(tmp) / ".local/share/z8/ai/claude").iterdir()), [])

    def test_claude_verified_publication_and_failed_reinstall_preserve_existing(self):
        code = module()
        pin, payloads = claude_fixture()
        fingerprint = pin["manifestSignature"]["signingKey"]["fingerprint"]
        def download(url, target, expected, size, **_kwargs):
            data = payloads[url]
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
            self.assertEqual(len(data), size)
            target.write_bytes(data)
        with tempfile.TemporaryDirectory() as tmp, patch.object(code, "download", side_effect=download), \
                patch.object(code, "verify_claude_signature", return_value=fingerprint) as verify, \
                patch.object(code, "version_check", return_value="2.1.285 (Claude Code)") as version, \
                contextlib.redirect_stdout(io.StringIO()):
            home = Path(tmp)
            code.install_tool(home, "claude", pin)
            launcher = home / ".local/bin/claude"
            installed = launcher.resolve()
            receipt = installed.parent / "receipt.json"
            initial = receipt.read_bytes()
            record = json.loads(initial)["manifestVerification"]
            self.assertEqual(record["primaryFingerprint"], fingerprint)
            self.assertEqual(record["manifestSha256"], pin["manifestSha256"])
            verify.side_effect = RuntimeError("invalid signature")
            version.reset_mock()
            with self.assertRaises(RuntimeError):
                code.install_tool(home, "claude", pin)
            version.assert_not_called()
            self.assertEqual(launcher.resolve(), installed)
            self.assertEqual(installed.read_bytes(), arm64_elf())
            self.assertEqual(receipt.read_bytes(), initial)
            self.assertFalse(list(installed.parent.parent.glob(".install-*")))
            # Editing both a local receipt and binary cannot substitute for the
            # independently signed release pin during an explicit reinstall.
            changed = arm64_elf() + b"user change"
            installed.write_bytes(changed)
            edited = json.loads(initial)
            edited["binarySha256"] = hashlib.sha256(changed).hexdigest()
            receipt.write_text(json.dumps(edited))
            verify.side_effect = None
            with self.assertRaises(RuntimeError):
                code.install_tool(home, "claude", pin)
            version.assert_not_called()
            self.assertEqual(installed.read_bytes(), changed)

    def test_claude_signed_manifest_must_match_pinned_binary_before_execution(self):
        code = module()
        pin, payloads = claude_fixture()
        pin["sha256"] = "0" * 64
        def download(url, target, _hash, _size, **_kwargs):
            target.write_bytes(payloads[url])
        with tempfile.TemporaryDirectory() as tmp, patch.object(code, "download", side_effect=download) as fetch, \
                patch.object(code, "verify_claude_signature", return_value=pin["manifestSignature"]["signingKey"]["fingerprint"]), \
                patch.object(code, "version_check") as version:
            with self.assertRaises(RuntimeError):
                code.install_tool(Path(tmp), "claude", pin)
            version.assert_not_called()
            self.assertEqual(fetch.call_count, 3)
            self.assertFalse((Path(tmp) / ".local/bin/claude").exists())


if __name__ == "__main__":
    unittest.main()
