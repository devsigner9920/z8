"""Exercise browser helper through a real Unix socket, and native queue lifecycle.

No real URL is opened; Java handlers and PTYs are deterministic test doubles.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'runtime/guest/browser-open.py'
SPEC = importlib.util.spec_from_file_location('z8_browser_open', HELPER)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class BrowserHelperTests(unittest.TestCase):
    def test_http_urls_preserve_auth_state_without_interpretation(self):
        url = 'https://example.test/oauth?state=a%2Bb%26c&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Fcallback#f'
        event = helper.envelope(url, {'Z8_LAUNCH_ID': 'launch-1', 'Z8_EVENT_TOKEN': 'a' * 64})
        self.assertEqual(event['url'], url)
        self.assertEqual(set(event), {'schemaVersion', 'eventId', 'launchId', 'token', 'kind', 'url'})
        self.assertEqual(event['kind'], 'browser')
        self.assertTrue(helper.valid_url('http://[::1]:3000/'))
        self.assertTrue(helper.valid_url('http://127.0.0.1:3000/'))

    def test_rejects_non_web_urls_credentials_controls_and_invalid_ports(self):
        for url in ('file:///etc/passwd', 'javascript:alert(1)', 'intent://example', 'data:text/html,test',
                    'about:config', 'about:blank#script', 'about:blank?next=https://example.test/', 'ABOUT:blank', ' about:blank',
                    'http://user:password@example.test/', 'https:///no-host', 'https://example.test:0',
                    'https://example.test:65536', 'https://example.test:-2', 'https://x/\nsecret',
                    'https://x/%0aheader', 'https://x\\y/', ' https://x/', 'https://x/ space', 'https://x/' + 'a' * 8192):
            with self.subTest(url=url[:80]): self.assertFalse(helper.valid_url(url))
        self.assertIsNone(helper.envelope('https://x/', {'Z8_LAUNCH_ID': 'ok', 'Z8_EVENT_TOKEN': 'not-a-token'}))

    def test_exact_blank_tab_uses_authenticated_request(self):
        event = helper.envelope('about:blank', {'Z8_LAUNCH_ID': 'launch-blank', 'Z8_EVENT_TOKEN': 'a' * 64})
        self.assertEqual((event['kind'], event['url']), ('browser', 'about:blank'))
        self.assertIsNone(helper.envelope('about:blank', {}))

    def test_real_socket_delivery_is_silent_and_no_shell_runs(self):
        with tempfile.TemporaryDirectory(prefix='z8-browser-', dir='/tmp') as directory:
            path = str(Path(directory) / 'events.sock')
            received = []
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(path); server.listen(1); server.settimeout(2)
                def receive():
                    with server.accept()[0] as client:
                        received.append(json.loads(client.makefile('rb').readline()))
                        client.sendall(b'{"status":"accepted"}\n')
                worker = threading.Thread(target=receive); worker.start()
                # Shell punctuation stays URL data in JSON, not another command.
                url = 'https://example.test/?state=$(touch%20NEVER)&q=semi;colon'
                result = subprocess.run([sys.executable, str(HELPER), '--', url], capture_output=True, timeout=3,
                    env=dict(os.environ, Z8_LAUNCH_ID='launch-1', Z8_EVENT_TOKEN='a' * 64, Z8_EVENT_SOCKET=path), cwd=directory)
                worker.join(3)
                self.assertFalse(worker.is_alive())
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b'', b''))
                self.assertEqual(received[0]['url'], url)
                self.assertFalse((Path(directory) / 'NEVER').exists())

    def test_failure_does_not_echo_url_token_or_socket_path(self):
        url = 'https://example.test/?code=PRIVATE_AUTH_CODE'
        result = subprocess.run([sys.executable, str(HELPER), url], capture_output=True, timeout=3,
            env=dict(os.environ, Z8_LAUNCH_ID='launch-1', Z8_EVENT_TOKEN='a' * 64, Z8_EVENT_SOCKET='/tmp/PRIVATE_SOCKET'))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')
        self.assertNotIn(b'PRIVATE', result.stderr)
        self.assertNotIn(b'a' * 64, result.stderr)

    def test_idle_server_has_bounded_wait(self):
        with tempfile.TemporaryDirectory(prefix='z8-browser-', dir='/tmp') as directory:
            path = str(Path(directory) / 'events.sock')
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(path); server.listen(1)
                started = time.monotonic()
                result = subprocess.run([sys.executable, str(HELPER), 'https://example.test/'], capture_output=True, timeout=3,
                    env=dict(os.environ, Z8_LAUNCH_ID='launch-1', Z8_EVENT_TOKEN='a' * 64, Z8_EVENT_SOCKET=path))
                self.assertEqual(result.returncode, 1)
                self.assertLess(time.monotonic() - started, 2.5)

    def test_profile_survives_login_path_reset_preserves_personal_browser(self):
        profile = ROOT / 'runtime/guest/browser-profile.sh'
        result = subprocess.run(['bash', '-c', 'source "$1"; printf "%s\\n%s\\n%s\\n" "$PATH" "$BROWSER" "$GH_BROWSER"', 'test', str(profile)],
            capture_output=True, text=True, check=True,
            env={'HOME': '/z8/home', 'Z8_LAUNCH_ID': 'live', 'PATH': '/usr/bin:/bin', 'BROWSER': '/personal/browser'})
        self.assertEqual(result.stdout.splitlines(), ['/usr/local/lib/z8/browser/bin:/usr/bin:/bin', '/personal/browser', '/personal/browser'])


class BrowserQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java: raise unittest.SkipTest('A JDK is required')
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-browser-queue-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        sources = []
        for name, source in STUBS.items():
            path = cls.directory / name
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(source); sources.append(str(path))
        sources += [str(ROOT / 'overlay/app/src/main/java/com/termux/app' / name)
                    for name in ('Z8BrowserBridge.java', 'Z8BrowserUrls.java', 'Z8SessionOrigin.java')]
        result = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(cls.directory), *sources], capture_output=True, text=True, timeout=30)
        if result.returncode: raise AssertionError(result.stdout + result.stderr)

    def probe(self, scenario):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.BrowserProbe', scenario], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_only_consumes_in_attached_foreground_ui(self): self.probe('foreground')
    def test_stale_unowned_or_expired_sessions_never_open(self): self.probe('stale')
    def test_queue_capacity_and_duplicate_delivery(self): self.probe('limits')
    def test_native_http_parser_rejects_unsafe_intents(self): self.probe('urls')
    def test_blank_request_retains_original_project_and_session(self): self.probe('blank')


STUBS = {
    'android/os/SystemClock.java': '''package android.os;public class SystemClock {public static long now=1;
        public static long elapsedRealtime(){return now;}}''',
    'android/os/Looper.java': '''package android.os;public class Looper {public static Looper getMainLooper(){return new Looper();}}''',
    'android/os/Handler.java': '''package android.os;import java.util.*;public class Handler {
        public Handler(Looper looper){}static final List<Runnable> tasks=new ArrayList<>();
        public boolean post(Runnable task){tasks.add(task);return true;}
        public boolean postDelayed(Runnable task,long delay){return true;}
        public void removeCallbacks(Runnable task){tasks.remove(task);}
        public static void drain(){while(!tasks.isEmpty())tasks.remove(0).run();}}''',
    'com/termux/terminal/TerminalSession.java': '''package com.termux.terminal;public class TerminalSession {
        public final String mHandle;public boolean running=true;public TerminalSession(String h){mHandle=h;}
        public boolean isRunning(){return running;}}''',
    'com/termux/app/BrowserProbe.java': '''package com.termux.app;
        import com.termux.terminal.TerminalSession;import android.os.*;import java.util.*;
        public class BrowserProbe {
            static void check(boolean good){if(!good)throw new AssertionError();}
            static TerminalSession session(String id){TerminalSession s=new TerminalSession(id);Z8SessionOrigin.remember(s,"project-"+id,"Project "+id);return s;}
            static String send(TerminalSession s,String id){return Z8BrowserBridge.submit(s,id,"https://example.test/?state=secret");}
            public static void main(String[] args){
                List<Z8BrowserBridge.Request> opened=new ArrayList<>();
                Z8BrowserBridge.Listener listener=request->{opened.add(request);return true;};
                TerminalSession one=session("one");
                switch(args[0]) {
                case "foreground":
                    check(send(one,"event").equals("accepted"));Handler.drain();check(opened.isEmpty());
                    Z8BrowserBridge.attach(listener);Z8BrowserBridge.detach(listener);Handler.drain();check(opened.isEmpty());
                    Z8BrowserBridge.attach(listener);Handler.drain();check(opened.size()==1&&Z8BrowserBridge.pendingCount()==0);
                    check(opened.get(0).projectId.equals("project-one")&&opened.get(0).sessionHandle.equals("one"));
                    Z8BrowserBridge.detach(listener);
                    Z8BrowserBridge.Listener refusing=request->false;check(send(one,"second").equals("accepted"));
                    Z8BrowserBridge.attach(refusing);Handler.drain();check(Z8BrowserBridge.pendingCount()==1);
                    Z8BrowserBridge.attach(listener);Handler.drain();check(opened.size()==2);break;
                case "stale":
                    check(send(null,"id").equals("stale"));check(send(new TerminalSession("unknown"),"id").equals("stale"));
                    check(send(one,"event").equals("accepted"));one.running=false;
                    Z8BrowserBridge.attach(listener);Handler.drain();check(opened.isEmpty()&&Z8BrowserBridge.pendingCount()==0);
                    one.running=true;check(send(one,"second").equals("accepted"));SystemClock.now+=120001;
                    Z8BrowserBridge.attach(listener);Handler.drain();check(opened.isEmpty()&&Z8BrowserBridge.pendingCount()==0);break;
                case "limits":
                    check(send(one,"event").equals("accepted"));check(send(one,"event").equals("duplicate"));check(send(one,"second").equals("busy"));
                    for(int i=0;i<15;i++)check(send(session("more"+i),"event").equals("accepted"));
                    check(send(session("overflow"),"event").equals("busy"));check(Z8BrowserBridge.pendingCount()==16);
                    Z8BrowserBridge.attach(listener);Handler.drain();check(opened.size()==16);
                    check(send(one,"event").equals("duplicate"));Z8BrowserBridge.clear();check(send(one,"event").equals("accepted"));break;
                case "urls":
                    for(String u:new String[]{"https://example.test/oauth?state=a%2Bb", "http://127.0.0.1:3000/", "http://[::1]:3000/", "about:blank"})check(Z8BrowserBridge.validUrl(u));
                    for(String u:new String[]{"file:///secret","intent://browser","javascript:alert(1)","https://user:pass@example.test/","https:///missing","https://x:65536/","https://x:0/","https://x/%0Dheader","https://x/ space","https://x/\\nsecret", "about:config", "about:blank#script", "about:blank?next=https://example.test/", "ABOUT:blank", " about:blank"})check(!Z8BrowserBridge.validUrl(u));break;
                case "blank":
                    check(Z8BrowserBridge.submit(one,"blank","about:blank").equals("accepted"));
                    Z8BrowserBridge.attach(listener);Handler.drain();check(opened.size()==1);
                    check(opened.get(0).url.equals("about:blank")&&opened.get(0).sessionHandle.equals("one")
                        &&opened.get(0).projectId.equals("project-one"));break;
                default:throw new AssertionError(args[0]);
                }
                System.out.println("PASS browser "+args[0]);
            }
        }'''
}
