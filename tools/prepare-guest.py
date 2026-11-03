#!/usr/bin/env python3
"""Verify and normalize a pinned Ubuntu Base guest; default is a read-only plan.

No package install or guest code is executed. Rootfs ZIPs contain ordinary files
and directories plus a deferred SYMLINKS.txt; Android must install into a new,
private staging directory and publish only after complete validation.
"""
import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "runtime/guest/image.lock.json"
MAX_ARCHIVE = 128 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024
MAX_ENTRIES = 30_000
NORMALIZATION_VERSION = 1

# Retained inputs can replace only these Z8-owned sources, never Ubuntu files.
HISTORICAL_MANAGED_FILES = frozenset((
    "etc/profile.d/z8.sh", "etc/z8/guest-target", "etc/z8/shellrc", "etc/z8/welcome.sh",
    *("opt/z8/hooks/" + name for name in ("claude.hooks.json", "codex.hooks.json", "enable.py", "z8_event.py")),
    *("usr/local/lib/z8/" + name for name in ("ai-tools.lock.json", "debian-base-packages.txt", "guest-task.sh",
        "install-ai.sh", "install-node.py", "node.lock.json", "probe-tools.sh", "provision.sh", "setup-tools.sh", "shellrc", "welcome.sh")),
))
HISTORICAL_LATER_ADDITIONS = frozenset((
    "etc/profile.d/z8-browser.sh", "etc/profile.d/z8-cli.sh", "usr/local/lib/z8/browser-open.py",
    "usr/local/lib/z8/html-preview.py", "usr/local/lib/z8/browser/bin/xdg-open",
    "usr/local/lib/z8/browser/bin/", "usr/local/lib/z8/browser/",
))

# Exact block from the hash-pinned Ubuntu Base /etc/bash.bashrc. Keep the
# upstream non-root behavior and fail closed if Ubuntu changes this block.
UBUNTU_SUDO_HINT = (
    b'# sudo hint\n'
    b'if [ ! -e "$HOME/.sudo_as_admin_successful" ] && [ ! -e "$HOME/.hushlogin" ] ; then\n'
    b'    case " $(groups) " in *\\ admin\\ *|*\\ sudo\\ *)\n'
    b'    if [ -x /usr/bin/sudo ]; then\n'
    b'\tcat <<-EOF\n'
    b'\tTo run a command as administrator (user "root"), use "sudo <command>".\n'
    b'\tSee "man sudo_root" for details.\n'
    b'\t\n'
    b'\tEOF\n'
    b'    fi\n'
    b'    esac\n'
    b'fi\n'
)


def normalize_ubuntu_sudo_hint(data):
    """Skip an irrelevant sudo hint for guest root without probing Android gids."""
    # Tiny fixture images and other minimal bashrc files need no such patch.
    if b"# sudo hint\n" not in data:
        return data
    if data.count(b"# sudo hint\n") != 1 or data.count(UBUNTU_SUDO_HINT) != 1:
        raise GuestError("Pinned Ubuntu sudo hint block changed; review guest normalization")
    guarded = UBUNTU_SUDO_HINT.replace(b"if [ ! -e", b'if [ "$EUID" -ne 0 ] && [ ! -e', 1)
    return data.replace(UBUNTU_SUDO_HINT, guarded, 1)


class GuestError(ValueError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _historical_regular_file(path, maximum):
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise GuestError("Historical input path contains a symlink")
    if not path.is_file() or not 0 < path.stat().st_size <= maximum:
        raise GuestError("Missing or oversized historical source input")
    return path


def _historical_unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GuestError("Duplicate historical manifest key")
        result[key] = value
    return result


def read_historical_managed_inputs(path, lock):
    """Read retained source as data; no captured script is executed."""
    path = _historical_regular_file(path, 256 * 1024)
    data = json.loads(path.read_text(), object_pairs_hook=_historical_unique_object)
    if not isinstance(data, dict) or type(data.get("schemaVersion")) is not int or data["schemaVersion"] != 1 or data.get("kind") != "z8-historical-guest-managed-source":
        raise GuestError("Unsupported historical managed-input manifest")
    for key in ("guestArchiveSha256", "guestManifestSha256", "referenceCurrentSourceInputSha256"):
        if not isinstance(data.get(key), str) or not re.fullmatch(r"[a-f0-9]{64}", data[key]):
            raise GuestError("Historical input digest is not a full SHA-256")
    if data.get("guestSource") != lock["source"]:
        raise GuestError("Historical inputs do not match the pinned Ubuntu source")
    records = data.get("files")
    absent = data.get("absentFromHistoricalGuest")
    if (not isinstance(records, list) or len(records) != len(HISTORICAL_MANAGED_FILES)
            or not isinstance(absent, list) or any(not isinstance(name, str) for name in absent)
            or len(absent) != len(HISTORICAL_LATER_ADDITIONS) or set(absent) != HISTORICAL_LATER_ADDITIONS):
        raise GuestError("Historical input path set is incomplete or outside the fixed scope")
    entries = {}
    for record in records:
        if not isinstance(record, dict):
            raise GuestError("Invalid historical source record")
        name = record.get("guestPath")
        if not isinstance(name, str) or name not in HISTORICAL_MANAGED_FILES or name in entries or record.get("path") != "files/" + name:
            raise GuestError("Historical source path is duplicated or outside the fixed scope")
        if (type(record.get("guestMode")) is not int or record["guestMode"] != 0o644
                or type(record.get("bytes")) is not int or not 0 < record["bytes"] <= 1024 * 1024
                or not isinstance(record.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", record["sha256"])):
            raise GuestError("Invalid historical source size, mode or digest")
        source = _historical_regular_file(path.parent / record["path"], 1024 * 1024)
        content = source.read_bytes()
        if len(content) != record["bytes"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
            raise GuestError("Historical source bytes do not match the manifest")
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise GuestError("Historical managed source is not UTF-8 text") from error
        entries[name] = {"type": "file", "mode": record["guestMode"], "data": content}
    return {"manifest": data, "manifestSha256": sha256(path), "entries": entries}


def apply_historical_managed_inputs(files, historical):
    """Replace captured managed files and omit only the known later additions."""
    result = dict(files)
    for name in sorted(HISTORICAL_LATER_ADDITIONS, key=len, reverse=True):
        entry = result.get(name)
        expected_type = "directory" if name.endswith("/") else "file"
        if entry is None or entry["type"] != expected_type:
            raise GuestError("Current normalizer changed a historical reconstruction path")
        if name.endswith("/") and any(other != name and other.startswith(name) for other in result):
            raise GuestError("Refusing to remove a nonempty historical reconstruction directory")
        del result[name]
    for name, entry in historical["entries"].items():
        if name not in result or result[name]["type"] != "file":
            raise GuestError("Historical managed source target is not a regular file")
        result[name] = entry
    return result


def checked_name(name, directory=False):
    if not isinstance(name, str) or not name or len(name.encode()) > 4096:
        raise GuestError("Invalid guest path")
    if name.startswith("/") or "\\" in name or "←" in name or any(ord(c) < 32 for c in name):
        raise GuestError("Unsafe guest path")
    body = name[:-1] if directory and name.endswith("/") else name
    if not body or any(part in ("", ".", "..") for part in body.split("/")):
        raise GuestError("Guest path must be a normalized relative path")
    return body


def tar_name(name, directory=False):
    while name.startswith("./"):
        name = name[2:]
    if name in ("", ".") and directory:
        return None
    return checked_name(name.rstrip("/") if directory else name)


def safe_link_target(destination, target):
    if not isinstance(target, str) or not target or len(target.encode()) > 4096 or "\\" in target or "←" in target or any(ord(c) < 32 for c in target):
        raise GuestError("Unsafe guest symlink target")
    if target.startswith("/"):
        # Absolute guest links must never become absolute Android host links.
        # Ubuntu uses normalized absolute targets; reject unusual dot segments
        # rather than silently changing symlink resolution semantics.
        if any(part in (".", "..", "") for part in target[1:].split("/")):
            raise GuestError("Unnormalized absolute guest link")
        target = posixpath.relpath(target[1:], posixpath.dirname(destination) or ".")
    return target


def validate_links(links, entries):
    kinds = {name.rstrip("/"): value["type"] for name, value in entries.items()}
    if len(kinds) != len(entries):
        raise GuestError("File/directory path collision")
    for destination, target in links.items():
        checked_name(destination)
        if destination in kinds or target.startswith("/"):
            raise GuestError("Symlink collides with an entry or is absolute")
        for existing in (*kinds, *links):
            if existing.startswith(destination + "/"):
                raise GuestError("Archive entries cannot live beneath a symlink")
        # Resolve the complete link graph, including .. after other links. A
        # lexical prefix check alone is insufficient to keep host links inside.
        pending = deque(target.split("/"))
        resolved = destination.split("/")[:-1]
        expansions = 0
        while pending:
            part = pending.popleft()
            if part in ("", "."):
                continue
            if part == "..":
                if not resolved:
                    raise GuestError("Symlink escapes guest root")
                resolved.pop()
                continue
            resolved.append(part)
            other = "/".join(resolved)
            if other in links:
                expansions += 1
                if expansions > 40:
                    raise GuestError("Symlink cycle or excessive expansion")
                resolved.pop()
                pending.extendleft(reversed(links[other].split("/")))
    for name in kinds:
        for parent in PurePosixPath(name).parents:
            if str(parent) != "." and kinds.get(str(parent)) != "directory":
                raise GuestError("Missing or non-directory archive parent")


def read_lock():
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("schemaVersion") != 1 or lock.get("architecture") != "aarch64" or lock.get("distribution") != "ubuntu":
        raise GuestError("Unsupported guest lock")
    for key in ("sha256", "sha256SumsSha256"):
        if not re.fullmatch(r"[a-f0-9]{64}", lock["source"].get(key, "")):
            raise GuestError("Guest source hash must be pinned")
    for key in ("url", "sha256SumsUrl"):
        url = urllib.parse.urlparse(lock["source"][key])
        if url.scheme != "https" or url.netloc != "cdimage.ubuntu.com":
            raise GuestError("Expected an official Ubuntu HTTPS source")
    return lock


def download(url, destination, digest, maximum):
    if destination.is_symlink():
        raise GuestError("Cache path is a symlink")
    if destination.is_file():
        if destination.stat().st_size <= maximum and sha256(destination) == digest:
            return
        raise GuestError("Cached download differs from its pinned hash; preserve it for review")
    descriptor, temporary = tempfile.mkstemp(prefix=".download-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as output, urllib.request.urlopen(url, timeout=60) as response:
            redirected = urllib.parse.urlparse(response.geturl())
            if redirected.scheme != "https" or redirected.netloc != "cdimage.ubuntu.com":
                raise GuestError("Unexpected download redirect")
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum:
                    raise GuestError("Download exceeds limit")
                output.write(chunk)
        if sha256(temporary) != digest:
            raise GuestError("Downloaded hash differs from pinned source")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def normalize(source_archive):
    files, links, hardlinks = {}, {}, {}
    seen = set()
    total = 0
    with tarfile.open(source_archive, "r:gz") as archive:
        for member in archive:
            name = tar_name(member.name, member.isdir())
            if name is None:
                continue
            if name in seen or len(seen) >= MAX_ENTRIES:
                raise GuestError("Duplicate or excessive tar entries")
            seen.add(name)
            mode = member.mode & 0o777  # Never carry host setuid/setgid/sticky bits.
            if member.isdir():
                files[name + "/"] = {"type": "directory", "mode": mode, "data": b""}
            elif member.issym():
                links[name] = safe_link_target(name, member.linkname)
            elif member.islnk():
                hardlinks[name] = (tar_name(member.linkname), mode)
            elif member.isreg():
                total += member.size
                if member.size < 0 or total > MAX_EXPANDED:
                    raise GuestError("Expanded tar exceeds limit")
                stream = archive.extractfile(member)
                data = stream.read(member.size + 1)
                if len(data) != member.size:
                    raise GuestError("Truncated tar file")
                files[name] = {"type": "file", "mode": mode, "data": data}
            else:
                raise GuestError("Device nodes, FIFOs and special tar members are unsupported")
    # Materialize hard links as regular files; no Android hardlink privilege or
    # cross-directory sharing is required to install the image.
    for name, (target, mode) in hardlinks.items():
        visited = {name}
        while target in hardlinks:
            if target in visited:
                raise GuestError("Hardlink cycle")
            visited.add(target)
            target = hardlinks[target][0]
        if target not in files or files[target]["type"] != "file":
            raise GuestError("Hardlink target is not an archive regular file")
        files[name] = {"type": "file", "mode": mode, "data": files[target]["data"]}
    add_managed_files(files, links)
    validate_links(links, files)
    links_data = "".join(f"{target}←{name}\n" for name, target in sorted(links.items())).encode("utf-8")
    if "SYMLINKS.txt" in files or "SYMLINKS.txt" in links:
        raise GuestError("Reserved installer path in input")
    files["SYMLINKS.txt"] = {"type": "file", "mode": 0o600, "data": links_data}
    return files


def add_managed_files(files, links):
    for name in ("dev", "dev/pts", "dev/shm", "proc", "tmp", "run", "run/z8", "run/z8/attention", "workspace", "z8", "z8/home", "etc/z8", "etc/profile.d", "usr/local", "usr/local/lib", "usr/local/lib/z8", "usr/local/lib/z8/browser", "usr/local/lib/z8/browser/bin", "opt", "opt/z8", "opt/z8/hooks"):
        if name in links or name in files:
            raise GuestError("Required guest mount point is not a directory")
        files.setdefault(name + "/", {"type": "directory", "mode": 0o755, "data": b""})
    for device in ("null", "zero", "random", "urandom", "tty", "ptmx"):
        name = "dev/" + device
        if name in links or name + "/" in files:
            raise GuestError("Device mount point is not a regular file")
        files.setdefault(name, {"type": "file", "mode": 0o600, "data": b""})
    for name, target in {"dev/fd": "../proc/self/fd", "dev/stdin": "fd/0", "dev/stdout": "fd/1", "dev/stderr": "fd/2"}.items():
        if name in files or name + "/" in files:
            raise GuestError("Standard descriptor path already exists")
        if name in links and links[name] != target:
            raise GuestError("Unexpected standard descriptor symlink")
        links[name] = target
    profile = b'if [ "${HOME-}" = /z8/home ] && [ -r /etc/z8/shellrc ]; then\n    . /etc/z8/shellrc\nfi\n'
    bashrc = files.get("etc/bash.bashrc")
    if bashrc is not None:
        if bashrc["type"] != "file":
            raise GuestError("Ubuntu global bashrc is not a regular file")
        bashrc["data"] = normalize_ubuntu_sudo_hint(bashrc["data"])
        bashrc["data"] += b"\n# z8 interactive defaults, including nested shells.\n" + profile
    managed = {
        "etc/z8/guest-target": b"z8-guest-v1\n",
        "etc/z8/shellrc": (ROOT / "runtime/guest/shellrc").read_bytes(),
        "etc/z8/welcome.sh": (ROOT / "runtime/guest/welcome.sh").read_bytes(),
        "etc/profile.d/z8.sh": profile,
        "etc/profile.d/z8-browser.sh": (ROOT / "runtime/guest/browser-profile.sh").read_bytes(),
        "etc/profile.d/z8-cli.sh": (ROOT / "runtime/guest/cli-profile.sh").read_bytes(),
    }
    for name in ("provision.sh", "debian-base-packages.txt", "shellrc", "welcome.sh", "setup-tools.sh",
                 "guest-task.sh", "install-ai.sh", "ai-tools.lock.json", "install-node.py", "node.lock.json", "probe-tools.sh", "browser-open.py", "html-preview.py"):
        managed["usr/local/lib/z8/" + name] = (ROOT / "runtime/guest" / name).read_bytes()
    managed["usr/local/lib/z8/browser/bin/xdg-open"] = (ROOT / "runtime/guest/xdg-open").read_bytes()
    for name in ("z8_event.py", "claude.hooks.json", "codex.hooks.json", "enable.py"):
        managed["opt/z8/hooks/" + name] = (ROOT / "runtime/hooks" / name).read_bytes()
    for name, data in managed.items():
        if name in files or name in links:
            raise GuestError("Managed z8 path already exists in upstream image")
        files[name] = {"type": "file", "mode": 0o755 if name.endswith("/browser/bin/xdg-open") else 0o644, "data": data}


def verify_manifest(manifest_path):
    """Read-only artifact validation for APK embedding; returns (archive Path, data)."""
    path = Path(manifest_path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise GuestError("Invalid guest manifest")
    manifest = json.loads(path.read_text())
    lock = read_lock()
    for key, value in (("schemaVersion", 1), ("type", "z8-guest-rootfs"), ("normalizationVersion", NORMALIZATION_VERSION), ("archive", "rootfs.zip")):
        if type(manifest.get(key)) is not type(value) or manifest.get(key) != value:
            raise GuestError("Unsupported guest manifest field: " + key)
    for key in ("distribution", "release", "architecture", "source"):
        if manifest.get(key) != lock[key]:
            raise GuestError("Guest manifest does not match pinned image: " + key)
    archive_path = path.parent / "rootfs.zip"
    if archive_path.is_symlink() or not archive_path.is_file():
        raise GuestError("Missing guest ZIP")
    if type(manifest.get("archiveBytes")) is not int or not 0 < manifest["archiveBytes"] <= MAX_ARCHIVE or archive_path.stat().st_size != manifest["archiveBytes"] or sha256(archive_path) != manifest.get("archiveSha256"):
        raise GuestError("Guest ZIP size/hash mismatch")
    if type(manifest.get("entryCount")) is not int or not 0 < manifest["entryCount"] <= MAX_ENTRIES:
        raise GuestError("Invalid guest entry count")
    if type(manifest.get("totalUncompressedBytes")) is not int or not 0 < manifest["totalUncompressedBytes"] <= MAX_EXPANDED:
        raise GuestError("Invalid guest expanded size")
    records = manifest.get("files")
    if not isinstance(records, list) or len(records) != manifest["entryCount"]:
        raise GuestError("Guest entry table mismatch")
    entries = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {"path", "type", "size", "mode"}:
            raise GuestError("Invalid guest file record")
        kind = record["type"]
        if kind not in ("file", "directory"):
            raise GuestError("Invalid guest file kind")
        name = record["path"]
        checked_name(name, kind == "directory")
        if name in entries or (kind == "directory") != name.endswith("/"):
            raise GuestError("Duplicate or malformed guest file record")
        if type(record["mode"]) is not int or not 0 <= record["mode"] <= 0o777 or type(record["size"]) is not int or record["size"] < 0 or (kind == "directory" and record["size"] != 0):
            raise GuestError("Invalid guest size/mode")
        entries[name] = record
    if sum(record["size"] for record in records) != manifest["totalUncompressedBytes"]:
        raise GuestError("Expanded size table mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) != manifest["entryCount"] or len({entry.filename for entry in infos}) != len(infos):
            raise GuestError("ZIP entry count or uniqueness mismatch")
        for info in infos:
            record = entries.get(info.filename)
            kind = stat.S_IFMT(info.external_attr >> 16)
            if record is None or info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) or info.file_size != record["size"] or kind not in (stat.S_IFREG, stat.S_IFDIR):
                raise GuestError("ZIP entry metadata mismatch")
            if info.is_dir() != (record["type"] == "directory") or (info.external_attr >> 16) & 0o777 != record["mode"]:
                raise GuestError("ZIP file mode/type mismatch")
            with archive.open(info) as stream:
                header = stream.read(20)
                if header.startswith(b"\x7fELF") and (len(header) < 20 or header[4:6] != b"\x02\x01" or int.from_bytes(header[18:20], "little") != 183):
                    raise GuestError("Guest contains a non-AArch64 ELF")
                while stream.read(1024 * 1024):
                    pass  # Force decompression/CRC validation for every file.
        if "SYMLINKS.txt" not in entries or entries["SYMLINKS.txt"]["size"] > 1024 * 1024:
            raise GuestError("Missing or oversized deferred symlinks")
        links = {}
        for line in archive.read("SYMLINKS.txt").decode("utf-8").splitlines():
            if line.count("←") != 1:
                raise GuestError("Malformed deferred symlink")
            target, destination = line.split("←")
            if destination in links or target.startswith("/") or safe_link_target(destination, target) != target:
                raise GuestError("Duplicate or unsafe deferred symlink")
            links[destination] = target
        validate_links(links, entries)
        for required in ("usr/bin/bash", "usr/bin/env", "etc/z8/guest-target", "etc/z8/shellrc", "etc/profile.d/z8.sh"):
            if required not in entries or entries[required]["type"] != "file":
                raise GuestError("Required guest file missing: " + required)
        if archive.read("etc/z8/guest-target") != b"z8-guest-v1\n":
            raise GuestError("Guest image marker mismatch")
    return archive_path.resolve(), manifest


def build(historical_managed_inputs=None):
    lock = read_lock()
    historical = read_historical_managed_inputs(historical_managed_inputs, lock) if historical_managed_inputs else None
    cache = ROOT / ".local/guest-cache"
    output_root = ROOT / "artifacts/guest" / ("ubuntu-" + lock["release"] + "-arm64")
    for directory in (ROOT / ".local", cache, ROOT / "artifacts", ROOT / "artifacts/guest", output_root):
        if directory.is_symlink():
            raise GuestError("Build directory is a symlink")
        directory.mkdir(exist_ok=True)
    sums = cache / "SHA256SUMS"
    source = cache / Path(urllib.parse.urlparse(lock["source"]["url"]).path).name
    download(lock["source"]["sha256SumsUrl"], sums, lock["source"]["sha256SumsSha256"], 64 * 1024)
    expected_line = lock["source"]["sha256"] + " *" + source.name
    if expected_line not in sums.read_text().splitlines():
        raise GuestError("Pinned checksum list does not contain expected image")
    download(lock["source"]["url"], source, lock["source"]["sha256"], MAX_ARCHIVE)
    files = normalize(source)
    if historical:
        files = apply_historical_managed_inputs(files, historical)
    with tempfile.TemporaryDirectory(prefix=".guest-", dir=output_root) as temporary:
        staging = Path(temporary)
        archive_path = staging / "rootfs.zip"
        records = []
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, entry in sorted(files.items()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = ((stat.S_IFDIR if entry["type"] == "directory" else stat.S_IFREG) | entry["mode"]) << 16
                if entry["type"] == "directory":
                    info.external_attr |= 0x10
                archive.writestr(info, entry["data"], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
                records.append({"path": name, "type": entry["type"], "mode": entry["mode"], "size": len(entry["data"])})
        if historical and sha256(archive_path) != historical["manifest"]["guestArchiveSha256"]:
            raise GuestError("Historical reconstruction differs from the exact recorded guest archive; nothing published")
        manifest = dict(lock, type="z8-guest-rootfs", normalizationVersion=NORMALIZATION_VERSION,
                        archive="rootfs.zip", archiveSha256=sha256(archive_path), archiveBytes=archive_path.stat().st_size,
                        entryCount=len(records), totalUncompressedBytes=sum(record["size"] for record in records), files=records)
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        if historical and sha256(manifest_path) != historical["manifest"]["guestManifestSha256"]:
            raise GuestError("Historical reconstruction manifest differs from the recorded guest; nothing published")
        verify_manifest(manifest_path)
        destination = output_root / manifest["archiveSha256"]
        if destination.exists():
            old_archive, old_manifest = verify_manifest(destination / "manifest.json")
            if old_manifest != manifest:
                raise GuestError("Existing artifact metadata differs")
        else:
            # Publish the fully validated archive+manifest pair together.
            os.rename(staging, destination)
        result = {"manifest": str(destination / "manifest.json"), "archiveSha256": manifest["archiveSha256"],
                "archiveBytes": manifest["archiveBytes"], "entryCount": manifest["entryCount"],
                "totalUncompressedBytes": manifest["totalUncompressedBytes"], "deviceExecution": "NOT_TESTED",
                "packagesProvisioned": False}
        if historical:
            result["historicalManagedInputsSha256"] = historical["manifestSha256"]
            result["exactHistoricalGuestReconstruction"] = True
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--build", action="store_true")
    group.add_argument("--verify", metavar="MANIFEST")
    parser.add_argument("--historical-managed-inputs", type=Path, metavar="MANIFEST",
                        help="With --build, reconstruct the exact recorded guest using retained Z8-owned source inputs")
    arguments = parser.parse_args()
    if arguments.historical_managed_inputs and not arguments.build:
        parser.error("--historical-managed-inputs requires --build")
    try:
        if arguments.build:
            result = build(arguments.historical_managed_inputs)
        elif arguments.verify:
            archive, manifest = verify_manifest(arguments.verify)
            result = {"state": "VERIFIED_ARTIFACT", "archive": str(archive), "archiveSha256": manifest["archiveSha256"], "deviceExecution": "NOT_TESTED"}
        else:
            result = {"state": "DRY_RUN", "lock": read_lock(), "action": "Use --build to download, verify and normalize. No guest packages are installed."}
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, zipfile.BadZipFile) as error:
        parser.exit(2, "z8 guest: " + str(error) + "\n")


if __name__ == "__main__":
    main()
