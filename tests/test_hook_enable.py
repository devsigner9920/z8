"""Filesystem and merge tests; do not enable host CLI hooks or imply live CLI support."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'runtime/hooks'
SPEC = importlib.util.spec_from_file_location('z8_enable_hooks', ASSETS / 'enable.py')
HOOKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HOOKS)


class HookEnableTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name).resolve() / 'home'
        self.home.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def run_enable(self, provider='claude', apply=False):
        return HOOKS.enable(self.home, ASSETS, provider, apply)

    def settings(self, provider='claude'):
        directory, name = HOOKS.DESTINATIONS[provider]
        return self.home / directory / name

    def put(self, value, provider='claude'):
        path = self.settings(provider)
        path.parent.mkdir(exist_ok=True)
        data = (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
        path.write_bytes(data)
        return data

    def test_default_preview_makes_no_files_and_cli_rejects_host(self):
        preview = self.run_enable()
        self.assertEqual(preview['state'], 'dry-run')
        self.assertEqual(set(preview['addedEvents']), {'PermissionRequest', 'PreToolUse', 'Notification', 'Stop'})
        self.assertEqual(list(self.home.iterdir()), [])
        result = subprocess.run([sys.executable, str(ASSETS / 'enable.py'), 'claude'],
                                env={**os.environ, 'HOME': str(self.home)}, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_preserves_unknown_fields_hooks_original_backup_and_mode(self):
        user_hook = {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'my-review'}],
                     'customFutureField': {'enabled': True}}
        original = {'model': 'user-model', 'permissions': {'deny': ['Read(.env)']},
                    'unknown': ['한글', {'future': 3}], 'hooks': {'PermissionRequest': [user_hook],
                    'FutureEvent': [{'newSchema': 'keep-me'}]}}
        before = self.put(original)
        self.settings().chmod(0o640)
        result = self.run_enable(apply=True)
        after = json.loads(self.settings().read_bytes())
        for key in ('model', 'permissions', 'unknown'):
            self.assertEqual(after[key], original[key])
        self.assertEqual(after['hooks']['PermissionRequest'][0], user_hook)
        self.assertEqual(after['hooks']['FutureEvent'], original['hooks']['FutureEvent'])
        self.assertEqual(Path(result['backup']).read_bytes(), before)
        self.assertEqual(stat.S_IMODE(Path(result['backup']).stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.settings().stat().st_mode), 0o640)
        self.assertFalse(self.settings().is_symlink())

    def test_idempotence_does_not_rewrite_or_create_extra_backup(self):
        first = self.run_enable('codex', True)
        self.assertIsNone(first['backup'])
        before = self.settings('codex').stat().st_mtime_ns
        content = self.settings('codex').read_bytes()
        second = self.run_enable('codex', True)
        self.assertEqual(second['state'], 'unchanged')
        self.assertEqual(second['addedEvents'], [])
        self.assertIsNone(second['backup'])
        self.assertEqual(self.settings('codex').stat().st_mtime_ns, before)
        self.assertEqual(self.settings('codex').read_bytes(), content)
        self.assertEqual(list(self.settings('codex').parent.glob('*.z8-backup-*')), [])

    def test_rejects_corrupt_ambiguous_and_modified_configs(self):
        for data in (b'{', b'[]', b'{"hooks":null}', b'{"hooks":{"Stop":{}}}',
                     b'{"x":1,"x":2}', b'{"x":NaN}', b'"\xff"'):
            with self.subTest(data=data):
                path = self.settings()
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(data)
                with self.assertRaises((ValueError, UnicodeError)):
                    self.run_enable(apply=True)
                self.assertEqual(path.read_bytes(), data)
        changed = HOOKS.reviewed_template(ASSETS, 'claude')
        changed['hooks']['Stop'][0]['hooks'][0]['timeout'] = 3
        before = self.put(changed)
        with self.assertRaisesRegex(ValueError, 'edited z8 observer'):
            self.run_enable(apply=True)
        self.assertEqual(self.settings().read_bytes(), before)

    def test_rejects_asset_changes_symlinks_and_nonregular_files(self):
        fake = self.home.parent / 'assets'
        fake.mkdir()
        for name in ('z8_event.py', 'claude.hooks.json'):
            (fake / name).write_bytes((ASSETS / name).read_bytes())
        (fake / 'z8_event.py').write_text('modified helper')
        with self.assertRaisesRegex(ValueError, 'asset changed'):
            HOOKS.enable(self.home, fake, 'claude', True)
        self.assertEqual(list(self.home.iterdir()), [])
        outside = self.home.parent / 'outside'
        outside.mkdir()
        (self.home / '.claude').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.run_enable(apply=True)
        self.assertEqual(list(outside.iterdir()), [])
        (self.home / '.claude').unlink()
        (self.home / '.claude').mkdir()
        external = outside / 'settings'
        external.write_text('{}')
        self.settings().symlink_to(external)
        with self.assertRaises(OSError):
            self.run_enable(apply=True)
        self.assertEqual(external.read_text(), '{}')
        self.settings().unlink()
        os.mkfifo(self.settings())
        with self.assertRaisesRegex(ValueError, 'regular configuration'):
            self.run_enable(apply=True)

    def test_conflicting_editor_write_preserves_new_disk_content(self):
        old = self.put({'model': 'old'})
        real_write = HOOKS.write_new

        def racing_write(directory, name, data, mode=0o600):
            real_write(directory, name, data, mode)
            if name.endswith('.tmp'):
                self.settings().write_text('{"model":"edited-while-saving"}')

        with mock.patch.object(HOOKS, 'write_new', side_effect=racing_write):
            with self.assertRaisesRegex(ValueError, 'changed before save'):
                self.run_enable(apply=True)
        self.assertEqual(json.loads(self.settings().read_bytes())['model'], 'edited-while-saving')
        backups = list(self.settings().parent.glob('*.z8-backup-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), old)
        self.assertEqual(list(self.settings().parent.glob('*.tmp')), [])

    def test_preferences_inline_hooks_and_trust_are_preserved(self):
        self.put({'disableAllHooks': True})
        claude = self.run_enable(apply=True)
        self.assertTrue(json.loads(self.settings().read_bytes())['disableAllHooks'])
        self.assertTrue(any('disableAllHooks' in note for note in claude['notes']))
        self.put({'unknown': 'preserve'}, 'codex')
        config = self.settings('codex').parent / 'config.toml'
        contents = b'[features]\nhooks = false\n[[hooks.Stop]]\n[[hooks.Stop.hooks]]\ntype = "command"\ncommand = "my-review"\n'
        config.write_bytes(contents)
        trust = config.parent / 'hook-trust.json'
        trust.write_text('user-owned-trust')
        result = self.run_enable('codex', True)
        self.assertEqual(config.read_bytes(), contents)
        self.assertEqual(trust.read_text(), 'user-owned-trust')
        self.assertTrue(any('trust each new' in note for note in result['notes']))
        self.assertTrue(any('disabled' in note for note in result['notes']))
        config.write_bytes(contents.replace(b'my-review', b'python3 /opt/z8/hooks/z8_event.py --provider codex'))
        before = self.settings('codex').read_bytes()
        with self.assertRaisesRegex(ValueError, 'inline hooks already'):
            self.run_enable('codex', True)
        self.assertEqual(self.settings('codex').read_bytes(), before)

    def test_size_limit_and_concurrent_installer_lock(self):
        self.put({})
        self.settings().write_bytes(b' ' * (HOOKS.MAX_BYTES + 1))
        with self.assertRaisesRegex(ValueError, 'at most 1 MiB'):
            self.run_enable(apply=True)
        self.put({})
        lock = self.settings().parent / '.z8-hooks.lock'
        with lock.open('wb') as stream:
            HOOKS.fcntl.flock(stream, HOOKS.fcntl.LOCK_EX | HOOKS.fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.run_enable(apply=True)
        self.assertEqual(json.loads(self.settings().read_bytes()), {})


if __name__ == '__main__':
    unittest.main()
