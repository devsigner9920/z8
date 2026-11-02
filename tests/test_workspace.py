"""Exercise actual Java filesystem helpers with an isolated temporary source tree."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceStorageTests(unittest.TestCase):
    def test_real_java_storage_and_conflicts(self):
        jdk = ROOT / ".local/jdk/Contents/Home/bin"
        javac = str(jdk / "javac") if (jdk / "javac").is_file() else shutil.which("javac")
        java = str(jdk / "java") if (jdk / "java").is_file() else shutil.which("java")
        if not javac or not java:
            self.skipTest("A JDK is required for filesystem helper tests")
        with tempfile.TemporaryDirectory(prefix="z8-workspace-tests-") as temporary:
            directory = Path(temporary).resolve()
            context = directory / "android/content/Context.java"
            context.parent.mkdir(parents=True)
            context.write_text("package android.content; public abstract class Context { public abstract java.io.File getFilesDir(); }")
            test = directory / "WorkspaceStorageProbe.java"
            test.write_text(JAVA_PROBE)
            sources = ROOT / "overlay/app/src/main/java/com/termux/app"
            compiled = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), "-encoding", "UTF-8", "-d", str(directory),
                str(context), str(sources / "Z8Files.java"), str(sources / "Z8Projects.java"), str(test)],
                capture_output=True, text=True, timeout=45)
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            tested = subprocess.run([java, "-cp", str(directory), "com.termux.app.WorkspaceStorageProbe",
                str(directory / "storage")], capture_output=True, text=True, timeout=30)
            self.assertEqual(0, tested.returncode, tested.stdout + tested.stderr)
            self.assertIn("PASS: 29 filesystem scenarios", tested.stdout)


JAVA_PROBE = r'''
package com.termux.app;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class WorkspaceStorageProbe {
    interface Action { void run() throws Exception; }
    static int assertions;
    static void check(boolean value, String label) {
        if (!value) throw new AssertionError(label);
        assertions++;
    }
    static void denied(Action action, String label) throws Exception {
        try { action.run(); } catch (IOException expected) { assertions++; return; }
        throw new AssertionError(label);
    }
    public static void main(String[] args) throws Exception {
        File storage = new File(args[0]);
        Z8Projects projects = new Z8Projects(storage);
        Z8Projects.Project project = projects.create("작업 공간");
        check(projects.list().size() == 1 && projects.open(project.id).name.equals("작업 공간"), "persist project metadata");
        check(project.source.getPath().endsWith(project.id + "/source"), "source separated from environment");
        denied(() -> projects.open("../../outside"), "project ID traversal");
        denied(() -> Z8Files.create(project.source, "", "../escape", false), "entry traversal");
        Z8Files.create(project.source, "", "nested space", true);
        check(Z8Files.directory(project.source, "nested space").isDirectory(), "spaces in valid paths");
        Z8Files.create(project.source, "nested space", "test.txt", false);
        String relative = "nested space/test.txt";
        Z8Files.Document blank = Z8Files.read(project.source, relative);
        Z8Files.Document saved = Z8Files.save(project.source, relative, blank.version, "hello 한글\n");
        check(saved.text.equals("hello 한글\n"), "UTF8 atomic save and read");
        Path file = new File(project.source, relative).toPath();
        Files.write(file, "external edit\n".getBytes(StandardCharsets.UTF_8));
        denied(() -> Z8Files.save(project.source, relative, saved.version, "overwrite"), "external write conflict");
        check(Z8Files.read(project.source, relative).text.equals("external edit\n"), "conflict preserves disk content");
        Z8Files.Document current = Z8Files.read(project.source, relative);
        Path replacement = file.resolveSibling("replacement");
        Files.write(replacement, current.text.getBytes(StandardCharsets.UTF_8));
        Files.move(replacement, file, StandardCopyOption.REPLACE_EXISTING);
        denied(() -> Z8Files.save(project.source, relative, current.version, "overwrite"), "same content replacement conflicts");
        File external = new File(storage.getParentFile(), "outside"); external.mkdir();
        Files.createSymbolicLink(new File(project.source, "escape").toPath(), external.toPath());
        denied(() -> Z8Files.directory(project.source, "escape"), "directory symlink escape");
        Files.createSymbolicLink(new File(project.source, "link.txt").toPath(), file);
        denied(() -> Z8Files.read(project.source, "link.txt"), "file symlink read");
        Z8Files.create(project.source, "", "existing", false);
        denied(() -> Z8Files.rename(project.source, relative, "../existing"), "rename traversal");
        Z8Files.create(project.source, "nested space", "second.txt", false);
        denied(() -> Z8Files.rename(project.source, relative, "second.txt"), "rename overwrite");
        denied(() -> Z8Files.delete(project.source, "nested space"), "no implicit recursive deletion");
        Files.write(new File(project.source, "binary").toPath(), new byte[] {0, 1, 2});
        denied(() -> Z8Files.read(project.source, "binary"), "binary read");
        Files.write(new File(project.source, "huge").toPath(), new byte[Z8Files.MAX_TEXT_BYTES + 1]);
        denied(() -> Z8Files.read(project.source, "huge"), "bounded file read");
        Z8Files.rename(project.source, relative, "renamed.txt");
        Z8Files.delete(project.source, "nested space/renamed.txt");
        check(!file.toFile().exists(), "rename and explicit file delete");
        Files.createSymbolicLink(new File(storage, "linked-source").toPath(), external.toPath());
        denied(() -> Z8Files.directory(new File(storage, "linked-source"), ""), "root symlink rejected");
        Z8Projects.Project disposable = projects.create("삭제 검증");
        Path env = storage.toPath().getParent().resolve("environments").resolve(disposable.id);
        Path home = storage.toPath().getParent().resolve("homes").resolve(disposable.id);
        Files.createDirectories(env.resolve("rootfs/etc"));
        Files.createDirectories(home.getParent());
        Path witness = external.toPath().resolve("retain.txt");
        Files.writeString(witness, "outside must survive");
        Files.writeString(env.resolve("rootfs/etc/test"), "owned environment");
        Files.writeString(disposable.source.toPath().resolve("code.txt"), "owned source");
        Files.createSymbolicLink(home, external.toPath());
        denied(() -> projects.delete(disposable.id), "top-level HOME link refuses whole delete");
        check(Files.exists(env.resolve("rootfs/etc/test")) && disposable.source.isDirectory(), "validate all roots before deletion");
        Files.delete(home); Files.createDirectory(home);
        Files.writeString(home.resolve("secret.txt"), "owned HOME");
        Files.createSymbolicLink(env.resolve("rootfs/external-link"), external.toPath());
        denied(() -> projects.delete("../" + disposable.id), "delete UUID traversal");
        check(disposable.source.setWritable(false, false), "prepare read-only source root");
        projects.delete(disposable.id);
        check(!Files.exists(env) && !Files.exists(home), "environment and HOME removed");
        check(!disposable.source.getParentFile().exists(), "source and metadata removed");
        check(Files.readString(witness).equals("outside must survive"), "nested links never followed during deletion");
        check(projects.list().size() == 1 && projects.open(project.id).name.equals("작업 공간"), "other projects retained");
        denied(() -> projects.delete(disposable.id), "already removed project cannot target another path");
        Z8Projects.Project interrupted = projects.create("삭제 재시도");
        Files.delete(interrupted.source.toPath());
        Files.delete(interrupted.source.getParentFile().toPath().resolve("project.properties"));
        Z8Projects.restoreDeleteRecord(interrupted);
        check(projects.open(interrupted.id).name.equals("삭제 재시도") && projects.list().size() == 2,
            "final-phase failure restores addressable project record without resurrecting data");
        projects.delete(interrupted.id);
        check(projects.list().size() == 1, "repaired record can be removed on explicit retry");
        if (assertions != 29) throw new AssertionError("scenario count " + assertions);
        System.out.println("PASS: 29 filesystem scenarios");
    }
}
'''


if __name__ == "__main__":
    unittest.main()
