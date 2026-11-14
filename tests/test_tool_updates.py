"""Foreground-only metadata coordination and hostile public release fixtures; no network."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ToolUpdateTests(unittest.TestCase):
    def test_metadata_consent_cache_singleflight_and_validation(self):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').exists() else shutil.which('javac')
        java = str(jdk / 'java') if (jdk / 'java').exists() else shutil.which('java')
        jars = list((ROOT / '.local/gradle/caches/modules-2/files-2.1/com.google.code.gson/gson').glob('*/*/gson-*.jar'))
        if not jars:
            jars = list((Path.home() / '.gradle/caches/modules-2/files-2.1/com.google.code.gson/gson').glob('*/*/gson-*.jar'))
        if not java or not javac or not jars:
            self.skipTest('Requires configured JDK and cached Gson test decoder')
        gson = str(sorted(jars)[-1])
        with tempfile.TemporaryDirectory(prefix='z8-tool-updates-') as temporary:
            root = Path(temporary); files = []
            for name, content in STUBS.items():
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content); files.append(str(path))
            source = ROOT / 'overlay/app/src/main/java/com/termux/app/Z8ToolUpdates.java'
            lifecycle = source.with_name('Z8ToolUpdateLifecycle.java')
            result = subprocess.run([javac, '-encoding', 'UTF-8', '-cp', gson, '-d', str(root), str(source), str(lifecycle), *files], capture_output=True, text=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([java, '-cp', str(root) + ':' + gson, 'com.termux.app.ToolUpdatesProbe'], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS metadata contracts', result.stdout)


STUBS = {
'android/content/SharedPreferences.java': '''package android.content;public interface SharedPreferences {
boolean getBoolean(String k,boolean d);String getString(String k,String d);long getLong(String k,long d);Editor edit();
interface Editor{Editor putBoolean(String k,boolean v);Editor putString(String k,String v);Editor putLong(String k,long v);boolean commit();void apply();}}
''',
'android/content/Context.java': '''package android.content;import java.util.*;public class Context {
public static final int MODE_PRIVATE=0;public Context getApplicationContext(){return this;}public final Pref p=new Pref();
public SharedPreferences getSharedPreferences(String n,int m){return p;}
public static class Pref implements SharedPreferences,SharedPreferences.Editor {
Map<String,Object> m=new HashMap<>();public boolean writable=true;
public boolean getBoolean(String k,boolean d){return (Boolean)m.getOrDefault(k,d);}public String getString(String k,String d){return (String)m.getOrDefault(k,d);}
public long getLong(String k,long d){return (Long)m.getOrDefault(k,d);}public Editor edit(){return this;}
public Editor putBoolean(String k,boolean v){m.put(k,v);return this;}public Editor putString(String k,String v){m.put(k,v);return this;}public Editor putLong(String k,long v){m.put(k,v);return this;}
public boolean commit(){return writable;}public void apply(){}}
}''',
'android/os/Looper.java': '''package android.os;public class Looper{public static Looper getMainLooper(){return new Looper();}}''',
'android/os/Handler.java': '''package android.os;import java.util.*;public class Handler{
public static final List<Runnable> pending=new ArrayList<>();public Handler(Looper x){}public boolean post(Runnable r){r.run();return true;}
public boolean postDelayed(Runnable r,long delay){if(delay!=500)throw new AssertionError("Bounded lifecycle grace");pending.add(r);return true;}
public void removeCallbacks(Runnable r){pending.removeIf(item->item==r);}public static void flush(){List<Runnable>x=new ArrayList<>(pending);pending.clear();for(Runnable r:x)r.run();}}
''',
'android/os/Bundle.java': '''package android.os;public class Bundle{}''',
'android/app/Activity.java': '''package android.app;public class Activity{}''',
'android/app/Application.java': '''package android.app;import android.os.Bundle;public class Application extends android.content.Context{
public int registrations;public ActivityLifecycleCallbacks callbacks;public void registerActivityLifecycleCallbacks(ActivityLifecycleCallbacks value){registrations++;callbacks=value;}
public interface ActivityLifecycleCallbacks{void onActivityStarted(Activity a);void onActivityStopped(Activity a);void onActivityCreated(Activity a,Bundle b);
void onActivityResumed(Activity a);void onActivityPaused(Activity a);void onActivitySaveInstanceState(Activity a,Bundle b);void onActivityDestroyed(Activity a);}}
''',
'org/json/JSONObject.java': '''package org.json;import java.util.*;import com.google.gson.Gson;
public class JSONObject {final Map<String,Object> m;public JSONObject(String s){m=new Gson().fromJson(s,Map.class);}JSONObject(Map<String,Object> x){m=x;}
public Object get(String k){if(!m.containsKey(k))throw new IllegalArgumentException();return m.get(k);}public Object opt(String k){return m.get(k);}
public String getString(String k){Object v=get(k);if(!(v instanceof String))throw new IllegalArgumentException();return (String)v;}
public long getLong(String k){return ((Number)get(k)).longValue();}public JSONArray getJSONArray(String k){return new JSONArray((List<Object>)get(k));}}
''',
'org/json/JSONArray.java': '''package org.json;import java.util.*;import com.google.gson.Gson;public class JSONArray{
final List<Object> a;public JSONArray(String s){a=new Gson().fromJson(s,List.class);}JSONArray(List<Object>x){a=x;}public int length(){return a.size();}
public JSONObject getJSONObject(int i){return new JSONObject((Map<String,Object>)a.get(i));}public String getString(int i){return (String)a.get(i);}}
''',
'com/termux/app/ToolUpdatesProbe.java': r'''package com.termux.app;
import android.content.Context;import java.util.*;import java.util.concurrent.atomic.*;import java.io.*;
import java.net.*;import javax.net.ssl.*;import java.security.cert.Certificate;
public class ToolUpdatesProbe {
static void check(boolean x,String why){if(!x)throw new AssertionError(why);}
interface Action{void run()throws Exception;}static void reject(Action a)throws Exception{try{a.run();}catch(Exception x){return;}throw new AssertionError("Expected rejection");}
static String codex="{\"tag_name\":\"rust-v0.170.0\",\"draft\":false,\"prerelease\":false,\"assets\":[{\"name\":\"codex-package-aarch64-unknown-linux-musl.tar.gz\",\"browser_download_url\":\"https://github.com/openai/codex/releases/download/rust-v0.170.0/codex-package-aarch64-unknown-linux-musl.tar.gz\",\"digest\":\"sha256:"+"a".repeat(64)+"\",\"size\":1234}]}";
static String node="[{\"version\":\"v26.1.0\",\"lts\":\"Other\",\"files\":[\"linux-arm64\"]},{\"version\":\"v24.22.1\",\"lts\":\"Krypton\",\"files\":[\"linux-arm64\"]},{\"version\":\"v24.21.0\",\"lts\":\"Krypton\",\"files\":[\"linux-arm64\"]}]";
static class Connection extends HttpsURLConnection {
String body="2.1.300\n";int code=200;boolean disconnected;Map<String,String> headers=new HashMap<>();
Connection(URL u){super(u);}public void connect(){}public void disconnect(){disconnected=true;}public boolean usingProxy(){return false;}
public String getCipherSuite(){return "fixture";}public Certificate[] getLocalCertificates(){return null;}public Certificate[] getServerCertificates(){return null;}
public int getResponseCode(){responseRequests++;return code;}public InputStream getInputStream(){return new ByteArrayInputStream(body.getBytes(java.nio.charset.StandardCharsets.UTF_8));}
public long getContentLengthLong(){return body.length();}public void setRequestProperty(String k,String v){headers.put(k,v);}
}
static Connection next;static boolean cancelOnOpen;static int responseRequests;
public static void main(String[]args)throws Exception {
check(Z8ToolUpdates.parse("codex",codex).equals("0.170.0"),"Codex exact native asset");
check(Z8ToolUpdates.parse("node",node).equals("v24.22.1"),"Node stays on 24 LTS");
check(Z8ToolUpdates.parse("claude","2.1.300\n").equals("2.1.300"),"Claude exact stable version");
for(String bad:new String[]{"latest","2.1.0;id","01.2.3","1.2.3-beta","1.2.3\n4.5.6","9999999.1.0"})reject(()->Z8ToolUpdates.parse("claude",bad));
reject(()->Z8ToolUpdates.parse("codex",codex.replace("\"prerelease\":false","\"prerelease\":true")));
reject(()->Z8ToolUpdates.parse("codex",codex.replace("sha256:","sha1:")));
reject(()->Z8ToolUpdates.parse("codex",codex.replace("https://github.com/", "https://evil.invalid/")));
reject(()->Z8ToolUpdates.parse("node",node.replace("linux-arm64","linux-x64")));
reject(()->Z8ToolUpdates.parse("node",node.replace("\"Krypton\"","false")));
check(Z8ToolUpdates.newer("node","v24.22.0","v24.9.9"),"Numeric version comparison");
check(!Z8ToolUpdates.newer("node","v26.0.0","v24.9.9"),"No major automatic offer");
Context context=new Context();List<Runnable> queue=new ArrayList<>();AtomicLong now=new AtomicLong(1000000);AtomicInteger calls=new AtomicInteger(),callbacks=new AtomicInteger();
Z8ToolUpdates.worker=queue::add;Z8ToolUpdates.clock=now::get;
Z8ToolUpdates.fetcher=(url,max)->{calls.incrementAndGet();return url.equals(Z8ToolUpdates.CODEX)?codex:url.equals(Z8ToolUpdates.NODE)?node:"2.1.300";};
Z8ToolUpdates.requestCheck(context,false,null);check(queue.isEmpty()&&calls.get()==0,"No opt in means zero requests");
Z8ToolUpdates.requestCheck(context,true,s->callbacks.incrementAndGet());
Z8ToolUpdates.requestCheck(context,true,s->callbacks.incrementAndGet());check(queue.size()==1,"Single flight with callback join");
queue.remove(0).run();check(calls.get()==3&&callbacks.get()==2&&!Z8ToolUpdates.enabled(context),"Force once does not opt in");
check(Z8ToolUpdates.cached(context).get("claude").upstreamVersion.equals("2.1.300"),"Cached metadata");
Z8ToolUpdates.setEnabled(context,true);Z8ToolUpdates.requestCheck(context,false,null);check(queue.isEmpty(),"24h success throttle");
now.addAndGet(Z8ToolUpdates.INTERVAL);Z8ToolUpdates.requestCheck(context,false,null);check(queue.size()==1,"Due only on next request");
Z8ToolUpdates.fetcher=(url,max)->{throw new IOException("private URL should not be exposed");};queue.remove(0).run();
check(Z8ToolUpdates.cached(context).get("claude").upstreamVersion.equals("2.1.300"),"Keep last success on failure");
check(Z8ToolUpdates.cached(context).get("claude").error.equals("Metadata check unavailable"),"No raw exception leakage");
Z8ToolUpdates.requestCheck(context,false,null);check(queue.isEmpty(),"Failures throttled");
Z8ToolUpdates.requestCheck(context,true,s->callbacks.incrementAndGet());Z8ToolUpdates.cancel();queue.remove(0).run();
check(callbacks.get()==2,"No cancelled callbacks");Z8ToolUpdates.requestCheck(context,false,null);check(queue.isEmpty(),"No reopen retry after cancellation");
Z8ToolUpdates.setEnabled(context,false);now.addAndGet(Z8ToolUpdates.INTERVAL);Z8ToolUpdates.requestCheck(context,false,null);check(queue.isEmpty(),"Disable stops future requests");
android.app.Application app=new android.app.Application();android.app.Activity one=new android.app.Activity(),two=new android.app.Activity();
Z8ToolUpdateLifecycle.install(app);Z8ToolUpdateLifecycle.install(app);check(app.registrations==1,"One lifecycle observer");
app.callbacks.onActivityStarted(one);check(queue.isEmpty(),"Lifecycle without opt in performs no request");
app.callbacks.onActivityStopped(one);android.os.Handler.flush();Z8ToolUpdates.setEnabled(app,true);
app.callbacks.onActivityStarted(one);check(queue.size()==1,"Visible entry requests metadata once");
app.callbacks.onActivityStarted(two);app.callbacks.onActivityStopped(one);android.os.Handler.flush();check(Z8ToolUpdates.cached(app).checking,"Other activity remains visible");
app.callbacks.onActivityStopped(two);check(Z8ToolUpdates.cached(app).checking,"No immediate cancel during navigation grace");
app.callbacks.onActivityStarted(one);android.os.Handler.flush();check(queue.size()==1&&Z8ToolUpdates.cached(app).checking,"Rotation cancels hidden callback and joins same flight");
app.callbacks.onActivityStopped(one);android.os.Handler.flush();check(!Z8ToolUpdates.cached(app).checking,"Final activity stop cancels request");
int before=calls.get();queue.remove(0).run();check(calls.get()==before&&queue.isEmpty(),"Cancelled queued lifecycle work cannot fetch or reschedule");
app.callbacks.onActivityStarted(one);check(queue.isEmpty(),"Reopen within day retains attempt throttle");
app.callbacks.onActivityStopped(one);android.os.Handler.flush();now.addAndGet(Z8ToolUpdates.INTERVAL);
check(queue.isEmpty(),"A day passing in background schedules nothing");app.callbacks.onActivityStarted(one);check(queue.size()==1,"Next visible entry after day checks");
Z8ToolUpdates.cancel();queue.remove(0).run();
URL.setURLStreamHandlerFactory(protocol->protocol.equals("https")?new URLStreamHandler(){protected URLConnection openConnection(URL url){next=new Connection(url);if(cancelOnOpen)Z8ToolUpdates.cancel();return next;}}:null);
check(Z8ToolUpdates.fetch(Z8ToolUpdates.CLAUDE,128).trim().equals("2.1.300"),"Bounded HTTPS metadata fetch");
check(!next.getInstanceFollowRedirects()&&next.getConnectTimeout()==10000&&next.getReadTimeout()==10000,"Redirects disabled and deadlines");
check(!next.headers.containsKey("Authorization")&&!next.headers.containsKey("Cookie")&&next.headers.size()==3,"No account or installed data headers");
check(next.disconnected,"Connection closed");reject(()->Z8ToolUpdates.fetch("https://api.github.com/repos/other/private",128));
reject(()->Z8ToolUpdates.fetch(Z8ToolUpdates.CLAUDE,2));
Z8ToolUpdates.fetcher=Z8ToolUpdates::fetch;cancelOnOpen=true;int beforeResponse=responseRequests;Z8ToolUpdates.requestCheck(context,true,s->callbacks.incrementAndGet());queue.remove(0).run();
check(next.disconnected&&callbacks.get()==2&&responseRequests==beforeResponse,"Cancellation between open and registration closes connection before response request");
System.out.println("PASS metadata contracts");
}}
'''
}
