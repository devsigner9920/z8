#!/bin/bash
# Read-only readiness: executable versions, not install marker existence.
set -u
export DISABLE_AUTOUPDATER=1
export PATH=/usr/local/lib/z8/browser/bin:/opt/z8/node/current/bin:/z8/home/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
z8_requested=${1-all}
# Tools opening uses one local inventory pass, never ten CLI launches.
if [ "$z8_requested" = snapshot ]; then
    declare -A z8_packages
    while IFS=$'\t' read -r name status flag version; do
        [ "$status" = installed ] && [ "$flag" = ok ] && [ -n "$version" ] && z8_packages[$name]=$version
    done < <(dpkg-query -W -f='${Package}\t${db:Status-Status}\t${db:Status-Eflag}\t${Version}\n' \
        python3 python3-pip python3-venv git gh make gcc tmux openssh-client bash-completion curl wget ripgrep fd-find fzf jq less nano tree file unzip zip procps 2>/dev/null || true)
    z8_package_snapshot() {
        local name=$1 package=$2 executable=$3
        if [ -n "${z8_packages[$package]-}" ]; then printf '%s\t%s\n' "$name" "${z8_packages[$package]}"
        elif command -v "$executable" >/dev/null 2>&1; then printf '%s\t?\n' "$name"
        else printf '%s\t-\n' "$name"; fi
    }
    z8_package_snapshot python python3 python3
    z8_package_snapshot pip python3-pip pip3
    z8_package_snapshot venv python3-venv __z8_no_venv_command
    for spec in git:git:git gh:gh:gh make:make:make cc:gcc:cc tmux:tmux:tmux ssh:openssh-client:ssh; do
        IFS=: read -r name package executable <<< "$spec"; z8_package_snapshot "$name" "$package" "$executable"
    done
    z8_utilities=true
    for package in bash-completion curl wget ripgrep fd-find fzf jq less nano tree file unzip zip procps; do
        [ -n "${z8_packages[$package]-}" ] || z8_utilities=false
    done
    if [ "$z8_utilities" = true ]; then printf 'utilities\t%s\n' "${z8_packages[jq]}"
    elif command -v jq >/dev/null 2>&1; then printf 'utilities\t?\n'; else printf 'utilities\t-\n'; fi
    if [ ! -x /usr/bin/python3 ]; then
        for tool in node npm codex claude; do
            if command -v "$tool" >/dev/null 2>&1; then printf '%s\t?\n' "$tool"; else printf '%s\t-\n' "$tool"; fi
        done
        exit 0
    fi
    /usr/bin/python3 - <<'Z8_STATUS_PYTHON'
import json, os, re, shutil
from pathlib import Path

def output(tool, version): print(tool + "\t" + version)
def unknown(tool): return "?" if shutil.which(tool) else "-"
def receipt(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024: raise ValueError()
    value=json.loads(path.read_text())
    if not isinstance(value,dict): raise ValueError()
    return value
def regular_binary(path, base):
    return path.is_file() and not path.is_symlink() and os.access(path, os.X_OK) and path.resolve().is_relative_to(base)
# This is last-verified managed metadata, not a new executable/integrity check.
try:
    base=Path('/opt/z8/node'); link=base/'current'; target=os.readlink(link)
    if not re.fullmatch(r'v24\.[0-9]+\.[0-9]+',target): raise ValueError()
    directory=base/target
    if directory.resolve()!=directory: raise ValueError()
    data=receipt(directory/'.z8-node-receipt.json')
    if data.get('manager')!='z8-node-v1' or data.get('version')!=target or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',data.get('npm','')): raise ValueError()
    if not regular_binary(directory/'bin/node',directory): raise ValueError()
    if not shutil.which('node') or Path(shutil.which('node')).resolve()!=(directory/'bin/node').resolve(): raise ValueError()
    if not (directory/'bin/npm').resolve().is_relative_to(directory) or not (directory/'bin/npm').is_file() or not os.access(directory/'bin/npm',os.X_OK): raise ValueError()
    if not shutil.which('npm') or Path(shutil.which('npm')).resolve()!=(directory/'bin/npm').resolve(): raise ValueError()
    output('node',target);output('npm',data['npm'])
except (OSError,ValueError,TypeError,KeyError,RuntimeError):
    output('node',unknown('node'));output('npm',unknown('npm'))
for tool in ('codex','claude'):
    try:
        base=Path('/z8/home/.local/share/z8/ai')/tool; link=Path('/z8/home/.local/bin')/tool
        if not link.is_symlink() or base.resolve()!=base: raise ValueError()
        binary=link.resolve(strict=True); parts=binary.relative_to(base).parts
        if not shutil.which(tool) or Path(shutil.which(tool)).resolve()!=binary: raise ValueError()
        if not (len(parts)==2 and parts[1]==tool or tool=='codex' and len(parts)==3 and parts[1:]==('bin','codex')): raise ValueError()
        directory=base/parts[0]; data=receipt(directory/'receipt.json');version=data.get('version','')
        if data.get('manager')!='z8-ai-v1' or data.get('tool')!=tool or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version): raise ValueError()
        if parts[0] not in (version,version+'-package-v1') or not regular_binary(binary,directory): raise ValueError()
        if not re.fullmatch(r'[0-9a-f]{64}',data.get('binarySha256','')): raise ValueError()
        output(tool,version)
    except (OSError,ValueError,TypeError,KeyError,RuntimeError): output(tool,unknown(tool))
Z8_STATUS_PYTHON
    exit $?
fi
z8_deadline=$((SECONDS + 90))
z8_probe() {
    local name="$1"; shift
    case "$z8_requested:$name" in
        all:*|python:python|python:pip|python:venv|node:node|node:npm|build-tools:make|build-tools:cc) ;;
        *) [ "$z8_requested" = "$name" ] || return 0 ;;
    esac
    local value remaining=$((z8_deadline - SECONDS))
    if ! command -v "$1" >/dev/null 2>&1; then printf '%s\t%s\n' "$name" '-'; return 0; fi
    if [ "$remaining" -le 0 ]; then printf '%s\t%s\n' "$name" '?'; return 0; fi
    local allowance=8
    # These launch language runtimes and scan many small package files under PRoot.
    case "$name" in pip|npm) allowance=30 ;; esac
    [ "$remaining" -le "$allowance" ] || remaining=$allowance
    if value=$(timeout -k 1 "$remaining" "$@" 2>&1); then
        value=${value%%$'\n'*}
        value=${value//$'\t'/ }
        if [ -n "${value//[[:space:]]/}" ]; then printf '%s\t%s\n' "$name" "${value:0:160}"; else printf '%s\t?\n' "$name"; fi
    else
        # A present custom/broken executable is unknown, never proven absent.
        printf '%s\t%s\n' "$name" '?'
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
z8_probe ssh ssh -V
z8_probe utilities bash -c 'for tool in curl wget rg fdfind fzf jq less nano tree file unzip zip ps; do command -v "$tool" >/dev/null || exit 1; done; jq --version'
z8_probe claude claude --version
z8_probe codex codex --version

# Distinguish an incomplete aggregate check from individual missing executables.
[ "$SECONDS" -lt "$z8_deadline" ] || exit 124
