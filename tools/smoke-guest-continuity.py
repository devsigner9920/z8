#!/usr/bin/env python3
"""Check guest PTY continuity and project inheritance on the dedicated emulator.

Requires an installed matching runtime/bootstrap and an existing fixture guest.
Does not install tools, use credentials, force-stop the app or end any session.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


device = load('z8_continuity_device', 'smoke-emulator.py')
runtime = load('z8_continuity_runtime', 'smoke-tmux.py')


def bounds(node):
    values = re.findall(r'\d+', node.get('bounds', ''))
    if len(values) != 4:
        raise RuntimeError('Observed control has no usable bounds')
    left, top, right, bottom = map(int, values)
    if right <= left or bottom <= top:
        raise RuntimeError('Observed control has empty bounds')
    return left, top, right, bottom


def scroll_forward(tree):
    node = next((item for item in tree.iter('node') if item.get('scrollable') == 'true'), None)
    if node is None:
        raise RuntimeError('Control is not visible and no observed scrollable container is available')
    left, top, right, bottom = bounds(node)
    x = str((left + right) // 2)
    device.adb('shell', 'input', 'swipe', x, str(top + (bottom - top) * 4 // 5),
               x, str(top + (bottom - top) // 4), '300')


def find_text(text, attempts=7):
    for attempt in range(attempts):
        tree = device.observe()
        node = next((item for item in tree.iter('node') if item.get('text') == text and item.get('enabled') != 'false'), None)
        if node is not None:
            return node
        if attempt + 1 < attempts:
            scroll_forward(tree)
    raise RuntimeError('Expected emulator control was not found: ' + text)


def terminal(timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        tree = device.observe()
        node = next((item for item in tree.iter('node') if item.get('resource-id', '').endswith(':id/terminal_view')), None)
        if node is not None:
            return tree, node
        time.sleep(.2)
    raise RuntimeError('No actual terminal view appeared')


def wake():
    device.adb('shell', 'input', 'keyevent', '224')
    device.adb('shell', 'wm', 'dismiss-keyguard')


def resume_current():
    # Launcher navigation never requests session creation or a diagnostic shell.
    device.resume()
    terminal()


def open_fixture(name, project_id):
    device.prepared_guest(project_id, name)
    terminal()


def fold_states(output):
    result = {}
    for identifier, name in re.findall(r"\bidentifier\s*=\s*(\d+)[^}\n]*?\bname\s*=\s*['\"](CLOSED|OPENED)['\"]", output):
        if name in result:
            raise RuntimeError('Ambiguous fold-state names from the emulator')
        result[name] = int(identifier)
    if set(result) != {'CLOSED', 'OPENED'} or result['CLOSED'] == result['OPENED']:
        raise RuntimeError('The emulator did not expose unambiguous CLOSED/OPENED state IDs')
    return result


def fold(identifier):
    device.adb('shell', 'cmd', 'device_state', 'state', str(identifier))
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if device.adb('shell', 'cmd', 'device_state', 'print-state').strip() == str(identifier):
            wake()
            return
        time.sleep(.3)
    raise RuntimeError('Requested fold state did not commit')


def display_ports(output):
    """Validate the dedicated foldable AVD's observed inner/outer displays."""
    displays = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'\s*Display\s+(\d+)\s+\(HWC display\s+(\d+)\):\s*(.+)', line)
        if match is None:
            raise RuntimeError('Unrecognized SurfaceFlinger display record')
        display_id, hwc, details = match.groups()
        ports = re.findall(r'\bport=(\d+)\b', details)
        names = re.findall(r'\bdisplayName="([^"]+)"', details)
        if len(ports) != 1 or len(names) != 1:
            raise RuntimeError('SurfaceFlinger display has missing or ambiguous port/name')
        port = int(ports[0])
        if port not in (0, 1) or int(hwc) != port or names[0] != 'EMU_display_' + str(port):
            raise RuntimeError('Observed displays do not match the dedicated foldable AVD')
        if port in displays or display_id in displays.values():
            raise RuntimeError('Duplicate SurfaceFlinger port or display ID')
        displays[port] = display_id
    if set(displays) != {0, 1}:
        raise RuntimeError('Both inner and outer emulator displays must be present')
    return displays


def capture(name, port):
    if port not in (0, 1):
        raise ValueError('Capture requires an explicit inner/outer display port')
    display_id = display_ports(device.adb('shell', 'dumpsys', 'SurfaceFlinger', '--display-id'))[port]
    # Default screencap can select the inactive inner panel while folded closed.
    device.adb('shell', 'screencap', '-p', '-d', display_id, '/sdcard/z8-smoke.png')
    device.adb('pull', '/sdcard/z8-smoke.png', str(device.REPORTS / name))
    return {'file': name, 'displayId': display_id, 'displayPort': port}


def control(tree, identifier):
    candidates = []
    for node in tree.iter('node'):
        if not node.get('resource-id', '').endswith(':id/' + identifier) or node.get('enabled') == 'false':
            continue
        if node.get('visible-to-user') == 'false':
            continue
        try:
            bounds(node)
        except RuntimeError:
            continue
        candidates.append(node)
    if len(candidates) > 1:
        raise RuntimeError('Ambiguous visible control: ' + identifier)
    return candidates[0] if candidates else None


def session_panel(tree):
    # Only the actual visible drawer or sidebar is used. The legacy controls
    # remain in the APK for upstream clients but are deliberately hidden.
    narrow = control(tree, 'z8_session_drawer')
    return narrow if narrow is not None else control(tree, 'z8_session_sidebar')


def drawer():
    tree = device.observe()
    panel = session_panel(tree)
    if panel is not None:
        return tree, panel
    tree, _ = terminal()
    toggle = control(tree, 'z8_sessions_toggle')
    if toggle is None or toggle.get('clickable') != 'true':
        raise RuntimeError('Actual z8 session toggle is unavailable; no command substitute is allowed')
    device.click(toggle)
    for _ in range(5):
        tree = device.observe()
        panel = session_panel(tree)
        if panel is not None:
            return tree, panel
        time.sleep(.2)
    raise RuntimeError('Actual z8 session panel did not open')


def rows(tree):
    panel = session_panel(tree)
    if panel is None:
        raise RuntimeError('Actual z8 session panel is unavailable')
    result = {}
    for node in panel.iter('node'):
        if not node.get('resource-id', '').endswith(':id/z8_session_row'):
            continue
        description = node.get('content-desc', '')
        if not description.startswith('세션 선택: '):
            raise RuntimeError('Session row has no project/name description')
        fields = description[len('세션 선택: '):].rsplit(' / ', 1)
        identity = fields[0].split(' / ', 1)
        if len(fields) != 2 or len(identity) != 2 or not all(identity) or not fields[1]:
            raise RuntimeError('Invalid session row description')
        key = tuple(identity)
        if key in result:
            raise RuntimeError('Ambiguous project/session names in the visible panel')
        result[key] = node
    return result


def panel_signature(tree):
    panel = session_panel(tree)
    if panel is None:
        raise RuntimeError('Session panel disappeared during traversal')
    return tuple((node.get('text'), node.get('content-desc'), node.get('bounds')) for node in panel.iter('node'))


def scroll_sessions(tree, forward=True):
    panel = session_panel(tree)
    if panel is None:
        raise RuntimeError('Actual z8 session panel is unavailable')
    container = next((node for node in panel.iter('node') if node.get('scrollable') == 'true'
                      and node.get('class') == 'android.widget.ScrollView'), None)
    if container is None:
        return None
    left, top, right, bottom = bounds(container)
    x = str((left + right) // 2)
    upper, lower = top + (bottom - top) // 5, top + (bottom - top) * 4 // 5
    device.adb('shell', 'input', 'swipe', x, str(lower if forward else upper),
               x, str(upper if forward else lower), '250')
    return device.observe()


def panel_start():
    tree, _ = drawer()
    for _ in range(24):
        earlier = scroll_sessions(tree, forward=False)
        if earlier is None or panel_signature(earlier) == panel_signature(tree):
            return tree if earlier is None else earlier
        tree = earlier
    raise RuntimeError('Session panel could not be scrolled to its beginning')


def expand_groups(tree):
    for _ in range(24):
        panel = session_panel(tree)
        if panel is None:
            raise RuntimeError('Session panel disappeared while expanding projects')
        collapsed = next((node for node in panel.iter('node')
                          if node.get('content-desc', '').startswith('프로젝트 세션 목록: ')
                          and node.get('content-desc', '').endswith(' · 접힘')
                          and node.get('clickable') == 'true' and node.get('enabled') != 'false'), None)
        if collapsed is None:
            return tree
        device.click(collapsed)
        tree = device.observe()
    raise RuntimeError('Project groups did not expand within the traversal bound')


def session_snapshot():
    tree = panel_start()
    identities = set()
    for _ in range(24):
        tree = expand_groups(tree)
        identities.update(rows(tree))
        following = scroll_sessions(tree)
        if following is None or panel_signature(following) == panel_signature(tree):
            if not 0 <= len(identities) <= 8:
                raise RuntimeError('The actual session panel did not expose 0–8 unambiguous sessions')
            return identities
        tree = following
    raise RuntimeError('Session panel traversal exceeded its bound')


def fixture_shells(snapshot, project_name):
    # Terminal numbers are durable high-water marks, not a 1..active-count suffix.
    return sum(1 for project, name in snapshot if project == project_name
               and re.fullmatch(r'Terminal [1-9][0-9]{0,95}', name))


def select_created_session(expected_total, project_name, expected_shells):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        snapshot = session_snapshot()
        if len(snapshot) == expected_total and fixture_shells(snapshot, project_name) == expected_shells:
            # A newly allocated Terminal has a larger number than existing titles,
            # including after previous terminals were deleted or renamed.
            candidates = [key for key in snapshot if key[0] == project_name
                          and re.fullmatch(r'Terminal [1-9][0-9]{0,95}', key[1])]
            if not candidates:
                raise RuntimeError('No numbered fixture Terminal is available')
            key = max(candidates, key=lambda item: int(item[1].split(' ', 1)[1]))
            tree = panel_start()
            for _ in range(24):
                node = rows(tree).get(key)
                if node is not None:
                    if node.get('clickable') != 'true' or node.get('enabled') == 'false':
                        raise RuntimeError('New fixture Shell row is not selectable')
                    # Select the observed new row; a TerminalView alone can still
                    # belong to an older PTY during asynchronous guest setup.
                    device.click(node)
                    tree, _ = terminal()
                    current = control(tree, 'z8_current_project')
                    if current is None or current.get('text') != project_name:
                        raise RuntimeError('Selected Shell does not identify the fixture project')
                    selected = [tab for tab in tree.iter('node')
                                if tab.get('resource-id', '').endswith(':id/z8_session_tab')
                                and tab.get('selected') == 'true']
                    label = '세션 전환: ' + project_name + ' / ' + key[1] + ' / '
                    if len(selected) != 1 or not selected[0].get('content-desc', '').startswith(label):
                        raise RuntimeError('The actual selected tab does not identify the new fixture Shell')
                    time.sleep(.4)
                    return
                following = scroll_sessions(tree)
                if following is None or panel_signature(following) == panel_signature(tree):
                    break
                tree = following
        time.sleep(.2)
    raise RuntimeError('No new fixture Shell appeared in the actual z8 session panel')


def wait_direct_shell(project_name):
    """Observe direct Terminal creation; never dismiss or select a session chooser."""
    deadline = time.monotonic() + 20
    prefix = '세션 전환: ' + project_name + ' / '
    while time.monotonic() < deadline:
        tree = device.observe()
        if any(node.get('text') in ('새 세션의 프로젝트', project_name + ' · 새 세션')
               for node in tree.iter('node')):
            raise RuntimeError('New-session creation unexpectedly opened a chooser')
        current = control(tree, 'z8_current_project')
        selected = [node for node in tree.iter('node')
                    if node.get('resource-id', '').endswith(':id/z8_session_tab')
                    and node.get('selected') == 'true']
        if current is not None and current.get('text') == project_name and len(selected) == 1:
            description = selected[0].get('content-desc', '')
            if description.startswith(prefix):
                parts = description[len(prefix):].rsplit(' / ', 1)
                if len(parts) == 2 and parts[1] and re.fullmatch(r'Terminal [1-9][0-9]{0,95}', parts[0]) \
                        and control(tree, 'terminal_view') is not None:
                    time.sleep(.4)
                    return parts[0]
        time.sleep(.25)
    raise RuntimeError('Direct Shell creation did not select the expected fixture project')


def new_session_control(project_name):
    tree = device.observe()
    if control(tree, 'z8_session_drawer') is not None:
        # Back closes only an observed narrow drawer. Never use it on the wide
        # sidebar, where Android Back would leave the terminal Activity.
        device.adb('shell', 'input', 'keyevent', '4')
    tree, _ = terminal()
    current = control(tree, 'z8_current_project')
    button = control(tree, 'z8_new_session')
    if current is None or current.get('text') != project_name or button is None or button.get('clickable') != 'true':
        raise RuntimeError('Actual new-session control is not attached to the fixture project')
    device.click(button)
    wait_direct_shell(project_name)


def probe_script(identifier, sentinel):
    if not re.fullmatch(r'[0-9a-f]{12}', identifier) or not re.fullmatch(r'[0-9a-f]{32}', sentinel):
        raise ValueError('Invalid generated fixture identifier')
    return r'''# Source in the actual interactive guest shell; never inspect its environment.
_z8_continuity_probe() {
    case "$1" in seed|after-home|after-closed|after-opened|new-session) ;; *) return 2 ;; esac
    [ "${HOME:-}" = /z8/home ] && [ "${SHELL:-}" = /bin/bash ] && [ -n "${BASH_VERSION:-}" ] || return 3
    [ "$(cat /workspace/z8-continuity-@ID@.source)" = '@VALUE@' ] || return 4
    mkdir -p /z8/home/z8-continuity-@ID@ || return
    if [ "$1" = seed ]; then _Z8_GUEST_CONTINUITY_VALUE='@VALUE@'; fi
    printf '%s\n' "$$" > "/z8/home/z8-continuity-@ID@/$1.pid"
    printf '%s\n' "${_Z8_GUEST_CONTINUITY_VALUE:-}" > "/z8/home/z8-continuity-@ID@/$1.value"
    printf '%s\n' "$HOME" > "/z8/home/z8-continuity-@ID@/$1.home"
    printf '%s\n' "$SHELL" > "/z8/home/z8-continuity-@ID@/$1.shell"
    printf '%s\n' "$BASH_VERSION" > "/z8/home/z8-continuity-@ID@/$1.bash"
    pwd > "/z8/home/z8-continuity-@ID@/$1.cwd"
    printf '%s\n' Z8_PROJECT_SOURCE_OK > "/workspace/z8-continuity-@ID@.$1.proof"
    printf '%s\n' Z8_GUEST_CONTINUITY_OK > "/z8/home/z8-continuity-@ID@/$1.done"
}
_z8_continuity_probe "$@"
'''.replace('@ID@', identifier).replace('@VALUE@', sentinel)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='Existing fixture project UUID')
    parser.add_argument('--name', required=True, help='Exact visible fixture project label')
    args = parser.parse_args()
    if str(uuid.UUID(args.project)) != args.project:
        parser.error('Use the canonical fixture project UUID')
    identifier, sentinel = uuid.uuid4().hex[:12], uuid.uuid4().hex
    stem = 'z8-continuity-' + identifier
    source = 'files/z8/projects/' + args.project + '/source'
    home = 'files/z8/homes/' + args.project + '/' + stem
    uploads = []
    original_state = None
    report = {'source': 'EMULATOR', 'status': 'FAIL', 'projectId': args.project,
              'startedAtUtc': datetime.now(timezone.utc).isoformat(),
              'limitations': ['Activity/configuration handling only; no process death, force-stop or reboot',
                              'One Home/return and CLOSED/OPENED cycle on the dedicated emulator',
                              'No tmux recovery, AI login or authenticated workflow in this probe',
                              'Physical Galaxy hardware and sustained battery/background behavior are not tested',
                              'Two test guest sessions and small fixture proof files remain; existing sessions are preserved']}
    try:
        apk_hash, bootstrap_hash, pages = runtime.checked_runtime()
        report.update(apkSha256=apk_hash, bootstrapSha256=bootstrap_hash, pageSizeBytes=pages)
        installed = json.loads(runtime.run_as('/system/bin/cat', 'files/z8/environments/' + args.project + '/rootfs/.z8-environment.json').stdout)
        if installed.get('projectId') != args.project or not re.fullmatch(r'[0-9a-f]{64}', installed.get('archiveSha256', '')):
            raise RuntimeError('Fixture installed-guest marker is invalid')
        report['guestImageSha256'] = installed['archiveSha256']
        states = fold_states(device.adb('shell', 'cmd', 'device_state', 'print-states'))
        original_state = device.adb('shell', 'cmd', 'device_state', 'print-state').strip()
        if not original_state.isdigit():
            raise RuntimeError('Cannot read the original committed fold state')
        with tempfile.TemporaryDirectory(prefix='z8-guest-continuity-') as temporary:
            directory = Path(temporary)
            for suffix, content in (('.sh', probe_script(identifier, sentinel)), ('.source', sentinel + '\n')):
                path = directory / (stem + suffix)
                path.write_text(content)
                uploaded = '/data/local/tmp/' + path.name
                uploads.append(uploaded)
                device.adb('push', str(path), uploaded)
                runtime.run_as('/system/bin/cp', uploaded, source + '/' + path.name)

        def read(name):
            return runtime.run_as('/system/bin/cat', home + '/' + name, timeout=5).stdout.strip()

        def proof(phase, same_pid=None, fresh=False):
            device.command('. /workspace/' + stem + '.sh ' + phase)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    if read(phase + '.done') == 'Z8_GUEST_CONTINUITY_OK':
                        break
                except RuntimeError:
                    pass
                time.sleep(.25)
            else:
                raise RuntimeError('Guest proof missing after ' + phase + '; refusing to infer session continuity')
            pid, value = read(phase + '.pid'), read(phase + '.value')
            if not pid.isdigit() or read(phase + '.home') != '/z8/home' or read(phase + '.cwd') != '/z8/home' or read(phase + '.shell') != '/bin/bash':
                raise RuntimeError('Expected project guest HOME/cwd/shell was not preserved after ' + phase)
            if fresh:
                if pid == same_pid or value:
                    raise RuntimeError('NEW SESSION did not create a fresh, independent guest shell')
            elif (same_pid is not None and pid != same_pid) or value != sentinel:
                raise RuntimeError('Guest PID or unexported shell variable changed after ' + phase)
            source_proof = runtime.run_as('/system/bin/cat', source + '/' + stem + '.' + phase + '.proof').stdout.strip()
            if source_proof != 'Z8_PROJECT_SOURCE_OK':
                raise RuntimeError('Project source bind proof failed')
            report.setdefault('phases', {})[phase] = {'pid': pid, 'home': '/z8/home', 'cwd': '/z8/home',
                'shell': '/bin/bash', 'bashVersion': read(phase + '.bash'), 'projectSourceBind': 'PASS',
                'unexportedVariable': 'ABSENT_IN_NEW_SHELL' if fresh else 'PRESERVED'}
            return pid

        wake(); device.resume()
        before = session_snapshot()
        before_sessions = len(before)
        before_shells = fixture_shells(before, args.name)
        if before_sessions > 6:
            raise RuntimeError('This probe needs two free terminal slots; existing sessions will not be closed')
        open_fixture(args.name, args.project)
        select_created_session(before_sessions + 1, args.name, before_shells + 1)
        pid = proof('seed')
        device.adb('shell', 'input', 'keyevent', '3')
        time.sleep(10)
        wake(); resume_current(); proof('after-home', pid)
        device.REPORTS.mkdir(parents=True, exist_ok=True)
        report.setdefault('screenshots', {})['after-home'] = capture('emulator-guest-after-home.png', 0)
        for state in ('CLOSED', 'OPENED'):
            fold(states[state]); resume_current(); proof('after-' + state.lower(), pid)
            report['screenshots'][state.lower()] = capture('emulator-guest-' + state.lower() + '.png',
                                                          1 if state == 'CLOSED' else 0)
        new_session_control(args.name)
        select_created_session(before_sessions + 2, args.name, before_shells + 2)
        new_pid = proof('new-session', pid, fresh=True)
        report['screenshots']['new-session'] = capture('emulator-guest-new-session.png', 0)
        report.update(status='PASS', backgroundWaitSeconds=10, foldStates=states,
                      originalGuestPid=pid, newGuestPid=new_pid, drawerNewSession='PASS',
                      diagnosticFallbackObserved=False, finalFoldState='OPENED')
    except Exception as error:
        report['failure'] = str(error)
        if original_state is not None:
            try:
                device.adb('shell', 'cmd', 'device_state', 'state', original_state)
                wake()
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                report['foldRestore'] = 'FAILED'
        raise
    finally:
        for uploaded in uploads:
            try:
                device.adb('shell', 'rm', '-f', uploaded)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                report['uploadCleanup'] = 'FAILED'
        device.REPORTS.mkdir(parents=True, exist_ok=True)
        (device.REPORTS / 'guest-continuity.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
