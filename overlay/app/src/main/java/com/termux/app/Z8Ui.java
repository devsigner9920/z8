package com.termux.app;

import android.app.AlertDialog;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

/** Shared native controls: quiet surfaces, readable dialogs, bounded press feedback. */
public final class Z8Ui {
    private Z8Ui() {}
    public static Button button(Context context, Z8Theme.Palette palette, String text, Runnable action) {
        Z8ChromeStyle style = Z8ChromeStyle.from(palette);
        Button view = new Button(context);
        view.setText(text); view.setAllCaps(false); view.setTextSize(14);
        view.setTextColor(new ColorStateList(new int[][] {new int[]{-android.R.attr.state_enabled}, new int[0]},
            new int[]{style.faint, style.text}));
        view.setBackgroundTintList(null); view.setMinimumWidth(0); view.setMinWidth(0);
        view.setMinHeight(dp(context, 48)); view.setMinimumHeight(dp(context, 48));
        view.setPadding(dp(context, 12), dp(context, 8), dp(context, 12), dp(context, 8));
        view.setBackground(style.interactive(context, style.surface, style.border, 12));
        view.setOnClickListener(ignored -> action.run());
        return view;
    }
    public static Button primary(Context context, Z8Theme.Palette palette, String text, Runnable action) {
        Button view = button(context, palette, text, action);
        view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        view.setBackground(Z8ChromeStyle.from(palette).selectedSurface(context, 12));
        return view;
    }
    public static Button quiet(Context context, Z8Theme.Palette palette, String text, Runnable action) {
        Button view = button(context, palette, text, action);
        view.setBackground(Z8ChromeStyle.from(palette).interactive(context, Color.TRANSPARENT, Color.TRANSPARENT, 10));
        return view;
    }
    public static AlertDialog.Builder dialog(Context context) {
        boolean light = Z8Theme.selected(context).light;
        return new AlertDialog.Builder(context, light ? android.R.style.Theme_Material_Light_Dialog_Alert
                : android.R.style.Theme_Material_Dialog_Alert) {
            @Override public AlertDialog show() {
                AlertDialog dialog = super.show(); finish(dialog); return dialog;
            }
        };
    }
    /** Call after show() when a dialog uses create()/custom onShow validation. */
    public static void finish(AlertDialog dialog) {
        Z8ChromeStyle style = Z8ChromeStyle.from(Z8Theme.selected(dialog.getContext()));
        if (dialog.getWindow() != null) {
            dialog.getWindow().setBackgroundDrawable(style.shape(dialog.getContext(), style.panel, style.border, 22));
            tint(dialog.getWindow().getDecorView(), style);
        }
        for (int id : new int[]{AlertDialog.BUTTON_POSITIVE, AlertDialog.BUTTON_NEGATIVE, AlertDialog.BUTTON_NEUTRAL}) {
            Button view = dialog.getButton(id);
            if (view != null) {
                view.setTextColor(style.accent); view.setAllCaps(false);
                view.setMinHeight(dp(dialog.getContext(), 48));
            }
        }
    }
    private static void tint(View view, Z8ChromeStyle style) {
        if (view instanceof TextView) ((TextView)view).setTextColor(style.text);
        if (view instanceof EditText) {
            ((EditText)view).setHintTextColor(style.muted);
            view.setBackgroundTintList(ColorStateList.valueOf(style.accent));
        }
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup)view;
            for (int i = 0; i < group.getChildCount(); i++) tint(group.getChildAt(i), style);
        }
    }
    private static int dp(Context context, int value) { return Math.round(value * context.getResources().getDisplayMetrics().density); }
}
