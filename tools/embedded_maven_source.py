"""Exact JSR305 1.3.9 source evidence; collection is not release approval.

The original JAR contains its Java sources. Google's preserved SVN dump supplies
the contemporaneous build and license files, unlike its newer HEAD snapshot.
Only the recorded primary-source hashes and SVN revision are accepted here.
"""
import gzip
import hashlib
import io
from pathlib import PurePosixPath
import re
import zipfile

COORDINATE = ('com.google.code.findbugs', 'jsr305', '1.3.9')
BINARY_SHA256 = '905721a0eea90a81534abb7ee6ef4ea2e5e645fa1def0a5cd88402df1b46c9ed'
DUMP_SHA256 = '4f0debcffb11dab2986dbf1bc9e1375fec2eae0fa837f0ece21f375262a4be4b'
DUMP_URL = 'https://storage.googleapis.com/google-code-archive-source/v2/code.google.com/jsr-305/repo.svndump.gz'
BINARY_URL = 'https://repo.maven.apache.org/maven2/com/google/code/findbugs/jsr305/1.3.9/jsr305-1.3.9.jar'
REVISION = 49
MAPPING_TYPE = 'embedded-binary-svn-source'
DISPOSITION = 'EMBEDDED_SOURCE_WITH_PINNED_UPSTREAM'
SOURCE_PREFIX = 'trunk/ri/src/main/java/'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_mapping(mapping, parts, binary_hashes):
    if (parts != COORDINATE or set(binary_hashes) != {BINARY_SHA256}
            or mapping.get('type') != MAPPING_TYPE
            or mapping.get('revision') != REVISION
            or mapping.get('sourceArchive', {}).get('sha256') != BINARY_SHA256
            or mapping.get('sourceArchive', {}).get('url') != BINARY_URL
            or mapping.get('upstreamArchive', {}).get('sha256') != DUMP_SHA256
            or mapping.get('upstreamArchive', {}).get('url') != DUMP_URL):
        raise ValueError('Embedded source mapping must match the exact JSR305 binary and preserved SVN revision')


def svn_snapshot(data, revision):
    """Read fulltext SVN dump records in memory. Never execute or extract paths."""
    if len(data) > 4 * 1024 * 1024:
        raise ValueError('SVN evidence exceeds inspection limit')
    tree, revisions, current, offset = {}, {}, None, 0
    while offset < len(data):
        offset += len(data[offset:]) - len(data[offset:].lstrip(b'\n'))
        if offset == len(data):
            break
        end = data.find(b'\n\n', offset)
        if end < 0:
            raise ValueError('Truncated SVN evidence headers')
        headers = dict(line.decode('utf-8').split(': ', 1) for line in data[offset:end].splitlines())
        offset = end + 2
        length = int(headers.get('Content-length', 0))
        payload = data[offset:offset + length]
        if length < 0 or len(payload) != length:
            raise ValueError('Truncated SVN evidence content')
        offset += length
        if 'Revision-number' in headers:
            if current is not None:
                revisions[current] = dict(tree)
            current = int(headers['Revision-number'])
            if current > revision:
                break
        if 'Node-path' not in headers:
            continue
        name = headers['Node-path']
        if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or '\\' in name:
            raise ValueError('Unsafe SVN evidence path')
        if headers.get('Text-delta') == 'true' or headers.get('Prop-delta') == 'true':
            raise ValueError('Delta SVN evidence is not supported')
        if headers['Node-action'] in ('delete', 'replace'):
            tree = {key: value for key, value in tree.items() if key != name and not key.startswith(name + '/')}
        if 'Node-copyfrom-path' in headers:
            origin = headers['Node-copyfrom-path']
            source = revisions[int(headers['Node-copyfrom-rev'])]
            for key, value in source.items():
                if key == origin or key.startswith(origin + '/'):
                    tree[name + key[len(origin):]] = value
        if headers.get('Node-kind') == 'dir' and headers['Node-action'] != 'delete':
            tree[name + '/'] = None
        if 'Text-content-length' in headers:
            text = payload[int(headers.get('Prop-content-length', 0)):]
            if len(text) != int(headers['Text-content-length']):
                raise ValueError('SVN text length mismatch')
            for algorithm in ('md5', 'sha1'):
                if 'Text-content-' + algorithm in headers:
                    if hashlib.new(algorithm, text).hexdigest() != headers['Text-content-' + algorithm]:
                        raise ValueError('SVN text checksum mismatch')
            tree[name] = text
    if current == revision:
        revisions[current] = dict(tree)
    if revision not in revisions:
        raise ValueError('Requested SVN revision is absent')
    return revisions[revision]


def evidence(binary_bytes, dump_bytes):
    if digest(binary_bytes) != BINARY_SHA256 or digest(dump_bytes) != DUMP_SHA256:
        raise ValueError('Embedded source primary evidence hash mismatch')
    with gzip.GzipFile(fileobj=io.BytesIO(dump_bytes)) as compressed:
        dump = compressed.read(4 * 1024 * 1024 + 1)
    tree = svn_snapshot(dump, REVISION)
    selected = {name: data for name, data in tree.items()
                if name.startswith('trunk/ri/') or name == 'trunk/pom.xml'}
    source_matches, class_sources, per_file = [], [], []
    with zipfile.ZipFile(io.BytesIO(binary_bytes)) as archive:
        members = {name: archive.read(name) for name in archive.namelist() if not name.endswith('/')}
    java = {name: data for name, data in members.items() if name.endswith('.java')}
    upstream_java = {name.removeprefix(SOURCE_PREFIX): data for name, data in selected.items()
                     if name.startswith(SOURCE_PREFIX) and name.endswith('.java')}
    if java != upstream_java or len(java) != 31:
        raise ValueError('Embedded Java sources do not exactly match the pinned SVN revision')
    for name, data in sorted(java.items()):
        source_matches.append({'binaryMember': name, 'upstreamMember': SOURCE_PREFIX + name,
                               'bytes': len(data), 'sha256': digest(data)})
        if name in {'javax/annotation/concurrent/' + file + '.java'
                    for file in ('GuardedBy', 'Immutable', 'NotThreadSafe')}:
            header = re.search(rb'/\*.*?\*/', data, re.S)
            if not header or b'creativecommons.org/licenses/by/2.5' not in header.group():
                raise ValueError('Expected per-file attribution license missing')
            per_file.append({'member': name, 'license': 'CC-BY-2.5',
                             'header': header.group().decode('utf-8')})
    for name in sorted(members):
        if name.endswith('.class'):
            source = name.split('$', 1)[0].removesuffix('.class') + '.java'
            if source not in java:
                raise ValueError('Class has no matching embedded Java source path')
            class_sources.append({'classMember': name, 'sourceMember': source,
                                  'classSha256': digest(members[name])})
        elif name != 'META-INF/MANIFEST.MF' and not name.endswith('.java'):
            raise ValueError('Unaccounted resource in embedded source JAR')
    if len(class_sources) != 35 or len(per_file) != 3:
        raise ValueError('Unexpected JSR305 class or per-file license coverage')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(selected.items()):
            info = zipfile.ZipInfo('jsr-305-r49/' + name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ((0o40755 << 16) | 0x10) if data is None else (0o100644 << 16)
            archive.writestr(info, b'' if data is None else data)
    report = {'kind': 'z8-embedded-source-evidence', 'schemaVersion': 1,
              'binarySha256': BINARY_SHA256, 'upstreamDumpSha256': DUMP_SHA256,
              'revision': REVISION, 'sourceMatches': source_matches, 'classSources': class_sources,
              'buildFiles': [{'member': name, 'sha256': digest(selected[name])}
                             for name in ('trunk/pom.xml', 'trunk/ri/pom.xml', 'trunk/ri/build.xml')],
              'license': {'member': 'trunk/ri/LICENSE', 'sha256': digest(selected['trunk/ri/LICENSE']),
                          'name': 'BSD-3-Clause', 'text': selected['trunk/ri/LICENSE'].decode('utf-8')},
              'perFileLicenses': per_file,
              'limitations': ['Source paths and bytes are matched; class-to-source paths are not a binary-identical rebuild.',
                              'The later HEAD archive changes Syntax.java and is not substituted for revision 49.',
                              'Collection does not assert shipped-class presence, combined-work scope or release approval.']}
    return output.getvalue(), report
