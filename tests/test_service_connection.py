"""Execute generated foreground service-connection gating and retry callbacks."""
from pathlib import Path
import importlib.util
import json
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


class ForegroundServiceConnection(unittest.TestCase):
    def test_real_generated_callbacks_defer_keyguard_recover_denial_and_consume_navigation_once(self):
        spec = importlib.util.spec_from_file_location('prepare_connection', ROOT / 'tools/prepare-app.py')
        prepare = importlib.util.module_from_spec(spec); spec.loader.exec_module(prepare)
        with tempfile.TemporaryDirectory(prefix='z8-service-connection-') as directory:
            tree = Path(directory)
            shutil.copytree(ROOT / 'upstream/termux-app', tree / 'app', ignore=shutil.ignore_patterns('.git', 'build', '.gradle', '.cxx'))
            prepare.apply_patches(tree / 'app', json.loads((ROOT / 'tools/sources.lock.json').read_text()), 'diagnostic')
            activity = (tree / 'app/app/src/main/java/com/termux/app/TermuxActivity.java').read_text()
            helpers = '\n'.join(method(activity, signature) for signature in (
                'public void z8RequestServiceConnection()', 'private void z8ConnectServiceIfReady()',
                'public void onServiceConnected(ComponentName componentName, IBinder service)',
                'public void termuxSessionListNotifyUpdated()',
            ))
            fields = prepare.ACTIVITY_HELPERS.split('    private String mZ8FocusProjectPending;', 1)[1].split('    private static final String Z8_INTERNAL_SESSION_KEY', 1)[0]
            source = r'''import java.util.ArrayDeque;
public class ConnectionProbe {
    static class Context { static final int BIND_AUTO_CREATE=1;static final String KEYGUARD_SERVICE="keyguard"; }
    static class R { static class string { static final int error_termux_service_start_failed_general=1; } }
    static class Logger {
        static int errors,toasts;static void logDebug(String tag,String text){}
        static void logStackTraceWithMessage(String tag,String text,Exception e){errors++;}
        static void showToast(Object context,String text,boolean length){toasts++;}
    }
    static class Intent { Intent(Object context,Class<?> target){} }
    static class ComponentName {}
    interface IBinder {}
    static class TermuxService {
        boolean stopping;boolean wantsToStop(){return stopping;}
        static class LocalBinder implements IBinder {
            final TermuxService service;LocalBinder(TermuxService service){this.service=service;}
        }
    }
    static class SessionListController { int updates;void notifyDataSetChanged(){updates++;} }
    static class Decor {
        final ArrayDeque<Runnable> queue=new ArrayDeque<>();
        void post(Runnable task){queue.add(task);}void removeCallbacks(Runnable task){queue.removeIf(value->value==task);}
        void drain(){int count=0;while(!queue.isEmpty()){if(++count>20)throw new AssertionError("Retry spin");queue.remove().run();}}
    }
    static class Window { final Decor decor=new Decor();Decor getDecorView(){return decor;} }
    static final String LOG_TAG="fixture";
    final Window window=new Window();final android.app.KeyguardManager keyguard=new android.app.KeyguardManager();
    boolean mIsInvalidState,mIsVisible=true,finishing,destroyed,focus=true,rejectStart,failBind;
    TermuxService mTermuxService;SessionListController mTermuxSessionListViewController;
    int starts,binds,dispatches;String pendingIntent="explicit-terminal-request";
    Window getWindow(){return window;}boolean hasWindowFocus(){return focus;}
    boolean isFinishing(){return finishing;}boolean isDestroyed(){return destroyed;}
    Object getSystemService(String name){return keyguard;}String getString(int id){return "error";}
    void finishActivityIfNotFinishing(){finishing=true;}
    void setTermuxSessionsListView(){mTermuxSessionListViewController=new SessionListController();}
    void z8RefreshSessionChrome(){}
    void startService(Intent intent){starts++;if(rejectStart){rejectStart=false;throw new IllegalStateException("app is in background");}}
    boolean bindService(Intent intent,Object connection,int flags){binds++;if(flags!=1)throw new AssertionError();if(failBind){failBind=false;return false;}return true;}
    void z8DispatchConnectedService(){dispatches++;pendingIntent=null;}
''' + fields + helpers + r'''
    static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    void request(){z8RequestServiceConnection();window.decor.drain();}
    public static void main(String[] args) {
        ConnectionProbe app=new ConnectionProbe();
        app.request();check(app.starts==0,"onCreate/not-resumed never starts service");
        app.mZ8Resumed=true;app.keyguard.locked=true;app.request();
        check(app.starts==0&&!app.mIsInvalidState,"Resumed behind keyguard remains retryable");
        app.keyguard.locked=false;app.focus=false;app.request();
        check(app.starts==0,"No service before actual window focus");
        app.focus=true;app.rejectStart=true;app.request();
        check(app.starts==1&&app.binds==0&&!app.mIsInvalidState&&!app.mZ8ServiceBound,"Background denial does not poison Activity");
        check(app.window.decor.queue.isEmpty(),"No automatic retry timer after denial");
        app.z8RequestServiceConnection();app.z8RequestServiceConnection();app.z8RequestServiceConnection();
        check(app.window.decor.queue.size()==1,"Foreground requests coalesce");app.window.decor.drain();
        check(app.starts==2&&app.binds==1&&app.mZ8ServiceBound,"Same Activity retries once after unlock");
        app.request();app.request();check(app.binds==1,"Pending binding is never duplicated");
        app.mZ8Resumed=false;
        app.onServiceConnected(new ComponentName(),new TermuxService.LocalBinder(new TermuxService()));
        check(app.dispatches==0&&app.pendingIntent!=null&&app.mZ8ServiceNavigationPending,"Late connection preserves intent across pause");
        // Client.onStart sees the now-connected service and sends this update
        // before Activity.onResume can dispatch pending navigation.
        app.termuxSessionListNotifyUpdated();
        check(app.mTermuxSessionListViewController.updates==1&&app.dispatches==0,
            "Callback after stop wires list before next onStart without consuming intent");
        app.mZ8Resumed=true;app.request();
        check(app.dispatches==1&&app.pendingIntent==null&&app.starts==2,"Foreground consumes connected navigation once");
        app.request();app.request();check(app.dispatches==1&&app.binds==1,"Focus churn cannot replay terminal request");
        ConnectionProbe failed=new ConnectionProbe();failed.mZ8Resumed=true;failed.failBind=true;failed.request();
        check(!failed.mIsInvalidState&&!failed.mZ8ServiceBound&&Logger.toasts==1,"Bind failure is visible and retryable");
        failed.request();check(failed.binds==2&&failed.mZ8ServiceBound,"Explicit user retry can rebind");
        ConnectionProbe race=new ConnectionProbe();race.mZ8Resumed=true;race.z8RequestServiceConnection();race.mZ8Resumed=false;race.window.decor.drain();
        check(race.starts==0,"Eligibility rechecked at posted callback execution");
        race.mZ8Resumed=true;race.z8RequestServiceConnection();race.mZ8ServiceDisposed=true;race.window.decor.drain();
        check(race.starts==0,"Destroyed callback never starts service");
        race.onServiceConnected(new ComponentName(),new TermuxService.LocalBinder(new TermuxService()));
        check(race.mTermuxService==null&&race.dispatches==0,"Late callback cannot resurrect destroyed Activity");
        System.out.println("PASS generated foreground connection lifecycle");
    }
}'''
            (tree / 'ConnectionProbe.java').write_text(source)
            guard = tree / 'android/app/KeyguardManager.java';guard.parent.mkdir(parents=True)
            guard.write_text('package android.app;public class KeyguardManager {public boolean locked;public boolean isKeyguardLocked(){return locked;}}')
            jdk = ROOT / '.local/jdk/Contents/Home/bin'
            result = subprocess.run([str(jdk / 'javac'), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-d', str(tree), str(guard), str(tree / 'ConnectionProbe.java')], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(jdk / 'java'), '-cp', str(tree), 'ConnectionProbe'], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS generated foreground', result.stdout)
            create = method(activity, 'public void onCreate(Bundle savedInstanceState)')
            self.assertNotIn('startService(', create);self.assertNotIn('bindService(', create)
            self.assertNotIn('startForegroundService(', activity)
            resume = method(activity, 'public void onResume()')
            self.assertLess(resume.index('mZ8Resumed = true;'), resume.index('z8RequestServiceConnection();'))
            self.assertIn('mZ8Resumed = false;', method(activity, 'protected void onPause()'))
            self.assertIn('if (hasFocus) z8RequestServiceConnection();', method(activity, 'public void onWindowFocusChanged(boolean hasFocus)'))
            destroy = method(activity, 'public void onDestroy()')
            self.assertIn('removeCallbacks(mZ8ConnectService)', destroy)
            self.assertIn('if (mZ8ServiceBound)', destroy)
            connected = method(activity, 'public void onServiceConnected(ComponentName componentName, IBinder service)')
            self.assertNotIn('setIntent(', connected)
            self.assertNotIn('z8OpenRequestedSession(', connected)
            self.assertIn('setTermuxSessionsListView();', connected)
            dispatch = method(activity, 'private void z8DispatchConnectedService()')
            self.assertNotIn('setTermuxSessionsListView();', dispatch)
            self.assertIn('final Intent intent = getIntent();', dispatch)
            self.assertIn('if (!Z8GuestSessionLauncher.isPendingIntent(intent)) setIntent(null);', dispatch)


if __name__ == '__main__':
    unittest.main()
