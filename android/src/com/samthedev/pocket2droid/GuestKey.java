package com.samthedev.pocket2droid;
import java.util.*;

/** Windows Mobile targets, independent of the gameplay artwork. */
enum GuestKey {
 CALL("Call","f3"), END_CALL("End call","f4"),
 SOFT_LEFT("Left soft key","f1"), SOFT_RIGHT("Right soft key","f2"),
 UP("Up","up"), DOWN("Down","down"), LEFT("Left","left"), RIGHT("Right","right"),
 ENTER("Enter / Select","ret"), BACK("Back","esc"), TAB("Tab","tab"), SPACE("Space","spc"), HOME("Home","meta_l"),
 DIGIT_1("1","1"),DIGIT_2("2","2"),DIGIT_3("3","3"),DIGIT_4("4","4"),DIGIT_5("5","5"),
 DIGIT_6("6","6"),DIGIT_7("7","7"),DIGIT_8("8","8"),DIGIT_9("9","9"),DIGIT_0("0","0"),
 STAR("*","f8"),HASH("#","f9"),BACKSPACE("Backspace","backspace",false);
 final String label,qcode; final boolean visible;
 GuestKey(String label,String qcode){this(label,qcode,true);}
 GuestKey(String label,String qcode,boolean visible){this.label=label;this.qcode=qcode;this.visible=visible;}
 static GuestKey fromQcode(String code){for(GuestKey key:values())if(key.qcode.equals(code))return key;return null;}
 static List<GuestKey> mappingTargets(){List<GuestKey> keys=new ArrayList<>();for(GuestKey k:values())if(k.visible)keys.add(k);return Collections.unmodifiableList(keys);}
}
