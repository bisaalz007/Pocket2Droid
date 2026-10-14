package com.samthedev.pocket2droid;
import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.util.Arrays;
public final class AudioProtocolTest {
    static void check(boolean b) { if (!b) throw new AssertionError("Audio protocol behavior"); }
    static ByteBuffer packet() {
        ByteBuffer b=ByteBuffer.allocate(67648).order(ByteOrder.LITTLE_ENDIAN);
        AudioProtocol.initialize(b);
        b.putInt(20,1);b.putInt(28,8);b.putInt(36,7);b.putInt(44,1);
        b.putInt(64,7);b.putInt(68,48000);b.putInt(72,2);b.putInt(76,0);b.putLong(80,1000000000L);
        b.putShort(2112,(short)32767);b.putShort(2114,(short)-32768);b.putShort(2116,(short)123);b.putShort(2118,(short)-456);
        return b;
    }
    public static void main(String[] args) throws Exception {
        short[] pcm=new short[4096];AudioProtocol.Packet p=new AudioProtocol.Packet();
        ByteBuffer b=packet();check(AudioProtocol.read(b,pcm,p,1010000000L)==2);
        check(Arrays.equals(Arrays.copyOf(pcm,4),new short[]{32767,-32768,123,-456}));check(p.rate==48000&&p.epoch==7);
        check(AudioProtocol.read(b,pcm,p,1010000000L)==0);
        b=packet();check(AudioProtocol.read(b,pcm,p,1300000000L)==0);
        for(int[] bad:new int[][]{{0,37},{20,65},{28,65540},{72,2049},{68,0},{76,4},{44,9}}) {
            b=packet();b.putInt(bad[0],bad[1]);boolean rejected=false;
            try { AudioProtocol.read(b,pcm,p,1010000000L); }catch(IOException expected){rejected=true;}check(rejected);
        }
        if(args.length==2) {
            File f=new File(args[0]);try(RandomAccessFile file=new RandomAccessFile(f,"rw");FileChannel ch=file.getChannel()) {
                file.setLength(67648);ByteBuffer m=ch.map(FileChannel.MapMode.READ_WRITE,0,67648);AudioProtocol.initialize(m);
                Process child=new ProcessBuilder(args[1],f.getPath(),"1").inheritIO().start();check(child.waitFor()==0);
                try(FileLock lock=ch.tryLock()){check(lock!=null);check(AudioProtocol.read(m,pcm,p,System.nanoTime())==2);}
                check(Arrays.equals(Arrays.copyOf(pcm,4),new short[]{32767,-32768,123,-456}));
                try(FileLock lock=ch.tryLock()){Process blocked=new ProcessBuilder(args[1],f.getPath(),"1").start();check(blocked.waitFor()==2);}
            }
        }
        System.out.println("PASS actual audio protocol values, malformed packets, stale queue and C/Java locking");
    }
}
