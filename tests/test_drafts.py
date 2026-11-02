"""Exercise durable draft recovery independently of Android lifecycle timing."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class DraftRecoveryTests(unittest.TestCase):
    def test_durable_recovery_and_conflict_preservation(self):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            temporary = str(directory)
            probe = directory / 'DraftProbe.java'
            probe.write_text(PROBE)
            sources = ROOT / 'overlay/app/src/main/java/com/termux/app'
            result = subprocess.run([str(jdk/'javac'), '-encoding','UTF-8','-d',temporary,
                str(sources/'Z8DraftStore.java'),str(sources/'Z8Files.java'),str(probe)], capture_output=True,text=True)
            self.assertEqual(0,result.returncode,result.stderr)
            result = subprocess.run([str(jdk/'java'),'-cp',temporary,'com.termux.app.DraftProbe',temporary],capture_output=True,text=True)
            self.assertEqual(0,result.returncode,result.stdout+result.stderr)
            self.assertIn('PASS durable drafts',result.stdout)

PROBE=r'''
package com.termux.app;
import java.io.*;
import java.nio.file.*;
import java.util.UUID;
public class DraftProbe {
    static void check(boolean value) { if (!value) throw new AssertionError(); }
    interface Action { void run() throws Exception; }
    static void denied(Action action) throws Exception { try { action.run(); } catch(IOException ok) { return; } throw new AssertionError("must reject"); }
    public static void main(String[] args) throws Exception {
        File files = new File(args[0], "files"); files.mkdirs();
        File source = new File(args[0], "source"); source.mkdirs();
        Z8Files.create(source,"","한글.txt",false);
        Z8Files.Document base = Z8Files.read(source,"한글.txt");
        Z8DraftStore store = new Z8DraftStore(files);
        String project = UUID.randomUUID().toString(), other = UUID.randomUUID().toString();
        check(store.read(project)==null);
        store.save(project,new Z8DraftStore.Draft("한글.txt","수정\n=:#\\\uD83D\uDC99",base.version,base.text,5));
        Z8DraftStore.Draft recovered = new Z8DraftStore(files).read(project);
        check(recovered.text.equals("수정\n=:#\\\uD83D\uDC99") && recovered.selection==5 && recovered.version.equals(base.version));
        check(recovered.baseline.equals(base.text) && !recovered.text.equals(recovered.baseline));
        check(store.read(other)==null && Z8Files.read(source,"한글.txt").text.isEmpty());
        Z8Files.save(source,"한글.txt",base.version,"AI external change");
        denied(()->Z8Files.save(source,recovered.path,recovered.version,recovered.text));
        check(store.read(project).text.equals(recovered.text));
        store.save(project,new Z8DraftStore.Draft("한글.txt","newest",base.version,base.text,100));
        check(store.read(project).text.equals("newest") && store.read(project).selection==6);
        denied(()->store.save("../escape",recovered));
        denied(()->store.save(project,new Z8DraftStore.Draft("../outside","x",base.version,base.text,0)));
        denied(()->store.save(project,new Z8DraftStore.Draft("한글.txt","한".repeat(Z8Files.MAX_TEXT_BYTES),base.version,base.text,0)));
        check(store.read(project).text.equals("newest"));
        store.clear(project); check(store.read(project)==null);
        store.clear(project);
        Path draft = new File(files,"z8-editor-drafts/"+project+".properties").toPath();
        Files.createSymbolicLink(draft,new File(source,"한글.txt").toPath());
        denied(()->store.save(project,recovered)); denied(()->store.read(project)); denied(()->store.clear(project));
        check(Z8Files.read(source,"한글.txt").text.equals("AI external change"));
        System.out.println("PASS durable drafts: restart, UTF-8, cursor, project scope, conflict, replacement, bounds, clear, symlink");
    }
}
'''
