package com.termux.app;

import android.content.Context;
import android.os.Build;

import com.termux.BuildConfig;
import com.termux.shared.android.PackageUtils;
import com.termux.shared.errors.Error;
import com.termux.shared.termux.TermuxConstants;
import com.termux.shared.termux.file.TermuxFileUtils;
import com.termux.shared.termux.shell.command.environment.TermuxShellEnvironment;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InterruptedIOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.FileVisitResult;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/** Headless native runtime preparation. The calling service owns work and progress. */
public final class Z8Bootstrap {
    public interface Progress { void onProgress(int percent, String message); }
    private static final String RECEIPT = ".z8-bootstrap.sha256";
    private static final String STAGE_OWNER = "bootstrap-extraction";
    private static final String BACKUP_OWNER = "bootstrap-early-prefix";
    private static final String UPGRADE_OWNER = "bootstrap-version-upgrade";
    private static final String RECREATED_OWNER = "bootstrap-regenerated-startup";
    private static final int MAX_ARCHIVE = 512 * 1024 * 1024;
    private static final long MAX_EXPANDED = 2L * 1024 * 1024 * 1024;
    private static final int MAX_ENTRIES = 100000;
    private static final int MAX_LINKS = 16 * 1024 * 1024;
    private static final Set<String> EARLY_FILES = new HashSet<>(Arrays.asList(
        "etc/termux/termux.env", "etc/termux/termux.env.tmp", "etc/profile.d/z8-managed.sh"));
    private static final Set<String> EARLY_DIRS = new HashSet<>(Arrays.asList(
        "", "tmp", "etc", "etc/termux", "etc/profile.d"));

    private Z8Bootstrap() {}

    /** Blocking; call off the main thread. Progress is delivered on the calling thread. */
    public static synchronized void ensure(Context context, Progress listener) throws Exception {
        interrupted();
        Context app = context.getApplicationContext();
        if (!BuildConfig.Z8_HAS_BOOTSTRAP) throw new IOException(Z8Text.text("This APK does not include the runtime.", "이 APK에는 실행 기반이 포함되어 있지 않습니다."));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N && !PackageUtils.isCurrentUserThePrimaryUser(app))
            throw new IOException(Z8Text.text("Install this runtime under the device's primary Android user.", "이 실행 기반은 기기의 기본 Android 사용자에서 설치할 수 있습니다."));
        Error accessible = TermuxFileUtils.isTermuxFilesDirectoryAccessible(app, true, true);
        if (accessible != null) throw new IOException(Error.getMinimalErrorString(accessible));
        Path prefix = TermuxConstants.TERMUX_PREFIX_DIR.toPath();
        // Android exposes /data/data and /data/user/0 aliases whose canonical
        // strings need not agree. Compare the actual directory inode instead.
        if (!Files.isSameFile(prefix.getParent(), app.getFilesDir().toPath()))
            throw new IOException(Z8Text.text("The app storage path does not match the runtime build path.", "앱 저장 경로와 실행 기반의 빌드 경로가 일치하지 않습니다."));
        Z8RuntimeLauncher.ensureAppLibraries(app);
        recoverUpgrade(app, prefix);
        recoverEarlyPrefix(prefix);
        Z8InstallStaging.recover(prefix.getParent(), ".z8-bootstrap-", STAGE_OWNER);
        progress(listener, 0, Z8Text.text("Checking the runtime…", "실행 기반을 확인하고 있습니다."));
        boolean upgrading = false;
        if (Files.exists(prefix, LinkOption.NOFOLLOW_LINKS)) {
            if (installed(prefix)) { progress(listener, 100, Z8Text.text("The runtime is ready.", "실행 기반이 준비되었습니다.")); return; }
            try { earlyPrefix(prefix); }
            catch (IOException notEarlyPrefix) {
                verifyUpgrade(app, prefix);
                synchronized (Z8RuntimeLauncher.EXECUTION_LOCK) { Z8ProjectProcesses.requireRuntimeIdle(); }
                upgrading = true;
            }
        }

        byte[] archive = TermuxInstaller.loadZipBytes();
        if (archive == null || archive.length == 0 || archive.length > MAX_ARCHIVE)
            throw new IOException(Z8Text.text("The runtime image size is invalid.", "실행 기반 이미지 크기가 올바르지 않습니다."));
        String expected = BuildConfig.Z8_BOOTSTRAP_SHA256;
        if (expected == null || !expected.matches("[a-f0-9]{64}") || !expected.equals(hash(archive)))
            throw new IOException(Z8Text.text("The runtime image SHA-256 does not match.", "실행 기반 이미지의 SHA-256이 일치하지 않습니다."));
        progress(listener, 8, Z8Text.text("Runtime image verified.", "실행 기반 이미지 검증을 마쳤습니다."));

        Path stage = Z8InstallStaging.create(prefix.getParent(), ".z8-bootstrap-", STAGE_OWNER);
        Path backup = null;
        String backupOwner = upgrading ? UPGRADE_OWNER : BACKUP_OWNER;
        boolean published = false;
        try {
            Z8GuestArchive.mode(stage, 0700);
            extract(archive, stage, prefix, listener);
            executable(stage, "bin/bash"); executable(stage, "bin/proot");
            Files.write(stage.resolve(RECEIPT), (expected + "\n").getBytes(StandardCharsets.UTF_8),
                java.nio.file.StandardOpenOption.CREATE_NEW, java.nio.file.StandardOpenOption.WRITE);
            interrupted();
            synchronized (Z8RuntimeLauncher.EXECUTION_LOCK) {
                if (Files.exists(prefix, LinkOption.NOFOLLOW_LINKS)) {
                    if (upgrading) { Z8ProjectProcesses.requireRuntimeIdle(); verifyUpgrade(app, prefix); }
                    else earlyPrefix(prefix);
                    backup = Z8InstallStaging.reserve(prefix.getParent(),
                        upgrading ? ".z8-bootstrap-upgrade-" : ".z8-bootstrap-previous-", backupOwner);
                    Files.move(prefix, backup);
                    if (!upgrading) earlyPrefix(backup);
                    preserveEarlyFiles(backup, stage);
                } else if (upgrading) throw Z8BootstrapUpgrade.preserved();
                if (Files.exists(prefix, LinkOption.NOFOLLOW_LINKS))
                    throw new IOException(Z8Text.text("The runtime path changed during installation. Existing files have been preserved.", "설치 중 실행 기반 경로가 변경되었습니다. 기존 파일을 보존했습니다."));
                // Sibling rename publishes the verified image while all app launch paths are excluded.
                Files.move(stage, prefix);
                published = true;
            }
            TermuxShellEnvironment.writeEnvironmentToFile(app);
            progress(listener, 100, Z8Text.text("The runtime is ready.", "실행 기반이 준비되었습니다."));
        } finally {
            synchronized (Z8RuntimeLauncher.EXECUTION_LOCK) {
                if (!published && backup != null && !Files.exists(prefix, LinkOption.NOFOLLOW_LINKS))
                    Files.move(backup, prefix);
            }
            Z8InstallStaging.discard(stage, STAGE_OWNER);
            if (backup != null && (published || !Files.exists(backup, LinkOption.NOFOLLOW_LINKS)))
                Z8InstallStaging.discard(backup, backupOwner);
        }
    }

    private static void verifyUpgrade(Context context, Path prefix) throws IOException {
        try (java.io.InputStream input = context.getAssets().open(Z8BootstrapUpgrade.ASSET)) {
            Z8BootstrapUpgrade.verify(prefix, input, EARLY_FILES, EARLY_DIRS);
        }
    }

    /** A killed rename either restores the verified old image or accepts the complete new image. */
    private static void recoverUpgrade(Context context, Path prefix) throws IOException {
        synchronized (Z8RuntimeLauncher.EXECUTION_LOCK) {
            for (Path backup : Z8InstallStaging.owned(prefix.getParent(), ".z8-bootstrap-upgrade-", UPGRADE_OWNER)) {
                if (!Files.exists(backup, LinkOption.NOFOLLOW_LINKS)) {
                    Z8InstallStaging.discard(backup, UPGRADE_OWNER); continue;
                }
                verifyUpgrade(context, backup);
                Z8ProjectProcesses.requireRuntimeIdle();
                if (!Files.exists(prefix, LinkOption.NOFOLLOW_LINKS)) Files.move(backup, prefix);
                else if (!installed(prefix)) {
                    // Application.onCreate can regenerate termux.env before
                    // this recovery runs. Accept only that known early tree.
                    // Preserve it separately because its generated values can
                    // differ from the old tree; never merge by overwriting.
                    earlyPrefix(prefix);
                    Path regenerated = Z8InstallStaging.reserve(prefix.getParent(),
                        ".z8-preserved-startup-", RECREATED_OWNER);
                    Files.move(prefix, regenerated);
                    Files.move(backup, prefix);
                }
                Z8InstallStaging.discard(backup, UPGRADE_OWNER);
            }
        }
    }

    /** Recover a kill between moving the small startup prefix and publishing the image. */
    private static void recoverEarlyPrefix(Path prefix) throws IOException {
        for (Path backup : Z8InstallStaging.owned(prefix.getParent(), ".z8-bootstrap-previous-", BACKUP_OWNER)) {
            if (!Files.exists(backup, LinkOption.NOFOLLOW_LINKS)) {
                Z8InstallStaging.discard(backup, BACKUP_OWNER); continue;
            }
            earlyPrefix(backup); // Never erase a backup containing unknown or linked files.
            if (!Files.exists(prefix, LinkOption.NOFOLLOW_LINKS)) {
                Files.move(backup, prefix);
                Z8InstallStaging.discard(backup, BACKUP_OWNER); continue;
            }
            if (!installed(prefix)) earlyPrefix(prefix);
            boolean conflict = false;
            for (String name : EARLY_FILES) {
                Path source = backup.resolve(name);
                if (!Files.exists(source, LinkOption.NOFOLLOW_LINKS)) continue;
                Path target = Z8GuestArchive.checked(prefix.toFile(), name);
                if (!Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
                    Files.createDirectories(target.getParent()); Files.copy(source, target);
                } else if (!Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS)
                        || !java.util.Arrays.equals(Files.readAllBytes(source), Files.readAllBytes(target))) conflict = true;
            }
            // If startup regenerated a different value, preserve both copies for
            // inspection; an installation retry must not choose one by deleting it.
            if (!conflict) Z8InstallStaging.discard(backup, BACKUP_OWNER);
        }
    }

    private static boolean installed(Path prefix) throws IOException {
        if (!Files.isDirectory(prefix, LinkOption.NOFOLLOW_LINKS))
            throw new IOException(Z8Text.text("The existing runtime path is not a directory. Files have been preserved.", "기존 실행 기반 경로가 폴더가 아닙니다. 파일을 보존했습니다."));
        Path receipt = prefix.resolve(RECEIPT);
        if (!Files.isRegularFile(receipt, LinkOption.NOFOLLOW_LINKS) || Files.size(receipt) > 128) return false;
        String stored = new String(Files.readAllBytes(receipt), StandardCharsets.UTF_8).trim();
        if (!BuildConfig.Z8_BOOTSTRAP_SHA256.equals(stored)) return false;
        try { executable(prefix, "bin/bash"); executable(prefix, "bin/proot"); return true; }
        catch (IOException invalid) { return false; }
    }

    private static void executable(Path root, String name) throws IOException {
        Path file = Z8GuestArchive.checked(root.toFile(), name);
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || !Files.isExecutable(file))
            throw new IOException(Z8Text.text("Cannot verify runtime executable ", "실행 기반의 ") + name + Z8Text.text(".", " 실행 파일을 확인하지 못했습니다."));
    }

    /** Only known startup-generated files and empty startup folders may precede bootstrap. */
    private static void earlyPrefix(Path prefix) throws IOException {
        if (!Files.isDirectory(prefix, LinkOption.NOFOLLOW_LINKS)) throw preserved();
        Files.walkFileTree(prefix, new SimpleFileVisitor<Path>() {
            @Override public FileVisitResult preVisitDirectory(Path path, BasicFileAttributes attributes) throws IOException {
                if (!EARLY_DIRS.contains(prefix.relativize(path).toString())) throw preserved();
                return FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult visitFile(Path path, BasicFileAttributes attributes) throws IOException {
                if (!attributes.isRegularFile() || !EARLY_FILES.contains(prefix.relativize(path).toString())) throw preserved();
                return FileVisitResult.CONTINUE;
            }
        });
    }
    private static IOException preserved() {
        return new IOException(Z8Text.text("The existing runtime is incomplete or uses a different version. Files have been preserved; automatic replacement has stopped.", "기존 실행 기반이 불완전하거나 다른 버전입니다. 파일을 보존했으며 자동 덮어쓰기를 중단했습니다."));
    }

    private static void preserveEarlyFiles(Path old, Path stage) throws IOException {
        for (String name : EARLY_FILES) {
            Path source = old.resolve(name);
            if (!Files.exists(source, LinkOption.NOFOLLOW_LINKS)) continue;
            Path target = Z8GuestArchive.checked(stage.toFile(), name);
            Files.createDirectories(target.getParent());
            Files.copy(source, target); // An image conflict is an error, never an overwrite.
        }
        if (Files.isDirectory(old.resolve("tmp"), LinkOption.NOFOLLOW_LINKS)) Files.createDirectories(stage.resolve("tmp"));
    }

    private static void extract(byte[] archive, Path stage, Path prefix, Progress listener) throws Exception {
        Set<String> names = new HashSet<>();
        byte[] links = null;
        long expanded = 0;
        ByteArrayInputStream input = new ByteArrayInputStream(archive);
        try (ZipInputStream zip = new ZipInputStream(input, StandardCharsets.UTF_8)) {
            ZipEntry entry; byte[] buffer = new byte[65536];
            int previousProgress = -1;
            while ((entry = zip.getNextEntry()) != null) {
                interrupted();
                String name = Z8GuestArchive.path(entry.getName(), entry.isDirectory());
                if (!names.add(name) || names.size() > MAX_ENTRIES || name.equals(RECEIPT) || name.startsWith(RECEIPT + "/"))
                    throw new IOException(Z8Text.text("The runtime image contains duplicate or reserved paths.", "실행 기반 이미지에 중복되거나 예약된 경로가 있습니다."));
                Path target = Z8GuestArchive.checked(stage.toFile(), name);
                if (entry.isDirectory()) {
                    Files.createDirectories(target);
                    if (zip.read() != -1) throw new IOException(Z8Text.text("A directory entry contains unexpected data.", "폴더 항목에 예상하지 않은 내용이 있습니다."));
                } else {
                    Files.createDirectories(target.getParent());
                    ByteArrayOutputStream linkContent = name.equals("SYMLINKS.txt") ? new ByteArrayOutputStream() : null;
                    try (OutputStream output = linkContent == null ? Files.newOutputStream(target,
                            java.nio.file.StandardOpenOption.CREATE_NEW, java.nio.file.StandardOpenOption.WRITE,
                            LinkOption.NOFOLLOW_LINKS) : linkContent) {
                        int count;
                        while ((count = zip.read(buffer)) != -1) {
                            interrupted(); expanded += count;
                            if (expanded > MAX_EXPANDED || linkContent != null && linkContent.size() + count > MAX_LINKS)
                                throw new IOException(Z8Text.text("The expanded runtime image is too large.", "실행 기반 이미지의 압축 해제 크기가 너무 큽니다."));
                            output.write(buffer, 0, count);
                        }
                    }
                    if (linkContent != null) links = linkContent.toByteArray();
                    else Z8GuestArchive.mode(target, name.startsWith("bin/") || name.startsWith("libexec/")
                        || name.equals("lib/apt/apt-helper") || name.startsWith("lib/apt/methods/") ? 0700 : 0600);
                }
                zip.closeEntry();
                int value = 8 + (int) (77L * (archive.length - input.available()) / archive.length);
                if (value != previousProgress) { progress(listener, value, Z8Text.text("Preparing runtime files…", "실행 기반 파일을 준비하고 있습니다.")); previousProgress = value; }
            }
        }
        if (links == null || links.length == 0) throw new IOException(Z8Text.text("The runtime image has no link manifest.", "실행 기반 이미지의 링크 목록이 없습니다."));
        Map<String, String> mappings = links(links, names, prefix);
        progress(listener, 90, Z8Text.text("Applying runtime links and permissions…", "실행 기반 링크와 권한을 적용하고 있습니다."));
        for (Map.Entry<String, String> link : mappings.entrySet()) {
            interrupted();
            Path target = Z8GuestArchive.checked(stage.toFile(), link.getKey());
            Files.createDirectories(target.getParent());
            Files.createSymbolicLink(target, java.nio.file.Paths.get(link.getValue()));
        }
    }

    private static Map<String, String> links(byte[] bytes, Set<String> names, Path prefix) throws IOException {
        String contents;
        try { contents = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString(); }
        catch (Exception invalid) { throw new IOException(Z8Text.text("The link manifest has an invalid character encoding.", "링크 목록의 문자 인코딩이 올바르지 않습니다."), invalid); }
        Map<String, String> result = new LinkedHashMap<>();
        for (String line : contents.split("\n", -1)) {
            if (line.isEmpty()) continue;
            int arrow = line.indexOf('←');
            if (arrow <= 0 || arrow != line.lastIndexOf('←') || arrow == line.length() - 1) throw new IOException(Z8Text.text("The link manifest format is invalid.", "링크 목록 형식이 올바르지 않습니다."));
            String destination = Z8GuestArchive.path(line.substring(arrow + 1), false);
            String target = line.substring(0, arrow);
            if (target.length() > 4096 || target.indexOf('\\') >= 0) throw new IOException(Z8Text.text("Invalid link path.", "잘못된 링크 경로입니다."));
            for (int i = 0; i < target.length(); i++) if (Character.isISOControl(target.charAt(i))) throw new IOException(Z8Text.text("Invalid link path.", "잘못된 링크 경로입니다."));
            if (target.startsWith("/")) {
                String root = prefix.toString() + "/";
                if (!target.startsWith(root)) throw new IOException(Z8Text.text("A link points outside the runtime.", "실행 기반 밖으로 나가는 링크입니다."));
                // Preserve final-prefix semantics while allowing complete staging validation.
                Path parent = java.nio.file.Paths.get(destination).getParent();
                if (parent == null) parent = java.nio.file.Paths.get("");
                target = parent.relativize(java.nio.file.Paths.get(target.substring(root.length()))).toString();
            }
            if (destination.equals(RECEIPT) || destination.equals("SYMLINKS.txt") || names.contains(destination)
                    || result.put(destination, target) != null || result.size() + names.size() > MAX_ENTRIES)
                throw new IOException(Z8Text.text("A link overlaps an existing image entry.", "링크가 기존 이미지 항목과 겹칩니다."));
        }
        Set<String> ancestors = new HashSet<>();
        for (String path : names) ancestors(path, ancestors);
        for (String path : result.keySet()) ancestors(path, ancestors);
        for (String path : result.keySet()) {
            if (ancestors.contains(path)) throw new IOException(Z8Text.text("An image entry is nested under a link.", "링크 아래에 이미지 항목이 있습니다."));
            resolve(path, result);
        }
        return result;
    }

    private static void ancestors(String path, Set<String> result) {
        int slash = path.indexOf('/');
        while (slash >= 0) { result.add(path.substring(0, slash)); slash = path.indexOf('/', slash + 1); }
    }
    private static void resolve(String path, Map<String, String> links) throws IOException {
        Deque<String> pending = new ArrayDeque<>(Arrays.asList(path.split("/", -1)));
        Deque<String> resolved = new ArrayDeque<>(); int followed = 0;
        while (!pending.isEmpty()) {
            String component = pending.removeFirst();
            if (component.isEmpty() || component.equals(".")) continue;
            if (component.equals("..")) {
                if (resolved.isEmpty()) throw new IOException(Z8Text.text("A link points outside the runtime.", "실행 기반 밖으로 나가는 링크입니다."));
                resolved.removeLast(); continue;
            }
            resolved.addLast(component);
            String target = links.get(String.join("/", resolved));
            if (target != null) {
                if (++followed > 128) throw new IOException(Z8Text.text("A runtime link contains a cycle.", "순환하는 실행 기반 링크입니다."));
                resolved.removeLast();
                String[] parts = target.split("/", -1);
                for (int i = parts.length - 1; i >= 0; i--) pending.addFirst(parts[i]);
            }
        }
    }

    private static String hash(byte[] bytes) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        for (int offset = 0; offset < bytes.length; offset += 65536) {
            interrupted(); digest.update(bytes, offset, Math.min(65536, bytes.length - offset));
        }
        StringBuilder result = new StringBuilder();
        for (byte value : digest.digest()) result.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
        return result.toString();
    }
    private static void interrupted() throws InterruptedIOException {
        if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException(Z8Text.text("Runtime preparation was interrupted.", "실행 기반 준비가 중단되었습니다."));
    }
    private static void progress(Progress listener, int percent, String message) throws InterruptedIOException {
        interrupted(); if (listener != null) listener.onProgress(percent, message);
    }
}
