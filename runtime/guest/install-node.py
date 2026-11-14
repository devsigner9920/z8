#!/usr/bin/python3
"""Pinned official Node LTS inside the marked project guest; never modifies HOME."""
import hashlib
import argparse
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

VERSION = r'v24\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})'


def official(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != 'nodejs.org' or not parsed.path.startswith('/dist/'):
        raise ValueError('Expected official Node HTTPS distribution URL')
    return url

class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        official(new_url)
        return super().redirect_request(request, fp, code, message, headers, new_url)


def metadata(url, maximum):
    request = urllib.request.Request(official(url), headers={'User-Agent': 'z8-node-installer/1', 'Accept-Encoding': 'identity'})
    deadline = time.monotonic() + 30
    with urllib.request.build_opener(OfficialRedirect()).open(request, timeout=10) as response:
        official(response.geturl())
        result = bytearray()
        while True:
            block = response.read(min(65536, maximum + 1 - len(result)))
            if not block:
                return bytes(result)
            result.extend(block)
            if len(result) > maximum or time.monotonic() > deadline:
                raise ValueError('Node metadata exceeds its response limit')


def selected_lock(version):
    if not isinstance(version, str) or not re.fullmatch(VERSION, version):
        raise ValueError('Choose an exact Node v24.X.Y maintenance release')
    baseline = lock_data(Path(__file__).with_name('node.lock.json'))
    if version == baseline['version']:
        return dict(baseline, selectedRelease=True)
    releases = json.loads(metadata('https://nodejs.org/dist/index.json', 2 * 1024 * 1024))
    if not isinstance(releases, list):
        raise ValueError('Unexpected Node release index')
    matches = [item for item in releases if isinstance(item, dict) and item.get('version') == version]
    if len(matches) != 1:
        raise ValueError('Selected Node release is not unique in the official index')
    item = matches[0]
    if not isinstance(item.get('lts'), str) or not item['lts'] or 'linux-arm64' not in item.get('files', []) \
            or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', item.get('npm') or ''):
        raise ValueError('Selected release is not a supported ARM64 Node 24 LTS distribution')
    root = 'https://nodejs.org/dist/' + version + '/'
    filename = 'node-' + version + '-linux-arm64.tar.xz'
    sums = metadata(root + 'SHASUMS256.txt', 128 * 1024)
    hashes = [line.split()[0] for line in sums.decode('ascii').splitlines()
              if re.fullmatch(r'[0-9a-f]{64}  ' + re.escape(filename), line)]
    if len(hashes) != 1:
        raise ValueError('Official Node checksums lack a unique ARM64 archive')
    return dict(schemaVersion=1, architecture='linux-arm64', version=version, npm=item['npm'], lts=item['lts'],
        url=root + filename, sha256=hashes[0], checksumsUrl=root + 'SHASUMS256.txt',
        checksumsSha256=hashlib.sha256(sums).hexdigest(), selectedRelease=True)


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
            deadline = time.monotonic() + 600
            with urllib.request.build_opener(OfficialRedirect()).open(official(url), timeout=30) as response, destination.open('wb') as out:
                official(response.geturl())
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > maximum:
                        raise ValueError('Node download exceeds size limit')
                    if time.monotonic() > deadline:
                        raise ValueError('Node download exceeds time limit')
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


def install(selected_version=None):
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64') or Path('/etc/z8/guest-target').read_text().strip() != 'z8-guest-v1' or os.getuid() != 0:
        raise ValueError('Node installation requires the marked ARM64 z8 guest')
    data = selected_lock(selected_version) if selected_version is not None else lock_data(Path(__file__).with_name('node.lock.json'))
    root = Path('/opt/z8/node')
    for path in (Path('/opt'), Path('/opt/z8'), root):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError('Node install directory is not private storage')
        path.mkdir(exist_ok=True)
    # Advisory lock is released by the kernel even if Android kills the process.
    descriptor = os.open(root / '.install.lock', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(descriptor, 'w') as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise ValueError('Node installation lock is not a regular file; it was preserved')
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
    previous_target = os.readlink(current) if current.is_symlink() else None
    if current.exists() and not current.is_symlink():
        raise ValueError('Refusing to replace a user Node directory')
    # Check every public command before changing the selected version pointer.
    validate_launchers(bindir)
    verified_current = None
    if current.is_symlink():
        selected = os.readlink(current)
        if not re.fullmatch(VERSION, selected) or (root / selected).is_symlink() or not (root / selected).is_dir():
            raise ValueError('Preserving an unrecognized Node installation')
        verify_managed(root / selected)
        verified_current = selected
    if version.exists() or version.is_symlink():
        if version.is_symlink() or not version.is_dir():
            raise ValueError('Node version path is not a directory')
        versions(version, data)
        if verified_current != data['version']:
            verify_managed(version)
        if not (version / '.z8-node-receipt.json').exists():
            write_receipt(version, data)
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
            write_receipt(expanded, data)
            os.rename(expanded, version)
    # A user or another tool may change launchers while downloads are running.
    validate_launchers(bindir)
    if (os.readlink(current) if current.is_symlink() else None) != previous_target \
            or current.exists() and not current.is_symlink():
        raise ValueError('Node selection changed during installation; it was preserved')
    if previous_target is not None and previous_target != data['version']:
        verify_managed(root / previous_target)
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


def validate_launchers(bindir):
    if bindir.is_symlink():
        raise ValueError('Refusing a linked /usr/local/bin')
    for name in ('node', 'npm', 'npx'):
        destination = bindir / name
        if destination.is_symlink() and os.readlink(destination) == '/opt/z8/node/current/bin/' + name:
            continue
        if destination.exists() or destination.is_symlink():
            raise ValueError('Preserving existing ' + str(destination) + '; review before installing Node')


def write_receipt(version, data):
    receipt = version / '.z8-node-receipt.json'
    value = {'manager': 'z8-node-v1', 'version': data['version'], 'npm': data['npm'],
        'artifactSha256': data['sha256'], 'url': data['url'], 'files': tree_records(version)}
    pending = version / ('.z8-receipt-' + uuid.uuid4().hex)
    try:
        with pending.open('x') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(pending, receipt)
    finally:
        pending.unlink(missing_ok=True)


def tree_records(root):
    result, total = [], 0
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if name == '.z8-node-receipt.json':
            continue
        info = path.lstat()
        entry = {'path': name, 'mode': stat.S_IMODE(info.st_mode)}
        if path.is_symlink():
            entry.update(kind='link', target=os.readlink(path))
        elif path.is_dir():
            entry.update(kind='directory')
        elif path.is_file():
            total += info.st_size
            if total > 512 * 1024 * 1024:
                raise ValueError('Managed Node installation exceeds its size limit')
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            entry.update(kind='file', size=info.st_size, sha256=digest.hexdigest())
        else:
            raise ValueError('Unsupported entry in managed Node installation')
        result.append(entry)
        if len(result) > 30000:
            raise ValueError('Managed Node installation exceeds its entry limit')
    return result


def verify_managed(version):
    receipt = version / '.z8-node-receipt.json'
    if receipt.is_symlink():
        raise ValueError('Preserving changed Node receipt')
    if receipt.is_file():
        if receipt.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('Node receipt exceeds size limit')
        saved = json.loads(receipt.read_text())
        if saved.get('manager') != 'z8-node-v1' or saved.get('version') != version.name or saved.get('files') != tree_records(version):
            raise ValueError('Preserving modified Node installation; review before updating')
        return
    # Older Z8 versions had no file receipt. Compare them to the exact bundled
    # archive before any update; version text alone cannot prove ownership.
    baseline = lock_data(Path(__file__).with_name('node.lock.json'))
    if version.name != baseline['version']:
        raise ValueError('Node installation has no managed receipt; review before updating')
    with tempfile.TemporaryDirectory(prefix='.verify-', dir=version.parent) as temporary:
        directory = Path(temporary)
        artifact = directory / 'node.tar.xz'
        download(baseline['url'], artifact, baseline['sha256'], 128 * 1024 * 1024)
        reference = extract(artifact, directory / 'unpack', 'node-' + baseline['version'] + '-linux-arm64')
        if tree_records(reference) != tree_records(version):
            raise ValueError('Preserving modified legacy Node installation; review before updating')


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
    parser = argparse.ArgumentParser(description='Install the bundled Node pin or an explicitly selected Node 24 LTS release.')
    parser.add_argument('--version', dest='selected_version')
    arguments = parser.parse_args()
    install(arguments.selected_version)
