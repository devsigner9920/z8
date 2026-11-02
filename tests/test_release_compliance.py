"""Release evidence boundary tests: no credentials, no recipe execution, no false green."""
import hashlib
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
from release_compliance import archive_inventory, bytes_sha, deb822, json_bytes, safe_relative, sha256


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
        self.root = Path(self.temp.name)
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
