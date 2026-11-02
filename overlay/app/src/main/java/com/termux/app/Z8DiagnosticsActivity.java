package com.termux.app;

import android.app.Activity;
import android.app.ActivityManager;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.system.Os;
import android.system.OsConstants;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.termux.BuildConfig;
import com.termux.shared.termux.TermuxConstants;

import java.io.File;
import java.util.Locale;

/** G0 entry point. Displays observations; it does not certify Linux or CLI compatibility. */
public final class Z8DiagnosticsActivity extends Activity {

    public static final String EXTRA_DIAGNOSTIC_SHELL =
        "dev.devsigner.z8.DIAGNOSTIC_SHELL";

    private int BACKGROUND;
    private int FOREGROUND;
    private int SECONDARY;
    private Z8Theme.Palette palette;

    private TextView runtimeStatus;
    private TextView runtimeExplanation;
    private TextView observations;
    private Button linuxButton;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (!Z8Theme.isSetupComplete(this)) {
            startActivity(new Intent(this, Z8ThemeActivity.class)
                .putExtra(Z8ThemeActivity.EXTRA_FIRST_SETUP, true));
            finish();
            return;
        }
        renderContent();
    }

    private void renderContent() {
        palette = Z8Theme.selected(this);
        BACKGROUND = palette.background;
        FOREGROUND = palette.foreground;
        SECONDARY = palette.secondary;
        Z8Theme.applyChrome(this, palette);
        setTitle(Z8Text.text("z8 · Runtime diagnostics", "z8 · 실행 진단"));

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BACKGROUND);

        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(24), dp(28), dp(24), dp(28));
        scroll.addView(content, new ScrollView.LayoutParams(
            ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));

        TextView title = text(Z8Text.text("z8 Runtime Diagnostics", "z8 실행 진단"), 28, FOREGROUND);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        content.addView(title);
        content.addView(text(Z8Text.text("Check the execution environment on this device.", "이 기기의 실행 환경을 확인합니다."), 16, SECONDARY));

        Button themeButton = button(Z8Text.text("Theme settings · ", "테마 설정 · ") + palette.name);
        themeButton.setOnClickListener(view -> startActivity(new Intent(this, Z8ThemeActivity.class)));
        addSpaced(content, themeButton, 18);

        Button workspaceButton = button(Z8Text.text("Projects and sessions", "프로젝트와 세션"));
        workspaceButton.setOnClickListener(view -> startActivity(new Intent(this, TermuxActivity.class)
            .putExtra(Z8WorkspaceActivity.EXTRA_SHOW_SESSIONS, true)));
        addSpaced(content, workspaceButton, 10);
        Button attentionButton = button(Z8Text.text("Responses and hook notifications", "응답 확인 / 훅 알림"));
        attentionButton.setOnClickListener(view -> startActivity(new Intent(this, Z8AttentionActivity.class)));
        addSpaced(content, attentionButton, 10);

        runtimeStatus = text("", 20, FOREGROUND);
        runtimeStatus.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        addSpaced(content, runtimeStatus, 28);
        runtimeExplanation = text("", 15, SECONDARY);
        addSpaced(content, runtimeExplanation, 10);

        Button resumeButton = button(Z8Text.text("Open or resume terminal", "터미널 열기 / 이어가기"));
        // Navigation reconnects to the current session without creating a shell.
        resumeButton.setOnClickListener(view ->
            startActivity(new Intent(this, TermuxActivity.class)));
        addSpaced(content, resumeButton, 24);

        Button diagnosticButton = button(Z8Text.text("New Android diagnostic shell", "새 Android 진단 셸 만들기"));
        diagnosticButton.setOnClickListener(view -> openTerminal(true));
        addSpaced(content, diagnosticButton, 10);
        addSpaced(content, text(
            Z8Text.text("Runs /system/bin/sh through the Termux terminal and service. ", "/system/bin/sh를 Termux 터미널과 서비스로 실행합니다. ")
                + Z8Text.text("This does not install a PRoot Linux environment, Claude or Codex.", "PRoot Linux 환경이나 Claude·Codex가 설치되는 것은 아닙니다."),
            14, SECONDARY), 6);

        linuxButton = button(Z8Text.text("Install Linux runtime / Open terminal", "Linux 런타임 설치 / 터미널 열기"));
        linuxButton.setOnClickListener(view -> {
            // Recheck at the action boundary instead of trusting the last rendered state.
            if (BuildConfig.Z8_HAS_BOOTSTRAP && prefixMatchesApp()) {
                openTerminal(false);
            } else {
                refreshObservations();
                Toast.makeText(this, Z8Text.text("This APK cannot start Linux runtime installation.", "이 APK에서는 Linux 런타임 설치를 시작할 수 없습니다."),
                    Toast.LENGTH_LONG).show();
            }
        });
        addSpaced(content, linuxButton, 18);

        TextView detailsTitle = text(Z8Text.text("Device and runtime information", "기기 및 런타임 정보"), 20, FOREGROUND);
        detailsTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        addSpaced(content, detailsTitle, 28);
        observations = text("", 14, FOREGROUND);
        observations.setTypeface(Typeface.MONOSPACE);
        observations.setTextIsSelectable(true);
        addSpaced(content, observations, 12);

        Button refresh = button(Z8Text.text("Refresh information", "정보 새로고침"));
        refresh.setOnClickListener(view -> refreshObservations());
        addSpaced(content, refresh, 18);
        addSpaced(content, text(
            Z8Text.text("File presence and APK build information alone do not establish compatibility. ", "파일 존재와 APK 빌드 정보만으로 실행 호환성을 판정하지 않습니다. ")
                + Z8Text.text("Shell, tmux, PRoot and CLI execution, and background session survival require separate tests.", "셸·tmux·PRoot·AI CLI의 실제 작업과 백그라운드 유지 시험은 별도로 필요합니다."),
            14, SECONDARY), 14);

        setContentView(scroll);
        refreshObservations();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (observations != null) {
            if (!palette.id.equals(Z8Theme.selected(this).id)) renderContent();
            else refreshObservations();
        }
    }

    private void refreshObservations() {
        File bash = new File(TermuxConstants.TERMUX_PREFIX_DIR_PATH, "bin/bash");
        boolean bashPresent = bash.isFile();
        boolean matchingPrefix = prefixMatchesApp();
        boolean canInstall = BuildConfig.Z8_HAS_BOOTSTRAP && matchingPrefix;

        if (!matchingPrefix) {
            runtimeStatus.setText(Z8Text.text("Android diagnostic shell / Runtime path mismatch", "Android 진단 셸 / 런타임 경로 불일치"));
            runtimeExplanation.setText(
                Z8Text.text("The runtime build path differs from the app's internal path. ", "빌드된 런타임 경로와 현재 앱의 내부 경로가 다릅니다. ")
                    + Z8Text.text("Stop Linux installation and check the application ID and bootstrap build settings.", "Linux 설치를 중지하고 앱 ID와 bootstrap 빌드 설정을 확인해야 합니다."));
        } else if (!BuildConfig.Z8_HAS_BOOTSTRAP) {
            runtimeStatus.setText(bashPresent
                ? Z8Text.text("Android diagnostic shell / Existing runtime files found", "Android 진단 셸 / 기존 런타임 파일 감지")
                : Z8Text.text("Android diagnostic shell / Linux runtime not installed", "Android 진단 셸 / Linux 런타임 미설치"));
            runtimeExplanation.setText(
                Z8Text.text("This diagnostic APK does not include a bootstrap built for Z8's paths. ", "이 진단 APK에는 z8 전용 경로로 빌드한 bootstrap이 포함되어 있지 않습니다. ")
                    + Z8Text.text("Installing and running Linux requires a runtime APK containing that bootstrap. ", "Linux 설치·실행에는 해당 bootstrap을 포함한 런타임 APK가 필요합니다. ")
                    + (bashPresent ? Z8Text.text("An existing bash file was found, but this screen will not execute it.", "기존 bash 파일은 발견했지만 이 화면에서 실행하지 않습니다.") : ""));
        } else if (!bashPresent) {
            runtimeStatus.setText(Z8Text.text("Android diagnostic shell / Linux runtime not yet installed", "Android 진단 셸 / Linux 런타임 설치 전"));
            runtimeExplanation.setText(
                Z8Text.text("This APK includes a bootstrap. Use the button below to start installation. ", "이 APK에는 bootstrap이 포함되어 있습니다. 아래 버튼으로 설치를 시작할 수 있습니다. ")
                    + Z8Text.text("Bootstrap installation prepares the Termux runtime; ", "bootstrap 설치는 Termux 실행 기반을 준비하는 단계이며, ")
                    + Z8Text.text("installing and verifying the PRoot distribution and CLIs are separate steps.", "PRoot 배포판과 AI CLI의 설치·검증은 별도입니다."));
        } else {
            runtimeStatus.setText(Z8Text.text("Linux runtime files found / Execution verification required", "Linux 런타임 파일 감지 / 실행 검증 필요"));
            runtimeExplanation.setText(
                Z8Text.text("prefix/bin/bash exists. File presence does not prove installation completeness or a G0 test pass. ", "prefix/bin/bash 파일이 존재합니다. 파일 존재는 설치 완료 또는 G0 통과의 증거가 아닙니다. ")
                    + Z8Text.text("Verify actual execution, PRoot and CLI behavior in a terminal.", "터미널에서 실제 실행과 PRoot·AI CLI 동작을 확인해야 합니다."));
        }

        linuxButton.setEnabled(canInstall);
        linuxButton.setAlpha(canInstall ? 1f : 0.4f);
        linuxButton.setText(bashPresent ? Z8Text.text("Open Linux runtime terminal", "Linux 런타임 터미널 열기") : Z8Text.text("Install Linux runtime / Open terminal", "Linux 런타임 설치 / 터미널 열기"));

        StringBuilder report = new StringBuilder();
        field(report, Z8Text.text("Manufacturer", "제조사"), Build.MANUFACTURER);
        field(report, Z8Text.text("Model", "모델"), Build.MODEL);
        field(report, Z8Text.text("Device codename", "기기 코드"), Build.DEVICE);
        field(report, "Android", Build.VERSION.RELEASE);
        field(report, "SDK / target SDK", Build.VERSION.SDK_INT + " / "
            + getApplicationInfo().targetSdkVersion);
        field(report, Z8Text.text("Supported ABIs", "지원 ABI"), joinAbis());
        field(report, Z8Text.text("App process", "앱 프로세스"), Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
            ? (android.os.Process.is64Bit() ? "64-bit" : "32-bit") : Z8Text.text("Unavailable", "확인 불가"));
        appendMemory(report);
        field(report, Z8Text.text("Memory page size", "메모리 페이지 크기"), pageSize());
        field(report, Z8Text.text("Application ID", "앱 ID"), getPackageName());
        field(report, Z8Text.text("Actual files path", "실제 files 경로"), getFilesDir().getAbsolutePath());
        field(report, Z8Text.text("Built prefix", "빌드된 prefix"), TermuxConstants.TERMUX_PREFIX_DIR_PATH);
        field(report, Z8Text.text("Prefix matches", "prefix 일치"), matchingPrefix ? Z8Text.text("Yes", "예") : Z8Text.text("No / Verification failed", "아니오 / 확인 실패"));
        field(report, Z8Text.text("Bootstrap included", "bootstrap 포함"), BuildConfig.Z8_HAS_BOOTSTRAP ? Z8Text.text("Yes", "예") : Z8Text.text("No", "아니오"));
        field(report, "bootstrap SHA-256", knownValue(BuildConfig.Z8_BOOTSTRAP_SHA256));
        field(report, "prefix/bin/bash", bashPresent ? Z8Text.text("File exists (execution not verified)", "파일 존재 (실행 미검증)") : Z8Text.text("File missing", "파일 없음"));
        field(report, "upstream commit", knownValue(BuildConfig.Z8_UPSTREAM_COMMIT));
        field(report, Z8Text.text("Build fingerprint", "빌드 지문"), Build.FINGERPRINT);
        field(report, Z8Text.text("G0 verification", "G0 검증"), Z8Text.text("NOT TESTED — This screen does not run compatibility tests", "NOT TESTED — 이 화면은 호환성 시험을 실행하지 않음"));
        observations.setText(report.toString());
    }

    private boolean prefixMatchesApp() {
        try {
            File configured = new File(TermuxConstants.TERMUX_PREFIX_DIR_PATH);
            if (!TermuxConstants.TERMUX_PACKAGE_NAME.equals(getPackageName())
                || !"usr".equals(configured.getName()) || configured.getParentFile() == null) {
                return false;
            }
            // Android may expose /data/data and /data/user/0 as bind aliases.
            // Canonical path strings need not match. Compare the existing files
            // directories by inode; usr does not exist on a fresh installation.
            android.system.StructStat expected = Os.stat(getFilesDir().getAbsolutePath());
            android.system.StructStat actual = Os.stat(configured.getParentFile().getAbsolutePath());
            return expected.st_dev == actual.st_dev && expected.st_ino == actual.st_ino;
        } catch (Exception exception) {
            return false;
        }
    }

    private void appendMemory(StringBuilder report) {
        ActivityManager manager = (ActivityManager) getSystemService(ACTIVITY_SERVICE);
        if (manager == null) {
            field(report, "RAM", Z8Text.text("Unavailable", "확인 불가"));
            return;
        }
        ActivityManager.MemoryInfo memory = new ActivityManager.MemoryInfo();
        manager.getMemoryInfo(memory);
        field(report, Z8Text.text("Total RAM (reported by Android)", "RAM 총량 (Android 보고)"), gib(memory.totalMem));
        field(report, Z8Text.text("Available RAM", "현재 가용 RAM"), gib(memory.availMem));
        field(report, Z8Text.text("System lowMemory", "시스템 lowMemory"), memory.lowMemory ? Z8Text.text("Yes", "예") : Z8Text.text("No", "아니오"));
    }

    private static String pageSize() {
        try {
            long bytes = Os.sysconf(OsConstants._SC_PAGESIZE);
            return bytes > 0 ? bytes + " bytes" : Z8Text.text("Unavailable", "확인 불가");
        } catch (Exception exception) {
            return Z8Text.text("Unavailable", "확인 불가");
        }
    }

    private static String joinAbis() {
        StringBuilder value = new StringBuilder();
        for (String abi : Build.SUPPORTED_ABIS) {
            if (value.length() != 0) value.append(", ");
            value.append(abi);
        }
        return value.length() == 0 ? Z8Text.text("Unavailable", "확인 불가") : value.toString();
    }

    private void openTerminal(boolean diagnostic) {
        Intent intent = TermuxActivity.z8SessionIntent(this);
        intent.putExtra(EXTRA_DIAGNOSTIC_SHELL, diagnostic);
        startActivity(intent);
    }

    private TextView text(String value, int sizeSp, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sizeSp);
        view.setTextColor(color);
        view.setLineSpacing(dp(3), 1f);
        return view;
    }

    private Button button(String title) {
        Button button = new Button(this);
        button.setText(title);
        button.setTextColor(palette.background);
        button.setBackgroundTintList(ColorStateList.valueOf(palette.accent));
        button.setAllCaps(false);
        button.setMinHeight(dp(48));
        button.setPadding(dp(12), dp(10), dp(12), dp(10));
        return button;
    }

    private void addSpaced(LinearLayout parent, View view, int topDp) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(topDp);
        parent.addView(view, params);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static String gib(long bytes) {
        return String.format(Locale.ROOT, "%.2f GiB", bytes / (1024d * 1024d * 1024d));
    }

    private static String knownValue(String value) {
        return value == null || value.trim().isEmpty() ? Z8Text.text("None", "없음") : value;
    }

    private static void field(StringBuilder target, String label, String value) {
        target.append(label).append("\n").append(value).append("\n\n");
    }
}
