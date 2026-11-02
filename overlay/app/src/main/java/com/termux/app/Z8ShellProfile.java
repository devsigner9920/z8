package com.termux.app;

import android.content.Context;
import android.util.AtomicFile;
import android.util.Log;

import com.termux.shared.shell.command.ExecutionCommand;
import com.termux.shared.termux.TermuxConstants;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;

/** APK-managed shell conveniences. Project source and user startup files are never replaced. */
public final class Z8ShellProfile {
    private Z8ShellProfile() {}

    public static HashMap<String, String> environment(Context context, ExecutionCommand command) {
        if (!command.isPluginExecutionCommand &&
                Z8RuntimeLauncher.isGuestCommand(command.executable, command.arguments)) {
            HashMap<String, String> environment = new HashMap<>();
            // Native Android preload libraries must never reach the guest ELF loader.
            environment.put("LD_PRELOAD", "");
            environment.put("LD_LIBRARY_PATH", "");
            environment.put("PROOT_TMP_DIR", context.getCacheDir().getAbsolutePath());
            environment.put("Z8_SHOW_WELCOME", "1");
            return environment;
        }
        if (!command.isPluginExecutionCommand && !command.isFailsafe && command.executable == null) {
            HashMap<String, String> environment = new HashMap<>();
            boolean linked = Z8RuntimeLauncher.requiresSystemLinker(android.os.Build.VERSION.SDK_INT);
            environment.put("LD_PRELOAD", TermuxConstants.TERMUX_PREFIX_DIR_PATH + "/lib/libtermux-exec-"
                + (linked ? "linker" : "direct") + "-ld-preload.so");
            environment.put("TERMUX_EXEC__SYSTEM_LINKER_EXEC__MODE", linked ? "force" : "enable");
            try {
                File directory = new File(TermuxConstants.TERMUX_PREFIX_DIR_PATH, "etc/profile.d");
                install(context, directory, "z8-managed.sh", "z8/native.profile");
                environment.put("Z8_SHOW_WELCOME", "1");
            } catch (IOException exception) {
                Log.w("z8", "Native shell conveniences unavailable", exception);
            }
            return environment;
        }
        if (!command.isFailsafe || command.isPluginExecutionCommand
            || (command.executable != null && !"/system/bin/sh".equals(command.executable))) {
            return null;
        }

        HashMap<String, String> environment = new HashMap<>();
        // Android's /data/local/tmp is not writable by this app UID.
        environment.put("TMPDIR", context.getCacheDir().getAbsolutePath());
        try {
            File directory = new File(context.getFilesDir(), "z8/shell");
            File profile = install(context, directory, "diagnostic.mkshrc", "z8/diagnostic.mkshrc");
            environment.put("ENV", profile.getAbsolutePath());
            // Consumed and unset by the first interactive shell, never on reattach.
            environment.put("Z8_SHOW_WELCOME", "1");
        } catch (IOException exception) {
            // A convenience profile failure must leave the rescue shell usable.
            Log.w("z8", "Diagnostic aliases unavailable; opening the standard Android shell", exception);
        }
        return environment;
    }

    private static File install(Context context, File directory, String name, String asset) throws IOException {
        if (!directory.isDirectory() && !directory.mkdirs())
            throw new IOException("Cannot create managed shell profile directory");
        File profile = new File(directory, name);
        AtomicFile atomic = new AtomicFile(profile);
        FileOutputStream output = null;
        try (InputStream input = context.getAssets().open(asset)) {
            output = atomic.startWrite();
            byte[] buffer = new byte[4096];
            int count;
            while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            atomic.finishWrite(output);
            output = null;
        } catch (IOException exception) {
            if (output != null) atomic.failWrite(output);
            throw exception;
        }
        return profile;
    }
}
