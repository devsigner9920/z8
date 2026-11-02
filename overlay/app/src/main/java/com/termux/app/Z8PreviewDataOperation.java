package com.termux.app;

import java.util.ArrayList;
import java.util.List;

/** Main-thread operation shared by settings and preview. Completion belongs to the provider callback. */
final class Z8PreviewDataOperation {
    enum State { IDLE, RUNNING, COMPLETE, UNSUPPORTED, FAILED }
    interface Backend {
        boolean supported();
        void stopPreviews();
        void delete(Runnable completed);
    }
    private final Backend backend;
    private final List<Runnable> observers = new ArrayList<>();
    private State state = State.IDLE;
    private int generation;

    Z8PreviewDataOperation(Backend backend) { this.backend = backend; }
    State state() { return state; }
    boolean running() { return state == State.RUNNING; }
    void observe(Runnable observer) { if (!observers.contains(observer)) observers.add(observer); }
    void forget(Runnable observer) { observers.remove(observer); }

    boolean start() {
        if (running()) return false;
        final int request = ++generation;
        try {
            if (!backend.supported()) { change(State.UNSUPPORTED); return false; }
            // The gate closes before stopping renderers, so none can reload while deletion runs.
            change(State.RUNNING);
            backend.stopPreviews();
            backend.delete(() -> {
                if (request == generation && state == State.RUNNING) change(State.COMPLETE);
            });
            return true;
        } catch (RuntimeException failure) {
            // Never expose provider exception text, URLs or filesystem paths.
            if (request == generation && state != State.COMPLETE) change(State.FAILED);
            return false;
        }
    }

    private void change(State next) {
        state = next;
        for (Runnable observer : new ArrayList<>(observers)) {
            try { observer.run(); } catch (RuntimeException ignored) { /* A detached UI cannot cancel deletion. */ }
        }
    }
}
