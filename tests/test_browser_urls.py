"""Run the browser's real Java URL boundary without Android or network access."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BrowserUrlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-browser-url-test-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        probe = cls.directory / 'BrowserUrlProbe.java'
        probe.write_text(PROBE)
        actual = ROOT / 'overlay/app/src/main/java/com/termux/app/Z8BrowserUrls.java'
        result = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(cls.directory), str(actual), str(probe)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, name):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.BrowserUrlProbe', name],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS browser-url ' + name)

    def test_web_urls_preserve_path_query_and_fragment(self):
        self.probe('web')

    def test_script_file_content_and_intent_schemes_cannot_be_opened(self):
        self.probe('schemes')

    def test_userinfo_ambiguous_authorities_and_invalid_ports_are_rejected(self):
        self.probe('authority')

    def test_only_literal_loopback_hosts_can_render_inside_app(self):
        self.probe('preview')

    def test_authentication_query_and_fragment_never_appear_in_host_labels(self):
        self.probe('labels')

    def test_empty_control_characters_and_oversize_urls_fail_closed(self):
        self.probe('invalid')

    def test_cli_routes_blank_and_literal_loopback_inside_app(self):
        self.probe('request')


PROBE = r'''
package com.termux.app;

public final class BrowserUrlProbe {
    private static void eq(Object expected, Object actual) {
        if (!java.util.Objects.equals(expected, actual)) throw new AssertionError("URL policy mismatch");
    }
    private static void rejected(String... values) {
        for (String value : values) {
            eq(null, Z8BrowserUrls.normalize(value));
            eq(false, Z8BrowserUrls.isPreview(value));
            eq("Browser", Z8BrowserUrls.host(value));
        }
    }
    public static void main(String[] args) {
        switch (args[0]) {
            case "request":
                eq(Z8BrowserUrls.RequestTarget.BLANK, Z8BrowserUrls.requestTarget("about:blank"));
                // Blank is an action and remains excluded from WebView/Intent URL normalization.
                eq(null, Z8BrowserUrls.normalize("about:blank"));
                for (String value : new String[]{"http://localhost:3000/", "http://127.0.0.1:8080/?next=https://auth.test/", "http://[::1]:5173/"})
                    eq(Z8BrowserUrls.RequestTarget.PREVIEW, Z8BrowserUrls.requestTarget(value));
                for (String value : new String[]{"https://auth.example.test/oauth?redirect_uri=http://localhost:3000/", "https://localhost.evil.test/", "http://192.168.1.10/"})
                    eq(Z8BrowserUrls.RequestTarget.EXTERNAL, Z8BrowserUrls.requestTarget(value));
                for (String value : new String[]{"about:config", "about:blank#script", "about:blank?next=https://auth.test/", " ABOUT:blank ",
                        "file:///etc/passwd", "javascript:alert(1)", "data:text/html,hi", "http://user:pass@localhost/", "intent://localhost/"})
                    eq(Z8BrowserUrls.RequestTarget.INVALID, Z8BrowserUrls.requestTarget(value));
                break;
            case "web":
                eq("http://localhost:3000/", Z8BrowserUrls.normalize("localhost:3000/"));
                eq("http://127.0.0.1:8080/path?x=1#part", Z8BrowserUrls.normalize("  127.0.0.1:8080/path?x=1#part  "));
                eq("https://example.test/login?state=a%2Fb&code=c%3Dd#flow", Z8BrowserUrls.normalize("https://example.test/login?state=a%2Fb&code=c%3Dd#flow"));
                eq("https://example.test/%ED%95%9C%EA%B8%80", Z8BrowserUrls.normalize("https://example.test/한글"));
                eq("http://example.test:65535/", Z8BrowserUrls.normalize("http://example.test:65535/"));
                break;
            case "schemes":
                rejected("javascript:alert(1)", "javascript://localhost/alert(1)", "data:text/html,<script>alert(1)</script>",
                    "data://localhost/payload", "file:///data/data/private", "content://settings/system",
                    "intent://localhost/#Intent;scheme=http;end", "ftp://localhost:21/", "about:blank", "mailto:dev@example.test");
                break;
            case "authority":
                rejected("https://user:password@example.test/", "http://localhost@evil.test/", "http://evil.test@localhost/",
                    "http://localhost:0/", "http://localhost:65536/", "http://localhost:-1/", "http://localhost:abc/",
                    "http:///localhost/", "https://", "//localhost:3000/", "http://local_host/", "http://localhost\\@evil.test/",
                    "http://%6cocalhost/", "http://localhost%2Eevil.test/");
                break;
            case "preview":
                for (String value : new String[]{"localhost", "LOCALHOST:3000", "http://localhost/path?next=https://evil.test/",
                        "https://127.0.0.1:443/", "http://[::1]:8080/", "http://localhost/#@evil.test"})
                    eq(true, Z8BrowserUrls.isPreview(value));
                for (String value : new String[]{"https://example.test/", "http://localhost.evil.test/", "http://evil-localhost/",
                        "http://127.0.0.1.evil.test/", "http://127.0.0.2/", "http://127.1/", "http://2130706433/",
                        "http://0.0.0.0/", "http://192.168.1.10:3000/", "http://[::ffff:127.0.0.1]/",
                        "https://example.test/?next=http://localhost:3000/"})
                    eq(false, Z8BrowserUrls.isPreview(value));
                break;
            case "labels":
                eq("auth.example.test", Z8BrowserUrls.host("https://auth.example.test/authorize?code=Z8_TEST_SECRET&state=Z8_TEST_STATE#Z8_TEST_TOKEN"));
                eq("localhost", Z8BrowserUrls.host("http://localhost:53682/callback?code=Z8_TEST_SECRET"));
                eq("[::1]", Z8BrowserUrls.host("http://[::1]:53682/callback#Z8_TEST_TOKEN"));
                rejected("https://Z8_TEST_SECRET@auth.example.test/authorize");
                break;
            case "invalid":
                rejected(null, "", "   ", "http://localhost/path\nnext", "http://localhost/\rnext", "http://localhost/\tword",
                    "http://localhost/\u0000word", "http://localhost/\u007fword", "http://localhost/has space", "http://localhost/%zz");
                String prefix = "https://example.test/";
                String limit = prefix + "x".repeat(8192 - prefix.length());
                eq(limit, Z8BrowserUrls.normalize(limit));
                rejected(limit + "x");
                break;
            default: throw new AssertionError("Unknown test");
        }
        System.out.println("PASS browser-url " + args[0]);
    }
}
'''
