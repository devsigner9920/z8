"""Fixed tool choices and the UI's install/update decision boundary, without Android or network."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ToolCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temp = tempfile.TemporaryDirectory(prefix='z8-tool-catalog-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        probe = cls.directory / 'ToolCatalogProbe.java'
        probe.write_text(PROBE)
        sources = [ROOT / 'overlay/app/src/main/java/com/termux/app' / name for name in ('Z8ToolCatalog.java', 'Z8Text.java')]
        result = subprocess.run([javac, '-encoding', 'UTF-8', '-d', str(cls.directory), *map(str, sources), str(probe)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, case):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.ToolCatalogProbe', case], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS ' + case)

    def test_fixed_ids_immutable_choices_and_native_tools_optional(self): self.probe('catalog')
    def test_native_tool_dependency_plan_does_not_add_unneeded_node(self): self.probe('dependencies')
    def test_missing_or_failed_checks_do_not_claim_manual_installs_absent(self): self.probe('presence')
    def test_install_uses_configured_pin_and_rejects_supplied_versions(self): self.probe('install')
    def test_update_requires_exact_native_version_and_node_stays_on_24(self): self.probe('update')
    def test_package_updates_reject_arbitrary_versions_or_tools(self): self.probe('packages')
    def test_only_known_version_output_formats_are_accepted(self): self.probe('output')
    def test_language_switch_changes_app_copy_without_changing_ids_or_packages(self): self.probe('language')


PROBE = r'''
package com.termux.app;
import java.util.*;
public class ToolCatalogProbe {
static void eq(Object a,Object b){if(!Objects.equals(a,b))throw new AssertionError(a+" != "+b);}
static void bad(Runnable r){try{r.run();throw new AssertionError("Accepted unsafe request");}catch(IllegalArgumentException expected){}}
static void immutable(Runnable r){try{r.run();throw new AssertionError("Mutable catalog");}catch(UnsupportedOperationException expected){}}
public static void main(String[] args){
switch(args[0]){
case "catalog": {
 Set<String> actual=new LinkedHashSet<>();int recommended=0;
 for(Z8ToolCatalog.Tool t:Z8ToolCatalog.TOOLS){if(!actual.add(t.id))throw new AssertionError("Duplicate");if(t.group==Z8ToolCatalog.Group.RECOMMENDED)recommended++;}
 eq(new LinkedHashSet<>(Arrays.asList("python","git","node","codex","claude","gh","ssh","build-tools","tmux","utilities")),actual);eq(2,recommended);
 eq(Z8ToolCatalog.Group.OPTIONAL,Z8ToolCatalog.get("codex").group);eq(Z8ToolCatalog.Group.OPTIONAL,Z8ToolCatalog.get("claude").group);
 immutable(()->Z8ToolCatalog.TOOLS.clear());immutable(()->Z8ToolCatalog.get("python").packages().clear());break;}
case "dependencies": {
 eq(Arrays.asList("python3","ca-certificates"),Z8ToolCatalog.get("codex").packages());
 eq(Arrays.asList("python3","ca-certificates","gpgv"),Z8ToolCatalog.get("claude").packages());
 eq(Arrays.asList("python3","python3-pip","python3-venv","ca-certificates"),Z8ToolCatalog.get("python").packages());
 for(String id:Arrays.asList("node","codex","claude"))if(Z8ToolCatalog.get(id).packages().contains("nodejs"))throw new AssertionError("Unneeded Node dependency");
 eq(true,Z8ToolCatalog.get("gh").packages().contains("git"));
 eq(true,Z8ToolCatalog.get("gh").packages().contains("python3"));break;}
case "presence": {
 eq(Z8ToolCatalog.Presence.UNKNOWN,Z8ToolCatalog.presence(false,false,false));
 eq(Z8ToolCatalog.Presence.UNKNOWN,Z8ToolCatalog.presence(true,false,true));
 eq(Z8ToolCatalog.Presence.INSTALLED,Z8ToolCatalog.presence(true,true,true));
 eq(Z8ToolCatalog.Presence.NEEDS_INSTALLATION,Z8ToolCatalog.presence(true,false,false));break;}
case "install": {
 for(Z8ToolCatalog.Tool t:Z8ToolCatalog.TOOLS){Z8ToolCatalog.Request r=new Z8ToolCatalog.Request(t.id,false,null);eq("",r.version);eq(false,r.update);eq(t,r.tool);}
 bad(()->new Z8ToolCatalog.Request("codex",false,"1.2.3"));bad(()->new Z8ToolCatalog.Request("node",false,"v24.2.3"));break;}
case "update": {
 eq("v24.21.0",new Z8ToolCatalog.Request("node",true,"v24.21.0").version);
 eq("2.1.285",new Z8ToolCatalog.Request("claude",true,"2.1.285").version);
 eq("0.114.0",new Z8ToolCatalog.Request("codex",true,"0.114.0").version);
 for(String v:Arrays.asList("", "v26.1.0", "v24.01.0", "v24.1.0-beta", "v24.1.0;id", "https://example.invalid/tool", "v24.1000000.0"))bad(()->new Z8ToolCatalog.Request("node",true,v));
 for(String v:Arrays.asList("", "latest", "1.0.0/../../x", "1.0.0\n", "v1.0.0", "01.2.3"))bad(()->new Z8ToolCatalog.Request("codex",true,v));break;}
case "packages": {
 eq("",new Z8ToolCatalog.Request("git",true,"").version);bad(()->new Z8ToolCatalog.Request("git",true,"2.47.3"));
 for(String id:Arrays.asList("", "git;id", "node --version", "../claude", "python3", "unknown"))bad(()->new Z8ToolCatalog.Request(id,false,""));break;}
case "output": {
 eq("0.114.0",Z8ToolCatalog.releaseVersion("codex","codex-cli 0.114.0"));
 eq("2.1.285",Z8ToolCatalog.releaseVersion("claude","2.1.285 (Claude Code)"));
 eq("v24.21.0",Z8ToolCatalog.releaseVersion("node","v24.21.0"));
 eq("",Z8ToolCatalog.releaseVersion("node","v26.1.0"));
 eq("",Z8ToolCatalog.releaseVersion("codex","custom wrapper revision 0.114.0"));
 eq("",Z8ToolCatalog.releaseVersion("claude","2.1.285 (custom wrapper)"));
 eq("",Z8ToolCatalog.releaseVersion("codex",null));eq("",Z8ToolCatalog.releaseVersion(null,"1.2.3"));
 eq("",Z8ToolCatalog.releaseVersion("codex","codex-cli 1000000.0.0"));break;}
case "language": {
 Z8ToolCatalog.Tool t=Z8ToolCatalog.get("utilities");Z8Text.setLanguage("en");eq("Utilities",t.name());String packages=t.packages().toString();
 Z8Text.setLanguage("ko");eq("유틸리티",t.name());eq(packages,t.packages().toString());eq("utilities",t.id);break;}
default:throw new AssertionError("Unknown case");}
System.out.println("PASS "+args[0]);
}}
'''
