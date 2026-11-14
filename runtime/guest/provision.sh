#!/bin/sh
# Offline base preparation. Optional tools require an explicit tool-manager action.
set -eu
fail() { printf '%s\n' "z8 guest: $*" >&2; exit 2; }
case "${1---dry-run}" in
    --dry-run) [ "$#" -le 1 ] || fail 'unexpected argument'; printf '%s\n' 'Prepare the embedded Linux shell and managed defaults. No downloads or package changes.'; exit 0 ;;
    --apply) [ "$#" -eq 1 ] || fail 'unexpected argument' ;;
    --help|-h) printf '%s\n' 'Usage: provision.sh [--dry-run | --apply]' 'Optional tools: tool-manager.sh --apply TOOL'; exit 0 ;;
    *) fail 'choose --dry-run or --apply' ;;
esac
[ "$(uname -s)" = Linux ] || fail '--apply requires a Linux guest'
[ -f /etc/z8/guest-target ] || fail 'missing guest image marker'
[ "$(cat /etc/z8/guest-target)" = z8-guest-v1 ] || fail 'unexpected guest image marker'
[ "$(id -u)" = 0 ] || fail 'run as root inside the guest'
[ -r /etc/os-release ] || fail 'missing guest operating system identity'
z8_distro=$(sed -n 's/^ID=//p' /etc/os-release | tr -d "\"'")
case "$z8_distro" in debian|ubuntu) ;; *) fail 'unsupported guest distribution' ;; esac
z8_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ -r "$z8_script_dir/shellrc" ] && [ -r "$z8_script_dir/welcome.sh" ] || fail 'missing managed defaults'
[ ! -L /etc/z8 ] || fail 'refusing linked setup state directory'
mkdir -p /etc/z8 /etc/profile.d /z8/home /workspace
z8_atomic_receipt() {
    z8_receipt=$1
    z8_pending=$(mktemp /etc/z8/.setup-receipt.XXXXXXXX) || return 1
    if cat > "$z8_pending" && mv -f -- "$z8_pending" "$z8_receipt"; then
        return 0
    fi
    rm -f -- "$z8_pending"
    return 1
}
z8_install_default() {
    z8_default=$1
    # Existing configuration belongs to the user, including dangling symlinks.
    [ ! -e "$z8_default" ] && [ ! -L "$z8_default" ] || return 0
    z8_pending=$(mktemp "${z8_default%/*}/.z8-default.XXXXXXXX") || return 1
    if ! cat > "$z8_pending" || ! chmod 0644 "$z8_pending"; then
        rm -f -- "$z8_pending"
        return 1
    fi
    # An atomic hard-link creation publishes the complete file only if the exact
    # destination is still absent. GNU -T also prevents following a new directory
    # or directory symlink created at that path while the temporary file is written.
    if ln -T -- "$z8_pending" "$z8_default"; then
        rm -f -- "$z8_pending"
        return 0
    fi
    rm -f -- "$z8_pending"
    [ -e "$z8_default" ] || [ -L "$z8_default" ]
}

# Legacy tools.ready is intentionally untouched. It belongs to the older full
# profile, while this receipt describes only the usable offline base shell.
printf '%s\n' 'Z8_SETUP:base'
z8_install_default /etc/z8/shellrc < "$z8_script_dir/shellrc"
z8_install_default /etc/z8/welcome.sh < "$z8_script_dir/welcome.sh"
z8_install_default /etc/profile.d/z8.sh <<'Z8_PROFILE'
if [ "${HOME-}" = /z8/home ] && [ -r /etc/z8/shellrc ]; then
    . /etc/z8/shellrc
fi
Z8_PROFILE
/bin/bash --noprofile --norc -c ':'
/usr/bin/env /bin/sh -c ':'
printf '%s\n' z8-base-v1 | z8_atomic_receipt /etc/z8/base.ready
printf '%s\n' 'The terminal is ready. Choose optional development tools from Tools.'
