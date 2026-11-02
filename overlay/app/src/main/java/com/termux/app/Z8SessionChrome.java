package com.termux.app;

import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.LayerDrawable;
import android.graphics.drawable.InsetDrawable;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.InputFilter;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.drawerlayout.widget.DrawerLayout;

import com.termux.R;
import com.termux.terminal.TerminalSession;
import com.termux.shared.termux.shell.command.runner.terminal.TermuxSession;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.IntConsumer;

/** Project navigation around the existing service-owned terminal; never owns a PTY. */
public final class Z8SessionChrome {
    private final TermuxActivity activity;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    // Project metadata creation must finish even if a fold recreates this Activity.
    private static final Handler PROJECT_MAIN = new Handler(Looper.getMainLooper());
    private static final ExecutorService PROJECT_WRITES = Executors.newSingleThreadExecutor();
    private long removalRevision = Z8ProjectRemoval.revision();
    private static final String NAVIGATION_PREFS = "z8.terminal-navigation";
    private String selectedProject;
    private long projectLoadGeneration;
    private TextView emptyTerminal;
    private LinearLayout preparationPanel;
    private TextView preparationTitle, preparationDetail, preparationRetry, preparationLog, preparationNotifications;
    private ProgressBar preparationProgress;
    private final LinkedHashMap<String, String> projects = new LinkedHashMap<>();
    private final LinkedHashMap<String, Z8Projects.Problem> projectProblems = new LinkedHashMap<>();
    private final Set<String> collapsed = new HashSet<>();
    private final Map<String, String> names = new HashMap<>();
    private final Map<String, String> lastSessions = new HashMap<>();
    private List<Z8SessionCatalog.Entry> entries = Collections.emptyList();
    private Map<String, Integer> notices = Collections.emptyMap();
    private Z8Theme.Palette palette;
    private Z8ChromeStyle style;
    private LinearLayout body, side, drawerContent, header, tabRow, tabLine, terminalSurface;
    private HorizontalScrollView tabs;
    private ImageView addSession, openBrowser;
    private Z8BrowserPane browserPane;
    private String browserProject, browserSessionHandle;
    private boolean browserSelected, externalOpening;
    private final Z8WorkspaceKeys workspaceKeys = new Z8WorkspaceKeys(new Z8WorkspaceKeys.Host() {
        public boolean isBrowserSelected() { return browserSelected && browserPane != null; }
        public void newTerminal() { createForCurrent(); }
        public void cycleTabs(int direction) { cycleWorkspaceTabs(direction); }
        public void openBrowser() { openBrowserTab(); }
        public void focusBrowserAddress() { if (browserPane != null) browserPane.focusAddress(); }
        public void reloadBrowser() { if (browserPane != null) browserPane.reload(); }
        public void returnToTerminal() { returnFromBrowser(); }
    });
    private final Z8BrowserBridge.Listener browserListener = this::handleBrowserRequest;
    private boolean handleBrowserRequest(Z8BrowserBridge.Request request) {
        if (!visible || disposed || externalOpening || !request.isLive()) return false;
        selectProject(request.projectId, false);
        // A request may come from a different terminal in the same project.
        // Store that exact terminal before leaving so Android Back returns to it.
        for (Z8SessionCatalog.Entry entry : entries)
            if (entry.handle.equals(request.sessionHandle)) { select(entry); break; }
        openBrowserTab();
        browserSessionHandle = request.sessionHandle;
        externalOpening = true;
        externalOpening = browserPane.showRequest(request.url);
        return true;
    }
    private View divider, tabDivider;
    private final Z8ResourceMonitor resourceMonitor;
    private Z8ResourceMonitor.Snapshot resourceSample = Z8ResourceMonitor.Snapshot.pending();
    private TextView headerResourceText, headerProjectText;
    private int headerResourceWidth;
    private boolean resourcesVisible;
    private boolean wide, compact, visible, resumed, disposed, installed;
    private final Runnable restoreInput = this::restoreInputAfterLayout;
    private void restoreInputAfterLayout() {
        if (disposed || !resumed || !visible || browserSelected || !activity.hasWindowFocus()
                || activity.getCurrentSession() == null || !activity.getTerminalView().isShown()) return;
        activity.getTerminalView().z8ResumeInput();
    }
    private String fingerprint = "";
    private String preparationFingerprint = "";
    private boolean projectsLoaded, copying, badgeReadPending, layoutPending, revealPending;
    private String projectError = "";
    private long lastLaunchTap;
    private static final String FOCUS_TAG_PREFIX = "z8.chrome/";
    private static final class FocusTarget {
        final ViewGroup scope;
        final String tag;
        FocusTarget(ViewGroup scope, String tag) { this.scope = scope; this.tag = tag; }
    }
    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (!visible || disposed) return;
            if (removalRevision != Z8ProjectRemoval.revision()) { removalRevision = Z8ProjectRemoval.revision(); loadProjects(); }
            refresh();
            requestBadges();
            main.postDelayed(this, 1000);
        }
    };

    public Z8SessionChrome(TermuxActivity activity) {
        this.activity = activity;
        resourceMonitor = new Z8ResourceMonitor(sample -> {
            resourceSample = sample;
            renderResourceSample();
        });
        selectedProject = activity.getSharedPreferences(NAVIGATION_PREFS, Context.MODE_PRIVATE).getString("project", null);
    }

    public void install() {
        if (installed) return;
        installed = true;
        palette = Z8Theme.selected(activity);
        style = Z8ChromeStyle.from(palette);
        wide = activity.getResources().getConfiguration().screenWidthDp >= 720;
        DrawerLayout drawer = activity.getDrawer();
        View terminal = activity.getTerminalView();
        ((ViewGroup) terminal.getParent()).removeView(terminal);
        body = row(); body.setId(R.id.z8_session_chrome);
        side = column(); side.setId(R.id.z8_session_sidebar);
        body.addView(side, new LinearLayout.LayoutParams(dp(248), -1));
        divider = new View(activity);
        body.addView(divider, new LinearLayout.LayoutParams(dp(1), -1));
        LinearLayout surface = column();
        body.addView(surface, new LinearLayout.LayoutParams(0, -1, 1));
        header = row(); header.setPadding(dp(8), dp(4), dp(8), dp(4));
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.addOnLayoutChangeListener((view, left, top, right, bottom, oldLeft, oldTop, oldRight, oldBottom) ->
            updateResourceVisibility());
        surface.addView(header, new LinearLayout.LayoutParams(-1,
            dp(Math.max(56, Math.round(30 * activity.getResources().getConfiguration().fontScale + 26)))));
        tabLine = row();
        tabs = new HorizontalScrollView(activity) {
            @Override protected void onMeasure(int widthSpec, int heightSpec) {
                // Hug the tabs until the row fills up, then reserve an always
                // reachable add target while the tabs themselves scroll.
                if (MeasureSpec.getMode(widthSpec) != MeasureSpec.UNSPECIFIED) {
                    int reserved = addSession != null && addSession.getVisibility() != View.GONE ? dp(48) : 0;
                    if (openBrowser != null && openBrowser.getVisibility() != View.GONE) reserved += dp(48);
                    int available = Math.max(0, MeasureSpec.getSize(widthSpec) - reserved);
                    widthSpec = MeasureSpec.makeMeasureSpec(available, MeasureSpec.AT_MOST);
                }
                super.onMeasure(widthSpec, heightSpec);
            }
        };
        tabs.setId(R.id.z8_session_tabs);
        tabs.setHorizontalScrollBarEnabled(false); tabs.setFillViewport(false);
        tabs.addOnLayoutChangeListener((view, left, top, right, bottom, oldLeft, oldTop, oldRight, oldBottom) -> {
            if (right - left != oldRight - oldLeft) scheduleRevealSelectedTab();
        });
        tabRow = row(); tabRow.setPadding(dp(8), 0, 0, 0);
        tabs.addView(tabRow, new ViewGroup.LayoutParams(-2, -1));
        tabLine.addView(tabs, new LinearLayout.LayoutParams(-2, dp(48)));
        addSession = iconAction(R.drawable.z8_ic_add, Z8Text.text("New terminal in this project", "현재 프로젝트에 새 터미널"), this::createForCurrent);
        addSession.setId(R.id.z8_new_session);
        focusTag(addSession, "new-session");
        tabLine.addView(addSession, new LinearLayout.LayoutParams(dp(48), dp(48)));
        openBrowser = iconAction(R.drawable.z8_ic_browser, Z8Text.text("Open browser tab", "브라우저 탭 열기"), this::openBrowserTab);
        focusTag(openBrowser, "open-browser");
        tabLine.addView(openBrowser, new LinearLayout.LayoutParams(dp(48), dp(48)));
        surface.addView(tabLine);
        tabDivider = new View(activity);
        surface.addView(tabDivider, new LinearLayout.LayoutParams(-1, dp(1)));
        // Reparent the same TerminalView; attachSession remains the only switch operation.
        terminalSurface = column();
        terminalSurface.setPadding(dp(12), dp(12), dp(12), dp(8));
        terminalSurface.addView(terminal, new LinearLayout.LayoutParams(-1, -1));
        emptyTerminal = text("", 14, style.muted, false);
        emptyTerminal.setGravity(Gravity.CENTER);
        emptyTerminal.setLineSpacing(dp(7), 1);
        emptyTerminal.setPadding(dp(24), dp(24), dp(24), dp(24));
        terminalSurface.addView(emptyTerminal, new LinearLayout.LayoutParams(-1, -1));
        installPreparationPanel();
        surface.addView(terminalSurface, new LinearLayout.LayoutParams(-1, 0, 1));
        drawer.addView(body, 0, new DrawerLayout.LayoutParams(-1, -1));
        body.addOnLayoutChangeListener((view, left, top, right, bottom, oldLeft, oldTop, oldRight, oldBottom) -> {
            if (layoutPending || disposed || right <= left || bottom <= top) return;
            // DrawerLayout suppresses requestLayout while laying out children.
            // Rebuilding a hidden drawer in that pass leaves new rows unmeasured.
            layoutPending = true;
            main.post(() -> {
                layoutPending = false;
                if (!disposed) updateLayout(body.getWidth(), body.getHeight());
            });
        });
        LinearLayout legacy = activity.findViewById(R.id.left_drawer);
        // Upstream still holds adapters/control references. Retain these views, hidden.
        for (int index = 0; index < legacy.getChildCount(); index++) legacy.getChildAt(index).setVisibility(View.GONE);
        legacy.setDescendantFocusability(ViewGroup.FOCUS_AFTER_DESCENDANTS);
        DrawerLayout.LayoutParams drawerParams = (DrawerLayout.LayoutParams) legacy.getLayoutParams();
        drawerParams.width = dp(Math.min(320, activity.getResources().getConfiguration().screenWidthDp - 40));
        legacy.setLayoutParams(drawerParams);
        drawerContent = column(); drawerContent.setId(R.id.z8_session_drawer);
        legacy.addView(drawerContent, new LinearLayout.LayoutParams(-1, -1));
        side.setVisibility(wide ? View.VISIBLE : View.GONE);
        divider.setVisibility(wide ? View.VISIBLE : View.GONE);
        applyDrawerLock();
        refresh();
    }

    /** Termux consumes configuration changes; use the real available window width. */
    private void updateLayout(int widthPixels, int heightPixels) {
        if (disposed || drawerContent == null) return;
        int widthDp = Math.round(widthPixels / activity.getResources().getDisplayMetrics().density);
        boolean nextWide = widthDp >= 720;
        boolean nextCompact = heightPixels / activity.getResources().getDisplayMetrics().density < 480;
        DrawerLayout drawer = activity.getDrawer();
        View legacy = activity.findViewById(R.id.left_drawer);
        DrawerLayout.LayoutParams params = (DrawerLayout.LayoutParams) legacy.getLayoutParams();
        int targetWidth = dp(Math.max(200, Math.min(320, widthDp - 40)));
        if (params.width != targetWidth) { params.width = targetWidth; legacy.setLayoutParams(params); }
        if (wide == nextWide && compact == nextCompact) return;
        if (wide != nextWide) {
            drawer.closeDrawers(); wide = nextWide;
            side.setVisibility(wide ? View.VISIBLE : View.GONE);
            divider.setVisibility(wide ? View.VISIBLE : View.GONE);
            applyDrawerLock();
        }
        compact = nextCompact;
        fingerprint = ""; refresh();
    }

    public void setCopyMode(boolean copying) {
        this.copying = copying;
        applyDrawerLock();
    }
    private void applyDrawerLock() {
        activity.getDrawer().setDrawerLockMode(wide || copying
            ? DrawerLayout.LOCK_MODE_LOCKED_CLOSED : DrawerLayout.LOCK_MODE_UNLOCKED, Gravity.LEFT);
    }

    private void requestBadges() {
        if (disposed || !visible || badgeReadPending) return;
        badgeReadPending = true;
        // The bridge monitor can be held during its durable event write. Never
        // wait for it from the UI thread or enqueue overlapping badge reads.
        io.execute(() -> {
            Map<String, Integer> counts = Z8AttentionBridge.unseenSessionCounts();
            main.post(() -> {
                badgeReadPending = false;
                if (disposed) return;
                if (!notices.equals(counts)) { notices = counts; fingerprint = ""; if (visible) refresh(); }
            });
        });
    }

    public void onResume() {
        if (disposed) return;
        visible = true; resumed = true;
        preparationFingerprint = ""; // Notification permission may have changed in Android settings.
        // A full-screen browser also stops this Activity. onStart may restore
        // the terminal selection before onResume and clear browserSelected;
        // the pending browser return must still restore input focus. A separate
        // notification/project navigation must not be replaced by an old origin.
        if (externalOpening && browserPane != null
                && java.util.Objects.equals(selectedProject, browserProject)) returnFromBrowser();
        externalOpening = false;
        if (browserPane != null) browserPane.setForeground(true);
        Z8BrowserBridge.attach(browserListener);
        updateResourceVisibility();
        main.removeCallbacks(tick); main.post(tick);
        loadProjects();
        restoreTerminalInput();
    }
    public void onPause() {
        resumed = false;
        main.removeCallbacks(restoreInput);
        activity.getTerminalView().z8SuspendInput();
        workspaceKeys.reset();
        Z8BrowserBridge.detach(browserListener);
        if (browserPane != null) browserPane.setForeground(false);
    }
    public void onStop() {
        visible = false; main.removeCallbacks(tick);
        resourcesVisible = false; resourceMonitor.stop();
    }
    public void dispose() {
        disposed = true; onPause(); onStop(); resourceMonitor.close();
        closeBrowserTab();
        main.removeCallbacksAndMessages(null); io.shutdownNow();
    }

    private void loadProjects() {
        Context app = activity.getApplicationContext();
        long loadGeneration = ++projectLoadGeneration;
        io.execute(() -> {
            Z8Projects.Listing loaded;
            try { loaded = new Z8Projects(app).scan(); }
            catch (Exception exception) {
                main.post(() -> {
                    if (disposed || loadGeneration != projectLoadGeneration) return;
                    projectsLoaded = true; projectError = Z8Text.text("Could not load projects", "프로젝트 목록을 읽지 못했습니다");
                    fingerprint = ""; refresh();
                });
                return;
            }
            main.post(() -> {
                if (disposed || loadGeneration != projectLoadGeneration) return;
                projects.clear();
                projectProblems.clear();
                for (Z8Projects.Project project : loaded.projects) projects.put(project.id, project.name);
                for (Z8Projects.Problem problem : loaded.problems) projectProblems.put(problem.id, problem);
                projectsLoaded = true; projectError = "";
                if (selectedProject != null && !selectedProject.isEmpty() && !projects.containsKey(selectedProject)
                        && !projectProblems.containsKey(selectedProject)) {
                    boolean live = false;
                    for (Z8SessionCatalog.Entry entry : Z8SessionCatalog.snapshot(activity.getTermuxService(), activity.getCurrentSession()))
                        if (selectedProject.equals(entry.projectId)) live = true;
                    if (!live) { rememberProject(null); clearTerminal(); }
                }
                fingerprint = ""; refresh();
            });
        });
    }

    public void openSessions() {
        if (!installed || disposed) return;
        if (wide) { side.setVisibility(View.VISIBLE); divider.setVisibility(View.VISIBLE); }
        else activity.getDrawer().openDrawer(Gravity.LEFT);
        refresh();
        if (!body.isInTouchMode()) {
            View panel = wide ? side : drawerContent;
            panel.post(() -> { if (!disposed) focusSelectedSession((ViewGroup) panel); });
        }
    }

    private boolean focusSelectedSession(ViewGroup parent) {
        for (int index = 0; index < parent.getChildCount(); index++) {
            View child = parent.getChildAt(index);
            if (child.getId() == R.id.z8_session_row && child.isSelected()) return child.requestFocus();
            if (child instanceof ViewGroup && focusSelectedSession((ViewGroup) child)) return true;
        }
        return false;
    }

    private void focusTag(View view, String key) { view.setTag(FOCUS_TAG_PREFIX + key); }

    /** Preserve hardware navigation, never terminal input or a dialog's editor focus. */
    private FocusTarget captureChromeFocus() {
        if (!visible || !activity.hasWindowFocus() || body.isInTouchMode()) return null;
        View focused = activity.getCurrentFocus();
        if (focused == null || !(focused.getTag() instanceof String)) return null;
        String tag = (String) focused.getTag();
        if (!tag.startsWith(FOCUS_TAG_PREFIX)) return null;
        // Sidebar and drawer use matching semantic tags, but restoration must
        // stay in the panel the user was navigating, not jump to its hidden twin.
        for (ViewGroup scope : new ViewGroup[]{header, tabLine, side, drawerContent})
            if (isWithin(focused, scope)) return new FocusTarget(scope, tag);
        return null;
    }

    private static boolean isWithin(View view, View ancestor) {
        while (view != null) {
            if (view == ancestor) return true;
            view = view.getParent() instanceof View ? (View) view.getParent() : null;
        }
        return false;
    }

    private void restoreChromeFocus(FocusTarget previous) {
        if (previous == null || disposed || !visible || !activity.hasWindowFocus() || body.isInTouchMode()) return;
        View replacement = previous.scope.findViewWithTag(previous.tag);
        if (replacement != null && replacement.isShown() && replacement.isEnabled() && replacement.isFocusable())
            replacement.requestFocus();
        // No fallback: a removed/hidden navigation target is not a request to
        // focus the selected session. Run synchronously so select() can then
        // deliberately return focus to TerminalView without a later callback.
    }

    public void refresh() {
        if (!installed || disposed) return;
        List<Z8SessionCatalog.Entry> next = Z8SessionCatalog.snapshot(activity.getTermuxService(), activity.getCurrentSession());
        Map<String, Integer> pending = notices;
        Z8Theme.Palette theme = Z8Theme.selected(activity);
        boolean launchPending = Z8GuestSessionLauncher.hasPending(activity.getTermuxService());
        Z8GuestSessionLauncher.Preparation preparation = Z8GuestSessionLauncher.preparation(activity, selectedProject);
        String preparationContent = preparation == null ? "" : preparation.toString();
        StringBuilder signature = new StringBuilder(theme.id).append(Z8Text.language()).append(projects.toString()).append(projectError).append(projectsLoaded)
            .append(launchPending).append(selectedProject).append(preparation == null ? "none" : preparation.failed ? "failed" : "preparing")
            .append(browserSelected).append(browserProject);
        for (Z8SessionCatalog.Entry entry : next)
            signature.append('|').append(entry.handle).append(entry.title).append(entry.projectId).append(entry.tool)
                .append(entry.running).append(entry.selected).append(pending.get(entry.handle));
        if (fingerprint.equals(signature.toString())) {
            if (!preparationFingerprint.equals(preparationContent)) {
                preparationFingerprint = preparationContent;
                renderPreparation(browserSelected ? null : preparation);
            }
            return;
        }
        preparationFingerprint = preparationContent;
        FocusTarget previousFocus = captureChromeFocus();
        fingerprint = signature.toString(); entries = next; notices = pending; palette = theme;
        style = Z8ChromeStyle.from(theme);
        names.clear();
        for (Z8SessionCatalog.Entry entry : entries) {
            if (entry.selected && !entry.projectId.isEmpty()) lastSessions.put(entry.projectId, entry.handle);
            int total = 0, index = 0;
            for (Z8SessionCatalog.Entry other : entries)
                if (other.projectId.equals(entry.projectId) && other.title.equals(entry.title)) {
                    total++; if (other == entry) index = total;
                }
            names.put(entry.handle, entry.title + (total > 1 ? " · " + index : ""));
        }
        body.setBackgroundColor(style.canvas);
        header.setBackground(style.prism ? style.ambient(activity) : style.shape(activity, style.surface, Color.TRANSPARENT, 0));
        tabLine.setBackgroundColor(palette.background);
        terminalSurface.setBackgroundColor(palette.background);
        divider.setBackgroundColor(style.border);
        tabDivider.setBackgroundColor(Color.TRANSPARENT);
        ImageView add = activity.findViewById(R.id.z8_new_session);
        add.setImageTintList(ColorStateList.valueOf(style.muted));
        add.setBackground(new InsetDrawable(
            style.interactive(activity, Color.TRANSPARENT, Color.TRANSPARENT, 6), dp(8)));
        // A quiet 18dp glyph and 32dp feedback surface share the tabs' baseline.
        // The full 48dp view remains the touch and accessibility target.
        add.setPadding(dp(15), dp(15), dp(15), dp(15));
        Z8SessionCatalog.Entry selected = current();
        String addLabel = selectedProject == null || selectedProject.isEmpty() ? Z8Text.text("Open a terminal from the project list", "프로젝트 목록에서 터미널 열기")
            : projectName(selectedProject) + Z8Text.text(": new terminal", "에 새 터미널");
        add.setContentDescription(addLabel); add.setTooltipText(addLabel);
        add.setEnabled(!launchPending && !projectProblems.containsKey(selectedProject));
        add.setAlpha(add.isEnabled() ? 1f : .5f);
        boolean hasSession = selected != null;
        activity.getTerminalView().setVisibility(hasSession && preparation == null && !browserSelected ? View.VISIBLE : View.GONE);
        emptyTerminal.setVisibility(hasSession || preparation != null || browserSelected ? View.GONE : View.VISIBLE);
        renderPreparation(browserSelected ? null : preparation);
        terminalSurface.setPadding(browserSelected ? 0 : dp(12), browserSelected ? 0 : dp(12), browserSelected ? 0 : dp(12), browserSelected ? 0 : dp(8));
        if (browserPane != null) {
            browserPane.setVisibility(browserSelected ? View.VISIBLE : View.GONE);
            browserPane.setActive(browserSelected); browserPane.applyTheme();
        }
        openBrowser.setImageTintList(ColorStateList.valueOf(style.muted));
        emptyTerminal.setTextColor(style.muted);
        emptyTerminal.setText(selectedProject == null || selectedProject.isEmpty()
            ? Z8Text.text("Choose a project to get started.\nUse + in the list to create one.", "프로젝트를 선택해 시작하세요.\n목록의 +로 새 프로젝트를 만들 수 있어요.")
            : projectProblems.containsKey(selectedProject)
            ? projectName(selectedProject) + Z8Text.text("\nThis project needs attention.\nSelect “Check project info” in the list.", "\n프로젝트 정보를 확인해야 합니다.\n목록에서 ‘프로젝트 정보 확인 필요’를 눌러 주세요.")
            : projectName(selectedProject) + Z8Text.text("\nUse + beside the project name to open your first terminal.", "\n프로젝트 목록에서 이름 옆의 +로 첫 터미널을 여세요."));
        renderHeader(); renderTabs();
        renderPanel(side); renderPanel(drawerContent);
        restoreChromeFocus(previousFocus);
    }

    private Z8SessionCatalog.Entry current() {
        for (Z8SessionCatalog.Entry entry : entries) if (entry.selected) return entry;
        return null;
    }

    private void installPreparationPanel() {
        preparationPanel = column(); preparationPanel.setGravity(Gravity.CENTER);
        preparationPanel.setPadding(dp(20), dp(24), dp(20), dp(24));
        LinearLayout card = new LinearLayout(activity) {
            @Override protected void onMeasure(int width, int height) {
                super.onMeasure(MeasureSpec.makeMeasureSpec(Math.min(dp(360), MeasureSpec.getSize(width)), MeasureSpec.EXACTLY), height);
            }
        };
        card.setOrientation(LinearLayout.VERTICAL);
        preparationTitle = text("", 20, style.text, true);
        card.addView(preparationTitle);
        preparationDetail = text("", 13, style.muted, false);
        preparationDetail.setPadding(0, dp(10), 0, dp(22));
        preparationDetail.setLineSpacing(dp(5), 1);
        preparationDetail.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        card.addView(preparationDetail);
        preparationProgress = new ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal);
        preparationProgress.setMax(100);
        card.addView(preparationProgress, new LinearLayout.LayoutParams(-1, dp(4)));
        preparationRetry = text(Z8Text.text("Retry", "다시 시도"), 14, style.accent, true);
        preparationRetry.setGravity(Gravity.CENTER_VERTICAL); interactive(preparationRetry);
        preparationRetry.setOnClickListener(view -> createForCurrent());
        card.addView(preparationRetry, new LinearLayout.LayoutParams(-1, dp(48)));
        preparationLog = text(Z8Text.text("View error details", "상세 오류 보기"), 13, style.muted, false);
        preparationLog.setGravity(Gravity.CENTER_VERTICAL); interactive(preparationLog);
        preparationLog.setOnClickListener(view -> {
            Z8GuestSessionLauncher.Preparation state = Z8GuestSessionLauncher.preparation(activity, selectedProject);
            if (state == null || !state.failed) return;
            TextView details = text(state.message, 12, style.text, false);
            details.setTypeface(Typeface.MONOSPACE); details.setTextIsSelectable(true);
            details.setPadding(dp(20), dp(16), dp(20), dp(16));
            ScrollView scroll = new ScrollView(activity); scroll.addView(details);
            showDialog(dialogBuilder().setTitle(Z8Text.text("Setup error", "설치 오류")).setView(scroll).setPositiveButton(Z8Text.text("Close", "닫기"), null).create(), false);
        });
        card.addView(preparationLog, new LinearLayout.LayoutParams(-1, dp(48)));
        preparationNotifications = text(Z8Text.text("Enable progress notifications", "진행 알림 켜기"), 13, style.accent, false);
        preparationNotifications.setGravity(Gravity.CENTER_VERTICAL); interactive(preparationNotifications);
        preparationNotifications.setOnClickListener(view -> activity.startActivity(new Intent(
            android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(
                android.provider.Settings.EXTRA_APP_PACKAGE, activity.getPackageName())));
        card.addView(preparationNotifications, new LinearLayout.LayoutParams(-1, dp(48)));
        preparationPanel.addView(card, new LinearLayout.LayoutParams(-1, -2));
        terminalSurface.addView(preparationPanel, new LinearLayout.LayoutParams(-1, -1));
        preparationPanel.setVisibility(View.GONE);
    }

    private void renderPreparation(Z8GuestSessionLauncher.Preparation state) {
        preparationPanel.setVisibility(state == null ? View.GONE : View.VISIBLE);
        preparationRetry.setText(Z8Text.text("Retry", "다시 시도"));
        preparationLog.setText(Z8Text.text("View error details", "상세 오류 보기"));
        preparationNotifications.setText(Z8Text.text("Enable progress notifications", "진행 알림 켜기"));
        if (state == null) return;
        preparationTitle.setTextColor(style.text); preparationDetail.setTextColor(style.muted);
        preparationRetry.setTextColor(style.accent); preparationLog.setTextColor(style.muted);
        preparationNotifications.setTextColor(style.accent);
        android.app.NotificationManager notifications = activity.getSystemService(android.app.NotificationManager.class);
        preparationNotifications.setVisibility(!state.failed && notifications != null
            && !notifications.areNotificationsEnabled() ? View.VISIBLE : View.GONE);
        preparationRetry.setBackground(style.interactive(activity, Color.TRANSPARENT, Color.TRANSPARENT, 6));
        preparationLog.setBackground(style.interactive(activity, Color.TRANSPARENT, Color.TRANSPARENT, 6));
        preparationTitle.setText(state.failed ? Z8Text.text("Setup could not finish", "준비를 완료하지 못했어요")
            : state.resuming ? Z8Text.text("Resuming setup", "중단된 준비를 이어가고 있어요") : Z8Text.text("Getting ready for first use", "처음 실행을 준비하고 있어요"));
        int step = state.stage.equals("bootstrap") ? 1 : state.stage.equals("rootfs") ? 2 : 3;
        preparationDetail.setText(state.failed ? Z8Text.text("Completed steps and project files are preserved.\nCheck your connection and storage, then retry.", "완료된 설치와 프로젝트 파일은 유지돼요.\n연결과 저장 공간을 확인한 뒤 다시 시도해 주세요.")
            : step + " / 3   " + state.message
                + Z8Text.text("\n\nThis project's first setup may take a few minutes.", "\n\n이 프로젝트의 첫 준비는 몇 분 걸릴 수 있어요.")
                + Z8Text.text("\nSetup continues while you use other apps.", "\n다른 앱을 사용해도 설치는 계속돼요.")
                + Z8Text.text("\nIf the app is stopped, reopen it to resume setup.", "\n강제 종료되면 앱을 다시 열 때 이어서 준비해요.")
                + Z8Text.text("\nAfter that, you can start without reinstalling.", "\n다음부터는 설치 없이 바로 시작해요."));
        preparationProgress.setVisibility(state.failed ? View.GONE : View.VISIBLE);
        preparationProgress.setProgressTintList(ColorStateList.valueOf(style.accent));
        preparationProgress.setIndeterminateTintList(ColorStateList.valueOf(style.accent));
        preparationProgress.setIndeterminate(state.percent < 0);
        if (state.percent >= 0) preparationProgress.setProgress(state.percent);
        preparationProgress.setContentDescription(state.message + (state.percent >= 0 ? " " + state.percent + "%" : Z8Text.text(" in progress", " 진행 중")));
        preparationRetry.setVisibility(state.failed ? View.VISIBLE : View.GONE);
        preparationLog.setVisibility(state.failed ? View.VISIBLE : View.GONE);
    }
    private String projectName(String id) {
        if (id.isEmpty()) return Z8Text.text("Device shell", "기기 셸");
        if (projects.containsKey(id)) return projects.get(id);
        if (projectProblems.containsKey(id)) return projectProblems.get(id).name;
        for (Z8SessionCatalog.Entry entry : entries) if (entry.projectId.equals(id)) return entry.projectName;
        return Z8Text.text("Project", "프로젝트");
    }
    private String name(Z8SessionCatalog.Entry entry) { return names.getOrDefault(entry.handle, entry.title); }
    private int count(Z8SessionCatalog.Entry entry) { return notices.getOrDefault(entry.handle, 0); }
    private String status(Z8SessionCatalog.Entry entry) {
        return !entry.running ? Z8Text.text("Ended", "종료됨") : count(entry) > 0 ? Z8Text.text("Unread notifications: ", "미확인 알림 ") + count(entry) + Z8Text.text("", "개") : Z8Text.text("Session open", "세션 열림");
    }

    private void renderHeader() {
        header.removeAllViews();
        ImageView menu = iconAction(R.drawable.z8_ic_menu, Z8Text.text("Projects and sessions", "프로젝트와 세션 목록"), () -> {
            if (wide && side.getVisibility() == View.VISIBLE) { side.setVisibility(View.GONE); divider.setVisibility(View.GONE); }
            else openSessions();
        });
        menu.setId(R.id.z8_sessions_toggle);
        focusTag(menu, "menu");
        header.addView(menu, new LinearLayout.LayoutParams(dp(48), dp(48)));
        LinearLayout title = column(); title.setGravity(Gravity.CENTER_VERTICAL); title.setPadding(dp(8), 0, dp(5), 0);
        TextView primary = text(selectedProject == null ? "z8" : projectName(selectedProject), 16, style.text, true);
        headerProjectText = primary;
        primary.setId(R.id.z8_current_project); primary.setSingleLine(true); primary.setEllipsize(TextUtils.TruncateAt.END);
        title.addView(primary);

        header.addView(title, new LinearLayout.LayoutParams(0, -1, 1));
        headerResourceText = action("", Z8ResourceMonitor.scope(),
            () -> Toast.makeText(activity, Z8ResourceMonitor.scope(), Toast.LENGTH_LONG).show());
        headerResourceText.setTextSize(11);
        headerResourceText.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        headerResourceText.setFontFeatureSettings("tnum");
        headerResourceText.setSingleLine(true);
        headerResourceText.setTextColor(style.muted);
        headerResourceText.setGravity(Gravity.CENTER_VERTICAL | Gravity.END);
        headerResourceText.setPadding(dp(8), 0, dp(12), 0);
        headerResourceText.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_NONE);
        focusTag(headerResourceText, "resources");
        // Reserve the widest normal label; changing measurements never move the title.
        headerResourceWidth = (int) Math.ceil(headerResourceText.getPaint()
            .measureText(Z8Text.text("App  CPU 100%  RAM 99.9 GB", "앱  CPU 100%  RAM 99.9 GB"))) + dp(20);
        header.addView(headerResourceText, new LinearLayout.LayoutParams(headerResourceWidth, dp(48)));
        renderResourceSample();
        ImageView more = iconAction(R.drawable.z8_ic_settings, Z8Text.text("Settings", "환경설정"),
            () -> activity.startActivity(Z8SettingsActivity.intent(activity, selectedProject)));
        focusTag(more, "settings");
        header.addView(more, new LinearLayout.LayoutParams(dp(48), dp(48)));
        updateResourceVisibility();
    }

    private void renderResourceSample() {
        if (headerResourceText == null || disposed) return;
        headerResourceText.setText(resourceSample.label());
        headerResourceText.setContentDescription(resourceSample.description());
        headerResourceText.setTooltipText(resourceSample.description());
    }

    private void updateResourceVisibility() {
        if (headerResourceText == null || headerProjectText == null || disposed) return;
        int available = header.getWidth() - header.getPaddingLeft() - header.getPaddingRight();
        int titleWidth = (int) Math.ceil(headerProjectText.getPaint()
            .measureText(headerProjectText.getText().toString())) + dp(13);
        // On narrow windows, or when the project title needs this space, navigation wins.
        boolean fits = available >= dp(520) && available >= dp(96 + 24) + titleWidth + headerResourceWidth;
        headerResourceText.setVisibility(fits ? View.VISIBLE : View.GONE);
        boolean shouldSample = fits && visible;
        if (resourcesVisible == shouldSample) return;
        resourcesVisible = shouldSample;
        if (shouldSample) {
            resourceSample = Z8ResourceMonitor.Snapshot.pending();
            renderResourceSample();
            resourceMonitor.start();
        } else resourceMonitor.stop();
    }

    private void renderTabs() {
        tabRow.removeAllViews();
        String group = selectedProject;
        for (Z8SessionCatalog.Entry entry : entries) {
            if (!entry.projectId.equals(group)) continue;
            TextView tab = action(name(entry) + (!entry.running ? Z8Text.text(" · Ended", " · 종료") : count(entry) > 0 ? "  " + count(entry) : ""),
                Z8Text.text("Switch session: ", "세션 전환: ") + projectName(entry.projectId) + " / " + name(entry) + " / " + status(entry), () -> select(entry));
            tab.setId(R.id.z8_session_tab); tab.setTextSize(12); tab.setMinWidth(dp(80)); tab.setMaxWidth(dp(180));
            focusTag(tab, "tab/" + entry.handle);
            tab.setSingleLine(true); tab.setEllipsize(TextUtils.TruncateAt.END);
            tab.setSelected((entry.selected && !browserSelected));
            tab.setTextColor((entry.selected && !browserSelected) ? style.text : style.muted);
            tab.setTypeface(Typeface.create((entry.selected && !browserSelected) ? "sans-serif-medium" : "sans-serif", Typeface.NORMAL));
            // Keep the strip visually light: a 32dp feedback surface inside a
            // 48dp target, with one underline instead of a filled selected tile.
            Drawable background = new InsetDrawable(
                style.interactive(activity, Color.TRANSPARENT, Color.TRANSPARENT, 6), 0, dp(8), 0, dp(8));
            if ((entry.selected && !browserSelected)) {
                LayerDrawable layers = new LayerDrawable(new Drawable[]{background,
                    style.prism ? style.spectrum(activity, 1) : style.shape(activity, style.accent, Color.TRANSPARENT, 0)});
                layers.setLayerHeight(1, dp(2)); layers.setLayerGravity(1, Gravity.BOTTOM);
                layers.setLayerInset(1, dp(12), 0, dp(12), dp(8)); background = layers;
            }
            tab.setBackground(background);
            // Drawable insets must not change the label's center alignment.
            tab.setPadding(dp(12), 0, dp(12), 0);
            tab.setOnLongClickListener(view -> { sessionMenu(entry); return true; });
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-2, -1);
            tabRow.addView(tab, params);
            if ((entry.selected && !browserSelected)) scheduleRevealSelectedTab();
        }
        if (browserPane != null && group != null && group.equals(browserProject)) {
            TextView tab = action(Z8Text.text("Browser", "브라우저"), Z8Text.text("Select browser tab", "브라우저 탭 선택"), this::openBrowserTab);
            tab.setTextSize(12); tab.setMinWidth(dp(96)); tab.setSelected(browserSelected);
            tab.setTextColor(browserSelected ? style.text : style.muted);
            tab.setPadding(dp(12), 0, dp(12), 0); focusTag(tab, "browser-tab");
            Drawable background = new InsetDrawable(style.interactive(activity, Color.TRANSPARENT, Color.TRANSPARENT, 6), 0, dp(8), 0, dp(8));
            if (browserSelected) {
                LayerDrawable layers = new LayerDrawable(new Drawable[]{background, style.prism ? style.spectrum(activity, 1) : style.shape(activity, style.accent, Color.TRANSPARENT, 0)});
                layers.setLayerHeight(1, dp(2)); layers.setLayerGravity(1, Gravity.BOTTOM); layers.setLayerInset(1, dp(12), 0, dp(12), dp(8));
                background = layers;
            }
            tab.setBackground(background);
            tabRow.addView(tab, new LinearLayout.LayoutParams(-2, -1));
            if (browserSelected) scheduleRevealSelectedTab();
        }
        boolean hasTabs = tabRow.getChildCount() > 0;
        tabLine.setVisibility(hasTabs ? View.VISIBLE : View.GONE);
        tabDivider.setVisibility(hasTabs ? View.VISIBLE : View.GONE);
        addSession.setVisibility(hasTabs && group != null && !group.isEmpty() ? View.VISIBLE : View.GONE);
        openBrowser.setVisibility(hasTabs && group != null && !group.isEmpty() && browserPane == null ? View.VISIBLE : View.GONE);
    }

    /** Child positions are valid only after the new tab labels have been measured. */
    private void scheduleRevealSelectedTab() {
        if (disposed || revealPending) return;
        revealPending = true;
        tabs.getViewTreeObserver().addOnPreDrawListener(new android.view.ViewTreeObserver.OnPreDrawListener() {
            @Override public boolean onPreDraw() {
                if (tabs.getViewTreeObserver().isAlive()) tabs.getViewTreeObserver().removeOnPreDrawListener(this);
                revealPending = false;
                revealSelectedTab();
                return true;
            }
        });
        tabs.invalidate();
    }

    private void revealSelectedTab() {
        if (disposed || tabRow == null || tabs.getWidth() <= 0) return;
        for (int index = 0; index < tabRow.getChildCount(); index++) {
            View tab = tabRow.getChildAt(index);
            if (!tab.isSelected()) continue;
            int left = tab.getLeft(), right = tab.getRight(), scroll = tabs.getScrollX();
            if (left < scroll) tabs.scrollTo(left, 0);
            else if (right > scroll + tabs.getWidth()) tabs.scrollTo(right - tabs.getWidth(), 0);
            return;
        }
    }

    private void renderPanel(LinearLayout panel) {
        int scrollY = 0;
        for (int index = 0; index < panel.getChildCount(); index++)
            if (panel.getChildAt(index) instanceof ScrollView) scrollY = panel.getChildAt(index).getScrollY();
        panel.removeAllViews(); panel.setPadding(dp(12), dp(compact ? 4 : 12), dp(12), dp(8));
        panel.setBackgroundColor(style.panel);
        LinearLayout brand = row(); brand.setGravity(Gravity.CENTER_VERTICAL);
        brand.setPadding(dp(8), 0, dp(8), 0);
        if (style.prism) {
            ImageView emblem = icon(R.drawable.z8_ic_terminal, style.canvas, 20);
            emblem.setPadding(dp(7), dp(7), dp(7), dp(7));
            emblem.setBackground(style.spectrum(activity, 10));
            brand.addView(emblem, new LinearLayout.LayoutParams(dp(34), dp(34)));
        }
        LinearLayout brandCopy = column();
        TextView mark = text("z8", 22, style.text, true); mark.setLetterSpacing(-.05f);
        brandCopy.addView(mark);
        LinearLayout.LayoutParams wordmarkParams = new LinearLayout.LayoutParams(0, -2, 1);
        wordmarkParams.leftMargin = dp(style.prism ? 12 : 0); brand.addView(brandCopy, wordmarkParams);
        int unread = 0;
        for (int count : notices.values()) unread += count;
        final int unreadCount = unread;
        android.widget.FrameLayout bell = new android.widget.FrameLayout(activity);
        ImageView attention = iconAction(R.drawable.z8_ic_notifications_none,
            unreadCount > 0 ? Z8Text.text("Notifications, unread: ", "알림, 미확인 ") + unreadCount + Z8Text.text("", "개") : Z8Text.text("Notifications", "알림"),
            () -> activity.startActivity(new Intent(activity, Z8AttentionActivity.class)));
        focusTag(attention, "attention");
        bell.addView(attention, new android.widget.FrameLayout.LayoutParams(dp(48), dp(48)));
        if (unreadCount > 0) {
            View dot = new View(activity);
            dot.setBackground(style.shape(activity, style.accent, style.panel, 3));
            dot.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            android.widget.FrameLayout.LayoutParams badge = new android.widget.FrameLayout.LayoutParams(dp(6), dp(6));
            badge.gravity = Gravity.TOP | Gravity.RIGHT; badge.topMargin = dp(10); badge.rightMargin = dp(10);
            bell.addView(dot, badge);
        }
        brand.addView(bell, new LinearLayout.LayoutParams(dp(48), dp(48)));
        panel.addView(brand, new LinearLayout.LayoutParams(-1, dp(48)));

        LinearLayout caption = row(); caption.setGravity(Gravity.CENTER_VERTICAL);
        TextView label = text(Z8Text.text("Project", "프로젝트"), 11, style.muted, true); label.setPadding(dp(8), 0, 0, 0);
        caption.addView(label, new LinearLayout.LayoutParams(0, -2, 1));
        ImageView projectAdd = iconAction(R.drawable.z8_ic_add, Z8Text.text("Create project", "프로젝트 만들기"), this::createProject);
        focusTag(projectAdd, "project-create");
        caption.addView(projectAdd, new LinearLayout.LayoutParams(dp(48), dp(48)));
        add(panel, caption, compact ? 0 : 8);
        ScrollView scroll = new ScrollView(activity); scroll.setFillViewport(false);
        scroll.setVerticalScrollBarEnabled(true); scroll.setClipToPadding(false);
        LinearLayout groups = column(); scroll.addView(groups);
        panel.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        LinkedHashMap<String, String> all = new LinkedHashMap<>(projects);
        for (Z8Projects.Problem problem : projectProblems.values()) all.put(problem.id, problem.name);
        for (Z8SessionCatalog.Entry entry : entries) if (!entry.projectId.isEmpty()) all.putIfAbsent(entry.projectId, entry.projectName);
        for (Map.Entry<String, String> project : all.entrySet()) group(groups, project.getKey(), project.getValue());
        boolean nativePresent = false;
        for (Z8SessionCatalog.Entry entry : entries) if (entry.projectId.isEmpty()) nativePresent = true;
        if (nativePresent) group(groups, "", Z8Text.text("Device shell", "기기 셸"));
        if (all.isEmpty() && !nativePresent) {
            TextView empty = text(projectsLoaded ? Z8Text.text("Use + to create your first project.", "+로 첫 프로젝트를 만들어보세요.") : Z8Text.text("Loading projects…", "프로젝트 불러오는 중…"), 13, style.muted, false);
            empty.setLineSpacing(dp(4), 1); empty.setPadding(dp(8), dp(16), dp(8), dp(16)); groups.addView(empty);

        }
        if (!projectError.isEmpty()) add(groups, text(projectError, 12, style.danger, false), 10);
        final int previousScroll = scrollY;
        scroll.post(() -> { if (!disposed) scroll.scrollTo(0, previousScroll); });

    }

    private void group(LinearLayout parent, String id, String title) {
        List<Z8SessionCatalog.Entry> children = new ArrayList<>();
        for (Z8SessionCatalog.Entry entry : entries) if (entry.projectId.equals(id)) children.add(entry);
        LinearLayout group = column(); group.setPadding(0, 0, 0, dp(12));
        LinearLayout heading = row(); heading.setGravity(Gravity.CENTER_VERTICAL);
        boolean closed = collapsed.contains(id);
        ImageView toggle = iconAction(closed ? R.drawable.z8_ic_chevron_right : R.drawable.z8_ic_expand_more,
            Z8Text.text("Project sessions: ", "프로젝트 세션 목록: ") + title + (closed ? Z8Text.text(" · Collapsed", " · 접힘") : Z8Text.text(" · Expanded", " · 펼침")), () -> {
                if (collapsed.contains(id)) collapsed.remove(id); else collapsed.add(id);
                fingerprint = ""; refresh();
            });
        focusTag(toggle, "project/" + id + "/toggle");
        heading.addView(toggle, new LinearLayout.LayoutParams(dp(48), dp(48)));
        TextView label = action(title, Z8Text.text("Select project: ", "프로젝트 선택: ") + title, () -> selectProject(id));
        label.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
        focusTag(label, "project/" + id + "/select");
        label.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        label.setSingleLine(true); label.setEllipsize(TextUtils.TruncateAt.END); label.setTextSize(12);
        label.setPadding(0, 0, dp(4), 0);
        if (!id.isEmpty() && !projectProblems.containsKey(id))
            label.setOnLongClickListener(view -> { deleteProject(id, title); return true; });
        label.setSelected(id.equals(selectedProject));
        label.setTextColor(id.equals(selectedProject) ? style.accent : style.text);
        heading.addView(label, new LinearLayout.LayoutParams(0, dp(48), 1));
        TextView total = text(Integer.toString(children.size() + (id.equals(browserProject) ? 1 : 0)), 11, style.faint, false);
        total.setGravity(Gravity.CENTER); heading.addView(total, new LinearLayout.LayoutParams(dp(20), dp(48)));
        if (!id.isEmpty() && !projectProblems.containsKey(id)) {
            ImageView add = iconAction(R.drawable.z8_ic_add, title + Z8Text.text(": new session", "에 새 세션"), () -> openShell(id, title));
            add.setEnabled(!Z8GuestSessionLauncher.hasPending(activity.getTermuxService()));
            add.setAlpha(add.isEnabled() ? 1f : .5f);
            focusTag(add, "project/" + id + "/add");
            heading.addView(add, new LinearLayout.LayoutParams(dp(48), dp(48)));
        }
        group.addView(heading);
        if (projectProblems.containsKey(id)) {
            TextView problem = action(Z8Text.text("Check project info", "프로젝트 정보 확인 필요"), title + Z8Text.text(": check project info", ": 프로젝트 정보 확인 필요"),
                () -> showProjectProblem(id));
            problem.setTextSize(12); problem.setTextColor(style.danger);
            problem.setPadding(dp(30), 0, dp(8), 0);
            problem.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
            focusTag(problem, "project/" + id + "/problem");
            group.addView(problem, new LinearLayout.LayoutParams(-1, dp(48)));
        }
        if (!closed) {
            for (Z8SessionCatalog.Entry entry : children) {
                LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2); params.topMargin = dp(2);
                group.addView(sessionRow(entry), params);
            }
            if (id.equals(browserProject)) {
                TextView browser = action(Z8Text.text("Browser", "브라우저"), Z8Text.text("Select project browser", "프로젝트 브라우저 선택"), this::openBrowserTab);
                browser.setTextSize(13); browser.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
                browser.setPadding(dp(40), 0, dp(12), 0); browser.setSelected(browserSelected);
                browser.setTextColor(browserSelected ? style.text : style.muted);
                browser.setBackground(browserSelected && style.prism ? style.selectedSurface(activity, 8)
                    : style.interactive(activity, browserSelected ? style.selected : Color.TRANSPARENT, Color.TRANSPARENT, 7));
                focusTag(browser, "project-browser");
                group.addView(browser, new LinearLayout.LayoutParams(-1, dp(48)));
            }
            if (children.isEmpty() && !id.equals(browserProject) && !projectProblems.containsKey(id)) {
                TextView empty = text(Z8Text.text("No open sessions yet", "아직 열린 세션이 없어요"), 12, style.muted, false);
                empty.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
                empty.setPadding(dp(30), 0, dp(8), 0);
                group.addView(empty, new LinearLayout.LayoutParams(-1, dp(48)));
            }
        }
        parent.addView(group);
    }

    private void showProjectProblem(String id) {
        Z8Projects.Problem problem = projectProblems.get(id);
        if (problem == null) return;
        showDialog(dialogBuilder().setTitle(problem.name)
            .setMessage(Z8Text.text("Could not read this project's information. No files were deleted. You can still use other projects.\n\n", "이 프로젝트의 정보를 읽지 못했습니다. 파일은 삭제하지 않았으며 다른 프로젝트는 계속 사용할 수 있습니다.\n\n")
                + problem.detail)
            .setNegativeButton(Z8Text.text("Close", "닫기"), null)
            .setPositiveButton(Z8Text.text("Check again", "다시 확인"), (dialog, which) -> loadProjects()).create(), false);
    }

    private View sessionRow(Z8SessionCatalog.Entry entry) {
        LinearLayout item = row(); item.setId(R.id.z8_session_row); item.setGravity(Gravity.CENTER_VERTICAL);
        focusTag(item, "session/" + entry.handle);
        item.setPadding(dp(12), dp(8), dp(10), dp(8)); item.setMinimumHeight(dp(48));
        item.setBackground((entry.selected && !browserSelected) && style.prism ? style.selectedSurface(activity, 8)
            : style.interactive(activity, (entry.selected && !browserSelected) ? style.selected : Color.TRANSPARENT, Color.TRANSPARENT, 7));
        item.setSelected((entry.selected && !browserSelected)); interactive(item);
        item.setContentDescription(Z8Text.text("Select session: ", "세션 선택: ") + projectName(entry.projectId) + " / " + name(entry) + " / " + status(entry));
        item.setOnClickListener(view -> select(entry)); item.setOnLongClickListener(view -> { sessionMenu(entry); return true; });
        ImageView icon = icon(count(entry) > 0 ? R.drawable.z8_ic_notifications_none : toolIcon(entry.tool),
            count(entry) > 0 ? style.accent : style.prism ? toolColor(entry.tool) : (entry.selected && !browserSelected) ? style.accent : style.faint, 18);
        item.addView(icon, new LinearLayout.LayoutParams(dp(18), dp(18)));
        LinearLayout copy = column(); copy.setPadding(dp(10), 0, dp(5), 0);
        TextView title = text(name(entry), 13, (entry.selected && !browserSelected) ? style.text : style.muted, (entry.selected && !browserSelected));
        title.setSingleLine(true); title.setEllipsize(TextUtils.TruncateAt.END); copy.addView(title);
        if (!entry.running || count(entry) > 0) {
            TextView detail = text(status(entry), 11, count(entry) > 0 ? style.accent : style.faint, false);
            detail.setPadding(0, dp(3), 0, 0); copy.addView(detail);
        }
        item.addView(copy, new LinearLayout.LayoutParams(0, -2, 1));
        if (count(entry) > 0) {
            TextView badge = text(Integer.toString(count(entry)), 11, style.accent, true);
            badge.setGravity(Gravity.CENTER); badge.setBackground(style.shape(activity, style.raised, Color.TRANSPARENT, 5));
            item.addView(badge, new LinearLayout.LayoutParams(dp(24), dp(24)));
        } else if (!"Terminal".equals(entry.tool) && !"Shell".equals(entry.tool) && !entry.title.equals(entry.tool)) {
            TextView kind = text(entry.tool, 10, style.faint, false);
            kind.setSingleLine(true); kind.setMaxWidth(dp(52)); kind.setEllipsize(TextUtils.TruncateAt.END);
            item.addView(kind);
        }
        return item;
    }

    private void openBrowserTab() {
        if (disposed || selectedProject == null || selectedProject.isEmpty()) return;
        // Reopening an existing browser from a different terminal must return
        // to that terminal, not the one that originally created the tab.
        if (!browserSelected) {
            TerminalSession origin = activity.getCurrentSession();
            browserSessionHandle = origin == null ? null : origin.mHandle;
        }
        if (browserPane == null) {
            browserProject = selectedProject;
            browserPane = new Z8BrowserPane(activity, this::closeBrowserTab, this::returnFromBrowser,
                () -> externalOpening = true);
            terminalSurface.addView(browserPane, new LinearLayout.LayoutParams(-1, -1));
            browserPane.setForeground(visible);
        }
        browserSelected = true;
        activity.getTerminalView().z8SuspendInput();
        activity.getTerminalView().clearFocus();
        android.view.inputmethod.InputMethodManager keyboard = (android.view.inputmethod.InputMethodManager) activity.getSystemService(Context.INPUT_METHOD_SERVICE);
        if (keyboard != null) keyboard.hideSoftInputFromWindow(activity.getTerminalView().getWindowToken(), 0);
        fingerprint = ""; refresh();
    }

    private void closeBrowserTab() {
        boolean returnToTerminal = browserSelected;
        browserSelected = false;
        if (browserPane != null) { browserPane.dispose(); terminalSurface.removeView(browserPane); browserPane = null; }
        browserProject = null; browserSessionHandle = null;
        fingerprint = ""; if (!disposed) refresh();
        if (!disposed && returnToTerminal) {
            if (activity.getCurrentSession() != null) activity.getTerminalView().requestFocus();
            restoreTerminalInput();
        }
    }

    private void returnFromBrowser() {
        browserSelected = false;
        for (Z8SessionCatalog.Entry entry : entries) {
            if (entry.handle.equals(browserSessionHandle)) { select(entry); return; }
        }
        fingerprint = ""; refresh();
        if (activity.getCurrentSession() != null) activity.getTerminalView().requestFocus();
        restoreTerminalInput();
    }

    public boolean onBackPressed() {
        if (!browserSelected || browserPane == null) return false;
        if (!browserPane.goBack()) returnFromBrowser();
        return true;
    }

    public boolean dispatchKeyEvent(android.view.KeyEvent event) { return workspaceKeys.dispatch(event); }
    public void onFocusLost() { workspaceKeys.reset(); }
    public void restoreTerminalInput() {
        main.removeCallbacks(restoreInput);
        main.post(restoreInput);
    }
    private void cycleWorkspaceTabs(int direction) {
        List<Z8SessionCatalog.Entry> local = new ArrayList<>();
        int selected = -1;
        for (Z8SessionCatalog.Entry entry : entries) {
            if (!entry.projectId.equals(selectedProject)) continue;
            if (entry.selected && !browserSelected) selected = local.size();
            local.add(entry);
        }
        int total = local.size() + (browserPane != null ? 1 : 0);
        if (total == 0) return;
        if (browserSelected) selected = local.size();
        int target = Math.floorMod(selected + direction, total);
        if (target == local.size()) openBrowserTab();
        else select(local.get(target));
    }

    private void select(Z8SessionCatalog.Entry entry) {
        if (!Z8SessionCatalog.contains(activity.getTermuxService(), entry.session)) {
            toast(Z8Text.text("This session is no longer open.", "이 세션은 더 이상 열려 있지 않습니다.")); fingerprint = ""; refresh(); return;
        }
        browserSelected = false;
        activity.getTermuxTerminalSessionClient().setCurrentSession(entry.session);
        activity.getTermuxTerminalSessionClient().setCurrentStoredSession();
        activity.getDrawer().closeDrawers();
        activity.getTerminalView().requestFocus();
        refresh();
        restoreTerminalInput();
    }

    private void rememberProject(String id) {
        if (browserProject != null && !browserProject.equals(id)) closeBrowserTab();
        selectedProject = id;
        activity.getSharedPreferences(NAVIGATION_PREFS, Context.MODE_PRIVATE)
            .edit().putString("project", id).apply();
    }

    /** Called only after a real PTY selection (including notification/keyboard navigation). */
    public void onSessionSelected(TerminalSession session) {
        if (session == null) return;
        browserSelected = false;
        Z8SessionOrigin origin = Z8SessionOrigin.of(session);
        // A notification may select another terminal in this project while
        // the browser is open. Preserve that explicit destination on return.
        if (externalOpening && browserPane != null && origin != null
                && origin.projectId.equals(browserProject)) browserSessionHandle = session.mHandle;
        rememberProject(origin == null ? "" : origin.projectId);
        if (origin != null) lastSessions.put(origin.projectId, session.mHandle);
        fingerprint = "";
        restoreTerminalInput();
    }

    /** Restore navigation, never create work or fall through to another project's session. */
    public void restoreSelection() {
        if (disposed || activity.getTermuxService() == null) return;
        if (browserSelected && browserPane != null && !externalOpening) { refresh(); return; }
        if (selectedProject != null) { selectProject(selectedProject, false); return; }
        TerminalSession previous = activity.getTermuxTerminalSessionClient().getCurrentStoredSessionOrLast();
        if (previous != null) activity.getTermuxTerminalSessionClient().setCurrentSession(previous);
        else clearTerminal();
    }

    public void selectProject(String id) { selectProject(id, true); }

    private void selectProject(String id, boolean closeDrawer) {
        if (disposed || id == null) return;
        rememberProject(id);
        collapsed.remove(id);
        entries = Z8SessionCatalog.snapshot(activity.getTermuxService(), activity.getCurrentSession());
        Z8SessionCatalog.Entry target = null;
        String remembered = lastSessions.get(id);
        TerminalSession stored = activity.getTermuxTerminalSessionClient().getCurrentStoredSessionOrLast();
        if (remembered == null && stored != null) remembered = stored.mHandle;
        for (Z8SessionCatalog.Entry entry : entries) {
            if (!entry.projectId.equals(id)) continue;
            if (target == null || !target.running && entry.running) target = entry;
            if (entry.handle.equals(remembered) && entry.running) { target = entry; break; }
        }
        if (target != null) activity.getTermuxTerminalSessionClient().setCurrentSession(target.session);
        else clearTerminal();
        if (closeDrawer) activity.getDrawer().closeDrawers();
        fingerprint = ""; refresh();
    }

    private void clearTerminal() {
        // Detach only the view. Every existing PTY remains owned by the service.
        activity.getTerminalView().attachSession(null);
        activity.getTerminalView().clearFocus();
        android.view.inputmethod.InputMethodManager keyboard = (android.view.inputmethod.InputMethodManager)
            activity.getSystemService(Context.INPUT_METHOD_SERVICE);
        if (keyboard != null) keyboard.hideSoftInputFromWindow(activity.getTerminalView().getWindowToken(), 0);
        fingerprint = ""; refresh();
    }

    private void createForCurrent() { createForCurrent(null); }

    public void createForCurrent(String name) {
        refresh();
        if (selectedProject == null || selectedProject.isEmpty()) { openSessions(); return; }
        openShell(selectedProject, name == null ? projectName(selectedProject) : name);
    }

    private void openShell(String projectId, String projectName) {
        if (disposed || !requireConnectedService()) return;
        if (projectId.isEmpty()) { openSessions(); return; }
        if (projectProblems.containsKey(projectId)) { showProjectProblem(projectId); return; }
        if (Z8ProjectRemoval.isDeleting(projectId)) { toast(Z8Text.text("Deleting the project.", "프로젝트를 삭제하는 중입니다.")); return; }
        selectProject(projectId, false);
        if (entries.size() >= 8) { toast(Z8Text.text("You can open up to 8 terminals. Choose a session to close first.", "터미널은 최대 8개까지 열 수 있습니다. 종료할 세션을 명시적으로 선택해 주세요.")); return; }
        long now = SystemClock.elapsedRealtime();
        if (now - lastLaunchTap < 500 || Z8GuestSessionLauncher.hasPending(activity.getTermuxService())) return;
        lastLaunchTap = now;
        collapsed.remove(projectId);
        activity.getDrawer().closeDrawers();
        activity.getTermuxTerminalSessionClient().addGuestSession(projectId, null, projectName, null);
        refresh();
    }

    private void sessionMenu(Z8SessionCatalog.Entry entry) {
        choiceDialog(name(entry), projectName(entry.projectId) + "  /  " + entry.tool,
            new String[]{Z8Text.text("Rename", "이름 변경"), Z8Text.text("Copy recent output", "최근 출력 복사"), Z8Text.text("Notifications", "알림"), entry.running ? Z8Text.text("Close terminal…", "터미널 종료…") : Z8Text.text("Remove from list", "목록에서 제거")},
            null, new int[]{R.drawable.z8_ic_edit, R.drawable.z8_ic_copy, R.drawable.z8_ic_notifications_none, R.drawable.z8_ic_close}, true, which -> {
                if (which == 0) rename(entry);
                else if (which == 1) copyRecentOutput(entry);
                else if (which == 2) activity.startActivity(new Intent(activity, Z8AttentionActivity.class));
                else end(entry);
            });
    }

    private void copyRecentOutput(Z8SessionCatalog.Entry entry) {
        if (!Z8SessionCatalog.contains(activity.getTermuxService(), entry.session)
                || entry.session.getEmulator() == null) { toast(Z8Text.text("There is no output to copy.", "복사할 출력이 없습니다.")); return; }
        com.termux.terminal.TerminalEmulator emulator = entry.session.getEmulator();
        com.termux.terminal.TerminalBuffer buffer = emulator.getScreen();
        // Bounded native copy; does not execute a CLI command or include other sessions.
        String output = buffer.getSelectedText(0, -Math.min(1000, buffer.getActiveTranscriptRows()),
            emulator.mColumns, emulator.mRows).trim();
        if (output.length() > 128 * 1024) {
            int start = output.length() - 128 * 1024;
            if (Character.isLowSurrogate(output.charAt(start))) start++;
            output = output.substring(start);
        }
        if (output.isEmpty()) { toast(Z8Text.text("There is no output to copy.", "복사할 출력이 없습니다.")); return; }
        com.termux.shared.interact.ShareUtils.copyTextToClipboard(activity, output, Z8Text.text("Recent terminal output copied.", "최근 터미널 출력을 복사했어요."));
    }

    private void rename(Z8SessionCatalog.Entry entry) {
        AlertDialog.Builder builder = dialogBuilder();
        EditText input = new EditText(builder.getContext()); input.setSingleLine(true); input.setText(entry.title);
        input.setTextColor(style.text); input.setTextSize(16); input.setBackgroundTintList(ColorStateList.valueOf(style.accent));
        input.setFilters(new InputFilter[]{new InputFilter.LengthFilter(96)}); input.selectAll();
        LinearLayout field = column(); field.setPadding(dp(24), dp(8), dp(24), dp(8));
        field.addView(input, new LinearLayout.LayoutParams(-1, -2));
        TextView error = text(Z8Text.text("Enter a session name.", "세션 이름을 입력해 주세요."), 12, style.danger, false);
        error.setPadding(0, dp(8), 0, 0);
        error.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        error.setVisibility(View.GONE); field.addView(error);
        AlertDialog dialog = builder.setTitle(Z8Text.text("Rename session", "세션 이름 변경")).setView(field)
            .setNegativeButton(Z8Text.text("Cancel", "취소"), null).setPositiveButton(Z8Text.text("Save", "저장"), null).create();
        showDialog(dialog, false);
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
                if (!Z8SessionCatalog.contains(activity.getTermuxService(), entry.session)) { dialog.dismiss(); return; }
                String value = input.getText().toString().replaceAll("[\\p{Cntrl}\\p{Cf}\\p{Zl}\\p{Zp}]", "").trim();
                if (value.isEmpty()) {
                    error.setVisibility(View.VISIBLE);
                    input.setBackgroundTintList(ColorStateList.valueOf(style.danger));
                    return;
                }
                entry.session.mSessionName = value;
                TermuxSession wrapper = activity.getTermuxService().getTermuxSessionForTerminalSession(entry.session);
                if (wrapper != null) wrapper.getExecutionCommand().shellName = value;
                activity.getTermuxTerminalSessionClient().termuxSessionListNotifyUpdated(); refresh();
                dialog.dismiss();
            });
    }

    private void end(Z8SessionCatalog.Entry entry) {
        if (Z8ProjectRemoval.isDeleting(entry.projectId)) { toast(Z8Text.text("Deleting the project.", "프로젝트를 삭제하는 중입니다.")); return; }
        if (Z8ProjectRemoval.isStopping(entry.session)) { toast(Z8Text.text("Waiting for the terminal to close.", "터미널 종료를 확인하는 중입니다.")); return; }
        showDialog(dialogBuilder().setTitle(entry.running ? Z8Text.text("Close this session?", "이 세션을 종료할까요?") : Z8Text.text("Remove this ended session?", "종료된 세션을 제거할까요?"))
            .setMessage(projectName(entry.projectId) + " / " + name(entry)
                + (entry.running ? Z8Text.text("\n\nThis stops running programs. Switching to another session keeps them running.", "\n\n실행 중인 프로그램이 중단됩니다. 다른 세션으로 전환하는 동작과는 다릅니다.") : Z8Text.text("\nProject files will be kept.", "\n프로젝트 파일은 유지됩니다.")))
            .setNegativeButton(Z8Text.text("Cancel", "취소"), null).setPositiveButton(entry.running ? Z8Text.text("Close session", "세션 종료") : Z8Text.text("Remove", "제거"), (dialog, which) -> {
                if (!Z8SessionCatalog.contains(activity.getTermuxService(), entry.session)) return;
                Z8ProjectRemoval.stopSession(activity.getTermuxService(), entry.session, message -> {
                    if (disposed || activity.isFinishing()) return;
                    if (message != null) { toast(message); fingerprint = ""; refresh(); return; }
                    if (activity.getCurrentSession() == entry.session) {
                        activity.getTerminalView().attachSession(null);
                        activity.z8RestoreSessionSelection();
                    }
                    fingerprint = ""; refresh();
                });
                fingerprint = ""; refresh();
            }).create(), true);
    }

    private boolean requireConnectedService() {
        TermuxService service = activity.getTermuxService();
        if (service != null && !service.wantsToStop() && !service.z8IsStopRequested()) return true;
        activity.z8RequestServiceConnection();
        toast(Z8Text.text("Connecting to the runtime. Try again shortly.", "실행 환경에 연결 중입니다. 잠시 후 다시 시도해 주세요."));
        return false;
    }

    private boolean canDeleteProject(String projectId) {
        if (!requireConnectedService()) return false;
        if (Z8ProjectRemoval.isDeleting(projectId)) { toast(Z8Text.text("Deleting the project.", "프로젝트를 삭제하는 중입니다.")); return false; }
        if (Z8GuestSessionLauncher.hasPending(activity.getTermuxService())) {
            toast(Z8Text.text("Wait for terminal setup to finish, then try again.", "터미널 준비가 끝난 뒤 다시 시도해 주세요.")); return false;
        }
        return true;
    }

    private void deleteProject(String projectId, String name) {
        if (!canDeleteProject(projectId)) return;
        int running = 0;
        for (Z8SessionCatalog.Entry entry : Z8SessionCatalog.snapshot(activity.getTermuxService(), null))
            if (projectId.equals(entry.projectId) && entry.running) running++;
        String detail = (running > 0 ? Z8Text.text("Open terminals to close: ", "열린 터미널 ") + running + Z8Text.text(".\n\n", "개를 함께 종료합니다.\n\n") : "")
            + Z8Text.text("This deletes the source code, Linux environment, HOME, and project settings. This cannot be undone.", "소스 코드, Linux 환경, HOME 및 프로젝트 설정을 모두 삭제합니다. 되돌릴 수 없습니다.");
        AlertDialog dialog = dialogBuilder().setTitle(Z8Text.text("Delete " + name, name + " 삭제"))
            .setMessage(detail).setNegativeButton(Z8Text.text("Cancel", "취소"), null).setPositiveButton(running > 0 ? Z8Text.text("Close all and delete", "모두 종료하고 삭제") : Z8Text.text("Delete", "삭제"), null).create();
        showDialog(dialog, true);
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
            if (!canDeleteProject(projectId)) { dialog.dismiss(); return; }
            dialog.setCancelable(false);
            dialog.setMessage(Z8Text.text("Closing terminals and deleting the project…", "터미널을 종료하고 프로젝트를 삭제하는 중…"));
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(false);
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setEnabled(false);
            Z8ProjectRemoval.begin(activity.getTermuxService(), projectId, message -> {
                if (disposed || activity.isFinishing()) return;
                dialog.dismiss();
                if (message != null) { toast(message); loadProjects(); return; }
                projects.remove(projectId); lastSessions.remove(projectId); collapsed.remove(projectId);
                if (projectId.equals(selectedProject)) { rememberProject(null); clearTerminal(); }
                fingerprint = ""; refresh();
                toast(Z8Text.text("Project deleted.", "프로젝트를 삭제했습니다."));
            });
        });
    }

    private void createProject() {
        if (!requireConnectedService()) return;
        AlertDialog.Builder builder = dialogBuilder();
        EditText input = new EditText(builder.getContext());
        input.setSingleLine(true); input.setHint(Z8Text.text("Project name", "프로젝트 이름")); input.setTextColor(style.text);
        input.setFilters(new InputFilter[]{new InputFilter.LengthFilter(96)});
        input.setBackgroundTintList(ColorStateList.valueOf(style.accent));
        LinearLayout field = column(); field.setPadding(dp(24), dp(8), dp(24), dp(8));
        field.addView(input, new LinearLayout.LayoutParams(-1, -2));
        TextView error = text("", 12, style.danger, false);
        error.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        error.setPadding(0, dp(8), 0, 0); error.setVisibility(View.GONE); field.addView(error);
        AlertDialog dialog = builder.setTitle(Z8Text.text("New project", "새 프로젝트")).setView(field)
            .setNegativeButton(Z8Text.text("Cancel", "취소"), null).setPositiveButton(Z8Text.text("Create", "만들기"), null).create();
        showDialog(dialog, false);
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
            final String name;
            try { name = Z8Files.name(input.getText().toString().trim()); }
            catch (Exception invalid) { error.setText(Z8Text.text("Enter a name. Slashes and control characters are not allowed.", "이름을 입력해 주세요. / 와 제어 문자는 사용할 수 없어요.")); error.setVisibility(View.VISIBLE); return; }
            if (!requireConnectedService()) return;
            dialog.setCancelable(false); input.setEnabled(false);
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(false);
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setEnabled(false);
            Context app = activity.getApplicationContext();
            TermuxService service = activity.getTermuxService();
            PROJECT_WRITES.execute(() -> {
                try {
                    Z8Projects.Project created = new Z8Projects(app).create(name);
                    app.getSharedPreferences(NAVIGATION_PREFS, Context.MODE_PRIVATE).edit().putString("project", created.id).apply();
                    PROJECT_MAIN.post(() -> {
                        String request = Z8GuestSessionLauncher.newRequest(service);
                        if (request != null) Z8GuestSessionLauncher.request(service, request, created.id, null, created.name, null);
                        if (disposed || activity.isFinishing()) return;
                        dialog.dismiss(); projects.put(created.id, created.name); selectProject(created.id);
                    });
                } catch (Exception failure) {
                    main.post(() -> {
                        if (disposed || activity.isFinishing()) return;
                        dialog.setCancelable(true); input.setEnabled(true);
                        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(true);
                        dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setEnabled(true);
                        error.setText(Z8Text.text("Could not create the project. Check available storage.", "프로젝트를 만들지 못했습니다. 저장 공간을 확인해 주세요.")); error.setVisibility(View.VISIBLE);
                    });
                }
            });
        });
        input.requestFocus();
        if (dialog.getWindow() != null) dialog.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE);
    }

    private AlertDialog.Builder dialogBuilder() {
        return new AlertDialog.Builder(activity, palette.light
            ? android.R.style.Theme_Material_Light_Dialog_Alert : android.R.style.Theme_Material_Dialog_Alert);
    }

    private void showDialog(AlertDialog dialog, boolean destructive) {
        dialog.show();
        Window window = dialog.getWindow();
        if (window != null) {
            window.setBackgroundDrawable(style.shape(activity, style.surface, style.border, 16));
            window.setLayout(dp(Math.max(240, Math.min(420,
                activity.getResources().getConfiguration().screenWidthDp - 32))), -2);
            window.setDimAmount(.48f);
        }
        if (dialog.getButton(AlertDialog.BUTTON_POSITIVE) != null)
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setTextColor(destructive ? style.danger : style.accent);
        if (dialog.getButton(AlertDialog.BUTTON_NEGATIVE) != null)
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setTextColor(style.muted);
    }

    private void choiceDialog(String title, String subtitle, String[] labels, String[] details,
            int[] icons, boolean destructiveLast, IntConsumer selection) {
        AlertDialog dialog = dialogBuilder().create();
        LinearLayout content = column(); content.setPadding(dp(16), dp(20), dp(16), dp(12));
        TextView heading = text(title, 18, style.text, true);
        heading.setMaxLines(2); heading.setEllipsize(TextUtils.TruncateAt.END);
        heading.setPadding(dp(8), 0, dp(8), 0); content.addView(heading);
        TextView context = text(subtitle, 12, style.muted, false);
        context.setPadding(dp(8), dp(7), dp(8), dp(16)); content.addView(context);
        ScrollView scroll = new ScrollView(activity); scroll.setFillViewport(false);
        LinearLayout options = column(); scroll.addView(options);
        int rowHeight = Math.max(details == null ? 52 : 68,
            Math.round((details == null ? 18 : 32) * activity.getResources().getConfiguration().fontScale + 24));
        int available = Math.max(104, activity.getResources().getConfiguration().screenHeightDp - 210);
        content.addView(scroll, new LinearLayout.LayoutParams(-1, dp(Math.min(available, labels.length * rowHeight))));
        for (int index = 0; index < labels.length; index++) {
            final int selected = index;
            boolean danger = destructiveLast && index == labels.length - 1;
            LinearLayout option = row(); option.setGravity(Gravity.CENTER_VERTICAL);
            option.setPadding(dp(10), dp(8), dp(10), dp(8)); interactive(option);
            option.setBackground(style.interactive(activity, Color.TRANSPARENT, Color.TRANSPARENT, 8));
            option.setContentDescription(labels[index] + (details == null ? "" : ", " + details[index]));
            ImageView optionIcon = icon(icons[index], danger ? style.danger
                : details != null && style.prism ? toolColor(labels[index]) : style.muted, 20);
            int iconBox = details == null ? 20 : 36;
            if (details != null) {
                optionIcon.setPadding(dp(8), dp(8), dp(8), dp(8));
                optionIcon.setBackground(style.shape(activity, style.raised, style.border, 10));
            }
            option.addView(optionIcon, new LinearLayout.LayoutParams(dp(iconBox), dp(iconBox)));
            LinearLayout copy = column(); copy.setPadding(dp(14), 0, 0, 0);
            TextView optionTitle = text(labels[index], 14, danger ? style.danger : style.text, true);
            optionTitle.setSingleLine(true); optionTitle.setEllipsize(TextUtils.TruncateAt.END); copy.addView(optionTitle);
            if (details != null) {
                TextView explanation = text(details[index], 12, style.muted, false);
                explanation.setSingleLine(true); explanation.setEllipsize(TextUtils.TruncateAt.END);
                explanation.setPadding(0, dp(4), 0, 0); copy.addView(explanation);
            }
            option.addView(copy, new LinearLayout.LayoutParams(0, -2, 1));
            option.setOnClickListener(view -> { dialog.dismiss(); selection.accept(selected); });
            options.addView(option, new LinearLayout.LayoutParams(-1, dp(rowHeight)));
        }
        TextView cancel = action(Z8Text.text("Cancel", "취소"), Z8Text.text("Cancel", "취소"), dialog::dismiss); cancel.setTextColor(style.muted);
        LinearLayout.LayoutParams cancelParams = new LinearLayout.LayoutParams(dp(88), dp(48));
        cancelParams.gravity = Gravity.END; cancelParams.topMargin = dp(8); content.addView(cancel, cancelParams);
        dialog.setView(content); showDialog(dialog, false);
        if (dialog.getWindow() != null) dialog.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN);
    }

    private void toast(String message) { Toast.makeText(activity, message, Toast.LENGTH_LONG).show(); }
    private int toolIcon(String tool) {
        return tool.startsWith("Claude") ? R.drawable.z8_ic_auto_awesome
            : tool.startsWith("Codex") ? R.drawable.z8_ic_code : R.drawable.z8_ic_terminal;
    }
    private int toolColor(String tool) {
        return tool.startsWith("Claude") ? 0xffffbd9b : tool.startsWith("Codex") ? 0xffcbb5ff : 0xff9acbff;
    }
    private LinearLayout row() { LinearLayout view = new LinearLayout(activity); view.setOrientation(LinearLayout.HORIZONTAL); return view; }
    private LinearLayout column() { LinearLayout view = new LinearLayout(activity); view.setOrientation(LinearLayout.VERTICAL); return view; }
    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(activity); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setTypeface(Typeface.create(bold ? "sans-serif-medium" : "sans-serif", Typeface.NORMAL));
        view.setIncludeFontPadding(false); return view;
    }
    private TextView action(String value, String description, Runnable callback) {
        TextView view = text(value, 13, style.text, false); view.setGravity(Gravity.CENTER);
        view.setContentDescription(description); interactive(view);
        view.setBackground(style.interactive(activity, Color.TRANSPARENT, Color.TRANSPARENT, 7));
        view.setOnClickListener(ignored -> callback.run()); return view;
    }

    private void interactive(View view) {
        view.setClickable(true); view.setFocusable(true); view.setFocusableInTouchMode(false);
        view.setDefaultFocusHighlightEnabled(false);
    }
    private ImageView icon(int resource, int color, int size) {
        ImageView view = new ImageView(activity); view.setImageDrawable(drawable(resource, color, size));
        view.setScaleType(ImageView.ScaleType.FIT_CENTER); view.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        return view;
    }
    private ImageView iconAction(int resource, String description, Runnable callback) {
        ImageView view = icon(resource, style.muted, 20); view.setPadding(dp(14), dp(14), dp(14), dp(14));
        view.setContentDescription(description); view.setTooltipText(description);
        view.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES); interactive(view);
        view.setBackground(style.interactive(activity, Color.TRANSPARENT, Color.TRANSPARENT, 7));
        view.setOnClickListener(ignored -> callback.run()); return view;
    }
    private Drawable drawable(int resource, int color, int size) {
        Drawable result = activity.getDrawable(resource).mutate(); result.setTint(color);
        result.setBounds(0, 0, dp(size), dp(size)); return result;
    }
    private void attachIcon(TextView view, int resource, int color, int size) {
        view.setCompoundDrawables(drawable(resource, color, size), null, null, null);
        view.setCompoundDrawablePadding(dp(8));
    }
    private void add(LinearLayout parent, View child, int top) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2); params.topMargin = dp(top); parent.addView(child, params);
    }
    private int dp(int value) { return Math.round(value * activity.getResources().getDisplayMetrics().density); }
}
