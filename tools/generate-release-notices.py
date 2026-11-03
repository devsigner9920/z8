#!/usr/bin/env python3
"""Generate offline notices from the actual release inputs. Unknowns block strict mode."""
import argparse
import io
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile
from release_compliance import ROOT, atomic_write, bytes_sha, issue, json_bytes, read_json, sha256, maven_source_inventory, historical_guest_inventory
from release_compliance import HISTORICAL_GUEST_ARCHIVES_REQUIRING_SOURCES


def pom_licenses(path, cache=None, visited=None):
    visited = set() if visited is None else visited
    if path in visited:
        return []
    visited.add(path)
    tree = ET.fromstring(path.read_bytes())
    # Namespace-insensitive lookup without changing the original POM evidence.
    for item in tree.iter():
        item.tag = item.tag.rsplit('}', 1)[-1]
    found = [{'name': x.findtext('name', '').strip(), 'url': x.findtext('url', '').strip()}
             for x in tree.findall('./licenses/license')]
    if found:
        return found
    parent = tree.find('parent')
    if parent is not None and cache is not None:
        group, name, version = (parent.findtext(x, '') for x in ('groupId', 'artifactId', 'version'))
        candidates = list((cache / group / name / version).glob('*/*.pom'))
        if len(candidates) == 1:
            return pom_licenses(candidates[0], cache, visited)
    return []


def preserved_pom_licenses(component, directory):
    """Read the verified child-first POM chain, not its summarized license label."""
    records = component['metadataFiles']
    child_sha = records[0]['sha256'] if records else None
    for record in records:
        found = pom_licenses(directory / record['path'])
        if found:
            return found, child_sha
    return [], child_sha


def embedded_notices(path):
    result = []
    def visit(data, prefix='', nested=False):
        with zipfile.ZipFile(data) as z:
            for info in z.infolist():
                name = info.filename
                if info.is_dir() or info.file_size > 2 * 1024 * 1024:
                    continue
                if re.search(r'(^|/)(license|licence|notice|copying|copyright)([._-]|$)', name, re.I):
                    result.append((prefix + name, z.read(info).decode('utf-8', errors='replace')))
                elif name == 'classes.jar' and not nested:
                    visit(io.BytesIO(z.read(info)), prefix + 'classes.jar/', True)
    try:
        visit(path)
    except zipfile.BadZipFile:
        pass
    return result


def generate(args):
    root = args.root.resolve()
    sections, components, unresolved = [], [], []
    inputs = {'sourceLockSha256': sha256(root / 'tools/sources.lock.json')}
    notice_names = ['LICENSE', 'THIRD_PARTY_NOTICES.md', 'upstream/termux-app/LICENSE.md',
                 'upstream/termux-app/termux-shared/LICENSE.md',
                 'overlay/app/src/main/assets/z8-licenses/material-icons.md']
    notice_names += [p.relative_to(root).as_posix() for p in sorted((root / 'LICENSES').glob('*'))
                     if p.is_file() and not p.is_symlink()]
    for name in notice_names:
        path = root / name
        if not path.is_file():
            unresolved.append(issue('NOTICE_MISSING', name, 'Required source notice missing'))
            continue
        sections.append((name, path.read_text()))
    if args.source_manifest:
        source = read_json(args.source_manifest)
        inputs['sourceInputSha256'] = source['sourceInputSha256']
    else:
        unresolved.append(issue('SOURCE_SNAPSHOT_MISSING', 'application', 'Generate and supply the release source manifest'))
    if args.package_sources:
        packages = read_json(args.package_sources)
        inputs['packageSourcesSha256'] = sha256(args.package_sources)
        inputs.update(packages['inputs'])
        components += packages['components']
        unresolved += packages['unresolved']
        package_root = args.package_sources.parent
        for record in packages['installedNotices'] + packages.get('sourceNotices', []):
            path = package_root / record['path']
            if not path.is_file() or path.is_symlink() or sha256(path) != record['sha256']:
                raise ValueError('Installed license evidence changed')
            sections.append((record.get('member', record['path']), path.read_text(errors='replace')))
        if not any(name == 'LICENSE' or 'common-licenses/GPL-3' in name for name, _ in sections):
            unresolved.append(issue('GPL_TEXT_MISSING', 'application', 'Include the full GPLv3 license text with this release'))
    else:
        unresolved.append(issue('PACKAGE_INVENTORY_MISSING', 'bundled-runtime', 'Supply shipped package inventory and preserved notices'))
    maven = None
    maven_components = {}
    if getattr(args, 'maven_sources', None):
        maven = maven_source_inventory(args.maven_sources, args.gradle_artifacts)
        inputs['mavenSourcesSha256'] = sha256(args.maven_sources)
        unresolved += maven.get('unresolved', [])
        maven_components = {':'.join(component[key] for key in ('group', 'name', 'version')): component
                            for component in maven['components']}
    if args.gradle_artifacts:
        evidence = read_json(args.gradle_artifacts)
        if evidence.get('kind') != 'z8-gradle-runtime-artifacts' or evidence.get('configuration') != 'releaseRuntimeClasspath':
            raise ValueError('Expected resolved releaseRuntimeClasspath evidence')
        inputs['gradleArtifactsSha256'] = sha256(args.gradle_artifacts)
        cache = args.gradle_cache
        project_roots = [(root / '.local' / name).resolve() for name in ('build-src', 'build-candidate')]
        for item in evidence['components']:
            coordinate = ':'.join(item[x] for x in ('group', 'name', 'version'))
            path = Path(item['file'])
            if not path.is_absolute():
                path = root / path
            if not path.is_file() or path.is_symlink() or sha256(path) != item['sha256']:
                raise ValueError('Resolved dependency artifact changed: ' + coordinate)
            # Project modules are already included in the full modified application source.
            if any(path.resolve().is_relative_to(project_root) for project_root in project_roots):
                components.append(dict(id='project:' + coordinate, name=coordinate, version=item['version'],
                    scope='application-project-module', licenseDeclared='See Termux module/per-file notices', artifactSha256=item['sha256']))
                continue
            if maven is not None:
                licenses, child_pom_sha = preserved_pom_licenses(maven_components[coordinate], args.maven_sources.parent)
            else:
                candidates = list((cache / item['group'] / item['name'] / item['version']).glob('*/*.pom'))
                licenses = pom_licenses(candidates[0], cache) if len(candidates) == 1 else []
                child_pom_sha = sha256(candidates[0]) if len(candidates) == 1 else None
            component = {'id': 'maven:' + coordinate, 'name': coordinate, 'version': item['version'],
                         'scope': 'bundled-maven', 'artifactSha256': item['sha256'], 'licenses': licenses}
            if not licenses or any(not x['name'] for x in licenses):
                unresolved.append(issue('LICENSE_UNRESOLVED', coordinate, 'No unambiguous license declaration in artifact/POM hierarchy'))
            if child_pom_sha:
                component['pomSha256'] = child_pom_sha
            components.append(component)
            sections.append((coordinate, '\n'.join(x['name'] + ' — ' + x['url'] for x in licenses) or 'LICENSE REQUIRES REVIEW'))
            sections.extend((coordinate + '/' + name, text) for name, text in embedded_notices(path))
    else:
        unresolved.append(issue('GRADLE_INVENTORY_MISSING', 'application', 'Resolve releaseRuntimeClasspath with release-license.init.gradle'))
    if maven is None and any(c.get('scope') == 'bundled-maven' for c in components):
        unresolved.append(issue('MAVEN_SOURCES_MISSING', 'application', 'Collect and publish sources for the actual bundled runtime libraries; POM license labels alone do not establish source closure'))
    if getattr(args, 'historical_guest_inputs', None):
        historical = historical_guest_inventory(args.historical_guest_inputs, root)
        inputs['historicalGuestInputsSha256'] = sha256(args.historical_guest_inputs)
        if (historical['guestArchiveSha256'] != inputs.get('guestArchiveSha256')
                or historical['guestManifestSha256'] != inputs.get('guestManifestSha256')):
            unresolved.append(issue('HISTORICAL_GUEST_MISMATCH', 'guest', 'Managed script sources describe another bundled guest'))
    elif inputs.get('guestArchiveSha256') in HISTORICAL_GUEST_ARCHIVES_REQUIRING_SOURCES:
        unresolved.append(issue('HISTORICAL_GUEST_INPUTS_REQUIRED', 'guest', 'This known guest archive requires its retained managed-source inventory'))
    # Metadata discovery is not a substitute for review of source/header notices and copyleft scope.
    review_required = issue('RELEASE_LICENSE_REVIEW_REQUIRED', 'release',
        'A reviewer must confirm notice completeness, package source closure and any per-file/copyleft exceptions for these exact hashes')
    review = read_json(args.review) if getattr(args, 'review', None) else None
    if not (review and review.get('schemaVersion') == 1 and review.get('noticesInputs') == inputs
            and str(review.get('reviewedBy', '')).strip() and re.fullmatch(r'\d{4}-\d{2}-\d{2}', review.get('reviewedAt', ''))
            and review.get('sourceClosureReviewed') is True and review.get('noticeCompletenessReviewed') is True):
        unresolved.append(review_required)
    header = ('Z8 Open-Source and Third-Party Notices\n\n'
              'Z8 is a modified version of the GPL-3.0-only Termux app, with module- and file-specific exceptions.\n'
              'The notices below identify original copyrights, licenses and changes. Use the source link in the app to obtain source code.\n'
              'Z8 copyright notices do not restrict the rights granted by the GPL or individual component licenses.\n'
              'Original notices for included packages and runtime dependency metadata are preserved below.\n')
    if unresolved:
        header += ('\nRelease candidate notice: some corresponding-source or license review remains incomplete. '
                   'Generating this document alone does not establish compliance with public distribution requirements.\n')
    text = header + '\n'.join('\n' + '=' * 72 + '\n' + name + '\n\n' + content for name, content in sections)
    data = text.encode()
    report = {'schemaVersion': 1, 'kind': 'z8-release-notices', 'status': 'INCOMPLETE' if unresolved else 'READY',
              'inputs': inputs, 'noticeSha256': bytes_sha(data), 'components': components, 'unresolved': unresolved}
    if review:
        report['reviewEvidenceSha256'] = sha256(args.review)
    args.output.mkdir(parents=True, exist_ok=True)
    atomic_write(args.output / 'third-party-notices.txt', data)
    atomic_write(args.output / 'release-notices.json', json_bytes(report))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--output', type=Path, default=ROOT / 'overlay/app/src/main/assets/z8-licenses')
    p.add_argument('--source-manifest', type=Path)
    p.add_argument('--package-sources', type=Path)
    p.add_argument('--gradle-artifacts', type=Path)
    p.add_argument('--maven-sources', type=Path)
    p.add_argument('--historical-guest-inputs', type=Path)
    p.add_argument('--review', type=Path, help='Maintainer review of exact input hashes; never generated automatically')
    p.add_argument('--gradle-cache', type=Path, default=ROOT / '.local/gradle/caches/modules-2/files-2.1')
    p.add_argument('--allow-incomplete', action='store_true')
    args = p.parse_args()
    result = generate(args)
    print(json_bytes({'status': result['status'], 'components': len(result['components']), 'unresolvedCount': len(result['unresolved'])}).decode(), end='')
    return 0 if args.allow_incomplete or not result['unresolved'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
