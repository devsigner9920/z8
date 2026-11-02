package com.termux.app;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/** Extract only a verified normalized guest archive into a newly-created staging folder. */
final class Z8GuestArchive {
    static final long MAX_ARCHIVE = 512L * 1024 * 1024;
    static final long MAX_EXPANDED = 2L * 1024 * 1024 * 1024;
    static final int MAX_ENTRIES = 100000;
    static final int MAX_LINK_BYTES = 4 * 1024 * 1024;
    static final String LINKS = "SYMLINKS.txt";
    static final String MARKER = ".z8-environment.json";

    interface Source { InputStream open() throws IOException; }
    interface Progress { void update(int percent, String detail); }

    static final class Item {
        final String path;
        final boolean directory;
        final long size;
        final int mode;
        Item(String path, boolean directory, long size, int mode) {
            this.path = path; this.directory = directory; this.size = size; this.mode = mode;
        }
    }

    static final class Manifest {
        final String sha256;
        final long archiveBytes;
        final long expandedBytes;
        final Map<String, Item> items;
        Manifest(String sha256, long archiveBytes, long expandedBytes, List<Item> items) throws IOException {
            if (sha256 == null || !sha256.matches("[a-f0-9]{64}") || archiveBytes <= 0 || archiveBytes > MAX_ARCHIVE
                    || expandedBytes <= 0 || expandedBytes > MAX_EXPANDED || items.isEmpty() || items.size() > MAX_ENTRIES)
                throw new IOException(Z8Text.text("The guest image metadata has an invalid size or hash.", "게스트 이미지 메타데이터의 크기 또는 해시가 올바르지 않습니다."));
            this.sha256 = sha256; this.archiveBytes = archiveBytes; this.expandedBytes = expandedBytes;
            this.items = new LinkedHashMap<>();
            Set<String> destinations = new HashSet<>();
            long total = 0;
            for (Item item : items) {
                String name = path(item.path, item.directory);
                if (name.equals(MARKER) || name.startsWith(MARKER + "/") || item.size < 0
                        || item.size > MAX_EXPANDED || item.mode < 0 || (item.mode & ~0777) != 0
                        || (item.directory && item.size != 0)) throw new IOException(Z8Text.text("Unsupported image entry.", "허용되지 않는 이미지 항목입니다."));
                if (!destinations.add(name) || this.items.put(item.path, item) != null)
                    throw new IOException(Z8Text.text("The image contains duplicate paths.", "이미지에 중복된 경로가 있습니다."));
                total += item.size;
                if (total > MAX_EXPANDED) throw new IOException(Z8Text.text("The expanded image is too large.", "이미지의 압축 해제 크기가 너무 큽니다."));
            }
            if (total != expandedBytes || !this.items.containsKey(LINKS) || this.items.get(LINKS).directory
                    || this.items.get(LINKS).size > MAX_LINK_BYTES)
                throw new IOException(Z8Text.text("The image totals or link manifest do not match.", "이미지의 항목 합계 또는 링크 목록이 일치하지 않습니다."));
        }
    }

    private Z8GuestArchive() {}

    static void extract(Source archive, Manifest manifest, File staging, Progress progress) throws IOException {
        if (!staging.isDirectory() || Files.isSymbolicLink(staging.toPath())) throw new IOException(Z8Text.text("A new installation directory is required.", "새 설치 폴더가 필요합니다."));
        try (java.nio.file.DirectoryStream<Path> children = Files.newDirectoryStream(staging.toPath())) {
            if (children.iterator().hasNext()) throw new IOException(Z8Text.text("The installation directory is not empty.", "설치 폴더가 비어 있지 않습니다."));
        }
        verify(archive, manifest, progress);
        Set<String> seen = new HashSet<>();
        List<Item> directories = new ArrayList<>();
        byte[] linkBytes = null;
        long total = 0;
        long lastProgress = 0;
        try (ZipInputStream zip = new ZipInputStream(archive.open(), StandardCharsets.UTF_8)) {
            ZipEntry entry;
            byte[] buffer = new byte[65536];
            while ((entry = zip.getNextEntry()) != null) {
                Item item = manifest.items.get(entry.getName());
                if (item == null || !seen.add(item.path) || item.directory != entry.isDirectory())
                    throw new IOException(Z8Text.text("A ZIP entry does not match the verified manifest.", "ZIP 항목이 검증된 목록과 일치하지 않습니다."));
                String name = path(item.path, item.directory);
                Path destination = checked(staging, name);
                if (item.directory) {
                    Files.createDirectories(destination);
                    directories.add(item);
                    if (zip.read() != -1) throw new IOException(Z8Text.text("A directory entry contains unexpected data.", "폴더 항목에 예상하지 않은 내용이 있습니다."));
                } else {
                    Files.createDirectories(destination.getParent());
                    long count = 0;
                    ByteArrayOutputStream links = name.equals(LINKS) ? new ByteArrayOutputStream() : null;
                    OutputStream output = links == null ? Files.newOutputStream(destination,
                        java.nio.file.StandardOpenOption.CREATE_NEW, java.nio.file.StandardOpenOption.WRITE,
                        LinkOption.NOFOLLOW_LINKS) : links;
                    try (OutputStream sink = output) {
                        int read;
                        while ((read = zip.read(buffer)) != -1) {
                            count += read; total += read;
                            if (count > item.size || total > manifest.expandedBytes)
                                throw new IOException(Z8Text.text("The ZIP's actual size exceeds the verified size.", "ZIP의 실제 크기가 검증된 크기를 초과했습니다."));
                            sink.write(buffer, 0, read);
                        }
                    }
                    if (count != item.size) throw new IOException(Z8Text.text("The ZIP file size differs from the verified size.", "ZIP 파일 크기가 검증된 크기와 다릅니다."));
                    if (links != null) linkBytes = links.toByteArray();
                    else mode(destination, item.mode);
                }
                zip.closeEntry();
                long now = System.nanoTime();
                if (now - lastProgress > 100_000_000L) {
                    progress.update(20 + (int) (65 * total / Math.max(1, manifest.expandedBytes)), Z8Text.text("Preparing Linux files…", "Linux 파일을 준비하고 있습니다."));
                    lastProgress = now;
                }
            }
        }
        if (seen.size() != manifest.items.size() || total != manifest.expandedBytes || linkBytes == null)
            throw new IOException(Z8Text.text("Image files or the link manifest are missing.", "이미지 파일 또는 링크 목록이 누락되었습니다."));
        Map<String, String> links = links(linkBytes, manifest);
        progress.update(88, Z8Text.text("Applying Linux links and permissions…", "Linux 링크와 권한을 적용하고 있습니다."));
        for (Map.Entry<String, String> link : links.entrySet()) {
            Path destination = checked(staging, link.getKey());
            Files.createDirectories(destination.getParent());
            Files.createSymbolicLink(destination, java.nio.file.Paths.get(link.getValue()));
        }
        // Modes are deferred so read-only directories cannot prevent extraction.
        directories.sort(Comparator.comparingInt((Item item) -> item.path.length()).reversed());
        for (Item item : directories) mode(checked(staging, path(item.path, true)), item.mode);
    }

    private static void verify(Source archive, Manifest manifest, Progress progress) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            long bytes = 0;
            long lastProgress = 0;
            try (InputStream input = archive.open()) {
                byte[] buffer = new byte[65536]; int count;
                while ((count = input.read(buffer)) != -1) {
                    bytes += count;
                    if (bytes > manifest.archiveBytes) throw new IOException(Z8Text.text("The image file size does not match.", "이미지 파일 크기가 일치하지 않습니다."));
                    digest.update(buffer, 0, count);
                    long now = System.nanoTime();
                    if (now - lastProgress > 100_000_000L) {
                        progress.update((int) (20 * bytes / manifest.archiveBytes), Z8Text.text("Checking the image SHA-256…", "이미지 SHA-256을 확인하고 있습니다."));
                        lastProgress = now;
                    }
                }
            }
            StringBuilder sha = new StringBuilder();
            for (byte value : digest.digest()) sha.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
            if (bytes != manifest.archiveBytes || !sha.toString().equals(manifest.sha256))
                throw new IOException(Z8Text.text("Image SHA-256 verification failed.", "이미지 SHA-256 검증에 실패했습니다."));
        } catch (NoSuchAlgorithmException impossible) { throw new AssertionError(impossible); }
    }

    static String path(String input, boolean directory) throws IOException {
        if (input == null || input.isEmpty() || input.length() > 4096 || input.startsWith("/") || input.indexOf('\\') >= 0)
            throw new IOException(Z8Text.text("Invalid image path.", "잘못된 이미지 경로입니다."));
        String name = directory && input.endsWith("/") ? input.substring(0, input.length() - 1) : input;
        if (directory != input.endsWith("/")) throw new IOException(Z8Text.text("Invalid directory path format.", "폴더 경로 형식이 올바르지 않습니다."));
        for (String part : name.split("/", -1)) {
            if (part.isEmpty() || part.equals(".") || part.equals("..") || part.length() > 255)
                throw new IOException(Z8Text.text("An image path contains traversal or empty segments.", "이미지 경로에 이동 또는 빈 항목이 있습니다."));
            for (int index = 0; index < part.length(); index++)
                if (Character.isISOControl(part.charAt(index))) throw new IOException(Z8Text.text("An image path contains control characters.", "이미지 경로에 제어 문자가 있습니다."));
        }
        return name;
    }

    static Path checked(File root, String relative) throws IOException {
        Path base = root.toPath().toAbsolutePath().normalize();
        if (Files.isSymbolicLink(base) || !Files.isDirectory(base, LinkOption.NOFOLLOW_LINKS)) throw new IOException(Z8Text.text("Invalid installation root.", "설치 루트가 올바르지 않습니다."));
        Path value = base;
        for (String part : relative.split("/", -1)) {
            if (part.isEmpty() || part.equals(".") || part.equals("..")) throw new IOException(Z8Text.text("Invalid installation path.", "잘못된 설치 경로입니다."));
            value = value.resolve(part);
            if (Files.isSymbolicLink(value)) throw new IOException(Z8Text.text("The installation path contains an unexpected link.", "설치 경로에 예상하지 않은 링크가 있습니다."));
        }
        if (!value.normalize().startsWith(base) || !value.toFile().getCanonicalFile().toPath().startsWith(base.toFile().getCanonicalFile().toPath()))
            throw new IOException(Z8Text.text("The installation path escapes the environment.", "설치 경로가 환경 밖으로 이동했습니다."));
        return value;
    }

    private static Map<String, String> links(byte[] bytes, Manifest manifest) throws IOException {
        String content;
        try { content = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString(); }
        catch (Exception invalid) { throw new IOException(Z8Text.text("Could not read the link manifest.", "링크 목록을 읽을 수 없습니다."), invalid); }
        Map<String, String> links = new LinkedHashMap<>();
        for (String line : content.split("\n", -1)) {
            if (line.isEmpty()) continue;
            int separator = line.indexOf('←');
            if (separator <= 0 || separator != line.lastIndexOf('←') || separator == line.length() - 1)
                throw new IOException(Z8Text.text("The link manifest format is invalid.", "링크 목록 형식이 올바르지 않습니다."));
            String target = line.substring(0, separator);
            String destination = path(line.substring(separator + 1), false);
            if (target.startsWith("/") || target.indexOf('\\') >= 0 || target.length() > 4096)
                throw new IOException(Z8Text.text("Only relative links may be installed.", "상대 경로 링크만 설치할 수 있습니다."));
            for (int index = 0; index < target.length(); index++)
                if (Character.isISOControl(target.charAt(index))) throw new IOException(Z8Text.text("A link contains control characters.", "링크에 제어 문자가 있습니다."));
            if (destination.equals(MARKER) || destination.equals(LINKS) || links.put(destination, target) != null)
                throw new IOException(Z8Text.text("Duplicate or reserved link path.", "중복되거나 예약된 링크 경로입니다."));
        }
        if (links.size() + manifest.items.size() > MAX_ENTRIES) throw new IOException(Z8Text.text("The image contains too many entries.", "이미지 항목 수가 너무 많습니다."));
        List<String> all = new ArrayList<>();
        for (Item item : manifest.items.values()) all.add(path(item.path, item.directory));
        all.addAll(links.keySet());
        Set<String> ancestors = new HashSet<>();
        for (String value : all) {
            int slash = value.indexOf('/');
            while (slash >= 0) {
                ancestors.add(value.substring(0, slash));
                slash = value.indexOf('/', slash + 1);
            }
        }
        for (Map.Entry<String, String> link : links.entrySet()) {
            String destination = link.getKey();
            if (manifest.items.containsKey(destination) || manifest.items.containsKey(destination + "/"))
                throw new IOException(Z8Text.text("A file and a link use the same path.", "파일과 링크가 같은 경로를 사용합니다."));
            if (ancestors.contains(destination)) throw new IOException(Z8Text.text("Another image entry is nested under a link.", "링크 아래에 다른 이미지 항목이 있습니다."));
            resolveLink(destination, links);
        }
        return links;
    }

    /** Resolve links component by component; lexical normalization alone misses a/../ escapes. */
    private static void resolveLink(String destination, Map<String, String> links) throws IOException {
        Deque<String> pending = new ArrayDeque<>();
        Collections.addAll(pending, destination.split("/"));
        List<String> resolved = new ArrayList<>();
        int followed = 0;
        while (!pending.isEmpty()) {
            String part = pending.removeFirst();
            if (part.isEmpty() || part.equals(".")) continue;
            if (part.equals("..")) {
                if (resolved.isEmpty()) throw new IOException(Z8Text.text("A link escapes the environment.", "링크가 환경 밖으로 이동합니다."));
                resolved.remove(resolved.size() - 1); continue;
            }
            resolved.add(part);
            String target = links.get(String.join("/", resolved));
            if (target != null) {
                if (++followed > 40) throw new IOException(Z8Text.text("A link chain contains a cycle or is too long.", "순환하거나 너무 긴 링크 체인입니다."));
                resolved.remove(resolved.size() - 1);
                String[] parts = target.split("/", -1);
                for (int index = parts.length - 1; index >= 0; index--) pending.addFirst(parts[index]);
            }
        }
    }

    static void mode(Path path, int bits) throws IOException {
        Set<PosixFilePermission> permissions = new HashSet<>();
        PosixFilePermission[] flags = { PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE,
            PosixFilePermission.OWNER_EXECUTE, PosixFilePermission.GROUP_READ, PosixFilePermission.GROUP_WRITE,
            PosixFilePermission.GROUP_EXECUTE, PosixFilePermission.OTHERS_READ, PosixFilePermission.OTHERS_WRITE,
            PosixFilePermission.OTHERS_EXECUTE };
        for (int index = 0; index < flags.length; index++) if ((bits & (1 << (8 - index))) != 0) permissions.add(flags[index]);
        Files.setPosixFilePermissions(path, permissions);
    }
}
