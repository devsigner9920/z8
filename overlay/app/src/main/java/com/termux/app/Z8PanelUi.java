package com.termux.app;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import com.termux.R;

/** Shared restrained native layout for the settings and notification destinations. */
final class Z8PanelUi {
    final Activity activity;
    final Z8Theme.Palette palette;
    final Z8ChromeStyle style;
    final ScrollView scroll;
    final LinearLayout content, toolbar;

    Z8PanelUi(Activity activity, String title) {
        this.activity = activity;
        palette = Z8Theme.selected(activity); style = Z8ChromeStyle.from(palette);
        Z8Theme.applyChrome(activity, palette);
        scroll = new ScrollView(activity); scroll.setFillViewport(true); scroll.setBackgroundColor(style.canvas);
        LinearLayout frame = column(); frame.setGravity(Gravity.TOP | Gravity.CENTER_HORIZONTAL);
        scroll.addView(frame, new ScrollView.LayoutParams(-1, -2));
        content = new LinearLayout(activity) {
            @Override protected void onMeasure(int width, int height) {
                super.onMeasure(MeasureSpec.makeMeasureSpec(Math.min(dp(680), MeasureSpec.getSize(width)), MeasureSpec.EXACTLY), height);
            }
        };
        content.setOrientation(LinearLayout.VERTICAL); content.setPadding(dp(20), dp(12), dp(20), dp(32));
        frame.addView(content, new LinearLayout.LayoutParams(-1, -2));
        toolbar = row(); toolbar.setGravity(Gravity.CENTER_VERTICAL);
        ImageView back = icon(R.drawable.z8_ic_chevron_right, 22, style.text); back.setRotation(180);
        back.setPadding(dp(13), dp(13), dp(13), dp(13));
        back.setContentDescription("돌아가기"); back.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);
        control(back); back.setOnClickListener(view -> activity.finish());
        toolbar.addView(back, new LinearLayout.LayoutParams(dp(48), dp(48)));
        TextView heading = text(title, 21, style.text, true); heading.setPadding(dp(4), 0, 0, 0);
        heading.setAccessibilityHeading(true);
        toolbar.addView(heading, new LinearLayout.LayoutParams(0, -2, 1));
        content.addView(toolbar, new LinearLayout.LayoutParams(-1, dp(56)));
        activity.setContentView(scroll); activity.setTitle(title);
    }

    LinearLayout row() { LinearLayout result = new LinearLayout(activity); result.setOrientation(LinearLayout.HORIZONTAL); return result; }
    LinearLayout column() { LinearLayout result = new LinearLayout(activity); result.setOrientation(LinearLayout.VERTICAL); return result; }
    TextView text(String value, int size, int color, boolean medium) {
        TextView result = new TextView(activity); result.setText(value); result.setTextSize(size); result.setTextColor(color);
        result.setTypeface(Typeface.create(medium ? "sans-serif-medium" : "sans-serif", Typeface.NORMAL));
        result.setIncludeFontPadding(false); return result;
    }
    ImageView icon(int drawable, int size, int color) {
        ImageView result = new ImageView(activity); result.setImageResource(drawable); result.setColorFilter(color);
        result.setScaleType(ImageView.ScaleType.FIT_CENTER); result.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        result.setLayoutParams(new LinearLayout.LayoutParams(dp(size), dp(size))); return result;
    }
    void control(View view) {
        view.setClickable(true); view.setFocusable(true); view.setFocusableInTouchMode(false);
        view.setDefaultFocusHighlightEnabled(false);
        view.setBackground(style.interactive(activity, Color.TRANSPARENT, Color.TRANSPARENT, 8));
    }
    TextView section(String label) {
        TextView heading = text(label, 12, style.muted, true); heading.setAccessibilityHeading(true);
        heading.setPadding(dp(8), dp(28), dp(8), dp(8)); content.addView(heading); return heading;
    }
    LinearLayout setting(String title, String detail, Runnable action) {
        LinearLayout row = row(); row.setGravity(Gravity.CENTER_VERTICAL); row.setMinimumHeight(dp(64));
        row.setPadding(dp(8), dp(12), dp(8), dp(12));
        LinearLayout copy = column(); copy.addView(text(title, 15, style.text, false));
        if (detail != null && !detail.isEmpty()) {
            TextView secondary = text(detail, 12, style.muted, false); secondary.setPadding(0, dp(6), dp(8), 0); copy.addView(secondary);
        }
        row.addView(copy, new LinearLayout.LayoutParams(0, -2, 1));
        if (action != null) {
            row.addView(icon(R.drawable.z8_ic_chevron_right, 18, style.muted));
            control(row); row.setOnClickListener(view -> action.run());
        }
        content.addView(row, new LinearLayout.LayoutParams(-1, -2)); return row;
    }
    void rule(LinearLayout parent) {
        View rule = new View(activity); rule.setBackgroundColor(style.border);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, Math.max(1, dp(1))); params.topMargin = dp(16);
        parent.addView(rule, params);
    }
    int dp(int value) { return Math.round(value * activity.getResources().getDisplayMetrics().density); }
}
