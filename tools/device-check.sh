#!/bin/sh
# Read-only device inventory. Never installs, launches, or stops an app.
set -eu
z8_tools_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
z8_root_dir=$(dirname -- "$z8_tools_dir")
z8_python_works() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1
}
z8_find_python() {
    for z8_candidate in "$z8_root_dir/.local/python/bin/python3" "$z8_root_dir/.tools/python/bin/python3"; do
        if z8_python_works "$z8_candidate"; then
            printf '%s\n' "$z8_candidate"
            return 0
        fi
    done
    # Test every PATH candidate so a broken macOS stub does not hide a working
    # interpreter later in PATH. This function runs in a command substitution.
    z8_saved_ifs=$IFS
    IFS=:
    set -f
    for z8_path_dir in ${PATH:-}; do
        IFS=$z8_saved_ifs
        z8_candidate="${z8_path_dir:-.}/python3"
        if z8_python_works "$z8_candidate"; then
            printf '%s\n' "$z8_candidate"
            return 0
        fi
        IFS=:
    done
    return 1
}
z8_python_unavailable() {
    printf '%s\n' '{"schema_version":1,"status":"NOT_TESTED","gate_status":"NOT_TESTED","reason":"PYTHON_UNAVAILABLE"}'
    exit 2
}
if [ -n "${Z8_PYTHON:-}" ]; then
    z8_python=$Z8_PYTHON
    z8_python_works "$z8_python" || z8_python_unavailable
else
    z8_python=$(z8_find_python) || z8_python_unavailable
fi
exec "$z8_python" "$z8_tools_dir/collect-device-report.py" "$@"
