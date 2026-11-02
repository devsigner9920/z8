package com.termux.app;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;

/** Compatibility entry for old internal links; the terminal is the only workspace. */
public final class Z8WorkspaceActivity extends Activity {
    public static final String EXTRA_PROJECT_ID = "dev.devsigner.z8.PROJECT_ID";
    public static final String EXTRA_PROJECT_CWD = "dev.devsigner.z8.PROJECT_CWD";
    public static final String EXTRA_SHOW_SESSIONS = "dev.devsigner.z8.SHOW_SESSIONS";
    public static final String EXTRA_FOCUS_PROJECT_ID = "dev.devsigner.z8.FOCUS_PROJECT_ID";

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        Intent terminal = new Intent(this, TermuxActivity.class)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        String project = getIntent() == null ? null : getIntent().getStringExtra(EXTRA_PROJECT_ID);
        if (project == null || project.isEmpty()) terminal.putExtra(EXTRA_SHOW_SESSIONS, true);
        else terminal.putExtra(EXTRA_FOCUS_PROJECT_ID, project);
        // Selecting a project never asks the service to create a shell.
        startActivity(terminal);
        finish();
    }
}
