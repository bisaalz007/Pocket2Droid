package com.samsixx.pocket2droid;

/** UI-thread startup gate. A QMP connection or a blank frame is not a picture. */
final class RomBootState {
    private boolean waiting;
    private long minimumGeneration;
    void starting(long generation){minimumGeneration=generation+1;waiting=true;}
    boolean waiting(){return waiting;}
    boolean picture(long published,long current){
        if(!waiting||published!=current||published<minimumGeneration)return false;
        waiting=false;return true;
    }
    void failed(){waiting=false;}
    static boolean hasPicture(int[] pixels){
        for(int pixel:pixels)if((pixel>>>24)!=0&&(pixel&0x00ffffff)!=0)return true;
        return false;
    }
}
