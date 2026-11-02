#!/bin/bash
# Read-only readiness: executable versions, not install marker existence.
set -u
export PATH=/opt/z8/node/current/bin:/z8/home/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
z8_requested=${1-all}
z8_deadline=$((SECONDS + 90))
z8_probe() {
    local name="$1"; shift
    [ "$z8_requested" = all ] || [ "$z8_requested" = "$name" ] || return 0
    local value remaining=$((z8_deadline - SECONDS))
    if ! command -v "$1" >/dev/null 2>&1; then printf '%s\t%s\n' "$name" '-'; return 0; fi
    if [ "$remaining" -le 0 ]; then printf '%s\t%s\n' "$name" '?'; return 0; fi
    local allowance=8
    # These launch language runtimes and scan many small package files under PRoot.
    case "$name" in pip|npm) allowance=30 ;; esac
    [ "$remaining" -le "$allowance" ] || remaining=$allowance
    if value=$(timeout -k 1 "$remaining" "$@" 2>/dev/null); then
        value=${value%%$'\n'*}
        value=${value//$'\t'/ }
        printf '%s\t%s\n' "$name" "${value:0:160}"
    else
        local result=$?
        if [ "$result" -eq 124 ] || [ "$result" -eq 137 ]; then
            printf '%s\t%s\n' "$name" '?'
        else
            printf '%s\t%s\n' "$name" '-'
        fi
    fi
}
z8_probe python python3 --version
z8_probe pip python3 -m pip --version
z8_probe venv python3 -c 'import venv, ensurepip; print("available")'
z8_probe node node --version
z8_probe npm npm --version
z8_probe git git --version
z8_probe gh gh --version
z8_probe make make --version
z8_probe cc cc --version
z8_probe tmux tmux -V
z8_probe claude claude --version
z8_probe codex codex --version

# Distinguish an incomplete aggregate check from individual missing executables.
[ "$SECONDS" -lt "$z8_deadline" ] || exit 124
