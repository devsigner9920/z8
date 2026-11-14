#!/bin/bash
# Explicit per-project tool operation. No blanket distribution upgrade or removal.
set -euo pipefail
fail() { printf '%s\n' "Z8 Tools: $*" >&2; exit 2; }
[ "$#" -eq 2 ] || [ "$#" -eq 4 ] || fail 'Usage: tool-manager.sh --apply|--update TOOL [--version VERSION]'
mode=$1; tool=$2; version=
case "$mode" in --apply|--update) ;; *) fail 'unknown operation' ;; esac
if [ "$#" -eq 4 ]; then [ "$3" = --version ] || fail 'unknown option'; version=$4; fi
case "$tool" in
    python) packages=(python3 python3-pip python3-venv ca-certificates) ;;
    git) packages=(git ca-certificates) ;;
    node|codex) packages=(python3 ca-certificates) ;;
    claude) packages=(python3 ca-certificates gpgv) ;;
    gh) packages=(gh git python3 ca-certificates) ;;
    ssh) packages=(openssh-client ca-certificates) ;;
    build-tools) packages=(build-essential) ;;
    tmux) packages=(tmux) ;;
    utilities) packages=(bash-completion curl wget ripgrep fd-find fzf jq less nano tree file unzip zip procps ca-certificates) ;;
    *) fail 'unknown tool' ;;
esac
if [ "$mode" = --apply ] && [ -n "$version" ]; then fail 'Install uses the configured release; select Update for an explicit version'; fi
case "$mode:$tool" in
    --update:node|--update:codex|--update:claude) [ -n "$version" ] || fail 'Check the official release before updating' ;;
esac
if [ -n "$version" ]; then
    case "$tool" in
        node) [[ "$version" =~ ^v24\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})$ ]] || fail 'invalid Node version' ;;
        codex|claude) [[ "$version" =~ ^(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})$ ]] || fail 'invalid CLI version' ;;
        *) fail 'APT tool versions come from the configured distribution repository' ;;
    esac
fi
[ "$(uname -s)" = Linux ] && [ "$(id -u)" = 0 ] || fail 'run inside the prepared Linux guest'
[ -f /etc/z8/guest-target ] && [ ! -L /etc/z8/guest-target ] || fail 'missing guest marker'
[ "$(cat /etc/z8/guest-target)" = z8-guest-v1 ] || fail 'unexpected guest marker'
[ ! -L /etc/z8 ] || fail 'linked state directory is not supported'
[ -r /etc/os-release ] || fail 'missing distribution identity'
distro=$(sed -n 's/^ID=//p' /etc/os-release | tr -d "\"'")
case "$distro" in debian|ubuntu) ;; *) fail 'unsupported distribution' ;; esac
for command in apt-get dpkg-query dpkg flock; do command -v "$command" >/dev/null || fail "missing core command: $command"; done
[ ! -L /etc/z8/tool-manager.lock ] || fail 'linked operation lock is not supported'
exec 9>/etc/z8/tool-manager.lock
flock -n 9 || fail 'another tool operation is running in this project'
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export DISABLE_AUTOUPDATER=1
packages_valid() {
    inventory=$(dpkg-query -W -f='${Package}\t${db:Status-Status}\t${db:Status-Eflag}\t${Version}\n' "${packages[@]}") || return 1
    printf '%s\n' "$inventory" | awk -F '\t' -v expected="${#packages[@]}" '
        $2 != "installed" || $3 != "ok" || $4 == "" { bad=1 }
        END {exit bad || NR != expected}'
}
printf '%s\n' "Selected tool: $tool" 'Z8_SETUP:packages'
# A failed attempt keeps completed packages. A retry rechecks the live package
# database. APT's own locks stay intact; do not repair/remove unrelated packages.
if [ "$mode" = --update ] || ! packages_valid; then
    DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 -o Acquire::Languages=none update
    if ! DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 install -y --no-remove --no-install-recommends "${packages[@]}"; then
        printf '%s\n' 'The package operation did not finish. Completed packages and package-manager locks were preserved.' \
            'If dpkg reports an interrupted operation, open a recovery terminal and inspect: dpkg --audit' \
            'Review the affected selected packages/dependencies; configure those package names explicitly with dpkg --configure <package ...>, then Retry.' \
            'Z8 will not run a blanket upgrade, remove locks, or repair unrelated packages automatically.' >&2
        dpkg --audit >&2 || true
        exit 1
    fi
    packages_valid || fail 'selected package installation is incomplete; inspect the error and retry'
fi
case "$tool" in
    node)
        printf '%s\n' 'Z8_SETUP:node'
        if [ -n "$version" ]; then /usr/bin/python3 "$script_dir/install-node.py" --version "$version"
        else /usr/bin/python3 "$script_dir/install-node.py"; fi ;;
    codex|claude)
        if [ -n "$version" ]; then /bin/sh "$script_dir/install-ai.sh" --apply "$tool" --version "$version"
        else /bin/sh "$script_dir/install-ai.sh" --apply "$tool"; fi ;;
esac
printf '%s\n' 'Z8_SETUP:verify'
verified=$(/bin/bash "$script_dir/probe-tools.sh" "$tool") || fail 'tool verification did not finish'
printf '%s\n' "$verified" | awk -F '\t' '$2=="-" || $2=="?" || NF!=2 {bad=1} END{exit bad || NR==0}' || fail 'selected tool did not pass executable checks'
printf '%s\n' "$verified"
printf '%s\n' 'Selected tool is ready. Other tools and user configuration were not requested for upgrade.'
