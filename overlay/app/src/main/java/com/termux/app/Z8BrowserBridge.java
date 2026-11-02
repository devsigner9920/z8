package com.termux.app;

import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;

import com.termux.terminal.TerminalSession;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;

/** Ephemeral browser requests from authenticated, live terminal launches.
 * URLs may contain OAuth state: never persist, log, or put them in notifications.
 * Foreground UI alone consumes requests; this class never launches an Activity.
 */
public final class Z8BrowserBridge {
    public interface Listener { boolean onOpen(Request request); }
    public static final class Request {
        public final String url, sessionHandle, projectId, projectName;
        private final TerminalSession session;
        private final long createdAt;
        private Request(TerminalSession session, Z8SessionOrigin origin, String url) {
            this.session = session;
            this.url = url;
            sessionHandle = session.mHandle;
            projectId = origin.projectId;
            projectName = origin.projectName;
            createdAt = SystemClock.elapsedRealtime();
        }
        public boolean isLive() { return session.isRunning() && SystemClock.elapsedRealtime() - createdAt < TTL; }
    }

    private static final long TTL = 120_000;
    private static final int LIMIT = 16;
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final Map<String, Request> pending = new LinkedHashMap<>();
    private static final Map<String, Long> seen = new LinkedHashMap<>();
    private static Listener listener;
    private static boolean scheduled;
    private static final Runnable EXPIRY = Z8BrowserBridge::expire;

    private Z8BrowserBridge() { }

    /** Strict URL grammar independent of WebView/Intent's permissive parsing. */
    public static boolean validUrl(String value) {
        if (Z8BrowserUrls.isBlank(value)) return true;
        if (value == null || value.isEmpty() || value.getBytes(StandardCharsets.UTF_8).length > 8192) return false;
        for (int i = 0; i < value.length(); i++) {
            char character = value.charAt(i);
            if (character <= 32 || character == 127 || character == '\\') return false;
        }
        if (value.matches("(?is).*%(?:0[0-9a-f]|1[0-9a-f]|7f).*$")) return false;
        try {
            URI uri = new URI(value);
            String scheme = uri.getScheme();
            return ("https".equalsIgnoreCase(scheme) || "http".equalsIgnoreCase(scheme))
                && uri.getHost() != null && !uri.getHost().isEmpty() && uri.getRawUserInfo() == null
                && (uri.getPort() == -1 || uri.getPort() > 0 && uri.getPort() <= 65535);
        } catch (Exception invalid) { return false; }
    }

    /** Only the same-UID, launch-token authenticated transport may submit. */
    static synchronized String submit(TerminalSession session, String eventId, String url) {
        prune();
        if (!validUrl(url) || eventId == null || !eventId.matches("[A-Za-z0-9_.:-]{1,160}")) return "invalid";
        Z8SessionOrigin origin = Z8SessionOrigin.of(session);
        if (session == null || !session.isRunning() || origin == null || origin.projectId == null) return "stale";
        String key = session.mHandle + ":" + eventId;
        if (seen.containsKey(key)) return "duplicate";
        if (pending.containsKey(session.mHandle) || pending.size() >= LIMIT) return "busy";
        pending.put(session.mHandle, new Request(session, origin, url));
        seen.put(key, SystemClock.elapsedRealtime());
        while (seen.size() > 128) seen.remove(seen.keySet().iterator().next());
        scheduleExpiry();
        schedule();
        return "accepted";
    }

    public static synchronized void attach(Listener owner) {
        listener = owner;
        prune();
        schedule();
    }

    public static synchronized void detach(Listener owner) {
        if (listener == owner) listener = null;
    }

    public static synchronized int pendingCount() { prune(); return pending.size(); }

    static synchronized void clear() {
        pending.clear();
        seen.clear();
        MAIN.removeCallbacks(EXPIRY);
        // Activity owns attaching/detaching its UI listener across service restart.
    }

    private static void schedule() {
        if (listener == null || pending.isEmpty() || scheduled) return;
        scheduled = true;
        MAIN.post(Z8BrowserBridge::drain);
    }

    private static void drain() {
        ArrayList<Request> requests;
        Listener owner;
        synchronized (Z8BrowserBridge.class) {
            scheduled = false;
            prune();
            owner = listener;
            if (owner == null) return;
            requests = new ArrayList<>(pending.values());
        }
        for (Request request : requests) {
            synchronized (Z8BrowserBridge.class) {
                if (listener != owner) return;
                if (!request.isLive() || pending.get(request.sessionHandle) != request) continue;
            }
            boolean consumed = owner.onOpen(request);
            synchronized (Z8BrowserBridge.class) {
                if (consumed && pending.get(request.sessionHandle) == request) pending.remove(request.sessionHandle);
            }
        }
    }

    private static void prune() {
        pending.values().removeIf(request -> !request.isLive());
        long now = SystemClock.elapsedRealtime();
        Iterator<Map.Entry<String, Long>> iterator = seen.entrySet().iterator();
        while (iterator.hasNext()) if (now - iterator.next().getValue() >= TTL) iterator.remove();
    }

    private static synchronized void expire() { prune(); scheduleExpiry(); }

    private static void scheduleExpiry() {
        MAIN.removeCallbacks(EXPIRY);
        if (pending.isEmpty()) return;
        long next = pending.values().iterator().next().createdAt + TTL - SystemClock.elapsedRealtime();
        MAIN.postDelayed(EXPIRY, Math.max(1, next));
    }
}
