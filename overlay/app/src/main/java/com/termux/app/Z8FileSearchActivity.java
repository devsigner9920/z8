package com.termux.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.text.InputFilter;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

/** Explicit read-only filename search, with no per-keystroke filesystem work. */
public final class Z8FileSearchActivity extends Activity {
    public static final int REQUEST_OPEN = 8301;
    public static final String EXTRA_PROJECT_ID = "dev.devsigner.z8.SEARCH_PROJECT_ID";
    public static final String EXTRA_PATH = "dev.devsigner.z8.SEARCH_PATH";
    public static final String EXTRA_DIRECTORY = "dev.devsigner.z8.SEARCH_DIRECTORY";
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final AtomicBoolean cancelled = new AtomicBoolean();
    private Future<?> pending;
    private Z8Theme.Palette palette;
    private String projectId;
    private String projectName = "프로젝트";
    private String query = "";
    private String searchedQuery = "";
    private String failure = "";
    private boolean busy;
    private boolean restoredSearch;
    private Z8FileSearch.Result result;
    private EditText input;

    public static Intent intent(Context context, String projectId) {
        return new Intent(context, Z8FileSearchActivity.class).putExtra(EXTRA_PROJECT_ID, projectId);
    }

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        projectId = getIntent().getStringExtra(EXTRA_PROJECT_ID);
        if (state != null) {
            query = state.getString("query", "");
            searchedQuery = state.getString("searchedQuery", "");
            projectName = state.getString("projectName", "프로젝트");
            restoredSearch = !searchedQuery.isEmpty();
        }
        render();
        io.execute(() -> {
            try {
                String name = new Z8Projects(getApplicationContext()).open(projectId).name;
                runOnUiThread(() -> { if (!isDestroyed()) { rememberQuery(); projectName = name; render(); } });
            } catch (Exception error) { /* Search presents the actionable project error. */ }
        });
    }

    @Override protected void onResume() {
        super.onResume();
        if (palette != null && !palette.id.equals(Z8Theme.selected(this).id)) { rememberQuery(); render(); }
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        rememberQuery();
        state.putString("query", query);
        state.putString("searchedQuery", searchedQuery);
        state.putString("projectName", projectName);
        super.onSaveInstanceState(state);
    }

    @Override protected void onDestroy() {
        cancelled.set(true);
        if (pending != null) pending.cancel(true);
        io.shutdownNow();
        super.onDestroy();
    }

    private void rememberQuery() { if (input != null) query = input.getText().toString(); }

    private void search() {
        if (busy) return;
        rememberQuery();
        if (query.trim().isEmpty()) { failure = "검색어를 입력해 주세요."; render(); return; }
        final String requestedQuery = query;
        final Context context = getApplicationContext();
        final String selectedId = projectId;
        busy = true; failure = ""; result = null; searchedQuery = query; restoredSearch = false;
        render();
        pending = io.submit(() -> {
            try {
                Z8Projects.Project selected = new Z8Projects(context).open(selectedId);
                Z8FileSearch.Result found = Z8FileSearch.search(selected.source, requestedQuery, cancelled::get);
                if (cancelled.get()) return;
                runOnUiThread(() -> {
                    if (isDestroyed() || cancelled.get()) return;
                    projectName = selected.name; result = found; busy = false; render();
                });
            } catch (Exception error) {
                if (cancelled.get()) return;
                String message = error.getMessage() == null ? "프로젝트 파일을 검색하지 못했습니다." : error.getMessage();
                runOnUiThread(() -> {
                    if (isDestroyed() || cancelled.get()) return;
                    failure = message; busy = false; render();
                });
            }
        });
    }

    private void render() {
        palette = Z8Theme.selected(this);
        Z8Theme.applyChrome(this, palette);
        setTitle("z8 · 파일 검색");
        LinearLayout outer = column();
        outer.setGravity(Gravity.CENTER_HORIZONTAL);
        outer.setBackgroundColor(palette.background);
        LinearLayout body = column();
        body.setPadding(dp(20), dp(18), dp(20), dp(12));
        int width = getResources().getConfiguration().screenWidthDp > 900 ? dp(900) : -1;
        outer.addView(body, new LinearLayout.LayoutParams(width, -1));
        TextView heading = text(projectName + " / 파일 검색", 24, palette.foreground);
        heading.setTypeface(Typeface.DEFAULT, Typeface.BOLD); body.addView(heading);
        add(body, text("파일명·상대 경로에서 찾기 · 내용 검색 제외", 13, palette.accent), 8);
        input = new EditText(this);
        input.setTextColor(palette.foreground); input.setHintTextColor(palette.secondary);
        input.setSingleLine(true); input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        input.setFilters(new InputFilter[] { new InputFilter.LengthFilter(Z8FileSearch.MAX_QUERY) });
        input.setHint("예: README · src/main · 설정"); input.setText(query);
        input.setSelection(input.length()); input.setEnabled(!busy);
        add(body, input, 18);
        LinearLayout actions = new LinearLayout(this); actions.setOrientation(LinearLayout.HORIZONTAL);
        actions.addView(button("‹ 프로젝트로", this::finish), new LinearLayout.LayoutParams(0, dp(48), 1));
        Button submit = button(result == null && !restoredSearch ? "검색" : "다시 검색", this::search);
        submit.setEnabled(!busy); submit.setAlpha(busy ? .45f : 1f);
        LinearLayout.LayoutParams submitParams = new LinearLayout.LayoutParams(0, dp(48), 1);
        submitParams.leftMargin = dp(8); actions.addView(submit, submitParams); add(body, actions, 10);
        add(body, text("제외 폴더: " + Z8FileSearch.EXCLUDED + "\n링크 제외 · 최대 200건 / 20,000항목 / 깊이 32 / 3초", 12, palette.secondary), 14);
        String status = busy ? "검색 중…" : !failure.isEmpty() ? failure : result != null ? summary(result)
            : restoredSearch ? "화면이 변경되었습니다. 다시 검색하면 최신 파일 목록을 확인할 수 있습니다."
            : "검색어를 입력하고 검색을 누르세요.";
        add(body, text(status, 14, failure.isEmpty() ? palette.secondary : palette.accent), 12);
        if (result != null && result.incomplete()) add(body, text(incomplete(result), 13, palette.accent), 8);
        ListView list = new ListView(this); list.setDivider(null);
        list.setAdapter(new BaseAdapter() {
            @Override public int getCount() { return result == null ? 0 : result.matches.size(); }
            @Override public Object getItem(int position) { return result.matches.get(position); }
            @Override public long getItemId(int position) { return position; }
            @Override public View getView(int position, View reused, ViewGroup parent) {
                TextView view = reused instanceof TextView ? (TextView) reused : text("", 15, palette.foreground);
                Z8FileSearch.Match match = result.matches.get(position);
                view.setText((match.directory ? "폴더  " : "파일  ") + match.relative);
                view.setPadding(dp(4), dp(14), dp(4), dp(14)); view.setMinHeight(dp(54));
                return view;
            }
        });
        list.setOnItemClickListener((parent, view, position, id) -> {
            if (busy || result == null) return;
            Z8FileSearch.Match match = result.matches.get(position);
            setResult(RESULT_OK, new Intent().putExtra(EXTRA_PROJECT_ID, projectId)
                .putExtra(EXTRA_PATH, match.relative).putExtra(EXTRA_DIRECTORY, match.directory));
            finish();
        });
        LinearLayout.LayoutParams listParams = new LinearLayout.LayoutParams(-1, 0, 1);
        listParams.topMargin = dp(12); body.addView(list, listParams);
        setContentView(outer);
    }

    private String summary(Z8FileSearch.Result found) {
        return "결과 " + found.matches.size() + "개 · 확인 " + found.visited + "항목 · " + found.elapsedMillis
            + "ms\n제외 폴더 " + found.ignoredDirectories + "개 · 링크 " + found.ignoredLinks + "개";
    }

    private String incomplete(Z8FileSearch.Result found) {
        StringBuilder text = new StringBuilder("일부 결과만 표시됩니다: ");
        for (Z8FileSearch.Limit limit : found.limits) {
            if (text.charAt(text.length() - 1) != ' ') text.append(" · ");
            switch (limit) {
                case DEPTH: text.append("깊이 제한"); break;
                case VISITED: text.append("항목 제한"); break;
                case RESULTS: text.append("결과 제한"); break;
                case TIME: text.append("시간 제한"); break;
                case CANCELLED: text.append("검색 취소"); break;
                case UNSUPPORTED_NAME: text.append("지원하지 않는 이름"); break;
                case UNREADABLE: text.append("읽지 못한 경로"); break;
            }
        }
        return text.append(". 검색어를 구체적으로 입력하거나 폴더를 직접 열어 주세요.").toString();
    }

    private LinearLayout column() { LinearLayout view = new LinearLayout(this); view.setOrientation(LinearLayout.VERTICAL); return view; }
    private TextView text(String value, int size, int color) { TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color); return view; }
    private Button button(String value, Runnable action) {
        return Z8Ui.button(this, palette, value, action);
    }
    private void add(LinearLayout parent, View child, int margin) { LinearLayout.LayoutParams parameters = new LinearLayout.LayoutParams(-1, -2); parameters.topMargin = dp(margin); parent.addView(child, parameters); }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
