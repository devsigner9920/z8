package com.termux.app;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.util.Properties;

/** Bounded metadata-only inspection. It never executes a CLI or reads provider credentials. */
final class Z8ProviderInstallIdentity {
    final String version, fingerprint;
    private Z8ProviderInstallIdentity(String version, String fingerprint) { this.version = version; this.fingerprint = fingerprint; }
    static Z8ProviderInstallIdentity unknown() { return new Z8ProviderInstallIdentity("", ""); }
    interface Decoder { Receipt decode(String json) throws Exception; }
    static final class Receipt {
        final String manager, tool, version, binarySha256;
        Receipt(String manager, String tool, String version, String binarySha256) {
            this.manager = manager; this.tool = tool; this.version = version; this.binarySha256 = binarySha256;
        }
    }
    static Z8ProviderInstallIdentity inspect(Path files, String projectId, String tool, Decoder decoder) {
        try {
            Z8ProviderNotice.project(projectId); Z8ProviderNotice.name(tool);
            Path home = checked(files, "z8/homes/" + projectId);
            Path bin = checked(home, ".local/bin");
            Path launcher = bin.resolve(tool);
            if (!Files.isSymbolicLink(launcher)) return unknown();
            Path target = Files.readSymbolicLink(launcher);
            if (target.isAbsolute()) return unknown();
            Path nativeFile = bin.resolve(target).normalize();
            Path toolRoot = checked(home, ".local/share/z8/ai/" + tool);
            if (!nativeFile.startsWith(toolRoot)) return unknown();
            Path relative = toolRoot.relativize(nativeFile);
            boolean packaged = "codex".equals(tool) && relative.getNameCount() == 3
                && "bin".equals(relative.getName(1).toString()) && "codex".equals(relative.getName(2).toString());
            boolean single = relative.getNameCount() == 2 && tool.equals(relative.getName(1).toString());
            if (!packaged && !single) return unknown();
            checked(toolRoot, relative.toString());
            Path versionDir = toolRoot.resolve(relative.getName(0));
            byte[] raw = read(checked(versionDir, "receipt.json"), 128 * 1024);
            Receipt receipt = decoder.decode(new String(raw, StandardCharsets.UTF_8));
            String version = Z8ToolCatalog.releaseVersion(tool, receipt.version);
            if (!"z8-ai-v1".equals(receipt.manager) || !tool.equals(receipt.tool) || version.isEmpty()
                    || receipt.binarySha256 == null || !receipt.binarySha256.matches("[0-9a-f]{64}")
                    || !(version + (packaged ? "-package-v1" : "")).equals(relative.getName(0).toString())) return unknown();
            BasicFileAttributes stat = Files.readAttributes(nativeFile, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (!stat.isRegularFile() || stat.size() == 0) return unknown();
            // Detect ordinary replacement/update without a 300MB executable hash on every Open.
            // This is a disclosure-change token, not proof of integrity or a same-UID security boundary.
            String metadata = version + ":" + sha(raw) + ":" + target + ":" + stat.size() + ":"
                + stat.lastModifiedTime() + ":" + stat.creationTime() + ":" + stat.fileKey();
            return new Z8ProviderInstallIdentity(version, sha(metadata.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception unavailable) { return unknown(); }
    }
    private static Path checked(Path root, String relative) throws IOException {
        Path base = root.toAbsolutePath().normalize(), path = base.resolve(relative).normalize();
        if (!path.startsWith(base)) throw new IOException("Outside metadata scope");
        Path current = path.getRoot();
        for (Path part : path) {
            current = current.resolve(part);
            if (Files.isSymbolicLink(current)) throw new IOException("Linked metadata path");
        }
        return path;
    }
    private static byte[] read(Path path, int limit) throws IOException {
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.size(path) > limit) throw new IOException("Invalid metadata");
        try (java.io.InputStream input = Files.newInputStream(path)) {
            ByteArrayOutputStream out = new ByteArrayOutputStream(); byte[] buffer = new byte[4096]; int size;
            while ((size = input.read(buffer)) != -1) {
                if (out.size() + size > limit) throw new IOException("Metadata too large");
                out.write(buffer, 0, size);
            }
            return out.toByteArray();
        }
    }
    private static String sha(byte[] bytes) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(bytes);
        StringBuilder value = new StringBuilder(); for (byte b : hash) value.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return value.toString();
    }

    /** Outside source/HOME: project deletion removes it; a fresh clone does not inherit it. */
    static Z8ProviderNotice.Store store(Path files) {
        return new Z8ProviderNotice.Store() {
            private Path path(String projectId) throws IOException {
                Z8ProviderNotice.project(projectId);
                Path folder = checked(files, "z8/projects/" + projectId);
                if (!Files.isDirectory(folder, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Project unavailable");
                return checked(folder, "provider-disclosure.properties");
            }
            private Properties values(Path file) throws IOException {
                Properties values = new Properties();
                if (Files.exists(file, LinkOption.NOFOLLOW_LINKS)) try {
                    values.load(new ByteArrayInputStream(Z8ProviderInstallIdentity.read(file, 8192)));
                } catch (IllegalArgumentException malformed) { throw new IOException("Invalid acknowledgment", malformed); }
                return values;
            }
            public String read(String projectId, String tool) throws IOException {
                Z8ProviderNotice.name(tool); return values(path(projectId)).getProperty(tool, "");
            }
            public void write(String projectId, String tool, String value) throws IOException {
                Z8ProviderNotice.name(tool); Path file = path(projectId); Properties values = values(file);
                values.setProperty(tool, value);
                Path temporary = Files.createTempFile(file.getParent(), ".provider-disclosure-", ".tmp");
                try {
                    try (java.io.OutputStream output = Files.newOutputStream(temporary)) { values.store(output, "Z8 information acknowledgment; not provider contract assent"); }
                    path(projectId); // Refuse a replaced/linked destination before publication.
                    Files.move(temporary, file, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
                } finally { Files.deleteIfExists(temporary); }
            }
        };
    }
}
