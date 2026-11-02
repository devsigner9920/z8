package com.termux.app;

import android.content.Context;
import android.os.SystemClock;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

/** Service-owned installer process with identity capture and verified PRoot cleanup. */
final class Z8PreparationProcess implements AutoCloseable {
    static final String WRAPPER = "printf '%s %s\\n' \"$0\" \"$$\"; IFS= read -r z8_ack || exit 125; "
        + "[ \"$z8_ack\" = \"$0\" ] || exit 125; exec \"$@\"";
    private static final Map<String, Z8PreparationProcess> OUTSTANDING = new HashMap<>();
    private static final ExecutorService READERS = Executors.newCachedThreadPool(task -> {
        Thread thread = new Thread(task, "z8-setup-handshake"); thread.setDaemon(true); return thread;
    });
    private static final ScheduledExecutorService OBSERVER = Executors.newSingleThreadScheduledExecutor(task -> {
        Thread thread = new Thread(task, "z8-setup-processes"); thread.setDaemon(true); return thread;
    });

    private final String projectId;
    private final Process process;
    private final InputStream output;
    private Z8ProjectProcesses.PreparationTarget target;
    private ScheduledFuture<?> observation;
    private boolean acknowledged, closed;
    private volatile boolean closeAttempted;
    private volatile Exception observationFailure;

    private Z8PreparationProcess(String projectId, Process process) {
        this.projectId = projectId; this.process = process; output = process.getInputStream();
    }

    /** All arguments remain argv data. No project path or command text is interpolated into sh. */
    static synchronized Z8PreparationProcess start(Context context, String projectId, List<String> argv,
                                                    File directory, Map<String, String> environment) throws IOException {
        if (argv == null || argv.isEmpty() || projectId == null) throw new IOException(Z8Text.text("Initial setup launch information is missing.", "초기 설치 실행 정보가 없습니다."));
        List<Z8PreparationProcess> previous;
        synchronized (OUTSTANDING) { previous = new ArrayList<>(OUTSTANDING.values()); }
        for (Z8PreparationProcess pending : previous) {
            if (!pending.closeAttempted) throw new IOException(Z8Text.text("Another initial setup process is still running.", "다른 초기 설치 프로세스가 아직 실행 중입니다."));
            pending.close(); // Any failed cleanup blocks the whole serial installation queue.
        }
        String marker = "z8-setup-" + UUID.randomUUID();
        List<String> command = new ArrayList<>();
        command.add("/system/bin/sh"); command.add("-c"); command.add(WRAPPER); command.add(marker); command.addAll(argv);
        ProcessBuilder builder = new ProcessBuilder(command).directory(directory).redirectErrorStream(true);
        builder.environment().clear(); builder.environment().putAll(environment);
        Z8PreparationProcess child;
        synchronized (Z8RuntimeLauncher.EXECUTION_LOCK) { child = new Z8PreparationProcess(projectId, builder.start()); }
        synchronized (OUTSTANDING) { OUTSTANDING.put(projectId, child); }
        Future<Integer> handshake = READERS.submit(() -> readHandshake(child.output, marker));
        try {
            int pid = handshake.get(5, TimeUnit.SECONDS);
            child.target = Z8ProjectProcesses.capturePreparation(pid, projectId, marker, WRAPPER);
            child.observation = OBSERVER.scheduleWithFixedDelay(() -> {
                try { Z8ProjectProcesses.observePreparation(child.target); }
                catch (Exception error) { child.observationFailure = error; }
            }, 0, 250, TimeUnit.MILLISECONDS);
            // Set this before writing: a partial write/close failure must assume
            // PRoot could have begun. Only verified SIGQUIT cleanup is then valid.
            child.acknowledged = true;
            child.process.getOutputStream().write((marker + "\n").getBytes(StandardCharsets.UTF_8));
            child.process.getOutputStream().flush();
            child.process.getOutputStream().close();
            return child;
        } catch (Exception error) {
            if (error instanceof InterruptedException) Thread.currentThread().interrupt();
            IOException failure = new IOException(Z8Text.text("Could not start the initial setup process.", "초기 설치 프로세스를 시작하지 못했습니다."), error);
            try { child.close(); } catch (IOException cleanup) { failure.addSuppressed(cleanup); }
            throw failure;
        } finally { handshake.cancel(true); }
    }

    /** Byte-wise framing consumes only the handshake, never the first installer output. */
    static int readHandshake(InputStream input, String marker) throws IOException {
        ByteArrayOutputStream line = new ByteArrayOutputStream();
        while (line.size() < 160) {
            int value = input.read();
            if (value < 0) throw new IOException(Z8Text.text("The initial setup process exited before startup.", "초기 설치 프로세스가 시작 전에 종료되었습니다."));
            if (value == '\n') {
                String text = line.toString(StandardCharsets.UTF_8.name());
                String prefix = marker + " ";
                if (!text.startsWith(prefix)) throw new IOException(Z8Text.text("Could not verify the initial setup process response.", "초기 설치 프로세스의 응답을 확인하지 못했습니다."));
                String pid = text.substring(prefix.length());
                if (!pid.matches("[1-9][0-9]{0,9}")) throw new IOException(Z8Text.text("Invalid installation process ID.", "잘못된 설치 프로세스 ID입니다."));
                try { return Integer.parseInt(pid); }
                catch (NumberFormatException invalid) { throw new IOException(Z8Text.text("Invalid installation process ID.", "잘못된 설치 프로세스 ID입니다."), invalid); }
            }
            line.write(value);
        }
        throw new IOException(Z8Text.text("The initial setup process response is too large.", "초기 설치 프로세스 응답이 너무 큽니다."));
    }

    InputStream output() { return output; }
    boolean waitFor(long timeout, TimeUnit unit) throws InterruptedException { return process.waitFor(timeout, unit); }
    int exitValue() { return process.exitValue(); }

    @Override public synchronized void close() throws IOException {
        if (closed) return;
        closeAttempted = true;
        boolean interrupted = Thread.interrupted();
        if (observation != null) observation.cancel(false);
        try {
            if (acknowledged) {
                if (target == null) throw new IOException(Z8Text.text("The installation process identity is missing, so its exit could not be verified.", "설치 프로세스의 식별 정보가 없어 종료를 확인하지 못했습니다."));
                try { Z8ProjectProcesses.stopPreparation(target); }
                catch (Exception failure) {
                    IOException error = new IOException(Z8Text.text("Could not verify that initial setup stopped. Files have been preserved; a new installation will not start.", "초기 설치 종료를 확인하지 못했습니다. 파일을 보존했으며 새 설치를 시작하지 않습니다."), failure);
                    if (observationFailure != null) error.addSuppressed(observationFailure);
                    throw error;
                } finally { interrupted |= Thread.interrupted(); }
            } else {
                // The fixed wrapper has not received its acknowledgement, so it
                // cannot have exec'd PRoot or started any guest children. This is
                // the only place ordinary Process.destroy() is safe.
                process.destroy();
            }
            long deadline = SystemClock.elapsedRealtime() + 3000;
            boolean exited = false;
            while (!exited && SystemClock.elapsedRealtime() < deadline) {
                try { exited = process.waitFor(100, TimeUnit.MILLISECONDS); }
                catch (InterruptedException stopped) { interrupted = true; }
            }
            if (!exited) throw new IOException(Z8Text.text("Could not verify that the initial setup launcher stopped. A new installation will not start.", "초기 설치 실행기의 종료를 확인하지 못했습니다. 새 설치를 시작하지 않습니다."));
            closed = true;
            synchronized (OUTSTANDING) { if (OUTSTANDING.get(projectId) == this) OUTSTANDING.remove(projectId); }
            try { output.close(); } catch (IOException ignored) { }
            try { process.getOutputStream().close(); } catch (IOException ignored) { }
        } finally { if (interrupted) Thread.currentThread().interrupt(); }
    }
}
