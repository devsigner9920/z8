"""Selected package scope, offline inventory, and service-owned tool lifecycle."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.test_setup_resume import TOOL

ROOT = Path(__file__).resolve().parents[1]


class SelectedToolScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.bin = self.root / 'bin'; self.bin.mkdir()
        self.guest = self.root / 'guest'; (self.guest / 'etc/z8').mkdir(parents=True)
        (self.guest / 'etc/z8/guest-target').write_text('z8-guest-v1\n')
        (self.guest / 'etc/os-release').write_text('ID=debian\n')
        self.scripts = self.root / 'scripts'; self.scripts.mkdir()
        for name in ('uname','id','apt-get','dpkg','dpkg-query','python3'):
            path = self.bin / name; path.write_text(TOOL.replace('PYTHON', sys.executable, 1)); path.chmod(0o755)
        (self.bin / 'flock').write_text('#!/bin/sh\nexit 0\n'); (self.bin / 'flock').chmod(0o755)
        script = (ROOT / 'runtime/guest/tool-manager.sh').read_text()
        script = re.sub(r'(?<![\w/.-])/(?:etc/|z8/|workspace\b|opt/)',lambda m: str(self.guest)+m.group(),script)
        script = script.replace('/usr/bin/python3',str(self.bin/'python3'))
        (self.scripts / 'tool-manager.sh').write_text(script)
        (self.scripts / 'install-node.py').write_text('# fixture\n')
        (self.scripts / 'install-ai.sh').write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$Z8_FIXTURE/ai-args"\n')
        (self.scripts / 'probe-tools.sh').write_text('#!/bin/bash\nprintf "%s\\t1.2.3\\n" "$1"\n')
        self.env = dict(os.environ,PATH=str(self.bin)+':/usr/bin:/bin',Z8_FIXTURE=str(self.root))
        self.state({})
    def state(self,value): (self.root/'state').write_text(json.dumps(value))
    def calls(self):
        p=self.root/'calls';return [json.loads(v) for v in p.read_text().splitlines()] if p.exists() else []
    def run_tool(self,*args):
        return subprocess.run(['/bin/bash',str(self.scripts/'tool-manager.sh'),*args],env=self.env,capture_output=True,text=True,timeout=10)
    def test_git_install_only_requests_git_and_certificate_dependencies(self):
        r=self.run_tool('--apply','git');self.assertEqual(r.returncode,0,r.stderr)
        installs=[c for c in self.calls() if c[0]=='apt-get' and 'install' in c]
        self.assertEqual(len(installs),1);self.assertEqual(installs[0][-2:],['git','ca-certificates']);self.assertIn('--no-remove',installs[0])
        self.assertFalse(any(c[0] in ('node','npm','python3') for c in self.calls()))
    def test_verified_completed_packages_skip_network_on_retry(self):
        self.state({'installed':True});r=self.run_tool('--apply','git');self.assertEqual(r.returncode,0,r.stderr)
        self.assertFalse(any(c[0]=='apt-get' for c in self.calls()))
    def test_update_scopes_apt_transaction_to_selected_tool(self):
        self.state({'installed':True});r=self.run_tool('--update','tmux');self.assertEqual(r.returncode,0,r.stderr)
        install=[c for c in self.calls() if c[0]=='apt-get' and 'install' in c][0]
        self.assertEqual(install[-1],'tmux');self.assertNotIn('upgrade',install);self.assertIn('--no-remove',install)
    def test_native_version_is_fixed_argument_and_minimal_dependencies(self):
        r=self.run_tool('--update','claude','--version','2.3.4');self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual((self.root/'ai-args').read_text().splitlines(),['--apply','claude','--version','2.3.4'])
        install=[c for c in self.calls() if c[0]=='apt-get' and 'install' in c][0]
        self.assertEqual(install[-3:],['python3','ca-certificates','gpgv'])
    def test_github_browser_login_includes_python_browser_bridge_dependency(self):
        r=self.run_tool('--apply','gh');self.assertEqual(r.returncode,0,r.stderr)
        install=[c for c in self.calls() if c[0]=='apt-get' and 'install' in c][0]
        self.assertEqual(install[-4:],['gh','git','python3','ca-certificates'])
    def test_bad_tool_or_version_fails_before_package_side_effects(self):
        for args in [('--apply','all'),('--apply','git','--version','1.0.0'),('--apply','codex','--version','1.2.3;id'),('--update','node','--version','v25.0.0'),('--update','codex','--version','01.2.3'),('--update','claude','--version','9999999.1.0'),('--update','node','--version','v24.01.2'),('--apply','claude','--version','1.2.3'),('--update','codex')]:
            with self.subTest(args=args): self.assertNotEqual(self.run_tool(*args).returncode,0)
        self.assertEqual(self.calls(),[])
    def test_interrupted_dpkg_is_actionable_and_never_blanket_repaired(self):
        self.state({'apt_fail':True})
        # Permit the repository refresh, fail only the transaction as interrupted dpkg would.
        tool=(self.bin/'apt-get').read_text().replace("if state.get('apt_fail'): sys.exit(100)","if state.get('apt_fail') and 'install' in args: sys.exit(100)")
        (self.bin/'apt-get').write_text(tool)
        r=self.run_tool('--apply','git');self.assertNotEqual(r.returncode,0)
        self.assertIn('dpkg --audit',r.stderr);self.assertIn('dpkg --configure <package ...>',r.stderr)
        self.assertNotIn(['dpkg','--configure','-a'],self.calls())
        self.assertFalse(any('upgrade' in c or '-f' in c for c in self.calls()))
        self.state({});r=self.run_tool('--apply','git');self.assertEqual(r.returncode,0,r.stderr)


class NativeSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.home=self.root/'home';self.node=self.root/'node';self.other=self.root/'other';self.other.mkdir()
        (self.home/'.local/bin').mkdir(parents=True);self.node.mkdir()
        raw=(ROOT/'runtime/guest/probe-tools.sh').read_text().split("<<'Z8_STATUS_PYTHON'\n",1)[1].split('\nZ8_STATUS_PYTHON',1)[0]
        self.code=raw.replace('/opt/z8/node',str(self.node)).replace('/z8/home',str(self.home))
        self.env=dict(os.environ,PATH=str(self.node/'current/bin')+':'+str(self.home/'.local/bin'))
    def binary(self,path):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text('#!/bin/sh\nexit 99\n');path.chmod(0o755);return path
    def ai(self,tool='codex'):
        d=self.home/'.local/share/z8/ai'/tool/'1.2.3';b=self.binary(d/tool)
        (d/'receipt.json').write_text(json.dumps({'manager':'z8-ai-v1','tool':tool,'version':'1.2.3','binarySha256':'a'*64}))
        (self.home/'.local/bin'/tool).symlink_to(b);return d
    def install_node(self):
        d=self.node/'v24.1.2';self.binary(d/'bin/node');self.binary(d/'bin/npm')
        (d/'.z8-node-receipt.json').write_text(json.dumps({'manager':'z8-node-v1','version':'v24.1.2','npm':'11.2.3'}))
        (self.node/'current').symlink_to(d.name);return d
    def run_snapshot(self):
        r=subprocess.run([sys.executable,'-c',self.code],env=self.env,capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr);return dict(v.split('\t',1) for v in r.stdout.splitlines())
    def test_managed_receipts_are_read_without_running_binaries(self):
        self.install_node();self.ai();s=self.run_snapshot();self.assertEqual(s['node'],'v24.1.2');self.assertEqual(s['npm'],'11.2.3');self.assertEqual(s['codex'],'1.2.3')
    def test_shadowed_launcher_is_unknown_not_managed(self):
        self.install_node();self.ai();self.binary(self.node/'current/bin/codex');self.assertEqual(self.run_snapshot()['codex'],'?')
    def test_nonexecutable_npm_does_not_claim_verified_install(self):
        d=self.install_node();(d/'bin/npm').chmod(0o644);s=self.run_snapshot();self.assertNotEqual(s['npm'],'11.2.3')
    def test_malformed_receipt_is_per_tool_unknown(self):
        d=self.install_node();(d/'.z8-node-receipt.json').write_text('[]');self.ai();s=self.run_snapshot();self.assertEqual(s['node'],'?');self.assertEqual(s['codex'],'1.2.3')
    def test_looped_launcher_does_not_abort_other_tool_rows(self):
        link=self.home/'.local/bin/codex';link.symlink_to('codex');self.ai('claude');s=self.run_snapshot();self.assertIn(s['codex'],('-','?'));self.assertEqual(s['claude'],'1.2.3')
    def test_custom_binary_without_receipt_is_unknown(self):
        self.binary(self.home/'.local/bin/claude');self.assertEqual(self.run_snapshot()['claude'],'?')


class GuestToolLaunchBoundaryTests(unittest.TestCase):
    def test_legacy_install_action_cannot_bypass_service_owned_installer(self):
        source=(ROOT/'overlay/app/src/main/java/com/termux/app/Z8Guest.java').read_text()
        method=source.split('    public static Launch actionCommand(',1)[1].split('    /** Same guest execution adapter',1)[0]
        method='    public static Launch actionCommand('+method
        jdk=ROOT/'.local/jdk/Contents/Home/bin'
        javac=str(jdk/'javac') if (jdk/'javac').exists() else shutil.which('javac')
        java=str(jdk/'java') if (jdk/'java').exists() else shutil.which('java')
        if not javac or not java:self.skipTest('A JDK is required')
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp); (d/'Context.java').write_text('package android.content; public class Context {}')
            (d/'GuestBoundary.java').write_text('''package com.termux.app;
import android.content.Context;import java.util.*;import java.io.*;
public class GuestBoundary {
static int probes,launches;static String[] last;
static class Launch {}
static class Result {Map<String,String> versions=Map.of("codex","1.2.3","claude","1.2.3","gh","1.2.3","python","3.13");}
static boolean validAction(String s){return Arrays.asList("setup-tools","setup-codex","setup-claude","codex","claude","github-auth","hooks-codex","hooks-claude","rescue-shell").contains(s);}
static String actionLabel(String s){return s;}
static void invalidateReadiness(String s){}
static Result probe(Context c,String id,String required){probes++;return new Result();}
static Launch commandFor(Context c,String id,String cwd,String[] args){launches++;last=args;return new Launch();}
'''+method+'''
public static void main(String[] args)throws Exception{
 Context c=new Context();
 for(String action:new String[]{"setup-codex","setup-claude"}){
  try{actionCommand(c,"owned",null,action);throw new AssertionError("Legacy installer bypass");}
  catch(IOException expected){if(!expected.getMessage().contains("Tools"))throw expected;}
 }
 if(probes!=0||launches!=0)throw new AssertionError("Denied action had side effects");
 actionCommand(c,"owned",null,"codex");
 if(probes!=1||launches!=1||!Arrays.equals(last,new String[]{"/bin/bash","/usr/local/lib/z8/guest-task.sh","codex"}))throw new AssertionError("Normal CLI launch changed");
 actionCommand(c,"owned",null,"setup-tools");
 if(!Arrays.equals(last,new String[]{"/bin/bash","/usr/local/lib/z8/setup-tools.sh"}))throw new AssertionError("Local-only compatibility setup unavailable");
 System.out.println("PASS");
}}
''')
            c=subprocess.run([javac,'-d',str(d),str(d/'Context.java'),str(d/'GuestBoundary.java'),str(ROOT/'overlay/app/src/main/java/com/termux/app/Z8Text.java')],capture_output=True,text=True,timeout=30)
            self.assertEqual(c.returncode,0,c.stdout+c.stderr)
            r=subprocess.run([java,'-cp',str(d),'com.termux.app.GuestBoundary'],capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(r.stdout.strip(),'PASS')
