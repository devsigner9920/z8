"""Exercise Chrome navigation with synthetic UI observations; never invoke ADB."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("smoke_guest_continuity", ROOT / "tools/smoke-guest-continuity.py")
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def tree(*nodes):
    root = ET.Element("hierarchy")
    for attributes in nodes:
        ET.SubElement(root, "node", dict(bounds="[100,200][900,1200]", enabled="true", clickable="true") | attributes)
    return root


TERMINAL = {"resource-id": "dev.devsigner.z8:id/terminal_view"}
NEW_SESSION = {"resource-id": "dev.devsigner.z8:id/z8_new_session", "text": "＋", "content-desc": "새 세션"}
TOGGLE = {"resource-id": "dev.devsigner.z8:id/z8_sessions_toggle", "content-desc": "프로젝트와 세션 목록"}
CURRENT = {"resource-id": "dev.devsigner.z8:id/z8_current_project", "text": "Fixture"}
DISPLAYS = '''Display 4619827259835644672 (HWC display 0): port=0 pnpId=GGL screenPartStatus=UNSUPPORTED displayName="EMU_display_0"
Display 4619827551948147201 (HWC display 1): port=1 pnpId=GGL screenPartStatus=UNSUPPORTED displayName="EMU_display_1"
'''


class DisplayCapture(unittest.TestCase):
    def test_observed_inner_and_outer_display_mapping(self):
        self.assertEqual(smoke.display_ports(DISPLAYS),
                         {0: '4619827259835644672', 1: '4619827551948147201'})

    def test_missing_duplicate_and_wrong_fixture_displays_fail(self):
        for output in ('', DISPLAYS.splitlines()[0], DISPLAYS + DISPLAYS.splitlines()[0],
                       DISPLAYS.replace('4619827551948147201', '4619827259835644672'),
                       DISPLAYS.replace('EMU_display_1', 'Other_display'),
                       DISPLAYS.replace('port=1', 'port=2'),
                       DISPLAYS.replace('(HWC display 1)', '(HWC display 0)'),
                       DISPLAYS + 'unrecognized record'):
            with self.subTest(output=output), self.assertRaises(RuntimeError):
                smoke.display_ports(output)

    def test_capture_uses_observed_display_id_explicitly(self):
        with patch.object(smoke, 'device') as device:
            device.REPORTS = Path('/test/reports')
            device.adb.return_value = DISPLAYS
            result = smoke.capture('emulator-guest-closed.png', 1)
            self.assertEqual(device.adb.call_args_list[0].args,
                             ('shell', 'dumpsys', 'SurfaceFlinger', '--display-id'))
            self.assertEqual(device.adb.call_args_list[1].args,
                             ('shell', 'screencap', '-p', '-d', '4619827551948147201', '/sdcard/z8-smoke.png'))
            self.assertEqual(device.adb.call_args_list[2].args,
                             ('pull', '/sdcard/z8-smoke.png', '/test/reports/emulator-guest-closed.png'))
            self.assertEqual(result['displayPort'], 1)
            self.assertEqual(result['displayId'], '4619827551948147201')

    def test_invalid_display_list_never_captures_default_screen(self):
        with patch.object(smoke, 'device') as device:
            device.adb.return_value = DISPLAYS.splitlines()[0]
            with self.assertRaises(RuntimeError):
                smoke.capture('emulator-guest-closed.png', 1)
            self.assertEqual(device.adb.call_count, 1)


def chrome(panel_id=None, sessions=(), selected=None):
    root = tree(TERMINAL, NEW_SESSION, TOGGLE, CURRENT)
    if selected is not None:
        ET.SubElement(root, 'node', {'resource-id': 'dev.devsigner.z8:id/z8_session_tab',
                                    'content-desc': '세션 전환: Fixture / ' + selected + ' / 세션 열림', 'selected': 'true'})
    if panel_id is not None:
        panel = ET.SubElement(root, 'node', {'resource-id': 'dev.devsigner.z8:id/' + panel_id,
                                           'bounds': '[0,0][300,1000]', 'enabled': 'true'})
        for project, name in sessions:
            ET.SubElement(panel, 'node', {'resource-id': 'dev.devsigner.z8:id/z8_session_row',
                                         'content-desc': '세션 선택: ' + project + ' / ' + name + ' / 세션 열림',
                                         'bounds': '[0,100][300,180]', 'enabled': 'true', 'clickable': 'true'})
    return root


class ChromeNavigation(unittest.TestCase):
    def setUp(self):
        self.terminal_tree = chrome()
        self.view = next(self.terminal_tree.iter("node"))
        self.drawer_tree = chrome('z8_session_drawer', [('Fixture', 'Shell')])
        self.wide_tree = chrome('z8_session_sidebar', [('Fixture', 'Shell')])
        self.terminal_patch = patch.object(smoke, "terminal", return_value=(self.terminal_tree, self.view))
        self.terminal = self.terminal_patch.start()
        self.device_patch = patch.object(smoke, "device")
        self.device = self.device_patch.start()
        self.device.PACKAGE = "dev.devsigner.z8"
        self.sleep_patch = patch.object(smoke.time, 'sleep')
        self.sleep_patch.start()
        self.addCleanup(self.terminal_patch.stop)
        self.addCleanup(self.device_patch.stop)
        self.addCleanup(self.sleep_patch.stop)

    def test_visible_wide_sidebar_needs_no_toggle_or_back(self):
        self.device.observe.return_value = self.wide_tree
        _, panel = smoke.drawer()
        self.assertTrue(panel.get('resource-id').endswith(':id/z8_session_sidebar'))
        self.device.adb.assert_not_called()
        self.device.click.assert_not_called()
        self.terminal.assert_not_called()

    def test_visible_narrow_drawer_needs_no_toggle(self):
        self.device.observe.return_value = self.drawer_tree
        _, panel = smoke.drawer()
        self.assertTrue(panel.get('resource-id').endswith(':id/z8_session_drawer'))
        self.device.adb.assert_not_called()
        self.device.click.assert_not_called()

    def test_closed_narrow_drawer_opens_actual_chrome_toggle(self):
        self.device.observe.side_effect = [self.terminal_tree, self.drawer_tree]
        _, panel = smoke.drawer()
        self.assertTrue(panel.get('resource-id').endswith(':id/z8_session_drawer'))
        self.assertEqual(self.device.click.call_args.args[0].get('resource-id'), TOGGLE['resource-id'])
        self.device.adb.assert_not_called()

    def test_missing_toggle_fails_without_legacy_controls_or_commands(self):
        legacy = tree(TERMINAL, {'resource-id': 'dev.devsigner.z8:id/new_session_button'})
        self.device.observe.return_value = legacy
        self.terminal.return_value = legacy, self.view
        with self.assertRaisesRegex(RuntimeError, "session toggle is unavailable"):
            smoke.drawer()
        self.device.click.assert_not_called()
        self.device.adb.assert_not_called()

    def test_toggle_must_reveal_actual_panel(self):
        self.device.observe.return_value = self.terminal_tree
        with self.assertRaisesRegex(RuntimeError, "panel did not open"):
            smoke.drawer()
        self.assertEqual(self.device.click.call_count, 1)

    def test_rows_use_project_and_session_accessibility_labels(self):
        observed = chrome('z8_session_sidebar', [('Fixture', 'Shell · 1'), ('Fixture', 'Shell · 2'),
                                               ('Other', 'review / notes')])
        self.assertEqual(set(smoke.rows(observed)),
                         {('Fixture', 'Shell · 1'), ('Fixture', 'Shell · 2'), ('Other', 'review / notes')})

    def test_duplicate_visible_session_names_fail(self):
        observed = chrome('z8_session_sidebar', [('Fixture', 'Shell'), ('Fixture', 'Shell')])
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous project/session'):
            smoke.rows(observed)

    def test_snapshot_traverses_multiple_observed_pages(self):
        later = chrome('z8_session_sidebar', [('Other', 'Codex')])
        with patch.object(smoke, 'panel_start', return_value=self.wide_tree), \
                patch.object(smoke, 'scroll_sessions', side_effect=[later, None]):
            self.assertEqual(smoke.session_snapshot(), {('Fixture', 'Shell'), ('Other', 'Codex')})

    def test_terminal_first_empty_panel_has_zero_sessions_without_fallback(self):
        empty = chrome('z8_session_sidebar')
        with patch.object(smoke, 'panel_start', return_value=empty), \
                patch.object(smoke, 'scroll_sessions', return_value=None):
            self.assertEqual(smoke.session_snapshot(), set())
        self.device.adb.assert_not_called()
        self.device.click.assert_not_called()

    def test_fixture_creation_uses_uuid_ready_profile_gate(self):
        smoke.open_fixture('Fixture', '12345678-1234-1234-1234-123456789abc')
        self.device.prepared_guest.assert_called_once_with('12345678-1234-1234-1234-123456789abc', 'Fixture')
        self.device.command.assert_not_called()

    def test_resume_is_plain_launcher_navigation(self):
        smoke.resume_current()
        self.device.resume.assert_called_once_with()
        self.device.diagnostics.assert_not_called()
        self.device.click.assert_not_called()

    def test_collapsed_project_is_expanded_before_reading_rows(self):
        collapsed = chrome('z8_session_sidebar')
        ET.SubElement(smoke.session_panel(collapsed), 'node',
                      {'text': 'Fixture', 'content-desc': '프로젝트 세션 목록: Fixture · 접힘', 'clickable': 'true'})
        self.device.observe.return_value = self.wide_tree
        self.assertEqual(set(smoke.rows(smoke.expand_groups(collapsed))), {('Fixture', 'Shell')})
        self.assertEqual(self.device.click.call_args.args[0].get('content-desc'), '프로젝트 세션 목록: Fixture · 접힘')

    def test_expanded_accessibility_state_overrides_project_name_glyph(self):
        expanded = chrome('z8_session_drawer')
        ET.SubElement(smoke.session_panel(expanded), 'node',
                      {'text': '› Fixture', 'content-desc': '프로젝트 세션 목록: › Fixture · 펼침', 'clickable': 'true'})
        self.assertIs(smoke.expand_groups(expanded), expanded)
        self.device.click.assert_not_called()
        self.device.observe.assert_not_called()

    def test_scroll_uses_only_observed_vertical_panel_bounds(self):
        observed = chrome('z8_session_sidebar')
        ET.SubElement(smoke.session_panel(observed), 'node',
                      {'class': 'android.widget.ScrollView', 'scrollable': 'true', 'bounds': '[10,200][290,900]'})
        self.device.observe.return_value = observed
        smoke.scroll_sessions(observed)
        self.device.adb.assert_called_once_with('shell', 'input', 'swipe', '150', '760', '150', '340', '250')

    def test_terminal_numbers_survive_deleted_or_renamed_sessions(self):
        self.assertEqual(smoke.fixture_shells({('Other', 'Terminal 1')}, 'Fixture'), 0)
        self.assertEqual(smoke.fixture_shells({('Fixture', 'Terminal 12')}, 'Fixture'), 1)
        self.assertEqual(smoke.fixture_shells({('Fixture', 'Terminal 3'), ('Fixture', 'Terminal 12')}, 'Fixture'), 2)
        self.assertEqual(smoke.fixture_shells({('Fixture', 'Review'), ('Fixture', 'Shell'),
                                              ('Fixture', 'Terminal 0'), ('Fixture', 'Terminal 01')}, 'Fixture'), 0)

    def test_selects_new_high_number_terminal_and_confirms_selected_tab(self):
        rows = [('Fixture', 'Terminal 3'), ('Fixture', 'Terminal 12'), ('Other', 'Terminal 99')]
        observed = chrome('z8_session_sidebar', rows)
        self.terminal.return_value = chrome(selected='Terminal 12'), self.view
        with patch.object(smoke, 'session_snapshot', return_value=set(rows)), \
                patch.object(smoke, 'panel_start', return_value=observed):
            smoke.select_created_session(3, 'Fixture', 2)
        self.assertEqual(self.device.click.call_args.args[0].get('content-desc'),
                         '세션 선택: Fixture / Terminal 12 / 세션 열림')

    def test_new_session_uses_plus_to_open_shell_directly_on_wide_layout(self):
        self.device.observe.side_effect = [self.wide_tree, chrome(selected='Terminal 1')]
        smoke.new_session_control('Fixture')
        self.assertEqual(self.device.click.call_count, 1)
        self.assertEqual(self.device.click.call_args.args[0].get('resource-id'), NEW_SESSION['resource-id'])
        self.device.adb.assert_not_called()

    def test_new_session_closes_only_observed_narrow_drawer(self):
        self.device.observe.side_effect = [self.drawer_tree, chrome(selected='Terminal 2')]
        smoke.new_session_control('Fixture')
        self.device.adb.assert_called_once_with('shell', 'input', 'keyevent', '4')

    def test_direct_shell_wait_accepts_numbered_names_from_accessibility(self):
        self.device.observe.return_value = chrome(selected='Terminal 42')
        self.assertEqual(smoke.wait_direct_shell('Fixture'), 'Terminal 42')
        self.device.click.assert_not_called()

    def test_direct_shell_wait_rejects_any_new_session_chooser(self):
        for title in ('새 세션의 프로젝트', 'Fixture · 새 세션'):
            with self.subTest(title=title):
                self.device.observe.return_value = tree({'text': title})
                with self.assertRaisesRegex(RuntimeError, 'unexpectedly opened a chooser'):
                    smoke.wait_direct_shell('Fixture')
        self.device.click.assert_not_called()

    def test_direct_shell_wait_requires_correct_project_and_selected_shell(self):
        for observed in (chrome(selected='Codex'), chrome(selected='Claude Code'), chrome(selected='Shell'),
                         chrome(selected='Terminal 0'), chrome(selected='Terminal 01')):
            with self.subTest(observed=ET.tostring(observed)), \
                    patch.object(smoke.time, 'monotonic', side_effect=[0, 0, 21]):
                self.device.observe.return_value = observed
                with self.assertRaisesRegex(RuntimeError, 'expected fixture project'):
                    smoke.wait_direct_shell('Fixture')
        wrong_project = chrome(selected='Terminal 1')
        smoke.control(wrong_project, 'z8_current_project').set('text', 'Other')
        self.device.observe.return_value = wrong_project
        with patch.object(smoke.time, 'monotonic', side_effect=[0, 0, 21]), \
                self.assertRaisesRegex(RuntimeError, 'expected fixture project'):
            smoke.wait_direct_shell('Fixture')

    def test_global_new_session_refuses_wrong_project_before_click(self):
        wrong_project = chrome()
        smoke.control(wrong_project, 'z8_current_project').set('text', 'Other')
        self.terminal.return_value = wrong_project, self.view
        self.device.observe.return_value = self.wide_tree
        with self.assertRaisesRegex(RuntimeError, 'not attached to the fixture project'):
            smoke.new_session_control('Fixture')
        self.device.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
