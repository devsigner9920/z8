# Building Z8 development APKs and Play candidates

**English** | [한국어](BUILDING.ko.md)

Distinguish diagnostic APKs from runtime APKs built for Z8's own prefix. Shared screens cover projects, sessions, terminals, Linux preparation, themes, attention notifications, and execution diagnostics, using the actual Termux PTY/JNI, terminal, and service. Running `/system/bin/sh` in a diagnostic APK is a separate validation step from running a Linux guest or AI CLI. A successful build alone does not establish that G0 acceptance checks have passed.

## Development tools

The current setup requires macOS ARM64, Python 3.12 or later, working Git, and curl. macOS executables such as `/usr/bin/java`, `git`, and `python3` may be stubs if their tools are not installed. In that case, put working executables on PATH or set `Z8_GIT` and `Z8_PYTHON`.

```sh
python3 tools/setup-toolchain.py
python3 tools/prepare-app.py --mode diagnostic
python3 tools/generate-release-notices.py --allow-incomplete
python3 tools/build-app.py --mode diagnostic
```

The public repository does not include notices generated for an earlier candidate. Here, `prepare-app.py` prepares the pinned upstream sources, and `generate-release-notices.py` generates full license texts and notices for development from the current sources. `INCOMPLETE` is an expected indication that work remains; `--allow-incomplete` does not pass release review. For binary distribution, regenerate notices using the actual package and Gradle inventories and corresponding source described below.

Tools are installed under `.local/` without replacing the global JDK or SDK. Downloads of the JDK and Android command-line tools are checked against `tools/toolchain.lock.json`. SDK package IDs are pinned, but IDs updated upstream, such as platform-tools, do not guarantee a fully reproducible build. SDK installation includes the provider's license acceptance procedure.

Termux sources are fetched at the commit in `tools/sources.lock.json`. Do not modify `upstream/termux-app`. `tools/prepare-app.py` applies exact patches and `overlay/` to a separate `.local/build-src` tree, stopping if the original commit or expected code differs. The Gradle cache is kept in `.local/gradle`.

After creating an APK, the default build command runs terminal-emulator unit tests and checks APK signing, app ID, ABI, SDK, and 16 KiB ZIP alignment. Depending on the mode, outputs are `artifacts/z8-g0-diagnostic-arm64.apk` or `artifacts/z8-g0-runtime-arm64.apk`, with matching JSON, signing, and manifest reports. `.local/keys/z8-debug.jks` is generated on the first build for this development environment. It does not use the public Termux test key. Losing the key prevents updates signed with the same identity as existing installations. Play candidates and upload signing use the separate process below.

## APK identity and SDK

| Item | Current build setting |
| --- | --- |
| applicationId | `dev.devsigner.z8` |
| Java namespace / JNI | Retains upstream `com.termux` |
| Host prefix | `/data/data/dev.devsigner.z8/files/usr` |
| ABI | `arm64-v8a` |
| Min / target / compile SDK | 28 / 36 / 36 |
| External Termux app | Not required |

Target SDK 36 has been used since November 1, 2026. Android 10 and later use the system linker to execute Android/Bionic host programs; Android 9 retains direct execution. Linux guest execution uses PRoot, with the PRoot loader bundled as an APK native library. Device compatibility for this change and the application of Play's external executable code policy are separate reviews. Do not use ADB options to bypass installation blocks for low target SDKs. The app assumes standard internal paths for the primary Android user. Secure Folder, work profiles, and secondary users are untested.

## Play submission candidates and upload artifacts

Maintain the product scope: a free development terminal with no ads or in-app purchases, running official CLIs on the user's device. Build commands do not automatically upload files or publish source or policy pages.

`release/config.json` contains public, non-secret configuration. Fill in the developer display name, support email, privacy policy HTTPS URL, **public HTTPS URL that directly downloads this release's corresponding source ZIP**, and policy effective date. Do not include signing keys, passwords, or authentication tokens. URL format validation does not establish public availability or legal compliance. Only candidates can be created while actual operator values are missing.

```sh
python3 tools/build-app.py --variant candidate --mode runtime \
  --runtime-manifest /absolute/path/runtime/manifest.json \
  --guest-manifest /absolute/path/guest/manifest.json
```

Candidates are built with release optimization under `.local/build-candidate`. `artifacts/z8-candidate-runtime-arm64.aab` is an **unsigned candidate**, not a file ready for upload. The companion APK is converted from the same AAB with bundletool and signed with the local development key for device testing. Its JSON records version, SDK, debuggable state, hashes, missing public information, and validation scope. The bundletool version and SHA-256 are also pinned and checked. Do not create Play upload artifacts with the development key.

Prepare the following evidence for the candidate:

1. Use `tools/collect-release-package-sources.py`, `tools/package-release-source.py`, and `tools/generate-release-notices.py` to assemble notices and corresponding source for the actual host, guest, and Gradle components. Follow each command's `--help` and the [distribution notices](THIRD_PARTY_NOTICES.md). Unavailable source or license evidence must remain unresolved.
2. After finishing source and public configuration changes, regenerate the source snapshot and notices and **rebuild the final candidate**. Generated notices themselves are excluded from the snapshot to avoid a circular source hash. Do not use earlier candidate tests as results for new files.
3. Use `tools/verify-release-compliance.py` to connect the final AAB, notices, sources, packages, and Gradle inventory. `--source-url` and `--check-source-url` download the public source ZIP without authentication and verify its hash. The actual result must be `VERIFIED` before proceeding.
4. Copy `release/qa.example.json` and record the actual final candidate hash and device/test evidence. Emulators do not replace physical-device testing. Verify actual CLI authentication and work using authorized test accounts. Leave unperformed checks as `NOT_TESTED`.
5. Copy `release/decisions.example.json` and record review of policies, provider terms, store descriptions, Data safety, and service declarations. This is an operator review record, not an approval from Google or a provider. Keep fields `false` without supporting evidence.

Use a separate operator-managed upload key. Pass passwords through `Z8_UPLOAD_STORE_PASSWORD` and `Z8_UPLOAD_KEY_PASSWORD`, and the keystore path and alias through `Z8_UPLOAD_KEYSTORE` and `Z8_UPLOAD_KEY_ALIAS`. Do not put their values in source files, reports, or command records. Once all evidence is ready, the following command signs the validated candidate **without rebuilding it**:

```sh
python3 tools/promote-release.py \
  --candidate-metadata artifacts/z8-candidate-runtime-arm64.json \
  --compliance-report /absolute/path/verified-compliance.json \
  --qa-report /absolute/path/final-qa.json \
  --decisions /absolute/path/reviewed-decisions.json
```

Successful output is saved under `artifacts/releases/<versionCode>/`. The process verifies that the app payload is unchanged by signing and passes bundletool validation; it does not overwrite an existing release directory. Missing developer information, a development signing identity, a changed candidate, or incomplete testing, policy review, or corresponding source verification stops the process. Play App Signing enrollment, Console declarations, account-specific testing requirements, installation/update tests with Play-generated APKs, and review are separate operational steps. If the release signature differs from an installed development APK, it cannot update that installation. Use a separate test device rather than asking users to delete their projects.

## Default paths and shell conveniences

On first launch, preview and choose a terminal theme: Prism, Midnight, Graphite, Ember, or Paper. The selection and initial setup completion state are saved together. Change the theme later using the top gear menu, Settings, and Theme. Going back after only previewing a theme keeps the previous selection. Theme changes apply to the terminal background, text, cursor, and 16 ANSI colors without restarting the shell. User `colors.properties` and shell configuration files are not overwritten.

A new Android diagnostic session displays `Welcome to Z8 Terminal` and hints for `ll`, `mkcd`, and `z8help` once using the selected palette. Returning to a session, rotating the screen, nesting shells, or reloading the profile does not repeat the banner. It is not added to noninteractive shell output.

The diagnostic shell starts in the app's actual `files/home`. The APK-managed `files/z8/shell/diagnostic.mkshrc` is used as the interactive Android shell's `ENV`, providing `ll`, `la`, `l`, `..`, `...`, `cls`, and `mkcd`. Use `z8help` to list them. User `.profile` and `.mkshrc` files are neither overwritten nor arbitrarily executed at shell startup. `TMPDIR` is a cache directory writable by the app. Changes apply to newly created shells after an APK update.

The project PRoot `HOME` and normal starting directory of a new Linux terminal are `/z8/home`. Project sources are mapped separately at `/workspace`. The session list's `＋` opens a Terminal directly in that project's HOME. After consent to data use during initial app setup, the app prepares Git, gh, Python, pip, venv, Node LTS, npm, build-essential, and the [base packages](runtime/guest/README.md) in a hidden template environment before project creation. New projects copy independent files from this template and do not share HOME or sources. See [preparation lifecycle](docs/PREPARATION_LIFECYCLE.md) for progress notifications, network changes, and recovery after force termination. AI CLI installation and authentication are explicit user actions, not automatic initial setup steps. Consult validation records for the scope actually tested at each stage.

## Project and session navigation

The separate workspace home and file, Git, and GitHub screens were removed following the October 5, 2026 product decision. Use `git` and `gh`, installed during initial environment preparation, for Git and GitHub work. Earlier internal Workspace links now select a terminal project without creating a new shell.

The app starts on the terminal screen. The top-left list button opens project sessions. Windows at least 720dp wide use an expanded sidebar; narrower windows use a sliding panel. Layout updates when the panel is collapsed or expanded or the window is resized. Sessions in the current project also appear as horizontal tabs at the top, with `＋` fixed on the right even when there are many tabs.

Selecting a project name returns to that project's last session remembered by the current terminal screen. If the session is no longer alive, another existing session is selected. If none exists, the project is selected with an empty terminal area. Selecting a name does not create a session. The separate expand icon only collapses or expands the project list.

When the available height drops below 480dp, for example while the keyboard is shown, the top panel and project header spacing is reduced. The notification button remains to the right of the Z8 logo, and themes are opened from Settings in the top gear menu. There are no bottom attention or theme buttons.

The tab bar's `＋` opens a new Terminal in the selected project. If the project has no tabs, the bar and button are hidden; create the first terminal with `＋` beside the project. Ordinary terminals are named `Terminal 1`, `Terminal 2`, and so on within each project. Creating a session does not require a project/tool selection modal. If the Linux environment is missing, automatic preparation stages and progress appear in the terminal area without falling back to a shared device shell. Creating a project still asks for its name.

The add button is temporarily disabled while preparing a session to prevent rapid taps from requesting duplicates.

Run Claude Code or Codex in the terminal after explicitly installing the required CLI. Development builds also provide install/run buttons under Settings → Current project environment. Initial base environment installation includes neither AI CLI. It creates no default AI tab and does not start AI automatically. Tabs represent actual user-created sessions. Selecting an existing tab or session row attaches to the same PTY owned by the service. Switching sessions does not create another process or terminate the existing program. Long-press a tab or row to rename it, copy recent output, view notifications, or close the terminal. Long-press a project title to open the deletion confirmation. If terminals are running, the option to stop all and delete requests both operations together. Files are not deleted if process termination cannot be confirmed.

The unread notification indication uses only actual unread hook events received for live sessions. An open-session indication describes PTY process state, not whether AI is working. Recovery of shells or conversations after the app process ends is outside this UI's scope. See [session navigation](docs/SESSION_NAVIGATION.md) for behavior and Orca references. APK identity and actual test scope are recorded in the private internal session UI validation record, `reports/compatibility/session-navigation.json`.

## Build the Linux runtime

Diagnostic mode does not include a bootstrap. Its Linux button is disabled, and it can open only `/system/bin/sh`. Runtime mode requires a bootstrap manifest matching Z8's app ID, prefix, ABI, and SHA-256. It does not substitute a stock `com.termux` bootstrap.

```sh
# Build tools from source for Z8's own prefix using the Linux Docker backend.
bash tools/build-runtime.sh --build --profile core --jobs 4
# Use the generated verified manifest path.
python3 tools/build-app.py --mode runtime --runtime-manifest /absolute/path/runtime-manifest.json
# Check the pinned Ubuntu Base and create guest artifacts.
python3 tools/prepare-guest.py --build
# Add --guest-manifest to embed a project Linux image.
python3 tools/build-app.py --mode runtime --runtime-manifest /absolute/path/runtime-manifest.json --guest-manifest /absolute/path/guest/manifest.json
```

The bootstrap contains Android-native tools. Guest image installation and actual Claude/Codex sign-in, editing, shell, and test validation are separate. The Linux screen prepares each project's rootfs in a new staging directory before publishing it, without overwriting an existing environment. HOME and source files are kept outside rootfs. There is no UI to reset or delete only the environment yet. Deleting an entire project through its title removes source files, HOME, and the Linux environment together; distinguish this from environment recovery.

`tools/build-runtime.sh` pins source commits, the official builder image digest, and the NDK, and compiles tools from source for Z8's prefix. `core` focuses on the shell, tmux, PRoot, and compression tools; `workspace` is the full package management profile. It does not silently substitute official `com.termux` packages. See [runtime/README.md](runtime/README.md) for supply boundaries.

On macOS without Docker, `python3 tools/setup-builder-vm.py --install` can prepare a project-specific Lima build VM. The VM, tools, and settings are kept in `.local/`, sharing only the repository. Set `Z8_DOCKER="$PWD/.local/bin/docker-z8"` for builds. This is a cross-compilation environment on the development machine; the Android app does not require a VM or root. Stop it when unused with `LIMA_HOME="$PWD/.local/linux-vm" .local/lima/bin/limactl stop z8-builder`.

## Device checks

```sh
sh tools/device-check.sh --output reports/compatibility/device-report.json
python3 -m unittest discover -s tests -v
```

The device check is read-only and records `NOT_TESTED` when no device is connected. Prefer testing APK installation through the normal installation UI. After installation, inspect device and prefix information in diagnostics, open or resume the terminal, and run `id`, `pwd`, and `uname -m`. Creating a new Android diagnostic shell opens a separate session. Check that leaving, returning, and rotating preserve the same shell. Distinguish emulator results from physical-device results. Full acceptance criteria are in the [G0 plan](docs/validation/G0_VALIDATION_PLAN.md).

## Dedicated emulator smoke tests

The bottom ESC, CTRL, and arrow-key accessory bar is hidden by default. The earlier `NEW SESSION` and `KEYBOARD` panels have been replaced by the project/session UI and are no longer displayed. Create sessions with `＋` beside a project or the fixed tab-bar `＋` when tabs exist. Use terminal input and existing external-keyboard shortcuts for the system keyboard. The accessory bar and system keyboard have independent visibility.

```sh
# Run in a separate terminal. The first --install downloads the emulator/image.
sh tools/start-emulator.sh --install
# To use the emulator interactively with its window visible:
sh tools/start-emulator.sh --windowed
# After boot: verify the dedicated AVD, then install/update the APK and test.
python3 tools/smoke-emulator.py
```

The configuration uses the API 37.0 ARM64 16KB image and Pixel Fold hardware profile with 4GB RAM. It does not replace Galaxy or 8GB acceptance testing. The test grants notification permission through the normal UI, records a PID and shell variable from the app's PTY, and checks a 10-second Home/return cycle and one rotation. `run-as` prepares and reads test files in the dedicated debug app; a separate tmux continuity test uses it to execute a control client under the same app UID. Evidence of actual user commands comes from the PTY created by the app. Tests do not bypass installation policies, use root, or change physical-device settings. They stop if the target serial or AVD name differs.

After generating the runtime APK, use the following validation entry points. Linux tests require the existing test project UUID and display name. They do not automatically sign into accounts or make remote changes.

The October 17, 2026 check updated continuity and navigation scripts for the current `Terminal N` names and tab long-press menu, with related host checks passing. The command list below is a guide to test entry points, not a claim that every device test has passed for the current APK. Check each script's dedicated AVD restrictions and required initial state before running it. Actual rerun results are identified by APK hashes in dated `reports/compatibility/` records.

```sh
python3 tools/smoke-runtime.py
python3 tools/smoke-tmux.py
python3 tools/smoke-guest.py --project PROJECT_UUID --name 'z8 demo'
python3 tools/smoke-guest-continuity.py --project PROJECT_UUID --name 'z8 demo'
# Session navigation using two installed Linux environments:
python3 tools/smoke-session-navigation.py --project PROJECT_UUID --name 'z8 demo' --other-project OTHER_PROJECT_UUID --other-name 'hello-world'
```

The continuity test creates a small evidence file and two new sessions in an existing test project. It uses PIDs and shell variables to check Home/return, panel collapse/expansion, and project inheritance for new sessions without closing existing sessions. The current UI uses the terminal project-list button, top tabs, and fixed `＋`. Long-pressing the terminal and selecting `More…` → the session-list/new-session action opens the same panel. Distinguish earlier APK continuity results from current session UI testing using the APK identity in each report.

The session navigation test uses two separate dedicated fixture projects. It checks shell creation, renaming, tab/project switching, switching with the keyboard visible, and panel collapse/expansion. It closes only the `Scratch` session created by the test, using an explicit close confirmation. The `Build` and `Review` names, shells in the other project, and small evidence files remain. It performs no account authentication or AI tasks and requires a dedicated test state with at least four available session slots.

Each script checks the installed APK and bootstrap and records actual executables, PIDs, HOME, and page size. The manual connection test in `smoke-tmux` does not establish that automatic product-level tmux session management has been implemented. Actual CLI sign-in, file edits, and command/test execution must be completed separately with a user account.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for original licenses and the scope of modifications.
