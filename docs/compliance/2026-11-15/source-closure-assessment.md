# Bounded source-delivery assessment after rc7

Assessment date: November 15, 2026. This is a technical, evidence-based scope
assessment prepared by Codex, not an attribution of human approval to the
operator. It preserves the earlier [rc6 review](license-review.md). The baseline
is the immutable rc7 release; the additional input below is for the next source
snapshot, not a retroactive change to that release.

## Conclusion

The earlier concrete Coroutines omission and the source-export build-path
problem have been resolved. This follow-up identified **one further necessary
build-control input: the original 433-byte AndroidX annotation R8 rules**. That
input and its original license are now retained verbatim with exact publisher
provenance. No additional missing source or build-control input was identified
in the reviewed Android combination and bundled native/package scope.

The finite recommendation is to include these files in the next source package,
rebind the review to that exact package and notices, and verify the new Android
artifact and public source URL. Do not require a complete compiler source tree,
every upstream test/publication environment, or a byte-identical rebuild of
every dependency without a concrete reason. Conversely, this assessment does
not set a review flag for an unbuilt rc8 binary or claim every original,
unshrunk Maven JAR has been reconstructed in full.

## Exact baseline and reusable evidence

| Object | SHA-256 / identity |
| --- | --- |
| rc7 source commit | `9b13ee5998305c2985f998e805bf524adf33b5af` |
| rc7 source ZIP | `6ad6d1d6e97ef38a9d7089ddb32fbe7d89a947f7aae86b0c6d6f2f05dfe81521` |
| rc7 source manifest | `937177d41f4d9a981dedb78b9871cf49537d504b86111ac86f85b2ab1cf610a9` |
| rc7 source-input digest | `a9c03977b94fdf048323da62c7c066ae797203a475b83983611ac64b47cb0a7d` |
| Maven source inventory | `3c443d02bf7f4b87ef1f528c7f7298ba4ccb1fd6b18972e17a1234c38cd9467b` |
| Native/package source inventory | `54697820d7906b311565d1c4034571220d0852a9b6878520b4cf40f149ce9188` |
| Normalized runtime Gradle inventory | `7175529c63ae5fa2da515a3a4fec79f0517617b1425d92f7934cd412b9b7a7e8` |
| rc7 QA APK | `9d53696df74a542cd99d5fc78bf5559b60d2ae689cfc46d2b475b78ec550f0e8` |
| rc7 AAB | `46ec5946029652d341701dc65cc0644a8761ec638ae5309d0546d5f2415ce5e1` |

The [attached rc7 source package](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc7/z8-source.zip)
contains 13,008 checked file records and 205 preserved symlinks. Independent
verification rederived all 1,224 Maven payloads for 85 coordinates, all 65
supplements, 2,252 source-member matches, seven runtime-resource comparisons,
and one narrowly checked Kotlin version transformation. It also checked the
103 native/guest package rows, 228 unique source payloads, original notices and
21 effective historical build inputs. The source archive was downloaded
without credentials and matched the retained bytes.

An actual Android build completed from the extracted rc7 source, without
restoring the Termux app's Git history. It used separately bound generated
notices, the frozen runtime/guest images, and ordinary cached build tools and
dependencies. It did not rebuild every native package from source. The separate
Coroutines probe reconstruction reproduced all 1,738 bytes exactly. The
[four-library recipe](../../source-reconstruction-jars.md) compiled 788 retained
Java files and passed functional tests for Guava, CommonMark core/extension and
Commons IO without their original target binaries on the classpath.

## Scope of the delivered work

The modified Android app and its linked application libraries are treated as
the covered combination. The source handoff conservatively includes the
resolved runtime-library sources, resources and necessary control inputs.
Ordinary application libraries are not excluded merely because their own
licenses are permissive.

Bundled host tools, PRoot and the Debian userland also have their own license
obligations. Their original sources, Debian patches/build metadata, Termux
recipes and Z8 changes are retained. A normal command/PTY interface to a
separate program does not by itself turn that program into an app library.
Optional clients downloaded directly from their providers after a user's
request are a separate delivery flow; this does not waive their notices,
terms or any obligation if the distribution arrangement later changes.
[FSF aggregation guidance](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation)

GPLv3 requires editable source and necessary control scripts for the covered
work, while excluding qualifying System Libraries and unmodified general
purpose tools. Automatically regenerable outputs need not be retained as
additional source. This assessment retains Kotlin's relevant source,
generators, data and build mapping rather than relying on a blanket System
Library exemption. Unmodified JDK/Kotlin compiler, SDK/NDK and Gradle programs
used only to build the work do not create a requirement to collect their entire
implementation source recursively. This exclusion does not apply to a custom
build plugin or modified generator actually needed by the work.
[GPLv3 section 1](https://www.gnu.org/licenses/gpl-3.0.html#section1)

A matching historical binary hash is not the source-delivery test. The working
editable sources and necessary instructions matter. An unmodified compiler's
synthetic classes, `.kotlin_module` metadata, packaging timestamps and a
publisher's signing key do not independently establish missing editable code.
[FSF source/rebuild guidance](https://www.gnu.org/licenses/gpl-faq.html#MustSourceBuildToMatchExactHashOfBinary)

## Additional original control input

`androidx.annotation:annotation-jvm:1.9.0` contains
`META-INF/proguard/androidx-annotations.pro`. Its source JAR omits this file.
A scan of 967 retained source/input payloads found no byte-identical copy. The
433-byte rules are present in the exact rc7 R8 configuration and affect the
handling of `Keep` and `DoNotInline`; they are therefore meaningful control
input, although the `.pro` file itself is not copied into the APK.

The original [Google Maven JAR](https://dl.google.com/dl/android/maven2/androidx/annotation/annotation-jvm/1.9.0/annotation-jvm-1.9.0.jar)
was fetched again without credentials and matched its selected runtime SHA-256
`3236e1e44c41da378c1ac9b515bee0501d8dc512991465100acb4dfe64059a4e`.
The retained files are:

- [Original rules](inputs/androidx-annotation-jvm-1.9.0.pro), SHA-256
  `64fb2b6036d3bfab479f615c38c29dfce48071cc357b2d062a71020d645e5c9d`.
- [Original Apache license](inputs/androidx-annotation-LICENSE.txt), 10,175 bytes,
  SHA-256 `809fa1ed21450f59827d1e9aec720bbc4b687434fa22283c6cb5dd82a47ab9c0`.
- [Publisher/member provenance and reconstruction placement](inputs/androidx-annotation-jvm-1.9.0.provenance.json).

These are unchanged, human-readable publisher inputs, not decompiled code or
newly generated files represented as originals. When reconstructing this
library, include the `.pro` bytes at the original JAR member path above and
preserve the original license. The source packager includes `docs/` recursively;
the next archive must contain and hash all three files. No dependency version
or application behavior was changed by this preservation step.

## The remaining published-source JAR category

The old count of 15 unsupplemented published source JARs is not 15 demonstrated
source gaps. A fresh class-file inspection found **2,334 direct SourceFile and
package matches among 2,345 class entries**. This checks source presence, not
that the compiler produced a class from those exact bytes. The 11 exceptions
are scoped below rather than silently accepted.

| Group | Actual retained material / disposition |
| --- | --- |
| AndroidX annotation, core-common, collection, collection-ktx, concurrent-futures, lifecycle-common and resourceinspection-annotation | All Java/Kotlin class source-file references match retained source members. Kotlin module metadata is compiler output. The annotation rules above were the identified non-source-JAR input. Original POMs retain dependencies; existing shared AndroidX support inputs and normal Java/Kotlin compilation apply. No extra main-resource or custom generated-class input was found in these JARs. |
| Guava and Commons IO | Retained original code, POM chain, notices and the tested main-library reconstruction recipe; do not demand unrelated website/publishing tasks. |
| Error Prone, J2ObjC, Animal Sniffer and JetBrains annotations | Every class SourceFile/package has a retained source match; original POMs and applicable source notices are retained. No native or extra executable resource was found. |
| Checker compatibility annotations | 18 direct class/source matches. Ten `afu.*` shaded class entries do not have a direct package match in the source JAR. Their original binary's full relocation build is not claimed complete. The exact final rc7 R8 output records all ten as removed whole classes, with no `afu.*` retained or inline-origin mapping entries. The build-output AAB is byte-identical to the final AAB. This supports their exclusion from this shrunk Android combination, rather than assuming absence from a descriptor search alone. Recheck this scope for a new candidate. |
| JSpecify | Four annotation class sources are present. The eleventh nonmatch is the Java 9 multi-release `module-info.class`; its source is not in this source JAR. The Java module and OSGi descriptors are not delivered in the Android APK. This does not claim the full original multi-release JAR has been reconstructed. |

The Checker and JSR305 archives retain their original per-file terms, including
CC-BY-2.5 annotations, rather than relabeling all files Apache/GPL. The rc7 R8
usage/mapping also supports removal of those annotation classes from the app;
it does not erase the attribution duties for their separate retained source
archives. BSD, Apache, MIT and Unicode notices remain intact. The restored
Chromium BSD and CommonMark notices and Unicode source/data notices are part
of the verified collection. [Apache redistribution conditions](https://www.apache.org/licenses/LICENSE-2.0#redistribution),
[CC-BY-2.5 terms](https://creativecommons.org/licenses/by/2.5/legalcode.en).

## Finite next-release checks

1. Keep the selected dependency/source inventories unchanged unless a real
   dependency changes. Include the three new original-input/provenance files
   above in the new source snapshot and verify their bytes. The collector's
   `sourceClosureReviewed: false` must remain false: collection does not approve
   itself, and its validator deliberately enforces that invariant.
2. Bind a separate completed review to the **new exact** `noticesInputs`, with
   the reviewer honestly identified as **Codex technical source-delivery
   assessment**. The user delegated this review; it must not be attributed to
   the operator or represented as a lawyer's approval. A human signature is not
   an additional requirement identified in the applicable licenses. The
   existing workflow's former human-review wording should not create an
   artificial unresolved item. After confirming the new inputs below, the
   separate record may honestly set `sourceClosureReviewed` and
   `noticeCompletenessReviewed` to true for this bounded review. This does not
   change the collector's false flags or waive a missing payload, notice or
   failed hash.
3. Generate the new notices and candidate. Verify the actual runtime/guest,
   source/configuration, dependency and notice hashes. Recheck the R8 removal
   scope if it is relied upon; do not apply rc7 output findings to changed DEX
   by assertion. App-level rc8 changes need their own tests independently.
4. Publish the corresponding source ZIP before distributing that binary, then
   anonymously download and compare it. Keep a version-specific source link
   and clear instructions next to the Play/binary listing, plus the in-app
   link. GitHub's automatic repository ZIP is not this complete source package.
   A different source server is allowed with equivalent access and clear
   directions, but availability remains the distributor's responsibility.
   [GPLv3 section 6(d)](https://www.gnu.org/licenses/gpl-3.0.html#section6).

The first item resolves the only new content omission found here. The remaining
items are exact-release binding and delivery actions, not unspecified missing
libraries or a demand for an additional person's signature. The technical
review is complete; successful binding supports closing the bounded
source-delivery gate for those precise inputs. It is not a Google Play
approval, provider endorsement, patent opinion, or a claim that the old rc7
source archive already contained the newly retained rules.
