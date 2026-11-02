package com.termux.app;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Properties;
import java.util.UUID;

/** One recoverable editor per project, outside source/rootfs; never writes a source file. */
public final class Z8DraftStore {
    public static final class Draft {
        public final String path, text, version, baseline;
        public final int selection;
        public Draft(String path, String text, String version, String baseline, int selection) {
            this.path = path; this.text = text; this.version = version; this.baseline = baseline;
            this.selection = Math.max(0, Math.min(selection, text.length()));
        }
    }
    private final File root;
    public Z8DraftStore(File files) { root = new File(files, "z8-editor-drafts"); }
    private File file(String project) throws IOException {
        try { if (!UUID.fromString(project).toString().equals(project)) throw new IllegalArgumentException(); }
        catch (RuntimeException failure) { throw new IOException("Invalid draft project", failure); }
        if (Files.isSymbolicLink(root.toPath())) throw new IOException("Invalid draft directory");
        if (!root.isDirectory() && !root.mkdirs()) throw new IOException("Cannot create draft directory");
        File file = new File(root, project + ".properties");
        if (Files.isSymbolicLink(file.toPath())) throw new IOException("Invalid draft file");
        return file;
    }
    private static void validate(Draft draft) throws IOException {
        if (draft.path == null || draft.path.isEmpty() || draft.path.startsWith("/") || draft.path.length() > 4096)
            throw new IOException("Invalid draft path");
        for (String part : draft.path.split("/", -1)) Z8Files.name(part);
        if (draft.version == null || draft.version.isEmpty() || draft.version.length() > 1024)
            throw new IOException("Invalid draft version");
        if (draft.text.getBytes(StandardCharsets.UTF_8).length > Z8Files.MAX_TEXT_BYTES
            || draft.baseline.getBytes(StandardCharsets.UTF_8).length > Z8Files.MAX_TEXT_BYTES)
            throw new IOException("Draft exceeds 128 KiB UTF-8 limit");
    }
    public synchronized void save(String project, Draft draft) throws IOException {
        validate(draft);
        File target = file(project);
        Properties data = new Properties();
        data.setProperty("path", draft.path); data.setProperty("text", draft.text);
        data.setProperty("baseline", draft.baseline);
        data.setProperty("version", draft.version); data.setProperty("selection", Integer.toString(draft.selection));
        File temporary = File.createTempFile(".draft-", ".tmp", root);
        try {
            try (FileOutputStream output = new FileOutputStream(temporary)) {
                data.store(output, "Z8 recoverable editor draft"); output.getFD().sync();
            }
            Files.move(temporary.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } finally { Files.deleteIfExists(temporary.toPath()); }
    }
    public synchronized Draft read(String project) throws IOException {
        File target = file(project);
        if (!target.exists()) return null;
        if (target.length() > Z8Files.MAX_TEXT_BYTES * 16L) throw new IOException("Invalid draft size");
        Properties data = new Properties();
        try (InputStream input = new FileInputStream(target)) { data.load(input); }
        try {
            Draft draft = new Draft(data.getProperty("path"), data.getProperty("text"), data.getProperty("version"), data.getProperty("baseline", "\u0000"),
                Integer.parseInt(data.getProperty("selection", "0")));
            validate(draft); return draft;
        } catch (RuntimeException failure) { throw new IOException("Cannot read saved draft", failure); }
    }
    public synchronized void clear(String project) throws IOException { Files.deleteIfExists(file(project).toPath()); }
}
