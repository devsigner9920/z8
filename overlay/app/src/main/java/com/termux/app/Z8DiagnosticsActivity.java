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
        setTitle("z8 · 실행 진단");

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BACKGROUND);

        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(24), dp(28), dp(24), dp(28));
        scroll.addView(content, new ScrollView.LayoutParams(
            ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));

        TextView title = text("z8 실행 진단", 28, FOREGROUND);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        content.addView(title);
        content.addView(text("이 기기의 실행 환경을 확인합니다.", 16, SECONDARY));

        Button themeButton = button("테마 설정 · " + palette.name);
        themeButton.setOnClickListener(view -> startActivity(new Intent(this, Z8ThemeActivity.class)));
        addSpaced(content, themeButton, 18);

        Button workspaceButton = button("프로젝트와 세션");
        workspaceButton.setOnClickListener(view -> startActivity(new Intent(this, TermuxActivity.class)
            .putExtra(Z8WorkspaceActivity.EXTRA_SHOW_SESSIONS, true)));
        addSpaced(content, workspaceButton, 10);
        Button attentionButton = button("응답 확인 / 훅 알림");
        attentionButton.setOnClickListener(view -> startActivity(new Intent(this, Z8AttentionActivity.class)));
        addSpaced(content, attentionButton, 10);

        runtimeStatus = text("", 20, FOREGROUND);
        runtimeStatus.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        addSpaced(content, runtimeStatus, 28);
        runtimeExplanation = text("", 15, SECONDARY);
        addSpaced(content, runtimeExplanation, 10);

        Button resumeButton = button("터미널 열기 / 이어가기");
        // Navigation reconnects to the current session without creating a shell.
        resumeButton.setOnClickListener(view ->
            startActivity(new Intent(this, TermuxActivity.class)));
        addSpaced(content, resumeButton, 24);

        Button diagnosticButton = button("새 Android 진단 셸 만들기");
        diagnosticButton.setOnClickListener(view -> openTerminal(true));
        addSpaced(content, diagnosticButton, 10);
        addSpaced(content, text(
            "/system/bin/sh를 Termux 터미널과 서비스로 실행합니다. "
                + "PRoot Linux 환경이나 Claude·Codex가 설치되는 것은 아닙니다.",
            14, SECONDARY), 6);

        linuxButton = button("Linux 런타임 설치 / 터미널 열기");
        linuxButton.setOnClickListener(view -> {
            // Recheck at the action boundary instead of trusting the last rendered state.
            if (BuildConfig.Z8_HAS_BOOTSTRAP && prefixMatchesApp()) {
                openTerminal(false);
            } else {
                refreshObservations();
                Toast.makeText(this, "이 APK에서는 Linux 런타임 설치를 시작할 수 없습니다.",
                    Toast.LENGTH_LONG).show();
            }
        });
        addSpaced(content, linuxButton, 18);

        TextView detailsTitle = text("기기 및 런타임 정보", 20, FOREGROUND);
        detailsTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        addSpaced(content, detailsTitle, 28);
        observations = text("", 14, FOREGROUND);
        observations.setTypeface(Typeface.MONOSPACE);
        observations.setTextIsSelectable(true);
        addSpaced(content, observations, 12);

        Button refresh = button("정보 새로고침");
        refresh.setOnClickListener(view -> refreshObservations());
        addSpaced(content, refresh, 18);
        addSpaced(content, text(
            "파일 존재와 APK 빌드 정보만으로 실행 호환성을 판정하지 않습니다. "
                + "셸·tmux·PRoot·AI CLI의 실제 작업과 백그라운드 유지 시험은 별도로 필요합니다.",
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
            runtimeStatus.setText("Android 진단 셸 / 런타임 경로 불일치");
            runtimeExplanation.setText(
                "빌드된 런타임 경로와 현재 앱의 내부 경로가 다릅니다. "
                    + "Linux 설치를 중지하고 앱 ID와 bootstrap 빌드 설정을 확인해야 합니다.");
        } else if (!BuildConfig.Z8_HAS_BOOTSTRAP) {
            runtimeStatus.setText(bashPresent
                ? "Android 진단 셸 / 기존 런타임 파일 감지"
                : "Android 진단 셸 / Linux 런타임 미설치");
            runtimeExplanation.setText(
                "이 진단 APK에는 z8 전용 경로로 빌드한 bootstrap이 포함되어 있지 않습니다. "
                    + "Linux 설치·실행에는 해당 bootstrap을 포함한 런타임 APK가 필요합니다. "
                    + (bashPresent ? "기존 bash 파일은 발견했지만 이 화면에서 실행하지 않습니다." : ""));
        } else if (!bashPresent) {
            runtimeStatus.setText("Android 진단 셸 / Linux 런타임 설치 전");
            runtimeExplanation.setText(
                "이 APK에는 bootstrap이 포함되어 있습니다. 아래 버튼으로 설치를 시작할 수 있습니다. "
                    + "bootstrap 설치는 Termux 실행 기반을 준비하는 단계이며, "
                    + "PRoot 배포판과 AI CLI의 설치·검증은 별도입니다.");
        } else {
            runtimeStatus.setText("Linux 런타임 파일 감지 / 실행 검증 필요");
            runtimeExplanation.setText(
                "prefix/bin/bash 파일이 존재합니다. 파일 존재는 설치 완료 또는 G0 통과의 증거가 아닙니다. "
                    + "터미널에서 실제 실행과 PRoot·AI CLI 동작을 확인해야 합니다.");
        }

        linuxButton.setEnabled(canInstall);
        linuxButton.setAlpha(canInstall ? 1f : 0.4f);
        linuxButton.setText(bashPresent ? "Linux 런타임 터미널 열기" : "Linux 런타임 설치 / 터미널 열기");

        StringBuilder report = new StringBuilder();
        field(report, "제조사", Build.MANUFACTURER);
        field(report, "모델", Build.MODEL);
        field(report, "기기 코드", Build.DEVICE);
        field(report, "Android", Build.VERSION.RELEASE);
        field(report, "SDK / target SDK", Build.VERSION.SDK_INT + " / "
            + getApplicationInfo().targetSdkVersion);
        field(report, "지원 ABI", joinAbis());
        field(report, "앱 프로세스", Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
            ? (android.os.Process.is64Bit() ? "64-bit" : "32-bit") : "확인 불가");
        appendMemory(report);
        field(report, "메모리 페이지 크기", pageSize());
        field(report, "앱 ID", getPackageName());
        field(report, "실제 files 경로", getFilesDir().getAbsolutePath());
        field(report, "빌드된 prefix", TermuxConstants.TERMUX_PREFIX_DIR_PATH);
        field(report, "prefix 일치", matchingPrefix ? "예" : "아니오 / 확인 실패");
        field(report, "bootstrap 포함", BuildConfig.Z8_HAS_BOOTSTRAP ? "예" : "아니오");
        field(report, "bootstrap SHA-256", knownValue(BuildConfig.Z8_BOOTSTRAP_SHA256));
        field(report, "prefix/bin/bash", bashPresent ? "파일 존재 (실행 미검증)" : "파일 없음");
        field(report, "upstream commit", knownValue(BuildConfig.Z8_UPSTREAM_COMMIT));
        field(report, "빌드 지문", Build.FINGERPRINT);
        field(report, "G0 검증", "NOT TESTED — 이 화면은 호환성 시험을 실행하지 않음");
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
            field(report, "RAM", "확인 불가");
            return;
        }
        ActivityManager.MemoryInfo memory = new ActivityManager.MemoryInfo();
        manager.getMemoryInfo(memory);
        field(report, "RAM 총량 (Android 보고)", gib(memory.totalMem));
        field(report, "현재 가용 RAM", gib(memory.availMem));
        field(report, "시스템 lowMemory", memory.lowMemory ? "예" : "아니오");
    }

    private static String pageSize() {
        try {
            long bytes = Os.sysconf(OsConstants._SC_PAGESIZE);
            return bytes > 0 ? bytes + " bytes" : "확인 불가";
        } catch (Exception exception) {
            return "확인 불가";
        }
    }

    private static String joinAbis() {
        StringBuilder value = new StringBuilder();
        for (String abi : Build.SUPPORTED_ABIS) {
            if (value.length() != 0) value.append(", ");
            value.append(abi);
        }
        return value.length() == 0 ? "확인 불가" : value.toString();
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
        return value == null || value.trim().isEmpty() ? "없음" : value;
    }

    private static void field(StringBuilder target, String label, String value) {
        target.append(label).append("\n").append(value).append("\n\n");
    }
}
