package com.termux.app;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.os.Bundle;
import android.os.LocaleList;
import java.util.Locale;
import java.util.Map;
import java.util.WeakHashMap;

/** Explicit app preference: English on first launch, independent of the device language. */
public final class Z8Language {
    private static final String PREFS = "z8.language";
    private static final String KEY = "language";
    private static final Map<Activity, String> CREATED_LANGUAGES = new WeakHashMap<>();

    private Z8Language() {}

    private static String selected(Context context) {
        return "ko".equals(context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, "en")) ? "ko" : "en";
    }

    public static Context wrap(Context context) {
        String language = selected(context);
        Z8Text.setLanguage(language);
        Locale locale = Locale.forLanguageTag(language);
        Locale.setDefault(locale);
        Configuration configuration = new Configuration(context.getResources().getConfiguration());
        configuration.setLocales(new LocaleList(locale));
        return context.createConfigurationContext(configuration);
    }

    public static void initialize(Application application) {
        Z8Text.setLanguage(selected(application));
        application.registerActivityLifecycleCallbacks(new Application.ActivityLifecycleCallbacks() {
            @Override public void onActivityCreated(Activity activity, Bundle state) {
                CREATED_LANGUAGES.put(activity, Z8Text.language());
            }
            @Override public void onActivityResumed(Activity activity) {
                String previous = CREATED_LANGUAGES.get(activity);
                if (previous != null && !previous.equals(Z8Text.language())
                        && !activity.isFinishing() && !activity.isDestroyed()) {
                    CREATED_LANGUAGES.put(activity, Z8Text.language());
                    activity.recreate();
                }
            }
            @Override public void onActivityDestroyed(Activity activity) { CREATED_LANGUAGES.remove(activity); }
            @Override public void onActivityStarted(Activity activity) {}
            @Override public void onActivityPaused(Activity activity) {}
            @Override public void onActivityStopped(Activity activity) {}
            @Override public void onActivitySaveInstanceState(Activity activity, Bundle state) {}
        });
    }

    @SuppressWarnings("deprecation")
    public static boolean select(Context context, String language) {
        if (!"en".equals(language) && !"ko".equals(language)) return false;
        SharedPreferences preferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String previous = selected(context);
        if (!preferences.edit().putString(KEY, language).commit()) {
            // Android updates its in-memory preferences even if the disk write fails.
            // Restore that value too, so a newly wrapped activity keeps the current language.
            preferences.edit().putString(KEY, previous).commit();
            return false;
        }
        Z8Text.setLanguage(language);
        Locale locale = Locale.forLanguageTag(language);
        Locale.setDefault(locale);
        Context application = context.getApplicationContext();
        Configuration configuration = new Configuration(application.getResources().getConfiguration());
        configuration.setLocales(new LocaleList(locale));
        // Update existing service resources; activities receive a fresh wrapped context on recreation.
        application.getResources().updateConfiguration(configuration, application.getResources().getDisplayMetrics());
        return true;
    }
}
