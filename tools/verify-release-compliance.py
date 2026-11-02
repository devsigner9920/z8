#!/usr/bin/env python3
"""Verify source/notice/package integrity and exact APK/AAB linkage. Does not approve legal terms."""
import argparse
import importlib.util
from pathlib import Path
import urllib.parse
import zipfile
from release_compliance import ROOT, atomic_write, bytes_sha, checked_asset, download, issue, json_bytes, read_json, safe_relative, secret_path, sha256


def verify_source(manifest_path, root):
    source = read_json(manifest_path)
    archive = manifest_path.parent / safe_relative(source['archive'])
    problems = []
    if source.get('kind') != 'z8-release-source' or sha256(archive) != source['archiveSha256']:
        raise ValueError('Source archive identity/hash mismatch')
    records = source['files']
    if bytes_sha(json_bytes(records)) != source['sourceInputSha256']:
        raise ValueError('Source input manifest checksum mismatch')
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        expected = {x['path'] for x in records} | {'SOURCE_MANIFEST.json'}
        if len(names) != len(set(names)) or set(names) != expected:
            raise ValueError('Source archive entry set differs from manifest')
        internal = __import__('json').loads(z.read('SOURCE_MANIFEST.json'))
        if internal != {k: v for k, v in source.items() if k not in {'archive', 'archiveSha256'}}:
            raise ValueError('Source archive internal/external manifests differ')
        for item in records:
            name = safe_relative(item['path'])
            if secret_path(name) or '/.git/' in name or name.startswith('.local/'):
                raise ValueError('Disallowed source archive entry')
            payload = z.read(name)
            if bytes_sha(payload) != item['sha256'] or len(payload) != item['bytes']:
                raise ValueError('Source member changed: ' + name)
            if not name.startswith(('upstream/', 'third-party-sources/')):
                current = root / name
                if not current.is_file() or current.is_symlink() or sha256(current) != item['sha256']:
                    problems.append(issue('SOURCE_SNAPSHOT_STALE', name, 'Current build input differs from packaged source'))
    spec = importlib.util.spec_from_file_location('z8_release_source', ROOT / 'tools/package-release-source.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    packaged_own = {x['path'] for x in records if not x['path'].startswith(('upstream/', 'third-party-sources/'))}
    current_own = {name for name, path in module.own_sources(root)}
    if current_own != packaged_own:
        problems.append(issue('SOURCE_FILE_SET_CHANGED', 'application', 'Regenerate source snapshot after added/removed source files'))
    return source, archive, problems


def verify(args):
    blockers, links = [], {}
    source, archive, errors = verify_source(args.source_manifest, args.root)
    blockers += errors
    links['sourceArchiveSha256'] = source['archiveSha256']
    links['sourceInputSha256'] = source['sourceInputSha256']
    notices = read_json(args.notices)
    notice_text = args.notices.parent / 'third-party-notices.txt'
    if notices.get('kind') != 'z8-release-notices' or sha256(notice_text) != notices['noticeSha256']:
        raise ValueError('Notice body identity/hash mismatch')
    if notices['inputs'].get('sourceInputSha256') != source['sourceInputSha256']:
        blockers.append(issue('NOTICE_SOURCE_MISMATCH', 'application', 'Notices describe another source snapshot'))
    if notices['inputs'].get('sourceLockSha256') != sha256(args.root / 'tools/sources.lock.json'):
        blockers.append(issue('SOURCE_LOCK_MISMATCH', 'application', 'Notices do not match current upstream lock'))
    blockers += notices.get('unresolved', [])
    links['noticesSha256'] = sha256(args.notices)
    links['noticeTextSha256'] = sha256(notice_text)
    packages = read_json(args.package_sources)
    if source.get('packageSourcesSha256') != sha256(args.package_sources):
        blockers.append(issue('SOURCE_PACKAGE_PAYLOADS_NOT_INCLUDED', 'packages', 'Regenerate source ZIP with --package-sources so downloaded sources are actually distributed'))
    archive_records = {x['path']: x for x in source['files']}
    if notices['inputs'].get('packageSourcesSha256') != sha256(args.package_sources):
        blockers.append(issue('PACKAGE_INVENTORY_MISMATCH', 'packages', 'Notices describe a different package inventory'))
    for component in packages['components']:
        for item in component['sourceFiles']:
            path = args.package_sources.parent / safe_relative(item['path'])
            if item.get('status') != 'VERIFIED' or not path.is_file() or path.is_symlink() or sha256(path) != item['sha256']:
                blockers.append(issue('PACKAGE_SOURCE_MISSING', component['id'], item['path']))
            if archive_records.get('third-party-sources/' + item['path'], {}).get('sha256') != item['sha256']:
                blockers.append(issue('SOURCE_PAYLOAD_NOT_DISTRIBUTED', component['id'], item['path']))
    for item in packages.get('buildInputs', []):
        path = args.package_sources.parent / safe_relative(item['path'])
        if not path.is_file() or path.is_symlink() or sha256(path) != item['sha256']:
            blockers.append(issue('RUNTIME_BUILD_INPUT_MISSING', 'host', item['path']))
        if archive_records.get('third-party-sources/' + item['path'], {}).get('sha256') != item['sha256']:
            blockers.append(issue('RUNTIME_BUILD_INPUT_NOT_DISTRIBUTED', 'host', item['path']))
    # The binary inputs in the package inventory must be those selected for this build.
    for option, key in [('runtime_manifest', 'runtimeManifestSha256'), ('guest_manifest', 'guestManifestSha256')]:
        path = getattr(args, option, None)
        if path and sha256(path) != packages['inputs'].get(key):
            blockers.append(issue('BUNDLED_IMAGE_MISMATCH', key, 'Selected image manifest differs from source inventory'))
    if args.gradle_artifacts:
        if sha256(args.gradle_artifacts) != notices['inputs'].get('gradleArtifactsSha256'):
            blockers.append(issue('GRADLE_INVENTORY_MISMATCH', 'application', 'Resolved dependencies differ from notices'))
    else:
        blockers.append(issue('GRADLE_EVIDENCE_MISSING', 'application', 'Supply resolved releaseRuntimeClasspath evidence for this build'))
    if args.artifact:
        links['artifactSha256'] = sha256(args.artifact)
        with zipfile.ZipFile(args.artifact) as z:
            prefix = 'base/' if args.artifact.suffix == '.aab' else ''
            for basename, local in [('third-party-notices.txt', notice_text), ('release-notices.json', args.notices)]:
                name = prefix + 'assets/z8-licenses/' + basename
                if name not in z.namelist() or bytes_sha(z.read(name)) != sha256(local):
                    blockers.append(issue('PACKAGED_NOTICE_MISMATCH', basename, 'Final artifact lacks the exact generated notice asset'))
            guest_name = prefix + 'assets/z8/guest/rootfs.zip'
            expected_guest = packages['inputs'].get('guestArchiveSha256')
            if expected_guest and (guest_name not in z.namelist() or bytes_sha(z.read(guest_name)) != expected_guest):
                blockers.append(issue('PACKAGED_GUEST_MISMATCH', 'guest', 'Actual guest image differs from inventory'))
            expected_runtime = packages['inputs'].get('runtimeArchiveSha256')
            if expected_runtime:
                if not args.runtime_manifest:
                    blockers.append(issue('RUNTIME_MANIFEST_REQUIRED', 'host', 'Supply runtime manifest to check the actual native embedded bootstrap'))
                else:
                    runtime, _ = checked_asset(args.runtime_manifest)
                    native_name = prefix + 'lib/arm64-v8a/libtermux-bootstrap.so'
                    # termux-bootstrap-zip.S uses .incbin: the full ZIP is present
                    # verbatim in this ELF, not a separately named APK asset.
                    if (sha256(runtime) != expected_runtime or native_name not in z.namelist()
                            or runtime.read_bytes() not in z.read(native_name)):
                        blockers.append(issue('PACKAGED_RUNTIME_MISMATCH', 'host', 'Actual native embedded bootstrap differs from inventory'))
    else:
        blockers.append(issue('FINAL_ARTIFACT_MISSING', 'release', 'Supply the final APK/AAB to verify packaged notices'))
    parsed = urllib.parse.urlsplit(args.source_url or '')
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.hostname.endswith('.invalid'):
        blockers.append(issue('SOURCE_URL_REQUIRED', 'release', 'Provide the real HTTPS source distribution URL'))
    elif args.check_source_url:
        target = args.source_manifest.parent / ('verified-public-' + source['archiveSha256'][:16] + '.zip')
        # Always revalidate current availability, not a previously fetched file.
        if target.exists():
            target.unlink()
        try:
            download(args.source_url, target, source['archiveSha256'], limit=2 * 1024 * 1024 * 1024)
            links['sourceUrlVerified'] = args.source_url
        except Exception as exc:
            blockers.append(issue('SOURCE_URL_UNVERIFIED', 'release', type(exc).__name__ + ': ' + str(exc)[:300]))
    else:
        blockers.append(issue('SOURCE_URL_UNVERIFIED', 'release', 'Use --check-source-url after publishing the exact source ZIP'))
    if notices.get('reviewEvidenceSha256'):
        if not args.review or sha256(args.review) != notices['reviewEvidenceSha256']:
            blockers.append(issue('REVIEW_EVIDENCE_MISMATCH', 'release', 'Provide the exact maintainer review used by notice generation'))
    else:
        blockers.append(issue('RELEASE_REVIEW_MISSING', 'release', 'No exact-input maintainer source/license review supplied'))
    # Deduplicate without dropping different causes for the same component.
    blockers = list({__import__('json').dumps(x, sort_keys=True): x for x in blockers}.values())
    return {'schemaVersion': 1, 'kind': 'z8-release-compliance-verification',
            'status': 'BLOCKED' if blockers else 'VERIFIED', 'inputs': links, 'blockers': blockers,
            'scope': 'Source/notice integrity and availability only; not Play approval or legal/provider-contract clearance.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    for name in ('source-manifest', 'package-sources', 'notices'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('runtime-manifest', 'guest-manifest', 'gradle-artifacts', 'artifact', 'review', 'output'):
        p.add_argument('--' + name, type=Path)
    p.add_argument('--source-url', default='')
    p.add_argument('--check-source-url', action='store_true')
    p.add_argument('--allow-incomplete', action='store_true')
    args = p.parse_args()
    try:
        report = verify(args)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        report = {'schemaVersion': 1, 'kind': 'z8-release-compliance-verification', 'status': 'BLOCKED',
                  'blockers': [issue('INVALID_EVIDENCE', 'release', str(exc))]}
    if args.output:
        atomic_write(args.output, json_bytes(report))
    print(json_bytes(report).decode(), end='')
    return 0 if args.allow_incomplete or report['status'] == 'VERIFIED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
