#!/usr/bin/env python3
"""Exercise the live same-UID hook channel on the dedicated emulator shell.

Requires an already open app-owned diagnostic terminal. Secrets stay in that
shell's environment and are never copied to host output or test artifacts.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import time

spec = importlib.util.spec_from_file_location('z8_smoke', Path(__file__).with_name('smoke-emulator.py'))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def main():
    assert smoke.adb('shell', 'getprop', 'ro.kernel.qemu') == '1'
    assert smoke.adb('emu', 'avd', 'name').splitlines()[0] == 'z8-api37-arm64-16k'
    script = r'''set -eu
: "${Z8_EVENT_SOCKET:?}" "${Z8_EVENT_TOKEN:?}" "${Z8_LAUNCH_ID:?}"
z8_test_id="smoke-$$-$(date +%s)"
z8_test_event=$(printf '{"schemaVersion":1,"eventId":"%s","launchId":"%s","token":"%s","provider":"diagnostic","kind":"question"}' "$z8_test_id" "$Z8_LAUNCH_ID" "$Z8_EVENT_TOKEN")
z8_send() { /system/bin/toybox nc -U -w 2 -W 2 "$Z8_EVENT_SOCKET"; }
printf '%s\n' "$z8_test_event" | z8_send > "$HOME/z8-hook-accepted"
printf '%s\n' "$z8_test_event" | z8_send > "$HOME/z8-hook-duplicate"
printf '{"schemaVersion":1,"eventId":"bad-token","launchId":"%s","token":"%064d","provider":"diagnostic","kind":"question"}\n' "$Z8_LAUNCH_ID" 0 | z8_send > "$HOME/z8-hook-unauthorized"
printf '{"schemaVersion":1,"unexpected":"field"}\n' | z8_send > "$HOME/z8-hook-invalid"
{ head -c 20000 /dev/zero | tr '\000' x; printf '\n'; } | z8_send > "$HOME/z8-hook-oversize" || :
printf '%s\n' "$z8_test_event" | z8_send > "$HOME/z8-hook-recovery"
unset z8_test_event
echo Z8_HOOK_PROTOCOL_DONE > "$HOME/z8-hook-protocol-done"
'''
    subprocess.run([str(smoke.ADB), '-s', smoke.SERIAL, 'shell', 'run-as', smoke.PACKAGE,
                    'tee', 'files/home/z8-hook-test.sh'], input=script, text=True,
                   stdout=subprocess.DEVNULL, check=True, timeout=30)
    smoke.adb('shell', 'run-as', smoke.PACKAGE, 'rm', '-f', 'files/home/z8-hook-protocol-done')
    smoke.command('sh "$HOME/z8-hook-test.sh"')
    for attempt in range(10):
        time.sleep(1)
        try:
            if smoke.read('z8-hook-protocol-done') == 'Z8_HOOK_PROTOCOL_DONE':
                break
        except subprocess.CalledProcessError:
            pass
    else:
        raise RuntimeError('Live hook protocol test did not complete')
    checks = {}
    for name, expected in (('accepted', 'accepted'), ('duplicate', 'duplicate'),
                           ('unauthorized', 'unauthorized'), ('invalid', 'invalid'),
                           ('recovery', 'duplicate')):
        observed = json.loads(smoke.read('z8-hook-' + name))['status']
        assert observed == expected, (name, observed)
        checks[name] = observed
    assert not smoke.read('z8-hook-oversize'), 'Oversized frame unexpectedly received ACK'
    checks['oversizedFrameRejected'] = True
    report_path = smoke.REPORTS / 'attention-notifications.json'
    report = json.loads(report_path.read_text())
    report['protocolChecks'] = checks
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(checks, indent=2))


if __name__ == '__main__':
    main()
