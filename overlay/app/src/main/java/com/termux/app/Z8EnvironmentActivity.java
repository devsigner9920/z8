package com.termux.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.text.DateFormat;
import java.util.Date;
import java.util.Locale;

/** Project-scoped catalog. Visible UI reads cached status; the service owns explicit installs. */
public final class Z8EnvironmentActivity extends Activity {
    private static final String PROJECT_ID = "dev.devsigner.z8.ENVIRONMENT_PROJECT_ID";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private String projectId;
    private String projectName = Z8Text.text("Project", "프로젝트");
    private String rendered = "", completedJob = "";
    private boolean projectValid, resumed;
    private int restoredScroll;
    private ScrollView scroll;
    private Z8Theme.Palette palette;
    private Z8ChromeStyle style;
    private final Runnable changed = () -> {
        if (resumed && !isFinishing() && !isDestroyed()) {
            observeCompletion();
            renderIfChanged();
        }
    };
    // The app-level metadata check may start elsewhere. Poll cached values only, never CLI probes.
    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if (!resumed || isFinishing() || isDestroyed()) return;
            changed.run(); handler.postDelayed(this, 1000);
        }
    };

    public static Intent intent(Context context, String projectId) {
        return new Intent(context, Z8EnvironmentActivity.class).putExtra(PROJECT_ID, projectId);
    }

    @Override protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        projectId = getIntent().getStringExtra(PROJECT_ID);
        try {
            projectName = new Z8Projects(this).open(projectId).name;
            projectValid = true;
        } catch (Exception invalid) { projectValid = false; }
        if (saved != null) restoredScroll = saved.getInt("scroll");
        setTitle(Z8Text.text("Tools", "도구") + " · " + projectName);
        renderIfChanged();
    }
    @Override protected void onSaveInstanceState(Bundle saved) {
        saved.putInt("scroll", scroll == null ? 0 : scroll.getScrollY());
        super.onSaveInstanceState(saved);
    }
    @Override protected void onResume() {
        super.onResume(); resumed = true;
        if (projectValid) {
            Z8ToolManager.addListener(changed);
            Z8Guest.addToolListener(changed);
            // One receipt/package inventory batch. Opening this screen never executes ten CLIs.
            Z8Guest.refreshCatalog(getApplicationContext(), projectId, false);
        }
        handler.removeCallbacks(poll); handler.post(poll);
    }
    @Override protected void onPause() {
        resumed = false;
        handler.removeCallbacks(poll);
        Z8ToolManager.removeListener(changed);
        Z8Guest.removeToolListener(changed);
        super.onPause();
    }

    private void observeCompletion() {
        if (!projectValid) return;
        Z8ToolManager.State task = Z8ToolManager.state(this, projectId);
        if (task.phase != Z8ToolManager.Phase.READY) { completedJob = ""; return; }
        String key = task.toolId + ":" + task.update + ":" + task.version;
        if (!key.equals(completedJob)) {
            completedJob = key;
            Z8Guest.refreshCatalog(getApplicationContext(), projectId, true);
        }
    }
    private static boolean busy(Z8ToolManager.State task) {
        return task.phase == Z8ToolManager.Phase.QUEUED || task.phase == Z8ToolManager.Phase.RUNNING;
    }

    private void renderIfChanged() {
        Z8Theme.Palette selected = Z8Theme.selected(this);
        Z8Guest.State base = projectValid ? Z8Guest.state(this, projectId) : null;
        Z8ToolManager.State task = projectValid ? Z8ToolManager.state(this, projectId) : null;
        Z8ToolUpdates.Snapshot releases = Z8ToolUpdates.cached(this);
        StringBuilder signature = new StringBuilder(selected.id).append(':').append(Z8Text.language()).append(':').append(projectValid);
        if (base != null) signature.append(':').append(base.phase).append(':').append(base.hasRootfs).append(':').append(base.prootAvailable);
        if (task != null) signature.append(':').append(task.phase).append(':').append(task.toolId).append(':').append(task.update)
            .append(':').append(task.version).append(':').append(task.percent).append(':').append(task.message).append(':').append(task.allowMetered);
        signature.append(':').append(releases.checking).append(':').append(releases.enabled).append(':').append(releases.lastAttemptAt);
        for (Z8ToolCatalog.Tool tool : Z8ToolCatalog.TOOLS) {
            if (projectValid) {
                Z8Guest.ToolState state = Z8Guest.toolState(this, projectId, tool.id);
                signature.append(':').append(state.checked).append(':').append(state.checking).append(':').append(state.installed)
                    .append(':').append(state.incomplete).append(':').append(state.version).append(':').append(state.message);
            }
            Z8ToolUpdates.Entry release = releases.get(tool.id);
            if (release != null) signature.append(':').append(release.upstreamVersion).append(':').append(release.checkedAt).append(':').append(release.error);
        }
        if (signature.toString().equals(rendered)) return;
        rendered = signature.toString(); palette = selected; style = Z8ChromeStyle.from(palette);
        int position = scroll == null ? restoredScroll : scroll.getScrollY();
        Z8Theme.applyChrome(this, palette);
        scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.setBackgroundColor(style.canvas);
        LinearLayout frame = column(); frame.setGravity(android.view.Gravity.CENTER_HORIZONTAL); scroll.addView(frame);
        LinearLayout content = column(); content.setPadding(dp(20), dp(16), dp(20), dp(32));
        int width = getResources().getConfiguration().screenWidthDp > 760 ? dp(760) : -1;
        frame.addView(content, new LinearLayout.LayoutParams(width, -2));
        add(content, Z8Ui.quiet(this, palette, Z8Text.text("‹ Back to project", "‹ 프로젝트로"), this::finish), 0);
        add(content, heading(Z8Text.text("Tools", "도구"), 28), 14);
        add(content, text(Z8Text.text("This project · ", "현재 프로젝트 · ") + projectName, 15, style.accent), 6);
        add(content, text(Z8Text.text("Choose what you need for this project's Linux environment.", "이 프로젝트의 Linux 환경에 필요한 도구를 선택하세요."), 14, style.muted), 10);
        if (!projectValid) {
            add(content, text(Z8Text.text("This project is unavailable. Return to the project list.", "이 프로젝트를 사용할 수 없습니다. 프로젝트 목록으로 돌아가 주세요."), 16, style.danger), 24);
        } else {
            boolean baseReady = base.hasRootfs && base.prootAvailable
                && (base.phase == Z8Guest.Phase.READY || base.phase == Z8Guest.Phase.CHECKING);
            add(content, heading(Z8Text.text("Included", "기본 포함"), 20), 24);
            LinearLayout included = card(content);
            add(included, heading(Z8Text.text("Linux + terminal", "Linux + 터미널"), 18), 0);
            add(included, text(Z8Text.text("A local shell and the Linux base for this project.", "이 프로젝트의 로컬 셸과 Linux 기본 환경."), 14, style.muted), 6);
            add(included, text(baseReady ? Z8Text.text("Ready", "준비됨") : base.message, 14, baseReady ? style.accent : style.muted), 10);
            Button open = Z8Ui.primary(this, palette, baseReady ? Z8Text.text("Open terminal", "터미널 열기") : Z8Text.text("Prepare project", "프로젝트 준비"), this::openTerminal);
            open.setEnabled(base.phase != Z8Guest.Phase.DELETING && base.phase != Z8Guest.Phase.INSTALLING);
            add(included, open, 12);
            for (Z8ToolCatalog.Group group : Z8ToolCatalog.Group.values()) {
                add(content, heading(group == Z8ToolCatalog.Group.RECOMMENDED ? Z8Text.text("Recommended", "추천") : Z8Text.text("Optional", "선택 설치"), 20), 26);
                for (Z8ToolCatalog.Tool tool : Z8ToolCatalog.TOOLS)
                    if (tool.group == group) toolCard(content, tool, Z8Guest.toolState(this, projectId, tool.id), task, releases, baseReady);
            }
            updatesCard(content, releases);
            add(content, text(Z8Text.text("Projects retain their own tools and versions. Existing Ubuntu environments are kept when Z8 is updated.", "도구와 버전은 프로젝트별로 유지됩니다. Z8를 업데이트해도 기존 Ubuntu 환경을 유지합니다."), 13, style.muted), 20);
        }
        setContentView(scroll);
        scroll.post(() -> scroll.scrollTo(0, position));
    }

    private void toolCard(LinearLayout parent, Z8ToolCatalog.Tool tool, Z8Guest.ToolState state,
            Z8ToolManager.State task, Z8ToolUpdates.Snapshot releases, boolean baseReady) {
        LinearLayout card = card(parent);
        add(card, heading(tool.name(), 18), 0);
        add(card, text(tool.detail(), 14, style.muted), 6);
        Z8ToolCatalog.Presence presence = Z8ToolCatalog.presence(state.checked, state.installed, state.incomplete);
        String status = presence == Z8ToolCatalog.Presence.INSTALLED ? Z8Text.text("Installed", "설치됨")
            : presence == Z8ToolCatalog.Presence.NEEDS_INSTALLATION ? Z8Text.text("Needs installation", "설치 필요")
            : Z8Text.text("Installation not verified", "설치 상태 미확인");
        if (state.version != null && !state.version.isEmpty()) status += " · " + state.version;
        if (state.checking) status += Z8Text.text(" · Checking…", " · 확인 중…");
        add(card, text(status, 14, state.installed ? style.accent : style.muted), 10);
        if (state.incomplete) add(card, text(Z8Text.text("A manual or partial installation may exist. Check status before relying on it.", "수동 또는 일부 설치가 있을 수 있습니다. 사용 전 상태를 확인하세요."), 13, style.muted), 6);
        if (state.message != null && !state.message.isEmpty() && (state.checked || state.incomplete))
            add(card, text(state.message, 13, style.muted), 4);
        if (tool.releaseMetadata && !state.installed) {
            String configured = Z8Guest.configuredToolVersion(this, tool.id);
            if (!configured.isEmpty()) add(card, text(Z8Text.text("Default install · ", "기본 설치 버전 · ") + configured, 13, style.muted), 6);
        }
        Z8ToolUpdates.Entry release = releases.get(tool.id);
        String installedVersion = Z8ToolCatalog.releaseVersion(tool.id, state.version);
        boolean updateAvailable = tool.releaseMetadata && state.installed && release != null
            && Z8ToolUpdates.newer(tool.id, release.upstreamVersion, installedVersion);
        if (release != null && !release.upstreamVersion.isEmpty()) {
            String available = (updateAvailable ? Z8Text.text("Update available · ", "업데이트 있음 · ") : Z8Text.text("Latest checked release · ", "마지막 확인한 최신 버전 · ")) + release.upstreamVersion;
            add(card, text(available, 13, updateAvailable ? style.accent : style.muted), 6);
            if (release.checkedAt > 0) add(card, text(Z8Text.text("Checked ", "확인 시각 ") + date(release.checkedAt), 12, style.muted), 3);
        }
        if (release != null && !release.error.isEmpty())
            add(card, text(Z8Text.text("Release check unavailable. The last successful result is shown above when available.", "최신 버전을 확인하지 못했습니다. 이전 확인 결과가 있으면 위에 표시합니다."), 12, style.muted), 5);
        boolean ownTask = tool.id.equals(task.toolId);
        if (ownTask && task.phase != Z8ToolManager.Phase.IDLE && task.phase != Z8ToolManager.Phase.READY) {
            TextView progressText = text(task.message, 14, task.phase == Z8ToolManager.Phase.FAILED ? style.danger : style.accent);
            progressText.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
            add(card, progressText, 12);
            if (busy(task)) {
                ProgressBar progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
                progress.setMax(100); progress.setIndeterminate(task.percent < 0); progress.setProgress(Math.max(0, task.percent));
                add(card, progress, 10);
            } else if (task.phase == Z8ToolManager.Phase.FAILED || task.phase == Z8ToolManager.Phase.WAITING_NETWORK) {
                add(card, action(tool, task.phase == Z8ToolManager.Phase.FAILED ? Z8Text.text("Retry", "다시 시도") : Z8Text.text("Resume", "계속"), () -> retry(task), baseReady), 10);
                if (task.phase == Z8ToolManager.Phase.WAITING_NETWORK && !task.allowMetered)
                    add(card, action(tool, Z8Text.text("Allow metered downloads…", "유료 네트워크 허용…"), () -> confirm(tool, task.update, task.version), baseReady), 6);
            }
        }
        boolean canChange = baseReady && !busy(task) && !state.checking;
        LinearLayout actions = new LinearLayout(this);
        actions.setBaselineAligned(false);
        if (state.installed) {
            String label = tool.isProviderClient() ? Z8Text.text("Open", "열기") : Z8Text.text("Open terminal", "터미널 열기");
            addAction(actions, action(tool, label, () -> openTool(tool), baseReady && !(ownTask && busy(task))));
            if (!tool.releaseMetadata || updateAvailable)
                addAction(actions, action(tool, Z8Text.text("Update", "업데이트"), () -> confirm(tool, true, tool.releaseMetadata ? release.upstreamVersion : ""), canChange));
        } else {
            String label = presence == Z8ToolCatalog.Presence.UNKNOWN ? Z8Text.text("Install / repair…", "설치 · 복구…") : Z8Text.text("Install", "설치");
            addAction(actions, action(tool, label, () -> confirm(tool, false, ""), canChange));
        }
        addAction(actions, action(tool, Z8Text.text("Check status", "상태 확인"), () -> {
            Z8Guest.refreshTool(getApplicationContext(), projectId, tool.id, true); renderIfChanged();
        }, baseReady && !state.checking && !busy(task)));
        add(card, actions, 12);
        if (tool.isProviderClient()) {
            add(card, text(Z8Text.text("Sign-in and provider usage are separate. PRoot may limit the client's sandbox features.", "로그인과 제공자 사용 요금은 별도입니다. PRoot에서 클라이언트의 sandbox 기능이 제한될 수 있습니다."), 12, style.muted), 10);
            add(card, Z8Ui.quiet(this, palette, Z8Text.text("Data, terms and licenses", "데이터·약관·라이선스"),
                () -> Z8ProviderDisclosure.showInfo(this, tool.id, state.version)), 6);
        }
    }

    private void updatesCard(LinearLayout parent, Z8ToolUpdates.Snapshot releases) {
        add(parent, heading(Z8Text.text("Release checks", "최신 버전 확인"), 20), 26);
        LinearLayout card = card(parent);
        add(card, text(Z8Text.text("Check public release information for Node.js 24 LTS, Codex and Claude Code.", "Node.js 24 LTS, Codex, Claude Code의 공개 릴리스 정보를 확인합니다."), 14, style.muted), 0);
        add(card, text(Z8Text.text("Official providers receive your IP address and ordinary connection information. Project files and your installed-tool list are not sent.", "공식 제공자에게 IP 주소와 일반적인 연결 정보가 전송됩니다. 프로젝트 파일과 설치한 도구 목록은 전송하지 않습니다."), 13, style.muted), 8);
        add(card, text(releases.enabled ? Z8Text.text("Daily checks on app open: On · Change in Settings", "앱을 열 때 하루 한 번 확인: 켜짐 · 설정에서 변경") : Z8Text.text("Daily checks on app open: Off · Change in Settings", "앱을 열 때 하루 한 번 확인: 꺼짐 · 설정에서 변경"), 13, style.muted), 8);
        Button check = Z8Ui.primary(this, palette, releases.checking ? Z8Text.text("Checking…", "확인 중…") : Z8Text.text("Check now", "지금 확인"), () -> {
            Z8ToolUpdates.requestCheck(getApplicationContext(), true, result -> {
                if (resumed && !isFinishing() && !isDestroyed()) renderIfChanged();
            });
            renderIfChanged();
        });
        check.setEnabled(!releases.checking); add(card, check, 12);
        add(card, text(Z8Text.text("A listed release is available upstream; compatibility with this Linux environment is not guaranteed.", "표시된 버전은 공식 배포 여부를 뜻하며, 이 Linux 환경과의 호환성을 보장하지 않습니다."), 12, style.muted), 10);
        add(card, text(Z8Text.text("Updates are installed after you choose Update and confirm the download. Linux package updates use this environment's repositories.", "업데이트는 업데이트 버튼을 누르고 다운로드를 확인한 뒤 설치합니다. Linux 패키지 업데이트는 이 환경의 저장소를 사용합니다."), 12, style.muted), 10);
    }

    private void confirm(Z8ToolCatalog.Tool tool, boolean update, String version) {
        final Z8ToolCatalog.Request request;
        try { request = new Z8ToolCatalog.Request(tool.id, update, version); }
        catch (IllegalArgumentException invalid) { message(Z8Text.text("Check the release version before updating.", "업데이트할 버전을 먼저 확인하세요.")); return; }
        LinearLayout details = column(); details.setPadding(dp(24), dp(8), dp(24), 0);
        add(details, text(Z8Text.text("This project · ", "현재 프로젝트 · ") + projectName, 15, style.accent), 0);
        if (!request.version.isEmpty()) add(details, text(Z8Text.text("Version · ", "버전 · ") + request.version, 14, style.text), 10);
        else if (tool.releaseMetadata) {
            String configured = Z8Guest.configuredToolVersion(this, tool.id);
            if (!configured.isEmpty()) add(details, text(Z8Text.text("Default install · ", "기본 설치 버전 · ") + configured, 14, style.text), 10);
        }
        add(details, text(tool.source(), 14, style.muted), 12);
        if (update && tool.releaseMetadata) add(details, text(Z8Text.text("Updates apply to installations managed by Z8. Custom or modified installations are preserved and may need a manual update.", "업데이트는 Z8에서 관리하는 설치에 적용됩니다. 직접 설치하거나 수정한 파일은 보존되며, 수동 업데이트가 필요할 수 있습니다."), 13, style.muted), 10);
        add(details, text(Z8Text.text("Required packages · ", "필요한 패키지 · ") + String.join(", ", tool.packages()), 13, style.muted), 12);
        add(details, text(Z8Text.text("Missing dependencies are installed with this tool. Download and storage size depend on the packages needed.", "없는 의존성은 이 도구와 함께 설치됩니다. 다운로드와 저장 공간 사용량은 필요한 패키지에 따라 달라집니다."), 13, style.muted), 10);
        if (tool.isProviderClient()) {
            add(details, text(Z8Text.text("This optional official client has its own account, charges, terms and privacy settings. Z8 does not operate the model service. Download and version validation can contact the publisher and may send connection or diagnostic information before sign-in. Installing does not sign you in or accept provider contracts.", "이 선택 설치 공식 클라이언트에는 별도 계정·요금·약관·개인정보 설정이 적용됩니다. Z8는 모델 서비스를 운영하지 않습니다. 다운로드와 버전 확인 과정에서 로그인 전에도 배포자에 접속하여 연결·진단 정보를 보낼 수 있습니다. 설치해도 로그인되거나 제공자 계약에 동의하지 않습니다."), 13, style.muted), 10);
            String noticeVersion = request.version.isEmpty() ? Z8Guest.configuredToolVersion(this, tool.id) : request.version;
            add(details, Z8Ui.quiet(this, palette, Z8Text.text("Provider terms, privacy and licenses", "제공자 약관·개인정보·라이선스"),
                () -> Z8ProviderDisclosure.showInfo(this, tool.id, noticeVersion)), 8);
        }
        CheckBox metered = new CheckBox(this); metered.setText(Z8Text.text("Allow metered downloads", "데이터 요금이 부과될 수 있는 네트워크 허용")); metered.setTextColor(style.text); metered.setChecked(false); metered.setMinHeight(dp(48));
        add(details, metered, 12);
        ScrollView dialogScroll = new ScrollView(this); dialogScroll.addView(details);
        Z8Ui.dialog(this).setTitle((update ? Z8Text.text("Update ", "업데이트 · ") : Z8Text.text("Install ", "설치 · ")) + tool.name())
            .setView(dialogScroll).setNegativeButton(Z8Text.text("Cancel", "취소"), null)
            .setPositiveButton(update ? Z8Text.text("Download and update", "다운로드 · 업데이트") : Z8Text.text("Download and install", "다운로드 · 설치"),
                (dialog, which) -> start(request, metered.isChecked())).show();
    }
    private void retry(Z8ToolManager.State task) {
        try { start(new Z8ToolCatalog.Request(task.toolId, task.update, task.version), task.allowMetered); }
        catch (IllegalArgumentException invalid) { message(Z8Text.text("Choose the tool again to retry.", "도구를 다시 선택해 재시도하세요.")); }
    }
    private void start(Z8ToolCatalog.Request request, boolean allowMetered) {
        try {
            Z8ToolManager.start(getApplicationContext(), projectId, request.tool.id, request.update, request.version, allowMetered);
            completedJob = ""; renderIfChanged();
        } catch (RuntimeException unavailable) {
            message(Z8Text.text("Could not start this installation. Check the project and try again.", "설치를 시작하지 못했습니다. 프로젝트를 확인하고 다시 시도하세요."));
        }
    }
    private void openTerminal() {
        if (!projectValid) return;
        startActivity(TermuxActivity.z8SessionIntent(this).putExtra(Z8Guest.EXTRA_GUEST_SESSION, true)
            .putExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID, projectId));
        finish();
    }
    private void openTool(Z8ToolCatalog.Tool tool) {
        if (!tool.isProviderClient()) { openTerminal(); return; }
        Z8Guest.State base = Z8Guest.state(this, projectId);
        if (!base.hasRootfs || !base.prootAvailable || base.phase == Z8Guest.Phase.DELETING) return;
        startActivity(TermuxActivity.z8SessionIntent(this).putExtra(Z8Guest.EXTRA_GUEST_SESSION, true)
            .putExtra(Z8Guest.EXTRA_TOOL_ACTION, tool.id).putExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID, projectId)
            .putExtra(Z8WorkspaceActivity.EXTRA_PROJECT_CWD, ""));
    }
    private String date(long time) {
        Locale locale = Z8Text.language().equals("ko") ? Locale.KOREAN : Locale.US;
        return DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT, locale).format(new Date(time));
    }
    private LinearLayout column() { LinearLayout view = new LinearLayout(this); view.setOrientation(LinearLayout.VERTICAL); return view; }
    private LinearLayout card(LinearLayout parent) {
        LinearLayout view = column(); view.setPadding(dp(16), dp(16), dp(16), dp(16));
        view.setBackground(style.shape(this, style.panel, style.border, 16)); add(parent, view, 12); return view;
    }
    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color); view.setLineSpacing(dp(2), 1); return view;
    }
    private TextView heading(String value, int size) { TextView view = text(value, size, style.text); view.setTypeface(Typeface.DEFAULT, Typeface.BOLD); return view; }
    private Button action(Z8ToolCatalog.Tool tool, String value, Runnable run, boolean enabled) {
        Button view = Z8Ui.button(this, palette, value, run); view.setContentDescription(tool.name() + " · " + value); view.setEnabled(enabled); return view;
    }
    private void addAction(LinearLayout parent, View view) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -2, 1);
        if (parent.getChildCount() > 0) params.leftMargin = dp(8); parent.addView(view, params);
    }
    private void add(LinearLayout parent, View view, int top) { LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2); params.topMargin = dp(top); parent.addView(view, params); }
    private void message(String value) { Toast.makeText(this, value, Toast.LENGTH_LONG).show(); }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
