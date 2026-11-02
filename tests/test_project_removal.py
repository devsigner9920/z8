"""Execute the real deletion coordinator with owned files and deterministic PTY exit/clock adapters.

No Android app, emulator, user project, or network is accessed. The real coordinator's
main/worker handoff runs; the filesystem adapter deletes only this test's temp fixture.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProjectRemovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-owned-removal-test-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        sources = []
        for name, code in STUBS.items():
            path = cls.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code)
            sources.append(str(path))
        actual = ROOT / 'overlay/app/src/main/java/com/termux/app/Z8ProjectRemoval.java'
        result = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(cls.directory), str(actual), *sources],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, name):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.RemovalProbe',
                                 str(self.directory), name], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS removal ' + name, result.stdout)

    def test_waits_for_both_ptys_then_deletes_owned_files_only(self):
        self.probe('ordered')

    def test_timeout_and_service_stop_preserve_files(self):
        self.probe('timeout')

    def test_duplicate_and_pending_preparation_are_rejected(self):
        self.probe('duplicate')

    def test_activity_independent_work_holds_lease_through_io(self):
        self.probe('lease')

    def test_filesystem_error_releases_lease_without_reporting_success(self):
        self.probe('failure')

    def test_callback_failure_cannot_skip_service_notification_update(self):
        self.probe('callback')

    def test_unverified_process_exit_preserves_files_and_session_wrappers(self):
        self.probe('verification-error')

    def test_stop_verification_holds_lease_without_activity_or_early_delete(self):
        self.probe('verification-blocked')

    def test_service_stop_during_process_verification_preserves_files(self):
        self.probe('verification-stop')

    def test_service_stop_after_verification_before_main_callback_preserves_empty_project(self):
        self.probe('post-verification-stop')

    def test_single_session_stop_preserves_other_sessions_and_project_files_without_activity(self):
        self.probe('session-success')

    def test_duplicate_session_stop_is_rejected_while_verification_holds_lease(self):
        self.probe('session-duplicate')

    def test_service_stop_during_single_session_verification_preserves_wrapper(self):
        self.probe('session-cancel')

    def test_session_verification_failure_protects_wrapper_and_allows_verified_retry(self):
        self.probe('session-verification-error')

    def test_session_stop_and_same_project_delete_conflict_but_other_project_can_complete(self):
        self.probe('session-delete-conflict')

    def test_project_delete_rejects_single_stop_of_its_target(self):
        self.probe('deleting-session-conflict')

    def test_session_java_exit_timeout_preserves_wrapper(self):
        self.probe('session-timeout')

    def test_session_stop_after_verification_before_main_callback_preserves_wrapper(self):
        self.probe('session-post-verification-stop')

    def test_all_stop_waits_for_every_project_session_and_preserves_files(self):
        self.probe('all-success')

    def test_all_stop_verification_failure_preserves_and_protects_every_wrapper(self):
        self.probe('all-verification-error')

    def test_all_stop_rejects_active_setup_without_signalling(self):
        self.probe('all-setup-conflict')

    def test_all_stop_rejects_active_project_deletion_without_disturbing_it(self):
        self.probe('all-delete-conflict')

    def test_all_stop_rejects_active_single_session_stop_without_disturbing_it(self):
        self.probe('all-single-stop-conflict')

    def test_duplicate_all_stop_does_not_signal_or_acquire_again(self):
        self.probe('all-duplicate')

    def test_service_stop_cancels_all_verification_and_preserves_wrappers(self):
        self.probe('all-cancel')

    def test_all_stop_timeout_preserves_even_already_exited_wrappers(self):
        self.probe('all-timeout')

    def test_all_stop_late_service_cancellation_preserves_every_wrapper(self):
        self.probe('all-post-verification-stop')

    def test_requested_all_stop_blocks_new_individual_actions_but_can_complete(self):
        self.probe('all-requested-guard')

    def test_empty_all_stop_still_holds_service_lease_through_async_completion(self):
        self.probe('all-empty')


STUBS = {
    'android/content/Context.java': '''package android.content;import java.nio.file.*;import java.util.concurrent.*;
        public class Context {public final Path fixture;private final ConcurrentHashMap<String,SharedPreferences> preferences=new ConcurrentHashMap<>();
            public Context(Path fixture){this.fixture=fixture;}
            public Context getApplicationContext(){return this;}
            public SharedPreferences getSharedPreferences(String name,int mode){return preferences.computeIfAbsent(name,key->new SharedPreferences());}}''',
    'android/content/SharedPreferences.java': '''package android.content;import java.util.*;import java.util.concurrent.*;
        public class SharedPreferences {private final Map<String,String> data=new ConcurrentHashMap<>();
            public String getString(String key,String fallback){return data.getOrDefault(key,fallback);}
            public Editor edit(){return new Editor();}
            public class Editor {private final Map<String,String> pending=new HashMap<>();
                public Editor remove(String key){pending.put(key,null);return this;}
                public Editor putString(String key,String value){pending.put(key,value);return this;}
                public void apply(){for(Map.Entry<String,String> entry:pending.entrySet())
                    if(entry.getValue()==null)data.remove(entry.getKey());else data.put(entry.getKey(),entry.getValue());}}}''',
    'android/os/Looper.java': '''package android.os;public class Looper {private static final Thread OWNER=Thread.currentThread();
        private static final Looper MAIN=new Looper();public static Looper getMainLooper(){return MAIN;}
        public static Looper myLooper(){return Thread.currentThread()==OWNER?MAIN:null;}}''',
    'android/os/SystemClock.java': '''package android.os;public class SystemClock {
        public static volatile long now;public static long elapsedRealtime(){return now;}}''',
    'android/os/Handler.java': '''package android.os;import java.util.*;import java.util.concurrent.*;
        public class Handler {public Handler(Looper looper){}
            private static final BlockingQueue<Runnable> immediate=new LinkedBlockingQueue<>();
            private static final List<Delayed> delayed=new ArrayList<>();
            private static class Delayed {long when;Runnable task;Delayed(long when,Runnable task){this.when=when;this.task=task;}}
            public boolean post(Runnable task){return immediate.offer(task);}
            public boolean postDelayed(Runnable task,long delay){synchronized(delayed){delayed.add(new Delayed(SystemClock.now+delay,task));}return true;}
            public static void advance(long delta){SystemClock.now+=delta;List<Runnable> ready=new ArrayList<>();
                synchronized(delayed){Iterator<Delayed> it=delayed.iterator();while(it.hasNext()){Delayed entry=it.next();
                    if(entry.when<=SystemClock.now){ready.add(entry.task);it.remove();}}}for(Runnable task:ready)task.run();}
            public static Runnable take()throws Exception{Runnable task=immediate.poll(3,TimeUnit.SECONDS);
                if(task==null)throw new AssertionError("No coordinator completion");return task;}
            public static void next()throws Exception{take().run();}
        }''',
    'com/termux/terminal/TerminalSession.java': '''package com.termux.terminal;
        public class TerminalSession {public final String project;public volatile boolean running=true,unverified;public int signals;
            public TerminalSession(String project){this.project=project;}public boolean isRunning(){return running;}
            public void finishIfRunning(){if(android.os.Looper.myLooper()==android.os.Looper.getMainLooper())throw new AssertionError("Stop was not offloaded");if(running)signals++;}}''',
    'com/termux/app/TermuxService.java': '''package com.termux.app;import android.content.*;import java.nio.file.*;import java.util.*;
        import com.termux.terminal.TerminalSession;
        public class TermuxService extends Context {public boolean stopped,stopRequested;public int removed,notifications,acquisitionCount,removalLeaseChecks;
            public final List<TerminalSession> sessions=new ArrayList<>();public TermuxService(Path root){super(root);}
            public boolean wantsToStop(){return stopped;}
            public boolean z8IsStopRequested(){return stopRequested;}
            public void removeTermuxSession(TerminalSession session){if(session.isRunning())throw new AssertionError("Removed live PTY");
                if(!Z8ProjectRemoval.hasWork())throw new AssertionError("Session removed after execution lease released");removalLeaseChecks++;
                if(sessions.remove(session))removed++;}
            public void updateNotification(){notifications++;}
            public void z8AcquireExecution(){if(!Z8ProjectRemoval.hasWork())throw new AssertionError("Execution acquired before lease registration");acquisitionCount++;}
        }''',
    'com/termux/app/Z8SessionCatalog.java': '''package com.termux.app;import com.termux.terminal.TerminalSession;import java.util.*;
        public class Z8SessionCatalog {public static class Entry {public final String projectId;public final TerminalSession session;
                Entry(TerminalSession s){session=s;projectId=s.project;}}
            public static List<Entry> snapshot(TermuxService service,TerminalSession current){List<Entry> items=new ArrayList<>();
                for(TerminalSession s:new ArrayList<>(service.sessions))items.add(new Entry(s));return items;}
            public static boolean contains(TermuxService service,TerminalSession session){return service.sessions.contains(session);}}
        ''',
    'com/termux/app/Z8GuestSessionLauncher.java': '''package com.termux.app;public class Z8GuestSessionLauncher {
        public static boolean pending;public static boolean hasPending(TermuxService service){return pending;}}''',
    'com/termux/app/Z8SessionOrigin.java': '''package com.termux.app;import com.termux.terminal.TerminalSession;
        public class Z8SessionOrigin {public final String projectId;private Z8SessionOrigin(String id){projectId=id;}
            public static Z8SessionOrigin of(TerminalSession terminal){return terminal==null?null:new Z8SessionOrigin(terminal.project);}}''',
    'com/termux/app/Z8ProjectProcesses.java': '''package com.termux.app;import com.termux.terminal.TerminalSession;
        import java.util.*;import java.util.concurrent.*;import java.util.function.BooleanSupplier;import java.io.IOException;
        public class Z8ProjectProcesses {public static volatile int calls,captured;public static boolean fail;
            public static CountDownLatch entered=new CountDownLatch(0),release=new CountDownLatch(0);
            public static final class Target {final TerminalSession terminal;Target(TerminalSession terminal){this.terminal=terminal;}}
            public static boolean hasUnverified(TerminalSession terminal){return terminal!=null&&terminal.unverified;}
            public static Target capture(TerminalSession terminal) {
                if(android.os.Looper.myLooper()!=android.os.Looper.getMainLooper())throw new AssertionError("Capture left main thread");
                captured++;return new Target(terminal);}
            public static void stopAndVerify(List<Target> targets,BooleanSupplier stopping)throws Exception {
                if(android.os.Looper.myLooper()==android.os.Looper.getMainLooper())throw new AssertionError("Process wait blocked UI");
                if(!Z8ProjectRemoval.hasWork())throw new AssertionError("Stop worker has no foreground lease");
                calls++;for(Target target:targets){target.terminal.unverified=true;target.terminal.finishIfRunning();}entered.countDown();release.await();
                if(stopping.getAsBoolean())throw new IOException("Service stopped; owned files preserved");
                if(fail)throw new IOException("Process exit unverified; owned files preserved");
                for(Target target:targets)target.terminal.unverified=false;
            }}''',
    'com/termux/app/Z8Guest.java': '''package com.termux.app;import android.content.Context;import java.io.*;import java.nio.file.*;
        import java.nio.file.attribute.BasicFileAttributes;import java.util.concurrent.*;
        public class Z8Guest {public static volatile int calls;public static boolean fail;
            public static CountDownLatch entered=new CountDownLatch(0),release=new CountDownLatch(0);
            public static void deleteProject(Context context,String id)throws Exception {
                if(android.os.Looper.myLooper()==android.os.Looper.getMainLooper())throw new AssertionError("Filesystem ran on main thread");
                if(!Z8ProjectRemoval.isDeleting(id)||!Z8ProjectRemoval.hasWork())throw new AssertionError("Worker lost foreground lease");
                TermuxService service=(TermuxService)context;
                for(com.termux.terminal.TerminalSession session:service.sessions)
                    if(id.equals(session.project))throw new AssertionError("Files touched before every target PTY was removed");
                calls++;entered.countDown();release.await();if(fail)throw new IOException("owned fixture deletion failed");
                Path target=context.fixture.resolve(id).normalize();
                if(!target.getParent().equals(context.fixture)||!id.startsWith("owned-"))throw new AssertionError("Non-owned fixture path");
                Files.walkFileTree(target,new SimpleFileVisitor<Path>() {
                    @Override public FileVisitResult visitFile(Path file,BasicFileAttributes attrs)throws IOException {Files.delete(file);return FileVisitResult.CONTINUE;}
                    @Override public FileVisitResult postVisitDirectory(Path directory,IOException failure)throws IOException {
                        if(failure!=null)throw failure;Files.delete(directory);return FileVisitResult.CONTINUE;}});
            }}''',
    'com/termux/app/RemovalProbe.java': r'''package com.termux.app;
        import android.os.Handler;import android.content.SharedPreferences;
        import com.termux.terminal.TerminalSession;import java.nio.file.*;import java.util.concurrent.*;
        public class RemovalProbe {
            static void check(boolean value,String reason){if(!value)throw new AssertionError(reason);}
            static class Result implements Z8ProjectRemoval.Result {int calls;String error;boolean screenAttached=true;
                public void complete(String error){check(android.os.Looper.myLooper()==android.os.Looper.getMainLooper(),"Callback left main thread");
                    calls++;this.error=error;/* No Activity is required to finish deletion. */}}
            static void fixture(Path root,String id)throws Exception{for(String path:new String[]{"source/main.py","environment/rootfs/bin/tool","home/settings"}) {
                Path file=root.resolve(id).resolve(path);Files.createDirectories(file.getParent());Files.writeString(file,id+" sentinel");}}
            static TerminalSession session(TermuxService service,String id){TerminalSession s=new TerminalSession(id);service.sessions.add(s);return s;}
            static boolean exists(TermuxService service,String id){return Files.isRegularFile(service.fixture.resolve(id+"/source/main.py"));}
            public static void main(String[]args)throws Exception {
                Path root=Files.createTempDirectory(Path.of(args[0]),"owned-files-").toRealPath();
                TermuxService service=new TermuxService(root);fixture(root,"owned-target");fixture(root,"owned-other");
                String scenario=args[1];Result result=new Result();
                try {
                    switch(scenario) {
                        case "ordered": {
                            TerminalSession a=session(service,"owned-target"),b=session(service,"owned-target"),other=session(service,"owned-other");
                            SharedPreferences nav=service.getSharedPreferences("z8.terminal-navigation",0);
                            nav.edit().putString("project","owned-target").putString("local-project","owned-target").putString("remote-project","owned-other").apply();
                            service.getSharedPreferences("z8.project-preparation",0).edit().putString("owned-target","pending").putString("owned-other","other").apply();
                            Z8ProjectRemoval.begin(service,"owned-target",result);
                            check(service.acquisitionCount==1,"Project deletion acquires execution after registering its lease");
                            Handler.next(); // Process verification returns to main before Java PTY exit polling.
                            check(Z8ProjectProcesses.captured==2&&Z8ProjectProcesses.calls==1,"Capture only target identities then verify once off main");
                            check(a.signals==1&&b.signals==1&&other.signals==0,"Stop exactly target's two PTYs");
                            check(exists(service,"owned-target")&&Z8Guest.calls==0&&result.calls==0,"No early filesystem mutation");
                            a.running=false;Handler.advance(100);
                            check(exists(service,"owned-target")&&service.removed==0&&Z8Guest.calls==0,"Wait for second PTY too");
                            b.running=false;Handler.advance(100);Handler.next();
                            check(result.calls==1&&result.error==null,"Deletion reports one success");
                            check(!Files.exists(root.resolve("owned-target"))&&exists(service,"owned-other"),"Only owned target tree removed");
                            check(service.sessions.size()==1&&service.sessions.get(0)==other&&other.running,"Other project stays running");
                            check(nav.getString("project",null)==null&&nav.getString("local-project",null)==null,"Target selection cleared");
                            check("owned-other".equals(nav.getString("remote-project",null)),"Other selection preserved");
                            check(service.getSharedPreferences("z8.project-preparation",0).getString("owned-target",null)==null,"Target preparation marker cleared");
                            check("other".equals(service.getSharedPreferences("z8.project-preparation",0).getString("owned-other",null)),"Other marker preserved");
                            check(!Z8ProjectRemoval.hasWork()&&Z8ProjectRemoval.revision()==1&&service.notifications==1,"Lease released and observers notified");
                            break;
                        }
                        case "timeout": {
                            TerminalSession live=session(service,"owned-target");Z8ProjectRemoval.begin(service,"owned-target",result);Handler.next();
                            Handler.advance(9999);check(result.calls==0&&Z8ProjectRemoval.hasWork(),"Keep waiting before deadline");
                            Handler.advance(100);
                            check(result.calls==1&&result.error!=null&&result.error.contains("files were kept"),"Timeout explicitly reports preservation");
                            check(exists(service,"owned-target")&&Z8Guest.calls==0&&service.removed==0&&live.running,"Timeout never touches files/removes a live PTY");
                            check(!Z8ProjectRemoval.hasWork()&&service.notifications==1,"Timeout releases lease");
                            Result stopped=new Result();Z8ProjectRemoval.begin(service,"owned-target",stopped);Handler.next();service.stopped=true;Handler.advance(100);
                            check(stopped.calls==1&&stopped.error!=null&&exists(service,"owned-target"),"Service stop during exit also preserves files");
                            break;
                        }
                        case "duplicate": {
                            TerminalSession live=session(service,"owned-target");Z8ProjectRemoval.begin(service,"owned-target",result);Handler.next();
                            Result duplicate=new Result();Z8ProjectRemoval.begin(service,"owned-target",duplicate);
                            check(duplicate.calls==1&&duplicate.error.contains("already")&&live.signals==1,"Duplicate rejected without second stop");
                            check(service.acquisitionCount==1,"Rejected duplicate deletion must not acquire execution again");
                            Result pending=new Result();Z8GuestSessionLauncher.pending=true;Z8ProjectRemoval.begin(service,"owned-other",pending);
                            check(pending.calls==1&&pending.error!=null&&!Z8ProjectRemoval.isDeleting("owned-other"),"In-flight preparation blocks deletion");
                            check(service.acquisitionCount==1,"Rejected pending-preparation deletion must not acquire execution");
                            Z8GuestSessionLauncher.pending=false;live.running=false;Handler.advance(100);Handler.next();
                            check(result.calls==1&&result.error==null&&exists(service,"owned-other"),"Original work completes independently of rejection");
                            break;
                        }
                        case "lease": {
                            Z8Guest.entered=new CountDownLatch(1);Z8Guest.release=new CountDownLatch(1);
                            Z8ProjectRemoval.begin(service,"owned-target",result);result.screenAttached=false;Handler.next();
                            check(Z8Guest.entered.await(3,TimeUnit.SECONDS),"Worker reached owned fixture");
                            check(Z8ProjectRemoval.isDeleting("owned-target")&&Z8ProjectRemoval.hasWork()&&result.calls==0,"Lease held while IO blocks after screen leaves");
                            check(exists(service,"owned-target"),"Blocked IO has not removed files");
                            Z8Guest.release.countDown();Handler.next();
                            check(!result.screenAttached&&result.calls==1&&result.error==null&&!exists(service,"owned-target"),"Completion does not require Activity");
                            check(!Z8ProjectRemoval.hasWork()&&service.notifications==1,"IO completion releases foreground lease");
                            break;
                        }
                        case "failure": {
                            Z8Guest.fail=true;Z8ProjectRemoval.begin(service,"owned-target",result);Handler.next();Handler.next();
                            check(result.calls==1&&"owned fixture deletion failed".equals(result.error),"Filesystem error propagated");
                            check(exists(service,"owned-target")&&exists(service,"owned-other"),"Pre-delete failure preserves both trees");
                            check(!Z8ProjectRemoval.hasWork()&&service.notifications==1,"Failure releases lease and refreshes service");
                            break;
                        }
                        case "callback": {
                            Z8ProjectRemoval.begin(service,"owned-target",error->{throw new IllegalStateException("expired UI callback");});
                            Handler.next();
                            try {Handler.next();throw new AssertionError("Expected callback exception");}
                            catch(IllegalStateException expected){check(expected.getMessage().equals("expired UI callback"),"Callback identity");}
                            check(!Z8ProjectRemoval.hasWork()&&!exists(service,"owned-target"),"UI callback cannot undo completed independent work");
                            check(service.notifications==1,"Callback exception must not skip service notification update");
                            break;
                        }
                        case "verification-error": {
                            TerminalSession live=session(service,"owned-target");Z8ProjectProcesses.fail=true;
                            Z8ProjectRemoval.begin(service,"owned-target",result);Handler.next();
                            check(result.calls==1&&result.error!=null&&result.error.contains("unverified"),"Unverified tracee exit must surface a failure");
                            check(live.signals==1&&service.sessions.contains(live)&&service.removed==0,"Do not discard PTY records after verification fails");
                            check(Z8Guest.calls==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"No filesystem call before verified process exit");
                            check(!Z8ProjectRemoval.hasWork()&&service.notifications==1,"Verification failure releases lease");
                            break;
                        }
                        case "verification-blocked": {
                            TerminalSession live=session(service,"owned-target");
                            Z8ProjectProcesses.entered=new CountDownLatch(1);Z8ProjectProcesses.release=new CountDownLatch(1);
                            Z8ProjectRemoval.begin(service,"owned-target",result);result.screenAttached=false;
                            check(Z8ProjectProcesses.entered.await(3,TimeUnit.SECONDS),"Process verification worker entered");
                            check(Z8ProjectRemoval.hasWork()&&Z8ProjectRemoval.isDeleting("owned-target"),"Lease held while process verifier blocks");
                            check(result.calls==0&&service.removed==0&&Z8Guest.calls==0&&exists(service,"owned-target"),"No early callbacks, wrapper removal or file deletion");
                            Result duplicate=new Result();Z8ProjectRemoval.begin(service,"owned-target",duplicate);
                            check(duplicate.calls==1&&duplicate.error!=null&&live.signals==1,"Blocked verifier still rejects duplicate stop");
                            Z8ProjectProcesses.release.countDown();Handler.next();
                            check(result.calls==0&&exists(service,"owned-target"),"Verifier return still waits for Java PTY exit acknowledgement");
                            live.running=false;Handler.advance(100);Handler.next();
                            check(!result.screenAttached&&result.calls==1&&result.error==null&&!exists(service,"owned-target"),"Deletion completes independently after both verification and Java acknowledgement");
                            break;
                        }
                        case "verification-stop": {
                            TerminalSession live=session(service,"owned-target");
                            Z8ProjectProcesses.entered=new CountDownLatch(1);Z8ProjectProcesses.release=new CountDownLatch(1);
                            Z8ProjectRemoval.begin(service,"owned-target",result);
                            check(Z8ProjectProcesses.entered.await(3,TimeUnit.SECONDS),"Cancellable process verification entered");
                            service.stopped=true;Z8ProjectProcesses.release.countDown();Handler.next();
                            check(result.calls==1&&result.error!=null&&service.sessions.contains(live),"Service cancellation leaves PTY record for inspection");
                            check(Z8Guest.calls==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"Stop before verification cannot authorize filesystem deletion");
                            check(!Z8ProjectRemoval.hasWork()&&service.notifications==1,"Cancelled verifier releases lease");
                            break;
                        }
                        case "post-verification-stop": {
                            Z8ProjectRemoval.begin(service,"owned-target",result);
                            Runnable verified=Handler.take(); // Worker succeeded, but awaitExit has not run on main.
                            check(Z8ProjectProcesses.calls==1&&Z8ProjectProcesses.captured==0,"Empty target verified with no captured PTYs");
                            check(Z8ProjectRemoval.hasWork()&&result.calls==0&&Z8Guest.calls==0,"Hold lease between verifier and main handoff");
                            service.stopped=true;verified.run();
                            check(result.calls==1&&result.error!=null&&result.error.contains("files were kept"),"Late service stop must report preservation");
                            check(Z8Guest.calls==0&&service.removed==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"No filesystem call after late service stop even with no PTY to await");
                            check(!Z8ProjectRemoval.hasWork()&&service.notifications==1,"Main handoff cancellation releases lease and notifies service");
                            break;
                        }
                        case "session-success": {
                            TerminalSession target=session(service,"owned-target"),sibling=session(service,"owned-target"),other=session(service,"owned-other");
                            service.getSharedPreferences("z8.terminal-navigation",0).edit().putString("project","owned-target").apply();
                            Z8ProjectRemoval.stopSession(service,target,result);result.screenAttached=false;
                            check(service.acquisitionCount==1,"Single stop acquires execution after registering its lease");
                            check(Z8ProjectRemoval.isStopping(target)&&Z8ProjectRemoval.protects(target)&&Z8ProjectRemoval.hasWork(),"Single stop holds a session lease before worker completion");
                            Handler.next();
                            check(Z8ProjectProcesses.captured==1&&Z8ProjectProcesses.calls==1&&target.signals==1,"Capture and stop only requested PTY");
                            check(sibling.signals==0&&other.signals==0&&service.removed==0&&result.calls==0,"Other PTYs remain untouched and Java exit must still be acknowledged");
                            target.running=false;Handler.advance(100);
                            check(result.calls==1&&result.error==null&&!result.screenAttached,"Single stop completes without Activity");
                            check(!service.sessions.contains(target)&&service.sessions.size()==2&&service.sessions.contains(sibling)&&service.sessions.contains(other),"Remove exactly requested stopped wrapper");
                            check(Z8Guest.calls==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"Single stop never deletes project files");
                            check("owned-target".equals(service.getSharedPreferences("z8.terminal-navigation",0).getString("project",null)),"Single stop retains project selection");
                            check(!Z8ProjectRemoval.hasWork()&&!Z8ProjectRemoval.isStopping(target)&&!Z8ProjectRemoval.protects(target)&&service.notifications==1,"Completion releases session lease and updates service");
                            break;
                        }
                        case "session-duplicate": {
                            TerminalSession target=session(service,"owned-target");
                            Z8ProjectProcesses.entered=new CountDownLatch(1);Z8ProjectProcesses.release=new CountDownLatch(1);
                            Z8ProjectRemoval.stopSession(service,target,result);
                            check(Z8ProjectProcesses.entered.await(3,TimeUnit.SECONDS),"Single session verifier entered");
                            Result duplicate=new Result();Z8ProjectRemoval.stopSession(service,target,duplicate);
                            check(duplicate.calls==1&&duplicate.error!=null&&Z8ProjectProcesses.captured==1&&target.signals==1,"Duplicate must not capture or signal twice");
                            check(service.acquisitionCount==1,"Rejected duplicate session stop must not acquire execution again");
                            check(Z8ProjectRemoval.isStopping(target)&&Z8ProjectRemoval.protects(target)&&Z8ProjectRemoval.hasWork()&&service.removed==0,"Duplicate rejection cannot release original lease");
                            Z8ProjectProcesses.release.countDown();Handler.next();target.running=false;Handler.advance(100);
                            check(result.calls==1&&result.error==null&&service.removed==1&&!Z8ProjectRemoval.hasWork(),"Original stop completes once");
                            break;
                        }
                        case "session-cancel": {
                            TerminalSession target=session(service,"owned-target");
                            Z8ProjectProcesses.entered=new CountDownLatch(1);Z8ProjectProcesses.release=new CountDownLatch(1);
                            Z8ProjectRemoval.stopSession(service,target,result);
                            check(Z8ProjectProcesses.entered.await(3,TimeUnit.SECONDS),"Single session verifier entered before cancellation");
                            service.stopped=true;Z8ProjectProcesses.release.countDown();Handler.next();
                            check(result.calls==1&&result.error!=null&&service.sessions.contains(target)&&service.removed==0,"Cancellation preserves target wrapper");
                            check(Z8Guest.calls==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"Session cancellation never touches files");
                            check(!Z8ProjectRemoval.isStopping(target)&&!Z8ProjectRemoval.hasWork()&&Z8ProjectRemoval.protects(target)&&service.notifications==1,"Release active lease but retain unverified-process protection");
                            break;
                        }
                        case "session-verification-error": {
                            TerminalSession target=session(service,"owned-target");Z8ProjectProcesses.fail=true;
                            Z8ProjectRemoval.stopSession(service,target,result);Handler.next();
                            check(result.calls==1&&result.error!=null&&result.error.contains("unverified")&&service.sessions.contains(target),"Verification failure preserves wrapper and reports reason");
                            check(!Z8ProjectRemoval.isStopping(target)&&!Z8ProjectRemoval.hasWork()&&Z8ProjectRemoval.protects(target)&&service.removed==0,"Unverified tracees protect wrapper after lease releases");
                            Z8ProjectProcesses.fail=false;Result retry=new Result();Z8ProjectRemoval.stopSession(service,target,retry);Handler.next();
                            target.running=false;Handler.advance(100);
                            check(retry.calls==1&&retry.error==null&&service.removed==1&&!Z8ProjectRemoval.protects(target),"Verified retry can remove protected wrapper");
                            check(Z8Guest.calls==0&&exists(service,"owned-target")&&service.notifications==2,"Both completions notify without deleting files");
                            break;
                        }
                        case "session-delete-conflict": {
                            TerminalSession target=session(service,"owned-target");Z8ProjectRemoval.stopSession(service,target,result);Handler.next();
                            Result conflicting=new Result();Z8ProjectRemoval.begin(service,"owned-target",conflicting);
                            check(conflicting.calls==1&&conflicting.error!=null&&!Z8ProjectRemoval.isDeleting("owned-target"),"Do not delete project while its session stop awaits exit");
                            check(service.acquisitionCount==1,"Rejected same-project deletion must not acquire another execution lease");
                            check(Z8ProjectProcesses.captured==1&&target.signals==1,"Conflicting deletion must not signal session twice");
                            Result other=new Result();Z8ProjectRemoval.begin(service,"owned-other",other);Handler.next();Handler.next();
                            check(other.calls==1&&other.error==null&&!exists(service,"owned-other")&&exists(service,"owned-target"),"Independent project deletion can finish");
                            check(service.acquisitionCount==2,"Independent project work acquires its own execution lease");
                            check(Z8ProjectRemoval.hasWork()&&Z8ProjectRemoval.isStopping(target)&&result.calls==0,"Other completion cannot release original session lease");
                            target.running=false;Handler.advance(100);
                            check(result.calls==1&&result.error==null&&!Z8ProjectRemoval.hasWork()&&Z8Guest.calls==1,"Session stop completes independently without deleting its files");
                            break;
                        }
                        case "deleting-session-conflict": {
                            TerminalSession target=session(service,"owned-target");Z8ProjectRemoval.begin(service,"owned-target",result);Handler.next();
                            check(Z8ProjectRemoval.protects(target),"Project deletion protects its target wrapper while awaiting exit");
                            Result conflicting=new Result();Z8ProjectRemoval.stopSession(service,target,conflicting);
                            check(conflicting.calls==1&&conflicting.error!=null&&!Z8ProjectRemoval.isStopping(target),"Do not separately stop a session already owned by project deletion");
                            check(service.acquisitionCount==1,"Rejected same-project session stop must not acquire another execution lease");
                            check(target.signals==1&&Z8ProjectProcesses.captured==1&&Z8ProjectRemoval.isDeleting("owned-target"),"Rejected single stop cannot signal twice or release deletion lease");
                            target.running=false;Handler.advance(100);Handler.next();
                            check(result.calls==1&&result.error==null&&!exists(service,"owned-target")&&exists(service,"owned-other")&&!Z8ProjectRemoval.hasWork(),"Original deletion finishes normally");
                            break;
                        }
                        case "session-timeout": {
                            TerminalSession target=session(service,"owned-target");Z8ProjectRemoval.stopSession(service,target,result);Handler.next();
                            Handler.advance(9999);check(result.calls==0&&Z8ProjectRemoval.hasWork(),"Single stop retains lease before Java exit deadline");
                            Handler.advance(100);
                            check(result.calls==1&&result.error!=null&&target.running&&service.sessions.contains(target)&&service.removed==0,"Java exit timeout preserves running wrapper");
                            check(!Z8ProjectRemoval.hasWork()&&Z8Guest.calls==0&&exists(service,"owned-target")&&service.notifications==1,"Timeout releases lease but never deletes files");
                            break;
                        }
                        case "session-post-verification-stop": {
                            TerminalSession target=session(service,"owned-target");Z8ProjectRemoval.stopSession(service,target,result);
                            Runnable verified=Handler.take();target.running=false;service.stopped=true;verified.run();
                            check(result.calls==1&&result.error!=null&&service.sessions.contains(target)&&service.removed==0,"Late service stop preserves even an already-exited wrapper");
                            check(!Z8ProjectRemoval.hasWork()&&Z8Guest.calls==0&&exists(service,"owned-target")&&service.notifications==1,"Late cancellation releases lease without filesystem work");
                            break;
                        }
                        case "all-success": {
                            TerminalSession a=session(service,"owned-target"),b=session(service,"owned-other");
                            service.getSharedPreferences("z8.terminal-navigation",0).edit().putString("project","owned-target").apply();
                            Z8ProjectRemoval.stopAllSessions(service,result);result.screenAttached=false;
                            check(Z8ProjectRemoval.isStopping(a)&&Z8ProjectRemoval.isStopping(b)&&Z8ProjectRemoval.hasWork(),"Every target is protected by a lease before async work");
                            check(service.acquisitionCount==1,"Entire stop acquires execution once");
                            Handler.next();
                            check(Z8ProjectProcesses.captured==2&&Z8ProjectProcesses.calls==1&&a.signals==1&&b.signals==1,"One verifier batch stops both project PTYs");
                            a.running=false;Handler.advance(100);
                            check(result.calls==0&&service.removed==0&&Z8ProjectRemoval.isStopping(a)&&Z8ProjectRemoval.isStopping(b),"Do not discard even an exited wrapper before all PTYs acknowledge exit");
                            b.running=false;Handler.advance(100);
                            check(result.calls==1&&result.error==null&&!result.screenAttached&&service.sessions.isEmpty(),"Whole-service stop completes once without Activity");
                            check(service.removalLeaseChecks==2&&!Z8ProjectRemoval.hasWork()&&!Z8ProjectRemoval.isStopping(a)&&!Z8ProjectRemoval.isStopping(b),"Lease spans removal of the last wrapper then releases");
                            check(Z8Guest.calls==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"Stop all never deletes either project's files");
                            check("owned-target".equals(service.getSharedPreferences("z8.terminal-navigation",0).getString("project",null)),"Stop all preserves project navigation");
                            break;
                        }
                        case "all-verification-error": {
                            TerminalSession a=session(service,"owned-target"),b=session(service,"owned-other");Z8ProjectProcesses.fail=true;
                            Z8ProjectRemoval.stopAllSessions(service,result);Handler.next();
                            check(result.calls==1&&result.error!=null&&result.error.contains("unverified"),"Whole-service verifier error must be visible");
                            check(service.sessions.size()==2&&service.removed==0&&Z8ProjectRemoval.protects(a)&&Z8ProjectRemoval.protects(b),"Failure preserves and protects all wrappers");
                            check(!Z8ProjectRemoval.hasWork()&&!Z8ProjectRemoval.isStopping(a)&&!Z8ProjectRemoval.isStopping(b),"Failed operation releases active leases while retaining verification evidence");
                            check(Z8Guest.calls==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"Failed whole-service stop cannot delete files");
                            break;
                        }
                        case "all-setup-conflict": {
                            TerminalSession a=session(service,"owned-target"),b=session(service,"owned-other");Z8GuestSessionLauncher.pending=true;
                            Z8ProjectRemoval.stopAllSessions(service,result);
                            check(result.calls==1&&result.error!=null&&Z8ProjectProcesses.captured==0&&Z8ProjectProcesses.calls==0,"In-flight setup rejects whole-service stop before capturing or verifying");
                            check(a.signals==0&&b.signals==0&&service.sessions.size()==2&&service.acquisitionCount==0&&!Z8ProjectRemoval.hasWork(),"Rejected stop preserves setup and all sessions without a new lease");
                            check(Z8Guest.calls==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"Setup rejection keeps all files");
                            break;
                        }
                        case "all-delete-conflict": {
                            TerminalSession a=session(service,"owned-target"),b=session(service,"owned-other");
                            Z8ProjectRemoval.begin(service,"owned-target",result);Handler.next();
                            Result blocked=new Result();Z8ProjectRemoval.stopAllSessions(service,blocked);
                            check(blocked.calls==1&&blocked.error!=null&&Z8ProjectProcesses.calls==1&&Z8ProjectProcesses.captured==1,"Existing deletion rejects whole-service stop before extra process work");
                            check(a.signals==1&&b.signals==0&&service.acquisitionCount==1&&Z8ProjectRemoval.isDeleting("owned-target"),"Rejection leaves original deletion and other live PTY untouched");
                            a.running=false;Handler.advance(100);Handler.next();
                            check(result.calls==1&&result.error==null&&!exists(service,"owned-target")&&exists(service,"owned-other")&&service.sessions.contains(b),"Original project deletion still completes");
                            break;
                        }
                        case "all-single-stop-conflict": {
                            TerminalSession a=session(service,"owned-target"),b=session(service,"owned-other");
                            Z8ProjectRemoval.stopSession(service,a,result);Handler.next();
                            Result blocked=new Result();Z8ProjectRemoval.stopAllSessions(service,blocked);
                            check(blocked.calls==1&&blocked.error!=null&&Z8ProjectProcesses.calls==1&&Z8ProjectProcesses.captured==1,"Existing individual stop rejects whole-service stop");
                            check(a.signals==1&&b.signals==0&&service.acquisitionCount==1&&Z8ProjectRemoval.isStopping(a),"Rejection preserves original lease and does not signal another project");
                            a.running=false;Handler.advance(100);
                            check(result.calls==1&&result.error==null&&service.sessions.size()==1&&service.sessions.contains(b)&&Z8Guest.calls==0,"Original individual stop completes independently");
                            break;
                        }
                        case "all-duplicate": {
                            TerminalSession a=session(service,"owned-target"),b=session(service,"owned-other");
                            Z8ProjectProcesses.entered=new CountDownLatch(1);Z8ProjectProcesses.release=new CountDownLatch(1);
                            Z8ProjectRemoval.stopAllSessions(service,result);
                            check(Z8ProjectProcesses.entered.await(3,TimeUnit.SECONDS),"Whole-service verifier entered");
                            Result duplicate=new Result();Z8ProjectRemoval.stopAllSessions(service,duplicate);
                            check(duplicate.calls==1&&duplicate.error!=null&&Z8ProjectProcesses.captured==2&&Z8ProjectProcesses.calls==1,"Duplicate stop does not submit another verifier batch");
                            check(a.signals==1&&b.signals==1&&service.acquisitionCount==1&&Z8ProjectRemoval.hasWork(),"Duplicate stop neither re-signals nor releases the original lease");
                            Z8ProjectProcesses.release.countDown();Handler.next();a.running=false;b.running=false;Handler.advance(100);
                            check(result.calls==1&&result.error==null&&service.sessions.isEmpty()&&!Z8ProjectRemoval.hasWork(),"Original whole-service stop completes once");
                            break;
                        }
                        case "all-cancel": {
                            TerminalSession a=session(service,"owned-target"),b=session(service,"owned-other");
                            Z8ProjectProcesses.entered=new CountDownLatch(1);Z8ProjectProcesses.release=new CountDownLatch(1);
                            Z8ProjectRemoval.stopAllSessions(service,result);
                            check(Z8ProjectProcesses.entered.await(3,TimeUnit.SECONDS),"Whole-service verifier entered before cancellation");
                            service.stopped=true;Z8ProjectProcesses.release.countDown();Handler.next();
                            check(result.calls==1&&result.error!=null&&service.sessions.size()==2&&service.removed==0,"Service cancellation preserves every PTY record");
                            check(Z8ProjectRemoval.protects(a)&&Z8ProjectRemoval.protects(b)&&!Z8ProjectRemoval.hasWork(),"Cancelled unverified targets remain protected after active lease release");
                            check(Z8Guest.calls==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"Service cancellation leaves both project trees intact");
                            break;
                        }
                        case "all-timeout": {
                            TerminalSession a=session(service,"owned-target"),b=session(service,"owned-other");
                            Z8ProjectRemoval.stopAllSessions(service,result);Handler.next();a.running=false;
                            Handler.advance(9999);check(result.calls==0&&Z8ProjectRemoval.hasWork()&&service.removed==0,"Whole-service stop waits for final Java PTY acknowledgement");
                            Handler.advance(100);
                            check(result.calls==1&&result.error!=null&&service.sessions.size()==2&&service.removed==0&&b.running,"Timeout retains all wrappers, including one that exited");
                            check(!Z8ProjectRemoval.hasWork()&&Z8Guest.calls==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"Timed-out whole-service stop cannot delete files");
                            break;
                        }
                        case "all-post-verification-stop": {
                            TerminalSession a=session(service,"owned-target"),b=session(service,"owned-other");
                            Z8ProjectRemoval.stopAllSessions(service,result);Runnable verified=Handler.take();
                            a.running=false;b.running=false;service.stopped=true;verified.run();
                            check(result.calls==1&&result.error!=null&&service.sessions.size()==2&&service.removed==0,"Service stop between verifier and main callback preserves exited wrappers");
                            check(!Z8ProjectRemoval.hasWork()&&Z8Guest.calls==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"Late cancellation releases active work without touching files");
                            break;
                        }
                        case "all-requested-guard": {
                            TerminalSession a=session(service,"owned-target"),b=session(service,"owned-other");service.stopRequested=true;
                            Result project=new Result();Z8ProjectRemoval.begin(service,"owned-target",project);
                            Result session=new Result();Z8ProjectRemoval.stopSession(service,a,session);
                            check(project.calls==1&&project.error!=null&&session.calls==1&&session.error!=null,"Requested global stop rejects new individual stop/deletion work");
                            check(Z8ProjectProcesses.captured==0&&Z8ProjectProcesses.calls==0&&service.acquisitionCount==0&&!Z8ProjectRemoval.hasWork(),"Flag-rejected actions cannot signal, acquire, or register work");
                            Z8ProjectRemoval.stopAllSessions(service,result);Handler.next();a.running=false;b.running=false;Handler.advance(100);
                            check(result.calls==1&&result.error==null&&service.sessions.isEmpty()&&service.acquisitionCount==1,"The global stop request itself remains permitted");
                            check(Z8Guest.calls==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"Global stop request only closes sessions");
                            break;
                        }
                        case "all-empty": {
                            service.stopRequested=true;Z8ProjectProcesses.entered=new CountDownLatch(1);Z8ProjectProcesses.release=new CountDownLatch(1);
                            Z8ProjectRemoval.stopAllSessions(service,result);
                            check(Z8ProjectProcesses.entered.await(3,TimeUnit.SECONDS),"Empty whole-service verifier entered");
                            check(Z8ProjectRemoval.hasWork()&&service.acquisitionCount==1&&result.calls==0,"Empty snapshot still holds execution lease until main completion");
                            Result duplicate=new Result();Z8ProjectRemoval.stopAllSessions(service,duplicate);
                            check(duplicate.calls==1&&duplicate.error!=null&&Z8ProjectProcesses.calls==1&&Z8ProjectProcesses.captured==0,"Empty snapshot rejects duplicate while completion is pending");
                            Z8ProjectProcesses.release.countDown();Runnable completed=Handler.take();
                            check(Z8ProjectRemoval.hasWork(),"Empty stop retains lease across worker-to-main handoff");completed.run();
                            check(result.calls==1&&result.error==null&&!Z8ProjectRemoval.hasWork()&&service.notifications==1,"Empty stop completes and updates notification once");
                            check(service.removed==0&&Z8Guest.calls==0&&exists(service,"owned-target")&&exists(service,"owned-other"),"Empty stop never removes wrappers or files");
                            break;
                        }
                        default:throw new AssertionError("Unknown probe");
                    }
                    System.out.println("PASS removal "+scenario);
                } finally {
                    Z8Guest.release.countDown();Z8ProjectProcesses.release.countDown();
                    java.lang.reflect.Field field=Z8ProjectRemoval.class.getDeclaredField("IO");field.setAccessible(true);
                    ((ExecutorService)field.get(null)).shutdownNow();
                }
            }
        }''',
}
