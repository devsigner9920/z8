"""Guest archive/execution-boundary contracts; no real guest is run by tests."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_guest", ROOT / "tools/prepare-guest.py")
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class GuestNormalization(unittest.TestCase):
    def archive(self, root, members):
        archive = root / "input.tar.gz"
        with tarfile.open(archive, "w:gz") as out:
            for name, kind, data in members:
                info = tarfile.TarInfo(name)
                info.mode = 0o4755
                info.type = kind
                if kind == tarfile.REGTYPE:
                    info.size = len(data)
                    out.addfile(info, io.BytesIO(data))
                else:
                    if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                        info.linkname = data
                    out.addfile(info)
        return archive

    def base(self):
        return [("etc/", tarfile.DIRTYPE, ""), ("usr/", tarfile.DIRTYPE, ""),
                ("usr/bin/", tarfile.DIRTYPE, ""), ("usr/bin/tool", tarfile.REGTYPE, b"tool")]

    def test_safe_absolute_links_hardlinks_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.archive(Path(tmp), self.base() + [("bin", tarfile.SYMTYPE, "/usr/bin"), ("usr/bin/tool-copy", tarfile.LNKTYPE, "usr/bin/tool")])
            result = guest.normalize(source)
            self.assertEqual(result["usr/bin/tool"]["mode"], 0o755)
            self.assertEqual(result["usr/bin/tool-copy"]["data"], b"tool")
            self.assertIn(b"usr/bin\xe2\x86\x90bin\n", result["SYMLINKS.txt"]["data"])
            self.assertEqual(result["etc/z8/guest-target"]["data"], b"z8-guest-v1\n")
            self.assertNotIn("bin", result)

    def test_traversal_special_files_and_link_ancestors_rejected(self):
        cases = [
            [("../escape", tarfile.REGTYPE, b"x")],
            [("/absolute", tarfile.REGTYPE, b"x")],
            [("dev/null", tarfile.CHRTYPE, "")],
            [("escape", tarfile.SYMTYPE, "../outside")],
            [("bin", tarfile.SYMTYPE, "usr/bin"), ("bin/child", tarfile.REGTYPE, b"x")],
            [("first", tarfile.SYMTYPE, "second"), ("second", tarfile.SYMTYPE, "first")],
        ]
        for members in cases:
            with self.subTest(members=members), tempfile.TemporaryDirectory() as tmp:
                source = self.archive(Path(tmp), self.base() + members)
                with self.assertRaises(guest.GuestError):
                    guest.normalize(source)

    def test_link_graph_checks_dotdot_after_indirection(self):
        entries = {"a/": {"type": "directory"}, "a/b/": {"type": "directory"}}
        with self.assertRaises(guest.GuestError):
            guest.validate_links({"a/b/link": "../../top/../outside", "top": "."}, entries)
        with self.assertRaises(guest.GuestError):
            guest.validate_links({}, {"file": {"type": "file"}, "file/": {"type": "directory"}})

    def test_sudo_hint_patch_preserves_every_other_upstream_byte(self):
        prefix = b"# other Ubuntu startup behavior\nshopt -s checkwinsize\n\n"
        suffix = b"\n# unrelated errors must remain visible\nprintf 'other-error\\n' >&2\n"
        original = prefix + guest.UBUNTU_SUDO_HINT + suffix
        with tempfile.TemporaryDirectory() as tmp:
            source = self.archive(Path(tmp), self.base() + [("etc/bash.bashrc", tarfile.REGTYPE, original)])
            normalized = guest.normalize(source)["etc/bash.bashrc"]["data"]
        expected = original.replace(b'if [ ! -e "$HOME/.sudo_as_admin_successful" ]',
            b'if [ "$EUID" -ne 0 ] && [ ! -e "$HOME/.sudo_as_admin_successful" ]', 1)
        self.assertTrue(normalized.startswith(expected + b"\n# z8 interactive defaults"))
        self.assertEqual(guest.normalize_ubuntu_sudo_hint(original), expected)

    def test_root_hint_skips_groups_but_other_stderr_and_nonroot_behavior_remain(self):
        patched = guest.normalize_ubuntu_sudo_hint(guest.UBUNTU_SUDO_HINT)
        for euid in (0, 1000):
            with self.subTest(euid=euid), tempfile.TemporaryDirectory() as tmp:
                # Bash owns the readonly EUID variable. Substitute its reported
                # value to exercise both guest identities without host root or
                # PRoot; the rest of the exact normalized block runs unchanged.
                snippet = patched.replace(b'"$EUID"', str(euid).encode(), 1).decode()
                script = '''groups() {
    printf 'called\\n' >> "$HOME/groups-called"
    printf 'unmapped-group-warning\\n' >&2
    printf 'ordinary-group\\n'
}
printf 'before-error\\n' >&2
''' + snippet + "printf 'after-error\\n' >&2\n"
                result = subprocess.run(["bash", "--noprofile", "--norc", "-p", "-c", script],
                    env=dict(os.environ, HOME=tmp), capture_output=True, text=True, check=True)
                self.assertEqual((Path(tmp) / "groups-called").exists(), euid != 0)
                self.assertEqual(result.stderr, "before-error\n" +
                    ("unmapped-group-warning\n" if euid else "") + "after-error\n")

    def test_changed_sudo_hint_fails_closed_but_absent_hint_is_supported(self):
        for changed in (guest.UBUNTU_SUDO_HINT.replace(b"$(groups)", b"$(id -Gn)"),
                        guest.UBUNTU_SUDO_HINT + guest.UBUNTU_SUDO_HINT):
            with self.assertRaisesRegex(guest.GuestError, "sudo hint block changed"):
                guest.normalize_ubuntu_sudo_hint(changed)
        minimal = b"# minimal fixture bashrc\nPS1='fixture> '\n"
        self.assertEqual(guest.normalize_ubuntu_sudo_hint(minimal), minimal)
        with tempfile.TemporaryDirectory() as tmp:
            source = self.archive(Path(tmp), self.base() + [("etc/bash.bashrc", tarfile.REGTYPE, minimal)])
            self.assertTrue(guest.normalize(source)["etc/bash.bashrc"]["data"].startswith(minimal))


class LaunchRecipe(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.rootfs = self.root / "rootfs"
        self.home_dir = self.root / "private home"
        self.source = self.root / "project source"
        self.scratch = self.root / "scratch"
        for path in (self.home_dir, self.source, self.scratch):
            path.mkdir()
        for path in ("etc/z8", "dev/pts", "dev/shm", "proc", "tmp", "run/z8/attention", "z8/home", "workspace"):
            (self.rootfs / path).mkdir(parents=True, exist_ok=True)
        (self.rootfs / "etc/z8/guest-target").write_text("z8-guest-v1\n")
        self.arguments = ["bash", "-p", str(ROOT / "runtime/guest/launch.sh"), "--rootfs", str(self.rootfs),
                          "--home", str(self.home_dir), "--source", str(self.source), "--temp", str(self.scratch)]

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_preserves_quoted_argv_and_has_no_side_effect(self):
        result = subprocess.run(self.arguments, capture_output=True, text=True, check=True)
        args = [shlex.split(line)[0] for line in result.stdout.splitlines() if line.startswith("  ")]
        self.assertEqual(args[0], "/data/data/dev.devsigner.z8/files/usr/bin/proot")
        self.assertIn(str(self.home_dir.resolve()) + ":/z8/home", args)
        self.assertIn(str(self.source.resolve()) + ":/workspace", args)
        self.assertEqual(args[-2:], ["/bin/bash", "--login"])
        self.assertIn("--kill-on-exit", args)
        self.assertNotIn("-R", args)
        self.assertNotIn("-S", args)
        self.assertNotIn("-k", args)
        self.assertEqual(list(self.home_dir.iterdir()), [])
        self.assertEqual(list(self.source.iterdir()), [])
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_hooks_never_print_nonce_or_bind_journal(self):
        transport = self.root / "attention/transport"
        transport.mkdir(parents=True)
        token = "a" * 64
        result = subprocess.run(self.arguments + ["--hooks-transport", str(transport)], capture_output=True, text=True,
                                env=dict(os.environ, Z8_LAUNCH_ID="launch-1", Z8_EVENT_TOKEN=token), check=True)
        self.assertNotIn(token, result.stdout + result.stderr)
        self.assertIn(str(transport) + ":/run/z8/attention", result.stdout)
        self.assertNotIn(str(transport.parent) + ":", result.stdout)

    def test_source_traversal_and_overlapping_storage_rejected(self):
        for extra in (["--cwd", "/workspace/../rootfs"], ["--home", str(self.source)], ["--cwd", "/root"]):
            result = subprocess.run(self.arguments + extra, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
        outside = self.root / "outside"
        outside.mkdir()
        (self.source / "link").symlink_to(outside, target_is_directory=True)
        result = subprocess.run(self.arguments + ["--cwd", "/workspace/link"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
