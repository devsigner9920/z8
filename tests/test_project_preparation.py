"""Run the real preparation pipeline against small, local subprocess fixtures.

Bootstrap/rootfs adapters are stubbed; no emulator, guest image, network, or package
manager is accessed. The actual ProcessBuilder, output handling and cancellation run.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProjectPreparationTests(unittest.TestCase):
    def test_pipeline_processes_progress_and_cancellation(self):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not java:
            self.skipTest('A JDK is required')
        with tempfile.TemporaryDirectory(prefix='z8 preparation fixture ') as temporary:
            directory = Path(temporary).resolve()
            sources = []
            for name, code in STUBS.items():
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(code)
                sources.append(str(path))
            real = ROOT / 'overlay/app/src/main/java/com/termux/app/Z8ProjectPreparation.java'
            compiled = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(directory), str(real), *sources],
                                      capture_output=True, text=True, timeout=45)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            environment = os.environ.copy()
            environment['Z8_MUST_NOT_LEAK'] = 'parent-only-sentinel'
            result = subprocess.run([java, '-cp', str(directory), 'com.termux.app.PreparationProbe', str(directory)],
                                    capture_output=True, text=True, env=environment, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS: preparation subprocess lifecycle', result.stdout)


STUBS = {
    'com/termux/app/Z8EnvironmentTemplate.java': '''package com.termux.app;import android.content.Context;import java.io.IOException;
        public class Z8EnvironmentTemplate {public static boolean isTemplate(String id){return false;}public static void project(Context c,String id)throws IOException{new Z8Projects(c).open(id);}}''',
    'com/termux/app/Z8PreparationProcess.java': '''package com.termux.app;
        import android.content.Context;import java.io.*;import java.util.*;import java.util.concurrent.*;
        public class Z8PreparationProcess implements AutoCloseable {
            private final Process process; private Z8PreparationProcess(Process p){process=p;}
            static Z8PreparationProcess start(Context c,String id,List<String>argv,File cwd,Map<String,String>env)throws IOException {
                ProcessBuilder b=new ProcessBuilder(argv).directory(cwd).redirectErrorStream(true);
                b.environment().clear();b.environment().putAll(env);Process p=b.start();p.getOutputStream().close();return new Z8PreparationProcess(p);
            }
            InputStream output(){return process.getInputStream();}
            boolean waitFor(long time,TimeUnit unit)throws InterruptedException{return process.waitFor(time,unit);}
            int exitValue(){return process.exitValue();}
            public void close()throws IOException {boolean interrupted=Thread.interrupted();try{
                if(process.isAlive()){process.destroy();if(!process.waitFor(3,TimeUnit.SECONDS))throw new IOException("Host fixture failed to stop");}
                process.getInputStream().close();
            }catch(InterruptedException e){interrupted=true;throw new IOException(e);}finally{if(interrupted)Thread.currentThread().interrupt();}}
        }''',
    'android/content/Context.java': '''package android.content; import java.io.File;
        public class Context {public final File root;public Context(File root){this.root=root;}
            public File getCacheDir(){return new File(root,"cache");}}
    ''',
    'com/termux/app/Z8Projects.java': '''package com.termux.app;import android.content.Context;import java.io.IOException;
        public class Z8Projects {public Z8Projects(Context c){}public void open(String id)throws IOException {
            if(!"project".equals(id))throw new IOException("Missing project");}}
    ''',
    'com/termux/app/Z8Bootstrap.java': '''package com.termux.app;import android.content.Context;import java.io.IOException;
        public class Z8Bootstrap {public interface Progress{void update(int percent,String message);}
            static boolean installed,fail;static int calls,installs;
            public static void ensure(Context context,Progress progress)throws IOException {
                calls++;if(fail)throw new IOException("Bootstrap fixture failure");
                if(installed)return;installs++;progress.update(30,"bootstrap fixture");installed=true;
            }}
    ''',
    'com/termux/app/Z8Guest.java': '''package com.termux.app;import android.content.Context;import java.io.*;import java.nio.file.*;
        public class Z8Guest {public interface Progress{void update(int percent,String message);}
            static boolean installed,fail;static int calls,installs,actions,invalidations;
            public static void ensureRootfs(Context context,String id,Progress progress)throws IOException {
                calls++;if(fail)throw new IOException("Rootfs fixture failure");
                if(installed)return;installs++;progress.update(50,"rootfs fixture");installed=true;
            }
            public static boolean standardProfilePrepared(Context context,String id) {
                try{return Files.readString(new File(context.root,"receipt").toPath()).equals("z8-tools-v2");}
                catch(IOException error){return false;}
            }
            public static Launch actionCommand(Context context,String id,String cwd,String action) {
                if(cwd!=null||!"setup-tools".equals(action))throw new AssertionError("Wrong setup entrypoint");
                actions++;return new Launch(context);
            }
            public static void invalidateReadiness(String id){invalidations++;}
            public static class Launch {public String executable="/usr/bin/env";public String[]arguments;public String workingDirectory;public int commandOffset=0;
                Launch(Context context){workingDirectory=context.root.getAbsolutePath();arguments=new String[]{"/bin/sh",new File(context.root,"fixture.sh").getAbsolutePath(),workingDirectory};}}
        }
    ''',
    'com/termux/app/PreparationProbe.java': r'''package com.termux.app;
        import android.content.Context;import java.io.*;import java.nio.file.*;import java.util.*;import java.util.concurrent.atomic.AtomicReference;
        public class PreparationProbe {
            static Context context;
            static List<String> messages=Collections.synchronizedList(new ArrayList<>());
            static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
            static Path path(String name){return new File(context.root,name).toPath();}
            static void script(String body)throws Exception{Files.writeString(path("fixture.sh"),"#!/bin/sh\n"+body);}
            static void reset()throws Exception {
                for(String name:List.of("receipt","pid","terminated","path","tmp"))Files.deleteIfExists(path(name));
                messages.clear();Z8Bootstrap.installed=Z8Bootstrap.fail=Z8Guest.installed=Z8Guest.fail=false;
                Z8Bootstrap.calls=Z8Bootstrap.installs=Z8Guest.calls=Z8Guest.installs=Z8Guest.actions=Z8Guest.invalidations=0;
            }
            static void run(String id)throws Exception {
                Z8ProjectPreparation.run(context,id,(stage,percent,message)->{
                    check(percent==-1||(percent>=0&&percent<=100),"Invalid progress: "+percent);
                    check(List.of("bootstrap","rootfs","tools").contains(stage),"Unknown progress stage");
                    if(stage.equals("tools"))check(percent==-1,"Tool installation must not invent a percentage");
                    messages.add(stage+":"+percent+":"+message);
                });
            }
            static IOException failure()throws Exception {
                try{run("project");throw new AssertionError("Expected preparation failure");}
                catch(IOException expected){return expected;}
            }
            static void awaitFile(String name)throws Exception {
                long until=System.nanoTime()+5_000_000_000L;
                while(!Files.exists(path(name))&&System.nanoTime()<until)Thread.sleep(10);
                check(Files.exists(path(name)),"Missing fixture handshake: "+name);
            }
            public static void main(String[]args)throws Exception {
                Path root=Files.createDirectories(Path.of(args[0],"workspace with spaces")).toRealPath();
                context=new Context(root.toFile());Files.createDirectories(context.getCacheDir().toPath());

                reset();script("exit 99\n");
                try{run("missing");throw new AssertionError("Invalid project accepted");}
                catch(IOException expected){check(expected.getMessage().contains("Missing project"),"Project validation runs first");}
                check(Z8Bootstrap.calls==0&&Z8Guest.actions==0,"Invalid project does not install or execute");

                reset();Z8Bootstrap.installed=Z8Guest.installed=true;Files.writeString(path("receipt"),"z8-tools-v2");
                run("project");
                check(Z8Bootstrap.calls==1&&Z8Guest.calls==1,"Warm adapters still validate existing environment");
                check(Z8Bootstrap.installs==0&&Z8Guest.installs==0&&Z8Guest.actions==0,"Warm environment does not reinstall or start a setup process");
                check(Z8Guest.invalidations==0,"Warm fast path avoids extra tool work");

                reset();Z8Bootstrap.fail=true;
                check(failure().getMessage().contains("Bootstrap fixture failure"),"Bootstrap failure propagated");
                check(Z8Guest.calls==0&&Z8Guest.actions==0,"Bootstrap failure prevents guest work");
                reset();Z8Guest.fail=true;
                check(failure().getMessage().contains("Rootfs fixture failure"),"Rootfs failure propagated");
                check(Z8Guest.actions==0,"Rootfs failure prevents package installation");

                reset();script("[ \"${Z8_MUST_NOT_LEAK+x}\" != x ] || exit 91\n"
                    +"[ \"$PWD\" = \"$1\" ] || exit 92\n"
                    +"printf '%s' \"$PATH\" > \"$1/path\"\n"
                    +"printf '%s' \"$PROOT_TMP_DIR\" > \"$1/tmp\"\n"
                    +"if read payload; then exit 93; fi\n"
                    +"printf 'Z8_SETUP:packages\\nZ8_SETUP:unknown\\nprefix Z8_SETUP:node\\nZ8_SETUP:node\\nZ8_SETUP:verify\\n'\n"
                    +"printf z8-tools-v2 > \"$1/receipt\"\n");
                run("project");
                check(Z8Bootstrap.installs==1&&Z8Guest.installs==1&&Z8Guest.actions==1,"Cold path executes each phase once");
                check(Files.readString(path("path")).equals("/system/bin"),"Parent PATH is not inherited");
                check(Files.readString(path("tmp")).equals(context.getCacheDir().getAbsolutePath()),"PRoot cache is explicit");
                check(Z8Guest.invalidations==1,"Successful receipt invalidates cached readiness");
                List<String> toolMessages=new ArrayList<>();for(String message:messages)if(message.startsWith("tools:"))toolMessages.add(message);
                check(toolMessages.equals(List.of("tools:-1:Install developer tools","tools:-1:Installing Python, Git and developer tools","tools:-1:Installing Node.js and npm","tools:-1:Verifying installation")),"Only known exact stage markers produce progress: "+toolMessages);

                reset();script("printf z8-tools-v2 > \"$1/receipt\"\nprintf 'failure detail\\n' >&2\nexit 7\n");
                IOException exitError=failure();
                check(exitError.getMessage().contains("(7)")&&exitError.getMessage().contains("failure detail"),"Nonzero exit fails even with receipt and preserves stderr");
                check(Z8Guest.invalidations==0,"Failure does not mark readiness successful");
                reset();script("exit 0\n");
                check(failure().getMessage().contains("(0)"),"Zero exit without receipt is not ready");

                reset();script("printf 'TAIL-START\\n'\ni=0\nwhile [ \"$i\" -lt 2500 ]; do printf 'fixture-output-line-%s\\n' \"$i\"; i=$((i+1)); done\nprintf 'TAIL-END\\n'\nexit 8\n");
                String detail=failure().getMessage();
                check(detail.contains("TAIL-END")&&!detail.contains("TAIL-START"),"Failure retains the newest diagnostic output");
                check(detail.length()<=16400,"Diagnostic tail is bounded");

                reset();script("i=0\nwhile [ \"$i\" -lt 5000 ]; do printf '"+"x".repeat(100)+"'; i=$((i+1)); done\n"
                    +"printf 'Z8_SETUP:verify\\nZ8_SETUP:node\\nLONG-END'\nexit 9\n");
                detail=failure().getMessage();
                check(detail.length()<=16400&&detail.endsWith("LONG-END"),"Long unterminated output is bounded and retains its final bytes");
                check(messages.stream().noneMatch(m->m.equals("tools:-1:Verifying installation")),"Overflowed lines cannot impersonate a stage marker");
                check(messages.stream().anyMatch(m->m.equals("tools:-1:Installing Node.js and npm")),"Stage recognition recovers at the next newline");

                reset();script("printf '%s' \"$https_proxy\" > \"$1/proxy\"\nprintf z8-tools-v2 > \"$1/receipt\"\n");
                String proxy="http://z8:literal$(touch forbidden)@127.0.0.1:3128";
                Z8ProjectPreparation.run(context,"project",(s,p,m)->{},Map.of("https_proxy",proxy,"NO_PROXY",""));
                check(Files.readString(path("proxy")).equals(proxy)&&!Files.exists(path("forbidden")),"Proxy assignments reach guest env literally without shell expansion");
                reset();script("printf '%s' \"$https_proxy\"\nexit 1\n");
                try {Z8ProjectPreparation.run(context,"project",(s,p,m)->{},Map.of("https_proxy",proxy));throw new AssertionError("Expected failure");}
                catch(IOException expected){check(!expected.getMessage().contains(proxy)&&expected.getMessage().contains("[installation connection]"),"Proxy credentials are redacted from diagnostics");}
                reset();script("exit 1\n");
                try {Z8ProjectPreparation.run(context,"project",(s,p,m)->{},Map.of("BASH_ENV","payload"));throw new AssertionError("Unexpected environment key");}
                catch(IOException expected){check(expected.getMessage().contains("connection settings"),"Only managed proxy keys are accepted");}

                reset();script("printf '%s' \"$$\" > \"$1/pid\"\ntrap 'printf \"Z8_SETUP:verify\\n\"; printf stopped > \"$1/terminated\"; exit 0' TERM\nwhile :; do :; done\n");
                AtomicReference<Throwable> caught=new AtomicReference<>();
                Thread runner=new Thread(()->{try{run("project");}catch(Throwable error){caught.set(error);}},"fixture-setup-worker");
                runner.start();awaitFile("pid");long pid=Long.parseLong(Files.readString(path("pid")));
                try {
                    runner.interrupt();runner.join(8000);
                    check(!runner.isAlive(),"Interrupted preparation worker terminates");
                    check(caught.get() instanceof InterruptedException,"Interruption remains a cancellation failure");
                    long until=System.nanoTime()+2_000_000_000L;
                    while(ProcessHandle.of(pid).map(ProcessHandle::isAlive).orElse(false)&&System.nanoTime()<until)Thread.sleep(10);
                    check(!ProcessHandle.of(pid).map(ProcessHandle::isAlive).orElse(false),"Setup subprocess is stopped on interruption");
                    check(Z8Guest.invalidations==0&&!Files.exists(path("receipt")),"Cancellation cannot mark setup ready");
                    until=System.nanoTime()+2_000_000_000L;
                    boolean reader;
                    do {reader=Thread.getAllStackTraces().keySet().stream().anyMatch(t->t.isAlive()&&t.getName().equals("z8-setup-output"));if(reader)Thread.sleep(10);}
                    while(reader&&System.nanoTime()<until);
                    check(!reader,"Output reader exits after cancellation");
                    check(messages.stream().noneMatch(m->m.equals("tools:-1:Verifying installation")),"Cancellation suppresses late progress from process cleanup");
                } finally {ProcessHandle.of(pid).ifPresent(process->{process.destroyForcibly();});runner.interrupt();}
                System.out.println("PASS: preparation subprocess lifecycle");
            }
        }
    ''',
}


if __name__ == '__main__':
    unittest.main()
