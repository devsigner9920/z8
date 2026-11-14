"""Supplemental originals must preserve publisher evidence and fail closed."""
import base64
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import maven_upstream_supplements as upstream
from release_compliance import maven_source_inventory


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = load('collect-maven-sources')
notices = load('generate-release-notices')


def zipped(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return stream.getvalue()


class MavenUpstreamTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.java = b'package example; /* original copyright */ class Library {}'
        self.jar = zipped({'example/Library.java': self.java})
        self.original = zipped({'project/source/example/Library.java': self.java,
                                'project/build.gradle': b'apply plugin: "java"',
                                'project/LICENSE': b'Original fixture license text',
                                'project/res/values.xml': b'<resources/>'})
        self.spec = {'id': 'library', 'format': 'zip', 'repository': 'https://github.com/example/project',
                     'commit': 'a' * 40, 'rootPrefix': 'project/',
                     'url': 'https://codeload.github.com/example/project/zip/' + 'a' * 40,
                     'sha256': upstream.digest(self.original), 'bytes': len(self.original)}
        self.component = {'group': 'example', 'name': 'library', 'version': '1',
            'binaryArtifactSha256': ['b' * 64], 'sourceJarSha256': upstream.digest(self.jar),
            'sourceMatches': [{'sourceJarMember': 'example/Library.java', 'archiveId': 'library',
                               'upstreamMember': 'source/example/Library.java'}],
            'requiredInputs': [{'archiveId': 'library', 'member': member, 'category': category}
                               for member, category in [('build.gradle', 'build'), ('LICENSE', 'license'),
                                                        ('res/values.xml', 'resource')]],
            'generatedSources': [], 'commonSupportArchiveIds': [],
            'reviewLimitations': ['Exact source bytes; no binary-identical rebuild or legal approval.']}

    def lock(self):
        return {'schemaVersion': 1, 'kind': upstream.KIND,
                'archives': [self.spec], 'components': [self.component]}

    def proof(self):
        specs, components = upstream.validate_lock(self.lock())
        return upstream.evidence(components[('example', 'library', '1')], specs,
                                 self.jar, {'library': self.original})

    def test_complete_original_bytes_are_preserved_without_approval(self):
        proof = self.proof()
        self.assertEqual(proof['sourceMatches'][0]['sha256'], upstream.digest(self.java))
        self.assertEqual(len(proof['requiredInputs']), 3)
        self.assertIs(proof['sourceClosureReviewed'], False)

    def test_url_is_bound_to_exact_commit_and_repository(self):
        for url in ['http://codeload.github.com/example/project/zip/' + 'a' * 40,
                    'https://github.com/example/project/archive/main.zip',
                    self.spec['url'] + '?redirect=other']:
            spec = dict(self.spec, url=url)
            with self.assertRaises(ValueError):
                upstream.validate_spec(spec)

    def test_unknown_metadata_cannot_leak_local_paths_into_public_proof(self):
        self.spec['localPath'] = '/Users/private/secret'
        with self.assertRaisesRegex(ValueError, 'Unknown fields'):
            self.proof()

    def test_altered_original_payload_is_rejected_even_with_matching_source(self):
        self.original += b'changed container'
        with self.assertRaisesRegex(ValueError, 'hash or size'):
            self.proof()

    def test_changed_publisher_jar_cannot_reuse_original_correspondence(self):
        self.jar = zipped({'example/Library.java': self.java + b' changed'})
        with self.assertRaisesRegex(ValueError, 'exact publisher'):
            self.proof()

    def test_unmatched_source_and_omitted_java_fail(self):
        self.component['sourceMatches'][0]['upstreamMember'] = 'build.gradle'
        with self.assertRaisesRegex(ValueError, 'differs'):
            self.proof()
        self.component['sourceMatches'][0]['upstreamMember'] = 'source/example/Library.java'
        self.jar = zipped({'example/Library.java': self.java, 'example/Additional.kt': b'class Additional'})
        self.component['sourceJarSha256'] = upstream.digest(self.jar)
        with self.assertRaisesRegex(ValueError, 'every published'):
            self.proof()

    def test_missing_resource_is_not_silently_approved(self):
        self.component['requiredInputs'][-1]['member'] = 'res/missing.xml'
        with self.assertRaisesRegex(ValueError, 'missing or a link'):
            self.proof()

    def test_arbitrary_generated_source_exception_is_rejected(self):
        self.component['generatedSources'] = [{'sourceJarMember': 'example/BuildConfig.java'}]
        with self.assertRaisesRegex(ValueError, 'Unreviewed'):
            self.proof()

    def test_exact_kotlin_release_substitution_preserves_both_inputs(self):
        original = b'// original header\nfun version() = KotlinVersion(1, 8, 255)\n'
        published = original.replace(b'1, 8, 255', b'1, 8, 22')
        self.jar = zipped({'example/Library.java': self.java, upstream.KOTLIN_VERSION_SOURCE: published})
        entries = {'project/source/example/Library.java': self.java,
                   'project/' + upstream.KOTLIN_VERSION_ORIGINAL: original,
                   'project/build.gradle': b'build', 'project/LICENSE': b'license',
                   'project/res/values.xml': b'<resources/>'}
        self.original = zipped(entries)
        self.spec.update(sha256=upstream.digest(self.original), bytes=len(self.original))
        self.component.update(group='org.jetbrains.kotlin', name='kotlin-stdlib-common', version='1.8.22',
                              sourceJarSha256=upstream.digest(self.jar))
        self.component['sourceTransforms'] = [{'sourceJarMember': upstream.KOTLIN_VERSION_SOURCE,
            'archiveId': 'library', 'upstreamMember': upstream.KOTLIN_VERSION_ORIGINAL,
            'transform': 'kotlin-release-version-1.8.22'}]
        specs, _ = upstream.validate_lock(self.lock())
        def proof():
            return upstream.evidence(self.component, specs, self.jar, {'library': self.original})
        value = proof()['sourceTransforms'][0]
        self.assertEqual(value['upstreamSha256'], upstream.digest(original))
        self.assertEqual(value['sha256'], upstream.digest(published))
        self.assertIs(proof()['sourceClosureReviewed'], False)
        # Even a newly pinned publisher JAR cannot hide another source change.
        self.jar = zipped({'example/Library.java': self.java,
                           upstream.KOTLIN_VERSION_SOURCE: published + b'// unrelated change'})
        self.component['sourceJarSha256'] = upstream.digest(self.jar)
        with self.assertRaisesRegex(ValueError, 'beyond the exact version substitution'):
            proof()
        self.component['version'] = '1.8.23'
        with self.assertRaisesRegex(ValueError, 'Unreviewed source transformation'):
            upstream.validate_lock(self.lock())

    def test_unsafe_archive_paths_are_rejected_without_extracting(self):
        self.original = zipped({'project/../../escaped.java': b'never extract'})
        self.spec.update(sha256=upstream.digest(self.original), bytes=len(self.original))
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            self.proof()
        self.assertFalse((self.root.parent / 'escaped.java').exists())

    def test_selected_symlink_is_never_followed(self):
        stream = io.BytesIO(self.original)
        with zipfile.ZipFile(stream, 'a') as archive:
            info = zipfile.ZipInfo('project/link.java')
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, 'source/example/Library.java')
        self.original = stream.getvalue()
        self.spec.update(sha256=upstream.digest(self.original), bytes=len(self.original))
        self.assertEqual(self.proof()['ignoredNonRegularMembers']['library'], ['link.java'])
        self.component['sourceMatches'][0]['upstreamMember'] = 'link.java'
        with self.assertRaisesRegex(ValueError, 'differs'):
            self.proof()

    def test_gitiles_transports_preserve_exact_original_file(self):
        original = b'// original upstream build configuration\n'
        for format_name, payload in [('gitiles-base64', base64.b64encode(original)), ('gitiles-file', original)]:
            spec = {'id': 'root-build', 'format': format_name,
                    'repository': 'https://android.googlesource.com/platform/frameworks/support',
                    'commit': 'c' * 40, 'repositoryPath': 'build.gradle',
                    'url': 'https://android.googlesource.com/platform/frameworks/support/+/' + 'c' * 40 + '/build.gradle?format=TEXT',
                    'sha256': upstream.digest(payload), 'bytes': len(payload),
                    'transportEncoding': 'base64', 'payloadEncoding': 'decoded-original-file'}
            members, ignored = upstream.read_members(spec, payload)
            self.assertEqual(members, {'build.gradle': original})
            self.assertFalse(ignored)

    def test_github_original_file_is_bound_to_commit_path_and_bytes(self):
        raw = b'// original build configuration\n'
        spec = {'id': 'kotlin-build', 'format': 'github-file',
                'repository': 'https://github.com/JetBrains/kotlin', 'commit': 'c' * 40,
                'repositoryPath': 'libraries/stdlib/jvm/build.gradle',
                'url': 'https://raw.githubusercontent.com/JetBrains/kotlin/' + 'c' * 40 + '/libraries/stdlib/jvm/build.gradle',
                'sha256': upstream.digest(raw), 'bytes': len(raw)}
        members, ignored = upstream.read_members(spec, raw)
        self.assertEqual(members, {spec['repositoryPath']: raw})
        self.assertFalse(ignored)
        for update in ({'url': spec['url'].replace('c' * 40, 'main')},
                       {'repositoryPath': '../outside'}, {'rootPrefix': 'invented/'},
                       {'repositoryPath': 'build.gradle?raw=1'}, {'repositoryPath': '%2e%2e/outside'},
                       {'payloadEncoding': 'transformed'}, {'url': spec['url'] + '?token=private'}):
            with self.assertRaises(ValueError):
                upstream.validate_spec(dict(spec, **update))
        with self.assertRaisesRegex(ValueError, 'hash or size'):
            upstream.read_members(spec, raw + b'changed')

    def test_binary_resource_correspondence_requires_original_binary_and_payload(self):
        binary = zipped({'META-INF/rules.pro': b'<resources/>'})
        binary_sha = upstream.digest(binary)
        self.component['binaryArtifactSha256'] = [binary_sha]
        match = {'binaryArtifactSha256': binary_sha, 'binaryMember': 'META-INF/rules.pro',
                 'archiveId': 'library', 'upstreamMember': 'res/values.xml'}
        self.component['binaryMemberMatches'] = [match]
        specs, _ = upstream.validate_lock(self.lock())
        def proof(inputs):
            return upstream.evidence(self.component, specs, self.jar, {'library': self.original}, inputs)
        self.assertEqual(proof({binary_sha: binary})['binaryMemberMatches'][0]['sha256'],
                         upstream.digest(b'<resources/>'))
        for inputs in ({}, {binary_sha: binary + b'tampered'}):
            with self.assertRaisesRegex(ValueError, 'exact retained runtime artifact'):
                proof(inputs)
        match['upstreamMember'] = 'build.gradle'
        with self.assertRaisesRegex(ValueError, 'binary member differs'):
            proof({binary_sha: binary})
        match['upstreamMember'] = 'res/values.xml'
        match['binaryMember'] = 'missing/resource'
        with self.assertRaisesRegex(ValueError, 'binary member differs'):
            proof({binary_sha: binary})

    def test_binary_resource_reference_cannot_name_unrelated_or_duplicate_artifact(self):
        match = {'binaryArtifactSha256': 'f' * 64, 'binaryMember': 'META-INF/rules.pro',
                 'archiveId': 'library', 'upstreamMember': 'res/values.xml'}
        self.component['binaryMemberMatches'] = [match]
        with self.assertRaisesRegex(ValueError, 'Unknown or duplicate'):
            upstream.validate_lock(self.lock())
        match['binaryArtifactSha256'] = 'b' * 64
        self.component['binaryMemberMatches'].append(dict(match))
        with self.assertRaisesRegex(ValueError, 'Unknown or duplicate'):
            upstream.validate_lock(self.lock())

    def test_gitiles_tar_rejects_selected_links_and_preserves_source(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            info = tarfile.TarInfo('src/Library.java'); info.size = len(self.java)
            archive.addfile(info, io.BytesIO(self.java))
            link = tarfile.TarInfo('link.java'); link.type = tarfile.SYMTYPE; link.linkname = '../../outside'
            archive.addfile(link)
        raw = stream.getvalue()
        spec = {'id': 'module', 'format': 'tar.gz', 'repository': 'https://android.googlesource.com/platform/frameworks/support',
                'commit': 'd' * 40, 'repositoryPath': 'core/core', 'sha256': upstream.digest(raw), 'bytes': len(raw),
                'url': 'https://android.googlesource.com/platform/frameworks/support/+archive/' + 'd' * 40 + '/core/core.tar.gz'}
        members, ignored = upstream.read_members(spec, raw)
        self.assertEqual(members, {'src/Library.java': self.java})
        self.assertEqual(ignored, ['link.java'])

    def test_deduplicated_root_blob_must_exist_at_the_source_revision(self):
        repository = 'https://android.googlesource.com/platform/frameworks/support'
        self.spec.update(format='tar.gz', repository=repository, repositoryPath='module', rootPrefix='',
                         url=repository + '/+archive/' + 'a' * 40 + '/module.tar.gz')
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            for name, data in [('source/example/Library.java', self.java), ('LICENSE', b'License'),
                               ('build.gradle', b'original build'), ('res/values.xml', b'<resources/>')]:
                entry = tarfile.TarInfo(name); entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        self.original = stream.getvalue(); self.spec.update(sha256=upstream.digest(self.original), bytes=len(self.original))
        raw = b'original root build'
        git_object = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        tree_bytes = b")]}'\n" + json.dumps({'entries': [{'name': 'build.gradle', 'type': 'blob', 'id': git_object}]}).encode()
        blob = {'id': 'root-file', 'format': 'gitiles-file', 'repository': repository, 'commit': 'b' * 40,
                'repositoryPath': 'build.gradle', 'url': repository + '/+/' + 'b' * 40 + '/build.gradle?format=TEXT',
                'sha256': upstream.digest(raw), 'bytes': len(raw),
                'transportEncoding': 'base64', 'payloadEncoding': 'decoded-original-file'}
        tree = {'id': 'root-tree', 'format': 'gitiles-tree', 'repository': repository, 'commit': 'a' * 40,
                'repositoryPath': '', 'url': repository + '/+/' + 'a' * 40 + '/?format=JSON',
                'sha256': upstream.digest(tree_bytes), 'bytes': len(tree_bytes)}
        self.component['rootBlobBindings'] = [{'archiveId': 'root-file', 'treeArchiveId': 'root-tree',
                                              'repositoryPath': 'build.gradle', 'gitObject': git_object}]
        self.component['requiredInputs'].append({'archiveId': 'root-file', 'member': 'build.gradle', 'category': 'build'})
        lock = self.lock(); lock['archives'] += [blob, tree]
        specs, _ = upstream.validate_lock(lock)
        payloads = {'library': self.original, 'root-file': raw, 'root-tree': tree_bytes}
        proof = upstream.evidence(self.component, specs, self.jar, payloads)
        self.assertEqual(proof['rootBlobBindings'][0]['sourceCommit'], 'a' * 40)
        saved = self.component['rootBlobBindings']; self.component['rootBlobBindings'] = []
        with self.assertRaisesRegex(ValueError, 'requires its source-commit'):
            upstream.evidence(self.component, specs, self.jar, payloads)
        self.component['rootBlobBindings'] = saved
        self.component['rootBlobBindings'][0]['gitObject'] = 'f' * 40
        with self.assertRaisesRegex(ValueError, 'Git tree object'):
            upstream.evidence(self.component, specs, self.jar, payloads)
        self.component['rootBlobBindings'][0]['gitObject'] = git_object
        tree.update(commit='c' * 40, url=repository + '/+/' + 'c' * 40 + '/?format=JSON')
        with self.assertRaisesRegex(ValueError, 'source commit'):
            upstream.evidence(self.component, specs, self.jar, payloads)

    def collect(self, duplicate_binary=False, match_binary=False):
        binary = self.root / 'library.aar'
        binary.write_bytes(zipped({'classes.jar': zipped({'example/Library.class': b'fixture'}),
                                  'res/values.xml': b'<resources/>'}))
        self.component['binaryArtifactSha256'] = [collector.sha256(binary)]
        if match_binary:
            self.component['binaryMemberMatches'] = [{'binaryArtifactSha256': collector.sha256(binary),
                'binaryMember': 'res/values.xml', 'archiveId': 'library', 'upstreamMember': 'res/values.xml'}]
        lock = self.root / 'lock.json'; lock.write_text(json.dumps(self.lock()))
        cache = self.root / 'cache'; cache.mkdir(); (cache / 'upstream.zip').write_bytes(self.original)
        dependencies = self.root / 'dependencies.json'
        dependencies.write_text(json.dumps({'schemaVersion': 1, 'kind': 'z8-gradle-runtime-artifacts',
            'configuration': 'releaseRuntimeClasspath', 'components': [{'group': 'example', 'name': 'library',
            'version': '1', 'type': 'aar', 'file': str(binary), 'sha256': collector.sha256(binary)}]}))
        if duplicate_binary:
            original = json.loads(dependencies.read_text())
            original['components'].append(dict(original['components'][0]))
            dependencies.write_text(json.dumps(original))
            self.component['binaryArtifactSha256'] *= 2
            lock.write_text(json.dumps(self.lock()))
        args = types.SimpleNamespace(root=self.root, output=self.root / 'out', gradle_artifacts=dependencies,
                                     upstream_lock=lock, upstream_cache=[cache], fetch=False)
        def fake_download(url, output, fetch, previous):
            data = self.jar if url.endswith('-sources.jar') else b'<project><licenses><license><name>MIT</name></license></licenses></project>'
            relative = 'downloads/' + upstream.digest(data) + '/' + url.rsplit('/', 1)[1]
            collector.atomic_write(output / relative, data)
            return {'path': relative, 'url': url, 'sha256': upstream.digest(data), 'bytes': len(data), 'status': 'VERIFIED'}
        with mock.patch.object(collector, 'download', side_effect=fake_download):
            report = collector.collect(args)
        return args, report

    def test_collector_preserves_publisher_jar_and_validator_rederives_proof(self):
        args, report = self.collect()
        component = report['components'][0]
        self.assertEqual(component['sourceDisposition'], 'PUBLISHED_SOURCE_JAR')
        self.assertEqual(component['sourceFiles'][0]['sha256'], upstream.digest(self.jar))
        self.assertFalse(report['unresolved'])
        maven_source_inventory(args.output / 'maven-sources.json', args.gradle_artifacts)
        proof_record = component['upstreamSnapshot']['evidence']
        path = args.output / proof_record['path']
        altered = json.loads(path.read_text()); altered['sourceMatches'][0]['sha256'] = 'f' * 64
        path.write_bytes(collector.json_bytes(altered))
        for record in report['files'] + [proof_record]:
            if record['path'] == proof_record['path']:
                record.update(sha256=collector.sha256(path), bytes=path.stat().st_size)
        (args.output / 'maven-sources.json').write_bytes(collector.json_bytes(report))
        with self.assertRaisesRegex(ValueError, 'differs from original'):
            maven_source_inventory(args.output / 'maven-sources.json', args.gradle_artifacts)

    def test_removing_snapshot_cannot_turn_collection_into_approval(self):
        args, report = self.collect()
        del report['components'][0]['upstreamSnapshot']
        (args.output / 'maven-sources.json').write_bytes(collector.json_bytes(report))
        with self.assertRaisesRegex(ValueError, 'remain unresolved'):
            maven_source_inventory(args.output / 'maven-sources.json', args.gradle_artifacts)

    def test_binary_correspondence_is_portable_and_missing_input_is_not_approved(self):
        args, report = self.collect(match_binary=True)
        self.assertFalse(report['unresolved'])
        component = report['components'][0]
        snapshot = component['upstreamSnapshot']
        self.assertEqual(len(snapshot['binaryInputs']), 1)
        # Verification does not depend on a private Gradle cache or network.
        (self.root / 'library.aar').unlink()
        with mock.patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('offline')):
            maven_source_inventory(args.output / 'maven-sources.json')
        snapshot['binaryInputs'] = []
        (args.output / 'maven-sources.json').write_bytes(collector.json_bytes(report))
        with self.assertRaisesRegex(ValueError, 'retained binary correspondence'):
            maven_source_inventory(args.output / 'maven-sources.json')

    def test_altered_binary_proof_is_rederived_not_trusted(self):
        args, report = self.collect(match_binary=True)
        component = report['components'][0]
        proof_ref = component['upstreamSnapshot']['evidence']
        path = args.output / proof_ref['path']
        proof = json.loads(path.read_text()); proof['binaryMemberMatches'][0]['sha256'] = 'f' * 64
        path.write_bytes(collector.json_bytes(proof))
        for record in report['files'] + [proof_ref]:
            if record['path'] == proof_ref['path']:
                record.update(sha256=collector.sha256(path), bytes=path.stat().st_size)
        (args.output / 'maven-sources.json').write_bytes(collector.json_bytes(report))
        with self.assertRaisesRegex(ValueError, 'differs from original'):
            maven_source_inventory(args.output / 'maven-sources.json')

    def test_repeated_gradle_records_preserve_exact_binary_set(self):
        args, report = self.collect(duplicate_binary=True)
        self.assertFalse(report['unresolved'])
        self.assertEqual(len(report['components'][0]['binaryArtifacts']), 2)
        maven_source_inventory(args.output / 'maven-sources.json', args.gradle_artifacts)

    def test_missing_input_stays_incomplete_while_publisher_jar_is_retained(self):
        self.component['requiredInputs'][-1]['member'] = 'res/missing.xml'
        args, report = self.collect()
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(report['components'][0]['sourceFiles'][0]['sha256'], upstream.digest(self.jar))
        self.assertIn('MAVEN_UPSTREAM_SUPPLEMENT_UNAVAILABLE', {x['code'] for x in report['unresolved']})
        maven_source_inventory(args.output / 'maven-sources.json', args.gradle_artifacts)

    def test_original_upstream_license_text_is_in_notices_even_if_pom_label_differs(self):
        args, report = self.collect()
        (self.root / 'tools').mkdir()
        (self.root / 'tools/sources.lock.json').write_text('{}')
        source_manifest = self.root / 'source-manifest.json'
        source_manifest.write_text(json.dumps({'sourceInputSha256': 'c' * 64}))
        package_sources = self.root / 'package-sources.json'
        package_sources.write_text(json.dumps({'inputs': {'runtimeManifestSha256': 'd' * 64,
            'guestManifestSha256': 'e' * 64}, 'components': [], 'unresolved': [], 'installedNotices': []}))
        notice_args = types.SimpleNamespace(root=self.root, output=self.root / 'notices',
            source_manifest=source_manifest, package_sources=package_sources, gradle_artifacts=args.gradle_artifacts,
            gradle_cache=self.root / 'empty', maven_sources=args.output / 'maven-sources.json', review=None)
        # Package collection has its own validator tests. Isolate notice generation
        # here to ensure an upstream license cannot overwrite release provenance.
        with mock.patch.object(notices, 'package_source_indexes'):
            result = notices.generate(notice_args)
        self.assertIn('Original fixture license text', (notice_args.output / 'third-party-notices.txt').read_text())
        component = next(x for x in result['components'] if x['id'] == 'maven:example:library:1')
        self.assertEqual(component['licenses'][0]['name'], 'MIT')
        self.assertIn('upstreamSourceEvidenceSha256', component)
        expected_inputs = {'sourceLockSha256': collector.sha256(self.root / 'tools/sources.lock.json'),
            'sourceInputSha256': 'c' * 64, 'packageSourcesSha256': collector.sha256(package_sources),
            'runtimeManifestSha256': 'd' * 64, 'guestManifestSha256': 'e' * 64,
            'gradleArtifactsSha256': collector.sha256(args.gradle_artifacts),
            'mavenSourcesSha256': collector.sha256(notice_args.maven_sources)}
        self.assertEqual(result['inputs'], expected_inputs)
        emitted = json.loads((notice_args.output / 'release-notices.json').read_text())
        self.assertEqual(emitted['inputs'], expected_inputs)


if __name__ == '__main__':
    unittest.main()
