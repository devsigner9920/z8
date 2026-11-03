"""Changed-file notices preserve original license bytes and source structure."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location('source_modifications', Path(__file__).resolve().parents[1] / 'tools/source_modifications.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class ModificationNotices(unittest.TestCase):
    def test_original_header_and_code_are_preserved(self):
        data = b'/* Copyright original author. Licensed under Apache-2.0. */\npackage fixture;\n'
        marked = m.annotate(data, '.java')
        self.assertTrue(marked.endswith(data))
        self.assertIn(m.NOTICE_DATE.encode(), marked)
        self.assertNotIn(b'GPL', marked)
        with self.assertRaises(ValueError): m.annotate(marked, '.java')

    def test_xml_declaration_and_shell_shebang_stay_first(self):
        data = b'<?xml version="1.0" encoding="utf-8"?>\n<!-- Original attribution -->\n<resources><string name="x">value</string></resources>'
        marked = m.annotate(data, '.xml')
        self.assertTrue(marked.startswith(b'<?xml'))
        self.assertIn(b'<!-- Original attribution -->', marked)
        self.assertEqual(ET.fromstring(marked).find('string').text, 'value')
        script = b'#!/bin/sh\n# Original attribution\necho safe\n'
        result = m.annotate(script, '.sh')
        self.assertTrue(result.startswith(b'#!/bin/sh\n'))
        self.assertTrue(result.endswith(script.split(b'\n', 1)[1]))

    def test_only_changed_files_receive_notices_and_binary_assets_are_not_corrupted(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); original = root / 'upstream'; prepared = root / 'prepared'
            original.mkdir(); prepared.mkdir()
            before = {'changed.java': b'package old;\n', 'same.java': b'package same;\n',
                      'logo.png': b'original binary', 'removed.java': b'package removed;\n'}
            after = {'changed.java': b'package changed;\n', 'same.java': before['same.java'], 'logo.png': b'replacement binary'}
            for n, data in before.items(): (original / n).write_bytes(data)
            for n, data in after.items(): (prepared / n).write_bytes(data)
            report = m.mark_modified(original, prepared, before, 'a' * 40)
            self.assertEqual((prepared / 'same.java').read_bytes(), before['same.java'])
            self.assertEqual((prepared / 'logo.png').read_bytes(), after['logo.png'])
            self.assertEqual({r['path'] for r in report['files']}, {'changed.java', 'logo.png', 'removed.java'})
            self.assertEqual(json.loads((prepared / 'Z8-MODIFICATIONS.json').read_text()), report)
            self.assertEqual((original / 'changed.java').read_bytes(), before['changed.java'])

    def test_unknown_modified_format_requires_explicit_support(self):
        with self.assertRaises(ValueError): m.annotate(b'unknown', '.unknown')


if __name__ == '__main__': unittest.main()
