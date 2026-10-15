package com.samsixx.pocket2droid;
import android.app.*;
import android.content.*;
import android.content.pm.ActivityInfo;
import android.graphics.Color;
import android.hardware.input.InputManager;
import android.os.*;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.util.*;

public final class EmulatorActivity extends LibraryUi implements InputManager.InputDeviceListener {
    private Engine engine;
    private GuestSurface display;
    private RomProfile profile;
    private String filename;
    private boolean foreground,closing,fullscreen,panMode,pointer;
    private int lastX,lastY;
    private float panLastX,panLastY;
    private long lastMove;
    private TextView fps;
    private LinearLayout toolbar;
    private OnScreenControls keys;
    private FrameLayout screen;
    private ImageButton overflow;
    private PopupMenu popup;
    private RomLoadingView loader;
    private final RomBootState boot=new RomBootState();
    private View sessionContent;
    @Override boolean immersivePresentation(){return fullscreen;}
    @Override boolean guestPresentation(){return true;}
    private ButtonBindings inputBindings;
    private MappedInputState mappedKeys;
    private AndroidMappingInput mappingInput;
    private InputManager inputManager;
    private final Runnable tick=new Runnable(){public void run(){if(display==null||!foreground||!display.counterEnabled)return;String label=display.resumed&&engine.frameReady?String.format(Locale.US,"Display FPS %.1f",display.rate.sample(System.nanoTime())):"Display FPS — paused";if(!label.contentEquals(fps.getText()))fps.setText(label);ui.postDelayed(this,500);}};
    @Override public void onCreate(Bundle saved){super.onCreate(saved);inputBindings=PreferenceButtonMappings.load(this);mappedKeys=new MappedInputState(inputBindings,(k,down)->{if(engine!=null)engine.key(k.qcode,down);});mappingInput=new AndroidMappingInput(this::normalizedInput);inputManager=(InputManager)getSystemService(INPUT_SERVICE);inputManager.registerInputDeviceListener(this,ui);filename=getIntent().getStringExtra("rom");getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);setVolumeControlStream(android.media.AudioManager.STREAM_MUSIC);blackWindow();FrameLayout loading=new FrameLayout(this);loading.setBackgroundColor(Color.BLACK);loader=new RomLoadingView(this);loading.addView(loader,new FrameLayout.LayoutParams(-1,-1));install(loading);
        task(()->repository().verifyForLaunch(filename),p->{profile=p;engine=new Engine(this,this::message,StorageLayout.forContext(this,p));engine.audioStatus=this::message;build();engine.sound(prefs().getBoolean("sound_enabled",true));startEngine();});
    }
    private void startEngine(){boot.starting(engine.generation);display.pictureObserved=false;loadingVisible(true);engine.start();engine.running(foreground);}
    private void loadingVisible(boolean visible){if(loader==null)return;loader.active(false);loader.setVisibility(visible?View.VISIBLE:View.GONE);if(sessionContent!=null)sessionContent.setImportantForAccessibility(visible?View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS:View.IMPORTANT_FOR_ACCESSIBILITY_AUTO);loader.active(visible&&foreground);}
    private void firstPicture(long generation){post(()->{if(display!=null&&display.pictureObserved&&boot.picture(generation,engine.generation))loadingVisible(false);});}
    @Override void error(String text){boot.failed();loadingVisible(false);super.error(text);}
    private final SessionMessages messages=new SessionMessages();
    private AlertDialog errorDialog;
    private void message(String s){post(()->{String value=s==null?"":s;if(value.startsWith("Engine error:")||value.startsWith("Engine exited")||value.startsWith("Display error:")||value.startsWith("Wait for")||value.contains("restart blocked")){boot.failed();loadingVisible(false);}if(SessionMessages.error(value)&&messages.begin(value)){if(errorDialog!=null&&errorDialog.isShowing())errorDialog.setMessage(value);else{errorDialog=new AlertDialog.Builder(this).setTitle("Pocket2Droid").setMessage(value).setPositiveButton("OK",null).create();errorDialog.setOnDismissListener(d->{errorDialog=null;messages.dismiss();});errorDialog.show();}}else if(value.startsWith("Pan image:")||value.equals("Guest touch enabled"))Toast.makeText(this,value,Toast.LENGTH_SHORT).show();});}
    private void blackWindow(){getWindow().setStatusBarColor(Color.BLACK);getWindow().setNavigationBarColor(Color.BLACK);getWindow().getDecorView().setBackgroundColor(Color.BLACK);if(Build.VERSION.SDK_INT>=29){getWindow().setStatusBarContrastEnforced(false);getWindow().setNavigationBarContrastEnforced(false);}}
    @Override public void onConfigurationChanged(android.content.res.Configuration config){super.onConfigurationChanged(config);theme();blackWindow();if(popup!=null)popup.dismiss();if(display!=null)applyPreferences();}
    private void build(){LinearLayout root=column();root.setBackgroundColor(Color.BLACK);toolbar=new LinearLayout(this);toolbar.setGravity(Gravity.CENTER_VERTICAL);toolbar.setBackgroundColor(TOOLBAR);TextView title=text(profile.displayName,17,TOOLBAR_TEXT);title.setSingleLine(true);title.setEllipsize(android.text.TextUtils.TruncateAt.END);title.setPadding(dp(12),0,dp(4),0);toolbar.addView(title,new LinearLayout.LayoutParams(0,dp(48),1));toolbar.addView(iconButton(ToolbarIcon.Symbol.MORE,"Session menu",this::showMenu),new LinearLayout.LayoutParams(dp(48),dp(48)));root.addView(toolbar);
        screen=new FrameLayout(this);screen.setBackgroundColor(Color.BLACK);display=new GuestSurface(this,engine,this::message,this::firstPicture);display.setContentDescription("Emulated display");display.setScaleMode(profile.settings.scale);display.setScreenPosition(profile.settings.screenPosition);display.resumed=foreground;display.rate.reset(System.nanoTime());screen.addView(display,new FrameLayout.LayoutParams(-1,-1));
        fps=text("Display FPS — paused",13,0xff98f2b5);fps.setPadding(dp(7),dp(3),dp(7),dp(3));fps.setBackgroundColor(0xb0000000);FrameLayout.LayoutParams fp=new FrameLayout.LayoutParams(-2,-2,Gravity.TOP|Gravity.LEFT);screen.addView(fps,fp);
        keys=new OnScreenControls(this,(code,down)->mappedKeys.touch(GuestKey.fromQcode(code),down),()->foreground&&!closing&&popup==null);
        screen.addView(keys,new FrameLayout.LayoutParams(-1,dp(144),Gravity.BOTTOM));screen.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,or,ob)->updateControlsLayout());overflow=iconButton(ToolbarIcon.Symbol.MORE,"Session menu",this::showMenu);screen.addView(overflow,new FrameLayout.LayoutParams(dp(48),dp(48),Gravity.TOP|Gravity.RIGHT));root.addView(screen,new LinearLayout.LayoutParams(-1,0,1));status=null;sessionContent=root;FrameLayout stage=new FrameLayout(this);stage.addView(root,new FrameLayout.LayoutParams(-1,-1));((ViewGroup)loader.getParent()).removeView(loader);stage.addView(loader,new FrameLayout.LayoutParams(-1,-1));install(stage);display.setOnTouchListener((v,event)->touch(event));applyPreferences();
    }
    private boolean touch(MotionEvent e){int a=e.getActionMasked();if(panMode){if(a==MotionEvent.ACTION_DOWN){panLastX=e.getX();panLastY=e.getY();}else if(a==MotionEvent.ACTION_MOVE){display.panBy(e.getX()-panLastX,e.getY()-panLastY);panLastX=e.getX();panLastY=e.getY();}return true;}
        if(a==MotionEvent.ACTION_UP||a==MotionEvent.ACTION_CANCEL){if(pointer)engine.touch(lastX,lastY,display.guestWidth,display.guestHeight,false);pointer=false;return true;}
        if(e.getPointerCount()!=1)return true;int[] mapped=display.geometry().touch(e.getX(),e.getY());if(mapped==null)return true;
        if(a==MotionEvent.ACTION_DOWN){pointer=true;lastX=mapped[0];lastY=mapped[1];engine.touch(lastX,lastY,display.guestWidth,display.guestHeight,true);}
        else if(a==MotionEvent.ACTION_MOVE&&pointer&&System.nanoTime()-lastMove>16_000_000){lastMove=System.nanoTime();lastX=mapped[0];lastY=mapped[1];engine.touch(lastX,lastY,display.guestWidth,display.guestHeight,true);}return true;
    }
    private void releaseTouch(){if(keys!=null)keys.release();if(pointer&&engine!=null)engine.touch(lastX,lastY,display.guestWidth,display.guestHeight,false);pointer=false;}
    private void releaseInput(){releaseTouch();if(mappedKeys!=null)mappedKeys.releaseAll();if(mappingInput!=null)mappingInput.beginCapture();}
    private boolean hardwareAccepting(){return foreground&&!closing&&popup==null&&display!=null&&hasWindowFocus()&&engine!=null&&engine.frameReady;}
    private void normalizedInput(int device,String token,boolean down,boolean fresh){if(mappedKeys==null)return;if(!down)mappedKeys.input(device,token,false);else if(fresh&&hardwareAccepting())mappedKeys.input(device,token,true);}
    private void updateControlsLayout(){if(screen==null||screen.getWidth()==0||screen.getHeight()==0)return;int height=ControlsLayout.panelHeight(screen.getWidth(),screen.getHeight(),getResources().getDisplayMetrics().density);FrameLayout.LayoutParams controlLayout=(FrameLayout.LayoutParams)keys.getLayoutParams();if(controlLayout.height!=height){keys.release();controlLayout.height=height;keys.setLayoutParams(controlLayout);}FrameLayout.LayoutParams imageLayout=(FrameLayout.LayoutParams)display.getLayoutParams();int reserved=keys.getVisibility()==View.VISIBLE?height:0;if(imageLayout.bottomMargin!=reserved){imageLayout.bottomMargin=reserved;display.setLayoutParams(imageLayout);}}
    private void applyPreferences(){if(display==null)return;fullscreen=prefs().getBoolean("fullscreen_enabled",false);boolean showKeys=prefs().getBoolean("keys_enabled",true),showFps=prefs().getBoolean("fps_enabled",true);if(!showKeys)releaseTouch();keys.setVisibility(showKeys?View.VISIBLE:View.GONE);display.counterEnabled=showFps;fps.setVisibility(showFps?View.VISIBLE:View.GONE);toolbar.setVisibility(fullscreen?View.GONE:View.VISIBLE);overflow.setVisibility(fullscreen&&popup!=null?View.VISIBLE:View.GONE);
        keys.preferences(controlsTransparency(),prefs().getBoolean("controls_vibration",true));updateControlsLayout();
        engine.sound(prefs().getBoolean("sound_enabled",true));setRequestedOrientation(profile.settings.orientation==RomSettings.HostOrientation.LANDSCAPE?ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE:ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);
        int flags=View.SYSTEM_UI_FLAG_LAYOUT_STABLE;if(fullscreen)flags|=View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY;getWindow().getDecorView().setSystemUiVisibility(flags);refreshInsets();ui.removeCallbacks(tick);if(showFps&&foreground)ui.post(tick);
    }
    private void showMenu(){if(engine==null||closing)return;if(popup!=null){popup.dismiss();return;}releaseInput();if(fullscreen)overflow.setVisibility(View.VISIBLE);View anchor=fullscreen?overflow:toolbar.getChildAt(1);popup=new PopupMenu(this,anchor);Menu menu=popup.getMenu();
        menu.add(0,1,0,"Sound").setCheckable(true).setChecked(prefs().getBoolean("sound_enabled",true));menu.add(0,2,1,"Display FPS counter").setCheckable(true).setChecked(prefs().getBoolean("fps_enabled",true));menu.add(0,3,2,"On-screen controls").setCheckable(true).setChecked(prefs().getBoolean("keys_enabled",true));menu.add(0,4,3,"Fullscreen").setCheckable(true).setChecked(fullscreen);
        if(profile.settings.scale==RomSettings.ScaleMode.PIXEL_PERFECT)menu.add(0,5,4,"Pan image").setCheckable(true).setChecked(panMode);
        menu.add(0,9,5,display.frameObserved?"Guest display: "+display.guestWidth+"×"+display.guestHeight:"Guest display: awaiting frame").setEnabled(false);
        if(!engine.alive()&&!engine.starting)menu.add(0,7,6,"Start");menu.add(0,8,7,"Exit");
        popup.setOnMenuItemClickListener(item->{int id=item.getItemId();String key=id==1?"sound_enabled":id==2?"fps_enabled":id==3?"keys_enabled":id==4?"fullscreen_enabled":null;if(key!=null){prefs().edit().putBoolean(key,!item.isChecked()).apply();applyPreferences();}else if(id==5){panMode=!panMode;message(panMode?"Pan image: drag to move; turn off to use guest touch":"Guest touch enabled");}else if(id==7){startEngine();}else if(id==8)exit();return true;});popup.setOnDismissListener(menuView->{popup=null;if(fullscreen)overflow.setVisibility(View.GONE);applyPreferences();});popup.show();
    }
    private void exit(){if(closing)return;closing=true;releaseInput();message("Saving and exiting…");engine.close(success->post(()->{closing=false;if(success){startActivity(new Intent(this,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP));finish();}else error("Save/exit did not complete. Existing data is preserved; retry Exit after checking the error.");}));}
    @Override public void onBackPressed(){if(display==null){finish();return;}showMenu();}
    @Override protected void onResume(){super.onResume();if(mappedKeys!=null){mappedKeys.releaseHardware();inputBindings=PreferenceButtonMappings.load(this);mappedKeys.bindings(inputBindings);mappingInput.beginCapture();}foreground=true;if(loader!=null)loader.active(loader.getVisibility()==View.VISIBLE);if(display!=null){display.resumed=true;display.rate.reset(System.nanoTime());engine.running(true);applyPreferences();}}
    @Override protected void onPause(){foreground=false;if(loader!=null)loader.active(false);ui.removeCallbacks(tick);if(display!=null){releaseInput();display.resumed=false;engine.running(false);}super.onPause();}
    @Override public void onWindowFocusChanged(boolean focus){super.onWindowFocusChanged(focus);if(display!=null){if(focus)applyPreferences();else releaseInput();}}
    @Override protected void onDestroy(){if(loader!=null)loader.active(false);releaseInput();if(inputManager!=null)inputManager.unregisterInputDeviceListener(this);if(mappingInput!=null)mappingInput.normalizer.releaseAll();ui.removeCallbacks(tick);if(display!=null)display.destroyed=true;if(engine!=null)engine.dispose();super.onDestroy();}
    public void onInputDeviceAdded(int id){}public void onInputDeviceChanged(int id){onInputDeviceRemoved(id);}public void onInputDeviceRemoved(int id){if(mappingInput!=null)mappingInput.normalizer.releaseDevice(id);if(mappedKeys!=null)mappedKeys.releaseDevice(id);}
    @Override public boolean dispatchKeyEvent(KeyEvent e){if(mappingInput!=null&&mappingInput.key(e)&&inputBindings.resolve(InputNormalizer.keyToken(e.getKeyCode()))!=null)return true;return super.dispatchKeyEvent(e);}
    @Override public boolean onGenericMotionEvent(MotionEvent e){return mappingInput!=null&&mappingInput.motion(e)||super.onGenericMotionEvent(e);}
}
