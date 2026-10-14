package com.samthedev.pocket2droid;
import android.app.*;
import android.hardware.input.InputManager;
import android.os.*;
import android.view.*;
import android.widget.*;

public final class ButtonMappingActivity extends LibraryUi implements InputManager.InputDeviceListener {
 private ButtonMappingStore store;private MappingCapture capture;private AndroidMappingInput input;private ButtonMappingView keypad;private TextView log,current;private AlertDialog resetDialog;private InputManager manager;
 @Override public void onCreate(Bundle state){super.onCreate(state);store=new ButtonMappingStore(new PreferenceButtonMappings(this));LinearLayout root=column();LinearLayout toolbar=bar("Button Mapping",this::resetMappings,"Reset");root.addView(toolbar);
  log=text("Tap a target, then press a keyboard or controller input. Assignments save automatically.",14,TEXT);log.setPadding(dp(12),dp(8),dp(12),dp(8));log.setGravity(Gravity.BOTTOM);log.setMovementMethod(new android.text.method.ScrollingMovementMethod());log.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);root.addView(log,new LinearLayout.LayoutParams(-1,0,1));
  current=text("One shared mapping for every ROM and device",12,MUTED);current.setPadding(dp(12),dp(4),dp(12),dp(4));root.addView(current);
  input=new AndroidMappingInput((d,t,down,fresh)->{if(capture!=null&&hasWindowFocus())capture.input(d,t,down,fresh);});
  keypad=new ButtonMappingView(this,k->{input.beginCapture();capture.select(k);});keypad.setBackgroundColor(BACKGROUND);
  capture=new MappingCapture(store,AndroidMappingInput::label,new MappingCapture.Listener(){public void selected(GuestKey k,boolean listening){keypad.selection(k,store.current());current.setText(k==null?"One shared mapping for every ROM and device":k.label+": "+(store.current().customInput(k)==null?"default inputs":AndroidMappingInput.label(store.current().customInput(k))));}public void message(String text){append(text);}});
  ScrollView scroll=new ScrollView(this);scroll.setBackgroundColor(BACKGROUND);scroll.setPadding(0,0,0,dp(8));scroll.setClipToPadding(true);HorizontalScrollView horizontal=new HorizontalScrollView(this);horizontal.setFillViewport(true);horizontal.addView(keypad,new android.widget.FrameLayout.LayoutParams(-1,-2));scroll.addView(horizontal);root.addView(scroll,new LinearLayout.LayoutParams(-1,dp(550)));scroll.setTag("mapping-scroll");install(root);
  // Insets/current-label wrapping can change without changing the root bounds.
  // Size inside the padded safe area, retaining a visible instruction region.
  root.getViewTreeObserver().addOnGlobalLayoutListener(()->{int safe=root.getHeight()-root.getPaddingTop()-root.getPaddingBottom();int available=Math.max(0,safe-toolbar.getHeight()-current.getHeight()-dp(96));int height=Math.min(dp(558),available);LinearLayout.LayoutParams p=(LinearLayout.LayoutParams)scroll.getLayoutParams();if(p.height!=height){p.height=height;scroll.setLayoutParams(p);}});
  getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN);manager=(InputManager)getSystemService(INPUT_SERVICE);manager.registerInputDeviceListener(this,ui);
 }
 private void resetMappings(){if(resetDialog!=null&&resetDialog.isShowing())return;resetDialog=new AlertDialog.Builder(this).setTitle("Reset button mappings?").setMessage("Restore all button mappings to defaults?").setNegativeButton("Cancel",null).setPositiveButton("Reset",(d,w)->capture.reset()).create();resetDialog.setOnDismissListener(d->resetDialog=null);resetDialog.show();}
 private void append(String message){String text=log.getText().toString();String[]lines=text.split("\n");if(lines.length>=12){StringBuilder b=new StringBuilder();for(int i=lines.length-10;i<lines.length;i++)b.append(lines[i]).append('\n');text=b.toString();}log.setText(text+"\n"+message);log.post(()->{if(log.getLayout()!=null)log.scrollTo(0,Math.max(0,log.getLayout().getHeight()-log.getHeight()));});}
 @Override public boolean dispatchKeyEvent(KeyEvent e){if(input!=null&&input.key(e))return true;return super.dispatchKeyEvent(e);}
 @Override public boolean onGenericMotionEvent(MotionEvent e){return input!=null&&input.motion(e)||super.onGenericMotionEvent(e);}
 @Override public void onBackPressed(){if(capture!=null&&capture.listening())capture.cancel();else super.onBackPressed();}
 @Override protected void onPause(){if(capture!=null)capture.cancel();if(input!=null)input.beginCapture();super.onPause();}
 @Override public void onWindowFocusChanged(boolean focused){super.onWindowFocusChanged(focused);if(!focused&&capture!=null){capture.cancel();input.beginCapture();}}
 public void onInputDeviceAdded(int id){}public void onInputDeviceChanged(int id){onInputDeviceRemoved(id);}public void onInputDeviceRemoved(int id){if(input!=null)input.normalizer.releaseDevice(id);}
 @Override protected void onDestroy(){if(resetDialog!=null)resetDialog.dismiss();if(manager!=null)manager.unregisterInputDeviceListener(this);if(input!=null)input.normalizer.releaseAll();super.onDestroy();}
}
