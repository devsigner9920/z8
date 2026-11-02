"""Real isolated Git plus parser/runner safety tests; never use an application fallback."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NativeGitTests(unittest.TestCase):
    def test_real_git_and_bounded_runner(self):
        jdk = ROOT / ".local/jdk/Contents/Home/bin"
        javac = str(jdk / "javac") if (jdk / "javac").is_file() else shutil.which("javac")
        java = str(jdk / "java") if (jdk / "java").is_file() else shutil.which("java")
        git = os.environ.get("Z8_GIT")
        if not git:
            bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/git"
            git = str(bundled) if bundled.is_file() else shutil.which("git")
        if not javac or not java or not git:
            self.skipTest("Host tests require a JDK and a test-only Git executable")
        with tempfile.TemporaryDirectory(prefix="z8-git-tests-") as temporary:
            directory = Path(temporary).resolve()
            probe = directory / "GitProbe.java"
            probe.write_text(JAVA_PROBE)
            source = ROOT / "overlay/app/src/main/java/com/termux/app"
            compiled = subprocess.run([javac, "-encoding", "UTF-8", "-d", str(directory),
                str(source / "Z8Files.java"), str(source / "Z8Git.java"), str(source / "Z8GuestGit.java"), str(probe)],
                capture_output=True, text=True, timeout=45)
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            tested = subprocess.run([java, "-cp", str(directory), "com.termux.app.GitProbe",
                git, str(directory / "source"), java, str(directory)],
                capture_output=True, text=True, timeout=40)
            self.assertEqual(0, tested.returncode, tested.stdout + tested.stderr)
            self.assertIn("PASS: Git workflow and runner", tested.stdout)


JAVA_PROBE = r'''
package com.termux.app;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class GitProbe {
    interface Action { void run() throws Exception; }
    static int count;
    static void check(boolean value, String label) { if (!value) throw new AssertionError(label); count++; }
    static void denied(Action action, String label) throws Exception {
        try { action.run(); } catch (IOException expected) { count++; return; }
        throw new AssertionError(label);
    }
    static byte[] bytes(String value) { return value.getBytes(StandardCharsets.UTF_8); }
    static Z8Git.Change change(Z8Git.Status status, String path) {
        for (Z8Git.Change item : status.changes) if (item.path.equals(path)) return item;
        throw new AssertionError("missing path: " + path);
    }
    public static void main(String[] args) throws Exception {
        if (args.length == 1) {
            if (args[0].equals("sleep")) { Thread.sleep(10000); return; }
            if (args[0].equals("spam")) { for (int i = 0; i < 100000; i++) System.out.print('a'); return; }
        }
        File source = new File(args[1]); source.mkdir();
        Map<String, String> env = new HashMap<>(System.getenv());
        env.put("GIT_DIR", "/should/not/be/used");
        Z8Git git = new Z8Git(new File(args[0]), source,
            new File(source.getParentFile(), "git-home"), new File(source.getParentFile(), "git-tmp"), env);
        check(!git.repositoryExists(), "new project not initialized");
        git.init(); check(git.repositoryExists(), "explicit init");
        check(git.status().branch.equals("main") && git.status().head.isEmpty(), "unborn branch");
        Files.write(new File(source, "space file.txt").toPath(), bytes("first\n"));
        Files.write(new File(source, "-leading.txt").toPath(), bytes("second\n"));
        Files.write(new File(source, ":(glob)*").toPath(), bytes("literal\n"));
        check(git.status().changes.size() == 3, "real status with tricky names");
        check(git.diff(change(git.status(), "space file.txt"), false).contains("+first"), "untracked diff");
        git.stage(change(git.status(), ":(glob)*"));
        check(git.status().stagedCount() == 1, "literal pathspec only stages one file");
        git.unstage(change(git.status(), ":(glob)*"));
        check(git.status().stagedCount() == 0 && new File(source, ":(glob)*").isFile(), "unborn unstage preserves worktree");
        for (Z8Git.Change item : git.status().changes) git.stage(item);
        Z8Git.Status staged = git.status();
        check(git.diff(change(staged, "-leading.txt"), true).contains("+second"), "leading dash staged diff");
        git.commit(staged, "First commit\n\nQuoted `text` and $(value) remain text", "Z8 Test", "z8@example.test");
        check(git.status().changes.isEmpty() && !git.status().head.isEmpty(), "real commit");
        check(git.author()[0].isEmpty(), "identity override did not persist globally or locally");
        git.switchBranch(git.status(), "feature/z8", true);
        check(git.status().branch.equals("feature/z8") && git.branches().contains("main"), "create and select branch");
        git.switchBranch(git.status(), "main", false);
        check(git.status().branch.equals("main"), "explicit branch switch");
        denied(() -> git.switchBranch(git.status(), "--detach", true), "branch option rejected");
        denied(() -> git.switchBranch(git.status(), "@{-1}", false), "branch shorthand not accepted as literal branch");
        File bare = new File(source.getParentFile(), "remote.git");
        Z8Git.ProcessRunner admin = new Z8Git.ProcessRunner();
        Map<String, String> adminEnv = new HashMap<>(System.getenv());
        for (String key : new ArrayList<>(adminEnv.keySet())) if (key.startsWith("GIT_")) adminEnv.remove(key);
        adminEnv.put("GIT_CONFIG_NOSYSTEM", "1"); adminEnv.put("GIT_CONFIG_GLOBAL", "/dev/null");
        check(admin.run(Arrays.asList(args[0], "init", "--bare", bare.getAbsolutePath()), source, adminEnv, new byte[0], 10, 65536).code == 0, "isolated bare remote fixture");
        check(admin.run(Arrays.asList(args[0], "-C", source.getAbsolutePath(), "remote", "add", "origin", bare.getAbsolutePath()), source, adminEnv, new byte[0], 10, 65536).code == 0, "remote fixture registration");
        Z8Git.Remote origin = git.remotes().get(0);
        git.network(git.status(), origin, "push");
        git.network(git.status(), origin, "fetch");
        git.network(git.status(), origin, "pull");
        check(!git.status().head.isEmpty(), "real local remote push/fetch/ff-only pull");
        File peer = new File(source.getParentFile(), "peer");
        check(admin.run(Arrays.asList(args[0], "clone", "--branch", "main", bare.getAbsolutePath(), peer.getAbsolutePath()), source, adminEnv, new byte[0], 10, 65536).code == 0, "peer clone fixture");
        Z8Git peerGit = new Z8Git(new File(args[0]), peer, new File(source.getParentFile(), "peer-home"), new File(source.getParentFile(), "peer-tmp"), adminEnv);
        Files.write(new File(peer, "upstream.txt").toPath(), bytes("remote update\n"));
        peerGit.stage(change(peerGit.status(), "upstream.txt"));
        peerGit.commit(peerGit.status(), "Remote update", "Z8 Test", "z8@example.test");
        peerGit.network(peerGit.status(), peerGit.remotes().get(0), "push");
        git.network(git.status(), origin, "pull");
        check(new File(source, "upstream.txt").isFile() && git.status().head.equals(peerGit.status().head), "fast-forward updates real files");
        Z8Git.Remote credential = new Z8Git.Remote("origin", "https://user:secret@example.test/repo?q=token", "git@example.test:repo");
        check(credential.destination(false).equals("example.test/repo") && credential.destination(true).equals("example.test:repo"), "confirmation never shows URL credentials or query");
        Z8Git.Remote changed = new Z8Git.Remote("origin", "/other/path", "/other/path");
        denied(() -> git.network(git.status(), changed, "push"), "changed remote rejected before push");
        denied(() -> git.network(git.status(), origin, "push --force"), "unregistered network action rejected");
        Files.write(new File(source, "space file.txt").toPath(), bytes("updated\n"));
        denied(() -> git.switchBranch(git.status(), "feature/z8", false), "dirty branch switch does not discard files");
        denied(() -> git.network(git.status(), origin, "pull"), "dirty pull does not auto-stash");
        git.stage(change(git.status(), "space file.txt"));
        Z8Git.Status oldIndex = git.status();
        Files.write(new File(source, "-leading.txt").toPath(), bytes("changed\n"));
        git.stage(change(git.status(), "-leading.txt"));
        denied(() -> git.commit(oldIndex, "Stale", "Z8 Test", "z8@example.test"), "reject changed index before commit");
        git.unstage(change(git.status(), "space file.txt"));
        check(new String(Files.readAllBytes(new File(source, "space file.txt").toPath()), StandardCharsets.UTF_8).equals("updated\n"), "HEAD unstage preserves worktree");
        List<Z8Git.Change> parsed = Z8Git.parseStatus(bytes("R  new name\0old name\0UU conflict\0?? line\nname\0"));
        check(parsed.size() == 3 && parsed.get(0).path.equals("new name") && parsed.get(0).oldPath.equals("old name"), "rename NUL destination/source order");
        check(parsed.get(1).conflict() && parsed.get(2).path.equals("line\nname"), "conflict and raw newline parse");
        denied(() -> Z8Git.parseStatus(bytes("R  missing-source\0")), "truncated rename parse");
        denied(() -> Z8Git.parseStatus(new byte[] {'?', '?', ' ', (byte) 0xff, 0}), "invalid UTF8 parse");
        denied(() -> Z8Git.validatePath(source, "../escape", false), "path traversal");
        denied(() -> Z8Git.validatePath(source, ".git/config", false), "metadata staging");
        File outside = new File(source.getParentFile(), "outside"); outside.mkdir();
        Files.createSymbolicLink(new File(source, "link").toPath(), outside.toPath());
        denied(() -> Z8Git.validatePath(source, "link/file", false), "symlink containment");
        denied(() -> Z8Git.identity("x\nuser.email=y", false), "identity control bytes");
        final List<String> captured = new ArrayList<>();
        Z8Git.Runner recorder = (argv, cwd, environment, input, timeout, limit) -> {
            captured.addAll(argv);
            check(environment.get("GIT_DIR").equals(new File(source, ".git").getAbsolutePath()), "known Git root wins inherited redirect");
            return new Z8Git.Result(0, new byte[0], new byte[0]);
        };
        Z8Git capture = new Z8Git(new File(args[0]), source, new File(source.getParentFile(), "git-home"),
            new File(source.getParentFile(), "git-tmp"), env, recorder);
        capture.stage(new Z8Git.Change('?', '?', "$(touch owned); quote'", null));
        check(captured.get(0).equals(new File(args[0]).getAbsolutePath()) && captured.contains("--literal-pathspecs")
            && captured.get(captured.size() - 2).equals("--") && captured.get(captured.size() - 1).equals("$(touch owned); quote'"), "argv passes shell syntax literally");
        List<String> guestTemplate = new ArrayList<>(Arrays.asList("/private/usr/bin/proot", "--kill-on-exit", "-r", "/private/guest-rootfs",
            "-b", source.getAbsolutePath() + ":/workspace", "-w", "/workspace", "/usr/bin/env", "-u", "GIT_DIR",
            "-u", "GIT_WORK_TREE", "HOME=/z8/home", "TMPDIR=/tmp", "/usr/bin/git"));
        int commandOffset = guestTemplate.size() - 1;
        List<String> guestCaptured = new ArrayList<>();
        Map<String, String> guestEnvironment = new HashMap<>(env);
        guestEnvironment.put("Z8_EVENT_TOKEN", "protected-test-nonce");
        guestEnvironment.put("GIT_CONFIG_NOSYSTEM", "1");
        guestEnvironment.put("GIT_CONFIG_GLOBAL", "/unrelated-host-config");
        guestEnvironment.put("XDG_CONFIG_HOME", "/unrelated-host-home");
        guestEnvironment.put("PROOT_TMP_DIR", new File(source.getParentFile(), "guest-tmp").getAbsolutePath());
        Z8Git.Runner guestRecorder = (argv, cwd, environment, input, timeout, limit) -> {
            guestCaptured.clear(); guestCaptured.addAll(argv);
            check(environment.get("HOME").equals("/z8/home") && environment.get("TMPDIR").equals("/tmp"), "guest HOME/tmp match terminal");
            check(environment.get("PATH").equals("/z8/home/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"), "guest hooks can resolve per-user CLIs and system tools");
            check(environment.get("GIT_DIR").equals("/workspace/.git") && environment.get("GIT_WORK_TREE").equals("/workspace"), "guest fixed repo mapping");
            check(!environment.containsKey("GIT_CONFIG_NOSYSTEM") && !environment.containsKey("GIT_CONFIG_GLOBAL")
                && !environment.containsKey("GIT_CONFIG_SYSTEM") && !environment.containsKey("XDG_CONFIG_HOME"), "guest system/user config not replaced by Android isolation");
            check(environment.get("Z8_EVENT_TOKEN").equals("protected-test-nonce") && !String.join(" ", argv).contains("protected-test-nonce"), "hook nonce stays in environment");
            check(!argv.contains("core.hooksPath=/dev/null") && !argv.contains("commit.gpgsign=false"), "guest hooks and signing preserved");
            check(timeout == 30 && limit == Z8Git.MAX_OUTPUT && input.length == 0, "guest runner preserves limits and input");
            return new Z8Git.Result(0, new byte[0], new byte[0]);
        };
        Z8GuestGit guestRunner = new Z8GuestGit(new File(args[0]), source, new File(args[0]), guestTemplate, commandOffset, guestRecorder);
        Z8Git guestGit = Z8Git.guest(new File(args[0]), source, new File(source.getParentFile(), "guest-home"),
            new File(source.getParentFile(), "guest-tmp"), guestEnvironment, guestRunner);
        guestGit.stage(new Z8Git.Change('?', '?', "$(touch owned); quote'", null));
        check(guestCaptured.get(0).equals(args[0]) && guestCaptured.contains("/usr/bin/git"), "guest runner uses supplied proot entry and Linux git");
        check(guestCaptured.get(1).equals("/private/usr/bin/proot"), "target36 linker prefix survives Git command insertion");
        int actualGit = guestCaptured.indexOf("/usr/bin/git");
        check(guestCaptured.get(actualGit - 2).equals("GIT_DIR=/workspace/.git")
            && guestCaptured.get(actualGit - 1).equals("GIT_WORK_TREE=/workspace"), "fixed mapping follows env cleanup");
        check(guestCaptured.get(actualGit + 8).equals("/workspace")
            && guestCaptured.get(guestCaptured.size()-1).equals("$(touch owned); quote'"), "only fixed -C changes; user paths literal");
        List<String> initArgs = Arrays.asList(args[0], "--literal-pathspecs", "--no-pager", "-c", "core.fsmonitor=false",
            "-c", "color.ui=false", "-C", source.getAbsolutePath(), "init", "--initial-branch=main", "--", source.getAbsolutePath());
        List<String> mappedInit = Z8GuestGit.mapCommand(initArgs, args[0], source.getAbsolutePath());
        check(mappedInit.get(8).equals("/workspace") && mappedInit.get(12).equals("/workspace"), "init target maps into guest");
        List<String> invalidInit = new ArrayList<>(initArgs); invalidInit.set(12, "/other-project");
        denied(() -> Z8GuestGit.mapCommand(invalidInit, args[0], source.getAbsolutePath()), "wrong init root cannot reach guest");
        denied(() -> new Z8GuestGit(new File(args[0]), source, new File(args[0]), guestTemplate, commandOffset - 1, guestRecorder), "changed launch boundary fails closed");
        check(!Z8GuestGit.unavailable("missing guest").available(), "missing guest cannot become native fallback");
        Z8Git.ProcessRunner runner = new Z8Git.ProcessRunner();
        List<String> slow = Arrays.asList(args[2], "-cp", args[3], "com.termux.app.GitProbe", "sleep");
        long start = System.nanoTime();
        denied(() -> runner.run(slow, source, System.getenv(), new byte[65536], 1, 4096), "bounded wait and blocked stdin writer");
        check((System.nanoTime() - start) < 4_000_000_000L, "timeout returns promptly");
        List<String> spam = Arrays.asList(args[2], "-cp", args[3], "com.termux.app.GitProbe", "spam");
        denied(() -> runner.run(spam, source, System.getenv(), new byte[0], 3, 4096), "output limit");
        check(!new File(source, "owned").exists(), "no shell command evaluation");
        System.out.println("PASS: Git workflow and runner (" + count + " checks)");
    }
}

class Z8RuntimeLauncher { static final Object EXECUTION_LOCK = new Object(); }
'''


if __name__ == "__main__":
    unittest.main()
