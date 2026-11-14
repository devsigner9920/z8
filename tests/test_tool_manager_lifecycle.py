"""Selected-tool service/network ownership with deterministic Android boundaries."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ToolManagerLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').exists() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').exists() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('Requires configured JDK')
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-tool-manager-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        sources = []
        for name, value in STUBS.items():
            path = cls.directory / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(value); sources.append(str(path))
        app = ROOT / 'overlay/app/src/main/java/com/termux/app'
        result = subprocess.run([javac, '-encoding', 'UTF-8', '-d', str(cls.directory),
            str(app / 'Z8ToolManager.java'), str(app / 'Z8ToolCatalog.java'), str(app / 'Z8Text.java'), *sources], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, case):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.ToolManagerProbe', case], capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS ' + case)

    def test_worker_and_network_wait_for_accepted_data_sync_service(self): self.probe('promotion_wait')
    def test_preparation_timeout_closes_proxy_and_preserves_busy_until_cleanup(self): self.probe('timeout')

    def test_exact_selected_argv_and_invalid_versions_rejected(self): self.probe('argv')
    def test_bind_failure_releases_pending_operation(self): self.probe('bind')
    def test_foreground_acquisition_failure_releases_pending_operation(self): self.probe('fgs')
    def test_notification_failure_releases_pending_operation(self): self.probe('notification')
    def test_network_callback_failure_releases_pending_operation(self): self.probe('registration')
    def test_metered_requires_specific_consent_and_explicit_retry(self): self.probe('metered')
    def test_unmetered_cellular_is_allowed(self): self.probe('cellular')
    def test_network_loss_closes_proxy_before_interrupt(self): self.probe('network')
    def test_stopped_service_retains_busy_until_worker_cleanup_finishes(self): self.probe('cleanup')
    def test_failed_operation_is_not_replayed_without_user_retry(self): self.probe('failure')
    def test_deleting_project_and_template_are_refused_before_binding(self): self.probe('deleting')
    def test_journal_failure_has_no_binding_or_execution(self): self.probe('journal')
    def test_saved_running_operation_is_failed_not_automatically_replayed(self): self.probe('saved')
    def test_stale_disconnection_cannot_erase_new_operation_state(self): self.probe('stale')


STUBS = {
    'com/termux/app/Z8PreparationService.java': 'package com.termux.app; public class Z8PreparationService {public interface Interrupted{void stopped(String message);}public static Interrupted cancelled;public static Runnable ready;public static boolean defer;public static void begin(TermuxService s,String id,Runnable r,Interrupted c){if(s.failAcquire)throw new IllegalStateException("FGS rejected");s.acquired++; cancelled=c;ready=r;if(!defer)r.run();}public static void finish(TermuxService s,String id){}public static void refresh(TermuxService s){}public static void releaseOwner(TermuxService s){}}',
'android/os/Looper.java': '''package android.os;public class Looper{static final Thread OWNER=Thread.currentThread();static final Looper MAIN=new Looper();public static Looper getMainLooper(){return MAIN;}public static Looper myLooper(){return Thread.currentThread()==OWNER?MAIN:null;}}''',
'android/os/Handler.java': '''package android.os;import java.util.*;import java.util.concurrent.*;public class Handler{
public static final BlockingQueue<Runnable> posted=new LinkedBlockingQueue<>();public static final List<Runnable> delayed=Collections.synchronizedList(new ArrayList<>());
public Handler(Looper l){}public boolean post(Runnable r){posted.add(r);return true;}public boolean postDelayed(Runnable r,long ms){delayed.add(r);return true;}
public static void next()throws Exception{Runnable r=posted.poll(3,TimeUnit.SECONDS);if(r==null)throw new AssertionError("No completion");r.run();}
public static void flush(){Runnable r;while((r=posted.poll())!=null)r.run();List<Runnable> copy; synchronized(delayed){copy=new ArrayList<>(delayed);delayed.clear();}for(Runnable x:copy)x.run();}}
''',
'android/os/IBinder.java': '''package android.os;public interface IBinder{}''',
'android/content/ComponentName.java': '''package android.content;public class ComponentName{}''',
'android/content/Intent.java': '''package android.content;public class Intent{public Intent(Context c,Class<?> type){}}''',
'android/content/ServiceConnection.java': '''package android.content;import android.os.IBinder;public interface ServiceConnection{void onServiceConnected(ComponentName n,IBinder b);void onServiceDisconnected(ComponentName n);default void onBindingDied(ComponentName n){}default void onNullBinding(ComponentName n){}}''',
'android/content/SharedPreferences.java': '''package android.content;import java.util.*;public class SharedPreferences{
public static boolean failWrites;private final Map<String,Object> values=new HashMap<>();public synchronized String getString(String k,String d){return (String)values.getOrDefault(k,d);}
public synchronized boolean getBoolean(String k,boolean d){return (Boolean)values.getOrDefault(k,d);}public Editor edit(){return new Editor();}
public class Editor{Map<String,Object> change=new HashMap<>();public Editor putString(String k,String v){change.put(k,v);return this;}public Editor putBoolean(String k,boolean v){change.put(k,v);return this;}public boolean commit(){if(failWrites)return false;synchronized(SharedPreferences.this){values.putAll(change);}return true;}}}
''',
'android/content/Context.java': '''package android.content;import android.net.*;import java.util.*;public class Context{
public static final int MODE_PRIVATE=0,BIND_AUTO_CREATE=1;public static final ConnectivityManager NETWORK=new ConnectivityManager();public static final Map<String,SharedPreferences> STORE=new HashMap<>();
public boolean bindResult=true;public int binds,unbinds;public ServiceConnection last;
public Context getApplicationContext(){return this;}public <T>T getSystemService(Class<T> type){return type.cast(NETWORK);}
public SharedPreferences getSharedPreferences(String name,int mode){synchronized(STORE){return STORE.computeIfAbsent(name,k->new SharedPreferences());}}
public boolean bindService(Intent i,ServiceConnection c,int flags){binds++;last=c;return bindResult;}public void unbindService(ServiceConnection c){unbinds++;}
}
''',
'android/net/Network.java': '''package android.net;public class Network{final String id;public Network(String v){id=v;}public boolean equals(Object v){return v instanceof Network&&id.equals(((Network)v).id);}public int hashCode(){return id.hashCode();}}''',
'android/net/NetworkCapabilities.java': '''package android.net;public class NetworkCapabilities{
public static final int NET_CAPABILITY_INTERNET=1,NET_CAPABILITY_VALIDATED=2,NET_CAPABILITY_NOT_METERED=3,TRANSPORT_CELLULAR=4;
public boolean internet=true,validated=true,notMetered=true,cellular;public boolean hasCapability(int key){return key==1?internet:key==2?validated:notMetered;}
public boolean hasTransport(int key){return key==TRANSPORT_CELLULAR&&cellular;}}
''',
'android/net/ConnectivityManager.java': '''package android.net;public class ConnectivityManager{
public volatile Network network=new Network("test");public final NetworkCapabilities caps=new NetworkCapabilities();public NetworkCallback callback;public boolean failRegistration;public int registered,unregistered;
public Network getActiveNetwork(){return network;}public NetworkCapabilities getNetworkCapabilities(Network n){return network==null?null:caps;}
public void registerDefaultNetworkCallback(NetworkCallback c){if(failRegistration)throw new IllegalStateException("registration failed");callback=c;registered++;}
public void unregisterNetworkCallback(NetworkCallback c){if(callback==c)callback=null;unregistered++;}
public static class NetworkCallback{public void onAvailable(Network n){}public void onLost(Network n){}public void onCapabilitiesChanged(Network n,NetworkCapabilities c){}}}
''',
'com/termux/app/TermuxService.java': '''package com.termux.app;public class TermuxService extends android.content.Context{
public boolean stopping,failAcquire;public int acquired,updates;public boolean wantsToStop(){return stopping;}public boolean z8IsStopRequested(){return stopping;}
public void z8AcquireExecution(){if(failAcquire)throw new IllegalStateException("FGS rejected");acquired++;}public void updateNotification(){updates++;}
public static class LocalBinder implements android.os.IBinder{public final TermuxService service;public LocalBinder(TermuxService s){service=s;}}}
''',
'com/termux/app/Z8EnvironmentTemplate.java': '''package com.termux.app;public class Z8EnvironmentTemplate{public static final String ID="00000000-0000-4000-8000-000000000008";public static boolean isTemplate(String id){return ID.equals(id);}}''',
'com/termux/app/Z8ProjectRemoval.java': '''package com.termux.app;public class Z8ProjectRemoval{public static boolean deleting;public static boolean isDeleting(String id){return deleting;}}''',
'com/termux/app/Z8Guest.java': '''package com.termux.app;public class Z8Guest{public static int invalidated;public static void invalidateReadiness(String id){invalidated++;}}''',
'com/termux/app/Z8Projects.java': '''package com.termux.app;public class Z8Projects{public Z8Projects(android.content.Context c){}public void open(String id){}}''',
'com/termux/app/Z8PreparationNotification.java': '''package com.termux.app;public class Z8PreparationNotification{
public static boolean failBegin,lastUpdate;public static String lastName,lastProject;public static int begins,finishes,waits;public static void beginTool(TermuxService s,String id,String project,String name,boolean update){if(failBegin)throw new IllegalStateException("notification failed");begins++;lastName=name;lastProject=project;lastUpdate=update;}
public static void progress(TermuxService s,String id,String stage,int percent,String message){}public static void finish(TermuxService s,String id,boolean good,String detail){finishes++;}public static void waiting(TermuxService s,String id){waits++;}}
''',
'com/termux/app/Z8SetupDownloadProxy.java': '''package com.termux.app;import java.util.*;import android.net.*;public class Z8SetupDownloadProxy{
public static final List<String> events=Collections.synchronizedList(new ArrayList<>());public static volatile Z8SetupDownloadProxy last;public volatile boolean closed;
public static Z8SetupDownloadProxy open(android.content.Context c,Network n){events.add("open");return last=new Z8SetupDownloadProxy();}
public void close(){closed=true;events.add("close");}public Map<String,String> environment(){return Collections.singletonMap("http_proxy","bound");}}
''',
'com/termux/app/Z8ProjectPreparation.java': '''package com.termux.app;import java.util.*;import java.util.concurrent.*;import java.util.concurrent.atomic.*;public class Z8ProjectPreparation{
public interface Progress{void update(String stage,int percent,String message);}public static final AtomicInteger calls=new AtomicInteger();
public static volatile CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1),cleanupEntered=new CountDownLatch(1),cleanupRelease=new CountDownLatch(0);
public static volatile boolean fail;public static String tool,version;public static boolean update;
public static void installTool(android.content.Context c,String project,String selected,boolean upgrading,String selectedVersion,Progress progress,Map<String,String> environment)throws Exception{
calls.incrementAndGet();tool=selected;version=selectedVersion;update=upgrading;if(!"bound".equals(environment.get("http_proxy")))throw new AssertionError("No bound download proxy");
progress.update("packages",30,"fixture");CountDownLatch done=release;entered.countDown();
try{if(!done.await(5,TimeUnit.SECONDS))throw new AssertionError("Not released");}
catch(InterruptedException stopped){Z8SetupDownloadProxy.events.add("interrupt");cleanupEntered.countDown();boolean finished=false;while(!finished){try{finished=cleanupRelease.await(5,TimeUnit.SECONDS);}catch(InterruptedException again){}}throw stopped;}
if(fail)throw new java.io.IOException("fixture failure");}
}
''',
'com/termux/app/ToolManagerProbe.java': r'''package com.termux.app;
import android.content.*;import android.net.*;import android.os.*;import java.util.*;import java.util.concurrent.*;
public class ToolManagerProbe{
static final String ID="11111111-1111-4111-8111-111111111111";
static void check(boolean value,String why){if(!value)throw new AssertionError(why);}static void eq(Object a,Object b){check(Objects.equals(a,b),a+" != "+b);}
static void await(CountDownLatch latch)throws Exception{check(latch.await(3,TimeUnit.SECONDS),"Latch timeout");}
interface Work{void run();}static void reject(Work work){try{work.run();}catch(IllegalArgumentException expected){return;}throw new AssertionError("Invalid argv accepted");}
static void connect(Context app,TermuxService service){app.last.onServiceConnected(new ComponentName(),new TermuxService.LocalBinder(service));}
static void start(Context app,TermuxService service){Z8ToolManager.start(app,ID,"node",true,"v24.22.3",false);connect(app,service);}
static void finish()throws Exception{Z8ProjectPreparation.release.countDown();while(Z8ToolManager.busy(ID))Handler.next();Handler.flush();}
static void resetOperation(){Z8ProjectPreparation.entered=new CountDownLatch(1);Z8ProjectPreparation.release=new CountDownLatch(1);}
public static void main(String[]args){try{run(args[0]);System.out.println("PASS "+args[0]);System.exit(0);}catch(Throwable error){error.printStackTrace();System.exit(1);}}
static void run(String which)throws Exception{
Context app=new Context();TermuxService service=new TermuxService();ConnectivityManager network=Context.NETWORK;
switch(which){
case "promotion_wait":{
Z8PreparationService.defer=true;start(app,service);eq(0,Z8ProjectPreparation.calls.get());eq(null,network.callback);eq(null,Z8SetupDownloadProxy.last);
Z8PreparationService.cancelled.stopped("Foreground preparation rejected");check(!Z8ToolManager.busy(ID),"No stranded pending worker");eq(Z8ToolManager.Phase.FAILED,Z8ToolManager.state(app,ID).phase);
Handler.flush();eq(0,Z8ProjectPreparation.calls.get());Z8PreparationService.defer=false;start(app,service);await(Z8ProjectPreparation.entered);finish();break;}
case "timeout":{
Z8ProjectPreparation.cleanupRelease=new CountDownLatch(1);start(app,service);await(Z8ProjectPreparation.entered);Z8PreparationService.cancelled.stopped("Android preparation time limit");await(Z8ProjectPreparation.cleanupEntered);
check(Z8ToolManager.busy(ID),"Timed-out worker still protects files until verified cleanup");check(!Z8ToolManager.hasWork(service),"Foreground lease released");
List<String> events=Z8SetupDownloadProxy.events;check(events.indexOf("close")>=0&&events.indexOf("close")<events.indexOf("interrupt"),"Download proxy closed before interruption");
Z8ToolManager.start(app,ID,"git",false,null,false);eq(1,Z8ProjectPreparation.calls.get());
Z8ProjectPreparation.cleanupRelease.countDown();while(Z8ToolManager.busy(ID))Handler.next();eq(Z8ToolManager.Phase.FAILED,Z8ToolManager.state(app,ID).phase);Handler.flush();eq(1,Z8ProjectPreparation.calls.get());
resetOperation();start(app,service);await(Z8ProjectPreparation.entered);finish();eq(2,Z8ProjectPreparation.calls.get());break;}
case "argv":{
eq(Arrays.asList(Z8ToolManager.command("codex",true,"0.169.0")),Arrays.asList("/bin/bash","/usr/local/lib/z8/tool-manager.sh","--update","codex","--version","0.169.0"));
eq(4,Z8ToolManager.command("git",false,null).length);
for(String[] bad:new String[][]{{"node","v26.0.0"},{"node","v24.01.0"},{"codex","9999999.1.0"},{"git","1.2.3"},{"claude","1.2.3;id"},{"codex","1.2.3-beta"},{"bad",""}})reject(()->Z8ToolManager.command(bad[0],true,bad[1]));
reject(()->Z8ToolManager.command("codex",false,"0.169.0"));reject(()->Z8ToolManager.command("codex",true,""));
check(!Z8ToolManager.validCommand(new String[]{"/bin/bash","-c","echo BAD","codex"}),"No arbitrary shell");
check(!Z8ToolManager.validCommand(new String[]{"/bin/bash","/usr/local/lib/z8/tool-manager.sh","--apply","node","--version",""}),"No empty selected version");break;}
case "bind":{
app.bindResult=false;Z8ToolManager.start(app,ID,"git",false,null,false);check(!Z8ToolManager.busy(ID),"Failed bind clears pending");eq(Z8ToolManager.Phase.FAILED,Z8ToolManager.state(app,ID).phase);eq(0,Z8ProjectPreparation.calls.get());
app.bindResult=true;start(app,service);await(Z8ProjectPreparation.entered);finish();eq(Z8ToolManager.Phase.READY,Z8ToolManager.state(app,ID).phase);break;}
case "fgs":case "notification":case "registration":{
if(which.equals("fgs"))service.failAcquire=true;if(which.equals("notification"))Z8PreparationNotification.failBegin=true;if(which.equals("registration"))network.failRegistration=true;
start(app,service);check(!Z8ToolManager.busy(ID),"Setup failure clears pending");eq(Z8ToolManager.Phase.FAILED,Z8ToolManager.state(app,ID).phase);eq(0,Z8ProjectPreparation.calls.get());eq(1,app.unbinds);eq(null,network.callback);
service.failAcquire=false;Z8PreparationNotification.failBegin=false;network.failRegistration=false;start(app,service);await(Z8ProjectPreparation.entered);finish();eq(1,Z8ProjectPreparation.calls.get());break;}
case "metered":{
network.caps.notMetered=false;start(app,service);eq(Z8ToolManager.Phase.WAITING_NETWORK,Z8ToolManager.state(app,ID).phase);check(!Z8ToolManager.busy(ID),"Metered waits without worker");eq(0,Z8ProjectPreparation.calls.get());eq(0,service.acquired);
network.caps.notMetered=true;Handler.flush();eq(0,Z8ProjectPreparation.calls.get());network.caps.notMetered=false;
Z8ToolManager.start(app,ID,"node",true,"v24.22.3",true);connect(app,service);await(Z8ProjectPreparation.entered);finish();eq(Z8ToolManager.Phase.READY,Z8ToolManager.state(app,ID).phase);break;}
case "cellular":{
network.caps.cellular=true;network.caps.notMetered=true;start(app,service);await(Z8ProjectPreparation.entered);eq("node",Z8ProjectPreparation.tool);eq("v24.22.3",Z8ProjectPreparation.version);check(Z8ProjectPreparation.update,"Selected update flag");eq("Node.js 24 LTS",Z8PreparationNotification.lastName);eq(ID,Z8PreparationNotification.lastProject);eq(true,Z8PreparationNotification.lastUpdate);finish();eq(1,Z8PreparationNotification.finishes);eq(0,Z8PreparationNotification.waits);eq(Z8ToolManager.Phase.READY,Z8ToolManager.state(app,ID).phase);break;}
case "network":{
start(app,service);await(Z8ProjectPreparation.entered);network.callback.onLost(network.network);await(Z8ProjectPreparation.cleanupEntered);
List<String> events=Z8SetupDownloadProxy.events;check(events.indexOf("close")>=0&&events.indexOf("close")<events.indexOf("interrupt"),"Close network before worker interrupt");
while(Z8ToolManager.busy(ID))Handler.next();eq(Z8ToolManager.Phase.WAITING_NETWORK,Z8ToolManager.state(app,ID).phase);eq(1,Z8PreparationNotification.waits);eq(0,Z8PreparationNotification.finishes);eq(1,network.unregistered);Handler.flush();eq(1,Z8ProjectPreparation.calls.get());break;}
case "cleanup":{
Z8ProjectPreparation.cleanupRelease=new CountDownLatch(1);start(app,service);await(Z8ProjectPreparation.entered);Z8ToolManager.stop(service);await(Z8ProjectPreparation.cleanupEntered);
check(Z8ToolManager.busy(ID),"Project remains busy while old installer cleanup owns it");eq(false,Z8ToolManager.hasWork(service));eq(1,app.unbinds);
Context replacement=new Context();Z8ToolManager.start(replacement,ID,"git",false,null,false);eq(0,replacement.binds);eq(1,Z8ProjectPreparation.calls.get());
Z8ProjectPreparation.cleanupRelease.countDown();while(Z8ToolManager.busy(ID))Handler.next();eq(Z8ToolManager.Phase.FAILED,Z8ToolManager.state(app,ID).phase);
resetOperation();start(replacement,new TermuxService());await(Z8ProjectPreparation.entered);finish();eq(2,Z8ProjectPreparation.calls.get());break;}
case "failure":{
Z8ProjectPreparation.fail=true;start(app,service);await(Z8ProjectPreparation.entered);finish();eq(Z8ToolManager.Phase.FAILED,Z8ToolManager.state(app,ID).phase);
for(int i=0;i<20;i++){Z8ToolManager.state(app,ID);Handler.flush();}eq(1,Z8ProjectPreparation.calls.get());eq(1,app.binds);
Z8ProjectPreparation.fail=false;resetOperation();start(app,service);await(Z8ProjectPreparation.entered);finish();eq(2,Z8ProjectPreparation.calls.get());eq(Z8ToolManager.Phase.READY,Z8ToolManager.state(app,ID).phase);break;}
case "deleting":{
Z8ProjectRemoval.deleting=true;Z8ToolManager.start(app,ID,"git",false,null,false);eq(0,app.binds);check(!Z8ToolManager.busy(ID),"Deletion gate has no job");eq(Z8ToolManager.Phase.FAILED,Z8ToolManager.state(app,ID).phase);
reject(()->Z8ToolManager.start(app,Z8EnvironmentTemplate.ID,"git",false,null,false));eq(0,Z8ProjectPreparation.calls.get());break;}
case "journal":{
SharedPreferences.failWrites=true;Z8ToolManager.start(app,ID,"git",false,null,false);eq(0,app.binds);eq(0,Z8ProjectPreparation.calls.get());check(!Z8ToolManager.busy(ID),"No job without durable acceptance");eq(Z8ToolManager.Phase.FAILED,Z8ToolManager.state(app,ID).phase);break;}
case "saved":{
app.getSharedPreferences("z8.tool-operation."+ID,0).edit().putString("tool","node").putString("phase","RUNNING").putString("version","v24.22.3").commit();
eq(Z8ToolManager.Phase.FAILED,Z8ToolManager.state(app,ID).phase);eq(0,app.binds);eq(0,Z8ProjectPreparation.calls.get());check(!Z8ToolManager.busy(ID),"Saved interrupted job does not run");break;}
case "stale":{
start(app,service);ServiceConnection old=app.last;await(Z8ProjectPreparation.entered);finish();resetOperation();
Context replacement=new Context();TermuxService fresh=new TermuxService();start(replacement,fresh);await(Z8ProjectPreparation.entered);
old.onServiceDisconnected(new ComponentName());check(Z8ToolManager.busy(ID),"Old callback preserves current job");
check(Z8ToolManager.hasWork(fresh),"New service still owns current work");eq(Z8ToolManager.Phase.RUNNING,Z8ToolManager.state(replacement,ID).phase);
eq(0,replacement.unbinds);finish();eq(Z8ToolManager.Phase.READY,Z8ToolManager.state(replacement,ID).phase);eq(2,Z8ProjectPreparation.calls.get());break;}
default:throw new AssertionError("Unknown case");}
}}
'''
}
