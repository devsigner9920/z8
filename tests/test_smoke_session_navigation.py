"""Session-tab selection uses fresh UI observations; no emulator is accessed."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('smoke_session_navigation', ROOT / 'tools/smoke-session-navigation.py')
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def tab(title='Build', status='세션 열림', **overrides):
    return {'resource-id': 'dev.devsigner.z8:id/z8_session_tab',
            'content-desc': '세션 전환: Fixture / ' + title + ' / ' + status,
            'bounds': '[100,200][400,250]', 'enabled': 'true', 'clickable': 'true'} | overrides


def tree(*attributes):
    root = ET.Element('hierarchy')
    for item in attributes:
        ET.SubElement(root, 'node', item)
    return root


class SessionTabSelection(unittest.TestCase):
    def setUp(self):
        self.device_patch = patch.object(smoke, 'd')
        self.device = self.device_patch.start()
        self.device.PACKAGE = 'dev.devsigner.z8'
        self.wait_patch = patch.object(smoke, 'wait_selected')
        self.wait = self.wait_patch.start()
        self.direct_patch = patch.object(smoke.c, 'wait_direct_shell')
        self.direct = self.direct_patch.start()
        self.addCleanup(self.device_patch.stop)
        self.addCleanup(self.wait_patch.stop)
        self.addCleanup(self.direct_patch.stop)

    def test_selects_unique_resource_and_name_prefix_for_each_status(self):
        for status in ('세션 열림', '미확인 알림 2개', '종료됨'):
            with self.subTest(status=status):
                observed = tree(tab(status=status), tab(title='Build-Other'),
                                tab(**{'resource-id': 'dev.devsigner.z8:id/z8_session_row'}))
                self.device.observe.return_value = observed
                smoke.select('Fixture', 'Build', tab=True)
                self.assertIs(self.device.click.call_args.args[0], list(observed)[0])
        self.assertEqual(self.device.observe.call_count, 3)
        self.wait.assert_called_with('Fixture', 'Build')
        self.device.adb.assert_not_called()

    def test_missing_duplicate_disabled_and_wrong_resource_fail_without_tapping(self):
        for observed in (tree(), tree(tab(), tab()),
                         tree(tab(**{'enabled': 'false'})),
                         tree(tab(**{'visible-to-user': 'false'})),
                         tree(tab(**{'resource-id': 'other.app:id/z8_session_tab'})),
                         tree(tab(**{'content-desc': '세션 전환: Fixture / Build'}))):
            with self.subTest(observed=ET.tostring(observed)):
                self.device.observe.return_value = observed
                with self.assertRaisesRegex(RuntimeError, 'unique actual session tab'):
                    smoke.select('Fixture', 'Build', tab=True)
        self.device.click.assert_not_called()
        self.wait.assert_not_called()

    def test_session_menu_longpresses_current_selected_tab_from_fresh_bounds(self):
        for bounds, expected in (('[100,200][400,250]', ('250', '225')),
                                 ('[20,40][220,120]', ('120', '80'))):
            with self.subTest(bounds=bounds):
                self.device.observe.return_value = tree(
                    tab(**{'selected': 'true', 'bounds': bounds}),
                    tab(title='Other', selected='false'),
                    tab(**{'resource-id': 'dev.devsigner.z8:id/z8_session_row', 'selected': 'true'}))
                smoke.open_session_menu()
                self.device.adb.assert_called_with('shell', 'input', 'swipe',
                                                   *expected, *expected, '900')
        self.assertEqual(self.device.observe.call_count, 2)
        self.device.click.assert_not_called()

    def test_session_menu_refuses_ambiguous_hidden_disabled_or_invalid_tab(self):
        current = tab(selected='true')
        invalid = [tree(), tree(current, current), tree(tab(selected='false'))]
        for field in ('enabled', 'visible-to-user', 'clickable', 'long-clickable'):
            invalid.append(tree(current | {field: 'false'}))
        for bounds in ('', '[5,10][5,50]', '[10,10][50,10]', '[-20,10][50,50]'):
            invalid.append(tree(current | {'bounds': bounds}))
        for observed in invalid:
            with self.subTest(observed=ET.tostring(observed)):
                self.device.observe.return_value = observed
                with self.assertRaises(RuntimeError):
                    smoke.open_session_menu()
        self.device.adb.assert_not_called()
        self.device.click.assert_not_called()

    def test_global_add_verifies_project_then_opens_shell_directly(self):
        self.device.observe.side_effect = [
            tree({'resource-id': 'dev.devsigner.z8:id/z8_current_project', 'text': 'Fixture'}),
            tree({'resource-id': 'dev.devsigner.z8:id/z8_new_session'})]
        smoke.create('Fixture')
        clicked = [call.args[0] for call in self.device.click.call_args_list]
        self.assertEqual(len(clicked), 1)
        self.assertEqual(clicked[0].get('resource-id'), 'dev.devsigner.z8:id/z8_new_session')
        self.direct.assert_called_once_with('Fixture')
        self.device.adb.assert_not_called()

    def test_project_group_add_remains_contextual(self):
        self.device.observe.side_effect = [tree({'content-desc': 'Fixture에 새 세션'})]
        with patch.object(smoke, 'hide_keyboard') as hide:
            smoke.create('Fixture', via_group=True)
        hide.assert_called_once_with()
        clicked = [call.args[0] for call in self.device.click.call_args_list]
        self.assertEqual(len(clicked), 1)
        self.assertEqual(clicked[0].get('content-desc'), 'Fixture에 새 세션')
        self.direct.assert_called_once_with('Fixture')

    def test_global_add_refuses_wrong_or_absent_project_context_before_click(self):
        for project in ('Other', '기기 셸'):
            with self.subTest(project=project):
                self.device.observe.return_value = tree({'resource-id': 'dev.devsigner.z8:id/z8_current_project', 'text': project})
                with self.assertRaisesRegex(RuntimeError, 'not attached to the requested project'):
                    smoke.create('Fixture')
        self.device.click.assert_not_called()
        self.direct.assert_not_called()


if __name__ == '__main__':
    unittest.main()
