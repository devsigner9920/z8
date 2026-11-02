"""Exercise the production headless bootstrap installer with filesystem fixtures."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def test_installation_preservation_failure_and_real_archive(self):
        jdk = ROOT / ".local/jdk/Contents/Home/bin"
        javac = str(jdk / "javac") if (jdk / "javac").is_file() else shutil.which("javac")
        java = str(jdk / "java") if (jdk / "java").is_file() else shutil.which("java")
        if not javac or not java:
            self.skipTest("Bootstrap tests require a JDK")
        with tempfile.TemporaryDirectory(prefix="z8-bootstrap-tests-") as temporary:
            directory = Path(temporary)
            files = []
            for name, body in STUBS.items():
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body)
                files.append(str(path))
            probe = directory / "BootstrapProbe.java"
            probe.write_text(PROBE)
            source = ROOT / "overlay/app/src/main/java/com/termux/app"
            compiled = subprocess.run([javac, "-encoding", "UTF-8", "-d", str(directory),
                str(source / "Z8Bootstrap.java"), str(source / "Z8BootstrapUpgrade.java"), str(source / "Z8RuntimeLauncher.java"), str(source / "Z8GuestArchive.java"), str(source / "Z8InstallStaging.java"), str(probe), *files],
                capture_output=True, text=True, timeout=45)
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            args = [java, "-cp", str(directory), "com.termux.app.BootstrapProbe", str(directory / "fixtures")]
            manifests = sorted((ROOT / "artifacts/runtime").glob("*/manifest.json"), key=lambda path: path.stat().st_mtime)
            # Native man-page links include WINDOW/window. Android supports both;
            # a default macOS APFS directory cannot faithfully extract that ZIP.
            (directory / "case-probe-a").write_text("a")
            case_sensitive = not (directory / "case-probe-A").exists()
            if manifests and case_sensitive:
                manifest = json.loads(manifests[-1].read_text())
                args += [str(manifests[-1].parent / manifest["archive"]), manifest["sha256"]]
            tested = subprocess.run(args, capture_output=True, text=True, timeout=60)
            self.assertEqual(0, tested.returncode, tested.stdout + tested.stderr)
            self.assertIn("PASS: headless bootstrap", tested.stdout)
            if manifests and case_sensitive:
                self.assertIn("PASS: real bootstrap extraction", tested.stdout)


STUBS = {
    "android/content/Context.java": """package android.content;
import java.io.File;
public class Context { private final File files; public Context(File files) { this.files=files; }
 public android.content.pm.ApplicationInfo getApplicationInfo() { return new android.content.pm.ApplicationInfo(new File(files,"native").toString()); }
 public android.content.res.AssetManager getAssets() { return new android.content.res.AssetManager(); }
 public Context getApplicationContext() { return this; } public File getFilesDir() { files.mkdirs(); return files; }}""",
    "android/content/pm/ApplicationInfo.java": """package android.content.pm; public class ApplicationInfo {
 public String nativeLibraryDir; public ApplicationInfo(String path) { nativeLibraryDir=path; }}""",
    "android/content/res/AssetManager.java": """package android.content.res; public class AssetManager {
 public static byte[] upgrade; public java.io.InputStream open(String name)throws java.io.IOException {
 if(upgrade==null)throw new java.io.FileNotFoundException(name); return new java.io.ByteArrayInputStream(upgrade); }}""",
    "com/termux/app/Z8ProjectProcesses.java": """package com.termux.app; public class Z8ProjectProcesses {
 public static boolean active; static void requireRuntimeIdle()throws java.io.IOException {
 if(active)throw new java.io.IOException("active process; preserved"); }}""",
    "android/os/Build.java": """package android.os; public class Build {
 public static class VERSION { public static int SDK_INT=37; }
 public static class VERSION_CODES { public static final int N=24; }}""",
    "com/termux/BuildConfig.java": """package com.termux; public class BuildConfig {
 public static boolean Z8_HAS_BOOTSTRAP=true; public static String Z8_BOOTSTRAP_SHA256; }""",
    "com/termux/shared/android/PackageUtils.java": """package com.termux.shared.android;
public class PackageUtils { public static boolean primary=true;
 public static boolean isCurrentUserThePrimaryUser(android.content.Context context) { return primary; }}""",
    "com/termux/shared/errors/Error.java": """package com.termux.shared.errors;
public class Error { public static String getMinimalErrorString(Error error) { return "not accessible"; }}""",
    "com/termux/shared/termux/TermuxConstants.java": """package com.termux.shared.termux;
public class TermuxConstants { public static java.io.File TERMUX_PREFIX_DIR; }""",
    "com/termux/shared/termux/file/TermuxFileUtils.java": """package com.termux.shared.termux.file;
public class TermuxFileUtils { public static boolean accessible=true;
 public static com.termux.shared.errors.Error isTermuxFilesDirectoryAccessible(android.content.Context context,boolean create,boolean permissions) {
 context.getFilesDir(); return accessible ? null : new com.termux.shared.errors.Error(); }}""",
    "com/termux/shared/termux/shell/command/environment/TermuxShellEnvironment.java": """package com.termux.shared.termux.shell.command.environment;
public class TermuxShellEnvironment { public static int writes;
 public static void writeEnvironmentToFile(android.content.Context context) { writes++; }}""",
    "com/termux/app/TermuxInstaller.java": """package com.termux.app;
public class TermuxInstaller { public static byte[] archive; public static int loads;
 public static byte[] loadZipBytes() { loads++; return archive; }}""",
}

PROBE = r'''
package com.termux.app;
import android.content.Context;
import com.termux.BuildConfig;
import com.termux.shared.termux.TermuxConstants;
import com.termux.shared.android.PackageUtils;
import com.termux.shared.termux.file.TermuxFileUtils;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;
import java.util.zip.*;

public class BootstrapProbe {
    static Path base; static Context context; static Path prefix; static int checks;
    interface Action { void run() throws Exception; }
    static byte[] bytes(String value) { return value.getBytes(StandardCharsets.UTF_8); }
    static void check(boolean condition, String message) { if (!condition) throw new AssertionError(message); checks++; }
    static void denied(Action action, String reason) throws Exception {
        try { action.run(); } catch (IOException expected) { checks++; return; }
        throw new AssertionError("Allowed: " + reason);
    }
    static String hash(byte[] input) throws Exception {
        StringBuilder output = new StringBuilder();
        for (byte part : MessageDigest.getInstance("SHA-256").digest(input)) output.append(String.format("%02x", part & 255));
        return output.toString();
    }
    static LinkedHashMap<String, byte[]> content(String links) {
        LinkedHashMap<String, byte[]> files = new LinkedHashMap<>();
        files.put("bin/", bytes("")); files.put("bin/bash", bytes("bash"));
        files.put("bin/proot", bytes("proot")); files.put("SYMLINKS.txt", bytes(links));
        return files;
    }
    static byte[] zip(Map<String, byte[]> files) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(output)) {
            for (Map.Entry<String, byte[]> file : files.entrySet()) {
                zip.putNextEntry(new ZipEntry(file.getKey())); zip.write(file.getValue()); zip.closeEntry();
            }
        }
        return output.toByteArray();
    }
    static void image(Map<String, byte[]> files) throws Exception {
        TermuxInstaller.archive=zip(files); BuildConfig.Z8_BOOTSTRAP_SHA256=hash(TermuxInstaller.archive);
    }
    static void fixture() throws Exception {
        Path files=Files.createTempDirectory(base,"files-"); prefix=files.resolve("usr");
        context=new Context(files.toFile()); TermuxConstants.TERMUX_PREFIX_DIR=prefix.toFile();
        Path loader=files.resolve("native/libproot-loader.so"); Files.createDirectories(loader.getParent());
        Files.write(loader,new byte[]{1}); loader.toFile().setExecutable(true,true);
        TermuxInstaller.loads=0; PackageUtils.primary=true; TermuxFileUtils.accessible=true;
        BuildConfig.Z8_HAS_BOOTSTRAP=true; image(content("bash←bin/sh\n"));
        android.content.res.AssetManager.upgrade=null; Z8ProjectProcesses.active=false;
    }
    static void allowUpgrade() throws Exception {
        StringBuilder manifest=new StringBuilder("z8-bootstrap-upgrade-v1\t"+read(prefix.resolve(".z8-bootstrap.sha256")).trim()+"\n");
        try(var files=Files.walk(prefix)) {
            for(Path path:files.sorted().toList()) {
                String name=prefix.relativize(path).toString(); if(name.isEmpty()||name.equals(".z8-bootstrap.sha256"))continue;
                if(Files.isSymbolicLink(path))manifest.append("L\t\t"+Files.readSymbolicLink(path)+"\t"+name+"\n");
                else if(Files.isDirectory(path))manifest.append("D\t\t\t"+name+"\n");
                else manifest.append("F\t"+Files.size(path)+"\t"+hash(Files.readAllBytes(path))+"\t"+name+"\n");
            }
        }
        android.content.res.AssetManager.upgrade=bytes(manifest.toString());
        var updated=content("bash←bin/sh\n"); updated.put("bin/proot",bytes("new-proot")); image(updated);
    }
    static void ensure() throws Exception { Z8Bootstrap.ensure(context, (p,m) -> {}); }
    static void write(Path path, String value) throws Exception { Files.createDirectories(path.getParent()); Files.write(path,bytes(value)); }
    static String read(Path path) throws Exception { return new String(Files.readAllBytes(path),StandardCharsets.UTF_8); }
    static long stagingCount() throws Exception {
        try (java.util.stream.Stream<Path> entries=Files.list(prefix.getParent())) {
            return entries.filter(path->path.getFileName().toString().startsWith(".z8-bootstrap-")).count();
        }
    }
    public static void main(String[] args) throws Exception {
        base=Paths.get(args[0]); Files.createDirectories(base);
        fixture(); Path home=prefix.getParent().resolve("home/private-key"); write(home,"keep");
        ArrayList<Integer> progress=new ArrayList<>(); Z8Bootstrap.ensure(context,(p,m)->progress.add(p));
        check(Files.isExecutable(prefix.resolve("bin/bash")) && Files.isExecutable(prefix.resolve("bin/proot")),"executables prepared");
        check(Files.isSymbolicLink(prefix.resolve("bin/sh")) && read(prefix.resolve("bin/sh")).equals("bash"),"safe links installed");
        check(read(prefix.resolve(".z8-bootstrap.sha256")).trim().equals(BuildConfig.Z8_BOOTSTRAP_SHA256),"published receipt");
        check(read(home).equals("keep"),"HOME unchanged");
        check(progress.get(0)==0 && progress.get(progress.size()-1)==100,"progress boundaries");
        for(int i=1;i<progress.size();i++) check(progress.get(i)>=progress.get(i-1),"monotonic progress");
        int loads=TermuxInstaller.loads; write(prefix.resolve("custom-package"),"user"); ensure();
        check(TermuxInstaller.loads==loads && read(prefix.resolve("custom-package")).equals("user"),"ready prefix reused without extraction");
        check(stagingCount()==0,"successful temporary cleanup");

        fixture(); ensure(); allowUpgrade(); Path retained=prefix.getParent().resolve("z8/homes/p/.auth"); write(retained,"user-auth");
        write(prefix.resolve("etc/termux/termux.env"),"retained-env"); ensure();
        check(read(prefix.resolve("bin/proot")).equals("new-proot") && read(retained).equals("user-auth"),"allowlisted upgrade preserves project home");
        check(read(prefix.resolve("etc/termux/termux.env")).equals("retained-env") && stagingCount()==0,"managed environment survives upgrade");
        fixture(); ensure(); allowUpgrade(); write(prefix.resolve("bin/proot"),"user-modified"); denied(()->ensure(),"modified runtime");
        check(read(prefix.resolve("bin/proot")).equals("user-modified"),"modified host file preserved");
        fixture(); ensure(); allowUpgrade(); write(prefix.resolve("added-user-data"),"keep"); denied(()->ensure(),"added runtime data");
        check(read(prefix.resolve("added-user-data")).equals("keep"),"added host file preserved");
        fixture(); ensure(); allowUpgrade(); Z8ProjectProcesses.active=true; denied(()->ensure(),"active host or guest process");
        check(read(prefix.resolve("bin/proot")).equals("proot"),"active runtime not replaced");
        Z8ProjectProcesses.active=false; ensure(); check(read(prefix.resolve("bin/proot")).equals("new-proot"),"idle retry upgrades");
        fixture(); ensure(); allowUpgrade();
        denied(()->Z8Bootstrap.ensure(context,(p,m)->{if(p==90)try{write(prefix.resolve("late-user-file"),"keep");}catch(Exception e){throw new RuntimeException(e);}}),"late prefix edit");
        check(read(prefix.resolve("late-user-file")).equals("keep")&&read(prefix.resolve("bin/proot")).equals("proot"),"recheck before rename preserves concurrent edit");
        fixture(); ensure(); allowUpgrade(); Path upgradeBackup=Z8InstallStaging.reserve(prefix.getParent(),".z8-bootstrap-upgrade-","bootstrap-version-upgrade");
        Files.move(prefix,upgradeBackup); ensure();
        check(read(prefix.resolve("bin/proot")).equals("new-proot")&&stagingCount()==0,"killed upgrade rename restores old before retry");
        fixture(); ensure(); write(prefix.resolve("etc/termux/termux.env"),"old-startup-env"); allowUpgrade();
        upgradeBackup=Z8InstallStaging.reserve(prefix.getParent(),".z8-bootstrap-upgrade-","bootstrap-version-upgrade");
        Files.move(prefix,upgradeBackup); write(prefix.resolve("etc/termux/termux.env"),"new-startup-env"); ensure();
        check(read(prefix.resolve("bin/proot")).equals("new-proot"),"cold Application startup does not prevent interrupted-upgrade recovery");
        var regenerated=Z8InstallStaging.owned(prefix.getParent(),".z8-preserved-startup-","bootstrap-regenerated-startup");
        check(regenerated.size()==1 && read(regenerated.get(0).resolve("etc/termux/termux.env")).equals("new-startup-env"),"regenerated startup values retained separately");
        check(read(prefix.resolve("etc/termux/termux.env")).equals("old-startup-env"),"old startup values also survive recovery");
        fixture(); ensure(); allowUpgrade();
        upgradeBackup=Z8InstallStaging.reserve(prefix.getParent(),".z8-bootstrap-upgrade-","bootstrap-version-upgrade");
        Files.move(prefix,upgradeBackup); write(prefix.resolve("unknown-user-file"),"preserve");
        denied(()->ensure(),"unknown new prefix during interrupted upgrade");
        check(read(prefix.resolve("unknown-user-file")).equals("preserve") && Files.exists(upgradeBackup.resolve("bin/proot")),"unknown recreated prefix and original backup both preserved");

        fixture(); Path actualFiles=context.getFilesDir().toPath();
        Path alias=base.resolve("files-alias"); Files.createSymbolicLink(alias,actualFiles);
        prefix=alias.resolve("usr"); TermuxConstants.TERMUX_PREFIX_DIR=prefix.toFile(); ensure();
        check(Files.isExecutable(actualFiles.resolve("usr/bin/proot")),"same filesystem identity accepted through app storage alias");
        fixture(); TermuxConstants.TERMUX_PREFIX_DIR=Files.createTempDirectory(base,"wrong-files-").resolve("usr").toFile();
        denied(()->ensure(),"different app storage identity");

        fixture(); write(prefix.resolve("etc/termux/termux.env"),"env");
        write(prefix.resolve("etc/profile.d/z8-managed.sh"),"profile"); Files.createDirectories(prefix.resolve("tmp"));
        ensure(); check(read(prefix.resolve("etc/termux/termux.env")).equals("env"),"early environment preserved");
        check(read(prefix.resolve("etc/profile.d/z8-managed.sh")).equals("profile"),"early managed profile preserved");
        check(Files.isDirectory(prefix.resolve("tmp")) && stagingCount()==0,"empty early tmp preserved");

        fixture(); write(prefix.resolve("etc/termux/termux.env"),"original");
        LinkedHashMap<String,byte[]> collision=content("bash←bin/sh\n"); collision.put("etc/termux/termux.env",bytes("image")); image(collision);
        denied(()->ensure(),"image conflicts with an early file after prefix backup");
        check(read(prefix.resolve("etc/termux/termux.env")).equals("original") && stagingCount()==0,"publication failure restores original prefix");
        fixture(); write(prefix.resolve("etc/termux/termux.env"),"before");
        denied(()->Z8Bootstrap.ensure(context,(p,m)-> { if(p==90) try { write(prefix.resolve("new-user-file"),"keep"); }
            catch(Exception e) { throw new RuntimeException(e); } }),"prefix changes while image extracts");
        check(read(prefix.resolve("new-user-file")).equals("keep") && read(prefix.resolve("etc/termux/termux.env")).equals("before"),"concurrent unknown file preserved");
        check(stagingCount()==0,"conflicting extraction cleaned");

        fixture(); write(prefix.resolve("user-file"),"keep"); denied(()->ensure(),"unknown existing prefix");
        check(read(prefix.resolve("user-file")).equals("keep") && TermuxInstaller.loads==0,"invalid existing prefix untouched");
        fixture(); write(prefix.resolve("tmp/user-file"),"keep"); denied(()->ensure(),"nonempty unknown tmp");
        check(read(prefix.resolve("tmp/user-file")).equals("keep"),"unknown tmp never erased");
        fixture(); Path outside=Files.createTempDirectory(base,"outside-"); write(outside.resolve("keep"),"safe");
        Files.createSymbolicLink(prefix,outside); denied(()->ensure(),"prefix symlink");
        check(read(outside.resolve("keep")).equals("safe"),"symlink destination preserved");
        fixture(); Files.createDirectories(prefix.resolve("etc")); Files.createSymbolicLink(prefix.resolve("etc/termux"),outside);
        denied(()->ensure(),"early nested symlink"); check(read(outside.resolve("keep")).equals("safe"),"nested target preserved");

        fixture(); ensure(); Files.delete(prefix.resolve("bin/proot")); denied(()->ensure(),"receipt without executable proot");
        check(Files.isRegularFile(prefix.resolve("bin/bash")),"partial installed prefix preserved");
        fixture(); BuildConfig.Z8_BOOTSTRAP_SHA256="0".repeat(64); denied(()->ensure(),"hash mismatch");
        check(!Files.exists(prefix) && stagingCount()==0,"hash checked before extraction");
        fixture(); BuildConfig.Z8_HAS_BOOTSTRAP=false; denied(()->ensure(),"diagnostic build");
        fixture(); PackageUtils.primary=false; denied(()->ensure(),"secondary Android user");
        fixture(); TermuxFileUtils.accessible=false; denied(()->ensure(),"inaccessible files dir");

        String[] hostile={"../../escape←bin/out\n", "/outside←bin/out\n", "b←a\na←b\n", "bin←a\nbash←a/sh\n", "bin←bin\n", "bin←.z8-bootstrap.sha256\n", ".←a\na/../outside←b\n"};
        for(String links:hostile) { fixture(); image(content(links)); denied(()->ensure(),"hostile links: "+links); check(!Files.exists(prefix) && stagingCount()==0,"no partial publish"); }
        fixture(); LinkedHashMap<String,byte[]> invalid=content("bash←bin/sh\n"); invalid.put("../escape",bytes("no")); image(invalid);
        denied(()->ensure(),"zip traversal"); check(!Files.exists(prefix.getParent().resolve("escape")),"no traversal file");
        fixture(); invalid=content("bash←bin/sh\n"); invalid.put(".z8-bootstrap.sha256",bytes("spoof")); image(invalid);
        denied(()->ensure(),"reserved marker");
        fixture(); invalid=content("bash←bin/sh\n"); invalid.remove("bin/proot"); image(invalid); denied(()->ensure(),"missing proot");
        check(!Files.exists(prefix) && stagingCount()==0,"executable validated before publish");
        image(content("bash←bin/sh\n")); ensure(); check(Files.isExecutable(prefix.resolve("bin/proot")),"explicit retry after failed extraction");
        fixture(); image(content(prefix.toString()+"/bin/bash←bin/sh\n")); ensure();
        check(read(prefix.resolve("bin/sh")).equals("bash"),"absolute in-prefix link normalized safely");
        fixture(); image(content(prefix.toString()+"/../../escape←bin/sh\n")); denied(()->ensure(),"absolute dotdot link escape");

        fixture(); write(prefix.resolve("etc/termux/termux.env"),"before");
        try { denied(()->Z8Bootstrap.ensure(context,(p,m)->{ if(p>=8) Thread.currentThread().interrupt(); }),"interrupted install"); }
        finally { Thread.interrupted(); }
        check(read(prefix.resolve("etc/termux/termux.env")).equals("before") && stagingCount()==0,"interruption preserves early prefix");
        ensure(); check(Files.isExecutable(prefix.resolve("bin/proot")),"retry after interruption");
        fixture(); ExecutorService pool=Executors.newFixedThreadPool(2);
        try { Future<?> one=pool.submit(()->{try{ensure();}catch(Exception e){throw new RuntimeException(e);}});
              Future<?> two=pool.submit(()->{try{ensure();}catch(Exception e){throw new RuntimeException(e);}});
              one.get(); two.get(); }
        finally { pool.shutdownNow(); }
        check(TermuxInstaller.loads==1 && stagingCount()==0,"concurrent ensure installs once");

        // Simulate process death by abandoning durable ownership and extraction state.
        fixture(); Path interruptedStage=Z8InstallStaging.create(prefix.getParent(),".z8-bootstrap-","bootstrap-extraction");
        write(interruptedStage.resolve("partial/bin"),"partial");
        ensure(); check(!Files.exists(interruptedStage) && stagingCount()==0,"cold retry cleans abandoned bootstrap extraction");
        Path orphan=Z8InstallStaging.reserve(prefix.getParent(),".z8-bootstrap-","bootstrap-extraction");
        ensure(); check(stagingCount()==0,"kill between ownership and directory creation is recovered on warm open");

        fixture(); Path backup=Z8InstallStaging.reserve(prefix.getParent(),".z8-bootstrap-previous-","bootstrap-early-prefix");
        write(prefix.resolve("etc/profile.d/z8-managed.sh"),"retained"); Files.move(prefix,backup);
        ensure(); check(read(prefix.resolve("etc/profile.d/z8-managed.sh")).equals("retained") && stagingCount()==0,"kill after early prefix rename restores startup files");

        fixture(); backup=Z8InstallStaging.reserve(prefix.getParent(),".z8-bootstrap-previous-","bootstrap-early-prefix");
        write(backup.resolve("etc/profile.d/z8-managed.sh"),"retained");
        write(prefix.resolve("etc/termux/termux.env"),"regenerated");
        ensure(); check(read(prefix.resolve("etc/profile.d/z8-managed.sh")).equals("retained") && read(prefix.resolve("etc/termux/termux.env")).equals("regenerated") && stagingCount()==0,"recreated startup prefix merges only missing startup files");

        fixture(); backup=Z8InstallStaging.reserve(prefix.getParent(),".z8-bootstrap-previous-","bootstrap-early-prefix");
        write(backup.resolve("etc/termux/termux.env"),"old"); write(prefix.resolve("etc/termux/termux.env"),"new");
        ensure(); check(read(backup.resolve("etc/termux/termux.env")).equals("old") && read(prefix.resolve("etc/termux/termux.env")).equals("new"),"conflicting startup values both survive recovery");

        fixture(); Path environment=Files.createDirectories(prefix.getParent().resolve("z8/environments/project"));
        Path published=environment.resolve("rootfs"); write(published.resolve("user-package"),"keep");
        Path source=prefix.getParent().resolve("z8/projects/project/source/main.py"); write(source,"source");
        Path guestHome=prefix.getParent().resolve("z8/homes/project/.bashrc"); write(guestHome,"home");
        outside=Files.createTempDirectory(base,"recovery-outside-"); write(outside.resolve("keep"),"safe");
        Path own=Z8InstallStaging.create(environment,".install-","rootfs:project"); write(own.resolve("read-only/partial"),"partial");
        Files.createSymbolicLink(own.resolve("outside"),outside); Z8GuestArchive.mode(own.resolve("read-only"),0500);
        Path wrong=Z8InstallStaging.create(environment,".install-","rootfs:another"); write(wrong.resolve("keep"),"wrong owner");
        Path legacy=environment.resolve(".install-"+UUID.randomUUID()); write(legacy.resolve("keep"),"unmarked");
        Path linked=Z8InstallStaging.reserve(environment,".install-","rootfs:project"); Files.createSymbolicLink(linked,outside);
        Path linkedReceipt=environment.resolve(".install-"+UUID.randomUUID()); Files.createDirectory(linkedReceipt);
        Files.createSymbolicLink(linkedReceipt.resolveSibling(linkedReceipt.getFileName()+".owner"),wrong.resolveSibling(wrong.getFileName()+".owner"));
        Z8InstallStaging.recover(environment,".install-","rootfs:project");
        check(!Files.exists(own) && read(outside.resolve("keep")).equals("safe"),"owned partial tree removed without following nested links");
        check(Files.isSymbolicLink(linked) && Files.isDirectory(linkedReceipt),"linked root and linked ownership receipt preserved");
        check(read(wrong.resolve("keep")).equals("wrong owner") && read(legacy.resolve("keep")).equals("unmarked"),"other owner and unmarked directories preserved");
        check(read(published.resolve("user-package")).equals("keep") && read(source).equals("source") && read(guestHome).equals("home"),"published rootfs, project source and HOME untouched");
        Path beforePublish=Z8InstallStaging.create(environment,".install-","rootfs:project"); write(beforePublish.resolve("ready"),"ready");
        Path afterPublish=environment.resolve("published-new"); Files.move(beforePublish,afterPublish);
        Z8InstallStaging.recover(environment,".install-","rootfs:project");
        check(read(afterPublish.resolve("ready")).equals("ready") && !Files.exists(beforePublish.resolveSibling(beforePublish.getFileName()+".owner")),"kill after publication only removes obsolete ownership receipt");
        System.out.println("PASS: headless bootstrap ("+checks+" checks)");
        if(args.length==3) {
            fixture(); TermuxInstaller.archive=Files.readAllBytes(Paths.get(args[1])); BuildConfig.Z8_BOOTSTRAP_SHA256=args[2];
            ensure(); check(Files.isExecutable(prefix.resolve("bin/bash")) && Files.isExecutable(prefix.resolve("bin/proot")),"real binaries executable");
            check(stagingCount()==0,"real temporary cleanup");
            System.out.println("PASS: real bootstrap extraction "+args[2]);
        }
    }
}
'''


if __name__ == "__main__":
    unittest.main()
