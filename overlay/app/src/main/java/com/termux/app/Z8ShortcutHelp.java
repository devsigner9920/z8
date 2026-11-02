package com.termux.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.PopupWindow;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.WeakHashMap;

/** A held-key hint never takes terminal focus or sends text to the terminal. */
public final class Z8ShortcutHelp {
    private static final WeakHashMap<Activity, State> STATES = new WeakHashMap<>();
    private Z8ShortcutHelp() {}

    /** Call before Activity's normal key dispatch. Only the help chord is consumed. */
    public static boolean dispatch(Activity activity, KeyEvent event) {
        if (activity.isFinishing() || activity.isDestroyed()) { dismiss(activity); return false; }
        State state = STATES.get(activity);
        if (state == null) { state = new State(); STATES.put(activity, state); }
        int change = state.policy.accept(event);
        if ((change & HoldPolicy.HIDE) != 0) hide(state);
        if ((change & HoldPolicy.SHOW) != 0) showHeld(activity, state);
        return (change & HoldPolicy.CONSUME) != 0;
    }

    /** Call on pause and window-focus loss; a repeated key cannot reopen the hint. */
    public static void dismiss(Activity activity) {
        State state = STATES.remove(activity);
        if (state != null) hide(state);
    }

    /** Persistent, accessible alternative for touch users and system-reserved Meta keys. */
    public static void show(Activity activity) {
        if (activity.isFinishing() || activity.isDestroyed()) return;
        dismiss(activity);
        Z8Theme.Palette palette = Z8Theme.selected(activity);
        Z8ChromeStyle style = Z8ChromeStyle.from(palette);
        AlertDialog dialog = new AlertDialog.Builder(activity, palette.light
            ? android.R.style.Theme_Material_Light_Dialog_Alert : android.R.style.Theme_Material_Dialog_Alert)
            .setView(content(activity, style, false)).setPositiveButton("확인", null).create();
        dialog.show();
        if (dialog.getWindow() != null) {
            dialog.getWindow().setBackgroundDrawable(style.shape(activity, style.surface, style.border, 16));
            dialog.getWindow().setLayout(panelWidth(activity), ViewGroup.LayoutParams.WRAP_CONTENT);
            dialog.getWindow().setDimAmount(.36f);
        }
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setTextColor(style.accent);
    }

    private static void showHeld(Activity activity, State state) {
        View anchor = activity.getWindow().getDecorView();
        if (!anchor.isAttachedToWindow() || !anchor.hasWindowFocus()) return;
        Z8ChromeStyle style = Z8ChromeStyle.from(Z8Theme.selected(activity));
        ScrollView content = content(activity, style, true);
        Rect visible = new Rect(); anchor.getWindowVisibleDisplayFrame(visible);
        int width = panelWidth(activity);
        content.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(Math.max(dp(activity, 120), visible.height() - dp(activity, 112)), View.MeasureSpec.AT_MOST));
        PopupWindow popup = new PopupWindow(content, width, content.getMeasuredHeight(), false);
        popup.setTouchable(false);
        popup.setFocusable(false);
        popup.setOutsideTouchable(false);
        popup.setInputMethodMode(PopupWindow.INPUT_METHOD_NOT_NEEDED);
        popup.setBackgroundDrawable(style.shape(activity, style.surface, style.border, 16));
        popup.setElevation(dp(activity, 12));
        state.popup = popup;
        popup.showAtLocation(anchor, Gravity.TOP | Gravity.END, dp(activity, 16), dp(activity, 88));
    }

    private static void hide(State state) {
        PopupWindow popup = state.popup; state.popup = null;
        if (popup != null) popup.dismiss();
    }

    private static ScrollView content(Activity activity, Z8ChromeStyle style, boolean held) {
        ScrollView scroll = new ScrollView(activity);
        LinearLayout column = new LinearLayout(activity); column.setOrientation(LinearLayout.VERTICAL);
        column.setPadding(dp(activity, 20), dp(activity, 20), dp(activity, 20), dp(activity, 20));
        scroll.addView(column, new ScrollView.LayoutParams(-1, -2));
        TextView title = text(activity, "단축키", 17, style.text, true); title.setAccessibilityHeading(true); column.addView(title);
        TextView hint = text(activity, held ? "키를 놓으면 닫혀요" : "터미널과 브라우저에서 사용할 수 있어요", 12, style.muted, false);
        hint.setPadding(0, dp(activity, 6), 0, dp(activity, 12)); column.addView(hint);
        row(activity, column, style, "복사 / 붙여넣기", "Ctrl + Shift + C / V");
        row(activity, column, style, "텍스트 선택", "드래그 · 길게 누르기");
        row(activity, column, style, "명령 중단", "Ctrl + C");
        row(activity, column, style, "새 터미널", "Ctrl + Shift + T");
        row(activity, column, style, "다음 탭", "Ctrl + Tab");
        row(activity, column, style, "이전 탭", "Ctrl + Shift + Tab");
        row(activity, column, style, "브라우저 열기", "Ctrl + Shift + B");
        row(activity, column, style, "브라우저 주소", "Ctrl + L");
        row(activity, column, style, "브라우저 새로고침", "Ctrl + R");
        row(activity, column, style, "브라우저에서 복귀", "Esc");
        row(activity, column, style, "누르는 동안 안내", "Ctrl + Shift + /");
        if (!held) {
            TextView note = text(activity, "텍스트를 선택한 뒤 복사하세요. 터치에서는 길게 눌러 Copy / Paste를 선택하세요.\n\n"
                + "Ctrl + L / R와 Esc는 브라우저 탭에서만 동작해요. 터미널의 기존 키 동작은 그대로 사용할 수 있어요.\n\n"
                + "⌘C / ⌘V / ⌘H와 새 터미널의 ⌘T는 기기가 앱에 키를 전달하는 경우 지원합니다. 일부 Android 기기는 시스템 단축키로 사용합니다.",
                12, style.muted, false);
            note.setPadding(0, dp(activity, 16), 0, 0); note.setLineSpacing(dp(activity, 3), 1); column.addView(note);
        }
        return scroll;
    }

    private static void row(Activity activity, LinearLayout column, Z8ChromeStyle style, String label, String keys) {
        LinearLayout row = new LinearLayout(activity); row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL); row.setPadding(0, dp(activity, 10), 0, dp(activity, 10));
        TextView description = text(activity, label, 12, style.muted, false);
        description.setPadding(0, 0, dp(activity, 8), 0);
        row.addView(description, new LinearLayout.LayoutParams(0, -2, 1));
        TextView shortcut = text(activity, keys, 12, style.text, true); shortcut.setGravity(Gravity.END);
        row.addView(shortcut, new LinearLayout.LayoutParams(-2, -2)); column.addView(row);
    }

    private static TextView text(Activity activity, String value, int size, int color, boolean medium) {
        TextView text = new TextView(activity); text.setText(value); text.setTextSize(size); text.setTextColor(color);
        text.setTypeface(Typeface.create(medium ? "sans-serif-medium" : "sans-serif", Typeface.NORMAL));
        text.setIncludeFontPadding(false); return text;
    }
    private static int panelWidth(Activity activity) {
        return dp(activity, Math.max(200, Math.min(360, activity.getResources().getConfiguration().screenWidthDp - 32)));
    }
    private static int dp(Activity activity, int value) {
        return Math.round(value * activity.getResources().getDisplayMetrics().density);
    }
    private static final class State { final HoldPolicy policy = new HoldPolicy(); PopupWindow popup; }

    /** Event-only policy kept separate from popup rendering for host regression coverage. */
    static final class HoldPolicy {
        static final int SHOW = 1, HIDE = 2, CONSUME = 4;
        private int trigger = -1, device = -1;
        private boolean visible;

        int accept(KeyEvent event) {
            int key = event.getKeyCode(), action = event.getAction();
            if (action != KeyEvent.ACTION_DOWN && action != KeyEvent.ACTION_UP) return 0;
            if (trigger != -1) {
                if (event.getDeviceId() != device) return 0;
                if (event.isCanceled()) {
                    if (key == trigger) {
                        trigger = device = -1; visible = false; return HIDE | CONSUME;
                    }
                    if (visible && (isRequiredModifier(key, trigger) || !modifiersMatch(event, trigger))) {
                        visible = false; return HIDE;
                    }
                    return 0;
                }
                if (key == trigger) {
                    if (action == KeyEvent.ACTION_UP) { trigger = device = -1; visible = false; return HIDE | CONSUME; }
                    if (visible && !modifiersMatch(event, trigger)) { visible = false; return HIDE | CONSUME; }
                    return CONSUME; // Repeat must not recreate a dismissed popup or reach the PTY.
                }
                if (visible && (!modifiersMatch(event, trigger)
                    || (action == KeyEvent.ACTION_UP && isRequiredModifier(key, trigger)))) {
                    visible = false; return HIDE;
                }
                return 0;
            }
            if (action != KeyEvent.ACTION_DOWN || event.getRepeatCount() != 0 || event.isCanceled()) return 0;
            if (!modifiersMatch(event, key)) return 0;
            trigger = key; device = event.getDeviceId(); visible = true;
            return SHOW | CONSUME;
        }

        private static boolean modifiersMatch(KeyEvent event, int key) {
            if (event.isAltPressed()) return false;
            if (key == KeyEvent.KEYCODE_H) return event.isMetaPressed() && !event.isCtrlPressed() && !event.isShiftPressed();
            if (key == KeyEvent.KEYCODE_SLASH) return event.isCtrlPressed() && event.isShiftPressed() && !event.isMetaPressed();
            return false;
        }
        private static boolean isRequiredModifier(int key, int trigger) {
            if (trigger == KeyEvent.KEYCODE_H) return key == KeyEvent.KEYCODE_META_LEFT || key == KeyEvent.KEYCODE_META_RIGHT;
            return key == KeyEvent.KEYCODE_CTRL_LEFT || key == KeyEvent.KEYCODE_CTRL_RIGHT
                || key == KeyEvent.KEYCODE_SHIFT_LEFT || key == KeyEvent.KEYCODE_SHIFT_RIGHT;
        }
    }
}
