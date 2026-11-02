#!/usr/bin/env python3
"""Bounded, terminal-owned loopback preview for an explicitly selected HTML file.

No file:// access, directory indexes, symlink traversal, credential persistence,
or shell commands. This is a convenience server, not a PRoot security boundary.
"""
import errno
import fcntl
import hashlib
import hmac
import http.server
import importlib.util
import json
import mimetypes
import os
from pathlib import Path
import secrets
import select
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from urllib.parse import quote, unquote, urlsplit

RUNTIME_ROOT = Path('/tmp/z8-html-preview')
CHECK_INTERVAL = 10
IDLE_SECONDS = 30 * 60
MAX_SECONDS = 2 * 60 * 60
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_FRAME = 16384
NOFOLLOW = os.O_NOFOLLOW


class PreviewError(RuntimeError):
    pass


def safe_parts(value):
    parts = value.split('/')
    if any(not p or p.startswith('.') or '\\' in p or
           any(ord(c) < 32 or ord(c) == 127 for c in p) for p in parts):
        raise PreviewError('invalid path')
    return parts


def directory_fd(path):
    """Open every absolute directory component without following links."""
    if not os.path.isabs(path):
        raise PreviewError('absolute directory required')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.strip('/').split('/') if path != '/' else ():
            if part in ('', '.', '..'):
                raise PreviewError('invalid directory')
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def file_fd(root_fd, parts):
    directory = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | NOFOLLOW, dir_fd=directory)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            os.close(fd)
            raise PreviewError('not a bounded regular file')
        return fd, info
    finally:
        os.close(directory)


def selected_file(value):
    if not isinstance(value, str) or len(os.fsencode(value)) > 8192 or '://' in value:
        raise PreviewError('invalid filename')
    # ./ is a normal CLI spelling, but hidden paths and parent traversal are not
    # needed for this narrow convenience feature. HTTP requests use the same rule.
    parts = [p for p in value.split('/') if p and p != '.']
    safe_parts('/'.join(parts))
    path = Path(os.path.abspath(value))
    if path.suffix.lower() not in ('.html', '.htm') or str(path.parent) == '/':
        raise PreviewError('HTML file required')
    root = str(path.parent)
    fd = directory_fd(root)
    try:
        selected, _ = file_fd(fd, [path.name])
        os.close(selected)
    finally:
        os.close(fd)
    return root, path.name


def read_frame(connection):
    data = bytearray()
    deadline = time.monotonic() + 1.5
    while len(data) <= MAX_FRAME:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PreviewError('frame deadline')
        connection.settimeout(remaining)
        part = connection.recv(min(4096, MAX_FRAME + 1 - len(data)))
        if not part:
            raise PreviewError('incomplete frame')
        data.extend(part)
        if b'\n' in data:
            result = json.loads(data.split(b'\n', 1)[0])
            if not isinstance(result, dict):
                raise PreviewError('invalid frame')
            return result
    raise PreviewError('frame too long')


def control(path, message):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(1.5)
        client.connect(path)
        client.sendall(json.dumps(message).encode() + b'\n')
        return read_frame(client)


def runtime_directory():
    try:
        RUNTIME_ROOT.mkdir(mode=0o700)
    except FileExistsError:
        pass
    fd = directory_fd(str(RUNTIME_ROOT))
    info = os.fstat(fd)
    # Android private directories can inherit their parent's setgid bit. Only
    # access bits determine whether another UID/group can use this directory.
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o777 != 0o700:
        os.close(fd)
        raise PreviewError('runtime directory changed')
    return fd


def bridge_module():
    spec = importlib.util.spec_from_file_location('z8_preview_bridge', Path(__file__).with_name('browser-open.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def start_server(root, filename, socket_path, environment):
    config = {'root': root, 'filename': filename, 'socket': socket_path,
              'environment': {k: environment.get(k, '') for k in
                              ('Z8_EVENT_SOCKET', 'Z8_LAUNCH_ID', 'Z8_EVENT_TOKEN')}}
    # Detach from the short-lived Codex tool process group. The containing PRoot
    # --kill-on-exit session still owns this tracee; bridge checks also end it
    # when the Android service/terminal disappears. No PTY or output pipe stays open.
    child = subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve()), '--serve'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        cwd='/', env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'},
        start_new_session=True, close_fds=True)
    try:
        child.stdin.write(json.dumps(config).encode() + b'\n')
        child.stdin.close()
        ready, _, _ = select.select([child.stdout], [], [], 5)
        if not ready:
            raise PreviewError('startup deadline')
        line = child.stdout.readline(4097)
        result = json.loads(line)
        if not isinstance(result, dict) or result.get('status') != 'ready':
            raise PreviewError('startup failed')
        # A short-lived CLI may exit immediately; an embedding caller may live
        # longer. Reap in the latter case without keeping either caller alive.
        threading.Thread(target=child.wait, daemon=True, name='z8-preview-reaper').start()
        return result['url']
    except BaseException:
        child.terminate()
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=1)
        raise
    finally:
        child.stdout.close()


def preview_url(value, environment):
    root, filename = selected_file(value)
    token = environment.get('Z8_EVENT_TOKEN', '')
    launch = environment.get('Z8_LAUNCH_ID', '')
    if not bridge_module().live(environment):
        raise PreviewError('terminal unavailable')
    directory = runtime_directory()
    lock = None
    try:
        lock = os.open('start.lock', os.O_CREAT | os.O_RDWR | NOFOLLOW, 0o600, dir_fd=directory)
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise PreviewError('lock changed')
        deadline = time.monotonic() + 3
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PreviewError('preview busy')
                time.sleep(0.04)
        key = hashlib.sha256((launch + ':' + token).encode()).hexdigest()[:32]
        path = str(RUNTIME_ROOT / (key + '.sock'))
        if len(os.fsencode(path)) >= 104:
            raise PreviewError('socket path too long')
        message = {'action': 'open', 'token': token, 'root': root, 'filename': filename}
        try:
            result = control(path, message)
        except OSError as error:
            if error.errno not in (errno.ENOENT, errno.ECONNREFUSED):
                raise
            result = None
        if result is not None:
            if result.get('status') == 'ready':
                return result['url'], False
            if result.get('status') != 'different-root':
                raise PreviewError('existing preview unavailable')
            if control(path, {'action': 'stop', 'token': token}).get('status') != 'stopping':
                raise PreviewError('previous preview busy')
            deadline = time.monotonic() + 3
            while os.path.lexists(path):
                if time.monotonic() >= deadline:
                    raise PreviewError('previous preview still stopping')
                time.sleep(0.04)
        elif os.path.lexists(path):
            info = os.lstat(path)
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
                raise PreviewError('socket changed')
            os.unlink(path)
        return start_server(root, filename, path, environment), True
    finally:
        if lock is not None:
            os.close(lock)
        os.close(directory)


def stop_preview(environment, url):
    key = hashlib.sha256((environment.get('Z8_LAUNCH_ID', '') + ':' + environment.get('Z8_EVENT_TOKEN', '')).encode()).hexdigest()[:32]
    try:
        control(str(RUNTIME_ROOT / (key + '.sock')),
                {'action': 'stop', 'token': environment.get('Z8_EVENT_TOKEN', ''), 'url': url})
    except (OSError, ValueError, PreviewError):
        pass


class PreviewHTTP(http.server.HTTPServer):
    allow_reuse_address = False

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(2)
        # Per-read socket timeouts alone allow a trickling HTTP client to keep
        # the server busy indefinitely. Bound the entire connection as well.
        def expire():
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        self.connection_timer = threading.Timer(5, expire)
        self.connection_timer.daemon = True
        self.connection_timer.start()
        return connection, address

    def close_request(self, request):
        self.connection_timer.cancel()
        super().close_request(request)

    def handle_error(self, request, client_address):
        pass


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'z8-preview'
    sys_version = ''

    def log_message(self, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        # Never echo the request target, local filenames or query strings.
        body = b'Not available\n'
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def do_HEAD(self):
        self.serve_file(False)

    def do_GET(self):
        self.serve_file(True)

    def serve_file(self, body):
        fd = None
        try:
            if self.headers.get('Host') != '127.0.0.1:' + str(self.server.server_port):
                raise PreviewError('host rejected')
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or not parsed.path.startswith('/' + self.server.capability + '/'):
                raise PreviewError('URL rejected')
            relative = unquote(parsed.path[len(self.server.capability) + 2:], errors='strict')
            parts = safe_parts(relative)
            fd, info = file_fd(self.server.root_fd, parts)
        except (OSError, ValueError, UnicodeError, PreviewError):
            self.send_error(404)
            return
        try:
            self.server.last_activity = time.monotonic()
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(parts[-1])[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(info.st_size))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            if body:
                remaining = info.st_size
                while remaining:
                    chunk = os.read(fd, min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        finally:
            os.close(fd)


def serve(config, check_interval=CHECK_INTERVAL, idle_seconds=IDLE_SECONDS, max_seconds=MAX_SECONDS):
    environment = config['environment']
    bridge = bridge_module()
    if not bridge.live(environment):
        raise PreviewError('terminal unavailable')
    root, filename = selected_file(os.path.join(config['root'], config['filename']))
    root_fd = directory_fd(root)
    http = control_socket = None
    socket_identity = None
    stopped = False

    def stop(signum, frame):
        nonlocal stopped
        stopped = True

    def url(name):
        return 'http://127.0.0.1:%d/%s/%s' % (http.server_port, http.capability, quote(name, safe=''))

    try:
        http = PreviewHTTP(('127.0.0.1', 0), Handler)
        http.root_fd = root_fd
        http.capability = secrets.token_hex(24)
        http.last_activity = time.monotonic()
        control_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        control_socket.bind(config['socket'])
        os.chmod(config['socket'], 0o600)
        socket_identity = os.lstat(config['socket'])
        control_socket.listen(4)
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        # The caller consumes this single private pipe record; terminal stdout is
        # not inherited. Close the pipe immediately so command runners can return.
        print(json.dumps({'status': 'ready', 'url': url(filename)}), flush=True)
        sys.stdout.close()
        created = next_check = time.monotonic()
        while not stopped:
            now = time.monotonic()
            if now - created >= max_seconds or now - http.last_activity >= idle_seconds:
                break
            if now >= next_check:
                if not bridge.live(environment):
                    break
                next_check = time.monotonic() + check_interval
            ready, _, _ = select.select([http, control_socket], [], [], 0.5)
            if control_socket in ready:
                with control_socket.accept()[0] as client:
                    try:
                        request = read_frame(client)
                        if not isinstance(request.get('token'), str) or not hmac.compare_digest(request['token'], environment['Z8_EVENT_TOKEN']):
                            response = {'status': 'denied'}
                        elif request.get('action') == 'stop' and ('url' not in request or
                                isinstance(request['url'], str) and request['url'].startswith(
                                    'http://127.0.0.1:%d/%s/' % (http.server_port, http.capability))):
                            stopped = True
                            response = {'status': 'stopping'}
                        elif request.get('action') == 'open':
                            requested_root, name = selected_file(os.path.join(request['root'], request['filename']))
                            same = requested_root == root and os.path.samestat(os.stat(root, follow_symlinks=False), os.fstat(root_fd))
                            if same:
                                http.last_activity = time.monotonic()
                                response = {'status': 'ready', 'url': url(name)}
                            else:
                                response = {'status': 'different-root'}
                        else:
                            response = {'status': 'denied'}
                        client.sendall(json.dumps(response).encode() + b'\n')
                    except (OSError, ValueError, KeyError, TypeError, PreviewError):
                        pass
            if http in ready and not stopped:
                http.handle_request()
    finally:
        if http is not None:
            http.server_close()
        if control_socket is not None:
            control_socket.close()
        os.close(root_fd)
        if socket_identity is not None:
            try:
                if os.path.samestat(socket_identity, os.lstat(config['socket'])):
                    os.unlink(config['socket'])
            except OSError:
                pass


if __name__ == '__main__':
    try:
        if sys.argv[1:] != ['--serve']:
            raise PreviewError('internal entrypoint')
        raw = sys.stdin.buffer.readline(MAX_FRAME + 1)
        sys.stdin.close()
        if len(raw) > MAX_FRAME:
            raise PreviewError('config too long')
        serve(json.loads(raw))
    except (OSError, ValueError, KeyError, TypeError, PreviewError):
        sys.exit(1)
