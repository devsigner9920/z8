package com.termux.app;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.Locale;

/** Narrow HTML-link parsing and project-local path mapping. No shell interpolation. */
public final class Z8TerminalPath {
    private Z8TerminalPath() { }

    /** A printed filename is only a candidate; existence and provenance are checked off the UI thread. */
    public static String htmlToken(String printed) {
        if (printed == null || printed.isEmpty() || printed.length() > 4096) return null;
        String value = printed;
        while (value.length() > 1 && "`'\"([<".indexOf(value.charAt(0)) >= 0)
            value = value.substring(1);
        while (value.length() > 1 && "`'\")]>,.;!?".indexOf(value.charAt(value.length() - 1)) >= 0)
            value = value.substring(0, value.length() - 1);
        value = value.replaceFirst(":[0-9]+(?::[0-9]+)?$", "");
        while (value.startsWith("./")) value = value.substring(2);
        String lower = value.toLowerCase(Locale.ROOT);
        if (!(lower.endsWith(".html") || lower.endsWith(".htm")) || value.isEmpty()) return null;
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (Character.isWhitespace(c) || Character.isISOControl(c) || "\\:$;&|<>`\"'?#()[]".indexOf(c) >= 0)
                return null;
        }
        String[] parts = value.split("/", -1);
        for (int i = 0; i < parts.length; i++)
            if (parts[i].startsWith(".") || parts[i].isEmpty() && (i != 0 || !value.startsWith("/"))) return null;
        return value;
    }

    public static final class Matches {
        public final java.util.List<String> paths = new java.util.ArrayList<>();
        public boolean complete = true;
    }

    /** PRoot does not expose guest cwd in /proc. Search by suffix, never pretend it is known. */
    public static Matches find(String token, Path home, Path source) throws IOException {
        return find(token, home, source, 12000, 10, 2_000_000_000L);
    }

    static Matches find(String token, Path home, Path source, int entryLimit, int depthLimit, long timeLimit) throws IOException {
        String suffix = htmlToken(token);
        if (suffix == null) throw new IOException("HTML filename required");
        Matches result = new Matches();
        if (suffix.startsWith("/")) {
            result.paths.add(resolve(suffix, null, home, source));
            return result;
        }
        long deadline = System.nanoTime() + timeLimit;
        int[] visited = {0};
        search(root(home), root(home), suffix, "/z8/home/", result, visited, entryLimit, depthLimit, deadline);
        if (result.complete) search(root(source), root(source), suffix, "/workspace/", result, visited, entryLimit, depthLimit, deadline);
        java.util.Collections.sort(result.paths);
        return result;
    }

    private static void search(Path root, Path directory, String suffix, String guest, Matches result,
            int[] visited, int limit, int depth, long deadline) throws IOException {
        if (!result.complete) return;
        if (System.nanoTime() > deadline || visited[0] >= limit || result.paths.size() >= 20) { result.complete = false; return; }
        try (java.nio.file.DirectoryStream<Path> children = Files.newDirectoryStream(directory)) {
            for (Path child : children) {
                if (++visited[0] > limit || System.nanoTime() > deadline) { result.complete = false; return; }
                String name = child.getFileName().toString();
                if (name.startsWith(".") || name.equals("node_modules") || name.equals("venv") || name.equals("__pycache__")
                        || Files.isSymbolicLink(child)) continue;
                if (Files.isDirectory(child, LinkOption.NOFOLLOW_LINKS)) {
                    if (depth <= 0) { result.complete = false; return; }
                    search(root, child, suffix, guest, result, visited, limit, depth - 1, deadline);
                    if (!result.complete) return;
                } else if (Files.isRegularFile(child, LinkOption.NOFOLLOW_LINKS)) {
                    String relative = root.relativize(child).toString().replace(File.separatorChar, '/');
                    if ((relative.equals(suffix) || relative.endsWith("/" + suffix))
                            && Files.size(child) <= 32L * 1024 * 1024) {
                        result.paths.add(guest + relative);
                        if (result.paths.size() >= 20) { result.complete = false; return; }
                    }
                }
            }
        } catch (java.nio.file.AccessDeniedException | java.nio.file.NoSuchFileException changed) {
            result.complete = false;
        }
    }

    /** Resolve only the selected existing regular HTML file, without crossing a link or a project boundary. */
    public static String resolve(String token, Path currentDirectory, Path home, Path source) throws IOException {
        String path = htmlToken(token);
        if (path == null) throw new IOException("HTML filename required");
        Path homeRoot = root(home);
        Path sourceRoot = root(source);
        Path target;
        if (path.startsWith("/z8/home/")) target = homeRoot.resolve(path.substring("/z8/home/".length()));
        else if (path.startsWith("/workspace/")) target = sourceRoot.resolve(path.substring("/workspace/".length()));
        else if (path.startsWith("/")) throw new IOException("HTML file is outside this project");
        else {
            if (currentDirectory == null) throw new IOException("Current directory unavailable");
            target = currentDirectory.toRealPath().resolve(path);
        }
        target = target.normalize();
        Path root;
        String guestRoot;
        if (inside(target, homeRoot)) { root = homeRoot; guestRoot = "/z8/home/"; }
        else if (inside(target, sourceRoot)) { root = sourceRoot; guestRoot = "/workspace/"; }
        else throw new IOException("HTML file is outside this project");
        Path current = root;
        for (Path part : root.relativize(target)) {
            current = current.resolve(part);
            if (Files.isSymbolicLink(current)) throw new IOException("HTML links cannot cross symlinks");
        }
        if (!Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS) || Files.size(target) > 32L * 1024 * 1024)
            throw new IOException("HTML file unavailable");
        return guestRoot + root.relativize(target).toString().replace(File.separatorChar, '/');
    }

    /** The app files directory is trusted; every project-home component below it must be a real directory. */
    public static Path directory(Path trustedAnchor, String relative) throws IOException {
        Path current = trustedAnchor.toRealPath();
        for (String part : relative.split("/", -1)) {
            if (part.isEmpty() || part.equals(".") || part.equals("..") || part.indexOf('\\') >= 0)
                throw new IOException("Project directory unavailable");
            current = current.resolve(part);
            if (Files.isSymbolicLink(current) || !Files.isDirectory(current, LinkOption.NOFOLLOW_LINKS))
                throw new IOException("Project directory unavailable");
        }
        return current;
    }

    private static Path root(Path path) throws IOException {
        if (Files.isSymbolicLink(path) || !Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS))
            throw new IOException("Project folder unavailable");
        return path.toRealPath();
    }

    private static boolean inside(Path path, Path root) throws IOException {
        Path checkedRoot = root.toRealPath();
        return path.startsWith(checkedRoot);
    }

}
