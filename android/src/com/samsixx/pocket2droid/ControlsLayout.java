package com.samsixx.pocket2droid;

/** Artwork geometry in the user's 434 x 158 control-panel layout. */
final class ControlsLayout {
    enum Key {
        SOFT_LEFT("f1", "Left soft key"), SOFT_RIGHT("f2", "Right soft key"),
        BACK("esc", "Back"), TAB("tab", "Tab"), SPACE("spc", "Space"), HOME("meta_l", "Home"),
        UP("up", "Up"), DOWN("down", "Down"), LEFT("left", "Left"), RIGHT("right", "Right"),
        SELECT("ret", "Select");
        final String qcode, label;
        Key(String qcode, String label) { this.qcode = qcode; this.label = label; }
    }
    static final float WIDTH = 434, HEIGHT = 158;
    static int panelHeight(int width,int availableHeight,float density) {
        return Math.max(1,Math.round(Math.min(width*HEIGHT/WIDTH,
            Math.min(144*density,availableHeight*.36f))));
    }
    static final class Rect {
        final float left, top, right, bottom;
        Rect(float l, float t, float r, float b) { left=l; top=t; right=r; bottom=b; }
        float width() { return right-left; }
        float height() { return bottom-top; }
        boolean contains(float x, float y) {
            return x>=left && x<right && y>=top && y<bottom;
        }
    }
    final Rect pad;
    private final Rect[] rectangles = new Rect[Key.values().length];
    private final float scale, offsetX, offsetY;
    ControlsLayout(float width, float height) {
        scale = Math.max(0, Math.min(width/WIDTH, height/HEIGHT));
        offsetX = (width-WIDTH*scale)/2;
        offsetY = (height-HEIGHT*scale)/2;
        pad = box(148,18,288,143);
        put(Key.SOFT_LEFT,0,0,136,46); put(Key.SOFT_RIGHT,298,0,434,46);
        put(Key.BACK,9,66,57,139); put(Key.TAB,76,66,124,139);
        put(Key.SPACE,307,66,355,139); put(Key.HOME,375,66,423,139);
        put(Key.SELECT,189,62,247,99);
        put(Key.UP,186,18,250,62); put(Key.DOWN,186,99,250,143);
        put(Key.LEFT,148,52,189,109); put(Key.RIGHT,247,52,288,109);
    }
    private Rect box(float l, float t, float r, float b) {
        return new Rect(offsetX+l*scale,offsetY+t*scale,offsetX+r*scale,offsetY+b*scale);
    }
    private void put(Key key, float l, float t, float r, float b) { rectangles[key.ordinal()]=box(l,t,r,b); }
    Rect rect(Key key) { return rectangles[key.ordinal()]; }
    Key hit(float x, float y) {
        if (scale<=0) return null;
        for (Key key : new Key[]{Key.SOFT_LEFT,Key.SOFT_RIGHT,Key.BACK,Key.TAB,Key.SPACE,Key.HOME,Key.SELECT})
            if (rect(key).contains(x,y)) return key;
        if (!pad.contains(x,y)) return null;
        float dx=(x-(pad.left+pad.right)/2)/(pad.width()/2);
        float dy=(y-(pad.top+pad.bottom)/2)/(pad.height()/2);
        return Math.abs(dx)>Math.abs(dy) ? (dx<0?Key.LEFT:Key.RIGHT) : (dy<0?Key.UP:Key.DOWN);
    }
}
