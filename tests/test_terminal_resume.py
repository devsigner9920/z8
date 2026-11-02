"""Exercise generated TerminalView lifecycle and stale IME callbacks, not a mirror policy."""
from pathlib import Path
import importlib.util
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def method(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    index = brace + 1
    while depth:
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
        index += 1
    return source[start:index]


class TerminalResumeBehavior(unittest.TestCase):
    def test_ime_epoch_resume_preserves_history_and_rejects_stale_session_callbacks(self):
        with tempfile.TemporaryDirectory(prefix='z8-ime-resume-') as directory:
            tree = Path(directory)
            for name in ('app', 'terminal-view'):
                shutil.copytree(ROOT / 'upstream/termux-app' / name / 'src/main/java', tree / name / 'src/main/java')
            modules = []
            for name in ('prepare-app', 'patch-terminal-input'):
                spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                modules.append(module)
            modules[1].patch(tree, modules[0].replace_exact)
            view = (tree / 'terminal-view/src/main/java/com/termux/view/TerminalView.java').read_text()
            selected = [method(view, signature) for signature in (
                'public InputConnection onCreateInputConnection(EditorInfo outAttrs)',
                'public void z8SuspendInput()', 'public void z8ResumeInput()',
                'private void z8RestartInput()', 'private void z8FollowInput()',
            )]
            # This uses the real generated connection and lifecycle methods. Android
            # service/IME adapters below only supply deterministic observable effects.
            source = r'''import com.termux.view.Z8TerminalInput;
public class ResumeProbe {
    static final boolean TERMINAL_VIEW_KEY_LOGGING_ENABLED=false;
    static final String LOG_TAG="fixture";
    static final int KEY_EVENT_SOURCE_SOFT_KEYBOARD=0;
    static class InputType { static final int TYPE_TEXT_VARIATION_VISIBLE_PASSWORD=1,
        TYPE_TEXT_FLAG_NO_SUGGESTIONS=2,TYPE_NULL=0,TYPE_CLASS_TEXT=4,TYPE_TEXT_VARIATION_NORMAL=8; }
    static class EditorInfo { static final int IME_FLAG_NO_FULLSCREEN=1; int inputType,imeOptions; }
    interface InputConnection {}
    static class Editable implements CharSequence {
        String value="";
        void clear(){value="";}
        public int length(){return value.length();}
        public char charAt(int i){return value.charAt(i);}
        public CharSequence subSequence(int a,int b){return value.substring(a,b);}
        public String toString(){return value;}
    }
    static class KeyEvent { static final int ACTION_DOWN=0,KEYCODE_DEL=67; KeyEvent(int a,int b){} }
    static class BaseInputConnection implements InputConnection {
        final ResumeProbe owner; final Editable content=new Editable();
        BaseInputConnection(ResumeProbe owner,boolean full){this.owner=owner;}
        boolean setComposingText(CharSequence text,int position){content.value=text.toString();return true;}
        boolean finishComposingText(){return true;}
        boolean commitText(CharSequence text,int position){content.value=text.toString();return true;}
        boolean deleteSurroundingText(int left,int right){return true;}
        boolean sendKeyEvent(KeyEvent event){owner.keyEvents++;return true;}
        Editable getEditable(){return content;}
    }
    static class TerminalSession { boolean running=true; boolean isRunning(){return running;} }
    static class TerminalEmulator { static final int UNICODE_REPLACEMENT_CHAR=65533; }
    static class Client {
        boolean isTerminalViewSelected(){return true;} boolean shouldEnforceCharBasedInput(){return false;}
        boolean readShiftKey(){return false;} void logInfo(String tag,String message){}
    }
    static class Scroller { int aborts; void abortAnimation(){aborts++;} }
    static class Gesture { int cancels; void cancel(){cancels++;} }
    static class Context extends android.content.Context {
        final android.view.inputmethod.InputMethodManager manager=new android.view.inputmethod.InputMethodManager();
        public Object getSystemService(String name){return manager;}
    }
    TerminalSession mTermSession=new TerminalSession(); TerminalEmulator mEmulator=new TerminalEmulator();
    final Client mClient=new Client(); final Z8TerminalInput mZ8Input=new Z8TerminalInput();
    final Scroller mScroller=new Scroller(); final Gesture mGestureRecognizer=new Gesture();
    final Context context=new Context(); final StringBuilder sent=new StringBuilder();
    final Runnable mZ8ShowSoftKeyboard=()->{};
    int mZ8InputGeneration,mCombiningAccent,mZ8MouseButton,mTopRow=-20,keyEvents,updates,screens,invalidations;
    boolean mZ8InputSuspended,mZ8MouseTracking,focused=true,shown=true,preserve;
    boolean isFocused(){return focused;} boolean isShown(){return shown;} Context getContext(){return context;}
    void removeCallbacks(Runnable task){}
    void cancelRequestAutoFill(){}
    void updateSize(){updates++;} void onScreenUpdated(boolean skip){screens++;preserve=skip;}
    void stopTextSelectionMode(){} void setTopRow(int row){mTopRow=row;} void invalidate(){invalidations++;}
    void pasteText(String text){z8FollowInput();sent.append(text);}
    void inputCodePoint(int source,int point,boolean ctrl,boolean alt){z8FollowInput();sent.appendCodePoint(point);}
    static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
''' + '\n'.join(selected) + r'''
    public static void main(String[] args) {
        ResumeProbe view=new ResumeProbe(); EditorInfo info=new EditorInfo();
        BaseInputConnection first=(BaseInputConnection)view.onCreateInputConnection(info);
        first.setComposingText("한",1);
        view.mCombiningAccent=123; view.z8SuspendInput();
        first.finishComposingText(); first.commitText("stale",1);
        first.deleteSurroundingText(5,0); first.sendKeyEvent(new KeyEvent(0,0));
        check(view.sent.length()==0 && view.keyEvents==0,"Paused callbacks cannot type/delete");
        check(first.getEditable().length()==0,"Stale composition discarded");
        view.z8ResumeInput();
        check(!view.mZ8InputSuspended && view.mCombiningAccent==0,"Resume clears dead-key state");
        check(view.context.manager.restarts==1 && view.updates==1 && view.screens==1,"Resume refreshes geometry and IME");
        check(view.mTopRow==-20 && view.preserve,"Resume preserves deliberate scrollback");
        first.finishComposingText(); first.commitText("late",1);
        check(view.sent.length()==0,"Old connection still stale after resume");
        BaseInputConnection current=(BaseInputConnection)view.onCreateInputConnection(info);
        current.setComposingText("한",1); current.finishComposingText();
        current.commitText("글😀",1);
        check(view.sent.toString().equals("한글😀"),"Current Korean and surrogate input exactly once");
        check(view.mTopRow==0,"Actual input follows live viewport");
        view.sent.setLength(0);
        TerminalSession previous=view.mTermSession;
        view.mTermSession=new TerminalSession();
        current.commitText("wrong PTY",1);current.deleteSurroundingText(2,0);
        check(view.sent.length()==0 && view.keyEvents==0,"Session mismatch rejects writes/deletes");
        view.mTermSession=previous; ++view.mZ8InputGeneration;
        current.commitText("returned old PTY",1);
        check(view.sent.length()==0,"Back-and-forth switch keeps epoch stale");
        BaseInputConnection older=(BaseInputConnection)view.onCreateInputConnection(info);
        BaseInputConnection newest=(BaseInputConnection)view.onCreateInputConnection(info);
        older.commitText("superseded",1);newest.commitText("current",1);
        check(view.sent.toString().equals("current"),"Only latest IME connection writes");
        view.sent.setLength(0);view.mTermSession.running=false;newest.commitText("dead",1);
        check(view.sent.length()==0,"Exited PTY ignores IME text");
        view.focused=false;view.mTopRow=-5;view.z8ResumeInput();
        check(view.context.manager.restarts==1 && view.mTopRow==-5,"Unfocused pane does not steal IME");
        view.focused=true;view.shown=false;view.z8ResumeInput();
        check(view.context.manager.restarts==1,"Hidden pane does not steal IME");
        System.out.println("PASS generated lifecycle and stale IME callbacks");
    }
}'''
            (tree / 'ResumeProbe.java').write_text(source)
            context = tree / 'android/content/Context.java'
            context.parent.mkdir(parents=True)
            context.write_text('package android.content; public class Context { public static final String INPUT_METHOD_SERVICE="input"; public Object getSystemService(String name){return null;} }')
            manager = tree / 'android/view/inputmethod/InputMethodManager.java'
            manager.parent.mkdir(parents=True)
            manager.write_text('package android.view.inputmethod; public class InputMethodManager { public int restarts; public void restartInput(Object view){restarts++;} }')
            jdk = ROOT / '.local/jdk/Contents/Home/bin'
            compiled = subprocess.run([str(jdk / 'javac'), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(tree), str(context), str(manager),
                str(ROOT / 'overlay/terminal-view/src/main/java/com/termux/view/Z8TerminalInput.java'), str(tree / 'ResumeProbe.java')], capture_output=True, text=True, timeout=20)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(jdk / 'java'), '-cp', str(tree), 'ResumeProbe'], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS generated lifecycle', result.stdout)
            resize = method(view, 'public void updateSize()')
            self.assertLess(resize.index('forceStopTextSelectionMode();'), resize.index('mTermSession.updateSize('))
            key_down = method(view, 'public boolean onKeyDown(int keyCode, KeyEvent event)')
            self.assertIn('if (mZ8InputSuspended) return true;', key_down)
            self.assertIn('z8FollowInput();\n            mTermSession.write(event.getCharacters());', key_down)
            physical = method(view, 'public void inputCodePoint(')
            self.assertIn('if (mTermSession == null || mZ8InputSuspended) return;', physical)
            self.assertIn('z8FollowInput();', physical)
            self.assertIn('z8FollowInput();\n        mTermSession.write(code);', method(view, 'public boolean handleKeyCode('))


    def test_touch_tui_tap_reopens_ime_after_fold_without_affecting_mouse_or_selection(self):
        with tempfile.TemporaryDirectory(prefix='z8-touch-ime-') as directory:
            tree = Path(directory)
            for name in ('app', 'terminal-view'):
                shutil.copytree(ROOT / 'upstream/termux-app' / name / 'src/main/java', tree / name / 'src/main/java')
            modules = []
            for name in ('prepare-app', 'patch-terminal-input'):
                spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); modules.append(module)
            modules[1].patch(tree, modules[0].replace_exact)
            view = (tree / 'terminal-view/src/main/java/com/termux/view/TerminalView.java').read_text()
            client = (tree / 'app/src/main/java/com/termux/app/terminal/TermuxTerminalViewClient.java').read_text()
            source = TOUCH_IME_PROBE.replace('/* VIEW_METHODS */', '\n'.join(method(view, signature) for signature in (
                'public boolean onUp(MotionEvent event)', 'public boolean onSingleTapUp(MotionEvent event)',
                'public void z8ShowSoftKeyboard()', 'private void z8ShowSoftKeyboardAfterFocus()',
                'private void z8RestartInput()',
            ))).replace('/* CLIENT_METHOD */', method(client, 'public void onSingleTapUp(MotionEvent e)'))
            source_path = tree / 'TouchImeProbe.java';source_path.write_text(source)
            context = tree / 'android/content/Context.java';context.parent.mkdir(parents=True)
            context.write_text('package android.content;public class Context {public static final String INPUT_METHOD_SERVICE="input";public Object getSystemService(String name){return null;}}')
            manager = tree / 'android/view/inputmethod/InputMethodManager.java';manager.parent.mkdir(parents=True)
            manager.write_text('package android.view.inputmethod;public class InputMethodManager {'
                'public int restarts,shows;public boolean visible,active;public boolean isActive(Object view){return active;}'
                'public void restartInput(Object view){restarts++;active=true;}'
                'public boolean showSoftInput(Object view,int flags){shows++;visible=true;return true;}}')
            jdk = ROOT / '.local/jdk/Contents/Home/bin'
            compiled = subprocess.run([str(jdk / 'javac'), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(tree), str(context),
                str(manager), str(source_path)], capture_output=True, text=True, timeout=20)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(jdk / 'java'), '-cp', str(tree), 'TouchImeProbe'], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS touch IME after fold', result.stdout)
            # All pending touch requests must be revoked before pause, detach or
            # a different session. Otherwise a tap could open IME over a browser.
            for signature in ('public void z8SuspendInput()', 'protected void onDetachedFromWindow()',
                              'public boolean attachSession(TerminalSession session)'):
                self.assertIn('removeCallbacks(mZ8ShowSoftKeyboard);', method(view, signature))

    def test_generated_selection_coordinates_edge_drag_and_keyboard_resize(self):
        with tempfile.TemporaryDirectory(prefix='z8-selection-') as directory:
            tree = Path(directory)
            for name in ('app', 'terminal-view'):
                shutil.copytree(ROOT / 'upstream/termux-app' / name / 'src/main/java', tree / name / 'src/main/java')
            modules = []
            for name in ('prepare-app', 'patch-terminal-input'):
                spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); modules.append(module)
            modules[1].patch(tree, modules[0].replace_exact)
            view = (tree / 'terminal-view/src/main/java/com/termux/view/TerminalView.java').read_text()
            controller = (tree / 'terminal-view/src/main/java/com/termux/view/textselection/TextSelectionCursorController.java').read_text()
            handle = (tree / 'terminal-view/src/main/java/com/termux/view/textselection/TextSelectionHandleView.java').read_text()
            source = r'''public class SelectionProbe {
    static class TextUtils { static boolean isEmpty(String value){return value==null||value.isEmpty();} }
    static class Rect { int top,bottom; }
    static class WcWidth { static int width(char c){return c>127?2:1;} static int width(int c){return c>127?2:1;} }
    static class TextSelectionHandleView {}
    static class TerminalBuffer {
        int history=100; int rows=10;String text="ascii";
        int getActiveRows(){return history+rows;} int getActiveTranscriptRows(){return history;}
        String getSelectedText(int a,int b,int c,int d){return text;}
    }
    static class Emulator {
        int mRows=10,mColumns=20;boolean alternate;
        TerminalBuffer screen=new TerminalBuffer();TerminalBuffer getScreen(){return screen;}
        boolean isAlternateBufferActive(){return alternate;}
    }
    static class Renderer { int mFontLineSpacing=24;float mFontWidth=12;
        int getFontLineSpacing(){return mFontLineSpacing;}float getFontWidth(){return mFontWidth;} }
    static class TerminalView {
        final Emulator mEmulator=new Emulator();final Renderer mRenderer=new Renderer();int mTopRow=-20;
        int getTopRow(){return mTopRow;}void setTopRow(int row){mTopRow=row;}
        int getHeight(){return mRenderer.mFontLineSpacing*mEmulator.mRows;}
        static class Resources { float density=1;Resources getDisplayMetrics(){return this;} }
        final Resources resources=new Resources();Resources getResources(){return resources;}
        int clipTop=0,clipBottom=-1;boolean visible=true;
        boolean getLocalVisibleRect(Rect rect){rect.top=clipTop;rect.bottom=clipBottom<0?getHeight():clipBottom;return visible;}
        void invalidate(){}
''' + method(view, 'public int getCursorY(float y)') + '\n' + method(view, 'public int getCursorX(float x)') + '\n' + method(view, 'public int z8SelectionEdgeSize()') + '\n' + method(view, 'public int z8SelectionScrollDirection(int y)') + r'''
    }
    final TerminalView terminalView=new TerminalView();
    final TextSelectionHandleView mStartHandle=new TextSelectionHandleView(),mEndHandle=new TextSelectionHandleView();
    int mSelX1=2,mSelX2=7,mSelY1=-19,mSelY2=-16;boolean active=true;
    boolean isActive(){return active;}
''' + '\n'.join(method(controller, signature) for signature in (
                'public void updatePosition(TextSelectionHandleView handle, int x, int y)',
                'private int getValidCurX(TerminalBuffer screen, int cy, int cx)',
                'public void onTerminalRowsResized(int rowShift)',
            )) + r'''
    static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
    public static void main(String[] args) {
        SelectionProbe probe=new SelectionProbe();TerminalView view=probe.terminalView;
        for(int spacing:new int[]{12,24,40,64}) {
            view.mRenderer.mFontLineSpacing=spacing;
            for(int top:new int[]{0,-1,-20}) {
                view.mTopRow=top;
                for(int row=top;row<top+10;row++)
                    check(view.getCursorY((row-top+1)*spacing)==row,"Handle/cell inverse across fonts and scrollback");
            }
        }
        view.mRenderer.mFontLineSpacing=24;view.mTopRow=-20;
        for(float width:new float[]{7.2f,11.31f,12f,24f}) {
            view.mRenderer.mFontWidth=width;
            for(int column=0;column<20;column++) {
                probe.mSelX1=0;probe.mSelX2=19;probe.mSelY1=-18;probe.mSelY2=-16;
                probe.updatePosition(probe.mEndHandle,Math.round((column+1)*width),5*24);
                check(probe.mSelX2==column,"Stationary end boundary retains exact character across fractional fonts");
                probe.mSelX1=0;probe.mSelX2=19;probe.mSelY1=-18;probe.mSelY2=-16;
                probe.updatePosition(probe.mStartHandle,Math.round(column*width),3*24);
                check(probe.mSelX1==column,"Stationary start boundary retains exact character across fractional fonts");
            }
        }
        view.mRenderer.mFontWidth=12;probe.mSelX1=2;probe.mSelX2=7;probe.mSelY1=-19;probe.mSelY2=-16;
        view.mRenderer.mFontLineSpacing=24;view.mTopRow=-20;
        for(int i=0;i<5;i++)probe.updatePosition(probe.mEndHandle,10000,view.getHeight());
        check(view.mTopRow==-15 && probe.mSelY1==-19,"Stationary bottom-edge ticks extend without losing start");
        check(probe.mSelX2==19 && probe.active,"Right edge clamps to last column and keeps selection");
        for(int i=0;i<100;i++)probe.updatePosition(probe.mEndHandle,10000,view.getHeight()+1000);
        check(view.mTopRow==0&&probe.mSelY2==9,"End remains in bounds at final screen");
        probe.updatePosition(probe.mStartHandle,-1000,-1000);
        check(view.mTopRow==-1&&probe.mSelX1==0&&probe.mSelY1==-1,"Top edge expands backwards safely");
        view.mRenderer.mFontLineSpacing=38;view.resources.density=2.625f;
        view.mEmulator.mRows=37;view.mEmulator.screen.rows=37;view.mTopRow=-20;
        probe.mSelY1=-19;probe.mSelY2=-16;
        for(int i=0;i<5;i++)probe.updatePosition(probe.mEndHandle,120,view.getHeight()-80);
        check(view.mTopRow==-15&&probe.mSelY1==-19,"Samsung grip offset can scroll 80px before navigation edge");
        view.clipBottom=700;view.mTopRow=-20;
        for(int i=0;i<5;i++)probe.updatePosition(probe.mEndHandle,120,620);
        check(view.mTopRow==-15&&probe.mSelY1==-19,"Visible bottom scrolls even when full view continues below the IME");
        view.clipTop=240;probe.updatePosition(probe.mStartHandle,120,300);
        check(view.mTopRow==-16,"Visible top also scrolls before the clipped edge");
        int clippedTop=view.mTopRow;probe.updatePosition(probe.mEndHandle,120,470);
        check(view.mTopRow==clippedTop,"Visible midpoint does not scroll");
        view.visible=false;probe.updatePosition(probe.mEndHandle,120,690);
        check(view.mTopRow==clippedTop,"Invisible controller update cannot advance scrollback");
        view.visible=true;view.clipTop=0;view.clipBottom=-1;
        view.mRenderer.mFontLineSpacing=24;view.resources.density=1;
        view.mEmulator.mRows=10;view.mEmulator.screen.rows=10;
        view.mEmulator.alternate=true;int before=view.mTopRow;
        probe.updatePosition(probe.mStartHandle,0,0);
        check(view.mTopRow==before,"No transcript scroll on alternate screen");
        probe.mSelY1=-8;probe.mSelY2=4;view.mEmulator.mRows=6;
        probe.onTerminalRowsResized(4);
        check(probe.mSelY1==-12&&probe.mSelY2==0&&probe.active,"IME shrink translates intact selection");
        view.mEmulator.mRows=10;probe.onTerminalRowsResized(-4);
        check(probe.mSelY1==-8&&probe.mSelY2==4,"IME expand reverses row shift");
        view.mEmulator.screen.text="aaaaaaaaaaaaaaaaaa한";view.mTopRow=0;
        probe.mSelY1=1;probe.mSelY2=5;probe.mSelX1=0;probe.mSelX2=19;
        probe.updatePosition(probe.mEndHandle,20*12,6*24);
        check(probe.mSelX2==19,"Right-edge Korean glyph cannot advance beyond last cell");
        probe.updatePosition(probe.mStartHandle,19*12,2*24);
        check(probe.mSelX1==19,"Start wide-glyph alignment also stays in bounds");
        System.out.println("PASS generated selection coordinates and bounds");
    }
}'''
            (tree / 'SelectionProbe.java').write_text(source)
            jdk = ROOT / '.local/jdk/Contents/Home/bin'
            compiled = subprocess.run([str(jdk / 'javac'), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(tree), str(tree / 'SelectionProbe.java')], capture_output=True, text=True, timeout=20)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(jdk / 'java'), '-cp', str(tree), 'SelectionProbe'], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS generated selection', result.stdout)
            self.assertIn('getLocalVisibleRect(clip)', method(handle, 'private boolean isPositionVisible()'))
            self.assertNotIn('getLocationInWindow', method(handle, 'private boolean isPositionVisible()'))
            self.assertIn('getLocalVisibleRect(clip)', method(handle, 'private void checkChangedOrientation('))
            self.assertNotIn('terminalView.getBottom()', controller)
            self.assertIn('if (!mIsDragging || !mCursorController.isActive()) return;', handle)
            self.assertIn('removeCallbacks(mZ8EdgeScroll);', method(handle, 'public void hide()'))
            touch = method(handle, 'public boolean onTouchEvent(MotionEvent event)')
            self.assertIn('mTouchToWindowOffsetY = rawY - mPointY + mHotspotY + mTouchOffsetY;', touch)
            self.assertIn('case MotionEvent.ACTION_CANCEL:', touch)
            self.assertIn('removeCallbacks(mZ8EdgeScroll);', touch.split('case MotionEvent.ACTION_UP:')[1])


TOUCH_IME_PROBE = r'''import java.util.*;
public class TouchImeProbe {
    static class InputDevice {static final int SOURCE_MOUSE=2,SOURCE_TOUCHPAD=4,SOURCE_TOUCHSCREEN=8;}
    static class MotionEvent {final int source;MotionEvent(int source){this.source=source;}boolean isFromSource(int value){return source==value;}}
    static class Screen {String getWordAtLocation(int x,int y){return "https://example.test/";}}
    static class TerminalEmulator {
        static final int MOUSE_LEFT_BUTTON=0;boolean tracking=true;
        boolean isMouseTrackingActive(){return tracking;}Screen getScreen(){return new Screen();}
    }
    static class Session {boolean running=true;final TerminalEmulator emulator=new TerminalEmulator();
        boolean isRunning(){return running;}TerminalEmulator getEmulator(){return emulator;}}
    static class Props {boolean shouldOpenTerminalTranscriptURLOnClick(){return true;}}
    static class Preferences {boolean enabled=true;boolean isSoftKeyboardEnabled(){return enabled;}}
    static class Context extends android.content.Context {
        final android.view.inputmethod.InputMethodManager manager=new android.view.inputmethod.InputMethodManager();
        public Object getSystemService(String name){return manager;}
    }
    static class Activity {
        final Context context=new Context();final Session session=new Session();final Preferences prefs=new Preferences();
        final View view=new View(this);boolean disableImeFlag=true;int resizes;
        Session getCurrentSession(){return session;}View getTerminalView(){return view;}
        Props getProperties(){return new Props();}Preferences getPreferences(){return prefs;}
    }
    static class KeyboardUtils {
        static void clearDisableSoftKeyboardFlags(Activity activity){activity.disableImeFlag=false;}
        static void setSoftInputModeAdjustResize(Activity activity){activity.resizes++;}
    }
    static class TermuxUrlUtils {static LinkedHashSet<CharSequence> extractUrls(String text){return new LinkedHashSet<>();}}
    static class ShareUtils {static void openUrl(Activity activity,String url){throw new AssertionError("TUI tap must not open a transcript URL");}}
    static class Client {
        final Activity mActivity;Client(Activity activity){mActivity=activity;}
        /* CLIENT_METHOD */
    }
    static class View {
        final Activity activity;final Client mClient;Session mTermSession;TerminalEmulator mEmulator;
        boolean scrolledWithFinger,selecting,focused,shown=true,windowFocus=true,mZ8InputSuspended;
        float mScrollRemainder;int mousePresses,mouseReleases;
        final ArrayDeque<Runnable> queue=new ArrayDeque<>();
        final Runnable mZ8ShowSoftKeyboard=this::z8ShowSoftKeyboardAfterFocus;
        View(Activity activity){this.activity=activity;mClient=new Client(activity);mTermSession=activity.session;mEmulator=mTermSession.emulator;}
        boolean isSelectingText(){return selecting;}void stopTextSelectionMode(){selecting=false;}
        void requestFocus(){focused=true;}boolean isFocused(){return focused;}boolean isShown(){return shown;}
        boolean hasWindowFocus(){return windowFocus;}Context getContext(){return activity.context;}
        int[] getColumnAndRow(MotionEvent event,boolean relative){return new int[]{0,0};}
        void sendMouseEventCode(MotionEvent event,int code,boolean press){if(press)mousePresses++;else mouseReleases++;}
        void removeCallbacks(Runnable task){queue.removeIf(value->value==task);}void post(Runnable task){queue.add(task);}
        void drain(){while(!queue.isEmpty())queue.remove().run();}
        void tap(MotionEvent event){if(!onUp(event))onSingleTapUp(event);}
        /* VIEW_METHODS */
    }
    static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    public static void main(String[] args){
        MotionEvent finger=new MotionEvent(InputDevice.SOURCE_TOUCHSCREEN);
        Activity app=new Activity();View view=app.view;
        // A fold has hidden the keyboard while Codex remains in mouse mode.
        check(!app.context.manager.visible&&view.mEmulator.tracking,"Fold fixture starts without visible IME");
        view.tap(finger);
        check(view.focused&&view.queue.size()==1&&!app.context.manager.visible,"Touch requests focus before deferred keyboard display");
        view.drain();
        check(app.context.manager.visible&&app.context.manager.shows==1&&app.context.manager.restarts==1,"Finger tap must reopen IME inside mouse-reporting Codex");
        check(view.mousePresses==1&&view.mouseReleases==1,"TUI still receives exactly one click");
        check(!app.disableImeFlag&&app.resizes==1,"Explicit touch clears stale hardware/fold flag and keeps resize mode");
        app.context.manager.visible=false;view.tap(finger);view.tap(finger);
        check(view.queue.size()==1,"Repeated taps coalesce");view.drain();
        check(app.context.manager.shows==2,"One deferred show per tap burst");
        check(app.context.manager.restarts==1,"Already active IME is not restarted while Korean composition may be pending");
        for(int source:new int[]{InputDevice.SOURCE_MOUSE,InputDevice.SOURCE_TOUCHPAD}){
            Activity pointer=new Activity();pointer.view.tap(new MotionEvent(source));pointer.view.drain();
            check(pointer.context.manager.shows==0,"Mouse and trackpad must not open touch keyboard");
        }
        Activity selected=new Activity();selected.view.selecting=true;selected.view.tap(finger);selected.view.drain();
        check(selected.context.manager.shows==0&&selected.view.mousePresses==0,"Dismissing selection must not also type/click/show IME");
        Activity scroll=new Activity();scroll.view.scrolledWithFinger=true;scroll.view.onUp(finger);scroll.view.drain();
        check(scroll.context.manager.shows==0&&scroll.view.mousePresses==0,"Finishing a scroll is not a keyboard request");
        Activity disabled=new Activity();disabled.prefs.enabled=false;disabled.view.tap(finger);disabled.view.drain();
        check(disabled.context.manager.shows==0&&disabled.disableImeFlag,"Explicit disabled preference remains respected");
        for(int transition=0;transition<4;transition++){
            Activity interrupted=new Activity();interrupted.view.tap(finger);
            if(transition==0)interrupted.view.mZ8InputSuspended=true;
            if(transition==1)interrupted.view.shown=false;
            if(transition==2)interrupted.view.windowFocus=false;
            if(transition==3)interrupted.session.running=false;
            interrupted.view.drain();
            check(interrupted.context.manager.shows==0,"Late callback must not show IME after pane/lifecycle/session change");
        }
        System.out.println("PASS touch IME after fold");
    }
}
'''


if __name__ == '__main__':
    unittest.main()
