#!/bin/bash
# Service-owned setup exits with its real result; a retry validates and reuses
# completed package/Node stages without changing source or HOME.
[ ! -r /etc/z8/welcome.sh ] || . /etc/z8/welcome.sh
printf '\n%s\n\n' 'Z8 · Preparing development tools in this project'
z8_status=0
if /bin/sh /usr/local/lib/z8/provision.sh --apply; then
    printf '\n%s\n' 'Development tools are ready. Package versions: /etc/z8/packages.tsv'
else
    z8_status=$?
    printf '\n%s\n' "Setup stopped (exit $z8_status). Your source files are preserved."
    printf '%s\n' 'Completed stages are preserved. Setup will validate them before continuing.'
fi
exit "$z8_status"
