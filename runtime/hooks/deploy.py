#!/usr/bin/env python3
"""Stage optional hook assets into an explicitly marked offline z8 guest rootfs.

Does not install Python, edit CLI settings, trust hooks, bind sockets, or write
launch credentials. Default is a dry run. Assets already present but modified by
the user are preserved by refusing replacement.
"""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile

ASSETS = ("z8_event.py", "claude.hooks.json", "codex.hooks.json")


def real_path(root, relative):
    candidate = root
    for part in Path(relative).parts:
        if part in ("", ".", "..") or Path(part).is_absolute():
            raise ValueError("Unsafe guest path")
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("Guest hook paths must not cross symlinks")
    return candidate


def stage(rootfs, apply=False):
    rootfs = Path(rootfs)
    if rootfs.is_symlink() or not rootfs.is_dir():
        raise ValueError("Expected an actual guest rootfs directory")
    rootfs = rootfs.resolve(strict=True)
    if rootfs == Path(rootfs.anchor):
        raise ValueError("Refusing to stage into the host root")
    marker = real_path(rootfs, "etc/z8/guest-target")
    if not marker.is_file() or marker.read_bytes() not in (b"z8-guest-v1", b"z8-guest-v1\n"):
        raise ValueError("Expected z8-guest-v1 guest marker")
    destination = real_path(rootfs, "opt/z8/hooks")
    source = Path(__file__).resolve().parent
    payloads = []
    # Validate the complete set before making any changes.
    for name in ASSETS:
        target = real_path(rootfs, "opt/z8/hooks/" + name)
        data = (source / name).read_bytes()
        if target.exists() and (not target.is_file() or target.read_bytes() != data):
            raise ValueError("Existing hook asset differs; preserve and review it: " + name)
        payloads.append((target, data, 0o755 if name.endswith(".py") else 0o644))
    result = {"state": "staged" if apply else "dry-run", "guestDirectory": "/opt/z8/hooks",
              "requires": ["python3", "guest socket bind", "provider hook review/trust"],
              "sha256": {path.name: hashlib.sha256(data).hexdigest() for path, data, _ in payloads}}
    if apply:
        destination.mkdir(parents=True, exist_ok=True)
        for path, data, mode in payloads:
            if path.exists():
                continue
            descriptor, temporary = tempfile.mkstemp(prefix=".z8-hook-", dir=destination)
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                    os.fchmod(output.fileno(), mode)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    return result


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rootfs", required=True)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    try:
        print(json.dumps(stage(arguments.rootfs, arguments.apply), indent=2))
    except (OSError, ValueError) as error:
        parser.exit(2, "z8 hooks: " + str(error) + "\n")


if __name__ == "__main__":
    main()
