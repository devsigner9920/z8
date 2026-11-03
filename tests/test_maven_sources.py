"""Maven evidence collection must not turn metadata or empty artifacts into false closure."""
import hashlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
import shutil
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('maven_sources', ROOT / 'tools/collect-maven-sources.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
from release_compliance import maven_source_inventory
notice_spec = importlib.util.spec_from_file_location('maven_source_notices', ROOT / 'tools/generate-release-notices.py')
notices = importlib.util.module_from_spec(notice_spec)
notice_spec.loader.exec_module(notices)


def zipped(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return output.getvalue()


class MavenSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / 'collected'

    def binary(self, entries, group='example', name='library', version='1', kind='jar'):
        path = self.root / (name + '.' + kind)
        path.write_bytes(zipped(entries))
        return {'group': group, 'name': name, 'version': version, 'type': kind,
                'file': str(path), 'sha256': collector.sha256(path)}

    def args(self, components):
        path = self.root / 'dependencies.json'
        path.write_text(json.dumps({'kind': 'z8-gradle-runtime-artifacts',
            'configuration': 'releaseRuntimeClasspath', 'components': components}))
        return types.SimpleNamespace(root=self.root, output=self.output, gradle_artifacts=path, fetch=True)

    def fake_download(self, url, output, fetch, previous):
        if url.endswith('-sources.jar'):
            payload = zipped({'example/Library.java': '/* Original copyright */ class Library {}'})
        else:
            payload = (b'<project><licenses><license><name>MIT</name><url>https://example.invalid/license</url>'
                       b'</license></licenses><scm><url>https://example.invalid/source</url><tag>v1</tag></scm></project>')
        digest = hashlib.sha256(payload).hexdigest()
        relative = 'downloads/' + digest + '/' + url.rsplit('/', 1)[1]
        collector.atomic_write(output / relative, payload)
        return {'path': relative, 'url': url, 'sha256': digest, 'bytes': len(payload), 'status': 'VERIFIED'}

    def verify_report(self, report, args):
        path = args.output / 'maven-sources.json'
        path.write_bytes(collector.json_bytes(report))
        return maven_source_inventory(path, args.gradle_artifacts)

    def test_exact_runtime_inputs_collect_sources_without_claiming_closure(self):
        item = self.binary({'classes.jar': zipped({'example/Library.class': b'class fixture'}),
                            'res/values/strings.xml': b'<resources/>'}, kind='aar')
        args = self.args([item, dict(item)])
        with mock.patch.object(collector, 'download', side_effect=self.fake_download):
            report = collector.collect(args)
        self.verify_report(report, args)
        self.assertEqual(report['status'], 'SOURCES_COLLECTED_REVIEW_REQUIRED')
        self.assertIs(report['sourceClosureReviewed'], False)
        self.assertEqual(len(report['components']), 1)
        component = report['components'][0]
        self.assertEqual(len(component['binaryArtifacts']), 2)
        self.assertEqual(component['binaryArtifacts'][0]['classCount'], 1)
        self.assertEqual(component['sourceDisposition'], 'PUBLISHED_SOURCE_JAR')
        self.assertTrue(any('resources' in reason for reason in component['reviewRequired']))
        self.assertEqual(component['scm']['tag'], 'v1')
        self.assertEqual(component['licenses'][0]['name'], 'MIT')
        self.assertEqual({f['role'] for f in report['files']}, {'pom', 'published-source-jar', 'source-content-index'})
        for record in report['files']:
            self.assertEqual(collector.sha256(self.output / record['path']), record['sha256'])
        index = json.loads((self.output / component['contentInventory']['path']).read_text())
        self.assertEqual(index['members'][0]['path'], 'example/Library.java')

    def test_unknown_empty_artifact_is_not_exempt_and_services_count_as_resources(self):
        empty = self.binary({'META-INF/MANIFEST.MF': 'Manifest-Version: 1.0\n'})
        inventory = collector.archive_inventory(Path(empty['file']))
        self.assertFalse(collector.no_code_exception(('example', 'library', '1'), inventory))
        known = next(iter(collector.EMPTY_COMPATIBILITY))
        self.assertTrue(collector.no_code_exception(known, inventory))
        service = self.binary({'META-INF/services/example.Service': 'example.Provider'})
        self.assertFalse(collector.no_code_exception(known, collector.archive_inventory(Path(service['file']))))

    def test_known_empty_compatibility_artifact_has_explicit_evidence(self):
        group, name, version = next(iter(collector.EMPTY_COMPATIBILITY))
        item = self.binary({'META-INF/MANIFEST.MF': 'Manifest-Version: 1.0\n'}, group, name, version)
        with mock.patch.object(collector, 'download', side_effect=self.fake_download) as download:
            report = collector.collect(self.args([item]))
        self.assertEqual(report['components'][0]['sourceDisposition'], 'NO_CODE_ARTIFACT_VERIFIED')
        self.assertEqual(report['components'][0]['sourceFiles'], [])
        self.assertFalse(any(call.args[0].endswith('-sources.jar') for call in download.call_args_list))
        self.assertIs(report['sourceClosureReviewed'], False)

    def test_missing_source_for_code_remains_incomplete(self):
        item = self.binary({'example/Library.class': b'fixture'})
        def fail_source(url, *args):
            if url.endswith('-sources.jar'):
                raise OSError('HTTP 404')
            return self.fake_download(url, *args)
        args = self.args([item])
        with mock.patch.object(collector, 'download', side_effect=fail_source):
            report = collector.collect(args)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertIn('MAVEN_SOURCE_UNAVAILABLE', {x['code'] for x in report['unresolved']})
        self.verify_report(report, args)
        altered = copy.deepcopy(report)
        altered['status'] = 'SOURCES_COLLECTED_REVIEW_REQUIRED'
        with self.assertRaisesRegex(ValueError, 'summary'):
            self.verify_report(altered, args)
        altered = copy.deepcopy(report)
        altered['unresolved'] = []
        altered['status'] = 'SOURCES_COLLECTED_REVIEW_REQUIRED'
        with self.assertRaisesRegex(ValueError, 'summary'):
            self.verify_report(altered, args)
        altered['components'][0]['unresolved'] = []
        with self.assertRaisesRegex(ValueError, 'must remain unresolved'):
            self.verify_report(altered, args)

    def test_content_inventory_and_sources_cannot_be_stripped(self):
        args = self.args([self.binary({'example/Library.class': b'fixture'})])
        with mock.patch.object(collector, 'download', side_effect=self.fake_download):
            report = collector.collect(args)
        altered = copy.deepcopy(report)
        index_path = altered['components'][0]['contentInventory']['path']
        altered['files'] = [r for r in altered['files'] if r['path'] != index_path]
        with self.assertRaisesRegex(ValueError, 'reference missing'):
            self.verify_report(altered, args)
        altered = copy.deepcopy(report)
        altered['files'] = []
        altered['components'][0]['sourceFiles'] = []
        altered['components'][0]['metadataFiles'] = []
        with self.assertRaises(ValueError):
            self.verify_report(altered, args)
        altered = copy.deepcopy(report)
        altered['components'][0]['sourceFiles'] = []
        with self.assertRaisesRegex(ValueError, 'requires source files'):
            self.verify_report(altered, args)

    def test_empty_disposition_requires_known_coordinate_and_zero_counts(self):
        group, name, version = next(iter(collector.EMPTY_COMPATIBILITY))
        args = self.args([self.binary({'META-INF/MANIFEST.MF': 'Manifest-Version: 1.0\n'}, group, name, version)])
        with mock.patch.object(collector, 'download', side_effect=self.fake_download):
            report = collector.collect(args)
        self.verify_report(report, args)
        report['components'][0]['binaryArtifacts'][0]['classCount'] = 1
        with self.assertRaisesRegex(ValueError, 'empty-artifact'):
            self.verify_report(report, args)

    def test_changed_resolved_binary_fails_before_download(self):
        item = self.binary({'example/Library.class': b'fixture'})
        args = self.args([item])
        Path(item['file']).write_bytes(b'changed')
        with mock.patch.object(collector, 'download') as download:
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                collector.collect(args)
            download.assert_not_called()

    def test_official_repository_boundary_and_coordinate_validation(self):
        for url in ('http://repo.maven.apache.org/maven2/x', 'https://example.invalid/file',
                    'https://user:password@dl.google.com/a'):
            self.assertFalse(collector.allowed_url(url))
        with self.assertRaisesRegex(ValueError, 'Redirect'):
            collector.OfficialRedirects().redirect_request(None, None, 302, '', {}, 'https://example.invalid/evil')
        for name in ('../secret', 'a/b', '${artifact}'):
            with self.assertRaises(ValueError):
                collector.coordinate_parts({'group': 'example', 'name': name, 'version': '1'})
        self.assertTrue(collector.repository_url(('androidx.core', 'core', '1'), '-sources.jar').startswith(collector.GOOGLE))
        self.assertTrue(collector.repository_url(('org.jetbrains', 'annotations', '13'), '-sources.jar').startswith(collector.CENTRAL))

    def test_archive_traversal_is_rejected_without_extraction(self):
        path = self.root / 'untrusted.jar'
        path.write_bytes(zipped({'../outside.java': b'never write'}))
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            collector.archive_inventory(path, True)
        self.assertFalse((self.root.parent / 'outside.java').exists())

    def test_tampered_cache_is_not_trusted(self):
        record = self.fake_download('https://repo.maven.apache.org/maven2/example/library/1/library-1-sources.jar',
                                    self.output, True, [])
        (self.output / record['path']).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'not cached'):
            collector.download(record['url'], self.output, False, [record])

    def test_explicit_upstream_mapping_requires_exact_binary_and_source_hashes(self):
        item = self.binary({'example/Library.class': b'fixture'})
        archive = self.root / 'upstream.zip'
        archive.write_bytes(zipped({'project/Library.java': 'class Library {}', 'project/build.gradle': 'version="1"'}))
        commit = 'a' * 40
        entry = {'group': 'example', 'name': 'library', 'version': '1',
            'binaryArtifactSha256': [item['sha256']], 'repository': 'https://github.com/example/project',
            'tag': 'v1', 'commit': commit, 'versionEvidence': [{'path': 'project/build.gradle', 'value': 'version="1"'}],
            'sourceArchive': {'path': archive.name, 'sha256': collector.sha256(archive),
                'url': 'https://codeload.github.com/example/project/zip/' + commit}}
        pom = self.root / 'upstream.pom'
        pom.write_text('<project><licenses><license><name>MIT</name></license></licenses></project>')
        entry['metadataPom'] = {'path': pom.name, 'sha256': collector.sha256(pom)}
        mapping = self.root / 'mappings.json'
        mapping.write_text(json.dumps({'schemaVersion': 1, 'kind': 'z8-maven-source-mappings', 'components': [entry]}))
        args = self.args([item]); args.source_mappings = mapping
        with mock.patch.object(collector, 'download', side_effect=self.fake_download):
            report = collector.collect(args)
        self.assertEqual(report['components'][0]['sourceDisposition'], 'PINNED_UPSTREAM_SOURCE_ARCHIVE')
        self.assertEqual(report['components'][0]['sourceFiles'][0]['sha256'], entry['sourceArchive']['sha256'])
        self.assertIs(report['sourceClosureReviewed'], False)
        self.verify_report(report, args)
        self.assertEqual(report['inputs']['sourceMappingsSha256'], collector.sha256(mapping))
        self.assertEqual((self.output / 'provenance/source-mappings.json').read_bytes(), mapping.read_bytes())
        relocated = self.root / 'relocated'
        shutil.copytree(self.output, relocated)
        archive.unlink(); pom.unlink()
        replay_args = copy.copy(args)
        replay_args.source_mappings = relocated / 'source-mappings.json'
        replay_args.output = self.root / 'replayed'
        replay_args.fetch = False
        with mock.patch.object(collector, 'download', side_effect=AssertionError('Mapped evidence needs no fetch')):
            replay = collector.collect(replay_args)
        self.verify_report(replay, replay_args)
        for key in ('sourceFiles', 'metadataFiles'):
            self.assertEqual(replay['components'][0][key], report['components'][0][key])
        self.assertEqual(replay['inputs']['sourceMappingsSha256'], collector.sha256(replay_args.source_mappings))
        entry['binaryArtifactSha256'] = ['0' * 64]
        mapping.write_text(json.dumps({'schemaVersion': 1, 'kind': 'z8-maven-source-mappings', 'components': [entry]}))
        with self.assertRaisesRegex(ValueError, 'binary hashes'):
            collector.collect(args)

    def test_mapping_parent_symlink_cannot_import_external_evidence(self):
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external) / 'source.zip'
            outside.write_bytes(zipped({'Original.java': 'class Original {}'}))
            (self.root / 'linked').symlink_to(external, target_is_directory=True)
            mapping = {'sourceArchive': {'path': 'linked/source.zip', 'sha256': collector.sha256(outside)}}
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                collector.mapped_file(mapping, 'sourceArchive', self.root, self.output, 'upstream-source-archive')

    def test_notices_use_preserved_child_parent_poms_with_empty_gradle_cache(self):
        (self.root / 'tools').mkdir()
        (self.root / 'tools/sources.lock.json').write_text('{}')
        original_notice = 'Original dependency copyright and file-specific terms\n'
        args = self.args([self.binary({'example/Library.class': b'fixture', 'META-INF/NOTICE': original_notice})])
        empty_cache = self.root / 'empty-gradle-cache'
        empty_cache.mkdir()
        for child_license in ('', '<licenses><license><name>Child License</name><url>https://example.invalid/child</url></license></licenses>'):
            with self.subTest(child_declares_license=bool(child_license)):
                def poms(url, output, fetch, previous):
                    if url.endswith('/library-1.pom'):
                        payload = ('<project><parent><groupId>example</groupId><artifactId>parent</artifactId>'
                                   '<version>1</version></parent>' + child_license + '</project>').encode()
                    elif url.endswith('/parent-1.pom'):
                        payload = b'<project><licenses><license><name>Parent License</name><url>https://example.invalid/parent</url></license></licenses></project>'
                    else:
                        return self.fake_download(url, output, fetch, previous)
                    digest = hashlib.sha256(payload).hexdigest()
                    relative = 'downloads/' + digest + '/' + url.rsplit('/', 1)[1]
                    collector.atomic_write(output / relative, payload)
                    return {'path': relative, 'url': url, 'sha256': digest, 'bytes': len(payload), 'status': 'VERIFIED'}
                with mock.patch.object(collector, 'download', side_effect=poms):
                    evidence = collector.collect(args)
                # Notice generation must read preserved POM bytes, not trust this summary.
                evidence['components'][0]['licenses'] = [{'name': 'Incorrect summary', 'url': ''}]
                self.verify_report(evidence, args)
                notice_args = types.SimpleNamespace(root=self.root, output=self.root / 'notices',
                    source_manifest=None, package_sources=None, gradle_artifacts=args.gradle_artifacts,
                    gradle_cache=empty_cache, maven_sources=self.output / 'maven-sources.json', review=None)
                result = notices.generate(notice_args)
                actual = next(c for c in result['components'] if c['scope'] == 'bundled-maven')
                self.assertEqual(actual['licenses'][0]['name'], 'Child License' if child_license else 'Parent License')
                self.assertEqual(actual['pomSha256'], evidence['components'][0]['metadataFiles'][0]['sha256'])
                self.assertNotIn('LICENSE_UNRESOLVED', {i['code'] for i in result['unresolved']})
                self.assertIn('RELEASE_LICENSE_REVIEW_REQUIRED', {i['code'] for i in result['unresolved']})
                self.assertIn(original_notice, (notice_args.output / 'third-party-notices.txt').read_text())
                self.assertEqual(list(empty_cache.rglob('*')), [])
        child = self.output / evidence['components'][0]['metadataFiles'][0]['path']
        child.write_text('<project>tampered POM</project>')
        notice_args.output = self.root / 'must-not-be-written'
        with self.assertRaisesRegex(ValueError, 'payload changed'):
            notices.generate(notice_args)
        self.assertFalse(notice_args.output.exists())


if __name__ == '__main__':
    unittest.main()
