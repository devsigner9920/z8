# Application-managed compatibility for interactive project Bash sessions.
# Do not edit user startup files, npm launchers or credentials. Local execution
# policy is selected explicitly by the user in the managed first-run adapter.
[ "${HOME-}" = /z8/home ] && [ -n "${BASH_VERSION-}" ] || return 0
case $- in *i*) ;; *) return 0 ;; esac

if ! alias codex >/dev/null 2>&1 && ! declare -F codex >/dev/null 2>&1; then
    # Quoted definition: an existing alias must not expand while sourcing this
    # file, even when the condition above prevents installing the function.
    eval 'codex() {
        # Exporting this function supports nested interactive Bash, but scripts
        # and shells outside the project retain ordinary executable behavior.
        case $- in
            *i*) [ "${HOME-}" = /z8/home ] || { command codex "$@"; return $?; } ;;
            *) command codex "$@"; return $? ;;
        esac
        local z8_arg z8_binary z8_help
        for z8_arg in "$@"; do
            case "$z8_arg" in
                --) break ;;
                --remote|--remote=*|--no-daemon|--no-daemon=*|--help|-h|--version|-V)
                    command codex "$@"; return $? ;;
                app-server|exec-server|remote-control)
                    # Explicit server-management commands own their lifecycle.
                    command codex "$@"; return $? ;;
            esac
        done
        z8_binary=$(type -P codex) || { command codex "$@"; return $?; }
        case "$z8_binary" in /*) ;; *) z8_binary="$PWD/$z8_binary" ;; esac
        if [ -x /usr/bin/python3 ] && [ -r /usr/local/lib/z8/codex-launch.py ]; then
            /usr/bin/python3 /usr/local/lib/z8/codex-launch.py "$z8_binary" "$@"
            return $?
        fi
        # Check the selected installation on demand, so npm updates and older
        # releases work without stale version guesses or startup-time work.
        if [ -x /usr/bin/timeout ] && [ -x /usr/bin/head ] &&
                z8_help=$(set -o pipefail; /usr/bin/timeout -k 1 3 "$z8_binary" --help 2>/dev/null |
                    /usr/bin/head -c 131072); then
            case "$z8_help" in
                *--no-daemon*) command codex --no-daemon "$@"; return $? ;;
            esac
        fi
        command codex "$@"
    }'
    export -f codex
fi
