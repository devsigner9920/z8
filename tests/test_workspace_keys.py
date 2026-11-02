"""Exercise the actual workspace key policy with deterministic Android key events."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-workspace-keys-test-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        sources = []
        for name, code in STUBS.items():
            path = cls.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code)
            sources.append(str(path))
        actual = ROOT / 'overlay/app/src/main/java/com/termux/app/Z8WorkspaceKeys.java'
        result = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(cls.directory), str(actual), *sources],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, name):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.WorkspaceKeysProbe', name],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS workspace-keys ' + name)

    def test_new_terminal_and_browser_chords_invoke_host_once(self):
        self.probe('create')

    def test_tab_navigation_passes_direction_to_workspace_host(self):
        self.probe('cycle')

    def test_browser_address_reload_and_escape_are_context_sensitive(self):
        self.probe('browser')

    def test_terminal_controls_alt_combinations_and_plain_keys_pass_through(self):
        self.probe('terminal')

    def test_repeats_and_key_up_are_consumed_even_after_modifiers_release(self):
        self.probe('repeat')

    def test_simultaneous_shortcuts_and_multiple_keyboards_do_not_share_pressed_state(self):
        self.probe('devices')

    def test_focus_reset_does_not_retrigger_repeated_shortcut(self):
        self.probe('reset')

    def test_cancelled_and_multiple_events_never_execute_commands(self):
        self.probe('cancel')


STUBS = {
    'android/view/KeyEvent.java': r'''
        package android.view;
        public final class KeyEvent {
            public static final int ACTION_DOWN=0, ACTION_UP=1, ACTION_MULTIPLE=2;
            public static final int KEYCODE_T=48, KEYCODE_B=30, KEYCODE_L=40, KEYCODE_R=46,
                KEYCODE_TAB=61, KEYCODE_ESCAPE=111;
            public static final int CTRL=1, SHIFT=2, META=4, ALT=8;
            private final int action,key,modifiers,repeat,device;
            private final boolean canceled;
            public KeyEvent(int action,int key,int modifiers,int repeat,int device,boolean canceled) {
                this.action=action;this.key=key;this.modifiers=modifiers;this.repeat=repeat;this.device=device;this.canceled=canceled;
            }
            public int getAction(){return action;} public int getKeyCode(){return key;}
            public int getDeviceId(){return device;} public int getRepeatCount(){return repeat;}
            public boolean isCanceled(){return canceled;}
            public boolean isCtrlPressed(){return (modifiers&CTRL)!=0;}
            public boolean isShiftPressed(){return (modifiers&SHIFT)!=0;}
            public boolean isMetaPressed(){return (modifiers&META)!=0;}
            public boolean isAltPressed(){return (modifiers&ALT)!=0;}
        }
    ''',
    'com/termux/app/WorkspaceKeysProbe.java': r'''
        package com.termux.app;
        import android.view.KeyEvent;
        import static android.view.KeyEvent.*;
        import java.util.ArrayList;
        import java.util.Arrays;
        import java.util.List;
        public final class WorkspaceKeysProbe {
            private static final class Host implements Z8WorkspaceKeys.Host {
                boolean browser;
                final List<String> actions=new ArrayList<>();
                public boolean isBrowserSelected(){return browser;}
                public void newTerminal(){actions.add("terminal");browser=false;}
                public void cycleTabs(int direction){actions.add("cycle:"+direction);}
                public void openBrowser(){actions.add("browser");browser=true;}
                public void focusBrowserAddress(){actions.add("address");}
                public void reloadBrowser(){actions.add("reload");}
                public void returnToTerminal(){actions.add("return");browser=false;}
            }
            private static KeyEvent e(int action,int key,int mods,int repeat,int device,boolean canceled) {
                return new KeyEvent(action,key,mods,repeat,device,canceled);
            }
            private static KeyEvent down(int key,int mods){return e(ACTION_DOWN,key,mods,0,1,false);}
            private static KeyEvent up(int key){return e(ACTION_UP,key,0,0,1,false);}
            private static void yes(boolean value){if(!value)throw new AssertionError("Expected consumed");}
            private static void no(boolean value){if(value)throw new AssertionError("Unexpected consumed");}
            private static void actions(Host host,String... expected) {
                if(!host.actions.equals(Arrays.asList(expected)))throw new AssertionError("Unexpected actions: "+host.actions);
            }
            public static void main(String[] args) {
                Host host=new Host();Z8WorkspaceKeys keys=new Z8WorkspaceKeys(host);
                switch(args[0]) {
                    case "create":
                        yes(keys.dispatch(down(KEYCODE_T,CTRL|SHIFT)));yes(keys.dispatch(up(KEYCODE_T)));
                        yes(keys.dispatch(down(KEYCODE_T,META)));yes(keys.dispatch(up(KEYCODE_T)));
                        yes(keys.dispatch(down(KEYCODE_B,CTRL|SHIFT)));yes(keys.dispatch(up(KEYCODE_B)));
                        actions(host,"terminal","terminal","browser");break;
                    case "cycle":
                        yes(keys.dispatch(down(KEYCODE_TAB,CTRL)));yes(keys.dispatch(up(KEYCODE_TAB)));
                        host.browser=true;
                        yes(keys.dispatch(down(KEYCODE_TAB,CTRL|SHIFT)));yes(keys.dispatch(up(KEYCODE_TAB)));
                        actions(host,"cycle:1","cycle:-1");break;
                    case "browser":
                        for(int key:new int[]{KEYCODE_L,KEYCODE_R}){no(keys.dispatch(down(key,CTRL)));no(keys.dispatch(up(key)));}
                        no(keys.dispatch(down(KEYCODE_ESCAPE,0)));no(keys.dispatch(up(KEYCODE_ESCAPE)));
                        host.browser=true;
                        yes(keys.dispatch(down(KEYCODE_L,CTRL)));yes(keys.dispatch(up(KEYCODE_L)));
                        yes(keys.dispatch(down(KEYCODE_R,CTRL)));yes(keys.dispatch(up(KEYCODE_R)));
                        yes(keys.dispatch(down(KEYCODE_ESCAPE,0)));yes(keys.dispatch(up(KEYCODE_ESCAPE)));
                        no(keys.dispatch(down(KEYCODE_ESCAPE,0)));actions(host,"address","reload","return");break;
                    case "terminal":
                        host.browser=false;
                        for(int key:new int[]{KEYCODE_T,KEYCODE_B,KEYCODE_L,KEYCODE_R,KEYCODE_TAB,KEYCODE_ESCAPE,31,50,36}) {
                            no(keys.dispatch(down(key,0)));no(keys.dispatch(up(key)));
                            no(keys.dispatch(down(key,ALT|CTRL|SHIFT)));no(keys.dispatch(up(key)));
                            no(keys.dispatch(down(key,META|CTRL|SHIFT)));no(keys.dispatch(up(key)));
                        }
                        for(int key:new int[]{KEYCODE_T,KEYCODE_B,KEYCODE_L,KEYCODE_R,31,50,36}) {
                            no(keys.dispatch(down(key,CTRL)));no(keys.dispatch(up(key)));
                        }
                        host.browser=true;
                        for(int key:new int[]{KEYCODE_L,KEYCODE_R,KEYCODE_ESCAPE}) {
                            no(keys.dispatch(down(key,CTRL|SHIFT)));no(keys.dispatch(up(key)));
                        }
                        no(keys.dispatch(down(KEYCODE_T,META|SHIFT)));actions(host);break;
                    case "repeat":
                        yes(keys.dispatch(down(KEYCODE_T,CTRL|SHIFT)));
                        yes(keys.dispatch(e(ACTION_DOWN,KEYCODE_T,CTRL|SHIFT,1,1,false)));
                        yes(keys.dispatch(e(ACTION_DOWN,KEYCODE_T,0,2,1,false)));
                        no(keys.dispatch(up(113))); // A modifier release remains available to Android.
                        yes(keys.dispatch(up(KEYCODE_T)));no(keys.dispatch(up(KEYCODE_T)));
                        no(keys.dispatch(down(KEYCODE_T,0)));actions(host,"terminal");break;
                    case "devices":
                        yes(keys.dispatch(down(KEYCODE_T,CTRL|SHIFT)));
                        no(keys.dispatch(e(ACTION_UP,KEYCODE_T,0,0,2,false)));
                        yes(keys.dispatch(e(ACTION_DOWN,KEYCODE_T,META,0,2,false)));
                        yes(keys.dispatch(down(KEYCODE_B,CTRL|SHIFT)));
                        yes(keys.dispatch(up(KEYCODE_T)));yes(keys.dispatch(up(KEYCODE_B)));
                        yes(keys.dispatch(e(ACTION_UP,KEYCODE_T,0,0,2,false)));
                        actions(host,"terminal","terminal","browser");break;
                    case "reset":
                        yes(keys.dispatch(down(KEYCODE_T,CTRL|SHIFT)));keys.reset();
                        yes(keys.dispatch(e(ACTION_DOWN,KEYCODE_T,CTRL|SHIFT,8,1,false)));
                        yes(keys.dispatch(up(KEYCODE_T)));actions(host,"terminal");
                        yes(keys.dispatch(down(KEYCODE_T,CTRL|SHIFT)));keys.reset();
                        no(keys.dispatch(down(KEYCODE_T,0)));no(keys.dispatch(up(KEYCODE_T)));
                        actions(host,"terminal","terminal");break;
                    case "cancel":
                        yes(keys.dispatch(e(ACTION_DOWN,KEYCODE_T,CTRL|SHIFT,0,1,true)));
                        yes(keys.dispatch(e(ACTION_UP,KEYCODE_T,0,0,1,true)));
                        no(keys.dispatch(e(ACTION_MULTIPLE,KEYCODE_T,CTRL|SHIFT,0,1,false)));
                        no(keys.dispatch(up(KEYCODE_T)));actions(host);
                        yes(keys.dispatch(down(KEYCODE_T,CTRL|SHIFT)));
                        yes(keys.dispatch(e(ACTION_UP,KEYCODE_T,0,0,1,true)));
                        yes(keys.dispatch(down(KEYCODE_T,CTRL|SHIFT)));actions(host,"terminal","terminal");break;
                    default:throw new AssertionError("Unknown probe");
                }
                System.out.println("PASS workspace-keys "+args[0]);
            }
        }
    ''',
}
