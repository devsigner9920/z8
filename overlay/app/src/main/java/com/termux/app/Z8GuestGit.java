package com.termux.app;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** Maps the existing bounded Git runner into the project's exact PRoot guest. */
final class Z8GuestGit implements Z8Git.Runner {
    private final File proot;
    private final File source;
    private final String hostGit;
    private final List<String> prefix;
    private final Z8Git.Runner process;
    private final String unavailableReason;

    Z8GuestGit(File proot, File source, File hostGit, List<String> launchArguments,
            int commandOffset, Z8Git.Runner process) throws IOException {
        if (commandOffset < 1 || commandOffset != launchArguments.size() - 1
                || !"/usr/bin/git".equals(launchArguments.get(commandOffset)))
            throw new IOException(Z8Text.text("Could not verify the project's Git command path.", "프로젝트 Git 실행 경로를 확인할 수 없습니다."));
        List<String> beforeCommand = launchArguments.subList(0, commandOffset);
        if (!beforeCommand.contains("/usr/bin/env") || !beforeCommand.contains("HOME=/z8/home")
                || !beforeCommand.contains("-r") || !beforeCommand.contains("--kill-on-exit"))
            throw new IOException(Z8Text.text("Could not verify the project's Linux launch settings.", "프로젝트 Linux 실행 설정을 확인할 수 없습니다."));
        this.proot = proot;
        this.source = source;
        this.hostGit = hostGit.getAbsolutePath();
        this.prefix = new ArrayList<>(beforeCommand);
        this.process = process;
        this.unavailableReason = null;
    }

    private Z8GuestGit(String unavailableReason) {
        proot = null; source = null; hostGit = null; prefix = null; process = null;
        this.unavailableReason = unavailableReason;
    }

    static Z8GuestGit unavailable(String reason) { return new Z8GuestGit(reason); }

    @Override public boolean available() {
        return unavailableReason == null && proot.isFile() && proot.canExecute();
    }

    @Override public Z8Git.Result run(List<String> argv, File cwd, Map<String, String> environment,
            byte[] input, int timeout, int limit) throws IOException {
        if (!available()) throw new IOException(unavailableReason == null ? Z8Text.text("The z8 PRoot executable is missing.", "z8 전용 PRoot 실행 파일이 없습니다.") : unavailableReason);
        if (!cwd.getCanonicalFile().equals(source.getCanonicalFile()))
            throw new IOException(Z8Text.text("The Git working directory does not match the selected project.", "Git 작업 디렉터리가 선택한 프로젝트와 다릅니다."));
        List<String> gitCommand = mapCommand(argv, hostGit, source.getAbsolutePath());
        List<String> wrapped = new ArrayList<>();
        wrapped.add(proot.getAbsolutePath());
        wrapped.addAll(prefix);
        // These are fixed paths, not credentials. They follow env's -u cleanup
        // and override repo discovery/core.worktree without replacing config.
        wrapped.add("GIT_DIR=/workspace/.git");
        wrapped.add("GIT_WORK_TREE=/workspace");
        wrapped.addAll(gitCommand);
        Map<String, String> env = new HashMap<>(environment);
        env.remove("LD_PRELOAD"); env.remove("LD_LIBRARY_PATH");
        env.remove("PREFIX"); env.remove("ENV"); env.remove("BASH_ENV");
        env.remove("XDG_CONFIG_HOME"); // Use this guest HOME's normal .config/git.
        env.remove("GIT_CONFIG_NOSYSTEM"); env.remove("GIT_CONFIG_GLOBAL");
        env.remove("GIT_CONFIG_SYSTEM");
        env.put("HOME", "/z8/home");
        env.put("TMPDIR", "/tmp");
        env.put("GIT_DIR", "/workspace/.git");
        env.put("GIT_WORK_TREE", "/workspace");
        env.put("PATH", "/z8/home/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin");
        // Any launch nonce already in the environment stays there. It is never
        // copied into wrapped argv, a file, or an error string.
        return process.run(wrapped, source, env, input, timeout, limit);
    }

    static List<String> mapCommand(List<String> argv, String hostGit, String source) throws IOException {
        List<String> expected = Arrays.asList(hostGit, "--literal-pathspecs", "--no-pager", "-c", "core.fsmonitor=false",
            "-c", "color.ui=false", "-C", source);
        if (argv.size() <= expected.size() || !argv.subList(0, expected.size()).equals(expected))
            throw new IOException(Z8Text.text("Unsupported Git command arguments.", "지원하지 않는 Git 실행 인수입니다."));
        List<String> result = new ArrayList<>(argv);
        result.set(0, "/usr/bin/git");
        result.set(8, "/workspace");
        if ("init".equals(result.get(9))) {
            if (result.size() != 13 || !"--initial-branch=main".equals(result.get(10))
                    || !"--".equals(result.get(11)) || !source.equals(result.get(12)))
                throw new IOException(Z8Text.text("Could not verify the path for the new Git repository.", "Git 저장소 생성 경로를 확인할 수 없습니다."));
            result.set(12, "/workspace");
        }
        // All remaining user paths and per-commit identity values stay literal.
        return result;
    }
}
