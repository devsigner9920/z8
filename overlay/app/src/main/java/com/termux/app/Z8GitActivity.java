package com.termux.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
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
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.termux.shared.termux.TermuxConstants;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.util.Arrays;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

/** Real project Git state. Remote operations only run after explicit user selection. */
public final class Z8GitActivity extends Activity {
    private static final String PROJECT_ID = "dev.devsigner.z8.GIT_PROJECT_ID";
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private Z8Theme.Palette palette;
    private Z8Projects.Project project;
    private Z8Git git;
    private boolean guestMode;
    private String unavailableDetail = "";
    private String readFailure = "";
    private Z8Git.Status status;
    private boolean repository;
    private boolean busy;
    private String feedback = "";
    private String authorName = "";
    private String authorEmail = "";
    private TextView progress;
    private String projectId, commitMessage = "";
    private EditText commitMessageInput, authorNameInput, authorEmailInput;
    private AlertDialog commitDialog;
    private boolean restoreCommitDialog;
    private SharedPreferences drafts() { return getSharedPreferences("z8-git-draft-" + projectId, MODE_PRIVATE); }
    private void saveDraft() {
        if (commitMessageInput != null) commitMessage = commitMessageInput.getText().toString();
        if (authorNameInput != null) authorName = authorNameInput.getText().toString();
        if (authorEmailInput != null) authorEmail = authorEmailInput.getText().toString();
        drafts().edit().putString("message", commitMessage).putString("name", authorName).putString("email", authorEmail).apply();
    }

    public static Intent intent(Context context, String projectId) {
        return new Intent(context, Z8GitActivity.class).putExtra(PROJECT_ID, projectId);
    }

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        projectId = getIntent().getStringExtra(PROJECT_ID);
        commitMessage = drafts().getString("message", ""); authorName = drafts().getString("name", ""); authorEmail = drafts().getString("email", "");
        if (state != null) {
            authorName = state.getString("authorName", "");
            authorEmail = state.getString("authorEmail", "");
            commitMessage = state.getString("commitMessage", commitMessage);
            restoreCommitDialog = state.getBoolean("commitDialog", false);
        }
        render();
        String id = getIntent().getStringExtra(PROJECT_ID);
        job(() -> new Z8Projects(this).open(id), selected -> {
            project = selected;
            refresh();
        });
    }

    @Override protected void onResume() {
        super.onResume();
        if (palette != null && !palette.id.equals(Z8Theme.selected(this).id)) render();
        if (project != null && !busy) refresh();
    }

    @Override protected void onPause() { saveDraft(); super.onPause(); }

    @Override protected void onSaveInstanceState(Bundle state) {
        saveDraft(); state.putString("commitMessage", commitMessage);
        state.putBoolean("commitDialog", commitDialog != null && commitDialog.isShowing());
        state.putString("authorName", authorName);
        state.putString("authorEmail", authorEmail);
        super.onSaveInstanceState(state);
    }

    @Override protected void onDestroy() {
        // Let an accepted mutation finish; a recreated activity reads fresh state.
        if (commitDialog != null) commitDialog.dismiss();
        io.shutdown(); super.onDestroy();
    }

    private void render() {
        palette = Z8Theme.selected(this);
        Z8Theme.applyChrome(this, palette);
        setTitle("z8 · Git");
        LinearLayout frame = column();
        frame.setBackgroundColor(palette.background);
        frame.setGravity(Gravity.CENTER_HORIZONTAL);
        LinearLayout content = column();
        content.setPadding(dp(20), dp(18), dp(20), dp(10));
        int width = getResources().getConfiguration().screenWidthDp > 920 ? dp(920) : -1;
        frame.addView(content, new LinearLayout.LayoutParams(width, -1));
        TextView title = text(project == null ? "Git" : project.name + " / Git", 25, palette.foreground);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD); content.addView(title);
        add(content, text(guestMode ? "LOCAL · 프로젝트 Linux Git" : "LOCAL · Android Git (진단)", 12, palette.accent), 6);
        LinearLayout tools = row();
        equal(tools, button("‹ 프로젝트로", this::finish));
        equal(tools, button("새로고침", this::refresh));
        add(content, tools, 14);
        if (git == null) {
            add(content, text("프로젝트를 확인하고 있습니다…", 16, palette.secondary), 26);
        } else if (!git.available()) {
            add(content, text("Git이 아직 설치되지 않았습니다", 22, palette.foreground), 26);
            add(content, text(guestMode
                ? "이 프로젝트의 Linux 환경에 Git이 필요합니다. 설치되면 터미널과 같은 HOME·설정·훅을 사용합니다."
                : "현재는 Android Git 진단 경로입니다. 프로젝트 Linux 환경을 설치하면 그 환경의 Git을 사용합니다.", 16, palette.secondary), 12);
            if (!unavailableDetail.isEmpty()) add(content, text(unavailableDetail, 14, palette.secondary), 10);
            add(content, button("Linux 환경 열기", () -> startActivity(Z8EnvironmentActivity.intent(this, project.id))), 16);
        } else if (!readFailure.isEmpty()) {
            add(content, text("Git 상태를 읽지 못했습니다", 22, palette.foreground), 26);
            add(content, text(readFailure, 15, palette.secondary), 12);
            add(content, text("터미널에서 환경을 확인한 뒤 새로고침해 주세요.", 14, palette.secondary), 12);
        } else if (!repository) {
            add(content, text("이 프로젝트는 아직 Git 저장소가 아닙니다", 20, palette.foreground), 26);
            add(content, text("기존 소스 파일을 그대로 두고 로컬 버전 관리를 시작할 수 있습니다.", 15, palette.secondary), 12);
            add(content, button("Git 저장소 만들기", this::initRepository), 18);
        } else if (status != null) {
            add(content, text(status.branch + (status.head.isEmpty() ? " · 첫 커밋 전" : ""), 19, palette.foreground), 20);
            add(content, text("변경 " + status.changes.size() + "개 · 스테이지 " + status.stagedCount() + "개", 14, palette.secondary), 5);
            LinearLayout repositoryTools = row();
            equal(repositoryTools, button("브랜치", this::branchMenu));
            equal(repositoryTools, button("원격 작업", this::remoteMenu));
            add(content, repositoryTools, 10);
            Button commit = Z8Ui.primary(this, palette, "스테이지된 변경 커밋", () -> { if (!busy) prepareCommit(); });
            commit.setEnabled(status.stagedCount() > 0 && !status.conflicts());
            commit.setAlpha(commit.isEnabled() ? 1f : .45f);
            add(content, commit, 12);
            if (status.conflicts()) add(content, text("충돌을 해결한 파일만 확인 후 스테이지에 올려주세요.", 14, palette.accent), 8);
            if (status.changes.isEmpty()) add(content, text("변경사항이 없습니다.", 18, palette.secondary), 28);
            ListView changes = new ListView(this);
            changes.setDivider(null);
            changes.setAdapter(new BaseAdapter() {
                @Override public int getCount() { return status.changes.size(); }
                @Override public Object getItem(int index) { return status.changes.get(index); }
                @Override public long getItemId(int index) { return index; }
                @Override public View getView(int index, View reused, ViewGroup parent) {
                    TextView item = reused instanceof TextView ? (TextView) reused : text("", 15, palette.foreground);
                    Z8Git.Change change = status.changes.get(index);
                    item.setText("[" + change.index + change.worktree + "]  " + change.displayPath()
                        + "\n" + (change.conflict() ? "충돌" : change.untracked() ? "새 파일" : change.staged() && change.unstaged() ? "스테이지 + 추가 변경" : change.staged() ? "스테이지됨" : "변경됨"));
                    item.setPadding(dp(6), dp(15), dp(6), dp(15));
                    item.setMinHeight(dp(64)); return item;
                }
            });
            changes.setOnItemClickListener((parent, view, position, id) -> { if (!busy) changeMenu(status.changes.get(position)); });
            LinearLayout.LayoutParams listParams = new LinearLayout.LayoutParams(-1, 0, 1);
            listParams.topMargin = dp(12); content.addView(changes, listParams);
        }
        progress = text(busy ? "Git 작업 중…" : feedback, 13, palette.secondary);
        progress.setMinHeight(dp(34)); add(content, progress, 10);
        setContentView(frame);
    }

    private static final class Adapter {
        final Z8Git git;
        final boolean guest;
        final String unavailableDetail;
        Adapter(Z8Git git, boolean guest, String detail) {
            this.git = git; this.guest = guest; this.unavailableDetail = detail;
        }
    }

    /** Off the UI thread; a present/broken guest never falls back to host Git. */
    private Adapter adapter() throws IOException {
        Map<String, String> env = new HashMap<>(System.getenv());
        env.put("PATH", TermuxConstants.TERMUX_PREFIX_DIR_PATH + "/bin");
        env.put("PREFIX", TermuxConstants.TERMUX_PREFIX_DIR_PATH);
        File rootfs = new File(getFilesDir(), "z8/environments/" + project.id + "/rootfs");
        if (Files.exists(rootfs.toPath(), LinkOption.NOFOLLOW_LINKS)) {
            File executable = new File(rootfs, "usr/bin/git");
            File home = new File(getFilesDir(), "z8/homes/" + project.id);
            File temp = new File(getFilesDir(), "z8/environments/" + project.id + "/tmp");
            Z8GuestGit runner;
            String reason = "";
            try {
                File checked = executable.getCanonicalFile();
                if (!checked.toPath().startsWith(rootfs.getCanonicalFile().toPath()))
                    throw new IOException("프로젝트 Linux Git 경로가 환경 밖을 가리킵니다.");
                executable = checked;
                Z8Guest.Launch launch = Z8Guest.commandFor(this, project.id, "", new String[] { "/usr/bin/git" });
                runner = new Z8GuestGit(new File(launch.executable), project.source, executable,
                    Arrays.asList(launch.arguments), launch.commandOffset, new Z8Git.ProcessRunner());
                env.put("PROOT_TMP_DIR", temp.getAbsolutePath());
            } catch (IOException invalid) {
                reason = invalid.getMessage() == null ? "프로젝트 Linux 환경을 확인해 주세요." : invalid.getMessage();
                runner = Z8GuestGit.unavailable(reason);
            }
            return new Adapter(Z8Git.guest(executable, project.source, home, temp, env, runner), true, reason);
        }
        File executable = new File(TermuxConstants.TERMUX_PREFIX_DIR_PATH, "bin/git");
        return new Adapter(new Z8Git(executable, project.source,
            new File(project.source.getParentFile(), "git-home"),
            new File(project.source.getParentFile(), "git-tmp"), env), false, "");
    }

    private void refresh() {
        if (busy || project == null) return;
        job(() -> {
            Adapter adapter = adapter();
            Z8Git.Status loaded = null;
            String failure = "";
            try {
                if (adapter.git.available() && adapter.git.repositoryExists()) loaded = adapter.git.status();
            } catch (IOException invalid) {
                // Retain the newly selected environment even when its Git fails.
                // Old Android Git controls must not survive a guest transition.
                failure = invalid.getMessage() == null ? "프로젝트 Git 실행을 확인해 주세요." : invalid.getMessage();
            }
            return new Object[] { adapter, loaded, failure };
        }, result -> {
            Adapter selected = (Adapter) result[0];
            git = selected.git; guestMode = selected.guest; unavailableDetail = selected.unavailableDetail;
            status = (Z8Git.Status) result[1]; readFailure = (String) result[2];
            repository = status != null; render();
            if (restoreCommitDialog && status != null) {
                restoreCommitDialog = false;
                if (status.stagedCount() > 0 && !status.conflicts()) commitDialog(status);
            }
        });
    }

    private void initRepository() {
        if (busy || git == null) return;
        Z8Ui.dialog(this).setTitle("로컬 Git 저장소 만들기")
            .setMessage(project.name + "의 현재 소스 폴더에 Git 저장소를 만들까요? 파일을 자동으로 스테이지하거나 커밋하지 않습니다.")
            .setNegativeButton("취소", null).setPositiveButton("만들기", (dialog, which) ->
                job(() -> { git.init(); return true; }, ignored -> { feedback = "로컬 저장소를 만들었습니다."; refresh(); })).show();
    }

    private void branchMenu() {
        if (busy || status == null) return;
        job(() -> new Object[]{git.status(), git.branches()}, result -> {
            Z8Git.Status expected = (Z8Git.Status) result[0];
            @SuppressWarnings("unchecked") List<String> branches = (List<String>) result[1];
            List<String> labels = new ArrayList<>(); labels.add("+ 새 브랜치 만들기"); labels.addAll(branches);
            Z8Ui.dialog(this).setTitle("현재 브랜치 · " + expected.branch)
                .setItems(labels.toArray(new String[0]), (dialog, which) -> {
                    if (which == 0) {
                        EditText name = input("새 브랜치 이름", "", true);
                        Z8Ui.dialog(this).setTitle("브랜치 만들고 전환")
                            .setView(name).setNegativeButton("취소", null)
                            .setPositiveButton("만들기", (ignored, button) -> switchBranch(expected, name.getText().toString(), true)).show();
                    } else {
                        String branch = branches.get(which - 1);
                        Z8Ui.dialog(this).setTitle("브랜치 전환")
                            .setMessage(expected.branch + " → " + branch)
                            .setNegativeButton("취소", null)
                            .setPositiveButton("전환", (ignored, button) -> switchBranch(expected, branch, false)).show();
                    }
                }).setNegativeButton("닫기", null).show();
        });
    }

    private void switchBranch(Z8Git.Status expected, String branch, boolean create) {
        job(() -> { git.switchBranch(expected, branch, create); return true; }, ignored -> {
            feedback = branch + " 브랜치로 전환했습니다."; refresh();
        });
    }

    private void remoteMenu() {
        if (busy || status == null) return;
        job(() -> new Object[]{git.status(), git.remotes()}, result -> {
            Z8Git.Status expected = (Z8Git.Status) result[0];
            @SuppressWarnings("unchecked") List<Z8Git.Remote> remotes = (List<Z8Git.Remote>) result[1];
            if (remotes.isEmpty()) {
                Z8Ui.dialog(this).setTitle("원격 저장소가 필요합니다")
                    .setMessage("터미널에서 저장소를 clone하거나 remote를 등록한 뒤 다시 확인해 주세요. 여러 URL이 있는 remote는 터미널에서 처리할 수 있습니다.")
                    .setPositiveButton("확인", null).show(); return;
            }
            String[] names = new String[remotes.size()];
            for (int i = 0; i < names.length; i++) names[i] = remotes.get(i).name + " · " + remotes.get(i).destination(false);
            Z8Ui.dialog(this).setTitle("원격 저장소 선택")
                .setItems(names, (dialog, which) -> remoteActions(expected, remotes.get(which)))
                .setNegativeButton("취소", null).show();
        });
    }

    private void remoteActions(Z8Git.Status expected, Z8Git.Remote remote) {
        String[] actions = {"fetch", "pull", "push"};
        String[] labels = {"Fetch · 원격 변경 가져오기", "Pull · 현재 브랜치 앞으로 이동", "Push · 현재 브랜치 보내기"};
        Z8Ui.dialog(this).setTitle(remote.name)
            .setItems(labels, (dialog, which) -> {
                String action = actions[which];
                String explanation = which == 0 ? "로컬 작업 파일은 바꾸지 않고 원격 참조를 갱신합니다."
                    : which == 1 ? "변경 파일이 없는 상태에서 fast-forward가 가능할 때만 갱신합니다. 자동 병합·리베이스는 하지 않습니다."
                    : "현재 HEAD를 같은 이름의 원격 브랜치로 보냅니다. 강제 푸시는 사용하지 않습니다.";
                Z8Ui.dialog(this).setTitle(labels[which])
                    .setMessage(remote.destination(which == 2) + "\n브랜치 · " + expected.branch + "\n\n" + explanation)
                    .setNegativeButton("취소", null).setPositiveButton(action, (ignored, button) ->
                        job(() -> { git.network(expected, remote, action); return true; }, done -> {
                            feedback = action + " 작업을 완료했습니다."; refresh();
                        })).show();
            }).setNegativeButton("취소", null).show();
    }

    private void changeMenu(Z8Git.Change change) {
        List<String> names = new ArrayList<>();
        List<Runnable> actions = new ArrayList<>();
        if (change.unstaged()) {
            names.add("작업 파일 diff 보기"); actions.add(() -> showDiff(change, false));
            names.add("이 파일 스테이지"); actions.add(() -> job(() -> { git.stage(change); return true; }, ignored -> {
                feedback = "스테이지에 올렸습니다."; refresh();
            }));
        }
        if (change.staged()) {
            names.add("스테이지된 diff 보기"); actions.add(() -> showDiff(change, true));
            names.add("이 파일 스테이지 해제"); actions.add(() -> job(() -> { git.unstage(change); return true; }, ignored -> {
                feedback = "스테이지에서 내렸습니다. 작업 파일은 유지됩니다."; refresh();
            }));
        }
        Z8Ui.dialog(this).setTitle(change.displayPath())
            .setItems(names.toArray(new String[0]), (dialog, selected) -> actions.get(selected).run())
            .setNegativeButton("닫기", null).show();
    }

    private void showDiff(Z8Git.Change change, boolean staged) {
        job(() -> git.diff(change, staged), diff -> {
            TextView output = text(diff.isEmpty() ? "이 비교에서 표시할 차이가 없습니다." : diff, 13, palette.foreground);
            output.setTypeface(Typeface.MONOSPACE); output.setTextIsSelectable(true);
            output.setPadding(dp(16), dp(12), dp(16), dp(18)); output.setBackgroundColor(palette.background);
            ScrollView scroll = new ScrollView(this); scroll.addView(output);
            Z8Ui.dialog(this).setTitle(staged ? "스테이지된 diff" : "작업 파일 diff")
                .setView(scroll).setPositiveButton("닫기", null).show();
        });
    }

    private void prepareCommit() {
        if (status == null || busy) return;
        // Read again before showing the user the set that will be committed.
        job(() -> new Object[] { git.status(), git.author() }, values -> {
            status = (Z8Git.Status) values[0];
            String[] author = (String[]) values[1];
            if (authorName.isEmpty()) authorName = author[0];
            if (authorEmail.isEmpty()) authorEmail = author[1];
            render();
            if (status.stagedCount() == 0 || status.conflicts()) {
                feedback = "스테이지와 충돌 상태를 확인해 주세요."; render(); return;
            }
            commitDialog(status);
        });
    }

    private void commitDialog(Z8Git.Status expected) {
        LinearLayout content = column(); content.setPadding(dp(20), dp(8), dp(20), dp(12));
        content.setBackgroundColor(palette.background);
        StringBuilder files = new StringBuilder();
        for (Z8Git.Change change : expected.changes) if (change.staged()) {
            if (files.length() > 2000) { files.append("\n…"); break; }
            files.append(change.displayPath()).append('\n');
        }
        content.addView(text("스테이지된 " + expected.stagedCount() + "개 파일\n" + files, 13, palette.secondary));
        EditText message = input("커밋 메시지", commitMessage, false); commitMessageInput = message;
        message.setMinLines(3); message.setMaxLines(6);
        add(content, message, 8);
        EditText name = input("작성자 이름", authorName, true); authorNameInput = name;
        EditText email = input("작성자 이메일", authorEmail, true); authorEmailInput = email;
        email.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        add(content, name, 6); add(content, email, 6);
        add(content, text("초안은 이 프로젝트에 보관됩니다. 작성자 정보는 이번 커밋에만 적용되며 푸시는 별도로 실행합니다.", 12, palette.secondary), 10);
        ScrollView scroll = new ScrollView(this); scroll.addView(content);
        AlertDialog dialog = Z8Ui.dialog(this).setTitle("로컬 커밋")
            .setView(scroll).setNegativeButton("초안 저장 후 닫기", (d, w) -> saveDraft()).setPositiveButton("커밋", null).create();
        commitDialog = dialog; dialog.setOnCancelListener(d -> saveDraft());
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
            saveDraft();
            String text = message.getText().toString();
            if (text.trim().isEmpty()) { message.setError("커밋 메시지를 입력해 주세요."); return; }
            try {
                authorName = Z8Git.identity(name.getText().toString(), false);
                authorEmail = Z8Git.identity(email.getText().toString(), true);
            } catch (Exception error) { email.setError(error.getMessage()); return; }
            dialog.dismiss();
            job(() -> git.commit(expected, text, authorName, authorEmail), output -> {
                commitMessage = ""; commitMessageInput = null; authorNameInput = null; authorEmailInput = null; saveDraft();
                feedback = "로컬 커밋을 만들었습니다.";
                Toast.makeText(this, feedback, Toast.LENGTH_LONG).show(); refresh();
            });
        }));
        dialog.show(); Z8Ui.finish(dialog);
    }

    private interface Work<T> { T run() throws Exception; }
    private <T> void job(Work<T> work, Consumer<T> complete) {
        if (busy || isFinishing() || isDestroyed()) return;
        busy = true; if (progress != null) progress.setText("Git 작업 중…");
        io.execute(() -> {
            T value = null; Exception failure = null;
            try { value = work.run(); } catch (Exception exception) { failure = exception; }
            T result = value; Exception error = failure;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                busy = false;
                if (error == null) {
                    if (progress != null) progress.setText(feedback);
                    complete.accept(result);
                } else {
                    feedback = "작업을 완료하지 못했습니다. 초안은 보관했습니다. 상태를 새로고침해 주세요.";
                    if (progress != null) progress.setText(feedback);
                    Z8Ui.dialog(this).setTitle("Git 작업을 완료하지 못했습니다")
                        .setMessage(error.getMessage() == null ? error.toString() : error.getMessage())
                        .setPositiveButton("확인", null).show();
                }
            });
        });
    }

    private EditText input(String hint, String value, boolean singleLine) {
        EditText input = new EditText(this); input.setHint(hint); input.setText(value);
        input.setTextColor(palette.foreground); input.setHintTextColor(palette.secondary);
        input.setSingleLine(singleLine); input.setFilters(new InputFilter[] { new InputFilter.LengthFilter(singleLine ? 200 : 8192) });
        return input;
    }
    private LinearLayout column() { LinearLayout view = new LinearLayout(this); view.setOrientation(LinearLayout.VERTICAL); return view; }
    private LinearLayout row() { LinearLayout view = new LinearLayout(this); view.setOrientation(LinearLayout.HORIZONTAL); return view; }
    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color); view.setLineSpacing(dp(2), 1); return view;
    }
    private Button button(String value, Runnable action) {
        return Z8Ui.button(this, palette, value, () -> { if (!busy) action.run(); });
    }
    private void equal(LinearLayout parent, View view) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -2, 1); params.rightMargin = dp(5); parent.addView(view, params);
    }
    private void add(LinearLayout parent, View view, int top) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2); params.topMargin = dp(top); parent.addView(view, params);
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
