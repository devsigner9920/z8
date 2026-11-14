package com.termux.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import java.util.function.LongSupplier;
import javax.net.ssl.HttpsURLConnection;

/** Public release metadata only. No guest execution, artifact download or install. */
public final class Z8ToolUpdates {
    static final String PREFS = "z8-tool-updates-v1";
    static final long INTERVAL = 24L * 60 * 60 * 1000;
    static final String CODEX = "https://api.github.com/repos/openai/codex/releases/latest";
    static final String CLAUDE = "https://downloads.claude.ai/claude-code-releases/stable";
    static final String NODE = "https://nodejs.org/dist/index.json";
    static final String[] TOOLS = {"codex", "claude", "node"};
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final Object LOCK = new Object();
    private static final List<Callback> WAITING = new ArrayList<>();
    static Executor worker = Executors.newSingleThreadExecutor(task -> {
        Thread thread = new Thread(task, "z8-tool-metadata"); thread.setDaemon(true); return thread;
    });
    interface Fetcher { String get(String url, int maximum) throws Exception; }
    static Fetcher fetcher = Z8ToolUpdates::fetch;
    static LongSupplier clock = System::currentTimeMillis;
    private static boolean running;
    private static long generation;
    private static HttpsURLConnection connection;
    private static final ThreadLocal<Long> FETCH_TICKET = new ThreadLocal<>();

    public interface Callback { void onResult(Snapshot snapshot); }
    public static final class Entry {
        public final String tool, upstreamVersion, error;
        /** Last successful metadata check; zero means never. Not a compatibility test. */
        public final long checkedAt;
        Entry(String tool, String version, long checkedAt, String error) {
            this.tool = tool; this.upstreamVersion = version; this.checkedAt = checkedAt; this.error = error;
        }
    }
    public static final class Snapshot {
        public final Map<String, Entry> tools;
        public final boolean enabled, checking;
        public final long lastAttemptAt;
        Snapshot(Map<String, Entry> entries, boolean enabled, boolean checking, long attempted) {
            tools = Collections.unmodifiableMap(entries); this.enabled = enabled;
            this.checking = checking; lastAttemptAt = attempted;
        }
        public Entry get(String tool) { return tools.get(tool); }
    }
    private Z8ToolUpdates() {}
    private static SharedPreferences prefs(Context context) { return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE); }
    public static boolean enabled(Context context) { return prefs(context).getBoolean("enabled", false); }
    public static void setEnabled(Context context, boolean value) {
        prefs(context).edit().putBoolean("enabled", value).apply();
        if (!value) cancel();
    }
    public static Snapshot cached(Context context) {
        SharedPreferences values = prefs(context); Map<String, Entry> entries = new LinkedHashMap<>();
        for (String tool : TOOLS) {
            String version = values.getString(tool + ".version", "");
            if (!validVersion(tool, version)) version = "";
            String error = values.getString(tool + ".error", "");
            if (!error.isEmpty()) error = "Metadata check unavailable";
            entries.put(tool, new Entry(tool, version, values.getLong(tool + ".checked", 0), error));
        }
        synchronized (LOCK) { return new Snapshot(entries, values.getBoolean("enabled", false), running, values.getLong("attempt", 0)); }
    }
    static boolean due(boolean enabled, boolean force, long now, long last) {
        return force || enabled && (last <= 0 || now < last || now - last >= INTERVAL);
    }
    /** force is one explicit Check now action; it does not enable future checks. */
    public static void requestCheck(Context context, boolean force, Callback callback) {
        Context app = context.getApplicationContext(); long ticket;
        synchronized (LOCK) {
            SharedPreferences values = prefs(app);
            if (!force && !values.getBoolean("enabled", false)) { deliver(callback, cached(app)); return; }
            if (running) { if (callback != null) WAITING.add(callback); return; }
            if (!due(values.getBoolean("enabled", false), force, clock.getAsLong(), values.getLong("attempt", 0))) {
                deliver(callback, cached(app)); return;
            }
            // Persist the attempt, including failures, to avoid retrying on every app open.
            if (!values.edit().putLong("attempt", clock.getAsLong()).commit()) { deliver(callback, cached(app)); return; }
            running = true; ticket = ++generation;
            if (callback != null) WAITING.add(callback);
        }
        worker.execute(() -> check(app, ticket));
    }
    /** Called when the app is no longer visible; never schedules a replacement. */
    public static void cancel() {
        synchronized (LOCK) {
            generation++; running = false; WAITING.clear();
            if (connection != null) { connection.disconnect(); connection = null; }
        }
    }
    private static void check(Context context, long ticket) {
        for (String tool : TOOLS) {
            synchronized (LOCK) { if (generation != ticket) return; }
            String version = "", error = "";
            try {
                FETCH_TICKET.set(ticket);
                version = parse(tool, fetcher.get(endpoint(tool), tool.equals("claude") ? 128 : 2 * 1024 * 1024));
            }
            catch (Exception unavailable) { error = "Metadata check unavailable"; }
            finally { FETCH_TICKET.remove(); }
            synchronized (LOCK) {
                if (generation != ticket) return;
                SharedPreferences.Editor edit = prefs(context).edit().putString(tool + ".error", error);
                if (error.isEmpty()) edit.putString(tool + ".version", version).putLong(tool + ".checked", clock.getAsLong());
                edit.apply();
            }
        }
        List<Callback> callbacks;
        synchronized (LOCK) {
            if (generation != ticket) return;
            running = false; callbacks = new ArrayList<>(WAITING); WAITING.clear();
        }
        Snapshot result = cached(context);
        for (Callback callback : callbacks) deliver(callback, result);
    }
    private static void deliver(Callback callback, Snapshot value) { if (callback != null) MAIN.post(() -> callback.onResult(value)); }
    static String endpoint(String tool) {
        switch (tool) { case "codex": return CODEX; case "claude": return CLAUDE; case "node": return NODE; default: throw new IllegalArgumentException("Unknown tool"); }
    }
    public static boolean validVersion(String tool, String version) {
        if (version == null || tool == null) return false;
        return version.matches(tool.equals("node") ? "v24\\.(0|[1-9][0-9]{0,5})\\.(0|[1-9][0-9]{0,5})" : "(0|[1-9][0-9]{0,5})\\.(0|[1-9][0-9]{0,5})\\.(0|[1-9][0-9]{0,5})")
            && (tool.equals("node") || tool.equals("codex") || tool.equals("claude"));
    }
    public static boolean newer(String tool, String candidate, String installed) {
        if (!validVersion(tool, candidate) || !validVersion(tool, installed)) return false;
        String[] a = candidate.replaceFirst("^v", "").split("\\."), b = installed.replaceFirst("^v", "").split("\\.");
        for (int i = 0; i < 3; i++) { int order = Integer.compare(Integer.parseInt(a[i]), Integer.parseInt(b[i])); if (order != 0) return order > 0; }
        return false;
    }
    static String parse(String tool, String body) throws Exception {
        if (body == null || body.length() > 2 * 1024 * 1024) throw new IOException("Metadata size");
        String version;
        if (tool.equals("claude")) version = body.trim();
        else if (tool.equals("codex")) {
            JSONObject release = new JSONObject(body);
            if (!Boolean.FALSE.equals(release.get("draft")) || !Boolean.FALSE.equals(release.get("prerelease"))) throw new IOException("Not a stable release");
            String tag = release.getString("tag_name");
            if (!tag.startsWith("rust-v")) throw new IOException("Unsupported release tag");
            version = tag.substring(6);
            String name = "codex-package-aarch64-unknown-linux-musl.tar.gz";
            JSONArray assets = release.getJSONArray("assets"); int matching = 0;
            for (int i = 0; i < assets.length(); i++) {
                JSONObject asset = assets.getJSONObject(i);
                if (!name.equals(asset.getString("name"))) continue;
                String expected = "https://github.com/openai/codex/releases/download/" + tag + "/" + name;
                Object size = asset.get("size");
                if (!expected.equals(asset.getString("browser_download_url")) || !asset.getString("digest").matches("sha256:[0-9a-f]{64}")
                        || !(size instanceof Number) || ((Number) size).doubleValue() != ((Number) size).longValue()
                        || asset.getLong("size") <= 0 || asset.getLong("size") > 1024L * 1024 * 1024) throw new IOException("Unverified release artifact");
                matching++;
            }
            if (matching != 1) throw new IOException("Required package unavailable");
        } else if (tool.equals("node")) {
            JSONArray releases = new JSONArray(body); version = "";
            for (int i = 0; i < releases.length(); i++) {
                JSONObject item = releases.getJSONObject(i); String candidate = item.getString("version");
                if (!validVersion("node", candidate) || !(item.opt("lts") instanceof String) || item.getString("lts").isEmpty()) continue;
                JSONArray files = item.getJSONArray("files"); boolean arm64 = false;
                for (int j = 0; j < files.length(); j++) if ("linux-arm64".equals(files.getString(j))) arm64 = true;
                if (arm64 && (version.isEmpty() || newer("node", candidate, version))) version = candidate;
            }
        } else throw new IOException("Unknown tool");
        if (!validVersion(tool, version)) throw new IOException("Invalid release version");
        return version;
    }
    static String fetch(String address, int maximum) throws Exception {
        if (!address.equals(CODEX) && !address.equals(CLAUDE) && !address.equals(NODE)) throw new IOException("Unsupported metadata endpoint");
        HttpsURLConnection request;
        synchronized (LOCK) {
            requireCurrentFetch();
            request = (HttpsURLConnection) new URL(address).openConnection();
            try { requireCurrentFetch(); }
            catch (IOException cancelled) { request.disconnect(); throw cancelled; }
            connection = request;
        }
        request.setInstanceFollowRedirects(false); request.setConnectTimeout(10000); request.setReadTimeout(10000);
        request.setRequestProperty("User-Agent", "Z8-release-metadata/1");
        request.setRequestProperty("Accept", "application/json, text/plain");
        request.setRequestProperty("Accept-Encoding", "identity");
        request.setUseCaches(false);
        long deadline = System.nanoTime() + 20_000_000_000L;
        try {
            synchronized (LOCK) { requireCurrentFetch(); }
            if (request.getResponseCode() != 200 || request.getContentLengthLong() > maximum) throw new IOException("Metadata response unavailable");
            try (InputStream input = request.getInputStream(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192]; int count;
                while ((count = input.read(buffer)) != -1) {
                    synchronized (LOCK) { requireCurrentFetch(); }
                    if (System.nanoTime() > deadline || output.size() + count > maximum) throw new IOException("Metadata response limit");
                    output.write(buffer, 0, count);
                }
                return new String(output.toByteArray(), StandardCharsets.UTF_8);
            }
        } finally { request.disconnect(); synchronized (LOCK) { if (connection == request) connection = null; } }
    }
    private static void requireCurrentFetch() throws IOException {
        Long ticket = FETCH_TICKET.get();
        if (ticket != null && ticket != generation) throw new IOException("Metadata check cancelled");
    }
}
