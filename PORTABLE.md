# Telegram CSV portable UI

Extract the entire archive into a writable folder before starting.

- Windows: double-click **Start Telegram CSV.bat**.
- macOS: double-click **Start Telegram CSV.command**.
- Linux: run `./telegram-csv-ui` from the extracted folder.

The browser opens automatically. Keep the launcher window open; Ctrl+C stops the app.
Closing a browser tab does not stop the launcher. If the browser does not open, copy
the local URL printed in the launcher window.

Platform release folders include Python and dependencies. Choose the archive for
your operating system and CPU. Keep `_internal` beside the executable. These builds
are unsigned; your operating system may require approval. Linux builds require a
compatible glibc system (Ubuntu 22.04 or newer is the build baseline).

Sessions and exports go into `data` beside the executable. Move that folder with the
app to retain them, and protect it as you would a password. API credentials entered
in the browser are not saved. An existing TELEGRAM_SESSION environment variable
overrides the portable session path. To choose another folder, run
`telegram-csv-ui --data-dir /path/to/folder`. Use `--no-browser` for manual browser
startup and `--port 8501` to request a fixed port.

Source checkout: use the same Windows/macOS shortcuts, or `python3 launch.py` on
Linux. Python 3.10+ and an internet connection are needed for the initial dependency
installation. The local `.ui-venv` environment is not portable: when moving source
to another OS or computer, omit it so the launcher can create a fresh environment.

In the app, enter your API credentials from https://my.telegram.org/apps, sign in,
load your chats, select a chat, and export. Telegram decides which members are
visible. Local tools work without signing in.
