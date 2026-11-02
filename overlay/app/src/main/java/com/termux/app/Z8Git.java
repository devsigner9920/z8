package com.termux.app;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Call every method off the UI thread. Network writes require explicit UI actions. */
public final class Z8Git {
    public static final int MAX_OUTPUT = 1024 * 1024;
    private static final int MAX_INDEX = 32 * 1024 * 1024;
    private static final int TIMEOUT_SECONDS = 30;

    public static final class Change {
        public final char index;
        public final char worktree;
        public final String path;
        public final String oldPath;
        Change(char index, char worktree, String path, String oldPath) {
            this.index = index; this.worktree = worktree; this.path = path; this.oldPath = oldPath;
        }
        public boolean untracked() { return index == '?' && worktree == '?'; }
        public boolean staged() { return !untracked() && index != ' ' && index != '!'; }
        public boolean unstaged() { return untracked() || (worktree != ' ' && worktree != '!'); }
        public boolean conflict() {
            return index == 'U' || worktree == 'U' || (index == 'A' && worktree == 'A')
                || (index == 'D' && worktree == 'D');
        }
        public String displayPath() { return oldPath == null ? path : oldPath + " → " + path; }
    }

    public static final class Status {
        public final List<Change> changes;
        public final String branch;
        public final String head;
        public final String indexToken;
        Status(List<Change> changes, String branch, String head, String token) {
            this.changes = Collections.unmodifiableList(changes);
            this.branch = branch; this.head = head; this.indexToken = token;
        }
        public int stagedCount() { int count = 0; for (Change change : changes) if (change.staged()) count++; return count; }
        public boolean conflicts() { for (Change change : changes) if (change.conflict()) return true; return false; }
    }

    public static final class Result {
        public final int code;
        public final byte[] stdout;
        public final byte[] stderr;
        Result(int code, byte[] out, byte[] err) { this.code = code; stdout = out; stderr = err; }
        public String output() { return new String(stdout, StandardCharsets.UTF_8); }
    }

    interface Runner {
        default boolean available() { return true; }
        Result run(List<String> argv, File cwd, Map<String, String> environment, byte[] input, int timeout, int limit) throws IOException;
    }

    private final File executable;
    private final File source;
    private final File home;
    private final File temp;
    private final Map<String, String> environment;
    private final Runner runner;
    private final boolean guestConfiguration;

    /** The Activity passes only TermuxConstants.TERMUX_PREFIX_DIR_PATH/bin/git. */
    Z8Git(File executable, File source, File home, File temp, Map<String, String> environment) {
        this(executable, source, home, temp, environment, new ProcessRunner());
    }

    /** Package-private dependency injection is for isolated host tests, not an app fallback. */
    Z8Git(File executable, File source, File home, File temp, Map<String, String> environment, Runner runner) {
        this(executable, source, home, temp, environment, runner, false);
    }

    private Z8Git(File executable, File source, File home, File temp, Map<String, String> environment,
            Runner runner, boolean guestConfiguration) {
        this.executable = executable; this.source = source; this.home = home;
        this.temp = temp; this.environment = new HashMap<>(environment); this.runner = runner;
        this.guestConfiguration = guestConfiguration;
    }

    static Z8Git guest(File executable, File source, File home, File temp,
            Map<String, String> environment, Runner runner) {
        return new Z8Git(executable, source, home, temp, environment, runner, true);
    }

    public boolean available() { return executable.isFile() && executable.canExecute() && runner.available(); }

    public boolean repositoryExists() throws IOException {
        Z8Files.directory(source, "");
        Path dotGit = new File(source, ".git").toPath();
        if (!Files.exists(dotGit, LinkOption.NOFOLLOW_LINKS)) return false;
        repository();
        return true;
    }

    private void repository() throws IOException {
        Z8Files.directory(source, ".git");
        // This increment handles a repository stored in the project itself.
        // Gitfiles/worktrees and linked metadata need an explicit future mapping.
        for (String item : Arrays.asList("HEAD", "index", "config", "objects", "refs", "logs", "packed-refs"))
            validatePath(source, ".git/" + item, true);
    }

    public void init() throws IOException {
        if (repositoryExists()) throw new IOException("이미 Git 저장소입니다.");
        require(run(null, "init", "--initial-branch=main", "--", source.getAbsolutePath()));
        repository();
    }

    public Status status() throws IOException {
        repository();
        String before = token();
        Result result = require(run(null, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=none"));
        List<Change> changes = parseStatus(result.stdout);
        Result branchResult = run(null, "symbolic-ref", "--quiet", "--short", "HEAD");
        String branch;
        if (branchResult.code == 0) branch = branchResult.output().trim();
        else if (branchResult.code == 1) branch = "detached HEAD";
        else { require(branchResult); branch = ""; }
        String head = head();
        String after = token();
        if (!before.equals(after)) throw new IOException("Git 상태를 읽는 동안 인덱스가 변경되었습니다. 새로고침해 주세요.");
        return new Status(changes, branch, head, after);
    }

    public String diff(Change change, boolean staged) throws IOException {
        repository();
        validateChange(change);
        List<String> args = new ArrayList<>(Arrays.asList("diff", "--no-ext-diff", "--no-textconv", "--no-color"));
        boolean newFile = change.untracked();
        if (newFile) args.add("--no-index");
        else if (staged) args.add("--cached");
        args.add("--");
        if (newFile) args.add("/dev/null");
        args.add(change.path);
        if (!newFile && change.oldPath != null) args.add(change.oldPath);
        Result result = run(null, args.toArray(new String[0]));
        if (result.code != 0 && !(newFile && result.code == 1)) require(result);
        return result.output();
    }

    public void stage(Change change) throws IOException {
        repository(); validateChange(change);
        List<String> args = new ArrayList<>(Arrays.asList("add", "--"));
        args.add(change.path);
        if (change.oldPath != null) args.add(change.oldPath);
        require(run(null, args.toArray(new String[0])));
    }

    public void unstage(Change change) throws IOException {
        repository(); validateChange(change);
        List<String> args;
        if (head().isEmpty()) args = new ArrayList<>(Arrays.asList("rm", "--cached", "--force", "--ignore-unmatch", "--"));
        else args = new ArrayList<>(Arrays.asList("reset", "--quiet", "HEAD", "--"));
        args.add(change.path);
        if (change.oldPath != null) args.add(change.oldPath);
        require(run(null, args.toArray(new String[0])));
    }

    public String commit(Status expected, String message, String authorName, String authorEmail) throws IOException {
        repository();
        if (expected == null || expected.stagedCount() == 0) throw new IOException("먼저 커밋할 변경사항을 스테이지에 올려주세요.");
        if (expected.conflicts()) throw new IOException("충돌을 해결하고 스테이지에 올린 뒤 커밋해 주세요.");
        if (message == null || message.trim().isEmpty() || message.getBytes(StandardCharsets.UTF_8).length > 16 * 1024
                || message.indexOf('\0') >= 0) throw new IOException("커밋 메시지는 1~16 KiB로 입력해 주세요.");
        authorName = identity(authorName, false); authorEmail = identity(authorEmail, true);
        if (!expected.indexToken.equals(token()) || !expected.head.equals(head()))
            throw new IOException("커밋을 준비하는 동안 스테이지 또는 HEAD가 변경되었습니다. 새로고침 후 다시 확인해 주세요.");
        Result committed = require(run(message.getBytes(StandardCharsets.UTF_8),
            "-c", "user.name=" + authorName, "-c", "user.email=" + authorEmail,
            "commit", "--file=-", "--cleanup=strip"));
        return committed.output();
    }

    public String[] author() throws IOException {
        repository();
        return new String[] { config("user.name"), config("user.email") };
    }

    public List<String> branches() throws IOException {
        repository();
        String result = require(run(null, "for-each-ref", "--format=%(refname:short)", "refs/heads/")).output();
        List<String> values = new ArrayList<>();
        for (String line : result.split("\n")) if (!line.isEmpty()) {
            if (values.size() == 500) throw new IOException("브랜치가 500개를 초과했습니다. 터미널에서 확인해 주세요.");
            values.add(line);
        }
        return values;
    }

    public void switchBranch(Status expected, String branch, boolean create) throws IOException {
        repository(); checkExpected(expected, true); branchName(branch);
        require(create ? run(null, "switch", "--no-guess", "-c", branch)
            : run(null, "switch", "--no-guess", "--", branch));
    }

    private void branchName(String name) throws IOException {
        if (name == null || name.isEmpty() || name.length() > 200 || name.startsWith("-") || name.contains("@{"))
            throw new IOException("브랜치 이름을 확인해 주세요.");
        require(run(null, "check-ref-format", "--branch", name));
    }

    public static final class Remote {
        public final String name;
        private final String fetchUrl;
        private final String pushUrl;
        Remote(String name, String fetch, String push) { this.name = name; fetchUrl = fetch; pushUrl = push; }
        public String destination(boolean push) {
            String value = push ? pushUrl : fetchUrl;
            // Display host/path only; remote config may embed credentials or a query.
            if (value.contains("://")) {
                try {
                    java.net.URI uri = new java.net.URI(value);
                    return uri.getHost() == null ? "설정된 저장소" : uri.getHost() + (uri.getPath() == null ? "" : uri.getPath());
                } catch (Exception ignored) { return "설정된 저장소"; }
            }
            if (value.matches("[^ /]+@[^ /]+:.*")) value = value.substring(value.indexOf('@') + 1);
            int query = value.indexOf('?'); if (query >= 0) value = value.substring(0, query);
            for (int i = 0; i < value.length(); i++) if (Character.isISOControl(value.charAt(i))) return "설정된 저장소";
            return value.length() > 300 ? value.substring(0, 300) + "…" : value;
        }
    }

    public List<Remote> remotes() throws IOException {
        repository(); List<Remote> values = new ArrayList<>();
        for (String name : require(run(null, "remote")).output().split("\n")) if (!name.isEmpty()) {
            if (values.size() == 50) throw new IOException("원격 저장소가 50개를 초과했습니다.");
            if (!name.matches("[A-Za-z0-9][A-Za-z0-9._/-]{0,199}")) continue;
            String fetch = require(run(null, "remote", "get-url", "--all", name)).output().trim();
            String push = require(run(null, "remote", "get-url", "--push", "--all", name)).output().trim();
            // Multiple destinations need a fuller confirmation UI. Never pick one silently.
            if (fetch.contains("\n") || push.contains("\n")) continue;
            values.add(new Remote(name, fetch, push));
        }
        return values;
    }

    public void network(Status expected, Remote remote, String action) throws IOException {
        repository();
        if (!Arrays.asList("fetch", "pull", "push").contains(action) || remote == null)
            throw new IOException("지원하지 않는 원격 작업입니다.");
        boolean found = false;
        for (Remote current : remotes()) if (current.name.equals(remote.name)
                && current.fetchUrl.equals(remote.fetchUrl) && current.pushUrl.equals(remote.pushUrl)) found = true;
        if (!found) throw new IOException("원격 저장소 설정이 변경되었습니다. 새로 확인해 주세요.");
        if (!"fetch".equals(action)) {
            checkExpected(expected, "pull".equals(action));
            if (expected.head.isEmpty() || expected.branch.equals("detached HEAD"))
                throw new IOException("커밋된 로컬 브랜치를 선택해 주세요.");
            branchName(expected.branch);
        }
        Result result;
        if ("fetch".equals(action)) result = run(null, "fetch", "--", remote.name);
        else if ("pull".equals(action)) result = run(null, "-c", "rebase.autoStash=false", "-c", "merge.autoStash=false",
            "pull", "--ff-only", "--no-rebase", "--", remote.name, "refs/heads/" + expected.branch);
        else result = run(null, "push", "--porcelain", "--", remote.name,
            "HEAD:refs/heads/" + expected.branch);
        if (result.code != 0) throw new IOException("원격 " + action + " 작업이 완료되지 않았습니다 (종료 코드 " + result.code
            + "). 인증·브랜치 상태를 터미널에서 확인한 뒤 새로고침해 주세요. 자동으로 재시도하지 않습니다.");
    }

    private void checkExpected(Status expected, boolean clean) throws IOException {
        if (expected == null) throw new IOException("Git 상태를 새로고침해 주세요.");
        Status current = status();
        if (!expected.branch.equals(current.branch) || !expected.head.equals(current.head)
                || !expected.indexToken.equals(current.indexToken))
            throw new IOException("브랜치 또는 스테이지가 변경되었습니다. 새로고침 후 다시 확인해 주세요.");
        if (clean && !current.changes.isEmpty()) throw new IOException("변경 파일을 먼저 커밋하거나 터미널에서 정리해 주세요.");
    }

    private String config(String key) throws IOException {
        Result result = run(null, "config", "--get", key);
        if (result.code == 1) return "";
        require(result); return result.output().trim();
    }

    static String identity(String input, boolean email) throws IOException {
        String value = input == null ? "" : input.trim();
        if (value.isEmpty() || value.length() > 200 || value.indexOf('<') >= 0 || value.indexOf('>') >= 0)
            throw new IOException("작성자 이름과 이메일을 확인해 주세요.");
        for (int index = 0; index < value.length(); index++)
            if (Character.isISOControl(value.charAt(index))) throw new IOException("작성자 정보에 제어 문자를 사용할 수 없습니다.");
        if (email && (value.indexOf('@') < 1 || value.indexOf(' ') >= 0)) throw new IOException("작성자 이메일을 확인해 주세요.");
        return value;
    }

    private String head() throws IOException {
        Result result = run(null, "rev-parse", "--verify", "--quiet", "HEAD");
        if (result.code == 1) return "";
        require(result); return result.output().trim();
    }

    private String token() throws IOException {
        Path index = new File(source, ".git/index").toPath();
        validatePath(source, ".git/index", true);
        if (!Files.exists(index, LinkOption.NOFOLLOW_LINKS)) return "unborn-index";
        if (!Files.isRegularFile(index, LinkOption.NOFOLLOW_LINKS) || Files.size(index) > MAX_INDEX)
            throw new IOException("이 인덱스는 네이티브 Git 화면의 크기 제한을 초과했습니다.");
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            long total = 0;
            try (InputStream input = Files.newInputStream(index, LinkOption.NOFOLLOW_LINKS)) {
                byte[] buffer = new byte[8192];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    total += count;
                    if (total > MAX_INDEX) throw new IOException("Git 인덱스가 크기 제한을 초과했습니다.");
                    digest.update(buffer, 0, count);
                }
            }
            StringBuilder result = new StringBuilder();
            for (byte value : digest.digest()) result.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
            return result.toString();
        } catch (NoSuchAlgorithmException impossible) { throw new AssertionError(impossible); }
    }

    private void validateChange(Change change) throws IOException {
        if (change == null) throw new IOException("변경 파일을 선택해 주세요.");
        validatePath(source, change.path, false);
        if (change.oldPath != null) validatePath(source, change.oldPath, false);
    }

    static void validatePath(File source, String relative, boolean metadata) throws IOException {
        Z8Files.directory(source, "");
        if (relative == null || relative.isEmpty() || relative.startsWith("/") || relative.indexOf('\\') >= 0)
            throw new IOException("잘못된 Git 파일 경로입니다.");
        Path root = source.toPath().toAbsolutePath().normalize();
        Path cursor = root;
        for (String component : relative.split("/", -1)) {
            Z8Files.name(component);
            if (!metadata && component.equalsIgnoreCase(".git")) throw new IOException("Git 내부 파일은 스테이지에 올릴 수 없습니다.");
            cursor = cursor.resolve(component);
            if (Files.isSymbolicLink(cursor)) throw new IOException("링크 경로의 Git 작업은 터미널에서 확인해 주세요.");
        }
        if (!cursor.toFile().getCanonicalFile().toPath().startsWith(root.toFile().getCanonicalFile().toPath()))
            throw new IOException("프로젝트 밖의 Git 파일 경로입니다.");
    }

    static List<Change> parseStatus(byte[] bytes) throws IOException {
        String raw;
        try {
            raw = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
        } catch (Exception invalid) { throw new IOException("Git 파일 이름을 UTF-8로 읽을 수 없습니다.", invalid); }
        List<Change> result = new ArrayList<>();
        int offset = 0;
        while (offset < raw.length()) {
            int end = raw.indexOf('\0', offset);
            if (end < offset + 4 || raw.charAt(offset + 2) != ' ') throw new IOException("Git 상태 응답 형식이 올바르지 않습니다.");
            char index = raw.charAt(offset), worktree = raw.charAt(offset + 1);
            if (" MADRCU?!T".indexOf(index) < 0 || " MADRCU?!T".indexOf(worktree) < 0)
                throw new IOException("지원하지 않는 Git 상태 코드입니다.");
            String path = raw.substring(offset + 3, end);
            offset = end + 1;
            String old = null;
            if (index == 'R' || index == 'C' || worktree == 'R' || worktree == 'C') {
                end = raw.indexOf('\0', offset);
                if (end <= offset) throw new IOException("Git 이름 변경 응답이 완전하지 않습니다.");
                old = raw.substring(offset, end); offset = end + 1;
            }
            if (result.size() >= 2000) throw new IOException("변경 파일이 2,000개를 초과했습니다. 터미널에서 확인해 주세요.");
            result.add(new Change(index, worktree, path, old));
        }
        return result;
    }

    private Result run(byte[] input, String... arguments) throws IOException {
        if (!available()) throw new IOException(guestConfiguration ? "프로젝트 Linux 환경의 Git 또는 PRoot가 준비되지 않았습니다." : "z8 전용 Android Git 실행 파일이 설치되지 않았습니다.");
        Z8Files.directory(source, "");
        checkPrivateDirectory(home);
        checkPrivateDirectory(temp);
        Map<String, String> env = new HashMap<>(environment);
        for (String key : new ArrayList<>(env.keySet())) if (key.startsWith("GIT_")) env.remove(key);
        env.remove("LD_PRELOAD"); env.remove("LD_LIBRARY_PATH");
        env.put("HOME", home.getAbsolutePath());
        env.put("TMPDIR", temp.getAbsolutePath());
        env.put("GIT_TERMINAL_PROMPT", "0");
        if (!guestConfiguration) {
            env.put("GIT_CONFIG_NOSYSTEM", "1");
            File globalConfig = new File(home, ".gitconfig");
            if (Files.isSymbolicLink(globalConfig.toPath())) throw new IOException("프로젝트 Git 설정 파일이 링크입니다.");
            env.put("GIT_CONFIG_GLOBAL", globalConfig.getAbsolutePath());
        }
        // Explicit roots override core.worktree and prevent parent discovery.
        env.put("GIT_DIR", new File(source, ".git").getAbsolutePath());
        env.put("GIT_WORK_TREE", source.getAbsolutePath());
        env.put("GIT_PAGER", "cat");
        env.put("GIT_OPTIONAL_LOCKS", "0");
        List<String> argv = new ArrayList<>(Arrays.asList(executable.getAbsolutePath(), "--literal-pathspecs", "--no-pager",
            "-c", "core.fsmonitor=false", "-c", "color.ui=false", "-C", source.getAbsolutePath()));
        argv.addAll(Arrays.asList(arguments));
        return runner.run(argv, source, env, input == null ? new byte[0] : input, TIMEOUT_SECONDS, MAX_OUTPUT);
    }

    private static void checkPrivateDirectory(File directory) throws IOException {
        Path path = directory.toPath().toAbsolutePath().normalize();
        Path cursor = path.getRoot();
        for (Path component : path) {
            cursor = cursor.resolve(component);
            if (Files.isSymbolicLink(cursor)) throw new IOException("Git 작업 디렉터리에 링크가 있습니다.");
        }
        Files.createDirectories(path);
    }

    private static Result require(Result result) throws IOException {
        if (result.code == 0) return result;
        String message = new String(result.stderr.length > 0 ? result.stderr : result.stdout, StandardCharsets.UTF_8).trim();
        if (message.length() > 4000) message = message.substring(0, 4000) + "…";
        throw new IOException("Git 종료 코드 " + result.code + (message.isEmpty() ? "" : "\n" + message));
    }

    static final class ProcessRunner implements Runner {
        @Override public Result run(List<String> argv, File cwd, Map<String, String> environment,
                byte[] input, int timeout, int limit) throws IOException {
            ProcessBuilder builder = new ProcessBuilder(argv).directory(cwd);
            builder.environment().clear(); builder.environment().putAll(environment);
            Process process;
            synchronized (Z8RuntimeLauncher.EXECUTION_LOCK) { process = builder.start(); }
            ByteArrayOutputStream stdout = new ByteArrayOutputStream();
            ByteArrayOutputStream stderr = new ByteArrayOutputStream();
            AtomicReference<IOException> readFailure = new AtomicReference<>();
            AtomicReference<IOException> inputFailure = new AtomicReference<>();
            Thread out = drain(process.getInputStream(), stdout, limit, readFailure, process);
            Thread err = drain(process.getErrorStream(), stderr, limit, readFailure, process);
            Thread writer = new Thread(() -> {
                try {
                    process.getOutputStream().write(input);
                    process.getOutputStream().close();
                } catch (IOException exception) { inputFailure.set(exception); }
            }, "z8-git-input");
            writer.setDaemon(true); writer.start();
            try {
                if (!process.waitFor(timeout, TimeUnit.SECONDS)) {
                    process.destroy();
                    if (!process.waitFor(500, TimeUnit.MILLISECONDS)) process.destroyForcibly();
                    throw new IOException("Git 작업의 30초 제한을 초과했습니다. 상태를 새로고침하고 터미널에서 확인해 주세요.");
                }
                out.join(1000); err.join(1000); writer.join(1000);
                if (out.isAlive() || err.isAlive() || writer.isAlive()) throw new IOException("Git 하위 작업의 출력이 끝나지 않았습니다. 상태를 확인해 주세요.");
                if (readFailure.get() != null) throw readFailure.get();
                if (process.exitValue() == 0 && input.length > 0 && inputFailure.get() != null) throw inputFailure.get();
                return new Result(process.exitValue(), stdout.toByteArray(), stderr.toByteArray());
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt(); throw new IOException("Git 작업이 중단되었습니다.", interrupted);
            } finally {
                if (process.isAlive()) process.destroyForcibly();
                try { process.getInputStream().close(); } catch (IOException ignored) {}
                try { process.getErrorStream().close(); } catch (IOException ignored) {}
                try { process.getOutputStream().close(); } catch (IOException ignored) {}
            }
        }

        private static Thread drain(InputStream input, ByteArrayOutputStream output, int limit,
                AtomicReference<IOException> failure, Process process) {
            Thread thread = new Thread(() -> {
                try {
                    byte[] buffer = new byte[8192]; int count;
                    while ((count = input.read(buffer)) != -1) {
                        if (output.size() + count > limit) throw new IOException("Git 출력이 1 MiB 제한을 초과했습니다. 파일별로 확인하거나 터미널을 사용해 주세요.");
                        output.write(buffer, 0, count);
                    }
                } catch (IOException exception) {
                    failure.compareAndSet(null, exception); process.destroyForcibly();
                }
            }, "z8-git-output");
            thread.setDaemon(true); thread.start(); return thread;
        }
    }
}
