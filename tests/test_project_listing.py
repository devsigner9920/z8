"""Damaged records must not hide unrelated projects or mutate recoverable files."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProjectListingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').is_file() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').is_file() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temp = tempfile.TemporaryDirectory(prefix='z8-project-listing-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.build = Path(cls.temp.name)
        context = cls.build / 'android/content/Context.java'
        context.parent.mkdir(parents=True)
        context.write_text('package android.content; public abstract class Context { public abstract java.io.File getFilesDir(); }')
        probe = cls.build / 'ProjectListingProbe.java'
        probe.write_text(PROBE)
        source = ROOT / 'overlay/app/src/main/java/com/termux/app'
        result = subprocess.run([javac, '-encoding', 'UTF-8', '-d', str(cls.build), str(context),
            str(source / 'Z8Files.java'), str(source / 'Z8Projects.java'), str(probe)],
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def scenario(self, name):
        with tempfile.TemporaryDirectory(prefix='z8-owned-listing-') as directory:
            result = subprocess.run([self.java, '-cp', str(self.build), 'com.termux.app.ProjectListingProbe',
                str(Path(directory).resolve()), name], capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn('PASS ' + name, result.stdout)

    def test_missing_source_and_metadata_do_not_hide_healthy_projects(self): self.scenario('partial')
    def test_linked_records_and_metadata_are_reported_without_following_or_writing(self): self.scenario('links')
    def test_malformed_properties_raise_checked_error_for_recovery_callers(self): self.scenario('malformed')
    def test_manual_repair_reappears_only_after_validating_preserved_files(self): self.scenario('repair')
    def test_invalid_records_count_toward_bounded_scan_limit(self): self.scenario('limit')


PROBE = r'''
package com.termux.app;
import java.io.*;import java.nio.file.*;import java.util.*;
public class ProjectListingProbe {
interface Task {void run() throws Exception;}
static void check(boolean yes,String message){if(!yes)throw new AssertionError(message);}
static void denied(Task task)throws Exception{try{task.run();}catch(IOException expected){return;}throw new AssertionError("expected checked storage error");}
static Z8Projects.Problem problem(Z8Projects.Listing list,String id){for(Z8Projects.Problem p:list.problems)if(p.id.equals(id))return p;throw new AssertionError("problem missing "+id);}
public static void main(String[] args)throws Exception{
Path root=Paths.get(args[0]),storage=root.resolve("projects");
Z8Projects projects=new Z8Projects(storage.toFile());
Z8Projects.Project healthy=projects.create("건강한 프로젝트");
Path code=healthy.source.toPath().resolve("preserve.py");Files.writeString(code,"print('preserve')\n");
switch(args[1]){
case "partial":{
 Z8Projects.Project missingSource=projects.create("소스 복구 필요");Files.delete(missingSource.source.toPath());
 String incomplete=UUID.randomUUID().toString();Files.createDirectory(storage.resolve(incomplete));
 Z8Projects.Listing list=projects.scan();
 check(list.projects.size()==1&&list.projects.get(0).id.equals(healthy.id),"healthy record must stay available");
 check(list.problems.size()==2,"each invalid record must be shown separately");
 check(problem(list,missingSource.id).name.equals("소스 복구 필요"),"safe name should survive source damage");
 check(problem(list,incomplete).name.contains(incomplete.substring(0,8)),"unknown metadata needs stable identity");
 check(!Files.exists(missingSource.source.toPath())&&!Files.exists(storage.resolve(incomplete).resolve("source")),"listing must not recreate sources");
 denied(projects::list);denied(()->projects.open(missingSource.id));break;}
case "links":{
 Path outside=root.resolve("outside");Files.createDirectory(outside);Path witness=outside.resolve("project.properties");
 Files.writeString(witness,"name=Do not expose linked metadata\nopened=0\n");
 String linked=UUID.randomUUID().toString();Files.createSymbolicLink(storage.resolve(linked),outside);
 Z8Projects.Project metadataLink=projects.create("metadata link");Path meta=metadataLink.source.toPath().getParent().resolve("project.properties");
 Files.delete(meta);Files.createSymbolicLink(meta,witness);
 Z8Projects.Listing list=projects.scan();check(list.projects.size()==1,"links must not hide good projects");
 check(list.problems.size()==2,"linked roots and metadata reported");
 check(!problem(list,linked).name.contains("expose")&&!problem(list,metadataLink.id).name.contains("expose"),"no linked metadata reads");
 check(Files.readString(witness).equals("name=Do not expose linked metadata\nopened=0\n"),"external file remains untouched");
 check(Files.isSymbolicLink(meta)&&Files.isSymbolicLink(storage.resolve(linked)),"links remain available for manual repair");break;}
case "malformed":{
 Z8Projects.Project broken=projects.create("broken");Path meta=broken.source.toPath().getParent().resolve("project.properties");
 String invalid="name=broken\\uZZZZ\n";Files.writeString(meta,invalid);
 denied(()->projects.open(broken.id));denied(()->projects.touch(broken.id));denied(()->projects.delete(broken.id));
 Z8Projects.Listing list=projects.scan();check(list.projects.size()==1&&list.problems.size()==1,"malformed escape isolated");
 check(Files.readString(meta).equals(invalid)&&Files.isDirectory(broken.source.toPath()),"failed open/delete must preserve malformed record");break;}
case "repair":{
 Z8Projects.Project broken=projects.create("복구된 프로젝트");Path meta=broken.source.toPath().getParent().resolve("project.properties");
 byte[] original=Files.readAllBytes(meta);Files.delete(meta);
 Z8Projects.Listing before=projects.scan();check(before.projects.size()==1&&before.problems.size()==1,"missing metadata isolated");
 Files.write(meta,original);Z8Projects.Listing after=projects.scan();
 check(after.projects.size()==2&&after.problems.isEmpty(),"manual repair must restore normal listing");
 check(projects.open(broken.id).name.equals("복구된 프로젝트"),"repaired record independently validates");
 check(before.problems.size()==1,"published listing snapshot remains stable");break;}
case "limit":{
 for(int i=0;i<1000;i++)Files.createDirectory(storage.resolve(UUID.randomUUID().toString()));
 denied(projects::scan);break;}
default:throw new AssertionError(args[1]);}
check(Files.readString(code).equals("print('preserve')\n"),"unrelated project bytes unchanged");
System.out.println("PASS "+args[1]);
}}
'''


if __name__ == '__main__': unittest.main()
