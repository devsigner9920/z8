package com.termux.view;

/** Input decisions independent of Android dispatch, covered by host behavior tests. */
public final class Z8TerminalInput {
    public enum ClipboardShortcut { NONE, COPY, PASTE }

    /** Key is a logical C/V key label, independent of the current IME alphabet. */
    public static ClipboardShortcut clipboardShortcut(char key, boolean meta, boolean ctrl, boolean shift, boolean alt) {
        if (alt || !(meta || ctrl && shift)) return ClipboardShortcut.NONE;
        if (key == 'c' || key == 'C') return ClipboardShortcut.COPY;
        if (key == 'v' || key == 'V') return ClipboardShortcut.PASTE;
        return ClipboardShortcut.NONE;
    }

    private int anchorColumn, anchorRow;
    private boolean dragging, moved;
    private float scrollRemainder;
    private int scrollDevice = Integer.MIN_VALUE, scrollRoute = -1;

    /** Smooth wheels/trackpads send fractional detents, not necessarily one tick per event. */
    public int scrollRows(float verticalDetents, int deviceId, int route) {
        if (!Float.isFinite(verticalDetents) || verticalDetents == 0) return 0;
        if (scrollDevice != deviceId || scrollRoute != route) resetScroll();
        scrollDevice = deviceId; scrollRoute = route;
        // Preserve the established three-row mouse-wheel detent, but bound work per event.
        float rows = Math.max(-120f, Math.min(120f, -verticalDetents * 3f));
        float total = scrollRemainder + rows;
        int wholeRows = (int) total;
        scrollRemainder = total - wholeRows;
        return wholeRows;
    }

    public void resetScroll() { scrollRemainder = 0; scrollDevice = Integer.MIN_VALUE; scrollRoute = -1; }
    public void begin(int column, int row) { anchorColumn = column; anchorRow = row; dragging = true; moved = false; }
    /** Keep a held mouse press attached to its original text while new output moves rows. */
    public void shiftRows(int rows) { if (dragging) anchorRow -= rows; }
    public boolean isDragging() { return dragging; }
    public void finish() { dragging = false; }
    /** Null until a real range is dragged; terminal coordinates can include negative scrollback rows. */
    public int[] range(int column, int row) {
        if (!dragging) return null;
        if (column != anchorColumn || row != anchorRow) moved = true;
        if (!moved) return null;
        boolean forward = row > anchorRow || (row == anchorRow && column >= anchorColumn);
        return forward ? new int[]{anchorColumn, anchorRow, column, row}
            : new int[]{column, row, anchorColumn, anchorRow};
    }
    public static boolean requiresPasteConfirmation(String text) {
        return text != null && (text.indexOf('\n') >= 0 || text.indexOf('\r') >= 0);
    }
    /** A single IME newline is the Enter key, while bulk committed lines are a paste. */
    public static boolean isBulkImePaste(CharSequence text) {
        return text != null && text.length() > 1 && requiresPasteConfirmation(text.toString());
    }
}
