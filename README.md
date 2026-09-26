# Telegram members to CSV

Export members visible to your Telegram account from a group or channel. You can also validate a CSV and invite its users to a basic group, supergroup, or channel. Telegram controls which members you can see and who you can invite; an export may be incomplete even when the command succeeds.

Requires a Telegram user account and API credentials from [my.telegram.org](https://my.telegram.org/apps). Use Python 3.10 or newer, or download a standalone executable from [Releases](https://github.com/gsusI/Telegram-Group-or-Channel-users-to-CSV/releases). Windows x64, Linux x64, macOS Intel, and macOS Apple Silicon builds are produced for each release. Builds are unsigned; source installation remains available on every platform.

**Quick start:** install or download, set `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`, run the local browser UI or use the commands below. Standalone builds use the command interface without `python` and without the `.py` extension. QR login does not remove the API credential requirement.

## Launch the portable UI

For a source checkout, double-click **Start Telegram CSV.bat** on Windows or
**Start Telegram CSV.command** on macOS. On Linux, run `python3 launch.py`.
The launcher opens your browser, chooses an available local port, and uses the
`data` folder beside the app for sessions and exports. Source startup requires
Python 3.10+; if UI dependencies are missing it creates `.ui-venv` and installs them
on first launch. Keep the launcher window open while using the app.

The release workflow also builds `telegram-csv-ui-*` archives containing Python
and all UI dependencies for Windows x64, Linux x64, macOS Intel and Apple Silicon.
Extract the entire matching archive, then use its launch shortcut or executable.
Download the portable UI from [Releases](https://github.com/gsusI/Telegram-Group-or-Channel-users-to-CSV/releases/latest).
Choose a filename beginning with `telegram-csv-ui-`; filenames without `-ui` are terminal tools.
See [PORTABLE.md](PORTABLE.md) for platform limits,
moving the app, choosing a data folder, and manual browser startup.

```sh
python3 launch.py
# Optional: use another writable data folder or open the browser yourself
python3 launch.py --data-dir /path/to/data --no-browser
```

## Manual UI installation

The Streamlit UI covers account sign-in, single or batch exports, recovery checkpoints, local comparison/deduplication, and permission-based invitations. It binds to `127.0.0.1`, keeps credentials in the local process, and stores Telegram's session on this computer. CSV previews omit access hashes.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-ui.txt
.venv/bin/python -m streamlit run telegram_csv_ui.py
```

On Windows, use `.venv\Scripts\python.exe` in the final two commands. Enter the API ID and API hash from [my.telegram.org](https://my.telegram.org/apps), then use **Send login code**, **Load my chats**, and **Export selected chats**. The API values can instead come from the existing `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and optional `TELEGRAM_PHONE` environment variables. Direct `streamlit run` uses the CLI's default session location; use `launch.py` for portable session storage.

Release archives contain `telegram-csv` (macOS/Linux) or `telegram-csv.exe` (Windows). Extract one archive and run `./telegram-csv doctor` in a macOS/Linux terminal or `.\telegram-csv.exe doctor` in PowerShell. The macOS builds are not notarized, so macOS may ask you to approve first launch. Linux builds target x64 systems compatible with the GitHub Ubuntu runner; use Python source installation if your distribution cannot run that binary.

## Existing usage remains supported

The original script still opens its numbered menu. Pass a CSV path before the menu for options 2 and 3:

```sh
python telethon-bot-add-users-to-groups.py
python telethon-bot-add-users-to-groups.py members.csv
```

Menu option 1 exports to the original `members-GROUP-NAME.csv` filename with the original `username,user id,access hash,name,group,group id` header. It replaces that file, as before. Option 2 lists basic groups, supergroups, and broadcast channels, prompts for username or ID mode, and sends invitations; the menu choice is the authorization for that action. Your account needs permission to invite users to the selected chat. Option 3 displays the CSV. Existing credentials can still be entered by editing `api_id`, `api_hash`, and `phone` near the top of the original script. When a real phone is configured there, its old session filename is reused. Environment variables override those values.

## Install

In PowerShell on Windows:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

In a macOS or Linux terminal:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Set credentials for your current terminal session. On Windows PowerShell:

```powershell
$env:TELEGRAM_API_ID = "123456"
$env:TELEGRAM_API_HASH = "your_api_hash"
$env:TELEGRAM_PHONE = "+34123456789"
```

On macOS/Linux:

```sh
export TELEGRAM_API_ID=123456
export TELEGRAM_API_HASH=your_api_hash
export TELEGRAM_PHONE=+34123456789
```

`TELEGRAM_PHONE` is optional; normal login prompts for it if absent. First connection also prompts for Telegram login code and, if enabled, account password. QR login displays a short-lived code in your terminal for Telegram's **Settings > Devices > Link Desktop Device** screen; it also supports a 2FA password. Do not commit credentials or session file. New command interface stores its session in `~/.telegram-group-csv/session.session` by default. Original menu reuses the old phone-named session file when a phone is configured. Set `TELEGRAM_SESSION` to another path if needed; protect that file as you would a login token. Git ignores environment files, sessions, checkpoints, and CSV exports, including exports with custom filenames. Never force-add them.

Commands below use `python`; substitute `.venv\Scripts\python.exe` on Windows or `.venv/bin/python` on macOS/Linux. These subcommands are additional interface; the original script also accepts them.

```sh
python telegram_csv.py doctor       # local checks only; prints no secret values
python telegram_csv.py login --qr   # or: login, for phone/code sign-in
```

## Export

```sh
python telegram_csv.py dialogs
python telegram_csv.py export CHAT_ID
python telegram_csv.py export CHAT_ID --output members.csv
python telegram_csv.py export CHAT_ID --resumable
python telegram_csv.py export CHAT_ID --resumable --resume
python telegram_csv.py export-many CHAT_ID_1 CHAT_ID_2 --output-dir exports
```

`dialogs` lists group and channel IDs, including those beyond first page. `export` also accepts exact chat title or public username. Output defaults to `members-NAME-ID.csv` in current directory. Use `--overwrite` to replace an existing file. If a fetch fails, existing output remains intact and temporary output is removed. If Telegram requires admin access to list members, the command reports that requirement and does not replace the output.

CSV columns are `username,user_id,user_access_hash,name,group,group_id`. File is UTF-8 with a BOM so spreadsheet apps, including Excel on Windows, read names correctly. Access hashes are account-bound authorization data: keep exports private. The success message reports **visible** members and, when available, Telegram's displayed chat count. These counts can differ; completeness is unknown. Telegram may withhold participants even from an admin; `0` rows or fewer rows than displayed member count do not prove a bug in this tool. Joined private groups work when Telegram permits your account to list their members.

`--resumable` keeps a private SQLite checkpoint beside the requested CSV (`members.csv.checkpoint.sqlite`). If Telegram interrupts the scan, your existing CSV stays intact. `--resume` scans Telegram again and deduplicates by user ID against the saved observations. The checkpoint is tied to the same chat and Telegram account. Telegram does not promise a stable page position, so this does **not** jump directly to the interruption point or prove that every member is present. On success, the CSV replaces the requested output atomically and the checkpoint is deleted. Use `--overwrite` as well if an older completed CSV already exists. `export-many` processes explicitly named chats independently and reports each result; it returns a failure code if any chat fails. Add `--resumable` and `--resume` there for the same checkpoint behavior. A resumed batch skips already completed files unless `--overwrite` is set.

## Compare exports locally

```sh
python telegram_csv.py diff earlier.csv later.csv --output changes.csv
python telegram_csv.py dedupe group-a.csv group-b.csv --output unique.csv
```

These commands do not connect to Telegram. `diff` requires two exports of the same chat and writes `newly_observed` and `no_longer_visible` rows. Missing from a later export does **not** prove a member left: Telegram may have changed visibility. `dedupe` writes one row per user ID across files, with the observed chat IDs; it omits access hashes and cannot be used for ID-based invitations. Neither command overwrites an existing output file. CSV exports and local analysis files contain personal data; keep them private.

Example with invented IDs: export chat `123`, export it again later, then run `diff` on the two files. A result `42,new_user,123,newly_observed` means user 42 appeared in the later visible list. It does not establish their join date.

## Invite users

**Account risk:** Unwanted or repeated invitations can restrict or ban your Telegram account. A 60-second delay does not make an invite run safe. Invite only people who expect to be added. If Telegram limits your account, stop; do not rotate accounts or automate retries to evade the limit. Telegram alone decides restrictions and appeals. See [Telegram's API policy](https://core.telegram.org/api/obtaining_api_id) and [spam FAQ](https://telegram.org/faq_spam).

CSV can contain one username per line, `username,user_id,user_access_hash`, or full exported format. Header row is optional; data's first row is never discarded.

```sh
python telegram_csv.py preview members.csv
python telegram_csv.py invite CHAT_ID members.csv
python telegram_csv.py invite CHAT_ID members.csv --execute
python telegram_csv.py invite CHAT_ID members.csv --execute --progress invite-progress.csv
python telegram_csv.py invite CHAT_ID members.csv --execute --progress invite-progress.csv --resume
```

`invite` without `--execute` validates input only and does not connect to Telegram. Actual invitations require `--execute` and default to a 60-second delay between attempts. `--delay N` changes delay. Tool stops on Telegram flood errors; retries and account restrictions remain Telegram's decision. `user_id` plus `user_access_hash` work only when valid for signed-in account. Telegram can return a completed request with `missing_invitees`; those users are reported as not invited, not counted as successes.

Basic groups use Telegram's `messages.addChatUser` method with no chat-history forwarding. Supergroups and channels use `channels.inviteToChannel`. Both use the same CSV format and progress options. A basic group is selected by its ID or exact title; Telegram does not assign public usernames to basic groups.

`--progress PATH.csv` is optional. It writes each confirmed outcome immediately to a private CSV checkpoint. Existing progress files are never overwritten without `--resume`. Resume requires the same chat and skips every recorded outcome, including declined and privacy-blocked users; it does not retry them. An invite interrupted between Telegram's response and checkpoint write can have an unknown outcome: check membership before explicitly resuming. After a flood error, wait for Telegram's restriction to clear before resuming. Progress CSVs contain user identifiers, are ignored by Git, and should be kept private. The original numbered menu still works without a checkpoint.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests use fake Telegram clients and do not sign in or send invitations. GitHub Actions runs them on Windows, macOS, and Linux. Live Telegram test needs your own account credentials and a group/channel where you have permission; it is not part of CI.
