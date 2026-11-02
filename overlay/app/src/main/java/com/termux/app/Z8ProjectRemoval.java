package com.termux.app;

import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import com.termux.terminal.TerminalSession;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Stop this project's PTYs before touching its files. Independent of Activity lifetime. */
public final class Z8ProjectRemoval {
    public interface Result { void complete(String error); }
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final ExecutorService IO = Executors.newSingleThreadExecutor();
    private static final Set<String> ACTIVE = ConcurrentHashMap.newKeySet();
    private static final Map<TerminalSession, String> STOPPING = new ConcurrentHashMap<>();
    private static final Set<TermuxService> STOPPING_ALL = ConcurrentHashMap.newKeySet();
    private static volatile long revision;
    private Z8ProjectRemoval() {}
    public static boolean isDeleting(String id) { return id != null && ACTIVE.contains(id); }
    public static boolean hasWork() { return !ACTIVE.isEmpty() || !STOPPING.isEmpty() || !STOPPING_ALL.isEmpty(); }
    public static boolean isStopping(TerminalSession terminal) { return terminal != null && STOPPING.containsKey(terminal); }
    /** Upstream auto-close/Enter must not discard the evidence of an unverified stop. */
    public static boolean protects(TerminalSession terminal) {
        if (terminal == null) return false;
        Z8SessionOrigin origin = Z8SessionOrigin.of(terminal);
        return isStopping(terminal) || Z8ProjectProcesses.hasUnverified(terminal)
            || origin != null && isDeleting(origin.projectId);
    }
    public static long revision() { return revision; }

    public static void begin(TermuxService service, String id, Result result) {
        if (Looper.myLooper() != Looper.getMainLooper()) throw new IllegalStateException("Removal must start on the main thread");
        if (service == null || service.wantsToStop()) { result.complete(Z8Text.text("Reconnect to the runtime service.", "실행 서비스를 다시 연결해 주세요.")); return; }
        if (service.z8IsStopRequested()) { result.complete(Z8Text.text("Checking that the app's terminals have stopped.", "앱의 터미널 종료를 확인하는 중입니다.")); return; }
        if (Z8GuestSessionLauncher.hasPending(service)) { result.complete(Z8Text.text("Wait for environment setup to finish, then try again.", "환경 준비가 끝난 뒤 다시 시도해 주세요.")); return; }
        if (id != null && STOPPING.containsValue(id)) { result.complete(Z8Text.text("Wait for the terminal shutdown check to finish, then try again.", "터미널 종료 확인이 끝난 뒤 다시 시도해 주세요.")); return; }
        if (id == null || id.isEmpty() || !ACTIVE.add(id)) { result.complete(Z8Text.text("This project is already being deleted.", "이미 삭제 중인 프로젝트입니다.")); return; }
        service.z8AcquireExecution();
        List<TerminalSession> targets = new ArrayList<>();
        for (Z8SessionCatalog.Entry entry : Z8SessionCatalog.snapshot(service, null))
            if (id.equals(entry.projectId)) targets.add(entry.session);
        List<Z8ProjectProcesses.Target> processes = new ArrayList<>();
        for (TerminalSession terminal : targets) processes.add(Z8ProjectProcesses.capture(terminal));
        IO.execute(() -> {
            try {
                Z8ProjectProcesses.stopAndVerify(processes, service::wantsToStop);
                MAIN.post(() -> awaitExit(service, id, targets, SystemClock.elapsedRealtime() + 10000, result));
            } catch (Exception failure) {
                String detail = failure.getMessage();
                MAIN.post(() -> finish(service, id, detail == null
                    ? Z8Text.text("Could not confirm that the project stopped. Your files were kept. Try again.", "프로젝트 종료를 확인하지 못해 파일을 보존했습니다. 다시 시도해 주세요.") : detail, result));
            }
        });
    }

    /** End a single PTY using the same tracee verification as project removal. */
    public static void stopSession(TermuxService service, TerminalSession terminal, Result result) {
        if (Looper.myLooper() != Looper.getMainLooper()) throw new IllegalStateException("Session stop must start on the main thread");
        if (service == null || service.wantsToStop()) { result.complete(Z8Text.text("Reconnect to the runtime service.", "실행 서비스를 다시 연결해 주세요.")); return; }
        if (service.z8IsStopRequested()) { result.complete(Z8Text.text("Checking that the app's terminals have stopped.", "앱의 터미널 종료를 확인하는 중입니다.")); return; }
        if (!Z8SessionCatalog.contains(service, terminal)) { result.complete(Z8Text.text("This terminal has already been removed.", "이미 제거된 터미널입니다.")); return; }
        Z8SessionOrigin origin = Z8SessionOrigin.of(terminal);
        String id = origin == null || origin.projectId == null ? "" : origin.projectId;
        if (isDeleting(id)) { result.complete(Z8Text.text("Deleting the project.", "프로젝트를 삭제하는 중입니다.")); return; }
        if (STOPPING.putIfAbsent(terminal, id) != null) { result.complete(Z8Text.text("Checking that the terminal has stopped.", "터미널 종료를 확인하는 중입니다.")); return; }
        service.z8AcquireExecution();
        List<Z8ProjectProcesses.Target> processes = java.util.Collections.singletonList(Z8ProjectProcesses.capture(terminal));
        IO.execute(() -> {
            try {
                Z8ProjectProcesses.stopAndVerify(processes, service::wantsToStop);
                MAIN.post(() -> awaitSessionExit(service, terminal, SystemClock.elapsedRealtime() + 10000, result));
            } catch (Exception failure) {
                String detail = failure.getMessage();
                MAIN.post(() -> finishSession(service, terminal, detail == null
                    ? Z8Text.text("Could not confirm that the terminal stopped. Try again.", "터미널 종료를 확인하지 못했습니다. 다시 시도해 주세요.") : detail, result));
            }
        });
    }

    /** Explicit notification Stop: verify every PTY, remove wrappers, never delete files. */
    public static void stopAllSessions(TermuxService service, Result result) {
        if (Looper.myLooper() != Looper.getMainLooper()) throw new IllegalStateException("Service stop must start on the main thread");
        if (service == null || service.wantsToStop()) { result.complete(Z8Text.text("Reconnect to the runtime service.", "실행 서비스를 다시 연결해 주세요.")); return; }
        if (Z8GuestSessionLauncher.hasPending(service)) {
            result.complete(Z8Text.text("Environment setup is in progress. Wait for it to finish, then try stopping again.", "환경 준비가 진행 중입니다. 완료 후 다시 종료해 주세요.")); return;
        }
        if (hasWork() || !STOPPING_ALL.add(service)) {
            result.complete(Z8Text.text("A terminal is stopping or a project is being deleted. Wait for it to finish, then try stopping again.", "터미널 종료 또는 프로젝트 삭제가 진행 중입니다. 완료 후 다시 종료해 주세요.")); return;
        }
        List<TerminalSession> targets = new ArrayList<>();
        List<Z8ProjectProcesses.Target> processes = new ArrayList<>();
        for (Z8SessionCatalog.Entry entry : Z8SessionCatalog.snapshot(service, null)) {
            targets.add(entry.session);
            STOPPING.put(entry.session, entry.projectId == null ? "" : entry.projectId);
            processes.add(Z8ProjectProcesses.capture(entry.session));
        }
        service.z8AcquireExecution();
        IO.execute(() -> {
            try {
                Z8ProjectProcesses.stopAndVerify(processes, service::wantsToStop);
                MAIN.post(() -> awaitAllExits(service, targets, SystemClock.elapsedRealtime() + 10000, result));
            } catch (Exception failure) {
                String detail = failure.getMessage();
                MAIN.post(() -> finishAll(service, targets, detail == null
                    ? Z8Text.text("Could not confirm that the terminal stopped. Try again.", "터미널 종료를 확인하지 못했습니다. 다시 시도해 주세요.") : detail, result));
            }
        });
    }

    private static void awaitAllExits(TermuxService service, List<TerminalSession> targets, long deadline, Result result) {
        if (service.wantsToStop()) {
            finishAll(service, targets, Z8Text.text("The runtime service stopped, so shutdown could not be confirmed.", "실행 서비스가 중단되어 종료를 확인하지 못했습니다."), result); return;
        }
        for (TerminalSession terminal : targets) {
            if (!terminal.isRunning()) continue;
            if (SystemClock.elapsedRealtime() >= deadline) {
                finishAll(service, targets, Z8Text.text("Could not confirm that the terminal stopped. Try again.", "터미널 종료를 확인하지 못했습니다. 다시 시도해 주세요."), result); return;
            }
            MAIN.postDelayed(() -> awaitAllExits(service, targets, deadline, result), 100); return;
        }
        for (TerminalSession terminal : targets)
            if (Z8SessionCatalog.contains(service, terminal)) service.removeTermuxSession(terminal);
        finishAll(service, targets, null, result);
    }

    private static void finishAll(TermuxService service, List<TerminalSession> targets, String error, Result result) {
        for (TerminalSession terminal : targets) STOPPING.remove(terminal);
        STOPPING_ALL.remove(service); revision++;
        try { result.complete(error); }
        finally { service.updateNotification(); }
    }

    private static void awaitSessionExit(TermuxService service, TerminalSession terminal, long deadline, Result result) {
        if (service.wantsToStop()) {
            finishSession(service, terminal, Z8Text.text("The runtime service stopped, so shutdown could not be confirmed.", "실행 서비스가 중단되어 종료를 확인하지 못했습니다."), result); return;
        }
        if (terminal.isRunning()) {
            if (SystemClock.elapsedRealtime() >= deadline) {
                finishSession(service, terminal, Z8Text.text("Could not confirm that the terminal stopped. Try again.", "터미널 종료를 확인하지 못했습니다. 다시 시도해 주세요."), result); return;
            }
            MAIN.postDelayed(() -> awaitSessionExit(service, terminal, deadline, result), 100); return;
        }
        if (Z8SessionCatalog.contains(service, terminal)) service.removeTermuxSession(terminal);
        finishSession(service, terminal, null, result);
    }

    private static void finishSession(TermuxService service, TerminalSession terminal, String error, Result result) {
        STOPPING.remove(terminal); revision++;
        try { result.complete(error); }
        finally { service.updateNotification(); }
    }

    private static void awaitExit(TermuxService service, String id, List<TerminalSession> targets, long deadline, Result result) {
        if (service.wantsToStop()) {
            finish(service, id, Z8Text.text("The runtime service stopped. Your files were kept. Try again.", "실행 서비스가 중단되어 파일을 보존했습니다. 다시 시도해 주세요."), result); return;
        }
        for (TerminalSession terminal : targets) {
            if (!terminal.isRunning()) continue;
            if (SystemClock.elapsedRealtime() >= deadline || service.wantsToStop()) {
                finish(service, id, Z8Text.text("Could not confirm that the terminal stopped. Your files were kept. Try again.", "터미널 종료를 확인하지 못해 파일을 보존했습니다. 다시 시도해 주세요."), result); return;
            }
            MAIN.postDelayed(() -> awaitExit(service, id, targets, deadline, result), 100); return;
        }
        for (TerminalSession terminal : targets)
            if (Z8SessionCatalog.contains(service, terminal)) service.removeTermuxSession(terminal);
        IO.execute(() -> {
            String error = null;
            try {
                if (Thread.currentThread().isInterrupted() || service.wantsToStop())
                    throw new java.io.IOException(Z8Text.text("The runtime service stopped. Your files were kept. Try again.", "실행 서비스가 중단되어 파일을 보존했습니다. 다시 시도해 주세요."));
                Z8Guest.deleteProject(service.getApplicationContext(), id);
                android.content.SharedPreferences navigation = service.getSharedPreferences("z8.terminal-navigation", 0);
                android.content.SharedPreferences.Editor edit = navigation.edit();
                for (String key : new String[]{"project", "local-project", "remote-project"})
                    if (id.equals(navigation.getString(key, null))) edit.remove(key);
                edit.apply();
                service.getSharedPreferences("z8.project-preparation", 0).edit().remove(id).apply();
            } catch (Exception failure) {
                error = failure.getMessage() == null ? Z8Text.text("Could not delete the project. Try again.", "프로젝트를 삭제하지 못했습니다. 다시 시도해 주세요.") : failure.getMessage();
            }
            final String message = error;
            MAIN.post(() -> finish(service, id, message, result));
        });
    }

    private static void finish(TermuxService service, String id, String error, Result result) {
        ACTIVE.remove(id); revision++;
        try { result.complete(error); }
        finally { service.updateNotification(); }
    }
}
