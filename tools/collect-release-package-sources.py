#!/usr/bin/env python3
"""Inventory shipped packages; optionally fetch exact, checksum-verified source files.

HTTPS source indexes are evidence, not a claim that repository signatures were verified.
Unsupported recipe expressions stay unresolved; this program never sources shell recipes.
"""
import argparse
import concurrent.futures
import gzip
import lzma
from pathlib import Path
import re
import shlex
import tarfile
import urllib.parse
import zipfile
from release_compliance import ROOT, archive_inventory, atomic_write, checked_asset, deb822, download, issue, json_bytes, read_json, safe_relative, secret_path, sha256, source_id


def assignment(text, name):
    match = re.search(r'^' + re.escape(name) + r'=(.*)$', text, re.M)
    if not match:
        return []
    raw = match[1].strip()
    if raw.startswith('('):
        found = re.search(r'^' + re.escape(name) + r'=\((.*?)\)\s*$', text, re.M | re.S)
        if not found:
            return []
        raw = found[1]
    try:
        return shlex.split(raw, comments=True)
    except ValueError:
        return []


def expand(value, variables):
    def replace(m):
        token = m[1] or m[2]
        match = re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*)(?:\[([0-9]+)\])?(%\.\*|##\*\.|:[0-9]+)?', token)
        if not match:
            raise ValueError('Unsupported source expression')
        values = variables.get(match[1], [])
        index = int(match[2] or 0)
        if index >= len(values) or '$' in values[index] or '`' in values[index]:
            raise ValueError('Unresolved source expression')
        result = values[index]
        operation = match[3]
        if operation == '%.*':
            result = result.rsplit('.', 1)[0]
        elif operation == '##*.':
            result = result.rsplit('.', 1)[-1]
        elif operation:
            result = result[int(operation[1:]):]
        return result
    if '$(' in value or '`' in value:
        raise ValueError('Dynamic source expression requires reviewed metadata')
    result = re.sub(r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z_0-9]*)', replace, value)
    if '$' in result:
        raise ValueError('Unresolved source expression')
    return result


def recipe_values(recipe, depth=0):
    if depth > 3:
        raise ValueError('Excessive recipe metadata references')
    text = recipe.read_text()
    names = set(re.findall(r'^([A-Za-z_][A-Za-z_0-9]*)=', text, re.M))
    values = {name: assignment(text, name) for name in names}
    # A narrow data-only equivalent of ncurses' explicit metadata references.
    # No shell is invoked; every referenced file remains in the pinned source tree.
    pattern = re.compile(r'^\$\(\. \$TERMUX_SCRIPTDIR/((?:x11-)?packages/[a-z0-9+_.-]+/build\.sh); echo \$(TERMUX_PKG_(?:VERSION|SRCURL|SHA256))\)$')
    for name, items in values.items():
        for index, value in enumerate(items):
            match = pattern.fullmatch(value)
            if not match:
                continue
            reference = recipe.parents[2] / match[1]
            inherited = recipe_values(reference, depth + 1)
            candidates = inherited.get(match[2], [])
            if candidates:
                items[index] = expand(candidates[0], inherited)
    return values


def recipe_sources(recipe):
    text = recipe.read_text()
    values = recipe_values(recipe)
    declared = values.get('TERMUX_PKG_LICENSE', [])
    sources, problems = [], []
    urls, hashes = values.get('TERMUX_PKG_SRCURL', []), values.get('TERMUX_PKG_SHA256', [])
    if not urls:
        if 'TERMUX_PKG_SKIP_SRC_EXTRACT=true' not in text:
            problems.append('No source URL or reviewed in-recipe source declaration')
    elif len(urls) != len(hashes):
        problems.append('Source URL/checksum count differs')
    else:
        for raw, checksum in zip(urls, hashes):
            try:
                url = expand(raw, values)
                if not re.fullmatch('[a-f0-9]{64}', checksum):
                    raise ValueError('Unpinned source checksum; capture the exact source commit used by the binary build')
                if url.startswith('http://'):
                    url = 'https://' + url[7:]
                sources.append({'url': url, 'sha256': checksum, 'evidence': 'pinned Termux recipe'})
            except ValueError as exc:
                problems.append(str(exc))
    # GNU bash/readline apply a separately pinned patch series in the recipe.
    if recipe.parent.name in {'bash', 'readline'}:
        version = values['TERMUX_PKG_VERSION'][0]
        base, count = version.rsplit('.', 1)
        patches = dict(re.findall(r'PATCH_CHECKSUMS\[([0-9]{3})\]=([a-f0-9]{64})', text))
        for n in range(1, int(count) + 1):
            key = f'{n:03d}'
            if key not in patches:
                problems.append('Missing pinned GNU patch ' + key)
                continue
            name = recipe.parent.name
            sources.append({'url': f'https://mirrors.kernel.org/gnu/{name}/{name}-{base}-patches/{name}{base.replace(".", "")}-{key}',
                            'sha256': patches[key], 'evidence': 'pinned GNU patch series in Termux recipe'})
    return ', '.join(declared) or None, sources, sorted(set(problems))


def host_records(root, packages):
    base = root / 'upstream/termux-packages/packages'
    result = []
    for package in packages:
        name = package['Package']
        recipe = base / name / 'build.sh'
        if not recipe.exists():
            parents = list(base.glob('*/' + name + '.subpackage.sh'))
            recipe = parents[0].parent / 'build.sh' if len(parents) == 1 else None
        record = {'id': 'host:' + name, 'name': name, 'version': package['Version'], 'scope': 'bundled-host',
                  'sourceFiles': [], 'unresolved': []}
        if recipe is None or not recipe.is_file():
            record['unresolved'].append('No unique recipe for installed package')
        else:
            license_name, files, errors = recipe_sources(recipe)
            record.update(sourceName=recipe.parent.name, licenseDeclared=license_name,
                          recipe=recipe.relative_to(root).as_posix(), recipeSha256=sha256(recipe), sourceFiles=files)
            record['unresolved'].extend(errors)
            # Match installed version to the immutable recipe, not just its directory name.
            source_version = assignment(recipe.read_text(), 'TERMUX_PKG_VERSION')
            revision = assignment(recipe.read_text(), 'TERMUX_PKG_REVISION')
            expected = source_version[0] + ('-' + revision[0] if revision else '') if source_version else None
            if expected != package['Version']:
                record['unresolved'].append('Installed version differs from recipe version: ' + str(expected))
            if not license_name:
                record['unresolved'].append('Recipe has no license declaration')
        result.append(record)
    return result


def read_index(path):
    data = Path(path).read_bytes()
    if str(path).endswith('.xz'):
        data = lzma.decompress(data, memlimit=128 * 1024 * 1024)
    elif str(path).endswith('.gz'):
        data = gzip.decompress(data)
    if len(data) > 256 * 1024 * 1024:
        raise ValueError('Ubuntu source index exceeds limit')
    return deb822(data.decode())


def source_notices(path):
    """Read bounded license members without extracting any archive entry."""
    found = []
    pattern = re.compile(r'(^|/)(copying|copyright|license|licence|notice)([._-]|$)', re.I)
    total = 0
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if not member.is_dir() and pattern.search(member.filename) and member.file_size <= 1024 * 1024:
                        total += member.file_size
                        if total > 16 * 1024 * 1024:
                            break
                        found.append((member.filename, archive.read(member)))
        elif tarfile.is_tarfile(path):
            with tarfile.open(path) as archive:
                for member in archive:
                    if member.isfile() and pattern.search(member.name) and member.size <= 1024 * 1024:
                        total += member.size
                        if total > 16 * 1024 * 1024:
                            break
                        found.append((member.name, archive.extractfile(member).read()))
    except (tarfile.TarError, zipfile.BadZipFile, EOFError):
        return []
    return found


def ubuntu_records(packages, indexes):
    lookup = {}
    for path, url in indexes:
        for item in read_index(path):
            key = (item.get('Package'), item.get('Version'))
            lookup[key] = (item, url, sha256(path))
    result = []
    for package in packages:
        name, version = source_id(package)
        record = {'id': 'guest:' + package['Package'], 'name': package['Package'], 'version': package['Version'],
                  'sourceName': name, 'sourceVersion': version, 'scope': 'bundled-guest',
                  'licenseDeclared': 'See preserved package copyright and common license texts',
                  'sourceFiles': [], 'unresolved': []}
        found = lookup.get((name, version))
        if found is None:
            record['unresolved'].append('Exact Ubuntu source version not present in supplied indexes')
        else:
            item, index_url, index_sha = found
            record['sourceIndex'] = {'url': index_url, 'sha256': index_sha, 'signatureVerified': False}
            source_base = (index_url.split('/dists/', 1)[0] + '/'
                           if index_url.startswith('https://snapshot.ubuntu.com/ubuntu/')
                           else 'https://ports.ubuntu.com/ubuntu-ports/')
            directory = item.get('Directory', '')
            if not directory.startswith('pool/') or '..' in directory.split('/'):
                raise ValueError('Invalid Ubuntu source directory')
            for line in item.get('Checksums-Sha256', '').splitlines():
                if not line.strip():
                    continue
                digest, size, filename = line.split()
                if not re.fullmatch('[a-f0-9]{64}', digest) or '/' in filename or filename in {'.', '..'}:
                    raise ValueError('Invalid source checksum table')
                record['sourceFiles'].append({'url': source_base + directory + '/' + urllib.parse.quote(filename),
                    'sha256': digest, 'bytes': int(size), 'evidence': 'exact source package/version from Ubuntu Sources index'})
            if not record['sourceFiles']:
                record['unresolved'].append('Source index lacks SHA-256 payload table')
        result.append(record)
    return result


def preserve_runtime_inputs(root, out, provenance, extra_scripts):
    """Copy only the provenance's hash-identified source overlays, never a cache tree."""
    records, problems = [], []
    fingerprint = provenance.get('recipeFingerprint', '')
    if not re.fullmatch('[a-f0-9]{64}', fingerprint):
        raise ValueError('Invalid runtime recipe fingerprint')
    tree = root / '.local/runtime' / fingerprint[:20] / 'termux-packages'
    if not provenance.get('sourceOverlaySha256'):
        problems.append('Runtime provenance lacks effective source-overlay hashes')
    for name, expected in provenance.get('sourceOverlaySha256', {}).items():
        name = safe_relative(name)
        if secret_path(name):
            raise ValueError('Runtime build input has a forbidden credential filename')
        path = tree / name
        if not path.is_file() or path.is_symlink() or sha256(path) != expected:
            problems.append('Missing exact effective runtime build input: ' + name)
            continue
        relative = 'build-inputs/' + fingerprint + '/termux-packages/' + name
        atomic_write(out / relative, path.read_bytes())
        records.append({'path': relative, 'sha256': expected, 'originalPath': name,
                        'recipeFingerprint': fingerprint})
    expected = provenance.get('packagingScriptSha256')
    scripts = [root / 'tools/prepare-runtime.py'] + list(extra_scripts)
    matching = [p for p in scripts if p.is_file() and not p.is_symlink() and sha256(p) == expected]
    if matching:
        relative = 'build-inputs/' + fingerprint + '/prepare-runtime.py'
        atomic_write(out / relative, matching[0].read_bytes())
        records.append({'path': relative, 'sha256': expected, 'originalPath': 'tools/prepare-runtime.py',
                        'recipeFingerprint': fingerprint})
    else:
        problems.append('Missing exact runtime packaging script: ' + str(expected))
    return records, problems


def collect(args):
    root, out = args.root.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    records, inputs, notices, build_inputs, build_problems = [], {}, {}, [], []
    if args.runtime_manifest:
        path, data = checked_asset(args.runtime_manifest)
        if data['termuxPackagesCommit'] != read_json(root / 'tools/sources.lock.json')['termuxPackages']['commit']:
            raise ValueError('Runtime source commit mismatch')
        packages, texts = archive_inventory(path)
        records += host_records(root, packages)
        notices.update({'host/' + name: text for name, text in texts.items()})
        inputs['runtimeArchiveSha256'] = sha256(path)
        inputs['runtimeManifestSha256'] = sha256(args.runtime_manifest)
        provenance_path = args.runtime_manifest.parent / 'provenance.json'
        if provenance_path.is_file():
            provenance = read_json(provenance_path)
            if provenance.get('archiveSha256') != inputs['runtimeArchiveSha256'] or provenance.get('sourceLock') != read_json(root / 'tools/sources.lock.json'):
                raise ValueError('Runtime provenance does not match selected source inputs')
            inputs['runtimeProvenance'] = {k: provenance[k] for k in ('recipeFingerprint', 'builder', 'sourceOverlaySha256', 'packagingScriptSha256', 'verifiedDependencySeed') if k in provenance}
            # Do not copy arbitrary command/environment strings or builder credentials.
            files, errors = preserve_runtime_inputs(root, out, provenance, getattr(args, 'historical_packaging_script', []))
            build_inputs += files
            build_problems += errors
            seed = provenance.get('verifiedDependencySeed')
            if seed:
                old_sha = seed['sourceRuntimeSha256']
                old_path = root / 'artifacts/runtime' / ('core-' + old_sha[:16]) / 'provenance.json'
                if old_path.is_file():
                    previous = read_json(old_path)
                    if previous['archiveSha256'] != old_sha or previous['recipeFingerprint'] != seed['sourceRecipeFingerprint']:
                        raise ValueError('Dependency seed runtime provenance differs')
                    files, errors = preserve_runtime_inputs(root, out, previous, getattr(args, 'historical_packaging_script', []))
                    build_inputs += files
                    build_problems += errors
                else:
                    build_problems.append('Original dependency-seed runtime provenance unavailable')
        else:
            inputs['runtimeProvenanceMissing'] = True
    if args.guest_manifest:
        path, data = checked_asset(args.guest_manifest, hash_key='archiveSha256')
        packages, texts = archive_inventory(path)
        notices.update({'guest/' + name: text for name, text in texts.items()})
        indexes = [(p, 'provided-local-source-index') for p in args.ubuntu_index]
        for suite in ('noble', 'noble-updates', 'noble-security'):
            url = f'https://ports.ubuntu.com/ubuntu-ports/dists/{suite}/main/source/Sources.xz'
            target = out / 'indexes' / (suite + '-main-Sources.xz')
            try:
                if args.fetch:
                    download(url, target, limit=64 * 1024 * 1024)
                if target.is_file():
                    indexes.append((target, url))
            except Exception as exc:
                inputs.setdefault('indexErrors', []).append({'url': url, 'error': type(exc).__name__ + ': ' + str(exc)[:300]})
        for stamp in getattr(args, 'ubuntu_snapshot', []):
            if not re.fullmatch(r'\d{8}T\d{6}Z', stamp):
                raise ValueError('Ubuntu snapshot must be YYYYMMDDTHHMMSSZ')
            for suite in ('noble', 'noble-updates', 'noble-security'):
                url = f'https://snapshot.ubuntu.com/ubuntu/{stamp}/dists/{suite}/main/source/Sources.xz'
                target = out / 'indexes' / (stamp + '-' + suite + '-main-Sources.xz')
                try:
                    if args.fetch and not target.is_file():
                        download(url, target, limit=64 * 1024 * 1024)
                    if target.is_file():
                        indexes.append((target, url))
                except Exception as exc:
                    inputs.setdefault('indexErrors', []).append({'url': url, 'error': type(exc).__name__ + ': ' + str(exc)[:300]})
        records += ubuntu_records(packages, indexes)
        inputs['guestArchiveSha256'] = sha256(path)
        inputs['guestManifestSha256'] = sha256(args.guest_manifest)
    if not records:
        raise ValueError('Select at least one shipped runtime/guest manifest')
    if getattr(args, 'retained_git_sources', None):
        capture = read_json(args.retained_git_sources)
        seed = inputs.get('runtimeProvenance', {}).get('verifiedDependencySeed', {})
        capture_sha = capture.get('runtimeArchiveSha256')
        if capture_sha != inputs.get('runtimeArchiveSha256') and capture_sha != seed.get('sourceRuntimeSha256'):
            raise ValueError('Retained source capture belongs to a different runtime archive')
        inputs['retainedGitSourcesSha256'] = sha256(args.retained_git_sources)
        by_id = {x['id']: x for x in records}
        for item in capture['components']:
            component = by_id.get(item['id'])
            if (component is None or item.get('recipeSha256') != component.get('recipeSha256')
                    or item.get('version') != component['version']
                    or not re.fullmatch('[a-f0-9]{40}', item.get('sourceCommit', ''))):
                raise ValueError('Retained Git source identity does not match shipped package')
            if capture_sha != inputs.get('runtimeArchiveSha256'):
                expected_name = component['name'] + '_' + component['version'] + '_'
                if not any(p['archive'].startswith(expected_name) for p in seed.get('packages', [])):
                    raise ValueError('Retained source is not linked to a verified dependency-seed package')
            relative_archive = safe_relative(item['archive'])
            path = args.retained_git_sources.parent / relative_archive
            if not re.fullmatch('[a-f0-9]{64}', item.get('sha256', '')) or path.is_symlink() or sha256(path) != item['sha256']:
                raise ValueError('Retained Git source archive checksum mismatch')
            relative = 'downloads/' + item['sha256'] + '/' + Path(item['archive']).name
            atomic_write(out / relative, path.read_bytes())
            component['sourceCommit'] = item['sourceCommit']
            component['sourceCapture'] = item['captureMethod']
            component['sourceFiles'].append({'url': item['upstreamSourceUrl'], 'sha256': item['sha256'],
                'fileName': Path(item['archive']).name, 'downloadAllowed': False,
                'evidence': 'exact Git tree exported from retained binary-build cache; archive serialization retained locally'})
            component['unresolved'] = [x for x in component['unresolved'] if not x.startswith('Unpinned source checksum;')]
    # Preserve actual installed copyright/license files verbatim as evidence.
    for name, text in notices.items():
        atomic_write(out / 'installed-notices' / name, text)
    unique = {}
    for record in records:
        for source in record['sourceFiles']:
            suffix = source.get('fileName') or Path(urllib.parse.urlsplit(source['url']).path).name or 'source'
            source['path'] = 'downloads/' + source['sha256'] + '/' + safe_relative(suffix)
            # Different mirror URLs can name the same bytes differently. Verify
            # one canonical local payload and reference that actual path everywhere.
            canonical = unique.setdefault(source['sha256'], source)
            source['path'] = canonical['path']
    def obtain(source):
        path = out / source['path']
        try:
            if args.fetch and source.get('downloadAllowed', True):
                download(source['url'], path, source['sha256'])
            if path.is_file() and not path.is_symlink() and sha256(path) == source['sha256']:
                return source['sha256'], {'status': 'VERIFIED', 'bytes': path.stat().st_size}
            return source['sha256'], {'status': 'MISSING'}
        except Exception as exc:
            return source['sha256'], {'status': 'MISSING', 'error': type(exc).__name__ + ': ' + str(exc)[:300]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = dict(pool.map(obtain, unique.values()))
    source_notice_records = []
    for digest, source in unique.items():
        if results[digest]['status'] != 'VERIFIED':
            continue
        for index, (member, content) in enumerate(source_notices(out / source['path'])):
            relative = f'source-notices/{digest}/{index:04d}.txt'
            atomic_write(out / relative, content)
            source_notice_records.append({'path': relative, 'sourceSha256': digest, 'member': member,
                                          'sha256': sha256(out / relative)})
    for record in records:
        for source in record['sourceFiles']:
            source.update(results[source['sha256']])
            if source['status'] != 'VERIFIED':
                record['unresolved'].append('Missing source payload: ' + source['url'])
        # The conservative collector does not claim a legal completeness review of dynamic
        # build-time fetches, implicit static dependencies, or custom/copyleft notices.
    unresolved = [issue('PACKAGE_SOURCE', p['id'], error) for p in records for error in p['unresolved']]
    if inputs.get('runtimeProvenanceMissing'):
        unresolved.append(issue('RUNTIME_BUILD_INPUTS_UNRESOLVED', 'host', 'Restore exact binary-build recipe/provenance before claiming source correspondence'))
    unresolved += [issue('RUNTIME_BUILD_INPUTS_UNRESOLVED', 'host', message) for message in build_problems]
    evidence = {'schemaVersion': 1, 'kind': 'z8-package-source-inventory', 'inputs': inputs,
                'components': records, 'installedNotices': [{'path': 'installed-notices/' + n, 'sha256': sha256(out / 'installed-notices' / n)} for n in sorted(notices)],
                'sourceNotices': source_notice_records, 'buildInputs': build_inputs,
                'unresolved': unresolved, 'status': 'INCOMPLETE' if unresolved else 'COLLECTED',
                'legalCompletenessReviewed': False,
                'notes': ['COLLECTED means matching payloads were acquired, not legal approval.',
                    'Recipes, all local patches and build scripts are included separately in the application source archive.',
                    'Runtime package closure, static-linked components and additional custom recipe fetches require release review.',
                    'Official tools downloaded independently by users are not represented as APK-bundled binaries.']}
    atomic_write(out / 'package-sources.json', json_bytes(evidence))
    return evidence


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--runtime-manifest', type=Path)
    p.add_argument('--guest-manifest', type=Path)
    p.add_argument('--ubuntu-index', type=Path, action='append', default=[])
    p.add_argument('--ubuntu-snapshot', action='append', default=[], help='Official Ubuntu archive snapshot YYYYMMDDTHHMMSSZ; preserves exact historical source payloads')
    p.add_argument('--retained-git-sources', type=Path, help='Exact source-tree capture manifest tied to the selected runtime binary')
    p.add_argument('--historical-packaging-script', type=Path, action='append', default=[], help='Preserved original prepare-runtime.py; accepted only when its SHA matches binary-build provenance')
    p.add_argument('--fetch', action='store_true')
    p.add_argument('--allow-incomplete', action='store_true')
    args = p.parse_args()
    result = collect(args)
    print(json_bytes({'status': result['status'], 'components': len(result['components']), 'unresolvedCount': len(result['unresolved'])}).decode(), end='')
    return 0 if args.allow_incomplete or not result['unresolved'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
