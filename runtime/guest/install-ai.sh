#!/bin/sh
# Official native artifacts, installed only into a marked project's Linux HOME.
set -eu
z8_mode=dry-run
z8_tool=all
z8_mode_set=false
z8_tool_set=false
z8_version=
while [ "$#" -gt 0 ]; do
    z8_arg=$1
    shift
    case "$z8_arg" in
        --dry-run|--apply)
            [ "$z8_mode_set" = false ] || { printf '%s\n' 'Choose one execution mode.' >&2; exit 2; }
            z8_mode=${z8_arg#--}; z8_mode_set=true ;;
        codex|claude|all)
            [ "$z8_tool_set" = false ] || { printf '%s\n' 'Choose codex, claude or all.' >&2; exit 2; }
            z8_tool=$z8_arg; z8_tool_set=true ;;
        --version)
            [ -z "$z8_version" ] && [ "$#" -gt 0 ] || { printf '%s\n' 'Choose one exact version.' >&2; exit 2; }
            z8_version=$1; shift
            printf '%s\n' "$z8_version" | LC_ALL=C grep -Eq '^(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})$' || { printf '%s\n' 'Version must be X.Y.Z.' >&2; exit 2; }
            ;;
        --help|-h)
            printf '%s\n' 'Usage: install-ai.sh [--dry-run | --apply] [codex | claude | all] [--version X.Y.Z]' \
                'Default: print the pinned plan. Apply requires the ARM64 z8 Linux guest, HOME=/z8/home and Python 3.'; exit 0 ;;
        *) printf '%s\n' "Unknown argument: $z8_arg" >&2; exit 2 ;;
    esac
done
[ -z "$z8_version" ] || [ "$z8_tool" != all ] || { printf '%s\n' 'An exact version requires one tool.' >&2; exit 2; }
z8_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ -f "$z8_script_dir/ai-tools.lock.json" ] || { printf '%s\n' 'Missing AI artifact lock.' >&2; exit 2; }
if [ "$z8_mode" = dry-run ]; then
    printf '%s\n' "Plan: $z8_tool native tools under /z8/home/.local/bin" \
        'No download, installation, login or account request was performed.' \
        'Pinned public artifact metadata (PRoot/CLI compatibility still needs execution tests):'
    [ -z "$z8_version" ] || printf '%s\n' "Selected version: $z8_version (official integrity metadata checked only after Apply)."
    cat -- "$z8_script_dir/ai-tools.lock.json"
    exit 0
fi
# Fixed guest tools only. Never retain the Android host PATH or dynamic loader setup.
PATH=/usr/local/bin:/usr/bin:/bin
export PATH
[ "$(uname -s)" = Linux ] || { printf '%s\n' '--apply requires a Linux guest.' >&2; exit 2; }
case "$(uname -m)" in aarch64|arm64) ;; *) printf '%s\n' '--apply requires ARM64.' >&2; exit 2 ;; esac
[ "${HOME-}" = /z8/home ] || { printf '%s\n' 'HOME must be /z8/home.' >&2; exit 2; }
[ -z "${LD_PRELOAD-}${LD_LIBRARY_PATH-}" ] || { printf '%s\n' 'Clear inherited loader variables before entering the guest.' >&2; exit 2; }
[ -f /etc/z8/guest-target ] && [ ! -L /etc/z8/guest-target ] || { printf '%s\n' 'Missing z8 guest image marker.' >&2; exit 2; }
[ "$(cat /etc/z8/guest-target)" = z8-guest-v1 ] || { printf '%s\n' 'Incorrect z8 guest image marker.' >&2; exit 2; }
[ -d /z8/home ] && [ -w /z8/home ] || { printf '%s\n' 'Project HOME is not writable.' >&2; exit 2; }
[ -x /usr/bin/python3 ] || { printf '%s\n' 'Install the basic development tools first (Python 3 and CA certificates).' >&2; exit 2; }
exec /usr/bin/python3 - "$z8_script_dir/ai-tools.lock.json" "$z8_tool" "$z8_version" <<'Z8_AI_PYTHON'
import base64
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

MANAGER = "z8-ai-v1"
MAX_BINARY = 1024 * 1024 * 1024
ALLOWED_HOSTS = {"github.com", "api.github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "downloads.claude.ai"}

def fail(message):
    raise RuntimeError(message)

def safe_url(url):
    value = urllib.parse.urlsplit(url)
    if value.scheme != "https" or value.hostname not in ALLOWED_HOSTS or value.username or value.password or value.port not in (None, 443):
        fail("Artifact URL is outside the official HTTPS allowlist.")
    return url

class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        safe_url(new_url)
        return super().redirect_request(request, fp, code, message, headers, new_url)

def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                return result.hexdigest()
            result.update(block)

def download(url, target, expected_hash, expected_size=None, limit=MAX_BINARY):
    safe_url(url)
    opener = urllib.request.build_opener(OfficialRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "z8-native-installer/1", "Accept-Encoding": "identity"})
    deadline = time.monotonic() + 600
    total = 0
    result = hashlib.sha256()
    with opener.open(request, timeout=30) as response, target.open("xb") as output:
        safe_url(response.geturl())
        while True:
            if time.monotonic() > deadline:
                fail("Download exceeded ten minutes.")
            block = response.read(256 * 1024)
            if not block:
                break
            total += len(block)
            if total > limit or (expected_size is not None and total > expected_size):
                fail("Download exceeds the pinned artifact size.")
            result.update(block)
            output.write(block)
        output.flush()
        os.fsync(output.fileno())
    if (expected_size is not None and total != expected_size) or result.hexdigest() != expected_hash:
        fail("Official artifact SHA-256 or size mismatch.")

def metadata(url, limit):
    """Only callers construct these fixed official endpoints; no remote URL is executed."""
    safe_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "z8-native-installer/1", "Accept-Encoding": "identity"})
    deadline = time.monotonic() + 30
    with urllib.request.build_opener(OfficialRedirect()).open(request, timeout=10) as response:
        safe_url(response.geturl())
        output = bytearray()
        while True:
            block = response.read(min(65536, limit + 1 - len(output)))
            if not block:
                return bytes(output)
            output.extend(block)
            if len(output) > limit or time.monotonic() > deadline:
                fail("Official metadata exceeds its response limit.")

def selected_pin(tool, version, baseline):
    if not isinstance(version, str) or not re.fullmatch(r"(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})", version):
        fail("Select an exact X.Y.Z release version.")
    pin = copy.deepcopy(baseline)
    if version == pin["version"]:
        return pin
    pin["version"] = version
    if tool == "codex":
        tag = "rust-v" + version
        release = json.loads(metadata("https://api.github.com/repos/openai/codex/releases/tags/" + tag, 2 * 1024 * 1024))
        if release.get("tag_name") != tag or release.get("draft") is not False or release.get("prerelease") is not False:
            fail("The selected Codex release is not a published stable release.")
        name = "codex-package-aarch64-unknown-linux-musl.tar.gz"
        assets = [asset for asset in release.get("assets", []) if asset.get("name") == name]
        url = "https://github.com/openai/codex/releases/download/" + tag + "/" + name
        if len(assets) != 1:
            fail("This release has no unique supported ARM64 package.")
        asset = assets[0]
        if asset.get("browser_download_url") != url or not re.fullmatch(r"sha256:[0-9a-f]{64}", asset.get("digest") or "") \
                or type(asset.get("size")) is not int or not 0 < asset["size"] <= MAX_BINARY:
            fail("The official release does not provide the required SHA-256, size and platform identity.")
        pin.update(url=url, sha256=asset["digest"][7:], bytes=asset["size"], selectedRelease=True)
        pin["packageManifest"]["version"] = version
    elif tool == "claude":
        root = "https://downloads.claude.ai/claude-code-releases/" + version + "/"
        pin.update(url=root + "linux-arm64/claude", manifestUrl=root + "manifest.json")
        signature = pin["manifestSignature"]
        signature["url"] = pin["manifestUrl"] + ".sig"
        # Trust remains the bundled signing-key hash/fingerprint. A rotated or
        # untrusted key requires a Z8 update, never an automatic trust change.
        with tempfile.TemporaryDirectory(prefix="z8-claude-metadata-") as temporary:
            directory = Path(temporary)
            manifest, signed, key = (directory / name for name in ("manifest", "signature", "key"))
            raw = metadata(pin["manifestUrl"], 1024 * 1024)
            raw_signature = metadata(signature["url"], 65536)
            manifest.write_bytes(raw); signed.write_bytes(raw_signature)
            trusted = signature["signingKey"]
            download(trusted["url"], key, trusted["sha256"], trusted["bytes"], limit=65536)
            verify_claude_signature(manifest, signed, key, directory, trusted["fingerprint"])
            value = json.loads(raw)
            platform = value.get("platforms", {}).get("linux-arm64", {})
            if value.get("version") != version or not re.fullmatch(r"[0-9a-f]{64}", platform.get("checksum") or "") \
                    or type(platform.get("size")) is not int or not 0 < platform["size"] <= MAX_BINARY:
                fail("Signed Claude metadata does not match the selected ARM64 version.")
            pin.update(sha256=platform["checksum"], bytes=platform["size"], manifestSha256=hashlib.sha256(raw).hexdigest(), manifestBytes=len(raw))
            signature.update(sha256=hashlib.sha256(raw_signature).hexdigest(), bytes=len(raw_signature))
    else:
        fail("Unknown native tool.")
    return pin

def selected_codex_members(archive, pin):
    """Derive file hashes only after the entire official SHA-256 was verified.

    Only the bundled graph and the reviewed 0.169 exec-server graph are known.
    Other upstream layout changes need review and an app update.
    """
    actual, total = {}, 0
    with tarfile.open(archive, "r:gz") as source:
        seen, expanded = {}, 0
        for item in source:
            expanded += item.size
            if item.name in seen or len(seen) >= 100 or not (item.isfile() or item.isdir()) \
                    or item.size < 0 or expanded > MAX_BINARY:
                fail("Codex package has duplicate or excessive entries.")
            seen[item.name] = item
        manifest_item = seen.get("codex-package.json")
        if manifest_item is None or not manifest_item.isfile() or not 0 < manifest_item.size <= 16384:
            fail("Codex package lacks a bounded discovery manifest.")
        manifest = json.loads(source.extractfile(manifest_item).read())
        expected_manifest = dict(pin["packageManifest"])
        exec_server_manifest = dict(expected_manifest, execServer="bin/codex-exec-server")
        if manifest == exec_server_manifest and manifest != expected_manifest:
            removed = {"codex-resources/zsh", "codex-resources/zsh/bin", "codex-resources/zsh/bin/zsh"}
            pin["members"] = [dict(record) for record in pin["members"] if record["path"] not in removed]
            pin["members"].append({"path": "bin/codex-exec-server", "type": "file", "mode": 0o755, "size": 0, "sha256": "0" * 64})
            pin["binaries"] = [name for name in pin["binaries"] if name not in removed] + ["bin/codex-exec-server"]
            pin["packageManifest"] = manifest
        elif manifest != expected_manifest:
            fail("The selected Codex discovery layout needs an app update.")
        expected = package_members(pin)
        for item in seen.values():
            record = expected.get(item.name)
            if record is None or item.name in actual or item.mode != record["mode"] \
                    or (record["type"] == "directory" and not item.isdir()) \
                    or (record["type"] == "file" and not item.isfile()):
                fail("The selected Codex package layout needs an app update.")
            total += item.size
            if item.size < 0 or total > MAX_BINARY or item.isdir() and item.size != 0:
                fail("Codex package expansion exceeds the supported limit.")
            current = dict(record, size=item.size)
            if item.isfile():
                digest_value = hashlib.sha256()
                with source.extractfile(item) as stream:
                    for block in iter(lambda: stream.read(256 * 1024), b""):
                        digest_value.update(block)
                current["sha256"] = digest_value.hexdigest()
            actual[item.name] = current
    if set(actual) != set(expected):
        fail("The selected Codex package is incomplete.")
    pin["members"] = [actual[name] for name in sorted(actual)]

def private_directory(root, relative):
    if root.is_symlink() or not root.is_dir():
        fail("Project HOME must be a real directory.")
    current = root
    for part in Path(relative).parts:
        if part in ("", ".", "..") or "/" in part:
            fail("Invalid managed path.")
        current = current / part
        if current.is_symlink():
            fail("Refusing a symlink in the managed installation path.")
        current.mkdir(mode=0o700, exist_ok=True)
        if not current.is_dir():
            fail("Managed installation path is not a directory.")
    return current

def write_json(path, value):
    temporary = path.with_name(path.name + ".pending")
    if temporary.exists() or temporary.is_symlink():
        fail("An unfinished metadata write needs review: " + str(temporary))
    try:
        with temporary.open("x", encoding="utf-8") as output:
            json.dump(value, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()

def validate_elf(path):
    with path.open("rb") as stream:
        header = stream.read(20)
    if len(header) != 20 or header[:6] != b"\x7fELF\x02\x01" or header[18:20] != b"\xb7\x00":
        fail("Artifact is not a little-endian ARM64 ELF executable.")

def package_members(pin):
    records = pin.get("members")
    if not isinstance(records, list) or not records or len(records) > 100:
        fail("Codex package requires a bounded, pinned member table.")
    entries = {}
    total = 0
    for record in records:
        if not isinstance(record, dict) or set(record) != {"path", "type", "mode", "size", "sha256"}:
            fail("Unsupported Codex package member record.")
        name = record["path"]
        if not isinstance(name, str) or not name or name.startswith("/") or "\\" in name \
                or any(ord(c) < 32 for c in name) or any(p in ("", ".", "..") for p in name.split("/")):
            fail("Unsafe Codex package member path.")
        if name in entries or record["type"] not in ("file", "directory") \
                or type(record["mode"]) is not int or record["mode"] not in (0o555, 0o644, 0o755) \
                or type(record["size"]) is not int or not 0 <= record["size"] <= MAX_BINARY:
            fail("Invalid or duplicate Codex package member.")
        if record["type"] == "directory":
            if record["size"] != 0 or record["sha256"] is not None or record["mode"] != 0o755:
                fail("Invalid Codex package directory.")
        elif not re.fullmatch(r"[0-9a-f]{64}", record["sha256"] or ""):
            fail("Missing Codex package file hash.")
        entries[name] = record
        total += record["size"]
    if total > MAX_BINARY:
        fail("Codex package expanded size exceeds the installation limit.")
    for name in entries:
        for parent in PurePosixPath(name).parents:
            if str(parent) != "." and entries.get(str(parent), {}).get("type") != "directory":
                fail("Codex package member has a missing or non-directory parent.")
    binaries = pin.get("binaries")
    if not isinstance(binaries, list) or not binaries or len(set(binaries)) != len(binaries):
        fail("Missing expected Codex package binaries.")
    if pin.get("entryPoint") != "bin/codex" or pin.get("layoutRevision") != "codex-package-v1":
        fail("Unsupported Codex package launch layout.")
    for name in binaries:
        if entries.get(name, {}).get("type") != "file" or entries[name]["mode"] != 0o755:
            fail("Expected Codex executable is missing from the pinned package.")
    if "bin/codex" not in binaries or entries.get("codex-package.json", {}).get("type") != "file":
        fail("The complete Codex package requires its launcher and manifest.")
    manifest = {"layoutVersion": 1, "version": pin["version"], "target": "aarch64-unknown-linux-musl",
        "variant": "codex", "entrypoint": "bin/codex", "resourcesDir": "codex-resources", "pathDir": "codex-path"}
    if pin.get("packageManifest", {}).get("execServer") == "bin/codex-exec-server":
        manifest["execServer"] = "bin/codex-exec-server"
        if "bin/codex-exec-server" not in binaries:
            fail("The Codex exec-server layout requires its companion executable.")
    if pin.get("packageManifest") != manifest:
        fail("Unsupported Codex package discovery manifest.")
    return entries

def extract_codex_package(archive, target, pin):
    expected = package_members(pin)
    with tarfile.open(archive, "r:gz") as tar:
        seen = {}
        for item in tar:
            # Only the exact pinned graph is accepted. No tarfile.extract or
            # extractall, symlinks, hardlinks, devices, ownership or xattrs.
            name = item.name.rstrip("/") if item.isdir() else item.name
            record = expected.get(name)
            if record is None or name in seen or item.issparse() or item.mode != record["mode"] \
                    or item.size != record["size"] or (item.isdir() if record["type"] == "directory" else item.isfile()) is not True:
                fail("Unexpected Codex package member, type, size or mode: " + item.name)
            seen[name] = item
        if set(seen) != set(expected):
            fail("The Codex package is incomplete.")
        for name, record in sorted(expected.items(), key=lambda pair: (pair[0].count("/"), pair[0])):
            if record["type"] == "directory":
                (target / name).mkdir(mode=0o755)
                (target / name).chmod(0o755)
        # Read payloads in tar order to avoid repeatedly seeking through gzip.
        for name in seen:
            record = expected[name]
            destination = target / name
            if record["type"] == "directory":
                continue
            source = tar.extractfile(seen[name])
            if source is None:
                fail("Unreadable Codex package file.")
            result, count = hashlib.sha256(), 0
            with source, destination.open("xb") as output:
                while True:
                    block = source.read(256 * 1024)
                    if not block:
                        break
                    count += len(block)
                    if count > record["size"]:
                        fail("Codex package file exceeds its pinned size.")
                    result.update(block)
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
            if count != record["size"] or result.hexdigest() != record["sha256"]:
                fail("Codex package file differs from its pinned hash/size.")
            destination.chmod(record["mode"])
            with destination.open("rb") as stream:
                is_elf = stream.read(4) == b"\x7fELF"
            if is_elf or name in pin["binaries"]:
                validate_elf(destination)
    if json.loads((target / "codex-package.json").read_text()) != pin["packageManifest"]:
        fail("Codex package discovery manifest differs from its pinned layout.")
    return [dict(expected[name]) for name in sorted(expected)]

def verify_package_tree(version_dir, records):
    expected = {record["path"]: record for record in records}
    actual = set()
    for path in version_dir.rglob("*"):
        name = path.relative_to(version_dir).as_posix()
        if name in ("receipt.json", "version-output.txt"):
            if path.is_symlink() or not path.is_file():
                fail("Managed Codex metadata changed type.")
            continue
        record = expected.get(name)
        if path.is_symlink() or record is None:
            fail("Existing Codex package contains unowned files or links; it was preserved.")
        actual.add(name)
        if stat.S_IMODE(path.stat().st_mode) != record["mode"] \
                or (path.is_dir() if record["type"] == "directory" else path.is_file()) is not True:
            fail("Existing Codex package type or mode changed; it was preserved.")
        if record["type"] == "file" and (path.stat().st_size != record["size"] or digest(path) != record["sha256"]):
            fail("Existing Codex package file changed; it was preserved.")
    if actual != set(expected):
        fail("Existing Codex package is incomplete; it was preserved.")

def verify_existing_version(version_dir, tool, pin):
    if version_dir.is_symlink() or not version_dir.is_dir():
        fail("Existing version path is not a managed directory.")
    receipt_path = version_dir / "receipt.json"
    packaged = tool == "codex" and pin["kind"] == "codex-package.tar.gz"
    binary = version_dir / (pin["entryPoint"] if packaged else tool)
    if receipt_path.is_symlink() or binary.is_symlink() or not receipt_path.is_file() or not binary.is_file():
        fail("Existing files are unowned; refusing to replace them.")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("manager") != MANAGER or receipt.get("tool") != tool or receipt.get("version") != pin["version"] \
            or receipt.get("artifactSha256") != pin["sha256"] or receipt.get("binarySha256") != digest(binary):
        fail("Existing managed files changed; refusing to overwrite them.")
    if packaged:
        expected = [dict(record) for _, record in sorted(package_members(pin).items())]
        if receipt.get("layoutRevision") != pin["layoutRevision"] or receipt.get("entryPoint") != pin["entryPoint"] \
                or receipt.get("members") != expected or receipt.get("binaries") != pin["binaries"] \
                or receipt.get("packageManifest") != pin["packageManifest"]:
            fail("Existing Codex package receipt changed; it was preserved.")
        verify_package_tree(version_dir, expected)
        for name in pin["binaries"]:
            validate_elf(version_dir / name)
    elif tool == "claude":
        if binary.stat().st_size != pin["bytes"] or digest(binary) != pin["sha256"]:
            fail("Existing Claude binary differs from the signed release; it was preserved.")
        validate_elf(binary)
    return binary

def validate_launcher(launcher, tool_root, tool):
    if not launcher.exists() and not launcher.is_symlink():
        return
    if not launcher.is_symlink():
        fail("An existing " + tool + " launcher is not managed by z8; it was preserved.")
    destination = launcher.resolve(strict=True)
    try:
        relative = destination.relative_to(tool_root.resolve()).parts
    except ValueError:
        fail("The existing launcher belongs to another installation; it was preserved.")
    legacy = len(relative) == 2 and relative[1] == tool
    packaged = tool == "codex" and len(relative) == 3 and relative[1:] == ("bin", "codex")
    if not legacy and not packaged:
        fail("The existing launcher belongs to another installation; it was preserved.")
    version_dir = tool_root / relative[0]
    receipt = version_dir / "receipt.json"
    if receipt.is_symlink() or not receipt.is_file():
        fail("The existing launcher has no managed receipt.")
    value = json.loads(receipt.read_text(encoding="utf-8"))
    if value.get("manager") != MANAGER or value.get("tool") != tool or value.get("binarySha256") != digest(destination):
        fail("The existing launcher or binary changed; it was preserved.")
    version = value.get("version", "")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        fail("Existing managed launcher has an invalid version receipt.")
    if legacy:
        if relative[0] != version:
            fail("Existing managed launcher version path changed.")
    else:
        expected = package_members(value)
        if relative[0] != version + "-package-v1":
            fail("Existing Codex package version path changed.")
        verify_package_tree(version_dir, list(expected.values()))

def version_check(binary, version, staging):
    env = dict(os.environ)
    env.pop("LD_PRELOAD", None)
    env.pop("LD_LIBRARY_PATH", None)
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    env["DISABLE_AUTOUPDATER"] = "1"
    output_path = staging / "version-output.txt"
    with output_path.open("wb") as output:
        completed = subprocess.run([str(binary), "--version"], stdout=output, stderr=subprocess.STDOUT, timeout=45, env=env)
    if output_path.stat().st_size > 65536:
        fail("Version command produced too much output.")
    output = output_path.read_text(encoding="utf-8", errors="replace").strip()
    if completed.returncode != 0 or not re.search(r"(?<![\w.-])" + re.escape(version) + r"(?![\w.-])", output):
        fail("Native binary did not report the pinned version: " + output[:2000])
    return output

def verify_claude_signature(manifest, signature, armored_key, directory, fingerprint):
    # The raw key was hash/size checked before this transport-only conversion.
    # gpgv expects a binary keyring; all OpenPGP parsing and cryptography remain
    # in the existing guest verifier, never in this installer.
    armor = armored_key.read_text(encoding="ascii")
    match = re.fullmatch(r"-----BEGIN PGP PUBLIC KEY BLOCK-----\n\n([A-Za-z0-9+/=\n]+)\n=[A-Za-z0-9+/]{4}\n-----END PGP PUBLIC KEY BLOCK-----\n?", armor)
    if match is None:
        fail("Unsupported pinned Claude signing-key armor.")
    keyring = directory / "claude-keyring.gpg"
    with keyring.open("xb") as output:
        output.write(base64.b64decode(match.group(1).replace("\n", ""), validate=True))
    homedir = directory / "gnupg"
    homedir.mkdir(mode=0o700)
    verifier = Path("/usr/bin/gpgv")
    if not verifier.is_file() or not os.access(verifier, os.X_OK):
        fail("The guest's /usr/bin/gpgv is required to verify Claude's release signature.")
    status_path, log_path = directory / "gpgv-status.txt", directory / "gpgv-log.txt"
    # A private home and an explicit absolute keyring exclude the user's keys,
    # trust database and configuration. No keyserver or network lookup occurs.
    env = {"PATH": "/usr/bin:/bin", "HOME": str(homedir.resolve()),
        "GNUPGHOME": str(homedir.resolve()), "LANG": "C", "LC_ALL": "C"}
    with status_path.open("xb") as status_output, log_path.open("xb") as log_output:
        completed = subprocess.run([str(verifier), "--homedir", str(homedir.resolve()),
            "--keyring", str(keyring.resolve()), "--status-fd", "1",
            str(signature.resolve()), str(manifest.resolve())],
            stdin=subprocess.DEVNULL, stdout=status_output, stderr=log_output, timeout=45, env=env)
    if status_path.stat().st_size > 65536 or log_path.stat().st_size > 65536:
        fail("Claude signature verification produced too much output.")
    statuses = []
    rejected = {"BADSIG", "ERRSIG", "EXPSIG", "EXPKEYSIG", "REVKEYSIG", "NO_PUBKEY", "NODATA", "FAILURE", "ERROR", "KEYEXPIRED", "SIGEXPIRED", "KEYREVOKED"}
    for line in status_path.read_text(encoding="ascii").splitlines():
        if not line.startswith("[GNUPG:] "):
            fail("Unexpected Claude signature verification status.")
        fields = line[len("[GNUPG:] "):].split()
        if not fields or fields[0] in rejected:
            fail("Claude release signature verification failed.")
        if fields[0] == "VALIDSIG":
            statuses.append(fields[1:])
    if completed.returncode != 0 or len(statuses) != 1:
        fail("Claude release signature verification failed.")
    valid = statuses[0]
    # VALIDSIG field 1 is the signing key; optional field 10 identifies its
    # primary key when a subkey signed. Require the exact pinned primary key.
    if len(valid) not in (9, 10) or (valid[9] if len(valid) == 10 else valid[0]) != fingerprint \
            or not re.fullmatch(r"[0-9A-F]{40}", valid[0]) or valid[7] not in ("8", "9", "10", "11"):
        fail("Claude release signature does not match the pinned signing key.")
    return valid[0]

def verify_claude_manifest(staging, pin):
    signature_pin = pin["manifestSignature"]
    key_pin = signature_pin["signingKey"]
    with tempfile.TemporaryDirectory(prefix=".claude-verify-", dir=staging) as temporary:
        directory = Path(temporary)
        manifest, signature, key = (directory / name for name in ("manifest.json", "manifest.json.sig", "claude-code.asc"))
        download(pin["manifestUrl"], manifest, pin["manifestSha256"], pin["manifestBytes"], limit=1024 * 1024)
        download(signature_pin["url"], signature, signature_pin["sha256"], signature_pin["bytes"], limit=65536)
        download(key_pin["url"], key, key_pin["sha256"], key_pin["bytes"], limit=65536)
        signer = verify_claude_signature(manifest, signature, key, directory, key_pin["fingerprint"])
        value = json.loads(manifest.read_text(encoding="utf-8"))
        platform = value["platforms"][pin["manifestPlatform"]]
        if value["version"] != pin["version"] or platform["checksum"] != pin["sha256"] or platform["size"] != pin["bytes"]:
            fail("Claude's signed official manifest does not match the artifact lock.")
    return {"verifier": "gpgv", "manifestSha256": pin["manifestSha256"],
        "signatureSha256": signature_pin["sha256"], "signingKeySha256": key_pin["sha256"],
        "primaryFingerprint": key_pin["fingerprint"], "signingFingerprint": signer}

def install_tool(home, tool, pin):
    tool_root = private_directory(home, ".local/share/z8/ai/" + tool)
    remove_interrupted_staging(tool_root, tool)
    launch_dir = private_directory(home, ".local/bin")
    launcher = launch_dir / tool
    validate_launcher(launcher, tool_root, tool)
    packaged = tool == "codex" and pin["kind"] == "codex-package.tar.gz"
    # The first installer stored an incomplete single binary at <version>/codex.
    # Keep that directory and receipt intact; package layout uses a sibling.
    version_dir = tool_root / (pin["version"] + ("-package-v1" if packaged else ""))
    staging = Path(tempfile.mkdtemp(prefix=".install-", dir=tool_root))
    marker = staging / ".z8-ai-staging"
    marker.write_text("z8-ai-staging-v1\n" + staging.name + "\n" + tool + "\n")
    try:
        # Reinstalling an existing binary must not bypass signature validation.
        verification = verify_claude_manifest(staging, pin) if tool == "claude" else None
        artifact = staging / "download"
        if packaged and pin.get("selectedRelease"):
            download(pin["url"], artifact, pin["sha256"], pin["bytes"])
            selected_codex_members(artifact, pin)
        if version_dir.exists() or version_dir.is_symlink():
            binary = verify_existing_version(version_dir, tool, pin)
            version_output = version_check(binary, pin["version"], staging)
        else:
            print("Downloading official " + tool + " " + pin["version"] + "…", flush=True)
            if not artifact.exists():
                download(pin["url"], artifact, pin["sha256"], pin["bytes"])
            binary = staging / (pin["entryPoint"] if packaged else tool)
            if packaged:
                members = extract_codex_package(artifact, staging, pin)
                artifact.unlink()
            else:
                artifact.rename(binary)
            validate_elf(binary)
            binary.chmod(0o755)
            version_output = version_check(binary, pin["version"], staging)
            receipt = {"manager": MANAGER, "tool": tool, "version": pin["version"], "artifactSha256": pin["sha256"],
                "binarySha256": digest(binary), "source": pin["url"], "versionOutput": version_output,
                "installedAt": int(time.time()), "authenticatedWorkflow": "NOT_TESTED"}
            if packaged:
                receipt.update(layoutRevision=pin["layoutRevision"], entryPoint=pin["entryPoint"],
                    binaries=pin["binaries"], packageManifest=pin["packageManifest"], members=members)
            if verification is not None:
                receipt["manifestVerification"] = verification
            write_json(staging / "receipt.json", receipt)
            if version_dir.exists() or version_dir.is_symlink():
                fail("Another installation created this version; existing files were preserved.")
            marker.unlink()
            staging.rename(version_dir)
            binary = version_dir / (pin["entryPoint"] if packaged else tool)
        # Recheck immediately before replacing only our own managed launcher.
        validate_launcher(launcher, tool_root, tool)
        pending = launch_dir / ("." + tool + ".z8-" + str(os.getpid()))
        if pending.exists() or pending.is_symlink():
            fail("An unfinished launcher publication needs review.")
        try:
            pending.symlink_to(os.path.relpath(binary, launch_dir))
            os.replace(pending, launcher)
        finally:
            if pending.is_symlink():
                pending.unlink()
        print(version_output, flush=True)
        print("Installed " + str(launcher) + ". Login and an authenticated task have NOT been tested.", flush=True)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

def remove_interrupted_staging(root, tool):
    for entry in root.iterdir():
        if not re.fullmatch(r"\.install-[a-z0-9_]{8}", entry.name) or entry.is_symlink() or not entry.is_dir():
            continue
        try:
            descriptor = os.open(entry / ".z8-ai-staging", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    continue
                receipt = source.read(128)
        except OSError:
            continue
        if receipt == ("z8-ai-staging-v1\n" + entry.name + "\n" + tool + "\n").encode():
            # Only our abandoned temporary tree; rmtree does not follow links.
            shutil.rmtree(entry)

def installation_lock(root):
    path = root / ".install.lock"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError:
        fail("An unrecognized legacy installation lock was preserved; review it before retrying.")
    stream = os.fdopen(descriptor, "w")
    try:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            fail("The installation lock is not a regular file; it was preserved.")
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return stream
    except BlockingIOError:
        stream.close()
        fail("Another tool installation is running in this project.")
    except BaseException:
        stream.close()
        raise

def validate_lock(value):
    if value.get("schemaVersion") != 1 or value.get("platform") != "linux-aarch64":
        fail("Unsupported AI artifact lock.")
    for tool in ("codex", "claude"):
        pin = value["tools"][tool]
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", pin["version"]) or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]):
            fail("Invalid pinned version or SHA-256.")
        if type(pin["bytes"]) is not int or not 0 < pin["bytes"] <= MAX_BINARY:
            fail("Invalid pinned artifact size.")
        safe_url(pin["url"])
        if tool == "codex":
            if pin["kind"] != "codex-package.tar.gz":
                fail("Codex requires the complete official package, not a single executable.")
            package_members(pin)
        if tool == "claude":
            if pin["kind"] != "binary" or not re.fullmatch(r"[0-9a-f]{64}", pin["manifestSha256"]):
                fail("Unsupported Claude artifact metadata.")
            release = "https://downloads.claude.ai/claude-code-releases/" + pin["version"] + "/"
            signature = pin.get("manifestSignature", {})
            key = signature.get("signingKey", {})
            if pin.get("manifestPlatform") != "linux-arm64" or pin["url"] != release + "linux-arm64/claude" \
                    or pin["manifestUrl"] != release + "manifest.json" or signature.get("url") != pin["manifestUrl"] + ".sig" \
                    or key.get("url") != "https://downloads.claude.ai/keys/claude-code.asc" \
                    or not re.fullmatch(r"[0-9A-F]{40}", key.get("fingerprint", "")):
                fail("Unsupported Claude release signature identity or URL.")
            for checksum, size, limit in ((pin["manifestSha256"], pin.get("manifestBytes"), 1024 * 1024),
                    (signature.get("sha256", ""), signature.get("bytes"), 65536), (key.get("sha256", ""), key.get("bytes"), 65536)):
                if type(size) is not int or not 0 < size <= limit \
                        or not re.fullmatch(r"[0-9a-f]{64}", checksum):
                    fail("Missing bounded Claude release signature metadata.")
    return value

def main():
    value = validate_lock(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    tools = ("codex", "claude") if sys.argv[2] == "all" else (sys.argv[2],)
    home = Path("/z8/home")
    root = private_directory(home, ".local/share/z8/ai")
    # Kernel ownership is released after normal exit or Android process death.
    # Old directory locks are never silently removed or treated as our files.
    with installation_lock(root):
        for tool in tools:
            selected = sys.argv[3] if len(sys.argv) > 3 else ""
            if selected and len(tools) != 1:
                fail("Select one tool for an exact-version install.")
            pin = selected_pin(tool, selected, value["tools"][tool]) if selected else value["tools"][tool]
            install_tool(home, tool, pin)
    print("Run codex or claude in /workspace and complete the provider's own login flow when ready.")
    print("Permission and sandbox defaults were not changed. PRoot compatibility still requires a real authenticated task.")

if __name__ == "__main__":
    def interrupted(_signal, _frame):
        raise InterruptedError("Installation interrupted; no login was attempted.")
    signal.signal(signal.SIGTERM, interrupted)
    try:
        main()
    except Exception as error:
        print("z8 AI installer: " + str(error), file=sys.stderr)
        sys.exit(2)
Z8_AI_PYTHON
