package com.samthedev.pocket2droid;
import android.content.*;
import android.graphics.*;
import android.graphics.drawable.*;
import android.view.*;
import android.widget.*;
import java.util.*;
import java.util.function.Consumer;

/** Real accessible child targets; direction art shares the supplied pad. */
final class ButtonMappingView extends FrameLayout {
 private final Map<GuestKey,ImageButton> buttons=new EnumMap<>(GuestKey.class);
 private final Map<GuestKey,RectF> boxes=new EnumMap<>(GuestKey.class);
 private final Map<GuestKey,Bitmap> faces=new EnumMap<>(GuestKey.class),pressed=new EnumMap<>(GuestKey.class);
 private final Bitmap pad;private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG);
 private GuestKey selected;private ButtonBindings bindings=ButtonBindings.defaults();private RectF padBox;
 ButtonMappingView(Context c,Consumer<GuestKey> action){super(c);setBackgroundColor(Color.BLACK);setWillNotDraw(false);pad=load("control_pad");
  for(GuestKey k:GuestKey.mappingTargets()){
   String name=resource(k);if(name!=null)faces.put(k,load(name));String p=pressedResource(k);if(p!=null)pressed.put(k,load(p));
   ImageButton b=new ImageButton(c);b.setBackgroundColor(Color.TRANSPARENT);b.setPadding(0,0,0,0);b.setScaleType(ImageView.ScaleType.FIT_CENTER);b.setContentDescription(k.label);b.setTag(k);b.setOnClickListener(v->action.accept(k));b.setFocusable(true);b.setMinimumWidth(dp(48));b.setMinimumHeight(dp(48));buttons.put(k,b);addView(b);
  }refresh();
 }
 private int dp(float x){return Math.round(x*getResources().getDisplayMetrics().density);}
 private Bitmap load(String name){int id=getResources().getIdentifier(name,"drawable",getContext().getPackageName());Bitmap b=BitmapFactory.decodeResource(getResources(),id);if(b==null)throw new IllegalStateException("Missing mapping art: "+name);return b;}
 private String resource(GuestKey k){if(k.name().startsWith("DIGIT_"))return "mapping_key_"+k.qcode;if(k==GuestKey.STAR)return "mapping_key_asterisk";if(k==GuestKey.HASH)return "mapping_key_hash";switch(k){case CALL:return "mapping_call";case END_CALL:return "mapping_end_call";case SOFT_LEFT:case SOFT_RIGHT:return "control_soft_key";case ENTER:return "control_center";case BACK:return "control_back";case TAB:return "control_tab";case SPACE:return "control_space";case HOME:return "control_home";default:return null;}}
 private String pressedResource(GuestKey k){if(k.name().startsWith("DIGIT_")||k==GuestKey.STAR||k==GuestKey.HASH)return resource(k)+"_pressed";switch(k){case UP:return "control_pressed_up";case DOWN:return "control_pressed_down";case LEFT:return "control_pressed_left";case RIGHT:return "control_pressed_right";case ENTER:return "control_pressed_center";case SOFT_LEFT:case SOFT_RIGHT:return "control_pressed_soft_key";default:return "control_pressed_face";}}
 void selection(GuestKey k,ButtonBindings b){selected=k;bindings=b;refresh();invalidate();}
 private void refresh(){for(Map.Entry<GuestKey,ImageButton> e:buttons.entrySet()){
  GuestKey k=e.getKey();ImageButton b=e.getValue();b.setSelected(k==selected);Bitmap face=faces.get(k);if(face!=null){if(k==selected&&(k.name().startsWith("DIGIT_")||k==GuestKey.STAR||k==GuestKey.HASH))face=pressed.get(k);b.setImageBitmap(face);}
  String input=bindings.customInput(k);b.setContentDescription(k.label+" · "+(input==null?"default inputs":AndroidMappingInput.label(input)));
  GradientDrawable border=new GradientDrawable();border.setColor(Color.TRANSPARENT);border.setCornerRadius(dp(5));if(k==selected)border.setStroke(dp(2),LibraryUi.ACCENT);b.setForeground(border);
 }}
 View target(GuestKey key){return buttons.get(key);}
 @Override protected void onMeasure(int widthSpec,int heightSpec){int width=Math.max(dp(344),MeasureSpec.getSize(widthSpec));setMeasuredDimension(width,dp(550));geometry(width);for(GuestKey k:buttons.keySet()){RectF r=boxes.get(k);buttons.get(k).measure(MeasureSpec.makeMeasureSpec(Math.round(r.width()),MeasureSpec.EXACTLY),MeasureSpec.makeMeasureSpec(Math.round(r.height()),MeasureSpec.EXACTLY));}}
 private void box(GuestKey k,float x,float y,float w,float h){boxes.put(k,new RectF(x,y,x+w,y+h));}
 private void geometry(int width){float w=width,unit=dp(1),p=dp(144),side=(w-p)/2,half=(side-dp(4))/2;
  box(GuestKey.CALL,dp(8),dp(4),dp(52),dp(80));box(GuestKey.END_CALL,w-dp(60),dp(4),dp(52),dp(80));
  float top=dp(90);box(GuestKey.SOFT_LEFT,0,top,side,dp(48));box(GuestKey.SOFT_RIGHT,w-side,top,side,dp(48));
  for(int i=0;i<4;i++)box(new GuestKey[]{GuestKey.BACK,GuestKey.TAB,GuestKey.SPACE,GuestKey.HOME}[i],i<2?i*(half+dp(4)):w-side+(i-2)*(half+dp(4)),top+dp(68),half,dp(84));
  float px=side,py=top+dp(20);padBox=new RectF(px,py,px+p,py+p);
  box(GuestKey.UP,px+dp(48),py,dp(48),dp(48));box(GuestKey.DOWN,px+dp(48),py+dp(96),dp(48),dp(48));box(GuestKey.LEFT,px,py+dp(48),dp(48),dp(48));box(GuestKey.RIGHT,px+dp(96),py+dp(48),dp(48),dp(48));box(GuestKey.ENTER,px+dp(48),py+dp(48),dp(48),dp(48));
  GuestKey[] nums={GuestKey.DIGIT_1,GuestKey.DIGIT_2,GuestKey.DIGIT_3,GuestKey.DIGIT_4,GuestKey.DIGIT_5,GuestKey.DIGIT_6,GuestKey.DIGIT_7,GuestKey.DIGIT_8,GuestKey.DIGIT_9,GuestKey.STAR,GuestKey.DIGIT_0,GuestKey.HASH};
  float gap=dp(8),nw=(w-gap*4)/3;for(int i=0;i<12;i++)box(nums[i],gap+(i%3)*(nw+gap),dp(274)+(i/3)*dp(68),nw,dp(60));
 }
 @Override protected void onLayout(boolean changed,int l,int t,int r,int b){for(GuestKey k:buttons.keySet()){RectF q=boxes.get(k);buttons.get(k).layout(Math.round(q.left),Math.round(q.top),Math.round(q.right),Math.round(q.bottom));}}
 @Override protected void onDraw(Canvas c){super.onDraw(c);if(padBox==null)return;c.drawBitmap(pad,null,padBox,paint);if(selected==GuestKey.UP||selected==GuestKey.DOWN||selected==GuestKey.LEFT||selected==GuestKey.RIGHT)c.drawBitmap(pressed.get(selected),null,padBox,paint);}
 @Override protected void dispatchDraw(Canvas c){super.dispatchDraw(c);if(selected!=null&&!selected.name().startsWith("DIGIT_")&&selected!=GuestKey.STAR&&selected!=GuestKey.HASH&&faces.containsKey(selected)){RectF r=new RectF(boxes.get(selected));float dx=selected==GuestKey.ENTER?2f/368:selected==GuestKey.SOFT_LEFT||selected==GuestKey.SOFT_RIGHT?11f/640:14f/388;float dy=selected==GuestKey.ENTER?2f/232:selected==GuestKey.SOFT_LEFT||selected==GuestKey.SOFT_RIGHT?11f/216:14f/588;r.inset(r.width()*dx,r.height()*dy);c.drawBitmap(pressed.get(selected),null,r,paint);}}
}
