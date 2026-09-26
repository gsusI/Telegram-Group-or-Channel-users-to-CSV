# Telegram CSV portable UI

Extract the entire archive into a writable folder before starting.

- Windows: double-click **Start Telegram CSV.bat**.
- macOS: double-click **Telegram CSV.app**. Do not use the old `.command` launcher.
- Linux: run `./telegram-csv-ui` from the extracted folder.

The browser opens automatically. On macOS, use the **Telegram CSV** menu-bar item
to reopen the browser, open the data folder, or quit the app and its local server.
On Windows/Linux, keep the launcher window open; Ctrl+C stops the app.
Closing a browser tab does not stop the launcher. If the browser does not open,
use **Open Telegram CSV** in the Mac menu bar, or copy the local URL printed in
the Windows/Linux launcher window.

Platform release folders include Python and dependencies. Choose the archive for
your operating system and CPU. On Windows/Linux, keep `_internal` beside the executable. These builds
are unsigned; your operating system may require approval. Linux builds require a
compatible glibc system (Ubuntu 22.04 or newer is the build baseline).

On macOS, approve **Telegram CSV.app** in System Settings → Privacy & Security →
Open Anyway if macOS blocks it. The release contains one sealed application bundle,
not a script followed by a separately approved executable. macOS normally remembers
an exception for that unchanged app; replacing it with a new release, managed-device
policies, or additional privacy permissions can require approval again. This is not
an Apple-notarized build. The app never disables Gatekeeper or strips quarantine.

On macOS, sessions, exports and `launcher.log` live in
`~/Library/Application Support/Telegram CSV`, outside the sealed application and
Downloads folder. Use the menu's **Open data folder** to find or transfer them.
Existing `data` from the old release is not automatically moved: quit both versions
and copy its contents there if you want to retain your session and exports.
`TELEGRAM_CSV_DATA_DIR` can select another location. The app itself needs no Python
installation. Do not modify files inside `.app` after approving it.

On Windows/Linux, sessions and exports go into `data` beside the executable. Move that folder with the
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
