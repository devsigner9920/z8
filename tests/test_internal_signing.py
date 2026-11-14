"""Private internal signing stays distinct from production; no real keys/candidates used."""
import argparse
import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import warnings
import zipfile
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


signing = module('internal_signing', 'sign-internal-test.py')
production = module('internal_test_production_guard', 'promote-release.py')
adapter = module('internal_test_key_adapter', 'upload-signing.py')


def archive(path, values):
    with zipfile.ZipFile(path, 'w') as output:
        for name, content in values.items():
            output.writestr(name, content)


class InternalSigning(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.inputs = self.root / 'candidate'
        self.inputs.mkdir()
        self.original = {'base/manifest/AndroidManifest.xml': b'fixture-manifest',
                         'base/assets/runtime.zip': b'fixture-runtime',
                         'META-INF/retained-notice.txt': b'retained legal notice'}
        self.aab = self.inputs / 'candidate.aab'
        self.apk = self.inputs / 'candidate.apk'
        archive(self.aab, self.original)
        self.apk.write_bytes(b'inert tested apk')
        self.config = dict(signing.release_config.DEFAULT, developerName='QA fixture',
                           supportEmail='qa@example.com', privacyUrl='https://policies.google.com/privacy',
                           sourceUrl='https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc1/z8-source.zip')
        self.paths = {name: self.inputs / name for name in (
            'candidate-metadata.json', 'release-config.json', 'compliance-report.json', 'qa-report.json')}
        self.paths['release-config.json'].write_text(json.dumps(self.config))
        self.metadata = dict(variant='candidate', mode='runtime', debuggable=False, uploadReady=False,
            targetSdk=36, aabSigning='unsigned', bundleValidated=True, bootstrapIncluded=True,
            guestImageIncluded=True, versionCode=2, versionName='0.1.0-rc1', aab='candidate.aab',
            apk='candidate.apk', aabSha256=signing.sha256(self.aab), sha256=signing.sha256(self.apk),
            releaseConfigSha256=signing.sha256(self.paths['release-config.json']),
            testSigningCertificateSha256='d' * 64)
        self.compliance = dict(kind='z8-release-compliance-verification', status='VERIFIED', blockers=[],
            inputs={'artifactSha256': self.metadata['aabSha256'], 'sourceUrlVerified': self.config['sourceUrl']})
        self.qa = dict(kind='z8-release-qa', status='INCOMPLETE', aabSha256=self.metadata['aabSha256'],
            apkSha256=self.metadata['sha256'], unresolved=['PRIVATE_FIXTURE_REASON: Claude task not tested'],
            checks={name: {'status': 'PASS'} for name in signing.CHECKS})
        self.qa['checks']['claudeAuthenticatedTask']['status'] = 'NOT_TESTED'
        self.persist()
        self.args = argparse.Namespace(candidate_metadata=self.paths['candidate-metadata.json'],
            release_config=self.paths['release-config.json'], compliance_report=self.paths['compliance-report.json'],
            qa_report=self.paths['qa-report.json'])
        self.cert = b'inert upload certificate'
        self.observed_test_certificate = 'd' * 64
        self.env = {'Z8_UPLOAD_KEYSTORE': 'private-fixture-key', 'Z8_UPLOAD_KEY_ALIAS': 'upload-fixture',
                   'Z8_UPLOAD_STORE_PASSWORD': 'PRIVATE_FIXTURE_PASSWORD',
                   'Z8_UPLOAD_KEY_PASSWORD': 'PRIVATE_FIXTURE_PASSWORD'}
        self.calls = []
        self.inject = None

    def persist(self):
        for name, value in (('candidate-metadata.json', self.metadata),
                            ('compliance-report.json', self.compliance), ('qa-report.json', self.qa)):
            self.paths[name].write_text(json.dumps(value, indent=2) + '\n')

    def validate(self, **changes):
        arguments = dict(metadata=self.metadata, candidate_hash=signing.sha256(self.aab),
                         apk_hash=signing.sha256(self.apk), config_hash=signing.sha256(self.paths['release-config.json']),
                         config=self.config, compliance=self.compliance, qa=self.qa)
        arguments.update(changes)
        signing.validate_evidence(**arguments)

    def fake_run(self, arguments, env):
        args = [str(value) for value in arguments]
        self.calls.append(args)
        if self.inject:
            self.inject(args)
        if '-exportcert' in args:
            Path(args[args.index('-file') + 1]).write_bytes(self.cert)
        elif Path(args[0]).name == 'apksigner':
            return 'Signer #1 certificate SHA-256 digest: ' + self.observed_test_certificate + '\n'
        elif '-signedjar' in args:
            target = Path(args[args.index('-signedjar') + 1])
            shutil.copyfile(args[args.index('-signedjar') + 2], target)
            with zipfile.ZipFile(target, 'a') as output:
                output.writestr('META-INF/UPLOAD.SF', b'fixture SF')
                output.writestr('META-INF/UPLOAD.RSA', b'fixture signature')
        elif '-printcert' in args:
            return '-----BEGIN CERTIFICATE-----\n' + base64.b64encode(self.cert).decode() + '\n-----END CERTIFICATE-----\n'
        return ''

    def execute(self):
        with patch.object(signing, 'ROOT', self.root), patch.object(signing, 'signing_env', return_value=(self.env, self.root / 'jdk')), \
                patch.object(signing.bundletool, 'ensure', return_value=self.root / 'bundletool.jar'), \
                patch.object(signing, 'run', side_effect=self.fake_run):
            return signing.sign(self.args)

    def test_partial_qa_is_preserved_byte_for_byte_without_production_approval(self):
        original = self.aab.read_bytes()
        record = self.execute()
        destination = self.root / 'artifacts/internal-tests/2'
        self.assertEqual(record['kind'], 'z8-internal-test-candidate')
        self.assertFalse(record['productionReady'])
        self.assertFalse(record['readyForConsoleUpload'])
        self.assertEqual(record['submission'], 'NOT_SUBMITTED')
        self.assertEqual(record['qa']['checks']['claudeAuthenticatedTask'], 'NOT_TESTED')
        self.assertEqual(record['qa']['status'], 'INCOMPLETE')
        self.assertEqual(record['qa']['unresolvedCount'], 1)
        self.assertNotIn('PRIVATE_FIXTURE_REASON', json.dumps(record))
        for name, path in self.paths.items():
            self.assertEqual(path.read_bytes(), (destination / 'evidence' / name).read_bytes())
        self.assertEqual(original, self.aab.read_bytes())
        self.assertEqual(destination.stat().st_mode & 0o077, 0)
        self.assertTrue(any('-strict' in call for call in self.calls))
        self.assertTrue(any('validate' in call for call in self.calls))
        with self.assertRaises(ValueError):
            production.validate_evidence(record, self.metadata['aabSha256'], self.metadata['releaseConfigSha256'],
                                         self.config, self.compliance, self.qa, {})
        # Even the original candidate cannot use the partial QA to pass the old production contract.
        with self.assertRaises(ValueError):
            production.validate_evidence(self.metadata, self.metadata['aabSha256'], self.metadata['releaseConfigSha256'],
                                         self.config, self.compliance, self.qa, {})

    def test_missing_changed_or_unverified_source_rejects_before_key_use(self):
        for change in ({'status': 'BLOCKED'}, {'blockers': ['source missing']}, {'blockers': None},
                       {'inputs': {'artifactSha256': 'a' * 64, 'sourceUrlVerified': self.config['sourceUrl']}},
                       {'inputs': {'artifactSha256': self.metadata['aabSha256'], 'sourceUrlVerified': 'https://wrong.invalid/'}}):
            with self.subTest(change=change):
                self.compliance.update(change)
                self.persist()
                with self.assertRaises(ValueError): self.execute()
                self.assertEqual(self.calls, [])
                self.compliance = dict(kind='z8-release-compliance-verification', status='VERIFIED', blockers=[],
                    inputs={'artifactSha256': self.metadata['aabSha256'], 'sourceUrlVerified': self.config['sourceUrl']})

    def test_artifact_configuration_and_runtime_identity_fail_closed(self):
        for name in ('candidate_hash', 'apk_hash', 'config_hash'):
            with self.subTest(name=name), self.assertRaises(ValueError): self.validate(**{name: 'a' * 64})
        for name, value in (('targetSdk', 28), ('debuggable', True), ('aabSigning', 'signed'),
                            ('uploadReady', True), ('mode', 'diagnostic'), ('bundleValidated', 1),
                            ('guestImageIncluded', False), ('versionCode', 3)):
            metadata = dict(self.metadata, **{name: value})
            with self.subTest(name=name), self.assertRaises(ValueError): self.validate(metadata=metadata)

    def test_missing_or_fabricated_qa_cannot_be_changed_into_pass(self):
        for field, value in (('kind', 'z8-internal-test-candidate'), ('status', 'PASS'),
                             ('aabSha256', 'a' * 64), ('apkSha256', 'b' * 64), ('unresolved', [])):
            qa = copy.deepcopy(self.qa); qa[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate(qa=qa)
        for status in (None, 'SKIP', True, ['PASS']):
            qa = copy.deepcopy(self.qa); qa['checks']['claudeAuthenticatedTask']['status'] = status
            with self.subTest(status=status), self.assertRaises(ValueError): self.validate(qa=qa)
        qa = copy.deepcopy(self.qa); del qa['checks']['claudeAuthenticatedTask']
        with self.assertRaises(ValueError): self.validate(qa=qa)
        qa = copy.deepcopy(self.qa)
        for value in qa['checks'].values(): value['status'] = 'NOT_TESTED'
        with self.assertRaises(ValueError): self.validate(qa=qa)

    def test_existing_destination_and_parent_redirect_are_preserved(self):
        target = self.root / 'artifacts/internal-tests/2'
        target.mkdir(parents=True)
        important = target / 'keep'; important.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'already exists'): self.execute()
        self.assertEqual(important.read_bytes(), b'keep')
        shutil.rmtree(target.parent)
        outside = self.root / 'outside'; outside.mkdir()
        target.parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'): self.execute()
        self.assertEqual(list(outside.iterdir()), [])

    def test_artifact_paths_and_symlink_inputs_are_rejected(self):
        for name in ('../candidate.aab', '/tmp/candidate.aab', 'sub\\candidate.aab'):
            with self.subTest(name=name), self.assertRaises(ValueError): signing.sibling(self.args.candidate_metadata, name, '.aab')
        actual = self.inputs / 'actual.aab'; self.aab.rename(actual); self.aab.symlink_to(actual)
        with self.assertRaisesRegex(ValueError, 'symlink'): self.execute()

    def test_subprocess_failure_never_leaves_completed_output(self):
        def fail(args):
            if '-verify' in args: raise ValueError('fixture failure')
        self.inject = fail
        with self.assertRaises(ValueError): self.execute()
        parent = self.root / 'artifacts/internal-tests'
        self.assertEqual(list(parent.iterdir()), [])

    def test_changed_evidence_after_signing_is_not_published(self):
        def change(args):
            if 'validate' in args: self.paths['qa-report.json'].write_text('changed')
        self.inject = change
        with self.assertRaisesRegex(ValueError, 'changed during signing'): self.execute()
        self.assertFalse((self.root / 'artifacts/internal-tests/2').exists())

    def test_upload_certificate_equal_to_test_certificate_is_rejected(self):
        self.metadata['testSigningCertificateSha256'] = hashlib.sha256(self.cert).hexdigest()
        self.observed_test_certificate = self.metadata['testSigningCertificateSha256']
        self.persist()
        with self.assertRaisesRegex(ValueError, 'development certificate'): self.execute()
        self.assertFalse(any('-signedjar' in call for call in self.calls))

    def test_wrong_signed_certificate_and_added_payload_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'differs'):
            signing.verify_signed_certificate('-----BEGIN CERTIFICATE-----\nY2VydA==\n-----END CERTIFICATE-----', 'a' * 64)
        after = self.inputs / 'signed.aab'
        for contents in (dict(self.original, **{'base/new': b'injected'}),
                         dict(self.original, **{'META-INF/retained-notice.txt': b'changed'}),
                         dict(self.original, **{'base/assets/runtime.zip': b'changed'})):
            archive(after, dict(contents, **{'META-INF/UPLOAD.SF': b'sf', 'META-INF/UPLOAD.RSA': b'rsa'}))
            with self.assertRaisesRegex(ValueError, 'payload'): signing.verify_payloads(self.aab, after)

    def test_duplicate_unsafe_or_unsigned_archives_are_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.aab, 'a') as output: output.writestr('base/assets/runtime.zip', b'duplicate')
        with self.assertRaisesRegex(ValueError, 'Duplicate'): signing.payloads(self.aab)
        archive(self.aab, {'../outside': b'no'})
        with self.assertRaisesRegex(ValueError, 'Unsafe'): signing.payloads(self.aab)
        archive(self.aab, self.original)
        with self.assertRaisesRegex(ValueError, 'signature'): signing.verify_payloads(self.aab, self.aab)
        archive(self.aab, dict(self.original, **{'META-INF/OTHER.SF': b'pre-signed'}))
        with self.assertRaisesRegex(ValueError, 'unsigned'): signing.payloads(self.aab, unsigned=True)

    def test_private_key_environment_rejects_debug_alias_permissions_and_redirect(self):
        key = self.root / 'fixture.p12'; key.write_bytes(b'inert'); key.chmod(0o600)
        env = dict(self.env, Z8_UPLOAD_KEYSTORE=str(key))
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(signing.signing_env()[0]['Z8_UPLOAD_KEYSTORE'], str(key))
            key.chmod(0o644)
            with self.assertRaisesRegex(ValueError, 'owner-only'): signing.signing_env()
            key.chmod(0o600)
        with patch.dict(os.environ, dict(env, Z8_UPLOAD_KEY_ALIAS='z8-debug'), clear=True):
            with self.assertRaises(ValueError): signing.signing_env()
        redirected = self.root / 'redirect.p12'; redirected.symlink_to(key)
        with patch.dict(os.environ, dict(env, Z8_UPLOAD_KEYSTORE=str(redirected)), clear=True):
            with self.assertRaisesRegex(ValueError, 'symlink'): signing.signing_env()

    def test_command_errors_and_cli_summary_do_not_print_private_evidence(self):
        with patch.object(signing.subprocess, 'run', side_effect=subprocess.CalledProcessError(
                1, ['private-path'], output='PRIVATE_OUTPUT', stderr='PRIVATE_ERROR')):
            with self.assertRaises(ValueError) as caught: signing.run(['fixture'], self.env)
        self.assertNotIn('PRIVATE', str(caught.exception))
        record = self.execute(); output = io.StringIO()
        with patch.object(signing, 'sign', return_value=record), patch.object(signing.sys, 'argv',
                ['sign-internal-test.py', '--candidate-metadata', 'a', '--compliance-report', 'b', '--qa-report', 'c']), redirect_stdout(output):
            signing.main()
        self.assertNotIn('PRIVATE', output.getvalue())
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertFalse(json.loads(output.getvalue())['productionReady'])

    def test_key_adapter_routes_internal_test_without_modifying_production(self):
        with patch.object(adapter.sys, 'argv', ['upload-signing.py', 'internal-test', '--qa-report', 'fixture']), \
                patch.object(adapter, 'signing_environment', return_value=(self.env, {})), \
                patch.object(adapter.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            with self.assertRaises(SystemExit) as result: adapter.main()
        self.assertEqual(result.exception.code, 0)
        self.assertTrue(run.call_args.args[0][1].endswith('/tools/sign-internal-test.py'))
        self.assertEqual(run.call_args.kwargs['env'], self.env)


class RealJarSignature(unittest.TestCase):
    def test_strict_verification_rejects_wrong_identity_and_unsigned_added_entry(self):
        jdk = ROOT / '.local/jdk/Contents/Home'
        if not (jdk / 'bin/keytool').is_file(): self.skipTest('Pinned local JDK unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); env = os.environ.copy()
            env['Z8_TEST_KEY_PASSWORD'] = 'inert-test-password'
            key = root / 'fixture.p12'
            for alias in ('upload-fixture', 'other-fixture'):
                signing.run([jdk / 'bin/keytool', '-genkeypair', '-keystore', key, '-storetype', 'PKCS12',
                    '-alias', alias, '-keyalg', 'RSA', '-keysize', '2048', '-validity', '30',
                    '-dname', 'CN=Inert unit test', '-storepass:env', 'Z8_TEST_KEY_PASSWORD'], env)
            before = root / 'unsigned.aab'; after = root / 'signed.aab'
            archive(before, {'base/assets/file': b'fixture', 'META-INF/license.txt': b'preserved'})
            signing.run([jdk / 'bin/jarsigner', '-keystore', key, '-storepass:env', 'Z8_TEST_KEY_PASSWORD',
                         '-signedjar', after, before, 'upload-fixture'], env)
            verify = [jdk / 'bin/jarsigner', '-verify', '-strict', '-keystore', key,
                      '-storepass:env', 'Z8_TEST_KEY_PASSWORD', after]
            signing.run([*verify, 'upload-fixture'], env)
            signing.verify_payloads(before, after)
            cert = root / 'cert.der'
            signing.run([jdk / 'bin/keytool', '-exportcert', '-keystore', key, '-alias', 'upload-fixture',
                         '-storepass:env', 'Z8_TEST_KEY_PASSWORD', '-file', cert], env)
            signing.verify_signed_certificate(signing.run([jdk / 'bin/keytool', '-printcert', '-jarfile', after, '-rfc'], env), signing.sha256(cert))
            with self.assertRaises(ValueError): signing.run([*verify, 'other-fixture'], env)
            with zipfile.ZipFile(after, 'a') as output: output.writestr('base/injected', b'unsigned')
            with self.assertRaises(ValueError): signing.run([*verify, 'upload-fixture'], env)


if __name__ == '__main__':
    unittest.main()
