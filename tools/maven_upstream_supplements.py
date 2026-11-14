"""Pinned upstream inputs supplement, never replace, publisher source JARs.

Archives are read with bounded in-memory readers. No upstream recipe is run and
no symlink is followed. Source correspondence is not a release approval.
"""
import base64
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import stat
import tarfile
import zipfile

KIND = 'z8-maven-upstream-supplements'
ROLE = 'maven-upstream-input'
EVIDENCE_ROLE = 'maven-upstream-correspondence'
MAX_DOWNLOAD = 100 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
SOURCE_SUFFIXES = ('.java', '.kt', '.kts', '.scala', '.c', '.h', '.cpp', '.aidl')
HIDDEN_COORDINATE = ('org.lsposed.hiddenapibypass', 'hiddenapibypass', '6.1')
HIDDEN_GENERATED = 'org/lsposed/hiddenapibypass/library/BuildConfig.java'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fields(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError('Unknown fields in ' + label)


def safe_name(name):
    if (not isinstance(name, str) or not name or '\\' in name or '\x00' in name
            or PurePosixPath(name).is_absolute()
            or any(part in ('', '.', '..') for part in name.split('/'))):
        raise ValueError('Unsafe upstream member path')
    return name


def validate_spec(spec):
    fields(spec, ('id', 'format', 'repository', 'commit', 'repositoryPath', 'rootPrefix',
                  'url', 'sha256', 'bytes', 'transportEncoding', 'payloadEncoding'), 'upstream input')
    commit, repository = spec.get('commit', ''), spec.get('repository', '')
    if (not re.fullmatch(r'[0-9a-f]{40}', commit)
            or not re.fullmatch(r'[0-9a-f]{64}', spec.get('sha256', ''))
            or type(spec.get('bytes')) is not int or not 0 < spec['bytes'] <= MAX_DOWNLOAD
            or not re.fullmatch(r'[A-Za-z0-9_.-]+', spec.get('id', ''))):
        raise ValueError('Upstream input requires an exact commit, digest and bounded size')
    format_name = spec.get('format')
    if format_name == 'zip':
        if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Unsupported upstream GitHub repository')
        expected = 'https://codeload.github.com/' + repository[len('https://github.com/'):] + '/zip/' + commit
        prefix = spec.get('rootPrefix', '')
        if not prefix.endswith('/'):
            raise ValueError('GitHub input requires its exact archive root')
        safe_name(prefix[:-1])
    elif format_name in ('tar.gz', 'gitiles-base64', 'gitiles-file', 'gitiles-tree'):
        if not re.fullmatch(r'https://(?:android|chromium)\.googlesource\.com/[A-Za-z0-9_./-]+', repository):
            raise ValueError('Unsupported official Gitiles repository')
        safe_name(repository.split('.com/', 1)[1])
        path = spec.get('repositoryPath', '')
        if path:
            safe_name(path)
        elif format_name not in ('tar.gz', 'gitiles-tree'):
            raise ValueError('Missing upstream file path')
        if format_name == 'tar.gz':
            expected = repository + '/+archive/' + commit + ('/' + path if path else '') + '.tar.gz'
        elif format_name == 'gitiles-tree':
            if path:
                raise ValueError('Only root tree binding evidence is supported')
            expected = repository + '/+/' + commit + '/?format=JSON'
        else:
            expected = repository + '/+/' + commit + '/' + path + '?format=TEXT'
        if spec.get('rootPrefix', ''):
            raise ValueError('Gitiles input may not have an artificial archive root')
        if format_name == 'gitiles-file' and (spec.get('transportEncoding') != 'base64'
                or spec.get('payloadEncoding') != 'decoded-original-file'):
            raise ValueError('Decoded Gitiles input must describe its transport transformation')
    else:
        raise ValueError('Unsupported pinned upstream input format')
    if spec.get('url') != expected:
        raise ValueError('Upstream URL must bind the exact repository, commit and path')


def validate_lock(lock):
    fields(lock, ('schemaVersion', 'kind', 'archives', 'components'), 'upstream supplement lock')
    if lock.get('schemaVersion') != 1 or lock.get('kind') != KIND:
        raise ValueError('Expected pinned Maven upstream supplements')
    archives = {}
    for spec in lock.get('archives', []):
        validate_spec(spec)
        if spec['id'] in archives:
            raise ValueError('Duplicate upstream input ID')
        archives[spec['id']] = spec
    components = {}
    for component in lock.get('components', []):
        fields(component, ('group', 'name', 'version', 'binaryArtifactSha256', 'sourceJarSha256',
            'sourceMatches', 'requiredInputs', 'generatedSources', 'commonSupportArchiveIds',
            'rootBlobBindings', 'buildCommitClaim', 'releaseEvidenceUrl', 'reviewLimitations'), 'upstream component')
        if component.get('buildCommitClaim', False) is not False:
            raise ValueError('Source-byte correspondence cannot certify the original build commit')
        parts = tuple(component.get(key, '') for key in ('group', 'name', 'version'))
        if (any(not re.fullmatch(r'[A-Za-z0-9_.+\-]+', part) for part in parts)
                or parts in components
                or not re.fullmatch(r'[0-9a-f]{64}', component.get('sourceJarSha256', ''))
                or not component.get('binaryArtifactSha256')
                or any(not re.fullmatch(r'[0-9a-f]{64}', value) for value in component['binaryArtifactSha256'])):
            raise ValueError('Invalid or duplicate upstream supplement coordinate')
        matches = component.get('sourceMatches', [])
        if not matches or len({x['sourceJarMember'] for x in matches}) != len(matches):
            raise ValueError('Missing or duplicate upstream source correspondence')
        for item in matches + component.get('requiredInputs', []):
            if item.get('archiveId') not in archives:
                raise ValueError('Unknown upstream input reference')
            safe_name(item.get('upstreamMember', item.get('member', '')))
        for item in matches:
            fields(item, ('sourceJarMember', 'archiveId', 'upstreamMember'), 'source correspondence')
            safe_name(item['sourceJarMember'])
        for item in component.get('requiredInputs', []):
            fields(item, ('archiveId', 'member', 'category'), 'required upstream input')
        categories = {x.get('category') for x in component.get('requiredInputs', [])}
        if not {'build', 'license'} <= categories or not categories <= {'build', 'license', 'resource', 'source'}:
            raise ValueError('Supplement requires original build and license inputs')
        support = component.get('commonSupportArchiveIds', [])
        if len(set(support)) != len(support) or any(key not in archives for key in support):
            raise ValueError('Unknown or duplicate common upstream support input')
        for binding in component.get('rootBlobBindings', []):
            fields(binding, ('archiveId', 'treeArchiveId', 'repositoryPath', 'gitObject'), 'root blob binding')
            if (binding.get('archiveId') not in archives or binding.get('treeArchiveId') not in archives
                    or not re.fullmatch(r'[0-9a-f]{40}', binding.get('gitObject', ''))):
                raise ValueError('Invalid original root blob binding')
            safe_name(binding.get('repositoryPath', ''))
        generated = component.get('generatedSources', [])
        for item in generated:
            fields(item, ('sourceJarMember',), 'generated source')
        if generated and (parts != HIDDEN_COORDINATE or len(generated) != 1
                          or generated[0].get('sourceJarMember') != HIDDEN_GENERATED):
            raise ValueError('Unreviewed generated-source exception')
        if not isinstance(component.get('reviewLimitations'), list) or not component['reviewLimitations']:
            raise ValueError('Supplement must preserve its review limitations')
        components[parts] = component
    return archives, components


def read_members(spec, data):
    validate_spec(spec)
    if len(data) != spec['bytes'] or digest(data) != spec['sha256']:
        raise ValueError('Pinned upstream input hash or size mismatch')
    members, skipped, seen, total = {}, [], set(), 0
    prefix = spec.get('rootPrefix', '')
    def visit(name, size, reader, regular=True, directory=False):
        nonlocal total
        # No extraction or path resolution occurs, including for ignored links.
        name = name.rstrip('/') if directory else name
        safe_name(name)
        if name in seen or len(seen) >= 100000:
            raise ValueError('Duplicate or excessive upstream members')
        seen.add(name)
        if prefix:
            if directory and name == prefix[:-1]:
                return
            if not name.startswith(prefix):
                raise ValueError('Unexpected upstream archive root')
            name = name[len(prefix):]
            safe_name(name)
        if directory:
            return
        if not regular:
            skipped.append(name)
            return
        total += size
        if size < 0 or size > 64 * 1024 * 1024 or total > MAX_EXPANDED:
            raise ValueError('Upstream input exceeds inspection limit')
        payload = reader()
        if len(payload) != size:
            raise ValueError('Truncated upstream member')
        members[name] = payload
    if spec['format'] == 'zip':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for item in archive.infolist():
                mode = stat.S_IFMT(item.external_attr >> 16)
                visit(item.filename, item.file_size, lambda i=item: archive.read(i),
                      mode in (0, stat.S_IFREG), item.is_dir())
    elif spec['format'] == 'tar.gz':
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            for item in archive:
                visit(item.name, item.size, lambda i=item: archive.extractfile(i).read(),
                      item.isfile(), item.isdir())
    elif spec['format'] == 'gitiles-base64':
        payload = base64.b64decode(b''.join(data.split()), validate=True)
        visit(spec['repositoryPath'], len(payload), lambda: payload)
    elif spec['format'] == 'gitiles-file':
        visit(spec['repositoryPath'], len(data), lambda: data)
    else:
        visit('.gitiles-root.json', len(data), lambda: data)
    return members, sorted(skipped)


def source_members(data):
    members, total = {}, 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        seen = set()
        for item in archive.infolist():
            name = item.filename.rstrip('/') if item.is_dir() else item.filename
            safe_name(name)
            if name in seen or len(seen) >= 100000 or stat.S_IFMT(item.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError('Unsafe publisher source archive')
            seen.add(name)
            if item.is_dir():
                continue
            total += item.file_size
            if item.file_size > 64 * 1024 * 1024 or total > MAX_EXPANDED:
                raise ValueError('Publisher source archive exceeds inspection limit')
            if name.endswith(SOURCE_SUFFIXES):
                members[name] = archive.read(item)
    return members


def evidence(component, specs, source_jar, payloads):
    if digest(source_jar) != component['sourceJarSha256']:
        raise ValueError('Supplement does not match the exact publisher source JAR')
    source = source_members(source_jar)
    used = {x['archiveId'] for x in component['sourceMatches'] + component['requiredInputs']}
    used.update(component.get('commonSupportArchiveIds', []))
    used.update(x[key] for x in component.get('rootBlobBindings', []) for key in ('archiveId', 'treeArchiveId'))
    trees, ignored = {}, {}
    for key in sorted(used):
        trees[key], ignored[key] = read_members(specs[key], payloads[key])
    root_bindings = []
    source_revisions = {(specs[x['archiveId']]['repository'], specs[x['archiveId']]['commit'])
                        for x in component['sourceMatches']}
    source_repositories = {repository for repository, _ in source_revisions}
    for key in used:
        spec = specs[key]
        if (spec['format'] in ('gitiles-file', 'gitiles-base64')
                and spec['repository'] in source_repositories
                and (spec['repository'], spec['commit']) not in source_revisions
                and sum(x['archiveId'] == key for x in component.get('rootBlobBindings', [])) != 1):
            raise ValueError('Cross-commit original file requires its source-commit Git tree binding')
    for binding in component.get('rootBlobBindings', []):
        original_spec, tree_spec = specs[binding['archiveId']], specs[binding['treeArchiveId']]
        if (tree_spec['format'] != 'gitiles-tree'
                or (tree_spec['repository'], tree_spec['commit']) not in source_revisions
                or original_spec['repository'] != tree_spec['repository']
                or original_spec.get('repositoryPath') != binding['repositoryPath']):
            raise ValueError('Root blob binding must refer to the source commit and original file')
        original = trees[binding['archiveId']][binding['repositoryPath']]
        tree_bytes = trees[binding['treeArchiveId']]['.gitiles-root.json']
        if tree_bytes.startswith(b")]}'"):
            tree_bytes = tree_bytes[4:].lstrip(b'\r\n')
        tree = json.loads(tree_bytes)
        matching = [entry for entry in tree.get('entries', [])
                    if entry.get('name') == binding['repositoryPath'] and entry.get('type') == 'blob']
        git_object = hashlib.sha1(b'blob ' + str(len(original)).encode('ascii') + b'\x00' + original).hexdigest()
        if (len(matching) != 1 or matching[0].get('id') != binding['gitObject']
                or git_object != binding['gitObject']):
            raise ValueError('Original root file differs from source-commit Git tree object')
        root_bindings.append(dict(binding, sourceCommit=tree_spec['commit'], sha256=digest(original)))
    expected = {x['sourceJarMember'] for x in component['sourceMatches']}
    expected.update(x['sourceJarMember'] for x in component.get('generatedSources', []))
    if expected != set(source):
        raise ValueError('Supplement must account for every published source member')
    matches = []
    for item in component['sourceMatches']:
        payload = trees[item['archiveId']].get(item['upstreamMember'])
        if payload is None or source[item['sourceJarMember']] != payload:
            raise ValueError('Published source differs from pinned upstream member')
        matches.append(dict(item, bytes=len(payload), sha256=digest(payload)))
    required = []
    for item in component['requiredInputs']:
        payload = trees[item['archiveId']].get(item['member'])
        if payload is None:
            raise ValueError('Required upstream build, resource or license input is missing or a link')
        required.append(dict(item, bytes=len(payload), sha256=digest(payload)))
    generated = []
    for item in component.get('generatedSources', []):
        # This exact original AGP output is the sole reviewed exception.
        expected_bytes = (b'/**\n * Automatically generated file. DO NOT MODIFY\n */\n'
                          b'package org.lsposed.hiddenapibypass.library;\n\n'
                          b'public final class BuildConfig {\n'
                          b'  public static final boolean DEBUG = false;\n'
                          b'  public static final String LIBRARY_PACKAGE_NAME = "org.lsposed.hiddenapibypass.library";\n'
                          b'  public static final String BUILD_TYPE = "release";\n}\n')
        recipe = [x for x in required if x['member'] == 'library/build.gradle.kts' and x['category'] == 'build']
        if (source[item['sourceJarMember']] != expected_bytes or len(recipe) != 1
                or tuple(component[key] for key in ('group', 'name', 'version')) != HIDDEN_COORDINATE):
            raise ValueError('Generated source differs from the exact reviewed AGP output')
        raw = trees[recipe[0]['archiveId']][recipe[0]['member']]
        if b'buildConfig = true' not in raw or b'namespace = "org.lsposed.hiddenapibypass.library"' not in raw:
            raise ValueError('Original BuildConfig generator declarations are missing')
        generated.append(dict(item, bytes=len(expected_bytes), sha256=digest(expected_bytes), recipe=recipe[0]))
    return {'schemaVersion': 1, 'kind': 'z8-maven-upstream-correspondence',
            'coordinate': ':'.join(component[key] for key in ('group', 'name', 'version')),
            'sourceJarSha256': component['sourceJarSha256'],
            'binaryArtifactSha256': sorted(set(component['binaryArtifactSha256'])),
            'sourceMatches': matches, 'generatedSources': generated, 'requiredInputs': required,
            'rootBlobBindings': root_bindings,
            'upstreamInputs': [specs[key] for key in sorted(used)], 'ignoredNonRegularMembers': ignored,
            'reviewLimitations': component['reviewLimitations'], 'sourceClosureReviewed': False}
