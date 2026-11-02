"""Release evidence helpers. Source recipes are data, never executed by this module."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GENERATED_NOTICES = {'third-party-notices.txt', 'release-notices.json'}
SECRET_NAMES = {'.env', '.netrc', '.npmrc', 'credentials', 'credentials.json', 'auth.json',
                'local.properties', 'id_rsa', 'id_ed25519', 'id_ecdsa', 'testkey_untrusted.jks'}
SECRET_SUFFIXES = {'.jks', '.keystore', '.p12', '.pfx', '.pem', '.key'}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def bytes_sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Refusing symlink output: ' + str(path))
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    return json.loads(Path(path).read_text())


def safe_relative(name):
    parts = PurePosixPath(name).parts
    if not parts or name.startswith('/') or '\\' in name or '\x00' in name or '..' in parts:
        raise ValueError('Unsafe archive path')
    return str(PurePosixPath(name))


def secret_path(name):
    p = PurePosixPath(name)
    return (any(x.lower() in SECRET_NAMES or x.lower() in {'.ssh', '.aws', '.gnupg'}
                or x.lower().startswith('.env.')
                or (x.lower().startswith('credentials') and x.lower().endswith('.json'))
                for x in p.parts) or p.suffix.lower() in SECRET_SUFFIXES)


def zip_entry(bundle, name, data, mode=0o644, kind=0o100000):
    info = zipfile.ZipInfo(safe_relative(name), (1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (kind | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    bundle.writestr(info, data)


def deb822(text):
    """Read Debian control paragraphs, including multiline hashes and descriptions."""
    result, paragraph, key = [], {}, None
    for line in text.splitlines() + ['']:
        if not line:
            if paragraph:
                result.append(paragraph)
            paragraph, key = {}, None
        elif line[0].isspace():
            if key is not None:
                paragraph[key] += '\n' + line[1:]
        elif ':' in line:
            key, value = line.split(':', 1)
            paragraph[key] = value.strip()
    return result


def archive_inventory(path):
    """Inspect only regular archive metadata. Do not extract or follow guest symlinks."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive members')
        packages = deb822(z.read('var/lib/dpkg/status').decode())
        packages = [p for p in packages if p.get('Status') == 'install ok installed']
        notices = {}
        for name in names:
            lower = name.lower()
            if (('/share/doc/' in '/' + name or '/share/common-licenses/' in '/' + name)
                    and not name.endswith('/') and any(x in lower for x in
                    ['copyright', 'license', 'licence', 'copying', 'notice', 'common-licenses/'])):
                info = z.getinfo(name)
                if info.file_size <= 2 * 1024 * 1024:
                    # Preserve bytes exactly in the public evidence archive. UI
                    # decoding happens separately and never rewrites this copy.
                    notices[name] = z.read(name)
    return packages, notices


class HttpsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('Refusing non-HTTPS redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, target, expected=None, limit=512 * 1024 * 1024):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Source downloads require credential-free HTTPS')
    target = Path(target)
    if target.is_file() and not target.is_symlink() and (expected is None or sha256(target) == expected):
        return {'sha256': sha256(target), 'bytes': target.stat().st_size}
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.source-', dir=target.parent)
    try:
        opener = urllib.request.build_opener(HttpsRedirect())
        request = urllib.request.Request(url, headers={'User-Agent': 'z8-release-source/1'})
        with os.fdopen(fd, 'wb') as output, opener.open(request, timeout=30) as response:
            size = 0
            while chunk := response.read(256 * 1024):
                size += len(chunk)
                if size > limit:
                    raise ValueError('Source exceeds download size limit')
                output.write(chunk)
        actual = sha256(tmp)
        if expected is not None and actual != expected:
            raise ValueError('Downloaded source checksum differs from provenance')
        if target.is_symlink():
            raise ValueError('Refusing symlink download target')
        os.replace(tmp, target)
        return {'sha256': actual, 'bytes': size}
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def source_id(package):
    match = re.fullmatch(r'([^ ()]+)(?: \(([^)]+)\))?', package.get('Source', package['Package']))
    if not match:
        raise ValueError('Unsupported source package field')
    return match[1], match[2] or package['Version']


def checked_asset(manifest_path, archive_key='archive', hash_key='sha256'):
    manifest_path = Path(manifest_path)
    data = read_json(manifest_path)
    name = safe_relative(data[archive_key])
    path = manifest_path.parent / name
    if path.is_symlink() or sha256(path) != data[hash_key]:
        raise ValueError('Archive differs from manifest: ' + name)
    return path, data


def issue(code, component, detail):
    return {'code': code, 'component': component, 'detail': detail}
