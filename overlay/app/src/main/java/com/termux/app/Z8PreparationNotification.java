package com.termux.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.util.Log;

import com.termux.R;

import java.lang.ref.WeakReference;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

/** Installation is owned by the service, including its notification and temporary CPU lock. */
public final class Z8PreparationNotification {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final String RESULT_CHANNEL = "z8_project_preparation";
    private static final int RESULT_ID = 4204;
    private static final long UPDATE_INTERVAL_MS = 1000;
    private static final long WAKE_TIMEOUT_MS = 31 * 60 * 1000L;
    private static final long WAKE_RENEW_MS = 15 * 60 * 1000L;
    private static volatile Owner active;

    private static final class Progress {
        final int percent;
        final String stage, message;
        Progress(String stage, int percent, String message) {
            this.stage = stage;
            this.percent = "tools".equals(stage) || percent < 0 ? -1 : Math.min(100, percent);
            this.message = label(message, Z8Text.text("Preparing project environment", "프로젝트 환경 준비"));
        }
    }

    private static final class Entry {
        final String projectId, name;
        Progress progress = new Progress("bootstrap", -1, Z8Text.text("Preparing runtime", "실행 기반 준비"));
        Entry(String projectId, String name) {
            this.projectId = projectId;
            this.name = label(name, Z8Text.text("Project", "프로젝트"));
        }
    }

    private static final class Snapshot {
        final String projectId, name, text;
        final int percent;
        Snapshot(Entry entry, int waiting) {
            projectId = entry.projectId;
            name = entry.name;
            percent = entry.progress.percent;
            text = entry.progress.message + (percent < 0 ? "" : " · " + percent + "%")
                + (waiting == 0 ? "" : " · " + waiting + Z8Text.text(" project(s) waiting", "개 프로젝트 대기"));
        }
    }

    private static final class Owner {
        final WeakReference<TermuxService> service;
        // Entries are main-thread-only; worker progress has a bounded, coalesced mailbox.
        final Map<String, Entry> entries = new LinkedHashMap<>();
        final Map<String, Progress> updates = new ConcurrentHashMap<>();
        final AtomicBoolean updateScheduled = new AtomicBoolean();
        volatile Snapshot snapshot;
        PowerManager.WakeLock wakeLock;
        final Runnable refresh = () -> flush(this);
        final Runnable renew = () -> renewWakeLock(this);
        Owner(TermuxService service) { this.service = new WeakReference<>(service); }
    }

    private Z8PreparationNotification() {}

    private static void mainThread() {
        if (Looper.myLooper() != Looper.getMainLooper())
            throw new IllegalStateException("Preparation ownership stays on the main thread");
    }

    /** Call only for accepted first-install/recovery work, never for an ordinary new terminal. */
    public static void begin(TermuxService service, String requestId, String projectId, String name) {
        mainThread();
        Owner owner = active;
        if (owner != null && owner.service.get() != service) release(owner);
        if (active == null) active = new Owner(service);
        owner = active;
        owner.entries.put(requestId, new Entry(projectId, name));
        NotificationManager notifications = service.getSystemService(NotificationManager.class);
        if (notifications != null) notifications.cancel(projectId, RESULT_ID);
        publish(owner);
        if (owner.wakeLock == null) renewWakeLock(owner);
        service.updateNotification();
    }

    /** Worker-safe: at most one pending UI callback and one latest progress value per request. */
    public static void progress(TermuxService service, String requestId, String stage, int percent, String message) {
        Owner owner = active;
        if (owner == null || owner.service.get() != service) return;
        owner.updates.put(requestId, new Progress(stage, percent, message));
        if (owner.updateScheduled.compareAndSet(false, true)) MAIN.postDelayed(owner.refresh, UPDATE_INTERVAL_MS);
    }

    private static void flush(Owner owner) {
        owner.updateScheduled.set(false);
        if (active != owner) return;
        for (Map.Entry<String, Progress> update : owner.updates.entrySet()) {
            if (!owner.updates.remove(update.getKey(), update.getValue())) continue;
            Entry entry = owner.entries.get(update.getKey());
            if (entry != null) entry.progress = update.getValue();
        }
        publish(owner);
        TermuxService service = owner.service.get();
        if (service != null) service.updateNotification();
    }

    public static void finish(TermuxService service, String requestId, boolean success, String detail) {
        finish(service, requestId, success, false);
    }

    /** A paused download is actionable, but is not an installation failure. */
    public static void waiting(TermuxService service, String requestId) {
        finish(service, requestId, false, true);
    }

    private static void finish(TermuxService service, String requestId, boolean success, boolean waiting) {
        mainThread();
        Owner owner = active;
        if (owner == null || owner.service.get() != service) return;
        Entry entry = owner.entries.remove(requestId);
        if (entry == null) return;
        owner.updates.remove(requestId);
        if (owner.entries.isEmpty()) release(owner);
        else publish(owner);
        postResult(service, entry, success, waiting);
        service.updateNotification();
    }

    /** Service destruction/cancellation never leaves a CPU lock or a delayed notification callback. */
    public static void releaseOwner(TermuxService service) {
        mainThread();
        Owner owner = active;
        if (owner != null && owner.service.get() == service) release(owner);
    }

    private static void release(Owner owner) {
        if (active == owner) active = null;
        MAIN.removeCallbacks(owner.refresh);
        MAIN.removeCallbacks(owner.renew);
        owner.updates.clear();
        owner.entries.clear();
        owner.snapshot = null;
        if (owner.wakeLock != null) {
            if (owner.wakeLock.isHeld()) owner.wakeLock.release();
            owner.wakeLock = null;
        }
    }

    private static void publish(Owner owner) {
        owner.snapshot = owner.entries.isEmpty() ? null
            : new Snapshot(owner.entries.values().iterator().next(), owner.entries.size() - 1);
    }

    private static void renewWakeLock(Owner owner) {
        if (active != owner || owner.entries.isEmpty()) return;
        TermuxService service = owner.service.get();
        if (service == null || service.wantsToStop()) { release(owner); return; }
        try {
            if (owner.wakeLock == null) {
                PowerManager power = service.getSystemService(PowerManager.class);
                if (power == null) return;
                owner.wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "z8:project-preparation");
                owner.wakeLock.setReferenceCounted(false);
            }
            // A timeout bounds retention if lifecycle cleanup unexpectedly fails.
            owner.wakeLock.acquire(WAKE_TIMEOUT_MS);
            MAIN.removeCallbacks(owner.renew);
            MAIN.postDelayed(owner.renew, WAKE_RENEW_MS);
        } catch (SecurityException unavailable) {
            Log.w("z8", "Preparation CPU lock unavailable");
        }
    }

    /** Override the primary service card; false preserves the normal terminal notification. */
    public static boolean decorate(Notification.Builder builder, TermuxService service) {
        Owner owner = active;
        Snapshot snapshot = owner != null && owner.service.get() == service ? owner.snapshot : null;
        if (snapshot == null) return false;
        boolean initial = Z8InitialSetup.NOTIFICATION_ID.equals(snapshot.projectId);
        String explanation = Z8Text.text("First-time setup may take a while. Preparation continues after you leave the app.", "처음 준비할 때는 시간이 걸릴 수 있습니다. 앱을 나가도 준비를 계속합니다.");
        builder.setContentTitle(initial ? Z8Text.text("z8 · Initial setup", "z8 · 처음 준비") : snapshot.name + Z8Text.text(" · Preparing first launch", " · 첫 실행 준비"))
            .setContentText(snapshot.text)
            .setStyle(new Notification.BigTextStyle().bigText(snapshot.text + "\n" + explanation))
            .setContentIntent(projectIntent(service, snapshot.projectId))
            .setProgress(100, Math.max(0, snapshot.percent), snapshot.percent < 0)
            .setCategory(Notification.CATEGORY_PROGRESS)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
            .setOngoing(true);
        return true;
    }

    private static PendingIntent projectIntent(Context context, String projectId) {
        boolean initial = Z8InitialSetup.NOTIFICATION_ID.equals(projectId);
        Intent intent = new Intent(context, initial ? Z8SetupActivity.class : TermuxActivity.class)
            .setData(new Uri.Builder().scheme("z8").authority("preparation").appendPath(projectId).build())
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        if (!initial) intent.putExtra(Z8WorkspaceActivity.EXTRA_FOCUS_PROJECT_ID, projectId);
        return PendingIntent.getActivity(context, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    private static void postResult(Context context, Entry entry, boolean success, boolean waiting) {
        NotificationManager notifications = context.getSystemService(NotificationManager.class);
        if (notifications == null || !notifications.areNotificationsEnabled()) return;
        notifications.createNotificationChannel(new NotificationChannel(RESULT_CHANNEL,
            Z8Text.text("Development environment setup", "개발 환경 준비"), NotificationManager.IMPORTANCE_LOW));
        boolean initial = Z8InitialSetup.NOTIFICATION_ID.equals(entry.projectId);
        Notification.Builder builder = new Notification.Builder(context, RESULT_CHANNEL)
            .setSmallIcon(R.drawable.ic_service_notification)
            .setContentTitle((initial ? "z8" : entry.name) + (waiting ? Z8Text.text(" · Waiting for network", " · 네트워크 대기") : success ? Z8Text.text(" · Ready", " · 준비 완료") : Z8Text.text(" · Setup incomplete", " · 준비를 완료하지 못했어요")))
            .setContentText(waiting ? Z8Text.text("Download paused. Tap to check the connection and resume setup.", "다운로드를 멈췄어요. 눌러서 연결을 확인하고 이어서 준비하세요.")
                : success ? initial ? Z8Text.text("Developer tools are ready. Tap to create your first project.", "개발 도구를 준비했어요. 눌러서 첫 프로젝트를 만드세요.")
                    : Z8Text.text("The terminal is ready. Tap to open the project.", "터미널을 사용할 수 있습니다. 눌러서 프로젝트를 여세요.")
                : Z8Text.text("Tap to check the remaining setup steps.", "눌러서 남은 준비 단계를 확인하세요."))
            .setContentIntent(projectIntent(context, entry.projectId))
            .setOnlyAlertOnce(true).setAutoCancel(true)
            .setCategory(success || waiting ? Notification.CATEGORY_STATUS : Notification.CATEGORY_ERROR);
        // The installer log can contain paths or command output; never place it on the lock screen.
        try { notifications.notify(entry.projectId, RESULT_ID, builder.build()); }
        catch (SecurityException ignored) { /* Notification permission can change during setup. */ }
    }

    private static String label(String value, String fallback) {
        if (value == null || value.trim().isEmpty()) return fallback;
        String clean = value.replaceAll("[\\p{Cntrl}]", " ").trim();
        return clean.length() <= 120 ? clean : clean.substring(0, 120);
    }
}
