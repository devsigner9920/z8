package com.termux.app;

import com.termux.shared.termux.shell.command.runner.terminal.TermuxSession;
import com.termux.terminal.TerminalSession;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.WeakHashMap;
import java.math.BigInteger;

/** A display snapshot of this service's live PTY objects. No history or terminal output is read. */
public final class Z8SessionCatalog {
    private static final String NAMING_PREFS = "z8.terminal-names";
    private static final Map<String, BigInteger> HIGH_WATER = new HashMap<>();
    private static final Map<TerminalSession, String> LEGACY_NAMES = new WeakHashMap<>();
    private Z8SessionCatalog() {}

    public static final class Entry {
        public final TerminalSession session;
        public final String handle;
        public final String projectId;
        public final String projectName;
        public final String title;
        /** Launch purpose; this does not assert that an AI is currently working. */
        public final String tool;
        /** The PTY process is running. This is not an agent-task or connection health signal. */
        public final boolean running;
        public final boolean selected;

        private Entry(TermuxService service, TerminalSession session, TerminalSession current) {
            this.session = session;
            handle = session.mHandle;
            Z8SessionOrigin origin = Z8SessionOrigin.of(session);
            projectId = origin == null || origin.projectId == null ? "" : origin.projectId;
            projectName = origin == null ? Z8Text.text("Device shell", "기기 셸") : displayText(origin.projectName, 80, Z8Text.text("Project", "프로젝트"));
            tool = origin == null ? "Terminal" : actionLabel(origin.action);
            title = sessionTitle(service, session, origin, tool);
            running = session.isRunning();
            selected = session == current;
        }
    }

    /** Call on the main/UI thread, like the service's session mutations. Service order is preserved. */
    public static List<Entry> snapshot(TermuxService service, TerminalSession current) {
        if (service == null) return Collections.emptyList();
        List<Entry> entries = new ArrayList<>();
        for (TermuxSession wrapper : sessions(service)) {
            if (wrapper == null) continue;
            TerminalSession session = wrapper.getTerminalSession();
            if (session != null) entries.add(new Entry(service, session, current));
        }
        return Collections.unmodifiableList(entries);
    }

    /** Recheck immediately before selecting/renaming/ending an entry held by an older view. */
    public static boolean contains(TermuxService service, TerminalSession session) {
        if (service == null || session == null) return false;
        for (TermuxSession wrapper : sessions(service)) {
            if (wrapper != null && wrapper.getTerminalSession() == session) return true;
        }
        return false;
    }

    private static List<TermuxSession> sessions(TermuxService service) {
        synchronized (service) {
            return new ArrayList<>(service.getTermuxSessions());
        }
    }

    private static String actionLabel(String action) {
        if (action == null || "remote-shell".equals(action)) return "Terminal";
        switch (action) {
            case "claude": return "Claude Code";
            case "codex": return "Codex";
            case "setup-tools": return Z8Text.text("Install development tools", "개발 도구 설치");
            case "setup-codex": return Z8Text.text("Install Codex", "Codex 설치");
            case "setup-claude": return Z8Text.text("Install Claude", "Claude 설치");
            case "github-auth": return Z8Text.text("GitHub sign-in", "GitHub 로그인");
            case "hooks-codex": return Z8Text.text("Codex notifications", "Codex 알림");
            case "hooks-claude": return Z8Text.text("Claude notifications", "Claude 알림");
            default: return "Terminal";
        }
    }

    /** English generated-name tokens are stable even when the display language changes. */
    private static String englishActionLabel(String action) {
        if (action == null || "remote-shell".equals(action)) return "Terminal";
        switch (action) {
            case "claude": return "Claude Code";
            case "codex": return "Codex";
            case "setup-tools": return "Install development tools";
            case "setup-codex": return "Install Codex";
            case "setup-claude": return "Install Claude";
            case "github-auth": return "GitHub sign-in";
            case "hooks-codex": return "Codex notifications";
            case "hooks-claude": return "Claude notifications";
            default: return "Terminal";
        }
    }

    /** Exact historical generated-name tokens; never rewrite stored user names. */
    private static String historicalActionLabel(String action) {
        if (action == null || "remote-shell".equals(action)) return "Terminal";
        switch (action) {
            case "setup-tools": return "개발 도구 설치";
            case "setup-codex": return "Codex 설치";
            case "setup-claude": return "Claude 설치";
            case "github-auth": return "GitHub 로그인";
            case "hooks-codex": return "Codex 알림";
            case "hooks-claude": return "Claude 알림";
            default: return actionLabel(action);
        }
    }

    /** Allocate at PTY creation; a deleted/renamed Terminal never makes its number reusable. */
    static String nextTerminalName(TermuxService service, String projectId) {
        String key = projectId == null ? "" : projectId;
        BigInteger observed = BigInteger.ZERO;
        // Do not take the service monitor while holding the naming monitor.
        if (service != null) for (TermuxSession wrapper : sessions(service)) {
            if (wrapper == null || wrapper.getTerminalSession() == null) continue;
            TerminalSession session = wrapper.getTerminalSession();
            Z8SessionOrigin origin = Z8SessionOrigin.of(session);
            String owner = origin == null || origin.projectId == null ? "" : origin.projectId;
            if (key.equals(owner)) observed = observed.max(number(session.mSessionName));
        }
        synchronized (HIGH_WATER) {
            BigInteger previous = HIGH_WATER.getOrDefault(key, BigInteger.ZERO).max(observed);
            android.content.SharedPreferences preferences = service == null ? null
                : service.getApplicationContext().getSharedPreferences(NAMING_PREFS, android.content.Context.MODE_PRIVATE);
            if (preferences != null) previous = previous.max(number("Terminal " + preferences.getString(key, "0")));
            BigInteger next = previous.add(BigInteger.ONE);
            HIGH_WATER.put(key, next);
            if (preferences != null) preferences.edit().putString(key, next.toString()).apply();
            return "Terminal " + next;
        }
    }

    private static BigInteger number(String name) {
        if (name == null || !name.matches("Terminal [1-9][0-9]{0,95}")) return BigInteger.ZERO;
        return new BigInteger(name.substring("Terminal ".length()));
    }

    private static String defaultName(TermuxService service, TerminalSession session, Z8SessionOrigin origin) {
        synchronized (LEGACY_NAMES) {
            String title = LEGACY_NAMES.get(session);
            if (title != null) return title;
        }
        // The service can call notification-title code while holding its own
        // monitor. Do not hold a naming monitor while acquiring that monitor.
        String allocated = nextTerminalName(service, origin == null ? "" : origin.projectId);
        synchronized (LEGACY_NAMES) {
            String existing = LEGACY_NAMES.get(session);
            if (existing != null) return existing;
            LEGACY_NAMES.put(session, allocated);
            return allocated;
        }
    }

    /** One normalized display title for the tab, inbox and private notification. */
    static String title(TerminalSession session) {
        Z8SessionOrigin origin = Z8SessionOrigin.of(session);
        return sessionTitle(null, session, origin, origin == null ? "Terminal" : actionLabel(origin.action));
    }

    private static String sessionTitle(TermuxService service, TerminalSession session, Z8SessionOrigin origin, String tool) {
        String name = session.mSessionName;
        boolean terminal = origin == null || origin.action == null || "remote-shell".equals(origin.action);
        if (origin != null) {
            // The Korean fallback belongs to the old stored-name format, not UI text.
            String project = origin.projectName == null ? "프로젝트" : origin.projectName;
            String generatedLabel = terminal ? "Linux" : englishActionLabel(origin.action);
            String historicalLabel = terminal ? "Linux" : historicalActionLabel(origin.action);
            // Only the exact historical generated label is normalized. A user rename
            // containing the project name (or literally "Shell") remains user text.
            if ((project + " · " + generatedLabel).equals(name)
                    || (project + " · " + historicalLabel).equals(name)
                    || terminal && (project + " · Shell").equals(name))
                return terminal ? defaultName(service, session, origin) : tool;
        }
        String display = displayText(name, 96, "");
        return display.isEmpty() ? terminal ? defaultName(service, session, origin) : tool : display;
    }

    static String displayText(String value, int limit, String fallback) {
        if (value == null) return fallback;
        StringBuilder result = new StringBuilder();
        int count = 0;
        for (int offset = 0; offset < value.length();) {
            int codePoint = value.codePointAt(offset);
            offset += Character.charCount(codePoint);
            int kind = Character.getType(codePoint);
            if (Character.isISOControl(codePoint) || kind == Character.FORMAT
                    || kind == Character.SURROGATE || kind == Character.LINE_SEPARATOR
                    || kind == Character.PARAGRAPH_SEPARATOR) continue;
            if (count == limit) {
                int last = result.offsetByCodePoints(result.length(), -1);
                result.setLength(last);
                result.append('…');
                break;
            }
            result.appendCodePoint(codePoint);
            count++;
        }
        String text = result.toString().trim();
        return text.isEmpty() ? fallback : text;
    }
}
