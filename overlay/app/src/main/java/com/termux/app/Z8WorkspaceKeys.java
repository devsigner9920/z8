package com.termux.app;

import android.view.KeyEvent;
import java.util.HashSet;
import java.util.Set;

/** Event-only workspace shortcuts. Unmatched keys remain owned by the focused view. */
public final class Z8WorkspaceKeys {
    public interface Host {
        boolean isBrowserSelected();
        void newTerminal();
        void cycleTabs(int direction);
        void openBrowser();
        void focusBrowserAddress();
        void reloadBrowser();
        void returnToTerminal();
    }

    private final Host host;
    private final Set<Long> consumed = new HashSet<>();

    public Z8WorkspaceKeys(Host host) { this.host = host; }

    /** Reset on focus loss/pause so a missed key-up cannot capture a later press. */
    public void reset() { consumed.clear(); }

    public boolean dispatch(KeyEvent event) {
        int action = event.getAction();
        if (action != KeyEvent.ACTION_DOWN && action != KeyEvent.ACTION_UP) return false;
        long press = ((long) event.getDeviceId() << 32) | (event.getKeyCode() & 0xffffffffL);
        if (action == KeyEvent.ACTION_UP) return consumed.remove(press);
        if (consumed.contains(press)) return true;

        Runnable command = command(event);
        if (command == null) return false;
        consumed.add(press);
        // Repeat events after a focus reset are swallowed without creating work.
        if (event.getRepeatCount() == 0 && !event.isCanceled()) command.run();
        return true;
    }

    private Runnable command(KeyEvent event) {
        if (event.isAltPressed() || event.isCtrlPressed() && event.isMetaPressed()) return null;
        boolean ctrl = event.isCtrlPressed(), shift = event.isShiftPressed(), meta = event.isMetaPressed();
        int key = event.getKeyCode();
        if (key == KeyEvent.KEYCODE_T && (ctrl && shift && !meta || meta && !ctrl && !shift))
            return host::newTerminal;
        if (ctrl && !meta) {
            if (key == KeyEvent.KEYCODE_TAB) return () -> host.cycleTabs(shift ? -1 : 1);
            if (key == KeyEvent.KEYCODE_B && shift) return host::openBrowser;
            if (!shift && host.isBrowserSelected()) {
                if (key == KeyEvent.KEYCODE_L) return host::focusBrowserAddress;
                if (key == KeyEvent.KEYCODE_R) return host::reloadBrowser;
            }
        }
        if (key == KeyEvent.KEYCODE_ESCAPE && !ctrl && !shift && !meta && host.isBrowserSelected())
            return host::returnToTerminal;
        return null;
    }
}
