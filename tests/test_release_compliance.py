"""Release evidence boundary tests: no credentials, no recipe execution, no false green."""
import hashlib
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from release_compliance import archive_inventory, bytes_sha, deb822, json_bytes, safe_relative, sha256, maven_source_inventory, historical_guest_inventory
from release_compliance import HISTORICAL_GUEST_ARCHIVES_REQUIRING_SOURCES


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sources = load('package-release-source')
collector = load('collect-release-package-sources')
notices = load('generate-release-notices')
verifier = load('verify-release-compliance')


class ComplianceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        for name in ('tools', 'runtime', 'overlay', 'tests', 'docs'):
            (self.root / name).mkdir()
        self.lock = {'schemaVersion': 1, 'applicationId': 'dev.devsigner.z8'}
        for key, folder in [('termuxApp', 'termux-app'), ('termuxPackages', 'termux-packages')]:
            path = self.root / 'upstream' / folder
            path.mkdir(parents=True)
            subprocess.run(['git', 'init', '-q', str(path)], check=True)
            (path / 'LICENSE.md').write_text('GPL fixture\n')
            (path / 'testkey_untrusted.jks').write_bytes(b'public upstream fixture must still be excluded')
            subprocess.run(['git', '-C', str(path), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(path), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)
            commit = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
            self.lock[key] = {'commit': commit, 'url': 'https://example.invalid/' + folder}
        (self.root / 'tools/sources.lock.json').write_bytes(json_bytes(self.lock))
        (self.root / 'README.md').write_text('Source fixture\n')

    def tearDown(self):
        self.temp.cleanup()

    def test_snapshot_is_deterministic_and_does_not_copy_git_or_keys(self):
        (self.root / '.local').mkdir()
        (self.root / '.local/auth.json').write_text('secret')
        (self.root / 'tools/upload.keystore').write_text('secret')
        first = sources.package(self.root, self.root / 'out1')
        second = sources.package(self.root, self.root / 'out2')
        self.assertEqual(first['archiveSha256'], second['archiveSha256'])
        with zipfile.ZipFile(self.root / 'out1' / first['archive']) as z:
            self.assertTrue(any(n.startswith('upstream/termux-app/') for n in z.namelist()))
            self.assertFalse(any('/.git/' in n or n.startswith('.local/') or n.endswith(('.jks', '.keystore')) for n in z.namelist()))
        self.assertTrue(any(x['path'].endswith('testkey_untrusted.jks') for x in first['omitted']))

    def maven_fixture(self):
        directory = self.root / 'maven-inputs'
        directory.mkdir()
        payload = directory / 'library-sources.jar'
        with zipfile.ZipFile(payload, 'w') as archive:
            archive.writestr('original/Library.java', '/* Original copyright */\nclass Library {}\n')
        gradle = directory / 'gradle.json'
        binary = {'group': 'fixture', 'name': 'library', 'version': '1', 'type': 'jar', 'sha256': 'a' * 64}
        gradle.write_bytes(json_bytes({'components': [binary]}))
        file = {'path': payload.name, 'sha256': sha256(payload), 'bytes': payload.stat().st_size,
                'role': 'published-source-jar', 'status': 'VERIFIED'}
        pom = directory / 'library.pom'
        pom.write_text('<project><licenses><license><name>MIT</name></license></licenses></project>')
        metadata = {'path': pom.name, 'sha256': sha256(pom), 'bytes': pom.stat().st_size,
                    'role': 'pom', 'status': 'VERIFIED'}
        index = directory / 'content.json'
        with zipfile.ZipFile(payload) as archive:
            source_bytes = archive.read('original/Library.java')
        index.write_bytes(json_bytes({'schemaVersion': 1, 'kind': 'z8-source-content-inventory',
            'coordinate': 'fixture:library:1', 'sourceArtifactSha256': file['sha256'],
            'members': [{'path': 'original/Library.java', 'bytes': len(source_bytes), 'sha256': bytes_sha(source_bytes)}]}))
        content = {'path': index.name, 'sha256': sha256(index), 'bytes': index.stat().st_size,
                   'role': 'source-content-index', 'status': 'VERIFIED'}
        inventory = {'schemaVersion': 1, 'kind': 'z8-maven-sources',
                     'inputs': {'gradleArtifactsSha256': sha256(gradle)}, 'sourceClosureReviewed': False,
                     'status': 'SOURCES_COLLECTED_REVIEW_REQUIRED',
                     'components': [{**binary, 'binaryArtifacts': [{'type': 'jar', 'sha256': binary['sha256']}],
                                     'sourceFiles': [file], 'metadataFiles': [metadata], 'licenses': [{'name': 'MIT'}],
                                     'sourceDisposition': 'PUBLISHED_SOURCE_JAR', 'sourceFileCount': 1,
                                     'contentInventory': content, 'unresolved': []}],
                     'files': [file, metadata, content], 'unresolved': []}
        manifest = directory / 'maven-sources.json'
        manifest.write_bytes(json_bytes(inventory))
        return manifest, payload, gradle, inventory

    def test_maven_source_bytes_and_inventory_are_published_without_claiming_source_closure(self):
        manifest, payload, gradle, inventory = self.maven_fixture()
        maven_source_inventory(manifest, gradle)
        result = sources.package(self.root, self.root / 'out', maven_sources=manifest)
        self.assertEqual(result['mavenSourcesSha256'], sha256(manifest))
        self.assertFalse(result['claims']['completeCorrespondingSource'])
        with zipfile.ZipFile(self.root / 'out' / result['archive']) as z:
            self.assertEqual(z.read('third-party-sources/maven/library-sources.jar'), payload.read_bytes())
            self.assertEqual(z.read('third-party-sources/maven/maven-sources.json'), manifest.read_bytes())
        _, _, findings = verifier.verify_source(self.root / 'out/source-manifest.json', self.root)
        self.assertEqual(findings, [])

    def test_maven_source_tamper_and_dependency_mismatch_fail_closed(self):
        manifest, payload, gradle, inventory = self.maven_fixture()
        inventory['components'][0]['binaryArtifacts'][0]['sha256'] = 'b' * 64
        manifest.write_bytes(json_bytes(inventory))
        with self.assertRaisesRegex(ValueError, 'exact runtime artifacts'):
            maven_source_inventory(manifest, gradle)
        inventory['components'][0]['binaryArtifacts'][0]['sha256'] = 'a' * 64
        manifest.write_bytes(json_bytes(inventory))
        payload.write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'payload changed'):
            sources.package(self.root, self.root / 'out', maven_sources=manifest)

    def test_maven_reference_and_symlink_are_rejected(self):
        manifest, payload, gradle, inventory = self.maven_fixture()
        inventory['components'][0]['sourceFiles'][0] = {**inventory['files'][0], 'path': 'missing.jar'}
        manifest.write_bytes(json_bytes(inventory))
        with self.assertRaisesRegex(ValueError, 'reference missing'):
            maven_source_inventory(manifest, gradle)
        inventory['components'][0]['sourceFiles'][0] = inventory['files'][0]
        manifest.write_bytes(json_bytes(inventory))
        outside = self.root / 'outside.jar'; payload.rename(outside); payload.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'payload changed'):
            maven_source_inventory(manifest, gradle)

    def historical_fixture(self):
        directory = self.root / 'historical-inputs'
        preparer = load('prepare-guest')
        guest_lock = json.loads((ROOT / 'runtime/guest/image.lock.json').read_text())
        lock_path = self.root / 'runtime/guest/image.lock.json'
        lock_path.parent.mkdir(parents=True)
        lock_path.write_bytes(json_bytes(guest_lock))
        files = []
        for name in sorted(preparer.HISTORICAL_MANAGED_FILES):
            payload = directory / 'files' / name
            payload.parent.mkdir(parents=True, exist_ok=True)
            payload.write_bytes(b'# Historical Z8 source fixture\n')
            files.append({'path': 'files/' + name, 'guestPath': name, 'sha256': sha256(payload),
                          'bytes': payload.stat().st_size, 'guestMode': 0o644})
        manifest = directory / 'manifest.json'
        data = {'schemaVersion': 1, 'kind': 'z8-historical-guest-managed-source',
            'guestArchiveSha256': 'a' * 64, 'guestManifestSha256': 'b' * 64,
            'referenceCurrentSourceInputSha256': 'c' * 64, 'guestSource': guest_lock['source'],
            'files': files, 'absentFromHistoricalGuest': sorted(preparer.HISTORICAL_LATER_ADDITIONS)}
        manifest.write_bytes(json_bytes(data))
        return manifest, directory / 'files/etc/z8/shellrc', data

    def test_historical_guest_scripts_and_manifest_are_preserved_and_tamper_checked(self):
        manifest, payload, data = self.historical_fixture()
        result = sources.package(self.root, self.root / 'out', historical_guest_inputs=manifest)
        self.assertEqual(result['historicalGuestInputsSha256'], sha256(manifest))
        with zipfile.ZipFile(self.root / 'out' / result['archive']) as z:
            self.assertEqual(z.read('third-party-sources/historical-guest/files/etc/z8/shellrc'), payload.read_bytes())
            self.assertEqual(z.read('third-party-sources/historical-guest/manifest.json'), manifest.read_bytes())
        payload.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Historical source bytes'):
            sources.package(self.root, self.root / 'out2', historical_guest_inputs=manifest)

    def test_historical_guest_empty_omitted_and_unscoped_inputs_fail_before_packaging(self):
        manifest, payload, original = self.historical_fixture()
        cases = []
        empty = copy.deepcopy(original); empty['files'] = []; cases.append(empty)
        missing = copy.deepcopy(original); missing['files'].pop(); cases.append(missing)
        no_removals = copy.deepcopy(original); no_removals['absentFromHistoricalGuest'] = []; cases.append(no_removals)
        wrong_path = copy.deepcopy(original)
        wrong_path['files'][0].update(guestPath='usr/bin/bash', path='files/usr/bin/bash')
        cases.append(wrong_path)
        wrong_mode = copy.deepcopy(original); wrong_mode['files'][0]['guestMode'] = 0o4755; cases.append(wrong_mode)
        wrong_lock = copy.deepcopy(original); wrong_lock['guestSource']['sha256'] = 'd' * 64; cases.append(wrong_lock)
        for number, data in enumerate(cases):
            with self.subTest(case=number):
                manifest.write_bytes(json_bytes(data))
                with self.assertRaises(ValueError):
                    historical_guest_inventory(manifest, self.root)
                with self.assertRaises(ValueError):
                    sources.package(self.root, self.root / ('bad-' + str(number)), historical_guest_inputs=manifest)
                self.assertFalse((self.root / ('bad-' + str(number))).exists())

    def test_historical_guest_manifest_identity_is_bound_even_when_archive_hash_matches(self):
        manifest, payload, data = self.historical_fixture()
        package_path = self.root / 'packages.json'
        packages = {'components': [], 'installedNotices': [], 'sourceNotices': [], 'buildInputs': [],
            'unresolved': [], 'inputs': {'guestArchiveSha256': data['guestArchiveSha256'],
                                        'guestManifestSha256': 'd' * 64}}
        package_path.write_bytes(json_bytes(packages))
        with self.assertRaisesRegex(ValueError, 'different guest archive or manifest'):
            sources.package(self.root, self.root / 'out', package_sources=package_path, historical_guest_inputs=manifest)
        args = types.SimpleNamespace(root=self.root, output=self.root / 'assets', source_manifest=None,
            package_sources=package_path, gradle_artifacts=None, gradle_cache=self.root / 'cache',
            historical_guest_inputs=manifest, review=None)
        report = notices.generate(args)
        self.assertIn('HISTORICAL_GUEST_MISMATCH', {item['code'] for item in report['unresolved']})
        packages['inputs']['guestManifestSha256'] = data['guestManifestSha256']
        package_path.write_bytes(json_bytes(packages))
        report = notices.generate(args)
        self.assertNotIn('HISTORICAL_GUEST_MISMATCH', {item['code'] for item in report['unresolved']})
        self.assertEqual(report['status'], 'INCOMPLETE')  # Other real release evidence is absent.

    def test_historical_guest_validator_uses_the_selected_root_lock(self):
        manifest, payload, data = self.historical_fixture()
        lock = self.root / 'runtime/guest/image.lock.json'
        changed = json.loads(lock.read_text())
        changed['source']['sha256'] = 'e' * 64
        lock.write_bytes(json_bytes(changed))
        with self.assertRaisesRegex(ValueError, 'pinned Ubuntu source'):
            historical_guest_inventory(manifest, self.root)

    def test_known_historical_guest_cannot_omit_retained_sources_from_both_manifests(self):
        package_path = self.root / 'packages.json'
        packages = {'components': [], 'installedNotices': [], 'sourceNotices': [], 'buildInputs': [],
            'unresolved': [], 'inputs': {'guestArchiveSha256': next(iter(HISTORICAL_GUEST_ARCHIVES_REQUIRING_SOURCES)),
                                        'guestManifestSha256': 'b' * 64}}
        package_path.write_bytes(json_bytes(packages))
        sources.package(self.root, self.root / 'out', package_sources=package_path)
        args = types.SimpleNamespace(root=self.root, output=self.root / 'assets',
            source_manifest=self.root / 'out/source-manifest.json', package_sources=package_path,
            gradle_artifacts=None, gradle_cache=self.root / 'cache', historical_guest_inputs=None, review=None)
        report = notices.generate(args)
        self.assertIn('HISTORICAL_GUEST_INPUTS_REQUIRED', {item['code'] for item in report['unresolved']})
        # Ensure verification independently detects omission, even when fed a
        # notice fixture that failed to report it. Other missing evidence stays.
        report['unresolved'] = [item for item in report['unresolved'] if item['code'] != 'HISTORICAL_GUEST_INPUTS_REQUIRED']
        notice_path = self.root / 'assets/release-notices.json'
        notice_path.write_bytes(json_bytes(report))
        verification_args = types.SimpleNamespace(root=self.root, source_manifest=args.source_manifest,
            notices=notice_path, package_sources=package_path, gradle_artifacts=None, historical_guest_inputs=None,
            maven_sources=None, runtime_manifest=None, guest_manifest=None, artifact=None,
            source_url='', check_source_url=False, review=None)
        checked = verifier.verify(verification_args)
        self.assertIn('HISTORICAL_GUEST_INPUTS_REQUIRED', {item['code'] for item in checked['blockers']})
        self.assertEqual(checked['status'], 'BLOCKED')

    def test_public_release_config_included_but_private_decisions_excluded(self):
        release = self.root / 'release'
        release.mkdir()
        (release / 'config.json').write_text('{"versionCode":2}')
        (release / 'decisions.example.json').write_text('{}')
        (release / 'decisions.json').write_text('private reviewer identity')
        result = sources.package(self.root, self.root / 'out')
        names = {x['path'] for x in result['files']}
        self.assertIn('release/config.json', names)
        self.assertIn('release/decisions.example.json', names)
        self.assertNotIn('release/decisions.json', names)

    def test_public_license_and_workflows_are_preserved_in_release_sources(self):
        for name in ('LICENSE', 'CONTRIBUTING.md', 'SECURITY.md',
                     'LICENSES/termux-app.NOTICE.md', '.github/workflows/source-checks.yml'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('public attribution or build input\n')
        result = sources.package(self.root, self.root / 'out')
        names = {item['path'] for item in result['files']}
        self.assertIn('LICENSE', names)
        self.assertIn('LICENSES/termux-app.NOTICE.md', names)
        self.assertIn('.github/workflows/source-checks.yml', names)

    def test_source_directory_symlink_is_rejected(self):
        (self.root / 'docs').rmdir()
        (self.root / 'docs').symlink_to(self.root / '.local', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            sources.package(self.root, self.root / 'out')

    def test_verified_native_sources_are_inside_public_archive(self):
        native = self.root / 'package-sources'
        (native / 'downloads').mkdir(parents=True)
        payload = native / 'downloads/source.tar'
        payload.write_bytes(b'original native source fixture')
        inventory = native / 'package-sources.json'
        inventory.write_bytes(json_bytes({'components':[{'sourceFiles':[
            {'path':'downloads/source.tar','sha256':sha256(payload),'status':'VERIFIED'}]}],
            'installedNotices':[]}))
        result = sources.package(self.root, self.root / 'out', inventory)
        self.assertEqual(result['packageSourcesSha256'], sha256(inventory))
        with zipfile.ZipFile(self.root / 'out' / result['archive']) as z:
            self.assertEqual(z.read('third-party-sources/downloads/source.tar'), payload.read_bytes())
        payload.write_bytes(b'changed source after collection')
        with self.assertRaisesRegex(ValueError, 'changed before archiving'):
            sources.package(self.root, self.root / 'out2', inventory)

    def test_private_key_in_plain_source_name_fails(self):
        (self.root / 'tools/innocent.txt').write_text('-----BEGIN ' + 'PRIVATE KEY-----\nsecret')
        with self.assertRaisesRegex(ValueError, 'Private key'):
            sources.package(self.root, self.root / 'out')

    def test_local_source_symlink_is_not_followed(self):
        (self.root / 'tools/link').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            sources.package(self.root, self.root / 'out')

    def test_snapshot_changed_file_and_archive_tamper_detected(self):
        result = sources.package(self.root, self.root / 'out')
        manifest = self.root / 'out/source-manifest.json'
        _, _, issues = verifier.verify_source(manifest, self.root)
        self.assertEqual(issues, [])
        (self.root / 'README.md').write_text('changed after source packaging')
        _, _, issues = verifier.verify_source(manifest, self.root)
        self.assertEqual(issues[0]['code'], 'SOURCE_SNAPSHOT_STALE')
        with (self.root / 'out' / result['archive']).open('ab') as out:
            out.write(b'tampered')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            verifier.verify_source(manifest, self.root)

    def test_recipe_expansion_never_runs_subshell(self):
        fixture = self.root / 'bash/build.sh'
        fixture.parent.mkdir()
        fixture.write_text('TERMUX_PKG_LICENSE="GPL-3.0"\nTERMUX_PKG_VERSION=5.3.1\n'
                          'TERMUX_PKG_SRCURL="https://example.invalid/bash-${TERMUX_PKG_VERSION%.*}.tar.gz"\n'
                          'TERMUX_PKG_SHA256=' + '1' * 64 + '\nPATCH_CHECKSUMS[001]=' + '2' * 64 + '\n')
        license_name, files, problems = collector.recipe_sources(fixture)
        self.assertEqual(license_name, 'GPL-3.0')
        self.assertEqual(files[0]['url'], 'https://example.invalid/bash-5.3.tar.gz')
        self.assertTrue(files[1]['url'].endswith('bash53-001'))
        self.assertEqual(problems, [])
        with self.assertRaisesRegex(ValueError, 'Dynamic'):
            collector.expand('https://example.invalid/$(touch /tmp/unwanted)', {})

    def test_exact_ubuntu_source_version_not_a_similar_binary_version(self):
        digest = 'a' * 64
        path = self.root / 'Sources'
        path.write_text('Package: source-pkg\nVersion: 1.2-1\nDirectory: pool/main/s/source-pkg\nChecksums-Sha256:\n '
                        + digest + ' 17 source-pkg_1.2.orig.tar.xz\n\n')
        package = {'Package': 'binary-pkg', 'Version': '1.2-1+b1', 'Source': 'source-pkg (1.2-1)'}
        records = collector.ubuntu_records([package], [(path, 'https://example.invalid/Sources')])
        self.assertEqual(records[0]['sourceVersion'], '1.2-1')
        self.assertEqual(records[0]['sourceFiles'][0]['sha256'], digest)
        self.assertEqual(records[0]['unresolved'], [])
        snapshot = 'https://snapshot.ubuntu.com/ubuntu/20260908T120000Z/dists/noble/main/source/Sources.xz'
        historical = collector.ubuntu_records([package], [(path, snapshot)])
        self.assertTrue(historical[0]['sourceFiles'][0]['url'].startswith('https://snapshot.ubuntu.com/ubuntu/20260908T120000Z/pool/'))
        package['Source'] = 'source-pkg (1.2-2)'
        self.assertIn('Exact Ubuntu', collector.ubuntu_records([package], [(path, 'index')])[0]['unresolved'][0])

    def test_preserved_copyright_is_not_marked_license_complete(self):
        args = types.SimpleNamespace(root=self.root, output=self.root / 'assets', source_manifest=None,
            package_sources=None, gradle_artifacts=None, review=None)
        report = notices.generate(args)
        codes = {x['code'] for x in report['unresolved']}
        self.assertIn('RELEASE_LICENSE_REVIEW_REQUIRED', codes)
        self.assertIn('GRADLE_INVENTORY_MISSING', codes)
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.assertEqual(sha256(self.root / 'assets/third-party-notices.txt'), report['noticeSha256'])

    def test_notices_recognize_both_project_build_roots_without_exempting_maven(self):
        cache = self.root / '.local/gradle/caches/modules-2/files-2.1'
        locations = {
            'source-module': self.root / '.local/build-src/terminal-view/build/library.jar',
            'candidate-module': self.root / '.local/build-candidate/terminal-emulator/build/library.jar',
            'external-library': cache / 'example/external-library/1/hash/library.jar',
            'similar-prefix': self.root / '.local/build-candidate-cache/library.jar',
        }
        components = []
        original_notice = 'Copyright fixture owner\nOriginal dependency notice\n'
        for name, path in locations.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('META-INF/NOTICE', original_notice)
            components.append({'group': 'example', 'name': name, 'version': '1',
                               'file': str(path), 'sha256': sha256(path)})
        evidence = self.root / 'dependencies.json'
        evidence.write_bytes(json_bytes({'kind': 'z8-gradle-runtime-artifacts',
            'configuration': 'releaseRuntimeClasspath', 'components': components}))
        args = types.SimpleNamespace(root=self.root, output=self.root / 'assets', source_manifest=None,
            package_sources=None, gradle_artifacts=evidence, gradle_cache=cache, review=None)
        report = notices.generate(args)
        scopes = {item['name']: item['scope'] for item in report['components']}
        for name in ('source-module', 'candidate-module'):
            self.assertEqual(scopes['example:' + name + ':1'], 'application-project-module')
        for name in ('external-library', 'similar-prefix'):
            self.assertEqual(scopes['example:' + name + ':1'], 'bundled-maven')
        unresolved = {item['component'] for item in report['unresolved'] if item['code'] == 'LICENSE_UNRESOLVED'}
        self.assertEqual(unresolved, {'example:external-library:1', 'example:similar-prefix:1'})
        self.assertIn(original_notice, (self.root / 'assets/third-party-notices.txt').read_text())

    def test_runtime_effective_sources_require_recorded_hashes(self):
        fingerprint = 'a' * 64
        tree = self.root / '.local/runtime' / fingerprint[:20] / 'termux-packages'
        tree.mkdir(parents=True)
        recipe = tree / 'build.sh'
        recipe.write_text('exact historical build input')
        (tree / 'auth.json').write_text('never copy an entire build tree')
        script = self.root / 'tools/prepare-runtime.py'
        script.write_text('exact packaging input')
        provenance = {'recipeFingerprint':fingerprint, 'sourceOverlaySha256':{'build.sh':sha256(recipe)},
                      'packagingScriptSha256':sha256(script)}
        records, errors = collector.preserve_runtime_inputs(self.root, self.root / 'out', provenance, [])
        self.assertEqual(errors, [])
        self.assertEqual(len(records), 2)
        self.assertFalse(any('auth.json' in x['path'] for x in records))
        recipe.write_text('modified after binary build')
        records, errors = collector.preserve_runtime_inputs(self.root, self.root / 'out', provenance, [])
        self.assertEqual(len(records), 1)
        self.assertTrue(any('Missing exact effective' in x for x in errors))

    def test_bounded_archive_paths(self):
        for path in ('../credentials', '/absolute', 'x/../../auth.json', 'x\\secret'):
            with self.assertRaises(ValueError):
                safe_relative(path)
        self.assertEqual(safe_relative('downloads/hash/source.tar.gz'), 'downloads/hash/source.tar.gz')

    def test_installed_notice_original_bytes_are_preserved(self):
        path = self.root / 'runtime.zip'
        original = b'Copyright \xe9 original non-UTF8 bytes'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('var/lib/dpkg/status', 'Package: example\nVersion: 1\nStatus: install ok installed\n\n')
            archive.writestr('share/doc/example/copyright', original)
        packages, texts = archive_inventory(path)
        self.assertEqual(texts['share/doc/example/copyright'], original)


if __name__ == '__main__':
    unittest.main()
