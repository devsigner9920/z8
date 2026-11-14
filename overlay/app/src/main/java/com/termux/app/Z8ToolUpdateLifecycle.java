package com.termux.app;

import android.app.Activity;
import android.app.Application;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;

/** Foreground-only version checks; navigation and rotation do not schedule background work. */
public final class Z8ToolUpdateLifecycle implements Application.ActivityLifecycleCallbacks {
    private static boolean installed;
    private final Application application;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private int started;
    private final Runnable hidden = () -> { if (started == 0) Z8ToolUpdates.cancel(); };

    private Z8ToolUpdateLifecycle(Application application) { this.application = application; }

    public static synchronized void install(Application application) {
        if (installed) return;
        installed = true;
        application.registerActivityLifecycleCallbacks(new Z8ToolUpdateLifecycle(application));
    }

    @Override public void onActivityStarted(Activity activity) {
        handler.removeCallbacks(hidden);
        if (started++ == 0) Z8ToolUpdates.requestCheck(application, false, null);
    }

    @Override public void onActivityStopped(Activity activity) {
        if (started > 0) started--;
        // Allow replacement activities to start before treating the app as hidden.
        if (started == 0) handler.postDelayed(hidden, 500);
    }

    @Override public void onActivityCreated(Activity activity, Bundle state) {}
    @Override public void onActivityResumed(Activity activity) {}
    @Override public void onActivityPaused(Activity activity) {}
    @Override public void onActivitySaveInstanceState(Activity activity, Bundle state) {}
    @Override public void onActivityDestroyed(Activity activity) {}
}
