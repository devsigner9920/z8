package com.termux.app;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.LayerDrawable;
import android.graphics.drawable.RippleDrawable;
import android.graphics.drawable.StateListDrawable;

/** Native navigation colors and feedback. Does not change terminal colors or preferences. */
public final class Z8ChromeStyle {
    public final boolean prism;
    public final int canvas;
    public final int panel;
    public final int surface;
    public final int raised;
    public final int border;
    public final int text;
    public final int muted;
    public final int faint;
    public final int accent;
    public final int selected;
    public final int danger;

    private Z8ChromeStyle(Z8Theme.Palette palette) {
        prism = "prism".equals(palette.id);
        accent = prism ? 0xffbdd2ff : palette.accent;
        if (prism) {
            canvas = 0xff101218;
            panel = 0xff12151f;
            surface = 0xff171b26;
            raised = 0xff202635;
            border = 0xff303a51;
            text = 0xffeef0f7;
            muted = 0xffabb3c5;
            faint = 0xff8f9cae;
            danger = 0xffef9a9a;
        } else if (palette.light) {
            canvas = 0xfff4f6f8;
            panel = 0xfffbfcfd;
            surface = 0xffffffff;
            raised = 0xffeef1f5;
            border = 0xffdde2e8;
            text = 0xff26313e;
            muted = 0xff596878;
            faint = 0xff596574;
            danger = 0xffb83d4c;
        } else {
            canvas = 0xff121519;
            panel = 0xff15191d;
            surface = 0xff1a1f25;
            raised = 0xff232a32;
            border = 0xff303842;
            text = 0xffe6eaf0;
            muted = 0xff9ca6b2;
            faint = 0xff8c98a6;
            danger = 0xffef9a9a;
        }
        selected = prism ? 0xff242c43 : blend(panel, accent, .12f);
    }

    public static Z8ChromeStyle from(Z8Theme.Palette palette) {
        if (palette == null) throw new IllegalArgumentException("A terminal palette is required");
        return new Z8ChromeStyle(palette);
    }

    /** Creates a fresh drawable; callers may safely use different states on each view. */
    public GradientDrawable shape(Context context, int fill, int stroke, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(dp(context, Math.max(0, radiusDp)));
        if (Color.alpha(stroke) != 0) drawable.setStroke(Math.max(1, dp(context, 1)), stroke);
        return drawable;
    }

    /** Rounded ripple with an explicit keyboard-focus outline. Focus ownership is set by the view. */
    public Drawable interactive(Context context, int fill, int stroke, int radiusDp) {
        StateListDrawable content = new StateListDrawable();
        content.addState(new int[]{android.R.attr.state_focused}, shape(context, fill, accent, radiusDp));
        content.addState(new int[0], shape(context, fill, stroke, radiusDp));
        GradientDrawable mask = shape(context, Color.WHITE, Color.TRANSPARENT, radiusDp);
        int ripple = Color.argb(Math.round(255 * .18f), Color.red(accent), Color.green(accent), Color.blue(accent));
        return new RippleDrawable(ColorStateList.valueOf(ripple), content, mask);
    }

    /** Quiet navigation surface: opaque backing with 8% of the supplied image. */
    public Drawable ambient(Context context) {
        if (!prism) return shape(context, surface, Color.TRANSPARENT, 0);
        return imagePlate(context, surface, .08f, Color.TRANSPARENT, 0);
    }

    /** Full supplied image for a decorative brand mark or thin selection underline. */
    public Drawable spectrum(Context context, int radiusDp) {
        if (!prism) return shape(context, accent, Color.TRANSPARENT, radiusDp);
        return new Z8SpectrumDrawable(context, radiusDp);
    }

    /** A quiet selected row. The darker panel backing keeps secondary text legible. */
    public Drawable selectedSurface(Context context, int radiusDp) {
        if (!prism) return interactive(context, selected, Color.TRANSPARENT, radiusDp);
        StateListDrawable content = new StateListDrawable();
        content.addState(new int[]{android.R.attr.state_focused},
            imagePlate(context, panel, .12f, accent, radiusDp));
        content.addState(new int[0], imagePlate(context, panel, .12f, Color.TRANSPARENT, radiusDp));
        return imageFeedback(context, content, radiusDp, false);
    }

    /** Full-image icon plate. Use dark canvas-colored icon ink, not body text. */
    public Drawable primaryAction(Context context, int radiusDp) {
        if (!prism) return interactive(context, selected, border, radiusDp);
        StateListDrawable content = new StateListDrawable();
        content.addState(new int[]{android.R.attr.state_focused},
            imagePlate(context, surface, 1f, accent, radiusDp));
        content.addState(new int[0], imagePlate(context, surface, 1f, 0x70ffffff, radiusDp));
        return imageFeedback(context, content, radiusDp, true);
    }

    private Drawable imagePlate(Context context, int backing, float opacity, int stroke, int radiusDp) {
        Drawable image = new Z8SpectrumDrawable(context, radiusDp);
        image.setAlpha(Math.round(255 * opacity));
        return new LayerDrawable(new Drawable[]{
            shape(context, backing, Color.TRANSPARENT, radiusDp),
            image,
            shape(context, Color.TRANSPARENT, stroke, radiusDp)
        });
    }

    private Drawable imageFeedback(Context context, Drawable content, int radiusDp, boolean brightPlate) {
        // Only Android's bounded press/release ripple animates. The very light
        // blue overlay on selected rows preserves faint text contrast.
        int ripple = brightPlate ? 0x2effffff : Color.argb(4, Color.red(accent), Color.green(accent), Color.blue(accent));
        return new RippleDrawable(ColorStateList.valueOf(ripple), content,
            shape(context, Color.WHITE, Color.TRANSPARENT, radiusDp));
    }

    private static int dp(Context context, int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    private static int blend(int base, int over, float amount) {
        return Color.rgb(Math.round(Color.red(base) * (1 - amount) + Color.red(over) * amount),
            Math.round(Color.green(base) * (1 - amount) + Color.green(over) * amount),
            Math.round(Color.blue(base) * (1 - amount) + Color.blue(over) * amount));
    }
}
