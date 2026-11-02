package com.termux.app;

import android.app.AlertDialog;
import android.os.Handler;
import android.os.Looper;
import android.view.MotionEvent;
import android.widget.Toast;
import com.termux.terminal.TerminalSession;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Map;
import java.util.Set;
import java.util.WeakHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

/** Explicit HTML taps become a browser action, never bytes typed into a CLI. */
public final class Z8TerminalLinks {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final ExecutorService IO = Executors.newFixedThreadPool(2);
    private static final Set<TerminalSession> BUSY = Collections.newSetFromMap(new WeakHashMap<>());
    // Keep the containing PRoot alive only if this invocation created a preview server.
    // That server checks the original terminal lease and has its own idle/max deadlines.
    static final String HELPER = "import runpy,sys,threading; "
        + "m=runpy.run_path('/usr/local/lib/z8/browser-open.py'); r=m['main'](sys.argv[1:]); "
        + "print('Z8_HTML_READY='+str(r),flush=True); "
        + "[t.join() for t in threading.enumerate() if t.name=='z8-preview-reaper']; sys.exit(r)";

    private Z8TerminalLinks() { }

    public static boolean openAt(TermuxActivity activity, MotionEvent event) {
        TerminalSession session = activity.getCurrentSession();
        if (session == null || !session.isRunning() || session.getEmulator() == null
                || activity.getTerminalView().isSelectingText()) return false;
        Z8SessionOrigin origin = Z8SessionOrigin.of(session);
        if (origin == null || origin.projectId == null) return false;
        int[] cell = activity.getTerminalView().getColumnAndRow(event, true);
        String token = tokenAt(session, cell[0], cell[1]);
        if (token == null) return false;
        synchronized (BUSY) { if (!BUSY.add(session)) return true; }
        IO.execute(() -> {
            try {
                Z8Projects.Project project = new Z8Projects(activity).open(origin.projectId);
                Path home = Z8TerminalPath.directory(activity.getFilesDir().toPath(), "z8/homes/" + origin.projectId);
                Path source = project.source.toPath();
                Z8TerminalPath.Matches matches = Z8TerminalPath.find(token, home, source);
                MAIN.post(() -> {
                    synchronized (BUSY) { BUSY.remove(session); }
                    if (!current(activity, session)) return;
                    if (!matches.complete) { message(activity, Z8Text.text("The search is too broad to identify a file. Use the full HTML path.", "검색 범위가 커서 파일을 확정하지 못했습니다. 전체 HTML 경로를 사용해 주세요.")); return; }
                    if (matches.paths.isEmpty()) { message(activity, Z8Text.text("No HTML file was found in this project.", "이 프로젝트에서 HTML 파일을 찾지 못했습니다.")); return; }
                    if (matches.paths.size() == 1) { launch(activity, session, origin.projectId, matches.paths.get(0), home, source); return; }
                    String[] choices = matches.paths.toArray(new String[0]);
                    new AlertDialog.Builder(activity).setTitle(Z8Text.text("Choose an HTML file to preview", "미리볼 HTML 파일"))
                        .setItems(choices, (dialog, which) -> {
                            dialog.dismiss();
                            // Let the dialog release window focus before validating the terminal again.
                            MAIN.postDelayed(() -> {
                                if (current(activity, session)) launch(activity, session, origin.projectId, choices[which], home, source);
                            }, 100);
                        }).setNegativeButton(Z8Text.text("Cancel", "취소"), null).show();
                });
            } catch (Exception unavailable) {
                MAIN.post(() -> { synchronized (BUSY) { BUSY.remove(session); }
                    if (current(activity, session)) message(activity, Z8Text.text("Could not verify this project's HTML file.", "이 프로젝트의 HTML 파일을 확인하지 못했습니다.")); });
            }
        });
        return true;
    }

    /** Use terminal cell boundaries so Korean/wide glyphs before the path do not shift the hit target. */
    private static String tokenAt(TerminalSession session, int column, int row) {
        com.termux.terminal.TerminalEmulator terminal = session.getEmulator();
        if (column < 0 || column >= terminal.mColumns || row < -terminal.getScreen().getActiveTranscriptRows() || row >= terminal.mRows) return null;
        String tapped = terminal.getScreen().getSelectedText(column, row, column, row);
        if (tapped.isEmpty() || tapped.trim().isEmpty()) return null;
        int start = column, end = column;
        while (start > 0 && !terminal.getScreen().getSelectedText(start - 1, row, start - 1, row).trim().isEmpty()) start--;
        while (end + 1 < terminal.mColumns && !terminal.getScreen().getSelectedText(end + 1, row, end + 1, row).trim().isEmpty()) end++;
        return Z8TerminalPath.htmlToken(terminal.getScreen().getSelectedText(start, row, end, row));
    }

    private static boolean current(TermuxActivity activity, TerminalSession session) {
        return !activity.isFinishing() && !activity.isDestroyed() && activity.hasWindowFocus()
            && session.isRunning() && activity.getCurrentSession() == session
            && activity.getTerminalView().isShown() && !activity.getTerminalView().isSelectingText();
    }

    private static void launch(TermuxActivity activity, TerminalSession session, String projectId,
            String path, Path home, Path source) {
        synchronized (BUSY) { if (!BUSY.add(session)) return; }
        IO.execute(() -> {
            boolean ok = false;
            Process process = null;
            try {
                String target = Z8TerminalPath.resolve(path, null, home, source);
                Map<String, String> credentials = Z8AttentionBridge.browserEnvironment(session);
                if (credentials == null) throw new IOException("Terminal ended");
                Z8Guest.Launch launch = Z8Guest.commandFor(activity, projectId, null,
                    new String[]{"/usr/bin/python3", "-I", "-c", HELPER, target});
                ArrayList<String> argv = new ArrayList<>(); argv.add(launch.executable);
                argv.addAll(Arrays.asList(launch.arguments));
                ProcessBuilder builder = new ProcessBuilder(argv).directory(new File(launch.workingDirectory));
                builder.environment().clear(); builder.environment().put("PATH", "/system/bin");
                builder.environment().put("PROOT_TMP_DIR", activity.getCacheDir().getAbsolutePath());
                builder.environment().putAll(credentials);
                builder.redirectError(new File("/dev/null"));
                FutureTask<Boolean> selected = new FutureTask<>(() -> current(activity, session));
                MAIN.post(selected);
                if (!selected.get(2, TimeUnit.SECONDS)) throw new IOException("Terminal changed");
                synchronized (Z8RuntimeLauncher.EXECUTION_LOCK) { process = builder.start(); }
                process.getOutputStream().close();
                final InputStream output = process.getInputStream();
                FutureTask<String> status = new FutureTask<>(() -> {
                    java.io.ByteArrayOutputStream line = new java.io.ByteArrayOutputStream();
                    for (int i = 0; i < 64; i++) { int b = output.read(); if (b == -1 || b == '\n') break; line.write(b); }
                    return new String(line.toByteArray(), StandardCharsets.US_ASCII);
                });
                Thread reader = new Thread(status, "z8-html-result"); reader.setDaemon(true); reader.start();
                ok = "Z8_HTML_READY=0".equals(status.get(15, TimeUnit.SECONDS));
                output.close();
                if (ok) {
                    final Process owned = process;
                    Thread reaper = new Thread(() -> { try { owned.waitFor(); } catch (InterruptedException ignored) { Thread.currentThread().interrupt(); } }, "z8-html-helper");
                    reaper.setDaemon(true); reaper.start();
                }
            } catch (Exception unavailable) { /* Generic UI error only: never log paths, URLs or launch tokens. */ }
            finally {
                if (!ok && process != null) process.destroyForcibly();
                final boolean success = ok;
                MAIN.post(() -> { synchronized (BUSY) { BUSY.remove(session); }
                    if (!success && current(activity, session)) message(activity, Z8Text.text("Could not open the preview. Check that the terminal is running.", "미리보기를 열지 못했습니다. 터미널이 실행 중인지 확인해 주세요.")); });
            }
        });
    }

    private static void message(TermuxActivity activity, String value) {
        Toast.makeText(activity, value, Toast.LENGTH_LONG).show();
    }
}
