"""Run the production Java extractor against hostile fixtures and an optional real artifact."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GuestArchiveTests(unittest.TestCase):
    def test_extractor_and_real_image_when_present(self):
        jdk = ROOT / ".local/jdk/Contents/Home/bin"
        javac = str(jdk / "javac") if (jdk / "javac").is_file() else shutil.which("javac")
        java = str(jdk / "java") if (jdk / "java").is_file() else shutil.which("java")
        if not javac or not java:
            self.skipTest("Guest archive tests require a JDK")
        with tempfile.TemporaryDirectory(prefix="z8-guest-tests-") as temporary:
            directory = Path(temporary).resolve()
            probe = directory / "GuestArchiveProbe.java"
            probe.write_text(JAVA_PROBE)
            source = ROOT / "overlay/app/src/main/java/com/termux/app/Z8GuestArchive.java"
            compiled = subprocess.run([javac, str(ROOT / 'overlay/app/src/main/java/com/termux/app/Z8Text.java'), "-encoding", "UTF-8", "-d", str(directory), str(source), str(probe)],
                capture_output=True, text=True, timeout=45)
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            arguments = [java, "-cp", str(directory), "com.termux.app.GuestArchiveProbe", str(directory / "fixtures")]
            candidates = sorted((ROOT / "artifacts/guest").glob("*/*/manifest.json"), key=lambda path: path.stat().st_mtime)
            if candidates:
                manifest_path = candidates[-1]
                manifest = json.loads(manifest_path.read_text())
                converted = directory / "real-manifest.tsv"
                lines = [f"{manifest['archiveSha256']}\t{manifest['archiveBytes']}\t{manifest['totalUncompressedBytes']}"]
                for item in manifest["files"]:
                    self.assertNotIn("\t", item["path"])
                    self.assertNotIn("\n", item["path"])
                    lines.append(f"{item['path']}\t{1 if item['type'] == 'directory' else 0}\t{item['size']}\t{item['mode']}")
                converted.write_text("\n".join(lines) + "\n")
                arguments += [str(manifest_path.parent / "rootfs.zip"), str(converted)]
            tested = subprocess.run(arguments, capture_output=True, text=True, timeout=60)
            self.assertEqual(0, tested.returncode, tested.stdout + tested.stderr)
            self.assertIn("PASS: archive safety", tested.stdout)
            if candidates:
                self.assertIn("PASS: real image extraction", tested.stdout)


JAVA_PROBE = r'''
package com.termux.app;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;

public class GuestArchiveProbe {
    interface Action { void run() throws Exception; }
    static int checks;
    static File base;
    static byte[] bytes(String value) { return value.getBytes(StandardCharsets.UTF_8); }
    static void check(boolean value, String message) { if (!value) throw new AssertionError(message); checks++; }
    static void denied(Action action, String message) throws Exception {
        try { action.run(); } catch (IOException expected) { checks++; return; }
        throw new AssertionError(message);
    }
    static File stage() throws Exception { return Files.createTempDirectory(base.toPath(), "stage-").toFile(); }
    static class Image {
        final byte[] zip;
        final Z8GuestArchive.Manifest manifest;
        Image(String links) throws Exception {
            LinkedHashMap<String, byte[]> files = new LinkedHashMap<>();
            files.put("usr/", new byte[0]); files.put("usr/bin/", new byte[0]);
            files.put("usr/bin/bash", bytes("#!/bin/sh\n")); files.put("SYMLINKS.txt", bytes(links));
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            List<Z8GuestArchive.Item> items = new ArrayList<>(); long total = 0;
            try (ZipOutputStream stream = new ZipOutputStream(output)) {
                for (Map.Entry<String, byte[]> entry : files.entrySet()) {
                    ZipEntry item = new ZipEntry(entry.getKey()); stream.putNextEntry(item);
                    stream.write(entry.getValue()); stream.closeEntry();
                    boolean directory = entry.getKey().endsWith("/");
                    items.add(new Z8GuestArchive.Item(entry.getKey(), directory, entry.getValue().length, directory || entry.getKey().endsWith("bash") ? 0755 : 0600));
                    total += entry.getValue().length;
                }
            }
            zip = output.toByteArray();
            StringBuilder hash = new StringBuilder();
            for (byte value : MessageDigest.getInstance("SHA-256").digest(zip)) hash.append(String.format("%02x", value & 255));
            manifest = new Z8GuestArchive.Manifest(hash.toString(), zip.length, total, items);
        }
        void unpack(File target) throws Exception {
            Z8GuestArchive.extract(() -> new ByteArrayInputStream(zip), manifest, target, (percent, detail) -> {});
        }
    }
    public static void main(String[] args) throws Exception {
        base = new File(args[0]); base.mkdir();
        Image good = new Image("usr/bin←bin\n");
        File valid = stage(); good.unpack(valid);
        check(Files.isSymbolicLink(new File(valid, "bin").toPath()), "deferred link created");
        check(new File(valid, "bin/bash").isFile() && new File(valid, "bin/bash").canExecute(), "file contents and executable mode");
        check(!new File(valid, "SYMLINKS.txt").exists(), "link metadata consumed, not installed as guest content");
        File preexisting = stage(); Files.write(new File(preexisting, "keep").toPath(), bytes("user"));
        denied(() -> good.unpack(preexisting), "never extract into nonempty directory");
        check(new String(Files.readAllBytes(new File(preexisting, "keep").toPath())).equals("user"), "preexisting content preserved");
        Z8GuestArchive.Manifest wrongHash = new Z8GuestArchive.Manifest(String.join("", Collections.nCopies(64, "0")),
            good.zip.length, good.manifest.expandedBytes, new ArrayList<>(good.manifest.items.values()));
        File badHash = stage();
        denied(() -> Z8GuestArchive.extract(() -> new ByteArrayInputStream(good.zip), wrongHash, badHash, (p,d) -> {}), "hash mismatch");
        check(badHash.list().length == 0, "hash verified before writing files");
        denied(() -> Z8GuestArchive.path("../escape", false), "traversal path");
        denied(() -> Z8GuestArchive.path("/absolute", false), "absolute path");
        denied(() -> Z8GuestArchive.path("usr//file", false), "empty path component");
        denied(() -> Z8GuestArchive.path("usr\\file", false), "backslash path");
        denied(() -> new Image("../../outside←escape\n").unpack(stage()), "relative link escape");
        denied(() -> new Image(".←a\na/../outside←b\n").unpack(stage()), "symlink followed before dotdot");
        denied(() -> new Image("b←a\na←b\n").unpack(stage()), "symlink cycle");
        denied(() -> new Image("usr←usr/bin\n").unpack(stage()), "link overlaps a real directory");
        denied(() -> new Image("usr←usr\n").unpack(stage()), "link cannot parent regular entries");
        denied(() -> new Image("/outside←escape\n").unpack(stage()), "absolute symlink target");
        denied(() -> new Image("usr←a\nusr←a/sub\n").unpack(stage()), "link cannot parent another link");
        List<Z8GuestArchive.Item> wrongSize = new ArrayList<>(good.manifest.items.values());
        for (int i = 0; i < wrongSize.size(); i++) {
            Z8GuestArchive.Item item = wrongSize.get(i);
            if (item.path.equals("usr/bin/bash")) wrongSize.set(i, new Z8GuestArchive.Item(item.path, false, item.size - 1, item.mode));
        }
        Z8GuestArchive.Manifest bounded = new Z8GuestArchive.Manifest(good.manifest.sha256, good.zip.length,
            good.manifest.expandedBytes - 1, wrongSize);
        denied(() -> Z8GuestArchive.extract(() -> new ByteArrayInputStream(good.zip), bounded, stage(), (p,d) -> {}), "expanded data size mismatch");
        List<Z8GuestArchive.Item> missing = new ArrayList<>(good.manifest.items.values());
        missing.add(new Z8GuestArchive.Item("missing", false, 0, 0644));
        Z8GuestArchive.Manifest expectedMissing = new Z8GuestArchive.Manifest(good.manifest.sha256, good.zip.length,
            good.manifest.expandedBytes, missing);
        denied(() -> Z8GuestArchive.extract(() -> new ByteArrayInputStream(good.zip), expectedMissing, stage(), (p,d) -> {}), "missing inventory item");
        System.out.println("PASS: archive safety (" + checks + " checks)");
        if (args.length == 3) {
            List<String> lines = Files.readAllLines(Paths.get(args[2]), StandardCharsets.UTF_8);
            String[] header = lines.remove(0).split("\t");
            List<Z8GuestArchive.Item> items = new ArrayList<>();
            for (String line : lines) {
                String[] part = line.split("\t");
                items.add(new Z8GuestArchive.Item(part[0], part[1].equals("1"), Long.parseLong(part[2]), Integer.parseInt(part[3])));
            }
            Z8GuestArchive.Manifest manifest = new Z8GuestArchive.Manifest(header[0], Long.parseLong(header[1]), Long.parseLong(header[2]), items);
            File rootfs = stage();
            Z8GuestArchive.extract(() -> Files.newInputStream(Paths.get(args[1])), manifest, rootfs, (p,d) -> {});
            check(new File(rootfs, "bin/bash").isFile() && new File(rootfs, "bin/bash").canExecute(), "real image bash path");
            check(new File(rootfs, "etc/z8/shellrc").isFile(), "real image managed profile");
            check(Files.isSymbolicLink(new File(rootfs, "dev/fd").toPath()), "real image descriptor links");
            System.out.println("PASS: real image extraction " + header[0]);
        }
    }
}
'''


if __name__ == "__main__":
    unittest.main()
