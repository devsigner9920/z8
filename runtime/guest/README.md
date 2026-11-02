# z8 guest defaults

Status: **Initial setup prepares the native runtime, pinned Ubuntu Base and standard tools before project creation.** New projects copy the prepared environment independently, then open their first Terminal. The foreground service owns preparation; interrupted accepted work resumes on the next foreground launch, while completed stages are validated and reused. Clean failures offer retry. No temporary Android shell or tool-install tab is created. The optional environment details screen checks executable versions and reports rootfs, tools and AI separately. Native diagnostic shells are an explicit rescue function, never a project fallback.

## Paths and launch contract

Each environment gets its own writable rootfs, HOME and temporary files. The reference `launch.sh` binds that environment's persistent HOME directory to `/z8/home`, sets `HOME=/z8/home`, and starts a new terminal there using `/bin/bash --login`. It uses the core profile's own-prefix PRoot directly; a future PRoot-Distro adapter must preserve these same mappings. The shell profile deliberately does not run `cd`, so nested shells retain their current directory.

Project source remains a separate `/workspace` bind, consistent with the implementation spec. A future explicit “open terminal in this project/folder” action can select a directory under `/workspace`; the ordinary terminal default stays `/z8/home`. The old `/home/dev` HOME proposal is superseded by this requested default. Host storage still uses `files/z8/homes/<envId>/` and `files/z8/projects/<workspaceId>/source/` outside the disposable rootfs. Never share writable HOME between projects or bake a user's HOME into the base image.

The launcher binds the target project HOME before provisioning. Setup does not copy source files or rewrite HOME/startup settings.

## Included conveniences

`debian-base-packages.txt` is the default apt package list:

- Bash and completion, standard file/text/archive utilities.
- `git`, SSH client, `curl`, `wget` and CA certificates.
- `rg`, `fdfind`, `fzf`, `jq`, `tree`, `file` and process tools.
- `less`, `nano` and `tmux`.

Interactive shells get `ll='ls -alF'`, `la='ls -A'`, `l='ls -CF'`, `..='cd ..'`, `...='cd ../..'` and `cls='clear'`. `mkcd <directory>` accepts exactly one directory argument, creates it and enters it only if creation succeeds; quoted spaces and paths beginning with a dash are supported. Existing `cls` and `mkcd` commands, functions or aliases are preserved. `fd` aliases `fdfind` only when a command, function or alias named `fd` is absent. Bash also gets completion, appended history and window-size updates. No Git identity, credentials, SSH keys, CLI approval settings or automatic tmux session are configured.

The standard profile includes `python3`, `python3-pip`, `python3-venv`, `build-essential`, and an official pinned Node LTS distribution including npm. `--with-build-tools` remains a compatibility alias. AI CLIs and project dependencies are still explicit separate installations. Node 24.21.0 / npm 11.19.0 is pinned in `node.lock.json`, verified against the official Node SHA256SUMS file and installed in `/opt/z8/node/v24.21.0`. The `/opt/z8/node/current` pointer publishes only after actual Node/npm version probes pass. Existing `/usr/local/bin/node`, npm or npx that are not z8-managed links are preserved and require review.

## Provisioning a future guest

Preview from any host; neither command installs anything:

```sh
sh runtime/guest/provision.sh
sh runtime/guest/provision.sh --dry-run --with-build-tools
```

After a verified image builder has entered the target Debian/Ubuntu guest as guest root and mounted its dedicated HOME, it must mark the target rootfs. The following commands are **guest-only**, never Android host or development-machine setup:

```sh
mkdir -p /etc/z8
printf '%s\n' z8-guest-v1 > /etc/z8/guest-target
sh /path/to/runtime/guest/provision.sh --apply
```

`--apply` requires the marker, Linux, an exact Debian/Ubuntu distribution ID, guest root and apt. The marker prevents an accidental install on an unprepared system; it does not establish a security boundary. Use the guest's own configured apt repositories. No official-prefix Termux repository is involved.

On every guest launch the APK atomically refreshes only its fixed application-owned
scripts in `/usr/local/lib/z8`; existing environments therefore receive installer and
probe fixes without reinstalling their rootfs. Its separate browser and CLI profiles
in `/etc/profile.d/z8-browser.sh` and `/etc/profile.d/z8-cli.sh` are refreshed too.
HOME, source, `/etc/z8/shellrc`,
`/etc/profile.d/z8.sh`, AI credentials and user hooks are not overwritten. Provisioning
creates missing shell defaults only. Apt retains package-manager locking and retries
transient repository downloads; the Node installer uses a kernel-released file lock,
private staging, bounded HTTPS downloads, pinned hashes, archive path/ARM64 checks,
and version checks before publishing. A failed step never marks the profile ready.

`probe-tools.sh` runs bounded read-only version checks. A command that prints a version
but returns failure is not ready. Python pip/venv, compiler, make, Node/npm, Git/gh and
tmux must all work for `State.toolsReady`; AI executable readiness does not imply
successful authentication or sandbox compatibility. Missing AI fails before a PTY is
created. Explicit tool/action sessions exit with their actual status rather than
silently becoming a shell under an AI tab label.

Primary sources: [Node release lifecycle](https://nodejs.org/en/about/previous-releases),
[release index](https://nodejs.org/dist/index.json),
[pinned official checksums](https://nodejs.org/dist/v24.21.0/SHASUMS256.txt).

Package names are input requirements, not a reproducible image manifest: the selected distro release, repository snapshot, package versions, image digest and licenses must be recorded by the future image build. Device verification must check `pwd`, `printf '%s\n' "$HOME"`, `ll`, completion, package executables and persistence across new sessions. These inputs alone do not close the runtime build or guest-execution validation gates.


## Pinned Ubuntu Base artifact

`image.lock.json` pins the official Ubuntu Base 24.04.5 AArch64 tarball and its
published SHA256SUMS file. `tools/prepare-guest.py` defaults to a read-only plan:

```sh
python3 tools/prepare-guest.py
python3 tools/prepare-guest.py --build
python3 tools/prepare-guest.py --verify /absolute/artifact/path/manifest.json
```

The builder downloads over HTTPS, checks both pinned hashes and the tarball's
entry in the checksum list, and never executes guest code or runs apt. The hash
is a pin obtained from Canonical's HTTPS publication; GPG signature verification
is not claimed. It preserves the base image's package metadata and copyright
files. No compiler, AI CLI or convenience package is installed by this step.

Image normalization adds an effective-UID guard to Ubuntu's exact, verified
`/etc/bash.bashrc` sudo-hint block. Guest root skips this unnecessary hint before
it invokes `groups`, which otherwise warns about Android supplemental group IDs
that have no Ubuntu names. Non-root behavior and other shell errors are preserved;
Android group membership is unchanged. This applies only to newly built image
generations and never rewrites an existing project's rootfs.

Artifacts live in `artifacts/guest/ubuntu-24.04.5-arm64/<ZIP SHA-256>/`. The
`rootfs.zip`/`manifest.json` pair is validated before publication. ZIP order and
timestamps are normalized; byte reproducibility across Python/zlib versions has
not been established. `verify_manifest(path)` is the read-only embedding API and
returns `(archive_path, manifest_data)`.

The manifest includes `schemaVersion=1`, `type=z8-guest-rootfs`,
`normalizationVersion=1`, `architecture=aarch64`, distribution/release, pinned
source/checksum URLs and hashes, ZIP name/hash/bytes, `entryCount`,
`totalUncompressedBytes`, and every ZIP entry as `{path,type,size,mode}`.
Directory paths end in `/`, their size is zero, and modes are integers in
0..0777. Setuid/setgid/sticky bits are stripped. `SYMLINKS.txt` is an ordinary
counted ZIP entry containing `target←destination` lines. Absolute guest links are
converted to relative links, hard links are materialized as regular files, and
symlink destinations cannot be parents of other archive entries. Device nodes,
FIFOs, traversal, duplicate names and unsupported ELF architectures are rejected.
The validator resolves the symlink graph to catch escapes through intermediate
links, not only literal `..` at the beginning.

Android installation must verify the whole ZIP hash and manifest bounds, extract
regular files into a **new private staging rootfs**, apply modes, then create
validated symlinks last and atomically publish that generation. Never extract on
top of an existing environment, HOME or project source. Keep `SYMLINKS.txt` as a
regular file or explicitly omit its chmod step if the installer consumes it
without materializing it. Image creation includes the `/etc/z8/guest-target`
marker, shared `/etc/z8/shellrc` and login loader; mount-point directories and
standard `/dev/fd` links are prepared without creating privileged device nodes.

## Reference PRoot launch

All storage paths must already exist and be distinct; ordinary new sessions use
`/z8/home`, while explicit folder sessions may use a contained `/workspace/...`.
The launcher defaults to dry-run and prints the exact argument vector without
printing hook credentials:

```sh
bash -p runtime/guest/launch.sh --rootfs /app/environment/rootfs \
  --home /app/environment-home --source /app/project/source \
  --temp /app/environment-temp
# Add --run only on the Android runtime after inspecting the plan.
```

`-p` prevents inherited Bash startup functions/BASH_ENV from running before this
launcher. It removes inherited export attributes and exports a small guest
whitelist; `LD_PRELOAD`, `LD_LIBRARY_PATH`, Android PREFIX and other host settings
are not copied into guest tools. Hook nonce/launch ID, when enabled, remain in
environment values and are never interpolated into command arguments or source.
`Z8_SHOW_WELCOME=1` is set for the newly created shell.

The verified Termux PRoot 5.1.107.96 arguments are `--kill-on-exit --link2symlink
-0 -r ROOTFS`. `-0` emulates guest identity; it gives no Android root privileges.
`-k` changes the advertised kernel version and is deliberately not used.
`--kill-on-exit` ends traced children when the session's main shell exits; a UI
detach must keep that shell owned by the service/tmux session rather than exit it.
There is no automatic `-R`/`-S` host sharing and no QEMU `/host-rootfs` exposure.

Bindings are the selected HOME, selected source, environment tmp/shm, `/proc`,
`/dev/pts`, and `/dev/null`, `/dev/zero`, `/dev/random`, `/dev/urandom`, `/dev/tty`,
`/dev/ptmx` individually. No host HOME, `/etc`, `/sys`, full `/dev`, app storage,
SSH keys or other project directories are bound. `/proc` and the kernel remain
shared resources; PRoot is not a kernel security boundary. `PROOT_TMP_DIR` points
to the environment's host temporary directory for PRoot's own startup needs.

With `--hooks-transport /app/z8/attention/transport`, only that socket directory
is mapped to `/run/z8/attention`; the app journal stays outside the guest. The
launcher requires a valid nonce and registered launch ID in its environment. The
Python helper and provider hooks remain separate opt-in installation steps.

Ubuntu Base ships empty `/etc/resolv.conf` and `/etc/hosts`. Networking requires
a separate, per-environment DNS configuration derived from the device/user; this
recipe does not silently choose a public resolver or bind host `/etc` files.
Do not report apt, network or AI CLI compatibility from a successful bash launch.

Source references: [Ubuntu Base release](https://cdimage.ubuntu.com/ubuntu-base/releases/24.04/release/),
[official checksums](https://cdimage.ubuntu.com/ubuntu-base/releases/24.04/release/SHA256SUMS),
[pinned PRoot option definitions](https://github.com/termux/proot/blob/v5.1.107.96/src/cli/proot.h),
[pinned PRoot temp implementation](https://github.com/termux/proot/blob/v5.1.107.96/src/path/temp.c).

### Browser requests from a terminal

New terminal launches set `BROWSER` and `GH_BROWSER` to the managed
`/usr/local/lib/z8/browser/bin/xdg-open`. The same directory is added to `PATH`
after the Ubuntu login profile, so Python `webbrowser`, GitHub CLI, and ordinary
`xdg-open https://…` can request the Android browser. Personal shell startup files
may override these defaults. Existing running shells retain their old environment;
open a new terminal after upgrading the app.

The helper needs the standard profile's Python 3. It sends a single bounded JSON
frame through the existing private socket using the live launch token. Only HTTP(S)
URLs without embedded credentials or control characters, plus exact `about:blank`, are accepted. URL text is
passed as data, never evaluated as a command. Invalid requests return a nonzero exit
code without printing the URL or token. No browser URLs are written to the attention
journal, log, or notification text.

CLI requests for literal loopback HTTP(S) URLs open the in-app development preview;
exact `about:blank` opens its empty address tab. External HTTP(S) requests use an
external browser / Custom Tab, including authentication. If z8 is in the background,
a request waits in memory for foreground UI
(maximum one per session, 16 sessions, two minutes) and is dropped when its terminal
ends. A delivered request does not mean login succeeded; the CLI still owns OAuth
state, callbacks, and the authorization result. Browser credentials remain with the
browser. This follows [RFC 8252](https://www.rfc-editor.org/rfc/rfc8252), especially
sections 6 and 8.12, and [Android Custom Tabs](https://developer.chrome.com/docs/android/custom-tabs).
