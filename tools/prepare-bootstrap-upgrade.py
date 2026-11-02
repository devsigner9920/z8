#!/usr/bin/env python3
"""Generate the exact prior-runtime allowlist; never inspect installed user data."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import zipfile


def generate(manifest):
    data = json.loads(manifest.read_text())
    if data['applicationId'] != 'dev.devsigner.z8' or data['prefix'] != '/data/data/dev.devsigner.z8/files/usr':
        raise ValueError('Unexpected runtime identity')
    archive = manifest.parent / data['archive']
    if archive.parent.resolve() != manifest.parent.resolve() or hashlib.sha256(archive.read_bytes()).hexdigest() != data['sha256']:
        raise ValueError('Prior runtime archive hash/path mismatch')
    entries = {}
    def add(name, kind, size='', value=''):
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or any(c in name+value for c in '\t\n\r'):
            raise ValueError('Unsafe runtime path')
        for parent in path.parents:
            if str(parent) != '.': entries.setdefault(str(parent), ('D', '', ''))
        if name in entries and entries[name] != (kind, str(size), value): raise ValueError('Duplicate runtime entry')
        entries[name] = kind, str(size), value
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if info.filename == 'SYMLINKS.txt': continue
            name = info.filename.rstrip('/')
            if info.is_dir(): add(name, 'D')
            else: add(name, 'F', info.file_size, hashlib.sha256(bundle.read(info)).hexdigest())
        for line in bundle.read('SYMLINKS.txt').decode().splitlines():
            target, name = line.split('←')
            if target.startswith('/'):
                prefix = data['prefix'] + '/'
                if not target.startswith(prefix): raise ValueError('External runtime symlink')
                target = posixpath.relpath(target[len(prefix):], posixpath.dirname(name) or '.')
            add(name, 'L', '', target)
    return 'z8-bootstrap-upgrade-v1\t' + data['sha256'] + '\n' + ''.join(
        '\t'.join((*entries[name], name)) + '\n' for name in sorted(entries))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    text = generate(args.runtime_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    print(f'Wrote {len(text.splitlines()) - 1} verified prior-runtime entries')
