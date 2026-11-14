"""Protect the upload key boundary without putting real secrets in test reports."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('upload_signing', ROOT / 'tools/upload-signing.py')
signing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(signing)


class UploadIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_existing_identity_is_not_replaced(self):
        destination = self.root / 'identity'
        destination.mkdir()
        original = destination / 'important-key'
        original.write_bytes(b'original key bytes')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            signing.create(destination)
        self.assertEqual(original.read_bytes(), b'original key bytes')

    def test_creation_rejects_redirected_parent_before_generating_key(self):
        (self.root / 'outside').mkdir()
        (self.root / 'redirect').symlink_to(self.root / 'outside', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            signing.create(self.root / 'redirect' / 'identity')
        self.assertEqual(list((self.root / 'outside').iterdir()), [])

    def test_private_files_cannot_be_symlinks_or_group_readable(self):
        secret = self.root / 'secret'
        secret.write_text('fixture')
        secret.chmod(0o640)
        with self.assertRaisesRegex(ValueError, 'owner-only'):
            signing.private_path(secret)
        secret.chmod(0o600)
        self.assertEqual(signing.private_path(secret), secret)
        link = self.root / 'link'
        link.symlink_to(secret)
        with self.assertRaisesRegex(ValueError, 'non-symlink'):
            signing.private_path(link)

    def test_verification_rejects_redirected_parent(self):
        actual = self.root / 'actual'
        actual.mkdir(mode=0o700)
        (self.root / 'redirect').symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'parent cannot be a symlink'):
            signing.signing_environment(self.root / 'redirect' / 'identity')

    def test_certificate_change_is_rejected_before_promotion(self):
        identity = self.root / 'identity'
        identity.mkdir(mode=0o700)
        values = {'upload.p12': b'fixture', 'password': b'test-password-' + b'x' * 40,
                  'upload-certificate.der': b'original',
                  'identity.json': json.dumps({'kind': 'z8-private-upload-identity',
                      'alias': signing.ALIAS, 'certificateSha256': 'a' * 64}).encode()}
        for name, data in values.items():
            path = identity / name
            path.write_bytes(data)
            path.chmod(0o600)
        with patch.object(signing, 'keytool', return_value=b'changed'):
            with self.assertRaisesRegex(ValueError, 'certificate differs'):
                signing.signing_environment(identity)


if __name__ == '__main__':
    unittest.main()
