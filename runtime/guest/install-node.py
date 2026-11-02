#!/usr/bin/python3
"""Pinned official Node LTS inside the marked project guest; never modifies HOME."""
import hashlib
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import uuid


def official(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != 'nodejs.org' or not parsed.path.startswith('/dist/'):
        raise ValueError('Expected official Node HTTPS distribution URL')
    return url


def lock_data(path):
    data = json.loads(path.read_text())
    if data.get('schemaVersion') != 1 or data.get('architecture') != 'linux-arm64' or not re.fullmatch(r'v24\.\d+\.\d+', data.get('version', '')):
        raise ValueError('Unsupported Node lock')
    for field in ('sha256', 'checksumsSha256'):
        if not re.fullmatch('[0-9a-f]{64}', data.get(field, '')):
            raise ValueError('Node checksum is not pinned')
    for field in ('url', 'checksumsUrl'):
        official(data[field])
    expected = 'https://nodejs.org/dist/' + data['version'] + '/'
    if data['url'] != expected + 'node-' + data['version'] + '-linux-arm64.tar.xz' or data['checksumsUrl'] != expected + 'SHASUMS256.txt':
        raise ValueError('Node version and URL differ')
    return data


def download(url, destination, digest, maximum):
    # Retrying replaces only a private temporary download, never an installed version.
    for attempt in range(3):
        try:
            total = 0
            checksum = hashlib.sha256()
            with urllib.request.urlopen(official(url), timeout=30) as response, destination.open('wb') as out:
                official(response.geturl())
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > maximum:
                        raise ValueError('Node download exceeds size limit')
                    checksum.update(chunk)
                    out.write(chunk)
            if checksum.hexdigest() != digest:
                raise ValueError('Node download checksum mismatch')
            return
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def extract(archive, target, prefix):
    with tarfile.open(archive, 'r:xz') as source:
        entries = source.getmembers()
        if len(entries) > 30000:
            raise ValueError('Too many Node archive members')
        total = 0
        seen = set()
        for member in entries:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != prefix or member.name in seen:
                raise ValueError('Unsafe Node archive path')
            seen.add(member.name)
            if not (member.isfile() or member.isdir() or member.issym()):
                raise ValueError('Unsupported Node archive member')
            total += member.size
            if total > 512 * 1024 * 1024:
                raise ValueError('Node expansion exceeds size limit')
            if member.issym():
                # Node's npm/npx links may walk up within their own archive root.
                linked = os.path.normpath(str(path.parent / member.linkname))
                if PurePosixPath(member.linkname).is_absolute() or not (linked == prefix or linked.startswith(prefix + '/')):
                    raise ValueError('Node archive link escapes package')
        source.extractall(target, filter='data')
    node = target / prefix / 'bin/node'
    with node.open('rb') as binary:
        header = binary.read(20)
    if header[:6] != b'\x7fELF\x02\x01' or int.from_bytes(header[18:20], 'little') != 183:
        raise ValueError('Node executable must be Linux ARM64')
    return target / prefix


def versions(prefix, data):
    environment = dict(os.environ, PATH=str(prefix / 'bin') + ':/usr/bin:/bin')
    for name, expected in (('node', data['version']), ('npm', data['npm'])):
        value = subprocess.check_output([str(prefix / 'bin' / name), '--version'], env=environment, timeout=30, text=True).strip()
        if value != expected:
            raise ValueError(name + ' version differs from lock: ' + value)


def install():
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64') or Path('/etc/z8/guest-target').read_text().strip() != 'z8-guest-v1' or os.getuid() != 0:
        raise ValueError('Node installation requires the marked ARM64 z8 guest')
    data = lock_data(Path(__file__).with_name('node.lock.json'))
    root = Path('/opt/z8/node')
    for path in (Path('/opt'), Path('/opt/z8'), root):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError('Node install directory is not private storage')
        path.mkdir(exist_ok=True)
    # Advisory lock is released by the kernel even if Android kills the process.
    descriptor = os.open(root / '.install.lock', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another Node setup is running in this project')
        _install_locked(root, Path('/usr/local/bin'), data)


def _install_locked(root, bindir, data):
    """Publish only validated versions; called with the guest install lock held."""
    _remove_interrupted_staging(root)
    version = root / data['version']
    current = root / 'current'
    if current.exists() and not current.is_symlink():
        raise ValueError('Refusing to replace a user Node directory')
    if version.exists() or version.is_symlink():
        if version.is_symlink() or not version.is_dir():
            raise ValueError('Node version path is not a directory')
        versions(version, data)
    else:
        with tempfile.TemporaryDirectory(prefix='.install-', dir=root) as temporary:
            temporary = Path(temporary)
            # Only explicitly owned staging may be reclaimed on the next run.
            # The exclusive install lock ensures no current download is removed.
            (temporary / '.z8-node-staging').write_text('z8-node-staging-v1\n' + temporary.name + '\n')
            sums = temporary / 'checksums'
            download(data['checksumsUrl'], sums, data['checksumsSha256'], 128 * 1024)
            filename = data['url'].rsplit('/', 1)[1]
            if data['sha256'] + '  ' + filename not in sums.read_text().splitlines():
                raise ValueError('Node checksum index differs from lock')
            archive = temporary / filename
            download(data['url'], archive, data['sha256'], 128 * 1024 * 1024)
            expanded = extract(archive, temporary / 'unpack', 'node-' + data['version'] + '-linux-arm64')
            versions(expanded, data)
            os.rename(expanded, version)
    # An Android kill can leave the temporary link behind. A fresh identifier
    # avoids a future process reusing that PID and failing forever on the link.
    link = root / ('.current-' + uuid.uuid4().hex)
    try:
        link.symlink_to(data['version'], target_is_directory=True)
        os.replace(link, current)
    finally:
        link.unlink(missing_ok=True)
    # Keep ordinary login shells working even when /etc/profile rebuilds PATH.
    if bindir.is_symlink():
        raise ValueError('Refusing a linked /usr/local/bin')
    bindir.mkdir(exist_ok=True)
    for name in ('node', 'npm', 'npx'):
        destination = bindir / name
        target = '/opt/z8/node/current/bin/' + name
        if destination.is_symlink() and os.readlink(destination) == target:
            continue
        if destination.exists() or destination.is_symlink():
            raise ValueError('Preserving existing ' + str(destination) + '; review before installing Node')
        destination.symlink_to(target)
    print('Node ' + data['version'] + ' / npm ' + data['npm'] + ' verified inside this project.')


def _remove_interrupted_staging(root):
    for entry in root.iterdir():
        if not re.fullmatch(r'\.install-[a-z0-9_]{8}', entry.name) or entry.is_symlink() or not entry.is_dir():
            continue
        marker = entry / '.z8-node-staging'
        try:
            descriptor = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, 'rb') as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    continue
                receipt = source.read(128)
        except OSError:
            continue
        if receipt == ('z8-node-staging-v1\n' + entry.name + '\n').encode():
            # rmtree removes links inside the staging tree, never their targets.
            shutil.rmtree(entry)


if __name__ == '__main__':
    install()
