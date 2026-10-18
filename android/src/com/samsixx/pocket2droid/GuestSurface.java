package com.samsixx.pocket2droid;
import android.content.Context;
import android.graphics.*;
import android.view.SurfaceView;
import android.view.SurfaceHolder;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;

final class GuestSurface extends SurfaceView {
    private final Engine engine;
    final PresentationRate rate = new PresentationRate();
    volatile boolean resumed, counterEnabled = true, destroyed;
    volatile int guestWidth = 240, guestHeight = 320;
    volatile boolean frameObserved,pictureObserved;
    private final Engine.Status status;
    private final java.util.function.LongConsumer firstPicture;
    private volatile long surfaceGeneration;
    private volatile RomSettings.ScaleMode scaleMode=RomSettings.ScaleMode.FITTED;
    private volatile RomSettings.ScreenPosition screenPosition=RomSettings.ScreenPosition.CENTER;
    private volatile float panX,panY;
    private volatile DisplayTransform transform;
    void setScaleMode(RomSettings.ScaleMode mode){if(scaleMode!=mode){scaleMode=mode;panX=panY=0;transform=null;surfaceGeneration++;}}
    void setScreenPosition(RomSettings.ScreenPosition position){if(screenPosition!=position){screenPosition=position;panY=0;transform=null;surfaceGeneration++;}}
    DisplayTransform geometry(){DisplayTransform t=transform;int w=getWidth(),h=getHeight();if(t==null||t.vw!=w||t.vh!=h||t.width!=guestWidth||t.height!=guestHeight||t.mode!=scaleMode||t.position!=screenPosition){t=DisplayTransform.create(w,h,guestWidth,guestHeight,scaleMode,screenPosition,panX,panY);transform=t;}return t;}
    void panBy(float dx,float dy){if(scaleMode!=RomSettings.ScaleMode.PIXEL_PERFECT)return;DisplayTransform next=DisplayTransform.create(getWidth(),getHeight(),guestWidth,guestHeight,scaleMode,screenPosition,panX+dx,panY+dy);panX=next.left-(getWidth()-guestWidth)/2f;panY=next.top-(getHeight()-guestHeight)*screenPosition.anchor;transform=next;surfaceGeneration++;}
    GuestSurface(Context context, Engine e, Engine.Status sink) {
        this(context,e,sink,generation->{});
    }
    GuestSurface(Context context,Engine e,Engine.Status sink,java.util.function.LongConsumer firstPicture) {
        super(context); engine = e; status = sink;this.firstPicture=firstPicture;
        // SurfaceView's normal View background must stay transparent: an opaque
        // background would paint over the separate surface containing the guest.
        getHolder().addCallback(new SurfaceHolder.Callback() {
            public void surfaceCreated(SurfaceHolder h) { surfaceGeneration++; }
            public void surfaceChanged(SurfaceHolder h, int format, int w, int height) { surfaceGeneration++; }
            public void surfaceDestroyed(SurfaceHolder h) { surfaceGeneration++; }
        });
        new Thread(this::pump, "guest-display").start();
    }
    private void pump() {
        long generation = -1, last = 0, paintedSurface = -1;
        RandomAccessFile file = null;
        ByteBuffer mapped = null;
        Bitmap bitmap = null;
        int[] pixels = null;
        Paint paint = new Paint(); paint.setFilterBitmap(false);
        try {
            while (!destroyed) {
                long began = System.nanoTime();
                if (resumed && engine.frameReady && getHolder().getSurface().isValid()) {
                    if (generation != engine.generation) {
                        if (file != null) file.close();
                        file = new RandomAccessFile(engine.frames, "r");
                        mapped = null;
                        generation = engine.generation; last = 0;frameObserved=false;pictureObserved=false;
                    }
                    FrameProtocol.Header header = null;
                    long targetSurface = surfaceGeneration;
                    synchronized(Engine.frameAccess){try (FileLock lock = file.getChannel().tryLock(0, Long.MAX_VALUE, true)) {
                        if (lock != null) {
                            long length=file.length();
                            if(length<64||length>Integer.MAX_VALUE)throw new IllegalStateException("Frame buffer exceeds this platform's addressable memory");
                            if(mapped==null||mapped.capacity()!=length)mapped=file.getChannel().map(FileChannel.MapMode.READ_ONLY,0,length);
                            FrameProtocol.Header h = FrameProtocol.parse(mapped);
                            if (h != null && (h.sequence != last || targetSurface != paintedSurface)) {
                                if (bitmap == null || bitmap.getWidth() != h.width || bitmap.getHeight() != h.height) {
                                    if (bitmap != null) bitmap.recycle();
                                    bitmap = Bitmap.createBitmap(h.width, h.height, Bitmap.Config.ARGB_8888);
                                    pixels = new int[h.width * h.height];
                                }
                                ByteBuffer data = mapped.duplicate().order(ByteOrder.LITTLE_ENDIAN);
                                data.position(64); data.asIntBuffer().get(pixels);
                                header = h;
                            }
                        }
                    }} // Shared locks end before bitmap conversion or Android drawing.
                    if (header != null && resumed) {
                        bitmap.setPixels(pixels, 0, header.width, 0, 0, header.width, header.height);
                        Canvas canvas = null;
                        boolean posted = false;
                        try {
                            canvas = getHolder().lockCanvas();
                            if (canvas != null) {
                                canvas.drawColor(Color.BLACK);
                                guestWidth=header.width;guestHeight=header.height;
                                DisplayTransform t=geometry();
                                canvas.drawBitmap(bitmap,null,new RectF(t.left,t.top,t.left+header.width*t.scale,t.top+header.height*t.scale),paint);
                            }
                        } finally {
                            if (canvas != null) { getHolder().unlockCanvasAndPost(canvas); posted = true; }
                        }
                        if (posted) {
                            boolean changedImage = header.sequence != last;
                            last = header.sequence; guestWidth = header.width; guestHeight = header.height;frameObserved=true;
                            paintedSurface = targetSurface;
                            if (counterEnabled && changedImage) rate.presented(last, System.nanoTime());
                            // Only scan startup frames; do not add a scan to ongoing gameplay.
                            if(!pictureObserved&&RomBootState.hasPicture(pixels)){pictureObserved=true;firstPicture.accept(generation);}
                        }
                    }
                }
                long sleep = 16_000_000L - (System.nanoTime() - began);
                if (sleep > 0) Thread.sleep(sleep / 1_000_000, (int)(sleep % 1_000_000));
            }
        } catch (OutOfMemoryError error) {
            if (!destroyed) status.changed("Display error: not enough memory for this resolution");
        } catch (Exception error) {
            if (!destroyed) status.changed("Display error: " + error.getMessage());
        } finally {
            if (file != null) try { file.close(); } catch (Exception ignored) { }
            if (bitmap != null) bitmap.recycle();
        }
    }
}
