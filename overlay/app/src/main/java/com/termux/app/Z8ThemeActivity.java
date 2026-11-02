package com.termux.app;

import android.app.Activity;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;
import android.view.Gravity;
import android.view.View;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.termux.R;

import java.util.LinkedHashMap;
import java.util.Map;

/** Preview first; changing a swatch never saves preferences or replaces a live PTY. */
public final class Z8ThemeActivity extends Activity {
    public static final String EXTRA_FIRST_SETUP = "dev.devsigner.z8.FIRST_THEME_SETUP";
    private String selectedId;
    private boolean firstSetup;
    private boolean saving;
    private Z8BackNavigation backNavigation;
    private boolean wide;
    private ScrollView scroll;
    private LinearLayout preview;
    private Button apply;
    private View back;
    private final Map<String, View> choices = new LinkedHashMap<>();
    private final Map<String, ImageView> checks = new LinkedHashMap<>();
    private Z8ChromeStyle chrome;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        backNavigation = Z8BackNavigation.install(this, () -> { if (!saving) finish(); });
        firstSetup = getIntent().getBooleanExtra(EXTRA_FIRST_SETUP, false)
            || !Z8Theme.isSetupComplete(this);
        selectedId = state == null ? Z8Theme.selected(this).id : state.getString("selectedTheme");
        selectedId = Z8Theme.find(selectedId).id;
        setTitle(firstSetup ? "z8 · 시작 테마" : "z8 · 테마 설정");
        render();
        if (state != null && state.getBoolean("saveInProgress", false)) save();
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        state.putString("selectedTheme", selectedId);
        state.putBoolean("saveInProgress", saving);
        super.onSaveInstanceState(state);
    }

    @Override public void onBackPressed() {
        if (!saving) super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if (backNavigation != null) backNavigation.close();
        super.onDestroy();
    }

    private void render() {
        // A stable frame makes even the light palette easy to compare, without
        // flashing the whole screen or rebuilding the focused selection control.
        Z8Theme.Palette frame = Z8Theme.find("prism");
        chrome = Z8ChromeStyle.from(frame);
        Z8Theme.applyChrome(this, frame);
        int available = getResources().getConfiguration().screenWidthDp;
        float fontScale = getResources().getConfiguration().fontScale;
        wide = available >= 700 && fontScale <= 1.3f;
        int width = available > 1040 ? dp(1040) : -1;
        LinearLayout root = column();
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setBackgroundColor(chrome.canvas);

        LinearLayout bar = row();
        bar.setPadding(dp(16), dp(4), dp(16), dp(4));
        if (!firstSetup) {
            ImageView close = icon(R.drawable.z8_ic_chevron_right, chrome.text);
            close.setRotation(180);
            close.setPadding(dp(14), dp(14), dp(14), dp(14));
            close.setBackground(chrome.interactive(this, Color.TRANSPARENT, Color.TRANSPARENT, 12));
            close.setContentDescription("테마 설정 닫기");
            close.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
            close.setFocusable(true);
            close.setOnClickListener(view -> { if (!saving) finish(); });
            back = close;
            bar.addView(close, new LinearLayout.LayoutParams(dp(48), dp(48)));
        }
        TextView brand = text(firstSetup ? "z8" : "테마", firstSetup ? 25 : 16, chrome.text, true);
        brand.setPadding(dp(8), 0, 0, 0);
        bar.addView(brand, new LinearLayout.LayoutParams(0, -2, 1));
        if (firstSetup) bar.addView(text("처음 설정", 12, chrome.muted, false));
        root.addView(bar, new LinearLayout.LayoutParams(width, dp(56)));

        scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setVerticalScrollBarEnabled(false);
        root.addView(scroll, new LinearLayout.LayoutParams(width, 0, 1));
        LinearLayout content = column();
        content.setPadding(dp(24), dp(wide ? 22 : 12), dp(24), dp(wide ? 24 : 16));
        scroll.addView(content);
        TextView heading = text(firstSetup ? "어떤 색으로 시작할까요?" : "작업 공간의 테마", wide ? 27 : 24, chrome.text, true);
        heading.setAccessibilityHeading(true);
        content.addView(heading);
        add(content, text("테마를 눌러 터미널의 색을 미리 확인하세요.", 13, chrome.muted, false), 8);

        LinearLayout body = wide ? row() : column();
        body.setGravity(Gravity.TOP);
        preview = column();
        if (wide) body.addView(preview, new LinearLayout.LayoutParams(0, -2, 1));
        else body.addView(preview, new LinearLayout.LayoutParams(-1, -2));
        LinearLayout options = column();
        LinearLayout.LayoutParams optionsParams = new LinearLayout.LayoutParams(wide ? dp(264) : -1, -2);
        if (wide) optionsParams.leftMargin = dp(28);
        else optionsParams.topMargin = dp(16);
        body.addView(options, optionsParams);
        TextView label = text("테마 선택", 12, chrome.muted, true);
        label.setAccessibilityHeading(true);
        options.addView(label);
        choices.clear(); checks.clear();
        int columns = !wide && available >= 360 && fontScale <= 1.3f ? 2 : 1;
        java.util.List<Z8Theme.Palette> palettes = Z8Theme.palettes();
        for (int i = 0; i < palettes.size(); i += columns) {
            LinearLayout line = row();
            for (int j = 0; j < columns; j++) {
                LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -2, 1);
                if (j > 0) params.leftMargin = dp(8);
                if (i + j < palettes.size()) line.addView(choice(palettes.get(i + j)), params);
                else line.addView(new View(this), params);
            }
            add(options, line, 8);
        }
        add(content, body, wide ? 24 : 16);

        LinearLayout footer = column();
        View divider = new View(this); divider.setBackgroundColor(chrome.border);
        footer.addView(divider, new LinearLayout.LayoutParams(-1, dp(1)));
        LinearLayout actions = row();
        actions.setPadding(dp(24), dp(14), dp(24), dp(18));
        if (wide) actions.addView(text("나중에도 언제든 바꿀 수 있어요.", 12, chrome.muted, false),
            new LinearLayout.LayoutParams(0, -2, 1));
        apply = new Button(this);
        apply.setAllCaps(false); apply.setTextSize(15);
        apply.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        apply.setTextColor(chrome.canvas);
        apply.setBackgroundTintList(null);
        apply.setBackground(chrome.interactive(this, chrome.text, Color.TRANSPARENT, 12));
        apply.setMinHeight(dp(50));
        apply.setPadding(dp(20), dp(12), dp(20), dp(12));
        apply.setOnClickListener(view -> save());
        actions.addView(apply, new LinearLayout.LayoutParams(wide ? dp(216) : -1, -2));
        footer.addView(actions);
        root.addView(footer, new LinearLayout.LayoutParams(width, -2));
        setContentView(root);
        updateSelection();
    }

    private View choice(Z8Theme.Palette palette) {
        LinearLayout option = row();
        option.setPadding(dp(12), dp(12), dp(12), dp(12));
        option.setMinimumHeight(dp(64));
        option.setFocusable(true);
        option.setContentDescription(palette.name + ", " + palette.description);
        option.setAccessibilityDelegate(new View.AccessibilityDelegate() {
            @Override public void onInitializeAccessibilityNodeInfo(View host, AccessibilityNodeInfo info) {
                super.onInitializeAccessibilityNodeInfo(host, info);
                info.setClassName(RadioButton.class.getName());
                info.setCheckable(true);
                info.setChecked(palette.id.equals(selectedId));
            }
        });
        LinearLayout copy = column();
        copy.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        TextView name = text(palette.name, 14, chrome.text, true);
        copy.addView(name);
        LinearLayout colors = row();
        for (int index : new int[]{4, 5, 1, 2, 3}) {
            View swatch = new View(this);
            swatch.setBackground(chrome.shape(this, palette.ansi(index), Color.TRANSPARENT, 4));
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(14), dp(4));
            params.rightMargin = dp(4);
            colors.addView(swatch, params);
        }
        add(copy, colors, 8);
        option.addView(copy, new LinearLayout.LayoutParams(0, -2, 1));
        ImageView check = icon(R.drawable.z8_ic_check, chrome.accent);
        option.addView(check, new LinearLayout.LayoutParams(dp(18), dp(18)));
        checks.put(palette.id, check); choices.put(palette.id, option);
        option.setOnClickListener(view -> {
            if (saving || selectedId.equals(palette.id)) return;
            selectedId = palette.id;
            updateSelection();
        });
        return option;
    }

    private void updateSelection() {
        for (Map.Entry<String, View> entry : choices.entrySet()) {
            boolean selected = entry.getKey().equals(selectedId);
            entry.getValue().setSelected(selected);
            entry.getValue().setBackground(selected
                ? chrome.selectedSurface(this, 12)
                : chrome.interactive(this, chrome.surface, Color.TRANSPARENT, 12));
            checks.get(entry.getKey()).setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
        }
        renderPreview();
        setSavingState();
    }

    private void renderPreview() {
        preview.removeAllViews();
        Z8Theme.Palette palette = Z8Theme.find(selectedId);
        Z8ChromeStyle style = Z8ChromeStyle.from(palette);
        LinearLayout window = column();
        window.setBackground(style.shape(this, palette.background, style.border, 16));
        window.setClipToOutline(true);
        window.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
        window.setContentDescription(palette.name + " 터미널 미리보기. " + palette.description + ". 샘플 출력입니다.");
        LinearLayout navigation = row();
        navigation.setPadding(dp(16), dp(12), dp(16), dp(12));
        navigation.setBackground(style.ambient(this));
        navigation.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        navigation.addView(icon(R.drawable.z8_ic_terminal, style.muted), new LinearLayout.LayoutParams(dp(17), dp(17)));
        TextView project = text("my-project", 13, style.text, true);
        project.setPadding(dp(10), 0, 0, 0);
        navigation.addView(project, new LinearLayout.LayoutParams(0, -2, 1));
        navigation.addView(text("미리보기", 10, style.muted, false));
        window.addView(navigation);
        LinearLayout tabs = column();
        tabs.setPadding(dp(16), dp(8), dp(16), 0);
        tabs.setBackgroundColor(style.surface);
        tabs.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        tabs.addView(text("Terminal 1", 11, style.text, true));
        View underline = new View(this);
        underline.setBackground(style.spectrum(this, 1));
        LinearLayout.LayoutParams underlineParams = new LinearLayout.LayoutParams(dp(38), dp(2));
        underlineParams.topMargin = dp(8);
        tabs.addView(underline, underlineParams);
        window.addView(tabs);
        LinearLayout output = column();
        output.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
        output.setPadding(dp(18), dp(wide ? 20 : 14), dp(18), dp(wide ? 22 : 14));
        String sample = "/z8/home  main\n$ ll\nsrc/  README.md\n\n$ git status\nworking tree clean";
        SpannableString colored = new SpannableString(sample);
        color(colored, 0, "/z8/home".length(), palette.accent);
        color(colored, sample.indexOf("main"), sample.indexOf('\n'), palette.secondary);
        color(colored, sample.indexOf("src/"), sample.indexOf("src/") + 4, palette.ansi(4));
        color(colored, sample.indexOf("working tree clean"), sample.length(), palette.ansi(2));
        TextView terminal = text("", wide ? 14 : 12, palette.foreground, false);
        terminal.setTypeface(Typeface.MONOSPACE); terminal.setLineSpacing(dp(wide ? 5 : 3), 1);
        terminal.setText(colored);
        output.addView(terminal);
        window.addView(output);
        preview.addView(window, new LinearLayout.LayoutParams(-1, -2));
        LinearLayout caption = row();
        TextView name = text(palette.name, 14, chrome.text, true);
        caption.addView(name, new LinearLayout.LayoutParams(0, -2, 1));
        caption.addView(text(palette.light ? "라이트" : "다크", 11, chrome.muted, false));
        add(preview, caption, wide ? 14 : 10);
        add(preview, text(palette.description, 12, chrome.muted, false), 5);
    }

    private void setSavingState() {
        for (View option : choices.values()) option.setEnabled(!saving);
        if (back != null) back.setEnabled(!saving);
        apply.setEnabled(!saving);
        apply.setAlpha(saving ? .6f : 1f);
        apply.setText(saving ? "저장 중…" : firstSetup ? "이 테마로 시작" : "테마 적용");
    }

    private void save() {
        if (saving) return;
        saving = true;
        String choice = selectedId;
        setSavingState();
        new Thread(() -> {
            boolean saved = Z8Theme.save(getApplicationContext(), choice);
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed() || isChangingConfigurations()) return;
                saving = false;
                if (!saved) {
                    Toast.makeText(this, "테마를 저장하지 못했습니다. 다시 시도해 주세요.", Toast.LENGTH_LONG).show();
                    setSavingState();
                    return;
                }
                if (firstSetup) startActivity(new Intent(this, Z8SetupActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP));
                finish();
            });
        }, "z8-theme-save").start();
    }

    private LinearLayout column() {
        LinearLayout view = new LinearLayout(this); view.setOrientation(LinearLayout.VERTICAL); return view;
    }
    private LinearLayout row() {
        LinearLayout view = new LinearLayout(this); view.setGravity(Gravity.CENTER_VERTICAL); return view;
    }
    private TextView text(String value, int sizeSp, int color, boolean medium) {
        TextView view = new TextView(this);
        view.setText(value); view.setTextSize(sizeSp); view.setTextColor(color);
        view.setTypeface(Typeface.create(medium ? "sans-serif-medium" : "sans-serif", Typeface.NORMAL));
        view.setIncludeFontPadding(false); view.setLineSpacing(dp(2), 1);
        return view;
    }
    private ImageView icon(int resource, int tint) {
        ImageView view = new ImageView(this);
        view.setImageResource(resource); view.setImageTintList(ColorStateList.valueOf(tint));
        view.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        return view;
    }
    private void add(LinearLayout parent, View view, int marginTop) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.topMargin = dp(marginTop); parent.addView(view, params);
    }
    private void color(SpannableString text, int start, int end, int value) {
        text.setSpan(new ForegroundColorSpan(value), start, end, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
