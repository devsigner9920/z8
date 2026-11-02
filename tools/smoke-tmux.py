#!/usr/bin/env python3
"""Prove manual own-prefix tmux detach/reattach on the dedicated z8 emulator.

Requires the runtime APK and its matching bootstrap already installed. Does not
install, force-stop, delete user sessions, or inspect attention credentials.
"""
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('z8_tmux_device', ROOT / 'tools/smoke-emulator.py')
device = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(device)
PREFIX = '/data/data/' + device.PACKAGE + '/files/usr'
NATIVE_HOME = '/data/data/' + device.PACKAGE + '/files/home'


def run_as(*arguments, timeout=10, check=True):
    result = subprocess.run([str(device.ADB), '-s', device.SERIAL, 'shell', 'run-as', device.PACKAGE,
                             *arguments], text=True, capture_output=True, timeout=timeout)
    if check and result.returncode:
        # Do not dump arbitrary shell output or process environments on failures.
        raise RuntimeError('App-UID probe command failed with exit code ' + str(result.returncode))
    return result


def checked_runtime():
    if device.adb('shell', 'getprop', 'ro.kernel.qemu') != '1':
        raise RuntimeError('Only the dedicated emulator is allowed')
    if device.adb('emu', 'avd', 'name').splitlines()[0] != 'z8-api37-arm64-16k':
        raise RuntimeError('Refusing to operate an unrelated emulator')
    apk = ROOT / 'artifacts/z8-g0-runtime-arm64.apk'
    metadata = json.loads(apk.with_suffix('.json').read_text())
    with apk.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if metadata.get('sha256') != digest or metadata.get('bootstrapIncluded') is not True:
        raise RuntimeError('Expected a verified runtime APK artifact')
    with zipfile.ZipFile(apk) as archive:
        runtime = json.loads(archive.read('assets/z8-runtime.json'))
    if runtime.get('prefix') != PREFIX or runtime.get('applicationId') != device.PACKAGE:
        raise RuntimeError('Runtime APK has a different package/prefix')
    paths = device.adb('shell', 'pm', 'path', device.PACKAGE).splitlines()
    if len(paths) != 1 or not re.fullmatch(r'package:/data/app/[A-Za-z0-9_./=+~-]+/base\.apk', paths[0]):
        raise RuntimeError('Expected one installed base APK with a safe path')
    installed_hash = device.adb('shell', 'sha256sum', paths[0][8:]).split()[0]
    if installed_hash != digest:
        raise RuntimeError('Installed APK differs from the runtime artifact; install the intended APK first')
    marker = run_as('cat', 'files/usr/.z8-bootstrap.sha256').stdout.strip()
    if not re.fullmatch(r'[0-9a-f]{64}', marker) or marker != runtime.get('sha256'):
        raise RuntimeError('Matching bootstrap is not installed; run the native runtime smoke first')
    pages = int(device.adb('shell', 'getconf', 'PAGESIZE'))
    if pages != 16384:
        raise RuntimeError('This proof requires a real 16 KiB emulator kernel')
    return digest, marker, pages


def open_native_terminal():
    device.adb('shell', 'input', 'keyevent', '224')
    device.adb('shell', 'wm', 'dismiss-keyguard')
    tree = device.diagnostics()
    for attempt in range(8):
        button = next((node for node in tree.iter('node') if node.get('text') == 'Linux 런타임 터미널 열기'), None)
        if button is not None:
            device.click(button)
            break
        if attempt == 7:
            raise RuntimeError('Installed native runtime button was not visible')
        nodes = list(tree.iter('node'))
        bounds = re.findall(r'\d+', nodes[0].get('bounds', '')) if nodes else []
        if len(bounds) != 4:
            raise RuntimeError('Cannot determine the diagnostics viewport')
        left, top, right, bottom = map(int, bounds)
        x = str(left + (right - left) * 4 // 5)
        device.adb('shell', 'input', 'swipe', x, str(top + (bottom - top) * 4 // 5),
                   x, str(top + (bottom - top) // 3), '300')
        tree = device.observe()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        tree = device.observe()
        if any(node.get('resource-id', '').endswith(':id/terminal_view') for node in tree.iter('node')):
            return
        time.sleep(.2)
    raise RuntimeError('Fresh native terminal did not open')


def driver_script(directory, sentinel):
    if not re.fullmatch(r'/data/data/dev\.devsigner\.z8/files/z8/tmux-smoke/[0-9a-f]{12}', directory):
        raise ValueError('Unsafe test directory')
    if not re.fullmatch(r'[0-9a-f]{32}', sentinel):
        raise ValueError('Unsafe synthetic sentinel')
    return r'''# Fixed, generated probe. Never print the shell environment.
_z8_probe_dir='@DIRECTORY@'
_z8_probe_prefix='@PREFIX@'
_z8_probe_tmux() {
    LD_PRELOAD= LD_LIBRARY_PATH="$_z8_probe_prefix/lib" SHELL="$_z8_probe_prefix/bin/bash" \
      HOME='@HOME@' PATH="$_z8_probe_prefix/bin:/system/bin" TERM=xterm-256color \
      "$_z8_probe_prefix/bin/tmux" -f /dev/null -S "$_z8_probe_dir/socket" "$@"
}
_z8_probe_main() {
    case "$1" in
        outer-before)
            [ -n "${BASH_VERSION:-}" ] && [ "${PREFIX:-}" = "$_z8_probe_prefix" ] || return 11
            printf '%s\n' "$$" > "$_z8_probe_dir/outer-before.pid"
            printf '%s\n' "$BASH_VERSION" > "$_z8_probe_dir/bash.version"
            printf '%s\n' "${SHELL:-}" > "$_z8_probe_dir/shell.path"
            /system/bin/toybox readlink "/proc/$$/exe" > "$_z8_probe_dir/outer.exe" || return
            /system/bin/toybox tty > "$_z8_probe_dir/outer.tty" || return
            _z8_probe_tmux -V > "$_z8_probe_dir/tmux.version" || return
            printf '%s\n' Z8_OUTER_BEFORE > "$_z8_probe_dir/outer-before.done"
            ;;
        create)
            [ ! -e "$_z8_probe_dir/socket" ] || return 12
            _z8_probe_tmux new-session -d -s z8_smoke -c "$_z8_probe_dir" \
              "$_z8_probe_prefix/bin/bash --noprofile --norc -i" || return
            _z8_probe_tmux list-panes -t z8_smoke -F '#{pane_pid}' > "$_z8_probe_dir/pane.pid" || return
            printf '%s\n' Z8_CREATED > "$_z8_probe_dir/create.done"
            ;;
        attach) _z8_probe_tmux attach-session -t z8_smoke ;;
        clients) _z8_probe_tmux list-clients -F '#{client_session}|#{client_tty}' ;;
        seed)
            [ -n "${BASH_VERSION:-}" ] && [ -n "${TMUX:-}" ] || return 13
            _Z8_TMUX_SMOKE_SENTINEL='@SENTINEL@'
            printf '%s\n' "$$" > "$_z8_probe_dir/inside-before.pid"
            printf '%s\n' "$_Z8_TMUX_SMOKE_SENTINEL" > "$_z8_probe_dir/inside-before.value"
            /system/bin/toybox readlink "/proc/$$/exe" > "$_z8_probe_dir/inside.exe" || return
            printf '%s\n' "$BASH_VERSION" > "$_z8_probe_dir/inside-bash.version"
            printf '%s\n' Z8_INSIDE_SEEDED > "$_z8_probe_dir/seed.done"
            ;;
        detach) _z8_probe_tmux detach-client -s z8_smoke ;;
        outer-after)
            [ -n "${BASH_VERSION:-}" ] && [ -z "${TMUX:-}" ] || return 14
            printf '%s\n' "$$" > "$_z8_probe_dir/outer-after.pid"
            printf '%s\n' Z8_OUTER_AFTER > "$_z8_probe_dir/outer-after.done"
            ;;
        resumed)
            [ -n "${BASH_VERSION:-}" ] && [ -n "${TMUX:-}" ] || return 15
            printf '%s\n' "$$" > "$_z8_probe_dir/inside-after.pid"
            printf '%s\n' "${_Z8_TMUX_SMOKE_SENTINEL:-}" > "$_z8_probe_dir/inside-after.value"
            printf '%s\n' Z8_TMUX_RESUMED > "$_z8_probe_dir/resumed.done"
            ;;
        cleanup) _z8_probe_tmux kill-server ;;
        *) return 16 ;;
    esac
}
_z8_probe_main "$@"
'''.replace('@DIRECTORY@', directory).replace('@PREFIX@', PREFIX).replace('@HOME@', NATIVE_HOME).replace('@SENTINEL@', sentinel)


def main():
    report_path = device.REPORTS / 'tmux-continuity.json'
    started = datetime.now(timezone.utc).isoformat()
    try:
        digest, bootstrap_hash, pages = checked_runtime()
    except Exception as error:
        device.REPORTS.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({'source': 'EMULATOR', 'status': 'FAIL',
            'startedAtUtc': started, 'phase': 'PREFLIGHT', 'failure': str(error)}, indent=2) + '\n')
        raise
    identifier = uuid.uuid4().hex[:12]
    sentinel = uuid.uuid4().hex
    relative = 'files/z8/tmux-smoke/' + identifier
    directory = '/data/data/' + device.PACKAGE + '/' + relative
    script_path = directory + '/probe.sh'
    pushed = '/data/local/tmp/z8-tmux-' + identifier + '.sh'
    report = {'source': 'EMULATOR', 'status': 'FAIL', 'apkSha256': digest, 'startedAtUtc': started,
              'bootstrapSha256': bootstrap_hash, 'pageSizeBytes': pages,
              'androidRelease': device.adb('shell', 'getprop', 'ro.build.version.release'),
              'apiLevel': int(device.adb('shell', 'getprop', 'ro.build.version.sdk')),
              'managedProductSessionIntegration': 'NOT_TESTED',
              'limitations': ['Explicit tmux probe via an app-created native PTY; not product session management',
                              'Detach uses a separate run-as client of the same UID, not the Ctrl-B d gesture',
                              'No process death, force-stop, screen-off or sustained background workload in this probe',
                              'No PRoot or authenticated AI workload; physical Galaxy hardware remains untested',
                              'Creates one fresh native shell that remains open; existing sessions are preserved']}
    control_ready = False
    try:
        run_as('/system/bin/mkdir', '-p', 'files/z8/tmux-smoke')
        run_as('/system/bin/mkdir', relative)
        run_as('/system/bin/chmod', '700', relative)
        with tempfile.TemporaryDirectory(prefix='z8-tmux-probe-') as staging:
            source = Path(staging) / 'probe.sh'
            source.write_text(driver_script(directory, sentinel))
            device.adb('push', str(source), pushed)
        run_as('/system/bin/cp', pushed, relative + '/probe.sh')
        run_as('/system/bin/chmod', '600', relative + '/probe.sh')
        control_ready = True

        def read(name):
            if not re.fullmatch(r'[a-z.-]+', name):
                raise ValueError('Unsafe proof filename')
            return run_as('/system/bin/cat', relative + '/' + name, timeout=5).stdout.strip()

        def wait(name, expected):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    if read(name) == expected:
                        return
                except RuntimeError:
                    pass
                time.sleep(.2)
            raise RuntimeError('Expected proof was not written: ' + name)

        def ui(phase):
            # Only a fixed path and an enumerated phase enter the real terminal.
            device.command('. ' + script_path + ' ' + phase)

        def control(phase, check=True):
            return run_as('/system/bin/sh', script_path, phase, check=check)

        def attached():
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                clients = control('clients').stdout.strip().splitlines()
                if len(clients) == 1 and re.fullmatch(r'z8_smoke\|/dev/pts/[0-9]+', clients[0]):
                    return clients[0].split('|')[1]
                time.sleep(.2)
            raise RuntimeError('No real PTY client attached to the owned tmux session')

        open_native_terminal()
        ui('outer-before'); wait('outer-before.done', 'Z8_OUTER_BEFORE')
        outer_before = read('outer-before.pid')
        allowed_bash = {PREFIX + '/bin/bash', PREFIX.replace('/data/data/', '/data/user/0/') + '/bin/bash'}
        if not outer_before.isdigit() or read('outer.exe') not in allowed_bash or read('shell.path') != PREFIX + '/bin/bash':
            raise RuntimeError('Fresh terminal did not use the own-prefix native bash/SHELL')
        ui('create'); wait('create.done', 'Z8_CREATED')
        ui('attach'); tty_before = attached()
        ui('seed'); wait('seed.done', 'Z8_INSIDE_SEEDED')
        inside_before = read('inside-before.pid')
        if not inside_before.isdigit() or inside_before != read('pane.pid') or read('inside.exe') not in allowed_bash:
            raise RuntimeError('tmux pane is not the expected own-prefix bash process')
        if read('inside-before.value') != sentinel:
            raise RuntimeError('Initial shell variable proof failed')
        control('detach')
        if control('clients').stdout.strip():
            raise RuntimeError('Owned tmux session still has an attached client')
        # Allow the attached tmux client to restore the terminal before typing.
        time.sleep(.3)
        ui('outer-after'); wait('outer-after.done', 'Z8_OUTER_AFTER')
        outer_after = read('outer-after.pid')
        if outer_after != outer_before:
            raise RuntimeError('Detach did not return to the same original native shell')
        ui('attach'); tty_after = attached()
        ui('resumed'); wait('resumed.done', 'Z8_TMUX_RESUMED')
        inside_after = read('inside-after.pid')
        if inside_after != inside_before or read('inside-after.value') != sentinel:
            raise RuntimeError('Reattachment lost the original tmux pane process or unexported variable')
        device.REPORTS.mkdir(parents=True, exist_ok=True)
        device.capture('emulator-tmux-resumed.png')
        report.update({'status': 'PASS', 'versions': {'bash': read('bash.version'), 'tmux': read('tmux.version'),
                                                     'paneBash': read('inside-bash.version')},
                       'outerPidBefore': outer_before, 'outerPidAfterDetach': outer_after,
                       'panePidBefore': inside_before, 'panePidAfterReattach': inside_after,
                       'unexportedVariablePreserved': True, 'attachedTtyBefore': tty_before,
                       'attachedTtyAfter': tty_after, 'detachReattachCycles': 1,
                       'nativePtyTty': read('outer.tty')})
    except Exception as error:
        report['failure'] = str(error)
        raise
    finally:
        if control_ready:
            try:
                cleanup = run_as('/system/bin/sh', script_path, 'cleanup', check=False)
                report['ownedTmuxCleanup'] = 'PASS' if cleanup.returncode == 0 else 'NO_RUNNING_OWNED_SERVER_OR_FAILED'
            except (RuntimeError, subprocess.TimeoutExpired):
                report['ownedTmuxCleanup'] = 'FAILED'
            if report['status'] == 'PASS' and report['ownedTmuxCleanup'] != 'PASS':
                report['status'] = 'FAIL'
                report['failure'] = 'Continuity passed but owned tmux cleanup did not complete'
        # Only our random upload is removed. The small private proof directory is
        # retained for diagnosis, never included as an environment/transcript dump.
        try:
            device.adb('shell', 'rm', '-f', pushed)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            report['uploadCleanup'] = 'FAILED'
        device.REPORTS.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    if report['status'] != 'PASS':
        raise RuntimeError('tmux probe did not fully pass; inspect ' + str(report_path))


if __name__ == '__main__':
    main()
