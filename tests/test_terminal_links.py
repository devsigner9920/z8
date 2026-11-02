"""HTML taps resolve project files without guessing PRoot cwd or typing CLI commands."""
from pathlib import Path
import importlib.util
import json
import re
import sys
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
JDK = ROOT / '.local/jdk/Contents/Home/bin'


class TerminalLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='z8-terminal-links-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        harness = cls.directory / 'LinksProbe.java'
        harness.write_text(r'''package com.termux.app;
import java.nio.file.*;
public class LinksProbe {
    static void check(boolean value) { if (!value) throw new AssertionError(); }
    static void reject(RunnableIO action) throws Exception { try { action.run(); throw new AssertionError("accepted"); } catch (java.io.IOException expected) {} }
    interface RunnableIO { void run() throws Exception; }
    static void file(Path p) throws Exception { Files.createDirectories(p.getParent()); Files.write(p,new byte[]{1}); }
    public static void main(String[] args) throws Exception {
        Path base=Files.createTempDirectory("z8-link-case"), home=Files.createDirectory(base.resolve("home")), source=Files.createDirectory(base.resolve("source"));
        String scenario=args[0];
        if(scenario.equals("parser")) {
            check("dist/index.html".equals(Z8TerminalPath.htmlToken("`dist/index.html`")));
            check("dist/index.html".equals(Z8TerminalPath.htmlToken("(./dist/index.html:3:7).")));
            check("/z8/home/a/index.HTM".equals(Z8TerminalPath.htmlToken("/z8/home/a/index.HTM")));
            for(String bad:new String[]{"../a.html","a/../b.html",".secret/a.html","https://x/a.html","file:///a.html","$(id).html","a;id.html","a\\b.html","a\nb.html","a.html?x","a.html#fragment","a//b.html","/a//b.html","index.js"}) check(Z8TerminalPath.htmlToken(bad)==null);
        } else if(scenario.equals("unique")) {
            file(home.resolve("test/orb/dist/index.html"));
            Z8TerminalPath.Matches m=Z8TerminalPath.find("dist/index.html",home,source);
            check(m.complete&&m.paths.size()==1&&m.paths.get(0).equals("/z8/home/test/orb/dist/index.html"));
            check(Z8TerminalPath.resolve(m.paths.get(0),null,home,source).equals(m.paths.get(0)));
            reject(()->Z8TerminalPath.resolve("dist/index.html",null,home,source));
            // Kernel cwd often stays at /workspace under PRoot. It must not be used as a fallback.
            check(!Files.exists(source.resolve("dist/index.html")));
        } else if(scenario.equals("ambiguous")) {
            file(home.resolve("a/dist/index.html"));file(source.resolve("b/dist/index.html"));
            Z8TerminalPath.Matches m=Z8TerminalPath.find("dist/index.html",home,source);
            check(m.complete&&m.paths.size()==2);
        } else if(scenario.equals("excluded")) {
            file(home.resolve(".private/dist/index.html"));file(home.resolve("node_modules/pkg/dist/index.html"));
            Path outside=base.resolve("other-project");file(outside.resolve("dist/index.html"));
            Files.createSymbolicLink(home.resolve("linked"),outside);
            Z8TerminalPath.Matches m=Z8TerminalPath.find("dist/index.html",home,source);
            check(m.complete&&m.paths.isEmpty());
            reject(()->Z8TerminalPath.resolve("/z8/home/linked/dist/index.html",null,home,source));
            reject(()->Z8TerminalPath.find("dist/index.html",home.resolve("linked"),source));
            reject(()->Z8TerminalPath.resolve("/etc/index.html",null,home,source));
            Files.createDirectory(outside.resolve("id"));
            reject(()->Z8TerminalPath.directory(home,"linked/id"));
            check(Z8TerminalPath.directory(base,"home").equals(home.toRealPath()));
        } else if(scenario.equals("limits")) {
            file(home.resolve("a/b/c/dist/index.html"));
            check(!Z8TerminalPath.find("dist/index.html",home,source,1,10,2_000_000_000L).complete);
            check(!Z8TerminalPath.find("dist/index.html",home,source,100,1,2_000_000_000L).complete);
            check(!Z8TerminalPath.find("dist/index.html",home,source,100,10,-1).complete);
        } else if(scenario.equals("race")) {
            Path p=home.resolve("a/dist/index.html");file(p);
            String match=Z8TerminalPath.find("dist/index.html",home,source).paths.get(0);
            Files.delete(p);Path outside=base.resolve("other.html");file(outside);Files.createSymbolicLink(p,outside);
            reject(()->Z8TerminalPath.resolve(match,null,home,source));
        } else throw new AssertionError(scenario);
    }
}''')
        compiled = subprocess.run([str(JDK/'javac'), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-d', str(cls.directory),
            str(ROOT/'overlay/app/src/main/java/com/termux/app/Z8TerminalPath.java'),str(harness)],capture_output=True,text=True)
        if compiled.returncode: raise AssertionError(compiled.stderr)

    def probe(self, scenario):
        result=subprocess.run([str(JDK/'java'),'-cp',str(self.directory),'com.termux.app.LinksProbe',scenario],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_html_grammar_rejects_commands_traversal_and_schemes(self): self.probe('parser')
    def test_unique_nested_home_file_without_guessing_cwd(self): self.probe('unique')
    def test_ambiguous_project_paths_remain_distinct(self): self.probe('ambiguous')
    def test_hidden_dependency_and_symlink_paths_are_excluded(self): self.probe('excluded')
    def test_scan_limits_never_claim_unique_completion(self): self.probe('limits')
    def test_changed_file_is_revalidated_before_launch(self): self.probe('race')

    def test_link_gesture_never_opens_from_drag_longpress_pinch_selection_or_stale_session(self):
        probe = self.directory/'GestureProbe.java'
        probe.write_text(r'''import com.termux.view.Z8FileLinkGesture;
public class GestureProbe {
 static void check(boolean b){if(!b)throw new AssertionError();}
 public static void main(String[] args){
  Z8FileLinkGesture g=new Z8FileLinkGesture();
  g.begin(10,5,5,false,true);check(g.tap(10,100,500,false));g.consumed(10);
  check(g.wasConsumed(10)&&!g.tap(10,110,500,false));
  g.begin(20,5,5,false,true);check(!g.wasConsumed(20)&&g.tap(20,100,500,false));
  check(g.wasConsumed(10)); // Delayed confirmation from old gesture still stays consumed.
  g.begin(30,5,5,false,true);g.move(40,5,1,8);g.move(5,5,1,8);check(!g.tap(30,100,500,false));
  g.begin(40,5,5,false,true);g.move(5,5,2,8);check(!g.tap(40,100,500,false));
  g.begin(50,5,5,false,true);g.cancel();check(!g.tap(50,100,500,false));
  g.begin(60,5,5,false,true);check(!g.tap(60,600,500,false));
  g.begin(70,5,5,true,true);check(!g.tap(70,100,500,false));
  g.begin(80,5,5,false,false);check(!g.tap(80,100,500,false));
  g.begin(90,5,5,false,true);g.reset();check(!g.tap(90,100,500,false)&&!g.wasConsumed(10));
 }
}''')
        source=ROOT/'overlay/terminal-view/src/main/java/com/termux/view/Z8FileLinkGesture.java'
        result=subprocess.run([str(JDK/'javac'), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'),'-d',str(self.directory),str(source),str(probe)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run([str(JDK/'java'),'-cp',str(self.directory),'GestureProbe'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_separate_helper_reports_ready_then_owns_preview_lifetime_and_literal_argument(self):
        links=(ROOT/'overlay/app/src/main/java/com/termux/app/Z8TerminalLinks.java').read_text()
        constant=links.split('static final String HELPER =',1)[1].split('private Z8TerminalLinks()',1)[0]
        helper=''.join(json.loads(part) for part in re.findall(r'"(?:\\.|[^"\\])*"',constant))
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary); bridge=directory/'browser-open.py'; args=directory/'arguments.json'
            bridge.write_text('import json,threading,time\n'
                'def main(arguments):\n'
                f'    open({str(args)!r},"w").write(json.dumps(arguments))\n'
                '    t=threading.Thread(target=lambda:time.sleep(.8),name="z8-preview-reaper",daemon=True)\n'
                '    t.start()\n'
                '    return 0\n')
            helper=helper.replace('/usr/local/lib/z8/browser-open.py',str(bridge))
            value='/z8/home/literal;$(no-command)/index.html'
            process=subprocess.Popen([sys.executable,'-I','-c',helper,value],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            self.addCleanup(lambda: process.kill() if process.poll() is None else None)
            self.assertEqual(process.stdout.readline().strip(),'Z8_HTML_READY=0')
            self.assertIsNone(process.poll())
            self.assertEqual(json.loads(args.read_text()),[value])
            self.assertEqual(process.wait(timeout=3),0)
            process.stdout.close();process.stderr.close()

    def test_pinned_touch_patch_consumes_html_before_tui_mouse_and_preserves_drag(self):
        def module(name,path):
            spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
        prepare=module('prepare_links_test',ROOT/'tools/prepare-app.py')
        with tempfile.TemporaryDirectory() as temporary:
            tree=Path(temporary)
            for name in ('terminal-view','app'):
                shutil.copytree(ROOT/'upstream/termux-app'/name/'src/main/java',tree/name/'src/main/java')
            module('input_links_test',ROOT/'tools/patch-terminal-input.py').patch(tree,prepare.replace_exact)
            module('links_patch_test',ROOT/'tools/patch-terminal-links.py').patch(tree,prepare.replace_exact)
            view=(tree/'terminal-view/src/main/java/com/termux/view/TerminalView.java').read_text()
            up=view.split('public boolean onUp(MotionEvent event)',1)[1].split('public boolean onSingleTapUp',1)[0]
            self.assertLess(up.index('mClient.onOpenFileLink(event)'),up.index('sendMouseEventCode'))
            self.assertIn('!isSelectingText() && !scrolledWithFinger',up)
            self.assertIn('if (mZ8FileLinks.wasConsumed(event.getDownTime()))',view)
            recognizer=(ROOT/'upstream/termux-app/terminal-view/src/main/java/com/termux/view/GestureAndScaleRecognizer.java').read_text()
            self.assertIn('if (!isAfterLongPress)',recognizer)
            mouse=view.split('private boolean z8MouseEvent',1)[1].split('private int[] z8MouseCell',1)[0]
            self.assertLess(mouse.index('if (range != null)'),mouse.index('mClient.onOpenFileLink(event)'))
            links=(ROOT/'overlay/app/src/main/java/com/termux/app/Z8TerminalLinks.java').read_text()
            self.assertNotIn('session.write(',links)
            self.assertNotIn('getCwd(',links)
            self.assertIn('"-I", "-c", HELPER, target',links)
            self.assertIn('selected.get(2, TimeUnit.SECONDS)',links)
            self.assertIn("t.name=='z8-preview-reaper'",links)
