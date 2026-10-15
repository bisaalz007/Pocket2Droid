package com.samsixx.pocket2droid;

import android.content.Context;
import android.graphics.*;
import android.graphics.drawable.*;
import android.os.*;
import android.view.View;
import android.widget.ImageView;
import java.io.InputStream;

/** Plays the original GIF, fitted to the current view rather than a phone size. */
final class RomLoadingView extends ImageView {
    private AnimatedImageDrawable animation;
    private Movie movie;
    private final Paint paint=new Paint();
    private boolean active,running,attached;
    private long elapsed,began;
    RomLoadingView(Context context){this(context,false);}
    RomLoadingView(Context context,boolean forceLegacy){
        super(context);setBackgroundColor(Color.BLACK);setScaleType(ScaleType.FIT_CENTER);
        setContentDescription("Starting your ROM");setClickable(true);paint.setFilterBitmap(false);
        int resource=getResources().getIdentifier("rom_loading","raw",context.getPackageName());
        if(resource==0)throw new IllegalStateException("Missing ROM loading animation");
        if(Build.VERSION.SDK_INT>=28&&!forceLegacy){
            try{
                Drawable decoded=ImageDecoder.decodeDrawable(ImageDecoder.createSource(getResources(),resource));
                if(decoded instanceof AnimatedImageDrawable){animation=(AnimatedImageDrawable)decoded;setImageDrawable(decoded);}
            }catch(Exception ignored){ /* Older decoder path also handles valid GIFs. */ }
        }
        if(animation==null){
            try(InputStream stream=getResources().openRawResource(resource)){movie=Movie.decodeStream(stream);}
            catch(Exception error){throw new IllegalStateException("Cannot decode ROM loading animation",error);}
            if(movie==null)throw new IllegalStateException("Cannot decode ROM loading animation");
        }
    }
    void active(boolean value){active=value;updateAnimation();}
    boolean animating(){return animation!=null?animation.isRunning():running;}
    private void updateAnimation(){
        boolean next=active&&attached&&isShown()&&getWindowVisibility()==View.VISIBLE;
        if(next==running)return;
        long now=SystemClock.uptimeMillis();
        if(next)began=now;else elapsed+=now-began;
        running=next;
        if(animation!=null){if(next)animation.start();else animation.stop();}
        invalidate();
    }
    @Override protected void onAttachedToWindow(){super.onAttachedToWindow();attached=true;updateAnimation();}
    @Override protected void onDetachedFromWindow(){attached=false;updateAnimation();super.onDetachedFromWindow();}
    @Override protected void onVisibilityChanged(View view,int visibility){super.onVisibilityChanged(view,visibility);updateAnimation();}
    @Override protected void onWindowVisibilityChanged(int visibility){super.onWindowVisibilityChanged(visibility);updateAnimation();}
    @Override protected void onDraw(Canvas canvas){
        if(movie==null){super.onDraw(canvas);return;}
        int duration=movie.duration();if(duration<=0)duration=1000;
        movie.setTime((int)((elapsed+(running?SystemClock.uptimeMillis()-began:0))%duration));
        float scale=Math.min(getWidth()/(float)movie.width(),getHeight()/(float)movie.height());
        int saved=canvas.save();canvas.translate((getWidth()-movie.width()*scale)/2f,(getHeight()-movie.height()*scale)/2f);canvas.scale(scale,scale);movie.draw(canvas,0,0,paint);canvas.restoreToCount(saved);
        if(running)postInvalidateDelayed(40);
    }
}
