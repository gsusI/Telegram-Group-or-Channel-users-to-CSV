# Telegram members to CSV

Export members visible to your Telegram account from a group or channel. You can also validate a CSV and invite its users to a supergroup or channel. Telegram controls which members you can see and who you can invite; an export may be incomplete even when the command succeeds.

Requires Python 3.10 or newer, a Telegram user account, and API credentials from [my.telegram.org](https://my.telegram.org/apps). This tool uses Telethon 1.x. It works with Python on Windows, macOS, and Linux; no shell-specific code is required.

## Existing usage remains supported

The original script still opens its numbered menu. Pass a CSV path before the menu for options 2 and 3:

```sh
python telethon-bot-add-users-to-groups.py
python telethon-bot-add-users-to-groups.py members.csv
```

Menu option 1 exports to the original `members-GROUP-NAME.csv` filename with the original `username,user id,access hash,name,group,group id` header. It replaces that file, as before. Option 2 prompts for username or ID mode and sends invitations; the menu choice is the authorization for that action. Option 3 displays the CSV. Existing credentials can still be entered by editing `api_id`, `api_hash`, and `phone` near the top of the original script. When a real phone is configured there, its old session filename is reused. Environment variables override those values.

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

`TELEGRAM_PHONE` is optional; tool prompts for it if absent. First connection also prompts for Telegram login code and, if enabled, account password. Do not commit credentials or session file. New command interface stores its session in `~/.telegram-group-csv/session.session` by default. Original menu reuses the old phone-named session file when a phone is configured. Set `TELEGRAM_SESSION` to another path if needed; protect that file as you would a login token. Git ignores environment files, sessions, and CSV exports, including exports with custom filenames. Never force-add them.

Commands below use `python`; substitute `.venv\Scripts\python.exe` on Windows or `.venv/bin/python` on macOS/Linux. These subcommands are additional interface; the original script also accepts them.

## Export

```sh
python telegram_csv.py dialogs
python telegram_csv.py export CHAT_ID
python telegram_csv.py export CHAT_ID --output members.csv
```

`dialogs` lists group and channel IDs, including those beyond first page. `export` also accepts exact chat title or public username. Output defaults to `members-NAME-ID.csv` in current directory. Use `--overwrite` to replace an existing file. If a fetch fails, existing output remains intact and temporary output is removed.

CSV columns are `username,user_id,user_access_hash,name,group,group_id`. File is UTF-8 with a BOM so spreadsheet apps, including Excel on Windows, read names correctly. Access hashes are account-bound authorization data: keep exports private. Telegram may withhold participants even from an admin; `0` rows or fewer rows than displayed member count do not prove a bug in this tool.

## Invite users

Use this only for members you are authorized to invite. Telegram privacy and rate limits still apply. CSV can contain one username per line, `username,user_id,user_access_hash`, or full exported format. Header row is optional; data's first row is never discarded.

```sh
python telegram_csv.py preview members.csv
python telegram_csv.py invite CHAT_ID members.csv
python telegram_csv.py invite CHAT_ID members.csv --execute
```

`invite` without `--execute` validates input only and does not connect to Telegram. Actual invitations require `--execute` and default to a 60-second delay between successful invitations. `--delay N` changes delay. Tool stops on Telegram flood errors; retries and account restrictions remain Telegram's decision. `user_id` plus `user_access_hash` work only when valid for signed-in account.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests use fake Telegram clients and do not sign in or send invitations. GitHub Actions runs them on Windows, macOS, and Linux. Live Telegram test needs your own account credentials and a group/channel where you have permission; it is not part of CI.
