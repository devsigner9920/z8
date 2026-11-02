#!/usr/bin/env python3
"""Verify direct Shell creation and project navigation on the foldable emulator.

Requires two prepared fixture projects, the second with no open sessions. Creates four Shell sessions and small
proof files; does not launch AI tools, install packages or close other sessions.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('z8_project_selection', ROOT / 'tools/smoke-session-navigation.py')
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)
d, c, r = n.d, n.c, n.r
ui = n.ui


def bash_pids():
    uid = r.run_as('/system/bin/id', '-u').stdout.strip()
    rows = r.run_as('/system/bin/ps', '-A', '-o', 'UID,PID,NAME').stdout.splitlines()[1:]
    return sorted(row.split()[1] for row in rows
                  if row.split()[0] == uid and row.split()[-1].endswith('bash'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--other-project', required=True)
    parser.add_argument('--other-name', required=True)
    parser.add_argument('--report-dir', required=True)
    args = parser.parse_args()
    for value in (args.project, args.other_project):
        if str(uuid.UUID(value)) != value:
            parser.error('Use canonical fixture project UUIDs')
    if args.project == args.other_project:
        parser.error('Choose two distinct fixture projects')
    d.REPORTS = Path(args.report_dir).resolve()
    d.REPORTS.mkdir(parents=True, exist_ok=True)
    report = {'status': 'FAIL', 'source': 'EMULATOR', 'startedAtUtc': datetime.now(timezone.utc).isoformat(),
              'phases': {}, 'screenshots': {}, 'limitations': ['Dedicated API 37 foldable emulator; no Galaxy hardware',
                  'No AI CLI launch/authentication, process-death recovery or external keyboard validation']}
    stem = 'z8-project-selection-' + uuid.uuid4().hex[:12]
    uploaded = []
    report['fixtureStem'] = stem

    def proof(phase, project):
        filename = stem + '-' + phase
        # Source a fixed fixture driver through the real PTY. Keep shell syntax
        # out of Android's key-event injector (which can drop shifted symbols).
        d.command('. /z8/home/' + stem + '.sh ' + phase)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            output = r.run_as('/system/bin/cat', 'files/z8/homes/' + project + '/' + filename, check=False)
            values = output.stdout.splitlines()
            if output.returncode == 0 and len(values) == 3:
                assert values[0].isdigit() and values[1:] == ['/z8/home', '/z8/home']
                report['phases'][phase] = {'projectId': project, 'pid': values[0], 'home': values[1], 'cwd': values[2]}
                return values[0]
            time.sleep(.3)
        raise RuntimeError('No actual shell proof in the selected project: ' + phase)

    def unchanged(phase, expected):
        actual = bash_pids()
        assert actual == expected, 'Navigation unexpectedly changed shell processes: ' + phase
        report['phases'][phase] = {'bashPids': actual, 'noShellCreated': True}
        print(phase + ': PASS', flush=True)

    def direct_shell(phase, project_id, project_name, **control):
        before = bash_pids()
        n.press(**control)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            tree = d.observe()
            assert not any(x.get('text') in ui.labels('chooser') + ui.labels('tool_chooser')
                           or x.get('resource-id') == 'android:id/alertTitle' for x in tree.iter('node')), 'Unexpected session modal'
            if len(bash_pids()) > len(before):
                break
            time.sleep(.3)
        n.wait_selected(project_name)
        pid = proof(phase, project_id)
        assert pid not in before and bash_pids() == sorted(before + [pid]), 'Expected exactly one new Shell'
        report['phases'][phase]['openedWithoutChooser'] = True
        n.hide_keyboard()
        print(phase + ': PASS', flush=True)
        return pid

    try:
        apk, bootstrap, pages = r.checked_runtime()
        report.update(apkSha256=apk, bootstrapSha256=bootstrap, pageSizeBytes=pages)
        for project in (args.project, args.other_project):
            marker = json.loads(r.run_as('/system/bin/cat', 'files/z8/environments/' + project + '/rootfs/.z8-environment.json').stdout)
            assert marker['projectId'] == project
        with tempfile.TemporaryDirectory(prefix='z8-direct-shell-') as temporary:
            driver = Path(temporary) / (stem + '.sh')
            driver.write_text('printf \'%s\\n\' "$$" "$HOME" "$PWD" > /z8/home/' + stem + '-"$1"\n')
            remote = '/data/local/tmp/' + driver.name
            uploaded.append(remote)
            d.adb('push', str(driver), remote)
            for project in (args.project, args.other_project):
                r.run_as('/system/bin/cp', remote, 'files/z8/homes/' + project + '/' + driver.name)
        states = c.fold_states(d.adb('shell', 'cmd', 'device_state', 'print-states'))
        c.fold(states['OPENED']); time.sleep(2); c.wake()
        c.open_fixture(args.name, args.project)
        n.wait_selected(args.name)
        original = proof('initial', args.project)
        n.hide_keyboard()
        baseline = bash_pids()
        assert original in baseline, 'Process observation must include the actual PTY shell'
        second = direct_shell('tab-add', args.project, args.name,
                              **{'resource-id': d.PACKAGE + ':id/z8_new_session'})
        first_other = direct_shell('first-session', args.other_project, args.other_name,
                                   **{'content-desc': ui.labels('new_session', project=args.other_name)})
        all_before = bash_pids()
        n.press(**{'content-desc': ui.labels('select_project', project=args.name)})
        n.wait_selected(args.name)
        assert proof('project-title-return', args.project) == second
        unchanged('project-title-no-launch', all_before)
        n.hide_keyboard()
        last_other = direct_shell('project-add', args.other_project, args.other_name,
                                  **{'content-desc': ui.labels('new_session', project=args.other_name)})
        d.command('clear'); time.sleep(.3); n.hide_keyboard()
        report['screenshots']['result'] = c.capture('direct-session-opened.png', 0)
        n.press(**{'content-desc': ui.labels('expanded_project', project=args.name)})
        unchanged('collapse-no-launch', sorted(baseline + [second, first_other, last_other]))
        n.press(**{'content-desc': ui.labels('select_project', project=args.name)})
        n.wait_selected(args.name)
        assert proof('collapsed-project-return', args.project) == second
        n.hide_keyboard()
        c.fold(states['CLOSED']); time.sleep(2); c.wake()
        n.wait_selected(args.name)
        n.hide_keyboard()
        n.press(**{'content-desc': ui.labels('projects')})
        n.press(**{'content-desc': ui.labels('select_project', project=args.other_name)})
        n.wait_selected(args.other_name)
        assert proof('folded-project-return', args.other_project) == last_other
        unchanged('folded-no-launch', sorted(baseline + [second, first_other, last_other]))
        d.command('clear'); time.sleep(.3); n.hide_keyboard()
        report['screenshots']['folded'] = c.capture('direct-session-folded.png', 1)
        c.fold(states['OPENED']); time.sleep(2); c.wake()
        n.wait_selected(args.other_name)
        assert proof('final-same-shell', args.other_project) == last_other
        n.hide_keyboard()
        d.command('clear'); time.sleep(.3)
        n.hide_keyboard()
        report['status'] = 'PASS'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        for path in uploaded:
            d.adb('shell', 'rm', '-f', path)
        report['finishedAtUtc'] = datetime.now(timezone.utc).isoformat()
        path = d.REPORTS / 'project-selection.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print('Report: ' + str(path), flush=True)


if __name__ == '__main__':
    main()
