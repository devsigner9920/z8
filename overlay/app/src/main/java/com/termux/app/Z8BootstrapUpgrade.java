package com.termux.app;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/** An exact APK-owned allowlist, never a best-effort merge of a user's host prefix. */
final class Z8BootstrapUpgrade {
    static final String ASSET = "z8/bootstrap-upgrade.tsv";
    private Z8BootstrapUpgrade() {}

    static void verify(Path prefix, InputStream manifest, Set<String> mutableFiles,
                       Set<String> mutableDirectories) throws IOException {
        if (!Files.isDirectory(prefix, LinkOption.NOFOLLOW_LINKS)) throw preserved();
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        byte[] buffer = new byte[32768]; int count;
        while ((count = manifest.read(buffer)) != -1) {
            if (bytes.size() + count > 2 * 1024 * 1024) throw preserved();
            bytes.write(buffer, 0, count);
        }
        String[] lines = new String(bytes.toByteArray(), StandardCharsets.UTF_8).split("\n");
        if (lines.length < 2 || !lines[0].matches("z8-bootstrap-upgrade-v1\\t[a-f0-9]{64}")) throw preserved();
        String receipt = lines[0].substring(lines[0].indexOf('\t') + 1);
        Path receiptPath = prefix.resolve(".z8-bootstrap.sha256");
        if (!Files.isRegularFile(receiptPath, LinkOption.NOFOLLOW_LINKS) || Files.size(receiptPath) > 128
                || !new String(Files.readAllBytes(receiptPath), StandardCharsets.UTF_8).trim().equals(receipt)) throw preserved();
        Map<String, String[]> expected = new HashMap<>();
        for (int i = 1; i < lines.length; i++) {
            String[] fields = lines[i].split("\t", -1);
            if (fields.length != 4 || !fields[0].matches("[DFL]") || fields[3].isEmpty()
                    || fields[3].startsWith("/") || fields[3].contains("\\")
                    || !java.nio.file.Paths.get(fields[3]).normalize().toString().equals(fields[3])
                    || fields[3].equals("..") || fields[3].startsWith("../")
                    || expected.put(fields[3], fields) != null) throw preserved();
        }
        Set<String> seen = new HashSet<>();
        Files.walkFileTree(prefix, new SimpleFileVisitor<Path>() {
            private void check(Path path, BasicFileAttributes attrs) throws IOException {
                String name = prefix.relativize(path).toString();
                if (name.isEmpty() || name.equals(".z8-bootstrap.sha256")) return;
                String[] entry = expected.get(name);
                if (mutableFiles.contains(name)) {
                    if (!attrs.isRegularFile()) throw preserved();
                    if (entry != null) seen.add(name); return;
                }
                if (entry == null && attrs.isDirectory() && mutableDirectories.contains(name)) return;
                if (entry == null) throw preserved();
                seen.add(name);
                if (entry[0].equals("D")) { if (!attrs.isDirectory()) throw preserved(); }
                else if (entry[0].equals("L")) {
                    if (!attrs.isSymbolicLink() || !Files.readSymbolicLink(path).toString().equals(entry[2])) throw preserved();
                } else {
                    if (!attrs.isRegularFile() || !Long.toString(attrs.size()).equals(entry[1])
                            || !sha256(path).equals(entry[2])) throw preserved();
                }
            }
            @Override public FileVisitResult preVisitDirectory(Path path, BasicFileAttributes attrs) throws IOException {
                check(path, attrs); return FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult visitFile(Path path, BasicFileAttributes attrs) throws IOException {
                check(path, attrs); return FileVisitResult.CONTINUE;
            }
        });
        if (!seen.containsAll(expected.keySet())) throw preserved();
    }

    private static String sha256(Path path) throws IOException {
        try (InputStream input = Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256"); byte[] bytes = new byte[65536]; int count;
            while ((count = input.read(bytes)) != -1) digest.update(bytes, 0, count);
            StringBuilder result = new StringBuilder();
            for (byte part : digest.digest()) result.append(String.format(java.util.Locale.ROOT, "%02x", part & 255));
            return result.toString();
        } catch (java.security.NoSuchAlgorithmException impossible) { throw new IOException(impossible); }
    }

    static IOException preserved() {
        return new IOException(Z8Text.text("The existing runtime differs from the verified previous version or contains user additions or changes. All files have been preserved; automatic updates have stopped.", "기존 실행 기반이 확인된 이전 버전과 다르거나 사용자가 추가·수정한 파일이 있습니다. 모든 파일을 보존했으며 자동 갱신을 중단했습니다."));
    }
}
