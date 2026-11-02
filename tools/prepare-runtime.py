#!/usr/bin/env python3
"""Build source-derived z8 bootstrap archives in an immutable Linux container.

No mutation of pristine upstream, stock-prefix binaries or network repository
fallback. Archive inspection is a build gate, not proof of Android execution.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import struct
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]

# Exact source-built v2.5.0 files, inspected against the pinned recipe. These
# upstream comments quote stock paths even though executable paths are generated
# with the z8 prefix. No binary or executable shell statement is rewritten.
COMMENT_PREFIX_EXAMPLES = {
    "bin/termux-exec-ld-preload-lib": (
        "c86d7e56eac7d53081870e212efc36fa3315223ec9ade3cad4253c0df8157b8b", [103], "#"),
    "include/termux-exec/termux/termux_exec__nos__c/v1/termux/api/termux_exec/service/ld_preload/direct/exec/ExecIntercept.h": (
        "1d22ff61481babbd865eb74270966b3d040637f799d5bdb8a170c11bc0dd81bf", [88, 93, 97, 103], "*"),
}
OPTIONAL_SANITIZER_TESTS = (
    "libexec/installed-tests/termux-exec/lib/termux-exec_nos_c/tre/bin/libtermux-exec_nos_c_tre_runtime-binary-tests-fsanitize28",
    "libexec/installed-tests/termux-exec/lib/termux-exec_nos_c/tre/bin/libtermux-exec_nos_c_tre_unit-binary-tests-fsanitize",
    "libexec/installed-tests/termux-exec/lib/termux-exec_nos_c/tre/bin/libtermux-exec_nos_c_tre_runtime-binary-tests-fsanitize",
    "libexec/installed-tests/termux-core/lib/termux-core_nos_c/tre/bin/libtermux-core_nos_c_tre_unit-binary-tests-fsanitize",
)


class RuntimeError(ValueError):
    pass


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(argv, *, capture=False, cwd=None):
    try:
        result = subprocess.run(argv, check=True, cwd=cwd, text=True,
                                stdout=subprocess.PIPE if capture else None,
                                stderr=subprocess.PIPE if capture else None)
        return result.stdout if capture else None
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        raise RuntimeError(f"Command failed: {argv[0]}: {detail.strip()}") from exc


def replace(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f"Upstream patch anchor changed: {path.name}: {old[:90]!r}")
    path.write_text(text.replace(old, new))


def validate_inputs(root):
    lock = json.loads((root / "tools/sources.lock.json").read_text())
    builder = json.loads((root / "runtime/builder.lock.json").read_text())
    if lock.get("applicationId") != "dev.devsigner.z8" or lock.get("prefix") != "/data/data/dev.devsigner.z8/files/usr":
        raise RuntimeError("Unsupported runtime application identity")
    entry = lock.get("termuxPackages", {})
    if entry.get("url") != "https://github.com/termux/termux-packages.git" or not re.fullmatch(r"[a-f0-9]{40}", entry.get("commit", "")):
        raise RuntimeError("Missing verified termux-packages source lock")
    if (builder.get("schemaVersion") != 1 or builder.get("platform") != "linux/amd64"
            or not re.fullmatch(r"ghcr\.io/termux/package-builder@sha256:[a-f0-9]{64}", builder.get("image", ""))
            or builder.get("ndkVersion") != "30"):
        raise RuntimeError("Builder must be the locked Linux amd64 image and NDK r30")
    git = os.environ.get("Z8_GIT") or shutil.which("git")
    if not git:
        raise RuntimeError("Git required; set Z8_GIT")
    source = Path(os.environ.get("Z8_TERMUX_PACKAGES_DIR", root / "upstream/termux-packages"))
    if source.is_symlink() or not source.is_dir():
        raise RuntimeError("Pristine upstream checkout is absent or is a symlink")
    if run([git, "-C", str(source), "rev-parse", "HEAD"], capture=True).strip() != entry["commit"]:
        raise RuntimeError("Upstream HEAD differs from the source lock")
    if run([git, "-C", str(source), "status", "--porcelain", "--untracked-files=all"], capture=True).strip():
        raise RuntimeError("Upstream source is not pristine")
    names = run([git, "-C", str(source), "ls-files", "-z"], capture=True).split("\0")
    epoch = run([git, "-C", str(source), "show", "-s", "--format=%ct", "HEAD"], capture=True).strip()
    if not epoch.isdigit():
        raise RuntimeError("Invalid source commit date")
    setup = (source / "scripts/setup-android-sdk.sh").read_text()
    if f'ANDROID_NDK_SHA256={builder["ndkArchiveSha256"]}' not in setup:
        raise RuntimeError("NDK archive checksum differs from pinned package sources")
    return lock, builder, source, [name for name in names if name], epoch


def copy_sources(source, output, names):
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or ".git" in path.parts:
            raise RuntimeError("Unsafe tracked source path")
        original, target = source / name, output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if original.is_symlink():
            link = os.readlink(original)
            if Path(link).is_absolute() or not original.resolve().is_relative_to(source.resolve()):
                raise RuntimeError(f"Source symlink escapes upstream: {name}")
            target.symlink_to(link)
        elif original.is_file():
            shutil.copy2(original, target)
        else:
            raise RuntimeError(f"Missing tracked source: {name}")


def apply_overlay(tree, lock, builder, profile):
    replace(tree / "scripts/properties.sh", 'TERMUX_APP__PACKAGE_NAME="com.termux"',
            f'TERMUX_APP__PACKAGE_NAME="{lock["applicationId"]}"')
    # Android target >= 29 cannot exec the guest loader from writable app data.
    # The APK contains the identical source-built loader as a native library;
    # Z8Bootstrap maintains files/applib -> ApplicationInfo.nativeLibraryDir.
    # Keep make's output under libexec/proot so packaging has one verified source.
    loader = str(PurePosixPath(lock["prefix"]).parent / "applib/libproot-loader.so")
    (tree / "packages/proot/z8-apk-loader.patch").write_text(
        '--- a/src/execve/enter.c\n+++ b/src/execve/enter.c\n'
        '@@ -571,1 +571,1 @@\n'
        '-\treturn getenv("PROOT_LOADER") ?: PROOT_UNBUNDLE_LOADER "/loader";\n'
        f'+\treturn getenv("PROOT_LOADER") ?: "{loader}";\n')
    # NDK r30's upstream setup uses a FUSE overlay. A private copy supports
    # unprivileged Docker/QEMU backends without FUSE, mount or SYS_ADMIN access.
    replace(tree / "scripts/build/toolchain/termux_setup_toolchain_30.sh", '''\tif ! mountpoint -q "${TERMUX_STANDALONE_TOOLCHAIN}"; then
\t\tfuse-overlayfs \\
\t\t\t"${TERMUX_STANDALONE_TOOLCHAIN}" \\
\t\t\t-o lowerdir="${NDK}/toolchains/llvm/prebuilt/linux-x86_64" \\
\t\t\t-o upperdir="${TERMUX_STANDALONE_TOOLCHAIN}-upper" \\
\t\t\t-o workdir="${TERMUX_STANDALONE_TOOLCHAIN}-work"
\tfi''', '''\tif [ ! -f "${TERMUX_STANDALONE_TOOLCHAIN}/.z8-ndk-copy-complete" ]; then
        cp -a --reflink=auto "${NDK}/toolchains/llvm/prebuilt/linux-x86_64/." "${TERMUX_STANDALONE_TOOLCHAIN}/"
        touch "${TERMUX_STANDALONE_TOOLCHAIN}/.z8-ndk-copy-complete"
    fi''')
    # Keep TERMUX_REPO_* identifying com.termux so upstream mismatch protections
    # remain active; additionally fail closed before even fetching apt metadata.
    for name, function in (("termux_download_deb_pac.sh", "termux_download_deb_pac"),
                           ("termux_get_repo_files.sh", "termux_get_repo_files")):
        replace(tree / "scripts/build" / name, function + "() {", function + '''() {
    echo "z8: stock-prefix repository access is disabled; build dependencies from source" >&2
    return 1
''')
    apt = tree / "packages/apt/build.sh"
    start = '\t{\n\t\techo "# The main termux repository, with cloudflare cache"'
    text = apt.read_text()
    if text.count(start) != 1:
        raise RuntimeError("apt sources.list patch anchor changed")
    a = text.index(start)
    b = text.index('\n\n\t# apt-transport-tor', a)
    apt.write_text(text[:a] + '''\tprintf '%s\\n' '# z8: no compatible host package repository configured.' > "$TERMUX_PREFIX/etc/apt/sources.list"''' + text[b:])
    # `pkg` upstream selects public mirrors automatically. Restrict the generated
    # z8 package to apt's explicit sources until our own signed repository exists.
    tools = tree / "packages/termux-tools/build.sh"
    replace(tools, '\tTERMUX_PKG_CONFFILES="$(cat "$TERMUX_PKG_BUILDDIR/conffiles")"', '''\tTERMUX_PKG_CONFFILES="$(cat "$TERMUX_PKG_BUILDDIR/conffiles")"
    cat > "$TERMUX_PREFIX/bin/pkg" <<EOF
#!$TERMUX_PREFIX/bin/bash
exec "$TERMUX_PREFIX/bin/apt" "\\$@"
EOF
    cat > "$TERMUX_PREFIX/bin/termux-change-repo" <<EOF
#!$TERMUX_PREFIX/bin/bash
echo 'z8 requires its own package repository; official Termux mirrors are incompatible.' >&2
exit 1
EOF
    chmod 700 "$TERMUX_PREFIX/bin/pkg" "$TERMUX_PREFIX/bin/termux-change-repo"''')
    script = tree / "scripts/build-bootstraps.sh"
    replace(script, 'echo "$(readlink "$link")←${link}" >> SYMLINKS.txt',
            'echo "$(readlink "$link")←${link#./}" >> SYMLINKS.txt')
    replace(script, 'add_termux_bootstrap_second_stage_files "$package_arch"',
            'add_termux_bootstrap_second_stage_files "$TERMUX_ARCH"')
    if profile == "core":
        # Bash does not link termux-tools. Its supplied profile uses bash builtins
        # and guards optional files. z8 manages shell setup itself in the core
        # stage; retain all actual linked dependencies and omit this convenience
        # dependency only. The full workspace recipe retains upstream metadata.
        replace(tree / "packages/bash/build.sh",
                'TERMUX_PKG_DEPENDS="libandroid-support, libiconv, readline (>= 8.3), termux-tools"',
                'TERMUX_PKG_DEPENDS="libandroid-support, libiconv, readline (>= 8.3)"')
        packages = " ".join(builder["profiles"]["core"])
        if not re.fullmatch(r"[a-z0-9+ -]+", packages):
            raise RuntimeError("Invalid package names")
        replace(script, '\t\t# Build packages.\n',
                f'\t\t# z8 core stage: no host apt or Python until the workspace stage.\n\t\tPACKAGES=({packages})\n\n\t\t# Build packages.\n')
        replace(script, '\t\tadd_termux_bootstrap_second_stage_files "$TERMUX_ARCH"',
                '\t\t# z8 core has no dpkg; no package-manager second-stage is installed.')


def source_fingerprint(root, lock, builder, profile):
    h = hashlib.sha256(json.dumps([lock, builder, profile], sort_keys=True).encode())
    for relative in ("tools/prepare-runtime.py", "runtime/container-build.sh"):
        h.update((root / relative).read_bytes())
    return h.hexdigest()


def prepare(root, lock, builder, source, names, profile):
    key = source_fingerprint(root, lock, builder, profile)
    local = root / ".local"
    if local.is_symlink() or (local.exists() and not local.is_dir()):
        raise RuntimeError(".local must be a regular project directory")
    base = local / "runtime" / key[:20]
    if base.resolve().is_relative_to(root.resolve()) is False:
        raise RuntimeError("Runtime output escapes the project")
    base.mkdir(parents=True, exist_ok=True)
    tree = base / "termux-packages"
    metadata = base / "prepared.json"
    if tree.exists():
        if tree.is_symlink() or not metadata.is_file():
            raise RuntimeError("Existing runtime tree lacks provenance")
        data = json.loads(metadata.read_text())
        if data.get("fingerprint") != key:
            raise RuntimeError("Prepared source provenance mismatch")
        for name, expected in data["overlayHashes"].items():
            if digest(tree / name) != expected:
                raise RuntimeError(f"Prepared source changed: {name}; use a fresh recipe fingerprint")
        return base, tree, key
    staging = Path(tempfile.mkdtemp(prefix="prepare-", dir=base))
    try:
        copy_sources(source, staging, names)
        apply_overlay(staging, lock, builder, profile)
        shutil.copy2(root / "runtime/container-build.sh", staging / "z8-container-build.sh")
        changed = ["scripts/properties.sh", "scripts/build/termux_download_deb_pac.sh",
                   "scripts/build/toolchain/termux_setup_toolchain_30.sh",
                   "packages/bash/build.sh", "packages/proot/z8-apk-loader.patch",
                   "scripts/build/termux_get_repo_files.sh", "packages/apt/build.sh",
                   "packages/termux-tools/build.sh", "scripts/build-bootstraps.sh", "z8-container-build.sh"]
        hashes = {name: digest(staging / name) for name in changed}
        staging.rename(tree)
        metadata.write_text(json.dumps({"fingerprint": key, "profile": profile,
                                       "overlayHashes": hashes}, indent=2) + "\n")
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return base, tree, key


def seed_runtime(root, manifest, tree, lock, builder, profile):
    """Reuse only hash-verified own-prefix packages from an equivalent source recipe."""
    data = json.loads(manifest.read_text())
    previous = json.loads((manifest.parent / "provenance.json").read_text())
    archive = manifest.parent / data["archive"]
    if (profile != "core" or previous.get("profile") != profile or previous.get("sourceLock") != lock
            or previous.get("builder") != builder or digest(archive) != data["sha256"]
            or previous.get("archiveSha256") != data["sha256"]):
        raise RuntimeError("Dependency seed must be a verified core runtime from the identical sources and builder")
    old_key = previous.get("recipeFingerprint", "")
    if not re.fullmatch(r"[a-f0-9]{64}", old_key):
        raise RuntimeError("Dependency seed has no valid recipe fingerprint")
    old_tree = root / ".local/runtime" / old_key[:20] / "termux-packages"
    for name, expected in previous["sourceOverlaySha256"].items():
        # Container orchestration may gain validated seed handling. All package
        # recipes and source patches for dependencies must remain byte-identical.
        if name == "z8-container-build.sh":
            continue
        if digest(old_tree / name) != expected or digest(tree / name) != expected:
            raise RuntimeError(f"Dependency recipe differs from the published runtime: {name}")
    packages = []
    output = tree / "output"
    output.mkdir(exist_ok=True)
    for record in previous["packages"]:
        name = record["archive"]
        if not re.fullmatch(r"[a-z0-9.+_~%:-]+\.deb", name):
            raise RuntimeError("Unsafe dependency seed package name")
        if name.startswith("proot_"):
            continue  # This is the only changed native package; always compile it.
        original = old_tree / "output" / name
        if original.is_symlink() or digest(original) != record["sha256"]:
            raise RuntimeError(f"Dependency seed package checksum mismatch: {name}")
        target = output / name
        if target.exists() and digest(target) != record["sha256"]:
            raise RuntimeError(f"Existing output differs from dependency seed: {name}")
        if not target.exists(): shutil.copy2(original, target)
        packages.append(record)
    if not packages:
        raise RuntimeError("Dependency seed has no verified packages")
    receipt = {"schemaVersion": 1, "sourceRuntimeSha256": data["sha256"],
               "sourceRecipeFingerprint": old_key, "packages": packages,
               "rebuiltPackages": ["proot"]}
    (tree / "z8-dependency-seed.json").write_text(json.dumps(receipt, indent=2) + "\n")


def elf_dependencies(blob):
    """Read ELF64 little-endian dynamic dependencies without executing binaries."""
    if not blob.startswith(b"\x7fELF"):
        return [], None
    if len(blob) < 64 or blob[4:6] != b"\x02\x01":
        raise RuntimeError("Expected ELF64 little-endian program")
    phoff = struct.unpack_from("<Q", blob, 32)[0]
    phsize, phcount = struct.unpack_from("<HH", blob, 54)
    loads, dynamic, interpreter = [], None, None
    if phcount and (phsize < 56 or phoff + phsize * phcount > len(blob)):
        raise RuntimeError("Truncated ELF program table")
    for i in range(phcount):
        kind, flags, offset, vaddr, _, size, _, alignment = struct.unpack_from("<IIQQQQQQ", blob, phoff + i * phsize)
        if offset + size > len(blob):
            raise RuntimeError("Truncated ELF segment")
        if kind == 1:
            loads.append((vaddr, offset, size))
        elif kind == 2:
            dynamic = blob[offset:offset + size]
        elif kind == 3:
            interpreter = blob[offset:offset + size].rstrip(b"\0").decode("ascii")
    if dynamic is None:
        return [], interpreter
    needed, straddr = [], None
    for offset in range(0, len(dynamic) - 15, 16):
        tag, value = struct.unpack_from("<qQ", dynamic, offset)
        if tag == 0:
            break
        if tag == 1:
            needed.append(value)
        if tag == 5:
            straddr = value
    if not needed:
        return [], interpreter
    tables = [offset + straddr - address for address, offset, size in loads
              if straddr is not None and address <= straddr < address + size]
    if len(tables) != 1:
        raise RuntimeError("ELF dynamic string table cannot be mapped")
    names = []
    for index in needed:
        start = tables[0] + index
        end = blob.find(b"\0", start)
        if start >= len(blob) or end < 0:
            raise RuntimeError("Invalid ELF library name")
        names.append(blob[start:end].decode("ascii"))
    return names, interpreter


def verify_host_linkage(bundle):
    # Android public bionic/NDK libraries provided by the OS; all other SONAMEs
    # must be in this own-prefix archive, including libandroid-support/libc++.
    system = {"libc.so", "libdl.so", "libm.so", "liblog.so", "libandroid.so", "libz.so", "libstdc++.so"}
    available = {PurePosixPath(name).name for name in bundle.namelist() if name.startswith("lib/")}
    for line in bundle.read("SYMLINKS.txt").decode().splitlines():
        destination = line.split("←", 1)[1]
        if destination.startswith("lib/"):
            available.add(PurePosixPath(destination).name)
    count, load_count = 0, 0
    for info in bundle.infolist():
        if info.is_dir():
            continue
        with bundle.open(info) as stream:
            head = stream.read(4)
        if head != b"\x7fELF":
            continue
        count += 1
        data = bundle.read(info)
        needed, interpreter = elf_dependencies(data)
        phoff = struct.unpack_from("<Q", data, 32)[0]
        phsize, phcount = struct.unpack_from("<HH", data, 54)
        for i in range(phcount):
            kind, _, offset, address, _, _, _, alignment = struct.unpack_from("<IIQQQQQQ", data, phoff + i * phsize)
            if kind == 1:
                load_count += 1
                if alignment < 16384 or (offset - address) % 16384:
                    raise RuntimeError(f"ELF PT_LOAD is not 16 KiB page compatible: {info.filename}")
        if interpreter not in (None, "/system/bin/linker64"):
            raise RuntimeError(f"Non-Android ELF interpreter in {info.filename}: {interpreter}")
        missing = set(needed) - available - system
        if missing:
            raise RuntimeError(f"Missing runtime libraries in {info.filename}: {', '.join(sorted(missing))}")
    return {"elfFilesChecked": count, "missingSonames": [], "systemSonames": sorted(system),
            "pageAlignment": {"requiredPageBytes": 16384, "loadSegmentsChecked": load_count,
                              "incompatibleSegments": [], "deviceExecution": "NOT_TESTED"}}


def normalize_comment_examples(bundle, prefix):
    replacements, records = {}, []
    for name, (expected, line_numbers, comment_prefix) in COMMENT_PREFIX_EXAMPLES.items():
        if name not in bundle.namelist():
            continue
        if bundle.getinfo(name).file_size > 1024 * 1024:
            raise RuntimeError(f"Unexpected comment example file size: {name}")
        before = bundle.read(name)
        if b"/data/data/com.termux/files/usr" not in before:
            continue
        if hashlib.sha256(before).hexdigest() != expected:
            raise RuntimeError(f"Unrecognized upstream comment example file: {name}")
        lines = before.decode("utf-8").splitlines(keepends=True)
        actual = [i for i, line in enumerate(lines, 1) if "/data/data/com.termux/files/usr" in line]
        if actual != line_numbers or any(not lines[i - 1].lstrip().startswith(comment_prefix) for i in actual):
            raise RuntimeError(f"Stock-prefix occurrence is outside verified comment lines: {name}")
        for i in actual:
            lines[i - 1] = lines[i - 1].replace("/data/data/com.termux/files/usr", prefix)
        after = "".join(lines).encode("utf-8")
        replacements[name] = after
        records.append({"file": name, "lines": actual, "beforeSha256": expected,
                        "afterSha256": hashlib.sha256(after).hexdigest(),
                        "reason": "Normalize verified upstream documentation comments to the z8 prefix; no executable statement changed"})
    return replacements, records


def normalize_package_metadata(bundle, prefix, replacements, excluded):
    """Keep exact affected dpkg entries consistent with the packaged file bytes."""
    updates = {}
    for name in replacements:
        updates.setdefault("termux-exec", []).append(name)
    for name in excluded:
        package = "proot" if name == "libexec/proot/loader32" else name.split("/")[2]
        if package not in ("proot", "termux-core", "termux-exec"):
            raise RuntimeError(f"Unrecognized excluded package file: {name}")
        updates.setdefault(package, []).append(name)
    records, metadata_replacements = [], {}
    for package, paths in updates.items():
        for suffix in ("md5sums", "list"):
            name = f"var/lib/dpkg/info/{package}.{suffix}"
            affected = paths if suffix == "md5sums" else [path for path in paths if path in excluded]
            if name not in bundle.namelist() or not affected:
                continue
            if bundle.getinfo(name).file_size > 2 * 1024 * 1024:
                raise RuntimeError(f"Unexpected package metadata size: {name}")
            before = bundle.read(name)
            lines = before.decode("utf-8").splitlines(keepends=True)
            changes = {}
            for path in affected:
                full_path = prefix + "/" + path
                if suffix == "list":
                    expected = full_path + "\n"
                    replacement = ""
                else:
                    expected = hashlib.md5(bundle.read(path)).hexdigest() + "  " + full_path.lstrip("/") + "\n"
                    replacement = "" if path in excluded else (
                        hashlib.md5(replacements[path]).hexdigest() + "  " + full_path.lstrip("/") + "\n")
                indices = [i for i, line in enumerate(lines) if line == expected]
                if len(indices) != 1:
                    raise RuntimeError(f"Expected one exact package metadata entry: {name}: {path}")
                changes[indices[0]] = replacement
            after = "".join(changes.get(i, line) for i, line in enumerate(lines)).encode("utf-8")
            metadata_replacements[name] = after
            records.append({"file": name, "lines": sorted(i + 1 for i in changes),
                            "beforeSha256": hashlib.sha256(before).hexdigest(),
                            "afterSha256": hashlib.sha256(after).hexdigest(),
                            "reason": "Keep package file lists and checksums consistent with explicit packaging changes"})
    replacements.update(metadata_replacements)
    return records


def publish(root, base, tree, lock, builder, profile, key, command):
    raw_archive = tree / "bootstrap-aarch64.zip"
    if raw_archive.is_symlink() or not raw_archive.is_file():
        raise RuntimeError("Source builder did not emit a regular bootstrap archive")
    if raw_archive.stat().st_size > 512 * 1024 * 1024:
        raise RuntimeError("Raw bootstrap exceeds the app archive limit")
    archive = raw_archive
    excluded, exclusion_records = [], []
    # ARM64 PRoot also builds an optional ARM32 guest loader. z8's current
    # runtime and guest contract are ARM64 only. Retain the raw build artifact,
    # omit only that exact known helper. Normalize only pinned textual comments;
    # all other retained bytes remain identical to the raw build output.
    with zipfile.ZipFile(raw_archive) as bundle:
        infos = bundle.infolist()
        if len(infos) > 100000 or sum(info.file_size for info in infos) > 2 * 1024**3:
            raise RuntimeError("Raw bootstrap exceeds the app expanded-size limits")
        name = "libexec/proot/loader32"
        if name in bundle.namelist():
            if bundle.getinfo(name).file_size > 4 * 1024 * 1024:
                raise RuntimeError("Optional PRoot loader32 has an unexpected size")
            helper = bundle.read(name)
            if (len(helper) < 20 or helper[:6] != b"\x7fELF\x01\x01"
                    or int.from_bytes(helper[18:20], "little") != 40):
                raise RuntimeError("Unexpected ABI/content in optional PRoot loader32")
            excluded = [name]
            exclusion_records.append({"file": name, "sha256": hashlib.sha256(helper).hexdigest(),
                                      "reason": "Optional ARM32 guest loader; this runtime supports ARM64 guests"})
        if profile == "core":
            for name in OPTIONAL_SANITIZER_TESTS:
                if name not in bundle.namelist():
                    continue
                if bundle.getinfo(name).file_size > 4 * 1024 * 1024:
                    raise RuntimeError(f"Unexpected sanitizer fixture size: {name}")
                fixture = bundle.read(name)
                if (len(fixture) < 64 or fixture[:6] != b"\x7fELF\x02\x01"
                        or int.from_bytes(fixture[18:20], "little") != 183
                        or "libclang_rt.asan-aarch64-android.so" not in elf_dependencies(fixture)[0]):
                    raise RuntimeError(f"Unrecognized optional sanitizer test fixture: {name}")
                excluded.append(name)
                exclusion_records.append({"file": name, "sha256": hashlib.sha256(fixture).hexdigest(),
                                          "reason": "Optional installed sanitizer test; ASan runtime is not included in the core profile"})
        replacements, comment_records = normalize_comment_examples(bundle, lock["prefix"])
        metadata_records = normalize_package_metadata(bundle, lock["prefix"], replacements, excluded)
        if excluded or replacements:
            archive = base / "bootstrap-z8-aarch64.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
                for info in infos:
                    if info.filename not in excluded:
                        if info.filename in replacements:
                            output.writestr(info, replacements[info.filename])
                        else:
                            with bundle.open(info) as source, output.open(info, "w") as target:
                                shutil.copyfileobj(source, target)
    spec = importlib.util.spec_from_file_location("z8_prepare_app", root / "tools/prepare-app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_bootstrap_zip(archive, lock["prefix"])
    with zipfile.ZipFile(archive) as bundle:
        linkage = verify_host_linkage(bundle)
        for name in ("bin/tmux", "bin/proot", "libexec/proot/loader"):
            if name not in bundle.namelist():
                raise RuntimeError(f"Bootstrap missing expected executable: {name}")
        loader_path = str(PurePosixPath(lock["prefix"]).parent / "applib/libproot-loader.so")
        if (loader_path.encode() + b"\0") not in bundle.read("bin/proot"):
            raise RuntimeError("PRoot does not use the APK-installed guest loader")
        loader_sha = hashlib.sha256(bundle.read("libexec/proot/loader")).hexdigest()
        for name in bundle.namelist():
            if name == "etc/apt/sources.list" or (name.startswith("etc/apt/sources.list.d/") and not name.endswith("/")):
                lines = bundle.read(name).decode().splitlines()
                if any(line.strip() and not line.lstrip().startswith("#") for line in lines):
                    raise RuntimeError("Bootstrap must not enable an unverified package repository")
    sha = digest(archive)
    artifacts = root / "artifacts/runtime"
    artifacts.mkdir(parents=True, exist_ok=True)
    output = artifacts / f"{profile}-{sha[:16]}"
    if output.exists():
        module.verify_runtime(output / "manifest.json", lock)
        return output / "manifest.json"
    staging = Path(tempfile.mkdtemp(prefix="publish-", dir=artifacts))
    try:
        shutil.copy2(archive, staging / "bootstrap-aarch64.zip")
        manifest = {"schemaVersion": 1, "applicationId": lock["applicationId"], "prefix": lock["prefix"],
                    "architecture": "aarch64", "archive": "bootstrap-aarch64.zip", "sha256": sha,
                    "termuxPackagesCommit": lock["termuxPackages"]["commit"]}
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        module.verify_runtime(staging / "manifest.json", lock)
        provenance = {"schemaVersion": 1, "profile": profile, "recipeFingerprint": key,
                      "builder": builder, "sourceLock": lock, "command": command,
                      "builtAtUtc": datetime.now(timezone.utc).isoformat(), "archiveSha256": sha,
                      "deviceExecution": "NOT_TESTED", "bitReproducibility": "NOT_MEASURED",
                      "linkage": linkage,
                      "androidExecution": {"hostEntrypoint": "/system/bin/linker64",
                                           "guestLoader": loader_path,
                                           "apkLibraryName": "libproot-loader.so",
                                           "guestLoaderSha256": loader_sha},
                      "rawArchiveSha256": digest(raw_archive), "excludedOptionalFiles": excluded,
                      "excludedOptionalFileDetails": exclusion_records,
                      "normalizedCommentExamples": comment_records,
                      "normalizedPackageMetadata": metadata_records,
                      "supportedGuestArchitectures": ["aarch64"],
                      "packagingScriptSha256": digest(root / "tools/prepare-runtime.py"),
                      "packages": [{"archive": p.name, "sha256": digest(p)} for p in sorted((tree / "output").glob("*.deb"))]}
        prepared = base / "prepared.json"
        if prepared.is_file():
            provenance["sourceOverlaySha256"] = json.loads(prepared.read_text())["overlayHashes"]
        if (tree / "z8-dependency-seed.json").is_file():
            provenance["verifiedDependencySeed"] = json.loads((tree / "z8-dependency-seed.json").read_text())
        (staging / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return output / "manifest.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--preflight", action="store_true", help="Check source and Docker without downloads (default)")
    modes.add_argument("--prepare", action="store_true", help="Prepare isolated source overlay without Docker/downloads")
    modes.add_argument("--build", action="store_true", help="Pull locked builder, build packages, validate and publish")
    modes.add_argument("--finalize-source", type=Path,
                       help="Validate/publish an already completed generated build without rerunning compilation")
    parser.add_argument("--profile", choices=("core", "workspace"), default="workspace")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--seed-runtime", type=Path,
                        help="Reuse exact verified core dependencies; always compile changed PRoot from source")
    args = parser.parse_args()
    try:
        if not 1 <= args.jobs <= 64:
            raise RuntimeError("Build jobs must be 1 through 64")
        if args.seed_runtime and not args.build:
            raise RuntimeError("--seed-runtime requires --build")
        lock, builder, source, names, epoch = validate_inputs(ROOT)
        print(f'z8 runtime: {lock["prefix"]}; aarch64; profile={args.profile}', flush=True)
        print(f'Builder: {builder["image"]} ({builder["platform"]})', flush=True)
        if args.finalize_source:
            tree = args.finalize_source.resolve()
            base = tree.parent
            if tree.name != "termux-packages" or base.parent != (ROOT / ".local/runtime").resolve():
                raise RuntimeError("Finalize source must be a generated .local/runtime tree")
            metadata = json.loads((base / "prepared.json").read_text())
            key, profile = metadata["fingerprint"], metadata["profile"]
            if not re.fullmatch(r"[a-f0-9]{64}", key) or base.name != key[:20] or profile not in builder["profiles"]:
                raise RuntimeError("Invalid generated-tree provenance")
            for name, expected in metadata["overlayHashes"].items():
                if digest(tree / name) != expected:
                    raise RuntimeError(f"Generated source changed: {name}")
            command = json.loads((base / "command.json").read_text())
            if builder["image"] not in command:
                raise RuntimeError("Generated build command does not use the pinned builder")
            manifest = publish(ROOT, base, tree, lock, builder, profile, key, command)
            print(f"Validated runtime manifest: {manifest}")
            print("Finalization validates a completed artifact; it does not run compilation or prove Android execution.")
            return
        if args.prepare:
            base, tree, key = prepare(ROOT, lock, builder, source, names, args.profile)
            print(f"Prepared source: {tree}")
            return
        docker = os.environ.get("Z8_DOCKER") or shutil.which("docker")
        if not docker:
            raise RuntimeError("Linux Docker backend unavailable; set Z8_DOCKER to an executable wrapper")
        info = json.loads(run([docker, "info", "--format", "{{json .}}"], capture=True))
        if info.get("OSType") != "linux":
            raise RuntimeError("Docker daemon must run Linux containers")
        if not args.build:
            print("Source/backend preflight passed. Builder image/toolchain and runtime execution remain unverified.")
            return
        base, tree, key = prepare(ROOT, lock, builder, source, names, args.profile)
        if args.seed_runtime:
            seed_runtime(ROOT, args.seed_runtime.resolve(), tree, lock, builder, args.profile)
        run([docker, "pull", "--platform", builder["platform"], builder["image"]])
        image = json.loads(run([docker, "image", "inspect", builder["image"]], capture=True))[0]
        # Docker's classic image store reports the config digest as Id; its
        # containerd store reports the manifest digest. Require the immutable
        # repository digest in both cases, not one store's Id convention.
        if (image.get("Architecture") != "amd64" or image.get("Os") != "linux"
                or image.get("Id") not in (builder["configDigest"], builder["image"].split("@", 1)[1])
                or builder["image"] not in image.get("RepoDigests", [])):
            raise RuntimeError("Pulled builder architecture/repository digest mismatch")
        volume = "z8-runtime-" + key[:20]
        command = [docker, "run", "--rm", "--init", "--user", "0", "--platform", builder["platform"],
                   "--name", volume, "--mount", f"type=bind,source={tree},target=/home/builder/termux-packages",
                   "--mount", f"type=volume,source={volume}-data,target=/data",
                   "--mount", f"type=volume,source={volume}-cache,target=/home/builder/.termux-build",
                   "--env", f"Z8_BUILD_JOBS={args.jobs}", "--env", f"Z8_SOURCE_DATE_EPOCH={epoch}",
                   builder["image"], "bash", "z8-container-build.sh", args.profile]
        (base / "command.json").write_text(json.dumps(command, indent=2) + "\n")
        print(f"Build source: {tree}", flush=True)
        run(command)
        manifest = publish(ROOT, base, tree, lock, builder, args.profile, key, command)
        print(f"Validated runtime manifest: {manifest}")
        print("Android execution is NOT_TESTED until the runtime APK is installed and exercised.")
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"build-runtime: {exc}\n")


if __name__ == "__main__":
    main()
