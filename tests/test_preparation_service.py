"""Run real finite-work service lease/timeout transitions with deterministic Android boundaries."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PreparationServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').exists() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').exists() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('JDK required')
        cls.temp = tempfile.TemporaryDirectory(prefix='z8-data-sync-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        sources = []
        for name, code in STUBS.items():
            p = cls.directory / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(code)
            sources.append(str(p))
        app = ROOT / 'overlay/app/src/main/java/com/termux/app'
        result = subprocess.run([javac, '-encoding', 'UTF-8', '-d', str(cls.directory), str(app / 'Z8PreparationService.java'), str(app / 'Z8Text.java'), *sources], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, case):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.PreparationServiceProbe', case], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS ' + case)

    def test_worker_waits_for_both_foreground_promotion_and_runtime_binding(self): self.probe('promotion')
    def test_bind_and_foreground_request_failures_release_lease(self): self.probe('request_failure')
    def test_android_promotion_rejection_cancels_without_starting_worker(self): self.probe('promotion_failure')
    def test_concurrent_jobs_only_use_data_sync_and_last_finish_stops(self): self.probe('concurrent')
    def test_timeout_demotes_before_callbacks_and_preserves_interactive_owner(self): self.probe('timeout')
    def test_user_stop_cancels_preparation_without_touching_terminals(self): self.probe('stop')
    def test_late_intent_cannot_replay_completed_work_or_stop_other_work(self): self.probe('stale')
    def test_ending_service_rejects_new_lease_without_stranding_it(self): self.probe('ending')
    def test_throwing_observer_cannot_prevent_other_jobs_cleanup(self): self.probe('throwing')
    def test_old_destroy_cannot_cancel_new_service_lease(self): self.probe('generation')
    def test_wrong_runtime_binding_and_disconnect_never_start_or_replay(self): self.probe('binding')
    def test_pre_api29_uses_untyped_foreground_without_special_use(self): self.probe('legacy')
    def test_owner_destruction_cancels_remaining_work_without_cancelling_other_owner(self): self.probe('owner')
    def test_file_task_keeps_its_truthful_deletion_notice_and_bounded_lifetime(self): self.probe('file_task')


STUBS = {
'android/os/Looper.java': '''package android.os; public class Looper {static final Looper MAIN=new Looper();public static Looper myLooper(){return MAIN;}public static Looper getMainLooper(){return MAIN;}}''',
'android/os/IBinder.java': 'package android.os;public interface IBinder {}',
'android/os/Build.java': 'package android.os;public class Build {public static class VERSION {public static int SDK_INT=35;}}',
'android/content/ComponentName.java': 'package android.content;public class ComponentName {}',
'android/content/ServiceConnection.java': '''package android.content;import android.os.IBinder;public interface ServiceConnection {void onServiceConnected(ComponentName n,IBinder b);void onServiceDisconnected(ComponentName n);default void onBindingDied(ComponentName n){}default void onNullBinding(ComponentName n){}}''',
'android/content/Intent.java': '''package android.content;import java.util.*;public class Intent {String action;Map<String,String> values=new HashMap<>();public Class<?> target;public Intent(Context c,Class<?> t){target=t;}public Intent putExtra(String k,String v){values.put(k,v);return this;}public String getStringExtra(String k){return values.get(k);}public Intent setAction(String a){action=a;return this;}public String getAction(){return action;}}''',
'android/content/Context.java': '''package android.content;import java.util.*;import android.app.*;public class Context {public static final int BIND_AUTO_CREATE=1;public boolean bindResult=true,failStart;public int unbinds;public final List<ServiceConnection> connections=new ArrayList<>();public final List<Intent> starts=new ArrayList<>();public final NotificationManager notifications=new NotificationManager();public Context getApplicationContext(){return this;}public boolean bindService(Intent i,ServiceConnection c,int f){if(bindResult)connections.add(c);return bindResult;}public void unbindService(ServiceConnection c){if(!connections.remove(c))throw new IllegalArgumentException();unbinds++;}public ComponentName startForegroundService(Intent i){if(failStart)throw new IllegalStateException("denied");starts.add(i);return new ComponentName();}public <T>T getSystemService(Class<T> c){return c.cast(notifications);}}''',
'android/content/pm/ServiceInfo.java': '''package android.content.pm;public class ServiceInfo {public static final int FOREGROUND_SERVICE_TYPE_DATA_SYNC=1,FOREGROUND_SERVICE_TYPE_SPECIAL_USE=1073741824;}''',
'android/app/Service.java': '''package android.app;import android.content.*;import android.os.*;public class Service extends Context {public static final int START_NOT_STICKY=2,STOP_FOREGROUND_REMOVE=1;public int foregroundCalls,stopForegroundCalls,stopCalls,lastType=-1;public boolean failForeground;public IBinder onBind(Intent i){return null;}public int onStartCommand(Intent i,int f,int id){return 2;}public void onTimeout(int id,int type){}public void onDestroy(){}public void startForeground(int id,Notification n){foregroundCalls++;lastType=0;if(failForeground)throw new IllegalStateException("quota");}public void startForeground(int id,Notification n,int type){foregroundCalls++;lastType=type;if(failForeground)throw new IllegalStateException("quota");}public void stopForeground(int f){stopForegroundCalls++;}public void stopSelf(){stopCalls++;}public void stopSelf(int id){stopCalls++;}}''',
'android/app/Notification.java': '''package android.app;import android.content.Context;public class Notification {public static final String CATEGORY_PROGRESS="progress";public static String title,text,action;public static class Builder {public Builder(Context c,String channel){}public Builder setSmallIcon(int x){return this;}public Builder setContentTitle(String s){title=s;return this;}public Builder setContentText(String s){text=s;return this;}public Builder setCategory(String s){return this;}public Builder setOngoing(boolean b){return this;}public Builder setOnlyAlertOnce(boolean b){return this;}public Builder addAction(int i,String s,PendingIntent p){action=s;return this;}public Notification build(){return new Notification();}}}''',
'android/app/NotificationChannel.java': '''package android.app;public class NotificationChannel {public NotificationChannel(String a,String b,int c){}}''',
'android/app/NotificationManager.java': '''package android.app;public class NotificationManager {public static final int IMPORTANCE_LOW=2;public int updates;public void createNotificationChannel(NotificationChannel c){}public void notify(int id,Notification n){updates++;}}''',
'android/app/PendingIntent.java': '''package android.app;import android.content.*;public class PendingIntent {public static final int FLAG_UPDATE_CURRENT=1,FLAG_IMMUTABLE=2;public static PendingIntent getService(Context c,int id,Intent i,int f){return new PendingIntent();}}''',
'com/termux/R.java': 'package com.termux;public class R {public static class drawable {public static final int ic_service_notification=1;}}',
'com/termux/app/TermuxService.java': '''package com.termux.app;import android.content.Context;import android.os.IBinder;public class TermuxService extends Context {public boolean stopped;public int interactiveSessions=2;public boolean wantsToStop(){return stopped;}public boolean z8IsStopRequested(){return stopped;}public class LocalBinder implements IBinder {public final TermuxService service=TermuxService.this;}}''',
'com/termux/app/Z8PreparationNotification.java': '''package com.termux.app;import android.app.Notification;public class Z8PreparationNotification {public static boolean decorate(Notification.Builder b,TermuxService s){return true;}}''',
'com/termux/app/PreparationServiceProbe.java': r'''package com.termux.app;
import android.content.*;import android.app.*;import android.content.pm.ServiceInfo;import java.util.*;
public class PreparationServiceProbe {
 static void check(boolean ok,String why){if(!ok)throw new AssertionError(why);}
 static void eq(Object a,Object b){if(!Objects.equals(a,b))throw new AssertionError(a+" != "+b);}
 static final class Work {int starts,cancels;String message;boolean fail;Z8PreparationService timed;
 void ready(){starts++;}void stopped(String m){cancels++;message=m;if(timed!=null)check(timed.stopCalls>0&&timed.stopForegroundCalls>0,"Android deadline handled before observer");if(fail)throw new IllegalStateException("observer");}}
 static void begin(TermuxService owner,String id,Work w){Z8PreparationService.begin(owner,id,w::ready,w::stopped);}
 static void connect(TermuxService owner,int at){owner.connections.get(at).onServiceConnected(new ComponentName(),owner.new LocalBinder());}
 static void promote(TermuxService owner,Z8PreparationService service,int at){service.onStartCommand(owner.starts.get(at),0,at+1);}
 static void reject(Runnable r){try{r.run();throw new AssertionError("expected rejection");}catch(IllegalStateException expected){}}
 public static void main(String[] args){String c=args[0];TermuxService owner=new TermuxService();Z8PreparationService service=new Z8PreparationService();Work a=new Work(),b=new Work();
 switch(c){
 case "promotion":
 begin(owner,"a",a);eq(0,a.starts);promote(owner,service,0);eq(0,a.starts);eq(1,service.lastType);connect(owner,0);eq(1,a.starts);promote(owner,service,0);eq(1,a.starts);Z8PreparationService.finish(owner,"a");eq(1,owner.unbinds);eq(1,service.stopCalls);break;
 case "request_failure":
 owner.bindResult=false;reject(()->begin(owner,"a",a));eq(0,owner.starts.size());owner.bindResult=true;owner.failStart=true;reject(()->begin(owner,"a",a));eq(1,owner.unbinds);owner.failStart=false;begin(owner,"a",a);connect(owner,0);promote(owner,service,0);eq(1,a.starts);Z8PreparationService.finish(owner,"a");break;
 case "promotion_failure":
 begin(owner,"a",a);connect(owner,0);service.failForeground=true;promote(owner,service,0);eq(0,a.starts);eq(1,a.cancels);eq(1,owner.unbinds);eq(1,service.stopCalls);eq(2,owner.interactiveSessions);break;
 case "concurrent":
 begin(owner,"a",a);begin(owner,"b",b);connect(owner,0);connect(owner,1);promote(owner,service,0);promote(owner,service,1);eq(1,a.starts);eq(1,b.starts);eq(ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,service.lastType);Z8PreparationService.finish(owner,"a");eq(0,service.stopCalls);eq(1,owner.connections.size());Z8PreparationService.finish(owner,"b");eq(1,service.stopCalls);eq(0,owner.connections.size());break;
 case "timeout":case "stop":case "throwing":
 begin(owner,"a",a);begin(owner,"b",b);connect(owner,0);connect(owner,1);promote(owner,service,0);promote(owner,service,1);a.timed=service;b.timed=service;a.fail=c.equals("throwing");
 if(c.equals("stop"))service.onStartCommand(new Intent(owner,Z8PreparationService.class).setAction("z8.preparation.STOP"),0,10);else service.onTimeout(2,ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
 eq(1,a.cancels);eq(1,b.cancels);eq(2,owner.unbinds);eq(2,owner.interactiveSessions);check(!owner.stopped,"interactive service unaffected");service.onDestroy();eq(1,a.cancels);break;
 case "stale":
 begin(owner,"a",a);begin(owner,"b",b);connect(owner,0);connect(owner,1);promote(owner,service,0);promote(owner,service,1);Z8PreparationService.finish(owner,"a");promote(owner,service,0);eq(0,service.stopCalls);eq(1,a.starts);Z8PreparationService.finish(owner,"b");Z8PreparationService next=new Z8PreparationService();promote(owner,next,0);eq(0,next.foregroundCalls);eq(1,next.stopCalls);break;
 case "ending":
 begin(owner,"a",a);connect(owner,0);promote(owner,service,0);Z8PreparationService.finish(owner,"a");begin(owner,"b",b);connect(owner,0);promote(owner,service,1);eq(0,b.starts);eq(1,b.cancels);eq(0,owner.connections.size());service.onDestroy();break;
 case "generation":
 begin(owner,"a",a);connect(owner,0);promote(owner,service,0);Z8PreparationService.finish(owner,"a");begin(owner,"b",b);connect(owner,0);Z8PreparationService replacement=new Z8PreparationService();promote(owner,replacement,1);service.onDestroy();eq(0,b.cancels);eq(1,b.starts);Z8PreparationService.finish(owner,"b");break;
 case "binding":
 begin(owner,"a",a);ServiceConnection old=owner.connections.get(0);TermuxService different=new TermuxService();old.onServiceConnected(new ComponentName(),different.new LocalBinder());eq(1,a.cancels);eq(0,a.starts);old.onServiceDisconnected(new ComponentName());eq(1,a.cancels);begin(owner,"b",b);connect(owner,0);promote(owner,service,1);owner.connections.get(0).onServiceDisconnected(new ComponentName());eq(1,b.cancels);eq(1,b.starts);eq(0,owner.connections.size());break;
 case "owner":
 TermuxService other=new TermuxService();Work cwork=new Work();begin(owner,"a",a);begin(owner,"b",b);begin(other,"c",cwork);connect(owner,0);connect(owner,1);connect(other,0);promote(owner,service,0);promote(owner,service,1);promote(other,service,0);a.fail=true;
 Z8PreparationService.releaseOwner(owner);eq(1,a.cancels);eq(1,b.cancels);eq(0,cwork.cancels);eq(0,service.stopCalls);eq(2,owner.unbinds);Z8PreparationService.finish(other,"c");eq(1,service.stopCalls);break;
 case "file_task":
 Z8PreparationService.beginFileTask(owner,"delete","Deleting project","Already deleted files cannot be restored",a::ready,a::stopped);eq(0,a.starts);connect(owner,0);promote(owner,service,0);eq(1,a.starts);eq("Deleting project",Notification.title);eq("Already deleted files cannot be restored",Notification.text);eq("Stop tasks",Notification.action);eq(1,service.lastType);service.onTimeout(1,1);eq(1,a.cancels);eq(2,owner.interactiveSessions);break;
 case "legacy":
 android.os.Build.VERSION.SDK_INT=28;begin(owner,"a",a);connect(owner,0);promote(owner,service,0);eq(0,service.lastType);eq(1,a.starts);Z8PreparationService.finish(owner,"a");break;
 default:throw new AssertionError(c);
 }
 System.out.println("PASS "+c);
 }
}''',
}
