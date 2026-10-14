package com.samthedev.pocket2droid;

import android.content.Context;
import android.graphics.*;
import android.view.*;
import android.view.accessibility.*;
import java.util.function.BooleanSupplier;

/** The user's button art, drawn over an opaque black panel below the guest. */
final class OnScreenControls extends View {
    interface Listener { void key(String code, boolean down); }
    private final ControlsState state;
    private final BooleanSupplier sessionAccepting;
    private final Bitmap pad, center, soft, back, tab, space, home;
    private final Bitmap pressedCenter, pressedFace, pressedSoft, pressedUp, pressedDown, pressedLeft, pressedRight;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG);
    private final RectF destination=new RectF();
    private ControlsLayout layout=new ControlsLayout(0,0);
    private boolean feedback=true;
    private int opacity=255;
    private int accessibilityFocus=View.NO_ID, hovered=View.NO_ID;
    OnScreenControls(Context context, Listener listener, BooleanSupplier sessionAccepting) {
        super(context);
        this.sessionAccepting=sessionAccepting;
        setBackgroundColor(Color.BLACK);
        setContentDescription("Windows Mobile on-screen controls");
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
        state=new ControlsState((key,down)->{
            if (down && feedback) performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP);
            listener.key(key.qcode,down);
            invalidate();
        });
        pad=load("control_pad"); center=load("control_center"); soft=load("control_soft_key");
        back=load("control_back"); tab=load("control_tab"); space=load("control_space"); home=load("control_home");
        pressedCenter=load("control_pressed_center"); pressedFace=load("control_pressed_face"); pressedSoft=load("control_pressed_soft_key");
        pressedUp=load("control_pressed_up"); pressedDown=load("control_pressed_down");
        pressedLeft=load("control_pressed_left"); pressedRight=load("control_pressed_right");
    }
    private Bitmap load(String name) {
        int id=getResources().getIdentifier(name,"drawable",getContext().getPackageName());
        Bitmap image=BitmapFactory.decodeResource(getResources(),id);
        if (image==null) throw new IllegalStateException("Missing control artwork: "+name);
        return image;
    }
    void preferences(int transparency, boolean vibration) {
        opacity=Math.round(255*(1-Math.max(0,Math.min(100,transparency))/100f));
        feedback=vibration;
        invalidate();
    }
    // Check current eligibility at delivery; transient focus/menu callbacks must
    // never leave touch feedback latched off after the window becomes usable.
    private boolean accepting() { return sessionAccepting.getAsBoolean() && isShown() && hasWindowFocus(); }
    void release() { state.clear(); invalidate(); }
    @Override protected void onSizeChanged(int w,int h,int oldw,int oldh) {
        release(); layout=new ControlsLayout(w,h);
    }
    private void draw(Canvas canvas,Bitmap image,ControlsLayout.Rect rect) {
        destination.set(rect.left,rect.top,rect.right,rect.bottom);
        canvas.drawBitmap(image,null,destination,paint);
    }
    private void inset(Canvas canvas,Bitmap image,ControlsLayout.Rect rect,float dx,float dy) {
        destination.set(rect.left+rect.width()*dx,rect.top+rect.height()*dy,
                        rect.right-rect.width()*dx,rect.bottom-rect.height()*dy);
        canvas.drawBitmap(image,null,destination,paint);
    }
    private void button(Canvas canvas,ControlsLayout.Key key,Bitmap base,Bitmap pressed,float dx,float dy) {
        ControlsLayout.Rect rect=layout.rect(key);
        draw(canvas,base,rect);
        if (state.held(key)) inset(canvas,pressed,rect,dx,dy);
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        // Apply opacity to the composed artwork once, preserving the overlay's own alpha.
        int layer=canvas.saveLayerAlpha(0,0,getWidth(),getHeight(),opacity);
        button(canvas,ControlsLayout.Key.SOFT_LEFT,soft,pressedSoft,11f/640,11f/216);
        button(canvas,ControlsLayout.Key.SOFT_RIGHT,soft,pressedSoft,11f/640,11f/216);
        button(canvas,ControlsLayout.Key.BACK,back,pressedFace,14f/388,14f/588);
        button(canvas,ControlsLayout.Key.TAB,tab,pressedFace,14f/388,14f/588);
        button(canvas,ControlsLayout.Key.SPACE,space,pressedFace,14f/388,14f/588);
        button(canvas,ControlsLayout.Key.HOME,home,pressedFace,14f/388,14f/588);
        draw(canvas,pad,layout.pad);
        if (state.held(ControlsLayout.Key.UP)) draw(canvas,pressedUp,layout.pad);
        if (state.held(ControlsLayout.Key.DOWN)) draw(canvas,pressedDown,layout.pad);
        if (state.held(ControlsLayout.Key.LEFT)) draw(canvas,pressedLeft,layout.pad);
        if (state.held(ControlsLayout.Key.RIGHT)) draw(canvas,pressedRight,layout.pad);
        button(canvas,ControlsLayout.Key.SELECT,center,pressedCenter,2f/368,2f/232);
        canvas.restoreToCount(layer);
    }
    @Override public boolean onTouchEvent(MotionEvent event) {
        if (!accepting()) { release(); return true; }
        int action=event.getActionMasked();
        if (action==MotionEvent.ACTION_CANCEL) { release(); return true; }
        if (action==MotionEvent.ACTION_DOWN) {
            release(); getParent().requestDisallowInterceptTouchEvent(true);
        }
        if (action==MotionEvent.ACTION_DOWN || action==MotionEvent.ACTION_POINTER_DOWN || action==MotionEvent.ACTION_MOVE) {
            for (int i=0;i<event.getPointerCount();i++)
                state.update(event.getPointerId(i),layout.hit(event.getX(i),event.getY(i)));
        } else if (action==MotionEvent.ACTION_UP || action==MotionEvent.ACTION_POINTER_UP) {
            state.remove(event.getPointerId(event.getActionIndex()));
            if (action==MotionEvent.ACTION_UP) { release(); performClick(); }
        }
        invalidate(); return true;
    }
    @Override public boolean performClick() { super.performClick(); return true; }
    @Override public void onWindowFocusChanged(boolean focused) { super.onWindowFocusChanged(focused); if (!focused) release(); }
    @Override protected void onDetachedFromWindow() { release(); super.onDetachedFromWindow(); }

    private void accessibilityEvent(int id,int type) {
        if (id==View.NO_ID || getParent()==null) return;
        AccessibilityEvent event=AccessibilityEvent.obtain(type);
        event.setSource(this,id); event.setPackageName(getContext().getPackageName());
        event.setClassName("android.widget.Button");
        event.setContentDescription(ControlsLayout.Key.values()[id].label);
        getParent().requestSendAccessibilityEvent(this,event);
    }
    @Override public boolean dispatchHoverEvent(MotionEvent event) {
        AccessibilityManager manager=(AccessibilityManager)getContext().getSystemService(Context.ACCESSIBILITY_SERVICE);
        if (manager!=null && manager.isEnabled() && manager.isTouchExplorationEnabled()) {
            ControlsLayout.Key key=event.getActionMasked()==MotionEvent.ACTION_HOVER_EXIT?null:layout.hit(event.getX(),event.getY());
            int id=key==null?View.NO_ID:key.ordinal();
            if (id!=hovered) {
                accessibilityEvent(id,AccessibilityEvent.TYPE_VIEW_HOVER_ENTER);
                accessibilityEvent(hovered,AccessibilityEvent.TYPE_VIEW_HOVER_EXIT);
                hovered=id;
            }
            return true;
        }
        return super.dispatchHoverEvent(event);
    }

    // Expose separate buttons to TalkBack while retaining one multitouch drawing surface.
    @Override public AccessibilityNodeProvider getAccessibilityNodeProvider() {
        return new AccessibilityNodeProvider() {
            @Override public AccessibilityNodeInfo createAccessibilityNodeInfo(int id) {
                AccessibilityNodeInfo node=AccessibilityNodeInfo.obtain();
                if (id==View.NO_ID) {
                    OnScreenControls.this.onInitializeAccessibilityNodeInfo(node);
                    for (ControlsLayout.Key key:ControlsLayout.Key.values()) node.addChild(OnScreenControls.this,key.ordinal());
                } else if (id>=0 && id<ControlsLayout.Key.values().length) {
                    ControlsLayout.Key key=ControlsLayout.Key.values()[id];
                    node.setSource(OnScreenControls.this,id); node.setParent(OnScreenControls.this);
                    node.setPackageName(getContext().getPackageName()); node.setClassName("android.widget.Button");
                    node.setContentDescription(key.label); node.setEnabled(accepting()); node.setClickable(true);
                    node.setVisibleToUser(isShown()); node.setFocusable(true);
                    node.setAccessibilityFocused(accessibilityFocus==id);
                    ControlsLayout.Rect r=layout.rect(key); Rect bounds=new Rect((int)r.left,(int)r.top,(int)Math.ceil(r.right),(int)Math.ceil(r.bottom));
                    node.setBoundsInParent(bounds); int[] pos=new int[2];getLocationOnScreen(pos);bounds.offset(pos[0],pos[1]);node.setBoundsInScreen(bounds);
                    node.addAction(AccessibilityNodeInfo.ACTION_CLICK);
                    node.addAction(AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS);
                    node.addAction(AccessibilityNodeInfo.ACTION_CLEAR_ACCESSIBILITY_FOCUS);
                } else return null;
                return node;
            }
            @Override public boolean performAction(int id,int action,android.os.Bundle args) {
                if (id<0 || id>=ControlsLayout.Key.values().length) return false;
                if (action==AccessibilityNodeInfo.ACTION_CLICK && accepting()) {
                    // Distinct negative pointer IDs cannot steal a physical finger's key.
                    state.update(-id-1,ControlsLayout.Key.values()[id]);
                    postDelayed(()->{state.remove(-id-1);invalidate();},120); return true;
                }
                if (action==AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS || action==AccessibilityNodeInfo.ACTION_CLEAR_ACCESSIBILITY_FOCUS) {
                    if (action==AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS) {
                        if (accessibilityFocus==id) return false;
                        accessibilityEvent(accessibilityFocus,AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUS_CLEARED);
                        accessibilityFocus=id;
                        accessibilityEvent(id,AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUSED);
                    } else {
                        if (accessibilityFocus!=id) return false;
                        accessibilityFocus=View.NO_ID;
                        accessibilityEvent(id,AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUS_CLEARED);
                    }
                    return true;
                }
                return false;
            }
        };
    }
}
