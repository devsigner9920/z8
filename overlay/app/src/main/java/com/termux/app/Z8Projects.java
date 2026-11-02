package com.termux.app;

import android.content.Context;

import java.io.File;
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.FileVisitResult;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Properties;
import java.util.UUID;

/** Source storage is separate from every future replaceable Linux environment. */
public final class Z8Projects {
    public static final class Project {
        public final String id;
        public final String name;
        public final File source;
        public final long lastOpened;
        Project(String id, String name, File source, long lastOpened) {
            this.id = id; this.name = name; this.source = source; this.lastOpened = lastOpened;
        }
    }

    /** An invalid record stays visible without becoming an executable project. */
    public static final class Problem {
        public final String id, name, detail;
        Problem(String id, String name, String detail) {
            this.id = id; this.name = name; this.detail = detail;
        }
    }

    public static final class Listing {
        public final List<Project> projects;
        public final List<Problem> problems;
        Listing(List<Project> projects, List<Problem> problems) {
            this.projects = Collections.unmodifiableList(new ArrayList<>(projects));
            this.problems = Collections.unmodifiableList(new ArrayList<>(problems));
        }
    }

    private final File storage;

    public Z8Projects(Context context) {
        // Resolve Android-owned path aliases only at the trusted app root, before
        // app-owned project paths are appended. A later link in z8/projects must
        // still be rejected rather than canonicalized away.
        File files = context.getFilesDir();
        try { files = files.getCanonicalFile(); }
        catch (IOException ignored) { /* The checked storage operation reports failure. */ }
        storage = new File(files, "z8/projects");
    }

    /** Also usable by host-side storage tests without an Android runtime. */
    Z8Projects(File storage) { this.storage = storage; }

    private File root() throws IOException {
        File parent = storage.getParentFile();
        if (parent == null) throw new IOException(Z8Text.text("The project storage path is missing.", "프로젝트 저장 경로가 없습니다."));
        // Check every existing ancestor before creating anything through it.
        Path current = storage.toPath().toAbsolutePath().getRoot();
        for (Path part : storage.toPath().toAbsolutePath()) {
            current = current.resolve(part);
            if (Files.isSymbolicLink(current)) throw new IOException(Z8Text.text("The project storage path contains a symbolic link.", "프로젝트 저장 경로에 심볼릭 링크가 있습니다."));
        }
        Files.createDirectories(storage.toPath());
        return Z8Files.directory(storage, "");
    }

    private static String id(String value) throws IOException {
        try {
            if (value == null || !UUID.fromString(value).toString().equals(value)) throw new IllegalArgumentException();
            return value;
        } catch (IllegalArgumentException exception) { throw new IOException(Z8Text.text("Invalid project ID.", "잘못된 프로젝트 ID입니다.")); }
    }

    public Project create(String displayName) throws IOException {
        String name = Z8Files.name(displayName.trim());
        String id = UUID.randomUUID().toString();
        File folder = new File(root(), id);
        Files.createDirectory(folder.toPath());
        File source = new File(folder, "source");
        Files.createDirectory(source.toPath());
        long opened = System.currentTimeMillis();
        try {
            write(folder, name, opened);
        } catch (IOException exception) {
            Files.deleteIfExists(source.toPath());
            Files.deleteIfExists(folder.toPath());
            throw exception;
        }
        return new Project(id, name, source, opened);
    }

    public Project open(String projectId) throws IOException {
        File folder = Z8Files.directory(root(), id(projectId));
        File source = Z8Files.directory(folder, "source");
        Properties metadata = readMetadata(folder);
        String name = Z8Files.name(metadata.getProperty("name"));
        long opened;
        try { opened = Long.parseLong(metadata.getProperty("opened", "0")); }
        catch (NumberFormatException exception) { opened = 0; }
        return new Project(projectId, name, source, opened);
    }

    private static Properties readMetadata(File folder) throws IOException {
        Path meta = new File(folder, "project.properties").toPath();
        if (Files.isSymbolicLink(meta) || !Files.isRegularFile(meta, LinkOption.NOFOLLOW_LINKS)
                || Files.size(meta) > 8192) throw new IOException(Z8Text.text("Could not read project information.", "프로젝트 정보를 읽을 수 없습니다."));
        Properties metadata = new Properties();
        try (Reader reader = Files.newBufferedReader(meta, StandardCharsets.UTF_8)) { metadata.load(reader); }
        catch (IllegalArgumentException malformed) { throw new IOException(Z8Text.text("Invalid project information format.", "프로젝트 정보 형식이 올바르지 않습니다."), malformed); }
        return metadata;
    }

    public Project touch(String projectId) throws IOException {
        Project project = open(projectId);
        long now = System.currentTimeMillis();
        write(project.source.getParentFile(), project.name, now);
        return new Project(project.id, project.name, project.source, now);
    }

    public List<Project> list() throws IOException {
        Listing listing = scan();
        if (!listing.problems.isEmpty()) throw new IOException(Z8Text.text("Some project information could not be read.", "일부 프로젝트 정보를 읽을 수 없습니다."));
        return new ArrayList<>(listing.projects);
    }

    /** One damaged record must not hide healthy projects. Never repairs or deletes data. */
    public Listing scan() throws IOException {
        List<Project> result = new ArrayList<>();
        List<Problem> problems = new ArrayList<>();
        File projectRoot = root();
        int records = 0;
        try (DirectoryStream<Path> entries = Files.newDirectoryStream(projectRoot.toPath())) {
            for (Path entry : entries) {
                String key = entry.getFileName().toString();
                try { id(key); } catch (IOException ignored) { continue; }
                if (++records > 1000) throw new IOException(Z8Text.text("The project limit of 1,000 has been exceeded.", "프로젝트가 1,000개를 초과했습니다."));
                try { result.add(open(key)); }
                catch (IOException invalid) {
                    String name = Z8Text.text("Project ", "프로젝트 ") + key.substring(0, 8);
                    // A missing source can still have a valid display name. Check the
                    // entire folder and metadata path again; never follow a linked record.
                    try { name = Z8Files.name(readMetadata(Z8Files.directory(projectRoot, key)).getProperty("name")); }
                    catch (IOException unreadable) { /* The UUID identifies the preserved record. */ }
                    problems.add(new Problem(key, name,
                        Z8Text.text("Could not verify the project files or information. Files have been preserved.", "프로젝트 파일 또는 정보를 확인할 수 없습니다. 파일은 보존되어 있습니다.")));
                }
            }
        }
        result.sort(Comparator.comparingLong((Project project) -> project.lastOpened).reversed());
        problems.sort(Comparator.comparing(problem -> problem.id));
        return new Listing(result, problems);
    }

    /** Explicit whole-project deletion; caller must exclude live sessions and setup workers. */
    public void delete(String projectId) throws IOException {
        String key = id(projectId);
        Project project = open(key);
        Path folder = project.source.getParentFile().toPath();
        Path environment = ownedSibling("environments", key);
        Path home = ownedSibling("homes", key);
        writableDirectory(folder);
        writableDirectory(project.source.toPath());
        // Validate every top-level destination before removing any data. Links
        // inside a rootfs are removed as links and are never traversed.
        if (environment != null) removeTree(environment);
        if (home != null) removeTree(home);
        Path source = project.source.toPath();
        try (DirectoryStream<Path> children = Files.newDirectoryStream(folder)) {
            for (Path child : children) {
                String name = child.getFileName().toString();
                if (!name.equals("project.properties") && !name.equals("source")) removeTree(child);
            }
        }
        // Keep a valid metadata + source pair until the substantive deletion
        // completes, so an I/O failure can be retried from the same project.
        try (DirectoryStream<Path> children = Files.newDirectoryStream(source)) {
            for (Path child : children) removeTree(child);
        }
        try {
            Files.delete(source);
            Files.delete(folder.resolve("project.properties"));
            Files.delete(folder);
        } catch (IOException failure) {
            try { restoreDeleteRecord(project); }
            catch (IOException repair) { failure.addSuppressed(repair); }
            throw failure;
        }
    }

    /** Keep an explicitly interrupted removal addressable for a later retry. */
    static void restoreDeleteRecord(Project project) throws IOException {
        File folder = project.source.getParentFile();
        if (!Files.exists(folder.toPath(), LinkOption.NOFOLLOW_LINKS)) return;
        writableDirectory(folder.toPath());
        if (!Files.exists(project.source.toPath(), LinkOption.NOFOLLOW_LINKS))
            Files.createDirectory(project.source.toPath());
        Z8Files.directory(folder, "source");
        write(folder, project.name, project.lastOpened);
    }

    private static void writableDirectory(Path directory) throws IOException {
        if (Files.isSymbolicLink(directory) || !Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS))
            throw new IOException(Z8Text.text("Could not verify the project directory to delete.", "삭제할 프로젝트 폴더를 확인할 수 없습니다."));
        if ((!Files.isWritable(directory) && !directory.toFile().setWritable(true, true))
                || (!Files.isReadable(directory) && !directory.toFile().setReadable(true, true))
                || (!Files.isExecutable(directory) && !directory.toFile().setExecutable(true, true)))
            throw new IOException(Z8Text.text("Could not access the project directory to delete.", "삭제할 프로젝트 폴더에 접근할 수 없습니다."));
    }

    private Path ownedSibling(String name, String projectId) throws IOException {
        Path parent = storage.getParentFile().toPath().resolve(name);
        if (!Files.exists(parent, LinkOption.NOFOLLOW_LINKS)) return null;
        if (Files.isSymbolicLink(parent) || !Files.isDirectory(parent, LinkOption.NOFOLLOW_LINKS))
            throw new IOException(Z8Text.text("Project ", "프로젝트 ") + name + Z8Text.text(" storage path could not be verified.", " 저장 경로를 확인할 수 없습니다."));
        Path target = parent.resolve(projectId);
        if (!Files.exists(target, LinkOption.NOFOLLOW_LINKS)) return null;
        if (Files.isSymbolicLink(target) || !Files.isDirectory(target, LinkOption.NOFOLLOW_LINKS))
            throw new IOException(Z8Text.text("Project ", "프로젝트 ") + name + Z8Text.text(" path is not a directory.", " 경로가 폴더가 아닙니다."));
        return target;
    }

    private static void removeTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override public FileVisitResult preVisitDirectory(Path directory, BasicFileAttributes attributes) throws IOException {
                // Package archives can contain read-only directories. Only the
                // app-owned visited directory is made writable, never a symlink.
                writableDirectory(directory);
                return FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attributes) throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult postVisitDirectory(Path directory, IOException failure) throws IOException {
                if (failure != null) throw failure;
                Files.delete(directory);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    private static void write(File folder, String name, long opened) throws IOException {
        Z8Files.directory(folder, "");
        Properties values = new Properties();
        values.setProperty("name", name);
        values.setProperty("opened", Long.toString(opened));
        values.setProperty("format", "1");
        Path temporary = Files.createTempFile(folder.toPath(), ".project-", ".tmp");
        try {
            try (Writer writer = Files.newBufferedWriter(temporary, StandardCharsets.UTF_8)) {
                values.store(writer, "Z8 project metadata; source is retained independently of runtime state");
            }
            Path target = new File(folder, "project.properties").toPath();
            if (Files.isSymbolicLink(target)) throw new IOException(Z8Text.text("The project metadata file was replaced by a link.", "프로젝트 정보 파일이 링크로 변경되었습니다."));
            Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } finally { Files.deleteIfExists(temporary); }
    }
}
