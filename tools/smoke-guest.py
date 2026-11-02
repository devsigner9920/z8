#!/usr/bin/env python3
"""Open and verify one prepared emulator fixture project's real Linux guest.

First-time environment preparation now opens a package-installer PTY. Complete
that visible preparation separately; this probe never injects into an installer.
A complete standard tool profile and its actual readiness check are required.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("emulator", ROOT / "tools/smoke-emulator.py")
device = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(device)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Existing fixture project UUID")
    parser.add_argument("--name", required=True, help="Exact existing fixture project label")
    args = parser.parse_args()
    assert str(uuid.UUID(args.project)) == args.project
    assert device.adb("shell", "getprop", "ro.kernel.qemu") == "1"
    assert device.adb("emu", "avd", "name").splitlines()[0] == "z8-api37-arm64-16k"
    # Reuse the read-only installed APK/16KiB/bootstrap identity gate.
    runtime_spec = importlib.util.spec_from_file_location("runtime_gate", ROOT / "tools/smoke-tmux.py")
    runtime = importlib.util.module_from_spec(runtime_spec); runtime_spec.loader.exec_module(runtime)
    apk_hash, bootstrap_hash, _ = runtime.checked_runtime()
    continuity_spec = importlib.util.spec_from_file_location("guest_navigation", ROOT / "tools/smoke-guest-continuity.py")
    navigation = importlib.util.module_from_spec(continuity_spec); continuity_spec.loader.exec_module(navigation)
    device.resume()
    before = navigation.session_snapshot()
    if len(before) >= 8:
        raise RuntimeError("This probe needs one free terminal slot; existing sessions will not be closed")
    shells = navigation.fixture_shells(before, args.name)
    device.prepared_guest(args.project, args.name)
    # A TerminalView can still belong to an older task while guest startup is
    # asynchronous. Confirm the newly added Shell before sending any input.
    navigation.select_created_session(len(before) + 1, args.name, shells + 1)
    identifier = uuid.uuid4().hex
    name = "z8-guest-" + identifier
    script = ROOT / ".local" / (name + ".sh")
    script.write_text('''set -eu
out="$HOME/''' + name + '''"
mkdir -p "$out"
pwd > "$out/cwd"
echo "$HOME" > "$out/home"
echo "$SHELL" > "$out/shell"
echo "$BASH_VERSION" > "$out/bash-version"
echo "$$" > "$out/pid"
uname -m > "$out/architecture"
getconf PAGESIZE > "$out/page-size"
alias ll > "$out/alias-ll"
ll /workspace > "$out/ll-output"
cat /etc/os-release > "$out/os-release"
printf 'Z8_SOURCE_BIND_OK\\n' > /workspace/''' + name + '''.proof
getent ahostsv4 ports.ubuntu.com > "$out/dns"
echo Z8_LINUX_OK > "$out/result"
''')
    source = "files/z8/projects/" + args.project + "/source"
    device.adb("push", str(script), "/data/local/tmp/" + name + ".sh")
    device.adb("shell", "run-as", device.PACKAGE, "cp", "/data/local/tmp/" + name + ".sh", source + "/" + name + ".sh")
    device.command('. /workspace/' + name + '.sh')
    def read(file):
        return device.adb("shell", "run-as", device.PACKAGE, "cat", "files/z8/homes/" + args.project + "/" + name + "/" + file)
    deadline = time.monotonic() + 30
    while True:
        try:
            if read("result") == "Z8_LINUX_OK": break
        except subprocess.CalledProcessError:
            pass
        if time.monotonic() >= deadline:
            device.capture("emulator-guest-failure.png")
            raise RuntimeError("Real guest command failed; inspect the terminal and fixture output")
        time.sleep(1)
    assert read("cwd") == read("home") == "/z8/home"
    assert read("shell") == "/bin/bash"
    assert read("architecture") == "aarch64" and read("page-size") == "16384"
    assert device.adb("shell", "run-as", device.PACKAGE, "cat", source + "/" + name + ".proof") == "Z8_SOURCE_BIND_OK"
    assert read("dns")
    metadata = json.loads((ROOT / "artifacts/z8-g0-runtime-arm64.json").read_text())
    installed_guest = json.loads(device.adb("shell", "run-as", device.PACKAGE, "cat",
        "files/z8/environments/" + args.project + "/rootfs/.z8-environment.json"))
    assert installed_guest["projectId"] == args.project
    report = {
        "source": "EMULATOR", "apkSha256": apk_hash, "bootstrapSha256": bootstrap_hash,
        "status": "PASS", "projectId": args.project,
        "guestImageSha256": installed_guest["archiveSha256"],
        "embeddedGuestImageSha256": metadata.get("guestImageSha256"), "cwd": read("cwd"), "home": read("home"),
        "shell": read("shell"), "bashVersion": read("bash-version"), "pageSizeBytes": int(read("page-size")),
        "osRelease": read("os-release"), "pid": read("pid"), "projectSourceBind": "PASS", "dnsLookup": "PASS",
        "limitations": ["Standard profile prerequisite verified; this probe covers base guest execution, not AI login or agent workflows",
                        "API 37 Pixel Fold emulator; physical Galaxy not tested"],
    }
    (device.REPORTS / "guest-runtime.json").write_text(json.dumps(report, indent=2) + "\n")
    device.capture("emulator-guest-linux.png")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
