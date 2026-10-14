package com.samthedev.pocket2droid;
import android.content.ContextWrapper;
import java.io.*;
import java.lang.reflect.*;
import java.nio.*;
import java.nio.channels.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.*;
import android.media.AudioManager;
/** Actual Android sink plus consumer shutdown/focus-denial, on disposable files. */
public final class AudioPlayerArtTest {
    static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
    static void put(Object o,String n,Object v)throws Exception{Field f=o.getClass().getDeclaredField(n);f.setAccessible(true);f.set(o,v);}
    public static void main(String[] args)throws Exception {
        File root=new File(args[0]);check(root.isDirectory(),"Owned ART root");File file=new File(root,"output.bin");
        try(RandomAccessFile f=new RandomAccessFile(file,"rw")){f.setLength(AudioProtocol.SIZE);AudioProtocol.initialize(f.getChannel().map(FileChannel.MapMode.READ_WRITE,0,AudioProtocol.SIZE));}
        AtomicInteger permitted=new AtomicInteger();
        AudioPlayer p=new AudioPlayer(new ContextWrapper(null){public Object getSystemService(String name){return null;}},file,System.out::println,(id,allow)->{if(allow)permitted.incrementAndGet();});
        Field field=AudioPlayer.class.getDeclaredField("sink");field.setAccessible(true);AudioPump.Sink sink=(AudioPump.Sink)field.get(p);
        put(p,"foreground",true);put(p,"focused",true);
        check(sink.configure(48000,40),"Actual Android AudioTrack initialization");
        short[] tone=new short[4800];for(int i=0;i<2400;i++){tone[i*2]=(short)(Math.sin(i*2*Math.PI*440/48000)*2500);tone[i*2+1]=tone[i*2];}
        int accepted=sink.write(tone,0,tone.length);check(accepted>=0&&accepted<=tone.length&&(accepted&1)==0,"Actual nonblocking stereo write");
        p.setEnabled(false);check(sink.write(tone,0,2)==0,"Mute rejects late writes");sink.close();
        p.setEnabled(true);put(p,"focused",false);p.start(7);Thread.sleep(100);
        for(int i=0;i<100;i++){p.setForeground(false);p.setForeground(true);}
        check(p.stop(1000)&&!p.alive(),"Consumer wakes and stops within bound");check(permitted.get()==0,"Denied focus never enables native export");
        AtomicInteger grants=new AtomicInteger(),finished=new AtomicInteger();
        AudioPlayer raced=new AudioPlayer(new ContextWrapper(null){public Object getSystemService(String name){return null;}},file,text->{},new AudioPlayer.Control(){
            public void allowed(long id,boolean value){if(value)grants.incrementAndGet();}
            public void stopped(long id){finished.incrementAndGet();}
        });
        put(raced,"foreground",true);put(raced,"focused",true);put(raced,"focusAttempted",true);raced.start(8);
        long deadline=System.nanoTime()+1000000000L;while(grants.get()==0&&System.nanoTime()<deadline)Thread.sleep(2);
        check(grants.get()==1,"Initial consumer grants native export");
        Field wakeField=AudioPlayer.class.getDeclaredField("wake");wakeField.setAccessible(true);Object wake=wakeField.get(raced);
        synchronized(wake){raced.setForeground(false);raced.setForeground(true);}
        deadline=System.nanoTime()+1000000000L;while(grants.get()<2&&System.nanoTime()<deadline)Thread.sleep(2);
        boolean transientRecovered=grants.get()>=2;
        Object track=field.get(raced);CountDownLatch monitorHeld=new CountDownLatch(1),release=new CountDownLatch(1),paused=new CountDownLatch(1);
        Thread stall=new Thread(()->{synchronized(track){monitorHeld.countDown();try{release.await();}catch(InterruptedException e){Thread.currentThread().interrupt();}}});stall.start();
        check(monitorHeld.await(1,TimeUnit.SECONDS),"Simulated platform sink call holds its monitor");
        Thread ui=new Thread(()->{raced.setForeground(false);paused.countDown();});ui.start();
        boolean pauseResponsive=paused.await(200,TimeUnit.MILLISECONDS);release.countDown();ui.join(1000);stall.join(1000);
        check(raced.stop(1000),"Raced consumer stops");
        deadline=System.nanoTime()+1000000000L;while(finished.get()==0&&System.nanoTime()<deadline)Thread.sleep(2);
        System.out.println("Lifecycle checks: transient="+transientRecovered+" pauseResponsive="+pauseResponsive+" completion="+finished.get());
        check(transientRecovered,"Rapid pause/resume cannot permanently revoke native sound");
        check(pauseResponsive,"Platform sink stall cannot block caller pause/save");
        check(finished.get()==1,"Consumer completion reported exactly once after teardown");
        AudioPlayer focus=new AudioPlayer(new ContextWrapper(null){public Object getSystemService(String name){return null;}},file,text->{},(id,value)->{});
        put(focus,"foreground",true);Field listenerField=AudioPlayer.class.getDeclaredField("focusListener");listenerField.setAccessible(true);
        AudioManager.OnAudioFocusChangeListener old=(AudioManager.OnAudioFocusChangeListener)listenerField.get(focus);
        Method request=AudioPlayer.class.getDeclaredMethod("requestFocus");request.setAccessible(true);request.invoke(focus);
        Field focusedField=AudioPlayer.class.getDeclaredField("focused");focusedField.setAccessible(true);
        old.onAudioFocusChange(AudioManager.AUDIOFOCUS_GAIN);check(!focusedField.getBoolean(focus),"Abandoned request cannot grant denied new focus");
        AudioManager.OnAudioFocusChangeListener current=(AudioManager.OnAudioFocusChangeListener)listenerField.get(focus);
        current.onAudioFocusChange(AudioManager.AUDIOFOCUS_GAIN);old.onAudioFocusChange(AudioManager.AUDIOFOCUS_LOSS);
        check(focusedField.getBoolean(focus),"Stale loss cannot revoke current request focus");
        Field generation=AudioPlayer.class.getDeclaredField("focusGeneration");generation.setAccessible(true);
        Field callbacks=AudioPlayer.class.getDeclaredField("focusCallbacks");callbacks.setAccessible(true);
        long requestId=generation.getLong(focus),beforeCallback=callbacks.getLong(focus);
        current.onAudioFocusChange(AudioManager.AUDIOFOCUS_LOSS);
        Method result=AudioPlayer.class.getDeclaredMethod("focusResult",long.class,long.class,int.class);result.setAccessible(true);
        result.invoke(focus,requestId,beforeCallback,AudioManager.AUDIOFOCUS_REQUEST_GRANTED);
        boolean laterLossPreserved=!focusedField.getBoolean(focus);
        System.out.println("Focus callback during request preserved: "+laterLossPreserved);
        check(laterLossPreserved,"Synchronous request result cannot overwrite a later focus-loss callback");
        current.onAudioFocusChange(AudioManager.AUDIOFOCUS_GAIN);focus.setEnabled(false);
        current.onAudioFocusChange(AudioManager.AUDIOFOCUS_LOSS);focus.setEnabled(true);
        check(!focusedField.getBoolean(focus),"Current focus loss while muted remains lost on unmute");
        focus.stop(1000);
        System.out.println("PASS actual Android sound sink, stereo write, mute, denied focus and bounded consumer shutdown");
        for(Thread t:Thread.getAllStackTraces().keySet())if(!t.isDaemon())System.out.println("CLI remaining thread: "+t.getName());
        // app_process is a CLI fixture; Android framework helper threads may outlive main.
        System.exit(0);
    }
}
