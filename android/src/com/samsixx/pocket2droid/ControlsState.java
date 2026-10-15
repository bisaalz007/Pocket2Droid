package com.samsixx.pocket2droid;

import java.util.HashMap;
import java.util.Map;

/** Pointer IDs own held keys; only first press and last release reach the guest. */
final class ControlsState {
    interface Listener { void key(ControlsLayout.Key key, boolean down); }
    private final Listener listener;
    private final Map<Integer,ControlsLayout.Key> pointers = new HashMap<>();
    private final int[] owners = new int[ControlsLayout.Key.values().length];
    ControlsState(Listener listener) { this.listener=listener; }
    boolean held(ControlsLayout.Key key) { return owners[key.ordinal()]>0; }
    void update(int id, ControlsLayout.Key key) {
        ControlsLayout.Key previous=pointers.get(id);
        if (previous==key) return;
        remove(id);
        if (key!=null) {
            pointers.put(id,key);
            if (owners[key.ordinal()]++==0) listener.key(key,true);
        }
    }
    void remove(int id) {
        ControlsLayout.Key previous=pointers.remove(id);
        if (previous!=null && --owners[previous.ordinal()]==0) listener.key(previous,false);
    }
    void clear() {
        pointers.clear();
        for (ControlsLayout.Key key : ControlsLayout.Key.values()) {
            if (owners[key.ordinal()]>0) {
                owners[key.ordinal()]=0;
                listener.key(key,false);
            }
        }
    }
}
