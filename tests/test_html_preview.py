"""Real loopback/Unix socket tests; only synthetic pages, no browser/account."""
import contextlib
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preview = load('z8_html_test', ROOT / 'runtime/guest/html-preview.py')
browser = load('z8_browser_test', ROOT / 'runtime/guest/browser-open.py')


class LeaseServer:
    def __init__(self, path):
        self.path = str(path)
        self.active = True
        self.browser_status = 'accepted'
        self.events = []
        self.stopped = threading.Event()
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(16)
        self.server.settimeout(.1)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stopped.is_set():
            try:
                client, _ = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with client:
                try:
                    event = preview.read_frame(client)
                    self.events.append(event)
                    status = ('accepted' if self.active else 'stale') if event['kind'] == 'preview-check' else self.browser_status
                    client.sendall(json.dumps({'status': status}).encode() + b'\n')
                except (OSError, ValueError, RuntimeError):
                    pass

    def close(self):
        self.stopped.set()
        self.server.close()
        self.thread.join(1)


class HTMLPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='z8-html-', dir='/tmp')
        self.base = Path(self.temporary.name).resolve()
        self.site = self.base / 'site'
        self.site.mkdir()
        (self.site / 'index.html').write_text('<!doctype html><link rel="stylesheet" href="style.css"><script src="assets/app.js"></script>')
        (self.site / 'other.htm').write_text('<h1>Second page</h1>')
        (self.site / 'style.css').write_text('body { color: red; }')
        (self.site / 'assets').mkdir()
        (self.site / 'assets/app.js').write_text('window.syntheticQA = true;')
        self.lease = LeaseServer(self.base / 'events.sock')
        self.environment = {'Z8_LAUNCH_ID': 'qa-launch', 'Z8_EVENT_TOKEN': 'a' * 64, 'Z8_EVENT_SOCKET': self.lease.path}
        self.runtime_patch = mock.patch.object(preview, 'RUNTIME_ROOT', self.base / 'runtime')
        self.runtime_patch.start()
        self.urls = []

    def tearDown(self):
        for url in self.urls:
            preview.stop_preview(self.environment, url)
        self.wait_until(lambda: not list((self.base / 'runtime').glob('*.sock')), 2)
        self.lease.close()
        self.runtime_patch.stop()
        self.temporary.cleanup()

    def wait_until(self, predicate, seconds=2):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(.03)
        return predicate()

    def open(self, filename='index.html', directory=None):
        url, created = preview.preview_url(str((directory or self.site) / filename), self.environment)
        self.urls.append(url)
        return url, created

    def request(self, url, path=None, method='GET', headers=None):
        target = urlsplit(url)
        with contextlib.closing(http.client.HTTPConnection(target.hostname, target.port, timeout=2)) as client:
            client.request(method, target.path if path is None else path, headers=headers or {})
            response = client.getresponse()
            return response.status, dict(response.getheaders()), response.read()

    def test_real_html_relative_assets_head_and_live_edits(self):
        url, created = self.open()
        self.assertTrue(created)
        status, headers, body = self.request(url)
        self.assertEqual(status, 200)
        self.assertIn(b'<!doctype html>', body)
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        base = urlsplit(url).path.rsplit('/', 1)[0]
        self.assertEqual(self.request(url, base + '/style.css')[2], b'body { color: red; }')
        self.assertEqual(self.request(url, base + '/assets/app.js')[2], b'window.syntheticQA = true;')
        status, headers, body = self.request(url, method='HEAD')
        self.assertEqual((status, body), (200, b''))
        self.assertEqual(int(headers['Content-Length']), (self.site / 'index.html').stat().st_size)
        (self.site / 'updated.html').write_text('<h1>updated</h1>')
        os.replace(self.site / 'updated.html', self.site / 'index.html')
        self.assertEqual(self.request(url)[2], b'<h1>updated</h1>')
        next_url, created = self.open('other.htm')
        self.assertFalse(created)
        self.assertEqual(urlsplit(next_url).port, urlsplit(url).port)
        self.assertEqual(self.request(next_url)[2], b'<h1>Second page</h1>')

    def test_no_listing_traversal_hidden_symlinks_or_other_folders(self):
        outside = self.base / 'PRIVATE.txt'
        outside.write_text('PRIVATE OUTSIDE CONTENT')
        (self.site / 'escape.txt').symlink_to(outside)
        (self.site / 'linked').symlink_to(self.base, target_is_directory=True)
        (self.site / '.env').write_text('PRIVATE DOT CONTENT')
        (self.site / '.codex').mkdir()
        (self.site / '.codex/auth.json').write_text('SYNTHETIC SECRET')
        url, _ = self.open()
        base = urlsplit(url).path.rsplit('/', 1)[0]
        for path in ('/', base + '/', base + '/assets/', base + '/escape.txt', base + '/linked/PRIVATE.txt',
                     base + '/.env', base + '/.codex/auth.json', base + '/%2e%2e/PRIVATE.txt',
                     base + '/%2Eenv', base + '/assets/../../PRIVATE.txt', base + '//index.html',
                     base + '/%2findex.html', base + '/assets%5capp.js', '/wrong-cap/index.html'):
            with self.subTest(path=path):
                status, _, body = self.request(url, path)
                self.assertEqual(status, 404)
                self.assertNotIn(b'PRIVATE', body)
                self.assertNotIn(b'SYNTHETIC', body)
        self.assertEqual(self.request(url, headers={'Host': 'attacker.example'})[0], 404)
        self.assertEqual(self.request(url, method='POST')[0], 501)

    def test_rejects_initial_symlink_hidden_non_html_and_special_files(self):
        (self.site / 'link.html').symlink_to(self.site / 'index.html')
        linked_directory = self.base / 'link-dir'
        linked_directory.symlink_to(self.site, target_is_directory=True)
        (self.site / '.hidden.html').write_text('hidden')
        os.mkfifo(self.site / 'fifo.html')
        for name in (self.site / 'link.html', linked_directory / 'index.html', self.site / '.hidden.html',
                     self.site / 'style.css', self.site / 'fifo.html', self.site / 'missing.html'):
            with self.subTest(path=name):
                with self.assertRaises((OSError, preview.PreviewError)):
                    preview.selected_file(str(name))

    def test_root_directory_swap_cannot_expand_access(self):
        url, _ = self.open()
        moved = self.base / 'moved'
        self.site.rename(moved)
        self.site.symlink_to(self.base, target_is_directory=True)
        (self.base / 'index.html').write_text('OUTSIDE ROOT')
        self.assertIn(b'<!doctype html>', self.request(url)[2])
        self.assertNotIn(b'OUTSIDE', self.request(url)[2])

    def test_new_directory_replaces_only_this_terminal_server(self):
        old_url, _ = self.open()
        other = self.base / 'second'
        other.mkdir()
        (other / 'index.html').write_text('second directory')
        new_url, created = self.open(directory=other)
        self.assertTrue(created)
        self.assertEqual(self.request(new_url)[2], b'second directory')
        with self.assertRaises(OSError):
            self.request(old_url)
        # A delayed failed delivery for the prior server cannot stop its replacement.
        preview.stop_preview(self.environment, old_url)
        self.assertEqual(self.request(new_url)[0], 200)

    def test_dispatcher_delivers_real_loopback_url_and_sanitizes_failures(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(browser, 'load_preview', return_value=preview), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = browser.main([str(self.site / 'index.html')], self.environment)
        self.assertEqual((result, out.getvalue(), err.getvalue()), (0, '', ''))
        event = next(event for event in self.lease.events if event['kind'] == 'browser')
        self.urls.append(event['url'])
        self.assertEqual(self.request(event['url'])[0], 200)
        self.assertEqual({e['kind'] for e in self.lease.events}, {'browser', 'preview-check'})
        err = io.StringIO()
        with mock.patch.object(browser, 'load_preview', return_value=preview), contextlib.redirect_stderr(err):
            self.assertEqual(browser.main([str(self.site / 'PRIVATE-missing.html')], self.environment), 1)
        self.assertNotIn('PRIVATE', err.getvalue())
        self.assertNotIn('Traceback', err.getvalue())
        self.assertNotIn(str(self.base), err.getvalue())

    def test_delivery_failure_closes_new_server_and_no_runtime_for_stale_launch(self):
        self.lease.browser_status = 'busy'
        with mock.patch.object(browser, 'load_preview', return_value=preview), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(browser.main([str(self.site / 'index.html')], self.environment), 1)
        self.assertTrue(self.wait_until(lambda: not list((self.base / 'runtime').glob('*.sock'))))
        self.lease.active = False
        with self.assertRaises(preview.PreviewError):
            self.open()

    def test_runtime_death_removes_socket_and_stops_http(self):
        url, _ = self.open()
        self.lease.active = False
        self.assertTrue(self.wait_until(lambda: not list((self.base / 'runtime').glob('*.sock')), 12))
        with self.assertRaises(OSError):
            self.request(url)

    def test_android_inherited_setgid_runtime_directory_is_private(self):
        runtime = self.base / 'runtime'
        runtime.mkdir(mode=0o700)
        runtime.chmod(0o2700)
        self.assertEqual(runtime.stat().st_mode & 0o777, 0o700)
        url, _ = self.open()
        self.assertEqual(self.request(url)[0], 200)

    def short_server(self, idle, maximum):
        control_path = str(self.base / 'short.sock')
        config = {'root': str(self.site), 'filename': 'index.html', 'socket': control_path, 'environment': self.environment}
        code = "import importlib.util,json,sys; s=importlib.util.spec_from_file_location('p',sys.argv[1]); p=importlib.util.module_from_spec(s); s.loader.exec_module(p); p.serve(json.loads(sys.stdin.readline()),check_interval=.05,idle_seconds=float(sys.argv[2]),max_seconds=float(sys.argv[3]))"
        child = subprocess.Popen([sys.executable, '-I', '-c', code, str(ROOT / 'runtime/guest/html-preview.py'), str(idle), str(maximum)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        child.stdin.write(json.dumps(config) + '\n'); child.stdin.close()
        result = json.loads(child.stdout.readline())
        return child, result['url'], control_path

    def test_idle_and_absolute_lifetime_bounds(self):
        child, url, path = self.short_server(.25, 5)
        try:
            self.assertEqual(self.request(url)[0], 200)
            self.assertEqual(child.wait(timeout=2), 0)
            self.assertFalse(os.path.lexists(path))
        finally:
            if child.poll() is None: child.kill(); child.wait()
            child.stdout.close(); child.stderr.close()
        child, url, path = self.short_server(5, .5)
        try:
            deadline = time.monotonic() + 2
            while child.poll() is None and time.monotonic() < deadline:
                try: self.request(url)
                except OSError: break
                time.sleep(.06)
            self.assertEqual(child.wait(timeout=2), 0)
            self.assertFalse(os.path.lexists(path))
        finally:
            if child.poll() is None: child.kill(); child.wait()
            child.stdout.close(); child.stderr.close()


if __name__ == '__main__':
    unittest.main()
