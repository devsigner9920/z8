package com.termux.app;

import android.content.Context;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Set;

/** App-owned prepared Linux base. It is never registered as a user project. */
public final class Z8EnvironmentTemplate {
    public static final String ID = "00000000-0000-4000-8000-000000000008";
    private static final long MAX_BYTES = 4L * 1024 * 1024 * 1024;
    private static final int MAX_ITEMS = 200000;
    private Z8EnvironmentTemplate() {}

    public static boolean isTemplate(String id) { return ID.equals(id); }

    /** The service may provision this owner before any user project exists. */
    public static Z8Projects.Project project(Context context, String id) throws IOException {
        if (!isTemplate(id)) return new Z8Projects(context).open(id);
        File source = Z8Guest.privateDirectory(context, "z8/template/source");
        return new Z8Projects.Project(ID, Z8Text.text("Initial setup", "초기 설정"), source, 0);
    }

    static File rootfs(Context context) throws IOException {
        return Z8Files.directory(context.getFilesDir().getCanonicalFile(), "z8/environments/" + ID + "/rootfs");
    }

    /** Cheap durable receipt check; preparation itself performs executable probes. */
    public static boolean isReady(Context context) {
        try {
            Z8Guest.marker(rootfs(context), ID);
            return Z8Guest.standardProfilePrepared(context, ID);
        } catch (IOException invalid) { return false; }
    }

    /** Never permit a user shell or login command to modify the shared base. */
    static boolean allows(String[] command) {
        return command != null && command.length == 2 && "/bin/bash".equals(command[0])
            && ("/usr/local/lib/z8/setup-tools.sh".equals(command[1])
                || "/usr/local/lib/z8/probe-tools.sh".equals(command[1]));
    }

    private static final class Entry {
        final Path relative;
        final boolean directory;
        final Path link;
        final long size;
        final Set<PosixFilePermission> permissions;
        Entry(Path relative, BasicFileAttributes attrs, Path path) throws IOException {
            this.relative = relative; directory = attrs.isDirectory(); size = attrs.isRegularFile() ? attrs.size() : 0;
            link = attrs.isSymbolicLink() ? Files.readSymbolicLink(path) : null;
            permissions = link == null ? Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS) : null;
        }
    }

    /** Copy bytes and links into a new owned stage; no inode or writable HOME is shared. */
    static void copyRootfs(File prepared, File staging, Z8GuestArchive.Progress progress) throws IOException {
        final Path source = Z8Files.directory(prepared, "").toPath();
        final Path target = Z8Files.directory(staging, "").toPath();
        if (source.startsWith(target) || target.startsWith(source)) throw new IOException(Z8Text.text("The environment copy paths overlap.", "환경 복사 경로가 겹칩니다."));
        try (java.nio.file.DirectoryStream<Path> children = Files.newDirectoryStream(target)) {
            if (children.iterator().hasNext()) throw new IOException(Z8Text.text("The destination for the environment copy is not empty.", "환경 복사 대상이 비어 있지 않습니다."));
        }
        progress.update(-1, Z8Text.text("Checking the installed environment size…", "설치된 개발 환경의 크기를 확인하고 있습니다."));
        final List<Entry> entries = new ArrayList<>();
        final long[] total = {0};
        Files.walkFileTree(source, new SimpleFileVisitor<Path>() {
            private void add(Path path, BasicFileAttributes attrs) throws IOException {
                interrupted();
                if (!attrs.isDirectory() && !attrs.isRegularFile() && !attrs.isSymbolicLink())
                    throw new IOException(Z8Text.text("The environment contains special files that cannot be copied.", "개발 환경에 복사할 수 없는 특수 파일이 있습니다."));
                Entry entry = new Entry(source.relativize(path), attrs, path);
                entries.add(entry); total[0] += entry.size;
                if (entries.size() > MAX_ITEMS || total[0] > MAX_BYTES)
                    throw new IOException(Z8Text.text("The prepared environment exceeds the copy size limit.", "준비된 개발 환경이 복사 크기 제한을 초과했습니다."));
            }
            @Override public FileVisitResult preVisitDirectory(Path path, BasicFileAttributes attrs) throws IOException {
                if (path.equals(source)) return FileVisitResult.CONTINUE;
                add(path, attrs);
                return emptyMount(source.relativize(path).toString()) ? FileVisitResult.SKIP_SUBTREE : FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult visitFile(Path path, BasicFileAttributes attrs) throws IOException {
                if (!source.relativize(path).toString().equals(Z8GuestArchive.MARKER)) add(path, attrs);
                return FileVisitResult.CONTINUE;
            }
        });
        if (staging.getUsableSpace() < total[0] + 128L * 1024 * 1024)
            throw new IOException(Z8Text.text("There is not enough storage to copy the project environment.", "프로젝트 환경을 복사할 저장 공간이 부족합니다."));
        long copied = 0; int count = 0, lastProgress = -1;
        byte[] buffer = new byte[65536];
        for (Entry entry : entries) {
            interrupted();
            Path original = source.resolve(entry.relative);
            Path destination = target.resolve(entry.relative);
            if (entry.directory) {
                Files.createDirectory(destination);
            } else if (entry.link != null) {
                Files.createSymbolicLink(destination, portableLink(source, original, entry.link));
            } else {
                long fileBytes = 0;
                try (InputStream input = Files.newInputStream(original, LinkOption.NOFOLLOW_LINKS);
                        OutputStream output = Files.newOutputStream(destination, StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)) {
                    int size;
                    while ((size = input.read(buffer)) != -1) {
                        interrupted(); fileBytes += size; copied += size;
                        if (fileBytes > entry.size) throw new IOException(Z8Text.text("The source environment changed during copying.", "복사 중 원본 환경이 변경되었습니다."));
                        output.write(buffer, 0, size);
                        int percent = total[0] == 0 ? 0 : (int) (copied * 90 / total[0]);
                        if (percent != lastProgress) {
                            lastProgress = percent;
                            progress.update(percent, Z8Text.text("Copying environment · ", "개발 환경 복사 · ") + count + " / " + entries.size() + Z8Text.text(" files", " 파일"));
                        }
                    }
                }
                if (fileBytes != entry.size) throw new IOException(Z8Text.text("A source file changed size.", "원본 환경의 파일 크기가 변경되었습니다."));
                Files.setPosixFilePermissions(destination, entry.permissions);
            }
            count++;
        }
        // Apply directory modes only after descendants exist (some are read-only).
        for (int index = entries.size() - 1; index >= 0; index--) {
            Entry entry = entries.get(index);
            if (entry.directory) Files.setPosixFilePermissions(target.resolve(entry.relative), entry.permissions);
        }
        progress.update(90, Z8Text.text("Copying environment · ", "개발 환경 복사 · ") + count + " / " + entries.size() + Z8Text.text(" files", " 파일"));
    }

    private static boolean emptyMount(String relative) {
        return Arrays.asList("workspace", "z8/home", "tmp", "proc", "sys", "dev/shm", "run/z8/attention").contains(relative);
    }

    static Path portableLink(Path root, Path original, Path link) throws IOException {
        if (link.isAbsolute()) {
            Path normalized = link.normalize();
            // PRoot's link2symlink can encode an absolute Android host rootfs path.
            // Relocate it within this copy rather than retaining a shared target.
            if (normalized.startsWith(root)) return original.getParent().relativize(normalized);
            if (normalized.startsWith("/data") || normalized.startsWith("/storage") || normalized.startsWith("/sdcard"))
                throw new IOException(Z8Text.text("A base environment link points outside app storage.", "기본 환경의 링크가 앱 외부 저장소를 가리킵니다."));
            return link; // Guest-absolute links such as /etc/alternatives are preserved.
        }
        if (!original.getParent().resolve(link).normalize().startsWith(root))
            throw new IOException(Z8Text.text("A relative link points outside the base environment.", "기본 환경 밖을 가리키는 상대 링크가 있습니다."));
        return link;
    }

    private static void interrupted() throws IOException {
        if (Thread.currentThread().isInterrupted()) throw new IOException(Z8Text.text("Environment copying was interrupted.", "환경 복사가 중단되었습니다."));
    }
}
