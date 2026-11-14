"""Explicit probe verification must not execute unverified inputs or overwrite evidence."""
import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('verify_coroutines_probe', ROOT / 'tools/verify-coroutines-probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class CoroutinesProbeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.raw = b'verified compiler fixture'
        self.record = ('example', 'compiler', '1', len(self.raw), hashlib.sha256(self.raw).hexdigest())
        self.filename = self.root / 'compiler-1.jar'

    def test_missing_compiler_is_not_downloaded_without_explicit_flag(self):
        with mock.patch.object(probe, 'TOOLCHAIN', [self.record]), mock.patch('urllib.request.build_opener') as network:
            with self.assertRaisesRegex(ValueError, 'explicitly use --fetch-toolchain'):
                probe.toolchain(self.root, False)
            network.assert_not_called()

    def test_wrong_cached_compiler_is_rejected_without_overwriting_it(self):
        self.filename.write_bytes(b'changed compiler')
        with mock.patch.object(probe, 'TOOLCHAIN', [self.record]), mock.patch('urllib.request.build_opener') as network:
            with self.assertRaisesRegex(ValueError, 'hash/size mismatch'):
                probe.toolchain(self.root, True)
            network.assert_not_called()
        self.assertEqual(self.filename.read_bytes(), b'changed compiler')

    def test_symlink_compiler_is_rejected_even_when_target_bytes_match(self):
        target = self.root / 'other.jar'; target.write_bytes(self.raw)
        self.filename.symlink_to(target)
        with mock.patch.object(probe, 'TOOLCHAIN', [self.record]):
            with self.assertRaisesRegex(ValueError, 'symlink'):
                probe.toolchain(self.root, False)

    def test_wrong_download_is_never_written_as_verified_compiler(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = 'https://repo.maven.apache.org/maven2/example/compiler/1/compiler-1.jar'
        response.read.return_value = self.raw + b'unexpected bytes'
        opener = mock.Mock(); opener.open.return_value = response
        with mock.patch.object(probe, 'TOOLCHAIN', [self.record]), mock.patch('urllib.request.build_opener', return_value=opener):
            with self.assertRaisesRegex(ValueError, 'download hash/size mismatch'):
                probe.toolchain(self.root, True)
        self.assertFalse(self.filename.exists())

    def test_existing_verification_output_is_preserved_without_compiling(self):
        output = self.root / 'existing'; output.mkdir(); (output / 'evidence').write_text('preserve')
        java_home = self.root / 'jdk'; (java_home / 'bin').mkdir(parents=True); (java_home / 'bin/java').write_text('fixture')
        args = types.SimpleNamespace(maven_sources=self.root / 'inventory.json', toolchain_dir=self.root,
                                     fetch_toolchain=False, java_home=java_home, output=output)
        with mock.patch.object(probe, 'retained_inputs', return_value=(b'source', b'class', self.root / 'core.jar', {})), \
                mock.patch.object(probe, 'toolchain', return_value=({}, [])), mock.patch.object(subprocess, 'run') as run:
            with self.assertRaises(FileExistsError):
                probe.verify(args)
            run.assert_not_called()
        self.assertEqual((output / 'evidence').read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
