"""Compile the actual help helper and exercise its held-key policy.

The Android SDK checks the UI API surface. KeyEvent is the only Android runtime
stub used by these event-policy probes; popup rendering is a device QA task.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ShortcutHelpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').exists() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').exists() else shutil.which('java')
        sdk = ROOT / '.local/android-sdk/platforms/android-36/android.jar'
        if not javac or not cls.java or not sdk.is_file():
            raise unittest.SkipTest('A JDK and the configured Android 36 SDK are required')
        temporary = tempfile.TemporaryDirectory(prefix='z8-shortcut-help-')
        cls.addClassCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        sources = [str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8ShortcutHelp.java')]
        for name, code in STUBS.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code)
            sources.append(str(path))
        result = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-cp', str(sdk), '-d', str(directory), *sources],
                                capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.classpath = str(directory) + os.pathsep + str(sdk)

    def probe(self, scenario):
        result = subprocess.run([self.java, '-cp', self.classpath, 'com.termux.app.ShortcutProbe', scenario],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS: ' + scenario, result.stdout)

    def test_only_exact_help_chords_are_owned(self):
        self.probe('chords')

    def test_letter_release_and_repeat_never_reopen_or_leak(self):
        self.probe('hold')

    def test_modifier_release_and_cancellation_close_the_hint(self):
        self.probe('release')

    def test_other_keyboard_and_unrelated_input_remain_independent(self):
        self.probe('devices')


STUBS = {
    'android/view/KeyEvent.java': '''package android.view; public class KeyEvent {
        public static final int ACTION_DOWN=0,ACTION_UP=1,ACTION_MULTIPLE=2;
        public static final int KEYCODE_H=36,KEYCODE_SLASH=76,KEYCODE_C=31,KEYCODE_V=50,
            KEYCODE_META_LEFT=117,KEYCODE_META_RIGHT=118,KEYCODE_CTRL_LEFT=113,KEYCODE_CTRL_RIGHT=114,
            KEYCODE_SHIFT_LEFT=59,KEYCODE_SHIFT_RIGHT=60,KEYCODE_ALT_LEFT=57;
        private final int action,key,modifiers,repeat,device;private final boolean canceled;
        public KeyEvent(int a,int k,int m,int r,int d,boolean c){action=a;key=k;modifiers=m;repeat=r;device=d;canceled=c;}
        public int getAction(){return action;}public int getKeyCode(){return key;}public int getDeviceId(){return device;}
        public int getRepeatCount(){return repeat;}public boolean isCanceled(){return canceled;}
        public boolean isShiftPressed(){return (modifiers&1)!=0;}public boolean isCtrlPressed(){return (modifiers&2)!=0;}
        public boolean isMetaPressed(){return (modifiers&4)!=0;}public boolean isAltPressed(){return (modifiers&8)!=0;}
    }''',
    'com/termux/app/Z8Theme.java': '''package com.termux.app; import android.content.Context;
        public class Z8Theme {public static class Palette {public boolean light;}
            public static Palette selected(Context context){return new Palette();}}
    ''',
    'com/termux/app/Z8ChromeStyle.java': '''package com.termux.app;import android.content.Context;import android.graphics.drawable.Drawable;
        public class Z8ChromeStyle {public int surface,border,accent,text,muted;
            public static Z8ChromeStyle from(Z8Theme.Palette palette){return new Z8ChromeStyle();}
            public Drawable shape(Context context,int fill,int stroke,int radius){return null;}}
    ''',
    'com/termux/app/ShortcutProbe.java': '''package com.termux.app;
        import android.view.KeyEvent;import static android.view.KeyEvent.*;
        public class ShortcutProbe {
            static final int SHIFT=1,CTRL=2,META=4,ALT=8;
            static final int OPEN=Z8ShortcutHelp.HoldPolicy.SHOW|Z8ShortcutHelp.HoldPolicy.CONSUME;
            static final int CLOSE=Z8ShortcutHelp.HoldPolicy.HIDE|Z8ShortcutHelp.HoldPolicy.CONSUME;
            static final int CONSUME=Z8ShortcutHelp.HoldPolicy.CONSUME,HIDE=Z8ShortcutHelp.HoldPolicy.HIDE;
            static void eq(int expected,int actual,String message){if(expected!=actual)throw new AssertionError(message+": "+actual);}
            static KeyEvent key(int action,int code,int mods){return new KeyEvent(action,code,mods,0,7,false);}
            static Z8ShortcutHelp.HoldPolicy fresh(){return new Z8ShortcutHelp.HoldPolicy();}
            public static void main(String[]args) {
                String scenario=args[0];Z8ShortcutHelp.HoldPolicy policy=fresh();
                if(scenario.equals("chords")) {
                    for(int mods=0;mods<16;mods++)for(int code:new int[]{KEYCODE_H,KEYCODE_SLASH,KEYCODE_C,KEYCODE_V}) {
                        int expected=code==KEYCODE_H&&mods==META||code==KEYCODE_SLASH&&mods==(CTRL|SHIFT)?OPEN:0;
                        eq(expected,fresh().accept(key(ACTION_DOWN,code,mods)),"only exact help chord, key="+code+" modifiers="+mods);
                    }
                    eq(0,policy.accept(key(ACTION_MULTIPLE,KEYCODE_H,META)),"multiple events are not help key presses");
                    eq(0,policy.accept(key(ACTION_UP,KEYCODE_H,META)),"unowned key release is not intercepted");
                } else if(scenario.equals("hold")) {
                    for(int code:new int[]{KEYCODE_H,KEYCODE_SLASH}) {
                        int mods=code==KEYCODE_H?META:CTRL|SHIFT;policy=fresh();
                        eq(0,policy.accept(new KeyEvent(ACTION_DOWN,code,mods,1,7,false)),"repeat after focus return cannot open");
                        eq(OPEN,policy.accept(key(ACTION_DOWN,code,mods)),"first press opens");
                        for(int repeat=1;repeat<20;repeat++)eq(CONSUME,policy.accept(new KeyEvent(ACTION_DOWN,code,mods,repeat,7,false)),"repeat is consumed without another popup");
                        eq(CLOSE,policy.accept(key(ACTION_UP,code,mods)),"letter release closes and consumes");
                        eq(OPEN,policy.accept(key(ACTION_DOWN,code,mods)),"new key press can reopen");
                    }
                } else if(scenario.equals("release")) {
                    for(int modifier:new int[]{KEYCODE_META_LEFT,KEYCODE_META_RIGHT,KEYCODE_CTRL_LEFT,KEYCODE_CTRL_RIGHT,KEYCODE_SHIFT_LEFT,KEYCODE_SHIFT_RIGHT}) {
                        boolean meta=modifier==KEYCODE_META_LEFT||modifier==KEYCODE_META_RIGHT;
                        int code=meta?KEYCODE_H:KEYCODE_SLASH,mods=meta?META:CTRL|SHIFT;policy=fresh();
                        eq(OPEN,policy.accept(key(ACTION_DOWN,code,mods)),"start chord");
                        eq(HIDE,policy.accept(key(ACTION_UP,modifier,mods)),"modifier release hides even with stale meta bits");
                        eq(CONSUME,policy.accept(new KeyEvent(ACTION_DOWN,code,mods,1,7,false)),"still-held letter cannot reopen after modifier release");
                        eq(CLOSE,policy.accept(key(ACTION_UP,code,0)),"owned letter release is still consumed after hiding");
                        eq(0,policy.accept(key(ACTION_DOWN,KEYCODE_H,CTRL)),"ordinary Ctrl+H still reaches terminal");
                    }
                    policy=fresh();policy.accept(key(ACTION_DOWN,KEYCODE_H,META));
                    eq(CLOSE,policy.accept(new KeyEvent(ACTION_UP,KEYCODE_H,META,0,7,true)),"canceled owned key closes");
                    eq(0,policy.accept(new KeyEvent(ACTION_DOWN,KEYCODE_H,META,3,7,false)),"canceled repeat cannot reopen");
                    policy=fresh();policy.accept(key(ACTION_DOWN,KEYCODE_SLASH,CTRL|SHIFT));
                    eq(HIDE,policy.accept(new KeyEvent(ACTION_UP,KEYCODE_CTRL_LEFT,SHIFT,0,7,true)),"canceled modifier closes hint");
                    eq(CONSUME,policy.accept(new KeyEvent(ACTION_DOWN,KEYCODE_SLASH,SHIFT,1,7,false)),"canceled modifier cannot leak remaining slash repeat");
                    eq(CLOSE,policy.accept(key(ACTION_UP,KEYCODE_SLASH,SHIFT)),"owned release stays consumed after canceled modifier");
                    policy=fresh();policy.accept(key(ACTION_DOWN,KEYCODE_SLASH,CTRL|SHIFT));
                    eq(HIDE,policy.accept(key(ACTION_DOWN,KEYCODE_ALT_LEFT,CTRL|SHIFT|ALT)),"different modifier ends chord");
                    eq(CONSUME,policy.accept(new KeyEvent(ACTION_DOWN,KEYCODE_SLASH,CTRL|SHIFT|ALT,1,7,false)),"altered repeated slash does not leak");
                } else if(scenario.equals("devices")) {
                    eq(OPEN,policy.accept(key(ACTION_DOWN,KEYCODE_H,META)),"start first keyboard");
                    eq(0,policy.accept(new KeyEvent(ACTION_UP,KEYCODE_H,0,0,8,false)),"second keyboard release cannot dismiss first");
                    eq(0,policy.accept(new KeyEvent(ACTION_DOWN,KEYCODE_C,CTRL,0,8,false)),"other keyboard Ctrl+C passes through");
                    eq(0,policy.accept(key(ACTION_DOWN,KEYCODE_C,META)),"unrelated shortcut not owned");
                    eq(CONSUME,policy.accept(new KeyEvent(ACTION_DOWN,KEYCODE_H,META,1,7,false)),"original chord still active");
                    eq(CLOSE,policy.accept(key(ACTION_UP,KEYCODE_H,0)),"original keyboard closes");
                    Z8ShortcutHelp.HoldPolicy other=fresh();
                    eq(0,other.accept(key(ACTION_UP,KEYCODE_H,0)),"activities do not share held-key state");
                } else throw new AssertionError(scenario);
                System.out.println("PASS: "+scenario);
            }
        }
    ''',
}


if __name__ == '__main__':
    unittest.main()
