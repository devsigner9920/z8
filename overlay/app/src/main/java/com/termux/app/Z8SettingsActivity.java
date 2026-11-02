package com.termux.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.NotificationManager;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.Toast;
import com.termux.BuildConfig;

/** App preferences. Runtime repair and transport diagnostics stay in debug builds. */
public final class Z8SettingsActivity extends Activity {
    private static final String PROJECT_ID = "dev.devsigner.z8.SETTINGS_PROJECT_ID";
    private String projectId;
    private Z8PanelUi ui;
    private final Runnable dataChanged = () -> { if (!isFinishing() && !isDestroyed()) render(); };

    public static Intent intent(Context context, String selectedProjectId) {
        Intent intent = new Intent(context, Z8SettingsActivity.class);
        if (selectedProjectId != null && !selectedProjectId.isEmpty()) intent.putExtra(PROJECT_ID, selectedProjectId);
        return intent;
    }

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        projectId = getIntent().getStringExtra(PROJECT_ID);
    }

    @Override public void onResume() { super.onResume(); render(); }
    @Override public void onStart() { super.onStart(); Z8BrowserData.observe(dataChanged); }
    @Override public void onStop() { Z8BrowserData.forget(dataChanged); super.onStop(); }

    private void render() {
        int scrollY = ui == null ? 0 : ui.scroll.getScrollY();
        ui = new Z8PanelUi(this, "설정");
        ui.section("화면");
        ui.setting("테마", ui.palette.name, () -> startActivity(new Intent(this, Z8ThemeActivity.class)));
        ui.section("입력");
        ui.setting("단축키 보기", "복사·붙여넣기 · Ctrl + Shift + /", () -> Z8ShortcutHelp.show(this));
        ui.section("알림");
        NotificationManager manager = getSystemService(NotificationManager.class);
        boolean enabled = manager != null && manager.areNotificationsEnabled();
        ui.setting("시스템 알림", enabled ? "켜짐 · Android 설정에서 변경" : "꺼짐 · Android 설정에서 변경",
            () -> startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName())));
        ui.section("앱 정보");
        ui.setting("z8", "버전 " + BuildConfig.VERSION_NAME, null);
        ui.setting("개인정보처리방침", "데이터 처리와 문의 안내", () -> openAbout(Z8AboutActivity.Page.PRIVACY));
        ui.setting("데이터 보관·삭제", "프로젝트 · 로그인 정보 · 브라우저", () -> openAbout(Z8AboutActivity.Page.DATA));
        ui.setting("환경·외부 도구 안내", "Linux 실행 범위와 외부 서비스", () -> openAbout(Z8AboutActivity.Page.ENVIRONMENT));
        ui.setting("오픈소스 라이선스·소스", "포함된 소프트웨어의 고지", () -> openAbout(Z8AboutActivity.Page.LICENSES));
        ui.section("미리보기 데이터");
        ui.setting("미리보기 데이터 삭제", Z8BrowserData.status(),
            Z8BrowserData.running() ? null : this::confirmClearPreviewData);

        if (BuildConfig.DEBUG) {
            ui.section("개발자");
            ui.setting("런타임 진단", "실행 환경과 기기 호환성 확인",
                () -> startActivity(new Intent(this, Z8DiagnosticsActivity.class)));
            if (projectId != null && projectId.matches("[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}")) {
                ui.setting("현재 프로젝트 환경", "개발 도구 설치와 환경 복구",
                    () -> startActivity(Z8EnvironmentActivity.intent(this, projectId)));
            }
            ui.setting("훅 수신 테스트", Z8AttentionBridge.diagnosticStatus(this), () ->
                Z8AttentionBridge.sendDiagnostic(this, status -> {
                    if (isFinishing() || isDestroyed()) return;
                    Toast.makeText(this, status, Toast.LENGTH_LONG).show(); render();
                }));
        }
        ui.scroll.post(() -> { if (!isDestroyed()) ui.scroll.scrollTo(0, scrollY); });
    }

    private void openAbout(Z8AboutActivity.Page page) {
        startActivity(Z8AboutActivity.intent(this, page));
    }

    private void confirmClearPreviewData() {
        if (Z8BrowserData.running()) return;
        new AlertDialog.Builder(this).setTitle("모든 미리보기 데이터를 삭제할까요?")
            .setMessage("모든 프로젝트가 공유하는 Z8 내부 미리보기의 쿠키, 사이트 저장소, 캐시와 서비스 워커를 삭제합니다. 열린 미리보기를 멈추며, 웹페이지의 로그인 상태와 저장된 작업이 사라질 수 있습니다.\n\n프로젝트 파일, CLI 로그인 정보, 기기 브라우저의 로그인 상태는 삭제하지 않습니다. 터미널과 개발 서버는 계속 실행됩니다. 이 작업은 되돌릴 수 없습니다.")
            .setNegativeButton("취소", null)
            .setPositiveButton("전체 미리보기 데이터 삭제", (dialog, which) -> Z8BrowserData.clear()).show();
    }

}
