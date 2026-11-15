"""Exercise backup boundaries with inert fixtures and no native/key operations."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('upload_backup', ROOT / 'tools/backup-upload-key.py')
backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup)


class UploadBackupTests(unittest.TestCase):
    def setUp(self):
        previous_mask = os.umask(0o077)
        self.addCleanup(os.umask, previous_mask)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / 'inert-identity'
        self.source.mkdir(mode=0o700)
        self.certificate = b'inert certificate fixture, not a key'
        self.inner_password = 'INERT-INNER-PASSWORD-' + 'x' * 40
        self.outer_password = 'INERT-OUTER-PASSWORD-' + 'y' * 40
        self.metadata = {
            'kind': 'z8-private-upload-identity', 'alias': backup.upload_signing.ALIAS,
            'certificateSha256': hashlib.sha256(self.certificate).hexdigest(),
            'externalBackupVerified': False,
        }
        self.original = {
            'upload.p12': b'inert PKCS12 fixture, never usable for signing',
            'password': (self.inner_password + '\n').encode(),
            'identity.json': json.dumps(self.metadata).encode(),
            'upload-certificate.der': self.certificate,
        }
        for name, content in self.original.items():
            (self.source / name).write_bytes(content)
        # Any forgotten subprocess mock must fail before running a native tool.
        self.start_patch(patch.object(backup.subprocess, 'run',
                                     side_effect=AssertionError('Unexpected native operation')))
        self.start_patch(patch.object(backup.upload_signing, 'IDENTITY', self.source))
        self.identity_check = self.start_patch(patch.object(
            backup.upload_signing, 'signing_environment', return_value=({}, self.metadata)))
        self.start_patch(patch.object(backup.secrets, 'token_urlsafe',
                                     return_value=self.outer_password))
        self.directory = self.root / 'backup'
        self.events = []
        self.staged = None
        self.mount = None

    def start_patch(self, item):
        result = item.start()
        self.addCleanup(item.stop)
        return result

    def create_command(self, argv, password=None, env=None):
        args = [str(value) for value in argv]
        self.assertEqual(args[:4], ['diskutil', 'image', 'create', 'from'])
        self.assertIn('--encrypt', args)
        self.assertIn('--stdinpassphrase', args)
        self.assertEqual(args[args.index('--format') + 1], 'UDZO')
        self.assertEqual(password, (self.outer_password + '\n').encode())
        self.assertNotIn(self.outer_password, ' '.join(args))
        stage, image = Path(argv[-2]), Path(argv[-1])
        self.staged = {p.name: p.read_bytes() for p in stage.iterdir()}
        self.assertEqual(self.staged, self.original)
        self.assertNotIn('recovery-password.txt', self.staged)
        self.assertFalse((stage / 'recovery-password.txt').exists())
        image.write_bytes(b'inert encrypted-image placeholder')
        self.events.append('create')
        return plistlib.dumps({})

    def make_backup(self):
        with patch.object(backup, 'command', side_effect=self.create_command):
            result = backup.create(self.directory)
        self.downloaded = self.root / 'downloaded-backup.dmg'
        shutil.copyfile(self.directory / 'z8-upload-key-backup.dmg', self.downloaded)
        self.receipt = json.loads((self.directory / 'backup-private.json').read_text())
        return result

    def restore_command(self, argv, password=None, env=None):
        args = [str(value) for value in argv]
        self.assertNotIn(self.outer_password, ' '.join(args))
        self.assertNotIn(self.inner_password, ' '.join(args))
        if args[:2] == ['hdiutil', 'isencrypted']:
            self.events.append('encryption-check')
            return plistlib.dumps({'encrypted': True})
        if args[:3] == ['diskutil', 'image', 'attach']:
            self.events.append('attach')
            self.assertIn('--readOnly', args)
            self.assertIn('--nobrowse', args)
            self.assertIn('--stdinpassphrase', args)
            self.assertEqual(password, (self.outer_password + '\n').encode())
            self.mount = Path(argv[args.index('--mountPoint') + 1])
            for name, content in self.staged.items():
                (self.mount / name).write_bytes(content)
            return plistlib.dumps({'system-entities': [{'mount-point': str(self.mount)}]})
        if args[:2] == ['diskutil', 'eject']:
            self.assertEqual(Path(argv[-1]), self.mount)
            self.events.append('eject')
            return b''
        if Path(args[0]).name == 'keytool':
            self.events.append('certificate')
            self.assertEqual(Path(argv[args.index('-keystore') + 1]), self.mount / 'upload.p12')
            self.assertEqual(env['Z8_RESTORED_STORE_PASSWORD'], self.inner_password)
            return self.certificate
        if Path(args[0]).name == 'jarsigner':
            self.assertEqual(Path(argv[args.index('-keystore') + 1]), self.mount / 'upload.p12')
            self.assertEqual(env['Z8_RESTORED_STORE_PASSWORD'], self.inner_password)
            self.assertIn('-storepass:env', args)
            if '-verify' in args:
                self.assertIn('-strict', args)
                self.events.append('strict-verify')
            else:
                self.assertIn('-keypass:env', args)
                signed = Path(argv[args.index('-signedjar') + 1])
                unsigned = Path(argv[-2])
                with zipfile.ZipFile(unsigned) as archive:
                    self.assertEqual(archive.namelist(), ['restore-probe.txt'])
                # This is only an orchestration fixture, not a cryptographic test.
                shutil.copyfile(unsigned, signed)
                self.events.append('sign')
            return b''
        self.fail('Unexpected mocked command')

    @contextlib.contextmanager
    def restore_mocks(self, command=None, readonly=True):
        with patch.object(backup, 'command', side_effect=command or self.restore_command), \
             patch.object(backup.os, 'statvfs', return_value=types.SimpleNamespace(
                 f_flag=os.ST_RDONLY if readonly else 0)):
            yield

    def assert_no_restore_receipt(self):
        self.assertFalse((self.directory / 'restore-verification.json').exists())

    def test_command_keeps_password_out_of_argv_and_hides_child_failure_output(self):
        marker = b'INERT-SECRET-OUTPUT-MUST-NOT-BE-PRINTED'
        for status in (0, 1):
            with self.subTest(exit_code=status):
                result = types.SimpleNamespace(returncode=status, stdout=marker, stderr=marker)
                out, err = io.StringIO(), io.StringIO()
                with patch.object(backup.subprocess, 'run', return_value=result) as run, \
                     contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    if status:
                        with self.assertRaises(ValueError) as failure:
                            backup.command(['inert-tool'], password=marker)
                        self.assertNotIn(marker.decode(), str(failure.exception))
                    else:
                        self.assertEqual(backup.command(['inert-tool'], password=marker), marker)
                self.assertEqual(run.call_args.args[0], ['inert-tool'])
                self.assertEqual(run.call_args.kwargs['input'], marker)
                self.assertTrue(run.call_args.kwargs['capture_output'])
                self.assertEqual(out.getvalue() + err.getvalue(), '')

    def test_create_stages_only_four_files_and_preserves_originals(self):
        (self.source / 'unrelated-secret.txt').write_text('inert excluded extra file')
        result = self.make_backup()
        self.assertEqual(self.staged, self.original)
        self.assertEqual({n: (self.source / n).read_bytes() for n in self.original}, self.original)
        self.assertFalse(result['externalBackupVerified'])
        self.assertFalse(self.receipt['externalCopyVerified'])
        self.assertFalse(self.receipt['independentRecoveryPasswordStorageConfirmed'])
        self.assertEqual(set(self.receipt['files']), set(self.original))
        self.assertNotIn(self.outer_password, json.dumps(result))
        self.assertNotIn(self.inner_password, json.dumps(result))
        self.assertEqual((self.directory / 'recovery-password.txt').stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.directory.glob('.source-*')), [])

    def test_create_refuses_existing_or_redirected_destination_before_key_access(self):
        existing = self.root / 'existing'
        existing.mkdir()
        (existing / 'keep').write_text('preserve')
        redirect = self.root / 'redirect'
        redirect.symlink_to(existing, target_is_directory=True)
        for destination in (existing, redirect / 'new'):
            with self.subTest(destination=destination.name), \
                 self.assertRaisesRegex(ValueError, 'new, non-symlink'):
                backup.create(destination)
        self.identity_check.assert_not_called()
        self.assertEqual((existing / 'keep').read_text(), 'preserve')
        self.assertFalse((existing / 'new').exists())

    def test_create_rejects_symlinked_source_file_without_native_operation(self):
        original = self.source / 'upload.p12'
        alternate = self.root / 'fixture-payload'
        original.rename(alternate)
        original.symlink_to(alternate)
        with patch.object(backup, 'command') as command, \
             self.assertRaisesRegex(ValueError, 'non-symlink'):
            backup.create(self.directory)
        command.assert_not_called()
        self.assertFalse(self.directory.exists())

    def test_create_does_not_record_success_if_original_changes_during_native_creation(self):
        def mutate_after_copy(argv, **kwargs):
            result = self.create_command(argv, **kwargs)
            (self.source / 'identity.json').write_text('changed inert fixture')
            return result
        with patch.object(backup, 'command', side_effect=mutate_after_copy), \
             self.assertRaisesRegex(ValueError, 'Original signing identity changed'):
            backup.create(self.directory)
        self.assertFalse((self.directory / 'backup-private.json').exists())
        self.assertEqual(list(self.directory.glob('.source-*')), [])

    def test_restore_checks_real_pipeline_order_but_does_not_claim_external_custody(self):
        self.make_backup()
        self.events.clear()
        with self.restore_mocks():
            result = backup.verify(self.directory, self.downloaded)
        self.assertEqual(self.events, ['encryption-check', 'attach', 'certificate',
                                       'sign', 'strict-verify', 'eject'])
        self.assertEqual(result['status'], 'PASS')
        self.assertTrue(result['mountEjected'])
        self.assertNotIn('externalBackupVerified', result)
        self.assertIn('caller must independently prove external download', result['scope'])
        self.assertEqual(json.loads((self.directory / 'backup-private.json').read_text()), self.receipt)
        self.assertEqual({n: (self.source / n).read_bytes() for n in self.original}, self.original)
        self.assertEqual(list(self.directory.glob('.restore-*')), [])

    def test_download_mismatch_and_symlink_are_rejected_before_mounting(self):
        self.make_backup()
        link = self.root / 'download-link.dmg'
        link.symlink_to(self.downloaded)
        with patch.object(backup, 'command') as command:
            with self.assertRaisesRegex(ValueError, 'non-symlink'):
                backup.verify(self.directory, link)
            self.downloaded.write_bytes(b'changed encrypted-image fixture')
            with self.assertRaisesRegex(ValueError, 'Downloaded copy differs'):
                backup.verify(self.directory, self.downloaded)
        command.assert_not_called()
        self.assert_no_restore_receipt()

    def test_unencrypted_image_is_rejected_even_when_download_hash_matches(self):
        self.make_backup()
        with patch.object(backup, 'command', return_value=plistlib.dumps({'encrypted': False})) as command, \
             self.assertRaisesRegex(ValueError, 'encrypted disk image'):
            backup.verify(self.directory, self.downloaded)
        self.assertEqual(command.call_count, 1)
        self.assert_no_restore_receipt()

    def test_malformed_attach_plist_still_ejects_and_never_records_success(self):
        self.make_backup()
        def malformed(argv, **kwargs):
            result = self.restore_command(argv, **kwargs)
            return b'not a plist' if list(map(str, argv[:3])) == ['diskutil', 'image', 'attach'] else result
        with self.restore_mocks(malformed), self.assertRaises(plistlib.InvalidFileException):
            backup.verify(self.directory, self.downloaded)
        self.assertEqual(self.events[-2:], ['attach', 'eject'])
        self.assertNotIn('sign', self.events)
        self.assert_no_restore_receipt()

    def test_failed_attach_with_observed_partial_mount_is_ejected(self):
        self.make_backup()
        def interrupted(argv, **kwargs):
            result = self.restore_command(argv, **kwargs)
            if list(map(str, argv[:3])) == ['diskutil', 'image', 'attach']:
                raise ValueError('inert interrupted native attach')
            return result
        with self.restore_mocks(interrupted), \
             patch.object(backup.os.path, 'ismount', side_effect=lambda p: p == self.mount), \
             self.assertRaisesRegex(ValueError, 'interrupted native attach'):
            backup.verify(self.directory, self.downloaded)
        self.assertEqual(self.events[-2:], ['attach', 'eject'])
        self.assert_no_restore_receipt()

    def test_writable_mount_is_ejected_before_reading_or_using_keys(self):
        self.make_backup()
        with self.restore_mocks(readonly=False), self.assertRaisesRegex(ValueError, 'read-only'):
            backup.verify(self.directory, self.downloaded)
        self.assertEqual(self.events[-2:], ['attach', 'eject'])
        self.assertNotIn('certificate', self.events)
        self.assert_no_restore_receipt()

    def test_wrong_mount_path_is_rejected_and_requested_mount_is_ejected(self):
        self.make_backup()
        def wrong_mount(argv, **kwargs):
            result = self.restore_command(argv, **kwargs)
            if list(map(str, argv[:3])) == ['diskutil', 'image', 'attach']:
                return plistlib.dumps({'system-entities': [{'mount-point': '/not-the-requested-mount'}]})
            return result
        with self.restore_mocks(wrong_mount), self.assertRaisesRegex(ValueError, 'Unexpected restore mount'):
            backup.verify(self.directory, self.downloaded)
        self.assertEqual(self.events[-1], 'eject')
        self.assert_no_restore_receipt()

    def test_modified_missing_extra_or_symlink_payload_is_rejected_before_signing(self):
        self.make_backup()
        for change in ('modified', 'missing', 'extra', 'symlink'):
            with self.subTest(change=change):
                self.events.clear()
                def changed(argv, **kwargs):
                    result = self.restore_command(argv, **kwargs)
                    if list(map(str, argv[:3])) == ['diskutil', 'image', 'attach']:
                        target = self.mount / 'upload.p12'
                        if change == 'modified':
                            target.write_bytes(b'different inert PKCS12')
                        elif change == 'extra':
                            (self.mount / 'unexpected.txt').write_text('inert')
                        else:
                            target.unlink()
                            if change == 'symlink':
                                target.symlink_to(self.source / 'upload.p12')
                    return result
                with self.restore_mocks(changed), self.assertRaisesRegex(ValueError, 'payload|file differs'):
                    backup.verify(self.directory, self.downloaded)
                self.assertEqual(self.events[-1], 'eject')
                self.assertNotIn('certificate', self.events)
                self.assert_no_restore_receipt()

    def test_certificate_mismatch_ejects_before_signing(self):
        self.make_backup()
        def mismatched(argv, **kwargs):
            result = self.restore_command(argv, **kwargs)
            return b'wrong inert certificate' if Path(str(argv[0])).name == 'keytool' else result
        with self.restore_mocks(mismatched), self.assertRaisesRegex(ValueError, 'certificate differs'):
            backup.verify(self.directory, self.downloaded)
        self.assertEqual(self.events[-1], 'eject')
        self.assertNotIn('sign', self.events)
        self.assert_no_restore_receipt()

    def test_strict_signature_failure_ejects_without_success_receipt(self):
        self.make_backup()
        def reject_signature(argv, **kwargs):
            result = self.restore_command(argv, **kwargs)
            if '-verify' in argv:
                raise ValueError('inert strict signature failure')
            return result
        with self.restore_mocks(reject_signature), self.assertRaisesRegex(ValueError, 'signature failure'):
            backup.verify(self.directory, self.downloaded)
        self.assertEqual(self.events[-3:], ['sign', 'strict-verify', 'eject'])
        self.assert_no_restore_receipt()

    def test_eject_failure_never_claims_a_completed_restore(self):
        self.make_backup()
        def reject_eject(argv, **kwargs):
            result = self.restore_command(argv, **kwargs)
            if list(map(str, argv[:2])) == ['diskutil', 'eject']:
                raise ValueError('inert eject failure')
            return result
        with self.restore_mocks(reject_eject), self.assertRaisesRegex(ValueError, 'eject failure'):
            backup.verify(self.directory, self.downloaded)
        self.assert_no_restore_receipt()


if __name__ == '__main__':
    unittest.main()
