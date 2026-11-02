package com.termux.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.net.LocalServerSocket;
import android.net.LocalSocket;
import android.net.LocalSocketAddress;
import android.net.Uri;
import android.os.Process;
import android.system.Os;
import android.util.AtomicFile;
import android.util.Log;
import android.widget.Toast;

import com.termux.shared.shell.command.ExecutionCommand;
import com.termux.terminal.TerminalSession;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** Service-owned, same-UID observation channel. Never makes a CLI approval decision. */
public final class Z8AttentionBridge {
    public static final String EXTRA_EVENT = "dev.devsigner.z8.attention.event";
    private static final String CHANNEL = "z8_agent_attention";
    private static final int LIMIT = 16384;
    private static final int MAX_ITEMS = 256;
    private static volatile Z8AttentionBridge active;
    private final Context context;
    private final AtomicFile stateFile;
    private final File socketFile;
    private final Map<ExecutionCommand, Launch> preparing = new IdentityHashMap<>();
    private final Map<String, Launch> launches = new HashMap<>();
    private final List<JSONObject> items = new ArrayList<>();
    private LocalSocket listener;
    private LocalServerSocket server;
    private volatile boolean closed;
    private long lastFailureLogAt;
    private int failureLogCount;

    private static final class Launch {
        final String id = UUID.randomUUID().toString();
        final String token;
        TerminalSession session;
        Launch() {
            byte[] bytes = new byte[32];
            new SecureRandom().nextBytes(bytes);
            StringBuilder value = new StringBuilder();
            for (byte b : bytes) value.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
            token = value.toString();
        }
    }

    private Z8AttentionBridge(Context context) throws IOException {
        this.context = context.getApplicationContext();
        File directory = new File(context.getFilesDir(), "z8/attention");
        if (!directory.isDirectory() && !directory.mkdirs()) throw new IOException("Event directory unavailable");
        try { Os.chmod(directory.getAbsolutePath(), 0700); } catch (Exception e) { throw new IOException(e); }
        stateFile = new AtomicFile(new File(directory, "items.json"));
        // Only this transport directory is eligible for a guest bind; keep the
        // app-wide observation journal outside every project guest.
        File transport = new File(directory, "transport");
        if (!transport.isDirectory() && !transport.mkdirs()) throw new IOException("Event transport unavailable");
        try { Os.chmod(transport.getAbsolutePath(), 0700); } catch (Exception e) { throw new IOException(e); }
        socketFile = new File(transport, "events.sock");
        loadState();
        // A socket cannot survive an Android process death; old launches are never reattached by guesswork.
        for (JSONObject item : items) put(item, "state", "STALE");
        saveState();
        if (socketFile.exists() && !socketFile.delete()) throw new IOException("Stale event socket unavailable");
        listener = new LocalSocket();
        try {
            listener.bind(new LocalSocketAddress(socketFile.getAbsolutePath(), LocalSocketAddress.Namespace.FILESYSTEM));
            Os.chmod(socketFile.getAbsolutePath(), 0600);
            server = new LocalServerSocket(listener.getFileDescriptor());
        } catch (Exception e) {
            try { listener.close(); } catch (IOException ignored) { }
            socketFile.delete();
            throw new IOException(e);
        }
        Thread worker = new Thread(this::receiveLoop, "z8-attention");
        worker.setDaemon(true);
        worker.start();
    }

    public static synchronized void start(Context context) {
        if (active != null) return;
        try { active = new Z8AttentionBridge(context); }
        catch (IOException e) { Log.w("z8", "Attention bridge unavailable; terminal remains usable", e); }
    }

    public static synchronized void stop() {
        Z8AttentionBridge bridge = active;
        active = null;
        if (bridge == null) return;
        bridge.closed = true;
        try { bridge.server.close(); } catch (IOException ignored) { }
        try { bridge.listener.close(); } catch (IOException ignored) { }
        bridge.socketFile.delete();
        Z8BrowserBridge.clear();
        synchronized (bridge) {
            for (JSONObject item : bridge.items) put(item, "state", "STALE");
            try { bridge.saveState(); } catch (IOException ignored) { }
            bridge.launches.clear();
            bridge.preparing.clear();
        }
    }

    /** Called before execute, then registerLaunch exactly once after successful session creation. */
    public static HashMap<String, String> prepareLaunch(ExecutionCommand command, HashMap<String, String> base) {
        Z8AttentionBridge bridge = active;
        if (bridge == null || command.isPluginExecutionCommand) return base;
        HashMap<String, String> env = base == null ? new HashMap<>() : new HashMap<>(base);
        synchronized (bridge) {
            bridge.pruneLaunches();
            // Bound failed/incomplete launch bookkeeping; live terminal sessions are independently limited by UI.
            if (bridge.preparing.size() >= 64) return base;
            Launch launch = new Launch();
            bridge.preparing.put(command, launch);
            env.put("Z8_EVENT_SOCKET", bridge.socketFile.getAbsolutePath());
            env.put("Z8_LAUNCH_ID", launch.id);
            env.put("Z8_EVENT_TOKEN", launch.token);
        }
        return env;
    }

    public static void registerLaunch(ExecutionCommand command, TerminalSession session) {
        Z8AttentionBridge bridge = active;
        if (bridge == null) return;
        synchronized (bridge) {
            Launch launch = bridge.preparing.remove(command);
            if (launch != null) {
                launch.session = session;
                bridge.launches.put(launch.id, launch);
            }
        }
    }

    /** Package-local transport credentials for an explicit HTML click on this exact live PTY. Never log or persist. */
    static Map<String, String> browserEnvironment(TerminalSession session) {
        Z8AttentionBridge bridge = active;
        if (bridge == null || session == null || !session.isRunning()) return null;
        synchronized (bridge) {
            if (bridge.closed) return null;
            for (Launch launch : bridge.launches.values()) if (launch.session == session) {
                Map<String, String> result = new HashMap<>();
                result.put("Z8_LAUNCH_ID", launch.id);
                result.put("Z8_EVENT_TOKEN", launch.token);
                return result;
            }
        }
        return null;
    }

    public static void discardLaunch(ExecutionCommand command) {
        Z8AttentionBridge bridge = active;
        if (bridge != null) synchronized (bridge) { bridge.preparing.remove(command); }
    }

    private void receiveLoop() {
        while (!closed) {
            try (LocalSocket client = server.accept()) {
                client.setSoTimeout(300);
                if (client.getPeerCredentials().getUid() != Process.myUid()) {
                    logFailure("peer-uid", null);
                    continue;
                }
                byte[] data = readFrame(client, 1000);
                String status;
                try { status = accept(new JSONObject(new String(data, StandardCharsets.UTF_8))); }
                catch (JSONException | IllegalArgumentException e) { status = "invalid"; }
                if (!"accepted".equals(status) && !"duplicate".equals(status)) logFailure("rejected-" + status, null);
                // No token, tool input, command, question or transcript is ever echoed.
                client.getOutputStream().write(("{\"status\":\"" + status + "\"}\n").getBytes(StandardCharsets.UTF_8));
                client.getOutputStream().flush();
            } catch (IOException e) {
                // Malformed, idle or vanished clients are independent of the next connection.
                if (closed) break;
                logFailure("server-io", e);
            }
        }
    }

    private synchronized void logFailure(String stage, Exception failure) {
        long now = android.os.SystemClock.elapsedRealtime();
        if (failureLogCount >= 20 || (failureLogCount > 0 && now - lastFailureLogAt < 5000)) return;
        lastFailureLogAt = now;
        failureLogCount++;
        // Stage is a fixed internal label. Never log exception messages, frames or credentials.
        Log.w("z8", "Attention transport: " + stage + (failure == null ? "" : " / " + failure.getClass().getSimpleName()));
    }

    private static byte[] readFrame(LocalSocket socket, int totalMillis) throws IOException {
        long deadline = android.os.SystemClock.elapsedRealtime() + totalMillis;
        InputStream stream = socket.getInputStream();
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        int next;
        while (true) {
            long remaining = deadline - android.os.SystemClock.elapsedRealtime();
            if (remaining <= 0) throw new IOException("Frame deadline exceeded");
            socket.setSoTimeout((int) remaining);
            next = stream.read();
            if (next == -1) break;
            if (next == '\n') return bytes.toByteArray();
            if (bytes.size() >= LIMIT) throw new IOException("Frame too large");
            bytes.write(next);
        }
        throw new IOException("Missing frame delimiter");
    }

    private synchronized String accept(JSONObject event) throws JSONException, IOException {
        pruneLaunches();
        if ("browser".equals(event.optString("kind"))) return acceptBrowser(event);
        if ("preview-check".equals(event.optString("kind"))) return acceptPreviewCheck(event);
        Set<String> allowed = new HashSet<>(java.util.Arrays.asList("schemaVersion", "eventId", "launchId", "token", "provider", "providerSessionId", "requestId", "kind"));
        Iterator<String> keys = event.keys();
        while (keys.hasNext()) if (!allowed.contains(keys.next())) return "invalid";
        if (!(event.opt("schemaVersion") instanceof Number) || event.getDouble("schemaVersion") != 1) return "invalid";
        String eventId = id(event, "eventId", false);
        String launchId = id(event, "launchId", false);
        String provider = id(event, "provider", false);
        String providerSession = id(event, "providerSessionId", true);
        String request = id(event, "requestId", true);
        String kind = id(event, "kind", false);
        if (!java.util.Arrays.asList("permission", "question", "plan", "finished").contains(kind)) return "invalid";
        if (!java.util.Arrays.asList("claude", "codex", "diagnostic").contains(provider)) return "invalid";
        Launch launch = launches.get(launchId);
        Object token = event.opt("token");
        if (launch == null || !(token instanceof String) || ((String) token).length() != 64 ||
            !MessageDigest.isEqual(launch.token.getBytes(StandardCharsets.US_ASCII), ((String) token).getBytes(StandardCharsets.US_ASCII))) return "unauthorized";
        if (launch.session == null || !launch.session.isRunning()) return "stale";
        for (JSONObject item : items) {
            if (launchId.equals(item.optString("launchId")) &&
                (eventId.equals(item.optString("eventId")) || (!request.isEmpty() && request.equals(item.optString("requestId")) && provider.equals(item.optString("provider")) && providerSession.equals(item.optString("providerSessionId")) && kind.equals(item.optString("kind"))))) return "duplicate";
        }
        // Bounded history must not permanently silence new requests after normal
        // use. Unread requests on live sessions stay; only read/completed/stale
        // records can make room, and removal commits with the incoming event.
        JSONObject displaced = items.size() >= MAX_ITEMS ? oldestDiscardableItem() : null;
        if (items.size() >= MAX_ITEMS && displaced == null) return "full";
        JSONObject item = new JSONObject();
        item.put("id", UUID.randomUUID().toString());
        item.put("eventId", eventId);
        item.put("launchId", launchId);
        item.put("sessionHandle", launch.session.mHandle);
        attachSessionLabels(item, launch.session);
        item.put("provider", provider);
        item.put("providerSessionId", providerSession);
        item.put("requestId", request);
        item.put("kind", kind);
        item.put("observedAt", System.currentTimeMillis());
        item.put("state", "OBSERVED");
        item.put("seenAt", 0);
        item.put("deliveryState", "QUEUED");
        int displacedIndex = displaced == null ? -1 : items.indexOf(displaced);
        if (displaced != null) items.remove(displacedIndex);
        items.add(item);
        try { saveState(); } catch (IOException e) {
            items.remove(item);
            if (displaced != null) items.add(displacedIndex, displaced);
            return "storage-failed";
        }
        if (displaced != null) {
            try { context.getSystemService(NotificationManager.class).cancel(displaced.optString("id"), 1); }
            catch (RuntimeException ignored) { /* Journal is durable; stale notification cleanup is best effort. */ }
        }
        postNotification(item);
        // The durable event write precedes ACK. Delivery metadata is best effort and recoverable.
        try { saveState(); } catch (IOException ignored) { }
        return "accepted";
    }

    private JSONObject oldestDiscardableItem() {
        JSONObject oldest = null;
        for (JSONObject item : items) {
            if (item.optLong("seenAt") == 0 && !"STALE".equals(item.optString("state"))
                    && !"finished".equals(item.optString("kind"))) continue;
            if (oldest == null || item.optLong("observedAt") < oldest.optLong("observedAt")) oldest = item;
        }
        return oldest;
    }

    /** Read-only lease check for a local HTML preview. No inbox or browser side effects. */
    private String acceptPreviewCheck(JSONObject event) throws JSONException {
        Set<String> allowed = new HashSet<>(java.util.Arrays.asList("schemaVersion", "eventId", "launchId", "token", "kind"));
        Iterator<String> keys = event.keys();
        while (keys.hasNext()) if (!allowed.contains(keys.next())) return "invalid";
        if (!(event.opt("schemaVersion") instanceof Number) || event.getDouble("schemaVersion") != 1) return "invalid";
        id(event, "eventId", false);
        String launchId = id(event, "launchId", false);
        Object token = event.opt("token");
        Launch launch = launches.get(launchId);
        if (launch == null || !(token instanceof String) || ((String) token).length() != 64 ||
                !MessageDigest.isEqual(launch.token.getBytes(StandardCharsets.US_ASCII), ((String) token).getBytes(StandardCharsets.US_ASCII)))
            return "unauthorized";
        if (launch.session == null || !launch.session.isRunning()
                || Z8SessionOrigin.of(launch.session) == null) return "stale";
        return "accepted";
    }

    private String acceptBrowser(JSONObject event) throws JSONException {
        Set<String> allowed = new HashSet<>(java.util.Arrays.asList("schemaVersion", "eventId", "launchId", "token", "kind", "url"));
        Iterator<String> keys = event.keys();
        while (keys.hasNext()) if (!allowed.contains(keys.next())) return "invalid";
        if (!(event.opt("schemaVersion") instanceof Number) || event.getDouble("schemaVersion") != 1) return "invalid";
        String eventId = id(event, "eventId", false);
        String launchId = id(event, "launchId", false);
        Object token = event.opt("token"), url = event.opt("url");
        Launch launch = launches.get(launchId);
        if (launch == null || !(token instanceof String) || ((String) token).length() != 64 ||
                !MessageDigest.isEqual(launch.token.getBytes(StandardCharsets.US_ASCII), ((String) token).getBytes(StandardCharsets.US_ASCII)))
            return "unauthorized";
        if (!(url instanceof String)) return "invalid";
        return Z8BrowserBridge.submit(launch.session, eventId, (String) url);
    }

    private static String id(JSONObject object, String name, boolean optional) {
        if (!object.has(name) && optional) return "";
        Object value = object.opt(name);
        if (!(value instanceof String) || !((String) value).matches("[A-Za-z0-9_.:-]{1,160}")) throw new IllegalArgumentException("Invalid identifier");
        return (String) value;
    }

    private void postNotification(JSONObject item) {
        if ("finished".equals(item.optString("kind"))) { put(item, "deliveryState", "SUPPRESSED"); return; }
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        try {
            NotificationChannel channel = new NotificationChannel(CHANNEL, "응답 확인", NotificationManager.IMPORTANCE_DEFAULT);
            channel.setDescription("CLI 권한 요청이나 질문이 발생하면 원래 세션으로 돌아갑니다.");
            channel.setLockscreenVisibility(Notification.VISIBILITY_PRIVATE);
            manager.createNotificationChannel(channel);
            if (!manager.areNotificationsEnabled() || manager.getNotificationChannel(CHANNEL).getImportance() == NotificationManager.IMPORTANCE_NONE) {
                put(item, "deliveryState", "BLOCKED"); return;
            }
            String itemId = item.optString("id");
            Intent intent = new Intent(context, Z8AttentionActivity.class).putExtra(EXTRA_EVENT, itemId)
                .setData(Uri.parse("z8-attention://event/" + itemId));
            PendingIntent pending = PendingIntent.getActivity(context, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            Notification publicNotice = new Notification.Builder(context, CHANNEL).setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle("z8 · 확인이 필요합니다").build();
            Notification notice = new Notification.Builder(context, CHANNEL).setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle("z8 · 확인 요청이 발생했습니다")
                .setContentText(Z8SessionCatalog.displayText(item.optString("projectName"), 80, "프로젝트")
                    + " / " + Z8SessionCatalog.displayText(item.optString("sessionName"), 96, "세션"))
                .setContentIntent(pending).setAutoCancel(true).setOnlyAlertOnce(true)
                .setVisibility(Notification.VISIBILITY_PRIVATE).setPublicVersion(publicNotice).build();
            manager.notify(itemId, 1, notice);
            put(item, "deliveryState", "POSTED");
        } catch (SecurityException e) { put(item, "deliveryState", "BLOCKED"); }
        catch (RuntimeException e) { put(item, "deliveryState", "FAILED"); }
    }

    /** Small live-only badge snapshot. No disk access, output parsing or approval inference. */
    public static Map<String, Integer> unseenSessionCounts() {
        Map<String, Integer> result = new HashMap<>();
        Z8AttentionBridge bridge = active;
        if (bridge == null) return result;
        synchronized (bridge) {
            for (JSONObject item : bridge.items) {
                if (item.optLong("seenAt") != 0 || !"OBSERVED".equals(item.optString("state"))
                        || "finished".equals(item.optString("kind"))) continue;
                Launch launch = bridge.launches.get(item.optString("launchId"));
                if (launch == null || launch.session == null || !launch.session.isRunning()) continue;
                String handle = launch.session.mHandle;
                result.put(handle, result.getOrDefault(handle, 0) + 1);
            }
        }
        return result;
    }

    public static List<JSONObject> snapshot(Context context) {
        Z8AttentionBridge bridge = active;
        if (bridge != null) synchronized (bridge) {
            bridge.pruneLaunches();
            ArrayList<JSONObject> result = new ArrayList<>();
            for (JSONObject item : bridge.items) {
                Launch launch = bridge.launches.get(item.optString("launchId"));
                if (launch == null || !launch.session.isRunning()) put(item, "state", "STALE");
                try {
                    JSONObject copy = new JSONObject(item.toString());
                    if (launch != null && launch.session != null) attachSessionLabels(copy, launch.session);
                    result.add(copy);
                } catch (JSONException ignored) { }
            }
            return result;
        }
        ArrayList<JSONObject> result = new ArrayList<>();
        AtomicFile file = new AtomicFile(new File(context.getFilesDir(), "z8/attention/items.json"));
        try {
            JSONArray data = new JSONArray(new String(file.readFully(), StandardCharsets.UTF_8));
            for (int i = 0; i < data.length() && i < MAX_ITEMS; i++) {
                JSONObject item = data.getJSONObject(i);
                put(item, "state", "STALE");
                result.add(item);
            }
        } catch (IOException | JSONException ignored) { }
        return result;
    }

    /** One bounded pass for an inbox refresh; individual taps still revalidate through canOpen. */
    public static Set<String> openableEventIds() {
        Set<String> result = new HashSet<>();
        Z8AttentionBridge bridge = active;
        if (bridge == null) return result;
        synchronized (bridge) {
            for (JSONObject item : bridge.items) {
                Launch launch = bridge.launches.get(item.optString("launchId"));
                if (launch != null && launch.session != null && launch.session.isRunning())
                    result.add(item.optString("id"));
            }
        }
        return result;
    }

    public static boolean canOpen(String itemId) {
        Z8AttentionBridge bridge = active;
        if (bridge == null) return false;
        synchronized (bridge) {
            for (JSONObject item : bridge.items) if (item.optString("id").equals(itemId)) {
                Launch launch = bridge.launches.get(item.optString("launchId"));
                return launch != null && launch.session != null && launch.session.isRunning();
            }
        }
        return false;
    }

    /** Explicit housekeeping removes history, not a CLI approval or resolution. */
    public static void clearHistory(Context context) {
        Z8AttentionBridge bridge = active;
        if (bridge == null) {
            for (JSONObject item : snapshot(context)) context.getSystemService(NotificationManager.class).cancel(item.optString("id"), 1);
            new AtomicFile(new File(context.getFilesDir(), "z8/attention/items.json")).delete();
            return;
        }
        synchronized (bridge) {
            Iterator<JSONObject> iterator = bridge.items.iterator();
            while (iterator.hasNext()) {
                JSONObject item = iterator.next();
                Launch launch = bridge.launches.get(item.optString("launchId"));
                if (item.optLong("seenAt") > 0 || launch == null || !launch.session.isRunning()) {
                    bridge.context.getSystemService(NotificationManager.class).cancel(item.optString("id"), 1);
                    iterator.remove();
                }
            }
            try { bridge.saveState(); } catch (IOException ignored) { }
        }
    }

    public interface DiagnosticResult { void completed(String status); }

    public static String diagnosticStatus(Context context) {
        return context.getSharedPreferences("z8_attention_diagnostics", Context.MODE_PRIVATE)
            .getString("last_result", "아직 진단을 실행하지 않았습니다.");
    }

    private static void recordDiagnostic(Context context, String status) {
        context.getSharedPreferences("z8_attention_diagnostics", Context.MODE_PRIVATE).edit()
            .putString("last_result", status).apply();
    }

    /** Explicit UI diagnostic uses the real filesystem socket, framing, credentials and validation. */
    public static void sendDiagnostic(android.app.Activity activity, DiagnosticResult callback) {
        Z8AttentionBridge bridge = active;
        JSONObject event = new JSONObject();
        if (bridge != null) synchronized (bridge) {
            for (Launch launch : bridge.launches.values()) if (launch.session != null && launch.session.isRunning()) {
                put(event, "schemaVersion", 1);
                put(event, "eventId", UUID.randomUUID().toString());
                put(event, "launchId", launch.id);
                put(event, "token", launch.token);
                put(event, "provider", "diagnostic");
                put(event, "kind", "permission");
                break;
            }
        }
        if (event.length() == 0) {
            recordDiagnostic(activity, "먼저 터미널 세션을 열어 주세요");
            callback.completed("먼저 터미널 세션을 열어 주세요");
            return;
        }
        recordDiagnostic(activity, "진단 이벤트 전송 중");
        new Thread(() -> {
            String status;
            String stage = "client-create";
            try (LocalSocket socket = new LocalSocket()) {
                // setSoTimeout does not create LocalSocket's descriptor. Asking
                // for its output stream does, without sending any bytes.
                socket.getOutputStream();
                socket.setSoTimeout(5000);
                stage = "client-connect";
                socket.connect(new LocalSocketAddress(bridge.socketFile.getAbsolutePath(), LocalSocketAddress.Namespace.FILESYSTEM));
                stage = "client-write";
                socket.getOutputStream().write((event.toString() + "\n").getBytes(StandardCharsets.UTF_8));
                stage = "client-ack";
                String answer = new JSONObject(new String(readFrame(socket, 5000), StandardCharsets.UTF_8)).optString("status", "failed");
                status = java.util.Arrays.asList("accepted", "duplicate").contains(answer)
                    ? bridge.diagnosticReceipt(event, "수신 확인")
                    : "수신 거절 · " + (java.util.Arrays.asList("invalid", "unauthorized", "stale", "full", "storage-failed").contains(answer) ? answer : "invalid-response");
            } catch (IOException | JSONException e) {
                bridge.logFailure(stage, e);
                // A durable receipt is authoritative even if the local ACK was lost.
                // Match this exact nonce; an unrelated POSTED event cannot turn failure into success.
                status = bridge.diagnosticReceipt(event, "응답을 확인하지 못했습니다. 다시 진단해 주세요.");
            }
            recordDiagnostic(activity.getApplicationContext(), status);
            final String result = status;
            activity.runOnUiThread(() -> callback.completed(result));
        }, "z8-hook-diagnostic").start();
    }

    private static void attachSessionLabels(JSONObject item, TerminalSession session) {
        Z8SessionOrigin origin = Z8SessionOrigin.of(session);
        put(item, "projectId", origin == null || origin.projectId == null ? "" : origin.projectId);
        put(item, "projectName", Z8SessionCatalog.displayText(origin == null ? null : origin.projectName, 80, "기기 셸"));
        put(item, "sessionName", Z8SessionCatalog.title(session));
    }

    /** Reconcile only this diagnostic's durable event, never assume notification delivery. */
    private synchronized String diagnosticReceipt(JSONObject event, String absent) {
        for (JSONObject item : items) {
            if (event.optString("launchId").equals(item.optString("launchId"))
                    && event.optString("eventId").equals(item.optString("eventId"))) {
                String delivery = item.optString("deliveryState");
                return "수신 확인 · " + ("POSTED".equals(delivery) ? "알림 게시됨"
                    : "BLOCKED".equals(delivery) ? "알림 차단됨 · 알림 설정 확인"
                    : "FAILED".equals(delivery) ? "알림 게시 실패 · 앱 기록에서 확인"
                    : "알림 게시 중");
            }
        }
        return absent;
    }

    public static String availability() { return active == null ? "수신기 중지됨" : "로컬 훅 수신 중"; }

    public static Intent sessionIntent(Context context, String itemId) {
        return new Intent(context, TermuxActivity.class).putExtra(EXTRA_EVENT, itemId);
    }

    /** Return true even for stale events: callers must NEVER create a replacement shell. */
    public static boolean routeRequestedSession(TermuxActivity activity, Intent intent) {
        if (intent == null || !intent.hasExtra(EXTRA_EVENT)) return false;
        String wanted = intent.getStringExtra(EXTRA_EVENT);
        Z8AttentionBridge bridge = active;
        TerminalSession session = null;
        if (bridge != null) synchronized (bridge) {
            for (JSONObject item : bridge.items) if (item.optString("id").equals(wanted)) {
                Launch launch = bridge.launches.get(item.optString("launchId"));
                if (launch != null && launch.session != null && launch.session.isRunning()) {
                    session = launch.session;
                    put(item, "seenAt", System.currentTimeMillis());
                    // Seeing a request never proves that the CLI resolved it.
                    try { bridge.saveState(); } catch (IOException ignored) { }
                    bridge.context.getSystemService(NotificationManager.class).cancel(wanted, 1);
                }
                break;
            }
        }
        if (session != null && activity.getTermuxService() != null) activity.getTermuxTerminalSessionClient().setCurrentSession(session);
        else {
            Toast.makeText(activity, "이 세션은 종료되었거나 다시 연결할 수 없습니다.", Toast.LENGTH_LONG).show();
            activity.startActivity(new Intent(activity, Z8AttentionActivity.class));
            activity.finish();
        }
        return true;
    }

    /** Drop expired nonces and terminal references when their processes finish. */
    private void pruneLaunches() {
        Set<String> ended = new HashSet<>();
        Iterator<Map.Entry<String, Launch>> iterator = launches.entrySet().iterator();
        while (iterator.hasNext()) {
            Map.Entry<String, Launch> entry = iterator.next();
            if (entry.getValue().session == null || !entry.getValue().session.isRunning()) {
                ended.add(entry.getKey());
                iterator.remove();
            }
        }
        if (!ended.isEmpty()) {
            for (JSONObject item : items) if (ended.contains(item.optString("launchId"))) {
                put(item, "state", "STALE");
                context.getSystemService(NotificationManager.class).cancel(item.optString("id"), 1);
            }
            try { saveState(); } catch (IOException ignored) { }
        }
    }

    private void loadState() {
        try {
            byte[] bytes = stateFile.readFully();
            if (bytes.length > 512 * 1024) return;
            JSONArray array = new JSONArray(new String(bytes, StandardCharsets.UTF_8));
            for (int i = 0; i < array.length() && i < MAX_ITEMS; i++) items.add(array.getJSONObject(i));
        } catch (IOException | JSONException ignored) { }
    }

    private void saveState() throws IOException {
        JSONArray array = new JSONArray();
        for (JSONObject item : items) array.put(item);
        FileOutputStream output = null;
        try {
            output = stateFile.startWrite();
            output.write(array.toString().getBytes(StandardCharsets.UTF_8));
            stateFile.finishWrite(output);
        } catch (IOException e) { if (output != null) stateFile.failWrite(output); throw e; }
    }

    private static void put(JSONObject object, String key, Object value) {
        try { object.put(key, value); } catch (JSONException impossible) { throw new IllegalStateException(impossible); }
    }
}
