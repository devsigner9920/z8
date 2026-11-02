package com.termux.app;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import com.termux.R;
import org.json.JSONObject;
import java.text.DateFormat;
import java.util.Date;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Project → terminal → observed event. Opening an event never supplies a CLI response. */
public final class Z8AttentionActivity extends Activity {
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private Z8PanelUi ui;
    private LinearLayout groups;
    private TextView summary, clear;
    private DateFormat dateFormat;
    private boolean visible, loading;
    private int generation;
    private String fingerprint = "";
    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if (!visible || isFinishing() || isDestroyed()) return;
            load(); main.postDelayed(this, 2000);
        }
    };

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        String eventId = getIntent().getStringExtra(Z8AttentionBridge.EXTRA_EVENT);
        if (Z8AttentionInbox.openEvent(this, eventId)) { finish(); return; }
        build();
    }

    @Override public void onResume() {
        super.onResume();
        if (isFinishing()) return;
        if (ui == null || !ui.palette.id.equals(Z8Theme.selected(this).id)) build();
        visible = true; main.removeCallbacks(poll); main.post(poll);
    }
    @Override public void onPause() { visible = false; generation++; main.removeCallbacks(poll); super.onPause(); }
    @Override public void onDestroy() { generation++; main.removeCallbacksAndMessages(null); io.shutdownNow(); super.onDestroy(); }

    private void build() {
        ui = new Z8PanelUi(this, "알림");
        dateFormat = DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT);
        clear = ui.text("기록 정리", 12, ui.style.muted, false); clear.setGravity(Gravity.CENTER);
        clear.setPadding(ui.dp(12), 0, ui.dp(4), 0); ui.control(clear);
        clear.setContentDescription("읽은 알림과 종료된 세션의 기록 정리");
        clear.setTooltipText("읽은 알림과 종료된 세션의 기록만 정리해요.");
        clear.setOnClickListener(view -> clearHistory());
        ui.toolbar.addView(clear, new LinearLayout.LayoutParams(-2, ui.dp(48)));
        summary = ui.text("알림을 불러오는 중…", 13, ui.style.muted, false);
        summary.setPadding(ui.dp(8), ui.dp(12), ui.dp(8), ui.dp(8)); ui.content.addView(summary);
        groups = ui.column(); ui.content.addView(groups, new LinearLayout.LayoutParams(-1, -2));
        fingerprint = "";
    }

    private void clearHistory() {
        if (loading) return;
        loading = true; clear.setEnabled(false);
        int token = generation;
        io.execute(() -> {
            Z8AttentionBridge.clearHistory(getApplicationContext());
            main.post(() -> {
                loading = false;
                if (isDestroyed() || isFinishing() || token != generation) return;
                clear.setEnabled(true); fingerprint = ""; load();
            });
        });
    }

    private void load() {
        if (loading) return;
        loading = true;
        int token = generation;
        io.execute(() -> {
            List<JSONObject> records = Z8AttentionBridge.snapshot(getApplicationContext());
            Set<String> openable = Z8AttentionBridge.openableEventIds();
            List<Z8AttentionInbox.Project> projects = Z8AttentionInbox.group(records, openable::contains);
            StringBuilder signature = new StringBuilder(records.toString());
            for (Z8AttentionInbox.Project project : projects) for (Z8AttentionInbox.Session session : project.sessions)
                for (Z8AttentionInbox.Item item : session.items) signature.append(item.id).append(item.openable);
            main.post(() -> {
                loading = false;
                if (!visible || isDestroyed() || isFinishing() || token != generation) return;
                clear.setEnabled(true);
                if (fingerprint.equals(signature.toString())) return;
                fingerprint = signature.toString(); render(projects);
            });
        });
    }

    private void render(List<Z8AttentionInbox.Project> projects) {
        int scrollY = ui.scroll.getScrollY();
        View focused = getCurrentFocus(); Object focusedTag = focused == null ? null : focused.getTag();
        boolean restoreFocus = focusedTag instanceof String && !ui.scroll.isInTouchMode();
        groups.removeAllViews();
        int unseen = 0, total = 0;
        for (Z8AttentionInbox.Project project : projects) {
            unseen += project.unseen;
            for (Z8AttentionInbox.Session session : project.sessions) total += session.items.size();
        }
        summary.setText(total == 0 ? "권한 요청과 질문, 작업 완료 알림을 모아 보여드려요."
            : (unseen > 0 ? "미확인 " + unseen + "개 · " : "") + "알림을 누르면 해당 터미널로 이동해요.");
        clear.setVisibility(total == 0 ? View.GONE : View.VISIBLE);
        if (total == 0) {
            TextView empty = ui.text("아직 알림이 없어요", 17, ui.style.text, false);
            empty.setPadding(ui.dp(8), ui.dp(64), ui.dp(8), ui.dp(12)); groups.addView(empty);
        }
        for (Z8AttentionInbox.Project project : projects) {
            LinearLayout projectHeading = ui.row(); projectHeading.setGravity(Gravity.CENTER_VERTICAL);
            projectHeading.setPadding(ui.dp(8), ui.dp(28), ui.dp(8), ui.dp(12));
            projectHeading.addView(ui.icon(R.drawable.z8_ic_folder_open, 18, ui.style.muted));
            TextView projectName = ui.text(project.name, 15, ui.style.text, true);
            projectName.setPadding(ui.dp(10), 0, 0, 0); projectName.setAccessibilityHeading(true);
            projectHeading.addView(projectName, new LinearLayout.LayoutParams(0, -2, 1));
            if (project.unseen > 0) projectHeading.addView(ui.text(Integer.toString(project.unseen), 12, ui.style.accent, true));
            groups.addView(projectHeading);
            for (Z8AttentionInbox.Session session : project.sessions) {
                LinearLayout terminalHeading = ui.row(); terminalHeading.setGravity(Gravity.CENTER_VERTICAL);
                terminalHeading.setPadding(ui.dp(16), ui.dp(12), ui.dp(8), ui.dp(6));
                terminalHeading.addView(ui.icon(R.drawable.z8_ic_terminal, 16, ui.style.muted));
                TextView name = ui.text(session.name, 13, ui.style.muted, true);
                name.setPadding(ui.dp(8), 0, 0, 0); name.setAccessibilityHeading(true);
                terminalHeading.addView(name, new LinearLayout.LayoutParams(-1, -2)); groups.addView(terminalHeading);
                for (Z8AttentionInbox.Item item : session.items) addItem(project, session, item);
            }
        }
        if (total > 0) {
            TextView note = ui.text("승인과 답변은 터미널에서 진행하세요. 알림 기록만으로 현재 대기 여부를 판단하지 않아요.", 12, ui.style.muted, false);
            note.setPadding(ui.dp(8), ui.dp(28), ui.dp(8), 0); note.setLineSpacing(ui.dp(4), 1); groups.addView(note);
        }
        ui.scroll.post(() -> { if (!isDestroyed()) ui.scroll.scrollTo(0, scrollY); });
        if (restoreFocus) { View replacement = groups.findViewWithTag(focusedTag); if (replacement != null && replacement.isEnabled()) replacement.requestFocus(); }
    }

    private void addItem(Z8AttentionInbox.Project project, Z8AttentionInbox.Session session, Z8AttentionInbox.Item item) {
        LinearLayout row = ui.column(); row.setMinimumHeight(ui.dp(72)); row.setPadding(ui.dp(40), ui.dp(13), ui.dp(8), ui.dp(13));
        row.setTag("event/" + item.id);
        LinearLayout titleLine = ui.row(); titleLine.setGravity(Gravity.CENTER_VERTICAL);
        titleLine.addView(ui.text(item.title, 14, item.openable ? ui.style.text : ui.style.muted, item.unseenRequest), new LinearLayout.LayoutParams(0, -2, 1));
        TextView status = ui.text(item.status(), 11, item.unseenRequest ? ui.style.accent : ui.style.muted, false);
        status.setPadding(ui.dp(12), 0, 0, 0); titleLine.addView(status); row.addView(titleLine);
        String date = item.observedAt > 0 ? dateFormat.format(new Date(item.observedAt)) : "시간 기록 없음";
        TextView detail = ui.text(item.provider + " · " + date, 12, ui.style.muted, false); detail.setPadding(0, ui.dp(7), 0, 0); row.addView(detail);
        if ("BLOCKED".equals(item.delivery) || "FAILED".equals(item.delivery)) {
            TextView delivery = ui.text("시스템 알림으로 전달되지 않아 여기에 보관했어요.", 12, ui.style.muted, false);
            delivery.setPadding(0, ui.dp(5), 0, 0); row.addView(delivery);
        }
        row.setContentDescription(project.name + " / " + session.name + ", " + item.title + ", " + item.provider + ", " + date + ", " + item.status()
            + (item.openable ? ", 해당 터미널 열기" : ", 다시 열 수 없음"));
        row.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
        if (item.openable) {
            ui.control(row);
            row.setOnClickListener(view -> {
                if (Z8AttentionInbox.open(this, item)) finish();
                else { Toast.makeText(this, "이 터미널은 종료되어 열 수 없어요.", Toast.LENGTH_SHORT).show(); fingerprint = ""; load(); }
            });
        } else { row.setEnabled(false); row.setFocusable(false); }
        groups.addView(row, new LinearLayout.LayoutParams(-1, -2));
    }
}
