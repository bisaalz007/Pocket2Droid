package com.samsixx.pocket2droid;
import java.util.function.Function;
/** Capture state is transient; confirmation follows durable acceptance. */
final class MappingCapture {
 interface Listener {void selected(GuestKey key,boolean listening);void message(String text);}
 private final ButtonMappingStore store;private final Function<String,String> label;private final Listener listener;
 private GuestKey selected;private boolean listening;
 MappingCapture(ButtonMappingStore s,Function<String,String> l,Listener listener){store=s;label=l;this.listener=listener;}
 GuestKey selected(){return selected;}boolean listening(){return listening;}
 void select(GuestKey key){if(key==null||!key.visible)return;selected=key;listening=true;listener.selected(key,true);listener.message("Press any key to assign "+key.label);}
 void input(int device,String token,boolean down,boolean fresh){if(!listening||!down||!fresh||!ButtonBindings.validToken(token))return;
  ButtonBindings.Change change=store.current().assign(selected,token);if(!store.save(change.bindings)){listener.message("Could not save assignment. Previous mappings kept; try again.");return;}
  listening=false;listener.selected(selected,false);String message=selected.label+" mapped as "+label.apply(token);if(change.displacedTarget!=null)message+=" · "+change.displacedTarget.label+" assignment cleared";listener.message(message);
 }
 void cancel(){if(!listening)return;listening=false;listener.selected(selected,false);listener.message("Assignment cancelled");}
 boolean clearSelected(){if(selected==null)return false;if(!store.save(store.current().clear(selected))){listener.message("Could not save. Previous mappings kept.");return false;}listening=false;listener.selected(selected,false);listener.message(selected.label+" assignment cleared; defaults restored");return true;}
 boolean reset(){if(!store.save(ButtonBindings.defaults())){listener.message("Could not save. Previous mappings kept.");return false;}selected=null;listening=false;listener.selected(null,false);listener.message("Default mappings restored");return true;}
}
