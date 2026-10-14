package com.samthedev.pocket2droid;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

final class FrameProtocol {
    static final int SIZE = 64 + 1024 * 800 * 4;
    static final class Header {
        final int width, height;
        final long sequence;
        Header(int w, int h, long s) { width = w; height = h; sequence = s; }
    }
    static Header parse(ByteBuffer raw) {
        if (raw.capacity() < 64) throw new IllegalArgumentException("Short frame header");
        ByteBuffer b = raw.duplicate().order(ByteOrder.LITTLE_ENDIAN);
        int magic = b.getInt(0);
        if (magic == 0) return null; // Producer has not published its first image.
        int w = b.getInt(8), h = b.getInt(12);
        long seq = b.getLong(24);
        if (magic != 0x46443250 || b.getInt(4) != 1 || b.getInt(16) != 1 ||
            w < 1 || w > 1024 || h < 1 || h > 800 || seq <= 0)
            throw new IllegalArgumentException("Invalid frame protocol");
        return new Header(w, h, seq);
    }
    static int[] touch(float x, float y, int vw, int vh, int gw, int gh) {
        if (vw <= 0 || vh <= 0 || gw <= 0 || gh <= 0) return null;
        float scale = Math.min((float)vw / gw, (float)vh / gh);
        float left = (vw - gw * scale) / 2, top = (vh - gh * scale) / 2;
        x = (x - left) / scale; y = (y - top) / scale;
        if (x < 0 || y < 0 || x >= gw || y >= gh) return null;
        return new int[]{(int)x, (int)y};
    }
}
