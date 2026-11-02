# Managed z8 browser bridge. User shell startup files can override BROWSER later.
if [ "${HOME-}" = /z8/home ] && [ -n "${Z8_LAUNCH_ID-}" ]; then
    case ":${PATH-}:" in
        *:/usr/local/lib/z8/browser/bin:*) ;;
        *) PATH="/usr/local/lib/z8/browser/bin:${PATH:-/usr/local/bin:/usr/bin:/bin}"; export PATH ;;
    esac
    : "${BROWSER:=/usr/local/lib/z8/browser/bin/xdg-open}"
    : "${GH_BROWSER:=$BROWSER}"
    export BROWSER GH_BROWSER
fi
