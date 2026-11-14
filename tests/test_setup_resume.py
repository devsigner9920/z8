"""Run the guest provisioner against fake package tools; never install on the host."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = r'''#!PYTHON
import json, os, sys, time
from pathlib import Path
root = Path(os.environ['Z8_FIXTURE'])
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / 'calls').open('a') as log:
    log.write(json.dumps([name, *args]) + '\n')
state = json.loads((root / 'state').read_text())
def save(): (root / 'state').write_text(json.dumps(state))
def wait(stage):
    (root / ('entered-' + stage)).touch()
    while True: time.sleep(.05)
if name == 'uname': print('Linux')
elif name == 'id': print('0')
elif name == 'dpkg-query':
    if not state.get('installed'): sys.exit(1)
    for package in args[2:]:
        print(package + '\t' + ('unpacked' if state.get('invalid') else 'installed') + '\tok\t1.0')
elif name == 'dpkg':
    if args == ['--audit']:
        if state.get('audit'): print('Interrupted package')
    elif state.get('unpacked'): sys.exit(1)
elif name == 'apt-get':
    if state.get('apt_fail'): sys.exit(100)
    if 'install' in args:
        if state.get('wait_packages'):
            state['unpacked'] = True; save(); wait('packages')
        if '-f' in args: state['unpacked'] = False
        else: state['installed'] = True
        save()
elif name == 'python3':
    if args[0].endswith('install-node.py'):
        if state.get('wait_node'): wait('node')
        if state.get('node_fail'): sys.exit(1)
    elif state.get('verify_fail'): sys.exit(1)
elif name == 'node': print('v24.21.0')
elif name == 'npm': print('11.19.0')
elif name == 'ln':
    if state.get('wait_defaults'): wait('defaults')
    if state.get('link_fail'): sys.exit(1)
    if state.get('race_default'): Path(args[-1]).write_text('concurrent user configuration')
    try: os.link(args[-2], args[-1])
    except OSError: sys.exit(1)
'''


class SetupResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.guest = self.root / 'guest'
        self.state_dir = self.guest / 'etc/z8'
        self.state_dir.mkdir(parents=True)
        (self.guest / 'etc/os-release').write_text('ID=ubuntu\n')
        (self.state_dir / 'guest-target').write_text('z8-guest-v1\n')
        self.home_dir = self.guest / 'z8/home'
        self.source_dir = self.guest / 'workspace'
        for directory in (self.home_dir, self.source_dir):
            directory.mkdir(parents=True)
            (directory / 'user-file').write_text('preserve me')
        self.scripts = self.root / 'scripts'
        self.scripts.mkdir()
        for name in ('debian-base-packages.txt', 'shellrc', 'welcome.sh', 'install-node.py'):
            shutil.copyfile(ROOT / 'runtime/guest' / name, self.scripts / name)
        source = (ROOT / 'runtime/guest/provision.sh').read_text()
        # Redirect fixed guest storage only in the test copy. Production never
        # accepts an environment override that could bypass its host guard.
        source = re.sub(r'(?<![\w/.-])/(?:etc/|z8/|workspace\b|opt/)',
                        lambda match: str(self.guest) + match.group(), source)
        (self.scripts / 'provision.sh').write_text(source)
        for name in ('uname', 'id', 'dpkg-query', 'dpkg', 'apt-get', 'python3', 'node', 'npm', 'ln'):
            executable = self.bin / name
            executable.write_text(TOOL.replace('PYTHON', sys.executable, 1))
            executable.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + ':/usr/bin:/bin', Z8_FIXTURE=str(self.root))
        self.write_state({})

    def tearDown(self):
        self.temp.cleanup()

    def write_state(self, state):
        (self.root / 'state').write_text(json.dumps(state))

    def calls(self):
        path = self.root / 'calls'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def run_setup(self):
        return subprocess.run(['/bin/sh', str(self.scripts / 'provision.sh'), '--apply'],
                              env=self.env, capture_output=True, text=True, timeout=15)

    def kill_at(self, phase):
        process = subprocess.Popen(['/bin/sh', str(self.scripts / 'provision.sh'), '--apply'],
            env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            deadline = time.monotonic() + 10
            while not (self.root / ('entered-' + phase)).exists():
                self.assertIsNone(process.poll(), 'Fixture exited before interruption point')
                self.assertLess(time.monotonic(), deadline, 'Fixture interruption deadline')
                time.sleep(.02)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)

    def assert_preserved(self):
        for directory in (self.home_dir, self.source_dir):
            self.assertEqual((directory / 'user-file').read_text(), 'preserve me')

    def test_fresh_base_setup_is_offline_and_installs_no_optional_packages(self):
        self.write_state({'apt_fail': True, 'node_fail': True})
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state_dir / 'base.ready').read_text(), 'z8-base-v1\n')
        self.assertFalse((self.state_dir / 'tools.ready').exists())
        self.assertFalse(any(call[0] in ('apt-get','dpkg','dpkg-query','python3','node','npm') for call in self.calls()))
        self.assert_preserved()

    def test_legacy_full_profile_receipt_and_user_data_are_preserved(self):
        (self.state_dir / 'tools.ready').write_text('z8-tools-v2\n')
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state_dir / 'tools.ready').read_text(), 'z8-tools-v2\n')
        self.assertEqual((self.state_dir / 'base.ready').read_text(), 'z8-base-v1\n')
        self.assert_preserved()

    def test_invalid_guest_identity_fails_without_publishing_ready(self):
        (self.state_dir / 'guest-target').write_text('different environment\n')
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.state_dir / 'base.ready').exists())
        self.assert_preserved()

    def test_kill_before_default_publication_never_leaves_partial_destination(self):
        self.write_state({'installed': True, 'wait_defaults': True})
        self.kill_at('defaults')
        self.assertFalse((self.state_dir / 'shellrc').exists())
        self.assertFalse((self.state_dir / 'base.ready').exists())
        self.write_state({'installed': True})
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ('shellrc', 'welcome.sh'):
            self.assertEqual((self.state_dir / name).read_bytes(), (self.scripts / name).read_bytes())
        self.assertTrue((self.guest / 'etc/profile.d/z8.sh').read_text().endswith('fi\n'))
        self.assert_preserved()

    def test_default_publication_failure_leaves_no_destination_or_ready_receipt(self):
        self.write_state({'installed': True, 'link_fail': True})
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.state_dir / 'shellrc').exists())
        self.assertFalse((self.state_dir / 'base.ready').exists())
        self.assertFalse(list(self.state_dir.glob('.z8-default.*')))
        self.assert_preserved()

    def test_existing_config_files_and_broken_or_directory_links_are_preserved(self):
        (self.state_dir / 'shellrc').write_text('user shell configuration')
        (self.state_dir / 'welcome.sh').symlink_to(self.root / 'does-not-exist')
        profiles = self.guest / 'etc/profile.d'
        profiles.mkdir()
        (profiles / 'z8.sh').symlink_to(self.source_dir, target_is_directory=True)
        self.write_state({'installed': True})
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state_dir / 'shellrc').read_text(), 'user shell configuration')
        self.assertEqual((self.state_dir / 'welcome.sh').readlink(), self.root / 'does-not-exist')
        self.assertEqual((profiles / 'z8.sh').readlink(), self.source_dir)
        self.assertEqual([file.name for file in self.source_dir.iterdir()], ['user-file'])
        self.assertFalse(any(call[0] == 'ln' for call in self.calls()))

    def test_configuration_created_during_publication_is_never_overwritten(self):
        self.write_state({'installed': True, 'race_default': True})
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in (self.state_dir / 'shellrc', self.state_dir / 'welcome.sh',
                     self.guest / 'etc/profile.d/z8.sh'):
            self.assertEqual(path.read_text(), 'concurrent user configuration')


if __name__ == '__main__':
    unittest.main()
