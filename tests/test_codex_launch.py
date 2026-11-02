"""Real wrapper exec/PTY consent and private project-preference filesystem behavior."""
from pathlib import Path
import importlib.util
import json
import os
import pty
import select
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / 'runtime/guest/codex-launch.py'
PROJECT = '11111111-2222-4333-8444-555555555555'
OTHER = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
SPEC = importlib.util.spec_from_file_location('codex_launch', MODULE_PATH)
launcher = importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(launcher)


class CodexLaunch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='z8-codex-launch-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / 'home';self.home.mkdir(mode=0o700)
        self.log = self.root / 'calls.jsonl'
        self.binary = self.root / 'codex fixture'
        self.binary.write_text('#!' + sys.executable + '\n' + r'''import json,os,sys,time
with open(os.environ['FAKE_CALLS'],'a') as output: output.write(json.dumps(sys.argv[1:])+"\n")
if sys.argv[1:]==['--help']:
    mode=os.environ.get('FAKE_HELP','normal')
    if mode=='slow':time.sleep(8)
    elif mode=='large':print('x'*140000)
    elif mode=='missing':print('--no-daemon')
    else: print('--no-daemon\n-s, --sandbox <MODE>\npossible values: read-only, workspace-write, danger-full-access')
    raise SystemExit(0)
print('FIXTURE_LAUNCHED',flush=True)
raise SystemExit(37)
''')
        self.binary.chmod(0o700)
        # Python-level fixture injection exists only in the test harness. Production
        # has no environment variable or command flag to bypass its guest guard.
        self.runner = self.root / 'run.py'
        self.runner.write_text(f'''import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('actual',{str(MODULE_PATH)!r})
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.guest_context=lambda: (Path({str(self.home)!r}),{PROJECT!r})
raise SystemExit(module.main(sys.argv[1:]))
''')

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def run_wrapper(self, args=(), answer=None, tty=True, help_mode='normal', interrupt=False, language='en'):
        env = dict(os.environ, FAKE_CALLS=str(self.log), FAKE_HELP=help_mode, Z8_UI_LANGUAGE=language)
        command = [sys.executable, str(self.runner), str(self.binary), *args]
        if not tty:
            result = subprocess.run(command, input='', capture_output=True, text=True, env=env, timeout=6)
            return result.returncode, result.stdout + result.stderr
        master, slave = pty.openpty()
        process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
        os.close(slave)
        output = bytearray();sent = False;deadline = time.monotonic() + 7
        try:
            while time.monotonic() < deadline:
                if select.select([master], [], [], .05)[0]:
                    try: chunk = os.read(master, 65536)
                    except OSError: break
                    if not chunk: break
                    output.extend(chunk)
                if not sent and ('선택: ' if language == 'ko' else 'Choice: ').encode() in output:
                    sent = True
                    if interrupt: process.send_signal(signal.SIGINT)
                    else: os.write(master, answer if answer is not None else b'\n')
                if process.poll() is not None:
                    # Drain the remaining PTY bytes before asserting indicator text.
                    while select.select([master], [], [], 0)[0]:
                        try: output.extend(os.read(master, 65536))
                        except OSError: break
                    break
            return process.wait(timeout=1), output.decode('utf-8', errors='replace')
        finally:
            if process.poll() is None: process.kill();process.wait()
            os.close(master)

    def test_first_consent_remember_resume_fork_reset_preserves_argv_and_exit(self):
        args = ['--model', 'model name', 'make this work; $(literal)']
        status, output = self.run_wrapper(args, b'yes\n')
        self.assertEqual(status, 37, output)
        self.assertIn('without further approval', output)
        self.assertIn('other Z8 projects', output)
        self.assertIn('Codex sandbox OFF', output)
        self.assertEqual(self.calls()[-1], ['--no-daemon', '--sandbox', 'danger-full-access', *args])
        state = self.home / '.config/z8/codex-local.json'
        self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(state.parent.stat().st_mode), 0o700)
        self.assertFalse(state.is_symlink());self.assertEqual(state.stat().st_nlink, 1)
        self.assertEqual(json.loads(state.read_text()), {'schemaVersion': 1, 'projectId': PROJECT, 'choice': launcher.CHOICE})
        for args in (['resume', '--last'], ['fork', 'session-id', 'continue here']):
            status, output = self.run_wrapper(args)
            self.assertEqual(status, 37, output);self.assertNotIn('Choice:', output)
            self.assertEqual(self.calls()[-1], ['--no-daemon', '--sandbox', 'danger-full-access', *args])
        before = self.calls();status, output = self.run_wrapper([launcher.RESET], tty=False)
        self.assertEqual(status, 0, output);self.assertFalse(state.exists());self.assertEqual(self.calls(), before)
        status, output = self.run_wrapper(answer='동의\n'.encode(), language='ko')
        self.assertEqual(status, 37, output)
        self.assertIn('추가 승인 없이', output)
        self.assertIn('다른 z8 프로젝트', output)
        self.assertIn('Codex sandbox 꺼짐', output)

    def test_inherited_sgid_directory_keeps_private_store_usable(self):
        config = self.home / '.config';config.mkdir(mode=0o700);config.chmod(0o2700)
        directory = config / 'z8';directory.mkdir(mode=0o700);directory.chmod(0o2700)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o2700)
        launcher.save_approval(self.home, PROJECT)
        self.assertTrue(launcher.approved(self.home, PROJECT))
        state = directory / launcher.STATE
        self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)
        launcher.reset_approval(self.home)
        self.assertFalse(state.exists())
        for mode in (0o2710, 0o2704):
            directory.chmod(mode)
            with self.assertRaises(ValueError): launcher.save_approval(self.home, PROJECT)

    def test_enter_eof_other_answer_and_interrupt_cancel_without_cli_or_receipt(self):
        for answer, interrupted in ((b'\n', False), (b'\x04', False), (b'no\n', False), (b'yes \n', False), (b'', True)):
            with self.subTest(answer=answer, interrupted=interrupted):
                if self.log.exists(): self.log.unlink()
                status, output = self.run_wrapper(answer=answer, interrupt=interrupted)
                self.assertEqual(status, 130, output)
                self.assertEqual(self.calls(), [['--help']])
                self.assertFalse((self.home / '.config').exists())

    def test_non_tty_subcommands_explicit_policy_and_ambiguous_flags_passthrough(self):
        args_list = [[], ['exec', 'hello'], ['review'], ['login'], ['logout'], ['help'], ['--help'],
                     ['--version'], ['app-server'], ['remote'], ['features'], ['internal-ssh-serve'], ['--no-daemon'],
                     ['--sandbox', 'workspace-write'], ['resume', '--last', '-a', 'on-request'],
                     ['fork', '--profile', 'custom'], ['--config', 'a=b'], ['-c=a=b'], ['-ma'],
                     ['--full-auto'], ['--dangerously-bypass-approvals-and-sandbox'], ['-C', '/other'],
                     ['--cd=/other'], ['resume', '--all'], ['--add-dir', '/other'], ['--unknown'],
                     [launcher.RESET, '--version']]
        for args in args_list:
            with self.subTest(args=args):
                if self.log.exists(): self.log.unlink()
                status, output = self.run_wrapper(args, tty=bool(args))
                self.assertEqual(status, 0 if args == ['--help'] else 37, output)
                self.assertEqual(self.calls(), [args])
                self.assertNotIn('Choice:', output)
        self.assertFalse((self.home / '.config').exists())

    def test_unsupported_and_bounded_capability_probe_never_changes_argv(self):
        for mode in ('missing', 'large', 'slow'):
            with self.subTest(mode=mode):
                if self.log.exists(): self.log.unlink()
                begin = time.monotonic()
                status, output = self.run_wrapper(['hello'], help_mode=mode)
                self.assertLess(time.monotonic() - begin, 5)
                self.assertEqual(status, 37, output)
                self.assertEqual(self.calls(), [['--help'], ['hello']])
                self.assertNotIn('Choice:', output)
        self.assertFalse((self.home / '.config').exists())

    def test_corrupt_cross_project_or_public_receipt_fails_without_unsandboxed_exec(self):
        launcher.save_approval(self.home, PROJECT)
        state = self.home / '.config/z8/codex-local.json'
        for record in ({'schemaVersion': 1, 'projectId': OTHER, 'choice': launcher.CHOICE},
                       {'schemaVersion': True, 'projectId': PROJECT, 'choice': launcher.CHOICE},
                       {'schemaVersion': 1, 'projectId': PROJECT, 'choice': launcher.CHOICE, 'extra': True},
                       {'schemaVersion': 2, 'projectId': PROJECT, 'choice': launcher.CHOICE}):
            state.write_text(json.dumps(record))
            if self.log.exists(): self.log.unlink()
            status, output = self.run_wrapper()
            self.assertEqual(status, 1, output);self.assertEqual(self.calls(), [['--help']])
        state.write_text('{"schemaVersion":1,"schemaVersion":1}')
        with self.assertRaises(ValueError): launcher.approved(self.home, PROJECT)
        state.write_bytes(b'x' * 4097)
        with self.assertRaises(ValueError): launcher.approved(self.home, PROJECT)
        state.chmod(0o644)
        with self.assertRaises(ValueError): launcher.approved(self.home, PROJECT)

    def test_symlink_parent_receipt_and_write_failure_cannot_publish_consent(self):
        outside = self.root / 'outside';outside.mkdir(mode=0o700)
        (self.home / '.config').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError): launcher.save_approval(self.home, PROJECT)
        self.assertEqual(list(outside.iterdir()), [])
        (self.home / '.config').unlink()
        launcher.save_approval(self.home, PROJECT)
        state = self.home / '.config/z8/codex-local.json';state.unlink()
        target = outside / 'keep';target.write_text('preserve');target.chmod(0o600)
        state.symlink_to(target)
        for action in (lambda: launcher.approved(self.home, PROJECT), lambda: launcher.save_approval(self.home, PROJECT),
                       lambda: launcher.reset_approval(self.home)):
            with self.assertRaises(OSError): action()
        self.assertEqual(target.read_text(), 'preserve');self.assertTrue(state.is_symlink())
        state.unlink()
        with patch.object(launcher.os, 'replace', side_effect=OSError('fixture publication failure')):
            with self.assertRaises(OSError): launcher.save_approval(self.home, PROJECT)
        self.assertFalse(state.exists())
        self.assertEqual(list(state.parent.iterdir()), [])

    def test_production_context_requires_exact_home_canonical_project_and_real_marker(self):
        marker = self.root / 'marker';marker.write_text('z8-guest-v1\n');marker.chmod(0o600)
        with patch.object(launcher, 'MARKER', marker), patch.object(launcher.platform, 'system', return_value='Linux'):
            with patch.dict(os.environ, {'HOME': '/z8/home', 'Z8_PROJECT_ID': PROJECT}):
                self.assertEqual(launcher.guest_context(), (Path('/z8/home'), PROJECT))
            for home, project in (('/elsewhere', PROJECT), ('/z8/home/', PROJECT), ('/z8/home', ''),
                                  ('/z8/home', OTHER.upper()), ('/z8/home', '{' + PROJECT + '}')):
                with patch.dict(os.environ, {'HOME': home, 'Z8_PROJECT_ID': project}):
                    with self.assertRaises(ValueError): launcher.guest_context()
            marker.unlink();marker.symlink_to(self.binary)
            with patch.dict(os.environ, {'HOME': '/z8/home', 'Z8_PROJECT_ID': PROJECT}):
                with self.assertRaises(OSError): launcher.guest_context()


if __name__ == '__main__': unittest.main()
