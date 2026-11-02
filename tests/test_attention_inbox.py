"""Group real inbox rows and exercise their existing-event navigation contract.

Android intents/live-session lookups are stubs; this does not claim a device PTY test.
"""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('catalog_fixtures', ROOT / 'tests/test_session_catalog.py')
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


class AttentionInboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-inbox-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        sources = []
        for name, code in (catalog.STUBS | STUBS).items():
            path = cls.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code)
            sources.append(str(path))
        sources += [str(ROOT / 'overlay/app/src/main/java/com/termux/app' / name)
                    for name in ('Z8SessionOrigin.java', 'Z8SessionCatalog.java', 'Z8AttentionInbox.java')]
        result = subprocess.run([javac, '-encoding', 'UTF-8', '-d', str(cls.directory), *sources],
                                capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, name):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.InboxProbe', name],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS: ' + name, result.stdout)

    def test_group_identity_order_and_history(self):
        self.probe('groups')

    def test_observed_unread_does_not_infer_current_approval_state(self):
        self.probe('state')

    def test_group_row_opens_original_event_and_rejects_ended_session(self):
        self.probe('route')

    def test_empty_and_sanitized_display_fields(self):
        self.probe('text')

    def test_maximum_inbox_preserves_session_and_event_order(self):
        self.probe('capacity')


STUBS = {
    'android/content/Intent.java': '''package android.content;import java.util.*;
        public class Intent {public final Map<String,String>extras=new HashMap<>();public final String destination;
            public Intent(String destination){this.destination=destination;}
            public Intent putExtra(String name,String value){extras.put(name,value);return this;}}
    ''',
    'android/content/Context.java': '''package android.content;import java.util.*;
        public class Context {public static final int MODE_PRIVATE=0;private static final Map<String,SharedPreferences>preferences=new HashMap<>();
            public Context getApplicationContext(){return this;}public SharedPreferences getSharedPreferences(String name,int mode){return preferences.computeIfAbsent(name,key->new SharedPreferences());}
            public final List<Intent>opened=new ArrayList<>();public void startActivity(Intent intent){opened.add(intent);}}
    ''',
    'org/json/JSONObject.java': '''package org.json;import java.util.*;
        public class JSONObject {private final Map<String,Object> values=new HashMap<>();
            public JSONObject put(String name,Object value){values.put(name,value);return this;}
            public String optString(String name){Object value=values.get(name);return value instanceof String?(String)value:"";}
            public long optLong(String name){Object value=values.get(name);return value instanceof Number?((Number)value).longValue():0;}
            public boolean has(String name){return values.containsKey(name);}}
    ''',
    'com/termux/app/Z8AttentionBridge.java': '''package com.termux.app;import android.content.*;import java.util.*;
        import com.termux.terminal.TerminalSession;
        public class Z8AttentionBridge {
            public static final String EXTRA_EVENT="attention.event";
            static final Map<String,TerminalSession> targets=new HashMap<>();
            static int lookups,intents;
            public static boolean canOpen(String id){lookups++;TerminalSession session=targets.get(id);return session!=null&&session.isRunning();}
            public static Intent sessionIntent(Context context,String id){intents++;return new Intent("TermuxActivity").putExtra(EXTRA_EVENT,id);}
        }
    ''',
    'com/termux/app/InboxProbe.java': r'''package com.termux.app;
        import android.content.*;import org.json.JSONObject;import java.util.*;import com.termux.terminal.TerminalSession;
        public class InboxProbe {
            static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
            static JSONObject event(String id,String project,String terminal,long date,String kind) {
                return new JSONObject().put("id",id).put("projectId",project).put("projectName","Same name")
                    .put("sessionHandle",terminal).put("sessionName","Shell").put("observedAt",date)
                    .put("kind",kind).put("provider","claude").put("state","OBSERVED").put("seenAt",0);
            }
            static Z8AttentionInbox.Item first(List<Z8AttentionInbox.Project> projects){return projects.get(0).sessions.get(0).items.get(0);}
            public static void main(String[]args) {
                String scenario=args[0];
                if(scenario.equals("groups")) {
                    List<JSONObject> source=List.of(event("a-old","A","t1",1,"permission"),event("b","B","t1",4,"question"),
                        event("a-new","A","t2",9,"plan"),event("a-old-newer","A","t1",7,"permission"));
                    List<Z8AttentionInbox.Project> groups=Z8AttentionInbox.group(source,id->true);
                    check(groups.size()==2,"Equal project names remain separate by ID");
                    check(groups.get(0).key.equals("project:A")&&groups.get(1).key.equals("project:B"),"Projects ordered by latest event");
                    check(groups.get(0).sessions.size()==2,"Equal terminal titles remain separate by handle");
                    check(groups.get(0).sessions.get(0).key.equals("session:t2"),"Terminal groups ordered by latest event");
                    check(groups.get(0).sessions.get(1).items.get(0).id.equals("a-old-newer"),"Events newest first inside group");
                    check(source.get(0).optString("id").equals("a-old"),"Grouping does not mutate source order");
                    JSONObject old=new JSONObject().put("id","history").put("projectName","Same name").put("sessionName","Shell").put("state","STALE");
                    groups=Z8AttentionInbox.group(List.of(source.get(0),old),id->true);
                    check(groups.size()==2&&groups.get(1).key.startsWith("history:"),"Unknown historical IDs are not joined to current projects");
                } else if(scenario.equals("state")) {
                    List<JSONObject> records=List.of(event("request","A","t",7,"permission"),event("finished","A","t",6,"finished"),
                        event("seen","A","t",5,"question").put("seenAt",100),event("stale","A","t",4,"plan").put("state","STALE"),
                        event("gone","A","t",3,"permission"),event("unknown","A","t",2,"unknown"));
                    Z8AttentionInbox.Project project=Z8AttentionInbox.group(records,id->!id.equals("gone")).get(0);
                    List<Z8AttentionInbox.Item> items=project.sessions.get(0).items;
                    check(project.unseen==1,"Only live unread observed requests count toward badge");
                    check(items.get(0).status().equals("미확인"),"Request status states unread, not waiting or approved");
                    check(items.get(1).finished&&!items.get(1).unseenRequest&&items.get(1).status().equals("완료 기록"),"Completion is a record, not an approval request");
                    check(items.get(2).status().equals("읽음"),"Seen is not resolved");
                    check(!items.get(3).openable&&!items.get(4).openable,"Stale and vanished sessions are disabled");
                    check(items.get(5).status().equals("알림")&&!items.get(5).finished,"Unknown event cannot claim completion");
                    check(records.get(0).optLong("seenAt")==0,"Rendering never marks a request as seen");
                } else if(scenario.equals("route")) {
                    TerminalSession original=new TerminalSession("t1","Shell");
                    TerminalSession other=new TerminalSession("t2","Shell");
                    Z8AttentionBridge.targets.put("target",original);Z8AttentionBridge.targets.put("other",other);
                    Z8AttentionInbox.Item item=first(Z8AttentionInbox.group(List.of(event("target","A","t1",1,"permission")),Z8AttentionBridge::canOpen));
                    Context context=new Context();int before=Z8AttentionBridge.lookups;
                    check(Z8AttentionInbox.open(context,item),"Live grouped row opens");
                    check(Z8AttentionBridge.lookups>before,"Tap revalidates the live mapping");
                    Intent intent=context.opened.get(0);
                    check(intent.destination.equals("TermuxActivity"),"Uses existing terminal destination");
                    check(intent.extras.size()==1&&"target".equals(intent.extras.get(Z8AttentionBridge.EXTRA_EVENT)),"Only original event ID is routed; no new-session/project/approval extras");
                    check(Z8AttentionBridge.targets.get(intent.extras.get(Z8AttentionBridge.EXTRA_EVENT))==original,"Duplicate display names cannot select the other terminal mapping");
                    original.running=false;
                    check(!Z8AttentionInbox.open(context,item)&&context.opened.size()==1,"Session ending after render does not open or replace a terminal");
                    check(!Z8AttentionInbox.openEvent(context,"missing")&&!Z8AttentionInbox.openEvent(context,null),"Unknown and absent deep links do not route");
                    check(Z8AttentionBridge.intents==1,"Rejected taps do not even construct launch intents");
                } else if(scenario.equals("capacity")) {
                    List<JSONObject> records=new ArrayList<>();
                    Set<String> live=new HashSet<>();
                    for(int i=0;i<256;i++) {
                        records.add(event("event-"+i,"A","terminal-"+(i%128),i,"permission"));
                        if(i%2==0)live.add("event-"+i);
                    }
                    int[] lookups={0};
                    Z8AttentionInbox.Project project=Z8AttentionInbox.group(records,id->{lookups[0]++;return live.contains(id);}).get(0);
                    check(lookups[0]==256,"Each record uses one batched live-state lookup");
                    check(project.sessions.size()==128&&project.unseen==128,"Capacity grouping keeps independent sessions and unread counts");
                    for(int i=0;i<128;i++) {
                        Z8AttentionInbox.Session session=project.sessions.get(i);
                        check(session.key.equals("session:terminal-"+(127-i)),"Session order follows latest observation");
                        check(session.items.size()==2&&session.items.get(0).id.equals("event-"+(255-i))
                            &&session.items.get(1).id.equals("event-"+(127-i)),"Repeated session lookup preserves newest-first events");
                    }
                } else if(scenario.equals("text")) {
                    check(Z8AttentionInbox.group(List.of(),id->true).isEmpty(),"No sample notifications are inserted");
                    JSONObject record=event("id","A","t",-1,"permission").put("projectName","Demo\u202e\n").put("sessionName","Shell\t\u0000").put("provider","diagnostic");
                    Z8AttentionInbox.Project project=Z8AttentionInbox.group(List.of(record),id->true).get(0);
                    check(project.name.equals("Demo")&&project.sessions.get(0).name.equals("Shell"),"Display labels strip controls");
                    Z8AttentionInbox.Item item=project.sessions.get(0).items.get(0);
                    check(item.observedAt==0&&item.provider.equals("진단 테스트"),"Invalid time stays unknown and diagnostics are explicit");
                    check(Z8AttentionInbox.group(List.of(new JSONObject().put("kind","permission")),id->true).isEmpty(),"Unroutable empty ID is omitted");
                } else throw new AssertionError(scenario);
                System.out.println("PASS: "+scenario);
            }
        }
    ''',
}
