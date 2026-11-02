"""Exercise the real preparation notification owner with deterministic Android boundaries."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class PreparationNotificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temp = tempfile.TemporaryDirectory(prefix='z8-preparation-notification-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        sources = []
        for name, source in STUBS.items():
            path = cls.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
            sources.append(str(path))
        probe = cls.directory / 'NotificationProbe.java'
        probe.write_text(PROBE)
        sources.extend([str(probe), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8PreparationNotification.java')])
        result = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(cls.directory), *sources], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, case):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.NotificationProbe', case], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_live_progress_and_navigation_never_create_a_session(self): self.probe('progress')
    def test_installation_progress_is_coalesced_and_tools_are_indeterminate(self): self.probe('coalescing')
    def test_queue_transitions_and_final_failure_release_scoped_lock(self): self.probe('queue')
    def test_destroyed_service_cannot_publish_or_keep_a_lock(self): self.probe('destroy')
    def test_disabled_notifications_do_not_block_installation_cleanup(self): self.probe('disabled')
    def test_new_service_ignores_old_worker_updates(self): self.probe('generation')
    def test_initial_setup_notification_opens_setup_without_project_or_session(self): self.probe('initial')
    def test_network_pause_is_waiting_not_failure_and_releases_lock(self): self.probe('waiting')

STUBS = {
'android/os/Looper.java': r'''package android.os; public class Looper {
static final Looper MAIN = new Looper(); public static Looper getMainLooper(){return MAIN;} public static Looper myLooper(){return MAIN;}}
''',
'android/os/Handler.java': r'''package android.os; import java.util.*; public class Handler {
public static final Map<Runnable,Long> queue = new LinkedHashMap<>(); public Handler(Looper l){}
public boolean postDelayed(Runnable r,long ms){queue.put(r,ms);return true;} public void removeCallbacks(Runnable r){queue.remove(r);}
public static void tick(long delay){for(Runnable r:new ArrayList<>(queue.keySet())) if(queue.get(r)!=null && queue.get(r)<=delay){queue.remove(r);r.run();}}
}''',
'android/os/PowerManager.java': r'''package android.os; public class PowerManager {
public static final int PARTIAL_WAKE_LOCK=1; public final WakeLock lock=new WakeLock();
public WakeLock newWakeLock(int type,String tag){return lock;}
public static class WakeLock{public int acquired,released; public long timeout; public boolean held,referenceCounted=true;
public void setReferenceCounted(boolean b){referenceCounted=b;} public void acquire(long ms){acquired++;held=true;timeout=ms;}
public boolean isHeld(){return held;} public void release(){released++;held=false;}}
}''',
'android/content/Context.java': r'''package android.content; import android.app.*; import android.os.*;
public class Context { public final NotificationManager notifications=new NotificationManager(); public final PowerManager power=new PowerManager();
public <T>T getSystemService(Class<T> type){return type.cast(type==NotificationManager.class?notifications:power);}}
''',
'android/content/Intent.java': r'''package android.content; import android.net.Uri; import java.util.*; public class Intent {
public static final int FLAG_ACTIVITY_CLEAR_TOP=1,FLAG_ACTIVITY_SINGLE_TOP=2; public final Map<String,String> extras=new HashMap<>(); public Uri data;
public Class<?> target; public Intent(Context c,Class<?> cls){target=cls;} public Intent setData(Uri d){data=d;return this;} public Intent addFlags(int f){return this;}
public Intent putExtra(String k,String v){extras.put(k,v);return this;}}
''',
'android/net/Uri.java': r'''package android.net; public class Uri { public String value; Uri(String s){value=s;}
public static class Builder {String value=""; public Builder scheme(String s){value+=s+":";return this;} public Builder authority(String s){value+="//"+s;return this;}
public Builder appendPath(String p){value+="/"+p;return this;} public Uri build(){return new Uri(value);}}}
''',
'android/app/PendingIntent.java': r'''package android.app; import android.content.*; public class PendingIntent {
public static final int FLAG_UPDATE_CURRENT=1,FLAG_IMMUTABLE=2; public Intent intent; public int flags;
public static PendingIntent getActivity(Context c,int code,Intent i,int flags){PendingIntent p=new PendingIntent();p.intent=i;p.flags=flags;return p;}}
''',
'android/app/Notification.java': r'''package android.app; import android.content.Context; public class Notification {
public static final String CATEGORY_PROGRESS="progress",CATEGORY_STATUS="status",CATEGORY_ERROR="error";
public Builder source; public static class BigTextStyle {public BigTextStyle bigText(String s){return this;}}
public static class Builder { public String title,text; public int progress; public boolean indeterminate,ongoing,autoCancel; public PendingIntent intent;
public Builder(Context c){} public Builder(Context c,String channel){} public Builder setContentTitle(String s){title=s;return this;}
public Builder setContentText(String s){text=s;return this;} public Builder setStyle(BigTextStyle s){return this;}
public Builder setContentIntent(PendingIntent p){intent=p;return this;} public Builder setProgress(int max,int p,boolean i){progress=p;indeterminate=i;return this;}
public Builder setCategory(String s){return this;} public Builder setOnlyAlertOnce(boolean b){return this;} public Builder setShowWhen(boolean b){return this;}
public Builder setOngoing(boolean b){ongoing=b;return this;} public Builder setAutoCancel(boolean b){autoCancel=b;return this;}
public Builder setSmallIcon(int icon){return this;} public Notification build(){Notification n=new Notification();n.source=this;return n;}}
}''',
'android/app/NotificationChannel.java': r'''package android.app; public class NotificationChannel {public NotificationChannel(String id,String name,int importance){}}''',
'android/app/NotificationManager.java': r'''package android.app; import java.util.*; public class NotificationManager {
public static final int IMPORTANCE_LOW=2; public boolean enabled=true; public final Map<String,Notification> posted=new HashMap<>();
public void cancel(String tag,int id){posted.remove(tag);} public boolean areNotificationsEnabled(){return enabled;}
public void createNotificationChannel(NotificationChannel c){} public void notify(String tag,int id,Notification n){posted.put(tag,n);}}
''',
'android/util/Log.java': r'''package android.util; public class Log {public static int w(String tag,String text){return 0;}}''',
'com/termux/R.java': r'''package com.termux; public class R {public static class drawable {public static final int ic_service_notification=1;}}''',
'com/termux/app/TermuxActivity.java': r'''package com.termux.app; public class TermuxActivity {}''',
'com/termux/app/Z8SetupActivity.java': r'''package com.termux.app; public class Z8SetupActivity {}''',
'com/termux/app/Z8InitialSetup.java': r'''package com.termux.app; public class Z8InitialSetup {public static final String NOTIFICATION_ID="__initial_setup__";}''',
'com/termux/app/TermuxService.java': r'''package com.termux.app; public class TermuxService extends android.content.Context {
public int updates; public boolean stopped; public void updateNotification(){updates++;} public boolean wantsToStop(){return stopped;}}''',
'com/termux/app/Z8WorkspaceActivity.java': r'''package com.termux.app; public class Z8WorkspaceActivity {public static final String EXTRA_FOCUS_PROJECT_ID="focus";}''',
}

PROBE = r'''
package com.termux.app;
import android.app.*;
import android.os.*;
public class NotificationProbe {
static void eq(Object a,Object b){if(!java.util.Objects.equals(a,b))throw new AssertionError(a+" != "+b);}
static Notification.Builder card(TermuxService s){Notification.Builder b=new Notification.Builder(s);eq(true,Z8PreparationNotification.decorate(b,s));return b;}
static void empty(TermuxService s){eq(false,Z8PreparationNotification.decorate(new Notification.Builder(s),s));}
public static void main(String[] args){
TermuxService s=new TermuxService(); Z8PreparationNotification.begin(s,"a","project-a","My project");
eq(true,s.power.lock.held);eq(false,s.power.lock.referenceCounted);eq(true,s.power.lock.timeout>0);
switch(args[0]){
case "progress": {
Notification.Builder b=card(s);eq(true,b.ongoing);eq(true,b.indeterminate);eq("My project · Preparing first launch",b.title);
eq(1,b.intent.intent.extras.size());eq("project-a",b.intent.intent.extras.get("focus"));eq(3,b.intent.flags);
Z8PreparationNotification.progress(s,"a","rootfs",48,"환경 압축 해제"); Handler.tick(1000);b=card(s);eq(false,b.indeterminate);eq(48,b.progress);
Z8PreparationNotification.finish(s,"a",true,"private");empty(s);eq(false,s.power.lock.held);eq(true,s.notifications.posted.get("project-a").source.autoCancel);
eq("project-a",s.notifications.posted.get("project-a").source.intent.intent.extras.get("focus"));break;}
case "coalescing": {
int before=s.updates;for(int i=0;i<100;i++)Z8PreparationNotification.progress(s,"a","rootfs",i,"extract");
eq(before,s.updates);eq(2,Handler.queue.size()); Handler.tick(1000);eq(before+1,s.updates);eq(99,card(s).progress);
Z8PreparationNotification.progress(s,"a","tools",75,"Node.js 설치");Handler.tick(1000);eq(true,card(s).indeterminate);break;}
case "queue": {
Z8PreparationNotification.begin(s,"b","project-b","Second");eq(1,s.power.lock.acquired);eq(true,card(s).text.contains("1 project(s) waiting"));
Z8PreparationNotification.finish(s,"a",true,null);eq(true,s.power.lock.held);eq("Second · Preparing first launch",card(s).title);
Z8PreparationNotification.finish(s,"b",false,"TOKEN_SECRET\nprivate log");eq(false,s.power.lock.held);eq(1,s.power.lock.released);empty(s);
eq(false,s.notifications.posted.get("project-b").source.text.contains("TOKEN_SECRET"));eq(0,Handler.queue.size());break;}
case "destroy": {
Z8PreparationNotification.progress(s,"a","tools",-1,"install");Z8PreparationNotification.releaseOwner(s);eq(false,s.power.lock.held);
eq(0,Handler.queue.size());int count=s.updates;Z8PreparationNotification.progress(s,"a","tools",-1,"late");Handler.tick(1000);eq(count,s.updates);empty(s);break;}
case "disabled": {
s.notifications.enabled=false;Z8PreparationNotification.finish(s,"a",false,"error");eq(false,s.power.lock.held);eq(0,s.notifications.posted.size());empty(s);break;}
case "generation": {
TermuxService replacement=new TermuxService();Z8PreparationNotification.begin(replacement,"b","project-b","New owner");eq(false,s.power.lock.held);empty(s);
Z8PreparationNotification.progress(s,"a","rootfs",77,"late");Handler.tick(1000);eq("New owner · Preparing first launch",card(replacement).title);
Z8PreparationNotification.releaseOwner(s);eq(true,replacement.power.lock.held);Z8PreparationNotification.releaseOwner(replacement);eq(false,replacement.power.lock.held);break;}
case "initial": {
Z8PreparationNotification.releaseOwner(s);Z8PreparationNotification.begin(s,"initial",Z8InitialSetup.NOTIFICATION_ID,"template");
Notification.Builder b=card(s);eq("z8 · Initial setup",b.title);eq(Z8SetupActivity.class,b.intent.intent.target);eq(0,b.intent.intent.extras.size());
Z8PreparationNotification.finish(s,"initial",true,null);b=s.notifications.posted.get(Z8InitialSetup.NOTIFICATION_ID).source;
eq(Z8SetupActivity.class,b.intent.intent.target);eq(true,b.text.contains("first project"));eq(false,s.power.lock.held);break;}
case "waiting": {
Z8PreparationNotification.releaseOwner(s);Z8PreparationNotification.begin(s,"initial",Z8InitialSetup.NOTIFICATION_ID,"template");
Z8PreparationNotification.waiting(s,"initial");Notification.Builder b=s.notifications.posted.get(Z8InitialSetup.NOTIFICATION_ID).source;
eq("z8 · Waiting for network",b.title);eq(Z8SetupActivity.class,b.intent.intent.target);eq(false,s.power.lock.held);empty(s);break;}
default:throw new AssertionError("Unknown case");
}
System.out.println("PASS "+args[0]);}
}
'''
