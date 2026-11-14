"""Verify an exported upstream tree without inventing Git history.

The release ZIP's independently obtained checksum is the trust anchor. This
checks consistency with its manifest, not authenticity of a self-supplied file.
Only the selected upstream tree is immutable; users may edit Z8's overlay.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat


def exported_app_files(source, commit):
    source = Path(source)
    root = source.parent.parent
    if source.name != 'termux-app' or source.parent.name != 'upstream':
        raise ValueError('Exported sources must use upstream/termux-app')
    if any(p.is_symlink() for p in (source, source.parent, root)):
        raise ValueError('Exported upstream must not use symlink directories')
    path = root / 'SOURCE_MANIFEST.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024**2:
        raise ValueError('Missing or invalid SOURCE_MANIFEST.json; use the published source ZIP or pinned Git checkout')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(manifest, dict) or manifest.get('schemaVersion') != 1 or manifest.get('kind') != 'z8-release-source'
            or manifest.get('sourceLock', {}).get('termuxApp', {}).get('commit') != commit):
        raise ValueError('Exported source identity differs from the pinned app revision')
    records = manifest.get('files')
    if not isinstance(records, list) or not records or len(records) > 200000:
        raise ValueError('Invalid exported source inventory')
    encoded = (json.dumps(records, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    if hashlib.sha256(encoded).hexdigest() != manifest.get('sourceInputSha256'):
        raise ValueError('Exported source inventory digest differs')
    prefix = 'upstream/termux-app/'
    expected = {}
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('Invalid exported source record')
        name = record.get('path', '')
        parts = name.split('/') if isinstance(name, str) else []
        if (not parts or any(p in ('', '.', '..') for p in parts)
                or '\\' in name or '\0' in name or name in seen):
            raise ValueError('Unsafe or duplicate exported source path')
        seen.add(name)
        if not name.startswith(prefix):
            continue
        relative = name[len(prefix):]
        if (record.get('type') != 'file' or '.git' in PurePosixPath(relative).parts
                or type(record.get('bytes')) is not int or record['bytes'] < 0
                or not re.fullmatch(r'[a-f0-9]{64}', record.get('sha256', ''))
                or record.get('mode') not in (0o644, 0o755, 0o664, 0o775)):
            raise ValueError('Unsupported exported upstream record: ' + name)
        expected[relative] = record
    if not expected:
        raise ValueError('Export contains no pinned app source files')
    actual = set()
    for item in source.rglob('*'):
        if item.is_symlink():
            raise ValueError('Symlink in exported app sources: ' + item.relative_to(source).as_posix())
        if item.is_dir():
            continue
        relative = item.relative_to(source).as_posix()
        if not stat.S_ISREG(item.stat().st_mode) or relative not in expected:
            raise ValueError('Unexpected exported upstream file: ' + relative)
        record = expected[relative]
        data = item.read_bytes()
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Changed exported upstream file: ' + relative)
        # ZIP tools do not consistently preserve executable bits. Restore those
        # on the generated copy, never mutate the user's extracted sources here.
        actual.add(relative)
    if actual != set(expected):
        raise ValueError('Exported upstream files are missing')
    return sorted(expected), {name: entry['mode'] for name, entry in expected.items()}
