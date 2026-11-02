"""Actual template copier filesystem behavior; no Android device or host packages."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EnvironmentTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jdk = ROOT / '.local/jdk/Contents/Home/bin'
        javac = str(jdk / 'javac') if (jdk / 'javac').exists() else shutil.which('javac')
        cls.java = str(jdk / 'java') if (jdk / 'java').exists() else shutil.which('java')
        if not javac or not cls.java:
            raise unittest.SkipTest('A JDK is required')
        cls.temp = tempfile.TemporaryDirectory(prefix='z8-template-tests-')
        cls.directory = Path(cls.temp.name).resolve()
        sources = []
        for name, text in STUBS.items():
            path = cls.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            sources.append(str(path))
        actual = ROOT / 'overlay/app/src/main/java/com/termux/app'
        sources += [str(actual / name) for name in ('Z8Files.java', 'Z8Projects.java', 'Z8GuestArchive.java', 'Z8EnvironmentTemplate.java')]
        result = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), '-encoding', 'UTF-8', '-d', str(cls.directory), *sources], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def scenario(self, name):
        result = subprocess.run([self.java, '-cp', str(self.directory), 'com.termux.app.TemplateProbe', name,
                                 str(self.directory / name)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_template_owner_is_hidden_and_cannot_run_user_commands(self): self.scenario('hidden')
    def test_clone_has_independent_files_and_empty_home_source(self): self.scenario('independent')
    def test_host_absolute_link_is_relocated_to_copied_backing_file(self): self.scenario('links')
    def test_unknown_host_links_and_escaping_relative_links_fail(self): self.scenario('bad-links')
    def test_existing_or_nested_destination_is_never_overwritten(self): self.scenario('destination')
    def test_interruption_never_modifies_original_and_progress_is_measured(self): self.scenario('interrupt')


STUBS = {
    'android/content/Context.java': '''package android.content;
        public abstract class Context { public abstract java.io.File getFilesDir(); }''',
    'com/termux/app/Z8Guest.java': '''package com.termux.app;
        import java.io.*; import java.nio.file.*;
        final class Z8Guest {
            static File privateDirectory(android.content.Context context,String relative)throws IOException {
                Path current=context.getFilesDir().toPath();
                for(String part:relative.split("/")){current=current.resolve(Z8Files.name(part));
                    if(Files.isSymbolicLink(current))throw new IOException("linked private path");
                    if(!Files.exists(current))Files.createDirectory(current);}
                return current.toFile();
            }
            static void marker(File root,String id)throws IOException {
                if(!Files.readString(root.toPath().resolve(Z8GuestArchive.MARKER)).equals(id))throw new IOException("marker");
            }
            static boolean standardProfilePrepared(android.content.Context context,String id){return false;}
        }''',
    'com/termux/app/TemplateProbe.java': r'''package com.termux.app;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
public class TemplateProbe {
    interface Action {void run()throws Exception;}
    static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
    static void deny(Action action)throws Exception{try{action.run();}catch(IOException expected){return;}throw new AssertionError("Must refuse");}
    static void file(Path root,String relative,String content)throws Exception {
        Path path=root.resolve(relative);Files.createDirectories(path.getParent());Files.writeString(path,content);
    }
    static class Ctx extends android.content.Context {
        final File root;Ctx(Path root){this.root=root.toFile();}public File getFilesDir(){return root;}
    }
    static Path base(Path root)throws Exception {
        Path source=Files.createDirectory(root.resolve("base"));
        file(source,"usr/bin/bash","original-bash"); source.resolve("usr/bin/bash").toFile().setExecutable(true);
        Files.createSymbolicLink(source.resolve("bin"),Path.of("usr/bin"));
        file(source,"etc/z8/tools.ready","z8-tools-v2\n");
        file(source,Z8GuestArchive.MARKER,Z8EnvironmentTemplate.ID);
        file(source,"z8/home/.credentials","must not copy");
        file(source,"workspace/user-code","must not copy");
        file(source,"tmp/transient","must not copy");
        return source;
    }
    public static void main(String[] args)throws Exception {
        Path root=Files.createDirectories(Path.of(args[1]));Ctx context=new Ctx(root);
        if(args[0].equals("hidden")) {
            Z8Projects.Project owner=Z8EnvironmentTemplate.project(context,Z8EnvironmentTemplate.ID);
            check(new Z8Projects(context).list().isEmpty(),"Template is not a visible project");
            check(!owner.source.toPath().startsWith(root.resolve("z8/projects")),"Private source is outside projects");
            Z8Projects.Project user=new Z8Projects(context).create("real");
            check(Z8EnvironmentTemplate.project(context,user.id).source.equals(user.source),"User project remains real");
            for(String[] command:new String[][]{{"/bin/bash","--login"},{"/bin/bash","-c","anything"},
                    {"/usr/bin/python3","-c","anything"},{"/bin/bash","/usr/local/lib/z8/guest-task.sh","github-auth"}})
                check(!Z8EnvironmentTemplate.allows(command),"No user commands in template");
            check(Z8EnvironmentTemplate.allows(new String[]{"/bin/bash","/usr/local/lib/z8/setup-tools.sh"}),"Setup permitted");
            check(Z8EnvironmentTemplate.allows(new String[]{"/bin/bash","/usr/local/lib/z8/probe-tools.sh"}),"Probe permitted");
            return;
        }
        Path source=base(root), target=Files.createDirectory(root.resolve("stage"));
        List<Integer> percents=new ArrayList<>();
        Z8GuestArchive.Progress progress=(percent,detail)->percents.add(percent);
        switch(args[0]) {
        case "independent":
            Files.createLink(source.resolve("usr/bin/bash-copy"),source.resolve("usr/bin/bash"));
            Z8EnvironmentTemplate.copyRootfs(source.toFile(),target.toFile(),progress);
            check(!Files.exists(target.resolve(Z8GuestArchive.MARKER)),"Template project marker is not copied");
            check(Files.readString(target.resolve("etc/z8/tools.ready")).equals("z8-tools-v2\n"),"Validated tools receipt copied");
            check(!Files.isSameFile(source.resolve("usr/bin/bash"),target.resolve("usr/bin/bash")),"No shared inode with template");
            check(!Files.isSameFile(target.resolve("usr/bin/bash"),target.resolve("usr/bin/bash-copy")),"Regular source hardlinks become independent files");
            Files.writeString(target.resolve("usr/bin/bash"),"project edit");
            check(Files.readString(source.resolve("usr/bin/bash")).equals("original-bash"),"Template immutable to project edits");
            check(target.resolve("usr/bin/bash").toFile().canExecute(),"Executable mode preserved");
            for(String name:new String[]{"z8/home","workspace","tmp"})try(var list=Files.list(target.resolve(name))){check(list.count()==0,"Empty private mount "+name);}
            check(Files.readSymbolicLink(target.resolve("bin")).equals(Path.of("usr/bin")),"Relative links preserved");
            check(percents.get(percents.size()-1)==90,"Measured copy completes before marker publication");
            break;
        case "links":
            file(source,"usr/bin/.l2s.backing","original backing");
            Files.createSymbolicLink(source.resolve("usr/bin/tool"),source.resolve("usr/bin/.l2s.backing"));
            Files.createSymbolicLink(source.resolve("usr/bin/guest-absolute"),Path.of("/etc/alternatives/tool"));
            Z8EnvironmentTemplate.copyRootfs(source.toFile(),target.toFile(),progress);
            check(Files.readSymbolicLink(target.resolve("usr/bin/tool")).equals(Path.of(".l2s.backing")),"Host link converted relative");
            Files.writeString(target.resolve("usr/bin/tool"),"own backing");
            check(Files.readString(source.resolve("usr/bin/.l2s.backing")).equals("original backing"),"No shared backing through absolute link");
            check(Files.readSymbolicLink(target.resolve("usr/bin/guest-absolute")).equals(Path.of("/etc/alternatives/tool")),"Guest absolute link retained");
            break;
        case "bad-links":
            deny(()->Z8EnvironmentTemplate.portableLink(source,source.resolve("etc/link"),Path.of("../../outside")));
            deny(()->Z8EnvironmentTemplate.portableLink(source,source.resolve("etc/link"),Path.of("/data/user/0/other-app/files")));
            break;
        case "destination":
            file(target,"user-file","preserve");
            deny(()->Z8EnvironmentTemplate.copyRootfs(source.toFile(),target.toFile(),progress));
            check(Files.readString(target.resolve("user-file")).equals("preserve"),"Existing destination untouched");
            Path nested=Files.createDirectory(source.resolve("nested"));
            deny(()->Z8EnvironmentTemplate.copyRootfs(source.toFile(),nested.toFile(),progress));
            break;
        case "interrupt":
            Thread.currentThread().interrupt();
            try {deny(()->Z8EnvironmentTemplate.copyRootfs(source.toFile(),target.toFile(),progress));}
            finally {Thread.interrupted();}
            check(Files.readString(source.resolve("usr/bin/bash")).equals("original-bash"),"Interrupt preserves source");
            try(var list=Files.list(target)){check(list.count()==0,"Interrupt before copy leaves stage empty");}
            Z8EnvironmentTemplate.copyRootfs(source.toFile(),target.toFile(),progress);
            check(percents.contains(-1)&&percents.get(percents.size()-1)==90,"Measured progress phases");
            break;
        default: throw new AssertionError(args[0]);
        }
        System.out.println("PASS: "+args[0]);
    }
}'''
}
