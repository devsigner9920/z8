"""An embedded-source fallback must preserve original bytes, provenance and terms."""
import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import embedded_maven_source as embedded
from release_compliance import maven_source_inventory


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = load('collect-maven-sources')
notices = load('generate-release-notices')


def zipped(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return output.getvalue()


def record(headers, text=b''):
    headers = dict(headers)
    if text:
        headers.update({'Text-content-length': str(len(text)), 'Content-length': str(len(text)),
                        'Text-content-md5': hashlib.md5(text).hexdigest()})
    return ('\n'.join(key + ': ' + str(value) for key, value in headers.items()) + '\n\n').encode() + text + b'\n'


class EmbeddedSourcesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.java = {'example/Library%02d.java' % i: b'package example; /* fixture */' for i in range(28)}
        for name in ('GuardedBy', 'Immutable', 'NotThreadSafe'):
            self.java['javax/annotation/concurrent/' + name + '.java'] = (
                b'/* Copyright fixture; Creative Commons Attribution License\n'
                b' * http://creativecommons.org/licenses/by/2.5 */\n')
        self.members = dict(self.java, **{'META-INF/MANIFEST.MF': b'Manifest-Version: 1.0\n'})
        self.members.update({name.removesuffix('.java') + '.class': b'fixture class' for name in self.java})
        self.members.update({'example/Library00$Nested%d.class' % i: b'fixture inner class' for i in range(4)})
        self.binary = self.root / 'jsr305-1.3.9.jar'
        self.binary.write_bytes(zipped(self.members))
        # Exercise a real directory copy and deletion in the preserved revision.
        dump = record({'SVN-fs-dump-format-version': '2'}) + record({'Revision-number': 0})
        dump += record({'Revision-number': 1})
        files = {'source/java/' + name: data for name, data in self.java.items()}
        files.update({'trunk/pom.xml': b'<project/>', 'trunk/ri/pom.xml': b'<project/>',
                      'trunk/ri/build.xml': b'<project name="original"/>',
                      'trunk/ri/LICENSE': b'Original BSD-3-Clause fixture license\n'})
        for name, data in files.items():
            dump += record({'Node-path': name, 'Node-kind': 'file', 'Node-action': 'add'}, data)
        dump += record({'Node-path': 'trunk/ri/src/main/resources', 'Node-kind': 'dir', 'Node-action': 'add'})
        dump += record({'Revision-number': 2})
        dump += record({'Node-path': embedded.SOURCE_PREFIX.rstrip('/'), 'Node-kind': 'dir', 'Node-action': 'add',
                        'Node-copyfrom-rev': 1, 'Node-copyfrom-path': 'source/java'})
        dump += record({'Node-path': 'source/java', 'Node-kind': 'dir', 'Node-action': 'delete'})
        dump += record({'Revision-number': 49})
        self.dump_bytes = dump
        self.dump = self.root / 'repo.svndump.gz'
        self.dump.write_bytes(gzip.compress(dump))
        patcher = mock.patch.multiple(embedded, BINARY_SHA256=collector.sha256(self.binary), DUMP_SHA256=collector.sha256(self.dump))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.pom = self.root / 'jsr305.pom'
        self.pom.write_text('<project><licenses><license><name>Apache-2.0</name></license></licenses></project>')
        item = dict(zip(('group', 'name', 'version'), embedded.COORDINATE))
        self.mapping_entry = dict(item, type=embedded.MAPPING_TYPE, revision=49,
            binaryArtifactSha256=[embedded.BINARY_SHA256],
            sourceArchive={'path': self.binary.name, 'sha256': embedded.BINARY_SHA256, 'url': embedded.BINARY_URL},
            upstreamArchive={'path': self.dump.name, 'sha256': embedded.DUMP_SHA256, 'url': embedded.DUMP_URL},
            metadataPom={'path': self.pom.name, 'sha256': collector.sha256(self.pom)})
        self.mapping = self.root / 'mappings.json'
        self.write_mapping()
        self.gradle = self.root / 'gradle-artifacts.json'
        self.gradle.write_text(json.dumps({'kind': 'z8-gradle-runtime-artifacts', 'configuration': 'releaseRuntimeClasspath',
            'components': [dict(item, type='jar', file=str(self.binary), sha256=embedded.BINARY_SHA256)]}))
        self.args = types.SimpleNamespace(root=self.root, output=self.root / 'collected', gradle_artifacts=self.gradle,
                                          source_mappings=self.mapping, fetch=False)

    def write_mapping(self):
        self.mapping.write_text(json.dumps({'schemaVersion': 1, 'kind': 'z8-maven-source-mappings',
                                            'components': [self.mapping_entry]}))

    def collect(self):
        with mock.patch.object(collector, 'download', side_effect=AssertionError('No network required')):
            report = collector.collect(self.args)
        maven_source_inventory(self.args.output / 'maven-sources.json', self.gradle)
        return report

    def test_exact_embedded_sources_preserve_build_bytes_and_separate_original_license_notices(self):
        report = self.collect()
        self.assertIs(report['sourceClosureReviewed'], False)
        self.assertEqual(report['status'], 'SOURCES_COLLECTED_REVIEW_REQUIRED')
        component = report['components'][0]
        self.assertEqual(component['sourceDisposition'], embedded.DISPOSITION)
        self.assertEqual((self.args.output / component['sourceFiles'][0]['path']).read_bytes(), self.binary.read_bytes())
        evidence = json.loads((self.args.output / component['embeddedSourceEvidence']['path']).read_text())
        self.assertEqual(len(evidence['sourceMatches']), 31)
        self.assertEqual(len(evidence['classSources']), 35)
        snapshot = self.args.output / component['buildEvidenceFiles'][1]['path']
        with zipfile.ZipFile(snapshot) as archive:
            self.assertEqual(archive.read('jsr-305-r49/trunk/ri/build.xml'), b'<project name="original"/>')
            self.assertTrue(archive.getinfo('jsr-305-r49/trunk/ri/src/main/resources/').is_dir())
        (self.root / 'tools').mkdir()
        (self.root / 'tools/sources.lock.json').write_text('{}')
        result = notices.generate(types.SimpleNamespace(root=self.root, output=self.root / 'notices', source_manifest=None,
            package_sources=None, gradle_artifacts=self.gradle, gradle_cache=self.root / 'no-cache',
            maven_sources=self.args.output / 'maven-sources.json', review=None))
        actual = result['components'][0]
        self.assertEqual(actual['pomLicenseDeclarations'][0]['name'], 'Apache-2.0')
        self.assertEqual({row['name'] for row in actual['licenses']}, {'BSD-3-Clause', 'CC-BY-2.5'})
        self.assertEqual(actual['scope'], 'resolved-maven-runtime-input')
        text = (self.root / 'notices/third-party-notices.txt').read_text()
        self.assertIn('Original BSD-3-Clause fixture license', text)
        self.assertIn('javax/annotation/concurrent/GuardedBy.java', text)
        self.assertEqual(text.count('Copyright fixture;'), 3)
        self.assertIn('RELEASE_LICENSE_REVIEW_REQUIRED', {row['code'] for row in result['unresolved']})

    def test_portable_mapping_replays_without_original_evidence_location_or_network(self):
        original = self.collect()
        relocated = self.root / 'relocated'
        shutil.copytree(self.args.output, relocated)
        self.dump.unlink(); self.pom.unlink()
        self.args.output = self.root / 'replayed'
        self.args.source_mappings = relocated / 'source-mappings.json'
        replay = self.collect()
        for key in ('sourceFiles', 'buildEvidenceFiles', 'embeddedSourceEvidence'):
            self.assertEqual(original['components'][0][key], replay['components'][0][key])

    def test_unknown_coordinate_revision_and_primary_evidence_are_rejected(self):
        for key, value in [('revision', 50), ('type', 'arbitrary-source')]:
            changed = dict(self.mapping_entry, **{key: value})
            with self.assertRaisesRegex(ValueError, 'exact JSR305'):
                embedded.validate_mapping(changed, embedded.COORDINATE, [embedded.BINARY_SHA256])
        with self.assertRaisesRegex(ValueError, 'exact JSR305'):
            embedded.validate_mapping(self.mapping_entry, ('example', 'other', '1'), [embedded.BINARY_SHA256])
        with self.assertRaisesRegex(ValueError, 'primary evidence hash'):
            embedded.evidence(self.binary.read_bytes() + b'changed', self.dump.read_bytes())

    def test_changed_later_source_is_not_substituted_and_uncovered_class_is_rejected(self):
        changed = self.dump_bytes.replace(b'package example; /* fixture */', b'package example; /* changed */')
        payload = gzip.compress(changed)
        with mock.patch.object(embedded, 'DUMP_SHA256', embedded.digest(payload)):
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                embedded.evidence(self.binary.read_bytes(), payload)
        changed = dict(self.members, **{'example/Library00.java': b'a later incompatible source version'})
        binary = zipped(changed)
        with mock.patch.object(embedded, 'BINARY_SHA256', embedded.digest(binary)):
            with self.assertRaisesRegex(ValueError, 'do not exactly match'):
                embedded.evidence(binary, self.dump.read_bytes())
        changed = dict(self.members, **{'example/Undocumented.class': b'additional class'})
        binary = zipped(changed)
        with mock.patch.object(embedded, 'BINARY_SHA256', embedded.digest(binary)):
            with self.assertRaisesRegex(ValueError, 'no matching embedded Java'):
                embedded.evidence(binary, self.dump.read_bytes())

    def test_claimed_evidence_and_preserved_build_snapshot_cannot_be_rewritten(self):
        report = self.collect()
        for field in ('embeddedSourceEvidence', 'buildEvidenceFiles'):
            altered = copy.deepcopy(report)
            target = altered['components'][0][field]
            target = target[1] if isinstance(target, list) else target
            path = self.args.output / target['path']
            original = path.read_bytes()
            payload = (json.dumps({'kind': 'invented approval'}).encode() if field == 'embeddedSourceEvidence' else b'altered build')
            path.write_bytes(payload)
            for row in [target, *[row for row in altered['files'] if row['path'] == target['path']]]:
                row.update(sha256=embedded.digest(payload), bytes=len(payload))
            (self.args.output / 'maven-sources.json').write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, 'does not match original inputs'):
                maven_source_inventory(self.args.output / 'maven-sources.json', self.gradle)
            path.write_bytes(original)

    def test_svn_traversal_and_truncated_fulltext_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe SVN'):
            embedded.svn_snapshot(record({'Revision-number': 49}) + record(
                {'Node-path': '../outside', 'Node-action': 'add'}, b'outside'), 49)
        with self.assertRaisesRegex(ValueError, 'Truncated SVN'):
            embedded.svn_snapshot(b'Revision-number: 49\nContent-length: 100\n\nshort', 49)


if __name__ == '__main__':
    unittest.main()
