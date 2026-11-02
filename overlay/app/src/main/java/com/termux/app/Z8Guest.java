package com.termux.app;

import android.content.Context;
import android.net.ConnectivityManager;
import android.os.SystemClock;
import android.net.LinkProperties;
import android.net.Network;

import com.termux.shared.termux.TermuxConstants;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Per-project guest storage and launch. Expensive work belongs to the static worker. */
public final class Z8Guest {
    public static final String EXTRA_GUEST_SESSION = "dev.devsigner.z8.GUEST_SESSION";
    public static final String EXTRA_SETUP_TOOLS = "dev.devsigner.z8.GUEST_SETUP_TOOLS";
    public static final String EXTRA_TOOL_ACTION = "dev.devsigner.z8.GUEST_TOOL_ACTION";
    private static final String ROOTFS_ASSET = "z8/guest/rootfs.zip";
    private static final String MANIFEST_ASSET = "z8/guest/manifest.json";
    // This is a fixed application entrypoint, never interpolated with project paths or user text.
    static final String PREPARE_SHELL =
        "trap 'printf \"\\nZ8 · Preparation interrupted. Open a new session to retry.\\n\"; exit 75' INT TERM; "
        + "printf '\\nZ8 · Preparing this project once: Python, Node, git and gh.\\n'; "
        + "if /bin/bash /usr/local/lib/z8/setup-tools.sh; then "
        + "unset Z8_SHOW_WELCOME; exec /bin/bash --login; "
        + "else z8_status=$?; printf '\\nZ8 · Preparation stopped. Open a new session to retry. For manual repair: Linux environment > Recovery shell.\\n'; "
        + "[ \"$z8_status\" -ne 130 ] || z8_status=75; exit \"$z8_status\"; fi";
    private static final String DNS_HEADER = "# Managed by z8 from Android network DNS\n";
    private static final ExecutorService WORKER = Executors.newSingleThreadExecutor();
    private static final Map<String, State> STATES = new ConcurrentHashMap<>();
    private static final Map<String, Long> LAST_CHECKED = new ConcurrentHashMap<>();
    private static final Map<String, Integer> READINESS_REVISION = new ConcurrentHashMap<>();
    private static final Object LOCK = new Object();

    public enum Phase { CHECKING, UNAVAILABLE, AVAILABLE, INSTALLING, DELETING, READY, ERROR }

    public static final class State {
        public final Phase phase;
        public final int progress;
        public final String message;
        public final boolean hasRootfs;
        public final boolean prootAvailable;
        public final boolean toolsChecked;
        public final boolean toolsReady;
        public final boolean toolsCheckIncomplete;
        public final Map<String, String> versions;
        public boolean ready(String tool) { return versions.containsKey(tool); }
        State(Phase phase, int progress, String message, boolean hasRootfs, boolean prootAvailable) {
            this(phase, progress, message, hasRootfs, prootAvailable, false, Collections.emptyMap());
        }
        State(Phase phase, int progress, String message, boolean hasRootfs, boolean prootAvailable,
                boolean toolsChecked, Map<String, String> versions) {
            this(phase, progress, message, hasRootfs, prootAvailable, toolsChecked, versions, false);
        }
        State(Phase phase, int progress, String message, boolean hasRootfs, boolean prootAvailable,
                boolean toolsChecked, Map<String, String> versions, boolean toolsCheckIncomplete) {
            this.toolsCheckIncomplete = toolsCheckIncomplete;
            this.toolsChecked = toolsChecked;
            this.versions = Collections.unmodifiableMap(new LinkedHashMap<>(versions));
            this.toolsReady = toolsChecked && versions.keySet().containsAll(Arrays.asList(
                "python", "pip", "venv", "node", "npm", "git", "gh", "make", "cc", "tmux"));
            this.phase = phase; this.progress = progress; this.message = message;
            this.hasRootfs = hasRootfs; this.prootAvailable = prootAvailable;
        }
    }

    public static final class Launch {
        public final String executable;
        public final String[] arguments;
        public final String workingDirectory;
        public final int commandOffset;
        public final boolean preparesShell;
        Launch(String executable, List<String> arguments, String workingDirectory, int commandOffset) {
            this(executable, arguments, workingDirectory, commandOffset, false);
        }
        Launch(String executable, List<String> arguments, String workingDirectory, int commandOffset, boolean preparesShell) {
            this.preparesShell = preparesShell;
            this.executable = executable; this.arguments = arguments.toArray(new String[0]);
            this.workingDirectory = workingDirectory;
            this.commandOffset = commandOffset;
        }
    }

    private static final class Asset {
        final Z8GuestArchive.Manifest archive;
        final String distribution;
        final String release;
        final String sourceSha256;
        Asset(Z8GuestArchive.Manifest archive, String distribution, String release, String sourceSha256) {
            this.archive = archive; this.distribution = distribution;
            this.release = release; this.sourceSha256 = sourceSha256;
        }
    }

    private Z8Guest() {}

    /** Lightweight cached state, with filesystem existence checks after process restart. */
    public static State state(Context context, String projectId) {
        State value = STATES.get(projectId == null ? "" : projectId);
        if (value != null) return value;
        if (!validId(projectId)) return new State(Phase.ERROR, 0, "프로젝트 ID를 확인해 주세요.", false, false);
        File rootfs = new File(context.getFilesDir(), "z8/environments/" + projectId + "/rootfs");
        boolean ready = rootfs.isDirectory() && new File(rootfs, Z8GuestArchive.MARKER).isFile();
        boolean proot = proot().canExecute();
        if (ready) return new State(proot ? Phase.READY : Phase.UNAVAILABLE, 100,
            proot ? "프로젝트 Linux 환경이 설치되어 있습니다." : "Linux 환경은 있지만 z8 전용 PRoot가 설치되지 않았습니다.", true, proot);
        return new State(Phase.CHECKING, 0, "Linux 환경을 확인하고 있습니다.", false, proot);
    }

    /** Caller also refuses live/pending sessions. Run off the UI thread. */
    public static void deleteProject(Context context, String projectId) throws IOException {
        synchronized (LOCK) {
            if (!validId(projectId)) throw new IOException("프로젝트 ID를 확인해 주세요.");
            State current = STATES.get(projectId);
            if (current != null && (current.phase == Phase.INSTALLING || current.phase == Phase.CHECKING
                    || current.phase == Phase.DELETING))
                throw new IOException("환경 작업이 진행 중입니다. 완료 후 프로젝트를 삭제해 주세요.");
            State previous = current == null ? state(context, projectId) : current;
            STATES.put(projectId, new State(Phase.DELETING, 0, "프로젝트를 삭제하고 있습니다.",
                previous.hasRootfs, previous.prootAvailable));
        }
        try {
            // Recursive filesystem work and preference commits must never hold LOCK:
            // unrelated main-thread refresh/completion callbacks also use that lock.
            new Z8DraftStore(context.getFilesDir()).clear(projectId);
            if (!context.getSharedPreferences("z8-git-draft-" + projectId, Context.MODE_PRIVATE).edit().clear().commit()
                    || !context.getSharedPreferences("z8-github-drafts-" + projectId, Context.MODE_PRIVATE).edit().clear().commit())
                throw new IOException("프로젝트의 임시 작업 데이터를 지우지 못했습니다. 다시 시도해 주세요.");
            new Z8Projects(context).delete(projectId);
            synchronized (LOCK) {
                STATES.remove(projectId); LAST_CHECKED.remove(projectId); READINESS_REVISION.remove(projectId);
            }
        } catch (Exception failure) {
            boolean hasRootfs = false;
            File rootfs = new File(context.getFilesDir(), "z8/environments/" + projectId + "/rootfs");
            try { marker(rootfs, projectId); hasRootfs = true; }
            catch (IOException ignored) { /* A partial deletion is never reported as an intact rootfs. */ }
            String detail = failure.getMessage() == null ? "파일 삭제를 완료하지 못했습니다." : failure.getMessage();
            synchronized (LOCK) {
                LAST_CHECKED.remove(projectId);
                STATES.put(projectId, new State(Phase.ERROR, 0, "프로젝트 삭제를 완료하지 못했습니다. 다시 시도해 주세요. " + detail,
                    hasRootfs, proot().canExecute()));
            }
            if (failure instanceof IOException) throw (IOException) failure;
            throw new IOException(detail, failure);
        }
    }

    public static void invalidateReadiness(String projectId) {
        if (projectId == null) return;
        synchronized (LOCK) {
            LAST_CHECKED.remove(projectId);
            READINESS_REVISION.put(projectId, READINESS_REVISION.getOrDefault(projectId, 0) + 1);
        }
    }

    public static boolean needsReadinessRefresh(String projectId) {
        return projectId != null && !LAST_CHECKED.containsKey(projectId);
    }
    public static void refresh(Context context, String projectId) { refresh(context, projectId, false); }
    public static void refresh(Context context, String projectId, boolean force) {
        Context app = context.getApplicationContext();
        final int revision;
        synchronized (LOCK) {
            State current = STATES.get(projectId == null ? "" : projectId);
            if (current != null && (current.phase == Phase.INSTALLING || current.phase == Phase.CHECKING || current.phase == Phase.DELETING)) return;
            if (!validId(projectId)) return;
            Long checkedAt = LAST_CHECKED.get(projectId);
            if (!force && current != null && current.phase == Phase.READY && checkedAt != null
                    && SystemClock.elapsedRealtime() - checkedAt < 60000) return;
            State previous = state(app, projectId);
            revision = READINESS_REVISION.getOrDefault(projectId, 0);
            STATES.put(projectId, new State(Phase.CHECKING, 0, "Linux 도구를 확인하고 있습니다. 이전 확인 결과는 아래에 유지됩니다.",
                previous.hasRootfs, proot().canExecute(), previous.toolsChecked, previous.versions, previous.toolsCheckIncomplete));
        }
        WORKER.execute(() -> {
            try { inspect(app, projectId); }
            catch (Exception error) { failed(projectId, error); }
            finally {
                synchronized (LOCK) {
                    // A setup that finished during inspection invalidates this snapshot.
                    if (revision != READINESS_REVISION.getOrDefault(projectId, 0)) LAST_CHECKED.remove(projectId);
                }
            }
        });
    }

    public static void startInstall(Context context, String projectId) {
        Context app = context.getApplicationContext();
        synchronized (LOCK) {
            if (!validId(projectId)) return;
            State current = STATES.get(projectId);
            if (current != null && (current.phase == Phase.INSTALLING || current.phase == Phase.CHECKING || current.phase == Phase.DELETING || current.phase == Phase.READY)) return;
            STATES.put(projectId, new State(Phase.INSTALLING, 0, "설치를 준비하고 있습니다.", false, proot().canExecute()));
        }
        WORKER.execute(() -> install(app, projectId));
    }

    /** A service worker waits here; rootfs inspection/installation stays on its serial executor. */
    static void ensureRootfs(Context context, String id, Z8GuestArchive.Progress progress) throws Exception {
        java.util.concurrent.Future<?> task = WORKER.submit(() -> {
            try {
                Z8EnvironmentTemplate.project(context, id);
                synchronized (LOCK) {
                    State current = STATES.get(id);
                    if (current != null && current.phase == Phase.DELETING) throw new IOException("프로젝트를 삭제하는 중입니다.");
                    STATES.put(id, new State(Phase.INSTALLING, 0, "프로젝트 환경을 준비하고 있습니다.", false, true));
                }
                File environment = privateDirectory(context, "z8/environments/" + id);
                Z8InstallStaging.recover(environment.toPath(), ".install-", "rootfs:" + id);
                File rootfs = new File(environment, "rootfs");
                if (Files.exists(rootfs.toPath(), LinkOption.NOFOLLOW_LINKS)) {
                    marker(rootfs, id);
                    STATES.put(id, new State(Phase.READY, 100, "프로젝트 환경이 준비되었습니다.", true, true)); return;
                }
                install(context, id);
                marker(rootfs, id);
            } catch (Exception error) {
                synchronized (LOCK) {
                    State current = STATES.get(id);
                    if (current == null || current.phase != Phase.DELETING && current.phase != Phase.ERROR) failed(id, error);
                }
                throw new java.util.concurrent.CompletionException(error);
            }
        });
        try {
            while (true) {
                try { task.get(200, java.util.concurrent.TimeUnit.MILLISECONDS); break; }
                catch (java.util.concurrent.TimeoutException waiting) {
                    State current = state(context, id);
                    progress.update(current.phase == Phase.INSTALLING ? current.progress : -1,
                        Z8EnvironmentTemplate.isTemplate(id) ? "Linux 환경 준비" : "프로젝트 환경 준비");
                }
            }
        } catch (InterruptedException interrupted) {
            task.cancel(true); Thread.currentThread().interrupt(); throw interrupted;
        } catch (RuntimeException cancelled) {
            task.cancel(true); throw cancelled;
        } catch (java.util.concurrent.ExecutionException failed) {
            State current = state(context, id);
            throw new IOException(current.phase == Phase.ERROR ? current.message : "프로젝트 환경을 준비하지 못했습니다.", failed);
        }
    }

    private static void inspect(Context context, String id) throws Exception {
        synchronized (LOCK) {
            State current = STATES.get(id);
            if (current != null && (current.phase == Phase.INSTALLING || current.phase == Phase.DELETING)) return;
        }
        Z8EnvironmentTemplate.project(context, id);
        File environment = privateDirectory(context, "z8/environments/" + id);
        File rootfs = new File(environment, "rootfs");
        boolean available = proot().isFile() && proot().canExecute();
        if (Files.exists(rootfs.toPath(), LinkOption.NOFOLLOW_LINKS)) {
            marker(rootfs, id);
            ProbeResult checked;
            try { checked = available ? probe(context, id) : new ProbeResult(Collections.emptyMap(), true); }
            catch (IOException probeFailure) {
                // Readiness inspection must not erase a validated installed rootfs.
                State previous = STATES.get(id);
                inspected(id, new State(Phase.READY, 100,
                    "도구 확인을 완료하지 못해 이전 결과를 유지했습니다. 상태를 다시 확인하거나 기본 셸을 열어 주세요.",
                    true, true, previous != null && previous.toolsChecked,
                    previous == null ? Collections.emptyMap() : previous.versions, true));
                return;
            }
            String message = !available ? "Linux 환경은 있지만 z8 전용 PRoot가 설치되지 않았습니다."
                : checked.complete ? "프로젝트 Linux 환경을 확인했습니다."
                : "일부 도구의 확인 시간이 초과되었습니다. 확인된 버전은 유지했습니다. 필요하면 다시 확인해 주세요.";
            inspected(id, new State(available ? Phase.READY : Phase.UNAVAILABLE, 100,
                message, true, available, available, checked.versions, !checked.complete));
            return;
        }
        try {
            Asset asset = asset(context);
            try (InputStream ignored = context.getAssets().open(ROOTFS_ASSET)) { /* Verify the asset is present. */ }
            inspected(id, new State(available ? Phase.AVAILABLE : Phase.UNAVAILABLE, 0,
                available ? asset.distribution + " " + asset.release + " 환경을 이 프로젝트에 설치할 수 있습니다."
                    : "이 APK에는 Linux 이미지가 있지만 z8 전용 PRoot 실행 기반이 아직 없습니다.", false, available));
        } catch (FileNotFoundException missing) {
            inspected(id, new State(Phase.UNAVAILABLE, 0, "이 APK에는 검증된 Linux 이미지가 포함되어 있지 않습니다.", false, available));
        }
    }

    private static void install(Context context, String id) {
        File staging = null;
        try {
            Z8EnvironmentTemplate.project(context, id);
            if (!proot().isFile() || !proot().canExecute()) throw new IOException("먼저 z8 전용 PRoot 실행 기반을 설치해 주세요.");
            boolean fromTemplate = !Z8EnvironmentTemplate.isTemplate(id) && Z8EnvironmentTemplate.isReady(context);
            File prepared = fromTemplate ? Z8EnvironmentTemplate.rootfs(context) : null;
            Asset asset = fromTemplate ? null : asset(context);
            File environment = privateDirectory(context, "z8/environments/" + id);
            Z8InstallStaging.recover(environment.toPath(), ".install-", "rootfs:" + id);
            File target = new File(environment, "rootfs");
            if (Files.exists(target.toPath(), LinkOption.NOFOLLOW_LINKS))
                throw new IOException("기존 Linux 환경을 덮어쓰지 않습니다. 현재 설치 상태를 확인해 주세요.");
            if (!fromTemplate && environment.getUsableSpace() < asset.archive.expandedBytes + 128L * 1024 * 1024)
                throw new IOException("Linux 환경을 설치할 저장 공간이 부족합니다.");
            staging = Z8InstallStaging.create(environment.toPath(), ".install-", "rootfs:" + id).toFile();
            Z8GuestArchive.mode(staging.toPath(), 0700);
            Z8GuestArchive.Progress installProgress = (percent, detail) -> {
                    if (Thread.currentThread().isInterrupted()) throw new java.util.concurrent.CancellationException("설치가 중단되었습니다.");
                    STATES.put(id, new State(Phase.INSTALLING, percent, detail, false, true));
                };
            if (fromTemplate) Z8EnvironmentTemplate.copyRootfs(prepared, staging, installProgress);
            else Z8GuestArchive.extract(() -> context.getAssets().open(ROOTFS_ASSET), asset.archive, staging, installProgress);
            STATES.put(id, new State(Phase.INSTALLING, 92, "프로젝트 HOME과 연결 경로를 준비하고 있습니다.", false, true));
            for (String mount : Arrays.asList("dev", "proc", "sys", "tmp", "workspace", "z8/home", "run/z8/attention"))
                mountDirectory(staging, mount);
            privateDirectory(context, "z8/homes/" + id);
            updateDns(context, staging, true);
            JSONObject marker = fromTemplate ? marker(prepared, Z8EnvironmentTemplate.ID) : new JSONObject();
            marker.put("schemaVersion", 1); marker.put("projectId", id);
            marker.put("architecture", "aarch64");
            if (!fromTemplate) {
                marker.put("archiveSha256", asset.archive.sha256); marker.put("sourceSha256", asset.sourceSha256);
                marker.put("distribution", asset.distribution); marker.put("release", asset.release);
            }
            marker.put("installedAt", System.currentTimeMillis());
            Files.write(new File(staging, Z8GuestArchive.MARKER).toPath(), marker.toString().getBytes(StandardCharsets.UTF_8),
                java.nio.file.StandardOpenOption.CREATE_NEW, java.nio.file.StandardOpenOption.WRITE);
            Z8GuestArchive.mode(staging.toPath(), 0755);
            marker(staging, id);
            if (Thread.currentThread().isInterrupted()) throw new IOException("설치가 중단되었습니다.");
            if (Files.exists(target.toPath(), LinkOption.NOFOLLOW_LINKS)) throw new IOException("설치 중 다른 환경이 생성되었습니다.");
            // Same-filesystem directory rename publishes the complete tree. Never
            // request REPLACE_EXISTING, and serialize all installs in this process.
            Files.move(staging.toPath(), target.toPath());
            STATES.put(id, new State(Phase.READY, 100, "Linux 환경을 설치했습니다. 터미널에서 실제 실행을 확인할 수 있습니다.", true, true));
        } catch (Exception error) { failed(id, error); }
        finally {
            if (staging != null) {
                try { Z8InstallStaging.discard(staging.toPath(), "rootfs:" + id); }
                catch (Exception ignored) { /* Its ownership receipt permits cleanup after a process restart. */ }
            }
        }
    }

    /** Build off the UI thread: validates paths and refreshes managed resolver data. */
    public static Launch command(Context context, String id, String relativeCwd) throws IOException {
        if (standardProfilePrepared(context, id))
            return commandFor(context, id, relativeCwd, new String[] { "/bin/bash", "--login" });
        invalidateReadiness(id);
        Launch launch = commandFor(context, id, relativeCwd, new String[]{"/bin/bash", "-c", PREPARE_SHELL});
        return new Launch(launch.executable, Arrays.asList(launch.arguments), launch.workingDirectory, launch.commandOffset, true);
    }

    /** Tiny preparation receipt check, not a version scan. New sessions never run a full probe. */
    public static boolean standardProfilePrepared(Context context, String id) {
        if (!validId(id)) return false;
        Path receipt = new File(context.getFilesDir(), "z8/environments/" + id + "/rootfs/etc/z8/tools.ready").toPath();
        if (!Files.isRegularFile(receipt, LinkOption.NOFOLLOW_LINKS)) return false;
        try (InputStream input = Files.newInputStream(receipt, LinkOption.NOFOLLOW_LINKS)) {
            return "z8-tools-v2".equals(new String(read(input, 64), StandardCharsets.UTF_8).trim());
        } catch (IOException ignored) { return false; }
    }

    public static boolean validAction(String action) {
        return Arrays.asList("setup-tools", "setup-codex", "setup-claude", "codex", "claude", "github-auth",
            "hooks-codex", "hooks-claude", "rescue-shell").contains(action);
    }

    public static String actionLabel(String action) {
        if (action == null) return "Linux";
        switch (action) {
            case "setup-tools": return "개발 도구 설치";
            case "setup-codex": return "Codex 설치";
            case "setup-claude": return "Claude 설치";
            case "codex": return "Codex";
            case "claude": return "Claude Code";
            case "github-auth": return "GitHub 로그인";
            case "hooks-codex": return "Codex 알림";
            case "hooks-claude": return "Claude 알림";
            default: return "Linux";
        }
    }

    public static Launch actionCommand(Context context, String id, String relativeCwd, String action) throws IOException {
        if (!validAction(action)) throw new IOException("등록되지 않은 터미널 작업입니다.");
        if ("rescue-shell".equals(action))
            return commandFor(context, id, relativeCwd, new String[]{"/bin/bash", "--login"});
        if (action.startsWith("setup-") || action.startsWith("hooks-")) invalidateReadiness(id);
        if (Arrays.asList("codex", "claude", "github-auth", "hooks-codex", "hooks-claude").contains(action)) {
            String required = action.startsWith("hooks-") ? "python" : "github-auth".equals(action) ? "gh" : action;
            Map<String, String> versions = probe(context, id, required).versions;
            if (!versions.containsKey(required)) throw new IOException(actionLabel(action)
                + " 실행 준비가 되지 않았습니다. 프로젝트의 Linux 환경에서 설치 상태를 확인해 주세요.");
        }
        return commandFor(context, id, relativeCwd, "setup-tools".equals(action)
            ? new String[]{"/bin/bash", "/usr/local/lib/z8/setup-tools.sh"}
            : new String[]{"/bin/bash", "/usr/local/lib/z8/guest-task.sh", action});
    }

    /** Same guest execution adapter for terminals, Git and future CLI tools. */
    public static Launch commandFor(Context context, String id, String relativeCwd, String[] guestCommand) throws IOException {
        synchronized (LOCK) {
            State current = STATES.get(id == null ? "" : id);
            if (current != null && current.phase == Phase.DELETING)
                throw new IOException("삭제 중인 프로젝트에서는 새 작업을 실행할 수 없습니다.");
        }
        if (guestCommand == null || guestCommand.length == 0 || guestCommand.length > 2048
                || guestCommand[0] == null || !guestCommand[0].startsWith("/"))
            throw new IOException("절대 경로의 Linux 실행 파일이 필요합니다.");
        if (Z8EnvironmentTemplate.isTemplate(id) && !Z8EnvironmentTemplate.allows(guestCommand))
            throw new IOException("기본 개발 환경에서는 초기 설치와 확인 작업만 실행할 수 있습니다.");
        if (!Arrays.asList("/bin/bash", "/usr/bin/git", "/usr/bin/gh", "/usr/bin/python3").contains(guestCommand[0]))
            throw new IOException("등록되지 않은 Linux 실행 파일입니다.");
        boolean loginOrSetup = guestCommand.length == 2
            && ("--login".equals(guestCommand[1]) || "/usr/local/lib/z8/setup-tools.sh".equals(guestCommand[1])
                || "/usr/local/lib/z8/probe-tools.sh".equals(guestCommand[1]));
        boolean fixedAction = guestCommand.length == 3 && "/usr/local/lib/z8/guest-task.sh".equals(guestCommand[1])
            && validAction(guestCommand[2]) && !"setup-tools".equals(guestCommand[2]);
        boolean fixedProbe = guestCommand.length == 3 && "/usr/local/lib/z8/probe-tools.sh".equals(guestCommand[1])
            && Arrays.asList("python", "pip", "venv", "node", "npm", "git", "gh", "make", "cc", "tmux", "claude", "codex").contains(guestCommand[2]);
        boolean prepareShell = guestCommand.length == 3 && "-c".equals(guestCommand[1]) && PREPARE_SHELL.equals(guestCommand[2]);
        if (guestCommand[0].equals("/bin/bash") && !loginOrSetup && !fixedAction && !fixedProbe && !prepareShell)
            throw new IOException("등록되지 않은 Linux 셸 진입점입니다.");
        long argumentBytes = 0;
        for (String argument : guestCommand) {
            if (argument == null || argument.indexOf('\0') >= 0) throw new IOException("Linux 실행 인수가 올바르지 않습니다.");
            argumentBytes += argument.getBytes(StandardCharsets.UTF_8).length;
            if (argumentBytes > 65536) throw new IOException("Linux 실행 인수가 크기 제한을 초과했습니다.");
        }
        Z8Projects.Project project = Z8EnvironmentTemplate.project(context, id);
        File rootfs = new File(privateDirectory(context, "z8/environments/" + id), "rootfs");
        if (!Files.exists(rootfs.toPath(), LinkOption.NOFOLLOW_LINKS))
            throw new IOException("이 프로젝트에 Linux 환경을 먼저 설치해 주세요.");
        marker(rootfs, id);
        File executable = proot();
        if (!executable.isFile() || !executable.canExecute()) throw new IOException("z8 전용 PRoot 실행 파일이 없습니다.");
        Z8RuntimeLauncher.ensureAppLibraries(context);
        File home = privateDirectory(context, "z8/homes/" + id);
        File temp = privateDirectory(context, "z8/environments/" + id + "/tmp");
        File shm = privateDirectory(context, "z8/environments/" + id + "/shm");
        File transport = privateDirectory(context, "z8/attention/transport");
        String workingDirectory = "/z8/home";
        if (relativeCwd != null) {
            Z8Files.directory(project.source, relativeCwd);
            workingDirectory = relativeCwd.isEmpty() ? "/workspace" : "/workspace/" + relativeCwd;
        }
        syncManaged(context, rootfs);
        updateDns(context, rootfs, false);
        List<String> args = new ArrayList<>(Arrays.asList("--kill-on-exit", "--link2symlink", "--sysvipc", "-L",
            "--change-id=0:0", "-r", rootfs.getAbsolutePath(), "-b", "/proc:/proc",
            "-b", "/dev/pts:/dev/pts", "-b", "/dev/null:/dev/null", "-b", "/dev/zero:/dev/zero",
            "-b", "/dev/urandom:/dev/random", "-b", "/dev/urandom:/dev/urandom",
            "-b", "/dev/tty:/dev/tty", "-b", "/dev/ptmx:/dev/ptmx",
            "-b", shm.getAbsolutePath() + ":/dev/shm",
            "-b", temp.getAbsolutePath() + ":/tmp",
            "-b", project.source.getAbsolutePath() + ":/workspace",
            "-b", home.getAbsolutePath() + ":/z8/home",
            "-b", transport.getAbsolutePath() + ":/run/z8/attention",
            "-w", workingDirectory,
            "/usr/bin/env", "-u", "LD_PRELOAD", "-u", "LD_LIBRARY_PATH", "-u", "PREFIX",
            "-u", "ENV", "-u", "BASH_ENV", "-u", "GIT_DIR", "-u", "GIT_WORK_TREE",
            "HOME=/z8/home", "SHELL=/bin/bash", "USER=root", "LOGNAME=root", "Z8_PROJECT_ID=" + id,
            "PATH=/usr/local/lib/z8/browser/bin:/opt/z8/node/current/bin:/z8/home/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "TERM=xterm-256color", "LANG=C.UTF-8",
            "BROWSER=/usr/local/lib/z8/browser/bin/xdg-open", "GH_BROWSER=/usr/local/lib/z8/browser/bin/xdg-open",
            "TMPDIR=/tmp", "Z8_EVENT_SOCKET=/run/z8/attention/events.sock"));
        int offset = args.size();
        args.addAll(Arrays.asList(guestCommand));
        int api = android.os.Build.VERSION.SDK_INT;
        boolean linked = Z8RuntimeLauncher.requiresSystemLinker(api);
        return new Launch(linked ? Z8RuntimeLauncher.LINKER : executable.getAbsolutePath(),
            Z8RuntimeLauncher.hostArguments(executable.getAbsolutePath(), args, api),
            project.source.getAbsolutePath(), offset + (linked ? 1 : 0));
    }

    /** Actual bounded execution, independent of stale tools.ready files. Call off the UI thread. */
    private static final class ProbeResult {
        final Map<String, String> versions;
        final boolean complete;
        ProbeResult(Map<String, String> versions, boolean complete) { this.versions = versions; this.complete = complete; }
    }
    private static ProbeResult probe(Context context, String id) throws IOException { return probe(context, id, null); }
    private static ProbeResult probe(Context context, String id, String tool) throws IOException {
        Launch launch = commandFor(context, id, null, tool == null
            ? new String[]{"/bin/bash", "/usr/local/lib/z8/probe-tools.sh"}
            : new String[]{"/bin/bash", "/usr/local/lib/z8/probe-tools.sh", tool});
        List<String> argv = new ArrayList<>(); argv.add(launch.executable); argv.addAll(Arrays.asList(launch.arguments));
        Map<String, String> environment = new HashMap<>();
        environment.put("PATH", "/system/bin");
        environment.put("PROOT_TMP_DIR", context.getCacheDir().getAbsolutePath());
        Z8Git.Result result;
        try {
            result = new Z8Git.ProcessRunner().run(argv, new File(launch.workingDirectory), environment,
                new byte[0], 100, 64 * 1024);
        } catch (IOException error) { throw new IOException("Linux 도구 상태를 확인하지 못했습니다. 잠시 후 다시 확인해 주세요.", error); }
        if (result.code != 0 && result.code != 124)
            throw new IOException("Linux 도구 상태 확인이 완료되지 않았습니다 (" + result.code + ").");
        Map<String, String> values = new LinkedHashMap<>();
        boolean complete = result.code == 0;
        for (String line : result.output().split("\n")) {
            String[] fields = line.split("\t", 2);
            if (fields.length == 2 && fields[1].equals("?")) complete = false;
            if (fields.length == 2 && fields[0].matches("[a-z]+") && !fields[1].equals("-") && !fields[1].equals("?")
                    && !fields[1].isEmpty() && fields[1].length() <= 160) values.put(fields[0], fields[1]);
        }
        // The aggregate deadline can expire after core tools already passed. Preserve
        // those successes rather than turning an installed profile back into unknown.
        return new ProbeResult(values, complete);
    }

    /** Updates only application-owned entrypoints; never writes HOME, source or user startup/config files. */
    private static synchronized void syncManaged(Context context, File rootfs) throws IOException {
        File directory = Z8Files.directory(rootfs, "usr/local/lib/z8");
        for (String name : Arrays.asList("provision.sh", "debian-base-packages.txt", "shellrc", "welcome.sh",
                "setup-tools.sh", "guest-task.sh", "install-ai.sh", "ai-tools.lock.json", "install-node.py",
                "node.lock.json", "probe-tools.sh", "browser-open.py", "html-preview.py", "xdg-open", "browser-profile.sh", "cli-profile.sh", "codex-launch.py")) {
            byte[] content;
            try (InputStream input = context.getAssets().open("z8/guest-managed/" + name)) { content = read(input, 2 * 1024 * 1024); }
            // Keep just the browser shim on PATH; it must be executable for CLI
            // launchers which use BROWSER or discover xdg-open directly.
            File targetDirectory = directory;
            String targetName = name;
            if ("xdg-open".equals(name)) {
                for (String child : Arrays.asList("browser", "browser/bin")) {
                    Path childPath = Z8GuestArchive.checked(rootfs, "usr/local/lib/z8/" + child);
                    if (!Files.exists(childPath, LinkOption.NOFOLLOW_LINKS)) Files.createDirectory(childPath);
                    if (!Files.isDirectory(childPath, LinkOption.NOFOLLOW_LINKS))
                        throw new IOException("브라우저 실행 경로가 폴더가 아닙니다.");
                }
                targetDirectory = Z8Files.directory(rootfs, "usr/local/lib/z8/browser/bin");
            }
            if ("browser-profile.sh".equals(name) || "cli-profile.sh".equals(name)) {
                targetDirectory = Z8Files.directory(rootfs, "etc/profile.d");
                targetName = "browser-profile.sh".equals(name) ? "z8-browser.sh" : "z8-cli.sh";
            }
            Path target = new File(targetDirectory, targetName).toPath();
            if (Files.isSymbolicLink(target) || (Files.exists(target, LinkOption.NOFOLLOW_LINKS)
                    && !Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS)))
                throw new IOException("앱 관리 스크립트 경로가 변경되어 업데이트를 중단했습니다: " + name);
            if (Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS) && Files.size(target) == content.length
                    && Arrays.equals(Files.readAllBytes(target), content)
                    && (!"xdg-open".equals(name) || Files.isExecutable(target))) continue;
            Path temp = Files.createTempFile(targetDirectory.toPath(), ".managed-", ".tmp");
            try {
                Files.write(temp, content); Z8GuestArchive.mode(temp, "xdg-open".equals(name) ? 0755 : 0644);
                Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } finally { Files.deleteIfExists(temp); }
        }
    }

    private static Asset asset(Context context) throws IOException {
        try (InputStream input = context.getAssets().open(MANIFEST_ASSET)) {
            JSONObject json = new JSONObject(new String(read(input, 16 * 1024 * 1024), StandardCharsets.UTF_8));
            if (json.getInt("schemaVersion") != 1 || !"z8-guest-rootfs".equals(json.getString("type"))
                    || !"aarch64".equals(json.getString("architecture")) || json.getInt("normalizationVersion") != 1
                    || !"rootfs.zip".equals(json.getString("archive"))) throw new IOException("지원하지 않는 Linux 이미지 형식입니다.");
            String distribution = json.getString("distribution");
            String release = json.getString("release");
            if (!distribution.matches("[a-z0-9._-]{1,40}") || !release.matches("[A-Za-z0-9._-]{1,40}"))
                throw new IOException("Linux 이미지 정보가 올바르지 않습니다.");
            String sourceSha = json.getJSONObject("source").getString("sha256");
            if (!sourceSha.matches("[a-f0-9]{64}")) throw new IOException("원본 이미지 해시가 올바르지 않습니다.");
            JSONArray records = json.getJSONArray("files");
            if (records.length() != json.getInt("entryCount") || records.length() > Z8GuestArchive.MAX_ENTRIES)
                throw new IOException("이미지 항목 수가 올바르지 않습니다.");
            List<Z8GuestArchive.Item> items = new ArrayList<>();
            for (int index = 0; index < records.length(); index++) {
                JSONObject item = records.getJSONObject(index);
                String type = item.getString("type");
                if (!type.equals("file") && !type.equals("directory")) throw new IOException("특수 파일이 포함된 이미지는 설치할 수 없습니다.");
                items.add(new Z8GuestArchive.Item(item.getString("path"), type.equals("directory"), item.getLong("size"), item.getInt("mode")));
            }
            return new Asset(new Z8GuestArchive.Manifest(json.getString("archiveSha256"), json.getLong("archiveBytes"),
                json.getLong("totalUncompressedBytes"), items), distribution, release, sourceSha);
        } catch (IOException error) { throw error; }
        catch (Exception error) { throw new IOException("Linux 이미지 메타데이터를 읽을 수 없습니다.", error); }
    }

    static JSONObject marker(File rootfs, String id) throws IOException {
        Z8Files.directory(rootfs, "");
        Path path = Z8GuestArchive.checked(rootfs, Z8GuestArchive.MARKER);
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) throw new IOException("완료된 Linux 환경이 없습니다. 환경 설치 상태를 확인해 주세요.");
        JSONObject value;
        try (InputStream input = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS)) {
            value = new JSONObject(new String(read(input, 8192), StandardCharsets.UTF_8));
            if (value.getInt("schemaVersion") != 1 || !id.equals(value.getString("projectId"))
                    || !"aarch64".equals(value.getString("architecture"))
                    || !value.getString("archiveSha256").matches("[a-f0-9]{64}"))
                throw new IOException("Linux 환경의 프로젝트 또는 이미지 정보가 맞지 않습니다.");
        } catch (IOException error) { throw error; }
        catch (Exception error) { throw new IOException("Linux 환경의 설치 기록을 읽을 수 없습니다.", error); }
        File bash = new File(rootfs, "bin/bash").getCanonicalFile();
        if (!bash.toPath().startsWith(rootfs.getCanonicalFile().toPath()) || !bash.isFile() || !bash.canExecute())
            throw new IOException("Linux bash 실행 파일이 없거나 환경 밖을 가리킵니다.");
        return value;
    }

    static File privateDirectory(Context context, String relative) throws IOException {
        File root = context.getFilesDir().getCanonicalFile();
        Path current = root.toPath();
        for (String part : relative.split("/", -1)) {
            Z8Files.name(part); current = current.resolve(part);
            if (Files.isSymbolicLink(current)) throw new IOException("앱 저장 경로에 링크가 있습니다.");
            if (!Files.exists(current, LinkOption.NOFOLLOW_LINKS)) Files.createDirectory(current);
            if (!Files.isDirectory(current, LinkOption.NOFOLLOW_LINKS)) throw new IOException("앱 저장 경로가 폴더가 아닙니다.");
        }
        return current.toFile();
    }

    private static void mountDirectory(File rootfs, String relative) throws IOException {
        Path path = Z8GuestArchive.checked(rootfs, relative);
        Files.createDirectories(path);
        if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Linux 연결 경로가 폴더가 아닙니다.");
    }

    private static void updateDns(Context context, File rootfs, boolean firstInstall) throws IOException {
        List<String> servers = new ArrayList<>();
        try {
            ConnectivityManager manager = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
            Network active = manager == null ? null : manager.getActiveNetwork();
            LinkProperties properties = active == null ? null : manager.getLinkProperties(active);
            if (properties != null) for (InetAddress address : properties.getDnsServers()) {
                if (!address.isAnyLocalAddress() && !address.isLoopbackAddress()) servers.add(address.getHostAddress());
            }
        } catch (SecurityException ignored) { /* Never substitute an unrequested public DNS service. */ }
        Path etc = Z8GuestArchive.checked(rootfs, "etc");
        if (!Files.isDirectory(etc, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Linux /etc 경로가 없습니다.");
        Path resolver = etc.resolve("resolv.conf");
        if (!firstInstall && !Files.isSymbolicLink(resolver) && Files.isRegularFile(resolver, LinkOption.NOFOLLOW_LINKS)) {
            try (InputStream input = Files.newInputStream(resolver, LinkOption.NOFOLLOW_LINKS)) {
                String existing = new String(read(input, 65536), StandardCharsets.UTF_8);
                if (!existing.startsWith(DNS_HEADER)) return; // Preserve a user-managed resolver.
            }
        } else if (!firstInstall && Files.isSymbolicLink(resolver)) return;
        StringBuilder content = new StringBuilder(DNS_HEADER);
        if (servers.isEmpty()) content.append("# Android has no active DNS server; reconnect the network and reopen this terminal.\n");
        else for (String server : servers) content.append("nameserver ").append(server).append('\n');
        Path temp = Files.createTempFile(etc, ".z8-resolv-", ".tmp");
        try {
            Files.write(temp, content.toString().getBytes(StandardCharsets.UTF_8));
            Z8GuestArchive.mode(temp, 0644);
            Files.move(temp, resolver, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } finally { Files.deleteIfExists(temp); }
    }

    private static byte[] read(InputStream input, int limit) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192]; int count;
        while ((count = input.read(buffer)) != -1) {
            if (output.size() + count > limit) throw new IOException("메타데이터가 크기 제한을 초과했습니다.");
            output.write(buffer, 0, count);
        }
        return output.toByteArray();
    }

    private static boolean validId(String id) {
        try { return id != null && UUID.fromString(id).toString().equals(id); }
        catch (IllegalArgumentException invalid) { return false; }
    }
    private static File proot() { return new File(TermuxConstants.TERMUX_PREFIX_DIR_PATH, "bin/proot"); }
    private static void inspected(String id, State result) {
        synchronized (LOCK) {
            State current = STATES.get(id);
            if (current != null && current.phase == Phase.CHECKING) {
                STATES.put(id, result);
                if (result.phase == Phase.READY) LAST_CHECKED.put(id, SystemClock.elapsedRealtime());
            }
        }
    }
    private static void failed(String id, Exception error) {
        STATES.put(id, new State(Phase.ERROR, 0, error.getMessage() == null ? "Linux 환경 작업에 실패했습니다." : error.getMessage(), false, proot().canExecute()));
    }
}
