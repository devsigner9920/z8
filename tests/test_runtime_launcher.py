"""Execute target36 launch and APK loader-update contracts without device data."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RuntimeLauncherTests(unittest.TestCase):
    def test_arguments_and_apk_loader_update_preserve_user_files(self):
        from test_bootstrap import STUBS
        jdk = ROOT / ".local/jdk/Contents/Home/bin"
        with tempfile.TemporaryDirectory(prefix="z8-launcher-tests-") as temporary:
            folder = Path(temporary)
            sources = []
            for name in ("android/content/Context.java", "android/content/pm/ApplicationInfo.java", "android/content/res/AssetManager.java",
                         "com/termux/shared/termux/TermuxConstants.java"):
                file = folder / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(STUBS[name])
                sources.append(str(file))
            probe = folder / "LauncherProbe.java"
            probe.write_text(PROBE)
            result = subprocess.run([str(jdk / "javac"), str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), "-d", str(folder), *sources,
                str(ROOT / "overlay/app/src/main/java/com/termux/app/Z8RuntimeLauncher.java"), str(probe)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(jdk / "java"), "-cp", str(folder), "com.termux.app.LauncherProbe",
                                     str(folder / "fixture")], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PASS launch and loader", result.stdout)


PROBE = r'''
package com.termux.app;
import java.nio.file.*;
import java.util.*;
import java.io.*;
import com.termux.shared.termux.TermuxConstants;
public class LauncherProbe {
    interface Action { void run() throws Exception; }
    static void check(boolean value) { if(!value) throw new AssertionError(); }
    static void denied(Action action) throws Exception {
        try { action.run(); } catch(IOException expected) { return; }
        throw new AssertionError("Expected preserved-file failure");
    }
    static Path nativeDir(Path path) throws Exception {
        Files.createDirectories(path);
        Files.writeString(path.resolve("libproot-loader.so"),"APK loader");
        path.resolve("libproot-loader.so").toFile().setExecutable(true,true); return path;
    }
    public static void main(String[] args) throws Exception {
        Path root=Paths.get(args[0]); Files.createDirectories(root);
        Path files=Files.createDirectory(root.resolve("files"));
        Path prefix=files.resolve("usr"); TermuxConstants.TERMUX_PREFIX_DIR=prefix.toFile();
        String proot=prefix.resolve("bin/proot").toString();
        List<String> guest=Arrays.asList("-r","a path with spaces","/usr/bin/env","/bin/bash","$literal;argument");
        List<String> wrapped=Z8RuntimeLauncher.hostArguments(proot,guest,36);
        check(wrapped.size()==guest.size()+1 && wrapped.get(0).equals(proot));
        check(wrapped.subList(1,wrapped.size()).equals(guest));
        check(!Z8RuntimeLauncher.requiresSystemLinker(28) && Z8RuntimeLauncher.requiresSystemLinker(29));
        check(Z8RuntimeLauncher.hostArguments(proot,guest,28).equals(guest));
        denied(()->Z8RuntimeLauncher.hostArguments(prefix+"-other/bin/proot",guest,36));
        denied(()->Z8RuntimeLauncher.hostArguments(prefix+"/../guest/bin/bash",guest,36));
        denied(()->Z8RuntimeLauncher.hostArguments("relative",guest,36));
        check(Z8RuntimeLauncher.isGuestCommand(Z8RuntimeLauncher.LINKER,wrapped.toArray(new String[0])));
        check(!Z8RuntimeLauncher.isGuestCommand(Z8RuntimeLauncher.LINKER,new String[]{"/bin/bash"}));
        Path one=nativeDir(root.resolve("install-1/lib")), two=nativeDir(root.resolve("install-2/lib"));
        Z8RuntimeLauncher.installAppLibraries(files,one);
        check(Files.isSameFile(files.resolve("applib/libproot-loader.so"),one.resolve("libproot-loader.so")));
        Z8RuntimeLauncher.installAppLibraries(files,one);
        Z8RuntimeLauncher.installAppLibraries(files,two);
        check(Files.readSymbolicLink(files.resolve("applib")).equals(two));
        check(Files.readString(one.resolve("libproot-loader.so")).equals("APK loader"));
        denied(()->Z8RuntimeLauncher.installAppLibraries(files,root.resolve("missing")));
        check(Files.readSymbolicLink(files.resolve("applib")).equals(two));
        Files.delete(files.resolve("applib")); Files.writeString(files.resolve("applib"),"user data");
        denied(()->Z8RuntimeLauncher.installAppLibraries(files,one));
        check(Files.readString(files.resolve("applib")).equals("user data"));
        System.out.println("PASS launch and loader");
    }
}
'''
