"""Preserve original notices and mark files changed by the Z8 app preparer."""
import hashlib
import json
from pathlib import Path

NOTICE_DATE = '2026-11-04'
NOTICE = ('Z8 modification notice recorded ' + NOTICE_DATE + ': this file has been changed for Z8. '
          'See Z8-MODIFICATIONS.json in the prepared source root. Original notices and license terms remain applicable.')


def annotate(data, suffix):
    """Return a comment plus unchanged source bytes, or None for binary assets."""
    if suffix in {'.png', '.webp', '.jpg', '.jar', '.zip'}:
        return None
    text = data.decode('utf-8')
    if NOTICE in text:
        raise ValueError('Modification notice was already applied')
    if suffix == '.xml':
        comment = '<!-- ' + NOTICE + ' -->\n'
        if text.startswith('<?xml'):
            end = text.index('?>') + 2
            return (text[:end] + '\n' + comment + text[end:]).encode()
        return (comment + text).encode()
    if suffix in {'.java', '.c', '.h', '.cpp', '.gradle', '.S'}:
        return ('// ' + NOTICE + '\n' + text).encode()
    if suffix in {'.properties', '.mk', '.sh'}:
        comment = '# ' + NOTICE + '\n'
        if text.startswith('#!'):
            first, separator, rest = text.partition('\n')
            return (first + '\n' + comment + rest).encode()
        return (comment + text).encode()
    raise ValueError('Changed upstream file needs a notice format: ' + suffix)


def mark_modified(source, prepared, names, upstream_commit):
    source, prepared = Path(source), Path(prepared)
    records = []
    digest = lambda data: hashlib.sha256(data).hexdigest()
    for name in sorted(names):
        original, target = source / name, prepared / name
        if not original.is_file() or original.is_symlink() or target.is_symlink():
            raise ValueError('Unsupported source entry during modification audit: ' + name)
        before = original.read_bytes()
        if not target.exists():
            records.append({'path': name, 'change': 'removed', 'upstreamSha256': digest(before)})
            continue
        current = target.read_bytes()
        if current == before:
            continue
        marked = annotate(current, target.suffix)
        if marked is not None:
            target.write_bytes(marked)
        records.append({'path': name, 'change': 'modified' if marked is not None else 'replaced-binary-asset',
                        'notice': 'file-comment' if marked is not None else 'this-index',
                        'upstreamSha256': digest(before), 'preparedSha256': digest(marked if marked is not None else current)})
    report = {'schemaVersion': 1, 'kind': 'z8-upstream-modifications', 'noticeRecordedAt': NOTICE_DATE,
              'upstreamCommit': upstream_commit, 'notice': NOTICE, 'files': records,
              'scope': 'Changes relative to the pinned upstream. Original copyright and license notices remain applicable.'}
    (prepared / 'Z8-MODIFICATIONS.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
