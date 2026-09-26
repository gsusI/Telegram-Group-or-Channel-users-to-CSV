#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
if [ -x ./telegram-csv-ui ]; then
    ./telegram-csv-ui "$@"
elif [ -x ./.ui-venv/bin/python ]; then
    ./.ui-venv/bin/python launch.py "$@"
elif [ -x ./.venv/bin/python ]; then
    ./.venv/bin/python launch.py "$@"
else
    python3 launch.py "$@"
fi
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nLaunch failed. Source installs need Python 3.10 or newer. Press Enter to close.\n'
    read -r answer
fi
exit "$result"
