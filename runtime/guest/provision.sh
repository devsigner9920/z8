#!/bin/sh
# Resumable development-tool installation inside a marked z8 Linux guest.
set -eu

usage() {
    cat <<'USAGE'
Usage: sh runtime/guest/provision.sh [--dry-run | --apply] [--with-build-tools]

No arguments or --dry-run prints the plan without changing the system.
--apply installs packages and shell defaults inside a prepared z8 Linux guest.
The standard profile includes build-essential, Python pip/venv and Node LTS/npm.
--with-build-tools is retained as a compatibility alias.

Apply requires Linux, Debian or Ubuntu, guest root, and the exact text
z8-guest-v1 in /etc/z8/guest-target. The image builder must create this marker
inside the guest; never create it on the Android host or development machine.
USAGE
}

fail() {
    printf '%s\n' "z8 guest: $*" >&2
    exit 2
}

z8_mode=dry-run
z8_mode_set=false
z8_build_tools=false
for z8_arg in "$@"; do
    case "$z8_arg" in
        --dry-run|--apply)
            [ "$z8_mode_set" = false ] || fail 'choose exactly one execution mode'
            z8_mode=${z8_arg#--}
            z8_mode_set=true
            ;;
        --with-build-tools) z8_build_tools=true ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; fail "unknown argument: $z8_arg" ;;
    esac
done

z8_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
z8_package_file=$z8_script_dir/debian-base-packages.txt
[ -r "$z8_package_file" ] || fail "missing package list: $z8_package_file"
[ -r "$z8_script_dir/shellrc" ] || fail 'missing managed shell defaults'
[ -r "$z8_script_dir/welcome.sh" ] || fail 'missing managed welcome message'
set --
while IFS= read -r z8_package || [ -n "$z8_package" ]; do
    case "$z8_package" in
        ''|'#'*) continue ;;
        -*|*[!a-z0-9+.-]*) fail "invalid package name: $z8_package" ;;
    esac
    set -- "$@" "$z8_package"
done < "$z8_package_file"
[ "$#" -gt 0 ] || fail 'package list is empty'

printf '%s\n' 'Guest HOME and initial directory: /z8/home' \
    'Project source bind: /workspace (separate from HOME and rootfs)' \
    'Packages:'
printf '  %s\n' "$@"
if [ "$z8_mode" = dry-run ]; then
    printf '%s\n' 'Dry run: no packages or files were changed. See runtime/guest/README.md.'
    exit 0
fi

# Explicit image identity is an accidental-host-install guard, not a sandbox.
[ "$(uname -s)" = Linux ] || fail '--apply requires a Linux guest'
[ -f /etc/z8/guest-target ] || fail 'missing /etc/z8/guest-target image marker'
[ "$(cat /etc/z8/guest-target)" = z8-guest-v1 ] || fail 'unexpected guest image marker'
[ -r /etc/os-release ] || fail 'missing guest /etc/os-release'
z8_distro=$(sed -n 's/^ID=//p' /etc/os-release | tr -d "\"'")
case "$z8_distro" in
    debian|ubuntu) ;;
    *) fail "unsupported guest distribution: $z8_distro" ;;
esac
[ "$(id -u)" = 0 ] || fail 'run as root inside the guest'
command -v apt-get >/dev/null 2>&1 || fail 'apt-get is unavailable'

mkdir -p /etc/z8
[ ! -L /etc/z8 ] || fail 'refusing linked setup state directory'
# Receipts describe completed validation, never an intention to install. A killed
# attempt may leave a private temporary file; only rename publishes completion.
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
z8_packages_valid() {
    # One query avoids starting a process per package under PRoot. The live dpkg
    # database, not the prior receipt, determines whether this stage can be skipped.
    z8_installed=$(dpkg-query -W -f='${Package}\t${db:Status-Status}\t${db:Status-Eflag}\t${Version}\n' "$@") || return 1
    printf '%s\n' "$z8_installed" | awk -F '\t' -v expected="$#" '
        $2 != "installed" || $3 != "ok" || $4 == "" { invalid = 1 }
        END { exit invalid || NR != expected }
    ' || return 1
    z8_audit=$(dpkg --audit) || return 1
    [ -z "$z8_audit" ]
}

# An explicit repair must not leave an old final receipt looking successful.
rm -f -- /etc/z8/tools.ready
printf '%s\n' 'Z8_SETUP:packages'
if z8_packages_valid "$@"; then
    printf '%s\n' 'Previously installed packages verified; continuing from the next stage.'
else
    # Package-manager locks are never removed. A process killed mid-unpack may
    # need dependency repair before configure can finish. Never remove packages
    # to make that repair succeed; report the failure instead.
    z8_updated=false
    if ! DEBIAN_FRONTEND=noninteractive dpkg --configure -a; then
        DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 -o Acquire::Languages=none update
        z8_updated=true
        DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 install -f -y --no-remove --no-install-recommends
        DEBIAN_FRONTEND=noninteractive dpkg --configure -a
    fi
    if [ "$z8_updated" = false ]; then
        # Package-description translations are not needed by this headless profile.
        DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 -o Acquire::Languages=none update
    fi
    DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 install -y --no-remove --no-install-recommends "$@"
    z8_packages_valid "$@" || fail 'installed packages did not pass validation; setup can be retried'
fi
printf '%s\n' "$z8_installed" | z8_atomic_receipt /etc/z8/packages.ready

mkdir -p /etc/z8 /etc/profile.d /z8/home /workspace
z8_install_default /etc/z8/shellrc < "$z8_script_dir/shellrc"
z8_install_default /etc/z8/welcome.sh < "$z8_script_dir/welcome.sh"
z8_install_default /etc/profile.d/z8.sh <<'Z8_PROFILE'
if [ "${HOME-}" = /z8/home ] && [ -r /etc/z8/shellrc ]; then
    . /etc/z8/shellrc
fi
Z8_PROFILE

# User HOME and existing startup/config files are never changed by setup.
printf '%s\n' "$z8_installed" | awk -F '\t' '{ print $1 "\t" $4 }' | z8_atomic_receipt /etc/z8/packages.tsv
printf '%s\n' 'Z8_SETUP:node'
python3 "$z8_script_dir/install-node.py"
export PATH=/opt/z8/node/current/bin:$PATH
printf '%s\n' 'Z8_SETUP:verify'
python3 -m pip --version
python3 -c 'import venv, ensurepip'
node --version
npm --version
printf '%s\n' z8-tools-v2 | z8_atomic_receipt /etc/z8/tools.ready
printf '%s\n' 'Guest packages and shell defaults provisioned.' \
    'Launcher must set HOME=/z8/home and the initial working directory to /z8/home.'
