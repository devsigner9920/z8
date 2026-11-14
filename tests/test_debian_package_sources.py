"""Bind Debian source payloads to exact image/index versions, not Ubuntu mirrors."""
import copy
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import sys
import tempfile
import types
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from release_compliance import package_source_indexes, sha256, json_bytes

spec = importlib.util.spec_from_file_location('debian_package_collector', ROOT / 'tools/collect-release-package-sources.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class DebianPackageSourcesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / 'sources'
        self.payload = b'Original source build fixture\n'
        self.payload_sha = hashlib.sha256(self.payload).hexdigest()
        text = ('Package: sample\nVersion: 1:2.0-1\nDirectory: pool/updates/main/s/sample\n'
                'Checksums-Sha256:\n ' + self.payload_sha + ' ' + str(len(self.payload)) + ' sample_2.0+dfsg-1.dsc\n\n')
        # Official indexes contain large unrelated source packages too. Only
        # installed versions enter this release's bounded payload collection.
        text += ('Package: unrelated\nVersion: 1\nDirectory: pool/main/u/unrelated\n'
                 'Checksums-Sha256:\n ' + 'e' * 64 + ' 900000000 unrelated.tar.xz\n\n')
        self.index = self.root / 'Sources.xz'
        self.index.write_bytes(lzma.compress(text.encode()))
        self.pin = {'archive': 'debian-security', 'suite': 'trixie-security',
            'url': 'https://snapshot.debian.org/archive/debian-security/20261104T212339Z/dists/trixie-security/main/source/Sources.xz',
            'sha256': sha256(self.index), 'bytes': self.index.stat().st_size}
        self.lock = {'schemaVersion': 1, 'distribution': 'debian', 'release': '13.7', 'architecture': 'aarch64',
                     'snapshot': '20261104T212339Z', 'source': {'url': 'https://example.invalid/fixture'},
                     'sourceIndexes': [self.pin]}
        lock_path = self.root / 'runtime/guest/image.lock.json'
        lock_path.parent.mkdir(parents=True)
        lock_path.write_bytes(json_bytes(self.lock))
        relative = 'indexes/debian-security-20261104T212339Z-trixie-security-Sources.xz'
        target = self.out / relative
        target.parent.mkdir(parents=True)
        target.write_bytes(self.index.read_bytes())
        self.index_record = dict(self.pin, path=relative, role='guest-source-index', status='VERIFIED', signatureVerified=False)
        self.package = {'Package': 'libsample', 'Version': '1:2.0-1+b2', 'Source': 'sample (1:2.0-1)', 'Status': 'install ok installed'}
        self.component = collector.distribution_records([self.package], [(self.index, self.pin['url'])], 'debian')[0]
        self.inventory = {'inputs': {'guestDistribution': 'debian', 'guestSourceIndexes': [self.pin]},
                          'components': [self.component], 'sourceIndexes': [self.index_record]}

    def test_exact_source_epoch_binnmu_and_security_snapshot_are_preserved(self):
        self.assertEqual(self.component['sourceName'], 'sample')
        self.assertEqual(self.component['sourceVersion'], '1:2.0-1')
        self.assertEqual(self.component['version'], '1:2.0-1+b2')
        self.assertEqual(self.component['unresolved'], [])
        self.assertEqual(self.component['sourceFiles'][0]['url'],
            'https://snapshot.debian.org/archive/debian-security/20261104T212339Z/pool/updates/main/s/sample/sample_2.0%2Bdfsg-1.dsc')
        self.assertNotIn('ubuntu', self.component['sourceFiles'][0]['url'])
        package_source_indexes(self.inventory, self.out)
        changed = dict(self.package, Source='sample (1:2.0-2)')
        self.assertTrue(collector.distribution_records([changed], [(self.index, self.pin['url'])], 'debian')[0]['unresolved'])

    def test_changed_index_guest_lock_and_false_signature_claim_fail_closed(self):
        collector.debian_indexes(self.root, self.out, self.lock, False)
        changed = copy.deepcopy(self.lock); changed['sourceIndexes'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'differs from the current image lock'):
            collector.debian_indexes(self.root, self.out, changed, False)
        for field, value in [('signatureVerified', True), ('sha256', '0' * 64), ('bytes', self.pin['bytes'] + 1),
                             ('url', self.pin['url'].replace('snapshot.debian.org', 'ports.ubuntu.com'))]:
            changed = copy.deepcopy(self.inventory)
            changed['sourceIndexes'][0][field] = value
            with self.assertRaises(ValueError):
                package_source_indexes(changed, self.out)
        (self.out / self.index_record['path']).write_bytes(b'changed index')
        with self.assertRaisesRegex(ValueError, 'index bytes changed'):
            package_source_indexes(self.inventory, self.out)

    def test_payload_mapping_and_index_cannot_be_stripped_or_repointed(self):
        for edit in ('missing-index', 'different-source-version', 'different-payload', 'wrong-size'):
            changed = copy.deepcopy(self.inventory)
            if edit == 'missing-index': changed['sourceIndexes'] = []
            if edit == 'different-source-version': changed['components'][0]['sourceVersion'] = '2.1'
            if edit == 'different-payload': changed['components'][0]['sourceFiles'][0]['url'] = 'https://example.invalid/source'
            if edit == 'wrong-size': changed['components'][0]['sourceFiles'][0]['bytes'] += 1
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                package_source_indexes(changed, self.out)

    def test_actual_guest_collection_retains_original_notices_and_does_not_approve_closure(self):
        guest = self.root / 'guest'
        guest.mkdir()
        archive = guest / 'rootfs.zip'
        status = '\n'.join(key + ': ' + value for key, value in self.package.items()) + '\n\n'
        original = b'Original Debian package copyright\n'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('var/lib/dpkg/status', status)
            z.writestr('usr/share/doc/libsample/copyright', original)
        manifest = guest / 'manifest.json'
        manifest.write_bytes(json_bytes(dict(self.lock, archive='rootfs.zip', archiveSha256=sha256(archive))))
        target = self.out / 'downloads' / self.payload_sha / 'sample_2.0+dfsg-1.dsc'
        target.parent.mkdir(parents=True)
        target.write_bytes(self.payload)
        args = types.SimpleNamespace(root=self.root, output=self.out, runtime_manifest=None, guest_manifest=manifest,
                                     ubuntu_index=[], fetch=False)
        report = collector.collect(args)
        self.assertEqual(report['status'], 'COLLECTED')
        self.assertIs(report['legalCompletenessReviewed'], False)
        self.assertEqual(report['inputs']['guestArchiveSha256'], sha256(archive))
        self.assertEqual(report['sourceIndexes'][0]['sha256'], self.pin['sha256'])
        notice = self.out / report['installedNotices'][0]['path']
        self.assertEqual(notice.read_bytes(), original)
        package_source_indexes(report, self.out)


if __name__ == '__main__':
    unittest.main()
