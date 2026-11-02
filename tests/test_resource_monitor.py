"""Exercise the real resource sampler math and lifecycle with public-API Android stubs."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ResourceMonitorTests(unittest.TestCase):
    def test_measurement_scope_and_visibility_lifecycle(self):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not java:
            self.skipTest('A JDK is required')
        with tempfile.TemporaryDirectory(prefix='z8-resource-monitor-') as temporary:
            directory = Path(temporary)
            sources = []
            for name, code in STUBS.items():
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(code)
                sources.append(str(path))
            real = ROOT / 'overlay/app/src/main/java/com/termux/app/Z8ResourceMonitor.java'
            compile_result = subprocess.run([javac, '-encoding', 'UTF-8', '-d', str(directory), str(real), *sources],
                                            capture_output=True, text=True, timeout=45)
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout + compile_result.stderr)
            result = subprocess.run([java, '-cp', str(directory), 'com.termux.app.ResourceProbe'],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS: truthful app resources and visibility lifecycle', result.stdout)


STUBS = {
    'android/os/Looper.java': '''package android.os; public class Looper {
        public static Looper getMainLooper(){return new Looper();}
    }''',
    'android/os/Handler.java': '''package android.os; import java.util.concurrent.*;
        public class Handler {
            public static final BlockingQueue<Runnable> queue=new LinkedBlockingQueue<>();
            public Handler(Looper looper){}
            public boolean post(Runnable value){queue.add(value);return true;}
            public void removeCallbacksAndMessages(Object token){queue.clear();}
            public static Runnable next()throws Exception {
                Runnable value=queue.poll(5,TimeUnit.SECONDS);
                if(value==null)throw new AssertionError("No measurement was posted");
                return value;
            }
        }
    ''',
    'android/os/Process.java': '''package android.os; public class Process {
        public static final int THREAD_PRIORITY_BACKGROUND=10; private static long cpu;
        public static void setThreadPriority(int priority){}
        public static synchronized long getElapsedCpuTime(){cpu+=100;return cpu;}
    }''',
    'android/os/SystemClock.java': '''package android.os; public class SystemClock {
        private static long now; public static synchronized long elapsedRealtime(){now+=1000;return now;}
    }''',
    'android/os/Debug.java': '''package android.os; public class Debug {
        public static volatile boolean failed;public static volatile int calls;
        public static long getPss(){calls++;if(failed)throw new SecurityException("unavailable");return 125000;}
    }''',
    'com/termux/app/ResourceProbe.java': '''package com.termux.app;
        import android.os.Handler;import android.os.Debug;import java.util.*;
        public class ResourceProbe {
            static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
            static void percent(double expected,long previousCpu,long previousWall,long cpu,long wall,int cores) {
                double actual=Z8ResourceMonitor.cpuPercent(previousCpu,previousWall,cpu,wall,cores);
                check(Math.abs(expected-actual)<0.000001,"CPU capacity calculation: "+actual);
            }
            public static void main(String[] args)throws Exception {
                percent(25,0,0,1000,1000,4);
                percent(100,0,0,4000,1000,4);
                percent(0,100,1000,100,4000,8);
                percent(12.5,100,1000,1100,3000,4);
                percent(100,0,0,9000,1000,4);
                check(Double.isNaN(Z8ResourceMonitor.cpuPercent(-1,-1,1000,1000,4)),"initial CPU is unknown");
                check(Double.isNaN(Z8ResourceMonitor.cpuPercent(200,1000,100,2000,4)),"counter reset is unknown");
                check(Double.isNaN(Z8ResourceMonitor.cpuPercent(100,1000,200,1000,4)),"zero interval is unknown");
                check(Double.isNaN(Z8ResourceMonitor.cpuPercent(100,2000,200,1000,4)),"time reversal is unknown");
                check(Double.isNaN(Z8ResourceMonitor.cpuPercent(100,1000,200,2000,0)),"invalid core count is unknown");
                check(Z8ResourceMonitor.memoryLabel(-1).equals("— MB"),"unknown memory never appears as zero");
                check(Z8ResourceMonitor.memoryLabel(125000).equals("128 MB"),"KiB converted to decimal MB");
                check(Z8ResourceMonitor.memoryLabel(1250000).equals("1.3 GB"),"decimal GB");
                check(Z8ResourceMonitor.memoryRefreshDue(-1,0),"first visible PSS sample is immediate");
                check(!Z8ResourceMonitor.memoryRefreshDue(0,3000),"CPU refresh does not repeat PSS work");
                check(!Z8ResourceMonitor.memoryRefreshDue(0,14999),"memory reuse has a bounded window");
                check(Z8ResourceMonitor.memoryRefreshDue(0,15000),"memory refresh at 15 seconds");
                check(Z8ResourceMonitor.memoryRefreshDue(2000,1000),"clock reversal refreshes memory");
                check(Z8ResourceMonitor.Snapshot.pending().label().equals("앱  CPU —%  RAM — MB"),"scope visible before sampling");
                List<Z8ResourceMonitor.Snapshot> samples=new ArrayList<>();
                Z8ResourceMonitor monitor=new Z8ResourceMonitor(samples::add);
                monitor.start();monitor.start();
                Runnable stale=Handler.next();
                monitor.stop();stale.run();
                check(samples.isEmpty(),"stop rejects an in-flight UI delivery");
                monitor.start();Handler.next().run();
                check(samples.size()==1&&Double.isNaN(samples.get(0).cpuPercent),"resume resets CPU baseline");
                check(samples.get(0).pssKb==125000,"PSS uses the platform result");
                int memoryCalls=Debug.calls;
                Handler.next().run();
                check(samples.size()==2&&!Double.isNaN(samples.get(1).cpuPercent),"second sample measures elapsed CPU");
                check(Debug.calls==memoryCalls,"frequent CPU updates reuse recent PSS");
                check(samples.get(1).description().contains("하위 프로세스는 포함하지 않습니다"),"child exclusion is explicit");
                check(samples.get(1).description().contains("15초"),"memory freshness cadence is disclosed");
                monitor.stop();Debug.failed=true;
                monitor.start();Handler.next().run();
                check(samples.get(2).pssKb==-1,"memory API failure remains unknown");
                check(Debug.calls==memoryCalls+1,"resume requests a fresh memory measurement");
                monitor.stop();Debug.failed=false;
                monitor.start();Runnable delayed=Handler.next();
                Thread.sleep(Z8ResourceMonitor.INTERVAL_SECONDS*1000+250);
                check(Handler.queue.isEmpty(),"a busy UI has at most one pending resource delivery");
                delayed.run();
                check(samples.size()==4&&!Double.isNaN(samples.get(3).cpuPercent),"pending delivery is replaced by latest CPU sample");
                monitor.close();monitor.close();monitor.start();
                check(Handler.queue.isEmpty(),"closed monitor cannot restart");
                System.out.println("PASS: truthful app resources and visibility lifecycle");
            }
        }
    ''',
}


if __name__ == '__main__':
    unittest.main()
