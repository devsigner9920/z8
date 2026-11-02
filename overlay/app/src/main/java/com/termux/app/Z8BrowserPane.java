package com.termux.app;

import android.content.ActivityNotFoundException;
import android.content.res.ColorStateList;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;
import android.net.Uri;
import android.os.Build;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.webkit.CookieManager;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import androidx.browser.customtabs.CustomTabColorSchemeParams;
import androidx.browser.customtabs.CustomTabsClient;
import androidx.browser.customtabs.CustomTabsIntent;
import com.termux.R;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Set;
import java.util.WeakHashMap;

/** One local preview renderer; external sites use a browser-owned Custom Tab over z8. */
public final class Z8BrowserPane extends LinearLayout {
    // Reserved for browser dismissal only; never inspect or log a returned Intent.
    public static final int REQUEST_EXTERNAL_BROWSER = 0x5A38;
    private static final Set<Z8BrowserPane> panes = Collections.newSetFromMap(new WeakHashMap<Z8BrowserPane, Boolean>());
    private final TermuxActivity activity;
    private final Runnable close, returnToTerminal, onExternalOpened;
    private final EditText address;
    private final ProgressBar progress;
    private final TextView message, openExternal;
    private final LinearLayout placeholder;
    private final ImageView back, reload;
    private Z8ChromeStyle style;
    private WebView web;
    private String externalUrl, previewUrl;
    private boolean active, foreground, timersPaused;
    private boolean dataDeletionNotice;

    public Z8BrowserPane(TermuxActivity activity, Runnable close, Runnable returnToTerminal,
                         Runnable onExternalOpened) {
        super(activity); this.activity = activity; this.close = close; this.returnToTerminal = returnToTerminal;
        this.onExternalOpened = onExternalOpened;
        setOrientation(VERTICAL);
        style = Z8ChromeStyle.from(Z8Theme.selected(activity));
        LinearLayout toolbar = new LinearLayout(activity); toolbar.setGravity(Gravity.CENTER_VERTICAL);
        back = icon(R.drawable.z8_ic_chevron_right, Z8Text.text("Browser back", "브라우저 뒤로"), () -> { if (web != null && web.canGoBack()) web.goBack(); });
        back.setRotation(180); toolbar.addView(back, new LayoutParams(dp(48), dp(48)));
        address = new EditText(activity); address.setSingleLine(true); address.setTextSize(13);
        address.setHint("localhost:3000"); address.setContentDescription(Z8Text.text("Browser address", "브라우저 주소"));
        address.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        address.setImeOptions(EditorInfo.IME_ACTION_GO); address.setSelectAllOnFocus(true);
        address.setSaveEnabled(false); // OAuth URLs must not enter saved instance state.
        address.setOnEditorActionListener((view, action, event) -> {
            if (event != null && event.getKeyCode() == android.view.KeyEvent.KEYCODE_ENTER) {
                if (event.getAction() == android.view.KeyEvent.ACTION_DOWN && event.getRepeatCount() == 0)
                    navigate(address.getText().toString());
                return true;
            }
            if (event == null && action == EditorInfo.IME_ACTION_GO) { navigate(address.getText().toString()); return true; }
            return false;
        });
        toolbar.addView(address, new LayoutParams(0, dp(48), 1));
        reload = icon(R.drawable.z8_ic_reload, Z8Text.text("Refresh page", "페이지 새로고침"), () -> { if (web != null) web.reload(); });
        toolbar.addView(reload, new LayoutParams(dp(48), dp(48)));
        toolbar.addView(icon(R.drawable.z8_ic_open_browser, Z8Text.text("Open in browser", "브라우저 창에서 열기"), () -> {
            String target = externalUrl != null ? externalUrl : previewUrl;
            if (target != null) launchExternal(target);
            else navigate(address.getText().toString());
        }), new LayoutParams(dp(48), dp(48)));
        toolbar.addView(icon(R.drawable.z8_ic_close, Z8Text.text("Close browser tab", "브라우저 탭 닫기"), close), new LayoutParams(dp(48), dp(48)));
        addView(toolbar, new LayoutParams(-1, dp(48)));
        progress = new ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100); progress.setVisibility(INVISIBLE); addView(progress, new LayoutParams(-1, dp(2)));
        placeholder = new LinearLayout(activity); placeholder.setOrientation(VERTICAL); placeholder.setGravity(Gravity.CENTER);
        placeholder.setPadding(dp(24), dp(24), dp(24), dp(24));
        message = new TextView(activity); message.setTextSize(14); message.setGravity(Gravity.CENTER); message.setLineSpacing(dp(6), 1);
        message.setAccessibilityLiveRegion(ACCESSIBILITY_LIVE_REGION_POLITE); placeholder.addView(message);
        openExternal = link(Z8Text.text("Reopen browser", "브라우저 창 다시 열기"), () -> { if (externalUrl != null) launchExternal(externalUrl); });
        placeholder.addView(openExternal, new LayoutParams(-1, dp(48)));
        placeholder.addView(link(Z8Text.text("Back to terminal", "터미널로 돌아가기"), returnToTerminal), new LayoutParams(-1, dp(48)));
        addView(placeholder, new LayoutParams(-1, 0, 1));
        showMessage(Z8Text.text("Preview your development server here.\nEnter a localhost address to open it in this tab.\nSign-in and external sites open in your browser.", "개발 서버를 여기서 확인하세요.\nlocalhost 주소를 입력하면 이 탭에서 열립니다.\n로그인과 외부 사이트는 브라우저 창에서 이어집니다."));
        applyTheme();
        panes.add(this);
    }

    public void applyTheme() {
        style = Z8ChromeStyle.from(Z8Theme.selected(activity));
        setBackgroundColor(style.canvas); address.setTextColor(style.text); address.setHintTextColor(style.muted);
        address.setBackgroundTintList(ColorStateList.valueOf(style.border)); message.setTextColor(style.muted);
        progress.setProgressTintList(ColorStateList.valueOf(style.accent));
        tint(this);
    }

    private void tint(android.view.ViewGroup parent) {
        for (int i = 0; i < parent.getChildCount(); i++) {
            View child = parent.getChildAt(i);
            if (child instanceof ImageView) ((ImageView) child).setImageTintList(ColorStateList.valueOf(style.muted));
            else if (child instanceof TextView && child != address && child != message) ((TextView) child).setTextColor(style.accent);
            if (child.isClickable() && child != address) child.setBackground(style.interactive(activity, Color.TRANSPARENT, Color.TRANSPARENT, 6));
            if (child instanceof android.view.ViewGroup && !(child instanceof WebView)) tint((android.view.ViewGroup) child);
        }
    }

    public void navigate(String raw) {
        if (Z8BrowserUrls.isBlank(raw)) { showBlank(); return; }
        String url = Z8BrowserUrls.normalize(raw);
        if (url == null) { address.setError(Z8Text.text("Enter an http or https address", "http 또는 https 주소를 입력해 주세요")); return; }
        address.clearFocus();
        InputMethodManager keyboard = (InputMethodManager) activity.getSystemService(android.content.Context.INPUT_METHOD_SERVICE);
        if (keyboard != null) keyboard.hideSoftInputFromWindow(address.getWindowToken(), 0);
        if (!Z8BrowserUrls.isPreview(url)) { showExternal(url, true); return; }
        if (Z8BrowserData.running()) {
            externalUrl = null; previewUrl = null; address.setText("");
            dataDeletionNotice = true;
            showMessage(Z8Text.text("Clearing preview data.\nReopen the address when it finishes.", "미리보기 데이터를 삭제하고 있어요.\n완료 후 주소를 다시 열어 주세요."));
            return;
        }
        dataDeletionNotice = false;
        externalUrl = null; previewUrl = url; address.setText(url);
        if (!ensureWeb()) return;
        placeholder.setVisibility(GONE); web.setVisibility(VISIBLE); web.loadUrl(url); updateLifecycle();
    }

    /** Returns whether an external Activity opened, so returning to z8 keeps a blank tab visible. */
    public boolean showRequest(String url) {
        switch (Z8BrowserUrls.requestTarget(url)) {
            case BLANK: showBlank(); return false;
            case PREVIEW: navigate(url); return false;
            case EXTERNAL: return showExternal(url, true);
            default: return false;
        }
    }

    private void showBlank() {
        dataDeletionNotice = false;
        externalUrl = null; previewUrl = null;
        destroyWeb(); address.setText(""); address.setError(null);
        showMessage(Z8Text.text("Preview your development server here.\nEnter a localhost address to open it in this tab.\nSign-in and external sites open in your browser.", "개발 서버를 여기서 확인하세요.\nlocalhost 주소를 입력하면 이 탭에서 열립니다.\n로그인과 외부 사이트는 브라우저 창에서 이어집니다."));
        focusAddress();
    }

    /** Only a verified live CLI request or an explicit address submission calls this. */
    public boolean showExternal(String url, boolean launch) {
        externalUrl = Z8BrowserUrls.normalize(url);
        if (externalUrl == null) return false;
        dataDeletionNotice = false;
        destroyWeb(); previewUrl = null;
        // Keep the full single-use URL only in memory, never in an editable field or a label.
        address.setText(Z8BrowserUrls.host(externalUrl));
        showMessage(Z8BrowserUrls.host(externalUrl) + Z8Text.text("\nContinue in the browser window.\nWhen finished, close it with × to return to your terminal.", "\n브라우저 창에서 계속하세요.\n완료 후 창의 ×를 누르면 원래 터미널로 돌아옵니다."));
        return launch && launchExternal(externalUrl);
    }

    private boolean launchExternal(String url) {
        String validated = Z8BrowserUrls.normalize(url);
        if (validated == null) return false;
        try {
            Z8Theme.Palette palette = Z8Theme.selected(activity);
            Z8ChromeStyle browserStyle = Z8ChromeStyle.from(palette);
            CustomTabsIntent.Builder builder = new CustomTabsIntent.Builder()
                .setShowTitle(true)
                .setUrlBarHidingEnabled(false)
                .setCloseButtonPosition(CustomTabsIntent.CLOSE_BUTTON_POSITION_START)
                .setColorScheme(palette.light ? CustomTabsIntent.COLOR_SCHEME_LIGHT : CustomTabsIntent.COLOR_SCHEME_DARK)
                .setDefaultColorSchemeParams(new CustomTabColorSchemeParams.Builder()
                    .setToolbarColor(browserStyle.panel)
                    .setNavigationBarColor(browserStyle.canvas)
                    .setNavigationBarDividerColor(browserStyle.border).build())
                .setShareState(CustomTabsIntent.SHARE_STATE_OFF)
                .setBookmarksButtonEnabled(false)
                .setDownloadButtonEnabled(false)
                .setInstantAppsEnabled(false)
                .setBackgroundInteractionEnabled(false)
                .setToolbarCornerRadiusDp(16);
            Drawable closeIcon = activity.getDrawable(R.drawable.z8_ic_close);
            if (closeIcon != null) {
                Bitmap bitmap = Bitmap.createBitmap(dp(24), dp(24), Bitmap.Config.ARGB_8888);
                closeIcon = closeIcon.mutate(); closeIcon.setTint(browserStyle.text);
                closeIcon.setBounds(0, 0, bitmap.getWidth(), bitmap.getHeight());
                closeIcon.draw(new Canvas(bitmap)); builder.setCloseButtonIcon(bitmap);
            }
            // Use the current app window, including split-screen/fold changes, not
            // the physical display. Unsupported browsers ignore these size hints.
            int width = Math.max(1, Math.round(getResources().getConfiguration().screenWidthDp
                * getResources().getDisplayMetrics().density));
            int height = Math.max(1, Math.round(getResources().getConfiguration().screenHeightDp
                * getResources().getDisplayMetrics().density));
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                Rect bounds = activity.getWindowManager().getCurrentWindowMetrics().getBounds();
                width = bounds.width(); height = bounds.height();
            }
            builder.setInitialActivityHeightPx(Math.max(1, Math.round(height * .9f)),
                    CustomTabsIntent.ACTIVITY_HEIGHT_ADJUSTABLE)
                .setInitialActivityWidthPx(Math.max(1, Math.min(width, Math.min(dp(640),
                    Math.max(dp(420), Math.round(width * .62f))))))
                .setActivitySideSheetBreakpointDp(600)
                .setActivitySideSheetPosition(CustomTabsIntent.ACTIVITY_SIDE_SHEET_POSITION_END)
                .setActivitySideSheetDecorationType(CustomTabsIntent.ACTIVITY_SIDE_SHEET_DECORATION_TYPE_DIVIDER)
                .setActivitySideSheetMaximizationEnabled(true);
            CustomTabsIntent tab = builder.build();
            String provider = CustomTabsClient.getPackageName(activity, null);
            if (provider != null) tab.intent.setPackage(provider);
            tab.intent.setData(Uri.parse(validated));
            // A result launch keeps this browser window above the originating z8
            // task and enables partial tabs without a bound browser service. Do
            // not add NEW_TASK or copy authentication data into an app WebView.
            activity.startActivityForResult(tab.intent, REQUEST_EXTERNAL_BROWSER, tab.startAnimationBundle);
            onExternalOpened.run();
            return true;
        } catch (ActivityNotFoundException missing) {
            showMessage(Z8Text.text("No browser is installed.\nInstall a browser such as Chrome, then try again.", "기기에 설치된 브라우저가 없어요.\nChrome 등 브라우저를 설치한 뒤 다시 열어 주세요."));
        } catch (SecurityException blocked) {
            showMessage(Z8Text.text("Could not open the browser.\nSelect Reopen browser to try again.", "브라우저 창을 열지 못했어요.\n브라우저 창 다시 열기를 눌러 주세요."));
        }
        return false;
    }

    private boolean ensureWeb() {
        if (Z8BrowserData.running()) return false;
        if (web != null) return true;
        try { web = new WebView(activity); }
        catch (RuntimeException unavailable) { showMessage(Z8Text.text("Android System WebView is unavailable.\nOpen the development server in your device's browser.", "Android System WebView를 사용할 수 없어요.\n기기 브라우저에서 개발 서버를 열어 주세요.")); externalUrl = previewUrl; openExternal.setVisibility(VISIBLE); return false; }
        web.setSaveEnabled(false);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true); settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false); settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false); settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setJavaScriptCanOpenWindowsAutomatically(false); settings.setSupportMultipleWindows(false);
        settings.setMediaPlaybackRequiresUserGesture(true); settings.setSafeBrowsingEnabled(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int value) {
                if (view != web) return;
                progress.setProgress(value); progress.setVisibility(value < 100 ? VISIBLE : INVISIBLE);
            }
        });
        web.setWebViewClient(new WebViewClient() {
            @Override public android.webkit.WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                // POST navigations do not pass through shouldOverrideUrlLoading.
                if (request.isForMainFrame() && !Z8BrowserUrls.isPreview(request.getUrl().toString())) {
                    String url = request.getUrl().toString();
                    post(() -> { if (web == view) showExternal(url, false); });
                    return new android.webkit.WebResourceResponse("text/plain", "UTF-8", 403,
                        "External navigation", java.util.Collections.emptyMap(), new java.io.ByteArrayInputStream(new byte[0]));
                }
                return null;
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (Z8BrowserUrls.isPreview(url)) return false;
                if (request.isForMainFrame() && Z8BrowserUrls.normalize(url) != null) {
                    // Destroying a WebView from its own callback is unsafe; defer the transition.
                    boolean gesture = request.hasGesture();
                    post(() -> { if (web == view) showExternal(url, gesture); });
                }
                return true;
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (view != web) return;
                if (Z8BrowserUrls.isPreview(url)) { previewUrl = url; address.setText(url); }
                back.setEnabled(view.canGoBack()); reload.setEnabled(true);
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (view == web && request.isForMainFrame()) {
                    showMessage(Z8Text.text("Could not connect to the development server.\nStart the server in your terminal, then refresh.", "개발 서버에 연결할 수 없어요.\n터미널에서 서버를 실행한 뒤 새로고침해 주세요."));
                    progress.setVisibility(INVISIBLE);
                }
            }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                if (view != web) return;
                if (!Z8BrowserUrls.isPreview(url)) {
                    view.stopLoading();
                    post(() -> { if (web == view) showExternal(url, false); });
                    return;
                }
                placeholder.setVisibility(GONE); view.setVisibility(VISIBLE);
            }
            @Override public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                if (view == web) { destroyWeb(); showMessage(Z8Text.text("The preview stopped.\nReopen the address. Your terminal is still running.", "미리보기가 중단됐어요.\n주소를 다시 열어 주세요. 터미널은 계속 실행 중입니다.")); }
                return true;
            }
        });
        addView(web, new LayoutParams(-1, 0, 1));
        return true;
    }

    private void showMessage(String value) {
        message.setText(value); placeholder.setVisibility(VISIBLE);
        openExternal.setVisibility(externalUrl == null ? GONE : VISIBLE);
        if (web != null) web.setVisibility(GONE);
        progress.setVisibility(INVISIBLE); back.setEnabled(web != null && web.canGoBack()); reload.setEnabled(web != null);
    }

    public void setActive(boolean value) { active = value; updateLifecycle(); }
    public void focusAddress() { address.requestFocus(); address.selectAll(); }
    public void reload() { if (web != null) web.reload(); else if (previewUrl != null) navigate(previewUrl); }
    public void setForeground(boolean value) { foreground = value; updateLifecycle(); }
    private void updateLifecycle() {
        if (web == null) return;
        boolean pause = !active || !foreground;
        if (pause == timersPaused) return;
        timersPaused = pause;
        // There is exactly one preview WebView. Timers are process-wide, so this
        // policy must be revisited before adding parallel browser renderers.
        if (pause) { web.onPause(); web.pauseTimers(); }
        else { web.resumeTimers(); web.onResume(); }
    }
    public boolean goBack() { if (web != null && web.canGoBack()) { web.goBack(); return true; } return false; }
    public void dispose() { panes.remove(this); externalUrl = null; previewUrl = null; destroyWeb(); }
    static void stopPreviewsForDataDeletion() {
        for (Z8BrowserPane pane : new ArrayList<>(panes)) {
            if (pane.web == null && pane.previewUrl == null) continue;
            pane.destroyWeb(); pane.previewUrl = null; pane.externalUrl = null;
            pane.address.setText(""); pane.dataDeletionNotice = true;
            pane.showMessage(Z8Text.text("Clearing preview data.\nYour terminal and development server keep running.", "미리보기 데이터를 삭제하고 있어요.\n터미널과 개발 서버는 계속 실행됩니다."));
        }
    }
    static void finishPreviewDataDeletion(boolean completed) {
        for (Z8BrowserPane pane : new ArrayList<>(panes)) {
            if (!pane.dataDeletionNotice) continue;
            pane.dataDeletionNotice = false;
            pane.showMessage(completed ? Z8Text.text("Preview data cleared.\nEnter a localhost address to open a new preview.", "미리보기 데이터를 삭제했습니다.\nlocalhost 주소를 입력하면 새로 열립니다.")
                : Z8Text.text("Could not confirm that data was cleared.\nYou can try again in Settings.", "데이터 삭제 완료를 확인하지 못했습니다.\n설정에서 다시 시도할 수 있어요."));
        }
    }
    private void destroyWeb() {
        if (web == null) return;
        WebView old = web; web = null; old.stopLoading(); old.onPause();
        if (timersPaused) old.resumeTimers();
        timersPaused = false; removeView(old); old.destroy();
    }
    private ImageView icon(int resource, String description, Runnable action) {
        ImageView view = new ImageView(activity); view.setImageResource(resource); view.setPadding(dp(14), dp(14), dp(14), dp(14));
        view.setContentDescription(description); view.setTooltipText(description); view.setFocusable(true); view.setOnClickListener(v -> action.run());
        return view;
    }
    private TextView link(String label, Runnable action) {
        TextView view = new TextView(activity); view.setText(label); view.setTextSize(13); view.setGravity(Gravity.CENTER);
        view.setFocusable(true); view.setOnClickListener(v -> action.run()); return view;
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
