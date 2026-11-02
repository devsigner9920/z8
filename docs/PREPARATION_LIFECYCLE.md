# Initial setup and project preparation lifecycle

Reviewed 2026-10-11. This document describes the recovery contract and acceptance
checks; it does not claim that every case has passed on a physical Samsung device.

## User-visible contract

Initial setup prepares a hidden app-owned Linux base before the first user project
exists. The reserved preparation owner is never listed as a project or exposed as
a terminal. The user can choose to install now or later, with explicit consent
before metered downloads. New projects copy the validated base into their own
writable rootfs; packages, source, HOME, and writable inodes are not shared.

Preparation is owned by `TermuxService`. Leaving
the Activity, switching apps, rotating, or folding must not cancel that request.
While preparation owns service work, the ongoing notification identifies the
initial setup or the project and current stage. Tapping it focuses the preparation
without creating a second terminal or replaying an action. Extraction percentages are real; package
installation and version checks use an indeterminate progress indicator.

If Android or the user stops the app process, preparation stops. On the next
user-initiated foreground launch, an interrupted preparation request can be
recovered. This is not an automatic restart while the app remains force-stopped.
Only initial setup and first-environment preparation are eligible: shell commands, AI prompts,
login flows, Git actions, and previous running processes must not be replayed.

“Continue from the missing stage” means validate completed stages, reuse them,
and retry the incomplete stage. It is not byte-offset continuation of an archive
or an exact instruction pointer inside `apt`.

## Durable stages

| Stage | Completion evidence | Recovery |
| --- | --- | --- |
| App runtime | `.z8-bootstrap.sha256` plus executable Bash and PRoot | Reuse the published runtime. An interrupted unpublished extraction starts again. |
| Project Linux image | Validated `.z8-environment.json` in published `rootfs` | Reuse the existing rootfs. Never replace it because package installation failed. |
| Distribution packages | Live `dpkg-query` installed/ok status for the complete profile and clean `dpkg --audit` | Skip package downloads when valid; otherwise complete configure/dependency repair without removing packages. |
| Node/npm | Pinned published Node directory passes actual version probes | Reuse the version, restore missing managed command links, or repeat an incomplete download/extraction. |
| Final profile | Atomic `tools.ready` publication after Python/pip/venv/Node/npm checks | Initial setup becomes ready without creating a terminal; a project request opens one terminal. A partial receipt cannot establish readiness. |
| New project copy | Complete independent rootfs copy with the new project's environment marker | Reuse the completed base without apt or Node downloads; retry only an unpublished copy. |

Project source and HOME are separate from rootfs. Recovery does not delete or
reset either directory and does not replace user startup files.

`Z8InstallStaging` writes an ownership sidecar before a disposable bootstrap or
rootfs extraction tree exists. Recovery requires an exact UUID name, bounded
matching ownership contents, and a real directory. It never follows a linked
ownership receipt or staging root. Nested symlinks are removed as links without
visiting their destinations. A receipt left after publication is discarded
without touching the published tree. Older unmarked directories are preserved
because their disposable ownership cannot be established safely.

The bootstrap's small startup-prefix backup uses the same ownership scheme.
After an interrupted rename, it is restored if `usr` is absent. If Android startup
has recreated `usr`, only missing known startup files are copied back. Conflicting
values are both preserved; unknown files in a backup stop automatic recovery.

## Download consent and network changes

`Z8SetupDownloadProxy` routes managed apt and Node installer downloads through a
short-lived authenticated loopback proxy. It resolves official download hosts and
creates upstream sockets using the selected Android `Network`. Losing that
network fails its connections instead of creating replacement connections on the
device's new default network. A changed network policy closes the proxy's listener
and all client/upstream sockets before the installation worker is cancelled.

The proxy accepts only HTTP GET/HEAD and HTTPS CONNECT for the configured Ubuntu
and Node distribution hosts on their expected ports. Proxy credentials stay in
memory/environment and are stripped from HTTP origin requests. It is not a
general browser proxy or a security boundary against arbitrary guest software.

Metering is a network capability, not a synonym for cellular transport: Wi-Fi can
also be metered. Default-network callbacks must wait for capabilities before
allowing a new connection. Android process binding alone is insufficient for
PRoot's separately executed Linux programs. See [network-state guidance](https://developer.android.com/develop/connectivity/network-ops/reading-network-state)
and [process network binding](https://developer.android.com/reference/android/net/ConnectivityManager#bindProcessToNetwork(android.net.Network)).

## Android behavior

Foreground work must be started from the visible, user-initiated flow and promoted
to a foreground service. Newer target SDK levels add service-type and background
start requirements; raising z8's target SDK remains a separate compatibility task.
See [Android foreground service launch documentation](https://developer.android.com/develop/background-work/services/fgs/launch).

Android 13 and newer can run a foreground service when notification permission is
denied, but its notification is absent from the notification drawer. The app must
explain this state and offer notification settings; it must not claim a visible
notification when the user has blocked it. Target SDK 32 and lower also do not
control the permission prompt timing in the same way as newer targets.
See [notification permission behavior](https://developer.android.com/develop/ui/compose/notifications/notification-permission).

The Android Active apps Stop control removes the whole app from memory and sends
no shutdown callback. Durable recovery cannot depend on `onDestroy` having run.
Android documents `cmd activity stop-app PACKAGE_NAME` for testing this case.
See [user-initiated foreground app stopping](https://developer.android.com/develop/background-work/services/fgs/handle-user-stopping).

## Emulator acceptance matrix

Use only a dedicated emulator and disposable test projects. Do not force-stop,
clear app data, revoke permissions, or change network settings on a user's active
physical project. Record the exact APK SHA, emulator API, project ID, receipts,
source/HOME hashes, number of setup subprocesses, and final terminal count.

| Case | Procedure | Required result |
| --- | --- | --- |
| Initial consent | Open an app without a prepared base; choose Later, then reopen setup | No implicit project/terminal is created, and no install starts before acceptance. |
| Metered consent | Use a metered emulator network | Download requires the explicit data-use choice; a policy change pauses and retains recovery state. |
| Network switch | Start on permitted Wi-Fi then change to a disallowed network during transfer | Proxy closes and the worker stops; no default-network retry or false success. |
| Leave during installation | Create project, wait for tools stage, Home; open notification drawer | Service remains foreground; notification reports the same project/stage; preparation advances without a visible Activity. |
| Tap notification | Tap the preparation notification repeatedly, rotate and fold | Same project is focused; one accepted preparation, one package manager, and one eventual terminal. |
| Screen off | Turn display off during package download, then wake | Work continues where device power policy permits; state is accurate and never falsely reports success. |
| Force-stop during bootstrap | Stop after an owned staging tree has content but before `usr` publication; relaunch | Stale owned tree cleaned; fresh verified runtime published; source/HOME unchanged. |
| Bootstrap rename gap | Fixture an owned early-prefix backup with `usr` absent or regenerated | Missing known files restored; conflicting values preserved; unknown/linked paths never deleted. |
| Force-stop during rootfs | Stop during extraction; relaunch | Only incomplete owned extraction is discarded; validated rootfs published once. |
| Force-stop during package unpack | Stop with packages unpacked but not all configured; relaunch | Existing rootfs reused; `dpkg`/dependency repair completes; no manual lock-file deletion. |
| Force-stop during Node | Packages already installed; stop during Node download/extraction; relaunch | Package stage revalidated without apt update/install; Node incomplete stage retried. |
| Force-stop after final receipt | Stop between ready receipt and UI delivery; relaunch | Tools are not reinstalled; recovery produces no more than one terminal. |
| Existing user terminal | Run a harmless counter script in a ready project, force-stop and relaunch | Previous script is not restarted. Recovery is limited to incomplete preparation. |
| Offline/error | Interrupt network during download; restore network and retry | Failure is visible; completed runtime/rootfs/packages remain; retry begins from the incomplete stage. |
| Notification blocked | Disable notification permission on emulator during preparation | Preparation remains valid; UI accurately links notification settings and does not promise drawer visibility. |
| Warm new terminal | Open another terminal after readiness | No extraction or package install; immediate ordinary terminal launch. |
| New project after setup | Create a project from the ready base | Rootfs files are copied independently with fresh HOME/source; no apt or Node download. |

Host regression coverage includes actual bootstrap extraction and filesystem
recovery fixtures (`tests/test_bootstrap.py`), hostile/real rootfs extraction
(`tests/test_guest_archive.py`), and subprocess lifecycle/provisioning tests. Those
checks complement Android lifecycle tests and do not substitute for them.
