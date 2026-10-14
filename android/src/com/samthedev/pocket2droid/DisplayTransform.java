package com.samthedev.pocket2droid;
final class DisplayTransform {
    final float left,top,scale;
    final int width,height,vw,vh;
    final RomSettings.ScaleMode mode;
    final RomSettings.ScreenPosition position;
    private DisplayTransform(int vw,int vh,int gw,int gh,float scale,float x,float y,RomSettings.ScaleMode mode,RomSettings.ScreenPosition position){this.vw=vw;this.vh=vh;width=gw;height=gh;this.scale=scale;left=x;top=y;this.mode=mode;this.position=position;}
    static DisplayTransform create(int vw,int vh,int gw,int gh,RomSettings.ScaleMode mode,float panX,float panY){
        return create(vw,vh,gw,gh,mode,RomSettings.ScreenPosition.CENTER,panX,panY);
    }
    static DisplayTransform create(int vw,int vh,int gw,int gh,RomSettings.ScaleMode mode,RomSettings.ScreenPosition position,float panX,float panY){
        float scale=vw>0&&vh>0&&gw>0&&gh>0?(mode==RomSettings.ScaleMode.PIXEL_PERFECT?1f:Math.min((float)vw/gw,(float)vh/gh)):0;
        float w=gw*scale,h=gh*scale,x=(vw-w)/2,y=(vh-h)*position.anchor;
        if(mode==RomSettings.ScaleMode.PIXEL_PERFECT){if(w>vw)x=Math.max(vw-w,Math.min(0,x+panX));if(h>vh)y=Math.max(vh-h,Math.min(0,y+panY));}
        return new DisplayTransform(vw,vh,gw,gh,scale,x,y,mode,position);
    }
    int[] touch(float x,float y){if(scale<=0||x<0||y<0||x>=vw||y>=vh)return null;x=(x-left)/scale;y=(y-top)/scale;if(x<0||y<0||x>=width||y>=height)return null;return new int[]{(int)x,(int)y};}
}
