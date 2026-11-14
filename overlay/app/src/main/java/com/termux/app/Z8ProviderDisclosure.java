package com.termux.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Information before app-created provider sessions. Manual shell commands remain user-controlled. */
public final class Z8ProviderDisclosure {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final ExecutorService READ = Executors.newSingleThreadExecutor();
    private static final Z8ProviderNotice.PendingRequests<Activity> PENDING = new Z8ProviderNotice.PendingRequests<>();
    private Z8ProviderDisclosure() {}

    /** No tool process or network operation precedes an explicit decision on an unseen notice. */
    public static void beforeLaunch(Activity activity, String projectId, String action, String requestId, Runnable launch, Runnable cancel) {
        if (!Z8ProviderNotice.applies(action)) { launch.run(); return; }
        Z8ProviderNotice.PendingRequests.Ticket ticket = PENDING.begin(activity, requestId, cancel);
        if (ticket == null) return;
        final Path files;
        try {
            new Z8Projects(activity).open(projectId);
            if (Z8ProjectRemoval.isDeleting(projectId)) throw new IllegalStateException();
            Z8ToolManager.State task = Z8ToolManager.state(activity, projectId);
            if (task.busy() && action.equals(task.toolId)) throw new IllegalStateException();
            files = activity.getFilesDir().getCanonicalFile().toPath();
        } catch (Exception unavailable) {
            PENDING.remove(activity, ticket); cancel.run();
            toast(activity, Z8Text.text("The project or tool is busy or unavailable. Try Open again when it is ready.", "프로젝트나 도구가 사용 중이거나 준비되지 않았습니다. 준비된 후 다시 열어 주세요.")); return;
        }
        READ.execute(() -> {
            Z8ProviderInstallIdentity identity = inspect(files, projectId, action);
            MAIN.post(() -> present(activity, projectId, action, files, identity, ticket, launch, cancel));
        });
    }

    private static Z8ProviderInstallIdentity inspect(Path files, String projectId, String tool) {
        return Z8ProviderInstallIdentity.inspect(files, projectId, tool, json -> {
            JSONObject receipt = new JSONObject(json);
            return new Z8ProviderInstallIdentity.Receipt(receipt.getString("manager"), receipt.getString("tool"),
                receipt.getString("version"), receipt.getString("binarySha256"));
        });
    }
    private static boolean live(Activity activity, Z8ProviderNotice.PendingRequests.Ticket ticket) {
        return PENDING.current(activity, ticket) && !activity.isFinishing() && !activity.isDestroyed();
    }
    private static void present(Activity activity, String projectId, String tool, Path files,
            Z8ProviderInstallIdentity identity, Z8ProviderNotice.PendingRequests.Ticket ticket, Runnable launch, Runnable cancel) {
        if (!live(activity, ticket)) { PENDING.remove(activity, ticket); cancel.run(); return; }
        String projectName;
        try { projectName = new Z8Projects(activity).open(projectId).name; }
        catch (Exception unavailable) { PENDING.remove(activity, ticket); cancel.run(); return; }
        Runnable checkedLaunch = () -> {
            PENDING.remove(activity, ticket);
            if (activity.isFinishing() || activity.isDestroyed() || Z8ProjectRemoval.isDeleting(projectId)) { cancel.run(); return; }
            Z8ToolManager.State task = Z8ToolManager.state(activity, projectId);
            if (task.busy() && tool.equals(task.toolId)) {
                cancel.run(); toast(activity, Z8Text.text("This tool is being installed or updated. Open it again when it is ready.", "이 도구를 설치 또는 업데이트 중입니다. 완료된 후 다시 열어 주세요.")); return;
            }
            try { new Z8Projects(activity).open(projectId); }
            catch (Exception unavailable) { cancel.run(); return; }
            launch.run();
        };
        Z8ProviderNotice.Decision decision = new Z8ProviderNotice.Decision(projectId, tool, identity.fingerprint,
            Z8ProviderInstallIdentity.store(files), checkedLaunch);
        if (decision.alreadyAcknowledged()) return;
        LinearLayout content = content(activity);
        paragraph(activity, content, Z8Text.text("This project · ", "현재 프로젝트 · ") + projectName, true);
        paragraph(activity, content, identity.version.isEmpty()
            ? Z8Text.text("Installed version is unverified or custom. This choice opens it once; Z8 will ask again next time.", "설치 버전이 미확인 또는 사용자 설치입니다. 이번에만 열며 다음에는 다시 확인합니다.")
            : Z8Text.text("Recorded installation · ", "기록된 설치 · ") + identity.version, false);
        paragraph(activity, content, Z8ProviderNotice.explanation(tool), false);
        paragraph(activity, content, identity.fingerprint.isEmpty() ? Z8ProviderNotice.boundary()
            : Z8Text.text("Remembered only for this project, this installation and this notice revision. An installation or notice change asks again. ", "이 프로젝트·설치·안내 버전에만 확인을 저장합니다. 설치나 안내가 바뀌면 다시 확인합니다. ") + Z8ProviderNotice.boundary(), false);
        addLinks(activity, content, tool, identity.version);
        ScrollView scroll = new ScrollView(activity); scroll.addView(content);
        boolean[] chosen = {false};
        AlertDialog dialog = Z8Ui.dialog(activity).setTitle(Z8Text.text("Before opening ", "열기 전 확인 · ") + Z8ProviderNotice.name(tool))
            .setView(scroll).setNegativeButton(Z8Text.text("Cancel", "취소"), (d, which) -> {
                chosen[0] = true; decision.cancel(); PENDING.remove(activity, ticket); cancel.run();
            }).setPositiveButton(Z8Text.text("Continue", "계속"), (d, which) -> {
                chosen[0] = true;
                // Recheck the install identity after a potentially long browser/terms visit.
                READ.execute(() -> {
                    Z8ProviderInstallIdentity current = inspect(files, projectId, tool);
                    MAIN.post(() -> {
                        if (!live(activity, ticket)) { decision.cancel(); PENDING.remove(activity, ticket); cancel.run(); return; }
                        if (!current.fingerprint.equals(identity.fingerprint)) {
                            decision.cancel(); present(activity, projectId, tool, files, current, ticket, launch, cancel); return;
                        }
                        decision.continueOnce();
                    });
                });
            }).show();
        dialog.setOnDismissListener(ignored -> {
            if (!chosen[0]) { decision.cancel(); PENDING.remove(activity, ticket); cancel.run(); }
        });
    }

    public static void showInfo(Activity activity, String tool, String version) {
        LinearLayout content = content(activity);
        paragraph(activity, content, Z8ProviderNotice.explanation(tool), false);
        paragraph(activity, content, Z8ProviderNotice.boundary(), false);
        paragraph(activity, content, Z8Text.text("Terms depend on how you sign in. Reading this page does not change any consent, account or client setting.", "로그인 방식에 따라 적용 약관이 달라집니다. 이 페이지를 읽어도 확인 기록·계정·클라이언트 설정은 바뀌지 않습니다."), false);
        addLinks(activity, content, tool, version);
        ScrollView scroll = new ScrollView(activity); scroll.addView(content);
        Z8Ui.dialog(activity).setTitle(Z8ProviderNotice.name(tool) + Z8Text.text(" · Data and terms", " · 데이터·약관"))
            .setView(scroll).setPositiveButton(Z8Text.text("Close", "닫기"), null).show();
    }

    private static void addLinks(Activity activity, LinearLayout content, String tool, String version) {
        paragraph(activity, content, Z8Text.text("Provider documents · opens your browser", "제공자 문서 · 브라우저에서 열림"), true);
        if ("codex".equals(tool) && Z8ToolCatalog.releaseVersion(tool, version).isEmpty())
            paragraph(activity, content, Z8Text.text("The installed version is unknown. Repository license links show the current source; check your installed release's separate component notices too.", "설치 버전을 알 수 없습니다. 라이선스 링크는 현재 저장소를 표시하며, 설치 릴리스의 개별 구성 요소 고지도 확인하세요."), false);
        for (Z8ProviderNotice.Link link : Z8ProviderNotice.links(tool, version)) {
            content.addView(Z8Ui.quiet(activity, Z8Theme.selected(activity), link.label, () -> {
                try { activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(link.url))); }
                catch (RuntimeException unavailable) { toast(activity, Z8Text.text("No browser is available to open this document.", "이 문서를 열 브라우저가 없습니다.")); }
            }), new LinearLayout.LayoutParams(-1, -2));
        }
    }
    private static LinearLayout content(Activity activity) {
        LinearLayout view = new LinearLayout(activity); view.setOrientation(LinearLayout.VERTICAL);
        int padding = dp(activity, 24); view.setPadding(padding, dp(activity, 8), padding, dp(activity, 8)); return view;
    }
    private static void paragraph(Activity activity, LinearLayout parent, String value, boolean accent) {
        TextView view = new TextView(activity); view.setText(value); view.setTextSize(14);
        Z8ChromeStyle style = Z8ChromeStyle.from(Z8Theme.selected(activity)); view.setTextColor(accent ? style.accent : style.text);
        view.setLineSpacing(dp(activity, 2), 1); LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.bottomMargin = dp(activity, 12); parent.addView(view, params);
    }
    private static int dp(Activity activity, int value) { return Math.round(value * activity.getResources().getDisplayMetrics().density); }
    private static void toast(Activity activity, String message) { Toast.makeText(activity, message, Toast.LENGTH_LONG).show(); }
}
