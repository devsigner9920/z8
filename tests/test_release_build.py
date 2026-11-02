"""Release guard regressions: public metadata, observed APK facts and candidate isolation.

All credentials/addresses below are inert test fixtures. No signing, build, network or
account access occurs; the Groovy test evaluates only generated public string literals.
"""
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('release_build_under_test', ROOT / 'tools/build-app.py')
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)
config = build.release_config
PROMOTION_SPEC = importlib.util.spec_from_file_location('release_promotion_under_test', ROOT / 'tools/promote-release.py')
promotion = importlib.util.module_from_spec(PROMOTION_SPEC)
PROMOTION_SPEC.loader.exec_module(promotion)

BADGING = """package: name='dev.devsigner.z8' versionCode='2' versionName='0.1.0-rc1' platformBuildVersionName='16' compileSdkVersion='36' compileSdkVersionCodename='16'
sdkVersion:'28'
targetSdkVersion:'36'
uses-permission: name='android.permission.INTERNET'
application-label:'z8'
launchable-activity: name='com.termux.app.TermuxActivity' label='z8' icon=''
native-code: 'arm64-v8a'
"""


class PublicReleaseConfig(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='z8-release-config-test-')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.path = self.directory / 'public-config.json'

    def load(self, changes=None, production=False):
        data = dict(config.DEFAULT)
        data.update(changes or {})
        self.path.write_text(json.dumps(data))
        return config.load(self.path, production=production)

    def test_candidate_can_have_unpublished_contact_but_production_cannot(self):
        self.assertEqual(self.load()['developerName'], '')
        with self.assertRaises(ValueError):
            self.load(production=True)
        supplied = {'developerName': 'Release QA fixture', 'supportEmail': 'qa@example.com',
                    'privacyUrl': 'https://policies.google.com/privacy', 'sourceUrl': 'https://github.com/termux/termux-app'}
        self.assertEqual(self.load(supplied, production=True)['developerName'], supplied['developerName'])

    def test_unknown_secret_fields_missing_fields_and_invalid_versions_fail_closed(self):
        for changes in ({'uploadPassword': 'INERT_FIXTURE'}, {'schemaVersion': True}, {'schemaVersion': 2},
                        {'versionCode': True}, {'versionCode': 0}, {'versionCode': 2100000001},
                        {'versionCode': '2'}, {'versionName': 'latest'}, {'versionName': '1.2.3\n'},
                        {'developerName': ' leading'}, {'developerName': 'bad\nline'},
                        {'supportEmail': 'not-an-address'}, {'policyDate': '2026-02-30'}):
            with self.subTest(changes=list(changes)):
                with self.assertRaises(ValueError): self.load(changes)
        data = dict(config.DEFAULT); del data['sourceUrl']
        self.path.write_text(json.dumps(data))
        with self.assertRaises(ValueError): config.load(self.path)

    def test_private_reserved_placeholder_and_malformed_urls_are_rejected(self):
        invalid = ['http://policies.google.com/privacy', 'https://user:fixture@policies.google.com/',
                   'https://@policies.google.com/', 'https://localhost/policy', 'https://a.localhost/',
                   'https://127.0.0.1/', 'https://[::1]/', 'https://10.0.0.1/', 'https://192.168.1.1/',
                   'https://100.64.0.1/', 'https://192.0.2.1/', 'https://[2001:db8::1]/',
                   'https://224.0.0.1/', 'https://2130706433/', 'https://127.1/',
                   'https://example.com/', 'https://privacy.example.org/', 'https://src.example.net/',
                   'https://public.invalid/', 'https://public.test/', 'https://public.example/',
                   'https://policies.google.com:wrong/', 'https://policies.google.com:65536/',
                   'https://policies.google.com:0/', 'https://policies.google.com:/',
                   'https://bad host.google.com/', 'https://bad_host.google.com/',
                   'https://policies.google.com/has space', 'https://policies.google.com/%zz',
                   'https://policies.google.com\\@localhost/', 'https:///privacy', 'https://[::1']
        for field in ('privacyUrl', 'sourceUrl'):
            for url in invalid:
                with self.subTest(field=field, url=url):
                    with self.assertRaises(ValueError): self.load({field: url})

    def test_public_https_format_is_accepted_without_network_lookup(self):
        for url in ('https://policies.google.com/privacy', 'https://github.com/termux/termux-app?tab=readme-ov-file#readme',
                    'https://developers.google.com:443/android/한글', 'https://8.8.8.8/policy'):
            with self.subTest(url=url):
                self.assertEqual(self.load({'privacyUrl': url})['privacyUrl'], url)

    def test_generated_gradle_values_are_literals_even_with_groovy_interpolation_syntax(self):
        jars = sorted((ROOT / '.local/gradle').glob('wrapper/dists/gradle-*/**/lib/groovy-*.jar'))
        jars = [jar for jar in jars if jar.name[7:8].isdigit()]
        jdk = ROOT / '.local/jdk/Contents/Home/bin/java'
        java = str(jdk) if jdk.is_file() else shutil.which('java')
        if not jars or not java:
            self.skipTest('Bundled Gradle Groovy runtime and Java are required')
        data = self.load({'developerName': 'Z8 $unbound ${7 * 6} O\'Reilly \\ folder "한글"'})
        script = self.directory / 'public-fields.groovy'
        script.write_text('def values = [:]\ndef buildConfigField = { type, name, value -> values[name] = value }\n'
                          + config.gradle_public_fields(data)
                          + '\nvalues.each { key, value -> println(key + ":" + value.getBytes("UTF-8").encodeBase64().toString()) }\n')
        result = subprocess.run([java, '-cp', str(jars[-1]), 'groovy.ui.GroovyMain', str(script)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = {line.split(':', 1)[0]: base64.b64decode(line.split(':', 1)[1]).decode()
                    for line in result.stdout.splitlines()}
        self.assertEqual(observed, {name: json.dumps(data[key], ensure_ascii=False) for key, name in config.PUBLIC_FIELDS.items()})


class FinalArtifactFacts(unittest.TestCase):
    def test_release_and_debug_badging_are_verified_as_observed(self):
        release = build.manifest_facts(BADGING)
        build.validate_facts(release, dict(config.DEFAULT), False)
        self.assertEqual(release, {'applicationId': 'dev.devsigner.z8', 'versionCode': 2,
                                  'versionName': '0.1.0-rc1', 'minSdk': 28, 'targetSdk': 36,
                                  'compileSdk': 36, 'debuggable': False, 'abis': ['arm64-v8a']})
        debug = build.manifest_facts(BADGING + 'application-debuggable\n')
        build.validate_facts(debug, dict(config.DEFAULT), True)
        with self.assertRaises(ValueError): build.validate_facts(debug, dict(config.DEFAULT), False)
        with self.assertRaises(ValueError): build.validate_facts(release, dict(config.DEFAULT), True)

    def test_identity_version_sdk_and_abi_drift_cannot_reuse_requested_metadata(self):
        drift = [('dev.devsigner.z8', 'com.termux'), ("versionCode='2'", "versionCode='1'"),
                 ("versionName='0.1.0-rc1'", "versionName='0.1.0-g0'"), ("sdkVersion:'28'", "sdkVersion:'21'"),
                 ("targetSdkVersion:'36'", "targetSdkVersion:'28'"),
                 ("compileSdkVersion='36'", "compileSdkVersion='35'"),
                 ("native-code: 'arm64-v8a'", "native-code: 'arm64-v8a' 'x86_64'"),
                 ("native-code: 'arm64-v8a'", "native-code: 'armeabi-v7a'")]
        for old, new in drift:
            with self.subTest(changed=old):
                with self.assertRaises(ValueError):
                    build.validate_facts(build.manifest_facts(BADGING.replace(old, new)), dict(config.DEFAULT), False)

    def test_missing_manifest_fields_fail_before_artifact_publication(self):
        for line in BADGING.splitlines():
            if line.startswith(('package:', 'sdkVersion:', 'targetSdkVersion:', 'native-code:')):
                with self.subTest(field=line.split(':', 1)[0]):
                    with self.assertRaises(ValueError): build.manifest_facts(BADGING.replace(line + '\n', ''))


class CandidateSigningIsolation(unittest.TestCase):
    def test_ambient_release_signing_switch_is_not_forwarded_to_any_build_child(self):
        class ReachedBuild(Exception): pass
        with tempfile.TemporaryDirectory(prefix='z8-candidate-isolation-test-') as temporary:
            root = Path(temporary); local = root / '.local'; jdk = local / 'jdk/Contents/Home'; sdk = local / 'android-sdk'
            for path in (jdk / 'bin/java', sdk / 'platform-tools/adb', local / 'keys/z8-debug.jks'):
                path.parent.mkdir(parents=True, exist_ok=True); path.write_text('inert test fixture')
            (root / 'upstream/termux-app').mkdir(parents=True)
            (root / 'tools').mkdir(); (root / 'release').mkdir()
            (root / 'tools/sources.lock.json').write_text(json.dumps({'termuxApp': {'commit': 'fixture-commit'}}))
            (root / 'release/config.json').write_text(json.dumps(config.DEFAULT))
            children = []
            def fake_run(argv, **kwargs):
                args = [str(value) for value in argv]
                if 'env' in kwargs:
                    children.append((args, kwargs['env'].copy()))
                    self.assertNotIn('Z8_RELEASE_BUILD', kwargs['env'])
                if any(value.endswith('prepare-app.py') for value in args):
                    (local / 'build-candidate').mkdir()
                if './gradlew' in args: raise ReachedBuild()
            def fake_capture(argv, **kwargs):
                args = [str(value) for value in argv]
                if 'rev-parse' in args: return 'fixture-commit\n'
                if 'status' in args: return ''
                raise AssertionError('Unexpected external command')
            with patch.object(build, 'ROOT', root), patch.object(build, 'LOCAL', local), \
                    patch.object(build.sys, 'argv', ['build-app.py', '--variant', 'candidate']), \
                    patch.object(build.sys, 'version_info', (3, 12)), \
                    patch.dict(os.environ, {'Z8_RELEASE_BUILD': '1', 'Z8_UPLOAD_KEYSTORE': 'INERT_UPLOAD_FIXTURE',
                                            'Z8_UPLOAD_STORE_PASSWORD': 'INERT_PASSWORD_FIXTURE', 'Z8_GIT': '/fixture/git'}, clear=True), \
                    patch.object(build, 'run', side_effect=fake_run), \
                    patch.object(build.subprocess, 'check_output', side_effect=fake_capture):
                with self.assertRaises(ReachedBuild): build.main()
                self.assertEqual(os.environ['Z8_RELEASE_BUILD'], '1')
            preparation = next(args for args, env in children if any(value.endswith('prepare-app.py') for value in args))
            gradle = next(args for args, env in children if './gradlew' in args)
            self.assertIn('--variant', preparation); self.assertIn('candidate', preparation)
            self.assertIn(':app:bundleRelease', gradle)


class PromotionEvidence(unittest.TestCase):
    def setUp(self):
        self.artifact_hash = 'a' * 64
        self.config_hash = 'b' * 64
        self.public = dict(config.DEFAULT, developerName='Release QA fixture', supportEmail='qa@example.com',
                           privacyUrl='https://policies.google.com/privacy', sourceUrl='https://github.com/termux/termux-app')
        self.metadata = {'variant': 'candidate', 'debuggable': False, 'targetSdk': 36, 'aabSigning': 'unsigned',
                         'bundleValidated': True, 'bootstrapIncluded': True, 'guestImageIncluded': True,
                         'aabSha256': self.artifact_hash, 'releaseConfigSha256': self.config_hash,
                         'versionCode': 2, 'versionName': '0.1.0-rc1'}
        self.compliance = {'kind': 'z8-release-compliance-verification', 'status': 'VERIFIED', 'blockers': [],
                           'inputs': {'artifactSha256': self.artifact_hash, 'sourceUrlVerified': self.public['sourceUrl']}}
        self.checks = ('freshInstall', 'updatePreservesProjects', 'projectDeletion', 'runtimeAndChildProcesses',
                       'codexAuthenticatedTask', 'claudeAuthenticatedTask', 'physicalDevice', 'pageSize16KiB',
                       'previewDataDeletion', 'backAndKeyboard', 'foregroundStopAndNotifications')
        self.qa = {'kind': 'z8-release-qa', 'status': 'PASS', 'aabSha256': self.artifact_hash, 'unresolved': [],
                   'checks': {name: {'status': 'PASS'} for name in self.checks}}
        self.decisions = {'aabSha256': self.artifact_hash, 'reviewedBy': 'inert test operator',
                          'reviewedAt': '2026-11-01T00:00:00Z', 'dataSafetyReviewed': True,
                          'externalCodePolicyReviewed': True, 'claudeDistributionTermsReviewed': True,
                          'guestDistributionTermsReviewed': True, 'storeListingReviewed': True,
                          'foregroundServiceDeclarationPrepared': True}

    def validate(self, **changes):
        arguments = dict(metadata=self.metadata, candidate_hash=self.artifact_hash, config_hash=self.config_hash,
                         config=self.public, compliance=self.compliance, qa=self.qa, decisions=self.decisions)
        arguments.update(changes)
        promotion.validate_evidence(**arguments)

    def test_complete_evidence_for_exact_candidate_is_accepted(self):
        self.validate()

    def test_artifact_config_source_and_each_evidence_hash_must_match(self):
        for key in ('candidate_hash', 'config_hash'):
            with self.subTest(changed=key), self.assertRaises(ValueError):
                self.validate(**{key: 'c' * 64})
        replacements = [('metadata', 'aabSha256'), ('metadata', 'releaseConfigSha256'),
                        ('qa', 'aabSha256'), ('decisions', 'aabSha256')]
        for target, field in replacements:
            value = copy.deepcopy(getattr(self, target)); value[field] = 'c' * 64
            with self.subTest(target=target, field=field), self.assertRaises(ValueError):
                self.validate(**{target: value})
        for field in ('artifactSha256', 'sourceUrlVerified'):
            value = copy.deepcopy(self.compliance); value['inputs'][field] = 'changed'
            with self.subTest(input=field), self.assertRaises(ValueError): self.validate(compliance=value)
        changed = dict(self.public, versionCode=3)
        with self.assertRaises(ValueError): self.validate(config=changed)

    def test_every_required_device_check_must_explicitly_pass(self):
        for name in self.checks:
            for status in (None, 'FAIL', 'SKIP', 'NOT_TESTED', True):
                value = copy.deepcopy(self.qa)
                if status is None: del value['checks'][name]
                else: value['checks'][name]['status'] = status
                with self.subTest(check=name, status=status), self.assertRaises(ValueError): self.validate(qa=value)
        for target, field, replacement in [('qa', 'unresolved', ['unfinished fixture']),
                                            ('qa', 'status', 'NOT_TESTED'), ('compliance', 'status', 'BLOCKED'),
                                            ('compliance', 'blockers', ['missing license fixture'])]:
            value = copy.deepcopy(getattr(self, target)); value[field] = replacement
            with self.subTest(target=target, field=field), self.assertRaises(ValueError): self.validate(**{target: value})

    def test_operator_choices_require_explicit_boolean_true_and_named_review(self):
        fields = ('dataSafetyReviewed', 'externalCodePolicyReviewed', 'claudeDistributionTermsReviewed',
                  'guestDistributionTermsReviewed', 'storeListingReviewed', 'foregroundServiceDeclarationPrepared')
        for name in fields:
            for status in (None, False, 'true', 1):
                value = dict(self.decisions)
                if status is None: del value[name]
                else: value[name] = status
                with self.subTest(decision=name, status=status), self.assertRaises(ValueError): self.validate(decisions=value)
        for name in ('reviewedBy', 'reviewedAt'):
            value = dict(self.decisions); del value[name]
            with self.subTest(missing=name), self.assertRaises(ValueError): self.validate(decisions=value)

    def test_unvalidated_debug_incomplete_or_wrong_target_candidate_is_rejected(self):
        changes = [('variant', 'debug'), ('debuggable', True), ('targetSdk', 28), ('aabSigning', 'development-key')]
        changes += [(field, value) for field in ('bundleValidated', 'bootstrapIncluded', 'guestImageIncluded')
                    for value in (False, None, 'false', 1)]
        for field, replacement in changes:
            value = dict(self.metadata); value[field] = replacement
            with self.subTest(field=field, replacement=replacement), self.assertRaises(ValueError):
                self.validate(metadata=value)
