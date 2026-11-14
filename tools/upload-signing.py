#!/usr/bin/env python3
"""Prepare a private upload identity, or invoke the evidence-gated promotion tool."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ROOT / '.local/keys/z8-play-upload'
ALIAS = 'z8-play-upload'


def private_path(path, directory=False):
    """Do not follow redirected key material or use group/world-accessible secrets."""
    path = Path(path)
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError('Upload key parent cannot be a symlink')
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Upload identity must use owner-only, non-symlink files and directories')
    return path


def keytool(jdk, arguments, env):
    try:
        return subprocess.run([str(jdk / 'bin/keytool'), *arguments], env=env,
                              check=True, capture_output=True).stdout
    except subprocess.CalledProcessError:
        # Do not echo subprocess output or environment values into reports.
        raise ValueError('Upload key operation failed; private key material was not printed') from None


def signing_environment(identity=IDENTITY, jdk=None):
    identity = private_path(identity, directory=True)
    for name in ('upload.p12', 'password', 'identity.json', 'upload-certificate.der'):
        private_path(identity / name)
    metadata = json.loads((identity / 'identity.json').read_text())
    if metadata.get('kind') != 'z8-private-upload-identity' or metadata.get('alias') != ALIAS:
        raise ValueError('Unexpected upload identity metadata')
    password = (identity / 'password').read_text().strip()
    if len(password) < 32 or any(c.isspace() for c in password):
        raise ValueError('Invalid private password record')
    env = os.environ.copy()
    env.update(Z8_UPLOAD_KEYSTORE=str((identity / 'upload.p12').resolve()),
               Z8_UPLOAD_KEY_ALIAS=ALIAS, Z8_UPLOAD_STORE_PASSWORD=password,
               Z8_UPLOAD_KEY_PASSWORD=password)
    jdk = jdk or Path(env.get('JAVA_HOME', ROOT / '.local/jdk/Contents/Home'))
    certificate = keytool(jdk, ['-exportcert', '-keystore', env['Z8_UPLOAD_KEYSTORE'],
        '-alias', ALIAS, '-storepass:env', 'Z8_UPLOAD_STORE_PASSWORD'], env)
    digest = hashlib.sha256(certificate).hexdigest()
    if (digest != metadata.get('certificateSha256') or
            certificate != (identity / 'upload-certificate.der').read_bytes()):
        raise ValueError('Upload certificate differs from its retained identity')
    return env, metadata


def create(identity=IDENTITY, jdk=None):
    identity = Path(identity)
    # Check parents before mkdir: never create key material through a symlink.
    for parent in identity.parents:
        if parent.is_symlink():
            raise ValueError('Upload key parent cannot be a symlink')
    identity.parent.mkdir(parents=True, exist_ok=True)
    if identity.exists() or identity.is_symlink():
        raise ValueError('Upload identity already exists; verify it instead of replacing it')
    jdk = jdk or Path(os.environ.get('JAVA_HOME', ROOT / '.local/jdk/Contents/Home'))
    env = os.environ.copy()
    password = secrets.token_urlsafe(48)
    env['Z8_NEW_UPLOAD_PASSWORD'] = password
    old_mask = os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(prefix='.upload-', dir=identity.parent) as temporary:
            stage = Path(temporary)
            keytool(jdk, ['-genkeypair', '-keystore', str(stage / 'upload.p12'),
                '-storetype', 'PKCS12', '-alias', ALIAS, '-keyalg', 'RSA', '-keysize', '3072',
                '-sigalg', 'SHA256withRSA', '-validity', '10000',
                '-dname', 'CN=Z8 Upload,OU=Android Upload,O=Romi Ethsy',
                '-storepass:env', 'Z8_NEW_UPLOAD_PASSWORD', '-keypass:env', 'Z8_NEW_UPLOAD_PASSWORD'], env)
            certificate = keytool(jdk, ['-exportcert', '-keystore', str(stage / 'upload.p12'),
                '-alias', ALIAS, '-storepass:env', 'Z8_NEW_UPLOAD_PASSWORD'], env)
            (stage / 'password').write_text(password + '\n')
            (stage / 'upload-certificate.der').write_bytes(certificate)
            metadata = {'schemaVersion': 1, 'kind': 'z8-private-upload-identity', 'alias': ALIAS,
                'algorithm': 'RSA-3072', 'certificateSha256': hashlib.sha256(certificate).hexdigest(),
                'createdAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'purpose': 'Google Play upload key; not a Play-managed app signing key',
                'registeredWithPlay': False, 'externalBackupVerified': False}
            (stage / 'identity.json').write_text(json.dumps(metadata, indent=2) + '\n')
            for path in stage.iterdir():
                path.chmod(0o600)
            stage.rename(identity)
    finally:
        os.umask(old_mask)
    _, metadata = signing_environment(identity, jdk)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'verify', 'promote', 'internal-test'))
    args, promotion_args = parser.parse_known_args()
    if args.action not in ('promote', 'internal-test') and promotion_args:
        parser.error('Additional arguments are only accepted for promote or internal-test')
    if args.action == 'create':
        metadata = create()
    else:
        env, metadata = signing_environment()
        if args.action in ('promote', 'internal-test'):
            # Internal-test signing is separate; it never grants production approval.
            script = 'promote-release.py' if args.action == 'promote' else 'sign-internal-test.py'
            raise SystemExit(subprocess.run([sys.executable, str(ROOT / 'tools' / script),
                                             *promotion_args], env=env).returncode)
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as failure:
        sys.exit('upload-signing: ' + str(failure))
