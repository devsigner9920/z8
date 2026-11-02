package com.termux.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputFilter;
import android.text.InputType;
import android.view.Gravity;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.File;
import java.io.IOException;
import java.text.DateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

/** Private GitHub reads and confirmed clones; authentication runs in the project PTY. */
public final class Z8GitHubActivity extends Activity {
    public static final String EXTRA_AUTH_SESSION = "dev.devsigner.z8.GITHUB_AUTH_SESSION";
    private static final String PROJECT_ID = "dev.devsigner.z8.GITHUB_PROJECT_ID";
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private Z8Theme.Palette palette;
    private String projectId;
    private Z8Projects.Project project;
    private Z8GitHub client;
    private boolean busy;
    private boolean stale;
    private String runtimeError = "";
    private String error = "";
    private String auth = Z8Text.text("Checking authentication…", "인증 상태 확인 중…");
    private boolean authChecking;
    private TextView authLabel;
    private String originRepository = "";
    private ScrollView pageScroll;
    private boolean scrollTop, toolsExpanded;
    private String draftRepository = "";
    private String draftSearch = "";
    private EditText repositoryInput, searchInput;
    private Z8GitHub.View selectedView = Z8GitHub.View.REPOSITORY;
    private String selectedRepository = "", selectedArgument = "";
    private int selectedPage = 1;
    private Z8GitHub.Page result;
    private long receivedAt;
    private final Handler cloneHandler = new Handler(Looper.getMainLooper());
    private Z8GitHub.CloneState shownClone;
    private Z8GitHub.DraftState shownDraft;
    private Z8GitHub.ReviewState shownReview;
    private AlertDialog reviewDialog;
    private EditText reviewBodyInput;
    private String reviewBody = "", reviewKey = "";
    private android.widget.Spinner reviewType;
    private Z8GitHub.DraftContext draftContext;
    private String prHead = "", prBase = "", prTitle = "", prBody = "";
    private boolean draftFormRequested;
    private EditText prHeadInput, prBaseInput, prTitleInput, prBodyInput;
    private AlertDialog prDialog;
    private boolean visible;
    private final Runnable cloneObserver = new Runnable() {
        @Override public void run() {
            if (!visible || isFinishing() || isDestroyed()) return;
            Z8GitHub.CloneState latest = Z8GitHub.cloneState(projectId);
            Z8GitHub.DraftState draft = Z8GitHub.draftState(projectId);
            Z8GitHub.ReviewState review = Z8GitHub.reviewState(projectId);
            if (latest != shownClone || draft != shownDraft || review != shownReview) { shownClone = latest; shownDraft = draft; shownReview = review; render(); }
            if ((latest != null && latest.phase == Z8GitHub.ClonePhase.RUNNING) || (draft != null && draft.running()) || (review != null && review.running)) cloneHandler.postDelayed(this, 750);
        }
    };

    public static Intent intent(Context context, String projectId) {
        return new Intent(context, Z8GitHubActivity.class).putExtra(PROJECT_ID, projectId);
    }

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        projectId = getIntent().getStringExtra(PROJECT_ID);
        SharedPreferences saved = drafts();
        draftRepository = saved.getString("repository", ""); draftSearch = saved.getString("search", "");
        prHead = saved.getString("prHead", ""); prBase = saved.getString("prBase", "");
        prTitle = saved.getString("prTitle", ""); prBody = saved.getString("prBody", "");
        String savedRepo = saved.getString("prRepository", "");
        if (!savedRepo.isEmpty()) draftContext = new Z8GitHub.DraftContext(savedRepo, "", prBase);
        if (state != null) {
            draftRepository = state.getString("repository", ""); draftSearch = state.getString("search", "");
            selectedRepository = state.getString("selectedRepository", ""); selectedArgument = state.getString("selectedArgument", "");
            selectedPage = Math.max(1, Math.min(100, state.getInt("page", 1)));
            try { selectedView = Z8GitHub.View.valueOf(state.getString("view", "REPOSITORY")); }
            catch (IllegalArgumentException ignored) { selectedView = Z8GitHub.View.REPOSITORY; }
            prHead = state.getString("prHead", ""); prBase = state.getString("prBase", "");
            prTitle = state.getString("prTitle", ""); prBody = state.getString("prBody", "");
            draftFormRequested = state.getBoolean("draftForm", false);
            if (state.containsKey("prRepository")) draftContext = new Z8GitHub.DraftContext(state.getString("prRepository", ""), state.getString("prAccount", ""), prBase);
        }
        render(); prepare();
    }

    @Override protected void onResume() {
        super.onResume();
        visible = true; cloneHandler.removeCallbacks(cloneObserver); cloneHandler.post(cloneObserver);
        if (result != null) stale = true;
        if (project != null && !busy) prepare();
    }

    @Override protected void onPause() {
        visible = false; saveDrafts(); cloneHandler.removeCallbacks(cloneObserver); super.onPause();
    }

    @Override protected void onSaveInstanceState(Bundle out) {
        inputs(); out.putString("repository", draftRepository); out.putString("search", draftSearch);
        out.putString("selectedRepository", selectedRepository); out.putString("selectedArgument", selectedArgument);
        out.putString("view", selectedView.name()); out.putInt("page", selectedPage);
        draftInputs(); out.putString("prHead", prHead); out.putString("prBase", prBase);
        out.putString("prTitle", prTitle); out.putString("prBody", prBody); out.putBoolean("draftForm", draftFormRequested);
        if (draftContext != null) { out.putString("prRepository", draftContext.repository); out.putString("prAccount", draftContext.account); }
        // Preserve only user-authored unsent PR fields; never remote bodies, auth output or tokens.
        super.onSaveInstanceState(out);
    }

    @Override protected void onDestroy() {
        cloneHandler.removeCallbacks(cloneObserver);
        if (prDialog != null) prDialog.dismiss();
        if (reviewDialog != null) reviewDialog.dismiss();
        // Finish any accepted local branch operation; remote writes belong to the shared worker.
        io.shutdown(); super.onDestroy();
    }

    private static final class Prepared {
        final Z8Projects.Project project; final Z8GitHub client; final String error, origin;
        Prepared(Z8Projects.Project project, Z8GitHub client, String error, String origin) {
            this.project = project; this.client = client; this.error = error; this.origin = origin;
        }
    }

    private void prepare() {
        job(() -> {
            Z8Projects.Project checked = new Z8Projects(this).open(projectId);
            try {
                File rootfs = new File(getFilesDir(), "z8/environments/" + checked.id + "/rootfs");
                File gh = new File(rootfs, "usr/bin/gh").getCanonicalFile();
                if (!gh.toPath().startsWith(rootfs.getCanonicalFile().toPath()))
                    throw new IOException(Z8Text.text("The project's gh path points outside the Linux environment.", "프로젝트 gh 경로가 Linux 환경 밖을 가리킵니다."));
                Z8Guest.Launch launch = Z8Guest.commandFor(this, checked.id, "", new String[] { "/usr/bin/gh" });
                Z8GitHub client = new Z8GitHub(new File(launch.executable), checked.source, gh,
                    new File(getFilesDir(), "z8/environments/" + checked.id + "/tmp"),
                    Arrays.asList(launch.arguments), launch.commandOffset, new Z8Git.ProcessRunner(), Z8GitHubActivity::decode);
                return new Prepared(checked, client, client.available() ? "" : Z8Text.text("The project's Linux environment needs GitHub CLI (gh). Run the Linux environment's developer tools setup.", "프로젝트 Linux 환경에 GitHub CLI(gh)가 필요합니다. Linux 환경의 개발 도구 설치를 실행해 주세요."), client.projectRepository());
            } catch (IOException invalid) { return new Prepared(checked, null, message(invalid), ""); }
        }, ready -> {
            project = ready.project; client = ready.client; runtimeError = ready.error; originRepository = ready.origin;
            if (draftRepository.isEmpty() && !originRepository.isEmpty()) { draftRepository = originRepository; repositoryInput = null; }
            if (draftRepository.isEmpty()) toolsExpanded = true;
            if (client != null && client.available()) checkAuth();
            if (draftFormRequested && draftContext != null && client != null && client.available() && !operationRunning()) showDraftForm();
        });
    }

    private void render() {
        int scrollY = pageScroll == null || scrollTop ? 0 : pageScroll.getScrollY(); scrollTop = false;
        inputs(); repositoryInput = null; searchInput = null; reconcileDraft(); palette = Z8Theme.selected(this); Z8Theme.applyChrome(this, palette); setTitle("z8 · GitHub");
        LinearLayout frame = column(); frame.setGravity(Gravity.CENTER_HORIZONTAL); frame.setBackgroundColor(palette.background);
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); pageScroll = scroll;
        scroll.post(() -> scroll.scrollTo(0, scrollY));
        int width = getResources().getConfiguration().screenWidthDp > 900 ? dp(900) : -1;
        frame.addView(scroll, new LinearLayout.LayoutParams(width, -1));
        LinearLayout content = column(); content.setPadding(dp(20), dp(18), dp(20), dp(24)); scroll.addView(content);
        TextView title = text(project == null ? "GitHub" : project.name + " / GitHub", 25, palette.foreground);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD); content.addView(title);
        add(content, text(Z8Text.text("LOCAL · Project Linux CLI  →  github.com", "LOCAL · 프로젝트 Linux CLI  →  github.com"), 12, palette.accent), 6);
        Button back = Z8Ui.quiet(this, palette, Z8Text.text("‹ Back to project", "‹ 프로젝트로"), this::finish); back.setEnabled(true); back.setOnClickListener(ignored -> finish()); add(content, back, 14);
        if (project == null) {
            add(content, text(busy ? Z8Text.text("Checking the project environment…", "프로젝트 환경을 확인하고 있습니다…") : error, 16, palette.secondary), 24);
            setContentView(frame); return;
        }
        shownClone = Z8GitHub.cloneState(projectId);
        shownDraft = Z8GitHub.draftState(projectId);
        shownReview = Z8GitHub.reviewState(projectId);
        if (shownClone != null) {
            add(content, text(shownClone.repository + " → " + project.name, 16, palette.foreground), 18);
            add(content, text(shownClone.message, 14, shownClone.phase == Z8GitHub.ClonePhase.FAILED ? palette.accent : palette.secondary), 6);
            if (shownClone.phase != Z8GitHub.ClonePhase.RUNNING)
                add(content, button(Z8Text.text("Open project Git", "프로젝트 Git 확인"), () -> startActivity(Z8GitActivity.intent(this, project.id))), 8);
        }
        if (shownDraft != null) {
            add(content, text("Draft PR · " + shownDraft.repository + "\n" + shownDraft.head + " → " + shownDraft.base, 16, palette.foreground), 18);
            add(content, text(shownDraft.message, 14, shownDraft.phase == Z8GitHub.DraftPhase.UNKNOWN || shownDraft.phase == Z8GitHub.DraftPhase.FAILED ? palette.accent : palette.secondary), 6);
            if (!shownDraft.url.isEmpty()) {
                TextView link = text(shownDraft.url, 13, palette.secondary); link.setTextIsSelectable(true); add(content, link, 6);
            }
            if (!shownDraft.running()) {
                Z8GitHub.DraftState completed = shownDraft;
                add(content, button(completed.number > 0 ? "PR #" + completed.number + Z8Text.text(" details", " 상세 보기") : Z8Text.text("Check the result in open PRs", "열린 PR에서 결과 확인"),
                    () -> load(completed.number > 0 ? Z8GitHub.View.PULL : Z8GitHub.View.PULLS, completed.repository,
                        completed.number > 0 ? Long.toString(completed.number) : "", 1, false)), 8);
            }
        }
        if (shownReview != null) {
            add(content, text(Z8Text.text("Review · ", "리뷰 · ") + shownReview.repository + " #" + shownReview.number, 16, palette.foreground), 18);
            add(content, text(shownReview.message, 14, palette.secondary), 6);
            if (!shownReview.running) {
                Z8GitHub.ReviewState done = shownReview;
                add(content, button(Z8Text.text("View submitted reviews", "제출된 리뷰 확인"), () -> load(Z8GitHub.View.REVIEWS, done.repository, Long.toString(done.number), 1, false)), 8);
            }
        }
        if (!runtimeError.isEmpty() || client == null || !client.available()) {
            add(content, text(Z8Text.text("Set up project GitHub tools", "프로젝트 GitHub 도구 준비"), 22, palette.foreground), 24);
            add(content, text(runtimeError.isEmpty() ? Z8Text.text("Check the project environment.", "프로젝트 환경을 확인해 주세요.") : runtimeError, 15, palette.secondary), 12);
            if (client != null && client.cloneAvailable()) {
                add(content, text(Z8Text.text("Git is ready. Public repositories can be cloned without installing GitHub CLI or signing in.", "Git은 준비되어 있습니다. 공개 저장소는 GitHub CLI 설치나 로그인 없이 clone할 수 있습니다."), 15, palette.secondary), 12);
                repositoryInput = input("owner/repository", draftRepository, 140); add(content, repositoryInput, 12);
                Button clone = button(Z8Text.text("Clone entered public repository", "입력한 공개 저장소 clone"), () -> { inputs(); confirmClone(draftRepository.trim()); });
                clone.setEnabled(!busy && !operationRunning()); add(content, clone, 8);
                if (!error.isEmpty()) add(content, text(error, 14, palette.accent), 8);
            }
            add(content, button(Z8Text.text("Open Linux environment", "Linux 환경 열기"), () -> startActivity(Z8EnvironmentActivity.intent(this, project.id))), 16);
            add(content, button(Z8Text.text("Check installation again", "설치 상태 다시 확인"), this::prepare), 8);
            setContentView(frame); return;
        }
        authLabel = text(auth, 13, palette.secondary); add(content, authLabel, 12);
        if (!draftRepository.isEmpty()) {
            TextView selected = text(draftRepository, 21, palette.foreground); selected.setTypeface(Typeface.DEFAULT, Typeface.BOLD); add(content, selected, 18);
            if (!originRepository.isEmpty() && !originRepository.equalsIgnoreCase(draftRepository))
                add(content, text(Z8Text.text("Project origin · ", "프로젝트 origin · ") + originRepository, 12, palette.secondary), 5);
            LinearLayout repositoryTools = row();
            equal(repositoryTools, button(Z8Text.text("Repository details", "저장소 정보"), () -> selected(Z8GitHub.View.REPOSITORY)));
            equal(repositoryTools, button(Z8Text.text("Issues", "이슈"), () -> selected(Z8GitHub.View.ISSUES)));
            equal(repositoryTools, button("PR", () -> selected(Z8GitHub.View.PULLS))); add(content, repositoryTools, 10);
            LinearLayout workTools = row();
            equal(workTools, button("Actions", () -> selected(Z8GitHub.View.ACTIONS)));
            Button newPr = Z8Ui.primary(this, palette, Z8Text.text("Draft a PR", "Draft PR 작성"), () -> { if (!busy) openDraftForm(); });
            newPr.setEnabled(!busy && !operationRunning()); equal(workTools, newPr); add(content, workTools, 8);
        }
        add(content, Z8Ui.quiet(this, palette, toolsExpanded ? Z8Text.text("Hide account and repository settings", "계정·저장소 설정 접기") : Z8Text.text("Switch account or repository", "계정·저장소 전환"), () -> { toolsExpanded = !toolsExpanded; render(); }), 8);
        if (toolsExpanded) {
            LinearLayout authTools = row();
            equal(authTools, button(Z8Text.text("Check authentication again", "인증 다시 확인"), this::checkAuth));
            equal(authTools, button(Z8Text.text("Sign in to GitHub", "GitHub 로그인"), this::login)); add(content, authTools, 8);
            add(content, text(Z8Text.text("Repository to view", "조회할 저장소"), 13, palette.secondary), 18);
            repositoryInput = input("owner/repository", draftRepository, 140); content.addView(repositoryInput);
            LinearLayout repositoryTools = row();
            equal(repositoryTools, button(Z8Text.text("Open repository", "저장소 열기"), () -> { inputs(); toolsExpanded = false; selected(Z8GitHub.View.REPOSITORY); }));
            Button clone = button(Z8Text.text("Clone into empty project", "빈 프로젝트에 clone"), () -> { inputs(); confirmClone(draftRepository.trim()); });
            clone.setEnabled(!busy && !operationRunning()); equal(repositoryTools, clone); add(content, repositoryTools, 8);
            add(content, text(Z8Text.text("Repository search", "저장소 검색"), 13, palette.secondary), 18);
            searchInput = input(Z8Text.text("Search term · Example: android terminal", "검색어 · 예: android terminal"), draftSearch, 200); content.addView(searchInput);
            add(content, button(Z8Text.text("Search GitHub", "GitHub에서 검색"), () -> { inputs(); load(Z8GitHub.View.SEARCH, "", draftSearch, 1, false); }), 8);
        }
        add(content, text(busy ? Z8Text.text("Checking GitHub…", "GitHub에서 확인하고 있습니다…") : error, 14, error.isEmpty() ? palette.secondary : palette.accent), 16);
        if (result == null) {
            add(content, text(originRepository.isEmpty() ? Z8Text.text("Enter or search for a GitHub repository. Clone into an empty project.", "GitHub 저장소를 입력하거나 검색해 주세요. clone은 빈 프로젝트에서 시작할 수 있습니다.") : Z8Text.text("Loaded the project's origin repository. Select Issues, PRs, or Actions.", "프로젝트의 origin 저장소를 불러왔습니다. 이슈·PR·Actions를 선택해 주세요."), 15, palette.secondary), 16);
            if (!selectedRepository.isEmpty() || !selectedArgument.isEmpty()) add(content, button(Z8Text.text("Reopen last query", "마지막 조회 다시 열기"), this::reload), 10);
        } else {
            add(content, text(result.summary + (selectedRepository.isEmpty() ? "" : " · " + selectedRepository), 19, palette.foreground), 20);
            add(content, text((stale || busy ? Z8Text.text("Previous results · ", "이전 결과 · ") : Z8Text.text("Query complete · ", "조회 완료 · ")) + DateFormat.getTimeInstance(DateFormat.SHORT).format(new Date(receivedAt))
                + " · " + Z8Text.text("Page " + selectedPage, selectedPage + "페이지"), 12, palette.secondary), 5);
            add(content, button(Z8Text.text("Refresh results", "결과 새로고침"), this::reload), 8);
            if (selectedView == Z8GitHub.View.PULL_FILES || selectedView == Z8GitHub.View.REVIEWS) {
                String repo = selectedRepository, number = selectedArgument;
                add(content, button("‹ PR #" + number + Z8Text.text(" details", " 상세로"), () -> load(Z8GitHub.View.PULL, repo, number, 1, false)), 8);
            }
            if (result.rows.isEmpty()) add(content, text(Z8Text.text("No items to show on this page.", "이 페이지에 표시할 항목이 없습니다."), 16, palette.secondary), 16);
            for (Z8GitHub.Row entry : result.rows) resultRow(content, entry);
            if (selectedPage > 1 || result.mayHaveNext) {
                LinearLayout pages = row();
                Button previous = button(Z8Text.text("‹ Previous page", "‹ 이전 페이지"), () -> load(selectedView, selectedRepository, selectedArgument, selectedPage - 1, false));
                previous.setEnabled(!busy && selectedPage > 1); equal(pages, previous);
                Button next = button(Z8Text.text("Next page ›", "다음 페이지 ›"), () -> load(selectedView, selectedRepository, selectedArgument, selectedPage + 1, false));
                next.setEnabled(!busy && result.mayHaveNext); equal(pages, next); add(content, pages, 16);
            }
            add(content, text(Z8Text.text("Up to 30 items per page. Check runs, commit statuses, and Actions are separate queries.", "페이지당 최대 30개. 체크 실행·커밋 상태·Actions는 서로 다른 조회 결과입니다."), 12, palette.secondary), 16);
        }
        setContentView(frame);
    }

    private void resultRow(LinearLayout content, Z8GitHub.Row entry) {
        LinearLayout item = column(); item.setPadding(dp(12), dp(14), dp(12), dp(14));
        GradientDrawable shape = new GradientDrawable(); shape.setColor(palette.background); shape.setStroke(dp(1), palette.secondary); shape.setCornerRadius(dp(10)); item.setBackground(shape);
        TextView name = text((entry.number > 0 ? "#" + entry.number + "  " : "") + entry.title, 17, palette.foreground);
        name.setTypeface(Typeface.DEFAULT, Typeface.BOLD); item.addView(name);
        add(item, text(entry.detail, 13, palette.accent), 5);
        boolean detail = selectedView == Z8GitHub.View.ISSUE || selectedView == Z8GitHub.View.PULL || selectedView == Z8GitHub.View.REPOSITORY || selectedView == Z8GitHub.View.PULL_FILES || selectedView == Z8GitHub.View.REVIEWS;
        if (!entry.body.isEmpty()) {
            TextView body = text(detail ? entry.body : entry.body.substring(0, Math.min(300, entry.body.length())), 14, palette.secondary);
            body.setTextIsSelectable(true);
            if (entry.kind == Z8GitHub.Kind.FILE) body.setTypeface(Typeface.MONOSPACE);
            add(item, body, 10);
        }
        if (entry.kind == Z8GitHub.Kind.REPOSITORY && selectedView != Z8GitHub.View.REPOSITORY) {
            add(item, button(Z8Text.text("Open this repository", "이 저장소 열기"), () -> {
                draftRepository = entry.repository; if (repositoryInput != null) repositoryInput.setText(entry.repository);
                load(Z8GitHub.View.REPOSITORY, entry.repository, "", 1, false);
            }), 10);
        } else if ((entry.kind == Z8GitHub.Kind.ISSUE || entry.kind == Z8GitHub.Kind.PULL) && !detail) {
            add(item, button(Z8Text.text("View details", "상세 보기"), () -> load(entry.kind == Z8GitHub.Kind.PULL ? Z8GitHub.View.PULL : Z8GitHub.View.ISSUE,
                entry.repository, Long.toString(entry.number), 1, false)), 10);
        }
        if (entry.kind == Z8GitHub.Kind.REPOSITORY) {
            Button clone = button(Z8Text.text("Clone into this project", "이 프로젝트에 clone"), () -> confirmClone(entry.repository));
            boolean running = operationRunning();
            clone.setEnabled(!busy && !running); clone.setAlpha(busy || running ? .45f : 1f); add(item, clone, 8);
        }
        if (selectedView == Z8GitHub.View.ISSUE) add(item, button(Z8Text.text("Start work on this issue", "이 이슈로 작업 시작"), () -> startIssue(entry)), 10);
        if (selectedView == Z8GitHub.View.PULL && !entry.sha.isEmpty()) {
            LinearLayout pullTools = row();
            equal(pullTools, button(Z8Text.text("Changed files · Diff", "변경 파일 · diff"), () -> load(Z8GitHub.View.PULL_FILES, entry.repository, Long.toString(entry.number), 1, false)));
            equal(pullTools, button(Z8Text.text("Review history", "리뷰 내역"), () -> load(Z8GitHub.View.REVIEWS, entry.repository, Long.toString(entry.number), 1, false)));
            add(item, pullTools, 10);
            add(item, button(Z8Text.text("Review this HEAD", "이 HEAD에 리뷰 작성"), () -> openReview(entry)), 8);
            add(item, text("HEAD " + entry.sha.substring(0, 12), 12, palette.secondary), 12);
            LinearLayout checks = row();
            equal(checks, button(Z8Text.text("Check runs", "체크 실행"), () -> load(Z8GitHub.View.CHECKS, entry.repository, entry.sha, 1, false)));
            equal(checks, button(Z8Text.text("Commit statuses", "커밋 상태"), () -> load(Z8GitHub.View.STATUSES, entry.repository, entry.sha, 1, false))); add(item, checks, 8);
        }
        add(content, item, 10);
    }

    private void selected(Z8GitHub.View view) { inputs(); load(view, draftRepository.trim(), "", 1, false); }
    private void reload() { load(selectedView, selectedRepository, selectedArgument, selectedPage, true); }
    private void load(Z8GitHub.View view, String repository, String argument, int page, boolean keep) {
        if (busy || client == null) return;
        try { Z8GitHub.endpoint(view, repository, argument, page); }
        catch (IOException invalid) { error = message(invalid); render(); return; }
        selectedView = view; selectedRepository = repository; selectedArgument = argument; selectedPage = page;
        if (!keep) { result = null; scrollTop = true; } stale = result != null;
        job(() -> client.load(view, repository, argument, page), loaded -> { result = loaded; receivedAt = System.currentTimeMillis(); stale = false; });
    }

    private void login() {
        saveDrafts(); auth = Z8Text.text("Sign in from this project's terminal. Authentication is checked automatically when you reopen GitHub.", "이 프로젝트 터미널에서 로그인합니다. GitHub를 다시 열면 인증을 자동 확인합니다.");
        startActivity(new Intent(this, TermuxActivity.class)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .putExtra(EXTRA_AUTH_SESSION, project.id)
            .putExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID, project.id)
            .putExtra(Z8Guest.EXTRA_GUEST_SESSION, true));
    }

    private void confirmClone(String repository) {
        if (busy || client == null) return;
        job(() -> { client.checkCloneReady(repository); return true; }, ready -> {
            Z8Ui.dialog(this).setTitle(Z8Text.text("Clone into this project", "이 프로젝트에 clone"))
                .setMessage(Z8Text.text("GitHub repository: ", "GitHub 저장소: ") + repository + Z8Text.text("\nTarget project: ", "\n대상 프로젝트: ") + project.name
                    + Z8Text.text("\nSource location: /workspace\n\nClone over HTTPS. Public repositories do not require sign-in; when authentication is needed, this project's settings are used. The clone will not start if any files, including hidden files, already exist. Wait until cloning finishes before editing project files. If cloning stops, you can inspect any remaining files.", "\n소스 위치: /workspace\n\nHTTPS clone을 실행합니다. 공개 저장소는 로그인 없이 이용할 수 있고, 인증이 필요하면 이 프로젝트의 설정을 사용합니다. 숨김 파일을 포함해 기존 파일이 있으면 시작하지 않습니다. 복제 중에는 이 프로젝트의 파일 수정을 기다려 주세요. 중단되면 남은 파일을 직접 확인할 수 있습니다."))
                .setNegativeButton(Z8Text.text("Cancel", "취소"), null)
                .setPositiveButton(Z8Text.text("Start clone", "clone 시작"), (dialog, which) -> {
                    // Publish the lease now; an Activity read queue can be cancelled on rotation.
                    // The accepted operation's network/process work runs on the shared worker.
                    try { client.startClone(project.id, repository); error = ""; }
                    catch (IOException failure) { error = message(failure); }
                    observeOperation();
                }).show();
        });
    }

    private void observeOperation() {
        cloneHandler.removeCallbacks(cloneObserver); if (visible) cloneHandler.post(cloneObserver);
        render();
    }

    private boolean operationRunning() {
        Z8GitHub.CloneState clone = Z8GitHub.cloneState(projectId); Z8GitHub.DraftState draft = Z8GitHub.draftState(projectId);
        Z8GitHub.ReviewState review = Z8GitHub.reviewState(projectId);
        return (clone != null && clone.phase == Z8GitHub.ClonePhase.RUNNING) || (draft != null && draft.running()) || (review != null && review.running);
    }

    private void openDraftForm() {
        inputs(); String selected = draftRepository.trim();
        job(() -> client.draftContext(selected), context -> {
            if (draftContext == null || !draftContext.repository.equalsIgnoreCase(context.repository)) {
                prHead = ""; prBase = ""; prTitle = ""; prBody = "";
            }
            draftContext = context; if (prBase.isEmpty()) prBase = context.defaultBranch;
            draftFormRequested = true; showDraftForm();
        });
    }

    private void draftInputs() {
        if (prHeadInput != null) prHead = prHeadInput.getText().toString();
        if (prBaseInput != null) prBase = prBaseInput.getText().toString();
        if (prTitleInput != null) prTitle = prTitleInput.getText().toString();
        if (prBodyInput != null) prBody = prBodyInput.getText().toString();
    }

    private void showDraftForm() {
        if (draftContext == null || operationRunning() || (prDialog != null && prDialog.isShowing())) return;
        LinearLayout fields = column(); fields.setPadding(dp(20), dp(12), dp(20), dp(16)); fields.setBackgroundColor(palette.background);
        fields.addView(text(draftContext.repository + Z8Text.text("\nGitHub account: ", "\nGitHub 계정: ") + draftContext.account, 15, palette.foreground));
        add(fields, text(Z8Text.text("Create a draft PR from a head branch you have already pushed to the remote.", "원격에 이미 push한 head 브랜치로 Draft PR을 만듭니다."), 13, palette.secondary), 10);
        prHeadInput = input(Z8Text.text("head · feature/name or owner:branch", "head · feature/name 또는 owner:branch"), prHead, 300); add(fields, prHeadInput, 12);
        prBaseInput = input(Z8Text.text("Base branch", "base 브랜치"), prBase, 255); add(fields, prBaseInput, 6);
        prTitleInput = input(Z8Text.text("PR title", "PR 제목"), prTitle, 256); add(fields, prTitleInput, 6);
        prBodyInput = input(Z8Text.text("PR body · Up to 16 KiB", "PR 본문 · 최대 16 KiB"), prBody, 16384); prBodyInput.setSingleLine(false);
        prBodyInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        prBodyInput.setMinLines(4); prBodyInput.setMaxLines(8); add(fields, prBodyInput, 6);
        ScrollView scroll = new ScrollView(this); scroll.addView(fields);
        prDialog = Z8Ui.dialog(this).setTitle(Z8Text.text("Draft a PR", "Draft PR 작성")).setView(scroll)
            .setNegativeButton(Z8Text.text("Close", "닫기"), (dialog, which) -> { draftInputs(); draftFormRequested = false; })
            .setPositiveButton(Z8Text.text("Review details", "내용 검토"), null).create();
        prDialog.setOnCancelListener(dialog -> { draftInputs(); draftFormRequested = false; });
        prDialog.setOnShowListener(ignored -> prDialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
            draftInputs();
            try {
                Z8GitHub.DraftRequest request = new Z8GitHub.DraftRequest(draftContext.repository, draftContext.account,
                    prHead.trim(), prBase.trim(), prTitle, prBody);
                prDialog.dismiss(); prDialog = null; previewDraft(request);
            } catch (IOException invalid) { prBodyInput.setError(message(invalid)); }
        }));
        prDialog.show(); Z8Ui.finish(prDialog);
    }

    private void previewDraft(Z8GitHub.DraftRequest request) {
        TextView review = text(Z8Text.text("Repository: ", "저장소: ") + request.repository + Z8Text.text("\nAccount: ", "\n계정: ") + request.account + Z8Text.text("\nBranch: ", "\n브랜치: ") + request.head + " → " + request.base
            + Z8Text.text("\nStatus: Draft\n\nTitle\n", "\n상태: Draft\n\n제목\n") + request.title + Z8Text.text("\n\nBody\n", "\n\n본문\n") + (request.body.isEmpty() ? Z8Text.text("(empty)", "(비어 있음)") : request.body), 15, palette.foreground);
        review.setTextIsSelectable(true); review.setPadding(dp(20), dp(12), dp(20), dp(20)); review.setBackgroundColor(palette.background);
        ScrollView scroll = new ScrollView(this); scroll.addView(review);
        prDialog = Z8Ui.dialog(this).setTitle(Z8Text.text("Create draft PR on GitHub", "GitHub에 Draft PR 생성")).setView(scroll)
            .setNegativeButton(Z8Text.text("Edit", "수정"), (dialog, which) -> { prDialog = null; showDraftForm(); })
            .setNeutralButton(Z8Text.text("Cancel", "취소"), (dialog, which) -> draftFormRequested = false)
            .setPositiveButton(Z8Text.text("Create reviewed draft PR", "검토한 Draft PR 생성"), (dialog, which) -> {
                draftFormRequested = false;
                try {
                    // Acceptance is synchronous; all remote work belongs to the shared worker.
                    client.startDraft(project.id, request);
                    // Preserve the authored fields until a verified CREATED/EXISTS receipt arrives.
                    saveDrafts(); error = "";
                } catch (IOException failure) { error = message(failure); }
                observeOperation();
            }).create();
        prDialog.setOnCancelListener(dialog -> draftFormRequested = false); prDialog.show(); Z8Ui.finish(prDialog);
    }

    private SharedPreferences drafts() { return getSharedPreferences("z8-github-drafts-" + projectId, MODE_PRIVATE); }
    private void saveDrafts() {
        inputs(); draftInputs();
        SharedPreferences.Editor saved = drafts().edit().putString("repository", draftRepository).putString("search", draftSearch)
            .putString("prHead", prHead).putString("prBase", prBase).putString("prTitle", prTitle).putString("prBody", prBody);
        if (draftContext != null) saved.putString("prRepository", draftContext.repository);
        if (reviewBodyInput != null && !reviewKey.isEmpty()) { reviewBody = reviewBodyInput.getText().toString(); saved.putString(reviewKey, reviewBody);
            if (reviewType != null) saved.putString(reviewKey + ".event", new String[] { "COMMENT", "APPROVE", "REQUEST_CHANGES" }[reviewType.getSelectedItemPosition()]); }
        saved.apply();
    }
    private void reconcileDraft() {
        Z8GitHub.DraftState completed = Z8GitHub.draftState(projectId);
        if (completed == null || (completed.phase != Z8GitHub.DraftPhase.CREATED && completed.phase != Z8GitHub.DraftPhase.EXISTS)) return;
        String receipt = completed.repository + ":" + completed.number;
        if (receipt.equals(drafts().getString("lastDraftReceipt", ""))) return;
        if (draftContext != null && draftContext.repository.equalsIgnoreCase(completed.repository)
                && prHead.equals(completed.head) && prBase.equals(completed.base)) {
            prHeadInput = null; prBaseInput = null; prTitleInput = null; prBodyInput = null;
            prHead = ""; prBase = ""; prTitle = ""; prBody = "";
            saveDrafts();
        }
        drafts().edit().putString("lastDraftReceipt", receipt).apply();
    }
    private void checkAuth() {
        if (authChecking || client == null || !client.available() || isFinishing() || isDestroyed()) return;
        authChecking = true; auth = Z8Text.text("Checking github.com account…", "github.com 계정 확인 중…");
        if (authLabel != null) authLabel.setText(auth);
        Z8GitHub selected = client;
        io.execute(() -> {
            String message;
            try { message = selected.authStatus().message; } catch (IOException invalid) { message = message(invalid); }
            String status = message;
            runOnUiThread(() -> { if (isFinishing() || isDestroyed()) return; authChecking = false; auth = status; if (authLabel != null) authLabel.setText(auth); });
        });
    }

    private Z8Git projectGit() throws IOException {
        File rootfs = new File(getFilesDir(), "z8/environments/" + project.id + "/rootfs");
        File executable = new File(rootfs, "usr/bin/git").getCanonicalFile();
        if (!executable.toPath().startsWith(rootfs.getCanonicalFile().toPath())) throw new IOException(Z8Text.text("Check the project's Git path.", "프로젝트 Git 경로를 확인해 주세요."));
        File temp = new File(getFilesDir(), "z8/environments/" + project.id + "/tmp");
        Z8Guest.Launch launch = Z8Guest.commandFor(this, project.id, "", new String[] { "/usr/bin/git" });
        Z8GuestGit runner = new Z8GuestGit(new File(launch.executable), project.source, executable,
            Arrays.asList(launch.arguments), launch.commandOffset, new Z8Git.ProcessRunner());
        return Z8Git.guest(executable, project.source, new File(getFilesDir(), "z8/homes/" + project.id), temp, Z8GitHub.environment(temp), runner);
    }
    private void startIssue(Z8GitHub.Row issue) {
        job(() -> {
            if (!issue.repository.equalsIgnoreCase(client.projectRepository())) throw new IOException(Z8Text.text("This issue's repository does not match the project's origin. Start work in a project cloned from that repository.", "이 이슈의 저장소와 프로젝트 origin이 다릅니다. 해당 저장소를 clone한 프로젝트에서 작업을 시작해 주세요."));
            Z8Git git = projectGit(); return new Object[] { git, git.status() };
        }, ready -> {
            Z8Git git = (Z8Git) ready[0]; Z8Git.Status expected = (Z8Git.Status) ready[1];
            LinearLayout fields = column(); fields.setPadding(dp(20), dp(12), dp(20), dp(16));
            fields.addView(text(issue.repository + " #" + issue.number + "\n" + issue.title + Z8Text.text("\nBase branch · ", "\n기준 브랜치 · ") + expected.branch, 15, palette.foreground));
            EditText branch = input(Z8Text.text("Working branch", "작업 브랜치"), "issue/" + issue.number, 200); add(fields, branch, 12);
            add(fields, text(Z8Text.text("Create and switch to a local branch from the current HEAD. The issue content is not executed as a command.", "현재 HEAD에서 로컬 브랜치를 만들고 전환합니다. 이슈 내용은 명령으로 실행하지 않습니다."), 13, palette.secondary), 12);
            AlertDialog dialog = Z8Ui.dialog(this).setTitle(Z8Text.text("Start issue work", "이슈 작업 시작")).setView(fields).setNegativeButton(Z8Text.text("Cancel", "취소"), null).setPositiveButton(Z8Text.text("Create and open branch", "브랜치 만들고 열기"), null).create();
            dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
                String name = branch.getText().toString();
                if (name.trim().isEmpty()) { branch.setError(Z8Text.text("Enter a branch name.", "브랜치 이름을 입력해 주세요.")); return; }
                dialog.dismiss(); job(() -> {
                    if (!issue.repository.equalsIgnoreCase(client.projectRepository())) throw new IOException(Z8Text.text("The origin has changed. Check the repository again.", "origin이 변경되었습니다. 저장소를 다시 확인해 주세요."));
                    git.switchBranch(expected, name, true); return true;
                }, done -> startActivity(Z8GitActivity.intent(this, project.id)));
            }));
            dialog.show(); Z8Ui.finish(dialog);
        });
    }

    private void openReview(Z8GitHub.Row pull) {
        if (operationRunning()) return;
        job(client::authStatus, authentication -> {
            if (!authentication.authenticated()) { error = authentication.message; return; }
            saveDrafts(); reviewBodyInput = null;
            reviewKey = "review." + pull.repository + "/" + pull.number;
            reviewBody = drafts().getString(reviewKey, "");
            showReviewForm(pull, authentication.account, drafts().getString(reviewKey + ".event", "COMMENT"));
        });
    }
    private void showReviewForm(Z8GitHub.Row pull, String account, String event) {
        LinearLayout fields = column(); fields.setPadding(dp(20), dp(12), dp(20), dp(16)); fields.setBackgroundColor(palette.background);
        fields.addView(text(pull.repository + " #" + pull.number + "\n@" + account + " · HEAD " + pull.sha.substring(0, 12), 15, palette.foreground));
        String[] events = { "COMMENT", "APPROVE", "REQUEST_CHANGES" };
        String[] labels = { Z8Text.text("Comment", "의견 남기기"), Z8Text.text("Approve", "승인"), Z8Text.text("Request changes", "변경 요청") };
        int selected = Arrays.asList(events).indexOf(event);
        android.widget.Spinner type = new android.widget.Spinner(this); reviewType = type;
        android.widget.ArrayAdapter<String> options = new android.widget.ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, labels);
        type.setAdapter(options); type.setSelection(Math.max(0, selected)); add(fields, type, 12);
        reviewBodyInput = input(Z8Text.text("Review body · Up to 16 KiB", "리뷰 내용 · 최대 16 KiB"), reviewBody, 16384); reviewBodyInput.setSingleLine(false);
        reviewBodyInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        reviewBodyInput.setMinLines(4); reviewBodyInput.setMaxLines(8); add(fields, reviewBodyInput, 10);
        ScrollView scroll = new ScrollView(this); scroll.addView(fields);
        reviewDialog = Z8Ui.dialog(this).setTitle(Z8Text.text("Write PR review", "PR 리뷰 작성")).setView(scroll).setNegativeButton(Z8Text.text("Save draft and close", "초안 저장 후 닫기"), (d, w) -> saveDrafts()).setPositiveButton(Z8Text.text("Review submission", "제출 내용 검토"), null).create();
        reviewDialog.setOnCancelListener(d -> saveDrafts());
        reviewDialog.setOnShowListener(d -> reviewDialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            saveDrafts();
            try {
                Z8GitHub.ReviewRequest request = new Z8GitHub.ReviewRequest(pull.repository, pull.number, account, pull.sha, events[type.getSelectedItemPosition()], reviewBody);
                reviewDialog.dismiss(); previewReview(pull, request);
            } catch (IOException invalid) { reviewBodyInput.setError(message(invalid)); }
        }));
        reviewDialog.show(); Z8Ui.finish(reviewDialog);
    }
    private void previewReview(Z8GitHub.Row pull, Z8GitHub.ReviewRequest request) {
        TextView preview = text(request.repository + " #" + request.number + "\n@" + request.account + "\nHEAD " + request.commit
            + "\n" + request.event + "\n\n" + request.body, 15, palette.foreground);
        preview.setTextIsSelectable(true); preview.setPadding(dp(20), dp(12), dp(20), dp(20)); preview.setBackgroundColor(palette.background);
        ScrollView scroll = new ScrollView(this); scroll.addView(preview);
        reviewDialog = Z8Ui.dialog(this).setTitle(Z8Text.text("Submit review to GitHub", "GitHub에 리뷰 제출")).setView(scroll)
            .setNegativeButton(Z8Text.text("Edit", "수정"), (d, w) -> showReviewForm(pull, request.account, request.event))
            .setPositiveButton(Z8Text.text("Submit reviewed response", "검토한 리뷰 제출"), (d, w) -> {
                saveDrafts();
                try { client.startReview(project.id, request); error = ""; } catch (IOException invalid) { error = message(invalid); }
                observeOperation();
            }).create();
        reviewDialog.show(); Z8Ui.finish(reviewDialog);
    }

    private interface Work<T> { T run() throws Exception; }
    private <T> void job(Work<T> work, Consumer<T> complete) {
        if (busy || isFinishing() || isDestroyed()) return;
        busy = true; error = ""; render();
        io.execute(() -> {
            T value = null; Exception failed = null;
            try { value = work.run(); } catch (Exception exception) { failed = exception; }
            T ready = value; Exception failure = failed;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                busy = false;
                if (failure == null) complete.accept(ready);
                else { error = message(failure); stale = result != null; }
                render();
            });
        });
    }

    /** Platform parser only; no markup, URLs or remote commands are evaluated. */
    private static Object decode(String text) throws IOException {
        try {
            JSONTokener parser = new JSONTokener(text); Object raw = parser.nextValue();
            if (parser.nextClean() != 0) throw new IOException(Z8Text.text("The GitHub response contains unexpected trailing data.", "GitHub 응답 뒤에 예상하지 못한 데이터가 있습니다."));
            return plain(raw, 0, new int[] { 0 });
        } catch (org.json.JSONException invalid) { throw new IOException(Z8Text.text("Could not read the GitHub JSON response.", "GitHub JSON 응답을 읽을 수 없습니다.")); }
    }
    private static Object plain(Object value, int depth, int[] nodes) throws IOException, org.json.JSONException {
        if (depth > 32 || ++nodes[0] > 50000) throw new IOException(Z8Text.text("The GitHub JSON response is too complex.", "GitHub JSON 응답이 너무 복잡합니다."));
        if (value == JSONObject.NULL) return null;
        if (value instanceof JSONObject) {
            JSONObject object = (JSONObject) value; Map<String, Object> result = new HashMap<>();
            Iterator<String> keys = object.keys();
            while (keys.hasNext()) { String key = keys.next(); result.put(key, plain(object.get(key), depth + 1, nodes)); }
            return result;
        }
        if (value instanceof JSONArray) {
            JSONArray array = (JSONArray) value; List<Object> result = new ArrayList<>();
            for (int i = 0; i < array.length(); i++) result.add(plain(array.get(i), depth + 1, nodes));
            return result;
        }
        return value;
    }

    private static String message(Exception failure) {
        String text = failure.getMessage(); return text == null || text.isEmpty() ? Z8Text.text("Could not complete the request. Check the environment and network.", "요청을 완료하지 못했습니다. 환경과 네트워크를 확인해 주세요.") : text;
    }
    private void inputs() {
        if (repositoryInput != null) draftRepository = repositoryInput.getText().toString();
        if (searchInput != null) draftSearch = searchInput.getText().toString();
    }
    private LinearLayout column() { LinearLayout value = new LinearLayout(this); value.setOrientation(LinearLayout.VERTICAL); return value; }
    private LinearLayout row() { LinearLayout value = new LinearLayout(this); value.setOrientation(LinearLayout.HORIZONTAL); return value; }
    private TextView text(String value, int size, int color) { TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color); view.setLineSpacing(dp(2), 1); return view; }
    private EditText input(String hint, String value, int limit) {
        EditText input = new EditText(this); input.setText(value); input.setHint(hint); input.setSingleLine(true);
        input.setTextColor(palette.foreground); input.setHintTextColor(palette.secondary);
        input.setFilters(new InputFilter[] { new InputFilter.LengthFilter(limit) }); input.setEnabled(!busy); return input;
    }
    private Button button(String label, Runnable action) {
        Button button = Z8Ui.button(this, palette, label, () -> { if (!busy) action.run(); });
        button.setEnabled(!busy); button.setAlpha(busy ? .45f : 1f); return button;
    }
    private void equal(LinearLayout parent, android.view.View child) { LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(0, -2, 1); p.rightMargin = dp(5); parent.addView(child, p); }
    private void add(LinearLayout parent, android.view.View child, int top) { LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2); p.topMargin = dp(top); parent.addView(child, p); }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
