package com.termux.app;

import android.content.Context;

import com.termux.shared.termux.TermuxConstants;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/** Android host execution only. Linux guest programs stay under PRoot's ELF loader. */
public final class Z8RuntimeLauncher {
    public static final Object EXECUTION_LOCK = new Object();
    public static final String LINKER = "/system/bin/linker64";
    private static final String LOADER = "libproot-loader.so";
    private Z8RuntimeLauncher() {}

    /** argv after the system linker's argv[0]; no shell interpolation or guest rewriting. */
    static boolean requiresSystemLinker(int apiLevel) { return apiLevel >= 29; }

    static List<String> hostArguments(String executable, List<String> arguments, int apiLevel) throws IOException {
        Path prefix = TermuxConstants.TERMUX_PREFIX_DIR.toPath().toAbsolutePath().normalize();
        Path target = Paths.get(executable).toAbsolutePath().normalize();
        if (!Paths.get(executable).isAbsolute() || !target.startsWith(prefix)
                || !target.toString().equals(executable))
            throw new IOException(Z8Text.text("The Android executable is outside the app runtime.", "Android 실행 파일이 앱 실행 기반 밖에 있습니다."));
        List<String> result = new ArrayList<>(arguments.size() + 1);
        if (requiresSystemLinker(apiLevel)) result.add(executable);
        result.addAll(arguments);
        return result;
    }

    static boolean isGuestCommand(String executable, String[] arguments) {
        String proot = new java.io.File(TermuxConstants.TERMUX_PREFIX_DIR, "bin/proot").getAbsolutePath();
        return proot.equals(executable) || (LINKER.equals(executable) && arguments != null
            && arguments.length > 0 && proot.equals(arguments[0]));
    }

    /** Refresh on every launch: Android changes nativeLibraryDir after an APK update. */
    static void ensureAppLibraries(Context context) throws IOException {
        String directory = context.getApplicationInfo().nativeLibraryDir;
        if (directory == null) throw new IOException(Z8Text.text("The bundled runtime loader path is missing.", "앱에 포함된 실행 로더 경로가 없습니다."));
        installAppLibraries(context.getFilesDir().toPath(), Paths.get(directory));
    }

    static void installAppLibraries(Path files, Path nativeDirectory) throws IOException {
        Path loader = nativeDirectory.resolve(LOADER);
        if (!nativeDirectory.isAbsolute() || !Files.isDirectory(nativeDirectory)
                || !Files.isRegularFile(loader, LinkOption.NOFOLLOW_LINKS) || !Files.isExecutable(loader))
            throw new IOException(Z8Text.text("Could not verify the bundled Linux runtime loader.", "앱에 포함된 Linux 실행 로더를 확인하지 못했습니다."));
        Path link = files.resolve("applib");
        if (Files.exists(link, LinkOption.NOFOLLOW_LINKS)) {
            if (!Files.isSymbolicLink(link))
                throw new IOException(Z8Text.text("A file already exists at the runtime loader path. It has been preserved.", "실행 로더 경로에 기존 파일이 있습니다. 파일을 보존했습니다."));
            if (Files.readSymbolicLink(link).equals(nativeDirectory)) return;
        }
        Path pending = files.resolve(".z8-applib-" + UUID.randomUUID());
        try {
            Files.createSymbolicLink(pending, nativeDirectory);
            Files.move(pending, link, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } finally { Files.deleteIfExists(pending); }
    }
}
