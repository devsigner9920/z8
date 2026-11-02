"""Exercise terminal-first smoke navigation with observations; never use ADB."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('smoke_terminal_entry', ROOT / 'tools/smoke-emulator.py')
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)
PROJECT = '12345678-1234-1234-1234-123456789abc'


def tree(*records):
    root = ET.Element('hierarchy')
    for record in records:
        ET.SubElement(root, 'node', {'bounds': '[0,0][400,600]', 'enabled': 'true'} | record)
    return root


CHROME = tree({'resource-id': smoke.PACKAGE + ':id/z8_sessions_toggle'},
              {'resource-id': smoke.PACKAGE + ':id/z8_current_project', 'text': 'Fixture'},
              {'content-desc': '터미널 메뉴'})
READY = tree({'text': 'Linux 설치됨 · 개발 도구 준비됨'}, {'text': '새 터미널 열기'})


class TerminalEntry(unittest.TestCase):
    def test_main_navigation_focuses_without_any_launch_extra(self):
        with patch.object(smoke, 'adb') as adb, patch.object(smoke, 'observe', return_value=CHROME):
            self.assertIs(smoke.resume(PROJECT, show_sessions=True), CHROME)
        args = adb.call_args.args
        self.assertIn(smoke.PACKAGE + '/com.termux.app.TermuxActivity', args)
        self.assertIn('android.intent.action.MAIN', args)
        self.assertEqual(args[-6:], ('--es', smoke.PACKAGE + '.FOCUS_PROJECT_ID', PROJECT,
                                    '--ez', smoke.PACKAGE + '.SHOW_SESSIONS', 'true'))
        self.assertEqual([arg for arg in args if 'PROJECT_ID' in arg], [smoke.PACKAGE + '.FOCUS_PROJECT_ID'])
        self.assertFalse(any('GUEST_SESSION' in arg or 'DIAGNOSTIC_SHELL' in arg for arg in args))

    def test_invalid_uuid_never_reaches_device(self):
        with patch.object(smoke, 'adb') as adb:
            with self.assertRaises(ValueError):
                smoke.resume('../not-a-project')
            with self.assertRaises(ValueError):
                smoke.prepared_guest('../not-a-project', 'Fixture')
            adb.assert_not_called()

    def test_diagnostics_uses_terminal_menu_after_navigation(self):
        with patch.object(smoke, 'resume') as resume, patch.object(smoke, 'terminal_action') as action:
            smoke.diagnostics()
            resume.assert_called_once_with()
            action.assert_called_once_with('실행 진단')

    def test_action_clicks_observed_overflow_then_exact_label(self):
        action = tree({'text': '실행 진단'})
        result = tree({'text': 'z8 실행 진단'})
        with patch.object(smoke, 'observe', side_effect=[CHROME, action, result]), \
                patch.object(smoke, 'click') as click, patch.object(smoke, 'adb') as adb:
            self.assertIs(smoke.terminal_action('실행 진단'), result)
            self.assertEqual(click.call_args_list[0].args[0].get('content-desc'), '터미널 메뉴')
            self.assertEqual(click.call_args_list[1].args[0].get('text'), '실행 진단')
            adb.assert_not_called()

    def test_action_closes_only_observed_narrow_drawer(self):
        drawer = tree({'resource-id': smoke.PACKAGE + ':id/z8_session_drawer'})
        with patch.object(smoke, 'observe', side_effect=[drawer, CHROME, tree({'text': '개발 환경'}), READY]), \
                patch.object(smoke, 'click'), patch.object(smoke, 'adb') as adb:
            smoke.terminal_action('개발 환경')
            adb.assert_called_once_with('shell', 'input', 'keyevent', '4')

    def test_missing_menu_never_guesses_click_or_native_fallback(self):
        with patch.object(smoke, 'observe', return_value=tree()), \
                patch.object(smoke, 'click') as click, patch.object(smoke, 'adb') as adb:
            with self.assertRaisesRegex(RuntimeError, 'observed terminal menu'):
                smoke.terminal_action('실행 진단')
            click.assert_not_called()
            adb.assert_not_called()

    def test_ready_guest_requires_marker_and_actual_ready_ui(self):
        with patch.object(smoke, 'adb', return_value='z8-tools-v2') as adb, \
                patch.object(smoke, 'resume', return_value=CHROME) as resume, \
                patch.object(smoke, 'terminal_action') as action, \
                patch.object(smoke, 'observe', return_value=READY), patch.object(smoke, 'click') as click:
            smoke.prepared_guest(PROJECT, 'Fixture')
            self.assertTrue(adb.call_args.args[-1].endswith('/rootfs/etc/z8/tools.ready'))
            resume.assert_called_once_with(PROJECT)
            action.assert_called_once_with('개발 환경')
            self.assertEqual(click.call_args.args[0].get('text'), '새 터미널 열기')

    def test_missing_or_old_tool_profile_stops_before_navigation(self):
        for marker in ('', 'z8-tools-v1', subprocess.CalledProcessError(1, 'read marker')):
            with self.subTest(marker=str(marker)), patch.object(smoke, 'adb') as adb, \
                    patch.object(smoke, 'resume') as resume, patch.object(smoke, 'click') as click:
                if isinstance(marker, Exception):
                    adb.side_effect = marker
                else:
                    adb.return_value = marker
                with self.assertRaisesRegex(RuntimeError, 'prepar|prepare'):
                    smoke.prepared_guest(PROJECT, 'Fixture')
                resume.assert_not_called()
                click.assert_not_called()

    def test_ready_marker_cannot_bypass_ui_check_or_inject_into_installer(self):
        cases = [tree({'resource-id': smoke.PACKAGE + ':id/terminal_view'}),
                 tree({'text': '개발 환경 준비'}),
                 tree({'text': 'Linux 설치됨 · 개발 도구 준비 필요'}, {'text': '기본 Linux 셸만 열기'}),
                 tree({'text': 'Linux 설치됨 · 일부 도구 확인 지연'}, {'text': '새 터미널 열기'})]
        for observation in cases:
            with self.subTest(observation=ET.tostring(observation)), \
                    patch.object(smoke, 'adb', return_value='z8-tools-v2'), \
                    patch.object(smoke, 'resume', return_value=CHROME), \
                    patch.object(smoke, 'terminal_action'), patch.object(smoke, 'observe', return_value=observation), \
                    patch.object(smoke, 'click') as click, patch.object(smoke, 'command') as command:
                with self.assertRaises(RuntimeError):
                    smoke.prepared_guest(PROJECT, 'Fixture')
                click.assert_not_called()
                command.assert_not_called()

    def test_basic_shell_alone_times_out_without_click(self):
        with patch.object(smoke, 'adb', return_value='z8-tools-v2'), \
                patch.object(smoke, 'resume', return_value=CHROME), \
                patch.object(smoke, 'terminal_action'), \
                patch.object(smoke, 'observe', return_value=tree({'text': '기본 Linux 셸만 열기'})), \
                patch.object(smoke.time, 'monotonic', side_effect=[0, 0, 121]), \
                patch.object(smoke.time, 'sleep'), patch.object(smoke, 'click') as click:
            with self.assertRaisesRegex(RuntimeError, 'no Shell or installer was selected'):
                smoke.prepared_guest(PROJECT, 'Fixture')
            click.assert_not_called()

    def test_mismatched_focused_project_stops_before_environment_action(self):
        with patch.object(smoke, 'adb', return_value='z8-tools-v2'), \
                patch.object(smoke, 'resume', return_value=CHROME), \
                patch.object(smoke, 'terminal_action') as action:
            with self.assertRaisesRegex(RuntimeError, 'Focused project'):
                smoke.prepared_guest(PROJECT, 'Wrong project')
            action.assert_not_called()


if __name__ == '__main__':
    unittest.main()
