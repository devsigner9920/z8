# Sourced by new interactive shells and explicit CLI launchers, once per launch.
if [ "${Z8_SHOW_WELCOME:-}" = 1 ]; then
    unset Z8_SHOW_WELCOME
    if [ -t 1 ]; then
        case "${TERM:-dumb}" in
            dumb|'') printf '\n%s\n' '  [ Z8 ]  LOCAL' '  Welcome to Z8 Terminal' '  Your project. Your space.' '  ll  |  mkcd <dir>  |  /workspace' ;;
            *) printf '\n\033[1;36m  [ Z8 ]\033[0m  \033[36mLOCAL\033[0m\n\033[1m  Welcome to Z8 Terminal\033[0m\n  Your project. Your space.\n\033[36m  ll  |  mkcd <dir>  |  /workspace\033[0m\n' ;;
        esac
        printf '\n'
    fi
fi
