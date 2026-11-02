"""Exercise the public export boundary using real files, archives and symlinks."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
SPEC = importlib.util.spec_from_file_location('public_repo', ROOT / 'tools/prepare-public-repo.py')
public = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(public)


class PublicSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in public.REQUIRED:
            self.write(name, 'public fixture\n')

    def write(self, name, content):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return target

    def export(self, name='out'):
        return public.prepare(self.root, self.root / name)

    def test_complete_public_documents_and_build_inputs_without_private_evidence(self):
        self.write('LICENSES/upstream.txt', 'original notice')
        self.write('.github/workflows/source-checks.yml', 'name: fixture')
        self.write('tools/helper.py', 'print("build input")')
        self.write('docs/design/brand/source.svg', '<svg/>')
        for name in ('reports/private.txt', 'artifacts/test.apk', '.git/config',
                     'release/decisions.json', 'tools/credentials-work.json',
                     'tools/.env.production', 'tools/.ssh/config',
                     'tools/signing.key', '.local/auth.json',
                     'overlay/app/src/main/assets/z8-licenses/release-notices.json'):
            self.write(name, 'must never be exported')
        result = self.export()
        with zipfile.ZipFile(result['archive']) as bundle:
            names = set(bundle.namelist())
            self.assertEqual(names, {item['path'] for item in result['files']})
            for name in public.REQUIRED + ('LICENSES/upstream.txt', '.github/workflows/source-checks.yml',
                                          'tools/helper.py', 'docs/design/brand/source.svg'):
                self.assertIn(name, names)
                self.assertEqual(bundle.read(name), (self.root / name).read_bytes())
            self.assertNotIn('tools/credentials-work.json', names)
            self.assertFalse(any('must never' in bundle.read(name).decode() for name in names))
        self.assertFalse(result['published'])
        self.assertFalse(result['includesBundledPackageSources'])
        self.assertTrue(result['scan']['manualReviewStillRequired'])

    def test_token_in_ordinary_file_blocks_export_without_printing_secret(self):
        token = 'gh' + 'p_' + 'A' * 40
        self.write('tools/helper.py', 'TOKEN = ' + repr(token))
        with self.assertRaises(ValueError) as caught:
            self.export()
        self.assertIn('github-token: tools/helper.py', str(caught.exception))
        self.assertNotIn(token, str(caught.exception))
        self.assertFalse((self.root / 'out').exists())

    def test_private_key_in_ordinary_file_blocks_export(self):
        self.write('docs/example.txt', '-----BEGIN ' + 'PRIVATE KEY-----\nfixture')
        with self.assertRaisesRegex(ValueError, 'private-key: docs/example.txt'):
            self.export()

    def test_source_directory_or_release_parent_symlinks_are_not_followed(self):
        outside = self.root / 'external'
        outside.mkdir()
        (self.root / 'docs').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.export()
        (self.root / 'docs').unlink()
        (self.root / 'release/config.json').unlink()
        (self.root / 'release').rmdir()
        (outside / 'config.json').write_text('not public')
        (self.root / 'release').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.export()

    def test_missing_license_prevents_export(self):
        (self.root / 'LICENSE').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing public source files: LICENSE'):
            self.export()

    def test_archives_are_deterministic_preserve_modes_and_never_overwrite(self):
        script = self.write('tools/run.sh', '#!/bin/sh\nexit 0\n')
        script.chmod(0o755)
        first, second = self.export('out1'), self.export('out2')
        self.assertEqual(Path(first['archive']).read_bytes(), Path(second['archive']).read_bytes())
        self.assertEqual((Path(first['directory']) / 'tools/run.sh').stat().st_mode & 0o777, 0o755)
        self.assertEqual(json.loads(Path(first['manifest']).read_text())['fileCount'], first['fileCount'])
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.export('out1')

    def test_outputs_cannot_be_in_source_tree_or_follow_symlinks(self):
        with self.assertRaisesRegex(ValueError, 'outside the public source'):
            public.prepare(self.root, self.root / 'docs/export')
        (self.root / 'out').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink output'):
            self.export()


if __name__ == '__main__':
    unittest.main()
