#!/usr/bin/env python3
"""Create or restore-check an encrypted private upload-key backup on macOS.

This tool never uploads files, prints secrets, or declares off-device recovery
complete. Keep the recovery password separate from the encrypted image.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import secrets
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('upload_signing', ROOT / 'tools/upload-signing.py')
upload_signing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(upload_signing)
FILES = ('upload.p12', 'password', 'identity.json', 'upload-certificate.der')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def command(argv, password=None, env=None):
    result = subprocess.run([str(x) for x in argv], input=password,
                            capture_output=True, env=env)
    if result.returncode:
        raise ValueError('Backup command failed; private output has been withheld')
    return result.stdout


def private_dir(path):
    path = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Backup paths cannot contain symlinks')
    return upload_signing.private_path(path, directory=True)


def create(destination):
    destination = Path(os.path.abspath(destination))
    if destination.exists() or any(p.is_symlink() for p in (destination, *destination.parents)):
        raise ValueError('Use a new, non-symlink backup directory')
    _, identity = upload_signing.signing_environment()
    source = private_dir(upload_signing.IDENTITY)
    files = {name: digest(upload_signing.private_path(source / name)) for name in FILES}
    destination.mkdir(parents=True, mode=0o700)
    recovery = destination / 'recovery-password.txt'
    # This outer secret is never included in the image or command arguments.
    with recovery.open('x') as stream:
        stream.write(secrets.token_urlsafe(48) + '\n')
    password = recovery.read_bytes()
    image = destination / 'z8-upload-key-backup.dmg'
    with tempfile.TemporaryDirectory(prefix='.source-', dir=destination) as temporary:
        stage = Path(temporary)
        for name in FILES:
            shutil.copyfile(source / name, stage / name)
            if digest(stage / name) != files[name]:
                raise ValueError('Source changed while preparing the backup')
        command(['diskutil', 'image', 'create', 'from', '--encrypt', '--stdinpassphrase',
                 '--plist', '--format', 'UDZO', '--volumeName', 'Z8UploadRecovery',
                 stage, image], password=password)
    if any(digest(source / name) != files[name] for name in FILES):
        raise ValueError('Original signing identity changed while creating the image')
    receipt = {'schemaVersion': 1, 'kind': 'z8-private-encrypted-key-backup',
               'createdAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'encryption': 'macOS disk image AES-256', 'format': 'UDZO/APFS',
               'image': image.name, 'imageSha256': digest(image), 'imageBytes': image.stat().st_size,
               'files': files, 'certificateSha256': identity['certificateSha256'],
               'recoveryPasswordFile': recovery.name, 'externalCopyVerified': False,
               'independentRecoveryPasswordStorageConfirmed': False}
    write_json(destination / 'backup-private.json', receipt)
    return {'status': 'ENCRYPTED_LOCAL_COPY_CREATED', 'directory': str(destination),
            'imageSha256': receipt['imageSha256'], 'imageBytes': receipt['imageBytes'],
            'externalBackupVerified': False}


def verify(directory, downloaded):
    directory = private_dir(directory)
    receipt = json.loads(upload_signing.private_path(directory / 'backup-private.json').read_bytes())
    downloaded = upload_signing.private_path(Path(os.path.abspath(downloaded)))
    if digest(downloaded) != receipt['imageSha256']:
        raise ValueError('Downloaded copy differs from the original encrypted image')
    if plistlib.loads(command(['hdiutil', 'isencrypted', '-plist', downloaded])).get('encrypted') is not True:
        raise ValueError('Expected an encrypted disk image')
    password = upload_signing.private_path(directory / receipt['recoveryPasswordFile']).read_bytes()
    jdk = ROOT / '.local/jdk/Contents/Home'
    with tempfile.TemporaryDirectory(prefix='.restore-', dir=directory) as temporary:
        work = Path(temporary); mount = work / 'mount'; mount.mkdir()
        attached = False
        try:
            raw = command(['diskutil', 'image', 'attach', '--readOnly',
                '--nobrowse', '--stdinpassphrase', '--plist', '--mountPoint', mount,
                downloaded], password=password)
            attached = True
            result = plistlib.loads(raw)
            entities = result.get('system-entities', [])
            if not any(e.get('mount-point') == str(mount) for e in entities):
                raise ValueError('Unexpected restore mount')
            if not os.statvfs(mount).f_flag & os.ST_RDONLY:
                raise ValueError('Restore mount must be read-only')
            # APFS-created filesystem metadata is not part of the key payload.
            visible = {p.name for p in mount.iterdir() if not p.name.startswith('.')}
            if visible != set(FILES):
                raise ValueError('Unexpected backup payload')
            for name in FILES:
                path = mount / name
                if path.is_symlink() or not path.is_file() or digest(path) != receipt['files'][name]:
                    raise ValueError('Restored signing file differs')
            metadata = json.loads((mount / 'identity.json').read_bytes())
            if metadata['alias'] != upload_signing.ALIAS:
                raise ValueError('Unexpected restored alias')
            env = os.environ.copy()
            env['Z8_RESTORED_STORE_PASSWORD'] = (mount / 'password').read_text().strip()
            cert = command([jdk / 'bin/keytool', '-exportcert', '-keystore', mount / 'upload.p12',
                '-alias', metadata['alias'], '-storepass:env', 'Z8_RESTORED_STORE_PASSWORD'], env=env)
            if hashlib.sha256(cert).hexdigest() != receipt['certificateSha256']:
                raise ValueError('Restored private key certificate differs')
            unsigned = work / 'probe.jar'; signed = work / 'probe-signed.jar'
            with zipfile.ZipFile(unsigned, 'w') as archive:
                archive.writestr('restore-probe.txt', 'Z8 inert private-key restoration check\n')
            command([jdk / 'bin/jarsigner', '-keystore', mount / 'upload.p12', '-storepass:env',
                'Z8_RESTORED_STORE_PASSWORD', '-keypass:env', 'Z8_RESTORED_STORE_PASSWORD',
                '-signedjar', signed, unsigned, metadata['alias']], env=env)
            command([jdk / 'bin/jarsigner', '-verify', '-strict', '-keystore', mount / 'upload.p12',
                '-storepass:env', 'Z8_RESTORED_STORE_PASSWORD', signed, metadata['alias']], env=env)
        finally:
            if attached or os.path.ismount(mount):
                command(['diskutil', 'eject', mount])
    result = {'schemaVersion': 1, 'kind': 'z8-key-backup-restoration', 'status': 'PASS',
              'verifiedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'encryptedImageSha256': receipt['imageSha256'], 'fileCount': len(FILES),
              'allRestoredFileHashesMatch': True, 'readOnlyRestore': True,
              'certificateSha256': receipt['certificateSha256'],
              'restoredPrivateKeySigningAndStrictVerification': 'PASS', 'mountEjected': True,
              'scope': 'Restored the supplied image; caller must independently prove external download '
                       'and recovery-password custody before claiming a disaster-recoverable backup.'}
    write_json(directory / 'restore-verification.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'verify'))
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--downloaded', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == 'create':
        result = create(args.directory)
    else:
        if not args.downloaded:
            parser.error('--downloaded is required for verify')
        result = verify(args.directory, args.downloaded)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, plistlib.InvalidFileException):
        raise SystemExit('backup-upload-key: validation or backup failed; secrets withheld; no external '
                         'backup completion was recorded. Preserve originals and inspect private state.')
