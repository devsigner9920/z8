# Pinned native AI tools in the project guest

This recipe downloads native Linux ARM64 tools into one project's `/z8/home`. The APK contains the recipe and public artifact metadata, not Claude Code or account credentials. No login, model request, API key setup or approval-policy change is part of installation.

```sh
sh /usr/local/lib/z8/install-ai.sh --dry-run
sh /usr/local/lib/z8/install-ai.sh --apply codex
sh /usr/local/lib/z8/install-ai.sh --apply claude
```

`--apply all` runs the two installations sequentially. The default is a dry run that prints the pinned plan and makes no changes. Install the basic guest tools first: Python 3 and CA certificates are prerequisites; Node/npm are not used.

The initial app/project preparation installs the basic development tools and
Node/npm. It does **not** install Codex or Claude Code. Either tool can be
installed explicitly with this recipe or its provider-supported installer;
for example, an npm global Codex installation is separate from the native
managed locations below. Tool status and app launch actions resolve the guest
PATH, so they also recognize npm installations. Installing a second copy does
not merge versions or credentials; the executable selected by PATH runs.

## Runtime orientation

The default working directory and HOME are `/z8/home`; `/workspace` is the
separate project source mount. This is an Android PRoot environment, not a
Sites-managed Linux container. An unset `SITES_MANAGED_LINUX_CONTAINER` is normal.
Likewise `rg --files` can return 1 when a new folder contains no matching files;
neither result alone establishes a process-launch or sandbox failure.

Use `xdg-open http://127.0.0.1:<port>` for a running development server, or
`xdg-open ./index.html` for a local HTML file and its relative assets. The latter
starts a bounded loopback preview for that file's folder. A successful request
only establishes delivery to z8: verify the HTTP response and page behavior
separately. See `docs/BROWSER_PREVIEW.md` for lifetime and path constraints.
This repository document is not injected into user prompts or `AGENTS.md`.

## Pins and provenance

| Tool | Pinned version | Native artifact | Integrity evidence |
| --- | --- | --- | --- |
| Codex | 0.160.0 | `codex-package-aarch64-unknown-linux-musl.tar.gz`, 150,934,664 bytes | SHA-256 from the official OpenAI GitHub release asset digest and package checksum list |
| Claude Code | 2.1.285 | `linux-arm64/claude`, 239,722,488 bytes | Exact SHA-256 and size from the pinned official release manifest; the manifest itself is also hash-pinned |

All URLs and full hashes are in `ai-tools.lock.json`. They were read from public official sources on 2026-10-04. They are a reproducible pin, not a promise to track `latest` automatically.

OpenAI's [CLI documentation](https://learn.chatgpt.com/docs/codex/cli) describes standalone installation and interactive sign-in. The pinned release's [official README](https://github.com/openai/codex/blob/rust-v0.160.0/README.md) also documents direct Linux ARM64 native downloads; the exact asset is in [release 0.160.0](https://github.com/openai/codex/releases/tag/rust-v0.160.0). Codex is Apache-2.0; that does not change z8's inherited Termux licensing.

This recipe installs the **complete official Codex package**. The earlier single
`codex-aarch64-unknown-linux-musl` executable can report its version while normal
interactive startup fails because the local package is incomplete. The complete
asset preserves `codex-package.json`, `bin/codex`, `bin/codex-code-mode-host`,
`codex-path/rg`, `codex-resources/bwrap`, the bundled zsh, and all voice resources,
libraries and license notices. The pinned package has 54 entries and expands to
401,678,403 bytes. Its discovery manifest uses layout version 1, target
`aarch64-unknown-linux-musl` and entrypoint `bin/codex`. The official
[package layout source](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/scripts/codex_package/layout.py)
defines these locations. Preserving a resource does not establish that its
feature works under PRoot.

Anthropic documents native Linux ARM64 binaries, direct binary integrity verification, and deployment tooling in [Claude Code setup](https://code.claude.com/docs/en/setup). Its stable channel resolved to 2.1.285 during verification. This recipe downloads directly from [that version's official manifest](https://downloads.claude.ai/claude-code-releases/2.1.285/manifest.json) and binary endpoint. It does not redistribute Claude Code in z8's APK or treat Claude Code as Apache/MIT software.

The inspected `https://claude.ai/install.sh` first downloads a current bootstrap binary even when an exact target version is supplied. To keep the bootstrap pinned too, this recipe uses the verified native binary directly in an app-managed version directory. It does not execute the downloaded shell installer. The inspected installer hash is recorded as provenance only.

This recipe verifies the Claude manifest's pinned HTTPS-delivered SHA-256. It does **not** claim to verify the detached GPG signature. Anthropic's setup guide documents that additional verification separately.

## Installation behavior

Apply requires Linux on ARM64, the exact `/etc/z8/guest-target` image marker, writable `HOME=/z8/home`, no inherited loader overrides, and the guest's Python at `/usr/bin/python3`. It uses guest system tool paths and does not inherit the Android host PATH.

Downloads require HTTPS and official allowed origin/redirect hosts. Byte counts
and hashes are checked before use. The Codex tar is read without `extractall`:
its exact pinned graph of directories and regular files is validated before
copying to a private staging directory. Every file's size, SHA-256 and mode is
checked. Missing, duplicate or extra entries, traversal, links, special files
and unpinned modes are rejected. Expanded content is bounded to 1 GiB. All six
expected Codex executables, and every bundled ELF encountered, must have a
64-bit little-endian ARM64 ELF header. Claude's binary has the same ELF check.

Each version is prepared in a fresh staging directory and must report its pinned
version under a bounded `--version` probe before publication. A receipt records
the source artifact hash, installed binary hash and actual version output. Codex
also records the complete member inventory, package manifest and executable
list. The directory is then renamed into place and an owned launcher symlink is
atomically updated:

```text
/z8/home/.local/share/z8/ai/codex/0.160.0-package-v1/bin/codex
/z8/home/.local/share/z8/ai/codex/0.160.0-package-v1/codex-package.json
/z8/home/.local/share/z8/ai/codex/0.160.0-package-v1/receipt.json
/z8/home/.local/share/z8/ai/claude/<version>/claude
/z8/home/.local/share/z8/ai/claude/<version>/receipt.json
/z8/home/.local/bin/<tool>
```

An existing installer-owned single-binary Codex `0.160.0/` directory and receipt
are preserved verbatim. The complete package is installed into the sibling
`0.160.0-package-v1/` directory; only the verified managed launcher is switched
after success. Existing processes and user files keep their original paths.
If the new package directory already contains unowned files, installation stops
without overwriting them. Reinstallation checks every packaged companion,
resource, mode and receipt; changed files are preserved and reported. Codex's
normal default configuration directory, `/z8/home/.codex`, remains outside the
package root.

Unowned launchers, changed binaries, symlinked managed directories and unknown existing version directories are preserved and reported. Older managed versions remain present so an existing process keeps its executable. A project-local installation lock prevents two copies of this recipe running together. A killed process can leave a lock that requires inspection; it is not silently removed by a new installer.

The installer does not edit `.claude`, `.codex`, shell startup files, authentication state, model selection, sandbox policy or approval defaults. If the user or a tool's own updater later changes a launcher or binary, the next z8 install preserves that change and asks for review through its error output. Version pins describe this installer, not an enforced prohibition on user updates.

## Authentication and actual compatibility

After successful installation, open `/workspace`, run `codex` or `claude`, and
complete that provider's interactive authentication flow yourself. The app's
Codex action selects `--no-daemon`: execution belongs to this terminal session
instead of the shared app-server daemon. New interactive project Bash sessions
also apply this mode to directly typed `codex`, including npm installations,
when the selected executable advertises the option in a bounded help check.
This addresses the observed Android/PRoot process-start-time lookup failure.
The session-lifecycle option itself does not change approval or sandbox policies. The tools run inside the same
project guest as its source and development tools. Their model inference still
uses the configured service.

The app updates `/etc/profile.d/z8-cli.sh` without changing user startup files
or AI binaries. Existing user aliases/functions take precedence, and the
compatibility function is inherited by nested interactive Bash sessions.
Noninteractive scripts, help/version queries, explicit server-management
commands and `--remote`/`--no-daemon` requests are passed through unchanged.
Older releases without `--no-daemon` support also keep their original arguments.
The function preserves argument boundaries and the tool's exit status; it never
replays a failed prompt. An already-open shell needs a new terminal or
`. /etc/profile.d/z8-cli.sh` after an app update to pick up the change. Explicit
executable paths and `command codex` bypass the function; callers can supply
`--no-daemon` themselves. This compatibility layer does not install either AI
tool, authenticate it, or modify `.codex`/`.claude` configuration. The separately
chosen local execution mode below changes the invocation sandbox policy only
after the user opts in.

The lock starts with `runtimeCompatibility: NOT_TESTED`. A successful `--version` probe establishes only that the downloaded executable starts in that environment. It does not establish login, file editing, command execution, tests, hooks or sandbox compatibility under Android/PRoot. Those require real device/guest validation, with user authentication, and must not be worked around with automatic approval bypass flags.

The 2026-10-04 emulator record (비공개 내부 검증 기록: `reports/compatibility/ai-cli-runtime.json`)
is **PARTIAL**. On API 37 / 16 KiB, Claude 2.1.285 reached its actual first-run
theme chooser. The complete Codex 0.160.0 package reached its sign-in chooser
with `--no-daemon`; default shared-daemon startup failed while recording the
server process's start time. Both tools reported unauthenticated state. No host
credentials were copied and no model task was submitted.

The normal-policy probe `codex sandbox -- /usr/bin/true` failed with
`cannot establish app-server socket mount isolation`, even with the complete
package. The pinned [mount validation source](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/linux-sandbox/src/daemon_mounts.rs#L71)
compares directory identity and mount paths with kernel `/proc` metadata. PRoot
path translation is a likely contributor; this error alone does not establish
which namespace syscall would fail. The [bwrap configuration](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/linux-sandbox/src/bwrap.rs#L375)
also requires user namespaces. Session mode fixes the observed CLI startup
path, **not** sandbox compatibility. The app shows this limitation and does not
silently disable the sandbox, bypass approvals, replay commands, or switch hosts.

The 2026-10-17 check reproduced this failure with npm Codex **0.162.1** in a
real z8 terminal on the Android 17 ARM64 emulator, using an empty, dedicated
HOME and no account/model calls. `codex sandbox -c 'sandbox_mode="read-only"'
-- /bin/true` returned 1 before executing the command. The bundled `bwrap`
also failed its minimum namespace/mount probe because Android denied access
to `/proc/sys/kernel/overflowuid`. The missing-system-bwrap startup warning
means Codex will try its bundled helper; installing another copy does not
remove the earlier socket mount validation requirement.

The packaged PRoot **5.1.107.96** explicitly [emulates success for `unshare`
and `setns`](https://github.com/termux/proot/blob/v5.1.107.96/src/syscall/enter.c#L2407).
An exit-zero namespace probe under this PRoot therefore does not establish
kernel isolation. Do not fabricate `/proc` data, remove Codex mount checks,
or treat a legacy-version downgrade as an equivalent sandbox fix.

The standard sandbox result remains **command execution and file editing:
unsupported in the tested environment**. The explicitly selected local mode
described below has separate authenticated execution evidence.
`apply_patch` shares the restricted filesystem execution path. Browser
preview success from a normal terminal does not change that result. Any
mode without the Codex sandbox needs a separate explicit user choice;
Android app permissions remain, but PRoot is not a security boundary between
z8 projects. See the execution evidence (비공개 내부 검증 기록: `reports/compatibility/2026-10-17-service-recovery/sandbox-app-terminal.txt`).

## Explicit project-local execution choice

On a prepared z8 terminal, typing `codex` uses one managed adapter for both npm
and native installations. On first use it explains that local mode removes
Codex filesystem/network sandbox restrictions and that routine actions may
execute without another approval. The user must type `yes` or `동의` to choose
this mode; Enter, EOF and interruption cancel the launch. Android app
permissions remain, but the mode does not protect other z8 projects from a
process running with the app's access. This is a usability compatibility mode,
not the macOS sandbox ported to Android.

The adapter adds `--no-daemon --sandbox danger-full-access` for a supported
interactive invocation. It does not add `--yolo`, change the user's approval
policy, alter repository trust, or answer Codex's own prompts. Keeping the
approval-policy setting does not keep the sandbox-boundary approval behavior.
Provider/organization requirements still apply; a rejection is not retried
with weaker settings.

The selection is stored separately from Codex settings, under
`/z8/home/.config/z8/codex-local.json`, tied to the app-provided project UUID and
consent schema. It is a user preference, not an authorization boundary against
other processes with the same Android UID. Project creation/templates do not
copy project HOME. Corrupt, foreign-project, or symlinked state never enables
local mode. `codex --z8-reset-local-mode` revokes the stored choice for future
launches; it does not change a running Codex session.

Explicit policy/config/profile/remote options, noninteractive scripts, help,
login, and other noninteractive subcommands retain their original arguments.
Capabilities are checked from the installed CLI with bounded output/time. An
app update applies the new project context to **new terminals**; existing
terminals and user aliases are not rewritten. Authentication remains the
provider's normal flow.

The owned Android 17 emulator fixture used the real `codex sandbox` execution
path with the explicitly selected local policy and verified file creation and
modification, Python and Node child processes, and a localhost HTTP preview.
This initial test used no account or model calls.

On 2026-10-17, a separate user-authorized authenticated test passed with Codex
0.162.1 on the Android 17 ARM64 emulator. The user connected their account and
explicitly allowed local mode for the emulator fixture. One interactive task
created HTML with the patch tool, applied a second edit, passed Python (3) and
Node (2) checks, started a loopback HTTP server in tmux, and opened the page via
the app browser bridge. The resulting file and WebView were independently
checked, including a real button tap that changed visible status. An unsent
Codex draft survived app switching, folding and unfolding, with the same Codex
process and working input after each transition. Browser close also restored
focused Codex input after both partial and maximized windows.

The matching APK was installed on the connected Samsung device and its
existing project loaded; this authenticated task was run on the emulator, not
repeated on the physical device. No physical-project local-mode choice was
made on the user's behalf. This does not establish standard-sandbox support,
all approval paths, or Claude Code task compatibility. See the
authenticated test report (비공개 내부 검증 기록: `reports/compatibility/2026-10-17-authenticated-flow/index.html`).

`tests/test_ai_install.py` covers the no-change default, host guard, pin/URL
validation, size/hash failures, complete tar graph/ELF handling, managed
publication, raw-binary migration, changed companions, preservation of unowned
files, path symlinks and the version-probe command. Tests use temporary synthetic
artifacts and a mocked version probe; they do not claim execution of the official
AI tools.
