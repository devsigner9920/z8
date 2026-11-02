"""Run the real guest Bash compatibility code against inert CLI fixtures."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUEST = ROOT / "runtime/guest"


class CLIProfileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="z8-cli-profile-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.jsonl"
        self.helper = self.root / "codex-launch.py"
        self.helper_log = self.root / "helper-calls.jsonl"
        self.executable("codex", f"""#!{sys.executable}
import json, os, sys, time
with open(os.environ['Z8_TEST_LOG'], 'a') as output:
    output.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1:] == ['--help']:
    time.sleep(float(os.environ.get('Z8_TEST_HELP_DELAY', '0')))
    print('Usage: codex ' + ('--no-daemon' if os.environ.get('Z8_TEST_SUPPORT', '1') == '1' else '--model'))
    sys.exit(int(os.environ.get('Z8_TEST_HELP_EXIT', '0')))
print(json.dumps(sys.argv[1:]))
sys.exit(int(os.environ.get('Z8_TEST_EXIT', '0')))
""")
        # macOS lacks GNU timeout. Exercise the wrapper's actual timeout argv
        # with an inert bounded subprocess substitute; no guest binary runs.
        self.executable("timeout", f"""#!{sys.executable}
import os, subprocess, sys
assert sys.argv[1:3] == ['-k', '1'], sys.argv
try:
    result = subprocess.run(sys.argv[4:], timeout=min(float(sys.argv[3]), float(os.environ.get('Z8_TEST_TIMEOUT', '5'))))
    sys.exit(result.returncode)
except subprocess.TimeoutExpired:
    sys.exit(124)
""")
        self.profile = self.root / "profile.sh"
        self.profile.write_text(self.fixture_source("cli-profile.sh"))
        self.environment = dict(os.environ, HOME="/z8/home", PATH=f"{self.bin}:/usr/bin:/bin",
                                Z8_TEST_LOG=str(self.log))
        # The parent runner must not provide its own exported shell function.
        self.environment = {key: value for key, value in self.environment.items() if not key.startswith("BASH_FUNC_")}

    def fixture_source(self, name):
        # Remap only the test copy: fallback tests see an absent helper even if
        # a development machine happens to have a managed launcher installed.
        return ((GUEST / name).read_text()
                .replace("/usr/bin/timeout", str(self.bin / "timeout"))
                .replace("/usr/bin/python3", sys.executable)
                .replace("/usr/local/lib/z8/codex-launch.py", str(self.helper)))

    def install_helper(self):
        # Inert delegation endpoint: it records argv and exits without probing
        # or launching Codex, so any fallback/replay is visible in self.log.
        self.helper.write_text("""import json, os, sys
with open(os.environ['Z8_TEST_HELPER_LOG'], 'a') as output:
    output.write(json.dumps(sys.argv[1:]) + '\\n')
sys.exit(int(os.environ['Z8_TEST_HELPER_EXIT']))
""")
        self.environment["Z8_TEST_HELPER_LOG"] = str(self.helper_log)

    def executable(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)
        return path

    def run_shell(self, code, *, interactive=True, before="", **environment):
        flags = ["-i"] if interactive else []
        return subprocess.run(["/bin/bash", "--noprofile", "--norc", *flags, "-c",
                               before + "\n. " + shlex.quote(str(self.profile)) + "\n" + code],
                              env=dict(self.environment, **environment), capture_output=True, text=True, timeout=8)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_lazy_start_and_exact_arguments_and_exit_status(self):
        idle = self.run_shell(":")
        self.assertEqual(idle.returncode, 0, idle.stderr)
        self.assertEqual(self.calls(), [])
        arguments = ["resume", "--last", "spaces ; $(never-execute) 한글\nnext", ""]
        result = self.run_shell("codex " + shlex.join(arguments), Z8_TEST_EXIT="37")
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual(self.calls(), [["--help"], ["--no-daemon", *arguments]])

    def test_explicit_modes_and_help_pass_through_without_probe(self):
        cases = [["--no-daemon", "resume"], ["--remote", "unix:///tmp/server"],
                 ["resume", "--remote=wss://example.invalid"], ["--version"], ["exec", "--help"],
                 ["app-server", "--listen", "stdio://"], ["remote-control", "start"], ["exec-server"]]
        for args in cases:
            with self.subTest(args=args):
                self.log.unlink(missing_ok=True)
                result = self.run_shell("codex " + shlex.join(args))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.calls(), [args])

    def test_option_separator_keeps_prompt_literal(self):
        result = self.run_shell("codex -- --remote")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [["--help"], ["--no-daemon", "--", "--remote"]])

    def test_older_failed_or_timed_out_help_does_not_change_or_replay_request(self):
        for env in ({"Z8_TEST_SUPPORT": "0"}, {"Z8_TEST_HELP_EXIT": "9"},
                    {"Z8_TEST_HELP_DELAY": "2", "Z8_TEST_TIMEOUT": "0.1"}):
            with self.subTest(env=env):
                self.log.unlink(missing_ok=True)
                result = self.run_shell("codex 'one prompt'", **env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.calls(), [["--help"], ["one prompt"]])

    def test_existing_alias_and_function_are_preserved_without_parse_expansion(self):
        for before in ("alias codex='printf alias-kept'", "codex() { printf function-kept; }"):
            with self.subTest(before=before):
                result = self.run_shell("codex", before=before)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("-kept", result.stdout)
                self.assertEqual(self.calls(), [])

    def test_other_home_and_noninteractive_sessions_remain_unchanged(self):
        for options in ({"HOME": str(self.root)}, {"interactive": False}):
            with self.subTest(options=options):
                self.log.unlink(missing_ok=True)
                result = self.run_shell("codex original", **options)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.calls(), [["original"]])

    def test_nested_interactive_bash_inherits_but_scripts_pass_through(self):
        result = self.run_shell("/bin/bash --noprofile --norc -ic 'codex nested'\n"
                                "/bin/bash --noprofile --norc -c 'codex script'")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [["--help"], ["--no-daemon", "nested"], ["script"]])

    def test_repeated_source_does_not_stack_and_changed_capability_is_not_cached(self):
        result = self.run_shell(". " + shlex.quote(str(self.profile)) + "\ncodex first\n"
                                "export Z8_TEST_SUPPORT=0\ncodex second")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [["--help"], ["--no-daemon", "first"], ["--help"], ["second"]])

    def test_probe_recognizes_path_installed_codex_and_claude(self):
        for tool, version in (("codex", "codex-cli 0.162.1"), ("claude", "2.1.285 (Claude Code)")):
            self.executable(tool, "#!/bin/bash\n[ \"$1\" = --version ] || exit 2\nprintf '%s\\n' " + shlex.quote(version) + "\n")
        source = (GUEST / "probe-tools.sh").read_text()
        source = "\n".join("export PATH=" + shlex.quote(str(self.bin)) if line.startswith("export PATH=") else line
                           for line in source.splitlines())
        for tool, version in (("codex", "codex-cli 0.162.1"), ("claude", "2.1.285 (Claude Code)")):
            result = subprocess.run(["/bin/bash", "-c", source, "probe", tool],
                                    env=self.environment, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, tool + "\t" + version + "\n")

    def test_app_action_resolves_path_and_preserves_exit_status(self):
        source = self.fixture_source("guest-task.sh")
        for supported, expected in (("1", ["--no-daemon"]), ("0", [])):
            with self.subTest(supported=supported):
                self.log.unlink(missing_ok=True)
                result = subprocess.run(["/bin/bash", "-c", source, "guest-task", "codex"],
                                        env=dict(self.environment, Z8_TEST_EXIT="31", Z8_TEST_SUPPORT=supported),
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 31, result.stderr)
                self.assertEqual(self.calls(), [["--help"], expected])
                self.assertIn("exit 31", result.stdout)

    def test_installed_helper_receives_absolute_cli_and_exact_arguments_once(self):
        self.install_helper()
        arguments = ["resume", "--last", "--", "spaces ; $(never-execute) 한글\nnext", ""]
        result = self.run_shell("codex " + shlex.join(arguments), Z8_TEST_HELPER_EXIT="43")
        self.assertEqual(result.returncode, 43, result.stderr)
        calls = [json.loads(line) for line in self.helper_log.read_text().splitlines()]
        self.assertEqual(calls, [[str(self.bin / "codex"), *arguments]])
        self.assertTrue(Path(calls[0][0]).is_absolute())
        self.assertEqual(self.calls(), [], "helper return must not probe or replay the CLI")

    def test_app_action_delegates_once_and_preserves_helper_exit_status(self):
        self.install_helper()
        result = subprocess.run(["/bin/bash", "-c", self.fixture_source("guest-task.sh"),
                                 "guest-task", "codex"],
                                env=dict(self.environment, Z8_TEST_HELPER_EXIT="47"),
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 47, result.stderr)
        calls = [json.loads(line) for line in self.helper_log.read_text().splitlines()]
        self.assertEqual(calls, [[str(self.bin / "codex")]])
        self.assertEqual(self.calls(), [], "app action must not probe or replay the CLI")
        self.assertEqual(result.stdout.count("Z8 · codex finished (exit 47)."), 1)

    def test_relative_path_cli_becomes_absolute_for_both_helper_entrypoints(self):
        self.install_helper()
        for entrypoint in ("profile", "app-action"):
            with self.subTest(entrypoint=entrypoint):
                self.helper_log.unlink(missing_ok=True)
                if entrypoint == "profile":
                    arguments = ["relative path prompt"]
                    result = self.run_shell("codex " + shlex.join(arguments),
                                            before="cd " + shlex.quote(str(self.root))
                                            + "\nexport PATH=./bin:/usr/bin:/bin",
                                            Z8_TEST_HELPER_EXIT="49")
                else:
                    arguments = []
                    result = subprocess.run(["/bin/bash", "-c", self.fixture_source("guest-task.sh"),
                                             "guest-task", "codex"], cwd=self.root,
                                            env=dict(self.environment, PATH="./bin:/usr/bin:/bin",
                                                     Z8_TEST_HELPER_EXIT="49"),
                                            capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 49, result.stderr)
                calls = [json.loads(line) for line in self.helper_log.read_text().splitlines()]
                self.assertEqual(len(calls), 1)
                self.assertTrue(Path(calls[0][0]).is_absolute(), calls)
                self.assertEqual(Path(calls[0][0]).resolve(), (self.bin / "codex").resolve())
                self.assertEqual(calls[0][1:], arguments)
                self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
