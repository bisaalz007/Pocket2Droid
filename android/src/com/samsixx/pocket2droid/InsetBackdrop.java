package com.samsixx.pocket2droid;
import android.graphics.*;
import android.graphics.drawable.Drawable;

/** Paint system insets ourselves when Android enforces edge-to-edge rendering. */
final class InsetBackdrop extends Drawable {
    final int content,topColor,bottomColor;
    private final Paint paint=new Paint();
    int top,bottom;
    InsetBackdrop(int content,int topColor,int bottomColor){this.content=content;this.topColor=topColor;this.bottomColor=bottomColor;}
    void insets(int top,int bottom){this.top=top;this.bottom=bottom;invalidateSelf();}
    static int navigation(int api,boolean light,int background,int dark){return light&&api<26?dark:background;}
    @Override public void draw(Canvas canvas){Rect r=getBounds();paint.setColor(content);canvas.drawRect(r,paint);paint.setColor(topColor);canvas.drawRect(r.left,r.top,r.right,r.top+top,paint);paint.setColor(bottomColor);canvas.drawRect(r.left,r.bottom-bottom,r.right,r.bottom,paint);}
    @Override public void setAlpha(int alpha){}
    @Override public void setColorFilter(ColorFilter filter){}
    @Override public int getOpacity(){return PixelFormat.OPAQUE;}
}
