package com.termux.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import com.termux.BuildConfig;

/** Application worker owns rootfs installation. Setup is a visible, service-owned guest session. */
public final class Z8EnvironmentActivity extends Activity {
    private static final String PROJECT_ID = "dev.devsigner.z8.ENVIRONMENT_PROJECT_ID";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private String projectId;
    private String projectName = Z8Text.text("Project", "프로젝트");
    private String rendered = "";
    private boolean prepareToolsAfterRootfs;
    private boolean resumed;
    private int restoredScroll;
    private ScrollView scroll;
    private Z8Theme.Palette palette;
    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if (isFinishing() || isDestroyed() || !resumed) return;
            renderIfChanged();
            Z8Guest.State state = Z8Guest.state(getApplicationContext(), projectId);
            if (prepareToolsAfterRootfs && state.phase == Z8Guest.Phase.READY) {
                prepareToolsAfterRootfs = false;
                openTerminal();
            } else if (state.phase == Z8Guest.Phase.READY && state.hasRootfs && Z8Guest.needsReadinessRefresh(projectId)) {
                // Cached for 60s; setup completion invalidates it even while this page is open.
                Z8Guest.refresh(getApplicationContext(), projectId);
            }
            handler.postDelayed(this, 500);
        }
    };

    public static Intent intent(Context context, String projectId) {
        return new Intent(context, Z8EnvironmentActivity.class).putExtra(PROJECT_ID, projectId);
    }

    @Override protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        projectId = getIntent().getStringExtra(PROJECT_ID);
        try { projectName = new Z8Projects(this).open(projectId).name; }
        catch (Exception ignored) { /* The state screen supplies the validation error. */ }
        if (saved != null) {
            prepareToolsAfterRootfs = saved.getBoolean("prepare_tools");
            restoredScroll = saved.getInt("scroll");
        }
        setTitle(projectName + Z8Text.text(" · Linux environment", " · Linux 환경"));
        refreshUnlessContinuingPreparation();
        renderIfChanged();
    }
    @Override protected void onSaveInstanceState(Bundle saved) {
        saved.putBoolean("prepare_tools", prepareToolsAfterRootfs);
        saved.putInt("scroll", scroll == null ? 0 : scroll.getScrollY());
        super.onSaveInstanceState(saved);
    }
    @Override protected void onResume() {
        super.onResume(); resumed = true;
        refreshUnlessContinuingPreparation();
        handler.removeCallbacks(poll); handler.post(poll);
    }
    private void refreshUnlessContinuingPreparation() {
        if (prepareToolsAfterRootfs && Z8Guest.state(getApplicationContext(), projectId).hasRootfs) return;
        Z8Guest.refresh(getApplicationContext(), projectId);
    }
    @Override protected void onPause() {
        resumed = false; handler.removeCallbacks(poll); super.onPause();
    }

    private void renderIfChanged() {
        Z8Guest.State state = Z8Guest.state(getApplicationContext(), projectId);
        Z8Theme.Palette selected = Z8Theme.selected(this);
        String signature = selected.id + ":" + Z8Text.language() + ":" + state.phase + ":" + state.progress + ":" + state.message
            + ":" + state.toolsChecked + ":" + state.versions + ":" + state.toolsCheckIncomplete;
        if (signature.equals(rendered)) return;
        int position = scroll == null ? restoredScroll : scroll.getScrollY();
        rendered = signature; palette = selected;
        Z8Theme.applyChrome(this, palette);
        scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.setBackgroundColor(palette.background);
        LinearLayout frame = new LinearLayout(this); frame.setOrientation(LinearLayout.VERTICAL);
        frame.setGravity(android.view.Gravity.CENTER_HORIZONTAL); scroll.addView(frame);
        LinearLayout content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(24), dp(16), dp(24), dp(32));
        int width = getResources().getConfiguration().screenWidthDp > 800 ? dp(800) : -1;
        frame.addView(content, new LinearLayout.LayoutParams(width, -2));
        add(content, Z8Ui.quiet(this, palette, Z8Text.text("‹ Back to project", "‹ 프로젝트로"), this::finish), 0);
        TextView title = text(projectName, 27, palette.foreground);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD); add(content, title, 20);
        add(content, text(Z8Text.text("LOCAL · Linux environment", "LOCAL · Linux 환경"), 14, palette.accent), 6);
        add(content, text(Z8Text.text("Each project has a PRoot environment. It shares the Android kernel and app permissions; it is not a security VM.", "프로젝트별 PRoot 환경 · Android 커널과 앱 권한은 공유합니다. 보안 VM은 아닙니다."), 14, palette.secondary), 12);
        add(content, text(state.message, 17, palette.foreground), 24);
        if (state.phase == Z8Guest.Phase.INSTALLING || state.phase == Z8Guest.Phase.CHECKING) {
            ProgressBar bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
            bar.setIndeterminate(state.phase == Z8Guest.Phase.CHECKING); bar.setMax(100); bar.setProgress(state.progress);
            add(content, bar, 16);
            if (state.phase == Z8Guest.Phase.INSTALLING)
                add(content, text(state.progress + Z8Text.text("% · 1/2 Installing Linux\nNext, this terminal will prepare development tools and open a shell. Keep the app open during installation.", "% · 1/2 Linux 설치 중\n완료하면 같은 터미널에서 개발 도구를 준비하고 셸을 엽니다. 설치 중에는 앱을 열어두세요."), 14, palette.secondary), 10);
        }
        if (state.phase == Z8Guest.Phase.AVAILABLE) {
            add(content, text(Z8Text.text("1. Install Ubuntu → 2. Prepare development tools\nPython · pip · venv · Node LTS · npm · Git · GitHub CLI · build tools · tmux", "1. Ubuntu 설치 → 2. 표준 개발 도구 준비\nPython · pip · venv · Node LTS · npm · Git · GitHub CLI · 빌드 도구 · tmux"), 15, palette.foreground), 20);
            add(content, text(Z8Text.text("Tools are installed in this project's app storage and downloaded over the internet. Allow about 2 GB or more of free space per project. The actual size depends on package versions.", "앱 저장소에 프로젝트 전용으로 설치합니다. 개발 도구는 인터넷으로 다운로드하며 프로젝트당 약 2 GB 이상의 여유 공간을 권장합니다. 실제 용량은 패키지 버전에 따라 달라집니다."), 14, palette.secondary), 12);
            add(content, Z8Ui.primary(this, palette, Z8Text.text("Set up environment", "개발 환경 준비"), this::openTerminal), 24);
        }
        if (BuildConfig.Z8_HAS_BOOTSTRAP && !state.prootAvailable
                && state.phase != Z8Guest.Phase.CHECKING && state.phase != Z8Guest.Phase.INSTALLING) {
            add(content, button(Z8Text.text("Prepare project", "프로젝트 준비"), this::openTerminal), 20);
        }
        if (state.phase == Z8Guest.Phase.READY || (state.phase == Z8Guest.Phase.CHECKING && state.hasRootfs)) {
            add(content, text(Z8Text.text("Linux installed · ", "Linux 설치됨 · ") + (state.toolsReady ? Z8Text.text("Tools ready", "개발 도구 준비됨") : state.toolsCheckIncomplete ? Z8Text.text("Some tool checks delayed", "일부 도구 확인 지연") : state.toolsChecked ? Z8Text.text("Tools need setup", "개발 도구 준비 필요") : Z8Text.text("Tools need checking", "개발 도구 확인 필요")), 18, palette.foreground), 20);
            if (state.toolsReady) add(content, Z8Ui.primary(this, palette, Z8Text.text("Open new terminal", "새 터미널 열기"), this::openTerminal), 18);
            else {
                if (state.toolsCheckIncomplete) {
                    add(content, Z8Ui.primary(this, palette, Z8Text.text("Check tools again", "도구 상태 다시 확인"), () -> {
                        Z8Guest.refresh(getApplicationContext(), projectId, true); renderIfChanged();
                    }), 18);
                    add(content, Z8Ui.quiet(this, palette, Z8Text.text("Install or repair tools", "표준 개발 도구 설치 · 복구"), () -> openAction("setup-tools")), 10);
                } else add(content, Z8Ui.primary(this, palette, Z8Text.text("Open terminal and set up tools", "터미널 열기 · 개발 도구 준비"), this::openTerminal), 18);
                add(content, Z8Ui.quiet(this, palette, Z8Text.text("Recovery shell", "복구용 기본 셸"), () -> openAction("rescue-shell")), 10);
                add(content, text(Z8Text.text("Python, pip, venv, Node LTS, npm, git, gh, and build tools are prepared before the first shell opens. Installed packages are reused for later sessions.", "프로젝트 안에 Python·pip·venv·Node LTS·npm·git·gh·빌드 도구를 자동 준비한 뒤 첫 셸을 엽니다. 준비된 패키지는 재사용하며, 새 세션마다 설치하지 않습니다."), 14, palette.secondary), 10);
            }
            add(content, text(Z8Text.text("HOME /z8/home · Source /workspace", "HOME /z8/home · 소스 /workspace"), 14, palette.accent), 16);
            if (state.toolsChecked) {
                StringBuilder versions = new StringBuilder();
                for (String tool : new String[]{"python", "pip", "venv", "node", "npm", "git", "gh", "make", "cc", "tmux"})
                    versions.append(tool).append("  ").append(state.versions.containsKey(tool) ? state.versions.get(tool) : Z8Text.text("Installation or execution needs checking", "설치 또는 실행 확인 필요")).append('\n');
                add(content, text(versions.toString().trim(), 13, palette.secondary), 12);
            }
            add(content, text(Z8Text.text("AI development tools", "AI 개발 도구"), 22, palette.foreground), 28);
            add(content, text(Z8Text.text("Finding an executable does not verify sign-in or AI tasks. Tools share the project's source files and manage their own accounts and conversations.", "실행 파일 확인과 로그인·실제 AI 작업 가능 여부는 별도입니다. 도구는 같은 소스를 사용하고 로그인과 대화는 각각 관리합니다."), 14, palette.secondary), 10);
            for (String tool : new String[]{"claude", "codex"}) {
                String label = tool.equals("claude") ? "Claude Code" : "Codex";
                boolean ready = state.ready(tool);
                add(content, text(label + " · " + (ready ? state.versions.get(tool) : Z8Text.text("Installation or execution needs checking", "설치 또는 실행 확인 필요")), 16, palette.foreground), 18);
                Button action = button(label + (ready ? Z8Text.text(" · Open", " 실행") : Z8Text.text(" · Install", " 설치")), () -> openAction(ready ? tool : "setup-" + tool));
                action.setEnabled(state.toolsChecked && (ready || state.toolsReady));
                add(content, action, 8);
                if (ready) add(content, button(label + Z8Text.text(" · Set up notification hooks", " 알림 훅 설정"), () -> openAction("hooks-" + tool)), 8);
            }
            if (!state.toolsReady) add(content, text(Z8Text.text("Set up development tools before installing AI tools.", "AI 도구 설치 전에 표준 개발 도구를 준비해 주세요."), 14, palette.secondary), 12);
            add(content, text(Z8Text.text("Tap a notification to answer a permission request in its session. Hook setup backs up existing settings and preserves other hooks. The CLI may ask you to trust the hooks.", "권한 요청은 알림을 눌러 해당 세션에서 답합니다. 훅 설정은 기존 설정을 백업하고 다른 훅을 유지합니다. CLI의 훅 신뢰 승인이 필요할 수 있습니다."), 14, palette.secondary), 18);
            add(content, text(Z8Text.text("Some CLI sandbox features may be limited in PRoot. Approval and sandbox defaults are not automatically disabled.", "PRoot에서 일부 CLI sandbox 기능은 제한될 수 있습니다. 승인·sandbox 기본값을 자동으로 해제하지 않습니다."), 14, palette.secondary), 14);
        }
        if (state.phase != Z8Guest.Phase.INSTALLING && state.phase != Z8Guest.Phase.CHECKING)
            add(content, Z8Ui.quiet(this, palette, Z8Text.text("Check installation again", "설치 상태 다시 확인"), () -> { Z8Guest.refresh(getApplicationContext(), projectId, true); renderIfChanged(); }), 20);
        add(content, text(Z8Text.text("Source files and HOME are stored separately from the Linux image. App updates refresh managed scripts without overwriting your settings or source files.", "소스와 HOME은 Linux 이미지와 따로 보관됩니다. 앱 업데이트는 앱 관리 스크립트를 갱신하며 사용자 설정과 소스를 덮어쓰지 않습니다."), 14, palette.secondary), 24);
        setContentView(scroll);
        scroll.post(() -> scroll.scrollTo(0, position));
    }

    private void openTerminal() {
        startActivity(TermuxActivity.z8SessionIntent(this).putExtra(Z8Guest.EXTRA_GUEST_SESSION, true)
            .putExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID, projectId));
        finish();
    }
    private void openAction(String action) {
        Z8Guest.State current = Z8Guest.state(getApplicationContext(), projectId);
        if (!current.hasRootfs || !current.prootAvailable) return;
        startActivity(TermuxActivity.z8SessionIntent(this).putExtra(Z8Guest.EXTRA_GUEST_SESSION, true)
            .putExtra(Z8Guest.EXTRA_TOOL_ACTION, action).putExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID, projectId)
            .putExtra(Z8WorkspaceActivity.EXTRA_PROJECT_CWD, ""));
    }
    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setLineSpacing(dp(3), 1); return view;
    }
    private Button button(String value, Runnable action) { return Z8Ui.button(this, palette, value, action); }
    private void add(LinearLayout parent, android.view.View view, int top) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2); params.topMargin = dp(top); parent.addView(view, params);
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
