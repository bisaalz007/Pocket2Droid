package com.samsixx.pocket2droid;

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;

/** Small app-owned toolbar symbols, drawn only when Android redraws the toolbar. */
final class ToolbarIcon extends Drawable {
    enum Symbol { ADD, SEARCH, SETTINGS, BACK, MORE, PPC_ROM, FILE }
    private final Symbol symbol;
    private final int size;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

    ToolbarIcon(Symbol symbol, int color, int size) {
        this.symbol = symbol;
        this.size = size;
        paint.setColor(color);
        paint.setStrokeWidth(1.9f);
        paint.setStrokeCap(Paint.Cap.ROUND);
        paint.setStrokeJoin(Paint.Join.ROUND);
    }

    @Override public void draw(Canvas canvas) {
        Rect bounds = getBounds();
        int saved = canvas.save();
        canvas.translate(bounds.left, bounds.top);
        canvas.scale(bounds.width() / 24f, bounds.height() / 24f);
        paint.setStyle(Paint.Style.STROKE);
        switch (symbol) {
            case ADD:
                canvas.drawLine(12, 5, 12, 19, paint);
                canvas.drawLine(5, 12, 19, 12, paint);
                break;
            case SEARCH:
                canvas.drawCircle(10.5f, 10.5f, 6.3f, paint);
                canvas.drawLine(15.1f, 15.1f, 20, 20, paint);
                break;
            case SETTINGS:
                Path gear = new Path();
                for (int i = 0; i < 32; i++) {
                    double angle = i * Math.PI / 16 - Math.PI / 2;
                    float radius = i % 4 == 1 || i % 4 == 2 ? 9.7f : 7.8f;
                    float x = 12 + radius * (float)Math.cos(angle);
                    float y = 12 + radius * (float)Math.sin(angle);
                    if (i == 0) gear.moveTo(x, y); else gear.lineTo(x, y);
                }
                gear.close();
                canvas.drawPath(gear, paint);
                canvas.drawCircle(12, 12, 3.1f, paint);
                break;
            case BACK:
                canvas.drawLine(15, 5, 8, 12, paint);
                canvas.drawLine(8, 12, 15, 19, paint);
                canvas.drawLine(8, 12, 21, 12, paint);
                break;
            case MORE:
                paint.setStyle(Paint.Style.FILL);
                for (int y : new int[]{5, 12, 19}) canvas.drawCircle(12, y, 1.6f, paint);
                break;
            case PPC_ROM:
                canvas.drawRoundRect(5, 2, 19, 22, 2, 2, paint);
                canvas.drawRect(7.5f, 4.5f, 16.5f, 16.5f, paint);
                canvas.drawCircle(12, 19.5f, 0.8f, paint);
                break;
            case FILE:
                Path document = new Path();
                document.moveTo(5, 2);document.lineTo(14, 2);document.lineTo(19, 7);
                document.lineTo(19, 22);document.lineTo(5, 22);document.close();
                canvas.drawPath(document, paint);
                canvas.drawLine(14, 2, 14, 7, paint);canvas.drawLine(14, 7, 19, 7, paint);
                break;
        }
        canvas.restoreToCount(saved);
    }

    @Override public int getIntrinsicWidth() { return size; }
    @Override public int getIntrinsicHeight() { return size; }
    @Override public void setAlpha(int alpha) { paint.setAlpha(alpha); invalidateSelf(); }
    @Override public void setColorFilter(ColorFilter filter) { paint.setColorFilter(filter); invalidateSelf(); }
    @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
}
