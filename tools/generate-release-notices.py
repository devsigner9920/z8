#!/usr/bin/env python3
"""Generate offline notices from the actual release inputs. Unknowns block strict mode."""
import argparse
import io
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile
from release_compliance import ROOT, atomic_write, bytes_sha, issue, json_bytes, read_json, sha256


def pom_licenses(path, cache, visited=None):
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
    if parent is not None:
        group, name, version = (parent.findtext(x, '') for x in ('groupId', 'artifactId', 'version'))
        candidates = list((cache / group / name / version).glob('*/*.pom'))
        if len(candidates) == 1:
            return pom_licenses(candidates[0], cache, visited)
    return []


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
    if args.gradle_artifacts:
        evidence = read_json(args.gradle_artifacts)
        if evidence.get('kind') != 'z8-gradle-runtime-artifacts' or evidence.get('configuration') != 'releaseRuntimeClasspath':
            raise ValueError('Expected resolved releaseRuntimeClasspath evidence')
        inputs['gradleArtifactsSha256'] = sha256(args.gradle_artifacts)
        cache = args.gradle_cache
        for item in evidence['components']:
            coordinate = ':'.join(item[x] for x in ('group', 'name', 'version'))
            path = Path(item['file'])
            if not path.is_file() or path.is_symlink() or sha256(path) != item['sha256']:
                raise ValueError('Resolved dependency artifact changed: ' + coordinate)
            # Project modules are already included in the full modified application source.
            if path.resolve().is_relative_to((root / '.local/build-src').resolve()):
                components.append(dict(id='project:' + coordinate, name=coordinate, version=item['version'],
                    scope='application-project-module', licenseDeclared='See Termux module/per-file notices', artifactSha256=item['sha256']))
                continue
            candidates = list((cache / item['group'] / item['name'] / item['version']).glob('*/*.pom'))
            licenses = pom_licenses(candidates[0], cache) if len(candidates) == 1 else []
            component = {'id': 'maven:' + coordinate, 'name': coordinate, 'version': item['version'],
                         'scope': 'bundled-maven', 'artifactSha256': item['sha256'], 'licenses': licenses}
            if not licenses or any(not x['name'] for x in licenses):
                unresolved.append(issue('LICENSE_UNRESOLVED', coordinate, 'No unambiguous license declaration in artifact/POM hierarchy'))
            if candidates:
                component['pomSha256'] = sha256(candidates[0])
            components.append(component)
            sections.append((coordinate, '\n'.join(x['name'] + ' — ' + x['url'] for x in licenses) or 'LICENSE REQUIRES REVIEW'))
            sections.extend((coordinate + '/' + name, text) for name, text in embedded_notices(path))
    else:
        unresolved.append(issue('GRADLE_INVENTORY_MISSING', 'application', 'Resolve releaseRuntimeClasspath with release-license.init.gradle'))
    # Metadata discovery is not a substitute for review of source/header notices and copyleft scope.
    review_required = issue('RELEASE_LICENSE_REVIEW_REQUIRED', 'release',
        'A reviewer must confirm notice completeness, package source closure and any per-file/copyleft exceptions for these exact hashes')
    review = read_json(args.review) if getattr(args, 'review', None) else None
    if not (review and review.get('schemaVersion') == 1 and review.get('noticesInputs') == inputs
            and str(review.get('reviewedBy', '')).strip() and re.fullmatch(r'\d{4}-\d{2}-\d{2}', review.get('reviewedAt', ''))
            and review.get('sourceClosureReviewed') is True and review.get('noticeCompletenessReviewed') is True):
        unresolved.append(review_required)
    header = ('Z8 오픈소스 및 제3자 고지\n\n'
              'Z8는 GPL-3.0-only 기반 Termux 앱의 수정 버전이며 모듈/파일별 예외가 있습니다.\n'
              '원저작자의 저작권·라이선스와 변경사항은 아래 고지를 참조하세요. 소스 제공 위치는 앱의 소스 링크에 표시합니다.\n'
              'Z8 자체 저작권 고지는 사용자에게 GPL 및 각 구성요소 라이선스가 부여한 권리를 제한하지 않습니다.\n'
              '아래에는 실제 포함 패키지의 원문과 런타임 의존성 메타데이터가 보존됩니다.\n')
    if unresolved:
        header += ('\n출시 후보 고지: 일부 대응 소스 또는 라이선스 검토가 미완료입니다. '
                   '이 문서 생성만으로 공개 배포 요건 충족을 확인한 것은 아닙니다.\n')
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
    p.add_argument('--review', type=Path, help='Maintainer review of exact input hashes; never generated automatically')
    p.add_argument('--gradle-cache', type=Path, default=ROOT / '.local/gradle/caches/modules-2/files-2.1')
    p.add_argument('--allow-incomplete', action='store_true')
    args = p.parse_args()
    result = generate(args)
    print(json_bytes({'status': result['status'], 'components': len(result['components']), 'unresolvedCount': len(result['unresolved'])}).decode(), end='')
    return 0 if args.allow_incomplete or not result['unresolved'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
