#!/data/data/dev.devsigner.z8/files/usr/bin/bash -p
# Own-prefix PRoot launcher. Call with `bash -p launch.sh ...` when not executable.
# -p prevents inherited BASH_ENV/functions from running before this script.
set -eu

fail() { printf '%s\n' "z8 guest: $*" >&2; exit 2; }
usage() {
    cat <<'USAGE'
Usage: bash -p runtime/guest/launch.sh [--dry-run|--run]
  --rootfs PATH --home PATH --source PATH --temp PATH [--cwd /z8/home|/workspace/...]
  [--hooks-transport PATH] [-- COMMAND ARG...]

Default is dry-run. All four host directories must already exist and be distinct.
HOME is /z8/home, source is /workspace, temporary files belong to this environment.
The installed own-prefix proot and Android execution are required only for --run.
No HOME, project, environment or package is deleted/reset/installed by this script.
USAGE
}

z8_mode=dry-run
z8_rootfs= z8_guest_home= z8_source= z8_temp= z8_hooks=
z8_cwd=/z8/home
while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) z8_mode=dry-run; shift ;;
        --run) z8_mode=run; shift ;;
        --rootfs|--home|--source|--temp|--cwd|--hooks-transport)
            [ "$#" -ge 2 ] || fail "missing value for $1"
            case "$1" in
                --rootfs) z8_rootfs=$2 ;;
                --home) z8_guest_home=$2 ;;
                --source) z8_source=$2 ;;
                --temp) z8_temp=$2 ;;
                --cwd) z8_cwd=$2 ;;
                --hooks-transport) z8_hooks=$2 ;;
            esac
            shift 2 ;;
        --help|-h) usage; exit 0 ;;
        --) shift; break ;;
        *) fail "unknown launcher option: $1" ;;
    esac
done
[ -n "$z8_rootfs" ] && [ -n "$z8_guest_home" ] && [ -n "$z8_source" ] && [ -n "$z8_temp" ] || { usage; fail 'all storage paths are required'; }

# Reject PRoot bind delimiters/control characters; quoting preserves ordinary
# spaces and punctuation without building shell command strings.
canonical_directory() {
    case "$1" in
        /*) ;;
        *) fail 'storage paths must be absolute' ;;
    esac
    case "$1" in
        *:*|*'!'*|*$'\n'*|*$'\r'*) fail 'unsupported character in storage path' ;;
    esac
    [ ! -L "$1" ] && [ -d "$1" ] || fail 'storage path must be an existing real directory'
    (CDPATH= cd -P -- "$1" && pwd -P)
}
z8_rootfs=$(canonical_directory "$z8_rootfs")
z8_guest_home=$(canonical_directory "$z8_guest_home")
z8_source=$(canonical_directory "$z8_source")
z8_temp=$(canonical_directory "$z8_temp")
z8_paths=("$z8_rootfs" "$z8_guest_home" "$z8_source" "$z8_temp")
for ((z8_i=0; z8_i<4; z8_i++)); do
    [ "${z8_paths[z8_i]}" != / ] || fail 'host root cannot be a project storage directory'
    for ((z8_j=z8_i+1; z8_j<4; z8_j++)); do
        case "${z8_paths[z8_i]}/" in "${z8_paths[z8_j]}/"*) fail 'storage directories must not overlap' ;; esac
        case "${z8_paths[z8_j]}/" in "${z8_paths[z8_i]}/"*) fail 'storage directories must not overlap' ;; esac
    done
done
[ -f "$z8_rootfs/etc/z8/guest-target" ] && [ ! -L "$z8_rootfs/etc/z8/guest-target" ] && [ "$(cat "$z8_rootfs/etc/z8/guest-target")" = z8-guest-v1 ] || fail 'unrecognized guest rootfs marker'
for z8_mount in dev dev/pts dev/shm proc tmp run run/z8 run/z8/attention z8 z8/home workspace; do
    [ -d "$z8_rootfs/$z8_mount" ] && [ ! -L "$z8_rootfs/$z8_mount" ] || fail "guest mount point unavailable: $z8_mount"
done
case "$z8_cwd" in
    /z8/home|/workspace|/workspace/*) ;;
    *) fail 'initial cwd must be /z8/home or under /workspace' ;;
esac
case "$z8_cwd" in *'/../'*|*/..|*'/./'*|*/.|*'//'*) fail 'initial cwd must be normalized' ;; esac
if [ "$z8_cwd" != /z8/home ]; then
    z8_relative=${z8_cwd#/workspace}
    z8_actual=$(canonical_directory "$z8_source$z8_relative")
    case "$z8_actual/" in "$z8_source/"*) ;; *) fail 'initial directory escapes the source bind' ;; esac
fi
[ ! -L "$z8_temp/shm" ] || fail 'temporary shared memory directory is a symlink'

z8_prefix=/data/data/dev.devsigner.z8/files/usr
z8_proot=$z8_prefix/bin/proot
# -r is intentional. -R/-S implicitly expose host HOME, /etc and other paths.
# --kill-on-exit closes children only when this session's main shell actually
# exits; UI detach must leave this process alive in the service/tmux session.
z8_args=("$z8_proot" --kill-on-exit --link2symlink -0 -r "$z8_rootfs"
    -b "$z8_guest_home:/z8/home" -b "$z8_source:/workspace"
    -b "$z8_temp:/tmp" -b "$z8_temp/shm:/dev/shm"
    -b /proc:/proc -b /dev/pts:/dev/pts)
for z8_device in null zero random urandom tty ptmx; do
    z8_args+=(-b "/dev/$z8_device:/dev/$z8_device")
done
if [ -n "$z8_hooks" ]; then
    z8_hooks=$(canonical_directory "$z8_hooks")
    [ "${z8_hooks##*/}" = transport ] || fail 'bind only the dedicated hook transport directory'
    [[ ${Z8_LAUNCH_ID-} =~ ^[A-Za-z0-9_.:-]{1,160}$ ]] && [[ ${Z8_EVENT_TOKEN-} =~ ^[a-f0-9]{64}$ ]] || fail 'hook launch credentials are absent or malformed'
    z8_args+=(-b "$z8_hooks:/run/z8/attention")
fi
z8_args+=(-w "$z8_cwd")
if [ "$#" -eq 0 ]; then
    z8_args+=(/bin/bash --login)
else
    case "$1" in /*) ;; *) fail 'guest command path must be absolute' ;; esac
    z8_args+=("$@")
fi
if [ "$z8_mode" = dry-run ]; then
    printf '%s\n' 'DRY_RUN: no guest or filesystem changes.' 'Argument vector (no credentials):'
    printf '  %q\n' "${z8_args[@]}"
    printf '%s\n' 'Environment: HOME=/z8/home; USER/LOGNAME=root; PATH=guest Linux directories; LANG=C.UTF-8; TERM=xterm-256color.'
    [ -z "$z8_hooks" ] || printf '%s\n' 'Hook nonce and launch ID stay in inherited environment; socket path becomes /run/z8/attention/events.sock.'
    exit 0
fi
[ -x "$z8_proot" ] || fail 'own-prefix proot is not installed'
[ "$(uname -s)" = Linux ] || fail 'guest execution requires Android/Linux'
for z8_device in null zero random urandom tty ptmx; do
    [ -e "/dev/$z8_device" ] || fail "required host device unavailable: $z8_device"
done
[ -d /proc ] && [ -d /dev/pts ] || fail 'required host process/PTY interfaces unavailable'
mkdir -p -- "$z8_temp/shm"
# Drop exported host configuration without serializing secrets to argv, logs,
# generated source or a credential file. Variables remain private shell values
# until the small explicit whitelist is exported for the new process.
for z8_exported in $(compgen -e); do export -n "$z8_exported"; done
export HOME=/z8/home USER=root LOGNAME=root SHELL=/bin/bash LANG=C.UTF-8 TERM=xterm-256color
export PATH=/usr/local/lib/z8/browser/bin:/z8/home/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export BROWSER=/usr/local/lib/z8/browser/bin/xdg-open GH_BROWSER=/usr/local/lib/z8/browser/bin/xdg-open
export TMPDIR=/tmp Z8_SHOW_WELCOME=1
# PRoot may need host temporary storage before guest path translation exists.
export PROOT_TMP_DIR="$z8_temp"
if [ -n "$z8_hooks" ]; then
    export Z8_LAUNCH_ID Z8_EVENT_TOKEN
    export Z8_EVENT_SOCKET=/run/z8/attention/events.sock
fi
exec "${z8_args[@]}"
