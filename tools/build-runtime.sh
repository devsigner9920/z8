#!/usr/bin/env bash
# Source preparation is host-portable; compilation runs in pinned Linux.
set -euo pipefail
script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${Z8_PYTHON:-python3}" "$script_dir/prepare-runtime.py" "$@"
