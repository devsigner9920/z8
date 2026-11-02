package com.termux.app;

import android.app.Activity;
import android.app.NotificationManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Bundle;
import android.os.IBinder;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import com.termux.R;

/** The first download always follows visible network disclosure and explicit consent. */
public final class Z8SetupActivity extends Activity implements ServiceConnection {
    private Z8BackNavigation backNavigation;
    private TermuxService service;
    private boolean bound, foreground, navigating, registeringNetwork;
    private String previousNetwork;
    private Z8ChromeStyle style;
    private TextView title, description, networkStatus, progressLabel, notifications;
    private LinearLayout consent, progressArea;
    private ProgressBar progress;
    private CheckBox meteredConsent;
    private Button install, later;
    private ConnectivityManager connectivity;
    private final Runnable stateListener = this::refresh;
    private final ConnectivityManager.NetworkCallback networkListener = new ConnectivityManager.NetworkCallback() {
        @Override public void onAvailable(Network network) { changed(); }
        @Override public void onLost(Network network) { changed(); }
        @Override public void onCapabilitiesChanged(Network network, NetworkCapabilities capabilities) { changed(); }
        private void changed() { runOnUiThread(() -> { if (foreground) refresh(); }); }
    };

    @Override protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        backNavigation = Z8BackNavigation.install(this, this::leaveSetup);
        if (!Z8Theme.isSetupComplete(this)) {
            startActivity(new Intent(this, Z8ThemeActivity.class).putExtra(Z8ThemeActivity.EXTRA_FIRST_SETUP, true));
            finish(); return;
        }
        connectivity = getSystemService(ConnectivityManager.class);
        render();
    }

    @Override protected void onStart() {
        super.onStart();
        if (isFinishing()) return;
        bound = bindService(new Intent(this, TermuxService.class), this, Context.BIND_AUTO_CREATE);
    }

    @Override protected void onResume() {
        super.onResume();
        if (isFinishing()) return;
        foreground = true;
        Z8InitialSetup.addListener(stateListener);
        if (connectivity != null) {
            try { connectivity.registerDefaultNetworkCallback(networkListener); registeringNetwork = true; }
            catch (SecurityException ignored) { /* The offline state remains conservative. */ }
        }
        resumeAcceptedWork();
        refresh();
    }

    @Override protected void onPause() {
        foreground = false;
        Z8InitialSetup.removeListener(stateListener);
        if (registeringNetwork && connectivity != null) {
            connectivity.unregisterNetworkCallback(networkListener); registeringNetwork = false;
        }
        super.onPause();
    }

    @Override protected void onStop() {
        if (bound) { unbindService(this); bound = false; }
        service = null;
        super.onStop();
    }

    @Override public void onServiceConnected(ComponentName name, IBinder binder) {
        service = ((TermuxService.LocalBinder) binder).service;
        // A consent screen alone is not execution and should not retain a foreground card.
        service.updateNotification();
        resumeAcceptedWork();
        refresh();
    }

    @Override public void onServiceDisconnected(ComponentName name) { service = null; refresh(); }

    @Override public void onBackPressed() { leaveSetup(); }

    @Override protected void onDestroy() {
        if (backNavigation != null) backNavigation.close();
        super.onDestroy();
    }

    private void leaveSetup() {
        if (Z8InitialSetup.state(this).phase == Z8InitialSetup.Phase.RUNNING) moveTaskToBack(true);
        else finishAndRemoveTask();
    }

    private void resumeAcceptedWork() {
        if (foreground && service != null && Z8InitialSetup.hasConsent(this)) Z8InitialSetup.resume(service);
    }

    private void render() {
        Z8Theme.Palette palette = Z8Theme.selected(this);
        Z8Theme.applyChrome(this, palette);
        style = Z8ChromeStyle.from(palette);
        setTitle(Z8Text.text("z8 · First setup", "z8 · 처음 준비"));
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true); scroll.setBackgroundColor(style.canvas);
        LinearLayout frame = column(); frame.setGravity(Gravity.CENTER);
        scroll.addView(frame, new ScrollView.LayoutParams(-1, -1));
        LinearLayout content = new LinearLayout(this) {
            @Override protected void onMeasure(int width, int height) {
                super.onMeasure(MeasureSpec.makeMeasureSpec(Math.min(dp(600), MeasureSpec.getSize(width)), MeasureSpec.EXACTLY), height);
            }
        };
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(24), dp(36), dp(24), dp(36));
        frame.addView(content, new LinearLayout.LayoutParams(-1, -2));
        LinearLayout brand = new LinearLayout(this); brand.setGravity(Gravity.CENTER_VERTICAL);
        ImageView icon = new ImageView(this); icon.setImageResource(R.drawable.z8_ic_terminal);
        icon.setImageTintList(ColorStateList.valueOf(style.accent));
        icon.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        brand.addView(icon, new LinearLayout.LayoutParams(dp(25), dp(25)));
        TextView wordmark = text("z8", 25, style.text, true); wordmark.setPadding(dp(10), 0, 0, 0);
        brand.addView(wordmark);
        content.addView(brand);
        title = text("", 27, style.text, true); title.setAccessibilityHeading(true); add(content, title, 30);
        description = text("", 14, style.muted, false); description.setLineSpacing(dp(5), 1); add(content, description, 12);

        consent = column(); consent.setPadding(dp(18), dp(18), dp(18), dp(18));
        consent.setBackground(style.shape(this, style.surface, style.border, 14));
        TextView tools = text("Python · Node.js · Git · GitHub CLI", 14, style.text, true); consent.addView(tools);
        TextView downloads = text(Z8Text.text("Set up Linux and download development tools.\nThis may use hundreds of MB or more.\nWi-Fi is recommended to avoid data charges.", "Linux 환경을 구성하고 개발 도구를 내려받아요.\n수백 MB 이상의 데이터가 사용될 수 있어요.\n데이터 요금이 발생할 수 있으니 Wi-Fi를 권장해요."), 13, style.muted, false);
        downloads.setLineSpacing(dp(4), 1); add(consent, downloads, 10);
        networkStatus = text("", 13, style.text, false); add(consent, networkStatus, 18);
        meteredConsent = new CheckBox(this);
        meteredConsent.setText(Z8Text.text("I agree to use mobile data or a metered network.", "모바일 데이터 또는 유료 네트워크 사용에 동의합니다."));
        meteredConsent.setTextSize(13); meteredConsent.setTextColor(style.text);
        meteredConsent.setButtonTintList(ColorStateList.valueOf(style.accent));
        meteredConsent.setMinHeight(dp(48));
        meteredConsent.setChecked(false);
        meteredConsent.setOnCheckedChangeListener((view, checked) -> updateInstallEnabled());
        add(consent, meteredConsent, 10);
        add(content, consent, 24);

        progressArea = column();
        progressLabel = text("", 13, style.muted, false);
        progressLabel.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        progressArea.addView(progressLabel);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100); progress.setProgressTintList(ColorStateList.valueOf(style.accent));
        progress.setIndeterminateTintList(ColorStateList.valueOf(style.accent));
        LinearLayout.LayoutParams track = new LinearLayout.LayoutParams(-1, dp(4)); track.topMargin = dp(12);
        progressArea.addView(progress, track); add(content, progressArea, 28);

        install = button(Z8Text.text("Start setup", "설치 시작"), true);
        install.setOnClickListener(view -> request()); add(content, install, 28);
        later = button(Z8Text.text("Later", "나중에"), false);
        later.setOnClickListener(view -> leaveSetup());
        add(content, later, 8);
        notifications = text(Z8Text.text("Enable progress notifications", "진행 알림 켜기"), 13, style.accent, false);
        notifications.setGravity(Gravity.CENTER); notifications.setMinimumHeight(dp(48));
        notifications.setFocusable(true); notifications.setOnClickListener(view -> startActivity(new Intent(
            Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName())));
        add(content, notifications, 4);
        setContentView(scroll);
    }

    private void refresh() {
        if (!foreground || isFinishing() || isDestroyed() || install == null) return;
        Z8InitialSetup.State state = Z8InitialSetup.state(this);
        if (state.phase == Z8InitialSetup.Phase.READY) {
            if (!navigating) {
                navigating = true;
                startActivity(new Intent(this, TermuxActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP));
                finish();
            }
            return;
        }
        NetworkState network = network();
        if (!network.key.equals(previousNetwork)) {
            previousNetwork = network.key;
            meteredConsent.setChecked(false);
        }
        boolean running = state.phase == Z8InitialSetup.Phase.RUNNING;
        boolean waiting = state.phase == Z8InitialSetup.Phase.WAITING_NETWORK;
        boolean failed = state.phase == Z8InitialSetup.Phase.FAILED;
        title.setText(running ? Z8Text.text("Preparing your workspace", "작업 공간을 준비하고 있어요") : waiting ? Z8Text.text("Waiting for a connection", "네트워크를 기다리고 있어요")
            : failed ? Z8Text.text("Setup could not finish", "준비를 완료하지 못했어요") : Z8Text.text("Set up development tools", "개발 도구를 준비할게요"));
        description.setText(running ? Z8Text.text("First setup may take a few minutes. It continues while you use other apps.\nIf the app is stopped, reopen it to check completed steps and resume.", "처음 한 번은 몇 분 걸릴 수 있어요. 다른 앱을 사용해도 준비는 계속돼요.\n강제 종료되면 앱을 다시 열 때 완료된 단계부터 확인하고 이어가요.")
            : waiting ? Z8Text.text("Completed steps are saved. Connect to Wi-Fi to continue.", "완료한 단계는 보관했어요. Wi-Fi에 연결하면 이어서 준비할 수 있어요.")
            : failed ? Z8Text.text("Completed steps and project files are preserved. Check your connection and storage, then retry.", "완료한 단계와 프로젝트 파일은 유지돼요. 연결과 저장 공간을 확인하고 다시 시도해 주세요.")
            : Z8Text.text("Prepare the tools needed to create projects.\nInstall them once and reuse them for future projects.", "프로젝트를 만들기 전에 필요한 도구를 준비해요.\n처음 한 번 설치하면 다음 프로젝트부터 재사용해요."));
        consent.setVisibility(running ? View.GONE : View.VISIBLE);
        networkStatus.setText(!network.online ? Z8Text.text("No internet connection. Connect to Wi-Fi.", "인터넷에 연결되지 않았어요. Wi-Fi에 연결해 주세요.")
            : network.metered ? Z8Text.text("You are using mobile data or a metered network.", "현재 모바일 데이터 또는 유료 네트워크에 연결되어 있어요.")
            : Z8Text.text("You are using an unmetered network.", "현재 데이터 사용량 제한이 없는 네트워크에 연결되어 있어요."));
        meteredConsent.setVisibility(network.online && network.metered ? View.VISIBLE : View.GONE);
        progressArea.setVisibility(running || waiting || failed ? View.VISIBLE : View.GONE);
        String message = state.message == null ? "" : state.message;
        // Full installer logs belong in a diagnostic view, not this primary flow.
        int line = message.indexOf('\n'); if (line >= 0) message = message.substring(0, line);
        if (message.length() > 180) message = message.substring(0, 180);
        progressLabel.setText(message + (running && state.percent >= 0 ? " · " + state.percent + "%" : ""));
        progress.setVisibility(running ? View.VISIBLE : View.GONE);
        progress.setIndeterminate(state.percent < 0); if (state.percent >= 0) progress.setProgress(state.percent);
        install.setVisibility(running ? View.GONE : View.VISIBLE);
        install.setText(failed ? Z8Text.text("Retry", "다시 시도") : waiting ? Z8Text.text("Continue on this connection", "이 연결로 계속") : Z8Text.text("Start setup", "설치 시작"));
        later.setText(running ? Z8Text.text("Continue in background", "백그라운드에서 계속") : Z8Text.text("Later", "나중에"));
        NotificationManager manager = getSystemService(NotificationManager.class);
        notifications.setVisibility(manager != null && !manager.areNotificationsEnabled() ? View.VISIBLE : View.GONE);
        updateInstallEnabled();
    }

    private void request() {
        if (!foreground || service == null || service.wantsToStop()) return;
        NetworkState network = network();
        if (!network.key.equals(previousNetwork)) { refresh(); return; }
        if (!network.online || network.metered && !meteredConsent.isChecked()) return;
        Z8InitialSetup.request(service, network.metered && meteredConsent.isChecked());
        refresh();
    }

    private void updateInstallEnabled() {
        if (install == null) return;
        NetworkState network = network();
        boolean enabled = foreground && service != null && !service.wantsToStop()
            && network.online && (!network.metered || meteredConsent.isChecked());
        install.setEnabled(enabled); install.setAlpha(enabled ? 1f : .45f);
    }

    private NetworkState network() {
        try {
            Network network = connectivity == null ? null : connectivity.getActiveNetwork();
            NetworkCapabilities capabilities = network == null ? null : connectivity.getNetworkCapabilities(network);
            boolean online = capabilities != null && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
            boolean metered = capabilities == null
                || !capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
                || capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR);
            return new NetworkState(online, metered, String.valueOf(network) + ":" + online + ":" + metered);
        } catch (SecurityException unavailable) { return new NetworkState(false, true, "unavailable"); }
    }

    private static final class NetworkState {
        final boolean online, metered; final String key;
        NetworkState(boolean online, boolean metered, String key) { this.online = online; this.metered = metered; this.key = key; }
    }

    private LinearLayout column() { LinearLayout view = new LinearLayout(this); view.setOrientation(LinearLayout.VERTICAL); return view; }
    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setTypeface(Typeface.create(bold ? "sans-serif-medium" : "sans-serif", Typeface.NORMAL));
        view.setIncludeFontPadding(false); return view;
    }
    private Button button(String value, boolean primary) {
        Button button = new Button(this); button.setAllCaps(false); button.setText(value); button.setTextSize(15);
        button.setTextColor(primary ? style.canvas : style.muted); button.setBackgroundTintList(null);
        button.setBackground(style.interactive(this, primary ? style.text : Color.TRANSPARENT, Color.TRANSPARENT, 10));
        button.setMinHeight(dp(50)); button.setPadding(dp(16), dp(10), dp(16), dp(10)); return button;
    }
    private void add(LinearLayout parent, View view, int top) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2); params.topMargin = dp(top); parent.addView(view, params);
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
