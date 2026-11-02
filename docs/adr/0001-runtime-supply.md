# ADR 0001: build a z8-prefix runtime and fail closed until verified

- Status: accepted; source builder implemented, Android execution gates remain separate
- Date: 2026-10-03

## Context

z8 is a standalone, non-root Android application using Termux-derived execution and terminal components. Its application ID is `dev.devsigner.z8`. Runtime executables, libraries and package metadata must use `/data/data/dev.devsigner.z8/files/usr`. An APK built with a renamed application ID and an official `com.termux` bootstrap is not an accepted runtime.

The host is macOS arm64. A project-local Lima/VZ ARM64 Linux builder now runs the digest-pinned official Linux amd64 package-builder through QEMU user emulation. Only this repository is mounted; host HOME and SSH agent are not shared. This VM is a developer build dependency, not part of the Android runtime. Builder execution and artifact inspection remain distinct from Android runtime and physical-device tests.

Official `termux-packages` revision `27d2485b86dd0aed74ae7095434c83cbba7bf1dd` was inspected. Its source-build bootstrap script supports extra packages and aarch64 selection; its repository-download bootstrap script is a different workflow. The primary application package property is `TERMUX_APP__PACKAGE_NAME`, assigned inside `scripts/properties.sh`, so a shell environment override of the legacy `TERMUX_APP_PACKAGE` is insufficient. The default native build NDK is r30, and the builder image tag is not an immutable backend pin. See the source inspection notes in `runtime/README.md` before implementing the recipe.

## Decision

1. Keep the official upstream source and its license notices. Record exact source commits centrally in `tools/sources.lock.json`; an unavailable revision remains a blocker rather than an invented pin.
2. Build z8's bootstrap and native packages for its application ID and prefix. Do not silently fetch official-prefix packages, including during first launch or dependency installation.
3. Supply a versioned manifest containing application ID, prefix, architecture, source commit and archive SHA-256. App preparation validates it before embedding an archive. Diagnostic builds use an explicitly empty runtime and cannot masquerade as runtime-ready builds.
4. `tools/build-runtime.sh` delegates to the implemented source builder. Its core profile builds Bash, Dash, termux-exec, tmux, PRoot, tar, gzip and their real dependencies. Every upstream package remains pinned by the reviewed package source checkout. A private generated source tree changes the application prefix and disables stock-prefix repository fetches. Core omits only Bash’s non-linked termux-tools convenience dependency; package manager installation belongs inside the Linux guest until an own-prefix host repository exists.
5. The official builder image is pinned by manifest digest, config digest and platform in `runtime/builder.lock.json`, with NDK r30 archive checksum checked against the source. The recipe records source overlays, commands and artifact provenance. Raw bootstrap archives are retained; only the explicitly verified optional ARM32 PRoot loader is excluded from the ARM64-only published archive. Archive validation checks architecture, paths, prefix and dynamic-library closure before publication. Source and toolchain pinning do not alone establish byte-for-byte reproducibility.

## Required evidence before closing G0 runtime supply

- Exact upstream package commit and reviewed z8-specific configuration/patches.
- Backend identity, toolchain versions, build commands, dependency source checksums and preserved notices.
- Artifact checksums and package index provenance for any later native-package installation.
- No official `com.termux` path in runtime loader/shebang/config paths where it determines execution.
- Non-root arm64 device tests: shell command, tmux detach/reattach, PRoot distro entry, runtime-package installation and persistence after returning from another app.
- Separate tests for actual Claude Code/Codex login, edit, command/test execution and their sandbox limits. A working shell or `--version` does not satisfy those tests.

## Consequences

Diagnostic APK work and guest image preparation can proceed while the source runtime is being compiled and tested. Linux build infrastructure, own-prefix package maintenance and artifact provenance are explicit project work. We accept that cost instead of distributing a bootstrap that can only run under another Android application's path. This decision does not promise root privileges, kernel containers, unbounded background execution or verified CLI compatibility.
