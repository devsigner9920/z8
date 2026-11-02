"""Explicit HTML touch links applied after input fixes, against the pinned source."""

def patch(tree, replace):
    path = tree / 'terminal-view/src/main/java/com/termux/view/TerminalViewClient.java'
    s = path.read_text()
    s = replace(s, '    void onSingleTapUp(MotionEvent e);', '''    void onSingleTapUp(MotionEvent e);

    /** Consume an explicit local HTML-file tap before forwarding a TUI mouse click. */
    default boolean onOpenFileLink(MotionEvent e) { return false; }''')
    path.write_text(s)
    path = tree / 'app/src/main/java/com/termux/app/terminal/TermuxTerminalViewClient.java'
    s = path.read_text()
    s = replace(s, '    public void onSingleTapUp(MotionEvent e) {', '''    public boolean onOpenFileLink(MotionEvent e) {
        return com.termux.app.Z8TerminalLinks.openAt(mActivity, e);
    }

    @Override
    public void onSingleTapUp(MotionEvent e) {''')
    path.write_text(s)
    path = tree / 'terminal-view/src/main/java/com/termux/view/TerminalView.java'
    s = path.read_text()
    s = replace(s, '    private int mZ8MouseButton;', '    private int mZ8MouseButton;\n    private final Z8FileLinkGesture mZ8FileLinks = new Z8FileLinkGesture();')
    s = replace(s, '''            public boolean onUp(MotionEvent event) {
                mScrollRemainder = 0.0f;''', '''            public boolean onUp(MotionEvent event) {
                mScrollRemainder = 0.0f;
                if (mEmulator != null && !event.isFromSource(InputDevice.SOURCE_MOUSE)
                        && !isSelectingText() && !scrolledWithFinger && z8FileLinkTap(event) && mClient.onOpenFileLink(event)) {
                    // A native file link must not also select a Codex row or open its keyboard.
                    mZ8FileLinks.consumed(event.getDownTime());
                    return true;
                }''')
    s = replace(s, '''            public boolean onSingleTapUp(MotionEvent event) {
                if (mEmulator == null) return true;''', '''            public boolean onSingleTapUp(MotionEvent event) {
                if (mZ8FileLinks.wasConsumed(event.getDownTime())) return true;
                if (mEmulator == null) return true;''')
    s = replace(s, "            public boolean onDown(float x, float y) {", """            public boolean onDown(float x, float y) {
                scrolledWithFinger = false;""")
    # Ordinary mouse click without a drag is a link; an actual drag remains native copy.
    s = replace(s, '''            } else if (action == MotionEvent.ACTION_UP && isSelectingText()) {
                getTextSelectionCursorController().finishMouseSelection();
            }''', '''            } else if (action == MotionEvent.ACTION_UP && isSelectingText()) {
                getTextSelectionCursorController().finishMouseSelection();
            } else if (action == MotionEvent.ACTION_UP && z8FileLinkTap(event)) {
                if (mClient.onOpenFileLink(event)) mZ8FileLinks.consumed(event.getDownTime());
            }''')
    s = replace(s, "        mTermSession = session;", "        mZ8FileLinks.reset();\n        mTermSession = session;")
    s = replace(s, "    public boolean onTouchEvent(MotionEvent event) {", """    public boolean onTouchEvent(MotionEvent event) {
        int z8Action = event.getActionMasked();
        if (z8Action == MotionEvent.ACTION_DOWN) {
            boolean primary = !event.isFromSource(InputDevice.SOURCE_MOUSE) || event.isButtonPressed(MotionEvent.BUTTON_PRIMARY);
            mZ8FileLinks.begin(event.getDownTime(), event.getX(), event.getY(), isSelectingText(), primary);
        } else if (z8Action == MotionEvent.ACTION_POINTER_DOWN || z8Action == MotionEvent.ACTION_CANCEL) {
            mZ8FileLinks.cancel();
        } else {
            mZ8FileLinks.move(event.getX(), event.getY(), event.getPointerCount(),
                android.view.ViewConfiguration.get(getContext()).getScaledTouchSlop());
        }""")
    s = replace(s, "    private boolean z8MouseEvent(MotionEvent event) {", """    private boolean z8FileLinkTap(MotionEvent event) {
        return mZ8FileLinks.tap(event.getDownTime(), event.getEventTime(),
            android.view.ViewConfiguration.getLongPressTimeout(), isSelectingText());
    }

    private boolean z8MouseEvent(MotionEvent event) {""")
    s = replace(s, "    public void z8SuspendInput() {", "    public void z8SuspendInput() {\n        mZ8FileLinks.cancel();")
    path.write_text(s)
