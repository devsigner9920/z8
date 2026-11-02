#!/bin/bash
# Fixed UI actions only. The terminal remains available after a tool exits.
[ ! -r /etc/z8/welcome.sh ] || . /etc/z8/welcome.sh
case "${1-}" in
    hooks-codex|hooks-claude)
        z8_tool=${1#hooks-}
        if [ -x /usr/bin/python3 ]; then
            /usr/bin/python3 /opt/z8/hooks/enable.py --apply "$z8_tool"
            z8_status=$?
        else
            printf '%s\n' 'Install the basic development tools first (Python 3 is required).'
            z8_status=127
        fi
        ;;
    setup-codex|setup-claude)
        z8_tool=${1#setup-}
        /bin/sh /usr/local/lib/z8/install-ai.sh --apply "$z8_tool"
        z8_status=$?
        ;;
    codex|claude)
        if type -P "$1" >/dev/null 2>&1; then
            if [ "$1" = codex ]; then
                if [ -x /usr/bin/python3 ] && [ -r /usr/local/lib/z8/codex-launch.py ]; then
                    z8_codex_binary=$(type -P codex)
                    case "$z8_codex_binary" in /*) ;; *) z8_codex_binary="$PWD/$z8_codex_binary" ;; esac
                    /usr/bin/python3 /usr/local/lib/z8/codex-launch.py "$z8_codex_binary"
                    z8_status=$?
                    printf '\n%s\n' "Z8 · codex finished (exit ${z8_status})."
                    exit "$z8_status"
                fi
                # Android/PRoot cannot reliably expose the shared daemon's
                # process-start metadata. Upstream's in-session mode keeps the
                # same approval and sandbox policy, without that daemon.
                printf '%s\n' 'Z8 · Codex runs in this terminal session.'
                z8_codex_arguments=()
                z8_codex_binary=$(type -P codex)
                if [ -x /usr/bin/timeout ] && [ -x /usr/bin/head ] &&
                        z8_codex_help=$(set -o pipefail; /usr/bin/timeout -k 1 3 "$z8_codex_binary" --help 2>/dev/null |
                            /usr/bin/head -c 131072); then
                    case "$z8_codex_help" in *--no-daemon*) z8_codex_arguments=(--no-daemon) ;; esac
                fi
                command codex "${z8_codex_arguments[@]}"
            else
                command claude
            fi
            z8_status=$?
        else
            printf '%s\n' "$1 is not installed in this project. Install it first."
            z8_status=127
        fi
        ;;
    github-auth)
        if [ -x /usr/bin/gh ]; then
            /usr/bin/gh auth login --hostname github.com --git-protocol https --web
            z8_status=$?
        else
            printf '%s\n' 'GitHub CLI is not installed. Install the basic development tools first.'
            z8_status=127
        fi
        ;;
    *) printf '%s\n' 'Unknown z8 terminal action.' >&2; exit 2 ;;
esac
printf '\n%s\n' "Z8 · ${1} finished (exit ${z8_status})."
exit "$z8_status"
