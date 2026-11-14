"""Guard release tag and published-policy consistency before source publication."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('store_preparation', ROOT / 'tools/verify-store-preparation.py')
store = importlib.util.module_from_spec(SPEC)
with patch.object(sys, 'path', [str(ROOT / 'tools')] + sys.path):
    SPEC.loader.exec_module(store)


class StorePreparation(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='z8-store-preparation-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = {
            'schemaVersion': 1, 'versionCode': 5, 'versionName': '0.1.0-rc4',
            'developerName': 'Store fixture', 'supportEmail': 'fixture@example.com',
            'privacyUrl': 'https://devsigner9920.github.io/z8/privacy.html',
            'sourceUrl': 'https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc4/z8-source.zip',
            'policyDate': '2026-11-14',
        }
        self.write_config()
        for name in ('privacy.html', 'privacy.ko.html'):
            self.write('docs/' + name,
                       '<link rel="canonical" href="https://devsigner9920.github.io/z8/' + name + '">'
                       '<time datetime="2026-11-14">Date</time>'
                       '<p>Store fixture fixture@example.com</p>')
        for locale in ('en-US', 'ko-KR'):
            for name in ('title.txt', 'short-description.txt', 'full-description.txt', 'release-notes.txt'):
                self.write('docs/store/' + locale + '/' + name, 'Z8 fixture\n')

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def write_config(self):
        self.write('release/config.json', json.dumps(self.config))

    def test_valid_prepublication_destination_does_not_need_network(self):
        result = store.verify(self.root, tag='v0.1.0-rc4')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['storeText']['ko-KR']['title.txt']['characters'], 10)

    def test_tag_from_an_older_candidate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'release tag'):
            store.verify(self.root, tag='v0.1.0-rc3')

    def test_source_for_an_older_candidate_is_rejected(self):
        self.config['sourceUrl'] = self.config['sourceUrl'].replace('rc4', 'rc3')
        self.write_config()
        with self.assertRaisesRegex(ValueError, 'source asset URL'):
            store.verify(self.root)

    def test_localized_policy_with_stale_operator_is_rejected(self):
        path = self.root / 'docs/privacy.ko.html'
        path.write_text(path.read_text().replace('Store fixture', 'Old operator'))
        with self.assertRaisesRegex(ValueError, 'privacy.ko.html'):
            store.verify(self.root)

    def test_localized_policy_with_wrong_canonical_is_rejected(self):
        path = self.root / 'docs/privacy.ko.html'
        path.write_text(path.read_text().replace('privacy.ko.html', 'privacy.html'))
        with self.assertRaisesRegex(ValueError, 'canonical privacy URL'):
            store.verify(self.root)

    def test_korean_title_limit_counts_characters_not_utf8_bytes(self):
        self.write('docs/store/ko-KR/title.txt', '가' * 30 + '\n')
        self.assertEqual(store.verify(self.root)['storeText']['ko-KR']['title.txt']['characters'], 30)
        self.write('docs/store/ko-KR/title.txt', '가' * 31 + '\n')
        with self.assertRaisesRegex(ValueError, 'character limit'):
            store.verify(self.root)

    def test_release_note_limit_applies_per_locale(self):
        self.write('docs/store/ko-KR/release-notes.txt', '가' * 500 + '\n')
        store.verify(self.root)
        self.write('docs/store/ko-KR/release-notes.txt', '가' * 501 + '\n')
        with self.assertRaisesRegex(ValueError, 'ko-KR/release-notes.txt'):
            store.verify(self.root)

    def test_multiline_short_description_is_rejected(self):
        self.write('docs/store/en-US/short-description.txt', 'Z8\nTerminal\n')
        with self.assertRaisesRegex(ValueError, 'single-line'):
            store.verify(self.root)


if __name__ == '__main__':
    unittest.main()
