#!/usr/bin/env python3
"""Observe a CLI hook; never return a permission decision or print hook output.

Requires Python 3 in the guest. It uses a launch-scoped private socket credential
provided by the app launcher. No transcripts, prompts, tool inputs or paths leave
this process. Failures leave the provider's own approval flow unchanged.
"""
import json
import os
import re
import select
import socket
import sys
import time
import uuid

MAX_FRAME = 16_384
DEADLINE_SECONDS = 0.45
IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")


def normalized_kind(provider, payload):
    event = payload.get("hook_event_name")
    if event == "PermissionRequest":
        return "permission"
    if event == "Stop":
        return "finished"
    if provider == "claude":
        if event == "PreToolUse":
            return {"AskUserQuestion": "question", "ExitPlanMode": "plan"}.get(payload.get("tool_name"))
        if event == "Notification":
            return {"permission_prompt": "permission", "elicitation_dialog": "question",
                    "elicitation_url_dialog": "question"}.get(payload.get("notification_type"))
    # Codex has no generic Notification event, and its question-tool coverage is
    # not established for the Android CLI version. Do not infer from tool text.
    return None


def envelope(provider, payload, environment):
    if provider not in ("claude", "codex") or not isinstance(payload, dict):
        return None
    kind = normalized_kind(provider, payload)
    launch = environment.get("Z8_LAUNCH_ID", "")
    token = environment.get("Z8_EVENT_TOKEN", "")
    if kind is None or not IDENTIFIER.fullmatch(launch) or not re.fullmatch(r"[a-f0-9]{64}", token):
        return None
    event = {"schemaVersion": 1, "eventId": str(uuid.uuid4()), "launchId": launch,
             "token": token, "provider": provider, "kind": kind}
    session = payload.get("session_id")
    if isinstance(session, str) and IDENTIFIER.fullmatch(session):
        event["providerSessionId"] = session
    # Neither current PermissionRequest contract promises a unique request ID.
    # Do not deduplicate distinct approvals by hashing their text/tool arguments.
    return event


def read_input(fd, deadline):
    chunks = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise TimeoutError("Hook input deadline")
        chunk = os.read(fd, min(4096, MAX_FRAME + 1 - len(chunks)))
        if not chunk:
            return json.loads(chunks.decode("utf-8"))
        chunks.extend(chunk)
        if len(chunks) > MAX_FRAME:
            raise ValueError("Hook input too large")


def send(event, path, deadline):
    if not isinstance(path, str) or not path.startswith("/") or len(path.encode()) >= 108:
        return False
    frame = json.dumps(event, separators=(",", ":")).encode() + b"\n"
    if len(frame) > MAX_FRAME:
        return False
    # Exactly one bounded attempt: no growing queue and no approval held hostage.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(max(0.001, deadline - time.monotonic()))
        connection.connect(path)
        connection.sendall(frame)
        answer = bytearray()
        while len(answer) <= 256:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            connection.settimeout(remaining)
            chunk = connection.recv(257 - len(answer))
            if not chunk:
                return False
            answer.extend(chunk)
            if b"\n" in answer:
                response = json.loads(answer.split(b"\n", 1)[0])
                return isinstance(response, dict) and response.get("status") in ("accepted", "duplicate")
    return False


def main():
    # Unknown options must also be quiet: argparse's usual stderr/exit-2 can alter
    # a provider hook outcome. This helper is strictly observational.
    if len(sys.argv) != 3 or sys.argv[1] != "--provider" or sys.argv[2] not in ("claude", "codex"):
        return 0
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        payload = read_input(sys.stdin.fileno(), deadline)
        event = envelope(sys.argv[2], payload, os.environ)
        if event is not None:
            send(event, os.environ.get("Z8_EVENT_SOCKET", ""), deadline)
    except (OSError, ValueError, TypeError, TimeoutError, RecursionError):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
