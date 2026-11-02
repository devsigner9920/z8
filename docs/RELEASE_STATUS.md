# Release status and validation scope

Documentation: [English](../README.md) | [한국어](../README.ko.md)

As of November 2, 2026, Z8 is a development project that has not reached a stable app release or Play Store launch. Source publication and app submission or approval are separate procedures. This document is a public summary of validation, not a compatibility guarantee for every build from current sources or every device.

## Current scope

Z8 provides project Linux environments with separate HOME and source directories, multiple terminal sessions, local web previews, and public privacy, retention/deletion, environment, and license information. Users explicitly install and authenticate official AI CLIs. Z8 does not supply accounts, model services, or usage. SSH host management and remote session connections are not yet provided by the app.

The current build configuration uses `dev.devsigner.z8`, ARM64, minSdk 28, and target/compile SDK 36. Declaring Android 9 or later does not mean every Android version, manufacturer, or user profile has been tested.

The current source revision is configured as `0.1.0-rc2`, versionCode `3`, with English as the initial app language and an explicit Korean option. See [app language](LOCALIZATION.md). Its source URL targets the `v0.1.0-rc2` source preview. This version setting does not establish that an app binary has been released or that the earlier device checks below have been repeated for rc2.

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

Follow the [build guide](../BUILDING.md) and [release notices and corresponding source procedure](RELEASE_LICENSES.md). A draft privacy policy does not replace a finalized policy that matches the operator's actual data handling and public URL.
