package com.samthedev.pocket2droid;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class FrontendTest {
    static void check(boolean ok) { if (!ok) throw new AssertionError(); }
    static void rejects(Runnable r) {
        try { r.run(); } catch (IllegalArgumentException expected) { return; }
        throw new AssertionError("Expected rejection");
    }
    public static void main(String[] args) throws Exception {
        ByteBuffer b = ByteBuffer.allocate(64).order(ByteOrder.LITTLE_ENDIAN);
        check(FrameProtocol.parse(b) == null);
        b.putInt(0, 0x46443250); b.putInt(4, 1); b.putInt(8, 240);
        b.putInt(12, 320); b.putInt(16, 1); b.putLong(24, 7);
        FrameProtocol.Header h = FrameProtocol.parse(b);
        check(h.width == 240 && h.height == 320 && h.sequence == 7);
        b.putInt(8, 1025); rejects(() -> FrameProtocol.parse(b));
        b.putInt(8, 240); b.putInt(16, 2); rejects(() -> FrameProtocol.parse(b));
        b.putInt(16, 1); rejects(() -> FrameProtocol.parse(ByteBuffer.allocate(31)));
        int[] xy = FrameProtocol.touch(150, 200, 300, 600, 240, 320);
        check(xy[0] == 120 && xy[1] == 80);
        check(FrameProtocol.touch(150, 50, 300, 600, 240, 320) == null);
        PresentationRate rate = new PresentationRate();
        rate.reset(1_000_000_000L);
        rate.presented(1, 1_500_000_000L);
        rate.presented(1, 1_600_000_000L); // Same sequence must not count.
        rate.presented(5, 1_700_000_000L); // Skipped publications count once.
        check(Math.abs(rate.sample(2_000_000_000L) - 2.0) < 0.0001);
        check(rate.sample(4_000_000_000L) == 0);
        rate.reset(5_000_000_000L); // Resume must not inherit paused elapsed time.
        rate.presented(6, 5_500_000_000L);
        check(Math.abs(rate.sample(6_000_000_000L) - 1.0) < 0.0001);
        for (int i = 0; i < 300; i++) rate.presented(10 + i, 6_000_000_000L + i * 16_666_667L);
        check(rate.sample(10_980_000_000L) > 59 && rate.sample(10_980_000_000L) < 61);
        try {
            StorageSync.flush(new java.io.FileDescriptor());
            throw new AssertionError("Invalid descriptor must not report sync success");
        } catch (java.io.SyncFailedException expected) { }
        System.out.println("PASS header validation, touch mapping, duplicate/skipped presentations, pause, rolling rate");
        long start = System.nanoTime();
        for (int i = 0; i < 1_000_000; i++) rate.presented(1000L + i, 20_000_000_000L + i * 16_666_667L);
        long elapsed = System.nanoTime() - start;
        System.out.println("Host accounting ns/presentation=" + elapsed / 1_000_000.0 + " (not Android overhead)");
    }
}
