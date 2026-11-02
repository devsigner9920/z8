"""Exercise the real language helpers with Android lifecycle/storage boundaries.

Only these small Android contracts are modeled, not the app's UI call sites.
The preferences fixture updates memory before attempting durable storage, as
Android SharedPreferencesImpl.commit() does, including when it returns false.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-language-test-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        sources = []
        for name, source in STUBS.items():
            path = cls.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding='utf-8')
            sources.append(str(path))
        probe = cls.directory / 'LanguageProbe.java'
        probe.write_text(PROBE, encoding='utf-8')
        actual = ROOT / 'overlay/app/src/main/java/com/termux/app'
        sources += [str(actual / 'Z8Text.java'), str(actual / 'Z8Language.java'), str(probe)]
        result = subprocess.run(
            [javac, '-encoding', 'UTF-8', '-d', str(cls.directory), *sources],
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, case, storage=None):
        storage = storage or self.directory / ('preferences-' + case)
        result = subprocess.run(
            [self.java, '-cp', str(self.directory), 'com.termux.app.LanguageProbe', case, str(storage)],
            capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS language ' + case)

    def test_first_launch_is_english_even_on_a_korean_device(self):
        self.probe('first-launch')

    def test_saved_korean_survives_an_actual_fresh_jvm_and_context_wrap(self):
        storage = self.directory / 'preferences-process-restart'
        self.probe('persist-writer', storage)
        self.probe('persist-reader', storage)

    def test_invalid_selection_does_not_change_text_preferences_or_resources(self):
        self.probe('invalid-selection')

    def test_failed_disk_commit_preserves_language_before_and_after_wrap(self):
        self.probe('failed-commit')

    def test_unsupported_stored_language_falls_back_to_english(self):
        self.probe('invalid-stored')

    def test_old_activity_recreates_once_on_resume_and_replacement_does_not_loop(self):
        self.probe('lifecycle')

    def test_destroyed_finishing_and_untracked_activities_are_not_recreated(self):
        self.probe('lifecycle-guards')

    def test_wrapping_preserves_non_language_configuration_and_application_identity(self):
        self.probe('configuration')

    def test_app_text_choice_preserves_raw_user_values_and_commands(self):
        self.probe('raw-values')


STUBS = {
'android/os/Bundle.java': 'package android.os; public class Bundle {}',
'android/os/LocaleList.java': r'''package android.os;
import java.util.Locale;
public final class LocaleList {
    private final Locale[] values;
    public LocaleList(Locale... values) { this.values = values.clone(); }
    public Locale get(int index) { return values[index]; }
    public int size() { return values.length; }
}''',
'android/util/DisplayMetrics.java': r'''package android.util;
public class DisplayMetrics { public int densityDpi = 480; }
''',
'android/content/res/Configuration.java': r'''package android.content.res;
import android.os.LocaleList;
import java.util.Locale;
public class Configuration {
    private LocaleList locales = new LocaleList(Locale.KOREAN);
    public float fontScale = 1.25f;
    public int orientation = 2, uiMode = 32, densityDpi = 480;
    public Configuration() {}
    public Configuration(Configuration other) {
        locales = other.locales; fontScale = other.fontScale;
        orientation = other.orientation; uiMode = other.uiMode; densityDpi = other.densityDpi;
    }
    public void setLocales(LocaleList values) { locales = values; }
    public LocaleList getLocales() { return locales; }
}''',
'android/content/res/Resources.java': r'''package android.content.res;
import android.util.DisplayMetrics;
public class Resources {
    private Configuration configuration;
    private final DisplayMetrics metrics = new DisplayMetrics();
    public int updates;
    public Resources(Configuration value) { configuration = new Configuration(value); }
    public Configuration getConfiguration() { return configuration; }
    public DisplayMetrics getDisplayMetrics() { return metrics; }
    public void updateConfiguration(Configuration value, DisplayMetrics displayMetrics) {
        configuration = new Configuration(value); updates++;
    }
}''',
'android/content/SharedPreferences.java': r'''package android.content;
import java.io.*;
import java.util.*;
public class SharedPreferences {
    private final File file;
    private final Properties values = new Properties();
    public boolean failWrites;
    public int commits;
    public SharedPreferences(File file) {
        this.file = file;
        if (file.exists()) try (InputStream input = new FileInputStream(file)) {
            values.load(input);
        } catch (IOException failure) { throw new AssertionError(failure); }
    }
    public String getString(String key, String fallback) { return values.getProperty(key, fallback); }
    public boolean contains(String key) { return values.containsKey(key); }
    public Editor edit() { return new Editor(); }
    public final class Editor {
        private final Map<String, String> changed = new HashMap<>();
        private boolean clear;
        public Editor putString(String key, String value) { changed.put(key, value); return this; }
        public Editor remove(String key) { changed.put(key, null); return this; }
        public Editor clear() { clear = true; return this; }
        public boolean commit() {
            commits++;
            // Android commitToMemory precedes its disk result:
            // https://android.googlesource.com/platform/frameworks/base/+/d88b5baa7b5a/core/java/android/app/SharedPreferencesImpl.java
            if (clear) values.clear();
            changed.forEach((key, value) -> { if (value == null) values.remove(key); else values.setProperty(key, value); });
            if (failWrites) return false;
            file.getParentFile().mkdirs();
            try (OutputStream output = new FileOutputStream(file)) {
                values.store(output, "Synthetic language test preferences");
                return true;
            } catch (IOException failure) { return false; }
        }
        public void apply() { commit(); }
    }
}''',
'android/content/Context.java': r'''package android.content;
import android.content.res.*;
import java.io.File;
import java.util.*;
public class Context {
    public static final int MODE_PRIVATE = 0;
    private final File directory;
    private final Map<String, SharedPreferences> preferences;
    private final Resources resources;
    private final Context application;
    public Context(File directory) {
        this.directory = directory; preferences = new HashMap<>();
        resources = new Resources(new Configuration()); application = this;
    }
    private Context(Context parent, Configuration configuration) {
        directory = parent.directory; preferences = parent.preferences;
        resources = new Resources(configuration); application = parent.getApplicationContext();
    }
    public SharedPreferences getSharedPreferences(String name, int mode) {
        return preferences.computeIfAbsent(name, key -> new SharedPreferences(new File(directory, key + ".properties")));
    }
    public Context getApplicationContext() { return application; }
    public Resources getResources() { return resources; }
    public Context createConfigurationContext(Configuration configuration) { return new Context(this, configuration); }
}''',
'android/app/Application.java': r'''package android.app;
import android.content.Context;
import android.os.Bundle;
import java.io.File;
import java.util.*;
public class Application extends Context {
    public final List<ActivityLifecycleCallbacks> callbacks = new ArrayList<>();
    public Application(File directory) { super(directory); }
    public void registerActivityLifecycleCallbacks(ActivityLifecycleCallbacks callback) { callbacks.add(callback); }
    public interface ActivityLifecycleCallbacks {
        void onActivityCreated(Activity activity, Bundle state);
        void onActivityResumed(Activity activity);
        void onActivityDestroyed(Activity activity);
        void onActivityStarted(Activity activity);
        void onActivityPaused(Activity activity);
        void onActivityStopped(Activity activity);
        void onActivitySaveInstanceState(Activity activity, Bundle state);
    }
}''',
'android/app/Activity.java': r'''package android.app;
public class Activity {
    public boolean finishing, destroyed;
    public int recreations;
    public boolean isFinishing() { return finishing; }
    public boolean isDestroyed() { return destroyed; }
    public void recreate() { recreations++; }
}''',
}


PROBE = r'''
package com.termux.app;

import android.app.*;
import android.content.*;
import android.content.res.Configuration;
import java.io.File;
import java.util.*;

public final class LanguageProbe {
    private static void eq(Object expected, Object actual) {
        if (!Objects.equals(expected, actual))
            throw new AssertionError("Language contract: expected " + expected + ", received " + actual);
    }
    private static void same(Object expected, Object actual) {
        if (expected != actual) throw new AssertionError("Unexpected replacement of an unmodified value");
    }
    private static SharedPreferences preferences(Context app) {
        return app.getSharedPreferences("z8.language", Context.MODE_PRIVATE);
    }
    private static String resourceLanguage(Context context) {
        return context.getResources().getConfiguration().getLocales().get(0).getLanguage();
    }
    private static Application.ActivityLifecycleCallbacks initialize(Application app) {
        Z8Language.initialize(app);
        eq(1, app.callbacks.size());
        return app.callbacks.get(0);
    }
    public static void main(String[] args) {
        File directory = new File(args[1]);
        Application app = new Application(directory);
        Locale.setDefault(Locale.KOREAN);
        switch (args[0]) {
            case "first-launch": {
                eq("en", Z8Text.language());
                eq("ko", resourceLanguage(app));
                initialize(app);
                eq("New project", Z8Text.text("New project", "새 프로젝트"));
                Context wrapped = Z8Language.wrap(app);
                eq("en", Z8Text.language()); eq("en", resourceLanguage(wrapped));
                eq("en", Locale.getDefault().getLanguage());
                eq(0, preferences(app).commits);
                break;
            }
            case "persist-writer": {
                initialize(app);
                eq(true, Z8Language.select(app, "ko"));
                eq("ko", preferences(app).getString("language", "missing"));
                eq("새 프로젝트", Z8Text.text("New project", "새 프로젝트"));
                eq("ko", resourceLanguage(app));
                // A later context must reload the explicit selection, not trust cached text state.
                Z8Text.setLanguage("en"); Locale.setDefault(Locale.JAPANESE);
                eq("ko", resourceLanguage(Z8Language.wrap(app)));
                eq("ko", Z8Text.language());
                break;
            }
            case "persist-reader": {
                // This case runs in another JVM: the class static defaults start over.
                eq("en", Z8Text.language());
                Locale.setDefault(Locale.GERMAN);
                eq("ko", resourceLanguage(Z8Language.wrap(app)));
                initialize(app);
                eq("ko", Z8Text.language()); eq("ko", Locale.getDefault().getLanguage());
                eq("새 프로젝트", Z8Text.text("New project", "새 프로젝트"));
                eq(0, preferences(app).commits);
                break;
            }
            case "invalid-selection": {
                initialize(app); eq(true, Z8Language.select(app, "ko"));
                int commits = preferences(app).commits, updates = app.getResources().updates;
                for (String invalid : new String[] { null, "", "fr", "KO", "ko-KR", " en", "en\n" }) {
                    eq(false, Z8Language.select(app, invalid));
                    eq("ko", Z8Text.language()); eq("ko", Locale.getDefault().getLanguage());
                    eq("ko", resourceLanguage(app));
                    eq("ko", preferences(app).getString("language", "missing"));
                }
                eq(commits, preferences(app).commits); eq(updates, app.getResources().updates);
                eq("ko", resourceLanguage(Z8Language.wrap(app)));
                break;
            }
            case "failed-commit": {
                initialize(app);
                for (String previous : new String[] { "en", "ko" }) {
                    preferences(app).failWrites = false;
                    eq(true, Z8Language.select(app, previous));
                    int updates = app.getResources().updates;
                    preferences(app).failWrites = true; // Also fails any attempted rollback disk write.
                    eq(false, Z8Language.select(app, "en".equals(previous) ? "ko" : "en"));
                    eq(previous, Z8Text.language()); eq(previous, Locale.getDefault().getLanguage());
                    eq(previous, resourceLanguage(app)); eq(updates, app.getResources().updates);
                    // Failed writes may alter Android's in-process preferences. Wrap must not adopt them.
                    eq(previous, resourceLanguage(Z8Language.wrap(app)));
                    eq(previous, Z8Text.language());
                    // Reopening storage independently must retain the last successfully committed value.
                    Application restarted = new Application(directory);
                    eq(previous, resourceLanguage(Z8Language.wrap(restarted)));
                }
                break;
            }
            case "invalid-stored": {
                eq(true, preferences(app).edit().putString("language", "fr").commit());
                Z8Text.setLanguage("ko");
                initialize(app);
                eq("en", Z8Text.language());
                eq("en", resourceLanguage(Z8Language.wrap(app)));
                eq("en", Locale.getDefault().getLanguage());
                break;
            }
            case "lifecycle": {
                Application.ActivityLifecycleCallbacks lifecycle = initialize(app);
                Activity old = new Activity();
                lifecycle.onActivityCreated(old, null); lifecycle.onActivityResumed(old);
                eq(0, old.recreations);
                eq(true, Z8Language.select(app, "ko"));
                eq(0, old.recreations); // A paused screen changes only when resumed.
                lifecycle.onActivityResumed(old); eq(1, old.recreations);
                lifecycle.onActivityResumed(old); lifecycle.onActivityResumed(old);
                eq(1, old.recreations);
                Activity replacement = new Activity();
                lifecycle.onActivityCreated(replacement, null);
                lifecycle.onActivityResumed(replacement); eq(0, replacement.recreations);
                eq(true, Z8Language.select(app, "ko"));
                lifecycle.onActivityResumed(replacement); eq(0, replacement.recreations);
                eq(true, Z8Language.select(app, "en"));
                lifecycle.onActivityResumed(replacement); eq(1, replacement.recreations);
                lifecycle.onActivityResumed(replacement); eq(1, replacement.recreations);
                break;
            }
            case "lifecycle-guards": {
                Application.ActivityLifecycleCallbacks lifecycle = initialize(app);
                Activity finishing = new Activity(), destroyed = new Activity(), forgotten = new Activity();
                lifecycle.onActivityCreated(finishing, null); finishing.finishing = true;
                lifecycle.onActivityCreated(destroyed, null); destroyed.destroyed = true;
                lifecycle.onActivityCreated(forgotten, null);
                lifecycle.onActivityDestroyed(forgotten);
                // Leave its flags false so this specifically tests forgetting the callback entry.
                eq(true, Z8Language.select(app, "ko"));
                lifecycle.onActivityResumed(finishing); eq(0, finishing.recreations);
                lifecycle.onActivityResumed(destroyed); eq(0, destroyed.recreations);
                lifecycle.onActivityResumed(forgotten); eq(0, forgotten.recreations);
                Activity unknown = new Activity(); lifecycle.onActivityResumed(unknown);
                eq(0, unknown.recreations);
                finishing.finishing = false; lifecycle.onActivityResumed(finishing);
                eq(1, finishing.recreations);
                break;
            }
            case "configuration": {
                Configuration original = new Configuration(app.getResources().getConfiguration());
                Context wrapped = Z8Language.wrap(app);
                Configuration changed = wrapped.getResources().getConfiguration();
                eq("en", resourceLanguage(wrapped)); eq("ko", resourceLanguage(app));
                eq(original.fontScale, changed.fontScale); eq(original.orientation, changed.orientation);
                eq(original.uiMode, changed.uiMode); eq(original.densityDpi, changed.densityDpi);
                same(app, wrapped.getApplicationContext());
                eq(true, Z8Language.select(wrapped, "ko"));
                eq("ko", resourceLanguage(app));
                eq("ko", resourceLanguage(Z8Language.wrap(app)));
                break;
            }
            case "raw-values": {
                String[] raw = { "새 프로젝트", "Settings", "printf '%s\\n' '$HOME/작업'", "/workspace/내 코드", "id-%s-${token}", "a\n한국어😀\t" };
                for (String language : new String[] { "en", "ko" }) {
                    Z8Text.setLanguage(language);
                    eq("ko".equals(language) ? "프로젝트: " : "Project: ", Z8Text.text("Project: ", "프로젝트: "));
                    for (String value : raw) {
                        // The helper chooses supplied app text; it does not parse, format, or translate values.
                        eq(value, Z8Text.text(value, value));
                        String rendered = Z8Text.text("Project: ", "프로젝트: ") + value;
                        eq(value, rendered.substring(rendered.length() - value.length()));
                    }
                    eq("%s", Z8Text.text("%s", "%s"));
                }
                break;
            }
            default: throw new AssertionError("Unknown probe case");
        }
        System.out.println("PASS language " + args[0]);
    }
}
'''
