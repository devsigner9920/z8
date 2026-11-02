"""Run real browser/terminal navigation methods against deterministic Android doubles.

No browser or device is opened. The harness preserves the onStart selection
callback ordering that used to clear browserSelected before onResume.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def method(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class BrowserReturn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-browser-return-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        chrome = (ROOT / 'overlay/app/src/main/java/com/termux/app/Z8SessionChrome.java').read_text()
        methods = '\n'.join(method(chrome, signature) for signature in (
            'public void onResume()', 'public void onPause()', 'public void onStop()',
            'private void openBrowserTab()', 'private void returnFromBrowser()',
            'private void select(Z8SessionCatalog.Entry entry)',
            'private void rememberProject(String id)',
            'public void onSessionSelected(TerminalSession session)',
            'public void restoreSelection()', 'private void selectProject(String id, boolean closeDrawer)',
            'public void restoreTerminalInput()', 'private void restoreInputAfterLayout()',
        ))
        source = HARNESS.replace('/* ACTUAL_METHODS */', methods)
        paths = []
        for name, content in {
            'BrowserReturnProbe.java': source,
            'android/view/inputmethod/InputMethodManager.java':
                'package android.view.inputmethod;public class InputMethodManager {'
                'public void hideSoftInputFromWindow(Object token,int flags){} }',
        }.items():
            path = cls.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            paths.append(str(path))
        result = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(cls.directory), *paths],
                                capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, scenario):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'BrowserReturnProbe', scenario],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fullscreen_stop_start_resume_restores_origin_and_input_focus(self):
        self.probe('fullscreen')

    def test_partial_resume_and_existing_browser_reopen_use_latest_terminal(self):
        self.probe('partial')

    def test_explicit_other_project_navigation_is_never_overridden(self):
        self.probe('other-project')

    def test_same_project_notification_selection_wins_and_recovers_focus(self):
        self.probe('same-project-notification')


HARNESS = r'''import java.util.*;
import com.termux.app.Z8Text;
public class BrowserReturnProbe {
    static final String NAVIGATION_PREFS="navigation";
    static class Context { static final int MODE_PRIVATE=0;static final String INPUT_METHOD_SERVICE="keyboard"; }
    static class LinearLayout { static class LayoutParams { LayoutParams(int w,int h){} } }
    static class TerminalSession {
        final String mHandle,project;TerminalSession(String handle,String project){mHandle=handle;this.project=project;}
    }
    static class TerminalView {
        boolean focused,shown=true,suspended;int resumptions;
        void z8SuspendInput(){suspended=true;}void clearFocus(){focused=false;}
        void requestFocus(){focused=true;}boolean isShown(){return shown;}Object getWindowToken(){return this;}
        void z8ResumeInput(){suspended=false;if(focused)resumptions++;}
    }
    static class Service { final List<Z8SessionCatalog.Entry> entries=new ArrayList<>(); }
    static class Z8SessionCatalog {
        static class Entry {
            final String handle,projectId;final TerminalSession session;boolean running=true;
            Entry(TerminalSession session){this.session=session;handle=session.mHandle;projectId=session.project;}
        }
        static boolean contains(Service service,TerminalSession session){return service.entries.stream().anyMatch(e->e.session==session);}
        static List<Entry> snapshot(Service service,TerminalSession current){return new ArrayList<>(service.entries);}
    }
    static class Z8SessionOrigin {
        String projectId;static Z8SessionOrigin of(TerminalSession session){Z8SessionOrigin result=new Z8SessionOrigin();result.projectId=session.project;return result;}
    }
    static class Preferences {
        Preferences edit(){return this;}Preferences putString(String key,String value){return this;}void apply(){}
    }
    static class Drawer { void closeDrawers(){} }
    class Client {
        TerminalSession stored;
        void setCurrentSession(TerminalSession session){
            if(session==null)return;
            activity.current=session;
            // Generated TermuxTerminalSessionActivityClient calls these even
            // when attachSession returns false for an already selected PTY.
            onSessionSelected(session);refresh();
        }
        void setCurrentStoredSession(){stored=activity.current;}
        TerminalSession getCurrentStoredSessionOrLast(){return stored;}
        void onStart(){restoreSelection();}
    }
    class Activity {
        TerminalSession current;final TerminalView terminal=new TerminalView();final Service service=new Service();
        final Client client=new Client();boolean focus=true;
        TerminalSession getCurrentSession(){return current;}TerminalView getTerminalView(){return terminal;}
        Service getTermuxService(){return service;}Client getTermuxTerminalSessionClient(){return client;}
        Drawer getDrawer(){return new Drawer();}boolean hasWindowFocus(){return focus;}
        Preferences getSharedPreferences(String name,int flags){return new Preferences();}
        Object getSystemService(String name){return new android.view.inputmethod.InputMethodManager();}
    }
    static class Z8BrowserPane {
        final Runnable external;boolean foreground;
        Z8BrowserPane(Activity a,Runnable close,Runnable back,Runnable external){this.external=external;}
        void setForeground(boolean value){foreground=value;}void launchExternal(){external.run();}
    }
    static class Z8BrowserBridge { static void attach(Object listener){}static void detach(Object listener){} }
    static class Surface { void addView(Object child,Object params){} }
    static class Monitor { void stop(){} }
    static class Keys { void reset(){} }
    static class Handler {
        final ArrayDeque<Runnable> queue=new ArrayDeque<>();
        void post(Runnable task){queue.add(task);}void removeCallbacks(Runnable task){queue.removeIf(value->value==task);}
        void drain(){while(!queue.isEmpty())queue.remove().run();}
    }
    final Activity activity=new Activity();final Surface terminalSurface=new Surface();
    final Handler main=new Handler();final Monitor resourceMonitor=new Monitor();final Keys workspaceKeys=new Keys();
    final Runnable tick=()->{},restoreInput=this::restoreInputAfterLayout;final Object browserListener=new Object();
    final Map<String,String> lastSessions=new HashMap<>();final Set<String> collapsed=new HashSet<>();
    List<Z8SessionCatalog.Entry> entries=new ArrayList<>();
    boolean disposed,visible=true,resumed=true,browserSelected,externalOpening,resourcesVisible;
    String selectedProject,browserProject,browserSessionHandle,fingerprint="",preparationFingerprint="";
    Z8BrowserPane browserPane;
    void updateResourceVisibility(){}void loadProjects(){}void toast(String text){}
    void refresh(){entries=Z8SessionCatalog.snapshot(activity.service,activity.current);activity.terminal.shown=!browserSelected&&activity.current!=null;}
    void closeBrowserTab(){browserPane=null;browserProject=null;browserSessionHandle=null;browserSelected=false;}
    void clearTerminal(){activity.current=null;activity.terminal.clearFocus();refresh();}
    /* ACTUAL_METHODS */
    static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    Z8SessionCatalog.Entry add(String handle,String project){
        Z8SessionCatalog.Entry entry=new Z8SessionCatalog.Entry(new TerminalSession(handle,project));
        activity.service.entries.add(entry);refresh();return entry;
    }
    void leaveForBrowser(boolean stopped){
        browserPane.launchExternal();onPause();activity.focus=false;
        if(stopped)onStop();
        main.drain();
        check(activity.terminal.suspended&&!activity.terminal.focused,"Browser suspends terminal input and clears focus");
    }
    void assertReturned(Z8SessionCatalog.Entry origin){
        main.drain();
        check(activity.current==origin.session,"Exact browser origin must be selected");
        check(activity.terminal.focused,"Returning browser must focus terminal even after onStart cleared tab selection");
        check(activity.terminal.resumptions>0&&!activity.terminal.suspended,"Live focused terminal input must resume");
        check(!externalOpening&&!browserSelected,"Browser return is consumed once");
    }
    public static void main(String[] args){
        BrowserReturnProbe app=new BrowserReturnProbe();
        Z8SessionCatalog.Entry first=app.add("terminal-1","project-a"),second=app.add("terminal-2","project-a");
        Z8SessionCatalog.Entry other=app.add("terminal-3","project-b");
        app.select(first);app.openBrowserTab();
        Z8BrowserPane originalPane=app.browserPane;
        // An existing project browser is reopened from a different terminal.
        app.returnFromBrowser();app.select(second);app.openBrowserTab();
        check(app.browserPane==originalPane&&app.browserSessionHandle.equals(second.handle),"Reopen must capture latest same-project terminal");
        if(args[0].equals("fullscreen")){
            app.leaveForBrowser(true);app.activity.focus=true;
            app.activity.client.onStart();
            check(!app.browserSelected&&app.externalOpening,"onStart selection clears browserSelected before onResume");
            check(!app.activity.terminal.focused,"onStart selection alone does not restore keyboard focus");
            app.onResume();app.assertReturned(second);
        }else if(args[0].equals("partial")){
            app.leaveForBrowser(false);app.activity.focus=true;
            check(app.browserSelected,"Partial tab only paused z8");
            app.onResume();app.assertReturned(second);
        }else if(args[0].equals("same-project-notification")){
            app.leaveForBrowser(true);app.activity.focus=true;app.activity.client.onStart();
            // routeRequestedSession in onNewIntent selects the notified PTY
            // directly before onResume, including within the same project.
            app.activity.client.setCurrentSession(first.session);
            app.onResume();app.assertReturned(first);
        }else if(args[0].equals("other-project")){
            app.leaveForBrowser(true);app.activity.focus=true;
            app.select(other);check(app.browserPane==null,"Project switch disposes its old browser");
            app.onResume();app.main.drain();
            check(app.activity.current==other.session&&app.selectedProject.equals(other.projectId),"Explicit project switch wins over old origin");
            // Also validate the guard if a browser instance still exists while
            // a separate navigation update has already changed the project.
            app.browserPane=originalPane;app.browserProject=first.projectId;app.browserSessionHandle=second.handle;
            app.externalOpening=true;app.browserSelected=false;
            app.onResume();app.main.drain();
            check(app.activity.current==other.session&&app.activity.terminal.focused,"Old browser origin must not override another project");
        }else throw new AssertionError("Unknown scenario");
        System.out.println("PASS "+args[0]);
    }
}
'''


if __name__ == '__main__':
    unittest.main()
