"""Compile the real session catalog against memory-only service/PTY stubs."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SessionCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temporary = tempfile.TemporaryDirectory(prefix='z8-session-catalog-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        sources = []
        for name, code in STUBS.items():
            path = cls.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code)
            sources.append(str(path))
        sources += [str(ROOT / 'overlay/app/src/main/java/com/termux/app' / name)
                    for name in ('Z8SessionOrigin.java', 'Z8SessionCatalog.java')]
        result = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(cls.directory), *sources],
                                capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, name):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.CatalogProbe', name],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS: ' + name, result.stdout)

    def test_project_groups_and_service_order(self):
        self.probe('groups')

    def test_default_and_user_renamed_titles(self):
        self.probe('titles')

    def test_numbering_survives_deletion_and_service_recreation(self):
        self.probe('numbering')

    def test_launch_purpose_is_not_inferred_from_terminal_output(self):
        self.probe('tools')

    def test_selected_and_ended_sessions(self):
        self.probe('state')

    def test_stale_session_identity_and_replacement_service(self):
        self.probe('stale')

    def test_control_characters_and_unicode_length(self):
        self.probe('text')

    def test_null_service_and_immutable_snapshot(self):
        self.probe('snapshot')


STUBS = {
    'android/content/Context.java': '''package android.content; import java.util.*;
        public class Context {public static final int MODE_PRIVATE=0;private static final Map<String,SharedPreferences> preferences=new HashMap<>();
        public Context getApplicationContext(){return this;} public SharedPreferences getSharedPreferences(String name,int mode){return preferences.computeIfAbsent(name,key->new SharedPreferences());}}''',
    'android/content/SharedPreferences.java': '''package android.content;import java.util.*;public class SharedPreferences {
        private final Map<String,String> data=new HashMap<>();
        public String getString(String key,String fallback){return data.getOrDefault(key,fallback);} public Editor edit(){return new Editor();}
        public class Editor {public Editor putString(String key,String value){data.put(key,value);return this;}public void apply(){}}}''',
    'com/termux/terminal/TerminalSession.java': '''package com.termux.terminal;
        public final class TerminalSession {
            public final String mHandle; public String mSessionName; public boolean running=true;
            public TerminalSession(String handle,String name){mHandle=handle;mSessionName=name;}
            public boolean isRunning(){return running;}
            public String getTitle(){throw new AssertionError("Must not read terminal titles");}
            public Object getEmulator(){throw new AssertionError("Must not read terminal output");}
        }''',
    'com/termux/shared/termux/shell/command/runner/terminal/TermuxSession.java': '''
        package com.termux.shared.termux.shell.command.runner.terminal;
        import com.termux.terminal.TerminalSession;
        public class TermuxSession {private final TerminalSession terminal;
            public TermuxSession(TerminalSession terminal){this.terminal=terminal;}
            public TerminalSession getTerminalSession(){return terminal;}
        }''',
    'com/termux/app/TermuxService.java': '''package com.termux.app;
        import java.util.*;
        import com.termux.shared.termux.shell.command.runner.terminal.TermuxSession;
        public class TermuxService extends android.content.Context {public final List<TermuxSession> sessions=new ArrayList<>();
            public synchronized List<TermuxSession> getTermuxSessions(){return sessions;}
        }''',
    'com/termux/app/CatalogProbe.java': r'''package com.termux.app;
        import java.util.*;
        import com.termux.terminal.TerminalSession;
        import com.termux.shared.termux.shell.command.runner.terminal.TermuxSession;
        public class CatalogProbe {
            static void check(boolean value,String description){if(!value)throw new AssertionError(description);}
            static TerminalSession add(TermuxService service,String handle,String name){
                TerminalSession session=new TerminalSession(handle,name);
                service.sessions.add(new TermuxSession(session));return session;
            }
            static Z8SessionCatalog.Entry entry(TermuxService service,TerminalSession session){
                for(Z8SessionCatalog.Entry entry:Z8SessionCatalog.snapshot(service,session))
                    if(entry.session==session)return entry;
                throw new AssertionError("Missing entry");
            }
            public static void main(String[] args){
                TermuxService service=new TermuxService();String probe=args[0];
                switch(probe){
                    case "groups": {
                        TerminalSession first=add(service,"1","web · Linux");
                        TerminalSession nativeShell=add(service,"2",null);
                        TerminalSession second=add(service,"3","scripts · Linux");
                        TerminalSession repeated=add(service,"4","web · Codex");
                        Z8SessionOrigin.remember(first,"web-id","web");
                        Z8SessionOrigin.remember(second,"scripts-id","scripts");
                        Z8SessionOrigin.remember(repeated,"web-id","web","codex");
                        List<Z8SessionCatalog.Entry> items=Z8SessionCatalog.snapshot(service,second);
                        check(items.size()==4,"All service-owned sessions visible");
                        check(items.get(0).session==first && items.get(1).session==nativeShell && items.get(3).session==repeated,"Service order preserved");
                        check(items.get(0).projectId.equals(items.get(3).projectId),"Same project grouping key");
                        check(!items.get(0).projectId.equals(items.get(2).projectId),"Different project grouping keys");
                        check(items.get(1).projectId.isEmpty() && items.get(1).projectName.equals("Device shell"),"Native shell has explicit separate group");
                        check(items.get(0).projectName.equals("web") && items.get(2).projectName.equals("scripts"),"Readable project labels");
                        break;
                    }
                    case "titles": {
                        TerminalSession shell=add(service,"1","web · Linux");
                        Z8SessionOrigin.remember(shell,"p","web");
                        check(entry(service,shell).title.equals("Terminal 1"),"Legacy generated Linux title numbered");
                        TerminalSession codex=add(service,"2","web · Codex");
                        Z8SessionOrigin.remember(codex,"p","web","codex");
                        check(entry(service,codex).title.equals("Codex"),"Generated tool title simplified");
                        codex.mSessionName="web · API 리뷰 ✨";
                        check(entry(service,codex).title.equals("web · API 리뷰 ✨"),"User project-prefixed rename preserved");
                        codex.mSessionName="배포 작업";
                        check(entry(service,codex).title.equals("배포 작업"),"User rename preserved");
                        codex.mSessionName="  ";
                        check(entry(service,codex).title.equals("Codex"),"Empty title uses launch label");
                        TerminalSession unnamed=add(service,"3",null);
                        check(entry(service,unnamed).title.equals("Terminal 1"),"Unnamed native shell has independent numbered fallback");
                        break;
                    }
                    case "numbering": {
                        String id="numbering-project";
                        service.getSharedPreferences("z8.terminal-names",0).edit().putString(id,"40").apply();
                        check(Z8SessionCatalog.nextTerminalName(service,id).equals("Terminal 41"),"Stored high-water counter restored");
                        TerminalSession original=add(service,"first","Terminal 80");
                        Z8SessionOrigin.remember(original,id,"web");
                        check(Z8SessionCatalog.nextTerminalName(service,id).equals("Terminal 81"),"Current raw names advance the sequence");
                        original.mSessionName="My server";
                        check(entry(service,original).title.equals("My server"),"User rename preserved");
                        service.sessions.clear();
                        check(Z8SessionCatalog.nextTerminalName(service,id).equals("Terminal 82"),"Deletion does not reuse numbers");
                        check(Z8SessionCatalog.nextTerminalName(service,"other-project").equals("Terminal 1"),"Each project owns its counter");
                        try {
                            java.lang.reflect.Field memory=Z8SessionCatalog.class.getDeclaredField("HIGH_WATER");memory.setAccessible(true);
                            ((Map<?,?>)memory.get(null)).clear();
                        } catch(Exception failure) {throw new AssertionError(failure);}
                        check(Z8SessionCatalog.nextTerminalName(new TermuxService(),id).equals("Terminal 83"),"Disk counter survives process-memory reset");
                        TerminalSession legacy=add(service,"old","web · Linux");Z8SessionOrigin.remember(legacy,id,"web");
                        String label=entry(service,legacy).title;
                        check(label.equals("Terminal 84") && entry(service,legacy).title.equals(label),"Legacy default numbered once across snapshots");
                        check(Z8SessionCatalog.title(legacy).equals(label),"Notifications share the same stable label");
                        legacy.mSessionName="Shell";
                        check(entry(service,legacy).title.equals("Shell"),"An explicit user title is never rewritten as a default");
                        legacy.mSessionName="custom · Linux";
                        check(entry(service,legacy).title.equals("custom · Linux"),"Different project prefix is user text");
                        break;
                    }
                    case "tools": {
                        String[][] cases={{"claude","Claude Code"},{"codex","Codex"},
                            {"setup-codex","Install Codex"},{"setup-claude","Install Claude"},
                            {"setup-tools","Install development tools"},{"github-auth","GitHub sign-in"},
                            {"hooks-codex","Codex notifications"},{"hooks-claude","Claude notifications"},{"remote-shell","Terminal"},{"future-action","Terminal"}};
                        for(String[] item:cases){TerminalSession session=add(service,item[0],"renamed");
                            Z8SessionOrigin.remember(session,"p","project",item[0]);
                            check(entry(service,session).tool.equals(item[1]),"Explicit launch purpose: "+item[0]);}
                        TerminalSession shell=add(service,"shell","Claude Code");
                        Z8SessionOrigin.remember(shell,"p","project");
                        check(entry(service,shell).tool.equals("Terminal"),"Renaming shell does not claim AI is running");
                        check(Z8SessionOrigin.of(shell).action==null,"Legacy origin remains compatible");
                        break;
                    }
                    case "state": {
                        TerminalSession active=add(service,"active","Shell");
                        TerminalSession ended=add(service,"ended","Codex");ended.running=false;
                        List<Z8SessionCatalog.Entry> items=Z8SessionCatalog.snapshot(service,ended);
                        check(items.get(0).running && !items.get(0).selected,"Active unselected PTY state");
                        check(!items.get(1).running && items.get(1).selected,"Ended selected PTY remains visible");
                        check(Z8SessionCatalog.contains(service,ended),"Ended object remains owned until removed");
                        check(items.get(0).handle.equals("active"),"Handle is the actual session handle");
                        break;
                    }
                    case "stale": {
                        TerminalSession original=add(service,"shared-handle","original");
                        Z8SessionOrigin.remember(original,"p","project");
                        check(Z8SessionCatalog.contains(service,original),"Current object is owned");
                        TerminalSession impersonator=new TerminalSession("shared-handle","original");
                        check(!Z8SessionCatalog.contains(service,impersonator),"Matching handle or title does not establish identity");
                        service.sessions.clear();
                        check(!Z8SessionCatalog.contains(service,original),"Removed cached object cannot be selected");
                        check(Z8SessionCatalog.snapshot(service,original).isEmpty(),"Origin records do not resurrect removed sessions");
                        check(!Z8SessionCatalog.contains(new TermuxService(),original),"Replacement service does not own old object");
                        break;
                    }
                    case "text": {
                        TerminalSession session=add(service,"text","  작업\n\t\u001b\u202e리뷰\u2028\u0000  ");
                        Z8SessionOrigin.remember(session,"p","웹\u202e\n프로젝트");
                        check(entry(service,session).title.equals("작업리뷰"),"Controls and direction changes removed");
                        check(entry(service,session).projectName.equals("웹프로젝트"),"Group label also sanitized");
                        StringBuilder longTitle=new StringBuilder();for(int i=0;i<150;i++)longTitle.appendCodePoint(0x1f4bb);
                        session.mSessionName=longTitle.toString();String shown=entry(service,session).title;
                        check(shown.codePointCount(0,shown.length())==96 && shown.endsWith("…"),"Long title bounded by code points");
                        for(int i=0;i<shown.length();i++)if(Character.isHighSurrogate(shown.charAt(i)))check(i+1<shown.length()&&Character.isLowSurrogate(shown.charAt(++i)),"No split emoji");
                        session.mSessionName="\u0000\u202e\ud800";
                        check(entry(service,session).title.equals("Terminal 1"),"Entirely invalid display text has numbered fallback");
                        break;
                    }
                    case "snapshot": {
                        check(Z8SessionCatalog.snapshot(null,null).isEmpty(),"Unbound service is empty");
                        check(!Z8SessionCatalog.contains(null,null) && !Z8SessionCatalog.contains(service,null),"Null identity never matches");
                        Z8SessionOrigin.remember(null,"p","project");
                        TerminalSession session=add(service,"one","Original");
                        service.sessions.add(null);service.sessions.add(new TermuxSession(null));
                        List<Z8SessionCatalog.Entry> items=Z8SessionCatalog.snapshot(service,session);
                        check(items.size()==1,"Invalid wrapper entries ignored");
                        session.mSessionName="Changed";session.running=false;service.sessions.clear();
                        check(items.get(0).title.equals("Original") && items.get(0).running,"Snapshot display metadata is stable");
                        boolean immutable=false;try{items.clear();}catch(UnsupportedOperationException expected){immutable=true;}
                        check(immutable,"Callers cannot mutate snapshot collection");
                        check(Z8SessionCatalog.snapshot(service,session).isEmpty(),"Next snapshot reflects service changes");
                        break;
                    }
                    default: throw new AssertionError("Unknown probe");
                }
                System.out.println("PASS: "+probe);
            }
        }''',
}


if __name__ == '__main__':
    unittest.main()
