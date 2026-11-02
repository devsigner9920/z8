#!/usr/bin/env python3
"""Request a real browser from a live z8 terminal; never print or persist URLs.

External URLs use the system browser; literal loopback URLs use the app preview.
The private app socket authenticates this launch and queues while z8 is not visible.
"""
import json
import importlib.util
import os
from pathlib import Path
import re
import socket
import sys
import time
import uuid
from urllib.parse import urlsplit

MAX_URL_BYTES = 8192
MAX_FRAME = 16_384
DEADLINE_SECONDS = 1.5


def valid_url(value):
    # A blank tab is an app action, never an arbitrary about:/data:/file: page.
    if value == "about:blank":
        return True
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > MAX_URL_BYTES:
        return False
    # No whitespace, literal controls/backslashes, userinfo, or encoded controls.
    if any(ord(char) <= 32 or ord(char) == 127 or char == "\\" for char in value):
        return False
    if re.search(r"%(?:0[0-9a-f]|1[0-9a-f]|7f)", value, re.IGNORECASE):
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme.lower() in ("http", "https") and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and (parsed.port is None or 0 < parsed.port <= 65535))
    except (ValueError, UnicodeError):
        return False


def envelope(url, environment):
    launch = environment.get("Z8_LAUNCH_ID", "")
    token = environment.get("Z8_EVENT_TOKEN", "")
    if not valid_url(url) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", launch) or not re.fullmatch(r"[a-f0-9]{64}", token):
        return None
    return {"schemaVersion": 1, "eventId": str(uuid.uuid4()), "launchId": launch,
            "token": token, "kind": "browser", "url": url}


def send(event, path):
    if not isinstance(path, str) or not path.startswith("/") or len(path.encode()) >= 108:
        return False
    frame = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    if len(frame) > MAX_FRAME:
        return False
    deadline = time.monotonic() + DEADLINE_SECONDS
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(DEADLINE_SECONDS)
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


def live(environment):
    """Read-only service lease: no notification, URL, or browser queue entry."""
    event = envelope('about:blank', environment)
    if event is None:
        return False
    event.pop('url')
    event['kind'] = 'preview-check'
    try:
        return send(event, environment.get('Z8_EVENT_SOCKET', ''))
    except (OSError, ValueError, TypeError, TimeoutError, RecursionError):
        return False


def load_preview():
    spec = importlib.util.spec_from_file_location('z8_html_preview', Path(__file__).with_name('html-preview.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(arguments=None, environment=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    environment = os.environ if environment is None else environment
    if arguments == ["--version"]:
        print("z8 browser bridge 1")
        return 0
    if arguments == ["--help"]:
        print("Usage: xdg-open URL | HTML_FILE\nOpens a localhost HTTP(S) preview or a local .html/.htm file in z8, an external HTTP(S) URL with the device browser, or about:blank as a new z8 browser tab. HTML previews serve only their containing folder, support relative assets, and expire after 30 idle minutes or 2 hours. Return to z8 if it is in the background.")
        return 0
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if len(arguments) != 1:
        print("z8: browser requires one HTTP(S) URL, about:blank, or a local .html/.htm file.", file=sys.stderr)
        return 2
    url = arguments[0]
    preview = None
    created = False
    if not valid_url(url):
        # File URLs and arbitrary URI schemes remain unsupported. The selected
        # file gets a narrow HTTP server; WebView file/content access stays off.
        if '://' in url or Path(url).suffix.lower() not in ('.html', '.htm'):
            print("z8: browser requires one HTTP(S) URL, about:blank, or a local .html/.htm file.", file=sys.stderr)
            return 2
        try:
            preview = load_preview()
            url, created = preview.preview_url(url, environment)
        except (OSError, ValueError, TypeError, RuntimeError, ImportError):
            print("z8: HTML preview unavailable. Select an existing .html/.htm file in a regular, non-hidden folder from a live z8 terminal.", file=sys.stderr)
            return 1
    try:
        event = envelope(url, environment)
        if event is not None and send(event, environment.get("Z8_EVENT_SOCKET", "")):
            return 0
    except (OSError, ValueError, TypeError, TimeoutError, RecursionError):
        pass
    if created:
        preview.stop_preview(environment, url)
    # Generic diagnostic deliberately excludes auth URLs, credentials and paths.
    print("z8: browser request unavailable. Return to your live z8 terminal and retry, or open the CLI link manually.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
