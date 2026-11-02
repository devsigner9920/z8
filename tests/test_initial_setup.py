"""Run the initial setup coordinator against deterministic lifecycle/network boundaries."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InitialSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temp = tempfile.TemporaryDirectory(prefix='z8-initial-setup-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        sources = []
        for name, source in STUBS.items():
            path = cls.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
            sources.append(str(path))
        probe = cls.directory / 'InitialSetupProbe.java'
        probe.write_text(PROBE)
        sources += [str(probe), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8InitialSetup.java')]
        result = subprocess.run([javac, '-encoding', 'UTF-8', '-d', str(cls.directory), *sources], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, case):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.InitialSetupProbe', case], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS ' + case)

    def test_no_consent_never_resumes_and_binding_does_not_install(self): self.probe('consent')
    def test_wifi_explicit_consent_creates_one_service_job_and_ready_template(self): self.probe('wifi')
    def test_metered_or_cellular_network_requires_explicit_permission(self): self.probe('cellular')
    def test_offline_and_unvalidated_networks_do_not_begin_download(self): self.probe('offline')
    def test_network_replacement_closes_bound_proxy_before_worker_interrupt(self): self.probe('network')
    def test_same_network_losing_unmetered_status_stops_download(self): self.probe('metered_change')
    def test_supplied_capabilities_stop_download_before_manager_snapshot_catches_up(self): self.probe('caps_event')
    def test_lost_bound_network_event_stops_download_before_default_snapshot_changes(self): self.probe('lost_event')
    def test_process_replacement_resumes_journal_only_after_old_cleanup(self): self.probe('replacement')
    def test_ready_template_and_receipt_bypass_download(self): self.probe('ready')
    def test_clean_failure_does_not_auto_retry_until_explicit_request(self): self.probe('failure')
    def test_listener_disposal_and_progress_burst_coalescing(self): self.probe('listeners')
    def test_consent_write_failure_has_no_network_or_installer_side_effect(self): self.probe('journal')
    def test_callback_registration_failure_releases_service_work(self): self.probe('callback_failure')
    def test_network_loss_after_verified_completion_keeps_ready_notification(self): self.probe('late_network')
    def test_offline_completed_template_repairs_interrupted_journal_without_network(self): self.probe('offline_ready')


STUBS = {
'android/os/Looper.java': r'''package android.os; public class Looper {
static final Looper MAIN=new Looper(); static final Thread OWNER=Thread.currentThread();
public static Looper getMainLooper(){return MAIN;} public static Looper myLooper(){return Thread.currentThread()==OWNER?MAIN:null;}}
''',
'android/os/Handler.java': r'''package android.os; import java.util.*; import java.util.concurrent.*;
public class Handler {
public static final BlockingQueue<Runnable> immediate=new LinkedBlockingQueue<>();
public static final List<Runnable> delayed=Collections.synchronizedList(new ArrayList<>());
public Handler(Looper l){} public boolean post(Runnable r){immediate.add(r);return true;}
public boolean postDelayed(Runnable r,long ms){delayed.add(r);return true;}
public static void flush(){Runnable r;while((r=immediate.poll())!=null)r.run();List<Runnable> todo; synchronized(delayed){todo=new ArrayList<>(delayed);delayed.clear();}for(Runnable callback:todo)callback.run();}
public static void next()throws Exception{Runnable r=immediate.poll(3,TimeUnit.SECONDS);if(r==null)throw new AssertionError("No completion callback");r.run();}
public static void awaitPost()throws Exception{Runnable r=immediate.poll(3,TimeUnit.SECONDS);if(r==null)throw new AssertionError("No worker finish posted");immediate.add(r);}
}
''',
'android/content/SharedPreferences.java': r'''package android.content; import java.util.*;
public class SharedPreferences {
public static boolean failWrites; private final Map<String,Object> values=new HashMap<>();
public synchronized boolean getBoolean(String k,boolean fallback){Object v=values.get(k);return v instanceof Boolean?(Boolean)v:fallback;}
public synchronized String getString(String k,String fallback){Object v=values.get(k);return v instanceof String?(String)v:fallback;}
public Editor edit(){return new Editor();}
public class Editor {final Map<String,Object> changed=new HashMap<>();public Editor putBoolean(String k,boolean v){changed.put(k,v);return this;}
public Editor putString(String k,String v){changed.put(k,v);return this;}public boolean commit(){if(failWrites)return false;synchronized(SharedPreferences.this){values.putAll(changed);}return true;}}
}
''',
'android/content/Context.java': r'''package android.content; import android.net.*; public class Context {
public static final int MODE_PRIVATE=0; public static final SharedPreferences PREFS=new SharedPreferences(); public static final ConnectivityManager NETWORK=new ConnectivityManager();
public <T>T getSystemService(Class<T> type){return type.cast(NETWORK);} public SharedPreferences getSharedPreferences(String name,int mode){return PREFS;}
public Context getApplicationContext(){return this;}}
''',
'android/net/Network.java': r'''package android.net; public class Network {
public final String id;public Network(String id){this.id=id;}@Override public boolean equals(Object o){return o instanceof Network&&id.equals(((Network)o).id);}@Override public int hashCode(){return id.hashCode();}}
''',
'android/net/NetworkCapabilities.java': r'''package android.net; public class NetworkCapabilities {
public static final int NET_CAPABILITY_INTERNET=1,NET_CAPABILITY_VALIDATED=2,TRANSPORT_CELLULAR=3,NET_CAPABILITY_NOT_METERED=4;
public boolean internet=true,validated=true,cellular,notMetered=true;
public boolean hasCapability(int kind){return kind==NET_CAPABILITY_INTERNET?internet:kind==NET_CAPABILITY_NOT_METERED?notMetered:validated;}
public boolean hasTransport(int kind){return kind==TRANSPORT_CELLULAR&&cellular;}}
''',
'android/net/ConnectivityManager.java': r'''package android.net; public class ConnectivityManager {
public volatile Network network=new Network("wifi");public final NetworkCapabilities caps=new NetworkCapabilities();public boolean metered,failRegistration;
public volatile NetworkCallback callback;public int registrations,unregistered;
public Network getActiveNetwork(){return network;}public NetworkCapabilities getNetworkCapabilities(Network n){return network==null?null:caps;}
public boolean isActiveNetworkMetered(){return metered;}public void registerDefaultNetworkCallback(NetworkCallback value){if(failRegistration)throw new IllegalStateException("registration failed");callback=value;registrations++;}
public void unregisterNetworkCallback(NetworkCallback value){if(callback==value)callback=null;unregistered++;}
public void changed(){NetworkCallback c=callback;if(c!=null)c.onCapabilitiesChanged(network,caps);}
public static class NetworkCallback{public void onAvailable(Network n){}public void onLost(Network n){}public void onCapabilitiesChanged(Network n,NetworkCapabilities c){}}
}
''',
'com/termux/app/TermuxService.java': r'''package com.termux.app; public class TermuxService extends android.content.Context {
public int acquired,updates;public boolean stopping;public void z8AcquireExecution(){acquired++;}public boolean wantsToStop(){return stopping;}
public boolean z8IsStopRequested(){return stopping;}public void updateNotification(){updates++;}}
''',
'com/termux/app/Z8EnvironmentTemplate.java': r'''package com.termux.app; public class Z8EnvironmentTemplate {
public static final String ID="template";public static volatile boolean ready;public static boolean isReady(android.content.Context c){return ready;}}
''',
'com/termux/app/Z8PreparationNotification.java': r'''package com.termux.app; public class Z8PreparationNotification {
public static int begins,finishes,waits,releases; public static void begin(TermuxService s,String id,String project,String name){begins++;}
public static void progress(TermuxService s,String id,String stage,int percent,String message){}
public static void finish(TermuxService s,String id,boolean success,String detail){finishes++;}
public static void waiting(TermuxService s,String id){waits++;}public static void releaseOwner(TermuxService s){releases++;}}
''',
'com/termux/app/Z8SetupDownloadProxy.java': r'''package com.termux.app; import java.util.*; import android.net.*;
public class Z8SetupDownloadProxy {
public static final List<String> events=Collections.synchronizedList(new ArrayList<>());public static volatile Z8SetupDownloadProxy last;
public final Network network;public boolean closed;Z8SetupDownloadProxy(Network n){network=n;}
public static Z8SetupDownloadProxy open(android.content.Context c,Network n){events.add("open");last=new Z8SetupDownloadProxy(n);return last;}
public void close(){closed=true;events.add("close");}public Map<String,String> environment(){return Collections.singletonMap("proxy","bound");}}
''',
'com/termux/app/Z8ProjectPreparation.java': r'''package com.termux.app;
import java.util.*;import java.util.concurrent.*;import java.util.concurrent.atomic.*;
public class Z8ProjectPreparation {
public interface Progress{void update(String stage,int percent,String message);}
public static volatile CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1),interrupted=new CountDownLatch(1),cleanupEntered=new CountDownLatch(1),cleanupRelease=new CountDownLatch(0);
public static final AtomicInteger calls=new AtomicInteger();public static volatile boolean fail;public static volatile int bursts=1;public static String project;
public static void run(android.content.Context c,String id,Progress p,Map<String,String> environment)throws Exception {
 calls.incrementAndGet();project=id;if(!"bound".equals(environment.get("proxy")))throw new AssertionError("missing proxy");
 CountDownLatch completion=release;
 for(int i=0;i<bursts;i++)p.update("tools",i,"step "+i);
 entered.countDown();
 try{if(!completion.await(5,TimeUnit.SECONDS))throw new AssertionError("Test worker was not released");}
 catch(InterruptedException e){Z8SetupDownloadProxy.events.add("interrupt");interrupted.countDown();cleanupEntered.countDown();cleanupRelease.await(5,TimeUnit.SECONDS);throw e;}
 if(fail)throw new java.io.IOException("fixture failure");Z8EnvironmentTemplate.ready=true;
}}
''',
}

PROBE = r'''
package com.termux.app;
import android.content.*;import android.net.*;import android.os.*;import java.util.*;import java.util.concurrent.*;
public class InitialSetupProbe {
static void eq(Object a,Object b){if(!Objects.equals(a,b))throw new AssertionError(a+" != "+b);}
static void await(CountDownLatch latch)throws Exception{if(!latch.await(3,TimeUnit.SECONDS))throw new AssertionError("Timed out");}
static void complete(TermuxService s)throws Exception{Z8ProjectPreparation.release.countDown();while(Z8InitialSetup.hasWork(s))Handler.next();Handler.flush();}
static void blocked(TermuxService s){eq(0,Z8ProjectPreparation.calls.get());eq(false,Z8InitialSetup.hasWork(s));eq(0,s.acquired);eq(Z8InitialSetup.Phase.WAITING_NETWORK,Z8InitialSetup.state(s).phase);}
public static void main(String[] args){try{run(args);}catch(Throwable failure){failure.printStackTrace();System.exit(1);}}
static void run(String[] args)throws Exception{
TermuxService service=new TermuxService();ConnectivityManager network=Context.NETWORK;SharedPreferences journal=Context.PREFS;
switch(args[0]){
case "consent":{
 journal.edit().putString("status","running").commit();Z8InitialSetup.resume(service);eq(0,Z8ProjectPreparation.calls.get());eq(false,Z8InitialSetup.hasConsent(service));eq(0,network.registrations);break;}
case "wifi":{
 eq(Z8InitialSetup.Phase.CONSENT,Z8InitialSetup.state(service).phase);Z8InitialSetup.request(service,false);await(Z8ProjectPreparation.entered);
 eq(true,Z8InitialSetup.hasConsent(service));eq(true,Z8InitialSetup.hasWork(service));eq(1,service.acquired);eq(1,Z8PreparationNotification.begins);
 eq(network.network,Z8SetupDownloadProxy.last.network);eq("template",Z8ProjectPreparation.project);eq("running",journal.getString("status",""));
 Z8InitialSetup.request(service,true);Z8InitialSetup.resume(service);eq(1,Z8ProjectPreparation.calls.get());
 complete(service);eq(true,Z8InitialSetup.isReady(service));eq(Z8InitialSetup.Phase.READY,Z8InitialSetup.state(service).phase);eq(1,network.unregistered);break;}
case "cellular":{
 network.caps.cellular=true;network.metered=false;Z8InitialSetup.request(service,false);blocked(service);
 Z8InitialSetup.request(service,true);await(Z8ProjectPreparation.entered);eq(true,Z8InitialSetup.state(service).allowMetered);complete(service);break;}
case "offline":{
 network.network=null;Z8InitialSetup.request(service,false);blocked(service);network.network=new Network("wifi");network.caps.validated=false;
 Z8InitialSetup.request(service,false);blocked(service);network.caps.validated=true;network.caps.notMetered=false;
 Z8InitialSetup.request(service,false);blocked(service);break;}
case "network":case "metered_change":case "caps_event":case "lost_event":{
 Z8InitialSetup.request(service,false);await(Z8ProjectPreparation.entered);
 if(args[0].equals("network")){network.network=new Network("cellular");network.callback.onAvailable(network.network);}
 else if(args[0].equals("caps_event")){NetworkCapabilities supplied=new NetworkCapabilities();supplied.notMetered=false;network.callback.onCapabilitiesChanged(network.network,supplied);}
 else if(args[0].equals("lost_event"))network.callback.onLost(network.network);
 else {network.caps.notMetered=false;network.changed();}
 await(Z8ProjectPreparation.interrupted);while(Z8InitialSetup.hasWork(service))Handler.next();
 eq(true,Z8SetupDownloadProxy.events.indexOf("close")<Z8SetupDownloadProxy.events.indexOf("interrupt"));
 eq(Z8InitialSetup.Phase.WAITING_NETWORK,Z8InitialSetup.state(service).phase);eq("waiting",journal.getString("status",""));
 eq(false,Z8EnvironmentTemplate.ready);eq(1,Z8PreparationNotification.waits);break;}
case "replacement":{
 Z8ProjectPreparation.cleanupRelease=new CountDownLatch(1);Z8InitialSetup.request(service,false);await(Z8ProjectPreparation.entered);
 Z8InitialSetup.stop(service);await(Z8ProjectPreparation.cleanupEntered);eq(false,Z8InitialSetup.hasWork(service));eq("running",journal.getString("status",""));
 TermuxService replacement=new TermuxService();Z8ProjectPreparation.entered=new CountDownLatch(1);Z8ProjectPreparation.release=new CountDownLatch(1);
 Z8InitialSetup.resume(replacement);eq(true,Z8InitialSetup.hasWork(replacement));eq(1,Z8ProjectPreparation.calls.get());
 Z8ProjectPreparation.cleanupRelease.countDown();await(Z8ProjectPreparation.entered);eq(2,Z8ProjectPreparation.calls.get());complete(replacement);
 eq(true,Z8InitialSetup.isReady(replacement));eq("template",Z8ProjectPreparation.project);eq(1,Z8PreparationNotification.releases);break;}
case "ready":{
 journal.edit().putBoolean("consent",true).putString("status","ready").commit();Z8EnvironmentTemplate.ready=true;
 Z8InitialSetup.request(service,true);Z8InitialSetup.resume(service);eq(0,Z8ProjectPreparation.calls.get());eq(true,Z8InitialSetup.isReady(service));break;}
case "failure":{
 Z8ProjectPreparation.fail=true;Z8InitialSetup.request(service,false);await(Z8ProjectPreparation.entered);complete(service);
 eq(Z8InitialSetup.Phase.FAILED,Z8InitialSetup.state(service).phase);eq("failed",journal.getString("status",""));Z8InitialSetup.resume(service);eq(1,Z8ProjectPreparation.calls.get());
 Z8ProjectPreparation.fail=false;Z8ProjectPreparation.entered=new CountDownLatch(1);Z8ProjectPreparation.release=new CountDownLatch(1);
 Z8InitialSetup.request(service,false);await(Z8ProjectPreparation.entered);complete(service);eq(true,Z8InitialSetup.isReady(service));break;}
case "listeners":{
 int[] notifications={0};Runnable listener=()->notifications[0]++;Z8InitialSetup.addListener(listener);Z8InitialSetup.addListener(listener);
 Z8ProjectPreparation.bursts=100;Z8InitialSetup.request(service,false);await(Z8ProjectPreparation.entered);eq(1,notifications[0]);eq(1,Handler.delayed.size());
 Handler.flush();eq(2,notifications[0]);eq(99,Z8InitialSetup.state(service).percent);Z8InitialSetup.removeListener(listener);complete(service);eq(2,notifications[0]);break;}
case "journal":{
 SharedPreferences.failWrites=true;Z8InitialSetup.request(service,false);eq(0,Z8ProjectPreparation.calls.get());eq(0,network.registrations);eq(0,service.acquired);
 eq(Z8InitialSetup.Phase.FAILED,Z8InitialSetup.state(service).phase);eq(false,Z8InitialSetup.hasConsent(service));break;}
case "callback_failure":{
 network.failRegistration=true;Z8InitialSetup.request(service,false);eq(false,Z8InitialSetup.hasWork(service));eq(0,Z8ProjectPreparation.calls.get());
 eq(Z8InitialSetup.Phase.FAILED,Z8InitialSetup.state(service).phase);eq(1,Z8PreparationNotification.finishes);break;}
case "late_network":{
 Z8InitialSetup.request(service,false);await(Z8ProjectPreparation.entered);Z8ProjectPreparation.release.countDown();Handler.awaitPost();
 eq(true,Z8InitialSetup.isReady(service));eq(true,Z8InitialSetup.hasWork(service));network.callback.onLost(network.network);
 while(Z8InitialSetup.hasWork(service))Handler.next();eq("ready",journal.getString("status",""));eq(Z8InitialSetup.Phase.READY,Z8InitialSetup.state(service).phase);
 eq(0,Z8PreparationNotification.waits);eq(1,Z8PreparationNotification.finishes);break;}
case "offline_ready":{
 journal.edit().putBoolean("consent",true).putString("status","running").putString("stage","tools").commit();
 Z8EnvironmentTemplate.ready=true;network.network=null;Z8InitialSetup.resume(service);eq("ready",journal.getString("status",""));
 eq(Z8InitialSetup.Phase.READY,Z8InitialSetup.state(service).phase);eq(0,Z8ProjectPreparation.calls.get());eq(0,network.registrations);eq(0,service.acquired);break;}
default:throw new AssertionError("Unknown case");}
System.out.println("PASS "+args[0]);System.exit(0);
}}
'''
