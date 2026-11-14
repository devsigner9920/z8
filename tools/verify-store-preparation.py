#!/usr/bin/env python3
"""Check local release metadata and store text without publishing or approving a release."""
import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import sys
from urllib.parse import urljoin, urlsplit

from release_config import load


ROOT = Path(__file__).resolve().parent.parent
LOCALES = ('en-US', 'ko-KR')
TEXT_LIMITS = {
    'title.txt': 30,
    'short-description.txt': 80,
    'full-description.txt': 4000,
    'release-notes.txt': 500,
}


class PolicyMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonical = []
        self.dates = []
        self.text = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical.append(attrs.get('href'))
        if tag == 'time' and 'datetime' in attrs:
            self.dates.append(attrs['datetime'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])

    def handle_data(self, data):
        self.text.append(data)


def verify(root=ROOT, tag=None):
    root = Path(root)
    config = load(root / 'release/config.json', production=True)
    expected_tag = 'v' + config['versionName']
    source = urlsplit(config['sourceUrl'])
    source_parts = source.path.strip('/').split('/')
    if (source.hostname != 'github.com' or source.query or source.fragment
            or len(source_parts) != 6
            or source_parts[2:] != ['releases', 'download', expected_tag, 'z8-source.zip']):
        raise ValueError('The GitHub source asset URL must match the configured release version.')
    if tag is not None and tag != expected_tag:
        raise ValueError('The release tag does not match release/config.json.')

    homepage = PolicyMetadata()
    homepage.feed((root / 'docs/index.html').read_text(encoding='utf-8'))
    if config['sourceUrl'] not in homepage.links:
        raise ValueError('The website must link to this version\'s corresponding source archive.')

    for name in ('privacy.html', 'privacy.ko.html'):
        policy = PolicyMetadata()
        policy.feed((root / 'docs' / name).read_text(encoding='utf-8'))
        text = ''.join(policy.text)
        if (config['developerName'] not in text or config['supportEmail'] not in text
                or policy.dates != [config['policyDate']]):
            raise ValueError('Release contact or effective date differs from ' + name)
        expected_url = config['privacyUrl'] if name == 'privacy.html' else urljoin(config['privacyUrl'], name)
        if policy.canonical != [expected_url]:
            raise ValueError('The canonical privacy URL differs from release configuration: ' + name)

    counts = {}
    for locale in LOCALES:
        counts[locale] = {}
        for name, limit in TEXT_LIMITS.items():
            value = (root / 'docs/store' / locale / name).read_text(encoding='utf-8').rstrip('\n')
            if not value or value != value.strip():
                raise ValueError('Store text is empty or has surrounding whitespace: ' + locale + '/' + name)
            if len(value) > limit:
                raise ValueError('Store text exceeds its character limit: ' + locale + '/' + name)
            if name in ('title.txt', 'short-description.txt') and '\n' in value:
                raise ValueError('Store title and short description must be single-line text.')
            if name == 'full-description.txt' and config['sourceUrl'] not in value.split():
                raise ValueError('Store listing must identify this version\'s corresponding source archive: ' + locale)
            counts[locale][name] = {'characters': len(value), 'limit': limit}

    return {
        'status': 'PASS',
        'scope': 'Local metadata consistency and store text limits only',
        'versionCode': config['versionCode'],
        'versionName': config['versionName'],
        'releaseTag': expected_tag,
        'storeText': counts,
        'limitations': [
            'Does not check public source downloads, screenshots, or signed release artifacts.',
            'Does not establish policy compliance, completed device QA, or permission to publish binaries.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--tag', help='Check an intended release tag against the configured version.')
    args = parser.parse_args()
    tag = args.tag
    ref_name = os.environ.get('GITHUB_REF_NAME', '')
    if tag is None and os.environ.get('GITHUB_REF_TYPE') == 'tag' and ref_name.startswith('v'):
        tag = ref_name
    try:
        result = verify(args.root, tag)
    except (ValueError, OSError) as error:
        print('ERROR:', error, file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
