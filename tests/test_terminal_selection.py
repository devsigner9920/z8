"""Execute patched selection lifecycle methods with observable Android adapter stubs."""
from pathlib import Path
import importlib.util
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def method(source, signature):
    start = source.index(signature)
    index = source.index('{', start) + 1
    depth = 1
    while depth:
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
        index += 1
    return source[start:index]


class TerminalSelectionBehavior(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='z8-selection-')
        self.addCleanup(self.temporary.cleanup)
        self.tree = Path(self.temporary.name)
        for name in ('app', 'terminal-view'):
            shutil.copytree(ROOT / 'upstream/termux-app' / name / 'src/main/java',
                            self.tree / name / 'src/main/java')
        modules = []
        for name in ('prepare-app', 'patch-terminal-input'):
            spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules.append(module)
        modules[1].patch(self.tree, modules[0].replace_exact)
        self.view = (self.tree / 'terminal-view/src/main/java/com/termux/view/TerminalView.java').read_text()
        self.controller = (self.tree / 'terminal-view/src/main/java/com/termux/view/textselection/TextSelectionCursorController.java').read_text()
        self.handle = (self.tree / 'terminal-view/src/main/java/com/termux/view/textselection/TextSelectionHandleView.java').read_text()

    def run_java(self, name, source, extra_sources=()):
        path = self.tree / (name + '.java')
        path.write_text(source)
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        result = subprocess.run([str(jdk / 'javac'), '-encoding', 'UTF-8', '-d', str(self.tree), str(path), *map(str, extra_sources)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(jdk / 'java'), '-cp', str(self.tree), name],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mouse_selection_anchor_tracks_streaming_output_before_and_during_drag(self):
        selected = [method(self.view, signature) for signature in (
            'public void onScreenUpdated(boolean skipScrolling)',
            'private void decrementYTextSelectionCursors(int decrement)',
        )]
        self.run_java('SelectionOutputProbe', r'''import com.termux.view.Z8TerminalInput;
import java.util.Arrays;
public class SelectionOutputProbe {
    static class Emulator {
        int scroll;int getScrollCounter(){return scroll;}void clearScrollCounter(){scroll=0;}
        Emulator getScreen(){return this;}int getActiveTranscriptRows(){return 100;}
        boolean isAutoScrollDisabled(){return false;}
    }
    static class Controller {
        boolean active;int[] range;
        void decrementYTextSelectionCursors(int shift){if(range!=null){range[1]-=shift;range[3]-=shift;}}
    }
    final Emulator mEmulator=new Emulator();
    final Z8TerminalInput mZ8Input=new Z8TerminalInput();
    final Controller mTextSelectionCursorController=new Controller();
    int mTopRow;
    boolean isSelectingText(){return mTextSelectionCursorController.active;}
    void stopTextSelectionMode(){mTextSelectionCursorController.active=false;mZ8Input.finish();}
    void setTopRow(int row){mTopRow=row;}void awakenScrollBars(){}void invalidate(){}
    void z8RefreshAccessibilityText(){}
    void range(int column,int row,int... expected){
        int[] actual=mZ8Input.range(column,row);
        if(!Arrays.equals(actual,expected))throw new AssertionError("Wrong anchored rows: "+Arrays.toString(actual));
        mTextSelectionCursorController.range=actual;mTextSelectionCursorController.active=true;
    }
''' + '\n'.join(selected) + r'''
    public static void main(String[] args){
        SelectionOutputProbe view=new SelectionOutputProbe();
        view.mZ8Input.begin(4,3);view.range(5,5,4,3,5,5);
        view.mEmulator.scroll=2;view.onScreenUpdated(false);
        view.range(5,3,4,1,5,3); // Same pointer/cells after two new output rows.
        view.mEmulator.scroll=3;view.onScreenUpdated(false);
        view.range(5,0,4,-2,5,0); // A second batch must not reset the original anchor.
        view.range(1,-4,1,-4,4,-2); // Reverse drag still anchors the original content.
        view.mZ8Input.finish();view.mTextSelectionCursorController.active=false;
        view.mZ8Input.begin(2,1); // Output can arrive between DOWN and the first MOVE.
        view.mEmulator.scroll=2;view.onScreenUpdated(false);
        view.range(5,2,2,-1,5,2);
        view.mZ8Input.finish();view.mTextSelectionCursorController.active=false;
        view.mEmulator.scroll=3;view.onScreenUpdated(false);
        view.mZ8Input.begin(1,4);view.range(2,5,1,4,2,5); // New press has a fresh anchor.
    }
}''', [ROOT / 'overlay/terminal-view/src/main/java/com/termux/view/Z8TerminalInput.java'])

    def test_floating_copy_toolbar_recovers_and_hardware_modifier_preserves_selection(self):
        selected = [method(self.controller, signature) for signature in (
            'public void render()', 'public void setMouseSelection(int[] range, boolean finished)',
            'public void finishMouseSelection()', 'public void onDestroyActionMode(ActionMode mode)',
            'public void onTouchModeChanged(boolean isInTouchMode)', 'public boolean hide(boolean force)',
            'public boolean isActive()',
        )]
        self.assertIn('callback.onDestroyActionMode(mode);', self.controller)
        self.run_java('SelectionLifecycleProbe', r'''public class SelectionLifecycleProbe {
    static class Handle {
        boolean dragging; int hides;
        boolean isDragging(){return dragging;}
        void positionAtCursor(int x,int y,boolean visible){}
        void hide(){hides++;}
    }
    static class TerminalView {
        boolean shown=true,focused=true; int redraws;
        boolean isShown(){return shown;} boolean hasWindowFocus(){return focused;}
        void invalidate(){redraws++;}
    }
    static class ActionMode {
        final SelectionLifecycleProbe owner; int invalidations;
        ActionMode(SelectionLifecycleProbe owner){this.owner=owner;}
        void invalidate(){invalidations++;}
        void finish(){owner.onDestroyActionMode(this);}
    }
    final Handle mStartHandle=new Handle(),mEndHandle=new Handle();
    final TerminalView terminalView=new TerminalView();
    ActionMode mActionMode;
    boolean mZ8MouseSelectionDragging,mIsSelectingText;
    int mSelX1,mSelY1,mSelX2,mSelY2,creates;
    long mShowStartTime;
    void setActionModeCallBacks(){mActionMode=new ActionMode(this);creates++;}
    static void check(boolean value){if(!value)throw new AssertionError();}
''' + '\n'.join(selected) + r'''
    public static void main(String[] args) {
        SelectionLifecycleProbe view=new SelectionLifecycleProbe();
        view.setMouseSelection(new int[]{2,-40,8,-20},false);
        check(view.isActive()&&view.creates==0); // Never interrupt a live mouse drag.
        view.finishMouseSelection();
        check(view.creates==1&&view.mActionMode!=null);
        ActionMode old=view.mActionMode;
        view.onTouchModeChanged(false);
        check(view.isActive()&&view.mSelY1==-40&&view.mSelY2==-20); // Cmd key retains the range.
        view.terminalView.focused=false;
        view.onDestroyActionMode(old);
        check(view.mActionMode==null&&view.terminalView.redraws==1&&view.isActive());
        view.render();check(view.creates==1); // No toolbar while another app owns focus.
        view.terminalView.focused=true;view.terminalView.shown=false;
        view.render();check(view.creates==1);
        view.terminalView.shown=true;view.mEndHandle.dragging=true;
        view.render();check(view.creates==1); // Wait for the native handle release.
        view.mEndHandle.dragging=false;view.render();
        check(view.creates==2&&view.mActionMode!=null&&view.mActionMode!=old);
        ActionMode recovered=view.mActionMode;
        view.onDestroyActionMode(old);
        check(view.mActionMode==recovered); // Delayed destruction cannot clear its replacement.
        view.render();check(view.creates==2&&recovered.invalidations==2);
        check(view.hide(true));
        view.render();
        check(!view.isActive()&&view.mActionMode==null&&view.creates==2);
        check(view.mStartHandle.hides==1&&view.mEndHandle.hides==1);
        view.setMouseSelection(new int[]{1,0,3,0},false);
        view.render();check(view.creates==2);
        view.finishMouseSelection();check(view.creates==3); // A fresh gesture remains usable.
    }
}''')

    def test_selection_entry_cancels_inertial_tui_scroll_and_queued_fling(self):
        selected = [method(self.view, signature) for signature in (
            'public boolean onFling(final MotionEvent e2, float velocityX, float velocityY)',
            'public void startTextSelectionMode(MotionEvent event)',
        )]
        self.run_java('SelectionFlingProbe', r'''import java.util.ArrayList;
public class SelectionFlingProbe {
    static class MotionEvent {}
    static class TerminalSession {}
    static class Emulator {
        int mRows=20; boolean tracking=true;
        boolean isMouseTrackingActive(){return tracking;}
        Emulator getScreen(){return this;} int getActiveTranscriptRows(){return 100;}
    }
    static class Scroller {
        boolean finished=true; int flings,aborts;
        boolean isFinished(){return finished;}
        void fling(int a,int b,int c,int d,int e,int f,int g,int h){flings++;finished=false;}
        void abortAnimation(){aborts++;finished=true;}
        boolean computeScrollOffset(){return false;} int getCurrY(){return 2;}
    }
    static class Input {int resets;void resetScroll(){resets++;}}
    static class Client {void copyModeChanged(boolean value){}}
    Emulator mEmulator=new Emulator(); TerminalSession mTermSession=new TerminalSession();
    final Scroller mScroller=new Scroller(); final Input mZ8Input=new Input(); final Client mClient=new Client();
    final ArrayList<Runnable> queued=new ArrayList<>();
    boolean selecting,focus=true; int mTopRow,scrolls; float mScrollRemainder=9;
    boolean isSelectingText(){return selecting;}
    boolean requestFocus(){return focus;}
    void showTextSelectionCursors(MotionEvent event){selecting=true;}
    void invalidate(){}
    void post(Runnable runnable){queued.add(runnable);}
    void doScroll(MotionEvent event,int rows){scrolls++;}
    static void check(boolean value){if(!value)throw new AssertionError();}
''' + '\n'.join(selected) + r'''
    public static void main(String[] args) {
        SelectionFlingProbe view=new SelectionFlingProbe();
        MotionEvent touch=new MotionEvent();
        view.onFling(touch,0,100);
        check(view.mScroller.flings==1&&view.queued.size()==1);
        view.startTextSelectionMode(touch);
        check(view.selecting&&view.mScroller.finished&&view.mScrollRemainder==0&&view.mZ8Input.resets==1);
        view.queued.get(0).run();check(view.scrolls==0);
        view.onFling(touch,0,100);check(view.mScroller.flings==1); // A late ACTION_UP cannot start another.
        view.selecting=false;view.onFling(touch,0,100);
        check(view.mScroller.flings==2&&view.queued.size()==2);
        view.selecting=true;view.queued.get(1).run();
        check(view.scrolls==0&&view.mScroller.finished); // Selection can also start before a queued callback.
        view.selecting=false;view.onFling(touch,0,100);view.queued.get(2).run();
        check(view.scrolls==1); // Ordinary TUI inertia still works outside copy mode.
    }
}''')

    def test_samsung_grip_stays_above_gestures_and_scrolls_without_further_moves(self):
        # Run the generated geometry, real touch adapter, and scheduled callback.
        # These dimensions reproduce the unfolded Samsung viewport and its grip
        # displacement; the old one-line edge failed before the finger hit Home.
        edge_scroll = method(self.handle, 'private final Runnable mZ8EdgeScroll = new Runnable()') + ';'
        self.assertIn('coords[1] += z8HandleTop();', method(self.handle, 'public void show()'))
        self.assertIn('coords[1] + z8HandleTop()', method(self.handle, 'private void moveTo('))
        self.run_java('TextSelectionHandleView', r'''public class TextSelectionHandleView {
    static class Rect { int left,top,right,bottom; }
    static class Resources {
        float density=2.625f;
        Resources getDisplayMetrics(){return this;}
    }
    static class Renderer { int spacing=38; int getFontLineSpacing(){return spacing;} }
    static class Emulator {
        boolean alternate;
        boolean isAlternateBufferActive(){return alternate;}
        Emulator getScreen(){return this;}
        int getActiveTranscriptRows(){return 100;}
    }
    static class MotionEvent {
        static final int ACTION_DOWN=0,ACTION_UP=1,ACTION_MOVE=2,ACTION_CANCEL=3;
        final int action;final float x,y;
        MotionEvent(int action,float x,float y){this.action=action;this.x=x;this.y=y;}
        int getActionMasked(){return action;}float getRawX(){return x;}float getRawY(){return y;}
    }
    static class TerminalView {
        final Renderer mRenderer=new Renderer();final Resources resources=new Resources();
        final Emulator mEmulator=new Emulator();
        int height=1411,top=-20,parentX=693,parentY=413,clipTop=0,clipBottom=1411;
        boolean shown=true,focused=true,visible=true;
        int getHeight(){return height;} int getTopRow(){return top;}
        Resources getResources(){return resources;}
        boolean isShown(){return shown;}boolean hasWindowFocus(){return focused;}
        void updateFloatingToolbarVisibility(MotionEvent event){}
        void getLocationInWindow(int[] coords){coords[0]=parentX;coords[1]=parentY;}
        boolean getLocalVisibleRect(Rect rect){rect.top=clipTop;rect.bottom=clipBottom;return visible;}
''' + method(self.view, 'public int z8SelectionEdgeSize()') + '\n' + method(self.view, 'public int z8SelectionScrollDirection(int y)') + r'''
    }
    final TerminalView terminalView=new TerminalView();
    class CursorController {
        boolean active=true;int calls,lastX,lastY;
        boolean isActive(){return active;}
        void updatePosition(TextSelectionHandleView handle,int x,int y){
            calls++;lastX=x;lastY=y;
            int direction=terminalView.z8SelectionScrollDirection(y);
            if(!terminalView.mEmulator.alternate){
                if(direction>0 && terminalView.top<0)terminalView.top++;
                else if(direction<0 && terminalView.top>-100)terminalView.top--;
            }
        }
    }
    final CursorController mCursorController=new CursorController();
    final int[] mTempCoords=new int[2];
    int mPointX=200,mPointY=1380,mHandleHeight=80,mLastParentX,mLastParentY;
    int mZ8DragX,mZ8DragY,queued,removed;
    float mTouchToWindowOffsetX,mTouchToWindowOffsetY,mHotspotX=10,mHotspotY=0,mTouchOffsetY=-24;
    boolean mIsDragging;
    Resources getResources(){return terminalView.getResources();}
    void postDelayed(Runnable runnable,int delay){queued++;}
    void removeCallbacks(Runnable runnable){removed++;}
''' + method(self.handle, 'private int z8HandleTop()') + '\n' + edge_scroll + '\n' + method(self.handle, 'public boolean onTouchEvent(MotionEvent event)') + r'''
    static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    public static void main(String[] args){
        TextSelectionHandleView handle=new TextSelectionHandleView();TerminalView view=handle.terminalView;
        check(view.z8SelectionEdgeSize()==126,"48dp edge at Samsung density");
        int visualTop=handle.z8HandleTop();
        check(visualTop==1310 && visualTop+handle.mHandleHeight==1390,"Whole grip ends 21px above terminal bottom");
        check(handle.mPointY==1380,"Visible clamping must not alter selected terminal row");
        float rawX=view.parentX+handle.mPointX+handle.mHotspotX;
        float rawY=view.parentY+visualTop+40;
        handle.onTouchEvent(new MotionEvent(MotionEvent.ACTION_DOWN,rawX,rawY));
        handle.onTouchEvent(new MotionEvent(MotionEvent.ACTION_MOVE,rawX,rawY));
        check(handle.mCursorController.lastY==1380,"Regrabbing the raised grip cannot jump selection");
        handle.onTouchEvent(new MotionEvent(MotionEvent.ACTION_UP,rawX,rawY));
        check(!handle.mIsDragging&&handle.removed==2,"Release cancels repeated edge work");

        // Finger can stay 29px above the view bottom while the corrected logical
        // endpoint is another 51px above it. No navigation-edge contact is needed.
        handle.mIsDragging=true;handle.mZ8DragY=view.height-80;handle.mZ8DragX=200;
        int initial=view.top,firstCalls=handle.mCursorController.calls;
        for(int i=0;i<5;i++)handle.mZ8EdgeScroll.run();
        check(view.top==initial+5&&handle.mCursorController.calls==firstCalls+5,"Stationary safe-edge hold keeps scrolling");
        handle.mZ8DragY=view.height/2;int before=handle.mCursorController.calls;
        handle.mZ8EdgeScroll.run();check(handle.mCursorController.calls==before,"Neutral region stops timer");
        handle.mZ8DragY=view.height-80;view.mEmulator.alternate=true;
        handle.mZ8EdgeScroll.run();check(handle.mCursorController.calls==before,"TUI private history is not scrolled by copy");
        view.mEmulator.alternate=false;view.focused=false;
        handle.mZ8EdgeScroll.run();check(handle.mCursorController.calls==before,"No scrolling after app loses focus");
        view.focused=true;handle.mIsDragging=false;
        handle.mZ8EdgeScroll.run();check(handle.mCursorController.calls==before,"No late tick after release");

        for(float density:new float[]{1,2.625f,4})for(int line:new int[]{12,38,90}){
            view.resources.density=density;view.mRenderer.spacing=line;
            view.height=1411;
            check(view.z8SelectionEdgeSize()>=48*density&&view.z8SelectionEdgeSize()>=2*line,"Touch and large-font target remain usable");
            view.height=120;
            check(view.z8SelectionEdgeSize()<=40,"Short viewport retains a neutral middle");
        }
        view.resources.density=2.625f;view.mRenderer.spacing=38;view.height=1411;
        view.clipTop=10;view.clipBottom=700;handle.mPointY=690;
        check(handle.z8HandleTop()+handle.mHandleHeight==679,"IME-clipped visible bottom also contains the full grip");
        handle.mIsDragging=true;handle.mZ8DragY=620;view.top=-20;
        for(int i=0;i<5;i++)handle.mZ8EdgeScroll.run();
        check(view.top==-15,"Stationary grip scrolls at actual visible bottom rather than hidden full height");
        view.clipTop=240;handle.mZ8DragY=300;
        handle.mZ8EdgeScroll.run();check(view.top==-16,"Top clipping has the same usable edge band");
        handle.mZ8DragY=470;before=handle.mCursorController.calls;
        handle.mZ8EdgeScroll.run();check(handle.mCursorController.calls==before,"Clipped viewport middle remains neutral");
        view.clipTop=600;view.clipBottom=690;handle.mZ8DragY=645;
        handle.mZ8EdgeScroll.run();check(handle.mCursorController.calls==before,"Even a narrow clipped viewport keeps neutral middle");
        view.visible=false;handle.mZ8DragY=690;
        handle.mZ8EdgeScroll.run();check(handle.mCursorController.calls==before,"Invisible viewport cannot scroll");
    }
}''')


if __name__ == '__main__':
    unittest.main()
