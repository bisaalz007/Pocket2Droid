package com.samsixx.pocket2droid;
import android.graphics.*;
public final class InsetBackdropArtTest {
    static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    public static void main(String[] args){
        for(int api:new int[]{24,25})check(InsetBackdrop.navigation(api,true,Color.WHITE,Color.BLACK)==Color.BLACK,"White navigation icons require a dark backdrop before API26");
        check(InsetBackdrop.navigation(26,true,Color.WHITE,Color.BLACK)==Color.WHITE,"API26 supports dark navigation icons");
        Bitmap bitmap=Bitmap.createBitmap(40,80,Bitmap.Config.ARGB_8888);
        InsetBackdrop light=new InsetBackdrop(Color.WHITE,Color.BLACK,Color.BLACK);light.setBounds(0,0,40,80);light.insets(12,8);light.draw(new Canvas(bitmap));
        check(bitmap.getPixel(20,6)==Color.BLACK,"Edge-to-edge white status icons have a dark top inset");
        check(bitmap.getPixel(20,40)==Color.WHITE,"Light content remains light");
        check(bitmap.getPixel(20,76)==Color.BLACK,"Legacy white navigation icons remain readable");
        InsetBackdrop guest=new InsetBackdrop(Color.BLACK,Color.BLACK,Color.BLACK);guest.setBounds(0,0,40,80);guest.insets(12,8);guest.draw(new Canvas(bitmap));
        for(int y:new int[]{0,6,40,76,79})check(bitmap.getPixel(20,y)==Color.BLACK,"Guest insets and borders must all be black");
        System.out.println("PASS actual Canvas system inset contrast and black guest borders; API24/25 navigation fallback");
    }
}
