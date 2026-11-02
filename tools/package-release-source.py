#!/usr/bin/env python3
"""Create a deterministic, secret-excluding source snapshot; no repository upload."""
import argparse
import io
import os
from pathlib import Path
import re
import posixpath
import subprocess
import tarfile
import tempfile
import zipfile
from release_compliance import ROOT, GENERATED_NOTICES, atomic_write, bytes_sha, json_bytes, read_json, safe_relative, secret_path, sha256, zip_entry

DIRECTORIES = ('tools', 'runtime', 'overlay', 'tests', 'docs', 'LICENSES', '.github')
ROOT_FILES = ('README.md', 'README.ko.md', 'BUILDING.md', 'BUILDING.ko.md', 'THIRD_PARTY_NOTICES.md', '.gitignore',
              'LICENSE', 'CONTRIBUTING.md', 'SECURITY.md')
RELEASE_FILES = ('config.json', 'decisions.example.json', 'qa.example.json')


def own_sources(root):
    root = Path(root)
    # Exact public build configuration and empty examples are source inputs.
    # Actual signed decisions/QA records can contain names and private evidence.
    for name in ROOT_FILES + tuple('release/' + name for name in RELEASE_FILES):
        path = root / name
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root and p.is_relative_to(root)):
            raise ValueError('Local source symlink requires explicit review: ' + name)
        if path.is_file():
            yield name, path
    for name in DIRECTORIES:
        if (root / name).is_symlink():
            raise ValueError('Local source symlink requires explicit review: ' + name)
        for path in sorted((root / name).rglob('*')):
            relative = path.relative_to(root).as_posix()
            if any(x in {'.git', '__pycache__', '.gradle', 'build', 'node_modules'} for x in path.parts):
                continue
            if path.name in GENERATED_NOTICES or path.name == '.DS_Store' or path.suffix == '.pyc':
                continue
            if path.is_symlink():
                raise ValueError('Local source symlink requires explicit review: ' + relative)
            if path.is_file() and not secret_path(relative):
                yield relative, path


def package(root, output, package_sources=None):
    root, output = Path(root), Path(output)
    lock = read_json(root / 'tools/sources.lock.json')
    records, omitted, payload, streamed = [], [], {}, {}
    for name, path in own_sources(root):
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('Unexpected large source file: ' + name)
        data = path.read_bytes()
        # Private keys are never acceptable, including in an innocuously named file.
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----', data):
            raise ValueError('Private key marker in source; output was not published')
        payload[name] = (data, 0o755 if os.access(path, os.X_OK) else 0o644, 0o100000)
    for key, folder in [('termuxApp', 'termux-app'), ('termuxPackages', 'termux-packages')]:
        source = root / 'upstream' / folder
        git = ['git', '-C', str(source)]
        if subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip() != lock[key]['commit']:
            raise ValueError('Upstream revision differs from source lock: ' + folder)
        if subprocess.check_output(git + ['status', '--porcelain', '--untracked-files=all']):
            raise ValueError('Upstream is not pristine: ' + folder)
        archive = subprocess.check_output(git + ['archive', '--format=tar', lock[key]['commit']])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar:
                name = 'upstream/' + folder + '/' + safe_relative(member.name)
                if member.isdir():
                    continue
                if secret_path(name):
                    omitted.append({'path': name, 'reason': 'credential/key filename excluded, including upstream public test keys'})
                    continue
                if member.issym():
                    # Keep symlink metadata in the source manifest, never dereference on the host.
                    target = member.linkname
                    destination = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
                    if target.startswith('/') or not destination.startswith('upstream/' + folder + '/'):
                        raise ValueError('Upstream symlink requires review: ' + name)
                    payload[name] = (target.encode(), 0o777, 0o120000)
                    continue
                if not member.isfile():
                    raise ValueError('Unsupported source archive entry')
                payload[name] = (tar.extractfile(member).read(), member.mode & 0o777, 0o100000)
    package_inventory_sha = None
    if package_sources:
        package_sources = Path(package_sources)
        inventory = read_json(package_sources)
        package_inventory_sha = sha256(package_sources)
        streamed['third-party-sources/package-sources.json'] = package_sources
        for component in inventory['components']:
            for record in component['sourceFiles']:
                if record.get('status') != 'VERIFIED':
                    continue
                relative = safe_relative(record['path'])
                path = package_sources.parent / relative
                if path.is_symlink() or sha256(path) != record['sha256']:
                    raise ValueError('Package source payload changed before archiving')
                streamed['third-party-sources/' + relative] = path
        for record in inventory['installedNotices'] + inventory.get('sourceNotices', []) + inventory.get('buildInputs', []):
            relative = safe_relative(record['path'])
            path = package_sources.parent / relative
            if path.is_symlink() or sha256(path) != record['sha256']:
                raise ValueError('Package copyright notice changed before archiving')
            streamed['third-party-sources/' + relative] = path
    for name, (data, mode, kind) in sorted(payload.items()):
        records.append({'path': name, 'sha256': bytes_sha(data), 'bytes': len(data), 'mode': mode,
                        'type': 'symlink' if kind == 0o120000 else 'file'})
    for name, path in sorted(streamed.items()):
        records.append({'path': name, 'sha256': sha256(path), 'bytes': path.stat().st_size, 'mode': 0o644, 'type': 'file'})
    records.sort(key=lambda x: x['path'])
    manifest = {'schemaVersion': 1, 'kind': 'z8-release-source', 'sourceLock': lock,
                'sourceInputSha256': bytes_sha(json_bytes(records)), 'files': records, 'omitted': omitted,
                'packageSourcesSha256': package_inventory_sha,
                'claims': {'sourceInputsPreserved': True, 'binaryReproducibility': 'NOT_TESTED',
                           'completeCorrespondingSource': False},
                'limitations': ['Package source payloads and runtime dependency licenses are verified separately.',
                    'No local Git configuration, private keys, caches or credentials are included.',
                    'To run the current exact-HEAD preparers, restore the pinned upstream checkouts with Git; the source exports contain no .git metadata.',
                    'Private signing material is intentionally omitted; use your own signing key.']}
    output.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.source-', suffix='.zip', dir=output)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name, (data, mode, kind) in sorted(payload.items()):
                zip_entry(z, name, data, mode, kind)
            for name, path in sorted(streamed.items()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_STORED
                with path.open('rb') as src, z.open(info, 'w', force_zip64=True) as dst:
                    while block := src.read(1024 * 1024):
                        dst.write(block)
            zip_entry(z, 'SOURCE_MANIFEST.json', json_bytes(manifest))
        digest = sha256(temporary)
        archive_path = output / ('z8-source-' + digest[:16] + '.zip')
        os.replace(temporary, archive_path)
        record = dict(manifest, archive=archive_path.name, archiveSha256=digest)
        atomic_write(output / 'source-manifest.json', json_bytes(record))
        return record
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--package-sources', type=Path, help='Include verified source payloads and installed copyright files')
    args = p.parse_args()
    result = package(args.root, args.output, args.package_sources)
    print(json_bytes({k: result[k] for k in ('archive', 'archiveSha256', 'sourceInputSha256')}).decode(), end='')


if __name__ == '__main__':
    main()
