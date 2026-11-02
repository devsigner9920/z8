"""Run the real launch state machine with deterministic Android/service stubs."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GuestSessionLauncherTests(unittest.TestCase):
    def test_service_owned_lifecycle(self):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not java:
            self.skipTest('A JDK is required')
        with tempfile.TemporaryDirectory(prefix='z8-launch-lifecycle-') as temporary:
            directory = Path(temporary).resolve()
            sources = []
            for name, code in STUBS.items():
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(code)
                sources.append(str(path))
            real = ROOT / 'overlay/app/src/main/java/com/termux/app/Z8GuestSessionLauncher.java'
            compile_result = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(directory), str(real), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8SessionCatalog.java'), *sources],
                                            capture_output=True, text=True, timeout=45)
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout + compile_result.stderr)
            result = subprocess.run([java, '-cp', str(directory), 'com.termux.app.LauncherProbe'],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS: service-owned launch lifecycle', result.stdout)


STUBS = {
    'com/termux/app/Z8InitialSetup.java': 'package com.termux.app; public class Z8InitialSetup {public static boolean hasWork(TermuxService service){return false;}}',
    'com/termux/app/Z8Projects.java': '''package com.termux.app;import android.content.Context;import java.io.IOException;
        public class Z8Projects {public Z8Projects(Context c){}public static class Project {public String name="Recovered project";}
        public Project open(String id)throws IOException {if(id.equals("removed-project"))throw new IOException("Removed");return new Project();}}''',
    'com/termux/app/Z8PreparationNotification.java': '''package com.termux.app;public class Z8PreparationNotification {
        public static int began,finished,released;public static volatile int progressed;
        public static void begin(TermuxService s,String id,String p,String n){began++;}
        public static void progress(TermuxService s,String id,String stage,int percent,String message){progressed++;}
        public static void finish(TermuxService s,String id,boolean success,String detail){finished++;}
        public static void releaseOwner(TermuxService s){released++;}}''',
    'com/termux/app/Z8ProjectRemoval.java': 'package com.termux.app; public class Z8ProjectRemoval {static boolean isDeleting(String id){return false;}}',
    'com/termux/app/Z8WorkspaceActivity.java': 'package com.termux.app; public class Z8WorkspaceActivity { public static final String EXTRA_PROJECT_ID="project"; }', 
    'android/content/Context.java': '''package android.content; import java.util.concurrent.*;
        public class Context {public static final int MODE_PRIVATE=0;private static final ConcurrentHashMap<String,SharedPreferences> preferences=new ConcurrentHashMap<>();
        public Context getApplicationContext(){return this;} public SharedPreferences getSharedPreferences(String name,int mode){return preferences.computeIfAbsent(name,key->new SharedPreferences());}}''',
    'android/content/SharedPreferences.java': '''package android.content;import java.util.*;import java.util.concurrent.*;public class SharedPreferences {
        public static volatile boolean failWrites; private final ConcurrentHashMap<String,String> data=new ConcurrentHashMap<>();
        public String getString(String key,String fallback){return data.getOrDefault(key,fallback);} public Map<String,?> getAll(){return new HashMap<>(data);} public Editor edit(){return new Editor();}
        public class Editor {private final Map<String,String> pending=new HashMap<>();public Editor putString(String key,String value){pending.put(key,value);return this;}
        public Editor remove(String key){pending.put(key,null);return this;}public void apply(){commit();}public boolean commit(){if(failWrites)return false;for(Map.Entry<String,String>e:pending.entrySet())if(e.getValue()==null)data.remove(e.getKey());else data.put(e.getKey(),e.getValue());return true;}}
    }''',
    'android/content/Intent.java': '''package android.content; import java.util.*; public class Intent {
        private final Map<String,Object> data=new HashMap<>(); public Intent(){} public Intent(Intent other){data.putAll(other.data);}
        public Intent putExtra(String key,String value){data.put(key,value);return this;} public Intent putExtra(String key,boolean value){data.put(key,value);return this;}
        public String getStringExtra(String key){return (String)data.get(key);} public boolean getBooleanExtra(String key,boolean fallback){return (Boolean)data.getOrDefault(key,fallback);}
    }''',
    'android/os/Bundle.java': '''package android.os; import java.util.*; public class Bundle {
        private final Map<String,Object> data=new HashMap<>(); public void putParcelable(String key,Object value){data.put(key,value);}
        @SuppressWarnings("unchecked") public <T>T getParcelable(String key){return (T)data.get(key);}
    }''',
    'android/os/Looper.java': '''package android.os; public class Looper { private static final Thread owner=Thread.currentThread(); private static final Looper MAIN=new Looper();
        public static Looper getMainLooper(){return MAIN;} public static Looper myLooper(){return Thread.currentThread()==owner?MAIN:null;}
    }''',
    'android/os/Handler.java': '''package android.os; import java.util.concurrent.*; public class Handler {
        public static final BlockingQueue<Runnable> queue=new LinkedBlockingQueue<>(); public Handler(Looper looper){}
        public boolean post(Runnable value){queue.add(value);return true;} public static void next()throws Exception{Runnable value=queue.poll(3,TimeUnit.SECONDS);if(value==null)throw new AssertionError("No completion");value.run();}
    }''',
    'android/R.java': '''package android; public class R {public static class string {public static final int ok=1;}}''',
    'android/app/AlertDialog.java': '''package android.app; import android.content.Context; public class AlertDialog {
        public static int shown; public static class Builder {public Builder(Context c){} public Builder setTitle(String s){return this;}
        public Builder setMessage(String s){return this;} public Builder setPositiveButton(int id,Object listener){return this;} public void show(){shown++;}}
    }''',
    'com/termux/terminal/TerminalSession.java': '''package com.termux.terminal; public class TerminalSession {public String mSessionName;public String mHandle=java.util.UUID.randomUUID().toString();public int starts;public boolean running=true;public boolean isRunning(){return running;}public void updateSize(int c,int r,int w,int h){starts++;}}''',
    'com/termux/shared/termux/shell/command/runner/terminal/TermuxSession.java': '''package com.termux.shared.termux.shell.command.runner.terminal;
        import com.termux.terminal.TerminalSession; public class TermuxSession {private final TerminalSession terminal=new TerminalSession();public TerminalSession getTerminalSession(){return terminal;}}
    ''',
    'com/termux/app/TermuxService.java': '''package com.termux.app; import android.content.Context; import java.util.*;
        import com.termux.shared.termux.shell.command.runner.terminal.TermuxSession;
        public class TermuxService extends Context {public boolean stopped,stopRequested;public int created; public List<TermuxSession> sessions=new ArrayList<>();
        public boolean z8IsStopRequested(){return stopRequested;}
        public void z8AcquireExecution(){if(!Z8GuestSessionLauncher.hasServiceWork(this))throw new AssertionError("Work lease must precede service start");}
        public void updateNotification(){}
        public boolean wantsToStop(){return stopped;} public int getTermuxSessionsSize(){return sessions.size();} public List<TermuxSession> getTermuxSessions(){return sessions;}
        public TermuxSession createTermuxSession(String e,String[]a,String in,String cwd,boolean failsafe,String name){created++;TermuxSession s=new TermuxSession();s.getTerminalSession().mSessionName=name;sessions.add(s);return s;}}
    ''',
    'com/termux/app/TermuxActivity.java': '''package com.termux.app; import android.content.*; import com.termux.terminal.TerminalSession;
        public class TermuxActivity extends Context {public TermuxService service; public boolean destroyed,finishing,visible=true; private Intent intent;public final Client client=new Client();public final Drawer drawer=new Drawer();
        public TermuxActivity(TermuxService s,Intent i){service=s;intent=i;}public TermuxService getTermuxService(){return service;}public Intent getIntent(){return intent;} public void setIntent(Intent i){intent=i;}
        public boolean isDestroyed(){return destroyed;}public boolean isFinishing(){return finishing;}public boolean isVisible(){return visible;}public Client getTermuxTerminalSessionClient(){return client;}public Drawer getDrawer(){return drawer;}
        public static class Client {public TerminalSession selected; public int stored;public void setCurrentSession(TerminalSession s){selected=s;}public void setCurrentStoredSession(){stored++;}}
        public static class Drawer{public void closeDrawers(){}}
    }''',
    'com/termux/app/Z8SessionOrigin.java': '''package com.termux.app; import java.util.*; import com.termux.terminal.TerminalSession; public class Z8SessionOrigin {
        public static int remembered; public String projectId,projectName,action;private static Map<TerminalSession,Z8SessionOrigin> origins=new HashMap<>();
        public static Z8SessionOrigin of(TerminalSession s){return origins.get(s);}
        public static void remember(TerminalSession s,String p,String n,String action){remembered++;Z8SessionOrigin o=new Z8SessionOrigin();o.projectId=p;o.projectName=n;o.action=action;origins.put(s,o);}}
    ''',
    'com/termux/app/Z8Guest.java': '''package com.termux.app; import android.content.Context;import java.util.concurrent.*;
        public class Z8Guest {public static final String EXTRA_GUEST_SESSION="guest";public static volatile CountDownLatch entered=new CountDownLatch(0),release=new CountDownLatch(0);public static volatile boolean fail; public static volatile boolean profilePrepared=true;
        public static boolean standardProfilePrepared(Context c,String p){return profilePrepared;}
        public static class Launch {public String executable="proot"; public String[] arguments={"-r","fixture"};public String workingDirectory="source";public boolean preparesShell=!profilePrepared;}
        public static Launch command(Context c,String p,String d)throws Exception {CountDownLatch gate=release;entered.countDown(); boolean done=false;while(!done){try{gate.await();done=true;}catch(InterruptedException ignored){}} if(fail)throw new Exception("Fixture failure");return new Launch();}
        public static Launch actionCommand(Context c,String p,String d,String a)throws Exception{return command(c,p,d);}public static String actionLabel(String a){return a==null?"Linux":a;}
    }''',
    'com/termux/app/Z8Bootstrap.java': '''package com.termux.app;import android.content.Context; public class Z8Bootstrap {
        interface Progress {void onProgress(int percent,String message);} public static volatile int calls;
        public static void ensure(Context context,Progress progress){calls++;progress.onProgress(100,"ready");}}
    ''',
    'com/termux/app/Z8ProjectPreparation.java': '''package com.termux.app;import android.content.Context;import java.util.concurrent.*;public class Z8ProjectPreparation {
        interface Progress {void update(String stage,int percent,String message);}
        public static volatile CountDownLatch entered=new CountDownLatch(0),release=new CountDownLatch(0);public static volatile boolean fail;
        public static volatile int calls,installations;
        static void run(Context context,String id,Progress progress)throws Exception {calls++;progress.update("bootstrap",20,"bootstrap");
            if(!Z8Guest.profilePrepared){progress.update("tools",-1,"tools");entered.countDown();release.await();
                if(fail)throw new java.io.IOException("Fixture automatic preparation failure");installations++;Z8Guest.profilePrepared=true;}}
    }''',
    'com/termux/app/LauncherProbe.java': r'''package com.termux.app;
        import android.content.Intent;import android.os.Bundle;import android.os.Handler;import java.util.concurrent.*;import java.util.concurrent.atomic.AtomicBoolean;
        public class LauncherProbe {
        static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
        static Intent guest(){return new Intent().putExtra(Z8Guest.EXTRA_GUEST_SESSION,true);}
        static void submit(TermuxService service,String id){Z8GuestSessionLauncher.request(service,id,"project",null,"fixture","codex");}
        public static void main(String[]args)throws Exception {
            check(!Z8GuestSessionLauncher.hasPending(null),"no service has no pending launch");
            // A project intent cannot accidentally select the Android native shell path.
            Intent projectOnly = new Intent().putExtra(Z8WorkspaceActivity.EXTRA_PROJECT_ID,"fixture-project");
            Z8GuestSessionLauncher.prepareIntent(projectOnly);
            check(projectOnly.getBooleanExtra(Z8Guest.EXTRA_GUEST_SESSION,false),"project intent is normalized to guest execution");
            check(Z8GuestSessionLauncher.isPendingIntent(projectOnly),"project-only intent receives a guest launch ticket");
            // Prepare and rotate before a service even exists.
            TermuxActivity original=new TermuxActivity(null,guest());Z8GuestSessionLauncher.restoreIntent(original,null);
            String first=Z8GuestSessionLauncher.requestId(original.getIntent());Bundle saved=new Bundle();Z8GuestSessionLauncher.saveIntent(original,saved);
            TermuxActivity rotated=new TermuxActivity(null,guest());Z8GuestSessionLauncher.restoreIntent(rotated,saved);
            check(first.equals(Z8GuestSessionLauncher.requestId(rotated.getIntent())),"pre-bind rotation retained the same ticket");
            TermuxService service=new TermuxService();Z8GuestSessionLauncher.start(service);rotated.service=service;Z8GuestSessionLauncher.observe(rotated);
            check(!Z8GuestSessionLauncher.hasPending(service),"prepared bootstrap ticket does not disable creation");
            submit(service,first);submit(service,first);
            check(Z8GuestSessionLauncher.hasPending(service),"accepted launch is pending until completion on main thread");
            check(!Z8GuestSessionLauncher.hasPending(new TermuxService()),"pending belongs only to its service generation");
            AtomicBoolean wrongThreadRejected=new AtomicBoolean();
            Thread wrongThread=new Thread(() -> {try{Z8GuestSessionLauncher.hasPending(service);}catch(IllegalStateException expected){wrongThreadRejected.set(true);}});
            wrongThread.start();wrongThread.join();check(wrongThreadRejected.get(),"pending query enforces main thread");
            Handler.next();
            check(!Z8GuestSessionLauncher.hasPending(service),"created launch is no longer pending");
            check(service.created==1 && rotated.client.selected!=null,"accepted once after pre-bind rotation");
            check(service.sessions.get(0).getTerminalSession().starts==1,"service starts PTY independently of view sizing");
            // Block preparation, rotate after acceptance, and reconnect the observer.
            Z8Guest.entered=new CountDownLatch(1);Z8Guest.release=new CountDownLatch(1);
            String second=Z8GuestSessionLauncher.newRequest(service);submit(service,second);check(Z8Guest.entered.await(2,TimeUnit.SECONDS),"worker entered");
            rotated.destroyed=true;Z8GuestSessionLauncher.forget(rotated);
            check(Z8GuestSessionLauncher.hasPending(service),"pending survives observer destruction");
            TermuxActivity next=new TermuxActivity(service,null);check(Z8GuestSessionLauncher.observe(next),"pending suppresses fallback native shell");
            Z8Guest.release.countDown();Handler.next();
            check(!Z8GuestSessionLauncher.hasPending(service),"completed launch releases the creation guard");
            check(service.created==2 && next.client.selected==service.sessions.get(1).getTerminalSession(),"rotation did not drop launch");
            // Finish with no observer, then deliver once on resume.
            next.visible=false;Z8GuestSessionLauncher.forget(next);String third=Z8GuestSessionLauncher.newRequest(service);submit(service,third);Handler.next();
            check(service.created==3 && service.sessions.get(2).getTerminalSession().starts==1,"background completion owns a running PTY");
            next.visible=true;check(Z8GuestSessionLauncher.observe(next),"resume delivered completed session");
            check(next.client.selected==service.sessions.get(2).getTerminalSession(),"resume selected correct new session");
            check(!Z8GuestSessionLauncher.observe(next),"delivery is consumed once");
            // Stop while preparation is blocked, then let the old result arrive.
            Z8Guest.entered=new CountDownLatch(1);Z8Guest.release=new CountDownLatch(1);
            String stopped=Z8GuestSessionLauncher.newRequest(service);submit(service,stopped);Z8Guest.entered.await(2,TimeUnit.SECONDS);
            Z8GuestSessionLauncher.stop(service);service.stopped=true;
            check(!Z8GuestSessionLauncher.hasPending(service),"service stop clears pending visibility before late result");
            Z8Guest.release.countDown();Handler.next();
            check(service.created==3,"stopped service never executes late result");
            TermuxService replacement=new TermuxService();Z8GuestSessionLauncher.start(replacement);submit(replacement,stopped);
            check(!Z8GuestSessionLauncher.hasPending(replacement),"replacement excludes cancelled old-generation work");
            check(replacement.created==0,"service restart does not replay ticket");
            // A restored ticket absent from this process is refused, not re-registered.
            Bundle foreign=new Bundle();foreign.putParcelable("z8_pending_guest_intent",guest().putExtra("dev.devsigner.z8.GUEST_REQUEST","unknown-process-id"));
            TermuxActivity restored=new TermuxActivity(replacement,guest());Z8GuestSessionLauncher.restoreIntent(restored,foreign);
            check(restored.getIntent()==null,"process restart does not restore an action");
            // A failure is visible without synthesizing a terminal; normal future requests still work.
            Z8GuestSessionLauncher.observe(restored);Z8Guest.fail=true;String failed=Z8GuestSessionLauncher.newRequest(replacement);submit(replacement,failed);Handler.next();
            check(!Z8GuestSessionLauncher.hasPending(replacement),"failed preparation releases the creation guard");
            check(replacement.created==0 && android.app.AlertDialog.shown==1,"failure reported without starting a PTY");
            String abandoned=Z8GuestSessionLauncher.newRequest(replacement);
            check(abandoned!=null && !Z8GuestSessionLauncher.hasPending(replacement),"abandoned bootstrap ticket cannot permanently block later launches");
            Z8Guest.fail=false;String finalId=Z8GuestSessionLauncher.newRequest(replacement);submit(replacement,finalId);Handler.next();
            check(replacement.created==1 && Z8SessionOrigin.remembered==4,"new explicit request succeeds with provenance");
            // The query does not change deliberate callers or the queued-work capacity limit.
            for(int index=0;index<6;index++){submit(replacement,Z8GuestSessionLauncher.newRequest(replacement));Handler.next();}
            Z8Guest.entered=new CountDownLatch(1);Z8Guest.release=new CountDownLatch(1);
            submit(replacement,Z8GuestSessionLauncher.newRequest(replacement));
            check(Z8Guest.entered.await(2,TimeUnit.SECONDS),"eighth session preparation entered");
            submit(replacement,Z8GuestSessionLauncher.newRequest(replacement));
            check(replacement.created==7 && android.app.AlertDialog.shown==2,"queued eighth session reserves capacity against ninth");
            check(Z8GuestSessionLauncher.hasPending(replacement),"capacity rejection does not hide remaining accepted work");
            Z8Guest.release.countDown();Handler.next();
            check(replacement.created==8 && !Z8GuestSessionLauncher.hasPending(replacement),"capacity remains eight and completed queue releases guard");
            Z8GuestSessionLauncher.stop(replacement);
            // Repeated setup taps share one accepted job and reconnect to its PTY.
            TermuxService setupService=new TermuxService();Z8GuestSessionLauncher.start(setupService);
            Z8Guest.entered=new CountDownLatch(1);Z8Guest.release=new CountDownLatch(1);
            Z8GuestSessionLauncher.request(setupService,Z8GuestSessionLauncher.newRequest(setupService),"project",null,"fixture","setup-tools");
            check(Z8Guest.entered.await(2,TimeUnit.SECONDS),"setup queued");
            Z8GuestSessionLauncher.request(setupService,Z8GuestSessionLauncher.newRequest(setupService),"project",null,"fixture","setup-tools");
            Z8Guest.release.countDown();Handler.next();check(setupService.created==1,"queued setup deduplicated");
            Z8GuestSessionLauncher.request(setupService,Z8GuestSessionLauncher.newRequest(setupService),"project",null,"fixture","setup-tools");
            check(setupService.created==1 && !Z8GuestSessionLauncher.hasPending(setupService),"running setup reused");
            setupService.sessions.get(0).getTerminalSession().running=false;
            Z8GuestSessionLauncher.request(setupService,Z8GuestSessionLauncher.newRequest(setupService),"project",null,"fixture","setup-tools");
            Handler.next();check(setupService.created==2,"stopped setup can be explicitly retried");
            Z8GuestSessionLauncher.stop(setupService);
            // Cold first shell is prepared headlessly; no PTY exists until the tools are ready.
            TermuxService firstShell=new TermuxService();Z8GuestSessionLauncher.start(firstShell);Z8Guest.profilePrepared=false;
            Z8Guest.entered=new CountDownLatch(0);Z8Guest.release=new CountDownLatch(0);
            Z8ProjectPreparation.entered=new CountDownLatch(1);Z8ProjectPreparation.release=new CountDownLatch(1);
            TermuxActivity preparingView=new TermuxActivity(firstShell,null);Z8GuestSessionLauncher.observe(preparingView);
            int dialogs=android.app.AlertDialog.shown;
            Z8GuestSessionLauncher.request(firstShell,Z8GuestSessionLauncher.newRequest(firstShell),"project",null,"fixture",null);
            check(Z8ProjectPreparation.entered.await(2,TimeUnit.SECONDS),"automatic tools preparation entered");
            check(firstShell.created==0 && android.app.AlertDialog.shown==dialogs,"preparation has no temporary terminal or modal");
            check(Z8GuestSessionLauncher.hasServiceWork(firstShell),"headless preparation keeps foreground service alive");
            check(!Z8GuestSessionLauncher.hasServiceWork(new TermuxService()),"preparation lease belongs only to current service");
            check(Z8GuestSessionLauncher.preparation(firstShell,"project").stage.equals("tools"),"main view observes worker progress");
            check(firstShell.getSharedPreferences("z8.project-preparation",0).getString("project",null)!=null,"unfinished operation persisted before work");
            Z8GuestSessionLauncher.request(firstShell,Z8GuestSessionLauncher.newRequest(firstShell),"project",null,"fixture",null);
            preparingView.destroyed=true;Z8GuestSessionLauncher.forget(preparingView);
            TermuxActivity preparationRotated=new TermuxActivity(firstShell,null);check(Z8GuestSessionLauncher.observe(preparationRotated),"rotation reconnects in-flight preparation");
            Z8ProjectPreparation.release.countDown();Handler.next();
            check(firstShell.created==1 && Z8ProjectPreparation.installations==1,"duplicate preparation creates exactly one ready shell");
            check(firstShell.sessions.get(0).getTerminalSession().mSessionName.equals("Terminal 1"),"first ordinary shell gets a raw numbered name");
            check(preparationRotated.client.selected==firstShell.sessions.get(0).getTerminalSession(),"ready shell delivered to rotated view");
            check(!Z8GuestSessionLauncher.hasServiceWork(firstShell) && Z8GuestSessionLauncher.preparation(firstShell,"project")==null,"successful preparation releases progress and service lease");
            check(firstShell.getSharedPreferences("z8.project-preparation",0).getString("project",null)==null,"completed durable marker cleared");
            Z8Guest.entered=new CountDownLatch(1);Z8Guest.release=new CountDownLatch(1);
            Z8GuestSessionLauncher.request(firstShell,Z8GuestSessionLauncher.newRequest(firstShell),"project",null,"fixture",null);
            check(Z8Guest.entered.await(2,TimeUnit.SECONDS),"warm shell launch entered");
            check(Z8GuestSessionLauncher.preparation(firstShell,"project")==null,"warm launch does not flash first-install or interruption copy");
            Z8Guest.release.countDown();
            Handler.next();check(firstShell.created==2 && Z8ProjectPreparation.installations==1,"prepared profile creates independent new shell without reinstall");
            check(firstShell.sessions.get(1).getTerminalSession().mSessionName.equals("Terminal 2"),"second ordinary shell has a distinct number");
            firstShell.sessions.get(0).getTerminalSession().mSessionName="custom server";
            check(Z8SessionCatalog.title(firstShell.sessions.get(0).getTerminalSession()).equals("custom server"),"renamed terminal stays user-owned");
            check(firstShell.sessions.get(0).getTerminalSession().running,"new shell leaves earlier PTY intact");
            Z8GuestSessionLauncher.request(firstShell,Z8GuestSessionLauncher.newRequest(firstShell),"project",null,"fixture",null);
            Handler.next();check(firstShell.sessions.get(2).getTerminalSession().mSessionName.equals("Terminal 3"),"ordinary shell retains sequence after rename");
            Z8GuestSessionLauncher.stop(firstShell);

            // A failed cold preparation stays inline, does not make a PTY, and is explicitly retryable.
            TermuxService errors=new TermuxService();Z8GuestSessionLauncher.start(errors);Z8Guest.profilePrepared=false;Z8ProjectPreparation.fail=true;
            TermuxActivity errorView=new TermuxActivity(errors,null);Z8GuestSessionLauncher.observe(errorView);
            Z8GuestSessionLauncher.request(errors,Z8GuestSessionLauncher.newRequest(errors),"project",null,"fixture",null);Handler.next();
            check(errors.created==0 && android.app.AlertDialog.shown==dialogs,"automatic failure remains inline without a shell or modal");
            check(Z8GuestSessionLauncher.preparation(errors,"project").failed,"failed state is visible and retryable");
            check(!Z8GuestSessionLauncher.hasServiceWork(errors),"failure releases headless service lease");
            Z8GuestSessionLauncher.stop(errors);
            TermuxService recovered=new TermuxService();Z8GuestSessionLauncher.start(recovered);
            check(Z8GuestSessionLauncher.preparation(recovered,"project").failed && !Z8GuestSessionLauncher.hasPending(recovered),"service recreation reports interruption without replaying install");
            Z8ProjectPreparation.fail=false;
            Z8GuestSessionLauncher.request(recovered,Z8GuestSessionLauncher.newRequest(recovered),"project",null,"fixture",null);Handler.next();
            check(recovered.created==1 && Z8GuestSessionLauncher.preparation(recovered,"project")==null,"explicit retry clears the old error");
            Z8GuestSessionLauncher.stop(recovered);

            // Service stop interrupts the headless worker; late completion cannot create a session.
            TermuxService cancelled=new TermuxService();Z8GuestSessionLauncher.start(cancelled);Z8Guest.profilePrepared=false;
            Z8ProjectPreparation.entered=new CountDownLatch(1);Z8ProjectPreparation.release=new CountDownLatch(1);
            String cancelledId=Z8GuestSessionLauncher.newRequest(cancelled);
            Z8GuestSessionLauncher.request(cancelled,cancelledId,"cancelled-project",null,"fixture",null);
            check(Z8ProjectPreparation.entered.await(2,TimeUnit.SECONDS),"cancellable preparation entered");
            Z8GuestSessionLauncher.stop(cancelled);cancelled.stopped=true;Handler.next();
            check(cancelled.created==0 && !Z8GuestSessionLauncher.hasServiceWork(cancelled),"service cancellation never launches a terminal");
            TermuxService restarted=new TermuxService();Z8GuestSessionLauncher.start(restarted);
            check(Z8GuestSessionLauncher.preparation(restarted,"cancelled-project").failed,"cancelled pending marker survives service recreation");
            Z8GuestSessionLauncher.request(restarted,cancelledId,"cancelled-project",null,"fixture",null);
            check(!Z8GuestSessionLauncher.hasPending(restarted),"old cancelled preparation ticket cannot restart work");
            Z8ProjectPreparation.release.countDown();Z8GuestSessionLauncher.stop(restarted);

            // Persisted state is necessary before work; a write failure has no installation side effects.
            TermuxService storage=new TermuxService();Z8GuestSessionLauncher.start(storage);int calls=Z8ProjectPreparation.calls;
            android.content.SharedPreferences.failWrites=true;
            Z8GuestSessionLauncher.request(storage,Z8GuestSessionLauncher.newRequest(storage),"storage-project",null,"fixture",null);Handler.next();
            android.content.SharedPreferences.failWrites=false;
            check(storage.created==0 && Z8ProjectPreparation.calls==calls,"failed durable marker prevents installation");
            check(Z8GuestSessionLauncher.preparation(storage,"storage-project").failed,"storage failure is inline and retryable");
            Z8GuestSessionLauncher.stop(storage);

            // Capacity failure must be a retryable error, never an endless bootstrap progress bar.
            TermuxService full=new TermuxService();Z8GuestSessionLauncher.start(full);Z8Guest.profilePrepared=true;
            for(int index=0;index<8;index++){submit(full,Z8GuestSessionLauncher.newRequest(full));Handler.next();}
            int beforeCapacity=Z8ProjectPreparation.calls;
            Z8GuestSessionLauncher.request(full,Z8GuestSessionLauncher.newRequest(full),"full-project",null,"fixture",null);
            check(full.created==8 && Z8ProjectPreparation.calls==beforeCapacity,"full service never begins extra preparation");
            check(Z8GuestSessionLauncher.preparation(full,"full-project").failed,"capacity rejection produces failed inline preparation");
            check(!Z8GuestSessionLauncher.hasServiceWork(full),"rejected capacity owns no service lease");
            Z8GuestSessionLauncher.stop(full);

            // Explicit notification Stop admits no new ticket, prepared ticket, or late worker result.
            TermuxService stopping=new TermuxService();Z8GuestSessionLauncher.start(stopping);
            String prepared=Z8GuestSessionLauncher.newRequest(stopping);int beforeStop=Z8ProjectPreparation.calls;
            stopping.stopRequested=true;
            check(Z8GuestSessionLauncher.newRequest(stopping)==null,"explicit Stop refuses a new launch ticket");
            submit(stopping,prepared);
            check(!Z8GuestSessionLauncher.hasPending(stopping)&&stopping.created==0&&Z8ProjectPreparation.calls==beforeStop,"prepared ticket cannot start work during Stop");
            stopping.stopRequested=false;Z8Guest.entered=new CountDownLatch(1);Z8Guest.release=new CountDownLatch(1);
            submit(stopping,Z8GuestSessionLauncher.newRequest(stopping));
            check(Z8Guest.entered.await(2,TimeUnit.SECONDS),"late result fixture entered");
            stopping.stopRequested=true;Z8Guest.release.countDown();Handler.next();
            check(stopping.created==0&&!Z8GuestSessionLauncher.hasPending(stopping),"late prepared command cannot create a PTY during Stop");
            stopping.stopRequested=false;
            submit(stopping,Z8GuestSessionLauncher.newRequest(stopping));Handler.next();
            check(stopping.created==1,"failed or blocked Stop does not destroy the service launch generation");
            Z8GuestSessionLauncher.stop(stopping);

            // Only interrupted, app-owned installation work resumes after a foreground return.
            android.content.SharedPreferences journal=stopping.getSharedPreferences("z8.project-preparation",0);
            for(String key:journal.getAll().keySet())journal.edit().remove(key).commit();
            journal.edit().putString("resume-project","running:tools").putString("failed-project","failed")
                .putString("removed-project","running:rootfs").commit();
            TermuxService resume=new TermuxService();Z8GuestSessionLauncher.start(resume);
            check(!Z8GuestSessionLauncher.hasPending(resume),"service creation alone never restarts work");
            TermuxActivity foreground=new TermuxActivity(resume,null);foreground.visible=false;
            Z8GuestSessionLauncher.observe(foreground);
            check(!Z8GuestSessionLauncher.hasPending(resume),"background observer cannot auto-resume");
            Z8Guest.profilePrepared=false;Z8ProjectPreparation.fail=false;
            Z8ProjectPreparation.entered=new CountDownLatch(1);Z8ProjectPreparation.release=new CountDownLatch(1);
            int notifications=Z8PreparationNotification.began;
            foreground.visible=true;Z8GuestSessionLauncher.observe(foreground);
            check(Z8ProjectPreparation.entered.await(2,TimeUnit.SECONDS),"foreground return resumes interrupted installer");
            check(Z8GuestSessionLauncher.preparation(resume,"resume-project").resuming,"UI identifies recovered preparation");
            check(journal.getString("resume-project","").equals("running:tools"),"current completed-boundary stage is durable");
            check(journal.getString("removed-project",null)==null,"deleted project is not recreated");
            check(journal.getString("failed-project",null).equals("failed"),"clean failure remains explicit retry");
            Z8GuestSessionLauncher.observe(foreground);Z8GuestSessionLauncher.observe(foreground);
            check(Z8PreparationNotification.began==notifications+1,"repeated resumes retain a single notification/job");
            Z8ProjectPreparation.release.countDown();Handler.next();
            check(resume.created==1 && journal.getString("resume-project",null)==null,"recovered installer completes once and clears receipt");
            check(Z8SessionOrigin.of(resume.sessions.get(0).getTerminalSession()).action==null,"recovery opens plain terminal, never an AI command");
            Z8GuestSessionLauncher.observe(foreground);check(resume.created==1,"completed recovery is not replayed");
            Z8GuestSessionLauncher.stop(resume);

            // Legacy pending receipts migrate through the same validated installer path.
            journal.edit().remove("failed-project").putString("legacy-project","pending").commit();
            TermuxService legacy=new TermuxService();Z8GuestSessionLauncher.start(legacy);
            Z8Guest.profilePrepared=false;
            Z8GuestSessionLauncher.observe(new TermuxActivity(legacy,null));Handler.next();
            check(legacy.created==1&&journal.getString("legacy-project",null)==null,"legacy interrupted installer recovers");
            Z8GuestSessionLauncher.stop(legacy);

            // A queued second project is durable before its worker gets a turn.
            TermuxService queued=new TermuxService();Z8GuestSessionLauncher.start(queued);Z8Guest.profilePrepared=false;
            Z8ProjectPreparation.entered=new CountDownLatch(1);Z8ProjectPreparation.release=new CountDownLatch(1);
            Z8GuestSessionLauncher.request(queued,Z8GuestSessionLauncher.newRequest(queued),"queue-first",null,"First",null);
            check(Z8ProjectPreparation.entered.await(2,TimeUnit.SECONDS),"first installer occupies serial worker");
            Z8GuestSessionLauncher.request(queued,Z8GuestSessionLauncher.newRequest(queued),"queue-second",null,"Second",null);
            check(journal.getString("queue-second","").equals("running:queued"),"queued acceptance is committed before worker execution");
            Z8GuestSessionLauncher.stop(queued);queued.stopped=true;Handler.next();
            Z8ProjectPreparation.release.countDown();
            TermuxService queueRecovery=new TermuxService();Z8GuestSessionLauncher.start(queueRecovery);
            Z8GuestSessionLauncher.observe(new TermuxActivity(queueRecovery,null));Handler.next();Handler.next();
            check(queueRecovery.created==2,"both accepted installers recover after service/process loss");
            check(journal.getAll().isEmpty(),"every completed queued installer clears its journal");
            Z8GuestSessionLauncher.stop(queueRecovery);
            System.out.println("PASS: service-owned launch lifecycle");
        }
    }''',
}
