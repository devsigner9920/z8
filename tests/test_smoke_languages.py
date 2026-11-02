"""English/Korean observed UI navigation; all device interaction is mocked."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('language_navigation', ROOT / 'tools/smoke-session-navigation.py')
n = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(n)
d, c, ui = n.d, n.c, n.ui
PROJECT = '12345678-1234-1234-1234-123456789abc'


def tree(*nodes):
    root = ET.Element('hierarchy')
    for attrs in nodes:
        ET.SubElement(root, 'node', {'bounds': '[20,40][420,640]', 'enabled': 'true'} | attrs)
    return root


class SmokeLanguages(unittest.TestCase):
    def test_fixture_names_remain_exact_even_if_they_are_translatable_words(self):
        with patch.object(d, 'observe', return_value=tree({'text': 'Settings'})):
            with self.assertRaises(RuntimeError):
                n.node(text='환경설정')
            self.assertEqual(n.node(text=('Settings', '환경설정')).get('text'), 'Settings')

    def test_bilingual_alternatives_still_reject_ambiguous_controls(self):
        with patch.object(d, 'observe', return_value=tree({'text': 'Cancel'}, {'text': '취소'})), \
                patch.object(d, 'click') as click:
            with self.assertRaises(RuntimeError):
                n.press(text=ui.labels('cancel'))
            click.assert_not_called()

    def test_current_settings_route_in_both_languages(self):
        for settings, action in (('Settings', 'Runtime diagnostics'), ('환경설정', '런타임 진단')):
            with self.subTest(settings=settings), \
                    patch.object(d, 'observe', side_effect=[tree({'content-desc': settings}), tree({'text': action}), tree()]), \
                    patch.object(d, 'click') as click, patch.object(d, 'adb') as adb:
                d.terminal_action('실행 진단')
                self.assertEqual([call.args[0].get('content-desc') or call.args[0].get('text')
                                  for call in click.call_args_list], [settings, action])
                adb.assert_not_called()

    def test_settings_scroll_uses_observed_container_before_exact_action(self):
        with patch.object(d, 'observe', side_effect=[tree({'content-desc': 'Settings'}),
                tree({'scrollable': 'true'}), tree({'text': 'Runtime diagnostics'}), tree()]), \
                patch.object(d, 'click') as click, patch.object(d, 'adb') as adb:
            d.terminal_action('실행 진단')
            adb.assert_called_once_with('shell', 'input', 'swipe', '220', '520', '220', '160', '300')
            self.assertEqual(click.call_count, 2)

    def test_english_ready_profile_still_requires_complete_tools(self):
        chrome = tree({'resource-id': d.PACKAGE + ':id/z8_current_project', 'text': 'Fixture'})
        for state, allowed in (('Linux installed · Tools ready', True),
                               ('Linux installed · Tools need setup', False),
                               ('Linux installed · Some tool checks delayed', False),
                               ('Set up environment', False)):
            with self.subTest(state=state), patch.object(d, 'adb', return_value='z8-tools-v2'), \
                    patch.object(d, 'resume', return_value=chrome), patch.object(d, 'terminal_action'), \
                    patch.object(d, 'observe', return_value=tree({'text': state}, {'text': 'Open new terminal'})), \
                    patch.object(d, 'click') as click:
                if allowed:
                    d.prepared_guest(PROJECT, 'Fixture')
                    click.assert_called_once()
                else:
                    with self.assertRaises(RuntimeError):
                        d.prepared_guest(PROJECT, 'Fixture')
                    click.assert_not_called()

    def test_english_session_identity_keeps_user_title_and_current_status(self):
        observed = tree({'resource-id': d.PACKAGE + ':id/z8_session_sidebar'})
        ET.SubElement(list(observed)[0], 'node', {'resource-id': d.PACKAGE + ':id/z8_session_row',
            'content-desc': 'Select session: 한국어 프로젝트 / review / notes / Session open'})
        self.assertEqual(set(c.rows(observed)), {('한국어 프로젝트', 'review / notes')})
        tab = tree({'resource-id': d.PACKAGE + ':id/z8_session_tab', 'clickable': 'true',
                    'content-desc': 'Switch session: 한국어 프로젝트 / review / notes / Unread notifications: 2'})
        with patch.object(d, 'observe', return_value=tab), patch.object(d, 'click') as click, \
                patch.object(n, 'wait_selected') as wait:
            n.select('한국어 프로젝트', 'review / notes', tab=True)
            click.assert_called_once()
            wait.assert_called_once_with('한국어 프로젝트', 'review / notes')

    def test_collapsed_groups_require_matching_language_prefix_and_state(self):
        self.assertTrue(ui.collapsed_project('Project sessions: 한국어 프로젝트 · Collapsed'))
        self.assertTrue(ui.collapsed_project('프로젝트 세션 목록: English project · 접힘'))
        for value in ('Project sessions: Fixture · Expanded', 'Project sessions: Fixture · 접힘',
                      '프로젝트 세션 목록: Fixture · Collapsed', 'Project sessions:  · Collapsed'):
            self.assertFalse(ui.collapsed_project(value))


if __name__ == '__main__':
    unittest.main()
