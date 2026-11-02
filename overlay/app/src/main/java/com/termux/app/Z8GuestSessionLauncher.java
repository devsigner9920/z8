package com.termux.app;

import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;

import com.termux.shared.termux.shell.command.runner.terminal.TermuxSession;

import java.lang.ref.WeakReference;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Process-local launch tickets. A live service owns execution; Activities only observe it. */
public final class Z8GuestSessionLauncher {
    private static final String REQUEST = "dev.devsigner.z8.GUEST_REQUEST";
    private static final String SAVED = "z8_pending_guest_intent";
    private static final int MAX_SESSIONS = 8;
    private static final int MAX_TICKETS = 256;
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final Map<String, Ticket> TICKETS = new LinkedHashMap<>();
    private static volatile Generation active;
    private static final String PREPARATION_PREFS = "z8.project-preparation";

    public static final class Preparation {
        public final String stage, message;
        public final int percent;
        public final boolean failed;
        public final boolean resuming;
        Preparation(String stage, int percent, String message, boolean failed) {
            this(stage, percent, message, failed, false);
        }
        Preparation(String stage, int percent, String message, boolean failed, boolean resuming) {
            this.stage = stage; this.percent = percent; this.message = message; this.failed = failed;
            this.resuming = resuming;
        }
        @Override public String toString() { return stage + percent + message + failed + resuming; }
    }

    private enum Phase { PREPARED, QUEUED, CREATED, FAILED, CANCELLED }
    private static final class Ticket {
        final String id = UUID.randomUUID().toString();
        Generation owner;
        Phase phase = Phase.PREPARED;
        String projectId;
        String action;
        boolean preparesShell;
        boolean autoPreparation;
        boolean recovering;
        volatile Preparation preparation;
        Ticket(Generation owner) { this.owner = owner; }
    }
    private static final class Generation {
        final WeakReference<TermuxService> service;
        final ExecutorService worker = Executors.newSingleThreadExecutor();
        WeakReference<TermuxActivity> observer = new WeakReference<>(null);
        TermuxSession delivery;
        final Map<String, TermuxSession> preparingShells = new LinkedHashMap<>();
        String failure;
        boolean alive = true;
        volatile boolean pending;
        boolean recoveryChecked;
        Generation(TermuxService service) { this.service = new WeakReference<>(service); }
    }

    private Z8GuestSessionLauncher() {}
    private static void mainThread() {
        if (Looper.myLooper() != Looper.getMainLooper()) throw new IllegalStateException("Launch state must stay on the main thread");
    }
    private static boolean alive(Generation generation, TermuxService service) {
        return generation != null && generation == active && generation.alive
            && generation.service.get() == service && service != null && !service.wantsToStop();
    }

    public static void start(TermuxService service) {
        mainThread();
        if (active != null) invalidate(active);
        active = new Generation(service);
        // A cold-launch Intent may be prepared before Android creates the service.
        for (Ticket ticket : TICKETS.values())
            if (ticket.owner == null && ticket.phase == Phase.PREPARED) ticket.owner = active;
    }

    public static void stop(TermuxService service) {
        mainThread();
        if (active != null && active.service.get() == service) {
            invalidate(active); active = null;
        }
    }

    private static void invalidate(Generation generation) {
        generation.alive = false;
        generation.pending = false;
        generation.observer.clear(); generation.delivery = null; generation.failure = null;
        generation.preparingShells.clear();
        TermuxService service = generation.service.get();
        if (service != null) Z8PreparationNotification.releaseOwner(service);
        generation.worker.shutdownNow();
        for (Ticket ticket : TICKETS.values())
            if (ticket.owner == generation && (ticket.phase == Phase.PREPARED || ticket.phase == Phase.QUEUED))
                ticket.phase = Phase.CANCELLED;
    }

    private static Ticket newTicket(Generation owner) {
        // Expired tickets may be forgotten: unknown restored IDs are refused, never replayed.
        Iterator<Ticket> iterator = TICKETS.values().iterator();
        while (TICKETS.size() >= MAX_TICKETS && iterator.hasNext()) {
            Ticket previous = iterator.next();
            if (previous.phase != Phase.PREPARED && previous.phase != Phase.QUEUED) iterator.remove();
        }
        if (TICKETS.size() >= MAX_TICKETS) return null;
        Ticket ticket = new Ticket(owner); TICKETS.put(ticket.id, ticket); return ticket;
    }

    public static String newRequest(TermuxService service) {
        mainThread();
        if (!alive(active, service) || service.z8IsStopRequested()) return null;
        Ticket ticket = newTicket(active);
        return ticket == null ? null : ticket.id;
    }

    /**
     * Whether this live service has accepted work that has not completed yet.
     * PREPARED tickets are excluded: bootstrap may fail or be abandoned without
     * calling request(), so they must not permanently disable creation controls.
     * Callers should debounce taps separately during that pre-acceptance gap.
     */
    public static boolean hasPending(TermuxService service) {
        mainThread();
        if (Z8InitialSetup.hasWork(service)) return true;
        if (!alive(active, service)) return false;
        for (Ticket ticket : TICKETS.values())
            if (ticket.owner == active && ticket.phase == Phase.QUEUED) return true;
        return false;
    }

    /** The foreground service can consult this without touching main-thread ticket state. */
    public static boolean hasServiceWork(TermuxService service) {
        Generation generation = active;
        return Z8InitialSetup.hasWork(service)
            || generation != null && generation.service.get() == service && generation.pending;
    }

    private static void updatePending(Generation generation) {
        boolean pending = false;
        for (Ticket item : TICKETS.values())
            if (item.owner == generation && item.phase == Phase.QUEUED) pending = true;
        generation.pending = pending;
        TermuxService service = generation.service.get();
        if (service != null && generation.alive) service.updateNotification();
    }

    public static Preparation preparation(android.content.Context context, String projectId) {
        mainThread();
        if (projectId == null || projectId.isEmpty()) return null;
        Ticket latest = null;
        for (Ticket ticket : TICKETS.values()) {
            if (ticket.owner != active || !projectId.equals(ticket.projectId) || !ticket.autoPreparation) continue;
            if (ticket.phase == Phase.CREATED || ticket.phase == Phase.QUEUED || ticket.phase == Phase.FAILED) latest = ticket;
        }
        if (latest != null) {
            // A ready project opens another shell without showing first-install copy.
            // Its short-lived durable marker is active work, not an interruption.
            if (latest.phase == Phase.CREATED || latest.phase == Phase.QUEUED && !latest.preparesShell) return null;
            return latest.preparation;
        }
        String interrupted = context.getSharedPreferences(PREPARATION_PREFS, android.content.Context.MODE_PRIVATE).getString(projectId, null);
        return interrupted == null ? null : new Preparation("error", -1,
            Z8Text.text("Setup was interrupted. Retry to keep completed steps and install the rest.", "준비가 중단되었습니다. 다시 시도하면 완료된 단계는 유지하고 나머지를 설치합니다."), true);
    }

    /** Only an unfinished installer may resume. CLI commands and old launch Intents never replay. */
    private static void resumeInterrupted(TermuxService service, Generation generation) {
        if (generation.recoveryChecked) return;
        generation.recoveryChecked = true;
        android.content.SharedPreferences journal = service.getSharedPreferences(PREPARATION_PREFS,
            android.content.Context.MODE_PRIVATE);
        for (Map.Entry<String, ?> entry : journal.getAll().entrySet()) {
            Object value = entry.getValue();
            if (!(value instanceof String) || !("pending".equals(value)
                    || ((String) value).startsWith("running:"))) continue;
            String projectId = entry.getKey();
            boolean accepted = false;
            for (Ticket ticket : TICKETS.values())
                if (ticket.owner == generation && projectId.equals(ticket.projectId)
                        && ticket.phase == Phase.QUEUED) accepted = true;
            if (accepted || Z8ProjectRemoval.isDeleting(projectId)) continue;
            try {
                // Deleted or invalid projects must not be recreated by recovery.
                Z8Projects.Project project = new Z8Projects(service).open(projectId);
                Ticket ticket = newTicket(generation);
                if (ticket == null) return;
                ticket.recovering = true;
                request(service, ticket.id, projectId, null, project.name, null);
            } catch (java.io.IOException invalidProject) {
                journal.edit().remove(projectId).apply();
            }
        }
    }

    private static boolean guest(Intent intent) {
        return intent != null && (intent.getBooleanExtra(Z8Guest.EXTRA_GUEST_SESSION, false)
            || intent.getStringExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID) != null);
    }

    /** Call before the Activity binds; a process-recreated saved action is never registered anew. */
    public static void restoreIntent(TermuxActivity activity, Bundle saved) {
        mainThread();
        if (saved != null) {
            Intent pending = saved.getParcelable(SAVED);
            if (isPendingIntent(pending)) activity.setIntent(new Intent(pending));
            else if (guest(activity.getIntent())) activity.setIntent(null);
        } else prepareIntent(activity.getIntent());
    }

    /** Fresh onNewIntent deliveries get a new ticket; only same-process known tickets can be reused. */
    public static void prepareIntent(Intent intent) {
        mainThread();
        if (!guest(intent)) return;
        intent.putExtra(Z8Guest.EXTRA_GUEST_SESSION, true);
        String id = intent.getStringExtra(REQUEST);
        if (id != null) return; // Unknown/stale tickets must not become new actions.
        Ticket ticket = newTicket(active);
        if (ticket != null) intent.putExtra(REQUEST, ticket.id);
    }

    public static void saveIntent(TermuxActivity activity, Bundle saved) {
        mainThread();
        if (isPendingIntent(activity.getIntent())) saved.putParcelable(SAVED, new Intent(activity.getIntent()));
    }

    public static boolean isPendingIntent(Intent intent) {
        mainThread();
        if (!guest(intent)) return false;
        Ticket ticket = TICKETS.get(intent.getStringExtra(REQUEST));
        return ticket != null && ticket.phase == Phase.PREPARED
            && (ticket.owner == null || alive(ticket.owner, ticket.owner.service.get()));
    }

    public static String requestId(Intent intent) {
        return intent == null ? null : intent.getStringExtra(REQUEST);
    }

    public static void forget(TermuxActivity activity) {
        mainThread();
        if (active != null && active.observer.get() == activity) active.observer.clear();
    }

    /** Returns true when pending work or a delivered result owns initial session selection. */
    public static boolean observe(TermuxActivity activity) {
        mainThread();
        TermuxService service = activity.getTermuxService();
        if (!alive(active, service)) return false;
        active.observer = new WeakReference<>(activity);
        if (activity.isVisible() && !service.z8IsStopRequested()) resumeInterrupted(service, active);
        boolean handled = active.delivery != null || active.failure != null;
        deliver(active);
        for (Ticket ticket : TICKETS.values())
            if (ticket.owner == active && ticket.phase == Phase.QUEUED) return true;
        return handled;
    }

    public static void request(TermuxService service, String requestId, String projectId,
                               String directory, String name, String action) {
        mainThread();
        Generation generation = active;
        Ticket ticket = TICKETS.get(requestId);
        if (!alive(generation, service) || ticket == null || ticket.owner != generation || ticket.phase != Phase.PREPARED) return;
        if (service.z8IsStopRequested()) { ticket.phase = Phase.CANCELLED; return; }
        if (Z8ProjectRemoval.isDeleting(projectId)) { ticket.phase = Phase.CANCELLED; return; }
        android.content.Context context = service.getApplicationContext();
        boolean needsProfile = projectId != null && !Z8Guest.standardProfilePrepared(context, projectId);
        ticket.preparesShell = action == null && (needsProfile || ticket.recovering);
        if (action == null && projectId != null) {
            for (Ticket other : TICKETS.values())
                if (other != ticket && other.owner == generation && other.phase == Phase.QUEUED
                        && projectId.equals(other.projectId) && other.autoPreparation && other.preparesShell) {
                    ticket.phase = Phase.CANCELLED; return;
                }
        }
        if (needsProfile && (action == null || "setup-tools".equals(action))) {
            for (Ticket other : TICKETS.values()) {
                if (other != ticket && other.owner == generation && other.phase == Phase.QUEUED
                        && projectId.equals(other.projectId) && (other.preparesShell || "setup-tools".equals(other.action))) {
                    ticket.phase = Phase.CANCELLED; return;
                }
            }
            TermuxSession preparing = generation.preparingShells.get(projectId);
            if (preparing != null && service.getTermuxSessions().contains(preparing)
                    && preparing.getTerminalSession().isRunning()) {
                ticket.phase = Phase.CREATED; generation.delivery = preparing; deliver(generation); return;
            }
        } else if (projectId != null && !needsProfile) generation.preparingShells.remove(projectId);
        // A second setup tap reconnects to its live setup rather than racing apt/installer state.
        boolean setup = projectId != null && action != null && (action.startsWith("setup-") || action.startsWith("hooks-"));
        if (setup) {
            for (Ticket other : TICKETS.values()) {
                if (other != ticket && other.owner == generation && other.phase == Phase.QUEUED
                        && projectId.equals(other.projectId) && action.equals(other.action)) {
                    ticket.phase = Phase.CANCELLED; return;
                }
            }
            for (TermuxSession running : service.getTermuxSessions()) {
                Z8SessionOrigin origin = Z8SessionOrigin.of(running.getTerminalSession());
                if (origin != null && projectId.equals(origin.projectId) && action.equals(origin.action)
                        && running.getTerminalSession().isRunning()) {
                    ticket.phase = Phase.CREATED; generation.delivery = running; deliver(generation); return;
                }
            }
        }
        // Acceptance happens before scheduling. Duplicate callbacks cannot enqueue again.
        ticket.projectId = projectId; ticket.action = action;
        ticket.autoPreparation = action == null;
        if (ticket.autoPreparation) ticket.preparation = new Preparation("bootstrap", -1,
            ticket.recovering ? Z8Text.text("Check completed steps", "완료된 단계 확인") : Z8Text.text("Prepare project", "프로젝트 준비"), false, ticket.recovering);
        ticket.phase = Phase.QUEUED;
        generation.pending = true;
        service.z8AcquireExecution();
        int pending = 0;
        for (Ticket item : TICKETS.values()) if (item.owner == generation && item.phase == Phase.QUEUED) pending++;
        if (service.getTermuxSessionsSize() + pending > MAX_SESSIONS) {
            ticket.phase = Phase.FAILED;
            updatePending(generation);
            String message = Z8Text.text("You can open up to 8 terminals.", "터미널은 최대 8개까지 열 수 있습니다.");
            if (ticket.autoPreparation) ticket.preparation = new Preparation("error", -1, message, true);
            else generation.failure = message;
            deliver(generation); return;
        }
        // Persist acceptance before enqueueing: a second project may wait behind
        // a long install, and must still be recoverable if the process is killed.
        // This single small commit is the durable acceptance boundary; progress
        // and all filesystem/package work remain on the worker.
        if (ticket.preparesShell && !context.getSharedPreferences(PREPARATION_PREFS,
                android.content.Context.MODE_PRIVATE).edit().putString(projectId, "running:queued").commit()) {
            MAIN.post(() -> complete(generation, ticket, null, projectId, name, action,
                Z8Text.text("Could not save setup progress. Check available storage, then retry.", "설치 상태를 저장하지 못했습니다. 저장 공간을 확인한 뒤 다시 시도해 주세요.")));
            return;
        }
        if (ticket.preparesShell)
            Z8PreparationNotification.begin(service, ticket.id, projectId, name);
        generation.worker.execute(() -> {
            try {
                if (ticket.autoPreparation) {
                    if (ticket.preparesShell && !context.getSharedPreferences(PREPARATION_PREFS, android.content.Context.MODE_PRIVATE)
                            .edit().putString(projectId, "running:bootstrap").commit())
                        throw new java.io.IOException(Z8Text.text("Could not save setup progress.", "설치 상태를 저장하지 못했습니다."));
                    final String[] persistedStage = {"bootstrap"};
                    Z8ProjectPreparation.run(context, projectId, (stage, percent, message) -> {
                        if (ticket.preparesShell && !stage.equals(persistedStage[0])) {
                            if (!context.getSharedPreferences(PREPARATION_PREFS, android.content.Context.MODE_PRIVATE)
                                    .edit().putString(projectId, "running:" + stage).commit())
                                throw new IllegalStateException(Z8Text.text("Could not save setup progress.", "설치 상태를 저장하지 못했습니다."));
                            persistedStage[0] = stage;
                        }
                        ticket.preparation = new Preparation(stage, percent, message, false, ticket.recovering);
                        if (ticket.preparesShell)
                            Z8PreparationNotification.progress(service, ticket.id, stage, percent, message);
                    });
                    if (Thread.currentThread().isInterrupted()) throw new InterruptedException();
                    if (ticket.preparesShell && !context.getSharedPreferences(PREPARATION_PREFS, android.content.Context.MODE_PRIVATE).edit().remove(projectId).commit())
                        throw new java.io.IOException(Z8Text.text("Could not save setup completion. Please try again.", "설치 완료 상태를 저장하지 못했습니다. 다시 시도해 주세요."));
                } else Z8Bootstrap.ensure(context, (percent, message) -> {});
                Z8Guest.Launch launch = action == null ? Z8Guest.command(context, projectId, directory)
                    : Z8Guest.actionCommand(context, projectId, directory, action);
                MAIN.post(() -> complete(generation, ticket, launch, projectId, name, action, null));
            } catch (Exception error) {
                // A clean failure waits for an explicit retry. Process death/interruption keeps
                // the running receipt so the next foreground launch can recover it once.
                if (ticket.preparesShell && !(error instanceof InterruptedException)
                        && !Thread.currentThread().isInterrupted())
                    context.getSharedPreferences(PREPARATION_PREFS, android.content.Context.MODE_PRIVATE)
                        .edit().putString(projectId, "failed").commit();
                String message = error.getMessage() == null ? Z8Text.text("Could not prepare the Linux session.", "Linux 세션을 준비하지 못했습니다.") : error.getMessage();
                MAIN.post(() -> complete(generation, ticket, null, projectId, name, action, message));
            }
        });
    }

    private static void complete(Generation generation, Ticket ticket, Z8Guest.Launch launch,
                                 String projectId, String name, String action, String error) {
        mainThread();
        TermuxService service = generation.service.get();
        if (!alive(generation, service) || ticket.phase != Phase.QUEUED) return;
        ticket.phase = Phase.FAILED;
        if (error == null && service.z8IsStopRequested()) error = Z8Text.text("Waiting for the app's terminals to close.", "앱의 터미널 종료를 확인하는 중입니다.");
        if (error == null && service.getTermuxSessionsSize() >= MAX_SESSIONS) error = Z8Text.text("You can open up to 8 terminals.", "터미널은 최대 8개까지 열 수 있습니다.");
        if (error == null) {
            String label = name == null ? Z8Text.text("Project", "프로젝트") : name;
            String sessionName = action == null
                ? Z8SessionCatalog.nextTerminalName(service, projectId)
                : label + " · " + Z8Guest.actionLabel(action);
            TermuxSession session = service.createTermuxSession(launch.executable, launch.arguments, null,
                launch.workingDirectory, false, sessionName);
            if (session == null) error = Z8Text.text("Could not start the Linux session.", "Linux 세션을 시작하지 못했습니다.");
            else {
                Z8SessionOrigin.remember(session.getTerminalSession(), projectId, label, action);
                if (launch.preparesShell || "setup-tools".equals(action)) generation.preparingShells.put(projectId, session);
                // Upstream starts the subprocess lazily on the first size update.
                // Start it even between Activities; the next attached view resizes it.
                session.getTerminalSession().updateSize(80, 24, 0, 0);
                ticket.phase = Phase.CREATED; generation.delivery = session;
            }
        }
        if (error != null) {
            if (ticket.autoPreparation) ticket.preparation = new Preparation("error", -1, error, true);
            else generation.failure = error;
        }
        if (ticket.preparesShell)
            Z8PreparationNotification.finish(service, ticket.id, error == null, error);
        updatePending(generation);
        deliver(generation);
    }

    private static void deliver(Generation generation) {
        TermuxActivity activity = generation.observer.get();
        TermuxService service = generation.service.get();
        if (!alive(generation, service) || activity == null || activity.isDestroyed() || activity.isFinishing()
                || !activity.isVisible() || activity.getTermuxService() != service) return;
        if (generation.delivery != null) {
            TermuxSession session = generation.delivery; generation.delivery = null;
            if (service.getTermuxSessions().contains(session)) {
                activity.getTermuxTerminalSessionClient().setCurrentSession(session.getTerminalSession());
                activity.getTermuxTerminalSessionClient().setCurrentStoredSession();
                activity.getDrawer().closeDrawers();
            }
        }
        if (generation.failure != null) {
            String message = generation.failure; generation.failure = null;
            new AlertDialog.Builder(activity).setTitle(Z8Text.text("Cannot open the Linux session", "Linux 세션을 열 수 없습니다"))
                .setMessage(message).setPositiveButton(android.R.string.ok, null).show();
        }
    }
}
