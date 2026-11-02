package com.termux.view;

/** A file opens only after one short, unmoved, single-pointer release. */
public final class Z8FileLinkGesture {
    private long down = -1, consumed = -1;
    private float x, y;
    private boolean eligible;

    public void begin(long time, float x, float y, boolean selecting, boolean primary) {
        down = time; this.x = x; this.y = y; eligible = !selecting && primary;
    }
    public void move(float x, float y, int pointers, float slop) {
        if (pointers != 1 || Math.abs(x - this.x) > slop || Math.abs(y - this.y) > slop) eligible = false;
    }
    public void cancel() { eligible = false; }
    public void reset() { eligible = false; down = consumed = -1; }
    public boolean tap(long downTime, long now, long longPressTimeout, boolean selecting) {
        return eligible && downTime == down && !selecting && now >= down && now - down < longPressTimeout;
    }
    public void consumed(long downTime) { consumed = downTime; eligible = false; }
    public boolean wasConsumed(long downTime) { return consumed >= 0 && consumed == downTime; }
}
