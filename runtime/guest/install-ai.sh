#!/bin/sh
# Official native artifacts, installed only into a marked project's Linux HOME.
set -eu
z8_mode=dry-run
z8_tool=all
z8_mode_set=false
z8_tool_set=false
for z8_arg in "$@"; do
    case "$z8_arg" in
        --dry-run|--apply)
            [ "$z8_mode_set" = false ] || { printf '%s\n' 'Choose one execution mode.' >&2; exit 2; }
            z8_mode=${z8_arg#--}; z8_mode_set=true ;;
        codex|claude|all)
            [ "$z8_tool_set" = false ] || { printf '%s\n' 'Choose codex, claude or all.' >&2; exit 2; }
            z8_tool=$z8_arg; z8_tool_set=true ;;
        --help|-h)
            printf '%s\n' 'Usage: install-ai.sh [--dry-run | --apply] [codex | claude | all]' \
                'Default: print the pinned plan. Apply requires the ARM64 z8 Linux guest, HOME=/z8/home and Python 3.'; exit 0 ;;
        *) printf '%s\n' "Unknown argument: $z8_arg" >&2; exit 2 ;;
    esac
done
z8_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ -f "$z8_script_dir/ai-tools.lock.json" ] || { printf '%s\n' 'Missing AI artifact lock.' >&2; exit 2; }
if [ "$z8_mode" = dry-run ]; then
    printf '%s\n' "Plan: $z8_tool native tools under /z8/home/.local/bin" \
        'No download, installation, login or account request was performed.' \
        'Pinned public artifact metadata (PRoot/CLI compatibility still needs execution tests):'
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
exec /usr/bin/python3 - "$z8_script_dir/ai-tools.lock.json" "$z8_tool" <<'Z8_AI_PYTHON'
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
ALLOWED_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "downloads.claude.ai"}

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
    output_path = staging / "version-output.txt"
    with output_path.open("wb") as output:
        completed = subprocess.run([str(binary), "--version"], stdout=output, stderr=subprocess.STDOUT, timeout=45, env=env)
    if output_path.stat().st_size > 65536:
        fail("Version command produced too much output.")
    output = output_path.read_text(encoding="utf-8", errors="replace").strip()
    if completed.returncode != 0 or not re.search(r"(?<![\w.-])" + re.escape(version) + r"(?![\w.-])", output):
        fail("Native binary did not report the pinned version: " + output[:2000])
    return output

def install_tool(home, tool, pin):
    tool_root = private_directory(home, ".local/share/z8/ai/" + tool)
    launch_dir = private_directory(home, ".local/bin")
    launcher = launch_dir / tool
    validate_launcher(launcher, tool_root, tool)
    packaged = tool == "codex" and pin["kind"] == "codex-package.tar.gz"
    # The first installer stored an incomplete single binary at <version>/codex.
    # Keep that directory and receipt intact; package layout uses a sibling.
    version_dir = tool_root / (pin["version"] + ("-package-v1" if packaged else ""))
    staging = Path(tempfile.mkdtemp(prefix=".install-", dir=tool_root))
    try:
        if version_dir.exists() or version_dir.is_symlink():
            binary = verify_existing_version(version_dir, tool, pin)
            version_output = version_check(binary, pin["version"], staging)
        else:
            print("Downloading official " + tool + " " + pin["version"] + "…", flush=True)
            if tool == "claude":
                manifest = staging / "manifest.json"
                download(pin["manifestUrl"], manifest, pin["manifestSha256"], limit=1024 * 1024)
                value = json.loads(manifest.read_text(encoding="utf-8"))
                platform = value["platforms"][pin["manifestPlatform"]]
                if value["version"] != pin["version"] or platform["checksum"] != pin["sha256"] or platform["size"] != pin["bytes"]:
                    fail("Claude's pinned official manifest does not match the artifact lock.")
            artifact = staging / "download"
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
            write_json(staging / "receipt.json", receipt)
            if version_dir.exists() or version_dir.is_symlink():
                fail("Another installation created this version; existing files were preserved.")
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
            safe_url(pin["manifestUrl"])
    return value

def main():
    value = validate_lock(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    tools = ("codex", "claude") if sys.argv[2] == "all" else (sys.argv[2],)
    home = Path("/z8/home")
    root = private_directory(home, ".local/share/z8/ai")
    lock = root / ".install.lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        fail("Another AI installation is active, or a stopped installation left " + str(lock) + ". Inspect it before retrying.")
    try:
        for tool in tools:
            install_tool(home, tool, value["tools"][tool])
    finally:
        lock.rmdir()
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
