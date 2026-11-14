"""Release evidence helpers. Source recipes are data, never executed by this module."""
import hashlib
import gzip
import importlib.util
from collections import Counter
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import urllib.parse
import urllib.request
import zipfile
import embedded_maven_source
import maven_upstream_supplements as supplements

ROOT = Path(__file__).resolve().parents[1]
GENERATED_NOTICES = {'third-party-notices.txt', 'release-notices.json'}
SECRET_NAMES = {'.env', '.netrc', '.npmrc', 'credentials', 'credentials.json', 'auth.json',
                'local.properties', 'id_rsa', 'id_ed25519', 'id_ecdsa', 'testkey_untrusted.jks'}
SECRET_SUFFIXES = {'.jks', '.keystore', '.p12', '.pfx', '.pem', '.key'}


# Public verification material is not a signing secret. This exception is
# deliberately tied to one upstream path, revision and byte sequence.
PINNED_PUBLIC_SOURCE_KEYS = {
    'upstream/termux-packages/scripts/llvm-snapshot.gpg.key': {
        'source': 'termuxPackages',
        'commit': '27d2485b86dd0aed74ae7095434c83cbba7bf1dd',
        'sha256': 'ce6eee4130298f79b0e0f09a89f93c1bc711cd68e7e3182d37c8e96c5227e2f0',
    },
}


def verified_public_source_key(name, payload, source_lock):
    expected = PINNED_PUBLIC_SOURCE_KEYS.get(name)
    return bool(expected
                and source_lock.get(expected['source'], {}).get('commit') == expected['commit']
                and payload.startswith(b'-----BEGIN PGP PUBLIC KEY BLOCK-----')
                and hashlib.sha256(payload).hexdigest() == expected['sha256'])

# This reviewed image contains older Z8-managed scripts than the current source.
# This is a known-archive guard, not automatic source-closure detection for future images.
HISTORICAL_GUEST_ARCHIVES_REQUIRING_SOURCES = frozenset({
    '38463da28ca71e6be8ef36c0ff0f5a4da558eee3577cfd7b30e14c0ce6d4ef54',
})


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def bytes_sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Refusing symlink output: ' + str(path))
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    return json.loads(Path(path).read_text())


def maven_source_inventory(path, gradle_artifacts=None):
    """Verify collected runtime-library source bytes, without declaring source closure."""
    path = Path(path)
    report = read_json(path)
    if report.get('schemaVersion') != 1 or report.get('kind') != 'z8-maven-sources':
        raise ValueError('Expected Maven source inventory')
    if gradle_artifacts:
        if report.get('inputs', {}).get('gradleArtifactsSha256') != sha256(gradle_artifacts):
            raise ValueError('Maven sources describe a different runtime dependency inventory')
        expected = Counter((x['group'], x['name'], x['version'], x['type'], x['sha256'])
                           for x in read_json(gradle_artifacts)['components'])
        actual = Counter((c['group'], c['name'], c['version'], b['type'], b['sha256'])
                         for c in report['components'] for b in c['binaryArtifacts'])
        if expected != actual:
            raise ValueError('Maven sources do not cover the exact runtime artifacts')
    seen, records = set(), {}
    for item in report.get('files', []):
        relative = safe_relative(item['path'])
        if relative in seen or relative != item['path'] or secret_path(relative):
            raise ValueError('Duplicate or disallowed Maven source record')
        if item.get('status') != 'VERIFIED':
            raise ValueError('Unverified Maven source record')
        seen.add(relative)
        records[relative] = item
        target = path.parent / relative
        if (any(parent.is_symlink() for parent in (target, *target.parents) if parent != path.parent and parent.is_relative_to(path.parent))
                or not target.is_file() or sha256(target) != item['sha256'] or target.stat().st_size != item['bytes']):
            raise ValueError('Maven source payload changed: ' + relative)
    def reference(item, role=None):
        if item['path'] not in records:
            raise ValueError('Maven source reference missing from file inventory')
        record = records[item['path']]
        if record['sha256'] != item['sha256']:
            raise ValueError('Maven source reference checksum mismatch')
        if (record['bytes'] != item.get('bytes') or item.get('status') != 'VERIFIED'
                or record.get('role') != item.get('role') or (role and item.get('role') != role)):
            raise ValueError('Maven source reference metadata mismatch')
        return path.parent / item['path']

    unresolved, components = [], {}
    source_roles = {'PUBLISHED_SOURCE_JAR': 'published-source-jar',
                    'PINNED_UPSTREAM_SOURCE_ARCHIVE': 'upstream-source-archive',
                    embedded_maven_source.DISPOSITION: 'embedded-source-binary'}
    for component in report['components']:
        coordinate = ':'.join(component[key] for key in ('group', 'name', 'version'))
        if coordinate in components or not component.get('binaryArtifacts'):
            raise ValueError('Duplicate or empty Maven component')
        components[coordinate] = component
        problems = component.get('unresolved')
        if not isinstance(problems, list) or any(not isinstance(x, dict) for x in problems):
            raise ValueError('Missing Maven component unresolved state')
        unresolved.extend(problems)
        codes = {x.get('code') for x in problems}
        sources, metadata = component.get('sourceFiles'), component.get('metadataFiles')
        if not isinstance(sources, list) or not isinstance(metadata, list):
            raise ValueError('Missing Maven source reference lists')
        for item in sources:
            reference(item)
        for item in metadata:
            reference(item, 'pom')
        if not metadata and 'MAVEN_POM_UNAVAILABLE' not in codes:
            raise ValueError('Missing Maven metadata must remain unresolved')
        if not component.get('licenses') and 'MAVEN_LICENSE_METADATA_MISSING' not in codes:
            raise ValueError('Missing Maven license metadata must remain unresolved')
        disposition = component.get('sourceDisposition')
        index = component.get('contentInventory')
        if disposition in source_roles:
            if (len(sources) != 1 or not index or type(component.get('sourceFileCount')) is not int
                    or component['sourceFileCount'] < 1):
                raise ValueError('Collected Maven source disposition requires source files and content inventory')
            reference(sources[0], source_roles[disposition])
            content = read_json(reference(index, 'source-content-index'))
            if (content.get('schemaVersion') != 1 or content.get('kind') != 'z8-source-content-inventory'
                    or content.get('coordinate') != coordinate
                    or content.get('sourceArtifactSha256') != sources[0]['sha256']
                    or sum(member['path'].endswith(('.java', '.kt', '.kts', '.c', '.h', '.cpp', '.scala'))
                           for member in content.get('members', [])) != component['sourceFileCount']):
                raise ValueError('Maven source content inventory does not match component')
            if disposition == embedded_maven_source.DISPOSITION:
                build_files = component.get('buildEvidenceFiles', [])
                if (len(build_files) != 2 or not component.get('embeddedSourceEvidence')
                        or tuple(component[key] for key in ('group', 'name', 'version')) != embedded_maven_source.COORDINATE
                        or {binary['sha256'] for binary in component['binaryArtifacts']} != {embedded_maven_source.BINARY_SHA256}):
                    raise ValueError('Embedded Maven source requires exact binary and build evidence')
                dump_path = reference(build_files[0], 'upstream-svn-dump')
                snapshot_path = reference(build_files[1], 'upstream-svn-snapshot')
                evidence_path = reference(component['embeddedSourceEvidence'], 'embedded-source-evidence')
                snapshot, evidence = embedded_maven_source.evidence(reference(sources[0]).read_bytes(), dump_path.read_bytes())
                if snapshot_path.read_bytes() != snapshot or read_json(evidence_path) != evidence:
                    raise ValueError('Embedded Maven source evidence does not match original inputs')
        elif disposition == 'MISSING':
            if sources or index or component.get('sourceFileCount', 0) or 'MAVEN_SOURCE_UNAVAILABLE' not in codes:
                raise ValueError('Missing Maven source must remain unresolved')
        elif disposition == 'NO_CODE_ARTIFACT_VERIFIED':
            if (coordinate != 'com.google.guava:listenablefuture:9999.0-empty-to-avoid-conflict-with-guava'
                    or sources or index or component.get('sourceFileCount', 0)
                    or any(type(binary.get(key)) is not int or binary[key] != 0
                           for binary in component['binaryArtifacts']
                           for key in ('classCount', 'nativeCount', 'resourceCount', 'moduleInfoCount'))):
                raise ValueError('Invalid Maven empty-artifact exception')
        else:
            raise ValueError('Unknown Maven source disposition')
    expected_status = 'INCOMPLETE' if unresolved else 'SOURCES_COLLECTED_REVIEW_REQUIRED'
    if report.get('unresolved') != unresolved or report.get('status') != expected_status:
        raise ValueError('Maven summary does not match component unresolved state')
    if report.get('sourceClosureReviewed') is not False:
        raise ValueError('Maven collection cannot claim source closure approval')
    mapping_sha = report.get('inputs', {}).get('sourceMappingsSha256')
    if mapping_sha:
        original = records.get('provenance/source-mappings.json', {})
        if original.get('sha256') != mapping_sha or original.get('role') != 'source-mapping-evidence':
            raise ValueError('Maven mapping provenance does not match original input')
        portable = report.get('portableSourceMappings')
        if not portable or portable.get('path') != 'source-mappings.json':
            raise ValueError('Missing portable Maven source mappings')
        mappings = read_json(reference(portable, 'portable-source-mappings'))
        if mappings.get('schemaVersion') != 1 or mappings.get('kind') != 'z8-maven-source-mappings':
            raise ValueError('Invalid portable Maven source mappings')
        mapped = set()
        for mapping in mappings['components']:
            coordinate = ':'.join(mapping[key] for key in ('group', 'name', 'version'))
            component = components.get(coordinate)
            embedded = mapping.get('type') == embedded_maven_source.MAPPING_TYPE
            expected_disposition = embedded_maven_source.DISPOSITION if embedded else 'PINNED_UPSTREAM_SOURCE_ARCHIVE'
            if (not component or coordinate in mapped
                    or component['sourceDisposition'] != expected_disposition
                    or not mapping.get('sourceArchive')
                    or (not embedded and any(mapping.get(key) != component.get('upstreamMapping', {}).get(key)
                           for key in ('repository', 'tag', 'commit', 'versionEvidence'))
                       )
                    or sorted(set(mapping['binaryArtifactSha256'])) != sorted({b['sha256'] for b in component['binaryArtifacts']})):
                raise ValueError('Portable Maven mapping does not match component')
            if embedded:
                embedded_maven_source.validate_mapping(mapping,
                    tuple(component[key] for key in ('group', 'name', 'version')), mapping['binaryArtifactSha256'])
            mapped.add(coordinate)
            for key, candidates in [('sourceArchive', component['sourceFiles']), ('metadataPom', component['metadataFiles']),
                                    ('upstreamArchive', component.get('buildEvidenceFiles', []))]:
                if key not in mapping:
                    continue
                item = mapping[key]
                if not any(item['path'] == c['path'] and item['sha256'] == c['sha256'] for c in candidates):
                    raise ValueError('Portable Maven mapping references unavailable source evidence')
        if any(coordinate not in mapped for coordinate, component in components.items()
               if component['sourceDisposition'] in ('PINNED_UPSTREAM_SOURCE_ARCHIVE', embedded_maven_source.DISPOSITION)
               and not component['unresolved']):
            raise ValueError('Portable Maven mapping is missing for a collected upstream source')
    elif any(component['sourceDisposition'] == embedded_maven_source.DISPOSITION for component in components.values()):
        raise ValueError('Embedded Maven source requires explicit mapping provenance')
    supplement_sha = report.get('inputs', {}).get('upstreamSupplementsSha256')
    if supplement_sha:
        lock_record = report.get('upstreamSupplements', {})
        if (lock_record.get('sha256') != supplement_sha
                or lock_record.get('path') != 'provenance/upstream-supplements.json'):
            raise ValueError('Missing pinned Maven upstream supplement provenance')
        specs, pinned = supplements.validate_lock(read_json(reference(lock_record, 'maven-upstream-lock')))
        for coordinate, component in components.items():
            parts = tuple(component[key] for key in ('group', 'name', 'version'))
            mapping, snapshot = pinned.get(parts), component.get('upstreamSnapshot')
            if not mapping:
                if snapshot:
                    raise ValueError('Unpinned upstream supplement')
                continue
            if not snapshot:
                if not any(x.get('code') == 'MAVEN_UPSTREAM_SUPPLEMENT_UNAVAILABLE' for x in component['unresolved']):
                    raise ValueError('Missing upstream inputs must remain unresolved')
                continue
            if (component['sourceDisposition'] != 'PUBLISHED_SOURCE_JAR'
                    or snapshot.get('sourceClosureReviewed') is not False
                    or snapshot.get('lockSha256') != supplement_sha
                    or sorted(set(mapping['binaryArtifactSha256'])) != sorted({x['sha256'] for x in component['binaryArtifacts']})):
                raise ValueError('Upstream supplement does not match actual runtime inputs')
            used = {x['archiveId'] for x in mapping['sourceMatches'] + mapping['requiredInputs']}
            used.update(mapping.get('commonSupportArchiveIds', []))
            used.update(x['archiveId'] for x in mapping.get('binaryMemberMatches', []))
            used.update(x['archiveId'] for x in mapping.get('sourceTransforms', []))
            used.update(x[key] for x in mapping.get('rootBlobBindings', []) for key in ('archiveId', 'treeArchiveId'))
            retained = snapshot.get('inputs', [])
            if len(retained) != len(used) or {x.get('archiveId') for x in retained} != used:
                raise ValueError('Missing or duplicate pinned upstream payload')
            payloads = {}
            for item in retained:
                spec = specs[item['archiveId']]
                if (any(item.get(key) != spec[key] for key in ('url', 'sha256', 'bytes'))
                        or records.get(item.get('path'), {}).get('url') != spec['url']):
                    raise ValueError('Upstream payload reference differs from pinned original')
                payloads[item['archiveId']] = reference(item, supplements.ROLE).read_bytes()
            binary_refs = snapshot.get('binaryInputs', [])
            expected_binary_shas = {x['binaryArtifactSha256'] for x in mapping.get('binaryMemberMatches', [])}
            if (len(binary_refs) != len(expected_binary_shas)
                    or {x.get('sha256') for x in binary_refs} != expected_binary_shas):
                raise ValueError('Missing or duplicate retained binary correspondence input')
            binary_inputs = {item['sha256']: reference(item, 'maven-binary-correspondence-input').read_bytes()
                             for item in binary_refs}
            proof = supplements.evidence(mapping, specs, reference(component['sourceFiles'][0]).read_bytes(),
                                         payloads, binary_inputs)
            if read_json(reference(snapshot['evidence'], supplements.EVIDENCE_ROLE)) != proof:
                raise ValueError('Upstream correspondence differs from original source bytes')
    elif any(component.get('upstreamSnapshot') for component in components.values()):
        raise ValueError('Upstream supplement lacks pinned provenance')
    return report


def historical_guest_inventory(path, root=ROOT):
    # Use the reconstruction command's exact validator so a source distribution
    # cannot pass release checks with an input set the actual preparer rejects.
    # Load our trusted tool implementation; only the selected project's lock is data.
    spec = importlib.util.spec_from_file_location('z8_historical_guest', ROOT / 'tools/prepare-guest.py')
    preparer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preparer)
    current = Path(root) / 'runtime/guest/image.lock.json'
    legacy = Path(root) / 'runtime/guest/legacy/ubuntu-24.04.5.lock.json'
    source = read_json(path).get('guestSource')
    candidates = [candidate for candidate in (current, legacy) if candidate.is_file()
                  and not candidate.is_symlink() and read_json(candidate).get('source') == source]
    if len(candidates) != 1:
        raise ValueError('Historical guest source must match one retained, known image lock')
    preparer.LOCK_PATH = candidates[0]
    return preparer.read_historical_managed_inputs(path, preparer.read_lock())['manifest']


def read_source_index(path):
    path = Path(path)
    maximum = 256 * 1024 * 1024
    if path.suffix == '.xz':
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('Compressed source index exceeds limit')
        decoder = lzma.LZMADecompressor(memlimit=128 * 1024 * 1024)
        data = decoder.decompress(path.read_bytes(), max_length=maximum + 1)
        if not decoder.eof or decoder.unused_data.strip(b'\0'):
            raise ValueError('Truncated, oversized or concatenated source index')
    else:
        opener = gzip.open if path.suffix == '.gz' else open
        with opener(path, 'rb') as stream:
            data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('Distribution source index exceeds limit')
    return deb822(data.decode())


def debian_snapshot_base(record):
    match = re.fullmatch(r'https://snapshot\.debian\.org/archive/(debian|debian-security)/(\d{8}T\d{6}Z)/dists/(trixie|trixie-updates|trixie-security)/main/source/Sources\.xz', record.get('url', ''))
    if (not match or record.get('archive') != match[1] or record.get('suite') != match[3]
            or (match[1] == 'debian-security') != (match[3] == 'trixie-security')
            or not re.fullmatch('[0-9a-f]{64}', record.get('sha256', ''))
            or type(record.get('bytes')) is not int or not 0 < record['bytes'] <= 64 * 1024 * 1024):
        raise ValueError('Invalid pinned Debian source index identity')
    return 'https://snapshot.debian.org/archive/' + match[1] + '/' + match[2] + '/'


def source_payload_table(item, base):
    directory = item.get('Directory', '')
    if not directory.startswith('pool/') or safe_relative(directory) != directory:
        raise ValueError('Invalid distribution source directory')
    files, names = [], set()
    for line in item.get('Checksums-Sha256', '').splitlines():
        if not line.strip():
            continue
        checksum, size, name = line.split()
        if (not re.fullmatch('[a-f0-9]{64}', checksum) or not re.fullmatch('[0-9]+', size)
                or not 0 < int(size) <= 512 * 1024 * 1024
                or safe_relative(name) != name or '/' in name or name in names):
            raise ValueError('Invalid source checksum table')
        names.add(name)
        files.append({'url': base + directory + '/' + urllib.parse.quote(name), 'sha256': checksum, 'bytes': int(size)})
    return files


def package_source_indexes(inventory, directory):
    """Verify retained Debian indexes and every exact source-version reference."""
    records = inventory.get('sourceIndexes', [])
    if inventory.get('inputs', {}).get('guestDistribution') != 'debian':
        if records:
            raise ValueError('Unexpected source indexes for an unrecognized distribution')
        return []
    pins = inventory.get('inputs', {}).get('guestSourceIndexes', [])
    if not pins or len(records) != len(pins) or len({pin.get('url') for pin in pins}) != len(pins):
        raise ValueError('Missing or duplicate pinned Debian source indexes')
    lookup, seen = {}, set()
    needed = {(component.get('sourceIndex', {}).get('url'), component.get('sourceName'), component.get('sourceVersion'))
              for component in inventory['components'] if component.get('scope') == 'bundled-guest'}
    for record in records:
        base = debian_snapshot_base(record)
        if (record.get('status') != 'VERIFIED' or record.get('signatureVerified') is not False
                or record.get('role') != 'guest-source-index' or record['url'] in seen
                or not any(all(record.get(key) == pin.get(key) for key in ('url', 'sha256', 'bytes', 'suite', 'archive')) for pin in pins)):
            raise ValueError('Debian source index differs from its image pin')
        seen.add(record['url'])
        relative = safe_relative(record['path'])
        path = Path(directory) / relative
        if (path.is_symlink() or not path.is_file() or path.stat().st_size != record['bytes']
                or sha256(path) != record['sha256']):
            raise ValueError('Pinned Debian source index bytes changed')
        for item in read_source_index(path):
            key = (record['url'], item.get('Package'), item.get('Version'))
            if key not in needed:
                continue
            table = source_payload_table(item, base)
            if key in lookup and lookup[key] != table:
                raise ValueError('Conflicting exact Debian source records')
            lookup[key] = table
    for component in inventory['components']:
        if component.get('scope') != 'bundled-guest':
            continue
        index = component.get('sourceIndex', {})
        if 'Exact Debian source version not present in supplied indexes' in component.get('unresolved', []):
            continue
        if not any(index.get('url') == record['url'] and index.get('sha256') == record['sha256'] for record in records):
            raise ValueError('Debian component names an unretained source index')
        if index.get('signatureVerified') is not False:
            raise ValueError('Pinned HTTPS evidence cannot claim repository signature verification')
        key = (index.get('url'), component.get('sourceName'), component.get('sourceVersion'))
        actual = [{key: source[key] for key in ('url', 'sha256', 'bytes')} for source in component['sourceFiles']]
        if key not in lookup or actual != lookup[key] or not actual:
            raise ValueError('Debian component does not match its exact source package/version table')
    return records


def safe_relative(name):
    parts = PurePosixPath(name).parts
    if not parts or name.startswith('/') or '\\' in name or '\x00' in name or '..' in parts:
        raise ValueError('Unsafe archive path')
    return str(PurePosixPath(name))


def secret_path(name):
    p = PurePosixPath(name)
    return (any(x.lower() in SECRET_NAMES or x.lower() in {'.ssh', '.aws', '.gnupg'}
                or x.lower().startswith('.env.')
                or (x.lower().startswith('credentials') and x.lower().endswith('.json'))
                for x in p.parts) or p.suffix.lower() in SECRET_SUFFIXES)


def zip_entry(bundle, name, data, mode=0o644, kind=0o100000):
    info = zipfile.ZipInfo(safe_relative(name), (1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (kind | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    bundle.writestr(info, data)


def deb822(text):
    """Read Debian control paragraphs, including multiline hashes and descriptions."""
    result, paragraph, key = [], {}, None
    for line in text.splitlines() + ['']:
        if not line:
            if paragraph:
                result.append(paragraph)
            paragraph, key = {}, None
        elif line[0].isspace():
            if key is not None:
                paragraph[key] += '\n' + line[1:]
        elif ':' in line:
            key, value = line.split(':', 1)
            paragraph[key] = value.strip()
    return result


def archive_inventory(path):
    """Inspect only regular archive metadata. Do not extract or follow guest symlinks."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive members')
        packages = deb822(z.read('var/lib/dpkg/status').decode())
        packages = [p for p in packages if p.get('Status') == 'install ok installed']
        notices = {}
        for name in names:
            lower = name.lower()
            if (('/share/doc/' in '/' + name or '/share/common-licenses/' in '/' + name)
                    and not name.endswith('/') and any(x in lower for x in
                    ['copyright', 'license', 'licence', 'copying', 'notice', 'common-licenses/'])):
                info = z.getinfo(name)
                if info.file_size <= 2 * 1024 * 1024:
                    # Preserve bytes exactly in the public evidence archive. UI
                    # decoding happens separately and never rewrites this copy.
                    notices[name] = z.read(name)
    return packages, notices


class HttpsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('Refusing non-HTTPS redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, target, expected=None, limit=512 * 1024 * 1024):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Source downloads require credential-free HTTPS')
    target = Path(target)
    if target.is_file() and not target.is_symlink() and (expected is None or sha256(target) == expected):
        return {'sha256': sha256(target), 'bytes': target.stat().st_size}
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.source-', dir=target.parent)
    try:
        opener = urllib.request.build_opener(HttpsRedirect())
        request = urllib.request.Request(url, headers={'User-Agent': 'z8-release-source/1'})
        with os.fdopen(fd, 'wb') as output, opener.open(request, timeout=30) as response:
            size = 0
            while chunk := response.read(256 * 1024):
                size += len(chunk)
                if size > limit:
                    raise ValueError('Source exceeds download size limit')
                output.write(chunk)
        actual = sha256(tmp)
        if expected is not None and actual != expected:
            raise ValueError('Downloaded source checksum differs from provenance')
        if target.is_symlink():
            raise ValueError('Refusing symlink download target')
        os.replace(tmp, target)
        return {'sha256': actual, 'bytes': size}
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def source_id(package):
    match = re.fullmatch(r'([^ ()]+)(?: \(([^)]+)\))?', package.get('Source', package['Package']))
    if not match:
        raise ValueError('Unsupported source package field')
    return match[1], match[2] or package['Version']


def checked_asset(manifest_path, archive_key='archive', hash_key='sha256'):
    manifest_path = Path(manifest_path)
    data = read_json(manifest_path)
    name = safe_relative(data[archive_key])
    path = manifest_path.parent / name
    if path.is_symlink() or sha256(path) != data[hash_key]:
        raise ValueError('Archive differs from manifest: ' + name)
    return path, data


def issue(code, component, detail):
    return {'code': code, 'component': component, 'detail': detail}
