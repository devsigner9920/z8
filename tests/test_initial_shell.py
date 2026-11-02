"""Exercise the production fixed first-shell entrypoint without installing host packages."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def entrypoint():
    source = (ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Guest.java').read_text()
    section = source.split('static final String PREPARE_SHELL =', 1)[1].split('private static final String DNS_HEADER', 1)[0]
    return ''.join(json.loads(value) for value in re.findall(r'"(?:\\.|[^"\\])*"', section))


class InitialShellTests(unittest.TestCase):
    def run_entrypoint(self, setup_status):
        with tempfile.TemporaryDirectory(prefix='z8-first-shell-') as temporary:
            root = Path(temporary)
            setup = root / 'setup.sh'
            setup.write_text('printf "installed\\n" >> "$Z8_TEST_LOG"\nexit ' + str(setup_status) + '\n')
            shell = root / 'shell.sh'
            shell.write_text('printf "shell\\n" >> "$Z8_TEST_LOG"\ntest -z "${Z8_SHOW_WELCOME-}"\n')
            command = entrypoint().replace('/usr/local/lib/z8/setup-tools.sh', str(setup)).replace('exec /bin/bash --login', 'exec /bin/bash ' + str(shell))
            log = root / 'log'
            result = subprocess.run(['/bin/bash', '-c', command], env=dict(os.environ, Z8_TEST_LOG=str(log), Z8_SHOW_WELCOME='1'), capture_output=True, text=True, timeout=5)
            return result, log.read_text().splitlines()

    def test_success_enters_shell_in_same_process_chain(self):
        result, events = self.run_entrypoint(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ['installed', 'shell'])

    def test_failure_preserves_status_and_does_not_enter_shell_or_retry(self):
        result, events = self.run_entrypoint(42)
        self.assertEqual(result.returncode, 42)
        self.assertEqual(events, ['installed'])
        self.assertIn('Open a new session to retry', result.stdout)

    def test_interruption_has_a_retained_nonzero_status(self):
        result, events = self.run_entrypoint(130)
        self.assertEqual(result.returncode, 75)
        self.assertEqual(events, ['installed'])
