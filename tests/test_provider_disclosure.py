"""Executable notice decisions and on-disk project/install boundaries, without Android/network."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProviderDisclosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temp = tempfile.TemporaryDirectory(prefix='z8-provider-notice-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name).resolve()
        probe = cls.directory / 'ProviderNoticeProbe.java'
        probe.write_text(PROBE)
        app = ROOT / 'overlay/app/src/main/java/com/termux/app'
        files = [app / x for x in ('Z8Text.java', 'Z8ToolCatalog.java', 'Z8ProviderNotice.java', 'Z8ProviderInstallIdentity.java')]
        result = subprocess.run([javac, '-encoding', 'UTF-8', '-d', str(cls.directory), *map(str, files), str(probe)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def probe(self, case):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.ProviderNoticeProbe', case], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS ' + case)

    def test_cancel_does_not_launch_or_remember_and_continuation_is_single_use(self): self.probe('decision')
    def test_project_provider_install_and_revision_boundaries(self): self.probe('scope')
    def test_unknown_client_and_failed_storage_never_create_blanket_acknowledgment(self): self.probe('unknown')
    def test_known_receipt_identity_changes_on_version_receipt_or_binary_replacement(self): self.probe('identity')
    def test_unmanaged_escape_links_oversized_and_invalid_receipts_are_unknown(self): self.probe('unsafe')
    def test_record_is_outside_source_home_and_deleted_with_project(self): self.probe('store')
    def test_official_links_both_account_terms_pinned_codex_notices_and_language(self): self.probe('links')
    def test_repeated_same_launch_ticket_survives_rotation_while_distinct_ticket_is_cancelled(self): self.probe('pending')

    def test_common_app_launch_path_gates_provider_before_service_request(self):
        text = (ROOT / 'tools/prepare-app.py').read_text()
        start = text.index('public void addGuestSession(String projectId, String directory, String name, String action, String requestId)')
        block = text[start:text.index('private void addNewSessionInDirectoryChecked', start)]
        self.assertIn('Z8ProviderDisclosure.beforeLaunch(mActivity, projectId, action, requestId,', block)
        self.assertIn('() -> com.termux.app.Z8GuestSessionLauncher.request(', block)
        self.assertIn('() -> com.termux.app.Z8GuestSessionLauncher.cancelRequest(service, requestId)', block)
        self.assertNotIn('actionCommand(', block)


PROBE = r'''
package com.termux.app;
import java.io.*;import java.nio.file.*;import java.nio.file.attribute.FileTime;import java.util.*;
public class ProviderNoticeProbe {
static final String P="00000000-0000-4000-8000-000000000001", Q="00000000-0000-4000-8000-000000000002";
static int launches;static void eq(Object a,Object b){if(!Objects.equals(a,b))throw new AssertionError(a+" != "+b);}
static class Memory implements Z8ProviderNotice.Store {
 Map<String,String> m=new HashMap<>();boolean fail;
 public String read(String p,String t)throws IOException {if(fail)throw new IOException();return m.get(p+":"+t);}
 public void write(String p,String t,String v)throws IOException {if(fail)throw new IOException();m.put(p+":"+t,v);}
}
static Z8ProviderNotice.Decision decision(String p,String t,String token,Z8ProviderNotice.Store store){return new Z8ProviderNotice.Decision(p,t,token,store,()->launches++);}
static Z8ProviderInstallIdentity.Decoder decoder(String version){return json->{if(!json.startsWith("fixture"))throw new IOException();return new Z8ProviderInstallIdentity.Receipt("z8-ai-v1","codex",version,"a".repeat(64));};}
static Path setup(Path files,String version)throws Exception{
 Path home=files.resolve("z8/homes/"+P), bin=home.resolve(".local/bin"), target=home.resolve(".local/share/z8/ai/codex/"+version+"-package-v1/bin/codex");
 Files.createDirectories(bin);Files.createDirectories(target.getParent());Files.writeString(target,"not executable; must never execute");Files.writeString(target.getParent().getParent().resolve("receipt.json"),"fixture "+version);
 Files.deleteIfExists(bin.resolve("codex"));Files.createSymbolicLink(bin.resolve("codex"),bin.relativize(target));return target;
}
static Z8ProviderInstallIdentity identity(Path files,String v){return Z8ProviderInstallIdentity.inspect(files,P,"codex",decoder(v));}
public static void main(String[] args)throws Exception{
switch(args[0]){
case "pending": {
 Z8ProviderNotice.PendingRequests<Object> pending=new Z8ProviderNotice.PendingRequests<>();Object owner=new Object();int[] cancelled={0,0};
 Z8ProviderNotice.PendingRequests.Ticket first=pending.begin(owner,"prepared-original",()->cancelled[0]++);eq(true,pending.current(owner,first));
 eq(null,pending.begin(owner,"prepared-original",()->cancelled[0]++));eq(0,cancelled[0]);eq(true,pending.current(owner,first));
 eq(null,pending.begin(owner,"prepared-new",()->cancelled[1]++));eq(1,cancelled[1]);eq(0,cancelled[0]);eq(true,pending.current(owner,first));
 Memory store=new Memory();Z8ProviderNotice.Decision original=decision(P,"claude","original-install",store);original.continueOnce();eq(1,launches);pending.remove(owner,first);
 Z8ProviderNotice.PendingRequests.Ticket next=pending.begin(owner,"prepared-new",()->cancelled[1]++);eq(true,pending.current(owner,next));
 pending.remove(owner,first);eq(true,pending.current(owner,next));pending.remove(owner,next);eq(false,pending.current(owner,next));break;}
case "decision": {
 Memory s=new Memory();Z8ProviderNotice.Decision c=decision(P,"codex","install-a",s);eq(true,c.needsNotice());c.cancel();c.continueOnce();eq(0,launches);eq(0,s.m.size());
 Z8ProviderNotice.Decision a=decision(P,"codex","install-a",s);eq(true,a.continueOnce());a.continueOnce();eq(1,launches);eq(false,decision(P,"codex","install-a",s).needsNotice());
 Z8ProviderNotice.Decision next=decision(P,"codex","install-a",s);next.alreadyAcknowledged();next.alreadyAcknowledged();eq(2,launches);break;}
case "scope": {
 Memory s=new Memory();decision(P,"codex","v1-file-a",s).continueOnce();eq(true,decision(Q,"codex","v1-file-a",s).needsNotice());eq(true,decision(P,"claude","v1-file-a",s).needsNotice());
 eq(true,decision(P,"codex","v2-file-a",s).needsNotice());eq(true,decision(P,"codex","v1-file-b",s).needsNotice());s.m.put(P+":codex","0:v1-file-a");eq(true,decision(P,"codex","v1-file-a",s).needsNotice());
 for(String action:Arrays.asList("", "python","git","node","setup-tools","github-auth","hooks-codex"))eq(false,Z8ProviderNotice.applies(action));eq(false,Z8ProviderNotice.applies(null));eq(true,Z8ProviderNotice.applies("claude"));break;}
case "unknown": {
 Memory s=new Memory();Z8ProviderNotice.Decision d=decision(P,"codex","",s);eq(false,d.continueOnce());eq(1,launches);eq(0,s.m.size());eq(true,decision(P,"codex","",s).needsNotice());
 s.fail=true;d=decision(P,"codex","known",s);eq(true,d.needsNotice());eq(false,d.continueOnce());eq(2,launches);eq(0,s.m.size());break;}
case "identity": {
 Path files=Files.createTempDirectory("z8-notice-identity").toRealPath();Path target=setup(files,"0.160.0");Z8ProviderInstallIdentity a=identity(files,"0.160.0");eq("0.160.0",a.version);eq(64,a.fingerprint.length());eq(a.fingerprint,identity(files,"0.160.0").fingerprint);
 Files.setLastModifiedTime(target,FileTime.fromMillis(100000));eq(false,a.fingerprint.equals(identity(files,"0.160.0").fingerprint));
 String before=identity(files,"0.160.0").fingerprint;Files.writeString(target.getParent().getParent().resolve("receipt.json"),"fixture changed");eq(false,before.equals(identity(files,"0.160.0").fingerprint));
 setup(files,"0.169.0");eq("0.169.0",identity(files,"0.169.0").version);eq(false,a.fingerprint.equals(identity(files,"0.169.0").fingerprint));break;}
case "unsafe": {
 Path files=Files.createTempDirectory("z8-notice-unsafe").toRealPath();Path target=setup(files,"0.160.0"), launcher=files.resolve("z8/homes/"+P+"/.local/bin/codex"), receipt=target.getParent().getParent().resolve("receipt.json");
 Files.writeString(receipt,"invalid");eq("",identity(files,"0.160.0").fingerprint);Files.writeString(receipt,"fixture"+"x".repeat(131072));eq("",identity(files,"0.160.0").fingerprint);
 Files.delete(receipt);Path outside=Files.createTempFile("outside", ".txt");Files.writeString(outside,"fixture");Files.createSymbolicLink(receipt,outside);eq("",identity(files,"0.160.0").fingerprint);
 Files.delete(launcher);Files.createSymbolicLink(launcher,outside);eq("",identity(files,"0.160.0").fingerprint);Files.delete(launcher);Files.writeString(launcher,"custom client");eq("",identity(files,"0.160.0").fingerprint);
 eq("",Z8ProviderInstallIdentity.inspect(files,"../escape","codex",decoder("0.160.0")).fingerprint);break;}
case "store": {
 Path files=Files.createTempDirectory("z8-notice-store").toRealPath(), folder=files.resolve("z8/projects/"+P);Files.createDirectories(folder.resolve("source"));Files.writeString(folder.resolve("source/keep.txt"),"own source");
 Z8ProviderNotice.Store s=Z8ProviderInstallIdentity.store(files);decision(P,"codex","one",s).continueOnce();eq(false,decision(P,"codex","one",s).needsNotice());eq(true,Files.exists(folder.resolve("provider-disclosure.properties")));eq("own source",Files.readString(folder.resolve("source/keep.txt")));
 Files.createDirectories(files.resolve("z8/projects/"+Q+"/source"));eq(true,decision(Q,"codex","one",s).needsNotice());
 Files.delete(folder.resolve("provider-disclosure.properties"));Path outside=Files.createTempFile("outside", ".properties");Files.writeString(outside,"preserve=yes");Files.createSymbolicLink(folder.resolve("provider-disclosure.properties"),outside);eq(true,decision(P,"codex","one",s).needsNotice());eq(false,decision(P,"codex","one",s).continueOnce());eq("preserve=yes",Files.readString(outside));
 Files.delete(folder.resolve("provider-disclosure.properties"));Files.delete(folder.resolve("source/keep.txt"));Files.delete(folder.resolve("source"));Files.delete(folder);eq(true,decision(P,"codex","one",s).needsNotice());break;}
case "links": {
 Z8Text.setLanguage("en");String en=Z8ProviderNotice.explanation("codex");eq(true,en.contains("diagnostics"));eq(true,en.contains("does not accept a provider contract"));eq(true,Z8ProviderNotice.boundary().contains("not automatically intercepted"));
 List<Z8ProviderNotice.Link> links=Z8ProviderNotice.links("codex","codex-cli 0.160.0");eq(6,links.size());eq(true,links.get(4).url.endsWith("rust-v0.160.0/LICENSE"));eq(true,links.get(5).url.endsWith("rust-v0.160.0/NOTICE"));eq(true,Z8ProviderNotice.links("codex","custom").get(4).url.endsWith("main/LICENSE"));
 for(String tool:Arrays.asList("codex","claude"))for(Z8ProviderNotice.Link l:Z8ProviderNotice.links(tool,"1.2.3"))eq(true,l.url.startsWith("https://"));
 eq(5,Z8ProviderNotice.links("claude","2.1.311").size());Z8Text.setLanguage("ko");eq(true,Z8ProviderNotice.explanation("claude").contains("제공자 계약에 동의하는 것이 아닙니다"));eq(false,en.equals(Z8ProviderNotice.explanation("codex")));break;}
default:throw new AssertionError(args[0]);}
System.out.println("PASS "+args[0]);
}}
'''
