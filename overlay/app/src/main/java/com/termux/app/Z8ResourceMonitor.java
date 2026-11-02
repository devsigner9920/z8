package com.termux.app;

import android.os.Debug;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import android.os.SystemClock;

import java.util.Locale;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

/**
 * Public-API measurements of this Android process, not its terminal/PRoot children.
 * Sampling is opt-in while the header is visible; no shell commands or main-thread I/O.
 */
public final class Z8ResourceMonitor implements AutoCloseable {
    static final long INTERVAL_SECONDS = 3;
    static final long MEMORY_INTERVAL_MILLIS = 15_000;
    public static String scope() { return Z8Text.text("Usage for the z8 app process only. Terminal and Linux child processes are not included.", "z8 앱 프로세스의 사용량입니다. 터미널·Linux 하위 프로세스는 포함하지 않습니다."); }
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ScheduledExecutorService worker = Executors.newSingleThreadScheduledExecutor(task -> {
        Thread thread = new Thread(task, "z8-resource-monitor");
        thread.setDaemon(true);
        return thread;
    });
    private final Consumer<Snapshot> listener;
    private ScheduledFuture<?> scheduled;
    private long generation;
    private boolean active, closed;
    private Snapshot pendingSample;
    private boolean deliveryPosted;

    public static final class Snapshot {
        public final double cpuPercent;
        public final long pssKb;
        public final int cores;

        Snapshot(double cpuPercent, long pssKb, int cores) {
            this.cpuPercent = cpuPercent;
            this.pssKb = pssKb;
            this.cores = cores;
        }

        public static Snapshot pending() { return new Snapshot(Double.NaN, -1, 0); }

        public String label() {
            String cpu = Double.isNaN(cpuPercent) ? "—" : Long.toString(Math.round(cpuPercent));
            return Z8Text.text("App  CPU ", "앱  CPU ") + cpu + "%  RAM " + memoryLabel(pssKb);
        }

        public String description() {
            return label() + ". " + scope() + Z8Text.text(
                " 100% CPU represents all " + Math.max(1, cores) + " available cores. RAM uses PSS, which apportions shared memory, and refreshes every 15 seconds.",
                " CPU는 사용 가능한 " + Math.max(1, cores) + "개 코어 전체를 100%로 표시합니다. RAM은 공유 메모리를 비례 배분한 PSS이며 최대 15초 간격으로 갱신합니다.");
        }
    }

    public Z8ResourceMonitor(Consumer<Snapshot> listener) { this.listener = listener; }

    /** Idempotent; a new visible interval always gets a fresh CPU baseline. */
    public synchronized void start() {
        if (closed || active) return;
        active = true;
        long token = ++generation;
        Sampler sampler = new Sampler(token);
        scheduled = worker.scheduleWithFixedDelay(sampler, 0, INTERVAL_SECONDS, TimeUnit.SECONDS);
    }

    public synchronized void stop() {
        active = false;
        generation++;
        if (scheduled != null) scheduled.cancel(false);
        scheduled = null;
        pendingSample = null;
        deliveryPosted = false;
        main.removeCallbacksAndMessages(null);
    }

    @Override public synchronized void close() {
        if (closed) return;
        stop();
        closed = true;
        worker.shutdownNow();
    }

    private synchronized boolean current(long token) { return !closed && active && token == generation; }

    /** Keep one UI delivery when rendering is busy; intermediate samples have no history value. */
    private synchronized void enqueue(long token, Snapshot sample) {
        if (!current(token)) return;
        pendingSample = sample;
        if (deliveryPosted) return;
        deliveryPosted = true;
        main.post(() -> {
            Snapshot latest;
            synchronized (Z8ResourceMonitor.this) {
                if (!current(token)) return;
                latest = pendingSample;
                pendingSample = null;
                deliveryPosted = false;
            }
            if (current(token)) listener.accept(latest);
        });
    }

    private final class Sampler implements Runnable {
        private final long token;
        private final int cores = Math.max(1, Runtime.getRuntime().availableProcessors());
        private long previousCpu = -1, previousElapsed = -1;
        private long previousMemoryElapsed = -1, pss = -1;

        Sampler(long token) { this.token = token; }

        @Override public void run() {
            if (!current(token)) return;
            Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND);
            long elapsed = SystemClock.elapsedRealtime();
            long cpu = Process.getElapsedCpuTime();
            double percent = cpuPercent(previousCpu, previousElapsed, cpu, elapsed, cores);
            previousCpu = cpu;
            previousElapsed = elapsed;
            // PSS walks memory mappings. It need not run at the faster CPU-counter cadence.
            // A new visible interval gets a fresh measurement instead of carrying a hidden sample.
            if (memoryRefreshDue(previousMemoryElapsed, elapsed)) {
                previousMemoryElapsed = elapsed;
                try { pss = Debug.getPss(); }
                catch (RuntimeException ignored) { pss = -1; /* Never keep a stale successful value after failure. */ }
            }
            Snapshot sample = new Snapshot(percent, pss > 0 ? pss : -1, cores);
            enqueue(token, sample);
        }
    }

    static boolean memoryRefreshDue(long previousElapsed, long elapsed) {
        return previousElapsed < 0 || elapsed < previousElapsed || elapsed - previousElapsed >= MEMORY_INTERVAL_MILLIS;
    }

    /** CPU time / elapsed wall time / eligible cores. First/reset samples are unknown. */
    static double cpuPercent(long previousCpu, long previousElapsed, long cpu, long elapsed, int cores) {
        if (previousCpu < 0 || previousElapsed < 0 || cpu < previousCpu || elapsed <= previousElapsed || cores <= 0)
            return Double.NaN;
        return Math.min(100d, 100d * (cpu - previousCpu) / (elapsed - previousElapsed) / cores);
    }

    static String memoryLabel(long pssKb) {
        if (pssKb <= 0) return "— MB";
        // Debug reports KiB; decimal MB/GB keep the displayed unit unambiguous.
        double megabytes = pssKb * 1024d / 1_000_000d;
        return megabytes >= 1000 ? String.format(Locale.US, "%.1f GB", megabytes / 1000)
            : Math.round(megabytes) + " MB";
    }
}
