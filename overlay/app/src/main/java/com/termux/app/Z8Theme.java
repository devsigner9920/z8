package com.termux.app;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.view.View;
import android.view.Window;
import android.view.WindowInsetsController;

import com.termux.terminal.TerminalColors;
import com.termux.terminal.TerminalEmulator;
import com.termux.terminal.TerminalSession;
import com.termux.terminal.TextStyle;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.WeakHashMap;

/** Built-in z8 colors. This class never writes a user's shell or Termux color files. */
public final class Z8Theme {
    private static final String PREFERENCES = "z8_appearance";
    private static final String THEME_ID = "theme_id";
    private static final String SETUP_COMPLETE = "setup_complete";

    public static final class Palette {
        public final String id;
        public final String name;
        public final String description;
        public final int background;
        public final int foreground;
        public final int secondary;
        public final int accent;
        public final boolean light;
        private final int[] ansi;

        private Palette(String id, String name, String description,
                int background, int foreground, int secondary, int accent,
                boolean light, int[] ansi) {
            this.id = id;
            this.name = name;
            this.description = description;
            this.background = background;
            this.foreground = foreground;
            this.secondary = secondary;
            this.accent = accent;
            this.light = light;
            this.ansi = ansi.clone();
        }

        public int ansi(int index) {
            if (index < 0 || index >= 16) throw new IllegalArgumentException("ANSI color index");
            return ansi[index];
        }
    }

    private static final List<Palette> PALETTES = Collections.unmodifiableList(Arrays.asList(
        new Palette("prism", "Prism", "블루·라일락·코럴이 번지는 스펙트럼",
            0xff11141c, 0xffeef0f7, 0xffabb3c5, 0xffbdceff, false,
            new int[] {
                0xff353e50, 0xfff29aac, 0xffa9deb8, 0xffedc89c,
                0xff98beff, 0xffc3adff, 0xff91d7eb, 0xffdbe1f1,
                0xff8d9cb7, 0xffffb3c1, 0xffcaf0d3, 0xffffdebb,
                0xffc2d8ff, 0xffdfceff, 0xffb4edf9, 0xfff8faff
            }),
        new Palette("midnight", "Midnight", "짙은 남색과 선명한 푸른 포인트",
            0xff101827, 0xffe5edf7, 0xffa5b4c9, 0xff87b9ff, false,
            new int[] {
                0xff303c50, 0xffff7c8e, 0xff91d7a3, 0xffecd287,
                0xff87b9ff, 0xffc7a0ef, 0xff79d3dc, 0xffc8d4e5,
                0xff8294af, 0xffffa5b1, 0xffb6ecc1, 0xffffe5a0,
                0xffaecfff, 0xffdfbfff, 0xffa7edf2, 0xfff4f8ff
            }),
        new Palette("graphite", "Graphite", "차분한 회색과 민트 포인트",
            0xff1b1e22, 0xffebedef, 0xffb0b7c0, 0xff94d8c1, false,
            new int[] {
                0xff3d424a, 0xffee8e91, 0xffa6cf91, 0xffe0c58a,
                0xff95b8e8, 0xffc3a4dd, 0xff8bcbd1, 0xffd7dbe0,
                0xff969faa, 0xffffb0b2, 0xffc6e7b5, 0xffffe3ab,
                0xffbed8ff, 0xffe4caff, 0xffb4eef3, 0xffffffff
            }),
        new Palette("ember", "Ember", "따뜻한 배경과 앰버 포인트",
            0xff251d1a, 0xfff2e7d8, 0xffc5b6a5, 0xffefb56f, false,
            new int[] {
                0xff4a3c35, 0xffee8b7d, 0xffb7ce88, 0xffefc27d,
                0xff91b8d5, 0xffd4a1c7, 0xff8dc8be, 0xffdcccbb,
                0xffaf9b89, 0xffffb0a3, 0xffd3e9ad, 0xffffdda6,
                0xffb9d9f1, 0xfff1c5e6, 0xffb2e4da, 0xfffff6e9
            }),
        new Palette("paper", "Paper", "밝은 종이색과 또렷한 글자",
            0xfff6f4ef, 0xff24314b, 0xff536174, 0xff2759b8, true,
            new int[] {
                0xff263044, 0xffa12735, 0xff2f6e42, 0xff806000,
                0xff245ca6, 0xff7b4096, 0xff176876, 0xff657080,
                0xff5b6474, 0xffb52b3b, 0xff247439, 0xff896300,
                0xff2b63b7, 0xff87409e, 0xff0d707d, 0xff344259
            })
    ));

    // Accessed from terminal activity callbacks on the main thread. Weak keys do
    // not retain completed sessions, and let OSC colors survive ordinary resume.
    private static final Map<TerminalColors, String> APPLIED = new WeakHashMap<>();

    private Z8Theme() {}

    public static List<Palette> palettes() {
        return PALETTES;
    }

    /** A missing or obsolete stored ID has a stable, readable fallback. */
    public static Palette find(String id) {
        for (Palette palette : PALETTES) {
            if (palette.id.equals(id)) return palette;
        }
        return PALETTES.get(0);
    }

    private static SharedPreferences preferences(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE);
    }

    public static Palette selected(Context context) {
        Object value = preferences(context).getAll().get(THEME_ID);
        return find(value instanceof String ? (String) value : null);
    }

    public static boolean isSetupComplete(Context context) {
        return Boolean.TRUE.equals(preferences(context).getAll().get(SETUP_COMPLETE));
    }

    /**
     * Call off the UI thread; navigate only after true. Both selection and setup
     * completion are committed together, so a process restart retains the choice.
     */
    public static synchronized boolean save(Context context, String id) {
        Palette palette = find(id);
        if (!palette.id.equals(id)) return false;
        SharedPreferences prefs = preferences(context);
        Map<String, ?> previous = prefs.getAll();
        boolean success = prefs.edit().putString(THEME_ID, id)
            .putBoolean(SETUP_COMPLETE, true).commit();
        if (!success) {
            // A failed commit can still update the SharedPreferences memory map.
            // Restore the prior state too, so failure is not mistaken for setup.
            SharedPreferences.Editor rollback = prefs.edit();
            Object oldId = previous.get(THEME_ID);
            Object oldComplete = previous.get(SETUP_COMPLETE);
            if (oldId instanceof String) rollback.putString(THEME_ID, (String) oldId);
            else rollback.remove(THEME_ID);
            if (oldComplete instanceof Boolean) rollback.putBoolean(SETUP_COMPLETE, (Boolean) oldComplete);
            else rollback.remove(SETUP_COMPLETE);
            rollback.commit();
        }
        return success;
    }

    /** Apply after Termux reads colors.properties, without editing that file. */
    public static void applyDefaults(Context context) {
        if (!isSetupComplete(context)) return;
        Palette palette = selected(context);
        int[] colors = TerminalColors.COLOR_SCHEME.mDefaultColors;
        for (int index = 0; index < 16; index++) colors[index] = palette.ansi(index);
        colors[TextStyle.COLOR_INDEX_FOREGROUND] = palette.foreground;
        colors[TextStyle.COLOR_INDEX_BACKGROUND] = palette.background;
        colors[TextStyle.COLOR_INDEX_CURSOR] = palette.accent;
    }

    /**
     * Main thread only. Hook resume, session changes, emulator creation and OSC
     * background changes. It redraws colors, without recreating a PTY or session.
     * Return false to retain unconfigured Termux color handling.
     */
    public static boolean applyToTerminal(TermuxActivity activity) {
        if (!isSetupComplete(activity)) return false;
        Palette palette = selected(activity);
        applyDefaults(activity);
        int background = palette.background;
        TerminalSession session = activity.getCurrentSession();
        TerminalEmulator emulator = session == null ? null : session.getEmulator();
        if (emulator != null) {
            if (!palette.id.equals(APPLIED.get(emulator.mColors))) {
                emulator.mColors.reset();
                APPLIED.put(emulator.mColors, palette.id);
                if (activity.getTerminalView() != null) activity.getTerminalView().invalidate();
            }
            // Applications may intentionally change the background with OSC.
            background = emulator.mColors.mCurrentColors[TextStyle.COLOR_INDEX_BACKGROUND];
        }
        applyChrome(activity, background,
            TerminalColors.getPerceivedBrightnessOfColor(background) >= 160);
        return true;
    }

    /** For setup previews and native screens; does not persist a preview. */
    public static void applyChrome(Activity activity, Palette palette) {
        applyChrome(activity, palette.background, palette.light);
    }

    private static void applyChrome(Activity activity, int background, boolean light) {
        Window window = activity.getWindow();
        View decor = window.getDecorView();
        Z8WindowInsets.install(activity);
        decor.setBackgroundColor(background);
        window.setStatusBarColor(background);
        window.setNavigationBarColor(background);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            window.setStatusBarContrastEnforced(false);
            window.setNavigationBarContrastEnforced(false);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowInsetsController controller = window.getInsetsController();
            if (controller != null) {
                int flags = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                    | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                controller.setSystemBarsAppearance(light ? flags : 0, flags);
            }
        } else {
            int flags = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            int visibility = decor.getSystemUiVisibility();
            decor.setSystemUiVisibility(light ? visibility | flags : visibility & ~flags);
        }
    }
}
