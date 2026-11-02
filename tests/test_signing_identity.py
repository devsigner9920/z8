import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('signing_identity', ROOT / 'tools/signing_identity.py')
signing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(signing)


class ReleaseSigningIdentity(unittest.TestCase):
    def test_single_verified_certificate_is_parsed_case_insensitively(self):
        self.assertEqual(signing.certificate_sha256('Verifies\nSigner #1 certificate SHA-256 digest: ' + 'AB' * 32 + '\n'), 'ab' * 32)

    def test_missing_malformed_or_multiple_signers_are_rejected(self):
        for output in ('', 'Signer #1 certificate SHA-256 digest: abc',
                       'Signer #2 certificate SHA-256 digest: ' + 'ab' * 32,
                       'Signer #1 certificate SHA-256 digest: ' + 'ab' * 32 + '\nSigner #2 certificate SHA-256 digest: ' + 'cd' * 32):
            with self.subTest(output=output[:30]):
                with self.assertRaises(ValueError): signing.certificate_sha256(output)

    def test_external_development_certificate_cannot_be_reused_under_another_alias(self):
        default_development, external_development, upload = 'aa' * 32, 'bb' * 32, 'cc' * 32
        # Aliases and local default-key paths deliberately do not determine certificate identity.
        self.assertNotEqual(default_development, external_development)
        with self.assertRaises(ValueError):
            signing.verify_test_certificate(external_development, external_development, external_development.upper())
        signing.verify_test_certificate(external_development, external_development, upload)

    def test_changed_or_unrecorded_candidate_certificate_is_rejected(self):
        for recorded in (None, '', 'invalid', 'aa' * 32):
            with self.subTest(recorded=recorded):
                with self.assertRaises(ValueError): signing.verify_test_certificate('bb' * 32, recorded, 'cc' * 32)


if __name__ == '__main__':
    unittest.main()
