# z8 runtime supply

Status: **the own-prefix core runtime compiled successfully and passed static archive validation on 2026-10-04 (KST).** The local result is `artifacts/runtime/core-360af8dad27815ef/manifest.json`: an 8,136,325-byte archive with 98 ARM64 ELF files and 288 compatible 16 KiB load segments. Android execution is recorded separately from these build checks. The diagnostic APK does not contain this runtime.

| Field | Required value |
| --- | --- |
| Android application ID | `dev.devsigner.z8` |
| Native package prefix | `/data/data/dev.devsigner.z8/files/usr` |
| Architecture | `aarch64` (Android ABI `arm64-v8a`) |
| Package sources | official `termux/termux-packages`, commit from `tools/sources.lock.json` |
| Builder | immutable official GHCR image in `builder.lock.json`, Linux amd64 |
| Native toolchain | upstream NDK r30, archive SHA-256 pinned in the builder lock |

Official `com.termux` packages are incompatible. The generated build changes the primary application identity, preserves the upstream repository identity mismatch, and blocks repository dependency downloads. It never uses `generate-bootstraps.sh`, which downloads published packages.

## Running the builder

Python 3.11+, Git, and a running Linux Docker daemon are required. macOS may launch Docker through a Linux VM. The official image contains x86_64 build tools, so an ARM host also requires working amd64 execution in its Linux backend. This is unrelated to rooting the Android app/device.

```sh
# Read-only source and Docker-daemon check; no pull or package download.
bash tools/build-runtime.sh --preflight

# Generate a source overlay without Docker or downloads.
bash tools/build-runtime.sh --prepare --profile core

# Fast first stage: real host bash, tmux and PRoot, without Python/host apt.
bash tools/build-runtime.sh --build --profile core --jobs 4

# Full host bootstrap: upstream essentials, tmux, proot and proot-distro.
bash tools/build-runtime.sh --build --profile workspace --jobs 4
```

Optional environment variables:

- `Z8_PYTHON`: Python executable.
- `Z8_GIT`: Git executable.
- `Z8_DOCKER`: one executable Docker wrapper; arguments are passed as an argv list. Useful for `limactl shell … docker`. The backend must see the repository at the same absolute path.
- `Z8_TERMUX_PACKAGES_DIR`: pristine checkout of the locked official source.

`--build` pulls only the locked image digest. At the recorded registry inspection it contained about 2.60 GB of compressed layers; source builds and their caches need additional space. The first core build took about 90 minutes on the local 6-vCPU ARM Linux VM with amd64 tools under QEMU and used roughly 5 GiB of source/toolchain cache. This is an observation, not a general timing guarantee. The full `workspace` profile expands to 126 recipe nodes including build-only dependencies at the pinned revision; proot-distro 5.9.0 brings Python/pip and Python brings further Tk/X11/build dependencies. That larger profile has not been compiled or timed.

## Stages and guarantees

`core` builds bash, dash, termux-exec, tmux, proot, tar and gzip plus their linked dependencies: 21 main recipes at the pinned revision. The core-only bash recipe omits the convenience dependency `termux-tools`; bash's actual `libandroid-support`, `libiconv` and `readline` dependencies remain. Its existing profile/bashrc use shell builtins and guard optional files; z8 supplies its own shell setup. This change is recorded in the generated-source hashes. Host apt/pkg, curl and GNU coreutils are not advertised in this stage; basic Android utilities remain accessible through `/system/bin`. Package-manager second-stage scripts are omitted. This stage validates the real terminal, tmux reconnect and manual PRoot entry; it is not a complete development environment.

For target API 36 on Android 10 or newer, host ELF entrypoints use
`/system/bin/linker64`; Android 9 retains direct execution because its linker
cannot run programs. Native shells preload the matching source-built
termux-exec 2.5 linker/direct library so their host child
processes use the same entrypoint. Guest sessions clear the Android preload and
library path before entering the Linux environment; guest ELF files are handled
by PRoot, never by Android's linker. The PRoot source overlay changes only its
default guest-loader location to `files/applib/libproot-loader.so`. Its normal
source build still produces `libexec/proot/loader`, whose identical bytes are
packaged in the APK's extracted native library directory. The app refreshes the
`files/applib` symlink after installation or update, refuses an unexpected file
at that path, and fails closed if the packaged loader is missing. Process cleanup
also verifies an executable PRoot mapping when `/proc/pid/exe` names the linker.
These are execution requirements; they do not establish Google Play policy
approval for user-installed executable packages.

An optional `--seed-runtime artifacts/runtime/core-360af8dad27815ef/manifest.json`
on `tools/prepare-runtime.py --build --profile core` reuses that published
runtime's source-built dependencies. It verifies the source lock, builder,
unchanged dependency overlays and every retained `.deb` checksum, extracts them
only into a new build volume without running maintainer scripts, and always
rebuilds PRoot. The output provenance records the reused packages and original
runtime digest. Without this option the complete dependency graph builds from
source as before.

The API 36 runtime upgrade accepts only the previous core archive recorded in
`assets/z8/bootstrap-upgrade.tsv`. It checks every immutable installed file and
symlink, preserves managed environment/profile files, and refuses extra or
modified host files. Any other live process owned by the app blocks the upgrade.
The final validation and directory renames share the app's process-launch lock;
a durable backup allows recovery if the process dies between renames. Project
source, project Linux filesystems, HOME and CLI login files are outside this host
prefix and are not moved or replaced. Regenerate the allowlist from a verified
prior artifact with `tools/prepare-bootstrap-upgrade.py`, never from a user's
installed directory.

`workspace` preserves upstream bootstrap essentials and adds tmux, proot and proot-distro. Host apt has an empty sources list, `pkg` delegates only to explicitly configured apt sources, and automatic official mirror selection is disabled. There is no z8 host package repository yet. Guest Debian repositories are a separate supply path inside the guest; they must not supply Android host binaries.

The source tree is copied from Git-tracked files after checking exact HEAD and a pristine working tree. Upstream is never edited. Generated source is stored under `.local/runtime/<recipe fingerprint>/termux-packages`; changed source/overlay/image inputs receive a different directory and independent Docker data/cache volumes. Repeat runs can resume already source-built packages within that fingerprint. No host `/data`, Docker socket, privileged container, or host sysctl changes are requested by the recipe.

The overlay additionally corrects two bootstrap packaging details at this pinned revision: symlink destinations omit the leading `./` for the retained app installer validator, and the second-stage architecture argument uses the active architecture. Original licenses and package metadata remain in the build sources/output.

For backends running the builder under QEMU, the container briefly initializes its two dedicated volume directories as container root, then drops to the normal `builder` account. This avoids an unsupported emulated sudo/setuid transition. NDK r30's FUSE overlay is replaced by a private toolchain copy in the build cache (`cp --reflink=auto`), retaining the same upstream NDK patches and avoiding `/dev/fuse`, mount capabilities or a privileged container. The copy consumes roughly another 2 GiB on filesystems without reflink support.

## Output and evidence

After successful compilation, `prepare-runtime.py` invokes the same `validate_bootstrap_zip` and `verify_runtime` functions used by the APK preparer. They reject stock-prefix strings, wrong ELF architecture, unsafe archive paths/symlinks and invalid manifests. Publication also checks that tmux/proot are present and apt has no enabled repository. Every ELF's `DT_NEEDED` SONAME must be present in the archive or in an explicit public Android system-library allowlist; foreign Linux ELF interpreters are rejected. Every ELF `PT_LOAD` segment must have at least 16 KiB alignment and compatible file/virtual offsets; segment counts and results go in provenance. These static checks do not replace testing Android's dynamic loader or execution on a device with 16 KiB pages.

Validated results go to `artifacts/runtime/<profile>-<archive digest>/`:

- `bootstrap-aarch64.zip`: the exact validated archive.
- `manifest.json`: the strict seven-field app contract.
- `provenance.json`: source lock, immutable builder, recipe fingerprint, command, package archive hashes and timestamp.

The ARM64 PRoot package also builds an optional ARM32 guest loader. If the exact `libexec/proot/loader32` entry is an ARM32 ELF, packaging excludes that helper while preserving the raw upstream ZIP. ARM32 guests are unsupported in this stage. All other foreign-ABI files still fail validation.

The core profile additionally excludes four exact installed sanitizer-test ELF paths from termux-core/termux-exec. Those developer fixtures depend on an ASan runtime absent from the core package closure. Each exclusion verifies ARM64 ELF format and the expected ASan dependency, and records the file's SHA-256 and reason. Unsanitized tests and all production executables/libraries remain; production linkage failures are still fatal.

Two pinned termux-exec text files contain stock-prefix paths only in documentation comments. Packaging verifies their entire original SHA-256 hashes and exact comment line numbers, then substitutes the z8 prefix in those comments. It does not alter executable statements or native binaries. Any unexpected original content fails closed. Only matching dpkg file-list/checksum lines are also updated to keep the package metadata consistent with these explicit packaging changes. All other retained file bytes remain identical. Provenance records the raw ZIP digest, excluded path, comment and metadata file names/line numbers/before-and-after hashes, and packaging script digest. The source-built `.deb` archives remain unmodified.

If compilation has already completed and only archive finalization needs to be retried, use `--finalize-source .local/runtime/<fingerprint>/termux-packages`. It verifies the saved overlay hashes, immutable builder command and resulting archive without repeating compilation; it does not itself attest that compilation or Android execution succeeded. Preserve the original build log as the execution evidence.

The first local build's original compiler/assembly log is `.local/runtime-core.log`; its older in-memory publisher correctly stopped on upstream stock-prefix documentation comments after reporting successful archive assembly. `.local/runtime-core-finalize.log` records successful finalization with the explicit normalization described above. The raw ZIP and 39 original `.deb` outputs remain in `.local/runtime/f287ff4424e3f68b65da/termux-packages/`.

Device execution is recorded as `NOT_TESTED` in build provenance. The immutable builder and source recipe support repeatable inputs; byte-for-byte reproducibility is **not measured**. A manifest and matching digest alone do not establish working Android execution, tmux persistence, PRoot, package installs, or AI CLI compatibility.

To consume an actual result, pass its `manifest.json` to `tools/build-app.py --mode runtime --runtime-manifest <path>`, then complete the [G0 validation plan](../docs/validation/G0_VALIDATION_PLAN.md). `manifest.example.json` remains an intentionally unusable format example, not a runtime.

## Guest defaults

[Guest provisioning inputs](guest/README.md) define `/z8/home` as each environment's persistent HOME and ordinary terminal start directory, with project source separately mounted at `/workspace`. The package list includes Git, SSH, network, search, archive and editing tools; compiler/Python tools are optional. These inputs are not packages installed in the diagnostic APK, and do not replace the own-prefix host bootstrap.

The official [Termux build-environment documentation](https://github.com/termux/termux-packages/wiki/Build-environment) describes the upstream Docker workflow. z8 pins the image by digest rather than following its mutable tag. See also [runtime supply ADR](../docs/adr/0001-runtime-supply.md).
