# Per-project Linux guest

`Z8EnvironmentActivity.intent(context, projectId)` opens the private Linux environment screen. `Z8Guest` owns installation state and work with a static executor and application context. Recreating or rotating the Activity does not recreate the installer or start a duplicate install. Process death can interrupt installation; this is not a foreground-service guarantee.

## Included image and installation

The optional APK assets are `z8/guest/rootfs.zip` and `z8/guest/manifest.json`. Without both assets, the UI reports that no verified image is included. Without the own-prefix PRoot executable, a runtime APK exposes an entry to install its execution base; a diagnostic APK cannot pretend to install one.

The schema version 1 manifest identifies the normalized Ubuntu ARM64 image, original download/checksum sources, ZIP SHA-256 and byte size, expanded size and entry count, and every regular/directory entry with mode and size. `SYMLINKS.txt` is included in those counts and consumed as deferred relative link records (`target←destination`). It is not installed as a guest file.

Installation verifies the complete ZIP SHA-256 before creating extracted files. It then matches every entry against the manifest, bounds each file and the aggregate size, rejects traversal/duplicate paths and special entries, applies explicit mode records, and creates links after regular files and directories. A link cannot be an ancestor of another archive entry. Link chains are resolved component by component to detect escapes involving symlinks followed by `..`; lexical path normalization alone is insufficient.

The app extracts into a fresh `.install-<UUID>` staging directory beneath that project's environment directory. A complete install marker and executable Bash are checked before a same-filesystem rename publishes `rootfs`. Existing `rootfs` is never selected for extraction or intentionally replaced. Failed staging data is cleaned up without following links; process death may leave an orphan staging directory, which is not considered an installed environment. Reset/removal of an environment is not implemented yet.

Limits: 512 MiB archive, 2 GiB expanded content, 100,000 total archive/link entries, 16 MiB manifest, 4 MiB link list, and at least 128 MiB free space beyond the declared expanded size. The actual pinned Ubuntu base is substantially smaller. These are defensive limits, not device performance guarantees.

## Persistent paths

| Role | Android app-private path | Guest path |
| --- | --- | --- |
| Replaceable environment | `files/z8/environments/<projectId>/rootfs` | `/` |
| Project HOME | `files/z8/homes/<projectId>` | `/z8/home` |
| Existing project source | `files/z8/projects/<projectId>/source` | `/workspace` |
| Temporary files/shared memory | `files/z8/environments/<projectId>/{tmp,shm}` | `/tmp`, `/dev/shm` |

Neither source nor HOME belongs to the environment image. Installing an environment does not delete or reset either. This separation must remain true when reset is eventually implemented.

## Shared execution adapter

`Z8Guest.command(context, id, relativeCwd)` returns `Launch { executable, arguments, workingDirectory, commandOffset }`. A null relative cwd starts at `/z8/home`; the empty string starts at `/workspace`; a nonempty relative path is validated inside the project's source before becoming `/workspace/<relative>`.

`commandFor(...)` uses the same environment for noninteractive Git and registered tools. The current allowlist is `/bin/bash`, `/usr/bin/git`, `/usr/bin/gh` and `/usr/bin/python3`. Bash accepts only the login entry or the managed setup-tools script. `commandOffset` identifies the actual guest executable after `/usr/bin/env` options and static assignments. Callers must keep dynamic hook tokens in the process environment, never argv.

The executable is the app's own-prefix PRoot. Arguments use the pinned build's `--kill-on-exit`, `--link2symlink`, `--sysvipc`, `-L`, `--change-id=0:0`, explicit rootfs and cwd. Only `/proc`, the selected terminal/entropy/null devices, project source/HOME/temp and the dedicated attention socket transport are bound. App-wide attention history, unrelated project directories, host HOME, host prefix and `/sys` are not bound. These flags follow the pinned [PRoot-Distro command builder](https://github.com/termux/proot-distro/blob/v5.9.0/proot_distro/commands/login/proot_cmd.py); actual Android operation still requires device testing.

The parent process must clear `LD_PRELOAD` and `LD_LIBRARY_PATH` **before starting PRoot**, and give PRoot an app-writable `PROOT_TMP_DIR`. Clearing them only inside the guest is too late for the guest loader. Guest `/usr/bin/env` removes remaining host-specific variables, sets HOME/PATH/TERM/LANG/TMPDIR, and preserves dynamically supplied Z8 session identifiers and event tokens. Only the nonsecret socket path is translated to `/run/z8/attention/events.sock` in argv.

## DNS and convenience tools

Installation writes a managed `/etc/resolv.conf` using active Android `LinkProperties` DNS servers. Opening a guest refreshes that file only while its z8 managed header remains; replacing it with a user-managed file or symlink opts out. No public DNS service is silently selected. With no active Android DNS, the file reports that fact and a later guest opening can update it after reconnection.

The ready screen can start the managed package setup script in a new Linux terminal. That terminal shows the real download, apt installation and result; the screen does not mark packages installed merely because it launched the script.

## Validation boundary

`tests/test_guest_archive.py` runs the actual Java extractor against traversal, size/hash mismatch, preexisting-content, symlink escape/cycle/ancestor and missing-entry fixtures. If a normalized artifact exists, it also extracts the actual image and checks Bash, the managed profile and descriptor links. Those tests establish host-side extraction behavior; they do not establish PRoot, networking, package installation, AI CLI compatibility or Android background execution.

Filesystem checks and PRoot are not a kernel security boundary against a hostile process sharing the app UID. The in-process installer serialization prevents duplicate app installs; it is not a cross-process transaction against arbitrary filesystem mutation.
