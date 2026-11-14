#!/usr/bin/env python3
"""Collect exact runtime Maven source artifacts without claiming source closure."""
import argparse
import base64
import copy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from release_compliance import ROOT, atomic_write, issue, json_bytes, read_json, sha256
import embedded_maven_source
import maven_upstream_supplements as supplements

GOOGLE = 'https://dl.google.com/dl/android/maven2/'
CENTRAL = 'https://repo.maven.apache.org/maven2/'
ALLOWED_HOSTS = {'dl.google.com', 'repo.maven.apache.org'}
MAX_DOWNLOAD = 100 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
EMPTY_COMPATIBILITY = {('com.google.guava', 'listenablefuture', '9999.0-empty-to-avoid-conflict-with-guava')}


def coordinate_parts(item):
    values = tuple(item[key] for key in ('group', 'name', 'version'))
    if any(not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.+\-]+', value)
           or value in ('.', '..') for value in values):
        raise ValueError('Unsafe Maven coordinate')
    if any(not part or part in ('.', '..') for part in values[0].split('.')):
        raise ValueError('Unsafe Maven group')
    return values


def repository_url(parts, suffix):
    group, name, version = parts
    base = GOOGLE if group.startswith('androidx.') or group == 'com.google.android.material' else CENTRAL
    path = '/'.join([*group.split('.'), name, version, name + '-' + version + suffix])
    return base + '/'.join(urllib.parse.quote(part, safe='._-+') for part in path.split('/'))


def allowed_url(url):
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == 'https' and parsed.hostname in ALLOWED_HOSTS
            and not parsed.username and not parsed.password and parsed.port in (None, 443))


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise ValueError('Redirect outside the allowed official Maven repositories')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def download(url, output, fetch, previous):
    if not allowed_url(url):
        raise ValueError('Only official Google Maven and Maven Central HTTPS URLs are allowed')
    for record in previous:
        if record.get('url') != url:
            continue
        relative = PurePosixPath(record['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe cached source path')
        path = output / relative
        if path.is_file() and not path.is_symlink() and sha256(path) == record['sha256']:
            return dict(record)
    if not fetch:
        raise ValueError('Source evidence is not cached; rerun with --fetch')
    opener = urllib.request.build_opener(OfficialRedirects())
    request = urllib.request.Request(url, headers={'User-Agent': 'Z8-source-evidence/1'})
    with opener.open(request, timeout=45) as response:
        if not allowed_url(response.geturl()):
            raise ValueError('Response outside the allowed official Maven repositories')
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError('Maven download exceeds the size limit')
    digest = hashlib.sha256(data).hexdigest()
    name = urllib.parse.unquote(PurePosixPath(urllib.parse.urlsplit(url).path).name)
    relative = 'downloads/' + digest + '/' + name
    atomic_write(output / relative, data)
    return {'path': relative, 'url': url, 'sha256': digest, 'bytes': len(data), 'status': 'VERIFIED'}


def archive_inventory(path, include_contents=False):
    """Inspect, never extract or execute, an artifact and its AAR classes.jar."""
    records, counts = [], {'classCount': 0, 'nativeCount': 0, 'resourceCount': 0, 'moduleInfoCount': 0}
    total = 0
    def visit(data, prefix='', nested=False):
        nonlocal total
        with zipfile.ZipFile(data) as archive:
            if len(archive.infolist()) > 100000:
                raise ValueError('Maven archive has too many entries')
            seen = set()
            for entry in archive.infolist():
                name = entry.filename
                pure = PurePosixPath(name)
                if pure.is_absolute() or '..' in pure.parts or '\\' in name or name in seen:
                    raise ValueError('Unsafe or duplicate Maven archive member')
                seen.add(name)
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Symlink in Maven archive')
                if entry.is_dir():
                    continue
                total += entry.file_size
                if entry.file_size > 64 * 1024 * 1024 or total > MAX_ARCHIVE_BYTES:
                    raise ValueError('Maven archive exceeds inspection limit')
                payload = archive.read(entry)
                record = {'path': prefix + name, 'bytes': len(payload),
                          'sha256': hashlib.sha256(payload).hexdigest()}
                records.append(record)
                if name == 'classes.jar' and not nested:
                    visit(io.BytesIO(payload), prefix + 'classes.jar/', True)
                elif name.endswith('/module-info.class') or name == 'module-info.class':
                    counts['moduleInfoCount'] += 1
                elif name.endswith('.class'):
                    counts['classCount'] += 1
                elif name.endswith(('.so', '.dll', '.dylib', '.a', '.dex')):
                    counts['nativeCount'] += 1
                elif not (name.upper() == 'META-INF/MANIFEST.MF'
                          or (name.startswith('META-INF/maven/') and name.endswith(('/pom.xml', '/pom.properties')))
                          or re.search(r'(^|/)(LICENSE|NOTICE|COPYING)([._-]|$)', name, re.I)):
                    counts['resourceCount'] += 1
    visit(path)
    return dict(counts, members=records if include_contents else None)


def no_code_exception(parts, inventory):
    return parts in EMPTY_COMPATIBILITY and all(inventory[key] == 0 for key in
        ('classCount', 'nativeCount', 'resourceCount', 'moduleInfoCount'))


def pom_data(path):
    tree = ET.fromstring(path.read_bytes())
    for item in tree.iter():
        item.tag = item.tag.rsplit('}', 1)[-1]
    parent = tree.find('parent')
    return {'licenses': [{'name': x.findtext('name', '').strip(), 'url': x.findtext('url', '').strip()}
                         for x in tree.findall('./licenses/license')],
            'scm': {key: tree.findtext('scm/' + key, '').strip() for key in ('url', 'connection', 'developerConnection', 'tag')},
            'projectUrl': tree.findtext('url', '').strip(),
            'parent': ({'group': parent.findtext('groupId', ''), 'name': parent.findtext('artifactId', ''),
                        'version': parent.findtext('version', '')} if parent is not None else None)}


def mapped_file(mapping, key, mapping_root, output, role):
    record = mapping[key]
    relative = PurePosixPath(record['path'])
    if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative):
        raise ValueError('Unsafe mapped evidence path')
    source = mapping_root / relative
    if (not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(mapping_root.resolve())
            or source.stat().st_size > MAX_DOWNLOAD or sha256(source) != record['sha256']):
        raise ValueError('Mapped evidence hash mismatch')
    destination = 'downloads/' + record['sha256'] + '/' + source.name
    atomic_write(output / destination, source.read_bytes())
    return {'path': destination, 'sha256': record['sha256'], 'bytes': source.stat().st_size,
            'status': 'VERIFIED', 'role': role, **({'url': record['url']} if record.get('url') else {})}


def upstream_file(spec, output, fetch, caches):
    """Retain exact original inputs, reusing cache bytes before any network request."""
    supplements.validate_spec(spec)
    extension = {'zip': '.zip', 'tar.gz': '.tar.gz', 'gitiles-base64': '.base64', 'gitiles-file': '.txt',
                 'gitiles-tree': '.json'}[spec['format']]
    relative = 'downloads/' + spec['sha256'] + '/' + spec['id'] + extension
    target = output / relative
    def valid(path):
        return (path.is_file() and not path.is_symlink() and path.stat().st_size == spec['bytes']
                and sha256(path) == spec['sha256'])
    data = target.read_bytes() if valid(target) else None
    if data is None:
        for cache in caches:
            for path in cache.rglob('*'):
                if valid(path):
                    data = path.read_bytes()
                    break
            if data is not None:
                break
    if data is None:
        if not fetch:
            raise ValueError('Pinned upstream input is not cached; supply --upstream-cache or --fetch')
        class PinnedRedirects(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, msg, headers, newurl):
                if newurl != spec['url']:
                    raise ValueError('Redirect away from immutable upstream input')
                return super().redirect_request(request, fp, code, msg, headers, newurl)
        request = urllib.request.Request(spec['url'], headers={'User-Agent': 'Z8-source-evidence/1'})
        with urllib.request.build_opener(PinnedRedirects()).open(request, timeout=45) as response:
            if response.geturl() != spec['url']:
                raise ValueError('Response outside the pinned upstream URL')
            data = response.read(MAX_DOWNLOAD * 2 + 1)
        if len(data) > MAX_DOWNLOAD * 2:
            raise ValueError('Upstream response exceeds download limit')
        if spec['format'] == 'gitiles-file':
            data = base64.b64decode(b''.join(data.split()), validate=True)
    if len(data) != spec['bytes'] or hashlib.sha256(data).hexdigest() != spec['sha256']:
        raise ValueError('Upstream download differs from the pinned original input')
    atomic_write(target, data)
    return {'path': relative, 'url': spec['url'], 'sha256': spec['sha256'], 'bytes': len(data),
            'status': 'VERIFIED', 'role': supplements.ROLE}


def collect(args):
    evidence = read_json(args.gradle_artifacts)
    if evidence.get('kind') != 'z8-gradle-runtime-artifacts' or evidence.get('configuration') != 'releaseRuntimeClasspath':
        raise ValueError('Expected resolved releaseRuntimeClasspath evidence')
    output = args.output.resolve()
    previous_file = output / 'maven-sources.json'
    previous = read_json(previous_file).get('files', []) if previous_file.is_file() else []
    groups = {}
    for item in evidence['components']:
        parts = coordinate_parts(item)
        path = Path(item['file'])
        if not path.is_absolute():
            path = args.root / path
        if not path.is_file() or path.is_symlink() or sha256(path) != item['sha256']:
            raise ValueError('Resolved runtime artifact changed: ' + ':'.join(parts))
        inventory = archive_inventory(path)
        inventory.pop('members')
        groups.setdefault(parts, []).append(dict(inventory, fileName=path.name,
            type=item.get('type', path.suffix.lstrip('.')), sha256=item['sha256'], bytes=path.stat().st_size))
    mappings = {}
    supplement_path = getattr(args, 'upstream_lock', None)
    supplement_specs, supplement_components = {}, {}
    if supplement_path:
        supplement_specs, supplement_components = supplements.validate_lock(read_json(supplement_path))
    mapping_path = getattr(args, 'source_mappings', None)
    if mapping_path:
        supplied = read_json(mapping_path)
        if supplied.get('schemaVersion') != 1 or supplied.get('kind') != 'z8-maven-source-mappings':
            raise ValueError('Expected explicit Maven source mappings')
        for mapping in supplied['components']:
            parts = coordinate_parts(mapping)
            if parts not in groups or parts in mappings:
                raise ValueError('Unknown or duplicate mapped coordinate')
            if sorted(set(mapping['binaryArtifactSha256'])) != sorted({x['sha256'] for x in groups[parts]}):
                raise ValueError('Mapped binary hashes do not match the actual runtime inventory')
            if mapping.get('type') == embedded_maven_source.MAPPING_TYPE:
                embedded_maven_source.validate_mapping(mapping, parts, mapping['binaryArtifactSha256'])
            else:
                commit = mapping.get('commit', '')
                url = mapping['sourceArchive']['url']
                repository = mapping.get('repository', '')
                if (mapping.get('type') not in (None, 'upstream-git-source')
                        or not re.fullmatch(r'[0-9a-f]{40}', commit) or not mapping.get('tag') or not mapping.get('versionEvidence')
                        or not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)
                        or url != 'https://codeload.github.com/' + repository.removeprefix('https://github.com/') + '/zip/' + commit):
                    raise ValueError('Mapping must identify an immutable upstream commit, tag and version evidence')
            mappings[parts] = mapping
    all_files, components, unresolved, portable_mappings = {}, [], [], []
    def retain(record, role):
        record = dict(record, role=role)
        all_files[record['path']] = record
        if record.get('url') and not any(item.get('url') == record['url'] for item in previous):
            previous.append(record)
        return record
    if mapping_path:
        mapping_bytes = mapping_path.read_bytes()
        atomic_write(output / 'provenance/source-mappings.json', mapping_bytes)
        retain({'path': 'provenance/source-mappings.json', 'sha256': hashlib.sha256(mapping_bytes).hexdigest(),
                'bytes': len(mapping_bytes), 'status': 'VERIFIED'}, 'source-mapping-evidence')
    supplement_record = None
    if supplement_path:
        lock_bytes = Path(supplement_path).read_bytes()
        atomic_write(output / 'provenance/upstream-supplements.json', lock_bytes)
        supplement_record = retain({'path': 'provenance/upstream-supplements.json',
            'sha256': hashlib.sha256(lock_bytes).hexdigest(), 'bytes': len(lock_bytes),
            'status': 'VERIFIED'}, 'maven-upstream-lock')
    upstream_records = {}
    for parts, binaries in sorted(groups.items()):
        coordinate = ':'.join(parts)
        component = {'id': 'maven:' + coordinate, 'group': parts[0], 'name': parts[1], 'version': parts[2],
            'binaryArtifacts': binaries, 'sourceFiles': [], 'metadataFiles': [], 'scm': {}, 'licenses': [],
            'reviewRequired': [], 'unresolved': []}
        parent_parts, seen = parts, set()
        mapping = mappings.get(parts)
        try:
            for _ in range(8):
                if parent_parts in seen:
                    raise ValueError('Cyclic POM parent chain')
                seen.add(parent_parts)
                if parent_parts == parts and mapping and mapping.get('metadataPom'):
                    record = retain(mapped_file(mapping, 'metadataPom', mapping_path.parent, output, 'pom'), 'pom')
                else:
                    record = retain(download(repository_url(parent_parts, '.pom'), output, args.fetch, previous), 'pom')
                component['metadataFiles'].append(record)
                metadata = pom_data(output / record['path'])
                if not component['licenses']:
                    component['licenses'] = metadata['licenses']
                for key, value in metadata['scm'].items():
                    if value and not component['scm'].get(key):
                        component['scm'][key] = value
                if parent_parts == parts:
                    component['projectUrl'] = metadata['projectUrl']
                if not metadata['parent']:
                    break
                parent_parts = coordinate_parts(metadata['parent'])
            else:
                raise ValueError('POM parent chain exceeds limit')
        except (ValueError, OSError, ET.ParseError) as error:
            component['unresolved'].append(issue('MAVEN_POM_UNAVAILABLE', coordinate, str(error)))
        if all(no_code_exception(parts, binary) for binary in binaries):
            component['sourceDisposition'] = 'NO_CODE_ARTIFACT_VERIFIED'
            component['reviewRequired'].append('Explicit empty listenablefuture compatibility artifact; no classes, native code, resources or module-info found. Retain its metadata and license declaration.')
        else:
            try:
                embedded = mapping and mapping.get('type') == embedded_maven_source.MAPPING_TYPE
                source_role = ('embedded-source-binary' if embedded else 'upstream-source-archive') if mapping else 'published-source-jar'
                record = (mapped_file(mapping, 'sourceArchive', mapping_path.parent, output, 'upstream-source-archive')
                          if mapping else download(repository_url(parts, '-sources.jar'), output, args.fetch, previous))
                inventory = archive_inventory(output / record['path'], True)
                source_count = sum(x['path'].endswith(('.java', '.kt', '.kts', '.c', '.h', '.cpp', '.scala'))
                                   for x in inventory['members'])
                if not source_count:
                    raise ValueError('Published sources JAR contains no recognized source files; no automatic exemption')
                if embedded:
                    upstream = mapped_file(mapping, 'upstreamArchive', mapping_path.parent, output, 'upstream-svn-dump')
                    snapshot, evidence = embedded_maven_source.evidence(
                        (output / record['path']).read_bytes(), (output / upstream['path']).read_bytes())
                    upstream = retain(upstream, 'upstream-svn-dump')
                    relative = 'derived/' + hashlib.sha256(snapshot).hexdigest() + '/jsr-305-r49.zip'
                    atomic_write(output / relative, snapshot)
                    snapshot_record = retain({'path': relative, 'sha256': hashlib.sha256(snapshot).hexdigest(),
                        'bytes': len(snapshot), 'status': 'VERIFIED'}, 'upstream-svn-snapshot')
                    evidence_bytes = json_bytes(evidence)
                    relative = 'inventories/' + hashlib.sha256(evidence_bytes).hexdigest() + '-embedded.json'
                    atomic_write(output / relative, evidence_bytes)
                    component['embeddedSourceEvidence'] = retain({'path': relative,
                        'sha256': hashlib.sha256(evidence_bytes).hexdigest(),
                        'bytes': len(evidence_bytes), 'status': 'VERIFIED'}, 'embedded-source-evidence')
                    component['buildEvidenceFiles'] = [upstream, snapshot_record]
                record = retain(record, source_role)
                component['sourceFiles'].append(record)
                content = json_bytes({'schemaVersion': 1, 'kind': 'z8-source-content-inventory',
                    'coordinate': coordinate, 'sourceArtifactSha256': record['sha256'], 'members': inventory['members']})
                relative = 'inventories/' + hashlib.sha256(coordinate.encode()).hexdigest() + '.json'
                atomic_write(output / relative, content)
                index = retain({'path': relative, 'sha256': hashlib.sha256(content).hexdigest(),
                    'bytes': len(content), 'status': 'VERIFIED'}, 'source-content-index')
                component['contentInventory'] = index
                component['sourceFileCount'] = source_count
                component['sourceDisposition'] = (embedded_maven_source.DISPOSITION if embedded else
                    'PINNED_UPSTREAM_SOURCE_ARCHIVE' if mapping else 'PUBLISHED_SOURCE_JAR')
                if embedded:
                    component['reviewRequired'].append('Exact embedded Java sources match preserved SVN revision 49. Original build and license files are retained; this is not a binary-identical rebuild or source-closure approval.')
                    component['reviewRequired'].append('POM Apache-2.0 metadata differs from the preserved BSD-3-Clause license and three CC-BY-2.5 source headers; notices must preserve the source evidence.')
                elif mapping:
                    component['upstreamMapping'] = {key: mapping[key] for key in ('repository', 'tag', 'commit', 'versionEvidence')}
                    component['reviewRequired'].append('Exact upstream tag/commit and binary hashes are recorded. Binary-identical rebuild and complete source closure have not been established.')
                else:
                    component['reviewRequired'].append('Published sources.jar is evidence, not a complete corresponding-source determination. Confirm version match, generated inputs and upstream build scripts.')
                if not embedded and any(binary['type'] == 'aar' or binary['resourceCount'] for binary in binaries):
                    component['reviewRequired'].append('Review Android resources, manifests and other non-class inputs: published sources.jar may omit inputs required to rebuild this artifact.')
            except (ValueError, OSError, zipfile.BadZipFile) as error:
                component['sourceDisposition'] = 'MISSING'
                component['unresolved'].append(issue('MAVEN_SOURCE_UNAVAILABLE', coordinate, str(error)))
        if not component['licenses']:
            component['unresolved'].append(issue('MAVEN_LICENSE_METADATA_MISSING', coordinate, 'No POM license declaration was found'))
        supplement = supplement_components.get(parts)
        if supplement:
            try:
                if (component['sourceDisposition'] != 'PUBLISHED_SOURCE_JAR'
                        or sorted(set(supplement['binaryArtifactSha256'])) != sorted({x['sha256'] for x in binaries})):
                    raise ValueError('Upstream supplement must match exact published-source runtime artifacts')
                used = {x['archiveId'] for x in supplement['sourceMatches'] + supplement['requiredInputs']}
                used.update(supplement.get('commonSupportArchiveIds', []))
                used.update(x[key] for x in supplement.get('rootBlobBindings', []) for key in ('archiveId', 'treeArchiveId'))
                for key in sorted(used):
                    if key not in upstream_records:
                        upstream_records[key] = retain(upstream_file(supplement_specs[key], output, args.fetch,
                            getattr(args, 'upstream_cache', []) or []), supplements.ROLE)
                proof = supplements.evidence(supplement, supplement_specs,
                    (output / component['sourceFiles'][0]['path']).read_bytes(),
                    {key: (output / upstream_records[key]['path']).read_bytes() for key in used})
                proof_bytes = json_bytes(proof)
                relative = 'inventories/' + hashlib.sha256(proof_bytes).hexdigest() + '-upstream.json'
                atomic_write(output / relative, proof_bytes)
                proof_record = retain({'path': relative, 'sha256': hashlib.sha256(proof_bytes).hexdigest(),
                    'bytes': len(proof_bytes), 'status': 'VERIFIED'}, supplements.EVIDENCE_ROLE)
                component['upstreamSnapshot'] = {'lockSha256': supplement_record['sha256'],
                    'inputs': [{'archiveId': key, **upstream_records[key]} for key in sorted(used)],
                    'evidence': proof_record, 'sourceClosureReviewed': False}
                component['reviewRequired'].append('Original upstream build, resource and license inputs are retained with recomputed published-source byte correspondence. Complete build closure and binary-identical rebuilding remain unconfirmed.')
            except (ValueError, OSError, zipfile.BadZipFile) as error:
                component['unresolved'].append(issue('MAVEN_UPSTREAM_SUPPLEMENT_UNAVAILABLE', coordinate, str(error)))
        if mapping and component['sourceFiles']:
            portable = copy.deepcopy(mapping)
            portable['sourceArchive']['path'] = component['sourceFiles'][0]['path']
            if mapping.get('type') == embedded_maven_source.MAPPING_TYPE:
                portable['upstreamArchive']['path'] = component['buildEvidenceFiles'][0]['path']
            if mapping.get('metadataPom'):
                matched = next((record for record in component['metadataFiles']
                                if record['sha256'] == mapping['metadataPom']['sha256']), None)
                if matched:
                    portable['metadataPom']['path'] = matched['path']
                else:
                    portable = None
            if portable:
                portable_mappings.append(portable)
        unresolved.extend(component['unresolved'])
        components.append(component)
    portable_record = None
    if mapping_path:
        portable_bytes = json_bytes({'schemaVersion': 1, 'kind': 'z8-maven-source-mappings',
                                     'components': portable_mappings})
        atomic_write(output / 'source-mappings.json', portable_bytes)
        portable_record = retain({'path': 'source-mappings.json',
            'sha256': hashlib.sha256(portable_bytes).hexdigest(), 'bytes': len(portable_bytes),
            'status': 'VERIFIED'}, 'portable-source-mappings')
    report = {'schemaVersion': 1, 'kind': 'z8-maven-sources',
        'inputs': {'gradleArtifactsSha256': sha256(args.gradle_artifacts)},
        'status': 'INCOMPLETE' if unresolved else 'SOURCES_COLLECTED_REVIEW_REQUIRED',
        'sourceClosureReviewed': False, 'components': components,
        'files': [all_files[key] for key in sorted(all_files)], 'unresolved': unresolved,
        'reviewRequired': ['This collection covers only the supplied resolved runtime inventory, not every local cache or build tool.',
            'A reviewer must determine combined-work source scope, preserve applicable copyright/license notices, and verify missing resources/build inputs. Collection is not human approval.']}
    if mapping_path:
        report['inputs']['sourceMappingsSha256'] = hashlib.sha256(mapping_bytes).hexdigest()
        report['portableSourceMappings'] = portable_record
    if supplement_record:
        report['inputs']['upstreamSupplementsSha256'] = supplement_record['sha256']
        report['upstreamSupplements'] = supplement_record
    atomic_write(previous_file, json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--gradle-artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-mappings', type=Path, help='Exact upstream ZIP or supported embedded-source mappings keyed to actual binary hashes; never approvals')
    parser.add_argument('--upstream-lock', type=Path, default=ROOT / 'tools/maven-upstream-supplements.lock.json',
                        help='Pinned supplemental original build/resource/license inputs; publisher source JARs remain intact')
    parser.add_argument('--upstream-cache', type=Path, action='append', default=[],
                        help='Reuse hash-matching original inputs from this directory; repeat for multiple caches')
    parser.add_argument('--fetch', action='store_true', help='Download from allowed Maven repositories and exact hash-pinned upstream HTTPS URLs')
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    report = collect(args)
    print(json.dumps({'status': report['status'], 'components': len(report['components']),
                      'files': len(report['files']), 'unresolvedCount': len(report['unresolved'])}))
    return 0 if not report['unresolved'] or args.allow_incomplete else 2


if __name__ == '__main__':
    raise SystemExit(main())
