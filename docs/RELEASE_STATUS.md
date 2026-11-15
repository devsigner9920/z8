# Release status and validation scope

Documentation: [English](../README.md) | [한국어](../README.ko.md)

As of November 15, 2026, Z8 is a development project that has not reached a stable app release or Play Store launch. Source publication and app submission or approval are separate procedures. This document is a public summary of validation, not a compatibility guarantee for every build from current sources or every device.

The [November 15 policy and license review](compliance/2026-11-15/README.md)
is the current review entry point. Its findings supplement the immutable rc6
releases and the historical records below; they do not change a tested binary
or establish Google Play approval.

## Subsequent operator preparation

On November 15, the maintainer explicitly deferred the authenticated Claude
workload test. It remains unverified; the immutable release QA report is not
changed to PASS. The [consumer Gmail follow-up](compliance/2026-11-15/support-mail-transfer-follow-up.md)
adds service-specific contract/country findings. Public documents still do not
establish the required processing scope, and no fictional country or consent
has been inserted into the policy.

An AES-256 encrypted upload-key image was stored in the maintainer's restricted
private Google Drive and downloaded again. Its exact bytes, all four restored
identity files, certificate and actual restored-key signing/strict verification
passed. The temporary volume was ejected and the original identity was preserved.
Independent recovery-password custody is still awaiting the maintainer's
confirmation; complete disaster recovery is not yet declared. No private cloud
location, secret or key artifact is published. See [the backup procedure](UPLOAD_KEY_BACKUP.md).
The release-specific report below retains the state observed at its creation.

## Published rc8 source and final-candidate validation

The **[0.1.0-rc8 source prerelease](https://github.com/devsigner9920/z8/releases/tag/v0.1.0-rc8)**
uses version code **9** and source commit
`b180705dc91a321674d697bea6ae9f6cfa95f501`. Later documentation and QA records
are supplements; they do not replace the immutable tag, source ZIP or tested
candidate. No installable APK or AAB is included in the public release.

| Artifact | SHA-256 |
| --- | --- |
| Public `z8-source.zip` | `3b3e32a429d3a27496175a3371caa32bd6dcdba0af45b6dde6656033fc3fe5ef` |
| Local development-signed QA APK | `0634cdd49f1c4c4ed64a63e6352327090618c16767bb0d721aed3584040f7395` |
| Original unsigned candidate AAB | `b99dfab5910e3ee2a5c350f1a94479e3f4d2072cec7e108887ef0f0357bcde8b` |

Interactive PTYs now use `TermuxService` with `specialUse`; finite setup, project
preparation, selected tool installation/update and confirmed project deletion
use a separate `dataSync` service. Workers wait for foreground promotion and
their runtime binding. **Stop tasks**, owner destruction and Android timeout
cancel finite work without stopping unrelated terminals; retry is explicit.
File deletion can be partial when interrupted. The app explains that already
deleted files cannot be restored and retains the remaining project for retry.
The Tools return label now follows its actual entry screen.

The final source passed **637 host tests**, with one case-sensitive-filesystem
skip and no failures, plus **145 terminal-engine tests**. Actual fresh Android
unpacking covers the skipped host extraction separately. The focused 134-test
lifecycle suite and independent 57-test service/deletion subset also passed;
these are subsets, not additional unique tests to add to the full-suite count.

The [bounded source-delivery assessment](compliance/2026-11-15/source-closure-assessment.md)
retains the original AndroidX annotation rules, license and provenance.
Independent verification checked all **13,018 source records**, preserved
build inputs, 85 Maven coordinates and exact package-source payloads.
The actual optimized APK/AAB, R8 mapping, notices, runtime, guest and dependency
identities match that source. Notices cover **191 components** with no
unresolved entries. The strict [corresponding-source verification](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc8/release-compliance.json)
is **VERIFIED**, including an anonymous download of the public source ZIP.
This is an attributed technical assessment, not a fabricated human/legal sign-off,
a claim that every dependency was rebuilt or permission from Google Play.

On a fresh ARM64 Android 17 emulator with **16 KiB pages**, the exact APK
prepared Debian 13.7 while offline with optional Python initially absent.
Background project preparation handed off from `dataSync` to the interactive
service. An actual Android timeout stopped Python installation while preserving
the running terminal and marker; explicit retry installed Python 3.13.5 and a
real calculation passed. Preview storage clearing, multiple terminals,
notification Exit, Android's user Stop and explicit relaunch without command
replay passed. English default and the Korean switch were checked.

A separate upgraded emulator preserved its project, tools and marker. An actual
**Stop tasks** action interrupted Git installation without killing the sibling
terminal/children; explicit retry completed. A new disposable project deleted
successfully while other work survived. **Cancellation during file deletion was
not observed on a device** because deletion completed too quickly; host tests
cover the cancellation boundary, and the deletion video demonstrates natural
completion only. Android timeout overrides were restored; both dedicated
emulators were closed with their data retained.

On an ARM64 Samsung phone with Android 17 and **4 KiB pages**, the exact
rc7 → rc8 in-place upgrade preserved the existing projects and known files.
The retained Ubuntu 24.04.5 base was not converted; this is upgrade evidence,
not a fresh Debian phone install. The same terminal survived background use
and explicit Git work while both foreground-service types were observed.
Existing official Codex 0.160.0 authentication remained usable. An actual
Codex task created two files and passed three unit tests; an independent shell
reran those three tests and an additional assertion successfully. Local execution
was enabled only in the already-authorized `RC7PhysicalQA` project, then reset
**off**. This does not establish default Codex sandbox compatibility in PRoot.
Preview rendering and new project deletion were not confirmed on this phone;
the corresponding final-candidate emulator results above remain separate.

The final phone cleanup rechecked all four known original fixture hashes,
preserved both new model files and the existing login, and confirmed the three
original project identities. Only the owned loopback server and verification
shells were terminated through normal job termination/exit; their absence was
verified. No project, credential or personal file was removed.

A **private internal-test AAB** was signed with the dedicated upload identity.
Signature/certificate, bundle validity and unchanged payload were verified;
the original unsigned candidate and exact incomplete QA/source evidence were
retained. Its SHA-256 is
`8cfe4b8a3f629939678c1a50ef2a4f5b5058236d95d7eadef494110cf914dc1e`.
This file is not published or uploaded. `productionReady=false` and
`readyForConsoleUpload=false` remain explicit: signing does not complete the
untested provider case, operator decisions or Console requirements. Upload-key
registration and an external backup are not verified. See [building and signing](../BUILDING.md).

The [public store preparation ZIP](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc8/z8-play-store-preparation.zip)
contains five actual English listing screenshots, English/Korean text, four
original service demonstration videos and scoped emulator evidence. Its 64
files were independently checked and anonymously downloaded with exact hashes.
The five RGB24 screenshots preserve every original RGB pixel; original captures
remain available separately. Phone authentication screens, private raw dumps,
installable binaries and signing keys are excluded. The [final validation record](compliance/2026-11-15/rc8-final-review.json)
binds the source, QA, signing result, store bundle and outstanding gates. These
are post-source observations, not modifications to the b180705 source archive.

The [final privacy assessment](compliance/2026-11-15/support-and-data-safety-final.md)
and [Data safety worksheet](store/play-console-data-safety.md) provide concrete
draft form choices. Ordinary Gmail support processing still lacks complete
country/overseas-route particulars; a change to another consumer-mail brand has
not been established as resolving that gap. Supported optional clients use the
user's own accounts and subscriptions. No authenticated Claude task has been
performed, and no provider purchase was made.

Console identity verification remains in progress, phone verification awaits
identity approval, and **Create app was disabled** at the recorded read-only
check. The app has **not been submitted**. Actual Console declarations, Play
track/pre-launch checks and the applicable personal-account closed test remain.
Native Linux-download policy treatment remains a normal Play review question;
source/QA success does not establish a policy exemption or legal-risk guarantee.

## Published rc7 source and exact candidate evidence

The **[0.1.0-rc7 source prerelease](https://github.com/devsigner9920/z8/releases/tag/v0.1.0-rc7)**
is published, using version code 8 and source commit
`9b13ee5998305c2985f998e805bf524adf33b5af`. Its
[implementation follow-up](compliance/2026-11-15/implementation.md) adds external
client notices and terms access, source supplements, and app building from
verified source exports. No installable APK or AAB is published.

The [validation summary](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc7/release-validation.json)
records the exact candidate, source and check scope. All 13,008 source records
were independently verified; the exported source built an Android candidate
without Git metadata and passed 145 terminal tests. Separate artifact checks
matched notices, runtime, guest, dependencies and 16KiB alignment. Focused
English/Korean emulator testing passed cancellation, rotation, terms-browser
return and remembered reopening, using a retained official Claude test fixture.
That earlier report did not test provider installation, authentication or model
requests; the subsequent final review below adds separate exact-candidate tests.

The [final review record](compliance/2026-11-15/final-review.json) binds the
following new results to the same rc7 APK. The host suite passed **594 tests**,
with one filesystem-specific skip and no failures. On a Samsung ARM64 phone
with Android 17 and 4 KiB pages, an in-place rc5 → rc7 update preserved existing
projects and a known source-file hash. The retained Ubuntu base remained
Ubuntu; this was not a fresh Debian installation. A new test project passed
shell/Python/Git use, explicit Git update, local preview and scoped deletion.
Official Codex 0.160.0 installed and signed in through its normal browser flow,
returned a real model response, and created two files with **three passing unit
tests**, independently rerun in a separate shell. The file task used the user's
explicitly approved local execution mode only in `RC7PhysicalQA`; that mode was
reset off afterward. This does not establish Codex's default Linux sandbox
compatibility in PRoot. Claude authentication/model work remains untested.

On a separate fresh ARM64 Android 17 emulator with 16 KiB pages, the exact APK
prepared its minimal Debian 13.7 environment and opened a working terminal
while offline, without installing optional native tools. Explicit Python
installation and execution then passed. Preview-data cancellation/clearing,
project deletion with other work preserved, and Android's user Stop action
passed within the recorded scopes. Explicit relaunch did not replay commands.
Daily version checking defaulted to off. One minor wording issue remains:
Tools opened from Settings says “Back to project” although it returns to Settings.

**At the rc7 final review, production preparation remained incomplete.** That
binary used the interactive terminal's `specialUse` type for standalone
setup/download jobs. Source-closure assessment, Gmail overseas-processing
particulars, supported-provider Data safety, Play declarations and upload signing
were recorded as open. The rc8 work above updates those findings without
changing rc7. The actual Console check showed identity verification in progress,
phone verification pending and **Create app disabled**. No app or release was
submitted. The rc6 publication and QA identities below remain historical.
New rc7 captures are QA evidence; older store screenshots/videos have not been
relabeled rc7, and the original rc7 source/candidate artifacts remain unchanged.
The [supplemental evidence ZIP](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc7/z8-rc7-final-review.zip)
contains bounded reports, 24 synthetic fresh-install captures, the raw setup
video and three physical Codex task/test/reset captures. Private authentication
screens and installable binaries are excluded. Its
[separate checksums](https://github.com/devsigner9920/z8/releases/download/v0.1.0-rc7/z8-rc7-final-review-SHA256SUMS)
cover only this follow-up; the original 15 assets remain unchanged.

## Current scope

Z8 provides project Linux environments with separate HOME and source directories, multiple terminal sessions, local web previews, and public privacy, retention/deletion, environment, and license information. Users explicitly install and authenticate official AI CLIs. Z8 does not supply accounts, model services, or usage. SSH host management and remote session connections are not yet provided by the app.

The current build configuration uses `dev.devsigner.z8`, ARM64, minSdk 28, and target/compile SDK 36. Declaring Android 9 or later does not mean every Android version, manufacturer, or user profile has been tested.

The published rc6 baseline uses versionCode `7`, with English as the initial app language and an explicit Korean option. See [app language](LOCALIZATION.md). This release separates included offline terminal preparation from optional tool installation. The Tools catalog groups included, recommended and optional tools per project. Opted-in on-open version checks retrieve public metadata at most once per 24 hours; Check now is a separate explicit request. Downloads and updates remain explicit user actions. The matching source archive and store materials have been published and independently downloaded without credentials; the exact validation scope is recorded below.

The rc5 source work opts out of Android WebView usage statistics, clarifies
platform diagnostic reporting separately from Z8-operated telemetry, and adds
private upload-key preparation without bypassing the existing release checks.
The optional Claude installer also verifies the official detached manifest
signature with the guest's existing `gpgv` and a pinned signing-key fingerprint
before downloading or executing the selected binary. It does not change the
official CLI or its authentication choices.
The current guest lock selects a fresh Debian 13.7 ARM64 base. Existing Ubuntu
projects and prepared bases are preserved on upgrade; they are not converted
or deleted. Consequently, an upgraded installation may continue creating
projects from its existing Ubuntu base, while a fresh installation prepares
the new Debian base. This is an explicit compatibility boundary, not a claim
that every stored project has changed distributions.
The [Data safety worksheet](store/play-console-data-safety.md) maps observed
features and transmission paths; it is not a completed Play declaration.

The previously missing `jsr305:1.3.9` sources were found inside the exact Maven
binary JAR. All 31 embedded Java files match the retained upstream SVN revision
49. Collection now verifies binary identity, class/source coverage, upstream
build files and file-specific BSD/CC-BY notices. This resolves that collection
gap; it does not by itself complete the separate combined-work source review.

The rc7 source collection retains 1,224 Maven payloads for 85 dependency
coordinates, with 65 upstream proofs, 2,252 direct source matches, seven binary
resource matches and one narrowly verified source-version substitution. It
preserves the earlier Android resources, build inputs and original licenses,
including the Chromium BSD notice. The rc6 audit's identified Coroutines gap
has been supplemented: its probe was rebuilt byte-for-byte from preferred
source. Kotlin build/generator and Unicode inputs are separately recorded.
Four Java libraries were rebuilt from 788 retained source files and passed
bounded functional checks. These completed checks are described in the
[implementation follow-up](compliance/2026-11-15/implementation.md); the
[original review](compliance/2026-11-15/license-review.md) remains historical
evidence. A full dependency rebuild or completed legal/source-closure approval
is not claimed.
See [the source and notice procedure](RELEASE_LICENSES.md#pinned-upstream-inputs-for-android-libraries).

## Published rc6 source and exact candidate evidence

The immutable [rc6 source release](https://github.com/devsigner9920/z8/releases/tag/v0.1.0-rc6)
is bound to commit `131ce7f3d83b6671121f1f0dedbcbda439f92905`.

| Artifact | SHA-256 |
| --- | --- |
| Public `z8-source.zip` | `36ff81fc7dd0f9444fff57dab523b8464278a0b1329706348a07f47e0786d10d` |
| Local test APK | `bed7761c4777ffb31f3009ef58e8a074b79b97d0fe4e77730f06c6f233ea31d7` |
| Local unsigned AAB | `4d426219d125bc7f380223e3295c157676e631b3a835a78af6944781a8b5eabd` |

All 16 public source and store-preparation assets were downloaded without
credentials and matched the staged hashes. The preparation ZIP contains five
actual screenshots and three foreground-service demonstrations. It contains no
installable binary. The test APK is development-signed, the AAB is unsigned,
and `uploadReady` remains false.

The final source passed 568 host tests with one filesystem-specific skip,
145 terminal-engine tests, bundle validation and 16 KiB alignment checks.
On dedicated ARM64 emulators, the exact final APK passed offline base
preparation and first-terminal file read/write without optional tools, explicit
Git installation and use, Claude Code 2.1.285 → 2.1.311 update with official
manifest-signature and installed-binary verification, and preservation of
existing project files and tools. English/Korean Tools controls, explicit
Check now, daily-check opt-in/off, notification return to the selected project,
and a real local preview were checked. The terminal demonstration includes
actual Android Stop and preserved project files; the tool-update demonstration
completed naturally and does not establish interruption/retry behavior.

Python installation with pip/venv, Node 24.21.0 → 24.22.3 update, and a real
authenticated Codex 0.169.0 task passed on the preceding rc6 candidate with the
same installers. These are not relabeled as final-APK model or install tests.
The final APK preserved the updated Codex client, login and fixture; five
independent fixture tests passed before the owned test login was logged out.
That task used explicitly consented project-local execution, not a working
default Linux sandbox. No authenticated Claude task or physical-device run of
this exact final rc6 binary is claimed. Host lifecycle tests cover selected
tool ownership and scoped deletion guards; earlier device deletion observations
remain attached to their own candidates below.

A minor locale-cache issue remains: after switching language in the same
process, a cached tool-status explanation can retain the old language until
Check status refreshes it. English cold-start default and tool actions remain
correct.

The November 15 live privacy update adopts deletion of operator-held support
correspondence 90 days after resolution, with a
[manual operating procedure](compliance/2026-11-15/support-retention.md).
It is a post-release documentation change, not an automated mailbox cleanup or
a change to the immutable rc6 source archive, in-app text or QA evidence.

## Earlier rc5 and rc4 validation

The published rc5 source and preparation release is bound to commit
`4de78e8e040c26646d76d2a22bb9bfbebfbd8e9e`. Its test APK SHA-256 is
`d64bace92c69311fd8dc1ca0d6a5cb0152d8a8838f60cd5846e7f7aa3a3cf818`;
its unsigned AAB SHA-256 is
`26b2c4988017424ee6961fb2ffb590ad248d6e3b8f210a74102564110ec041ae`.
Neither binary is included in the public source prerelease. The source archive,
notices, store preparation ZIP and both foreground-service videos were fetched
without credentials and matched the staged checksums. The public policy and
review pages matched the published commit.

On that exact rc5 APK, the storage-alias correction allowed a preserved Ubuntu
base to copy into an owned physical-phone test project, followed by terminal
file read/write. The earlier link failure's cause was not independently captured.
An aggressive process-churn deletion remained incomplete during an emulator
graphics stall and retained files. After restarting that dedicated emulator, a
fresh small-child deletion passed while preserving another project's running
session and source files. These are scoped observations, not a universal fix
claim. Preview-data deletion preserved project files and the existing CLI login.

A real Codex task edited files in the dedicated test project and four independent
unit tests passed. This used separately consented local mode after the default
Codex Linux sandbox failed in PRoot. It does not establish sandbox compatibility.
A provider-authenticated Claude task remains untested. The rc5 host suite passed
520 tests with one filesystem-specific skip, and 145 terminal-engine tests
passed. Fresh Debian setup and both foreground-service trigger/stop videos use
the same rc5 candidate. The rc6 Tools evidence is recorded separately above.

The rc4 candidate was exercised on two dedicated ARM64 emulators with 16 KiB
pages. Observed checks included initial environment setup, preserving an
existing project on update, Python/Node/Git execution, local preview, language
switching, foreground-service stop, preview-data deletion and project deletion.
The deletion check preserved another project's files and session. These were
emulator observations; real-provider authenticated tasks and physical-device
validation were not performed in those runs. Release-specific evidence remains
bound to the exact tested artifact rather than inferred from this summary.

## November 14 submission preparation

The public developer display name is **Romi Ethsy**. First-run preparation now exposes offline privacy, environment/external-tool, and open-source notices before downloading development tools. The setup screen identifies Z8 as GPL-3.0-only software with separately licensed components. The existing explicit download action and optional metered-network choice remain in place; reading a notice does not accept external provider contracts.

The [English-primary store preparation](store/README.md) includes localized descriptions, review instructions, an asset plan, and a checklist. GitHub source checks validate release-tag/configuration consistency, current privacy attribution, and listing limits. Source previews preserve corresponding-source evidence; only a separately validated and upload-signed artifact can be submitted to Play. A source tag, screenshot, or passing CI run is not store approval.

## November 4 source-distribution review

The source preparation now records dated modification notices for changed upstream files while preserving their original licenses. Runtime Maven source artifacts and version-matched upstream evidence can be collected and included in the public source package; source JAR availability alone does not prove all required resources and build scripts are present.

The historical rc3 source collection covered 85 resolved Maven coordinates with 265 evidence files: 80 published source JARs, three pinned upstream source mappings, and one verified empty compatibility artifact. That collection left `jsr305:1.3.9` unresolved; the rc5 follow-up above supplies exact embedded and upstream source evidence without replacing the old release. Its annotation classes were absent from the optimized local rc3 candidate inspected during that review. Applicable NDK and file-specific source notices are also preserved.

Nineteen retained Z8 guest source files allow reconstruction of the exact historical guest ZIP and manifest. Current guest defaults produce a different image and must not be substituted silently. The source package and verifier now bind these retained inputs explicitly. See [the reconstruction procedure](RELEASE_LICENSES.md).

The [distribution review](DISTRIBUTION_REVIEW.md) retains the rc3 Ubuntu findings and unsent inquiry drafts as historical evidence. Its November 14 follow-up adds a reasoned ordinary Play submission basis, the observed operator Commercial Terms assent, and the current Debian delivery decision. These do not replace rc3 binaries or source assets, complete license review, or establish store approval.

## English-default update

The November 2 localization checks passed 411 host tests, seven additional bilingual smoke-selector tests, and 145 terminal-emulator unit tests. An rc2 candidate built and validated as a non-debuggable ARM64 AAB with 16 KiB native-library and APK alignment checks.

On the dedicated API 37 emulator, an existing installation without a language preference opened in English. Switching English → Korean → English preserved the project names, terminal output and the same running shell process; terminal input continued to work. These checks cover the language change, not a repeat of every rc1 device test or real CLI authentication.

## Earlier candidate device validation (rc1)

The following results apply only to the specific candidate from November 1, 2026. Subsequent source, configuration, or dependency changes require the relevant checks to be repeated.

- Version: `0.1.0-rc1`, versionCode `2`
- Candidate AAB SHA-256: `580f337c25429824e76bd5cdc8b318b956327e6d5ff8f8208ce0d7b10e6b2eb2`
- Test APK SHA-256: `7f845a34e409daafe1e6dc9c4c75335c4b064956c8a9503e9af819de95631fac`
- Conditions: non-debug universal APK converted from the candidate AAB, signed with a local development key, on a fresh API 37 ARM64 emulator with 16 KiB pages and SELinux Enforcing

| Path checked | Result and scope |
| --- | --- |
| Fresh installation and preparation | Actual theme selection and download consent, base environment preparation, creation of two projects, and terminal execution |
| Preview data deletion | Cookies, localStorage, IndexedDB, Cache Storage, and service workers removed for two origins; HTTP cache refetched. Cancellation preserved data; deletion stopped active previews |
| Data outside the deletion scope | External Chrome web data and synthetic credential substitute/source files in a project preserved. This was not a test with actual CLI credentials |
| Public information and notices | Pages accessible from release Settings; display and navigation of the 5.22 MB license notices |
| Input and navigation | Returning from the browser to the terminal with Back; keyboard input in wide and narrow windows |
| Notifications denied | New terminal, Python, Node, and Git execution and access to the in-app inbox while notifications had never been allowed |

The UI and deletion tests summarized here did not sign in to real service accounts or make model requests. They do not establish behavior when previously granted notification permission is revoked, support for physical external input devices, or physical-device compatibility. Automated checks can be run separately using the entry points in [Contributing](../CONTRIBUTING.md).

## Known limitations

- PRoot shares the Android kernel and app UID. Separate project files do not provide a security VM or malicious-code isolation.
- Codex's default Linux sandbox failed in the tested PRoot environment. Success in a separately selected execution mode must not be interpreted as a working sandbox. The app does not work around this by silently changing approval or isolation policies or replaying failed commands automatically.
- Starting an official CLI or printing its version does not establish compatibility for login, file changes, tool calls, or hooks. Each tool and version needs actual validation.
- Automatic recovery of ordinary shells or AI conversations after the app process ends is not guaranteed. Resuming download preparation and replaying user commands are different operations.
- Secure Folder, work profiles, secondary users, manufacturer-specific background restrictions, and long-running work require further validation.

## Remaining distribution steps

Public contact information and the privacy policy, corresponding source distribution for the binary, external tool and package terms, the necessary tests of the final candidate, and Play Console declarations and review must be checked as part of distribution preparation. Filling in public settings or creating a candidate does not grant store approval.

The identified rc6 Coroutines omission and bounded reconstruction tasks were
addressed in rc7 as described above. The combined-work delivery assessment is
still open; a generic review flag alone is not a demonstrated missing input.
Preserve the published rc6/rc7 source and evidence. Any app, runtime, notice or
source-binding correction needs its own source snapshot and candidate checks.
`sourceClosureReviewed: false` remains until the actual delivery requirements
and exact evidence are assessed; merely changing a flag is not that assessment.

The final review identifies a concrete service-type alignment recommendation:
standalone setup and selected-tool jobs currently use `specialUse` even for
finite download, unpacking and file-processing work. The official
[foreground-service types](https://developer.android.com/develop/background-work/services/fgs/service-types)
map those activities to `dataSync`, while `specialUse` covers valid work outside
the other types. Give finite jobs the appropriate lifecycle and preserve
interactive terminals when types change or a job times out. Adding both types
unconditionally does not address this finding. This is a production engineering
recommendation, not a Google enforcement decision.

Complete the remaining exact-candidate provider coverage, applicable Play
Console declarations, operator distribution decisions and verified upload-key
backup before upload signing. Native-download and AI-feature policy
classification still depend on the actual disclosed functions and ordinary
review; technical success does not establish approval or exemption.

Follow the [build guide](../BUILDING.md) and [release notices and corresponding source procedure](RELEASE_LICENSES.md). A draft privacy policy does not replace a finalized policy that matches the operator's actual data handling and public URL.
