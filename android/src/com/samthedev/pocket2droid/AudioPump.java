package com.samthedev.pocket2droid;
/** Bounded playback state, separate from Android and guest timing. */
final class AudioPump {
    interface Sink { boolean configure(int rate,int targetBufferMs);int write(short[] pcm,int offset,int count);void flush();void close(); }
    interface Status { void changed(String message); }
    private final Sink sink;private final Status status;private final PcmResampler resampler=new PcmResampler();
    private final short[] pending=new short[24578];private int offset,count,rate,outputRate,epoch,retries;
    private long published;private boolean active,failed,configured;
    AudioPump(Sink sink,Status status){this.sink=sink;this.status=status;}
    boolean pending(){return count>offset;}
    boolean failed(){return failed;}
    void active(boolean value){if(active!=value){active=value;offset=count=0;sink.flush();epoch=0;}}
    void discard(){offset=count=0;sink.flush();epoch=0;}
    private boolean configure(int newRate) {
        int selected=newRate;
        if(!sink.configure(selected,40)) {
            selected=48000;
            if(!sink.configure(selected,40)){selected=44100;if(!sink.configure(selected,40)){disable("Sound disabled: device output format unavailable");return false;}}
        }
        rate=newRate;outputRate=selected;configured=true;return true;
    }
    private void disable(String message){failed=true;offset=count=0;sink.close();status.changed(message);}
    void accept(AudioProtocol.Packet p,short[] pcm) {
        if(!active||failed||p.frames==0)return;
        if(p.frames<0||p.frames>2048||pcm.length<p.frames*2||p.rate<8000||p.rate>192000){disable("Sound disabled: invalid PCM");return;}
        if(p.epoch!=epoch||p.rate!=rate||!configured) {
            sink.flush();offset=count=0;
            if((p.rate!=rate||!configured)&&!configure(p.rate))return;
            resampler.configure(p.rate,outputRate);epoch=p.epoch;
        }
        // A slow sink never grows a backlog: replace remaining host PCM.
        count=resampler.process(pcm,0,p.frames,pending,pending.length/2)*2;offset=0;published=p.publishedNs;
    }
    boolean step(long now) {
        if(!active||failed||!pending())return false;
        if(now<published||now-published>AudioProtocol.MAX_NS){discard();return false;}
        int wrote=sink.write(pending,offset,count-offset);
        if(wrote==0)return false;
        if(wrote<0) {
            offset=count=0;sink.close();configured=false;
            if(wrote==-6&&retries++==0){status.changed("Sound output restarted");configure(rate);epoch=0;}
            else disable("Sound disabled: playback error "+wrote);
            return false;
        }
        if((wrote&1)!=0||wrote>count-offset){disable("Sound disabled: incomplete stereo write");return false;}
        offset+=wrote;return true;
    }
    void close(){active=false;offset=count=0;sink.close();}
}
