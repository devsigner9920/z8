package com.termux.app;

import com.termux.terminal.TerminalSession;
import java.util.Map;
import java.util.WeakHashMap;

/** In-memory provenance for live service-owned PTYs, never a process-restart claim. */
public final class Z8SessionOrigin {
    private static final Map<TerminalSession, Z8SessionOrigin> ORIGINS = new WeakHashMap<>();
    public final String projectId;
    public final String projectName;
    /** Requested launch action, not an inference about what the shell is currently doing. */
    public final String action;
    private Z8SessionOrigin(String id, String name, String action) {
        projectId = id; projectName = name; this.action = action;
    }
    public static synchronized void remember(TerminalSession session, String id, String name) {
        remember(session, id, name, null);
    }
    public static synchronized void remember(TerminalSession session, String id, String name, String action) {
        if (session != null) ORIGINS.put(session, new Z8SessionOrigin(id, name, action));
    }
    public static synchronized Z8SessionOrigin of(TerminalSession session) { return ORIGINS.get(session); }
}
