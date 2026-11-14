# Reconstructing the retained Java main libraries

`tools/reconstruct-permissive-jars.py` builds four main libraries from their
retained published sources and runs functional checks. It does not use any of
their original binary JARs on a compiler or runtime classpath. It performs no
network requests, changes no app dependency, and does not set source-review or
license-approval flags.

This is a tested functional reconstruction, **not byte-identical reproduction**
of the publishers' releases, a replacement for their complete test suites, or
approval of the whole Z8 corresponding-source set.

## Inputs and supported scope

| Library | Retained main input | Build inputs and preserved resources |
| --- | --- | --- |
| Guava `24.1-jre` | All 570 Java files in the published source JAR | Module POM, `guava-parent:24.1-jre`, `oss-parent:9`; five pinned annotation dependencies below. Source copyright headers remain untouched; the Apache license is included in the output. |
| CommonMark `0.13.0` | All 97 Java files in the published source JAR | Module/parent/Atlassian POM chain; original `entities.properties`; exact upstream BSD notice. |
| CommonMark GFM strikethrough `0.13.0` | All 6 Java files in the published source JAR | The freshly reconstructed core JAR; original POM metadata and BSD notice. |
| Commons IO `2.5` | All 115 Java files in the published source JAR | Module POM, `commons-parent:39`, `apache:16`; original `LICENSE.txt`, `NOTICE.txt`, and source documentation resources. |

The source and compile-dependency SHA-256 values are fixed in the recipe.
Retained POM files are checked against their source inventory records and
copied to the output's `provenance/` directory. Sources are preserved unchanged
under `sources/`. Non-Java source-JAR members are copied into each output JAR;
the source JAR's manifest is retained under
`META-INF/z8-reconstruction/source-manifest.mf`, with a new manifest clearly
identifying the reconstructed output.

CommonMark's published source JARs do not contain the full BSD notice. The newer
source inventory retains official upstream commit
`f7716897f9e37f03d023cf713e92a5b1ced59bc1`, archive SHA-256
`66d1374a090a06a01ea412d65dacb92c496e1def153a77e813cbd0fc0a0b5602`.
The recipe reads its original 1,305-byte `LICENSE.txt`, SHA-256
`4c1ea7a8104cd00a7e62b794cc317aedca2e68c647048b5f546fc7388dddd306`.
That text also exactly matches the notice in both published binary JARs.
For an older source inventory, provide the same retained text using
`--commonmark-license /path/to/LICENSE.txt`; the checksum remains mandatory.
This source-JAR omission does not mean the existing release notices lack the
CommonMark notice.

## Run from an exported source archive

Use Python 3.9+ and a full JDK; the executed validation used **Eclipse Temurin
21.0.12.1+1** on macOS arm64. Verify the public source ZIP and accompanying
`gradle-artifacts.json` against the release's checksums before extracting them.
No `.git` directory is required.

Place these five JARs in a separate directory. Their published Maven Central
URLs are below; the recipe checks the exact resolved versions and SHA-256
values against both its pins and `gradle-artifacts.json` before invoking Java.
The recipe does not download dependencies or execute Maven plugins.

| Compile dependency | Official artifact |
| --- | --- |
| JSR305 `1.3.9` | [JAR](https://repo.maven.apache.org/maven2/com/google/code/findbugs/jsr305/1.3.9/jsr305-1.3.9.jar) |
| Checker compatibility annotations `2.0.0` | [JAR](https://repo.maven.apache.org/maven2/org/checkerframework/checker-compat-qual/2.0.0/checker-compat-qual-2.0.0.jar) |
| Error Prone annotations `2.15.0` | [JAR](https://repo.maven.apache.org/maven2/com/google/errorprone/error_prone_annotations/2.15.0/error_prone_annotations-2.15.0.jar) |
| J2ObjC annotations `1.1` | [JAR](https://repo.maven.apache.org/maven2/com/google/j2objc/j2objc-annotations/1.1/j2objc-annotations-1.1.jar) |
| Animal Sniffer annotations `1.14` | [JAR](https://repo.maven.apache.org/maven2/org/codehaus/mojo/animal-sniffer-annotations/1.14/animal-sniffer-annotations-1.14.jar) |

From the extracted source root, with the Gradle inventory alongside it:

```sh
python3 tools/reconstruct-permissive-jars.py \
  --maven-sources third-party-sources/maven/maven-sources.json \
  --gradle-inventory gradle-artifacts.json \
  --dependency-dir /path/to/five-annotation-jars \
  --java-home /path/to/jdk \
  --output /path/to/new-reconstructed-jars
```

For the checkout's existing verified cache, omit `--dependency-dir` and use
`--binary-root /path/to/z8`; the recipe resolves only those five dependency
records from the inventory. The output directory must not already exist, so
old compiled classes cannot mask missing inputs. The original four target JARs
are never opened by the build recipe. The GFM extension uses only the new core
JAR. Annotation processing is disabled; ambient Java classpath/agent options
are removed for compiler and test subprocesses.

The output includes four `*-reconstructed.jar` files, exact sources and POMs,
compile logs, the small functional test, and `reconstruction-report.json`.
The report records input hashes, compiler identity, explicit classpaths,
resource/legal-member hashes, output hashes, and actual test results. Failure
does not produce a PASS report; use a new directory after correcting inputs.

## Compiler differences and tested limits

Guava's original source level is Java 8. Its unchanged source directly uses
`sun.misc.Unsafe`, so JDK 21's `--release 8` hides a required internal API and
fails. This recipe deliberately uses `-source 8 -target 8` against the selected
JDK for Guava, recording the compiler warnings. It does **not** establish Java
8 API compatibility merely from the class-file target. Error Prone annotations
`2.15.0` are Z8's resolved dependency, replacing the parent POM's `2.1.3`.

CommonMark's original target is Java 7 and Commons IO's is Java 6. This bounded
recipe uses JDK 21 `--release 8` for both; it does not reproduce their older
target bytecode or OSGi/publishing manifests. None of their source is patched.
Javadoc, signing, publishing, website, benchmarks, and upstream test-only
dependencies are not needed to compile these main-library source sets and are
not executed here.

The 2026-11-15 run compiled all **788 Java files**, producing core/extension/
Guava/Commons IO class counts of **121 / 8 / 1,943 / 123**. Comparison with the
original inputs found four absent compiler-generated enum-switch helper
classes: three in Guava and one in CommonMark. `javap` confirmed their original
`ACC_SYNTHETIC` flags; every published Java source was compiled. Those compiler
differences are not represented as byte-for-byte reproduction.

The actual reconstructed JARs passed checks for Guava collections, iterator
paths, ordered graphs, cache loading/statistics, futures, and SHA-256;
CommonMark HTML rendering, a named entity loaded from `entities.properties`,
reference links, and GFM strikethrough; and Commons IO multi-buffer copying,
UTF-8 decoding, path normalization, and wildcard matching. Resource and notice
bytes were verified again after packaging. No Android app binary was replaced
or rebuilt with these diagnostic outputs, and no comprehensive ABI or platform
compatibility claim is made.
