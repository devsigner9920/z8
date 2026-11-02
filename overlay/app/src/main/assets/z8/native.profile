# Managed by the z8 APK. Loaded by the native runtime's etc/profile.
case $- in *i*) ;; *) return ;; esac
if [ -n "${PREFIX:-}" ] && [ -x "$PREFIX/bin/bash" ]; then
    SHELL="$PREFIX/bin/bash"; export SHELL
fi
# The minimal native bootstrap uses Android's standard utilities until a guest
# supplies its own GNU packages. Keep the app's binaries first.
case ":${PATH:-}:" in
    *:/system/bin:*) ;;
    *) PATH="${PATH:+$PATH:}/system/bin"; export PATH ;;
esac
alias ll >/dev/null 2>&1 || alias ll='ls -alF'
alias la >/dev/null 2>&1 || alias la='ls -A'
alias l >/dev/null 2>&1 || alias l='ls -CF'
alias .. >/dev/null 2>&1 || alias ..='cd ..'
alias ... >/dev/null 2>&1 || alias ...='cd ../..'
command -v cls >/dev/null 2>&1 || alias cls='clear'
if ! command -v mkcd >/dev/null 2>&1; then
    eval 'mkcd() {
        if [ "$#" -ne 1 ]; then printf "%s\n" "Usage: mkcd DIRECTORY" >&2; return 2; fi
        mkdir -p -- "$1" || return $?
        case "$1" in /*) cd -- "$1" ;; *) cd -- "./$1" ;; esac
    }'
fi
if ! command -v z8help >/dev/null 2>&1; then
    eval 'z8help() {
        printf "%s\n" "z8 native Android runtime" \
            "ll / la / l    list files" ".. / ...       parent directories" \
            "mkcd DIR       create and enter a directory" "cls            clear the terminal" \
            "HOME: $HOME" "/z8/home belongs to a separately installed project Linux environment."
    }'
fi
if [ "${Z8_SHOW_WELCOME:-}" = 1 ]; then
    unset Z8_SHOW_WELCOME
    if [ -t 1 ]; then
        case "${TERM:-dumb}" in
            dumb|'') printf '\n%s\n' '  [ Z8 ]  LOCAL' '  Welcome to Z8 Terminal' '  Android native runtime' '  ll  |  mkcd <dir>  |  z8help' ;;
            *) printf '\n\033[1;36m  [ Z8 ]\033[0m  \033[36mLOCAL\033[0m\n\033[1m  Welcome to Z8 Terminal\033[0m\n  Android native runtime\n\033[36m  ll  |  mkcd <dir>  |  z8help\033[0m\n' ;;
        esac
        printf '\n'
    fi
fi
