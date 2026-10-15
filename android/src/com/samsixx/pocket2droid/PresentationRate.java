package com.samsixx.pocket2droid;

/** Frontend-only accounting. No guest hooks, framebuffer reads or logging. */
final class PresentationRate {
    private final long[] times = new long[256];
    private int head, count;
    private long started, lastSequence;
    synchronized void reset(long now) { head = count = 0; started = now; lastSequence = 0; }
    synchronized void presented(long sequence, long now) {
        if (sequence <= 0 || sequence == lastSequence) return;
        lastSequence = sequence;
        if (count == times.length) { head = (head + 1) % times.length; count--; }
        times[(head + count++) % times.length] = now;
    }
    synchronized double sample(long now) {
        long cutoff = now - 2_000_000_000L;
        while (count > 0 && times[head] <= cutoff) { head = (head + 1) % times.length; count--; }
        long elapsed = Math.min(now - started, 2_000_000_000L);
        return elapsed <= 0 ? 0 : count * 1_000_000_000.0 / elapsed;
    }
}
