"""Actual fixed-shell handshake plus retained installer lifecycle behavior."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PreparationProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').exists() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').exists() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temp = tempfile.TemporaryDirectory(prefix='z8-preparation-process-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name).resolve()
        sources = []
        for name, source in STUBS.items():
            path = cls.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
            sources.append(str(path))
        actual = ROOT / 'overlay/app/src/main/java/com/termux/app/Z8PreparationProcess.java'
        result = subprocess.run([javac, '-encoding', 'UTF-8', '-d', str(cls.directory), str(actual), *sources],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def scenario(self, name):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.PreparationProcessProbe',
                                 name, str(self.directory / name)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_shell_waits_for_identity_capture_before_exec_and_preserves_output(self): self.scenario('gate')
    def test_wrong_acknowledgement_never_executes_guest(self): self.scenario('wrong-ack')
    def test_handshake_framing_rejects_malformed_or_oversized_pid(self): self.scenario('framing')
    def test_unverified_cleanup_blocks_other_installers_until_retry_succeeds(self): self.scenario('retained')
    def test_cleanup_restores_interruption_without_forced_process_kill(self): self.scenario('interrupt')


STUBS = {
    'com/termux/app/Z8RuntimeLauncher.java': 'package com.termux.app; public class Z8RuntimeLauncher {public static final Object EXECUTION_LOCK=new Object();}',
    'android/content/Context.java': 'package android.content; public class Context {}',
    'android/os/SystemClock.java': '''package android.os; public class SystemClock {
        public static long elapsedRealtime(){return System.nanoTime()/1000000;}}''',
    'com/termux/app/Z8ProjectProcesses.java': '''package com.termux.app; import java.io.*;
        final class Z8ProjectProcesses {
            static boolean reject; static int stops;
            static class PreparationTarget {}
            static PreparationTarget capturePreparation(int pid,String id,String marker,String wrapper){return new PreparationTarget();}
            static void observePreparation(PreparationTarget target){}
            static void stopPreparation(PreparationTarget target)throws IOException {stops++;if(reject)throw new IOException("tracee remains");}
        }''',
    'com/termux/app/PreparationProcessProbe.java': r'''package com.termux.app;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.lang.reflect.*;
public class PreparationProcessProbe {
    interface Run{void run()throws Exception;}
    static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
    static void deny(Run action)throws Exception{try{action.run();}catch(IOException expected){return;}throw new AssertionError("Must reject");}
    static class Child extends Process {
        int destroys;boolean interruptOnce;
        public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        public InputStream getInputStream(){return new ByteArrayInputStream(new byte[0]);}
        public InputStream getErrorStream(){return new ByteArrayInputStream(new byte[0]);}
        public int waitFor(){return 0;}
        public boolean waitFor(long timeout,TimeUnit unit)throws InterruptedException {
            if(interruptOnce){interruptOnce=false;throw new InterruptedException();}return true;}
        public int exitValue(){return 0;}
        public void destroy(){destroys++;}
        public Process destroyForcibly(){throw new AssertionError("Forced kill prohibited");}
    }
    static void field(Object owner,String name,Object value)throws Exception{
        Field field=owner.getClass().getDeclaredField(name);field.setAccessible(true);field.set(owner,value);}
    static Map<String,Z8PreparationProcess> outstanding()throws Exception{
        Field field=Z8PreparationProcess.class.getDeclaredField("OUTSTANDING");field.setAccessible(true);
        return (Map<String,Z8PreparationProcess>)field.get(null);}
    static Z8PreparationProcess owned(Child child)throws Exception {
        Constructor<Z8PreparationProcess> c=Z8PreparationProcess.class.getDeclaredConstructor(String.class,Process.class);c.setAccessible(true);
        Z8PreparationProcess handle=c.newInstance("owned-project",child);
        field(handle,"acknowledged",true);field(handle,"target",new Z8ProjectProcesses.PreparationTarget());
        outstanding().put("owned-project",handle);return handle;
    }
    public static void main(String[] args)throws Exception {
        Path root=Files.createDirectories(Path.of(args[1]));String marker="z8-setup-test-marker";
        switch(args[0]) {
        case "gate": case "wrong-ack": {
            Path executed=root.resolve("executed");
            Process process=new ProcessBuilder("/bin/sh","-c",Z8PreparationProcess.WRAPPER,marker,
                "/bin/sh","-c","printf guest > \"$1\"; printf 'Z8_SETUP:packages\\nremaining-output'; exit 7","guest",executed.toString()).start();
            try {
                int pid=Z8PreparationProcess.readHandshake(process.getInputStream(),marker);
                check(pid>0,"Real child PID handshake");
                check(!Files.exists(executed),"Guest cannot run before identity capture and ack");
                process.getOutputStream().write(((args[0].equals("gate")?marker:"wrong")+"\n").getBytes(StandardCharsets.UTF_8));
                process.getOutputStream().close();
                check(process.waitFor(5,TimeUnit.SECONDS),"Wrapper completes");
                String output=new String(process.getInputStream().readAllBytes(),StandardCharsets.UTF_8);
                if(args[0].equals("gate")){
                    check(process.exitValue()==7&&Files.readString(executed).equals("guest"),"Exact guest argv executes after ack");
                    check(output.equals("Z8_SETUP:packages\nremaining-output"),"First output byte after handshake retained");
                } else check(process.exitValue()==125&&!Files.exists(executed),"Wrong ack refuses guest exec");
            } finally {process.destroy();process.waitFor(3,TimeUnit.SECONDS);}
            break;
        }
        case "framing": {
            for(String line:new String[]{"other 123\n",marker+" 0\n",marker+" -1\n",marker+" 9999999999\n","x".repeat(161),""})
                deny(()->Z8PreparationProcess.readHandshake(new ByteArrayInputStream(line.getBytes(StandardCharsets.UTF_8)),marker));
            ByteArrayInputStream stream=new ByteArrayInputStream((marker+" 123\nnext").getBytes(StandardCharsets.UTF_8));
            check(Z8PreparationProcess.readHandshake(stream,marker)==123&&stream.read()=='n',"Framing never overreads output");
            break;
        }
        case "retained": {
            Child child=new Child();Z8PreparationProcess handle=owned(child);Z8ProjectProcesses.reject=true;
            deny(handle::close);check(outstanding().containsKey("owned-project"),"Unverified identity retained");
            // Must fail before attempting /system/bin/sh on this host, even when the next project differs.
            deny(()->Z8PreparationProcess.start(new android.content.Context(),"other-project",List.of("/fixture/proot"),root.toFile(),Map.of()));
            check(Z8ProjectProcesses.stops==2&&child.destroys==0,"Retry verifies retained tree and never kills acknowledged child directly");
            Z8ProjectProcesses.reject=false;handle.close();check(outstanding().isEmpty(),"Verified retry releases installation queue");
            break;
        }
        case "interrupt": {
            Child child=new Child();child.interruptOnce=true;Z8PreparationProcess handle=owned(child);
            Thread.currentThread().interrupt();
            try {handle.close();check(Thread.currentThread().isInterrupted(),"Interruption restored after bounded cleanup");}
            finally {Thread.interrupted();}
            check(child.destroys==0&&outstanding().isEmpty(),"Acknowledged process never uses destroy or force kill");
            break;
        }
        default:throw new AssertionError(args[0]);
        }
    }
}'''
}
