# Release status and validation scope

Documentation: [English](../README.md) | [한국어](../README.ko.md)

As of November 15, 2026, Z8 is a development project that has not reached a stable app release or Play Store launch. Source publication and app submission or approval are separate procedures. This document is a public summary of validation, not a compatibility guarantee for every build from current sources or every device.

The [November 15 policy and license review](compliance/2026-11-15/README.md)
is the current review entry point. Its findings supplement the immutable rc6
release and the historical records below; they do not change a tested binary
or establish Google Play approval.

## Current scope

Z8 provides project Linux environments with separate HOME and source directories, multiple terminal sessions, local web previews, and public privacy, retention/deletion, environment, and license information. Users explicitly install and authenticate official AI CLIs. Z8 does not supply accounts, model services, or usage. SSH host management and remote session connections are not yet provided by the app.

The current build configuration uses `dev.devsigner.z8`, ARM64, minSdk 28, and target/compile SDK 36. Declaring Android 9 or later does not mean every Android version, manufacturer, or user profile has been tested.

The published source release is `0.1.0-rc6`, versionCode `7`, with English as the initial app language and an explicit Korean option. See [app language](LOCALIZATION.md). This release separates included offline terminal preparation from optional tool installation. The Tools catalog groups included, recommended and optional tools per project. Opted-in on-open version checks retrieve public metadata at most once per 24 hours; Check now is a separate explicit request. Downloads and updates remain explicit user actions. The matching source archive and store materials have been published and independently downloaded without credentials; the exact validation scope is recorded below.

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

The latest source-evidence collection supplements 57 of the 59 resolved Android
library coordinates packaged as AARs while retaining their published source
JARs. ConstraintLayout and termux-am-library already have separate pinned
upstream source mappings. The new supplement
preserves 374 pinned upstream inputs, verifies 1,627 original Java/Kotlin files
byte for byte, and retains one original generated `BuildConfig.java` with its
generator recipe. Another 384 Git object checks connect shared root build files
to the selected source commits. Original Android resources, build scripts,
licenses and notices are retained; the generated notices now include the full
Chromium BSD license for WebKit's boundary interfaces. The other 23 published
JAR source collections have not received this full upstream-input supplement;
that is a review category, not 23 demonstrated missing libraries. The current
[license review](compliance/2026-11-15/license-review.md) identifies a concrete
coroutines source/resource gap, a bounded Kotlin build/source-set mapping, and
a functional reconstruction task from the public inputs. No complete dependency
rebuild or completed corresponding-source delivery is claimed.
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

Resolve the specific coroutines source/resource omission and bounded
reconstruction tasks in the current license review, rather than treating every
unsupplemented JAR or a generic review flag as a demonstrated defect. Preserve
the published rc6 evidence. Any runtime, notice or source-binding correction
must receive a new source snapshot and corresponding candidate checks.
`sourceClosureReviewed: false` remains until the actual delivery requirements
are supported; an arbitrary sign-off does not replace the missing evidence.

The exact final rc6 candidate still needs physical-device coverage, broader
lifecycle/preview regressions and a provider-authenticated Claude task for any
compatibility claim about that workflow. Complete the applicable Play Console
declarations and review, operator distribution decisions, and verified upload-key
backup before upload signing. Native-download policy and provider conditions
are assessed in the current review; technical success is not policy approval.

Follow the [build guide](../BUILDING.md) and [release notices and corresponding source procedure](RELEASE_LICENSES.md). A draft privacy policy does not replace a finalized policy that matches the operator's actual data handling and public URL.
