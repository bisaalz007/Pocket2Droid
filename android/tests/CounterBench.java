package com.samthedev.pocket2droid;

/** Temporary ART accounting benchmark, never packaged in the user APK. */
public final class CounterBench {
    private static volatile long sink;
    public static void main(String[] args) {
        PresentationRate rate = new PresentationRate();
        rate.reset(System.nanoTime());
        for (int i=0; i<2_000_000; i++) rate.presented(i+1, System.nanoTime());
        for (int trial=0; trial<3; trial++) {
            long started=System.nanoTime();
            for (int i=0; i<1_000_000; i++) rate.presented(10_000_000L+trial*1_000_000L+i, System.nanoTime());
            long elapsed=System.nanoTime()-started;
            System.out.println("accounting+clock ns/presentation="+elapsed/1_000_000.0);
            sink=elapsed;
        }
        System.out.println("This measures ART accounting plus clock; Android text/layout cost is separate.");
    }
}
