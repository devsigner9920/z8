package com.termux.app;

import android.os.SystemClock;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;
import com.termux.shared.termux.TermuxConstants;
import com.termux.terminal.TerminalSession;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.WeakHashMap;
import java.util.function.BooleanSupplier;

/** Stop only captured project processes and verify their identities before deleting files. */
public final class Z8ProjectProcesses {
    public static final class Target {
        final TerminalSession terminal;
        final int pid;
        final boolean guest;
        final String projectId;
        Target(TerminalSession terminal, int pid, String projectId) {
            this.terminal = terminal; this.pid = pid; this.projectId = projectId;
            this.guest = projectId != null && !projectId.isEmpty();
        }
    }
    static final class ProcessRecord {
        final int pid, uid, parent, tracer;
        final long started;
        final char state;
        ProcessRecord(int pid, int uid, int parent, int tracer, long started, char state) {
            this.pid = pid; this.uid = uid; this.parent = parent; this.tracer = tracer; this.started = started; this.state = state;
        }
        boolean same(ProcessRecord other) { return other != null && pid == other.pid && uid == other.uid && started == other.started; }
        boolean alive() { return state != 'Z' && state != 'X' && state != 'x'; }
    }
    interface Access {
        Map<Integer, ProcessRecord> scan() throws Exception;
        ProcessRecord read(int pid) throws Exception;
        boolean isProot(int pid, String projectId) throws Exception;
        void quit(int pid) throws Exception;
        long now();
        void pause() throws InterruptedException;
        default boolean isPreparationShell(int pid, String marker, String script) throws Exception { return false; }
    }
    private static final class Checkpoint {
        final Map<Integer, ProcessRecord> roots = new LinkedHashMap<>();
        final Map<Integer, ProcessRecord> tracked = new LinkedHashMap<>();
    }
    // A failed stop must not become a successful deletion merely because the PTY
    // has now exited. Keep its captured tracee identities until a retry verifies them.
    private static final Map<TerminalSession, Checkpoint> UNVERIFIED = new WeakHashMap<>();

    /** Captured while the fixed wrapper is waiting for acknowledgement, before exec. */
    static final class PreparationTarget {
        final ProcessRecord root;
        final String projectId, marker, script;
        final Checkpoint checkpoint = new Checkpoint();
        PreparationTarget(ProcessRecord root, String projectId, String marker, String script) {
            this.root = root; this.projectId = projectId; this.marker = marker; this.script = script;
            checkpoint.roots.put(root.pid, root); checkpoint.tracked.put(root.pid, root);
        }
    }
    private Z8ProjectProcesses() {}
    public static boolean hasUnverified(TerminalSession terminal) {
        synchronized (UNVERIFIED) { return UNVERIFIED.containsKey(terminal); }
    }

    /** Cheap capture only; /proc access belongs to the IO worker. */
    public static Target capture(TerminalSession terminal) {
        Z8SessionOrigin origin = Z8SessionOrigin.of(terminal);
        return new Target(terminal, terminal.getPid(), origin == null ? null : origin.projectId);
    }

    static PreparationTarget capturePreparation(int pid, String projectId, String marker, String script) throws Exception {
        return capturePreparation(pid, projectId, marker, script, android.os.Process.myUid(), android.os.Process.myPid(), new ProcAccess());
    }

    static PreparationTarget capturePreparation(int pid, String projectId, String marker, String script,
                                                int uid, int parentPid, Access access) throws Exception {
        ProcessRecord process = access.read(pid);
        if (process == null || !process.alive() || process.uid != uid || process.parent != parentPid
                || !access.isPreparationShell(pid, marker, script))
            throw preserved(Z8Text.text("Could not verify the owner of the initial setup process.", "초기 설치 프로세스의 소유자를 확인하지 못했습니다."));
        // Re-read after executable/cmdline checks to reject a PID reused mid-check.
        if (!process.same(access.read(pid))) throw preserved(Z8Text.text("The initial setup process changed during verification.", "초기 설치 프로세스가 확인 중 변경되었습니다."));
        return new PreparationTarget(process, projectId, marker, script);
    }

    static void observePreparation(PreparationTarget target) throws Exception { observePreparation(target, new ProcAccess()); }
    static void observePreparation(PreparationTarget target, Access access) throws Exception {
        synchronized (target) { collect(access.scan(), target.checkpoint.roots, target.checkpoint.tracked); }
    }

    /** The caller clears interruption for this bounded cleanup, then restores it. */
    static void stopPreparation(PreparationTarget target) throws Exception { stopPreparation(target, new ProcAccess()); }
    static void stopPreparation(PreparationTarget target, Access access) throws Exception {
        boolean interrupted = Thread.interrupted();
        try { synchronized (target) {
            Map<Integer, ProcessRecord> before = access.scan();
            collect(before, target.checkpoint.roots, target.checkpoint.tracked);
            ProcessRecord current = access.read(target.root.pid);
            if (target.root.same(current) && current.alive()) {
                // The same process may still be between read(ack) and exec. SIGQUIT
                // is safe for both the fixed childless wrapper and PRoot; SIGKILL
                // or SIGTERM after acknowledgement can orphan traced apt children.
                if (!access.isProot(current.pid, target.projectId)
                        && !access.isPreparationShell(current.pid, target.marker, target.script))
                    throw preserved(Z8Text.text("Could not verify the initial setup executable or project.", "초기 설치 실행 파일 또는 프로젝트를 확인하지 못했습니다."));
                if (target.root.same(access.read(current.pid))) access.quit(current.pid);
            }
            long deadline = access.now() + 10000;
            while (true) {
                Map<Integer, ProcessRecord> frame = access.scan();
                collect(frame, target.checkpoint.roots, target.checkpoint.tracked);
                boolean alive = false;
                for (ProcessRecord expected : target.checkpoint.tracked.values()) {
                    ProcessRecord found = frame.get(expected.pid);
                    if (found == null) found = access.read(expected.pid);
                    if (expected.same(found) && found.alive()) { alive = true; break; }
                }
                if (!alive) return;
                if (access.now() >= deadline) throw preserved(Z8Text.text("Child processes from initial setup are still running.", "초기 설치의 하위 프로세스가 아직 종료되지 않았습니다."));
                // Cancellation must not interrupt verification halfway through and
                // discard the retained identities. The outer close restores it.
                try { access.pause(); }
                catch (InterruptedException stopped) { interrupted = true; }
            }
        } } finally { if (interrupted) Thread.currentThread().interrupt(); }
    }

    public static void stopAndVerify(List<Target> targets, BooleanSupplier stopping) throws Exception {
        stopAndVerify(targets, stopping, new ProcAccess());
    }

    static void stopAndVerify(List<Target> targets, BooleanSupplier stopping, Access access) throws Exception {
        checkCancelled(stopping);
        if (targets.isEmpty()) return;
        Checkpoint checkpoint = new Checkpoint();
        synchronized (UNVERIFIED) {
            for (Target target : targets) {
                Checkpoint previous = UNVERIFIED.get(target.terminal);
                if (previous != null) {
                    checkpoint.roots.putAll(previous.roots);
                    checkpoint.tracked.putAll(previous.tracked);
                }
            }
        }
        Map<Integer, ProcessRecord> before = access.scan();
        Map<Integer, ProcessRecord> roots = checkpoint.roots;
        Map<Integer, ProcessRecord> tracked = checkpoint.tracked;
        Map<Integer, Target> liveTargets = new LinkedHashMap<>();
        // Validate every target before sending any signal. A PID name alone is never identity.
        for (Target target : targets) {
            if (target.pid <= 0) continue;
            ProcessRecord process = before.get(target.pid);
            if (process == null) {
                if (access.read(target.pid) != null) throw preserved(Z8Text.text("Could not verify the owner of the terminal process.", "터미널 프로세스의 소유자를 확인하지 못했습니다."));
                continue;
            }
            if (!process.alive()) continue;
            if (target.terminal.getPid() != target.pid) throw preserved(Z8Text.text("The terminal process has changed.", "터미널 프로세스가 변경되었습니다."));
            if (target.guest && !access.isProot(target.pid, target.projectId)) throw preserved(Z8Text.text("Could not verify the project's running process.", "프로젝트 실행 프로세스를 확인하지 못했습니다."));
            roots.put(process.pid, process); tracked.put(process.pid, process); liveTargets.put(process.pid, target);
        }
        collect(before, roots, tracked);
        if (!tracked.isEmpty()) synchronized (UNVERIFIED) {
            for (Target target : targets) UNVERIFIED.put(target.terminal, checkpoint);
        }
        for (Map.Entry<Integer, Target> item : liveTargets.entrySet()) {
            checkCancelled(stopping);
            ProcessRecord expected = roots.get(item.getKey());
            if (!expected.same(access.read(expected.pid))) continue; // Exited or reused: never signal the new owner.
            if (item.getValue().guest) access.quit(expected.pid);
            else item.getValue().terminal.finishIfRunning();
        }
        long deadline = access.now() + 10000;
        while (true) {
            checkCancelled(stopping);
            Map<Integer, ProcessRecord> current = access.scan();
            collect(current, roots, tracked);
            boolean remaining = false;
            for (ProcessRecord expected : tracked.values()) {
                ProcessRecord process = current.get(expected.pid);
                if (process == null) process = access.read(expected.pid);
                if (expected.same(process) && process.alive()) { remaining = true; break; }
            }
            if (!remaining) {
                synchronized (UNVERIFIED) {
                    for (Target target : targets)
                        if (UNVERIFIED.get(target.terminal) == checkpoint) UNVERIFIED.remove(target.terminal);
                }
                return;
            }
            if (access.now() >= deadline) throw preserved(Z8Text.text("The project still has running child processes.", "프로젝트의 실행 중인 하위 프로세스가 남아 있습니다."));
            access.pause();
        }
    }

    private static void collect(Map<Integer, ProcessRecord> current, Map<Integer, ProcessRecord> roots,
                                Map<Integer, ProcessRecord> tracked) throws IOException {
        boolean added;
        do {
            added = false;
            for (ProcessRecord process : current.values()) {
                if (process.same(tracked.get(process.pid))) continue;
                ProcessRecord tracer = roots.get(process.tracer);
                ProcessRecord parent = tracked.get(process.parent);
                // Never adopt children of a PID that has since been reused by another process.
                if ((tracer != null && tracer.same(current.get(tracer.pid)))
                        || (parent != null && parent.same(current.get(parent.pid)))) {
                    if (tracked.size() >= 32768) throw preserved(Z8Text.text("The process verification limit was exceeded.", "프로세스 확인 범위를 초과했습니다."));
                    tracked.put(process.pid, process); added = true;
                }
            }
        } while (added);
    }

    private static void checkCancelled(BooleanSupplier stopping) throws IOException {
        if (Thread.currentThread().isInterrupted() || stopping.getAsBoolean()) throw preserved(Z8Text.text("The runtime service has stopped.", "실행 서비스가 중단되었습니다."));
    }
    private static IOException preserved(String detail) { return new IOException(detail + Z8Text.text(" Your files were kept. Try again.", " 파일을 보존했습니다. 다시 시도해 주세요.")); }

    /** Called with EXECUTION_LOCK held before replacing an app-owned host runtime. */
    static void requireRuntimeIdle() throws IOException {
        requireRuntimeIdle(new ProcAccess(), android.os.Process.myPid());
    }
    static void requireRuntimeIdle(Access access, int callerPid) throws IOException {
        try {
            for (ProcessRecord process : access.scan().values()) {
                if (process.pid != callerPid && process.alive())
                    throw new IOException(Z8Text.text("Close open terminals and stop running tasks before updating the runtime. Your existing files were kept.", "실행 기반을 갱신하려면 열려 있는 터미널과 실행 작업을 먼저 종료해 주세요. 기존 파일은 보존했습니다."));
            }
        } catch (IOException error) { throw error; }
        catch (Exception error) { throw preserved(Z8Text.text("Could not verify running tasks.", "실행 중인 작업을 확인하지 못했습니다.")); }
    }

    static final class ProcAccess implements Access {
        final int uid;
        final Path proc;
        private final Path linker;
        ProcAccess() { this(Paths.get("/proc"), android.os.Process.myUid()); }
        ProcAccess(Path proc, int uid) { this(proc, uid, Paths.get("/system/bin/linker64")); }
        ProcAccess(Path proc, int uid, Path linker) { this.proc = proc; this.uid = uid; this.linker = linker; }
        @Override public Map<Integer, ProcessRecord> scan() throws Exception {
            Map<Integer, ProcessRecord> result = new LinkedHashMap<>();
            try (DirectoryStream<Path> entries = Files.newDirectoryStream(proc)) {
                for (Path path : entries) {
                    String name = path.getFileName().toString();
                    if (!name.matches("[1-9][0-9]*")) continue;
                    int pid;
                    try { pid = Integer.parseInt(name); } catch (NumberFormatException ignored) { continue; }
                    try { if (Os.stat(path.toString()).st_uid != uid) continue; }
                    catch (ErrnoException error) {
                        if (error.errno == OsConstants.ENOENT || error.errno == OsConstants.ESRCH) continue;
                        throw preserved(Z8Text.text("Could not read process ownership information.", "프로세스 소유 정보를 읽지 못했습니다."));
                    }
                    ProcessRecord record = read(pid);
                    if (record != null && record.uid == uid) result.put(pid, record);
                }
            } catch (IOException error) { throw preserved(Z8Text.text("Could not verify the project's process list.", "프로젝트 프로세스 목록을 확인하지 못했습니다.")); }
            return result;
        }
        @Override public ProcessRecord read(int pid) throws IOException {
            Path directory = proc.resolve(Integer.toString(pid));
            try {
                // Read stat on both sides of status, so exit/reuse during the read cannot splice identities.
                String first = small(directory.resolve("stat"));
                String status = small(directory.resolve("status"));
                String last = small(directory.resolve("stat"));
                ProcessRecord one = parse(pid, first, status), two = parse(pid, last, status);
                if (!one.same(two)) throw preserved(Z8Text.text("The process changed during verification.", "프로세스가 확인 중 변경되었습니다."));
                return two;
            } catch (java.nio.file.NoSuchFileException gone) { return null; }
            catch (IOException error) { throw preserved(Z8Text.text("Could not read the project process status.", "프로젝트 프로세스 상태를 읽지 못했습니다.")); }
        }
        @Override public boolean isProot(int pid, String projectId) throws IOException {
            Path prefix = Paths.get(TermuxConstants.TERMUX_PREFIX_DIR_PATH);
            Path proot = prefix.resolve("bin/proot");
            Path executable = proc.resolve(pid + "/exe");
            if (!Files.isSameFile(executable, proot)) {
                // System-linker launches retain linker64 as /proc/pid/exe. Do
                // not treat every linker process as PRoot: require its actual
                // executable mapping as well as the project argument below.
                if (!Files.isSameFile(executable, linker) || !mapsExecutable(pid, proot)) return false;
            }
            Path expected = prefix.getParent().resolve("z8/environments").resolve(projectId).resolve("rootfs");
            String[] arguments = small(proc.resolve(pid + "/cmdline")).split(String.valueOf('\0'), -1);
            // Verify the project too: another project's PRoot may have reused a finished PTY's PID.
            for (int index = 1; index + 1 < arguments.length; index++) {
                if ("-r".equals(arguments[index])) {
                    Path rootfs = Paths.get(arguments[index + 1]);
                    return rootfs.isAbsolute() && Files.isSameFile(rootfs, expected);
                }
            }
            return false;
        }
        private boolean mapsExecutable(int pid, Path expected) throws IOException {
            for (String line : small(proc.resolve(pid + "/maps")).split("\n")) {
                String[] fields = line.trim().split("\\s+", 6);
                if (fields.length != 6 || fields[1].length() != 4 || fields[1].charAt(2) != 'x'
                        || !fields[5].startsWith("/") || fields[5].endsWith(" (deleted)")) continue;
                Path mapped = Paths.get(fields[5]);
                if (Files.isSameFile(mapped, expected)) return true;
            }
            return false;
        }
        @Override public boolean isPreparationShell(int pid, String marker, String script) throws IOException {
            if (!Files.isSameFile(proc.resolve(pid + "/exe"), Paths.get("/system/bin/sh"))) return false;
            String[] arguments = small(proc.resolve(pid + "/cmdline")).split(String.valueOf('\0'), -1);
            return arguments.length >= 5 && "-c".equals(arguments[1]) && script.equals(arguments[2])
                && marker.equals(arguments[3]);
        }
        @Override public void quit(int pid) throws Exception {
            try { Os.kill(pid, OsConstants.SIGQUIT); }
            catch (ErrnoException error) { if (error.errno != OsConstants.ESRCH) throw preserved(Z8Text.text("Could not send a stop signal to the project.", "프로젝트 종료 신호를 보내지 못했습니다.")); }
        }
        @Override public long now() { return SystemClock.elapsedRealtime(); }
        @Override public void pause() throws InterruptedException { Thread.sleep(100); }
    }

    static ProcessRecord parse(int expectedPid, String stat, String status) throws IOException {
        try {
            int open = stat.indexOf('('), close = stat.lastIndexOf(')');
            if (open < 1 || close < open || Integer.parseInt(stat.substring(0, open).trim()) != expectedPid) throw new IllegalArgumentException();
            String[] fields = stat.substring(close + 1).trim().split("\\s+");
            if (fields.length < 20 || fields[0].length() != 1) throw new IllegalArgumentException();
            int parent = Integer.parseInt(fields[1]); long started = Long.parseLong(fields[19]);
            int uid = -1, tracer = -1;
            for (String line : status.split("\n")) {
                if (line.startsWith("Uid:")) uid = Integer.parseInt(line.substring(4).trim().split("\\s+")[0]);
                if (line.startsWith("TracerPid:")) tracer = Integer.parseInt(line.substring(10).trim());
            }
            if (uid < 0 || tracer < 0 || started < 0 || parent < 0) throw new IllegalArgumentException();
            return new ProcessRecord(expectedPid, uid, parent, tracer, started, fields[0].charAt(0));
        } catch (RuntimeException invalid) { throw preserved(Z8Text.text("Could not verify the process identity.", "프로세스 식별 정보를 확인하지 못했습니다.")); }
    }

    private static String small(Path path) throws IOException {
        try (InputStream input = Files.newInputStream(path); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096]; int count;
            while ((count = input.read(buffer)) != -1) {
                if (output.size() + count > 65536) throw new IOException("Process status exceeds limit");
                output.write(buffer, 0, count);
            }
            return output.toString(StandardCharsets.UTF_8.name());
        }
    }
}
