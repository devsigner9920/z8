package com.termux.app;

import android.content.Context;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.function.Predicate;

/** Display-only hierarchy. An observed request is never an inferred pending approval. */
final class Z8AttentionInbox {
    static final class Item {
        final String id, title, provider, delivery, sessionKey;
        final long observedAt, seenAt;
        final boolean openable, finished, unseenRequest;

        Item(JSONObject source, Predicate<String> canOpen) {
            id = source.optString("id");
            String kind = source.optString("kind");
            title = "permission".equals(kind) ? Z8Text.text("Permission request", "권한 요청") : "question".equals(kind) ? Z8Text.text("Question", "답변 요청")
                : "plan".equals(kind) ? Z8Text.text("Plan review request", "계획 검토 요청") : "finished".equals(kind) ? Z8Text.text("Completion notification", "작업 완료 알림") : Z8Text.text("Notification", "알림");
            String origin = source.optString("provider");
            provider = "claude".equals(origin) ? "Claude Code" : "codex".equals(origin) ? "Codex"
                : "diagnostic".equals(origin) ? Z8Text.text("Diagnostic test", "진단 테스트") : "CLI";
            observedAt = Math.max(0, source.optLong("observedAt"));
            seenAt = Math.max(0, source.optLong("seenAt"));
            finished = "finished".equals(kind);
            openable = !id.isEmpty() && !"STALE".equals(source.optString("state")) && canOpen.test(id);
            boolean request = "permission".equals(kind) || "question".equals(kind) || "plan".equals(kind);
            unseenRequest = openable && request && seenAt == 0 && "OBSERVED".equals(source.optString("state"));
            delivery = source.optString("deliveryState");
            String handle = source.optString("sessionHandle");
            String launch = source.optString("launchId");
            sessionKey = !handle.isEmpty() ? "session:" + handle : !launch.isEmpty() ? "launch:" + launch : "event:" + id;
        }

        String status() {
            return !openable ? Z8Text.text("Session ended", "세션 종료") : unseenRequest ? Z8Text.text("Unread", "미확인") : seenAt > 0 ? Z8Text.text("Read", "읽음") : finished ? Z8Text.text("Completion record", "완료 기록") : Z8Text.text("Notification", "알림");
        }
    }

    static final class Session {
        final String key, name;
        final List<Item> items = new ArrayList<>();
        Session(String key, String name) { this.key = key; this.name = name; }
    }

    static final class Project {
        final String key, name;
        final List<Session> sessions = new ArrayList<>();
        private final LinkedHashMap<String, Session> sessionsByKey = new LinkedHashMap<>();
        int unseen;
        Project(String key, String name) { this.key = key; this.name = name; }
    }

    static List<Project> group(List<JSONObject> source, Predicate<String> canOpen) {
        List<JSONObject> sorted = new ArrayList<>(source);
        sorted.sort(Comparator.comparingLong((JSONObject item) -> item.optLong("observedAt")).reversed());
        LinkedHashMap<String, Project> projects = new LinkedHashMap<>();
        for (JSONObject record : sorted) {
            Item item = new Item(record, canOpen);
            if (item.id.isEmpty()) continue;
            String name = Z8SessionCatalog.displayText(record.optString("projectName"), 80, Z8Text.text("Previous project", "이전 프로젝트"));
            String id = record.optString("projectId");
            // Old persisted records have no project ID. Keep them separate from current IDs.
            String key = record.has("projectId") ? (id.isEmpty() ? "device" : "project:" + id) : "history:" + name;
            Project project = projects.get(key);
            if (project == null) { project = new Project(key, name); projects.put(key, project); }
            Session session = project.sessionsByKey.get(item.sessionKey);
            if (session == null) {
                session = new Session(item.sessionKey, Z8SessionCatalog.displayText(record.optString("sessionName"), 96, Z8Text.text("Previous terminal", "이전 터미널")));
                project.sessionsByKey.put(item.sessionKey, session);
                project.sessions.add(session);
            }
            session.items.add(item);
            if (item.unseenRequest) project.unseen++;
        }
        return Collections.unmodifiableList(new ArrayList<>(projects.values()));
    }

    /** Revalidate on tap; only the existing event route may select its original PTY. */
    static boolean open(Context context, Item item) {
        return item != null && item.openable && openEvent(context, item.id);
    }

    static boolean openEvent(Context context, String eventId) {
        if (eventId == null || eventId.isEmpty() || !Z8AttentionBridge.canOpen(eventId)) return false;
        context.startActivity(Z8AttentionBridge.sessionIntent(context, eventId));
        return true;
    }

    private Z8AttentionInbox() {}
}
