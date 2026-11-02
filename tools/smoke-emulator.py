#!/usr/bin/env python3
"""Exercise the diagnostic APK on the dedicated z8 emulator, never a physical device."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ADB = ROOT / '.local/android-sdk/platform-tools/adb'
SERIAL = 'emulator-5580'
PACKAGE = 'dev.devsigner.z8'
REPORTS = ROOT / 'reports/compatibility'
_UI_SPEC = importlib.util.spec_from_file_location('z8_smoke_ui', Path(__file__).with_name('smoke_ui.py'))
ui = importlib.util.module_from_spec(_UI_SPEC)
_UI_SPEC.loader.exec_module(ui)


def adb(*args):
    return subprocess.check_output([str(ADB), '-s', SERIAL, *args], text=True, timeout=30).strip()


def screen():
    # uiautomator can report a null root with exit code 0 during transitions.
    # Remove the prior dump so a failed capture cannot masquerade as fresh UI.
    for _ in range(3):
        adb('shell', 'rm', '-f', '/sdcard/z8-smoke-window.xml')
        adb('shell', 'uiautomator', 'dump', '/sdcard/z8-smoke-window.xml')
        try:
            tree = ET.fromstring(adb('shell', 'cat', '/sdcard/z8-smoke-window.xml'))
            if list(tree.iter('node')):
                return tree
        except (subprocess.CalledProcessError, ET.ParseError):
            pass
        time.sleep(0.5)
    raise RuntimeError('No fresh emulator UI hierarchy; refusing to use an old dump')


def click(node):
    left, top, right, bottom = map(int, re.findall(r'\d+', node.attrib['bounds']))
    adb('shell', 'input', 'tap', str((left + right) // 2), str((top + bottom) // 2))


def observe():
    tree = screen()
    # The G0 target uses Android's normal first-channel permission prompt.
    # Grant only notification permission for our own emulator-installed app.
    if any(n.get('text', '') in ('Allow z8 to send you notifications?', 'Allow z8 G0 to send you notifications?') for n in tree.iter('node')):
        allow = next(n for n in tree.iter('node') if n.get('resource-id', '').endswith(':id/permission_allow_button'))
        click(allow)
        tree = screen()
    return tree


def terminal_action(label):
    """Follow observed Settings controls without inventing a project or session."""
    # Preserve the historical helper API while following the current settings UI.
    key = {'실행 진단': 'diagnostics', '개발 환경': 'environment'}.get(label, label)
    labels = ui.labels(key) if key in ui.LABELS else (label,)
    tree = observe()
    if any(node.get('resource-id', '').endswith(':id/z8_session_drawer')
           and node.get('visible-to-user') != 'false' for node in tree.iter('node')):
        adb('shell', 'input', 'keyevent', '4')
        tree = observe()
    def matches(attribute, value):
        return [node for node in tree.iter('node')
                if ui.matches(node.get(attribute), value) and node.get('enabled') != 'false'
                and node.get('visible-to-user') != 'false']
    actions = matches('text', labels)
    if not actions:
        menus = matches('content-desc', ui.labels('settings'))
        if len(menus) != 1:
            raise RuntimeError('Expected one observed terminal menu before ' + label)
        click(menus[0])
        tree = observe()
        actions = matches('text', labels)
        # Developer settings can be below the fold. Scroll only observed bounds.
        for _ in range(7):
            if actions:
                break
            scroll = [node for node in tree.iter('node') if node.get('scrollable') == 'true'
                      and node.get('visible-to-user') != 'false']
            if len(scroll) != 1:
                break
            bounds = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', scroll[0].get('bounds', ''))
            if bounds is None:
                break
            left, top, right, bottom = map(int, bounds.groups())
            if right <= left or bottom <= top:
                break
            x = str((left + right) // 2)
            adb('shell', 'input', 'swipe', x, str(top + (bottom - top) * 4 // 5),
                x, str(top + (bottom - top) // 5), '300')
            tree = observe()
            actions = matches('text', labels)
    if len(actions) != 1:
        raise RuntimeError('Expected one observed terminal action: ' + label)
    click(actions[0])
    return observe()


def resume(project_id=None, show_sessions=False):
    """Navigate only: MAIN and optional focus must never launch a new PTY."""
    arguments = ['shell', 'am', 'start', '-W', '-a', 'android.intent.action.MAIN', '-c',
                 'android.intent.category.LAUNCHER', '-f', '0x10200000', '-n',
                 PACKAGE + '/com.termux.app.TermuxActivity']
    if project_id is not None:
        if str(uuid.UUID(project_id)) != project_id:
            raise ValueError('Use a canonical fixture project UUID')
        arguments.extend(['--es', PACKAGE + '.FOCUS_PROJECT_ID', project_id])
    if show_sessions:
        arguments.extend(['--ez', PACKAGE + '.SHOW_SESSIONS', 'true'])
    adb(*arguments)
    tree = observe()
    setup = next((n for n in tree.iter('node') if n.get('text') in ui.labels('start_theme')), None)
    if setup is not None:
        click(setup)
        tree = observe()
    deadline = time.monotonic() + 20
    while not any(node.get('resource-id', '').endswith((':id/terminal_view', ':id/z8_sessions_toggle'))
                  for node in tree.iter('node')):
        if time.monotonic() >= deadline:
            raise RuntimeError('Terminal launcher did not open')
        tree = observe()
    return tree


def diagnostics():
    resume()
    return terminal_action('실행 진단')


def prepared_guest(project_id, project_name):
    """Open only the ready-profile Shell control, never a package installer."""
    if str(uuid.UUID(project_id)) != project_id:
        raise ValueError('Use a canonical fixture project UUID')
    try:
        marker = adb('shell', 'run-as', PACKAGE, 'cat',
                     'files/z8/environments/' + project_id + '/rootfs/etc/z8/tools.ready')
    except subprocess.CalledProcessError as error:
        raise RuntimeError('Complete standard development-tool preparation before this shell probe') from error
    if marker != 'z8-tools-v2':
        raise RuntimeError('Fixture has no current standard development-tool profile; prepare it before this probe')
    tree = resume(project_id)
    current = [node for node in tree.iter('node')
               if node.get('resource-id', '').endswith(':id/z8_current_project')]
    if len(current) != 1 or current[0].get('text') != project_name:
        raise RuntimeError('Focused project does not match the requested fixture')
    terminal_action('개발 환경')
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        tree = observe()
        nodes = list(tree.iter('node'))
        if any(node.get('resource-id', '').endswith(':id/terminal_view') for node in nodes):
            raise RuntimeError('Unexpected terminal during environment check; refusing a possible installer PTY')
        if any(node.get('text') in ui.labels('setup_environment') for node in nodes):
            raise RuntimeError('Fixture is not prepared; complete the visible setup before this shell probe')
        ready = any(node.get('text') in ui.labels('tools_ready') for node in nodes)
        buttons = [node for node in nodes if node.get('text') in ui.labels('open_terminal')
                   and node.get('enabled') != 'false' and node.get('visible-to-user') != 'false']
        if ready and len(buttons) == 1:
            click(buttons[0])
            return
        if any(node.get('text') in ui.labels('tools_needed') + ui.labels('tools_delayed') for node in nodes):
            raise RuntimeError('Actual standard-tool verification is incomplete; prepare/recheck it before this shell probe')
        time.sleep(.3)
    raise RuntimeError('Prepared development profile did not become ready; no Shell or installer was selected')


def command(text):
    # adb shell joins arguments on the guest; quote the text a second time.
    adb('shell', 'input', 'text', shlex.quote(text))
    adb('shell', 'input', 'keyevent', '66')


def read(name):
    return adb('shell', 'run-as', PACKAGE, 'cat', 'files/home/' + name)


def capture(name):
    adb('shell', 'screencap', '-p', '/sdcard/z8-smoke.png')
    adb('pull', '/sdcard/z8-smoke.png', str(REPORTS / name))


def main():
    assert adb('shell', 'getprop', 'ro.kernel.qemu') == '1', 'Only the dedicated emulator is allowed'
    avd = adb('emu', 'avd', 'name').splitlines()[0]
    assert avd == 'z8-api37-arm64-16k', 'Refusing to use an unrelated emulator'
    apk = ROOT / 'artifacts/z8-g0-diagnostic-arm64.apk'
    metadata = json.loads(apk.with_suffix('.json').read_text())
    with apk.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert metadata['sha256'] == digest and not metadata['bootstrapIncluded']
    REPORTS.mkdir(exist_ok=True)
    print(adb('install', '-r', str(apk)), flush=True)
    tree = diagnostics()
    diagnostic = [node for node in tree.iter('node') if node.get('text') in ui.labels('diagnostic_shell')]
    if len(diagnostic) != 1:
        raise RuntimeError('Explicit Android diagnostic Shell control is not visible')
    # Android aliases /data/data and /data/user/0 with mounts, not necessarily symlinks.
    identity = adb('shell', 'run-as', PACKAGE, 'stat', '-c', '%d:%i',
                   '/data/data/' + PACKAGE + '/files', '/data/user/0/' + PACKAGE + '/files').splitlines()
    assert len(identity) == 2 and identity[0] == identity[1], 'App prefix identity failed'
    click(diagnostic[0])
    resume()
    token = 'z8_' + uuid.uuid4().hex
    command('Z8_SESSION_TOKEN=' + token + '; echo $$ > "$HOME/z8-g0-pid"; '
            'echo Z8_PTY_OK > "$HOME/z8-g0-proof"; id; pwd; uname -m; echo Z8_PTY_OK')
    pid, proof = read('z8-g0-pid'), read('z8-g0-proof')
    assert pid.isdigit() and proof == 'Z8_PTY_OK'
    adb('shell', 'input', 'keyevent', '3')
    time.sleep(10)
    resume()
    command('echo $$ > "$HOME/z8-g0-return-pid"; echo $Z8_SESSION_TOKEN > "$HOME/z8-g0-return-token"; echo Z8_RESUMED')
    returned = read('z8-g0-return-pid')
    assert pid == returned and read('z8-g0-return-token') == token, 'Home/return lost the original shell'
    try:
        adb('shell', 'wm', 'user-rotation', 'lock', '1')
        tree = observe()
        assert tree.attrib['rotation'] == '1', 'Rotation did not occur'
        command('echo $$ > "$HOME/z8-g0-rotate-pid"; echo $Z8_SESSION_TOKEN > "$HOME/z8-g0-rotate-token"; echo Z8_ROTATION_OK')
        rotated = read('z8-g0-rotate-pid')
        assert pid == rotated and read('z8-g0-rotate-token') == token, 'Rotation lost the original shell'
    finally:
        adb('shell', 'wm', 'user-rotation', 'free')
    capture('emulator-terminal.png')
    result = {
        'source': 'EMULATOR', 'apkSha256': digest,
        'androidRelease': adb('shell', 'getprop', 'ro.build.version.release'),
        'apiLevel': int(adb('shell', 'getprop', 'ro.build.version.sdk')),
        'pageSizeBytes': int(adb('shell', 'getconf', 'PAGESIZE')),
        'ptyCommandResult': proof, 'pidBefore': pid, 'pidAfterHome': returned,
        'pidAfterRotation': rotated, 'shellVariablePreserved': True,
        'backgroundWaitSeconds': 10, 'rotationCycles': 1, 'smokeStatus': 'PASS',
        'g0GateStatus': 'NOT_TESTED',
        'limitations': ['ADB installation; stock device installation UI not tested',
                        'Pixel Fold emulator with 4GB RAM; not Galaxy hardware or 8GB acceptance',
                        'One short home/return and one rotation only',
                        'No Linux bootstrap, PRoot, tmux, AI CLI or hook integration'],
    }
    (REPORTS / 'emulator-smoke.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
