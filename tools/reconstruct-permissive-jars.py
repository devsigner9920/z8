#!/usr/bin/env python3
"""Offline, bounded reconstruction of four retained Java main libraries.

This is a functional reconstruction recipe, not a reproducible-build claim or
source-closure approval. No original target binary is used as compiler input.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import zipfile


# Published source JARs already retained by collect-maven-sources.py.
TARGETS = [
    ("com.atlassian.commonmark", "commonmark", "0.13.0",
     "f82d692fbc09e99567f822442d3f7a490b9ac10263365a03fa91ba659f65e694", 97),
    ("com.atlassian.commonmark", "commonmark-ext-gfm-strikethrough", "0.13.0",
     "e8cff657cc99797cc58a27956523dc372a04bb02857d331f1b639c65a8af0dcb", 6),
    ("com.google.guava", "guava", "24.1-jre",
     "3310420b11e001734f60b855ddbfad5ee615a8b0bb013e58517272a3676960e4", 570),
    ("commons-io", "commons-io", "2.5",
     "3b69b518d9a844732e35509b79e499fca63a960ee4301b1c96dc32e87f3f60a1", 115),
]
# These are the app's resolved compile annotations, not all upstream test/plugin
# dependencies. Error Prone 2.15.0 is the resolved replacement for POM 2.1.3.
DEPENDENCIES = [
    ("com.google.code.findbugs", "jsr305", "1.3.9", "905721a0eea90a81534abb7ee6ef4ea2e5e645fa1def0a5cd88402df1b46c9ed"),
    ("org.checkerframework", "checker-compat-qual", "2.0.0", "a40b2ce6d8551e5b90b1bf637064303f32944d61b52ab2014e38699df573941b"),
    ("com.google.errorprone", "error_prone_annotations", "2.15.0", "067047714349e7789a5bdbfad9d1c0af9f3a1eb28c55a0ee3f68e682f905c4eb"),
    ("com.google.j2objc", "j2objc-annotations", "1.1", "2994a7eb78f2710bd3d3bfb639b2c94e219cedac0d4d084d516e78c16dddecf6"),
    ("org.codehaus.mojo", "animal-sniffer-annotations", "1.14", "2068320bd6bad744c3673ab048f67e30bef8f518996fa380033556600669905d"),
]
COMMONMARK_LICENSE_SHA256 = "4c1ea7a8104cd00a7e62b794cc317aedca2e68c647048b5f546fc7388dddd306"
APACHE_LICENSE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
COMMONMARK_UPSTREAM_SHA256 = "66d1374a090a06a01ea412d65dacb92c496e1def153a77e813cbd0fc0a0b5602"
COMMONMARK_UPSTREAM_COMMIT = "f7716897f9e37f03d023cf713e92a5b1ced59bc1"

SMOKE = r'''import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import com.google.common.cache.*;
import com.google.common.base.Splitter;
import com.google.common.collect.*;
import com.google.common.graph.*;
import com.google.common.hash.Hashing;
import com.google.common.util.concurrent.*;
import org.commonmark.Extension;
import org.commonmark.parser.Parser;
import org.commonmark.renderer.html.HtmlRenderer;
import org.commonmark.ext.gfm.strikethrough.StrikethroughExtension;
import org.apache.commons.io.*;

public final class ReconstructionSmoke {
    private static void check(boolean ok, String name) {
        if (!ok) throw new AssertionError(name);
    }
    public static void main(String[] args) throws Exception {
        check(ImmutableList.of("a", "b").reverse().get(0).equals("b"), "immutable list");
        check(Splitter.on(',').splitToList("a,b").equals(Arrays.asList("a", "b")), "base iterator");
        check(Iterators.filter(Arrays.asList(1, 2, 3).iterator(), value -> value > 1).next() == 2,
            "collection iterator");
        MutableGraph<String> graph = GraphBuilder.directed().nodeOrder(ElementOrder.<String>natural()).build();
        graph.putEdge("b", "a");
        check(graph.nodes().iterator().next().equals("a") && graph.hasEdgeConnecting("b", "a"), "ordered graph");
        LoadingCache<String, Integer> cache = CacheBuilder.newBuilder().maximumSize(8)
            .recordStats().build(new CacheLoader<String, Integer>() {
                public Integer load(String key) { return key.length(); }
            });
        check(cache.get("hello") == 5 && cache.get("hello") == 5
            && cache.stats().hitCount() == 1, "loading cache and counters");
        SettableFuture<Integer> input = SettableFuture.create();
        ListenableFuture<Integer> result = Futures.transform(input,
            value -> value + 1, MoreExecutors.directExecutor());
        input.set(41);
        check(result.get(1, TimeUnit.SECONDS) == 42, "future completion");
        check(Hashing.sha256().hashString("abc", StandardCharsets.UTF_8).toString()
            .equals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"), "hash");
        System.out.println("PASS Guava: collections/iterators/graph, loading cache/counters, futures, SHA-256");

        String markdown = "# Hello\n\n&amp; &Aacute; **bold** ~~old~~ [link][id]\n\n[id]: https://example.invalid/\n";
        List<Extension> extensions = Collections.singletonList(StrikethroughExtension.create());
        String html = HtmlRenderer.builder().extensions(extensions).build().render(
            Parser.builder().extensions(extensions).build().parse(markdown));
        check(html.equals("<h1>Hello</h1>\n<p>&amp; Á <strong>bold</strong> <del>old</del> <a href=\"https://example.invalid/\">link</a></p>\n"),
            "CommonMark parser, entities.properties, renderer and GFM extension");
        System.out.println("PASS CommonMark: parser, named entity resource, HTML, GFM strikethrough");

        byte[] data = new byte[16391];
        for (int i = 0; i < data.length; i++) data[i] = (byte) (i * 31);
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        check(IOUtils.copy(new ByteArrayInputStream(data), output) == data.length
            && Arrays.equals(data, output.toByteArray()), "stream copy");
        check(IOUtils.toString(new ByteArrayInputStream("한글 café".getBytes(StandardCharsets.UTF_8)),
            StandardCharsets.UTF_8).equals("한글 café"), "UTF-8 decoding");
        check(FilenameUtils.normalize("a/b/../c.txt").equals("a/c.txt")
            && FilenameUtils.wildcardMatch("report.txt", "*.txt"), "filename operations");
        System.out.println("PASS Commons IO: multi-buffer copy, UTF-8, path normalization, wildcard");
    }
}
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_bytes(path, expected, size=None):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular input file: " + path.name)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Input exceeds bounded recipe size: " + path.name)
    data = path.read_bytes()
    if digest(data) != expected or (size is not None and len(data) != size):
        raise ValueError("Input checksum/size mismatch: " + path.name)
    return data


def safe_relative(value):
    if not isinstance(value, str) or "\\" in value or "\x00" in value:
        raise ValueError("Unsafe input path")
    parts = value.split("/")
    if not value or any(part in ("", ".", "..") for part in parts):
        raise ValueError("Unsafe input path")
    return PurePosixPath(value)


def confined(root, value):
    relative = safe_relative(value)
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlink in input path")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Input outside inventory root")
    return path


def component(items, group, name, version):
    selected = [x for x in items if (x.get("group"), x.get("name"), x.get("version"))
                == (group, name, version)]
    if len(selected) != 1:
        raise ValueError("Expected exactly one component: " + ":".join((group, name, version)))
    return selected[0]


def source_members(data):
    members = {}
    total = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if len(archive.infolist()) > 10000:
            raise ValueError("Too many source archive entries")
        for info in archive.infolist():
            name = info.filename.rstrip("/") if info.is_dir() else info.filename
            safe_relative(name)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("Source archive symlink")
            if info.is_dir():
                continue
            total += info.file_size
            if name in members or info.file_size > 8 * 1024 * 1024 or total > 64 * 1024 * 1024:
                raise ValueError("Duplicate or oversized source archive member")
            if name.endswith((".class", ".jar")):
                raise ValueError("Compiled code is not a source input")
            members[name] = archive.read(info)
    return members


def commonmark_license(inventory, root, override):
    if override:
        return checked_bytes(override, COMMONMARK_LICENSE_SHA256, 1305)
    item = component(inventory["components"], "com.atlassian.commonmark", "commonmark", "0.13.0")
    records = [r for r in item.get("upstreamSnapshot", {}).get("inputs", [])
               if r.get("sha256") == COMMONMARK_UPSTREAM_SHA256]
    if len(records) != 1:
        raise ValueError("Retained CommonMark upstream missing; supply --commonmark-license for older inventories")
    record = records[0]
    payload = checked_bytes(confined(root, record["path"]), COMMONMARK_UPSTREAM_SHA256, 430556)
    member = "commonmark-java-" + COMMONMARK_UPSTREAM_COMMIT + "/LICENSE.txt"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        matches = [entry for entry in archive.infolist() if entry.filename == member]
        if len(matches) != 1 or matches[0].file_size != 1305:
            raise ValueError("Unexpected retained CommonMark license member")
        license_bytes = archive.read(matches[0])
    if digest(license_bytes) != COMMONMARK_LICENSE_SHA256:
        raise ValueError("Retained CommonMark license checksum mismatch")
    return license_bytes


def write_members(root, members):
    for name, data in members.items():
        path = root / safe_relative(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def run(command, output, log_name):
    env = dict(os.environ)
    # Explicit classpaths/proc:none plus removal of ambient JVM injection prevent
    # a user's cached target JAR/annotation processor from satisfying the build.
    for key in ("CLASSPATH", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "JDK_JAVAC_OPTIONS", "_JAVA_OPTIONS"):
        env.pop(key, None)
    result = subprocess.run(command, cwd=output, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=180)
    (output / log_name).write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise RuntimeError("Command failed; see " + log_name)
    return result.stdout.strip()


def pack_jar(path, members):
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)


def reconstruct(args):
    inventory_path = args.maven_sources.resolve()
    inventory = json.loads(inventory_path.read_text())
    gradle = json.loads(args.gradle_inventory.read_text())
    apache = checked_bytes(args.apache_license, APACHE_LICENSE_SHA256)
    bsd_license = commonmark_license(inventory, inventory_path.parent, args.commonmark_license)
    java_home = args.java_home.resolve()
    javac, java = java_home / "bin/javac", java_home / "bin/java"
    if not javac.is_file() or not java.is_file():
        raise ValueError("--java-home must contain bin/javac and bin/java")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)  # Never reuse stale output classes.
    dependencies, dependency_records = [], []
    for group, name, version, checksum in DEPENDENCIES:
        record = component(gradle["components"], group, name, version)
        if record.get("type") != "jar" or record.get("sha256") != checksum:
            raise ValueError("Unexpected pinned compile dependency: " + name)
        filename = name + "-" + version + ".jar"
        path = (confined(args.dependency_dir.resolve(), filename) if args.dependency_dir else
                confined(args.binary_root.resolve(), record["file"]))
        data = checked_bytes(path, checksum)
        target = output / "dependencies" / filename
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(data)
        dependencies.append(str(target.relative_to(output)))
        dependency_records.append({"coordinate": ":".join((group, name, version)), "sha256": checksum})

    report = {"schemaVersion": 1, "kind": "z8-functional-main-jar-reconstruction",
              "sourceClosureReviewed": False, "byteIdenticalClaim": False,
              "mavenInventorySha256": digest(inventory_path.read_bytes()),
              "gradleInventorySha256": digest(args.gradle_inventory.read_bytes()),
              "javac": run([str(javac), "-version"], output, "javac-version.txt"),
              "java": run([str(java), "-version"], output, "java-version.txt"),
              "compileDependencies": dependency_records, "libraries": []}
    report["additionalLicenseInputs"] = {
        "commonmarkLicenseSha256": COMMONMARK_LICENSE_SHA256,
        "commonmarkUpstreamArchiveSha256": None if args.commonmark_license else COMMONMARK_UPSTREAM_SHA256,
        "apacheLicenseSha256": APACHE_LICENSE_SHA256}
    built = []
    for group, name, version, checksum, java_count in TARGETS:
        selected = component(inventory["components"], group, name, version)
        records = [r for r in selected["sourceFiles"] if r.get("role") == "published-source-jar"]
        if len(records) != 1 or records[0]["sha256"] != checksum:
            raise ValueError("Unexpected source JAR for " + name)
        record = records[0]
        data = checked_bytes(confined(inventory_path.parent, record["path"]), checksum, record["bytes"])
        members = source_members(data)
        java_files = sorted(n for n in members if n.endswith(".java"))
        if len(java_files) != java_count:
            raise ValueError("Unexpected Java source count for " + name)
        source_dir = output / "sources" / name
        write_members(source_dir, members)
        pom_records = []
        for pom in selected["metadataFiles"]:
            if pom.get("role") != "pom":
                continue
            payload = checked_bytes(confined(inventory_path.parent, pom["path"]), pom["sha256"], pom["bytes"])
            filename = PurePosixPath(pom["path"]).name
            dest = output / "provenance" / name / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(payload)
            pom_records.append({"name": filename, "sha256": pom["sha256"]})
        if not pom_records:
            raise ValueError("Missing POM provenance for " + name)

        classes = output / "classes" / name
        classes.mkdir(parents=True)
        empty = output / "empty-classpath"
        empty.mkdir(exist_ok=True)
        classpath = dependencies if name == "guava" else ([built[0]] if name.endswith("strikethrough") else ["empty-classpath"])
        # Guava 24.1 directly references sun.misc.Unsafe, which --release hides.
        # Its unchanged Java 8 source compiles against the selected JDK instead.
        flags = ["-source", "8", "-target", "8"] if name == "guava" else ["--release", "8"]
        source_relative = source_dir.relative_to(output)
        command = [str(javac), *flags, "-encoding", "UTF-8", "-proc:none", "-implicit:none",
                   "-classpath", os.pathsep.join(classpath), "-sourcepath", str(source_relative),
                   "-d", str(classes.relative_to(output)), *[str(source_relative / p) for p in java_files]]
        run(command, output, name + "-compile.log")
        jar_members = {p.relative_to(classes).as_posix(): p.read_bytes() for p in classes.rglob("*.class")}
        class_count = len(jar_members)
        for member, payload in members.items():
            if not member.endswith(".java"):
                target = "META-INF/z8-reconstruction/source-manifest.mf" if member == "META-INF/MANIFEST.MF" else member
                jar_members[target] = payload
        if name.startswith("commonmark"):
            jar_members["META-INF/LICENSE.txt"] = bsd_license
        if name == "guava":
            jar_members["META-INF/LICENSE.txt"] = apache
        jar_members["META-INF/MANIFEST.MF"] = (
            "Manifest-Version: 1.0\r\nCreated-By: Z8 functional source reconstruction\r\n\r\n").encode()
        jar_path = output / (name + "-" + version + "-reconstructed.jar")
        pack_jar(jar_path, jar_members)
        built.append(jar_path.name)
        # Reopen the packaged result: resource/legal preservation is checked on
        # the actual delivered JAR, rather than only the intermediate directory.
        with zipfile.ZipFile(jar_path) as jar:
            for member, payload in jar_members.items():
                if jar.read(member) != payload:
                    raise ValueError("Packaged resource/class mismatch")
        report["libraries"].append({"coordinate": ":".join((group, name, version)),
            "sourceJarSha256": checksum, "javaSourceCount": java_count,
            "classCount": class_count, "compilerFlags": flags,
            "classpath": classpath, "originalTargetBinaryUsed": False,
            "poms": pom_records, "jar": jar_path.name, "jarSha256": digest(jar_path.read_bytes()),
            "nonClassMembers": [{"name": n, "sha256": digest(p)} for n, p in sorted(jar_members.items())
                                if not n.endswith(".class")]})

    (output / "ReconstructionSmoke.java").write_text(SMOKE, encoding="utf-8")
    (output / "smoke-classes").mkdir()
    smoke_classpath = os.pathsep.join(built + dependencies)
    run([str(javac), "--release", "8", "-encoding", "UTF-8", "-proc:none", "-implicit:none",
         "-classpath", smoke_classpath, "-sourcepath", "empty-classpath", "-d", "smoke-classes",
         "ReconstructionSmoke.java"], output, "smoke-compile.log")
    report["functionalSmoke"] = run([str(java), "-cp", "smoke-classes" + os.pathsep + smoke_classpath,
                                      "ReconstructionSmoke"], output, "functional-smoke.log").splitlines()
    report["status"] = "PASS"
    (output / "reconstruction-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: four main libraries compiled; resource/legal preservation and functional smoke passed.")
    print("Evidence: " + str(output / "reconstruction-report.json"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maven-sources", type=Path, required=True)
    parser.add_argument("--gradle-inventory", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--commonmark-license", type=Path,
                        help="Optional exact Atlassian LICENSE.txt for older inventories lacking upstream supplement")
    parser.add_argument("--apache-license", type=Path, default=Path(__file__).resolve().parents[1] / "LICENSES/Apache-2.0.txt")
    parser.add_argument("--dependency-dir", type=Path, help="Five pinned dependency JARs by filename")
    parser.add_argument("--binary-root", type=Path, default=Path.cwd(), help="Root for Gradle inventory cache paths")
    parser.add_argument("--output", type=Path, required=True, help="New output directory; must not exist")
    args = parser.parse_args()
    try:
        reconstruct(args)
    except (ValueError, KeyError, OSError, RuntimeError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        parser.exit(1, "Reconstruction failed: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
