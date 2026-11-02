"""Execute production process verification with deterministic process identities and owned /proc fixtures.

Never signals a host/device process: Android's Os.kill stub fails if reached.
The production parser, matching, tracee traversal, cancellation and exit verification run.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProjectProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-owned-process-tests-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        sources = []
        for name, source in STUBS.items():
            path = cls.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
            sources.append(str(path))
        probe = cls.directory / 'ProcessProbe.java'
        probe.write_text(PROBE)
        actual = ROOT / 'overlay/app/src/main/java/com/termux/app/Z8ProjectProcesses.java'
        compiled = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(cls.directory),
                                   str(actual), str(probe), *sources], capture_output=True, text=True, timeout=30)
        if compiled.returncode:
            raise AssertionError(compiled.stdout + compiled.stderr)

    def probe(self, scenario):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.ProcessProbe',
                                 scenario, str(self.directory / scenario)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS processes ' + scenario, result.stdout)

    def test_waits_for_daemon_and_descendant_after_tracer_exits(self):
        self.probe('cleanup')

    def test_tracks_tracees_added_or_reusing_a_pid_during_cleanup(self):
        self.probe('late')

    def test_never_signals_or_adopts_children_of_reused_root(self):
        self.probe('reuse')

    def test_timeout_preserves_files_without_killing_the_tracer_forcibly(self):
        self.probe('timeout')

    def test_retry_after_pty_exit_still_verifies_remembered_tracees(self):
        self.probe('retry')

    def test_validates_all_project_identities_before_any_signal(self):
        self.probe('validation')

    def test_cancellation_and_interrupt_preserve_files(self):
        self.probe('cancel')

    def test_unreadable_process_information_fails_closed(self):
        self.probe('errors')

    def test_normal_device_shell_keeps_existing_stop_method(self):
        self.probe('native')

    def test_stat_and_status_parser_rejects_incomplete_identity(self):
        self.probe('parser')

    def test_production_proc_reader_matches_executable_and_project_rootfs(self):
        self.probe('filesystem')

    def test_runtime_upgrade_rejects_any_live_owned_child_without_signalling(self):
        self.probe('upgrade-idle')

    def test_preparation_capture_requires_owned_direct_child_and_fixed_wrapper(self):
        self.probe('preparation-capture')

    def test_preparation_stops_verified_proot_and_waits_for_tracees(self):
        self.probe('preparation-stop')

    def test_preparation_observation_retains_orphans_after_tracer_exit(self):
        self.probe('preparation-observe')

    def test_preparation_failed_cleanup_can_be_retried_without_forced_kill(self):
        self.probe('preparation-retry')

    def test_preparation_cleanup_finishes_and_restores_interruption(self):
        self.probe('preparation-interrupt')


STUBS = {
    'android/os/SystemClock.java': '''package android.os;public class SystemClock {
        public static long elapsedRealtime(){return System.nanoTime()/1000000;}}''',
    'android/os/Process.java': '''package android.os;public class Process {public static int myUid(){return 10001;}public static int myPid(){return 55;}}''',
    'android/system/ErrnoException.java': '''package android.system;public class ErrnoException extends Exception {
        public final int errno;public ErrnoException(String message,int errno){super(message);this.errno=errno;}}''',
    'android/system/StructStat.java': '''package android.system;public class StructStat {
        public final int st_uid;public StructStat(int uid){st_uid=uid;}}''',
    'android/system/OsConstants.java': '''package android.system;public class OsConstants {
        public static final int ENOENT=2,ESRCH=3,SIGQUIT=3; }''',
    'android/system/Os.java': '''package android.system;public class Os {
        public static StructStat stat(String path)throws ErrnoException {
            if(!java.nio.file.Files.exists(java.nio.file.Paths.get(path)))throw new ErrnoException("gone",2);
            return new StructStat(path.endsWith("/900")?20000:10001);}
        public static void kill(int pid,int signal)throws ErrnoException{throw new AssertionError("Tests must never signal a process");}}''',
    'com/termux/shared/termux/TermuxConstants.java': '''package com.termux.shared.termux;public class TermuxConstants {
        public static String TERMUX_PREFIX_DIR_PATH;}''',
    'com/termux/terminal/TerminalSession.java': '''package com.termux.terminal;public class TerminalSession {
        public volatile int pid;public int finished;public TerminalSession(int pid){this.pid=pid;}
        public int getPid(){return pid;}public void finishIfRunning(){finished++;}}''',
    'com/termux/app/Z8SessionOrigin.java': '''package com.termux.app;import com.termux.terminal.TerminalSession;
        public class Z8SessionOrigin {public String projectId;public static Z8SessionOrigin of(TerminalSession s){return null;}}''',
}

PROBE = r'''package com.termux.app;
import com.termux.terminal.TerminalSession;
import com.termux.shared.termux.TermuxConstants;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class ProcessProbe {
    static int checks;
    static void check(boolean value,String message){checks++;if(!value)throw new AssertionError(message);}
    interface Run {void run()throws Exception;}
    static void fails(Run operation,String fragment)throws Exception {
        try{operation.run();throw new AssertionError("Expected failure: "+fragment);}
        catch(IOException expected){check(expected.getMessage().contains(fragment),"Useful failure: "+expected.getMessage());}
    }
    static Z8ProjectProcesses.ProcessRecord p(int pid,int parent,int tracer,long started,char state){
        return new Z8ProjectProcesses.ProcessRecord(pid,10001,parent,tracer,started,state);}
    static Z8ProjectProcesses.ProcessRecord p(int pid,int parent,int tracer){return p(pid,parent,tracer,pid,'S');}
    static Map<Integer,Z8ProjectProcesses.ProcessRecord> frame(Z8ProjectProcesses.ProcessRecord... ps){
        Map<Integer,Z8ProjectProcesses.ProcessRecord> result=new LinkedHashMap<>();for(var p:ps)result.put(p.pid,p);return result;}
    static Z8ProjectProcesses.Target target(int pid,String project){return new Z8ProjectProcesses.Target(new TerminalSession(pid),pid,project);}
    static class Fake implements Z8ProjectProcesses.Access {
        List<Map<Integer,Z8ProjectProcesses.ProcessRecord>> frames=new ArrayList<>();
        Map<Integer,Z8ProjectProcesses.ProcessRecord> current=new LinkedHashMap<>();
        List<Integer> quit=new ArrayList<>();Set<Integer> invalid=new HashSet<>();
        int scans,pauses,failScan;long clock;boolean shell,interruptOnce;Z8ProjectProcesses.ProcessRecord replaceOnRead;AtomicBoolean cancel;
        Fake(Map<Integer,Z8ProjectProcesses.ProcessRecord>... values){frames.addAll(Arrays.asList(values));}
        public Map<Integer,Z8ProjectProcesses.ProcessRecord> scan()throws IOException{
            if(++scans==failScan)throw new IOException("unreadable owned process");
            current=frames.get(Math.min(scans-1,frames.size()-1));return current;}
        public Z8ProjectProcesses.ProcessRecord read(int pid){
            if(replaceOnRead!=null&&replaceOnRead.pid==pid)return replaceOnRead;return current.get(pid);}
        public boolean isProot(int pid,String project){return !invalid.contains(pid);}
        public boolean isPreparationShell(int pid,String marker,String script){return shell;}
        public void quit(int pid){quit.add(pid);}
        public long now(){return clock;}
        public void pause()throws InterruptedException{pauses++;clock+=1000;if(cancel!=null)cancel.set(true);
            if(interruptOnce){interruptOnce=false;throw new InterruptedException("fixture cancellation");}}
    }
    static void stop(Fake fake,Z8ProjectProcesses.Target... targets)throws Exception {
        Z8ProjectProcesses.stopAndVerify(Arrays.asList(targets),()->false,fake);
    }
    static String stat(int pid,int parent,long started,String comm){
        String[] values=new String[20];Arrays.fill(values,"0");values[0]="S";values[1]=""+parent;values[19]=""+started;
        return pid+" ("+comm+") "+String.join(" ",values)+" 4096 0 0\n";
    }
    static String status(int tracer){return "Name:\tfixture\nState:\tS (sleeping)\nUid:\t10001 10001 10001 10001\nTracerPid:\t"+tracer+"\n";}
    public static void main(String[] args)throws Exception {
        String scenario=args[0];
        switch(scenario){
            case "upgrade-idle": {
                Fake idle=new Fake(frame(p(55,1,0),p(100,55,0,100,'Z')));
                Z8ProjectProcesses.requireRuntimeIdle(idle,55);
                check(idle.quit.isEmpty(),"Idle check never signals a process");
                Fake live=new Fake(frame(p(55,1,0),p(100,55,0)));
                fails(()->Z8ProjectProcesses.requireRuntimeIdle(live,55),"stop running tasks");
                check(live.quit.isEmpty(),"Active host shell or PRoot is preserved");
                Fake unreadable=new Fake(frame()); unreadable.failScan=1;
                fails(()->Z8ProjectProcesses.requireRuntimeIdle(unreadable,55),"unreadable");break;
            }
            case "preparation-capture": {
                Fake fake=new Fake(frame(p(100,55,0)));fake.current=fake.frames.get(0);fake.shell=true;
                var handle=Z8ProjectProcesses.capturePreparation(100,"owned","marker","script",10001,55,fake);
                check(handle.root.pid==100&&handle.root.started==100,"Capture stable child identity before exec");
                fails(()->Z8ProjectProcesses.capturePreparation(100,"owned","marker","script",20000,55,fake),"owner");
                fails(()->Z8ProjectProcesses.capturePreparation(100,"owned","marker","script",10001,99,fake),"owner");
                fake.shell=false;
                fails(()->Z8ProjectProcesses.capturePreparation(100,"owned","marker","script",10001,55,fake),"owner");
                break;
            }
            case "preparation-stop": {
                var root=p(100,55,0);var child=p(200,1,100);
                var handle=new Z8ProjectProcesses.PreparationTarget(root,"owned","marker","script");
                Fake fake=new Fake(frame(root,child),frame(child),frame());
                Z8ProjectProcesses.stopPreparation(handle,fake);
                check(fake.quit.equals(Arrays.asList(100))&&fake.pauses==1,"Quit only verified PRoot then verify tracee exit");
                Fake invalid=new Fake(frame(root));invalid.invalid.add(100);
                fails(()->Z8ProjectProcesses.stopPreparation(handle,invalid),"executable");
                check(invalid.quit.isEmpty(),"No signal to unexpected exec target");
                break;
            }
            case "preparation-observe": {
                var root=p(100,55,0);var child=p(200,1,100);
                var handle=new Z8ProjectProcesses.PreparationTarget(root,"owned","marker","script");
                Z8ProjectProcesses.observePreparation(handle,new Fake(frame(root,child)));
                Fake fake=new Fake(frame(p(200,1,0)),frame(p(200,1,0)),frame());
                Z8ProjectProcesses.stopPreparation(handle,fake);
                check(fake.quit.isEmpty()&&fake.pauses==1,"Prior observations retain untraced orphan after root exit");
                break;
            }
            case "preparation-retry": {
                var root=p(100,55,0);var child=p(200,1,100);
                var handle=new Z8ProjectProcesses.PreparationTarget(root,"owned","marker","script");
                Fake failure=new Fake(frame(root,child),frame(child));
                fails(()->Z8ProjectProcesses.stopPreparation(handle,failure),"files were kept");
                check(failure.quit.equals(Arrays.asList(100)),"No forced signal after timeout");
                Fake retry=new Fake(frame(p(200,1,0)));
                fails(()->Z8ProjectProcesses.stopPreparation(handle,retry),"files were kept");
                check(retry.quit.isEmpty(),"Retried cleanup preserves remembered identity");
                Z8ProjectProcesses.stopPreparation(handle,new Fake(frame()));
                break;
            }
            case "preparation-interrupt": {
                var root=p(100,55,0);var handle=new Z8ProjectProcesses.PreparationTarget(root,"owned","marker","script");
                Fake fake=new Fake(frame(root),frame(root),frame());fake.interruptOnce=true;
                Thread.currentThread().interrupt();
                try {Z8ProjectProcesses.stopPreparation(handle,fake);
                    check(Thread.currentThread().isInterrupted(),"Cleanup restores prior or arriving cancellation");}
                finally {Thread.interrupted();}
                check(fake.quit.size()==1&&fake.pauses==1,"Cancellation cannot abandon verification");
                break;
            }
            case "cleanup": {
                var root=p(100,1,0);var daemon=p(200,1,100);var descendant=p(201,200,0);var other=p(300,1,0);
                Fake fake=new Fake(frame(root,daemon,descendant,other),frame(daemon,descendant,other),frame(other));
                stop(fake,target(100,"owned-project"));
                check(fake.quit.equals(Arrays.asList(100)),"Only selected PRoot receives SIGQUIT");
                check(fake.pauses==1&&fake.scans==3,"Wait for detached daemon and recursive child after PRoot is gone");
                check(fake.current.containsKey(300),"Other project process is untouched");break;
            }
            case "late": {
                var root=p(100,1,0);var original=p(200,100,100);var reused=p(200,1,100,999,'S');var late=p(210,1,100);
                Fake fake=new Fake(frame(root,original),frame(root,reused,late),frame(reused,late),frame());
                stop(fake,target(100,"owned-project"));
                check(fake.pauses==2,"Wait for both a new tracee and reused child identity observed before tracer exits");
                check(fake.quit.equals(Arrays.asList(100)),"Never independently SIGKILL guest children");break;
            }
            case "reuse": {
                var root=p(100,1,0);var child=p(200,100,100);var replacement=p(100,1,0,999,'S');
                Fake fake=new Fake(frame(root,child),frame(replacement,p(300,100,0)));fake.replaceOnRead=replacement;
                stop(fake,target(100,"owned-project"));
                check(fake.quit.isEmpty(),"Do not signal a reused numeric PID");
                check(fake.pauses==0,"Do not adopt replacement process descendants");break;
            }
            case "timeout": {
                var root=p(100,1,0);var child=p(200,1,100);
                Fake fake=new Fake(frame(root,child),frame(child));
                fails(()->stop(fake,target(100,"owned-project")),"files were kept");
                check(fake.quit.equals(Arrays.asList(100))&&fake.pauses==10,"Bounded wait; no SIGKILL fallback");break;
            }
            case "retry": {
                var root=p(100,1,0);var child=p(200,1,100);var terminal=new TerminalSession(100);
                var first=new Z8ProjectProcesses.Target(terminal,100,"owned");
                Fake failure=new Fake(frame(root,child),frame(child));
                fails(()->stop(failure,first),"files were kept");
                check(Z8ProjectProcesses.hasUnverified(terminal),"Retain identity evidence after failed stop");
                terminal.pid=-1;
                var retry=new Z8ProjectProcesses.Target(terminal,-1,"owned");
                var orphan=p(200,1,0);var grandchild=p(210,200,0);
                Fake stillAlive=new Fake(frame(orphan,grandchild));
                fails(()->stop(stillAlive,retry),"files were kept");
                check(stillAlive.quit.isEmpty()&&Z8ProjectProcesses.hasUnverified(terminal),"Finished PTY cannot bypass its surviving untraced child; never signal reused or absent root");
                Fake childExited=new Fake(frame(grandchild));
                fails(()->stop(childExited,retry),"files were kept");
                check(Z8ProjectProcesses.hasUnverified(terminal),"Retry also remembers a descendant discovered after the tracer exited");
                stop(new Fake(frame()),retry);
                check(!Z8ProjectProcesses.hasUnverified(terminal),"Release wrapper protection only after all remembered identities exit");
                break;
            }
            case "validation": {
                Fake fake=new Fake(frame(p(100,1,0),p(110,1,0)));fake.invalid.add(110);
                fails(()->stop(fake,target(100,"owned"),target(110,"other")),"files were kept");
                check(fake.quit.isEmpty(),"Validate all project executable and rootfs identities before stopping any");
                var moved=target(100,"owned");moved.terminal.pid=999;
                fails(()->stop(new Fake(frame(p(100,1,0))),moved),"has changed");
                Fake foreign=new Fake(frame());foreign.replaceOnRead=p(100,1,0);
                fails(()->stop(foreign,target(100,"owned")),"owner");break;
            }
            case "cancel": {
                Fake fake=new Fake(frame(p(100,1,0)));AtomicBoolean cancelled=new AtomicBoolean(true);
                fails(()->Z8ProjectProcesses.stopAndVerify(Collections.emptyList(),cancelled::get,fake),"files were kept");
                check(fake.scans==0&&fake.quit.isEmpty(),"Service stop is observed even without PTYs");
                cancelled.set(false);fake.cancel=cancelled;
                fails(()->Z8ProjectProcesses.stopAndVerify(Arrays.asList(target(100,"owned")),cancelled::get,fake),"files were kept");
                check(fake.quit.size()==1&&fake.pauses==1,"Cancel bounded wait without fallback kill");
                try{Thread.currentThread().interrupt();fails(()->stop(fake,target(100,"owned")),"files were kept");}
                finally{Thread.interrupted();}break;
            }
            case "errors": {
                Fake before=new Fake(frame(p(100,1,0)));before.failScan=1;
                fails(()->stop(before,target(100,"owned")),"unreadable");check(before.quit.isEmpty(),"Unreadable preflight never signals");
                Fake after=new Fake(frame(p(100,1,0)));after.failScan=2;
                fails(()->stop(after,target(100,"owned")),"unreadable");check(after.quit.size()==1,"Unreadable verification is a failure after graceful signal");break;
            }
            case "native": {
                var nativeTarget=target(100,null);Fake fake=new Fake(frame(p(100,1,0),p(200,100,0)),frame(p(200,1,0)),frame());
                stop(fake,nativeTarget);
                check(nativeTarget.terminal.finished==1&&fake.quit.isEmpty(),"Native shell uses existing finishIfRunning method");
                check(fake.pauses==1,"Native shell descendants are still verified");
                Fake zombies=new Fake(frame(p(100,1,0,100,'Z')),frame());stop(zombies,target(100,"owned"));
                check(zombies.quit.isEmpty(),"Exited zombie process is never signalled");break;
            }
            case "parser": {
                var record=Z8ProjectProcesses.parse(123,stat(123,1,987654321,"sh ) tricky ( name"),status(456));
                check(record.pid==123&&record.parent==1&&record.tracer==456&&record.uid==10001&&record.started==987654321,"Parse final comm delimiter and exact starttime field");
                check(record.alive()&&record.same(p(123,9,0,987654321,'Z')),"Identity is uid + pid + starttime, independent of parent/state");
                fails(()->Z8ProjectProcesses.parse(124,stat(123,1,1,"sh"),status(0)),"files were kept");
                fails(()->Z8ProjectProcesses.parse(123,"123 (sh) S 1",status(0)),"files were kept");
                fails(()->Z8ProjectProcesses.parse(123,stat(123,1,1,"sh"),"Uid: 10001\n"),"files were kept");
                fails(()->Z8ProjectProcesses.parse(123,stat(123,-1,1,"sh"),status(0)),"files were kept");
                fails(()->Z8ProjectProcesses.parse(123,stat(123,1,-1,"sh"),status(0)),"files were kept");break;
            }
            case "filesystem": {
                Path fixture=Paths.get(args[1]);Path files=fixture.resolve("files");Path prefix=files.resolve("usr");
                TermuxConstants.TERMUX_PREFIX_DIR_PATH=prefix.toString();Files.createDirectories(prefix.resolve("bin"));
                Path proot=Files.write(prefix.resolve("bin/proot"),new byte[]{1});
                Path rootfs=files.resolve("z8/environments/owned/rootfs");Files.createDirectories(rootfs);
                Path otherRoot=files.resolve("z8/environments/other/rootfs");Files.createDirectories(otherRoot);
                Path alias=fixture.resolve("alias");Files.createSymbolicLink(alias,files);
                Path proc=fixture.resolve("proc");Path process=proc.resolve("100");Files.createDirectories(process);
                Files.writeString(process.resolve("stat"),stat(100,1,100,"proot"));Files.writeString(process.resolve("status"),status(0));
                Files.createSymbolicLink(process.resolve("exe"),proot);
                Files.writeString(process.resolve("cmdline"),"proot\0--kill-on-exit\0-r\0"+alias.resolve("z8/environments/owned/rootfs")+"\0/bin/bash\0");
                var access=new Z8ProjectProcesses.ProcAccess(proc,10001);
                check(access.read(100).started==100&&access.read(999)==null,"Read real filesystem records; absent pid is gone");
                check(access.isProot(100,"owned"),"Executable and project rootfs inode match through app path alias");
                check(!access.isProot(100,"other"),"Reject another project's rootfs even with same PRoot binary");
                Files.createDirectories(proc.resolve("900"));Files.createDirectories(proc.resolve("not-a-pid"));
                check(access.scan().size()==1,"Skip foreign UID and nonnumeric proc entries");
                Files.writeString(process.resolve("cmdline"),"proot\0/bin/bash\0-r\0relative\0");
                check(!access.isProot(100,"owned"),"Reject a relative rootfs path");
                Path linker=Files.write(fixture.resolve("linker64"),new byte[]{2});
                Files.delete(process.resolve("exe")); Files.createSymbolicLink(process.resolve("exe"),linker);
                Files.writeString(process.resolve("cmdline"),"linker64\0"+proot+"\0--kill-on-exit\0-r\0"+rootfs+"\0/bin/bash\0");
                Files.writeString(process.resolve("maps"),"1000-2000 r-xp 00000000 00:00 1 "+proot+"\n");
                var linked=new Z8ProjectProcesses.ProcAccess(proc,10001,linker);
                check(linked.isProot(100,"owned"),"System linker and executable PRoot mapping identify target36 process");
                check(!linked.isProot(100,"other"),"Linker launched PRoot still requires the selected project");
                Files.writeString(process.resolve("maps"),"1000-2000 r--p 00000000 00:00 1 "+proot+"\n");
                check(!linked.isProot(100,"owned"),"Loading a data file is not executable PRoot identity");
                Files.writeString(process.resolve("maps"),"1000-2000 r-xp 00000000 00:00 1 "+linker+"\n");
                check(!linked.isProot(100,"owned"),"Other linker clients cannot impersonate PRoot with argv");
                Files.writeString(process.resolve("status"),"Uid: 10001\n");
                fails(()->access.scan(),"files were kept");
                Files.write(process.resolve("stat"),new byte[65537]);fails(()->access.read(100),"files were kept");break;
            }
            default:throw new AssertionError(scenario);
        }
        System.out.println("PASS processes "+scenario+" checks="+checks);
    }
}
'''
