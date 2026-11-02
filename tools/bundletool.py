"""Fetch only the checksum-pinned official bundletool used for AAB validation."""
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request


def ensure(root):
    lock = json.loads((root / "tools/toolchain.lock.json").read_text())["bundletool"]
    folder = root / ".local/bundletool"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / ("bundletool-all-" + lock["version"] + ".jar")
    if destination.is_file():
        with destination.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == lock["sha256"]:
                return destination
        raise ValueError("Cached bundletool checksum mismatch; inspect it before replacing it")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, suffix=".download", delete=False) as output:
            temporary = Path(output.name)
            with urllib.request.urlopen(lock["url"], timeout=60) as response:
                while block := response.read(1024 * 1024):
                    output.write(block)
        with temporary.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != lock["sha256"]:
                raise ValueError("Downloaded bundletool checksum mismatch")
        temporary.replace(destination)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
