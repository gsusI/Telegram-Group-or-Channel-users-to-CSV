#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
packaged=0
if [ -x ./telegram-csv-ui ]; then
    packaged=1
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
    if [ "$packaged" -eq 1 ]; then
        printf '\nThe bundled app could not start (exit %s). Python is already included.\n' "$result"
        if [ "$result" -eq 137 ]; then
            printf 'macOS terminated the app. This may be a security block; it is not a missing Python dependency.\n'
        fi
        printf 'Report this failure with your macOS version and release filename:\nhttps://github.com/gsusI/Telegram-Group-or-Channel-users-to-CSV/issues\n'
    else
        printf '\nSource launch failed (exit %s). Source installs require Python 3.10 or newer.\n' "$result"
    fi
    if [ -t 0 ]; then
        printf 'Press Enter to close.\n'
        read -r answer
    fi
fi
exit "$result"
