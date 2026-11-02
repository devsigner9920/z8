package com.termux.app;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/** Durable ownership for disposable install trees. Source and HOME never use this helper. */
final class Z8InstallStaging {
    private static final String SUFFIX = ".owner";
    private Z8InstallStaging() {}

    static Path reserve(Path parent, String prefix, String owner) throws IOException {
        Path stage = parent.resolve(prefix + UUID.randomUUID());
        // Publish ownership first: a process death can leave only the receipt, never
        // an unidentifiable nonempty extraction tree.
        Files.write(receipt(stage), contents(owner), StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        return stage;
    }

    static Path create(Path parent, String prefix, String owner) throws IOException {
        Path stage = reserve(parent, prefix, owner);
        Files.createDirectory(stage);
        return stage;
    }

    static List<Path> owned(Path parent, String prefix, String owner) throws IOException {
        List<Path> result = new ArrayList<>();
        try (DirectoryStream<Path> entries = Files.newDirectoryStream(parent, prefix + "*" + SUFFIX)) {
            for (Path entry : entries) {
                String name = entry.getFileName().toString();
                String id = name.substring(prefix.length(), name.length() - SUFFIX.length());
                try { if (!UUID.fromString(id).toString().equals(id)) continue; }
                catch (IllegalArgumentException invalid) { continue; }
                Path stage = parent.resolve(prefix + id);
                if (owns(stage, owner) && (!Files.exists(stage, LinkOption.NOFOLLOW_LINKS)
                        || Files.isDirectory(stage, LinkOption.NOFOLLOW_LINKS))) result.add(stage);
            }
        }
        return result;
    }

    static void recover(Path parent, String prefix, String owner) throws IOException {
        for (Path stage : owned(parent, prefix, owner)) discard(stage, owner);
    }

    static void discard(Path stage, String owner) throws IOException {
        if (!owns(stage, owner)) return;
        if (Files.exists(stage, LinkOption.NOFOLLOW_LINKS)) {
            if (!Files.isDirectory(stage, LinkOption.NOFOLLOW_LINKS)) return;
            Files.walkFileTree(stage, new SimpleFileVisitor<Path>() {
                @Override public FileVisitResult preVisitDirectory(Path path, BasicFileAttributes attrs) throws IOException {
                    Z8GuestArchive.mode(path, 0700);
                    return FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult visitFile(Path path, BasicFileAttributes attrs) throws IOException {
                    // walkFileTree does not follow symbolic links, including nested ones.
                    Files.delete(path); return FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult postVisitDirectory(Path path, IOException error) throws IOException {
                    if (error != null) throw error;
                    Files.delete(path); return FileVisitResult.CONTINUE;
                }
            });
        }
        Files.deleteIfExists(receipt(stage));
    }

    private static boolean owns(Path stage, String owner) throws IOException {
        Path marker = receipt(stage);
        if (!Files.isRegularFile(marker, LinkOption.NOFOLLOW_LINKS) || Files.size(marker) > 256) return false;
        try (java.io.InputStream input = Files.newInputStream(marker, LinkOption.NOFOLLOW_LINKS)) {
            byte[] expected = contents(owner), actual = new byte[257];
            int size = 0, count;
            while (size < actual.length && (count = input.read(actual, size, actual.length - size)) != -1) size += count;
            return size == expected.length && java.util.Arrays.equals(expected, java.util.Arrays.copyOf(actual, size));
        }
    }

    private static byte[] contents(String owner) { return ("z8-install-staging-v1\n" + owner + "\n").getBytes(StandardCharsets.UTF_8); }
    private static Path receipt(Path stage) { return stage.resolveSibling(stage.getFileName() + SUFFIX); }
}
