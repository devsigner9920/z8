import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import source_archive


class ExportedSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'upstream/termux-app'
        self.source.mkdir(parents=True)
        self.data = b'#!/bin/sh\necho fixture\n'
        (self.source / 'gradlew').write_bytes(self.data)
        self.records = [{'path': 'upstream/termux-app/gradlew', 'type': 'file',
                         'mode': 0o775, 'bytes': len(self.data),
                         'sha256': hashlib.sha256(self.data).hexdigest()}]
        self.write_manifest()

    def write_manifest(self):
        encoded = (json.dumps(self.records, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
        self.manifest = {'schemaVersion': 1, 'kind': 'z8-release-source',
                         'sourceLock': {'termuxApp': {'commit': 'a' * 40}},
                         'files': self.records, 'sourceInputSha256': hashlib.sha256(encoded).hexdigest()}
        (self.root / 'SOURCE_MANIFEST.json').write_text(json.dumps(self.manifest))

    def verify(self, commit='a' * 40):
        return source_archive.exported_app_files(self.source, commit)

    def test_export_needs_no_git_and_keeps_expected_executable_mode(self):
        self.assertEqual(self.verify(), (['gradlew'], {'gradlew': 0o775}))
        spec = importlib.util.spec_from_file_location('prepare_export_test', ROOT / 'tools/prepare-app.py')
        prepare = importlib.util.module_from_spec(spec); spec.loader.exec_module(prepare)
        names = prepare.verify_source(self.source, 'a' * 40, 'nonexistent-git')
        output = self.root / 'output'
        prepare.copy_tracked(self.source, output, names)
        self.assertEqual((output / 'gradlew').read_bytes(), self.data)
        self.assertEqual((output / 'gradlew').stat().st_mode & 0o777, 0o775)

    def test_identity_and_inventory_corruption_are_rejected(self):
        with self.assertRaises(ValueError): self.verify('b' * 40)
        self.manifest['sourceInputSha256'] = '0' * 64
        (self.root / 'SOURCE_MANIFEST.json').write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError): self.verify()

    def test_changed_missing_and_unlisted_upstream_files_are_rejected(self):
        (self.source / 'gradlew').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.verify()
        (self.source / 'gradlew').unlink()
        with self.assertRaises(ValueError): self.verify()
        (self.source / 'gradlew').write_bytes(self.data)
        (self.source / 'unexpected').write_text('extra')
        with self.assertRaises(ValueError): self.verify()

    def test_symlink_and_escape_are_rejected(self):
        (self.source / 'gradlew').unlink()
        outside = self.root / 'outside'; outside.write_bytes(self.data)
        (self.source / 'gradlew').symlink_to(outside)
        with self.assertRaises(ValueError): self.verify()
        (self.source / 'gradlew').unlink(); (self.source / 'gradlew').write_bytes(self.data)
        self.records.append(dict(self.records[0], path='upstream/termux-app/../escape'))
        self.write_manifest()
        with self.assertRaises(ValueError): self.verify()

    def test_duplicate_path_and_special_permissions_are_rejected(self):
        self.records.append(dict(self.records[0])); self.write_manifest()
        with self.assertRaises(ValueError): self.verify()
        self.records.pop(); self.records[0]['mode'] = 0o4755; self.write_manifest()
        with self.assertRaises(ValueError): self.verify()

    def test_user_overlay_changes_do_not_require_mutating_upstream(self):
        (self.root / 'overlay').mkdir()
        (self.root / 'overlay/custom.java').write_text('user changes')
        self.assertEqual(self.verify()[0], ['gradlew'])


if __name__ == '__main__':
    unittest.main()
