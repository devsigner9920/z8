package com.termux.app;

/** App-owned text only. Never translate commands, identifiers, paths or user content. */
public final class Z8Text {
    private static volatile boolean korean;

    private Z8Text() {}

    public static String language() { return korean ? "ko" : "en"; }

    public static void setLanguage(String language) { korean = "ko".equals(language); }

    public static String text(String english, String koreanTranslation) {
        return korean ? koreanTranslation : english;
    }
}
