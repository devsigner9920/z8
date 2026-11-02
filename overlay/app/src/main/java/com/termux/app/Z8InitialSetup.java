package com.termux.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Handler;
import android.os.Looper;
import java.io.IOException;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/** Consent belongs to onboarding; durable preparation belongs to the execution service. */
public final class Z8InitialSetup {
    public static final String NOTIFICATION_ID = "__initial_setup__";
    private static final String PREFS = "z8.initial-setup";
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    // A replacement service cannot overlap an old installer's process cleanup.
    private static final ExecutorService WORKER = Executors.newSingleThreadExecutor();
    private static final Set<Runnable> LISTENERS = new LinkedHashSet<>();
    private static volatile Job active;
    private static volatile State latest;

    public enum Phase { CONSENT, RUNNING, WAITING_NETWORK, FAILED, READY }
    public static final class State {
        public final Phase phase;
        public final String stage, message;
        public final int percent;
        public final boolean allowMetered;
        State(Phase phase, String stage, int percent, String message, boolean allowMetered) {
            this.phase = phase; this.stage = stage; this.percent = percent;
            this.message = message; this.allowMetered = allowMetered;
        }
    }

    private static final class Job {
        final TermuxService service;
        final String id = UUID.randomUUID().toString();
        final boolean allowMetered;
        final Network network;
        final ConnectivityManager connectivity;
        final AtomicBoolean scheduled = new AtomicBoolean();
        volatile Thread thread;
        volatile Z8SetupDownloadProxy proxy;
        volatile State progress;
        volatile boolean abandoned, networkStopped;
        boolean callbackRegistered;
        final ConnectivityManager.NetworkCallback callback = new ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(Network network) {
                if (!Job.this.network.equals(network)) pauseForNetwork(Job.this);
            }
            @Override public void onLost(Network network) {
                if (Job.this.network.equals(network)) pauseForNetwork(Job.this);
            }
            @Override public void onCapabilitiesChanged(Network network, NetworkCapabilities caps) {
                if (Job.this.network.equals(network) && !allowedCapabilities(caps, allowMetered)) pauseForNetwork(Job.this);
            }
        };
        Job(TermuxService service, boolean allowMetered, Network network) {
            this.service = service; this.allowMetered = allowMetered; this.network = network;
            connectivity = service.getSystemService(ConnectivityManager.class);
            progress = new State(Phase.RUNNING, "bootstrap", -1, Z8Text.text("Checking completed setup steps", "완료된 준비 단계 확인"), allowMetered);
        }
    }
    private Z8InitialSetup() {}
    private static void mainThread() {
        if (Looper.myLooper() != Looper.getMainLooper()) throw new IllegalStateException("Setup ownership stays on main thread");
    }
    private static SharedPreferences preferences(Context context) { return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE); }
    public static boolean hasConsent(Context context) { return preferences(context).getBoolean("consent", false); }
    public static boolean isReady(Context context) {
        return "ready".equals(preferences(context).getString("status", "")) && Z8EnvironmentTemplate.isReady(context);
    }
    public static State state(Context context) {
        if (isReady(context)) return new State(Phase.READY, "ready", 100, Z8Text.text("Development environment ready", "개발 환경 준비 완료"), false);
        Job job = active;
        if (job != null && !job.abandoned) return job.progress;
        if (latest != null && latest.phase != Phase.READY) return latest;
        SharedPreferences prefs = preferences(context);
        String status = prefs.getString("status", "");
        boolean metered = prefs.getBoolean("allowMetered", false);
        if ("failed".equals(status)) return new State(Phase.FAILED, "error", -1, Z8Text.text("Retry the remaining installation steps.", "남은 설치 단계를 다시 시도해 주세요."), metered);
        if ("running".equals(status) || "waiting".equals(status))
            return new State(Phase.WAITING_NETWORK, prefs.getString("stage", "bootstrap"), -1,
                Z8Text.text("Check the connection to resume from completed setup steps.", "연결을 확인한 뒤 완료된 단계부터 이어서 준비합니다."), metered);
        return new State(Phase.CONSENT, "", -1, "", false);
    }
    public static void addListener(Runnable listener) { mainThread(); LISTENERS.add(listener); }
    public static void removeListener(Runnable listener) { mainThread(); LISTENERS.remove(listener); }
    private static void changed() { for (Runnable listener : new LinkedHashSet<>(LISTENERS)) listener.run(); }
    public static boolean hasWork(TermuxService service) {
        Job job = active; return job != null && job.service == service && !job.abandoned;
    }
    public static void request(TermuxService service, boolean allowMetered) {
        mainThread();
        if (isReady(service) || active != null || service.wantsToStop() || service.z8IsStopRequested()) return;
        if (!preferences(service).edit().putBoolean("consent", true).putBoolean("allowMetered", allowMetered)
                .putString("status", "running").putString("stage", "bootstrap").commit()) {
            latest = new State(Phase.FAILED, "error", -1, Z8Text.text("Could not save installation consent. Check available storage.", "설치 동의를 저장하지 못했습니다. 저장 공간을 확인해 주세요."), allowMetered);
            changed(); return;
        }
        start(service, allowMetered);
    }
    /** Foreground return resumes accepted installation only, never a terminal or CLI command. */
    public static void resume(TermuxService service) {
        mainThread();
        if (!hasConsent(service) || isReady(service) || active != null || service.wantsToStop() || service.z8IsStopRequested()) return;
        String status = preferences(service).getString("status", "");
        if (!"running".equals(status) && !"waiting".equals(status)) return;
        // Recover a kill between the verified tools receipt and the UI journal write, even offline.
        if (Z8EnvironmentTemplate.isReady(service)) {
            if (preferences(service).edit().putString("status", "ready").putString("stage", "ready").commit()) {
                latest = null; changed();
            }
            return;
        }
        start(service, preferences(service).getBoolean("allowMetered", false));
    }
    private static void start(TermuxService service, boolean allowMetered) {
        ConnectivityManager manager = service.getSystemService(ConnectivityManager.class);
        Network network = allowedNetwork(manager, allowMetered);
        if (network == null) {
            preferences(service).edit().putString("status", "waiting").commit();
            latest = new State(Phase.WAITING_NETWORK, "network", -1,
                allowMetered ? Z8Text.text("Connect to the internet to continue.", "인터넷에 연결한 뒤 계속해 주세요.") : Z8Text.text("Connect to Wi-Fi or allow mobile data.", "Wi-Fi에 연결하거나 모바일 데이터 사용에 동의해 주세요."), allowMetered);
            changed(); return;
        }
        Job job = new Job(service, allowMetered, network);
        active = job; latest = null;
        service.z8AcquireExecution();
        Z8PreparationNotification.begin(service, job.id, NOTIFICATION_ID, "z8");
        try {
            manager.registerDefaultNetworkCallback(job.callback); job.callbackRegistered = true;
        } catch (RuntimeException error) {
            finish(job, new IOException(Z8Text.text("Could not check the network status.", "네트워크 상태를 확인할 수 없습니다."))); return;
        }
        changed();
        WORKER.execute(() -> run(job));
    }
    private static Network allowedNetwork(ConnectivityManager manager, boolean allowMetered) {
        try {
            Network network = manager == null ? null : manager.getActiveNetwork();
            NetworkCapabilities caps = network == null ? null : manager.getNetworkCapabilities(network);
            if (!allowedCapabilities(caps, allowMetered) || !network.equals(manager.getActiveNetwork())) return null;
            return network;
        } catch (SecurityException unavailable) { return null; }
    }
    private static boolean allowedCapabilities(NetworkCapabilities caps, boolean allowMetered) {
        return caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
            && (allowMetered || caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
                && !caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR));
    }
    private static void checkNetwork(Job job) {
        if (job.abandoned || active != job) return;
        if (job.network.equals(allowedNetwork(job.connectivity, job.allowMetered))) return;
        pauseForNetwork(job);
    }
    private static void pauseForNetwork(Job job) {
        if (job.abandoned || active != job) return;
        job.networkStopped = true;
        // Bound download sockets cannot silently migrate to the default mobile network.
        Z8SetupDownloadProxy proxy = job.proxy;
        if (proxy != null) proxy.close();
        Thread thread = job.thread;
        if (thread != null) thread.interrupt();
    }
    private static void run(Job job) {
        job.thread = Thread.currentThread();
        Exception failure = null;
        try {
            if (job.abandoned) throw new InterruptedException();
            checkNetwork(job);
            if (job.networkStopped) throw new InterruptedException();
            job.proxy = Z8SetupDownloadProxy.open(job.service, job.network);
            checkNetwork(job);
            if (job.networkStopped) throw new InterruptedException();
            final String[] stage = {""};
            Z8ProjectPreparation.run(job.service.getApplicationContext(), Z8EnvironmentTemplate.ID, (name, percent, message) -> {
                if (job.abandoned || job.networkStopped || Thread.currentThread().isInterrupted())
                    throw new java.util.concurrent.CancellationException(Z8Text.text("Installation paused.", "설치를 일시 중단했습니다."));
                if (!name.equals(stage[0])) {
                    if (!preferences(job.service).edit().putString("status", "running").putString("stage", name).commit())
                        throw new IllegalStateException(Z8Text.text("Could not save the installation status.", "설치 상태를 저장하지 못했습니다."));
                    stage[0] = name;
                }
                job.progress = new State(Phase.RUNNING, name, percent, message, job.allowMetered);
                Z8PreparationNotification.progress(job.service, job.id, name, percent, message);
                if (job.scheduled.compareAndSet(false, true)) MAIN.postDelayed(() -> {
                    job.scheduled.set(false); if (active == job) changed();
                }, 250);
            }, job.proxy.environment());
            if (job.abandoned || job.networkStopped || Thread.currentThread().isInterrupted()) throw new InterruptedException();
            if (!Z8EnvironmentTemplate.isReady(job.service)) throw new IOException(Z8Text.text("Could not verify the installed development environment.", "설치한 개발 환경을 확인하지 못했습니다."));
            if (!preferences(job.service).edit().putString("status", "ready").putString("stage", "ready").commit())
                throw new IOException(Z8Text.text("Could not save the completed installation status.", "설치 완료 상태를 저장하지 못했습니다."));
        } catch (Exception error) { failure = error; }
        finally {
            Z8SetupDownloadProxy proxy = job.proxy; if (proxy != null) proxy.close();
            job.thread = null;
            Thread.interrupted(); // Executor reuse must not inherit a prior network interruption.
        }
        Exception result = failure;
        MAIN.post(() -> finish(job, result));
    }
    private static void finish(Job job, Exception error) {
        mainThread();
        unregister(job);
        if (active != job || job.abandoned) return;
        boolean success = error == null;
        boolean waiting = !success && job.networkStopped;
        String status = success ? "ready" : waiting ? "waiting" : "failed";
        preferences(job.service).edit().putString("status", status).commit();
        latest = new State(success ? Phase.READY : waiting ? Phase.WAITING_NETWORK : Phase.FAILED,
            success ? "ready" : job.progress.stage, success ? 100 : -1,
            success ? Z8Text.text("Development environment ready", "개발 환경 준비 완료") : waiting ? Z8Text.text("The network changed, so the download was paused. Check the connection to continue.", "네트워크가 변경되어 다운로드를 멈췄어요. 연결을 확인하고 계속해 주세요.")
                : error.getMessage() == null ? Z8Text.text("Could not prepare the development environment.", "개발 환경을 준비하지 못했습니다.") : error.getMessage(), job.allowMetered);
        active = null;
        if (waiting) Z8PreparationNotification.waiting(job.service, job.id);
        else Z8PreparationNotification.finish(job.service, job.id, success, null);
        job.service.updateNotification();
        changed();
    }
    private static void unregister(Job job) {
        if (job.callbackRegistered) {
            try { job.connectivity.unregisterNetworkCallback(job.callback); }
            catch (IllegalArgumentException ignored) { }
            job.callbackRegistered = false;
        }
    }
    public static void stop(TermuxService service) {
        mainThread();
        Job job = active;
        if (job == null || job.service != service) return;
        job.abandoned = true; active = null; latest = null;
        unregister(job);
        if (job.proxy != null) job.proxy.close();
        if (job.thread != null) job.thread.interrupt();
        Z8PreparationNotification.releaseOwner(service);
    }
}
