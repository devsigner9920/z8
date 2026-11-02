package com.termux.app;

import java.io.File;
import java.io.IOException;
import java.nio.file.DirectoryIteratorException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Bounded, read-only filename/path search. No indexing, file contents or link following. */
public final class Z8FileSearch {
    public static final int MAX_DEPTH = 32;
    public static final int MAX_VISITED = 20000;
    public static final int MAX_RESULTS = 200;
    public static final long MAX_MILLIS = 3000;
    public static final int MAX_QUERY = 120;
    public static final String EXCLUDED = ".git · node_modules · build · .gradle";

    public interface Cancellation { boolean cancelled(); }
    interface Clock { long nanoTime(); }
    public enum Limit { DEPTH, VISITED, RESULTS, TIME, CANCELLED, UNREADABLE, UNSUPPORTED_NAME }

    public static final class Match {
        public final String relative;
        public final boolean directory;
        Match(String relative, boolean directory) { this.relative = relative; this.directory = directory; }
    }

    public static final class Result {
        public final List<Match> matches;
        public final Set<Limit> limits;
        public final int visited;
        public final int ignoredDirectories;
        public final int ignoredLinks;
        public final long elapsedMillis;
        Result(Search search) {
            search.matches.sort(Comparator.comparing((Match match) -> !match.directory)
                .thenComparing(match -> match.relative.toLowerCase(Locale.ROOT))
                .thenComparing(match -> match.relative));
            matches = Collections.unmodifiableList(new ArrayList<>(search.matches));
            limits = Collections.unmodifiableSet(EnumSet.copyOf(search.limits));
            visited = search.visited;
            ignoredDirectories = search.ignoredDirectories;
            ignoredLinks = search.ignoredLinks;
            elapsedMillis = Math.max(0, (search.clock.nanoTime() - search.started) / 1000000L);
        }
        public boolean incomplete() { return !limits.isEmpty(); }
    }

    static final class Bounds {
        final int depth, visited, results;
        final long nanos;
        Bounds(int depth, int visited, int results, long millis) {
            if (depth < 1 || depth > MAX_DEPTH || visited < 1 || visited > MAX_VISITED
                    || results < 1 || results > MAX_RESULTS || millis < 1 || millis > MAX_MILLIS)
                throw new IllegalArgumentException(Z8Text.text("Invalid search limits.", "검색 제한값이 잘못되었습니다."));
            this.depth = depth; this.visited = visited; this.results = results;
            nanos = millis * 1000000L;
        }
    }

    private Z8FileSearch() {}

    public static Result search(File source, String query, Cancellation cancellation) throws IOException {
        return search(source, query, cancellation,
            new Bounds(MAX_DEPTH, MAX_VISITED, MAX_RESULTS, MAX_MILLIS), System::nanoTime);
    }

    static Result search(File source, String query, Cancellation cancellation, Bounds bounds, Clock clock) throws IOException {
        if (source == null || query == null || query.trim().isEmpty() || query.length() > MAX_QUERY)
            throw new IOException(Z8Text.text("Enter a search term of 1–120 characters.", "검색어를 1~120자로 입력해 주세요."));
        for (int index = 0; index < query.length(); index++)
            if (Character.isISOControl(query.charAt(index))) throw new IOException(Z8Text.text("Search terms cannot contain control characters.", "검색어에 제어 문자를 사용할 수 없습니다."));
        Path root = source.toPath().toAbsolutePath().normalize();
        Path cursor = root.getRoot();
        for (Path component : root) {
            cursor = cursor.resolve(component);
            if (Files.isSymbolicLink(cursor)) throw new IOException(Z8Text.text("Projects cannot be searched through symbolic links.", "링크를 통해 프로젝트를 검색할 수 없습니다."));
        }
        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) throw new IOException(Z8Text.text("The project folder is missing.", "프로젝트 폴더가 없습니다."));
        root = root.toFile().getCanonicalFile().toPath();
        Search search = new Search(root, query.trim().toLowerCase(Locale.ROOT), cancellation, bounds, clock);
        search.walk(root, 0, true);
        return new Result(search);
    }

    private static final class Search {
        final Path root;
        final String query;
        final Cancellation cancellation;
        final Bounds bounds;
        final Clock clock;
        final long started;
        final List<Match> matches = new ArrayList<>();
        final EnumSet<Limit> limits = EnumSet.noneOf(Limit.class);
        int visited, ignoredDirectories, ignoredLinks;
        boolean stopped;

        Search(Path root, String query, Cancellation cancellation, Bounds bounds, Clock clock) {
            this.root = root; this.query = query; this.cancellation = cancellation;
            this.bounds = bounds; this.clock = clock; started = clock.nanoTime();
        }

        boolean stop() {
            if (stopped) return true;
            if (Thread.currentThread().isInterrupted() || (cancellation != null && cancellation.cancelled())) {
                limits.add(Limit.CANCELLED); stopped = true;
            } else if (clock.nanoTime() - started >= bounds.nanos) {
                limits.add(Limit.TIME); stopped = true;
            }
            return stopped;
        }

        boolean contained(Path path) throws IOException {
            if (!path.normalize().startsWith(root)) return false;
            Path cursor = root;
            if (Files.isSymbolicLink(root)) return false;
            for (Path component : root.relativize(path)) {
                cursor = cursor.resolve(component);
                if (Files.isSymbolicLink(cursor)) return false;
            }
            return path.toFile().getCanonicalFile().toPath().startsWith(root);
        }

        void walk(Path directory, int depth, boolean initial) throws IOException {
            if (stop()) return;
            try {
                if (!contained(directory) || !Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)) {
                    if (initial) throw new IOException(Z8Text.text("The project path has changed.", "프로젝트 경로가 변경되었습니다."));
                    limits.add(Limit.UNREADABLE); return;
                }
                try (DirectoryStream<Path> entries = Files.newDirectoryStream(directory)) {
                    if (!contained(directory)) {
                        if (initial) throw new IOException(Z8Text.text("The project path has changed.", "프로젝트 경로가 변경되었습니다."));
                        limits.add(Limit.UNREADABLE); return;
                    }
                    for (Path entry : entries) {
                        if (stop()) return;
                        if (visited >= bounds.visited) { limits.add(Limit.VISITED); stopped = true; return; }
                        visited++;
                        String name = entry.getFileName().toString();
                        if (!safeName(name)) { limits.add(Limit.UNSUPPORTED_NAME); continue; }
                        BasicFileAttributes attributes;
                        try {
                            attributes = Files.readAttributes(entry, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
                            if (attributes.isSymbolicLink()) { ignoredLinks++; continue; }
                            if (!contained(entry)) { limits.add(Limit.UNREADABLE); continue; }
                        } catch (IOException failure) { limits.add(Limit.UNREADABLE); continue; }
                        if (attributes.isDirectory() && excluded(name)) { ignoredDirectories++; continue; }
                        if (!attributes.isDirectory() && !attributes.isRegularFile()) continue;
                        String relative = root.relativize(entry).toString().replace(File.separatorChar, '/');
                        if (relative.toLowerCase(Locale.ROOT).contains(query)) {
                            matches.add(new Match(relative, attributes.isDirectory()));
                            if (matches.size() >= bounds.results) { limits.add(Limit.RESULTS); stopped = true; return; }
                        }
                        if (attributes.isDirectory()) {
                            if (depth + 1 >= bounds.depth) limits.add(Limit.DEPTH);
                            else walk(entry, depth + 1, false);
                        }
                    }
                }
            } catch (DirectoryIteratorException failure) {
                if (initial) throw failure.getCause();
                limits.add(Limit.UNREADABLE);
            } catch (IOException failure) {
                if (initial) throw failure;
                limits.add(Limit.UNREADABLE);
            }
        }
    }

    private static boolean excluded(String name) {
        return name.equals(".git") || name.equals("node_modules") || name.equals("build") || name.equals(".gradle");
    }

    private static boolean safeName(String name) {
        if (name.isEmpty() || name.length() > 120 || name.equals(".") || name.equals("..")
                || name.indexOf('/') >= 0 || name.indexOf('\\') >= 0) return false;
        for (int index = 0; index < name.length(); index++)
            if (Character.isISOControl(name.charAt(index))) return false;
        return true;
    }
}
