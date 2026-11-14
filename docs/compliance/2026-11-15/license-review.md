# rc6 source and license review

Review date: November 15, 2026. Scope: the published `v0.1.0-rc6`
source release and its associated, locally retained Android candidate. This is
an evidence-based technical compliance assessment, not a legal opinion or a
representation that Google has approved the app. It does not change release
gates, fill in a human reviewer's identity, or authorize a different binary.

## Result

The source release is substantial, publicly downloadable, and demonstrably
bound to the candidate. The remaining issue is **not 23 missing libraries or
191 unknown licenses**. There is one concrete source/resource omission in
`kotlinx-coroutines-core-jvm:1.6.4`, plus a bounded reconstruction/documentation
task. These should be addressed before describing this candidate's source as
complete for binary distribution.

The strongest finding is a 1,738-byte compiled resource actually present in the
APK, `DebugProbesKt.bin`. Its exact upstream source and generation/check
procedure are available, but are not in the retained Maven source collection.
Three consumer-rule inputs from the same library also need preserving. The
details and an attainable closure path appear below.

The review did not establish a conflicting license in the shipped app, an
unlicensed logo, or a need to obtain permission from every upstream developer.
Existing conservative review flags are not themselves evidence of a license
violation. Conversely, hashes and successful app tests do not prove source
completeness.

## Exact objects reviewed

| Object | Identity / SHA-256 |
| --- | --- |
| Source commit | `131ce7f3d83b6671121f1f0dedbcbda439f92905` |
| Version | `0.1.0-rc6`, version code `7` |
| Public `z8-source.zip` | `36ff81fc7dd0f9444fff57dab523b8464278a0b1329706348a07f47e0786d10d` |
| Candidate AAB | `4d426219d125bc7f380223e3295c157676e631b3a835a78af6944781a8b5eabd` |
| Candidate QA APK | `bed7761c4777ffb31f3009ef58e8a074b79b97d0fe4e77730f06c6f233ea31d7` |
| Source-input digest | `60b922fb61c0609db66eee91ffd4710a870f083bd6cf66450acde0444fb0af65` |

The relevant source is the attached
[568,534,054-byte source package](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc6/z8-source.zip),
not GitHub's automatically generated repository archive. The release's
[source manifest](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc6/source-manifest.json),
[Maven inventory](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc6/maven-sources.json),
[package inventory](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc6/package-sources.json),
and [notice inventory](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc6/release-notices.json)
identify retained inputs.

Existing independent verification was reused rather than rerunning the app's
test suite. It established anonymous public download equality, all 12,468
source entries' hashes/types/modes, 205 preserved symlinks, and equality of 332
own-source files to the release commit. The retained evidence is
`public-source-verification.json`, `source-independent.json`,
`committed-source-independent.json`, and `notices-independent.json` under the
private `reports/compliance/2026-11-15/rc6-final/` directory. These reports are
supporting local evidence, not a replacement for the public inputs.

Counts have different meanings:

| Inventory | Verified scope | What it does not establish |
| --- | --- | --- |
| 191 notice rows | 103 native/guest package rows plus 88 resolved Maven artifact rows | 191 distinct upstream projects or a license-compatibility conclusion |
| 103 packages | 25 host packages and 78 Debian guest binary packages; 228 unique retained source payloads, 21 effective historical build inputs | A fresh rebuild of every native component |
| 85 Maven coordinates | 702 retained files, no collector-unresolved payloads | That every source JAR alone contains all build inputs |
| 57 upstream supplements | Original build/resource/license inputs; 1,627 source-member byte matches and 384 Git object bindings | A complete rebuild of all Android libraries |
| 23 published JAR collections without those supplements | A review category; original source JARs and Maven metadata still exist | 23 demonstrated omissions or incompatible licenses |

The notice inventory's remaining generic `RELEASE_LICENSE_REVIEW_REQUIRED`
entry is a workflow marker. The concrete findings below are more informative
than that marker alone.

## Applicable scope of the licenses

Z8's application combines modified Termux code under GPL-3.0-only with
compatible third-party components. GPLv3 sections 1, 5, and 6 require the
corresponding editable source and necessary control scripts for the covered
combination, preservation of notices, and an appropriate source delivery route.
Section 1 excludes qualifying System Libraries and unmodified general-purpose
tools; it also permits automatically regenerable outputs to be omitted.
Section 6(d) permits source on a separate server with clear access information.
Section 10 bars additional restrictions on licensed rights.
[GPLv3 text](https://www.gnu.org/licenses/gpl-3.0.html)

Apache-2.0, BSD, MIT, and similar permissive licenses do not independently
require distributing a library's buildable source with every binary. Their
notice and attribution conditions remain applicable. For example, Apache-2.0
requires preservation of applicable notices and modification notices; it does
not grant general trademark rights. A library's role in the GPL-covered app
can create a corresponding-source requirement beyond its own permissive
license. [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)

The shell, Debian userland programs, and independently installed command-line
clients are not automatically one derivative program merely because they run
in the terminal. Their actual interfaces and integration matter. Bundled
copyleft executables still carry their own redistribution obligations.
Likewise, a dependency resolved during a build is not automatically code
conveyed in the final executable. These are scope distinctions, not blanket
exemptions. [FSF aggregation guidance](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation)

Normal Android platform APIs, an unmodified compiler, SDK tools, or Gradle need
not all be copied into this archive merely because a build uses them. A
claimed System Library exclusion must fit the actual component and packaging;
ordinary application add-on libraries should not simply be renamed system
libraries. Standard language runtimes may qualify, so Kotlin stdlib deserves
that analysis rather than an automatic source-violation finding.
[FSF GPLv3 guide](https://www.gnu.org/licenses/quick-guide-gplv3.html)

## Finite actions before source-complete binary release

### 1. Preserve the missing coroutines source and build resources

**Priority: fix before claiming complete corresponding source.**
Coordinate: `org.jetbrains.kotlinx:kotlinx-coroutines-core-jvm:1.6.4`.
The final APK contains `DebugProbesKt.bin` with Java class-file magic and SHA-256
`158a19eb94aa2f3e2f459db69ee10276c73b945dd6c5f8fc223cf2d85e2b5e33`.
It exactly matches the input JAR and upstream commit
`81e17dd37003a7105e542eb725f51ee0dc353354` at
`kotlinx-coroutines-core/jvm/resources/DebugProbesKt.bin`.
Whether Android normally executes the Java-agent feature does not remove the
fact that these bytes are distributed.

The exact source is
[`integration-testing/src/debugAgentTest/kotlin/DebugProbes.kt`](https://github.com/Kotlin/kotlinx.coroutines/blob/81e17dd37003a7105e542eb725f51ee0dc353354/integration-testing/src/debugAgentTest/kotlin/DebugProbes.kt),
SHA-256 `79f87242798d6b8643d5994462f7a74629e34784fc263f5fa4024f62f37d9285`.
It is absent from the retained source JARs. Their other `DebugProbes.kt` files
have different packages or implementations. Upstream's
[precompiled-probe check](https://github.com/Kotlin/kotlinx.coroutines/blob/81e17dd37003a7105e542eb725f51ee0dc353354/integration-testing/src/debugAgentTest/kotlin/PrecompiledDebugProbesTest.kt)
compares the generated class to this resource and can regenerate it. The
[integration build](https://github.com/Kotlin/kotlinx.coroutines/blob/81e17dd37003a7105e542eb725f51ee0dc353354/integration-testing/build.gradle)
specifies the Kotlin-package compiler option and source-set setup.

Also retain the exact three core consumer-rule files, absent from this source
JAR but present in its binary input. All three were compared directly with the
same upstream commit and matched:

| Path below `kotlinx-coroutines-core/jvm/resources/` | SHA-256 |
| --- | --- |
| `META-INF/com.android.tools/r8/coroutines.pro` | `4a9a4d1b42abb2bb031fe0e4bdef39b93c58c4bb789fa180df4fc5ddf1aecbd1` |
| `META-INF/com.android.tools/proguard/coroutines.pro` | `3135bb0ebf0f0af5e3cb3cb0b0482a9d03dfe950fdcfe9aa24b549d8aecef81d` |
| `META-INF/proguard/coroutines.pro` | `50518c7e4a79f867fc9b4063b33e24c6f15bb80ff2be13d8bf7377ae5725098b` |

The two coroutines Maven POMs do not contain the original Gradle build logic.
Preserve the relevant core/Android module configuration and reachable shared
build support, or provide an equivalent tested reconstruction recipe with
explicit provenance. In particular, common/concurrent/JVM source-set assembly,
compiler options, and atomicfu transformation must be accounted for.
[Core build](https://github.com/Kotlin/kotlinx.coroutines/blob/81e17dd37003a7105e542eb725f51ee0dc353354/kotlinx-coroutines-core/build.gradle),
[shared build](https://github.com/Kotlin/kotlinx.coroutines/blob/81e17dd37003a7105e542eb725f51ee0dc353354/build.gradle).

**Closure evidence:** retained exact source/rules and their hashes, a working
recipe for the affected JVM/Android outputs including the compiled probe,
and a documented correspondence check against the actual input artifacts.
There is no need to demand every unrelated JS/Native benchmark or test module.
The Android artifact's service descriptors and consumer rules are already in
its published source JAR; they should not be reported missing.

### 2. Complete a bounded reconstruction map, with justified exclusions

**Priority: verify the delivery path; do not label all remaining JARs missing.**

| Actual dependency | Already retained | Minimal outstanding work |
| --- | --- | --- |
| Kotlin stdlib/common/jdk7/jdk8 `1.8.22` | Published sources, generated Kotlin source files, POMs. All 24 Java/Kotlin blobs in upstream `core/builtins/{src,native}` byte-match retained source members. | Document the applicable System Library scope or retain/test the needed build/source-set and builtins-serialization mapping. The POMs alone have no build logic. Do not infer missing editable source merely from `.kotlin_builtins` in the APK. |
| Guava `24.1-jre` | 570 Java files; module POM, `guava-parent:24.1-jre`, `oss-parent:9`; no non-class runtime resource in the input inventory. | Document reconstruction using the retained `src` layout/POM chain and compile dependencies. No missing main code/resource has been demonstrated. Javadoc/JDK-source-unpacking configuration is not by itself a runtime-source gap. |
| CommonMark core and GFM strikethrough `0.13.0` | Source JARs, module/parent/Atlassian POM chain. Core's `org/commonmark/internal/util/entities.properties` is included. | Assemble Java and resources into the expected Maven layout and verify the main libraries. Unrelated benchmark/test modules are not a proven requirement for those outputs. |
| Commons IO `2.5` | Java source, `LICENSE.txt`, `NOTICE.txt`, module POM, `commons-parent:39`, `apache:16`; no runtime resource in the binary inventory. | State an appropriate compiler/tool version and main-library reconstruction. Source-distribution assembly descriptors, website/report configuration, and an old Java source level do not demonstrate missing library code. |

Kotlin's upstream tag resolves to
`fe0156151da01b3cecee587bf43e845766bdbfdf`. Its
[JVM stdlib build](https://github.com/JetBrains/kotlin/blob/fe0156151da01b3cecee587bf43e845766bdbfdf/libraries/stdlib/jvm/build.gradle)
shows the source sets, compiler options, and builtins input;
[builtins build configuration](https://github.com/JetBrains/kotlin/blob/fe0156151da01b3cecee587bf43e845766bdbfdf/core/builtins/build.gradle.kts)
shows the serializer and input selection. These explain a concrete
reconstruction question, not a demand to publish the whole compiler's source.

For comparison, the ordinary Maven build descriptions are available in the
[Guava module POM](https://github.com/google/guava/blob/v24.1/guava/pom.xml),
[CommonMark module POM](https://github.com/commonmark/commonmark-java/blob/commonmark-parent-0.13.0/commonmark/pom.xml),
and [Commons IO POM](https://github.com/apache/commons-io/blob/commons-io-2.5/pom.xml).
The retained published POM bytes are the primary evidence for the released
artifacts; a tag name alone is not proof of identical build provenance.

The other published JARs in the 23-item category are mostly AndroidX support
and annotation libraries. Their status should be assessed by actual contents
and surviving code, not promoted from a generic collector warning to a proven
violation. The existing 57 AAR supplements likewise provide meaningful evidence
without proving every reachable reconstruction input has been exercised.

The top-level source handoff also needs one documented functional
reconstruction from the public inputs: current preparers require pristine
pinned Git checkouts, while the export intentionally excludes `.git`.
Restore the recorded upstream revisions, or add archive-aware validation
against the manifest; preserve any inputs found genuinely necessary along the
way. Missing full Git history is not independently a license violation.
Functional reconstruction and actual source correspondence matter; matching
the distributed APK's exact hash is not a GPL requirement.
[FSF guidance on binary hashes](https://www.gnu.org/licenses/gpl-faq.html#MustSourceBuildToMatchExactHashOfBinary)

### 3. Preserve exact license scopes and correct misleading summaries

**Priority: accurate notice/source records, not a newly discovered incompatibility.**

PRoot's recipe label `GPL-2.0` is coarser than its actual source headers, which
allow GPL version 2 or later. The preserved talloc `2.5.0` `LICENSE` and
`talloc.c` use LGPLv3-or-later, despite the recipe's coarse `GPL-3.0` label.
Consequently, comparing those two labels does **not** establish a GPLv2-only /
GPLv3 conflict. The retained static talloc build and PRoot sources/recipes
matter for reconstructing and relinking that executable. Original texts must
remain authoritative. [PRoot source header](https://github.com/termux/proot/blob/v5.1.107.96/src/cli/cli.c),
[official talloc source distribution](https://www.samba.org/ftp/talloc/talloc-2.5.0.tar.gz),
[FSF license compatibility guidance](https://www.gnu.org/licenses/license-compatibility.en.html).

JSR305 `1.3.9` is no longer a missing-source case: the exact embedded Java
sources, retained SVN dump, revision-49 reconstruction, and contemporary build
files are preserved. The original BSD terms and Brian Goetz CC-BY-2.5 headers
on three concurrency annotations must take precedence over the broad POM
label. Checker Framework `2.0.0` also has a file-specific CC-BY-2.5 header;
animal-sniffer `1.14` has a retained MIT notice. They must not all be relabeled
Apache or GPL merely to simplify the table.

A read-only `apkanalyzer dex packages --defined-only` inspection of the exact
final APK found 3,526 defined classes. There were zero definitions under
`javax.annotation`, `org.checkerframework`, or
`org.codehaus.mojo.animal_sniffer`; there were 89 under `com.google.common`,
185 under `kotlin`, 143 under `kotlinx.coroutines`, 92 under `org.commonmark`,
and 17 under `org.apache.commons.io`. This bounds the named-class evidence;
it is not a proof that no code or metadata was inlined or transformed.
The original source archives are themselves redistributed, so their notices
still apply even where annotation classes are absent from DEX.

Preserved CC-BY-2.5 attribution/license references remain relevant. Compatibility
statements about CC-BY-4.0 cannot simply be applied to version 2.5. This review
does not establish that CC-BY-2.5 code was incorporated into the shipped
GPL-covered executable, or a resulting incompatibility. Independent source
archives can retain their own terms within a collection.
[CC-BY-2.5 legal text](https://creativecommons.org/licenses/by/2.5/legalcode.en)

Three stale descriptions were corrected alongside this review: `BUILDING.md`
now describes the offline base and manually selected project tools;
`RELEASE_LICENSES.md` uses the retained Debian `hostname_3.25.dsc` in its source
assembly example; and `LICENSES/README.md` identifies the current guest as
Debian. Historical Ubuntu provenance was preserved. These documentation fixes
do not change the immutable rc6 source archive or establish that its collected
Debian source payloads were missing.

## Notices, artwork, trademarks, and delivery

The GPL text, original Termux module notices, Apache/MIT/BSD source exceptions,
and the limited OpenJDK Classpath exception are retained. The exception belongs
only to files granting it; it is not a general relicensing of Termux.
The app exposes source/license information and paginated offline third-party
notices. The reviewed generated notice file is 6,740,228 bytes and bound to
13 verified input records.

The maintainer has already confirmed rights to publish the Z8 logo and Prism
art under GPL conditions. That dated consent is recorded, and editable raster
source assets and generation provenance are present. No evidence establishes
an omitted proprietary layered original. Google Material Icons retain their
separate Apache-2.0 provenance; they are not covered by the maintainer's logo
consent. [Pinned Material Icons license](https://github.com/google/material-design-icons/blob/737e3324305806514d7909874fa1818ae1808232/LICENSE)

Public descriptions identify Debian factually and include its ownership and
non-affiliation wording. No Debian logo is used as Z8 branding. That fits the
policy's factual-reference route; it does not require a new vendor inquiry
on the evidence reviewed. This is not a worldwide clearance search for the
name Z8. [Debian trademark policy](https://www.debian.org/trademark)

When the binary is eventually offered, retain the version-specific complete
source link beside the download/store information and in the app. Keep that
source accessible for the required distribution period. A generic repository
homepage is a weaker handoff than the exact source package.
[FSF source-hosting guidance](https://www.gnu.org/licenses/gpl-faq.html#SourceAndBinaryOnDifferentSites)
Signing with a production key does not automatically require publishing that
private key. Any applicable GPLv3 installation-information requirement and
restrictions on user-modified builds must be assessed against the actual
distribution arrangement, rather than treating ordinary signing as a blanket
exemption or violation. [GPLv3 section 6](https://www.gnu.org/licenses/gpl-3.0.html#section6)

## Completion criteria and limits

Unpublished follow-up implementation: after this rc6 audit, the collector was
extended with the exact coroutines archive, missing probe source/build inputs
and three rules. A separate explicit compilation with pinned Kotlin 1.6.21
recreated all 1,738 probe bytes and the SHA-256 recorded above. Eight Kotlin,
coroutines and CommonMark coordinates now have supplementary mappings in a new
inventory; Kotlin's bounded build mapping preserves its generator/templates,
Unicode inputs and the one exact release-version substitution separately.
CommonMark's original BSD notice is also retained and matched to both runtime
JARs. See [the follow-up evidence and reproduction command](../../RELEASE_LICENSES.md#coroutines-and-kotlin-jvm-source-follow-up).
This closes the identified probe/resource collection gap for a future source
package. It does not retroactively change the published rc6 archive or establish
a complete stdlib/coroutines/app rebuild. No closure or reviewer flag was set.

Close the concrete coroutines omission, establish the scoped reconstruction
path with justified exclusions, preserve original notice exceptions, and bind
the resulting source/notices to the final distributed candidate. If those
checks reveal another actual missing input, name that input and its role;
do not replace the investigation with an unlimited requirement to archive
every upstream repository and build machine.

A `reviewedBy` field is a project accountability mechanism, not a license
condition that substitutes for evidence. A lawyer's approval is not imposed
by this review. Existing `sourceClosureReviewed:false` and
`completeCorrespondingSource:false` remain unchanged because the concrete
work above has not been completed, not merely because a signature is absent.
No release approval or notice-completeness declaration has been fabricated.

This audit did not rebuild every dependency, perform a worldwide trademark
search, evaluate provider service contracts, or decide Play policy eligibility.
It reused prior public/hash verification, inspected retained archives and
POMs, checked actual final APK class/resource contents, and consulted exact
upstream source and primary license guidance. The original audit added this
review and corrected the three documentation issues identified above. The
subsequent source-collection changes are identified separately in the follow-up
paragraph. Published rc6 artifacts were not altered.
