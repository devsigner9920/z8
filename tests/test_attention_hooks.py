"""Behavior tests for the observational CLI helper with a real local socket."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "runtime/hooks/z8_event.py"
spec = importlib.util.spec_from_file_location("z8_event", HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AttentionHelperTest(unittest.TestCase):
    def test_does_not_forward_private_payload(self):
        payload = {"hook_event_name": "PermissionRequest", "session_id": "session-1",
                   "tool_input": {"command": "TOKEN=secret rm private"}, "transcript_path": "/secret/chat",
                   "cwd": "/private/project", "permission_suggestions": ["allowEverything"]}
        event = module.envelope("claude", payload, {"Z8_LAUNCH_ID": "launch-1", "Z8_EVENT_TOKEN": "a" * 64})
        self.assertEqual(set(event), {"schemaVersion", "eventId", "launchId", "token", "provider", "kind", "providerSessionId"})
        self.assertNotIn("secret", json.dumps(event))
        self.assertEqual(event["kind"], "permission")

    def test_does_not_invent_codex_questions_or_parse_text(self):
        self.assertIsNone(module.normalized_kind("codex", {"hook_event_name": "Notification", "notification_type": "permission_prompt"}))
        self.assertIsNone(module.normalized_kind("codex", {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion"}))
        self.assertIsNone(module.normalized_kind("claude", {"hook_event_name": "Other", "message": "Approve this?"}))
        self.assertEqual(module.normalized_kind("claude", {"hook_event_name": "PreToolUse", "tool_name": "ExitPlanMode"}), "plan")

    def test_distinct_permission_events_keep_distinct_ids(self):
        env = {"Z8_LAUNCH_ID": "launch-1", "Z8_EVENT_TOKEN": "a" * 64}
        payload = {"hook_event_name": "PermissionRequest"}
        self.assertNotEqual(module.envelope("codex", payload, env)["eventId"], module.envelope("codex", payload, env)["eventId"])

    def test_real_socket_delivery_and_silent_success(self):
        with tempfile.TemporaryDirectory(prefix="z8hook-", dir="/tmp") as directory:
            path = str(Path(directory) / "event.sock")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(path); server.listen(1); server.settimeout(2)
            received = []
            def receive():
                with server.accept()[0] as client:
                    received.append(json.loads(client.makefile("rb").readline()))
                    client.sendall(b'{"status":"accepted"}\n')
            worker = threading.Thread(target=receive); worker.start()
            env = dict(os.environ, Z8_EVENT_SOCKET=path, Z8_LAUNCH_ID="launch-1", Z8_EVENT_TOKEN="a" * 64)
            result = subprocess.run([sys.executable, str(HELPER), "--provider", "codex"],
                input=b'{"hook_event_name":"PermissionRequest","tool_input":{"command":"secret"}}',
                capture_output=True, env=env, timeout=2)
            worker.join(2); server.close()
            self.assertFalse(worker.is_alive())
            self.assertEqual(result.returncode, 0)
            self.assertEqual((result.stdout, result.stderr), (b"", b""))
            self.assertEqual(received[0]["kind"], "permission")
            self.assertNotIn("tool_input", received[0])

    def test_broken_socket_invalid_oversized_input_are_silent(self):
        env = dict(os.environ, Z8_EVENT_SOCKET="/tmp/no-z8-socket", Z8_LAUNCH_ID="launch-1", Z8_EVENT_TOKEN="a" * 64)
        for payload in (b"not json", b"x" * 20_000, b'{"hook_event_name":"Stop"}'):
            result = subprocess.run([sys.executable, str(HELPER), "--provider", "claude"],
                input=payload, capture_output=True, env=env, timeout=2)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))

    def test_open_stdin_cannot_hold_permission_forever(self):
        process = subprocess.Popen([sys.executable, str(HELPER), "--provider", "claude"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        start = time.monotonic()
        process.wait(timeout=2)
        self.assertLess(time.monotonic() - start, 1.5)
        self.assertEqual(process.stdout.read(), b"")
        self.assertEqual(process.stderr.read(), b"")
        process.stdin.close(); process.stdout.close(); process.stderr.close()


class HookDeploymentTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("z8_hook_deploy", ROOT / "runtime/hooks/deploy.py")
        self.deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.deploy)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "guest"
        (self.root / "etc/z8").mkdir(parents=True)
        (self.root / "etc/z8/guest-target").write_text("z8-guest-v1\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_and_idempotent_staging_do_not_enable_hooks(self):
        self.assertEqual(self.deploy.stage(self.root)["state"], "dry-run")
        self.assertFalse((self.root / "opt").exists())
        self.deploy.stage(self.root, apply=True)
        self.deploy.stage(self.root, apply=True)
        self.assertEqual({path.name for path in (self.root / "opt/z8/hooks").iterdir()}, set(self.deploy.ASSETS))
        self.assertFalse((self.root / "z8/home/.codex").exists())
        self.assertFalse((self.root / "z8/home/.claude").exists())

    def test_changed_user_asset_preserved_before_any_write(self):
        target = self.root / "opt/z8/hooks"
        target.mkdir(parents=True)
        (target / "codex.hooks.json").write_text("personal hook")
        with self.assertRaises(ValueError):
            self.deploy.stage(self.root, apply=True)
        self.assertEqual([path.name for path in target.iterdir()], ["codex.hooks.json"])
        self.assertEqual((target / "codex.hooks.json").read_text(), "personal hook")

    def test_symlink_escape_and_unmarked_root_rejected(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / "opt").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.deploy.stage(self.root, apply=True)
        self.assertEqual(list(outside.iterdir()), [])
        (self.root / "opt").unlink()
        (self.root / "etc/z8/guest-target").unlink()
        with self.assertRaises(ValueError):
            self.deploy.stage(self.root, apply=True)
        self.assertFalse((self.root / "opt").exists())


if __name__ == "__main__":
    unittest.main()
