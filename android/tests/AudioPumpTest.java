package com.samsixx.pocket2droid;
import java.util.*;
public final class AudioPumpTest {
    static void check(boolean v){if(!v)throw new AssertionError("Playback contract");}
    static final class Sink implements AudioPump.Sink {
        final List<Short> accepted=new ArrayList<>();int limit=2,writes,flushes,recreations,closed;boolean fail,only48000;
        public boolean configure(int rate,int ms){recreations++;return !only48000||rate==48000;}
        public int write(short[] v,int off,int count){writes++;if(fail)return -6;int n=Math.min(limit,count);for(int i=0;i<n;i++)accepted.add(v[off+i]);return n;}
        public void flush(){flushes++;}public void close(){closed++;}
    }
    public static void main(String[] args) {
        Sink s=new Sink();List<String> messages=new ArrayList<>();AudioPump p=new AudioPump(s,messages::add);p.active(true);
        AudioProtocol.Packet packet=new AudioProtocol.Packet();packet.frames=2;packet.rate=48000;packet.epoch=1;packet.publishedNs=1000000000;
        p.accept(packet,new short[]{32767,-32768,123,-456});check(p.step(1010000000));check(p.step(1010000000));
        check(s.accepted.equals(Arrays.asList((short)32767,(short)-32768,(short)123,(short)-456)));
        s.limit=0;p.accept(packet,new short[]{11,22,33,44});check(!p.step(1010000000));check(s.writes==3);
        p.active(false);s.limit=4;p.active(true);check(!p.step(1010000000));check(s.accepted.size()==4);
        packet.epoch=2;p.accept(packet,new short[]{55,66,77,88});check(!p.step(1300000000));check(s.accepted.size()==4);
        packet.publishedNs=1400000000;p.accept(packet,new short[]{55,66,77,88});s.fail=true;p.step(1410000000);p.accept(packet,new short[]{55,66,77,88});p.step(1410000000);
        check(s.recreations==2);check(messages.stream().anyMatch(v->v.contains("disabled")));p.close();
        PcmResampler r=new PcmResampler();r.configure(24000,48000);short[] out=new short[32];
        int n=r.process(new short[]{0,100,1000,1100,2000,2100},0,3,out,16);
        check(n==5);check(Arrays.equals(Arrays.copyOf(out,10),new short[]{0,100,500,600,1000,1100,1500,1600,2000,2100}));
        n=r.process(new short[]{3000,3100},0,1,out,16);check(n==2);check(out[0]==2500&&out[1]==2600&&out[2]==3000&&out[3]==3100);
        r.configure(48000,24000);n=r.process(new short[]{1,11,2,12,3,13,4,14},0,4,out,16);check(n==2&&out[0]==1&&out[2]==3);
        System.out.println("PASS actual pump partial/zero/error/mute/stale writes and streaming stereo resampler");
    }
}
