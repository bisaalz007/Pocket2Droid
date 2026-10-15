package com.samsixx.pocket2droid;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
final class AudioProtocol {
    static final int SIZE=67648, PCM=2112, CAP=65536, MAX_FRAMES=2048;
    static final long MAX_NS=200000000L;
    static final class Packet { int frames,rate,epoch;long publishedNs; }
    static long distance(int a,int b){return Integer.toUnsignedLong(a-b);}
    static void initialize(ByteBuffer b) {
        if(b.capacity()!=SIZE)throw new IllegalArgumentException("Wrong audio buffer size");
        b.order(ByteOrder.LITTLE_ENDIAN);
        for(int i=0;i<SIZE;i++)b.put(i,(byte)0);
        b.putInt(0,0x41443250);b.putInt(4,1);b.putInt(8,SIZE);b.putInt(12,64);b.putInt(16,CAP);
    }
    static long validate(ByteBuffer b,long now) throws IOException {
        if(b.capacity()!=SIZE)throw new IOException("Wrong audio buffer size");
        b.order(ByteOrder.LITTLE_ENDIAN);
        if(b.getInt(0)!=0x41443250||b.getInt(4)!=1||b.getInt(8)!=SIZE||b.getInt(12)!=64||b.getInt(16)!=CAP||
           b.getInt(44)<0||b.getInt(44)>3)throw new IOException("Invalid audio header");
        int wp=b.getInt(20),rp=b.getInt(24),wb=b.getInt(28),rb=b.getInt(32);
        long count=distance(wp,rp),duration=0;
        if(count>64||distance(wb,rb)>CAP||((wb|rb)&3)!=0)throw new IOException("Invalid audio counters");
        for(int i=0;i<count;i++) {
            int p=64+((rp+i)&63)*32,frames=b.getInt(p+8),rate=b.getInt(p+4);long time=b.getLong(p+16);
            if(frames<1||frames>MAX_FRAMES||rate<8000||rate>192000||b.getInt(p+12)!=rb||
               b.getInt(p)!=b.getInt(36)||time<=0||time>now+1000000000L||b.getLong(p+24)!=0)
                throw new IOException("Invalid audio packet");
            rb+=frames*4;duration+=(long)frames*1000000000L/rate;
        }
        if(rb!=wb)throw new IOException("Invalid audio byte count");
        return duration;
    }
    static void flush(ByteBuffer b) { b.putInt(24,b.getInt(20));b.putInt(32,b.getInt(28)); }
    static int read(ByteBuffer b,short[] dest,Packet out,long now) throws IOException {
        long duration=validate(b,now);
        while(b.getInt(20)!=b.getInt(24)) {
            int rp=b.getInt(24),p=64+(rp&63)*32,frames=b.getInt(p+8),rate=b.getInt(p+4),start=b.getInt(p+12);
            long time=b.getLong(p+16);
            if(time>now||now-time>MAX_NS||duration>MAX_NS) {
                b.putInt(24,rp+1);b.putInt(32,start+frames*4);duration-=(long)frames*1000000000L/rate;continue;
            }
            if(dest.length<frames*2)throw new IOException("Audio destination too small");
            for(int i=0;i<frames*2;i++)dest[i]=b.getShort(PCM+((start+i*2)&(CAP-1)));
            out.frames=frames;out.rate=rate;out.epoch=b.getInt(p);out.publishedNs=time;
            b.putInt(24,rp+1);b.putInt(32,start+frames*4);return frames;
        }
        out.frames=0;return 0;
    }
}
