package com.termux.app;

import android.app.Activity;
import android.os.Build;
import android.window.OnBackInvokedCallback;
import android.window.OnBackInvokedDispatcher;

/** Registers the platform back API while keeping legacy dispatch on Android 9–12. */
public final class Z8BackNavigation implements AutoCloseable {
    private Runnable unregister;

    private Z8BackNavigation(Runnable unregister) { this.unregister = unregister; }

    public static Z8BackNavigation install(Activity activity, Runnable action) {
        return new Z8BackNavigation(Build.VERSION.SDK_INT >= 33 ? Api33.register(activity, action) : null);
    }

    @Override public void close() {
        if (unregister != null) { unregister.run(); unregister = null; }
    }

    private static final class Api33 {
        static Runnable register(Activity activity, Runnable action) {
            OnBackInvokedDispatcher dispatcher = activity.getOnBackInvokedDispatcher();
            OnBackInvokedCallback callback = action::run;
            dispatcher.registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT, callback);
            return () -> dispatcher.unregisterOnBackInvokedCallback(callback);
        }
    }
}
