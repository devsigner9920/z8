#!/usr/bin/env python3
"""Exercise project/session navigation on the dedicated foldable emulator.

Creates fixture sessions and tiny proof files in two explicitly selected projects.
Only the Scratch session created by this run is explicitly terminated. No login,
network mutation, sandbox policy change, force-stop or existing-session closure.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('z8_navigation_helpers', ROOT / 'tools/smoke-guest-continuity.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
d, r = c.device, c.runtime


def node(**attrs):
    tree = d.observe()
    matches = [n for n in tree.iter('node') if all(n.get(k) == v for k, v in attrs.items())]
    if len(matches) != 1:
        raise RuntimeError('Expected one visible UI control: ' + str(attrs) + ', found ' + str(len(matches)))
    return matches[0]


def press(**attrs):
    d.click(node(**attrs))


def selected():
    tree, _ = c.terminal()
    project = next(n.get('text') for n in tree.iter('node') if n.get('resource-id', '').endswith(':id/z8_current_project'))
    tab = next(n.get('text') for n in tree.iter('node') if n.get('resource-id', '').endswith(':id/z8_session_tab') and n.get('selected') == 'true')
    return project, tab


def wait_selected(project, title=None):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        actual = selected()
        if actual[0] == project and (title is None or actual[1] == title):
            time.sleep(.5)
            return
        time.sleep(.25)
    raise RuntimeError('Selected project/session did not settle: ' + str(actual))


def open_session_menu():
    """Long-press the uniquely selected, observed terminal tab; never a stale header action."""
    tree = d.observe()
    matches = [item for item in tree.iter('node')
               if item.get('resource-id') == d.PACKAGE + ':id/z8_session_tab'
               and item.get('selected') == 'true' and item.get('clickable') == 'true'
               and item.get('enabled') != 'false' and item.get('long-clickable') != 'false'
               and item.get('visible-to-user') != 'false'
               and item.get('content-desc', '').startswith('세션 전환: ')]
    if len(matches) != 1:
        raise RuntimeError('Expected one selected terminal tab for its session menu')
    bounds = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', matches[0].get('bounds', ''))
    if bounds is None:
        raise RuntimeError('Selected terminal tab has no valid observed bounds')
    left, top, right, bottom = map(int, bounds.groups())
    if right <= left or bottom <= top:
        raise RuntimeError('Selected terminal tab has no usable observed bounds')
    x, y = str((left + right) // 2), str((top + bottom) // 2)
    d.adb('shell', 'input', 'swipe', x, y, x, y, '900')


def rename(title):
    open_session_menu()
    press(text='이름 변경')
    entry = node(**{'class': 'android.widget.EditText'})
    d.click(entry)
    # Wait for IME focus before injecting text. Fast ADB input immediately after
    # dialog focus can lose characters during keyboard transition on this AVD.
    time.sleep(.8)
    d.adb('shell', 'input', 'keyevent', '123')
    d.adb('shell', 'input', 'keyevent', *(['67'] * len(entry.get('text', ''))))
    d.adb('shell', 'input', 'text', title)
    assert node(**{'class': 'android.widget.EditText'}).get('text') == title, 'ADB did not enter the intended fixture title'
    press(text='저장')
    time.sleep(.3)
    assert selected()[1] == title, 'Rename did not reach the selected tab'


def hide_keyboard():
    # Dismiss only an observed IME; Back without an IME could leave the activity.
    state = d.adb('shell', 'dumpsys', 'input_method')
    if 'mInputShown=true' in state:
        d.adb('shell', 'input', 'keyevent', '4')
        time.sleep(.3)


def create(project, via_group=False):
    if via_group:
        hide_keyboard()
        press(**{'content-desc': project + '에 새 세션'})
    else:
        current = node(**{'resource-id': d.PACKAGE + ':id/z8_current_project'})
        if current.get('text') != project:
            raise RuntimeError('Global new-session control is not attached to the requested project')
        press(**{'resource-id': d.PACKAGE + ':id/z8_new_session'})
    c.wait_direct_shell(project)


def select(project, title, tab=False):
    if tab:
        tree = d.observe()
        label = '세션 전환: ' + project + ' / ' + title + ' / '
        matches = [n for n in tree.iter('node')
                   if n.get('resource-id') == d.PACKAGE + ':id/z8_session_tab'
                   and n.get('content-desc', '').startswith(label)
                   and n.get('clickable') == 'true' and n.get('enabled') != 'false'
                   and n.get('visible-to-user') != 'false']
        if len(matches) != 1:
            raise RuntimeError('Expected a unique actual session tab: ' + label)
        d.click(matches[0])
    else:
        tree = d.observe()
        label = '세션 선택: ' + project + ' / ' + title + ' / '
        matches = [n for n in tree.iter('node') if n.get('content-desc', '').startswith(label)]
        if not matches:
            press(**{'content-desc': '프로젝트와 세션 목록'})
            tree = d.observe()
            matches = [n for n in tree.iter('node') if n.get('content-desc', '').startswith(label)]
        if len(matches) != 1:
            raise RuntimeError('Expected a unique actual session row: ' + label)
        d.click(matches[0])
    wait_selected(project, title)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--other-project', required=True)
    parser.add_argument('--other-name', required=True)
    args = parser.parse_args()
    for value in (args.project, args.other_project):
        if str(uuid.UUID(value)) != value:
            parser.error('Use canonical fixture project UUIDs')
    if args.project == args.other_project:
        parser.error('Two distinct fixture projects are required')
    report = {'source': 'EMULATOR', 'status': 'FAIL', 'startedAtUtc': datetime.now(timezone.utc).isoformat(),
              'projects': [args.project, args.other_project], 'phases': {}, 'screenshots': {},
              'limitations': ['Only the dedicated API 37 foldable emulator, not Galaxy hardware',
                              'No process death, reboot, tmux recovery, AI authentication or live AI hooks',
                              'Two first-project shells and one other-project shell remain after this probe']}
    stem, sentinel = 'z8-navigation-' + uuid.uuid4().hex[:12], uuid.uuid4().hex
    report['fixtureStem'] = stem
    uploaded = []
    try:
        apk, bootstrap, pages = r.checked_runtime()
        report.update(apkSha256=apk, bootstrapSha256=bootstrap, pageSizeBytes=pages)
        for project in report['projects']:
            marker = json.loads(r.run_as('/system/bin/cat', 'files/z8/environments/' + project + '/rootfs/.z8-environment.json').stdout)
            assert marker['projectId'] == project
        states = c.fold_states(d.adb('shell', 'cmd', 'device_state', 'print-states'))
        c.fold(states['OPENED']); time.sleep(2); c.wake()
        # No existing session is selected as a writable probe; always create one.
        c.open_fixture(args.name, args.project)
        wait_selected(args.name)
        tree = d.observe()
        session_rows = [n for n in tree.iter('node') if n.get('resource-id', '').endswith(':id/z8_session_row')]
        if len(session_rows) > 5:
            raise RuntimeError('This probe requires three more free terminal slots')
        rename('Build')

        with tempfile.TemporaryDirectory(prefix='z8-navigation-') as directory:
            for project in report['projects']:
                text = '''# Sourced only into this probe's newly created PTYs.
case "$1" in seed) _Z8_NAV_TOKEN='@TOKEN@';; esac
test "$HOME" = /z8/home && test -n "$BASH_VERSION" || return 2
printf '%s\\n' "$$" "${_Z8_NAV_TOKEN:-}" "$HOME" "$PWD" > "/z8/home/@STEM@.$1"
'''.replace('@TOKEN@', sentinel).replace('@STEM@', stem)
                path = Path(directory) / (stem + '-' + project + '.sh')
                path.write_text(text)
                remote = '/data/local/tmp/' + path.name
                uploaded.append(remote)
                d.adb('push', str(path), remote)
                r.run_as('/system/bin/cp', remote, 'files/z8/homes/' + project + '/' + stem + '.sh')

        def proof(phase, project=args.project, expected_pid=None, fresh=False):
            time.sleep(.5)
            d.command('. /z8/home/' + stem + '.sh ' + phase)
            deadline = time.monotonic() + 12
            values = []
            while time.monotonic() < deadline:
                try:
                    values = r.run_as('/system/bin/cat', 'files/z8/homes/' + project + '/' + stem + '.' + phase).stdout.splitlines()
                    if len(values) == 4:
                        break
                except RuntimeError:
                    pass
                time.sleep(.3)
            assert len(values) == 4 and values[0].isdigit(), 'Missing actual PTY proof: ' + phase
            pid, value, home, cwd = values
            assert home == cwd == '/z8/home'
            assert value == ('' if fresh else sentinel), 'Shell-local variable mismatch: ' + phase
            if expected_pid is not None:
                assert (pid != expected_pid if fresh else pid == expected_pid), 'PID mismatch: ' + phase
            report['phases'][phase] = {'pid': pid, 'projectId': project, 'home': home, 'cwd': cwd,
                                       'unexportedVariable': 'ABSENT_IN_NEW_SHELL' if fresh else 'PRESERVED'}
            print(phase + ': PASS (PID ' + pid + ')', flush=True)
            return pid

        original = proof('seed')
        create(args.name); second = proof('new-tab', expected_pid=original, fresh=True)
        rename('Review')
        select(args.name, 'Build', tab=True); proof('tab-return', expected_pid=original)
        # IME remains visible after rename: same-tap tab switching must work.
        report['screenshots']['keyboard'] = c.capture('session-navigation-keyboard.png', 0)
        create(args.other_name, via_group=True)
        proof('other-project', project=args.other_project, expected_pid=original, fresh=True)
        select(args.name, 'Build'); proof('project-return', expected_pid=original)

        create(args.name); rename('Scratch')
        scratch = proof('scratch-created', expected_pid=original, fresh=True)
        open_session_menu(); press(text='터미널 종료…'); press(text='취소')
        assert proof('cancel-end', fresh=True) == scratch, 'Cancel replaced the Scratch session'
        open_session_menu(); press(text='터미널 종료…'); press(text='세션 종료')
        time.sleep(1)
        deadline = time.monotonic() + 8
        while r.run_as('/system/bin/kill', '-0', scratch, check=False).returncode == 0:
            if time.monotonic() > deadline:
                raise RuntimeError('Explicit end left the probe guest shell alive')
            time.sleep(.25)
        tree = d.observe()
        ended = next((n for n in tree.iter('node') if n.get('content-desc') == '세션 선택: ' + args.name + ' / Scratch / 종료됨'), None)
        if ended is not None:
            d.click(ended)
            open_session_menu(); press(text='목록에서 제거'); press(text='제거')
        select(args.name, 'Build'); proof('other-session-ended', expected_pid=original)
        tree = d.observe()
        assert not any(' / Scratch / ' in n.get('content-desc', '') for n in tree.iter('node'))
        report['explicitEnd'] = {'pid': scratch, 'guestShellExited': True,
                                 'cancelPreservedSession': True, 'otherSessionPreserved': True}

        for state, port in (('CLOSED', 1), ('OPENED', 0)):
            hide_keyboard()
            c.fold(states[state]); time.sleep(2); c.wake(); wait_selected(args.name, 'Build')
            hide_keyboard()
            tree = d.observe()
            side_visible = any(n.get('resource-id', '').endswith(':id/z8_session_sidebar') for n in tree.iter('node'))
            assert side_visible == (state == 'OPENED'), 'Sidebar did not adapt to real window width'
            proof('fold-' + state.lower(), expected_pid=original)
            if state == 'CLOSED':
                press(**{'content-desc': '프로젝트와 세션 목록'})
                node(**{'resource-id': d.PACKAGE + ':id/z8_session_drawer'})
                report['screenshots']['foldedDrawer'] = c.capture('session-navigation-folded-drawer.png', port)
                select(args.name, 'Review'); assert proof('folded-select', fresh=True) == second
                select(args.name, 'Build', tab=True); proof('folded-tab-return', expected_pid=original)
            d.command('clear'); time.sleep(.2)
            report['screenshots'][state.lower()] = c.capture('session-navigation-' + state.lower() + '.png', port)

        report['status'] = 'PASS'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        for path in uploaded:
            d.adb('shell', 'rm', '-f', path)
        report['finishedAtUtc'] = datetime.now(timezone.utc).isoformat()
        (d.REPORTS / 'session-navigation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print('Report: reports/compatibility/session-navigation.json', flush=True)


if __name__ == '__main__':
    main()
