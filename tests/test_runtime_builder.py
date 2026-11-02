"""Own-prefix supply contracts using executable shell stubs and ZIP fixtures."""
import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_runtime", ROOT / "tools/prepare-runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeSupplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.tree = self.root / "source"
        self.tree.mkdir()
        self.lock = json.loads((ROOT / "tools/sources.lock.json").read_text())
        self.builder = json.loads((ROOT / "runtime/builder.lock.json").read_text())

    def tearDown(self):
        self.temp.cleanup()

    def overlay(self, profile="core"):
        upstream = ROOT / "upstream/termux-packages"
        if not (upstream / "scripts/properties.sh").exists():
            self.skipTest("Pinned termux-packages checkout required")
        for name in ("scripts/properties.sh", "scripts/build/termux_download_deb_pac.sh",
                     "scripts/build/toolchain/termux_setup_toolchain_30.sh",
                     "packages/bash/build.sh",
                     "scripts/build/termux_get_repo_files.sh", "packages/apt/build.sh",
                     "packages/termux-tools/build.sh", "scripts/build-bootstraps.sh"):
            target = self.tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(upstream / name, target)
        (self.tree / "packages/proot").mkdir(parents=True, exist_ok=True)
        runtime.apply_overlay(self.tree, self.lock, self.builder, profile)

    def test_guest_loader_default_is_apk_owned_without_changing_build_output(self):
        self.overlay()
        patch = (self.tree / "packages/proot/z8-apk-loader.patch").read_text()
        self.assertIn('/data/data/dev.devsigner.z8/files/applib/libproot-loader.so', patch)
        self.assertIn('getenv("PROOT_LOADER")', patch)
        self.assertNotIn('com.termux', patch)

    def test_verified_dependency_seed_excludes_proot_and_rejects_changed_output(self):
        manifest = ROOT / 'artifacts/runtime/core-360af8dad27815ef/manifest.json'
        if not manifest.exists(): self.skipTest('Published own-prefix dependency seed required')
        self.overlay()
        runtime.seed_runtime(ROOT, manifest, self.tree, self.lock, self.builder, 'core')
        seed = json.loads((self.tree / 'z8-dependency-seed.json').read_text())
        self.assertGreater(len(seed['packages']), 10)
        self.assertEqual(seed['rebuiltPackages'], ['proot'])
        self.assertTrue(all(not p['archive'].startswith('proot_') for p in seed['packages']))
        changed = self.tree / 'output' / seed['packages'][0]['archive']
        changed.write_bytes(b'changed-package')
        with self.assertRaisesRegex(runtime.RuntimeError, 'Existing output differs'):
            runtime.seed_runtime(ROOT, manifest, self.tree, self.lock, self.builder, 'core')

    def test_repository_fetchers_fail_before_network(self):
        self.overlay()
        for function, script in (("termux_download_deb_pac", "termux_download_deb_pac.sh"),
                                 ("termux_get_repo_files", "termux_get_repo_files.sh")):
            result = subprocess.run(["bash", "-c", 'source "$1"; "$2" bash aarch64 1',
                "test", str(self.tree / "scripts/build" / script), function], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("stock-prefix repository access is disabled", result.stderr)

    def test_host_apt_output_has_no_active_repository(self):
        self.overlay("workspace")
        prefix = self.root / "prefix"
        for name in ("etc/apt", "lib/apt/methods"):
            (prefix / name).mkdir(parents=True, exist_ok=True)
        # Execute the patched upstream install hook with only its scratch prefix.
        result = subprocess.run(["bash", "-c",
            'TERMUX_PREFIX="$1"; source "$2"; termux_step_post_make_install', "test", str(prefix),
            str(self.tree / "packages/apt/build.sh")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = (prefix / "etc/apt/sources.list").read_text().splitlines()
        self.assertTrue(lines)
        self.assertTrue(all(not line.strip() or line.lstrip().startswith("#") for line in lines))

    def fixture(self, apt_source=None):
        (self.root / "tools").mkdir()
        shutil.copy2(ROOT / "tools/prepare-app.py", self.root / "tools/prepare-app.py")
        shutil.copy2(ROOT / "tools/release_config.py", self.root / "tools/release_config.py")
        shutil.copy2(ROOT / "tools/prepare-runtime.py", self.root / "tools/prepare-runtime.py")
        header = bytearray(64)
        header[:6] = b"\x7fELF\x02\x01"
        header[18:20] = (183).to_bytes(2, "little")
        with zipfile.ZipFile(self.tree / "bootstrap-aarch64.zip", "w") as bundle:
            for name in ("bin/bash", "bin/tmux", "libexec/proot/loader"):
                bundle.writestr(name, header)
            loader = str(Path(self.lock["prefix"]).parent / "applib/libproot-loader.so")
            bundle.writestr("bin/proot", header + loader.encode() + b"\0")
            bundle.writestr("SYMLINKS.txt", "bash←bin/sh\n")
            if apt_source is not None:
                bundle.writestr("etc/apt/sources.list", apt_source)

    def test_publish_rejects_repository_and_leaves_no_manifest(self):
        self.fixture("deb https://packages.termux.dev/apt/termux-main stable main\n")
        with self.assertRaisesRegex(runtime.RuntimeError, "unverified package repository"):
            runtime.publish(self.root, self.root, self.tree, self.lock, self.builder, "core", "fixture", [])
        self.assertFalse((self.root / "artifacts").exists())

    def test_publication_keeps_runtime_and_execution_evidence_separate(self):
        self.fixture("# No z8 repository configured\n")
        manifest = runtime.publish(self.root, self.root, self.tree, self.lock, self.builder, "core", "fixture", [])
        data = json.loads(manifest.read_text())
        evidence = json.loads((manifest.parent / "provenance.json").read_text())
        self.assertEqual(data["termuxPackagesCommit"], self.lock["termuxPackages"]["commit"])
        self.assertEqual(data["sha256"], runtime.digest(manifest.parent / data["archive"]))
        self.assertEqual(evidence["deviceExecution"], "NOT_TESTED")
        self.assertEqual(evidence["bitReproducibility"], "NOT_MEASURED")
        self.assertEqual(evidence["androidExecution"]["apkLibraryName"], "libproot-loader.so")

    def test_missing_soname_is_rejected_but_android_libc_is_allowed(self):
        self.fixture()
        def elf(name, alignment=16384):
            data = bytearray(512)
            data[:6] = b"\x7fELF\x02\x01"
            struct.pack_into("<Q", data, 32, 64)
            struct.pack_into("<HH", data, 54, 56, 2)
            struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, 0, 0, 0, 512, 512, alignment)
            struct.pack_into("<IIQQQQQQ", data, 120, 2, 6, 256, 256, 256, 48, 48, 8)
            struct.pack_into("<qQqQqQ", data, 256, 5, 400, 1, 0, 0, 0)
            encoded = name.encode() + b"\0"
            data[400:400 + len(encoded)] = encoded
            return data
        self.assertEqual(runtime.elf_dependencies(elf("libc.so")), (["libc.so"], None))
        with zipfile.ZipFile(self.tree / "dependency.zip", "w") as bundle:
            bundle.writestr("bin/probe", elf("libmissing.so"))
            bundle.writestr("SYMLINKS.txt", "probe←bin/probe-link\n")
        with zipfile.ZipFile(self.tree / "dependency.zip") as bundle:
            with self.assertRaisesRegex(runtime.RuntimeError, "libmissing.so"):
                runtime.verify_host_linkage(bundle)
        with zipfile.ZipFile(self.tree / "system.zip", "w") as bundle:
            bundle.writestr("bin/probe", elf("libc.so"))
            bundle.writestr("SYMLINKS.txt", "probe←bin/probe-link\n")
        with zipfile.ZipFile(self.tree / "system.zip") as bundle:
            self.assertEqual(runtime.verify_host_linkage(bundle)["missingSonames"], [])
        with zipfile.ZipFile(self.tree / "incompatible-page.zip", "w") as bundle:
            bundle.writestr("bin/probe", elf("libc.so", 4096))
            bundle.writestr("SYMLINKS.txt", "probe←bin/probe-link\n")
        with zipfile.ZipFile(self.tree / "incompatible-page.zip") as bundle:
            with self.assertRaisesRegex(runtime.RuntimeError, "not 16 KiB page compatible"):
                runtime.verify_host_linkage(bundle)

    def test_comment_normalization_refuses_uninspected_shell_content(self):
        self.fixture()
        with zipfile.ZipFile(self.tree / "bootstrap-aarch64.zip", "a") as bundle:
            bundle.writestr("bin/termux-exec-ld-preload-lib", "exec /data/data/com.termux/files/usr/bin/bash\n")
        with self.assertRaisesRegex(runtime.RuntimeError, "Unrecognized upstream comment example file"):
            runtime.publish(self.root, self.root, self.tree, self.lock, self.builder, "core", "fixture", [])
        self.assertFalse((self.root / "artifacts").exists())

    def test_only_named_optional_sanitizer_fixture_is_excluded(self):
        self.fixture()
        data = bytearray(512)
        data[:6] = b"\x7fELF\x02\x01"
        data[18:20] = (183).to_bytes(2, "little")
        struct.pack_into("<Q", data, 32, 64)
        struct.pack_into("<HH", data, 54, 56, 2)
        struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, 0, 0, 0, 512, 512, 16384)
        struct.pack_into("<IIQQQQQQ", data, 120, 2, 6, 256, 256, 256, 48, 48, 8)
        struct.pack_into("<qQqQqQ", data, 256, 5, 400, 1, 0, 0, 0)
        needed = b"libclang_rt.asan-aarch64-android.so\0"
        data[400:400 + len(needed)] = needed
        name = runtime.OPTIONAL_SANITIZER_TESTS[0]
        raw = self.tree / "bootstrap-aarch64.zip"
        with zipfile.ZipFile(raw, "a") as bundle:
            bundle.writestr(name, data)
        before = runtime.digest(raw)
        manifest = runtime.publish(self.root, self.root, self.tree, self.lock, self.builder, "core", "fixture", [])
        self.assertEqual(runtime.digest(raw), before)
        evidence = json.loads((manifest.parent / "provenance.json").read_text())
        self.assertEqual(evidence["excludedOptionalFiles"], [name])
        self.assertEqual(evidence["excludedOptionalFileDetails"][0]["sha256"], hashlib.sha256(data).hexdigest())
        with zipfile.ZipFile(manifest.parent / "bootstrap-aarch64.zip") as bundle:
            self.assertNotIn(name, bundle.namelist())
        # The same dependency in a production file must still fail validation.
        with zipfile.ZipFile(raw, "a") as bundle:
            bundle.writestr("bin/production-fsanitize", data)
        with self.assertRaisesRegex(runtime.RuntimeError, "Missing runtime libraries in bin/production-fsanitize"):
            runtime.publish(self.root, self.root, self.tree, self.lock, self.builder, "core", "fixture", [])

    def test_optional_arm32_loader_exclusion_preserves_raw_archive(self):
        self.fixture()
        helper = bytearray(52)
        helper[:6] = b"\x7fELF\x01\x01"
        helper[18:20] = (40).to_bytes(2, "little")
        raw = self.tree / "bootstrap-aarch64.zip"
        with zipfile.ZipFile(raw, "a") as bundle:
            bundle.writestr("libexec/proot/loader32", helper)
            path = self.lock["prefix"] + "/libexec/proot/loader32"
            bundle.writestr("var/lib/dpkg/info/proot.list", path + "\n" + self.lock["prefix"] + "/bin/proot\n")
            bundle.writestr("var/lib/dpkg/info/proot.md5sums", hashlib.md5(helper).hexdigest() + "  " + path.lstrip("/") + "\n")
        before = runtime.digest(raw)
        manifest = runtime.publish(self.root, self.root, self.tree, self.lock, self.builder, "core", "fixture", [])
        self.assertEqual(runtime.digest(raw), before)
        data = json.loads(manifest.read_text())
        evidence = json.loads((manifest.parent / "provenance.json").read_text())
        self.assertEqual(evidence["rawArchiveSha256"], before)
        self.assertEqual(evidence["excludedOptionalFiles"], ["libexec/proot/loader32"])
        self.assertEqual(len(evidence["normalizedPackageMetadata"]), 2)
        with zipfile.ZipFile(manifest.parent / data["archive"]) as bundle:
            self.assertNotIn("libexec/proot/loader32", bundle.namelist())
            self.assertNotIn(b"loader32", bundle.read("var/lib/dpkg/info/proot.list"))
            self.assertEqual(bundle.read("var/lib/dpkg/info/proot.md5sums"), b"")
            with zipfile.ZipFile(raw) as original:
                self.assertEqual(bundle.read("bin/bash"), original.read("bin/bash"))


if __name__ == "__main__":
    unittest.main()
