package com.samthedev.pocket2droid;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Real control geometry and pointer ownership, independent of Android UI. */
public final class ControlsTest {
    private static int checks;
    private static void check(boolean value, String message) {
        checks++;
        if (!value) throw new AssertionError(message);
    }
    private static void key(ControlsLayout layout, float x, float y,
                            ControlsLayout.Key expected) {
        check(layout.hit(x, y) == expected, "hit " + x + "," + y + " expected " + expected);
    }
    public static void main(String[] args) {
        ControlsLayout.Key[] expected = {ControlsLayout.Key.SOFT_LEFT, ControlsLayout.Key.SOFT_RIGHT,
            ControlsLayout.Key.BACK, ControlsLayout.Key.TAB, ControlsLayout.Key.SPACE, ControlsLayout.Key.HOME,
            ControlsLayout.Key.UP, ControlsLayout.Key.DOWN, ControlsLayout.Key.LEFT,
            ControlsLayout.Key.RIGHT, ControlsLayout.Key.SELECT};
        float[][] points = {{65,22},{366,22},{33,99},{100,99},{330,99},{400,99},
                            {218,35},{218,127},{163,80},{273,80},{218,80}};
        for (float scale : new float[]{0.65f, 1f, 2.5f}) {
            // Both a narrow portrait panel and a wide landscape panel.
            for (float extra : new float[]{0, 300}) {
                ControlsLayout layout = new ControlsLayout(434 * scale + extra, 158 * scale);
                for (int i = 0; i < expected.length; i++)
                    key(layout, extra / 2 + points[i][0] * scale, points[i][1] * scale, expected[i]);
                key(layout, extra / 2 + 70 * scale, 100 * scale, null);
                key(layout, extra / 2 + 218 * scale, 150 * scale, null);
                key(layout, -1, 20, null);
                key(layout, 434 * scale + extra, 20, null);
                check(layout.rect(ControlsLayout.Key.SELECT).width() < layout.pad.width() * .45f,
                      "small Select artwork");
            }
        }
        ControlsLayout mapped = new ControlsLayout(434, 158);
        ControlsLayout.Key tab = mapped.hit(100, 99), space = mapped.hit(330, 99);
        check(tab.qcode.equals("tab"), "left former Call button sends Tab");
        check(space.qcode.equals("spc"), "right former End button sends Space");
        ControlsLayout zero = new ControlsLayout(0, 0);
        key(zero, 0, 0, null);
        List<String> events = new ArrayList<>();
        ControlsState state = new ControlsState((k, down) -> events.add(k.qcode + ":" + down));
        state.update(3, ControlsLayout.Key.UP);
        state.update(3, ControlsLayout.Key.UP); // Moves within a held key never retrigger.
        state.update(9, ControlsLayout.Key.UP); // Two fingers own one physical key.
        state.remove(3);
        check(state.held(ControlsLayout.Key.UP), "second pointer retains key");
        state.update(9, ControlsLayout.Key.RIGHT); // Release old direction before new press.
        state.update(12, ControlsLayout.Key.TAB);
        state.update(9, null); // Sliding outside releases direction.
        check(events.equals(Arrays.asList("up:true", "up:false", "right:true", "tab:true", "right:false")),
              "multi-touch and slide event order: " + events);
        state.clear();
        state.clear(); // Cancel/pause/hidden release only once.
        state.remove(12);
        check(events.get(events.size() - 1).equals("tab:false") && events.size() == 6, "cancel releases all once");
        check(!state.held(ControlsLayout.Key.TAB), "cancel clears pressed overlay");
        state.update(1, ControlsLayout.Key.SOFT_LEFT);
        state.update(2, ControlsLayout.Key.SELECT);
        state.remove(1);
        check(state.held(ControlsLayout.Key.SELECT), "soft key release retains Select");
        state.clear();
        check(events.contains("f1:true") && events.contains("ret:true"), "soft and Select mappings");
        events.clear();
        state.update(21,ControlsLayout.Key.UP);
        state.update(42,ControlsLayout.Key.SELECT);
        state.update(7,ControlsLayout.Key.SOFT_RIGHT);
        check(state.held(ControlsLayout.Key.UP) && state.held(ControlsLayout.Key.SELECT) && state.held(ControlsLayout.Key.SOFT_RIGHT),
              "three different keys held together");
        state.remove(42);
        check(state.held(ControlsLayout.Key.UP) && state.held(ControlsLayout.Key.SOFT_RIGHT) && !state.held(ControlsLayout.Key.SELECT),
              "middle pointer release keeps both other keys");
        state.update(21,ControlsLayout.Key.LEFT);
        check(state.held(ControlsLayout.Key.LEFT) && state.held(ControlsLayout.Key.SOFT_RIGHT),"direction slide preserves soft key");
        state.remove(7);state.remove(21);
        check(events.equals(Arrays.asList("up:true","ret:true","f2:true","ret:false","up:false","left:true","f2:false","left:false")),
              "three-key exact press/release order");
        events.clear();
        state.update(1, tab);
        state.update(2, space);
        state.update(3, ControlsLayout.Key.SELECT);
        state.update(4, ControlsLayout.Key.LEFT);
        state.update(5, tab); // Shared Tab ownership must survive the first release.
        state.remove(1);
        check(state.held(tab) && state.held(space) && state.held(ControlsLayout.Key.SELECT)
              && state.held(ControlsLayout.Key.LEFT), "Tab, Space, Enter and direction held together");
        state.remove(2);
        check(state.held(tab) && state.held(ControlsLayout.Key.SELECT)
              && !state.held(space), "Space release preserves Tab and Enter");
        state.remove(5);
        state.clear();
        check(events.equals(Arrays.asList("tab:true", "spc:true", "ret:true", "left:true",
                                         "spc:false", "tab:false", "left:false", "ret:false")),
              "Tab/Space/Enter independent make and break: " + events);
        for (int[] size : new int[][]{{393,750},{868,360},{800,1000},{240,220}}) {
            int height=ControlsLayout.panelHeight(size[0],size[1],1);
            check(height<=Math.round(size[1]*.36f) && height<=144,"controls leave room for guest");
            ControlsLayout l=new ControlsLayout(size[0],height);
            check(l.pad.left>=0 && l.pad.right<=size[0] && l.pad.bottom<=height,"panel stays in viewport");
        }
        System.out.println(checks + " control geometry/input assertions passed");
        if (args.length>0 && args[0].equals("--layout")) {
            ControlsLayout l=new ControlsLayout(434,158);
            System.out.println("{\"pad\":"+json(l.pad)+",\"buttons\":{");
            ControlsLayout.Key[] keys=ControlsLayout.Key.values();
            for (int i=0;i<keys.length;i++) System.out.println("\""+keys[i]+"\":"+json(l.rect(keys[i]))+(i==keys.length-1?"":","));
            System.out.println("}}");
        }
    }
    private static String json(ControlsLayout.Rect r) {return "["+r.left+","+r.top+","+r.right+","+r.bottom+"]";}
}
