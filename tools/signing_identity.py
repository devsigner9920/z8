"""Bind local test APK certificates to release evidence; aliases are not identities."""
import re


def certificate_sha256(output):
    certificates = re.findall(r'^Signer #(\d+) certificate SHA-256 digest: ([0-9a-fA-F]{64})$', output, re.MULTILINE)
    if len(certificates) != 1 or certificates[0][0] != '1':
        raise ValueError('Expected exactly one verified APK signing certificate')
    return certificates[0][1].lower()


def verify_test_certificate(observed, recorded, upload):
    if any(not isinstance(value, str) or not re.fullmatch('[0-9a-fA-F]{64}', value)
           for value in (observed, recorded, upload)):
        raise ValueError('A valid certificate fingerprint is missing')
    if observed.lower() != recorded.lower():
        raise ValueError('Candidate test APK signing identity changed')
    if observed.lower() == upload.lower():
        raise ValueError('Upload certificate is the candidate development certificate, regardless of its path or alias')
