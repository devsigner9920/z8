"""Verify the real asynchronous preview-data coordinator without device data or network."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PreviewDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-preview-data-test-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        probe = cls.directory / 'PreviewDataProbe.java'
        probe.write_text(PROBE)
        actual = ROOT / 'overlay/app/src/main/java/com/termux/app/Z8PreviewDataOperation.java'
        result = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(cls.directory), str(actual), str(probe)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, name):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.PreviewDataProbe', name],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS preview-data ' + name)

    def test_completion_waits_for_provider_and_blocks_duplicate_requests(self):
        self.probe('callback')

    def test_unsupported_provider_does_not_stop_previews_or_delete_anything(self):
        self.probe('unsupported')

    def test_failure_never_claims_complete_and_late_callback_cannot_change_result(self):
        self.probe('failure')

    def test_detached_or_broken_observer_cannot_cancel_operation(self):
        self.probe('observers')

    def test_previous_callback_cannot_complete_a_new_deletion(self):
        self.probe('generation')

    def test_synchronous_provider_callback_is_supported(self):
        self.probe('synchronous')


PROBE = r'''
package com.termux.app;

public final class PreviewDataProbe {
    private static void eq(Object expected, Object actual) {
        if (!java.util.Objects.equals(expected, actual)) throw new AssertionError("Preview deletion state mismatch: " + expected + " != " + actual);
    }
    private static final class Backend implements Z8PreviewDataOperation.Backend {
        Z8PreviewDataOperation operation;
        boolean available = true, failSupport, failStop, failDelete, synchronous;
        int stops, deletes; Runnable callback;
        @Override public boolean supported() {
            if (failSupport) throw new RuntimeException("test");
            return available;
        }
        @Override public void stopPreviews() {
            eq(true, operation.running()); // The reload gate must close before renderer destruction.
            stops++;
            if (failStop) throw new RuntimeException("test");
        }
        @Override public void delete(Runnable done) {
            eq(true, operation.running()); eq(stops, deletes + 1);
            deletes++; callback = done;
            if (failDelete) throw new RuntimeException("test");
            if (synchronous) done.run();
        }
        Z8PreviewDataOperation create() { return operation = new Z8PreviewDataOperation(this); }
    }
    public static void main(String[] args) {
        Backend backend = new Backend();
        Z8PreviewDataOperation operation = backend.create();
        switch (args[0]) {
            case "callback":
                eq(Z8PreviewDataOperation.State.IDLE, operation.state());
                eq(true, operation.start());
                eq(Z8PreviewDataOperation.State.RUNNING, operation.state());
                eq(false, operation.start()); eq(1, backend.stops); eq(1, backend.deletes);
                backend.callback.run();
                eq(Z8PreviewDataOperation.State.COMPLETE, operation.state());
                eq(false, operation.running());
                backend.callback.run(); eq(Z8PreviewDataOperation.State.COMPLETE, operation.state());
                break;
            case "unsupported":
                backend.available = false; eq(false, operation.start());
                eq(Z8PreviewDataOperation.State.UNSUPPORTED, operation.state());
                eq(0, backend.stops); eq(0, backend.deletes); eq(null, backend.callback);
                backend.available = true; eq(true, operation.start());
                eq(Z8PreviewDataOperation.State.RUNNING, operation.state());
                break;
            case "failure":
                backend.failSupport = true; eq(false, operation.start());
                eq(Z8PreviewDataOperation.State.FAILED, operation.state()); eq(0, backend.stops); eq(0, backend.deletes);
                backend.failSupport = false; backend.failStop = true; eq(false, operation.start());
                eq(Z8PreviewDataOperation.State.FAILED, operation.state()); eq(0, backend.deletes);
                backend = new Backend(); operation = backend.create(); backend.failDelete = true;
                eq(false, operation.start()); eq(Z8PreviewDataOperation.State.FAILED, operation.state());
                backend.callback.run(); eq(Z8PreviewDataOperation.State.FAILED, operation.state());
                break;
            case "observers":
                int[] first = {0}, second = {0};
                Runnable observer = () -> first[0]++;
                operation.observe(observer); operation.observe(observer);
                operation.observe(() -> { throw new RuntimeException("detached UI"); });
                operation.observe(() -> second[0]++);
                operation.start(); eq(1, first[0]); eq(1, second[0]);
                operation.forget(observer);
                backend.callback.run();
                eq(1, first[0]); eq(2, second[0]); eq(Z8PreviewDataOperation.State.COMPLETE, operation.state());
                break;
            case "generation":
                operation.start(); Runnable old = backend.callback; old.run();
                operation.start(); old.run();
                eq(Z8PreviewDataOperation.State.RUNNING, operation.state());
                backend.callback.run(); eq(Z8PreviewDataOperation.State.COMPLETE, operation.state());
                eq(2, backend.stops); eq(2, backend.deletes);
                break;
            case "synchronous":
                backend.synchronous = true;
                eq(true, operation.start()); eq(Z8PreviewDataOperation.State.COMPLETE, operation.state());
                break;
            default: throw new AssertionError("Unknown test");
        }
        System.out.println("PASS preview-data " + args[0]);
    }
}
'''
