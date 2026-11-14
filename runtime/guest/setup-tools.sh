#!/bin/bash
# Historical entrypoint retained for interrupted setup and managed base preparation.
[ ! -r /etc/z8/welcome.sh ] || . /etc/z8/welcome.sh
printf '\n%s\n\n' 'Z8 · Preparing the local terminal'
if /bin/sh /usr/local/lib/z8/provision.sh --apply; then
    printf '%s\n' 'Terminal ready. Install optional tools from Tools when needed.'
else
    z8_status=$?
    printf '%s\n' "Setup stopped (exit $z8_status). Your source files are preserved."
    exit "$z8_status"
fi
