package com.samsixx.pocket2droid;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.channels.FileLock;

final class FrameProtocol {
    // Initial allocation retained for older sessions; larger frames grow on demand.
    static final int SIZE = 64 + 1024 * 800 * 4;
    static int frameBytes(int width,int height) {
        if(width<1||height<1||(long)width*height>(Integer.MAX_VALUE-64)/4)
            throw new IllegalArgumentException("Resolution exceeds this platform's addressable frame-buffer memory");
        return 64+width*height*4;
    }
    static void initialize(RandomAccessFile file,int width,int height)throws IOException {
        int bytes=Math.max(SIZE,frameBytes(width,height));
        try(FileLock lock=file.getChannel().lock(0,Long.MAX_VALUE,false)) {
            // A reader can still own an old mapping during restart. Never shrink it.
            if(file.length()<bytes)file.setLength(bytes);
            file.seek(0);file.write(new byte[64]);
        }
    }
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
            w < 1 || h < 1 || seq <= 0 || frameBytes(w,h)>raw.capacity())
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
