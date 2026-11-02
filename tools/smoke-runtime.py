#!/usr/bin/env python3
"""Exercise the source-built Android host runtime on the dedicated z8 emulator."""
import hashlib
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


def visible_button(labels):
    for _ in range(7):
        tree = device.observe()
        found = next((n for n in tree.iter("node") if n.get("text") in labels), None)
        if found is not None:
            return found
        device.adb("shell", "input", "swipe", "1400", "1450", "1400", "600", "350")
    raise RuntimeError("Runtime installation control not visible")


def main():
    assert device.adb("shell", "getprop", "ro.kernel.qemu") == "1"
    assert device.adb("emu", "avd", "name").splitlines()[0] == "z8-api37-arm64-16k"
    apk = ROOT / "artifacts/z8-g0-runtime-arm64.apk"
    metadata = json.loads(apk.with_suffix(".json").read_text())
    digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    assert metadata["sha256"] == digest and metadata["bootstrapIncluded"]
    device.adb("install", "-r", str(apk))
    device.adb("shell", "input", "keyevent", "224")
    device.adb("shell", "wm", "dismiss-keyguard")
    device.diagnostics()
    device.click(visible_button(device.ui.labels('install_runtime') + device.ui.labels('open_runtime')))
    deadline = time.monotonic() + 120
    while True:
        tree = device.observe()
        if any(n.get("resource-id", "").endswith(":id/terminal_view") for n in tree.iter("node")):
            # The install dialog overlays the old terminal until bootstrap is ready.
            try:
                if device.adb("shell", "run-as", device.PACKAGE, "ls", "files/usr/.z8-bootstrap.sha256"):
                    break
            except subprocess.CalledProcessError:
                pass
        if time.monotonic() >= deadline:
            raise RuntimeError("Bootstrap installation did not finish in two minutes")
        time.sleep(1)
    time.sleep(1)
    runtime_spec = importlib.util.spec_from_file_location("runtime_gate", ROOT / "tools/smoke-tmux.py")
    runtime = importlib.util.module_from_spec(runtime_spec); runtime_spec.loader.exec_module(runtime)
    installed_apk_hash, bootstrap_hash, _ = runtime.checked_runtime()
    assert installed_apk_hash == digest
    identifier = uuid.uuid4().hex
    output = "z8-native-" + identifier
    script = ROOT / ".local" / (output + ".sh")
    script.write_text('''set -eu
out="$HOME/''' + output + '''"
mkdir -p "$out"
echo "$BASH_VERSION" > "$out/bash-version"
echo "$PREFIX" > "$out/prefix"
echo "$HOME" > "$out/home"
echo "$$" > "$out/pid"
uname -m > "$out/architecture"
alias ll > "$out/alias-ll"
ll "$HOME" > "$out/ll-output"
"$PREFIX/bin/tmux" -V > "$out/tmux-version" 2>&1
"$PREFIX/bin/proot" --version > "$out/proot-version" 2>&1
"$PREFIX/bin/tar" --version > "$out/tar-version" 2>&1
"$PREFIX/bin/gzip" --version > "$out/gzip-version" 2>&1
echo Z8_NATIVE_OK > "$out/result"
''')
    device.adb("push", str(script), "/data/local/tmp/" + output + ".sh")
    device.adb("shell", "run-as", device.PACKAGE, "cp", "/data/local/tmp/" + output + ".sh", "files/home/" + output + ".sh")
    device.command('. "$HOME/' + output + '.sh"')
    time.sleep(2)
    def read(name):
        return device.read(output + "/" + name)
    assert read("result") == "Z8_NATIVE_OK"
    assert read("prefix") == "/data/data/" + device.PACKAGE + "/files/usr"
    assert read("architecture") == "aarch64"
    assert read("bash-version")
    device.capture("emulator-native-runtime.png")
    report = {
        "source": "EMULATOR", "apkSha256": digest, "status": "PASS",
        "bootstrapSha256": bootstrap_hash,
        "pageSizeBytes": int(device.adb("shell", "getconf", "PAGESIZE")),
        "versions": {name: read(name + "-version") for name in ("bash", "tmux", "proot", "tar", "gzip")},
        "prefix": read("prefix"), "aliasLl": read("alias-ll"),
        "limitations": ["Native runtime smoke only; guest Linux and AI workflows are separate tests",
                        "API 37 Pixel Fold emulator; physical Galaxy not tested"],
    }
    (device.REPORTS / "native-runtime.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
