#!/usr/bin/env python3
"""Explicitly merge reviewed z8 observers into this guest's CLI configuration.

Default is a dry run. This does not log in, change permission policy, trust hooks,
or send a test event. Public CLI destinations cannot be redirected to host files.
"""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import uuid

MAX_BYTES = 1024 * 1024
HOME = Path('/z8/home')
ASSET_DIR = Path('/opt/z8/hooks')
DESTINATIONS = {'claude': ('.claude', 'settings.json'), 'codex': ('.codex', 'hooks.json')}
REVIEWED_SHA256 = {
    'z8_event.py': '1e3a15f4200db07ceaabe2ad7132ea0b217e2845e2ecfaabb4ab9517fb94670f',
    'claude.hooks.json': '745f36b7e41e52c06d9e5e3bee9f0cba355cf90ccd0df0d8536600ba37a91e4a',
    'codex.hooks.json': '9240cd0821244b46c46421a817491ff6d2d4fd3b75d44b7dfc94e87ddcc20e81',
}


def open_directory(path):
    """Open every absolute component without following symlinks."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Expected an absolute path without parent traversal')
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            next_descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                      dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def snapshot(directory, name):
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError('Expected a regular configuration file of at most 1 MiB: ' + name)
        data = stream.read(MAX_BYTES + 1)
        final = os.fstat(stream.fileno())
        identity = lambda entry: (entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns,
                                  entry.st_ctime_ns, stat.S_IMODE(entry.st_mode))
        if len(data) > MAX_BYTES or identity(info) != identity(final):
            raise ValueError('Configuration changed while reading: ' + name)
        return data, identity(info)


def parse_json(data):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError('Invalid JSON constant: ' + value)

    result = json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(result, dict):
        raise ValueError('Configuration must be a JSON object')
    return result


def reviewed_template(asset_directory, provider):
    directory = open_directory(asset_directory)
    try:
        template = None
        for name in ('z8_event.py', provider + '.hooks.json'):
            item = snapshot(directory, name)
            if item is None or hashlib.sha256(item[0]).hexdigest() != REVIEWED_SHA256[name]:
                raise ValueError('Bundled hook asset changed; review it before enabling: ' + name)
            if name.endswith('.json'):
                template = parse_json(item[0])
        return template
    finally:
        os.close(directory)


def merge(existing, template):
    """Preserve user data; refuse ambiguous edited copies of our own observer."""
    merged = copy.deepcopy(existing)
    hooks = merged.setdefault('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('Existing hooks must be an object; no settings were replaced')
    added = []
    for event, expected_groups in template['hooks'].items():
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise ValueError('Existing hook event must be an array: ' + event)
        for expected in expected_groups:
            if expected in groups:
                continue
            command = expected['hooks'][0]['command']
            for group in groups:
                if not isinstance(group, dict) or not isinstance(group.get('hooks', []), list):
                    raise ValueError('Invalid existing hook group: ' + event)
                for handler in group.get('hooks', []):
                    if isinstance(handler, dict) and handler.get('command') == command:
                        raise ValueError('An edited z8 observer already exists for ' + event
                                         + '; review it instead of adding duplicate notifications')
            groups.append(copy.deepcopy(expected))
            added.append(event)
    return merged, added


def configuration_notes(provider, directory, existing):
    notes = ['Provider permissions, login, model and trust settings are unchanged.',
             'Live provider-to-Android notification delivery still requires verification.']
    if provider == 'claude':
        notes.append('Inspect the observers in Claude Code /hooks. Existing workspace and managed policies still apply.')
        if existing.get('disableAllHooks') is True:
            notes.append('ACTION REQUIRED: disableAllHooks is true; it was preserved. Review this setting in Claude Code.')
    else:
        notes.append('ACTION REQUIRED: review and trust each new definition in Codex /hooks; untrusted hooks are skipped.')
        if directory is not None:
            config = snapshot(directory, 'config.toml')
            if config is not None:
                import tomllib
                parsed = tomllib.loads(config[0].decode('utf-8'))
                if 'hooks' in parsed:
                    # Codex loads both forms. Avoid silently duplicating an already
                    # installed z8 handler; unrelated inline hooks remain intact.
                    if '/opt/z8/hooks/z8_event.py' in json.dumps(parsed['hooks']):
                        raise ValueError('Codex inline hooks already reference z8; review config.toml instead of duplicating them')
                    notes.append('Codex also has inline hooks in config.toml. Both sources load; review the startup warning and /hooks.')
                features = parsed.get('features', {})
                if isinstance(features, dict) and (features.get('hooks') is False or features.get('codex_hooks') is False):
                    notes.append('ACTION REQUIRED: Codex hooks are disabled in config.toml; this preference was preserved.')
        notes.append('Managed policies may disable user hooks; no managed policy or feature flag was changed.')
    return notes


def write_new(directory, name, data, mode=0o600):
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         mode, dir_fd=directory)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
        os.fchmod(stream.fileno(), mode)


def publish(directory, name, original, data):
    """Compare just before replacement, retain exact original bytes as a backup."""
    if snapshot(directory, name) != original:
        raise ValueError('Configuration changed; no settings were replaced')
    temporary = '.z8-hooks-' + uuid.uuid4().hex + '.tmp'
    backup = None
    try:
        mode = original[1][-1] & 0o777 if original is not None else 0o600
        write_new(directory, temporary, data, mode)
        if original is not None:
            backup = name + '.z8-backup-' + uuid.uuid4().hex
            write_new(directory, backup, original[0])
        if snapshot(directory, name) != original:
            raise ValueError('Configuration changed before save; no settings were replaced')
        # Do not use hard-link publication: PRoot --link2symlink can turn that
        # into a symlink. Rename publishes a regular file in one operation.
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
        return backup
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def enable(home, asset_directory, provider, apply=False):
    """Internal filesystem API; CLI always validates and fixes guest paths."""
    if provider not in DESTINATIONS:
        raise ValueError('Choose claude or codex')
    template = reviewed_template(asset_directory, provider)
    folder, filename = DESTINATIONS[provider]
    root = open_directory(home)
    directory = None
    lock = None
    try:
        try:
            directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        except FileNotFoundError:
            if apply:
                os.mkdir(folder, mode=0o700, dir_fd=root)
                directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        if apply:
            lock = os.open('.z8-hooks.lock', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                           0o600, dir_fd=directory)
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                raise ValueError('Invalid hook installer lock')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original = snapshot(directory, filename) if directory is not None else None
        existing = parse_json(original[0]) if original is not None else {}
        notes = configuration_notes(provider, directory, existing)
        merged, added = merge(existing, template)
        serialized = (json.dumps(merged, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
        if len(serialized) > MAX_BYTES:
            raise ValueError('Merged configuration exceeds 1 MiB; no settings were replaced')
        backup = publish(directory, filename, original, serialized) if apply and added else None
        return {'state': ('merged' if added else 'unchanged') if apply else 'dry-run',
                'provider': provider, 'path': str(Path(home) / folder / filename),
                'addedEvents': added, 'backup': str(Path(home) / folder / backup) if backup else None,
                'notes': notes}
    finally:
        if lock is not None:
            os.close(lock)
        if directory is not None:
            os.close(directory)
        os.close(root)


def validate_guest(provider):
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64'):
        raise ValueError('Run this installer inside the z8 ARM64 Linux guest')
    if os.environ.get('HOME') != str(HOME):
        raise ValueError('Expected the dedicated guest HOME=/z8/home')
    override = 'CLAUDE_CONFIG_DIR' if provider == 'claude' else 'CODEX_HOME'
    expected = str(HOME / DESTINATIONS[provider][0])
    if os.environ.get(override) not in (None, '', expected):
        raise ValueError(override + ' redirects CLI settings; review it before enabling hooks')
    marker_directory = open_directory('/etc/z8')
    try:
        marker = snapshot(marker_directory, 'guest-target')
        if marker is None or marker[0] not in (b'z8-guest-v1', b'z8-guest-v1\n'):
            raise ValueError('Expected z8-guest-v1 guest marker')
    finally:
        os.close(marker_directory)
    descriptor = open_directory(HOME)
    os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--dry-run', action='store_true')
    parser.add_argument('provider', choices=tuple(DESTINATIONS))
    args = parser.parse_args()
    try:
        validate_guest(args.provider)
        result = enable(HOME, ASSET_DIR, args.provider, args.apply)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        parser.exit(2, 'z8 hooks: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
