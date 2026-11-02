"""Run real input policy behavior, plus fail-closed pinned-source patch contracts."""
from pathlib import Path
import importlib.util
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def java_method(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        if source[end] == '{': depth += 1
        elif source[end] == '}': depth -= 1
        end += 1
    return source[start:end]


class TerminalInputBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-input-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        cls.java = str(jdk / 'java')
        source = cls.directory / 'InputProbe.java'
        source.write_text(r'''import com.termux.view.Z8TerminalInput;
        import java.util.Arrays;
        public class InputProbe {
            static void check(boolean value) { if (!value) throw new AssertionError(); }
            static void range(int[] got, int... expected) { check(Arrays.equals(got, expected)); }
            public static void main(String[] args) {
                Z8TerminalInput input = new Z8TerminalInput();
                check(input.range(10, 1) == null);
                input.begin(8, -4);
                check(input.range(8, -4) == null); // Focus-only click must not select.
                range(input.range(12, -4), 8, -4, 12, -4);
                range(input.range(3, -6), 3, -6, 8, -4); // Backwards scrollback drag.
                range(input.range(2, -2), 8, -4, 2, -2); // Next row beats column ordering.
                range(input.range(8, -4), 8, -4, 8, -4); // Drag back shrinks to anchor.
                input.finish();
                check(!input.isDragging() && input.range(1, 1) == null); // No stale drag after switch/cancel.
                input.begin(0, 0);
                check(input.range(0, 0) == null); // Prior drag state does not leak.
                check(input.scrollRows(1, 4, 0) == -3); // Wheel detent remains three rows.
                check(input.scrollRows(-2, 4, 0) == 6);
                check(input.scrollRows(0, 4, 0) == 0); // Horizontal-only event is not a down tick.
                input.resetScroll();
                check(input.scrollRows(.25f, 4, 0) == 0);
                check(input.scrollRows(.25f, 4, 0) == -1);
                check(input.scrollRows(.25f, 4, 0) == -1);
                check(input.scrollRows(.25f, 4, 0) == -1); // Four fractions conserve one detent.
                input.resetScroll();
                check(input.scrollRows(.25f, 4, 0) == 0);
                check(input.scrollRows(.25f, 5, 0) == 0); // New pointer device cannot inherit fractions.
                check(input.scrollRows(.25f, 5, 1) == 0); // Local scroll cannot leak into TUI reporting.
                check(input.scrollRows(.25f, 5, 2) == 0); // Alternate-screen key route also resets.
                input.resetScroll();
                check(input.scrollRows(.25f, 5, 2) == 0); // A new PTY starts with no accumulated motion.
                check(input.scrollRows(Float.NaN, 5, 2) == 0);
                check(input.scrollRows(Float.POSITIVE_INFINITY, 5, 2) == 0);
                input.resetScroll();
                check(input.scrollRows(Float.MAX_VALUE, 5, 0) == -120); // Bound per-event UI work.
                check(input.scrollRows(-Float.MAX_VALUE, 5, 0) == 120);
                check(!Z8TerminalInput.requiresPasteConfirmation("echo 안전😀"));
                for (String text : new String[]{"\n", "\r", "echo A\necho B", "echo A\r\necho B", "echo A\r"})
                    check(Z8TerminalInput.requiresPasteConfirmation(text));
                check(!Z8TerminalInput.isBulkImePaste("\n")); // Physical/IME Enter remains Enter.
                check(Z8TerminalInput.isBulkImePaste("one\ntwo"));
                check(Z8TerminalInput.isBulkImePaste("\r\n"));
                check(!Z8TerminalInput.isBulkImePaste("한글 조합"));
                // Every modifier combination uses the real Android-independent classifier.
                for (int modifiers = 0; modifiers < 16; modifiers++) {
                    boolean meta = (modifiers & 1) != 0, ctrl = (modifiers & 2) != 0;
                    boolean shift = (modifiers & 4) != 0, alt = (modifiers & 8) != 0;
                    boolean clipboard = !alt && (meta || ctrl && shift);
                    check(Z8TerminalInput.clipboardShortcut('c', meta, ctrl, shift, alt)
                        == (clipboard ? Z8TerminalInput.ClipboardShortcut.COPY : Z8TerminalInput.ClipboardShortcut.NONE));
                    check(Z8TerminalInput.clipboardShortcut('v', meta, ctrl, shift, alt)
                        == (clipboard ? Z8TerminalInput.ClipboardShortcut.PASTE : Z8TerminalInput.ClipboardShortcut.NONE));
                    check(Z8TerminalInput.clipboardShortcut('x', meta, ctrl, shift, alt) == Z8TerminalInput.ClipboardShortcut.NONE);
                }
                System.out.println("PASS input behavior");
            }
        }''')
        actual = ROOT / 'overlay/terminal-view/src/main/java/com/termux/view/Z8TerminalInput.java'
        result = subprocess.run([str(jdk / 'javac'), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(cls.directory), str(actual), str(source)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    def test_drag_order_reset_and_multiline_input_policy(self):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'InputProbe'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS input behavior', result.stdout)

    def test_real_pinned_patch_routes_every_app_paste_and_clears_session_selection(self):
        spec = importlib.util.spec_from_file_location('prepare_input_test', ROOT / 'tools/prepare-app.py')
        prepare = importlib.util.module_from_spec(spec); spec.loader.exec_module(prepare)
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            for module in ('terminal-view', 'app'):
                source = ROOT / 'upstream/termux-app' / module / 'src/main/java'
                shutil.copytree(source, tree / module / 'src/main/java')
            spec = importlib.util.spec_from_file_location('input_patch_test', ROOT / 'tools/patch-terminal-input.py')
            patch = importlib.util.module_from_spec(spec); spec.loader.exec_module(patch)
            patch.patch(tree, prepare.replace_exact)
            view = (tree / 'terminal-view/src/main/java/com/termux/view/TerminalView.java').read_text()
            attach = view.split('public boolean attachSession(', 1)[1].split('public InputConnection', 1)[0]
            self.assertLess(attach.index('forceStopTextSelectionMode();'), attach.index('mTermSession = session;'))
            self.assertIn('mZ8PasteDialog.dismiss()', attach)
            self.assertNotIn('com.termux.app.Z8Text', view)  # Library cannot depend on its host app.
            self.assertLess(attach.index('updateSize();'), attach.index('z8RefreshAccessibilityText();'))
            self.assertNotIn('onScreenUpdated(', attach) # Preserve scroll state while updating a11y text.
            self.assertNotIn('mAccessibilityEnabled', view)
            self.assertIn('enabled -> z8RefreshAccessibilityText()', view)
            attached = view.split('protected void onAttachedToWindow() {', 1)[1].split('protected void onDetachedFromWindow()', 1)[0]
            self.assertIn('addAccessibilityStateChangeListener(mZ8AccessibilityListener)', attached)
            detached = view.split('protected void onDetachedFromWindow() {', 1)[1].split('private final Runnable', 1)[0]
            self.assertIn('removeAccessibilityStateChangeListener(mZ8AccessibilityListener)', detached)
            self.assertIn('setContentDescription(null)', detached)
            refresh = view.split('private void z8RefreshAccessibilityText() {', 1)[1].split('public void forceStopTextSelectionMode()', 1)[0]
            self.assertIn('mZ8AccessibilityManager.isEnabled() && mEmulator != null', refresh)
            self.assertIn('else if (getContentDescription() != null)', refresh)

            self.assertIn('mScroller.abortAnimation();', attach)
            self.assertLess(attach.index('mZ8Input.resetScroll();'), attach.index('mTermSession = session;'))
            self.assertIn('mZ8Input.resetScroll();', detached)
            self.assertIn('mGestureRecognizer.cancel();', attach)
            self.assertIn('mGestureRecognizer.cancel();', detached)
            gestures = (tree / 'terminal-view/src/main/java/com/termux/view/GestureAndScaleRecognizer.java').read_text()
            self.assertIn('MotionEvent.ACTION_CANCEL', gestures)
            self.assertIn('finally { cancel.recycle(); }', gestures)
            self.assertIn('mEmulator == null || mTermSession != z8FlingSession || mouseTrackingAtStartOfFling', view)
            self.assertIn('if (mEmulator == null || mGestureRecognizer.isInProgress()) return;', view)
            key_down = view.split('public boolean onKeyDown(int keyCode, KeyEvent event) {', 1)[1].split('public void inputCodePoint', 1)[0]
            self.assertLess(key_down.index('z8HandleClipboardShortcut(keyCode, event)'), key_down.index('if (isSelectingText()'))
            self.assertLess(key_down.index('z8HandleClipboardShortcut(keyCode, event)'), key_down.index('mClient.onKeyDown'))
            self.execute_shortcut_dispatch(tree, view)
            self.execute_scroll_dispatch(tree, view)
            self.execute_scroll_routes(tree, view)
            self.assertIn('!KeyEvent.isModifierKey(keyCode)', view)
            self.assertIn('mTermSession == target && mEmulator == emulator && target.isRunning()', view)
            self.assertIn('mEmulator.isMouseTrackingActive() && (event.getMetaState() & KeyEvent.META_SHIFT_ON) == 0', view)
            self.assertEqual(view.count('mTermSession.onPasteTextFromClipboard();'), 2)
            self.assertNotIn('mEmulator.paste(', view) # All routes use captured live emulator in pasteText.
            self.assertIn('PointerIcon.TYPE_TEXT', view)
            # A delayed Android Autofill result belongs to the PTY which requested
            # it, not whichever project happens to occupy the same view now.
            autofill = '\n'.join(java_method(view, signature) for signature in (
                'public void autofill(AutofillValue value)',
                'private synchronized void resetAutoFill()',
                'public synchronized void requestAutoFill(String[] autoFillHints)',
                'public synchronized void cancelRequestAutoFill()',
            ))
            source = tree / 'AutofillProbe.java'
            source.write_text('''public class AutofillProbe {
                static final String LOG_TAG="fixture";
                static final int AUTOFILL_TYPE_NONE=0,AUTOFILL_TYPE_TEXT=1,
                    IMPORTANT_FOR_AUTOFILL_NO=0,IMPORTANT_FOR_AUTOFILL_YES=1;
                static class Build { static class VERSION { static final int SDK_INT=37; }
                    static class VERSION_CODES { static final int O=26; } }
                static class AutofillValue {
                    boolean isText() { return true; }
                    CharSequence getTextValue() { return "fixture"; }
                }
                static class Session { String text; boolean running=true; boolean isRunning(){return running;}
                    void write(String value) { text = value; } }
                static class TerminalSession extends Session {}
                TerminalSession mTermSession, mZ8AutofillSession;
                boolean mZ8InputSuspended;
                int mAutoFillType,mAutoFillImportance,pastes;
                String[] mAutoFillHints=new String[0];
                static class AutofillManager {
                    boolean enabled=true,failRequest,failCancel;int requests,cancels;
                    boolean isEnabled(){return enabled;}
                    void requestAutofill(Object view){requests++;if(failRequest)throw new IllegalStateException();}
                    void cancel(){cancels++;if(failCancel)throw new IllegalStateException();}
                }
                static class Client { void logStackTraceWithMessage(String tag,String text,Exception e){} }
                final Client mClient=new Client();
                final AutofillManager manager=new AutofillManager();
                AutofillManager getAutoFillManagerService(){return manager;}
                void pasteText(String text){pastes++;mTermSession.write(text);}
                void request(){requestAutoFill(new String[]{"fixture"});}
                static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
                ''' + autofill + '''
                public static void main(String[] args) {
                    AutofillProbe view = new AutofillProbe();
                    view.autofill(new AutofillValue());
                    check(view.mAutoFillType==0&&view.mZ8AutofillSession==null,"Detached autofill reset");
                    view.mTermSession = new TerminalSession();
                    view.request();
                    TerminalSession requested = view.mTermSession;
                    check(view.mZ8AutofillSession==requested,"Request captures original PTY");
                    view.mTermSession = new TerminalSession();
                    view.autofill(new AutofillValue());
                    if (view.mTermSession.text != null || requested.text != null)
                        throw new AssertionError("Delayed autofill crossed into another PTY");
                    view.request();
                    view.autofill(new AutofillValue());
                    if (!"fixture".equals(view.mTermSession.text) || view.pastes != 1)
                        throw new AssertionError("Live autofill changed");
                    view.mTermSession.text=null;
                    view.autofill(new AutofillValue());
                    if (view.mTermSession.text != null) throw new AssertionError("Unrequested repeat autofill");
                    view.request();view.mZ8InputSuspended=true;
                    view.autofill(new AutofillValue());
                    if (view.mTermSession.text != null) throw new AssertionError("Paused autofill");
                    view.mZ8InputSuspended=false;view.request();view.mTermSession.running=false;
                    view.autofill(new AutofillValue());
                    if (view.mTermSession.text != null) throw new AssertionError("Exited PTY autofill");
                    view.mTermSession.running=true;view.request();
                    view.cancelRequestAutoFill();
                    check(view.manager.cancels==1&&view.mZ8AutofillSession==null&&view.mAutoFillType==0,
                        "Cancel revokes request and platform dataset");
                    view.request();view.manager.enabled=false;view.cancelRequestAutoFill();
                    check(view.mZ8AutofillSession==null,"Disabled provider still revokes local request");
                    view.manager.enabled=true;view.request();view.manager.failCancel=true;
                    view.cancelRequestAutoFill();view.autofill(new AutofillValue());
                    check(view.mTermSession.text==null,"Failed provider cancellation cannot type");
                    view.manager.failCancel=false;view.manager.failRequest=true;view.request();
                    check(view.mZ8AutofillSession==null&&view.mAutoFillType==0,"Request failure revokes capture");
                    int requests=view.manager.requests;
                    view.mZ8InputSuspended=true;view.request();
                    check(view.manager.requests==requests,"Paused view cannot request datasets");
                    view.mZ8InputSuspended=false;view.mTermSession.running=false;view.request();
                    check(view.manager.requests==requests,"Exited PTY cannot request datasets");
                }
            }''')
            javac = ROOT / '.local/jdk/Contents/Home/bin/javac'
            compiled = subprocess.run([str(javac), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-d', str(tree), str(source)], capture_output=True, text=True, timeout=15)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([self.java, '-cp', str(tree), 'AutofillProbe'], capture_output=True, text=True, timeout=10)
            self.assertEqual(executed.returncode, 0, executed.stderr)
            self.assertLess(attach.index('cancelRequestAutoFill();'), attach.index('mTermSession = session;'))
            self.assertIn('cancelRequestAutoFill();', detached)
            self.assertIn('cancelRequestAutoFill();', java_method(view, 'public void z8SuspendInput()'))
            for name in ('TermuxTerminalSessionActivityClient', 'TermuxTerminalViewClient'):
                code = (tree / ('app/src/main/java/com/termux/app/terminal/' + name + '.java')).read_text()
                self.assertIn('getTerminalView().pasteText(text)', code)
                self.assertNotIn('.paste(text)', code)
            controller = (tree / 'terminal-view/src/main/java/com/termux/view/textselection/TextSelectionCursorController.java').read_text()
            self.assertIn('if (!force && System.currentTimeMillis() - mShowStartTime < 300)', controller)
            touch_copy = controller.split('case ACTION_COPY:', 1)[1].split('case ACTION_MORE:', 1)[0]
            self.assertEqual(touch_copy.count('forceStopTextSelectionMode()'), 2)
            self.assertNotIn('stopTextSelectionMode()', touch_copy)
            self.assertIn('menu.add(Menu.NONE, ACTION_COPY', controller)
            self.assertIn('menu.add(Menu.NONE, ACTION_PASTE', controller)
            self.assertIn('mClient.onLongPress(event)', view)
            self.assertIn('startTextSelectionMode(event)', view)
            canceled = view.split('if (action == MotionEvent.ACTION_CANCEL) {', 1)[1].split('if (action == MotionEvent.ACTION_DOWN)', 1)[0]
            self.assertIn('sendMouseEventCode(event, TerminalEmulator.MOUSE_LEFT_BUTTON, false)', canceled)


    def execute_scroll_routes(self, tree, view):
        """Execute actual local/TUI scroll routes and count viewport work, not wall-clock speed."""
        method = view.split('    void doScroll(MotionEvent event, int rowsDown) {', 1)[1]
        method = 'void doScroll(MotionEvent event, int rowsDown) {' + method.split('    /** Overriding', 1)[0]
        source = tree / 'ScrollRouteProbe.java'
        source.write_text(r'''public class ScrollRouteProbe {
                static class MotionEvent { final int meta; MotionEvent(int value){meta=value;} int getMetaState(){return meta;} }
                static class KeyEvent { static final int META_SHIFT_ON=1,KEYCODE_DPAD_UP=19,KEYCODE_DPAD_DOWN=20; }
                static class TerminalEmulator {
                    static final int MOUSE_WHEELUP_BUTTON=64,MOUSE_WHEELDOWN_BUTTON=65;
                    boolean tracking,alternate; int history=1000;
                    boolean isMouseTrackingActive(){return tracking;}
                    boolean isAlternateBufferActive(){return alternate;}
                    TerminalEmulator getScreen(){return this;} int getActiveTranscriptRows(){return history;}
                }
                TerminalEmulator mEmulator=new TerminalEmulator();
                int mTopRow,sets,redraws,mouseReports,keyReports,lastMouse,lastKey;
                boolean selecting; boolean isSelectingText(){return selecting;}
                void setTopRow(int top){mTopRow=top;sets++;}
                boolean awakenScrollBars(){return false;} void invalidate(){redraws++;}
                void sendMouseEventCode(MotionEvent event,int button,boolean pressed){if(!pressed)throw new AssertionError();mouseReports++;lastMouse=button;}
                void handleKeyCode(int key,int modifiers){keyReports++;lastKey=key;}
                static void check(boolean value){if(!value)throw new AssertionError();}
            ''' + method + r'''
                public static void main(String[] args) {
                    ScrollRouteProbe view=new ScrollRouteProbe();
                    MotionEvent normal=new MotionEvent(0),shift=new MotionEvent(KeyEvent.META_SHIFT_ON);
                    view.doScroll(normal,-100);
                    check(view.mTopRow==-100&&view.sets==1&&view.redraws==1); // A large local movement is one viewport update.
                    view.doScroll(normal,Integer.MIN_VALUE);
                    check(view.mTopRow==-1000&&view.sets==2); // Clamp without integer overflow.
                    view.doScroll(normal,-1);check(view.sets==2); // Boundary does not request redundant redraw.
                    view.doScroll(normal,Integer.MAX_VALUE);check(view.mTopRow==0&&view.sets==3);
                    view.mEmulator.tracking=true;
                    view.doScroll(normal,-3);
                    check(view.mouseReports==3&&view.lastMouse==TerminalEmulator.MOUSE_WHEELUP_BUTTON&&view.sets==3);
                    view.doScroll(normal,2);
                    check(view.mouseReports==5&&view.lastMouse==TerminalEmulator.MOUSE_WHEELDOWN_BUTTON);
                    view.doScroll(shift,-10);
                    check(view.mouseReports==5&&view.mTopRow==-10&&view.sets==4);
                    view.mEmulator.tracking=false;view.mEmulator.alternate=true;
                    view.doScroll(normal,3);check(view.keyReports==3&&view.lastKey==KeyEvent.KEYCODE_DPAD_DOWN&&view.sets==4);
                    view.doScroll(shift,-100);check(view.keyReports==3&&view.mTopRow==-110&&view.sets==5);
                    view.selecting=true; view.mEmulator.tracking=true;
                    view.doScroll(normal,-20);
                    check(view.mouseReports==5&&view.keyReports==3&&view.mTopRow==-130&&view.sets==6);
                    view.doScroll(normal,10);
                    check(view.mouseReports==5&&view.keyReports==3&&view.mTopRow==-120&&view.sets==7);
                    view.mEmulator.tracking=false;
                    view.doScroll(normal,20);
                    check(view.mouseReports==5&&view.keyReports==3&&view.mTopRow==-100&&view.sets==8);
                    // A fullscreen TUI with no native history stays put instead of
                    // scrolling its private transcript beneath the copy handles.
                    view.mTopRow=0; view.mEmulator.history=0; view.mEmulator.tracking=true;
                    view.doScroll(normal,-20); view.doScroll(normal,20);
                    check(view.mouseReports==5&&view.keyReports==3&&view.mTopRow==0&&view.sets==8);
                    view.selecting=false; view.doScroll(normal,1);
                    check(view.mouseReports==6&&view.keyReports==3); // TUI scroll resumes after copy.
                    view.mEmulator=null;view.doScroll(normal,-10);check(view.sets==8);
                    System.out.println("PASS generated local and TUI scroll routes");
                }
            }''')
        javac = ROOT / '.local/jdk/Contents/Home/bin/javac'
        compiled = subprocess.run([str(javac), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-d', str(tree), str(source)], capture_output=True, text=True, timeout=15)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        executed = subprocess.run([self.java, '-cp', str(tree), 'ScrollRouteProbe'], capture_output=True, text=True, timeout=10)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertIn('PASS generated local and TUI scroll routes', executed.stdout)

    def execute_scroll_dispatch(self, tree, view):
        """Run the generated motion adapter with real wheel/trackpad delta policy."""
        adapter = view.split('    public boolean onGenericMotionEvent(MotionEvent event) {', 1)[1]
        adapter = 'public boolean onGenericMotionEvent(MotionEvent event) {' + adapter.split('    @Override', 1)[0]
        source = tree / 'ScrollProbe.java'
        source.write_text(r'''import com.termux.view.Z8TerminalInput;
            public class ScrollProbe {
                static class InputDevice { static final int SOURCE_MOUSE=0x2002, SOURCE_TOUCHPAD=0x100008; }
                static class KeyEvent { static final int META_SHIFT_ON=1; }
                static class MotionEvent {
                    static final int ACTION_SCROLL=8, AXIS_VSCROLL=9;
                    final float delta; final int source, device, meta;
                    MotionEvent(float delta,int source,int device,int meta){this.delta=delta;this.source=source;this.device=device;this.meta=meta;}
                    boolean isFromSource(int wanted){return (source&wanted)==wanted;}
                    int getAction(){return ACTION_SCROLL;} int getDeviceId(){return device;}
                    int getMetaState(){return meta;} float getAxisValue(int axis){return delta;}
                }
                static class Emulator {
                    boolean tracking,alternate;
                    boolean isMouseTrackingActive(){return tracking;}
                    boolean isAlternateBufferActive(){return alternate;}
                }
                Emulator mEmulator=new Emulator(); final Z8TerminalInput mZ8Input=new Z8TerminalInput();
                int rows,calls;
                boolean selecting; boolean isSelectingText(){return selecting;}
                void doScroll(MotionEvent event,int delta){rows+=delta;calls++;}
                static void check(boolean value){if(!value)throw new AssertionError();}
                MotionEvent event(float delta,int source,int meta){return new MotionEvent(delta,source,4,meta);}
            ''' + adapter + r'''
                public static void main(String[] args) {
                    ScrollProbe view=new ScrollProbe();
                    check(!view.onGenericMotionEvent(view.event(0,InputDevice.SOURCE_MOUSE,0)));
                    check(view.calls==0); // Horizontal gesture must not scroll vertically.
                    for(int i=0;i<4;i++)check(view.onGenericMotionEvent(view.event(.25f,InputDevice.SOURCE_TOUCHPAD,0)));
                    check(view.rows==-3&&view.calls==3); // Fractional trackpad movement accumulates.
                    check(view.onGenericMotionEvent(view.event(-1,InputDevice.SOURCE_MOUSE,0)));
                    check(view.rows==0&&view.calls==4); // Whole detent retains legacy speed.
                    view.mZ8Input.resetScroll(); view.mEmulator.tracking=true;
                    view.onGenericMotionEvent(view.event(.25f,InputDevice.SOURCE_MOUSE,0));
                    view.onGenericMotionEvent(view.event(.25f,InputDevice.SOURCE_MOUSE,KeyEvent.META_SHIFT_ON));
                    check(view.calls==4); // Shift switches to local scrolling without sending cached TUI motion.
                    view.onGenericMotionEvent(view.event(.25f,InputDevice.SOURCE_MOUSE,KeyEvent.META_SHIFT_ON));
                    check(view.calls==5&&view.rows==-1);
                    view.mZ8Input.resetScroll();
                    view.onGenericMotionEvent(view.event(.25f,InputDevice.SOURCE_MOUSE,0));
                    view.selecting=true;
                    view.onGenericMotionEvent(view.event(.25f,InputDevice.SOURCE_MOUSE,0));
                    check(view.calls==5); // Entering copy mode drops cached TUI wheel fractions.
                    view.onGenericMotionEvent(view.event(.25f,InputDevice.SOURCE_MOUSE,0));
                    check(view.calls==6&&view.rows==-2);
                    check(!view.onGenericMotionEvent(view.event(Float.NaN,InputDevice.SOURCE_MOUSE,0)));
                    check(!view.onGenericMotionEvent(view.event(1,0,0)));
                    view.mEmulator=null;
                    check(!view.onGenericMotionEvent(view.event(1,InputDevice.SOURCE_MOUSE,0))&&view.calls==6);
                    System.out.println("PASS generated wheel and trackpad adapter");
                }
            }''')
        actual = ROOT / 'overlay/terminal-view/src/main/java/com/termux/view/Z8TerminalInput.java'
        javac = ROOT / '.local/jdk/Contents/Home/bin/javac'
        compiled = subprocess.run([str(javac), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(tree), str(actual), str(source)], capture_output=True, text=True, timeout=15)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        executed = subprocess.run([self.java, '-cp', str(tree), 'ScrollProbe'], capture_output=True, text=True, timeout=10)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertIn('PASS generated wheel and trackpad adapter', executed.stdout)


    def execute_shortcut_dispatch(self, tree, view):
        """Run the generated Android adapter, not a separate imitation of its decision tree."""
        adapter = view.split('    @Override\n    public boolean onKeyShortcut(int keyCode, KeyEvent event) {', 1)[1]
        adapter = 'public boolean onKeyShortcut(int keyCode, KeyEvent event) {' + adapter.split('    /** Accessibility', 1)[0]
        source = tree / 'ShortcutProbe.java'
        source.write_text(r'''import com.termux.view.Z8TerminalInput;
            class ShortcutBase {
                int forwarded;
                public boolean onKeyShortcut(int key, ShortcutProbe.KeyEvent event) { forwarded++; return false; }
            }
            public class ShortcutProbe extends ShortcutBase {
                static class KeyEvent {
                    static final int KEYCODE_C = 31, KEYCODE_V = 50, KEYCODE_X = 52;
                    final boolean meta, ctrl, shift, alt; final int repeat;
                    KeyEvent(boolean m, boolean c, boolean s, boolean a, int r) { meta=m; ctrl=c; shift=s; alt=a; repeat=r; }
                    boolean isMetaPressed() { return meta; }
                    boolean isCtrlPressed() { return ctrl; }
                    boolean isShiftPressed() { return shift; }
                    boolean isAltPressed() { return alt; }
                    int getRepeatCount() { return repeat; }
                }
                static class Session {
                    int copies, pastes; String copied;
                    void onCopyTextToClipboard(String text) { copies++; copied=text; }
                    void onPasteTextFromClipboard() { pastes++; }
                }
                Session mTermSession = new Session();
                Object mEmulator = new Object();
                boolean selected; int cleared;
                boolean isSelectingText() { return selected; }
                String getSelectedText() { return "선택한 text 😀"; }
                void forceStopTextSelectionMode() { selected=false; cleared++; }
                static void check(boolean value) { if (!value) throw new AssertionError(); }
            ''' + adapter + r'''
                public static void main(String[] args) {
                    ShortcutProbe view = new ShortcutProbe();
                    KeyEvent cmd = new KeyEvent(true,false,false,false,0);
                    view.selected=true;
                    check(view.onKeyShortcut(KeyEvent.KEYCODE_C, cmd));
                    check(view.mTermSession.copies==1 && "선택한 text 😀".equals(view.mTermSession.copied));
                    check(!view.selected && view.cleared==1 && view.forwarded==0);
                    check(view.onKeyShortcut(KeyEvent.KEYCODE_C, cmd)); // No selection is a consumed no-op.
                    check(view.mTermSession.copies==1 && view.forwarded==0);
                    check(view.onKeyShortcut(KeyEvent.KEYCODE_C, new KeyEvent(true,true,false,false,0)));
                    check(view.forwarded==0); // Even Meta+Ctrl+C may not become SIGINT.
                    check(view.onKeyShortcut(KeyEvent.KEYCODE_V, cmd));
                    check(view.mTermSession.pastes==1);
                    check(view.onKeyShortcut(KeyEvent.KEYCODE_V, new KeyEvent(true,false,false,false,1)));
                    check(view.mTermSession.pastes==1); // Held Cmd+V does not paste repeatedly.
                    check(!view.onKeyShortcut(KeyEvent.KEYCODE_C, new KeyEvent(false,true,false,false,0)));
                    check(view.forwarded==1); // Plain Ctrl+C remains upstream terminal input.
                    check(!view.onKeyShortcut(KeyEvent.KEYCODE_V, new KeyEvent(false,true,false,false,0)));
                    check(view.forwarded==2); // Plain Ctrl+V retains CLI semantics.
                    KeyEvent ctrlShift = new KeyEvent(false,true,true,false,0);
                    view.selected=true;
                    check(view.onKeyShortcut(KeyEvent.KEYCODE_C, ctrlShift));
                    check(view.mTermSession.copies==2 && view.cleared==2);
                    check(view.onKeyShortcut(KeyEvent.KEYCODE_V, ctrlShift));
                    check(view.mTermSession.pastes==2);
                    check(!view.onKeyShortcut(KeyEvent.KEYCODE_C, new KeyEvent(true,false,false,true,0)));
                    check(!view.onKeyShortcut(KeyEvent.KEYCODE_X, cmd));
                    check(view.forwarded==4);
                    Session previous = view.mTermSession; view.mTermSession=null; view.mEmulator=null;
                    check(view.onKeyShortcut(KeyEvent.KEYCODE_C, cmd));
                    check(view.onKeyShortcut(KeyEvent.KEYCODE_V, cmd));
                    check(previous.pastes==2 && previous.copies==2); // Detached home cannot paste.
                    System.out.println("PASS generated clipboard shortcut adapter");
                }
            }''')
        actual = ROOT / 'overlay/terminal-view/src/main/java/com/termux/view/Z8TerminalInput.java'
        javac = ROOT / '.local/jdk/Contents/Home/bin/javac'
        compiled = subprocess.run([str(javac), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(tree), str(actual), str(source)], capture_output=True, text=True, timeout=15)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        executed = subprocess.run([self.java, '-cp', str(tree), 'ShortcutProbe'], capture_output=True, text=True, timeout=10)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertIn('PASS generated clipboard shortcut adapter', executed.stdout)
