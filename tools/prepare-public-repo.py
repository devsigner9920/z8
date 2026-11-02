#!/usr/bin/env python3
"""Export reviewable repository sources locally. Never create, commit or push a repository."""
import argparse
import importlib.util
import os
from pathlib import Path
import re
import tempfile
import zipfile

from release_compliance import ROOT, bytes_sha, json_bytes, zip_entry

SPEC = importlib.util.spec_from_file_location('release_source', Path(__file__).with_name('package-release-source.py'))
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)

# These are content signatures, not a claim that an automated scan finds every secret.
SECRET_PATTERNS = (
    ('private-key', re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----')),
    ('github-token', re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{36,}\b')),
    ('github-fine-grained-token', re.compile(rb'\bgithub_pat_[A-Za-z0-9_]{50,}\b')),
    ('provider-key', re.compile(rb'\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{32,}\b')),
    ('aws-access-id', re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')),
)
REQUIRED = ('LICENSE', 'README.md', 'BUILDING.md', 'THIRD_PARTY_NOTICES.md',
            'CONTRIBUTING.md', 'SECURITY.md', 'release/config.json', 'tools/sources.lock.json')


def prepare(root, output):
    root, output = Path(root).resolve(), Path(output)
    # Resolve system aliases such as macOS /var, but reject a redirected output itself.
    if output.is_symlink():
        raise ValueError('Symlink output directory is not allowed')
    output = output.resolve()
    if output == root or any(output.is_relative_to(root / name) for name in source.DIRECTORIES + ('release',)):
        raise ValueError('Output must be outside the public source directories')

    files, records, findings = {}, [], []
    for name, path in source.own_sources(root):
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('Unexpected large repository file: ' + name)
        data = path.read_bytes()
        for kind, pattern in SECRET_PATTERNS:
            if pattern.search(data):
                findings.append(kind + ': ' + name)
        mode = 0o755 if os.access(path, os.X_OK) else 0o644
        files[name] = (data, mode)
        records.append({'path': name, 'sha256': bytes_sha(data), 'bytes': len(data), 'mode': mode})
    missing = sorted(set(REQUIRED) - files.keys())
    if missing:
        raise ValueError('Missing public source files: ' + ', '.join(missing))
    if findings:
        # Report filenames and categories only, never matched credentials.
        raise ValueError('Potential credentials require review; nothing exported:\n' + '\n'.join(findings))
    records.sort(key=lambda item: item['path'])
    digest = bytes_sha(json_bytes(records))
    basename = 'z8-public-' + digest[:16]
    manifest = {
        'schemaVersion': 1, 'kind': 'z8-public-repository-preparation',
        'sourceInputSha256': digest, 'files': records,
        'fileCount': len(records), 'totalBytes': sum(item['bytes'] for item in records),
        'scan': {'knownCredentialPatterns': 'PASS', 'manualReviewStillRequired': True},
        'published': False, 'includesBundledPackageSources': False,
        'limitations': [
            'This is a repository export, not the complete corresponding source for an APK or AAB.',
            'Use package-release-source.py with verified package sources for a binary release.',
            'No Git history, signing material, internal reports, build outputs or generated release notices are included.',
            'Pattern scanning is not a guarantee that every sensitive value has been identified.'
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    destination = output / basename
    archive = output / (basename + '.zip')
    manifest_path = output / (basename + '.json')
    if any(path.exists() or path.is_symlink() for path in (destination, archive, manifest_path)):
        raise ValueError('Export already exists; use a new output directory to preserve prior evidence')
    with tempfile.TemporaryDirectory(prefix='.z8-public-', dir=output) as directory:
        staging = Path(directory)
        tree = staging / 'repository'
        tree.mkdir()
        with zipfile.ZipFile(staging / 'source.zip', 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, (data, mode) in sorted(files.items()):
                target = tree / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                target.chmod(mode)
                zip_entry(bundle, name, data, mode)
        (staging / 'manifest.json').write_bytes(json_bytes(manifest))
        tree.rename(destination)
        (staging / 'source.zip').rename(archive)
        (staging / 'manifest.json').rename(manifest_path)
    return dict(manifest, directory=str(destination), archive=str(archive), manifest=str(manifest_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/public-repo')
    args = parser.parse_args()
    try:
        result = prepare(args.root, args.output)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')
    print(json_bytes({key: result[key] for key in ('directory', 'archive', 'manifest', 'fileCount', 'totalBytes')}).decode(), end='')


if __name__ == '__main__':
    main()
