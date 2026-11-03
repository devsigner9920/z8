"""Release evidence helpers. Source recipes are data, never executed by this module."""
import hashlib
import importlib.util
from collections import Counter
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GENERATED_NOTICES = {'third-party-notices.txt', 'release-notices.json'}
SECRET_NAMES = {'.env', '.netrc', '.npmrc', 'credentials', 'credentials.json', 'auth.json',
                'local.properties', 'id_rsa', 'id_ed25519', 'id_ecdsa', 'testkey_untrusted.jks'}
SECRET_SUFFIXES = {'.jks', '.keystore', '.p12', '.pfx', '.pem', '.key'}

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
                    'PINNED_UPSTREAM_SOURCE_ARCHIVE': 'upstream-source-archive'}
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
            if (not component or coordinate in mapped
                    or component['sourceDisposition'] != 'PINNED_UPSTREAM_SOURCE_ARCHIVE'
                    or not mapping.get('sourceArchive')
                    or any(mapping.get(key) != component.get('upstreamMapping', {}).get(key)
                           for key in ('repository', 'tag', 'commit', 'versionEvidence'))
                    or sorted(set(mapping['binaryArtifactSha256'])) != sorted({b['sha256'] for b in component['binaryArtifacts']})):
                raise ValueError('Portable Maven mapping does not match component')
            mapped.add(coordinate)
            for key, candidates in [('sourceArchive', component['sourceFiles']), ('metadataPom', component['metadataFiles'])]:
                if key not in mapping:
                    continue
                item = mapping[key]
                if not any(item['path'] == c['path'] and item['sha256'] == c['sha256'] for c in candidates):
                    raise ValueError('Portable Maven mapping references unavailable source evidence')
        if any(coordinate not in mapped for coordinate, component in components.items()
               if component['sourceDisposition'] == 'PINNED_UPSTREAM_SOURCE_ARCHIVE' and not component['unresolved']):
            raise ValueError('Portable Maven mapping is missing for a collected upstream source')
    return report


def historical_guest_inventory(path, root=ROOT):
    # Use the reconstruction command's exact validator so a source distribution
    # cannot pass release checks with an input set the actual preparer rejects.
    # Load our trusted tool implementation; only the selected project's lock is data.
    spec = importlib.util.spec_from_file_location('z8_historical_guest', ROOT / 'tools/prepare-guest.py')
    preparer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preparer)
    preparer.LOCK_PATH = Path(root) / 'runtime/guest/image.lock.json'
    return preparer.read_historical_managed_inputs(path, preparer.read_lock())['manifest']


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
