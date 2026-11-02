package com.termux.app;

import android.app.Activity;
import android.os.Build;
import android.view.View;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import java.util.Collections;
import java.util.Set;
import java.util.WeakHashMap;

/** One inset owner prevents terminal chrome, panels and IME from overlapping on API 35+. */
public final class Z8WindowInsets {
    private static final Set<View> installed = Collections.newSetFromMap(new WeakHashMap<>());
    private Z8WindowInsets() {}

    public static void install(Activity activity) {
        if (Build.VERSION.SDK_INT < 35) return;
        View content = activity.findViewById(android.R.id.content);
        if (content == null || !installed.add(content)) return;
        WindowCompat.setDecorFitsSystemWindows(activity.getWindow(), false);
        int left = content.getPaddingLeft(), top = content.getPaddingTop();
        int right = content.getPaddingRight(), bottom = content.getPaddingBottom();
        ViewCompat.setOnApplyWindowInsetsListener(content, (view, insets) -> {
            Insets safe = insets.getInsets(WindowInsetsCompat.Type.systemBars()
                | WindowInsetsCompat.Type.displayCutout() | WindowInsetsCompat.Type.ime());
            view.setPadding(left + safe.left, top + safe.top, right + safe.right, bottom + safe.bottom);
            // Descendants previously used fitsSystemWindows. Do not apply the same inset twice.
            return WindowInsetsCompat.CONSUMED;
        });
        ViewCompat.requestApplyInsets(content);
    }
}
