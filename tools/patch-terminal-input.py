"""Small, fail-closed patches against the pinned TerminalView; never edits upstream."""

def patch(tree, replace):
    path = tree / 'terminal-view/src/main/java/com/termux/view/TerminalView.java'
    s = path.read_text()
    s = replace(s, 'import android.graphics.Canvas;', 'import android.graphics.Canvas;\nimport android.graphics.Rect;')
    s = replace(s, '    private final boolean mAccessibilityEnabled;', '''    private final AccessibilityManager mZ8AccessibilityManager;
    private boolean mZ8AccessibilityListening;
    private final AccessibilityManager.AccessibilityStateChangeListener mZ8AccessibilityListener =
        enabled -> z8RefreshAccessibilityText();''')
    s = replace(s, '''        AccessibilityManager am = (AccessibilityManager) context.getSystemService(Context.ACCESSIBILITY_SERVICE);
        mAccessibilityEnabled = am.isEnabled();''', '''        mZ8AccessibilityManager = (AccessibilityManager) context.getSystemService(Context.ACCESSIBILITY_SERVICE);''')
    s = replace(s, '        if (mAccessibilityEnabled) setContentDescription(getText());', '        z8RefreshAccessibilityText();')
    s = replace(s, '''    public void onScreenUpdated(boolean skipScrolling) {
        if (mEmulator == null) return;

        int rowsInHistory''', '''    public void onScreenUpdated(boolean skipScrolling) {
        if (mEmulator == null) return;
        // Selection handles already track buffer scrolling. Translate the mouse
        // press too, including output received before its first MOVE event.
        mZ8Input.shiftRows(mEmulator.getScrollCounter());

        int rowsInHistory''')
    s = replace(s, '''        super.onAttachedToWindow();

        if (mTextSelectionCursorController != null) {''', '''        super.onAttachedToWindow();
        if (mZ8AccessibilityManager != null && !mZ8AccessibilityListening) {
            mZ8AccessibilityManager.addAccessibilityStateChangeListener(mZ8AccessibilityListener);
            mZ8AccessibilityListening = true;
        }
        z8RefreshAccessibilityText();

        if (mTextSelectionCursorController != null) {''')
    s = replace(s, '    private TextSelectionCursorController mTextSelectionCursorController;', '''    private TextSelectionCursorController mTextSelectionCursorController;
    private final Z8TerminalInput mZ8Input = new Z8TerminalInput();
    private int mZ8MouseButton;
    private boolean mZ8MouseTracking;
    private int mZ8InputGeneration;
    private boolean mZ8InputSuspended;
    private TerminalSession mZ8AutofillSession;
    private final Runnable mZ8ShowSoftKeyboard = this::z8ShowSoftKeyboardAfterFocus;
    private android.app.AlertDialog mZ8PasteDialog;''')
    s = replace(s, '        if (session == mTermSession) return false;\n\n        mTermSession = session;', '''        if (session == mTermSession) return false;

        cancelRequestAutoFill();
        ++mZ8InputGeneration;
        removeCallbacks(mZ8ShowSoftKeyboard);
        forceStopTextSelectionMode();
        mZ8Input.resetScroll();
        mScroller.abortAnimation();
        mGestureRecognizer.cancel();
        mZ8MouseButton = 0;
        mZ8MouseTracking = false;
        if (mZ8PasteDialog != null) mZ8PasteDialog.dismiss();
        mTermSession = session;''')
    s = replace(s, '''        updateSize();

        // Wait with enabling the scrollbar until we have a terminal to get scroll position from.''', '''        updateSize();
        // A stopped session emits no future onScreenUpdated callback. Publish the attached
        // buffer now, without changing its scroll counters or injecting terminal input.
        z8RefreshAccessibilityText();
        z8RestartInput();

        // Wait with enabling the scrollbar until we have a terminal to get scroll position from.''')
    s = replace(s, '            void sendTextToTerminal(CharSequence text) {\n                stopTextSelectionMode();', '''            void sendTextToTerminal(CharSequence text) {
                if (!z8AcceptsInput()) return;
                if (Z8TerminalInput.isBulkImePaste(text)) {
                    pasteText(text.toString());
                    return;
                }
                stopTextSelectionMode();''')
    # Android may call finish/commit/delete on an old connection after a session
    # switch or app return. Bind callbacks to both their original PTY and epoch.
    s = replace(s, '''        return new BaseInputConnection(this, true) {

            @Override
            public boolean finishComposingText() {''', '''        final TerminalSession z8InputSession = mTermSession;
        final int z8InputGeneration = ++mZ8InputGeneration;
        return new BaseInputConnection(this, true) {
            private boolean z8AcceptsInput() {
                return !mZ8InputSuspended && z8InputGeneration == mZ8InputGeneration
                    && z8InputSession != null && z8InputSession == mTermSession
                    && mEmulator != null && z8InputSession.isRunning();
            }

            @Override
            public boolean setComposingText(CharSequence text, int newCursorPosition) {
                if (!z8AcceptsInput()) return true;
                return super.setComposingText(text, newCursorPosition);
            }

            @Override
            public boolean sendKeyEvent(KeyEvent event) {
                if (!z8AcceptsInput()) return true;
                return super.sendKeyEvent(event);
            }

            @Override
            public boolean finishComposingText() {
                if (!z8AcceptsInput()) { getEditable().clear(); return true; }''')
    s = replace(s, '''            public boolean commitText(CharSequence text, int newCursorPosition) {
                if (TERMINAL_VIEW_KEY_LOGGING_ENABLED)''', '''            public boolean commitText(CharSequence text, int newCursorPosition) {
                if (!z8AcceptsInput()) { getEditable().clear(); return true; }
                if (TERMINAL_VIEW_KEY_LOGGING_ENABLED)''')
    s = replace(s, '''            public boolean deleteSurroundingText(int leftLength, int rightLength) {
                if (TERMINAL_VIEW_KEY_LOGGING_ENABLED)''', '''            public boolean deleteSurroundingText(int leftLength, int rightLength) {
                if (!z8AcceptsInput()) return true;
                if (TERMINAL_VIEW_KEY_LOGGING_ENABLED)''')
    # A touch tap must still request the IME when a TUI enables mouse reporting.
    # The upstream fast mouse-click route consumes the tap before onSingleTapUp.
    s = replace(s, '''                    sendMouseEventCode(event, TerminalEmulator.MOUSE_LEFT_BUTTON, false);
                    return true;''', '''                    sendMouseEventCode(event, TerminalEmulator.MOUSE_LEFT_BUTTON, false);
                    requestFocus();
                    mClient.onSingleTapUp(event);
                    return true;''')
    s = replace(s, '''        if (mTermSession == null) return;

        // Ensure cursor is shown''', '''        if (mTermSession == null || mZ8InputSuspended) return;

        // Ensure cursor is shown''')
    s = replace(s, '            mTermSession.writeCodePoint(altDown, codePoint);',
        '            z8FollowInput();\n            mTermSession.writeCodePoint(altDown, codePoint);')
    s = replace(s, '''        mTermSession.write(code);
        return true;''', '''        z8FollowInput();
        mTermSession.write(code);
        return true;''')
    s = replace(s, '''            mTermSession.write(event.getCharacters());
            return true;''', '''            z8FollowInput();
            mTermSession.write(event.getCharacters());
            return true;''')
    s = replace(s, '''        if (mEmulator == null || (newColumns != mEmulator.mColumns || newRows != mEmulator.mRows)) {
            mTermSession.updateSize''', '''        if (mEmulator == null || (newColumns != mEmulator.mColumns || newRows != mEmulator.mRows)) {
            boolean z8KeepSelection = isSelectingText() && mEmulator != null
                && newColumns == mEmulator.mColumns;
            int z8OldCursorRow = mEmulator == null ? 0 : mEmulator.getCursorRow();
            // Width reflow changes every cell coordinate. Height-only IME changes
            // preserve lines, so keep selection and translate it with the buffer.
            if (isSelectingText() && !z8KeepSelection) forceStopTextSelectionMode();
            mTermSession.updateSize''')
    s = replace(s, '''            mEmulator = mTermSession.getEmulator();
            mClient.onEmulatorSet();''', '''            mEmulator = mTermSession.getEmulator();
            if (z8KeepSelection && mEmulator != null) {
                int shift = z8OldCursorRow - mEmulator.getCursorRow();
                mZ8Input.shiftRows(shift);
                mTextSelectionCursorController.onTerminalRowsResized(shift);
                int oldest = -mEmulator.getScreen().getActiveTranscriptRows();
                mEmulator.setTopRow(Math.max(oldest, Math.min(0, mTopRow - shift)));
            }
            mClient.onEmulatorSet();''')
    s = replace(s, '''        return (int) (((y - 40) / mRenderer.mFontLineSpacing) + mTopRow);''', '''        // Handles are positioned at the bottom of their row. Use the same font
        // metric as getPointY, not a fixed pixel offset that jumps after zoom.
        return (int) Math.ceil(y / mRenderer.mFontLineSpacing) - 1 + mTopRow;''')
    s = replace(s, '        return (int) (x / mRenderer.mFontWidth);', '''        // getPointX rounds the rendered boundary to a pixel. Account for that
        // half-pixel rounding before mapping the start boundary back to a cell.
        return (int) Math.floor((x + 0.5f) / mRenderer.mFontWidth);''')
    s = replace(s, '''    public void autofill(AutofillValue value) {
        if (value.isText()) {
            mTermSession.write(value.getTextValue().toString());
        }

        resetAutoFill();
    }''', '''    public void autofill(AutofillValue value) {
        final TerminalSession target = mZ8AutofillSession;
        resetAutoFill();
        // Android can deliver a dataset after the same view switched projects.
        // Only an outstanding request from this still-live PTY may receive it.
        if (target != null && target == mTermSession && target.isRunning()
                && !mZ8InputSuspended && value != null && value.isText()) {
            pasteText(value.getTextValue().toString());
        }
    }''')
    s = replace(s, '''    private synchronized void resetAutoFill() {
        // Restore none type''', '''    private synchronized void resetAutoFill() {
        mZ8AutofillSession = null;
        // Restore none type''')
    s = replace(s, '''        if (autoFillHints == null || autoFillHints.length < 1) return;

        try {''', '''        if (autoFillHints == null || autoFillHints.length < 1) return;
        if (mTermSession == null || !mTermSession.isRunning() || mZ8InputSuspended) return;

        try {''')
    s = replace(s, '''                mAutoFillHints = autoFillHints;
                autofillManager.requestAutofill(this);''', '''                mAutoFillHints = autoFillHints;
                mZ8AutofillSession = mTermSession;
                autofillManager.requestAutofill(this);''')
    s = replace(s, '''            mClient.logStackTraceWithMessage(LOG_TAG, "Failed to request Autofill", e);''', '''            resetAutoFill();
            mClient.logStackTraceWithMessage(LOG_TAG, "Failed to request Autofill", e);''')
    s = replace(s, '''        if (mAutoFillType == AUTOFILL_TYPE_NONE) return;

        try {''', '''        if (mAutoFillType == AUTOFILL_TYPE_NONE) return;
        // Revoke locally even if the provider was disabled or cancel throws.
        resetAutoFill();

        try {''')
    s = replace(s, '''                resetAutoFill();
                autofillManager.cancel();''', '''                autofillManager.cancel();''')
    # Wheel + Shift is local scroll, including programs that enabled mouse reporting.
    start=s.index('    void doScroll(MotionEvent event, int rowsDown) {')
    end=s.index('    /** Overriding {@link View#onGenericMotionEvent', start)
    scroll=s[start:end].replace('mEmulator.isMouseTrackingActive())', 'mEmulator.isMouseTrackingActive() && (event.getMetaState() & KeyEvent.META_SHIFT_ON) == 0)')
    scroll=scroll.replace('mEmulator.isAlternateBufferActive())', 'mEmulator.isAlternateBufferActive() && (event.getMetaState() & KeyEvent.META_SHIFT_ON) == 0)')
    scroll=replace(scroll, '    void doScroll(MotionEvent event, int rowsDown) {', '''    void doScroll(MotionEvent event, int rowsDown) {
        if (mEmulator == null || rowsDown == 0) return;
        boolean local = isSelectingText() || (event.getMetaState() & KeyEvent.META_SHIFT_ON) != 0
            || !mEmulator.isMouseTrackingActive() && !mEmulator.isAlternateBufferActive();
        if (local) {
            // Scrollback has one final viewport; no need to redraw once per traversed row.
            int top = (int) Math.min(0L, Math.max(-(long) mEmulator.getScreen().getActiveTranscriptRows(),
                (long) mTopRow + rowsDown));
            if (top != mTopRow) { setTopRow(top); if (!awakenScrollBars()) invalidate(); }
            return;
        }''')
    scroll=replace(scroll, '''            } else {
                setTopRow(Math.min(0, Math.max(-(mEmulator.getScreen().getActiveTranscriptRows()), mTopRow + (up ? -1 : 1))));
                if (!awakenScrollBars()) invalidate();
            }''', '            }')
    s=s[:start]+scroll+s[end:]
    s=replace(s, '''        if (mEmulator != null && event.isFromSource(InputDevice.SOURCE_MOUSE) && event.getAction() == MotionEvent.ACTION_SCROLL) {
            // Handle mouse wheel scrolling.
            boolean up = event.getAxisValue(MotionEvent.AXIS_VSCROLL) > 0.0f;
            doScroll(event, up ? -3 : 3);
            return true;
        }''', '''        if (mEmulator != null && (event.isFromSource(InputDevice.SOURCE_MOUSE)
                || event.isFromSource(InputDevice.SOURCE_TOUCHPAD)) && event.getAction() == MotionEvent.ACTION_SCROLL) {
            float vertical = event.getAxisValue(MotionEvent.AXIS_VSCROLL);
            // A horizontal two-finger gesture must never invent a downward terminal scroll.
            if (!Float.isFinite(vertical) || vertical == 0) return false;
            boolean local = isSelectingText() || (event.getMetaState() & KeyEvent.META_SHIFT_ON) != 0;
            int route = local ? 0 : mEmulator.isMouseTrackingActive() ? 1 : mEmulator.isAlternateBufferActive() ? 2 : 0;
            int rows = mZ8Input.scrollRows(vertical, event.getDeviceId(), route);
            if (rows != 0) doScroll(event, rows);
            return true;
        }''')
    start=s.index('    @SuppressLint("ClickableViewAccessibility")\n    @Override\n    @TargetApi(23)\n    public boolean onTouchEvent(MotionEvent event) {')
    end=s.index('\n    @Override\n    public boolean onKeyPreIme',start)
    s=s[:start]+TOUCH+s[end:]
    s=replace(s, '''        if (mEmulator == null) return true;
        if (isSelectingText()) {
            stopTextSelectionMode();
        }

        if (mClient.onKeyDown(keyCode, event, mTermSession)) {''', '''        if (mEmulator == null) return true;
        if (z8HandleClipboardShortcut(keyCode, event)) return true;
        if (mZ8InputSuspended) return true;
        if (isSelectingText() && !KeyEvent.isModifierKey(keyCode)) {
            stopTextSelectionMode();
        }

        if (mClient.onKeyDown(keyCode, event, mTermSession)) {''')
    s = replace(s, '                final boolean mouseTrackingAtStartOfFling = mEmulator.isMouseTrackingActive();',
        '                final TerminalSession z8FlingSession = mTermSession;\n                final boolean mouseTrackingAtStartOfFling = mEmulator.isMouseTrackingActive();')
    s = replace(s, '''                // Do not start scrolling until last fling has been taken care of:
                if (!mScroller.isFinished()) return true;''', '''                // A native copy gesture must not scroll the application beneath
                // its selected cells, including a late fling after handle drag.
                if (isSelectingText()) return true;
                // Do not start scrolling until last fling has been taken care of:
                if (!mScroller.isFinished()) return true;''')
    s = replace(s, '                        if (mouseTrackingAtStartOfFling != mEmulator.isMouseTrackingActive()) {',
        '                        if (mEmulator == null || mTermSession != z8FlingSession || mouseTrackingAtStartOfFling != mEmulator.isMouseTrackingActive() || isSelectingText()) {')
    s = replace(s, '        showTextSelectionCursors(event);', '''        // Stop inertial TUI scroll before recording the selection coordinates.
        mScroller.abortAnimation();
        mScrollRemainder = 0.0f;
        mZ8Input.resetScroll();
        showTextSelectionCursors(event);''')
    s = replace(s, '                if (mGestureRecognizer.isInProgress()) return;',
        '                if (mEmulator == null || mGestureRecognizer.isInProgress()) return;')
    s=replace(s, '    private void decrementYTextSelectionCursors(int decrement) {', HELPERS+'\n    private void decrementYTextSelectionCursors(int decrement) {')
    s=replace(s, '        super.onDetachedFromWindow();\n\n        if (mTextSelectionCursorController != null) {', '''        super.onDetachedFromWindow();
        if (mZ8AccessibilityManager != null && mZ8AccessibilityListening) {
            mZ8AccessibilityManager.removeAccessibilityStateChangeListener(mZ8AccessibilityListener);
            mZ8AccessibilityListening = false;
        }
        setContentDescription(null);
        cancelRequestAutoFill();
        ++mZ8InputGeneration;
        removeCallbacks(mZ8ShowSoftKeyboard);
        mZ8Input.resetScroll();
        mScroller.abortAnimation();
        mGestureRecognizer.cancel();
        forceStopTextSelectionMode();
        if (mZ8PasteDialog != null) mZ8PasteDialog.dismiss();

        if (mTextSelectionCursorController != null) {''')
    path.write_text(s)
    path=tree / 'terminal-view/src/main/java/com/termux/view/GestureAndScaleRecognizer.java'
    s=replace(path.read_text(), '    public boolean isInProgress() {', '''    /** Discard delayed long-press/tap work before another PTY is attached. */
    public void cancel() {
        long now = android.os.SystemClock.uptimeMillis();
        MotionEvent cancel = MotionEvent.obtain(now, now, MotionEvent.ACTION_CANCEL, 0, 0, 0);
        try { onTouchEvent(cancel); }
        finally { cancel.recycle(); }
        isAfterLongPress = false;
    }

    public boolean isInProgress() {''')
    path.write_text(s)
    path=tree / 'terminal-view/src/main/java/com/termux/view/textselection/TextSelectionCursorController.java'
    s=replace(path.read_text(), '''    public boolean hide() {
        if (!isActive()) return false;''', '''    public boolean hide() { return hide(false); }

    public boolean hide(boolean force) {
        if (!isActive()) return false;''')
    s=replace(s, '    private boolean mIsSelectingText = false;', '''    private boolean mIsSelectingText = false;
    private boolean mZ8MouseSelectionDragging;''')
    s=replace(s, '        if (System.currentTimeMillis() - mShowStartTime < 300) {', '        if (!force && System.currentTimeMillis() - mShowStartTime < 300) {')
    s=replace(s, '    public void setInitialTextSelectionPosition(MotionEvent event) {', '''    public void setMouseSelection(int[] range, boolean finished) {
        mSelX1 = range[0]; mSelY1 = range[1]; mSelX2 = range[2]; mSelY2 = range[3];
        mZ8MouseSelectionDragging = !finished;
        mIsSelectingText = true;
        mShowStartTime = 0;
        if (finished && mActionMode == null) setActionModeCallBacks();
        render();
    }

    public void finishMouseSelection() {
        mZ8MouseSelectionDragging = false;
        if (isActive() && mActionMode == null) setActionModeCallBacks();
        render();
    }

    public void setInitialTextSelectionPosition(MotionEvent event) {''')
    s=replace(s, '''                        terminalView.mTermSession.onCopyTextToClipboard(selectedText);
                        terminalView.stopTextSelectionMode();''', '''                        terminalView.mTermSession.onCopyTextToClipboard(selectedText);
                        terminalView.forceStopTextSelectionMode();''')
    s=replace(s, '''                    case ACTION_PASTE:
                        terminalView.stopTextSelectionMode();''', '''                    case ACTION_PASTE:
                        terminalView.forceStopTextSelectionMode();''')
    # Finished action mode must not keep a dead object that blocks future mouse selection menus.
    s=replace(s, '''        mSelX1 = mSelY1 = mSelX2 = mSelY2 = -1;
        mIsSelectingText = false;''', '''        mActionMode = null;
        mSelX1 = mSelY1 = mSelX2 = mSelY2 = -1;
        mZ8MouseSelectionDragging = false;
        mIsSelectingText = false;''')
    s=replace(s, '''        if (mActionMode != null) {
            mActionMode.invalidate();
        }''', '''        // Android can destroy a floating toolbar during app/window changes
        // while the terminal intentionally retains its selected range. Recreate
        // only after return, never underneath an ongoing pointer drag.
        if (mActionMode == null && !mZ8MouseSelectionDragging
                && !mStartHandle.isDragging() && !mEndHandle.isDragging()
                && terminalView.isShown() && terminalView.hasWindowFocus()) {
            setActionModeCallBacks();
        }
        if (mActionMode != null) mActionMode.invalidate();''')
    s=replace(s, '''            public void onDestroyActionMode(ActionMode mode) {
            }''', '''            public void onDestroyActionMode(ActionMode mode) {
                if (mActionMode == mode) {
                    mActionMode = null;
                    terminalView.invalidate();
                }
            }''')
    s=replace(s, '''            public void onDestroyActionMode(ActionMode mode) {
                // Ignore.
            }''', '''            public void onDestroyActionMode(ActionMode mode) {
                callback.onDestroyActionMode(mode);
            }''')
    s=replace(s, '''    public void onTouchModeChanged(boolean isInTouchMode) {
        if (!isInTouchMode) {
            terminalView.stopTextSelectionMode();
        }
    }''', '''    public void onTouchModeChanged(boolean isInTouchMode) {
        // A hardware modifier can leave Android touch mode before Cmd+C arrives.
        // Actual key handling dismisses the selection for ordinary typing; the
        // input-device transition itself must preserve a copyable range.
    }''')
    s=replace(s, '''    public void decrementYTextSelectionCursors(int decrement) {''', '''    /** A keyboard height change translates existing rows rather than reflowing columns. */
    public void onTerminalRowsResized(int rowShift) {
        if (!isActive()) return;
        int oldest = -terminalView.mEmulator.getScreen().getActiveTranscriptRows();
        int newest = terminalView.mEmulator.mRows - 1;
        mSelY1 = Math.max(oldest, Math.min(newest, mSelY1 - rowShift));
        mSelY2 = Math.max(mSelY1, Math.min(newest, mSelY2 - rowShift));
    }

    public void decrementYTextSelectionCursors(int decrement) {''')
    s=replace(s, '''                int terminalBottom = terminalView.getBottom();
                int top = y1 + mHandleHeight;
                int bottom = y2 + mHandleHeight;
                if (top > terminalBottom) top = terminalBottom;
                if (bottom > terminalBottom) bottom = terminalBottom;

                outRect.set(x1, top, x2, bottom);''', '''                // ActionMode asks for coordinates local to TerminalView. A range
                // extending into scrollback must not place its toolbar off-screen.
                int terminalBottom = terminalView.getHeight();
                int top = Math.max(0, Math.min(terminalBottom, y1 + mHandleHeight));
                int bottom = Math.max(top, Math.min(terminalBottom, y2 + mHandleHeight));
                int right = terminalView.getWidth();
                outRect.set(Math.max(0, Math.min(right, x1)), top,
                    Math.max(0, Math.min(right, x2)), bottom);''')
    s=replace(s, '''        final int scrollRows = screen.getActiveRows() - terminalView.mEmulator.mRows;
        if (handle == mStartHandle) {''', '''        final int scrollRows = screen.getActiveRows() - terminalView.mEmulator.mRows;
        if (!terminalView.mEmulator.isAlternateBufferActive()) {
            int top = terminalView.getTopRow();
            int direction = terminalView.z8SelectionScrollDirection(y);
            terminalView.setTopRow(Math.max(-scrollRows, Math.min(0, top + direction)));
        }
        // Preserve pointer capture while its endpoint remains a valid visible cell.
        y = Math.max(terminalView.mRenderer.getFontLineSpacing(), Math.min(terminalView.getHeight(), y));
        if (handle == mStartHandle) {''')
    for endpoint in ('1', '2'):
        s=replace(s, f'''            if (mSelX{endpoint} < 0) {{
                mSelX{endpoint} = 0;
            }}''', f'''            mSelX{endpoint} = Math.max(0, Math.min(terminalView.mEmulator.mColumns - 1, mSelX{endpoint}));''')
        start=s.index('            if (!terminalView.mEmulator.isAlternateBufferActive()) {', s.index(f'            mSelX{endpoint} = terminalView.getCursorX(x);'))
        end=s.index(f'            mSelX{endpoint} = getValidCurX', start)
        s=s[:start]+s[end:]
        s=replace(s, f'            mSelX{endpoint} = getValidCurX(screen, mSelY{endpoint}, mSelX{endpoint});',
            f'            mSelX{endpoint} = Math.min(terminalView.mEmulator.mColumns - 1, getValidCurX(screen, mSelY{endpoint}, mSelX{endpoint}));')
    s=replace(s, '            mSelX2 = terminalView.getCursorX(x);', '''            // End handles sit after the final selected cell; start handles sit
            // before the first. Invert that boundary without adding a character.
            mSelX2 = (int) Math.ceil((x - 0.5f) / terminalView.mRenderer.getFontWidth()) - 1;''')
    path.write_text(s)
    path=tree / 'terminal-view/src/main/java/com/termux/view/textselection/TextSelectionHandleView.java'
    s=path.read_text()
    s=replace(s, '        coords[1] += mPointY;', '        coords[1] += z8HandleTop();')
    s=replace(s, '                int y1 = coords[1] + mPointY;', '                int y1 = coords[1] + z8HandleTop();')
    s=replace(s, '    private void moveTo(int x, int y, boolean forceOrientationCheck) {', '''    /** Keep the whole grip above system gestures without moving its selected cell. */
    private int z8HandleTop() {
        Rect visible = new Rect();
        if (!terminalView.getLocalVisibleRect(visible)) return mPointY;
        int margin = Math.round(8 * getResources().getDisplayMetrics().density);
        int top = visible.top + margin;
        int bottom = Math.max(top, visible.bottom - mHandleHeight - margin);
        return Math.max(top, Math.min(bottom, mPointY));
    }

    private void moveTo(int x, int y, boolean forceOrientationCheck) {''')
    start=s.index('        final TerminalView hostView = terminalView;', s.index('    private void checkChangedOrientation('))
    end=s.index('        if (posX - mHandleWidth < clip.left)', start)
    s=s[:start]+'''        final TerminalView hostView = terminalView;
        if (mTempRect == null) mTempRect = new Rect();
        final Rect clip = mTempRect;
        if (!hostView.getLocalVisibleRect(clip)) return;

'''+s[end:]
    start=s.index('        final TerminalView hostView = terminalView;', s.index('    private boolean isPositionVisible()'))
    end=s.index('\n    @Override\n    public void onDraw', start)
    s=s[:start]+'''        if (mTempRect == null) mTempRect = new Rect();
        final Rect clip = mTempRect;
        if (!terminalView.getLocalVisibleRect(clip)) return false;
        final int posX = mPointX + (int) mHotspotX;
        final int posY = mPointY + (int) mHotspotY;
        return posX >= clip.left && posX <= clip.right && posY >= clip.top && posY <= clip.bottom;
    }
'''+s[end:]
    s=replace(s, '    private boolean mIsDragging;', '''    private boolean mIsDragging;
    private int mZ8DragX, mZ8DragY;
    private final Runnable mZ8EdgeScroll = new Runnable() {
        @Override public void run() {
            if (!mIsDragging || !mCursorController.isActive()) return;
            if (!terminalView.isShown() || !terminalView.hasWindowFocus()) return;
            int direction = terminalView.z8SelectionScrollDirection(mZ8DragY);
            int top = terminalView.getTopRow();
            int oldest = -terminalView.mEmulator.getScreen().getActiveTranscriptRows();
            boolean canScroll = !terminalView.mEmulator.isAlternateBufferActive()
                && (direction < 0 && top > oldest || direction > 0 && top < 0);
            if (!canScroll) return;
            mCursorController.updatePosition(TextSelectionHandleView.this, mZ8DragX, mZ8DragY);
            postDelayed(this, 48);
        }
    };''')
    s=replace(s, '''    public void hide() {
        mIsDragging = false;''', '''    public void hide() {
        mIsDragging = false;
        removeCallbacks(mZ8EdgeScroll);''')
    s=replace(s, '                mTouchToWindowOffsetY = rawY - mPointY;', '''                // Account for the same grip offset used on MOVE so a stationary
                // first move does not jump the endpoint into the preceding row.
                mTouchToWindowOffsetY = rawY - mPointY + mHotspotY + mTouchOffsetY;''')
    s=replace(s, '''                mCursorController.updatePosition(this, Math.round(newPosX), Math.round(newPosY));''', '''                mZ8DragX = Math.round(newPosX);
                mZ8DragY = Math.round(newPosY);
                mCursorController.updatePosition(this, mZ8DragX, mZ8DragY);
                removeCallbacks(mZ8EdgeScroll);
                postDelayed(mZ8EdgeScroll, 48);''')
    s=replace(s, '''            case MotionEvent.ACTION_CANCEL:
                mIsDragging = false;''', '''            case MotionEvent.ACTION_CANCEL:
                mIsDragging = false;
                removeCallbacks(mZ8EdgeScroll);''')
    path.write_text(s)
    path=tree / 'app/src/main/java/com/termux/app/terminal/TermuxTerminalSessionActivityClient.java'
    s=replace(path.read_text(), '            mActivity.getTerminalView().mEmulator.paste(text);', '''            if (session == mActivity.getCurrentSession()) mActivity.getTerminalView().pasteText(text);''')
    path.write_text(s)
    path=tree / 'app/src/main/java/com/termux/app/terminal/TermuxTerminalViewClient.java'
    s = replace(path.read_text(), '            session.getEmulator().paste(text);', '            mActivity.getTerminalView().pasteText(text);')
    s = replace(s, '        if (mActivity.getProperties().shouldOpenTerminalTranscriptURLOnClick()) {',
        '        if (!term.isMouseTrackingActive() && mActivity.getProperties().shouldOpenTerminalTranscriptURLOnClick()) {')
    s = replace(s, '''        if (!term.isMouseTrackingActive() && !e.isFromSource(InputDevice.SOURCE_MOUSE)) {
            if (!KeyboardUtils.areDisableSoftKeyboardFlagsSet(mActivity))
                KeyboardUtils.showSoftKeyboard(mActivity, mActivity.getTerminalView());
            else
                Logger.logVerbose(LOG_TAG, "Not showing soft keyboard onSingleTapUp since its disabled");
        }''', '''        if (!e.isFromSource(InputDevice.SOURCE_MOUSE) && !e.isFromSource(InputDevice.SOURCE_TOUCHPAD)
                && mActivity.getPreferences().isSoftKeyboardEnabled()) {
            // A finger tap is an explicit keyboard request, even with an external
            // keyboard or a TUI mouse protocol. Clear stale fold/hardware flags;
            // the user's explicit disabled preference remains respected.
            KeyboardUtils.clearDisableSoftKeyboardFlags(mActivity);
            KeyboardUtils.setSoftInputModeAdjustResize(mActivity);
            mActivity.getTerminalView().z8ShowSoftKeyboard();
        }''')
    path.write_text(s)


TOUCH = '''    @Override
    public android.view.PointerIcon onResolvePointerIcon(MotionEvent event, int pointerIndex) {
        return android.view.PointerIcon.getSystemIcon(getContext(), android.view.PointerIcon.TYPE_TEXT);
    }

    @SuppressLint("ClickableViewAccessibility")
    @Override
    @TargetApi(23)
    public boolean onTouchEvent(MotionEvent event) {
        if (mEmulator == null) return true;
        if (event.isFromSource(InputDevice.SOURCE_MOUSE)) return z8MouseEvent(event);
        if (isSelectingText()) updateFloatingToolbarVisibility(event);
        mGestureRecognizer.onTouchEvent(event);
        return true;
    }

    private boolean z8MouseEvent(MotionEvent event) {
        final int action = event.getActionMasked();
        if (action == MotionEvent.ACTION_CANCEL) {
            // Complete the original reporting gesture so a TUI does not retain a held button.
            if (mZ8MouseTracking && mZ8MouseButton == MotionEvent.BUTTON_PRIMARY)
                sendMouseEventCode(event, TerminalEmulator.MOUSE_LEFT_BUTTON, false);
            forceStopTextSelectionMode(); mZ8MouseButton = 0; mZ8MouseTracking = false;
            return true;
        }
        if (action == MotionEvent.ACTION_DOWN) {
            requestFocus();
            mZ8MouseButton = event.isButtonPressed(MotionEvent.BUTTON_SECONDARY) ? MotionEvent.BUTTON_SECONDARY
                : event.isButtonPressed(MotionEvent.BUTTON_TERTIARY) ? MotionEvent.BUTTON_TERTIARY : MotionEvent.BUTTON_PRIMARY;
            if (mZ8MouseButton == MotionEvent.BUTTON_SECONDARY) { showContextMenu(); return true; }
            if (mZ8MouseButton == MotionEvent.BUTTON_TERTIARY) {
                // All paste paths share the same multiline confirmation. MOVE never pastes again.
                mTermSession.onPasteTextFromClipboard(); return true;
            }
            forceStopTextSelectionMode();
            mZ8MouseTracking = mEmulator.isMouseTrackingActive() && (event.getMetaState() & KeyEvent.META_SHIFT_ON) == 0;
            if (!mZ8MouseTracking) {
                int[] cell = z8MouseCell(event);
                mZ8Input.begin(cell[0], cell[1]);
            }
        }
        if (mZ8MouseButton != MotionEvent.BUTTON_PRIMARY) {
            if (action == MotionEvent.ACTION_UP) mZ8MouseButton = 0;
            return true;
        }
        if (mZ8MouseTracking) {
            if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_UP)
                sendMouseEventCode(event, TerminalEmulator.MOUSE_LEFT_BUTTON, action == MotionEvent.ACTION_DOWN);
            else if (action == MotionEvent.ACTION_MOVE && event.isButtonPressed(MotionEvent.BUTTON_PRIMARY))
                sendMouseEventCode(event, TerminalEmulator.MOUSE_LEFT_BUTTON_MOVED, true);
        } else if (mZ8Input.isDragging() && (action == MotionEvent.ACTION_MOVE || action == MotionEvent.ACTION_UP)) {
            if (event.getY() < 0) setTopRow(Math.max(-mEmulator.getScreen().getActiveTranscriptRows(), mTopRow - 1));
            else if (event.getY() >= getHeight()) setTopRow(Math.min(0, mTopRow + 1));
            int[] cell = z8MouseCell(event);
            int[] range = mZ8Input.range(cell[0], cell[1]);
            if (range != null) {
                getTextSelectionCursorController().setMouseSelection(range, action == MotionEvent.ACTION_UP);
                mClient.copyModeChanged(true);
                invalidate();
            } else if (action == MotionEvent.ACTION_UP && isSelectingText()) {
                getTextSelectionCursorController().finishMouseSelection();
            }
        }
        if (action == MotionEvent.ACTION_UP) {
            mZ8Input.finish(); mZ8MouseButton = 0; mZ8MouseTracking = false;
        }
        return true;
    }

    private int[] z8MouseCell(MotionEvent event) {
        int[] cell = getColumnAndRow(event, true);
        cell[0] = Math.max(0, Math.min(mEmulator.mColumns - 1, cell[0]));
        cell[1] = Math.max(-mEmulator.getScreen().getActiveTranscriptRows(), Math.min(mEmulator.mRows - 1, cell[1]));
        return cell;
    }
'''

HELPERS = r'''    /** Allow a held grip to scroll before the finger reaches system gesture edges. */
    public int z8SelectionEdgeSize() {
        int touch = Math.round(48 * getResources().getDisplayMetrics().density);
        int lines = 2 * mRenderer.getFontLineSpacing();
        // A short IME-resized viewport still needs a neutral region in its middle.
        return Math.min(Math.max(1, getHeight() / 3), Math.max(touch, lines));
    }

    /** The handle and repeated scroll must use the same visible viewport after clipping. */
    public int z8SelectionScrollDirection(int y) {
        Rect visible = new Rect();
        if (!getLocalVisibleRect(visible)) return 0;
        int top = Math.max(0, visible.top);
        int bottom = Math.min(getHeight(), visible.bottom);
        if (bottom <= top) return 0;
        int edge = Math.min(Math.max(1, (bottom - top) / 3), z8SelectionEdgeSize());
        return y <= top + edge ? -1 : y >= bottom - edge ? 1 : 0;
    }

    /** Invalidate pending IME work before an external app or another pane owns input. */
    public void z8SuspendInput() {
        mZ8InputSuspended = true;
        cancelRequestAutoFill();
        ++mZ8InputGeneration;
        removeCallbacks(mZ8ShowSoftKeyboard);
        mCombiningAccent = 0;
        mScroller.abortAnimation();
        mGestureRecognizer.cancel();
        mZ8Input.finish();
    }

    /** Reconnect the visible live PTY without sending keys, starting a command or showing the IME. */
    public void z8ResumeInput() {
        mZ8InputSuspended = false;
        ++mZ8InputGeneration;
        mCombiningAccent = 0;
        mZ8Input.resetScroll();
        mScroller.abortAnimation();
        mGestureRecognizer.cancel();
        mZ8MouseButton = 0;
        mZ8MouseTracking = false;
        updateSize();
        // Keep deliberate history reading/copy selection on return. The first
        // actual typed/pasted input follows the live cursor through z8FollowInput.
        onScreenUpdated(true);
        z8RestartInput();
    }

    private void z8RestartInput() {
        if (mZ8InputSuspended || !isFocused() || !isShown()) return;
        android.view.inputmethod.InputMethodManager manager =
            (android.view.inputmethod.InputMethodManager) getContext().getSystemService(Context.INPUT_METHOD_SERVICE);
        if (manager != null) manager.restartInput(this);
    }

    /** Explicit touch only: reconnect after focus settles, then request an IME. */
    public void z8ShowSoftKeyboard() {
        if (mZ8InputSuspended || mTermSession == null || !mTermSession.isRunning()
                || !isShown() || !hasWindowFocus() || isSelectingText()) return;
        requestFocus();
        removeCallbacks(mZ8ShowSoftKeyboard);
        post(mZ8ShowSoftKeyboard);
    }

    private void z8ShowSoftKeyboardAfterFocus() {
        if (mZ8InputSuspended || mTermSession == null || !mTermSession.isRunning()
                || !isFocused() || !isShown() || !hasWindowFocus() || isSelectingText()) return;
        android.view.inputmethod.InputMethodManager manager =
            (android.view.inputmethod.InputMethodManager) getContext().getSystemService(Context.INPUT_METHOD_SERVICE);
        if (manager != null) {
            // Repeated taps on an already served editor must preserve Korean
            // composition. Reconnect only if the fold/focus transition lost it.
            if (!manager.isActive(this)) manager.restartInput(this);
            manager.showSoftInput(this, 0);
        }
    }

    /** Typed/pasted input belongs to the live screen even while output scrolling is paused. */
    private void z8FollowInput() {
        if (mEmulator == null) return;
        mScroller.abortAnimation();
        if (mTopRow != 0) {
            setTopRow(0);
            invalidate();
        }
    }

    /** Android may dispatch external keyboard chords through either shortcut or key-down. */
    @Override
    public boolean onKeyShortcut(int keyCode, KeyEvent event) {
        return z8HandleClipboardShortcut(keyCode, event) || super.onKeyShortcut(keyCode, event);
    }

    private boolean z8HandleClipboardShortcut(int keyCode, KeyEvent event) {
        char key = keyCode == KeyEvent.KEYCODE_C ? 'c' : keyCode == KeyEvent.KEYCODE_V ? 'v' : 0;
        Z8TerminalInput.ClipboardShortcut shortcut = Z8TerminalInput.clipboardShortcut(key,
            event.isMetaPressed(), event.isCtrlPressed(), event.isShiftPressed(), event.isAltPressed());
        if (shortcut == Z8TerminalInput.ClipboardShortcut.NONE) return false;
        // Recognized copy chords are consumed even with no selection. In particular,
        // Meta+C must never fall through to terminal bytes or a Ctrl+C interrupt.
        if (event.getRepeatCount() != 0 || mTermSession == null || mEmulator == null) return true;
        if (shortcut == Z8TerminalInput.ClipboardShortcut.COPY) {
            if (isSelectingText()) {
                mTermSession.onCopyTextToClipboard(getSelectedText());
                forceStopTextSelectionMode();
            }
        } else mTermSession.onPasteTextFromClipboard();
        return true;
    }

    /** Accessibility may be enabled after this view was created (TalkBack, automation, etc.). */
    private void z8RefreshAccessibilityText() {
        if (mZ8AccessibilityManager != null && mZ8AccessibilityManager.isEnabled() && mEmulator != null)
            setContentDescription(getText());
        else if (getContentDescription() != null)
            setContentDescription(null);
    }

    /** Session switches cannot retain coordinates, handles or callbacks from another PTY. */
    public void forceStopTextSelectionMode() {
        mZ8Input.finish();
        removeCallbacks(mShowFloatingToolbar);
        if (mTextSelectionCursorController != null) {
            mTextSelectionCursorController.hide(true);
            mTextSelectionCursorController.unsetStoredSelectedText();
        }
        if (mClient != null) mClient.copyModeChanged(false);
        invalidate();
    }

    /** App menu, selection toolbar, mouse, shortcut and bulk IME paste converge here. */
    public void pasteText(String text) {
        final TerminalSession target = mTermSession;
        final TerminalEmulator emulator = mEmulator;
        if (text == null || target == null || emulator == null || !target.isRunning() || mZ8InputSuspended) return;
        if (mZ8PasteDialog != null) return;
        forceStopTextSelectionMode();
        if (!Z8TerminalInput.requiresPasteConfirmation(text)) { z8FollowInput(); emulator.paste(text); return; }
        int lines = text.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1).length;
        // Preview is bounded and strips non-printing controls; no clipboard data is logged or persisted.
        String preview = text.substring(0, Math.min(600, text.length())).replace("\r\n", "\n").replace('\r', '\n')
            .replaceAll("[\\p{Cc}&&[^\\n\\t]]", "");
        android.app.AlertDialog dialog = new android.app.AlertDialog.Builder(
                new android.view.ContextThemeWrapper(getContext(), android.R.style.Theme_Material_Dialog_Alert))
            .setTitle("여러 줄 붙여넣기")
            .setMessage(lines + "줄을 붙여넣습니다. 줄바꿈이 명령을 실행할 수 있습니다.\n\n" + preview
                + (text.length() > 600 ? "\n…" : ""))
            .setNegativeButton("취소", null)
            .setPositiveButton("붙여넣기", (unused, which) -> {
                // A response to a dialog belongs only to the original still-attached live PTY.
                if (mTermSession == target && mEmulator == emulator && target.isRunning() && !mZ8InputSuspended) {
                    z8FollowInput();
                    emulator.paste(text);
                }
            }).create();
        mZ8PasteDialog = dialog;
        dialog.setOnDismissListener(unused -> { if (mZ8PasteDialog == dialog) mZ8PasteDialog = null; });
        dialog.show();
    }
'''
