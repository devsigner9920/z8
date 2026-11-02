package com.termux.app;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

/** Bounded UTF-8 editing inside one source tree. Symlinks are visible, never followed. */
public final class Z8Files {
    public static final int MAX_TEXT_BYTES = 128 * 1024;
    public static final int MAX_ENTRIES = 2000;

    public static final class Entry {
        public final String name;
        public final boolean directory;
        public final boolean link;
        Entry(String name, boolean directory, boolean link) {
            this.name = name; this.directory = directory; this.link = link;
        }
    }

    public static final class Document {
        public final String text;
        public final String version;
        public Document(String text, String version) { this.text = text; this.version = version; }
    }

    public static final class ConflictException extends IOException {
        ConflictException() { super("파일이 다른 작업에서 변경되었습니다. 최신 파일을 확인한 뒤 다시 저장하세요."); }
    }

    private Z8Files() {}

    public static String name(String name) throws IOException {
        if (name == null || name.trim().isEmpty() || name.length() > 120
                || name.equals(".") || name.equals("..") || name.indexOf('/') >= 0
                || name.indexOf('\\') >= 0) throw new IOException("이름은 1~120자이며 / 또는 \\를 포함할 수 없습니다.");
        for (int i = 0; i < name.length(); i++) {
            if (Character.isISOControl(name.charAt(i))) throw new IOException("이름에 제어 문자를 사용할 수 없습니다.");
        }
        return name;
    }

    public static String child(String parent, String child) throws IOException {
        return parent.isEmpty() ? name(child) : parent + "/" + name(child);
    }

    /** A relative path must be lexical, canonical, inside the root and contain no links. */
    private static Path checked(File source, String relative, boolean mustExist) throws IOException {
        Path root = source.toPath().toAbsolutePath().normalize();
        // Reject links in the supplied root and its descendants. Android's /data/data
        // bind alias is not a symlink; callers use Context.getFilesDir() paths.
        Path cursor = root.getRoot();
        for (Path component : root) {
            cursor = cursor.resolve(component);
            if (Files.isSymbolicLink(cursor)) throw new IOException("심볼릭 링크 경로는 열 수 없습니다.");
        }
        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) throw new IOException("프로젝트 폴더가 없습니다.");
        if (relative == null || relative.startsWith("/") || relative.indexOf('\\') >= 0)
            throw new IOException("잘못된 프로젝트 경로입니다.");
        cursor = root;
        if (!relative.isEmpty()) for (String component : relative.split("/", -1)) {
            name(component);
            cursor = cursor.resolve(component);
            if (Files.isSymbolicLink(cursor)) throw new IOException("심볼릭 링크는 열거나 변경할 수 없습니다.");
        }
        if (!cursor.normalize().startsWith(root)
                || !cursor.toFile().getCanonicalFile().toPath().startsWith(root.toFile().getCanonicalFile().toPath()))
            throw new IOException("프로젝트 밖의 경로에 접근할 수 없습니다.");
        if (mustExist && !Files.exists(cursor, LinkOption.NOFOLLOW_LINKS)) throw new IOException("파일 또는 폴더가 없어졌습니다.");
        return cursor;
    }

    public static File directory(File source, String relative) throws IOException {
        Path path = checked(source, relative, true);
        if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) throw new IOException("폴더가 아닙니다.");
        return path.toFile();
    }

    public static List<Entry> list(File source, String relative) throws IOException {
        Path path = directory(source, relative).toPath();
        List<Entry> entries = new ArrayList<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(path)) {
            for (Path item : stream) {
                if (entries.size() >= MAX_ENTRIES) throw new IOException("이 폴더에는 2,000개 넘는 항목이 있습니다. 터미널에서 확인해 주세요.");
                entries.add(new Entry(item.getFileName().toString(),
                    Files.isDirectory(item, LinkOption.NOFOLLOW_LINKS), Files.isSymbolicLink(item)));
            }
        }
        entries.sort(Comparator.comparing((Entry item) -> !item.directory)
            .thenComparing(item -> item.name, String.CASE_INSENSITIVE_ORDER));
        return entries;
    }

    public static void create(File source, String parent, String name, boolean directory) throws IOException {
        directory(source, parent);
        Path path = checked(source, child(parent, name), false);
        if (directory) Files.createDirectory(path);
        else Files.createFile(path);
    }

    public static void rename(File source, String relative, String newName) throws IOException {
        if (relative.isEmpty()) throw new IOException("프로젝트 루트의 이름은 바꿀 수 없습니다.");
        Path original = checked(source, relative, true);
        int slash = relative.lastIndexOf('/');
        Path target = checked(source, child(slash < 0 ? "" : relative.substring(0, slash), newName), false);
        if (original.equals(target)) return;
        // No REPLACE_EXISTING: renaming must never overwrite another file.
        Files.move(original, target);
    }

    public static void delete(File source, String relative) throws IOException {
        if (relative.isEmpty()) throw new IOException("프로젝트 루트는 여기서 삭제할 수 없습니다.");
        // Only files and empty directories. A recursive delete is deliberately not implicit.
        Files.delete(checked(source, relative, true));
    }

    public static Document read(File source, String relative) throws IOException {
        Path path = checked(source, relative, true);
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) throw new IOException("일반 텍스트 파일만 편집할 수 있습니다.");
        BasicFileAttributes before = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (before.size() > MAX_TEXT_BYTES) throw new IOException("편집기는 최대 128 KiB 파일을 지원합니다.");
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (FileChannel input = FileChannel.open(path, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
            ByteBuffer buffer = ByteBuffer.allocate(8192);
            while (input.read(buffer) != -1) {
                buffer.flip();
                if (output.size() + buffer.remaining() > MAX_TEXT_BYTES) throw new IOException("파일이 편집 제한 크기를 초과했습니다.");
                output.write(buffer.array(), 0, buffer.remaining());
                buffer.clear();
            }
        }
        checked(source, relative, true);
        BasicFileAttributes after = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (!identity(before).equals(identity(after))) throw new ConflictException();
        byte[] bytes = output.toByteArray();
        for (byte value : bytes) if (value == 0) throw new IOException("바이너리 파일은 편집할 수 없습니다.");
        String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
        } catch (CharacterCodingException exception) {
            throw new IOException("UTF-8 텍스트 파일만 편집할 수 있습니다.", exception);
        }
        return new Document(text, identity(after) + ":" + digest(bytes));
    }

    /** Compare content and disk identity immediately before atomic replacement. */
    public static Document save(File source, String relative, String expectedVersion, String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_TEXT_BYTES) throw new IOException("저장할 내용이 128 KiB 제한을 초과했습니다.");
        if (text.indexOf('\0') >= 0) throw new IOException("NUL 문자는 저장할 수 없습니다.");
        Path target = checked(source, relative, true);
        if (!read(source, relative).version.equals(expectedVersion)) throw new ConflictException();
        Set<PosixFilePermission> permissions = Files.getPosixFilePermissions(target, LinkOption.NOFOLLOW_LINKS);
        Path temp = Files.createTempFile(target.getParent(), ".z8-save-", ".tmp");
        try {
            Files.setPosixFilePermissions(temp, permissions);
            try (FileChannel output = FileChannel.open(temp, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)) {
                ByteBuffer buffer = ByteBuffer.wrap(bytes);
                while (buffer.hasRemaining()) output.write(buffer);
                output.force(true);
            }
            checked(source, relative, true);
            if (!read(source, relative).version.equals(expectedVersion)) throw new ConflictException();
            Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            return read(source, relative);
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    private static String identity(BasicFileAttributes value) {
        return value.size() + ":" + value.lastModifiedTime() + ":" + value.fileKey();
    }

    private static String digest(byte[] value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value);
            StringBuilder result = new StringBuilder();
            for (byte item : digest) result.append(String.format(java.util.Locale.ROOT, "%02x", item & 255));
            return result.toString();
        } catch (NoSuchAlgorithmException exception) { throw new AssertionError(exception); }
    }
}
