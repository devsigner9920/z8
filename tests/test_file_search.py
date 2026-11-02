"""Compile and exercise the actual bounded Java tree search on real directories."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FileSearchTests(unittest.TestCase):
    def test_real_tree_and_limits(self):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not java:
            self.skipTest('A JDK is required')
        with tempfile.TemporaryDirectory(prefix='z8-file-search-') as temporary:
            directory = Path(temporary).resolve()
            probe = directory / 'FileSearchProbe.java'
            probe.write_text(JAVA_PROBE)
            source = ROOT / 'overlay/app/src/main/java/com/termux/app/Z8FileSearch.java'
            compiled = subprocess.run([javac, '-encoding', 'UTF-8', '-d', str(directory), str(source), str(probe)],
                                      capture_output=True, text=True, timeout=45)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            run = subprocess.run([java, '-cp', str(directory), 'com.termux.app.FileSearchProbe', str(directory)],
                                 capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('PASS: 16 search scenarios', run.stdout)


JAVA_PROBE = r'''
package com.termux.app;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public final class FileSearchProbe {
    static int count;
    interface Action { void run() throws Exception; }
    static void check(boolean value, String label) { if (!value) throw new AssertionError(label); count++; }
    static void denied(Action action, String label) throws Exception {
        try { action.run(); } catch (IOException | IllegalArgumentException expected) { count++; return; }
        throw new AssertionError(label);
    }
    static void file(Path path) throws Exception { Files.createDirectories(path.getParent()); Files.write(path, new byte[0]); }
    static Z8FileSearch.Result find(Path root, String query) throws Exception { return Z8FileSearch.search(root.toFile(), query, () -> false); }
    static boolean has(Z8FileSearch.Result result, String path) { return result.matches.stream().anyMatch(match -> match.relative.equals(path)); }
    public static void main(String[] args) throws Exception {
        Path storage = Paths.get(args[0]);
        Path root = Files.createDirectory(storage.resolve("tree"));
        file(root.resolve("src/README.md")); file(root.resolve("src/설정.java"));
        file(root.resolve("node_modules.txt")); file(root.resolve(".hidden/config"));
        check(has(find(root, "SRC/read"), "src/README.md"), "relative path case-insensitive matching");
        check(has(find(root, "설정"), "src/설정.java"), "Korean filename matching");
        Locale previous = Locale.getDefault(); Locale.setDefault(new Locale("tr", "TR"));
        try { file(root.resolve("INDEX.TXT")); check(has(find(root, "index"), "INDEX.TXT"), "Locale.ROOT independent of device locale"); }
        finally { Locale.setDefault(previous); }
        for (String ignored : new String[] {".git", "node_modules", "build", ".gradle"}) file(root.resolve(ignored + "/secret.txt"));
        Z8FileSearch.Result ignored = find(root, "secret");
        check(ignored.matches.isEmpty() && ignored.ignoredDirectories == 4, "default ignored directories");
        check(has(find(root, "node_modules"), "node_modules.txt") && has(find(root, "hidden"), ".hidden/config"), "ordinary same-prefix and hidden files searched");
        Path external = Files.createDirectory(storage.resolve("outside")); file(external.resolve("secret.txt"));
        Files.createSymbolicLink(root.resolve("link-dir"), external);
        Files.createSymbolicLink(root.resolve("link-file"), external.resolve("secret.txt"));
        Z8FileSearch.Result links = find(root, "link");
        check(links.matches.isEmpty() && links.ignoredLinks == 2, "file and directory links never followed");
        Path linkedRoot = storage.resolve("linked-root"); Files.createSymbolicLink(linkedRoot, root);
        denied(() -> find(linkedRoot, "read"), "root symlink containment");
        denied(() -> find(linkedRoot.resolve("src"), "read"), "ancestor symlink containment");
        denied(() -> find(root, "\n"), "invalid query rejected");
        Files.write(root.resolve("body.txt"), "needle-only-in-content".getBytes(StandardCharsets.UTF_8));
        check(find(root, "needle-only-in-content").matches.isEmpty(), "no file content searching");
        Path many = Files.createDirectory(storage.resolve("many"));
        for (int index = 0; index < 220; index++) file(many.resolve("match-" + index));
        Z8FileSearch.Result capped = find(many, "match");
        check(capped.matches.size() == 200 && capped.limits.contains(Z8FileSearch.Limit.RESULTS), "result cap");
        Z8FileSearch.Result visited = Z8FileSearch.search(many.toFile(), "absent", () -> false,
            new Z8FileSearch.Bounds(32, 3, 200, 3000), System::nanoTime);
        check(visited.visited == 3 && visited.limits.contains(Z8FileSearch.Limit.VISITED), "visited cap");
        Path deep = Files.createDirectory(storage.resolve("deep"));
        file(deep.resolve("a/b/c/match.txt"));
        Z8FileSearch.Result depth = Z8FileSearch.search(deep.toFile(), "match", () -> false,
            new Z8FileSearch.Bounds(2, 20000, 200, 3000), System::nanoTime);
        check(depth.matches.isEmpty() && depth.limits.contains(Z8FileSearch.Limit.DEPTH), "depth cap");
        long[] ticks = {0};
        Z8FileSearch.Result timed = Z8FileSearch.search(many.toFile(), "match", () -> false,
            new Z8FileSearch.Bounds(32, 20000, 200, 1), () -> { long before = ticks[0]; ticks[0] += 1000000; return before; });
        check(timed.matches.isEmpty() && timed.limits.contains(Z8FileSearch.Limit.TIME), "deterministic time cap");
        Z8FileSearch.Result cancelled = Z8FileSearch.search(many.toFile(), "match", () -> true);
        check(cancelled.visited == 0 && cancelled.limits.contains(Z8FileSearch.Limit.CANCELLED), "cancellation before IO");
        file(root.resolve("unsafe\\name"));
        Z8FileSearch.Result unusual = find(root, "unsafe");
        check(unusual.matches.isEmpty() && unusual.limits.contains(Z8FileSearch.Limit.UNSUPPORTED_NAME), "unopenable path component excluded explicitly");
        if (count != 16) throw new AssertionError("scenario count " + count);
        System.out.println("PASS: 16 search scenarios");
    }
}
'''
