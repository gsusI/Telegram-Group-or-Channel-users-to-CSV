"""Export visible Telegram participants and invite users from CSV."""

import argparse
import csv
import itertools
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


CSV_COLUMNS = ("username", "user_id", "user_access_hash", "name", "group", "group_id")
LEGACY_CSV_COLUMNS = ("username", "user id", "access hash", "name", "group", "group id")
PROGRESS_COLUMNS = ("chat_id", "user_id", "username", "status")
COMMANDS = {"dialogs", "export", "preview", "invite"}


@dataclass(frozen=True)
class Invitee:
    username: str = ""
    user_id: int | None = None
    access_hash: int | None = None


def _column_name(value):
    return re.sub(r"[\s_-]+", "", value.strip().lower().lstrip("\ufeff"))


def read_invitees(path):
    """Accept username-only, ID/hash, or this tool's exported CSV."""
    invitees = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as source:
        rows = csv.reader(source)
        first = next(rows, None)
        if first is None:
            raise ValueError("CSV file is empty")
        names = [_column_name(cell) for cell in first]
        has_header = bool(set(names) & {"username", "userid", "useraccesshash"})
        if has_header:
            if len(names) != len(set(names)):
                raise ValueError("CSV header has duplicate columns")
            indexes = {name: index for index, name in enumerate(names)}
            numbered_rows = enumerate(rows, start=2)
        else:
            indexes = {"username": 0, "userid": 1, "useraccesshash": 2}
            numbered_rows = enumerate(itertools.chain([first], rows), start=1)

        for line, row in numbered_rows:
            if not row or not any(cell.strip() for cell in row):
                continue

            def cell(name):
                index = indexes.get(name)
                return row[index].strip() if index is not None and index < len(row) else ""

            username = cell("username").lstrip("@")
            raw_id = cell("userid")
            raw_hash = cell("useraccesshash") or cell("accesshash")
            if not username and not (raw_id and raw_hash):
                raise ValueError(f"CSV line {line}: expected username or user ID and access hash")
            try:
                user_id = int(raw_id) if raw_id else None
                access_hash = int(raw_hash) if raw_hash else None
            except ValueError as error:
                raise ValueError(f"CSV line {line}: user ID and access hash must be integers") from error
            if (user_id is None) != (access_hash is None):
                raise ValueError(f"CSV line {line}: user ID and access hash must occur together")
            invitees.append(Invitee(username, user_id, access_hash))
    if not invitees:
        raise ValueError("CSV file contains no users")
    return invitees


def dialogs(client):
    """Return all group/channel dialogs, without old 10/200 item limit."""
    return [dialog for dialog in client.iter_dialogs() if dialog.is_group or dialog.is_channel]


def resolve_chat(client, reference):
    matches = [dialog.entity for dialog in dialogs(client)
               if str(dialog.id) == reference or dialog.name == reference]
    if len(matches) > 1:
        raise ValueError(f"Multiple chats named {reference!r}; use an ID from 'dialogs'")
    if matches:
        return matches[0]
    return client.get_entity(reference)


def default_output(chat):
    slug = re.sub(r"[^a-z0-9]+", "-", (chat.title or "chat").lower()).strip("-") or "chat"
    return Path(f"members-{slug}-{chat.id}.csv")


def legacy_output(chat):
    slug = re.sub("-+", "-", re.sub("[^a-zA-Z]", "-", chat.title.lower()))
    return Path(f"members-{slug}.csv")


def export_members(client, chat, output, overwrite=False, legacy=False):
    """Write a complete response atomically; Telegram may expose only some members."""
    output = Path(output).expanduser()
    if output.exists() and not overwrite:
        raise FileExistsError(f"{output} already exists; pass --overwrite to replace it")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    count = 0
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8" if legacy else "utf-8-sig", newline="",
                                         prefix=f".{output.name}.", suffix=".tmp",
                                         dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.writer(stream, lineterminator="\n" if legacy else "\r\n")
            writer.writerow(LEGACY_CSV_COLUMNS if legacy else CSV_COLUMNS)
            try:
                for user in client.iter_participants(chat):
                    name = " ".join(part for part in (user.first_name, user.last_name) if part)
                    writer.writerow((user.username or "", user.id, user.access_hash or "",
                                     name, chat.title, chat.id))
                    count += 1
            except Exception as error:
                from telethon.errors import ChatAdminRequiredError
                if isinstance(error, ChatAdminRequiredError):
                    raise ValueError("Telegram requires admin access to list members of this chat") from error
                raise
        os.replace(temporary, output)
        return count
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _invitee_key(invitee):
    if invitee.user_id is not None:
        return ("id", str(invitee.user_id))
    return ("username", invitee.username.casefold())


def _read_progress(path, chat_id):
    outcomes = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        if rows.fieldnames != list(PROGRESS_COLUMNS):
            raise ValueError("Progress CSV has an invalid header")
        for row in rows:
            if row["chat_id"] != str(chat_id):
                raise ValueError("Progress CSV belongs to a different chat")
            if row["status"] not in {"invited", "not_invited", "privacy_blocked"}:
                raise ValueError("Progress CSV has an invalid status")
            key = ("id", row["user_id"]) if row["user_id"] else ("username", row["username"].casefold())
            if not key[1]:
                raise ValueError("Progress CSV has a row without an invitee")
            outcomes[key] = row
    return outcomes


def _write_progress(path, outcomes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="",
                                         prefix=f".{path.name}.", suffix=".tmp",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=PROGRESS_COLUMNS)
            writer.writeheader()
            writer.writerows(outcomes.values())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def invite_members(client, chat, invitees, delay=60, execute=False, sleep=time.sleep,
                   by_id=False, progress=None, resume=False):
    """Return (invited, not_invited); stop on Telegram flood limits."""
    if not execute:
        return 0, 0
    if resume and progress is None:
        raise ValueError("--resume requires --progress")
    from telethon.errors import FloodWaitError, PeerFloodError, UserPrivacyRestrictedError
    from telethon.tl.functions.channels import InviteToChannelRequest
    from telethon.tl.types import InputPeerUser

    progress = Path(progress).expanduser() if progress is not None else None
    if progress and progress.suffix != ".csv":
        raise ValueError("Progress path must end in .csv so Git ignores it")
    if resume and not progress.is_file():
        raise ValueError(f"Progress CSV does not exist: {progress}")
    if progress and progress.exists() and not resume:
        raise FileExistsError(f"{progress} already exists; pass --resume to use it")
    outcomes = _read_progress(progress, chat.id) if resume else {}
    invited = skipped = 0
    for index, invitee in enumerate(invitees):
        key = _invitee_key(invitee)
        if key in outcomes:
            print(f"Already recorded {invitee.username or invitee.user_id}: {outcomes[key]['status']}")
            continue
        try:
            user = (InputPeerUser(invitee.user_id, invitee.access_hash)
                    if by_id or not invitee.username
                    else client.get_input_entity(invitee.username))
            result = client(InviteToChannelRequest(chat, [user]))
            if not hasattr(result, "missing_invitees"):
                raise RuntimeError("Telegram returned an unknown invite result; outcome was not recorded")
            if result.missing_invitees:
                skipped += 1
                status = "not_invited"
                print(f"Telegram did not invite {invitee.username or invitee.user_id}", file=sys.stderr)
            else:
                invited += 1
                status = "invited"
                print(f"Invited {invitee.username or invitee.user_id}")
        except UserPrivacyRestrictedError:
            skipped += 1
            status = "privacy_blocked"
            print(f"Privacy settings blocked {invitee.username or invitee.user_id}", file=sys.stderr)
        except (PeerFloodError, FloodWaitError) as error:
            raise RuntimeError(f"Telegram rate limit; stopped after {invited} invites: {error}") from error
        if progress:
            outcomes[key] = {"chat_id": str(chat.id), "user_id": str(invitee.user_id or ""),
                             "username": invitee.username,
                             "status": status}
            _write_progress(progress, outcomes)
        if delay and index < len(invitees) - 1:
            sleep(delay)
    return invited, skipped


def connect_client(credentials=None, legacy=False):
    configured_id, configured_hash, configured_phone = credentials or (None, None, None)
    api_id = os.environ.get("TELEGRAM_API_ID") or configured_id
    api_hash = os.environ.get("TELEGRAM_API_HASH") or configured_hash
    phone = os.environ.get("TELEGRAM_PHONE") or configured_phone
    if not api_id or not api_hash or api_hash == "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX":
        raise ValueError("Set TELEGRAM_API_ID and TELEGRAM_API_HASH, or edit the original script")
    try:
        api_id = int(api_id)
    except ValueError as error:
        raise ValueError("TELEGRAM_API_ID must be an integer") from error
    if api_id <= 0:
        raise ValueError("TELEGRAM_API_ID must be a positive integer")
    if phone == "+34000000000":
        phone = None

    from telethon.sync import TelegramClient
    default_session = phone if legacy and phone else "~/.telegram-group-csv/session"
    session = Path(os.environ.get("TELEGRAM_SESSION", default_session)).expanduser()
    session.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session), api_id, api_hash)
    try:
        client.start(phone=phone or (lambda: input("Phone number: ")))
    except BaseException:
        client.disconnect()
        raise
    return client


def _choose_chat(available, prompt):
    if not available:
        raise ValueError("No available groups or channels")
    print(prompt)
    for index, dialog in enumerate(available):
        print(f"{index}- {dialog.name}")
    try:
        index = int(input("Enter a Number: "))
        return available[index].entity
    except (ValueError, IndexError) as error:
        raise ValueError("Invalid group or channel number") from error


def legacy_main(argv, credentials=None):
    """Keep the original numbered menu and optional CSV positional argument."""
    print("What do you want to do:")
    try:
        mode = int(input("Enter \n1-List users in a group\n"
                         "2-Add users from CSV to Group (CSV must be passed as a parameter to the script\n"
                         "3-Show CSV\n\nYour option:  "))
        if mode not in (1, 2, 3):
            raise ValueError("Choose 1, 2, or 3")
        if mode in (2, 3) and len(argv) != 1:
            raise ValueError("Pass CSV path as the first argument")
        if mode == 3:
            for user in read_invitees(argv[0]):
                print({"username": user.username, "id": user.user_id,
                       "access_hash": user.access_hash})
            return 0

        invitees = read_invitees(argv[0]) if mode == 2 else None
        client = connect_client(credentials, legacy=True)
        try:
            available = dialogs(client)
            if mode == 1:
                chat = _choose_chat(available, "Choose a group to scrape members from:")
                count = export_members(client, chat, legacy_output(chat), overwrite=True, legacy=True)
                print(f"Members scraped successfully. Exported {count} visible member(s). "
                      "Telegram may hide others; completeness is unknown.")
            else:
                available = [dialog for dialog in available
                             if getattr(dialog.entity, "megagroup", False)]
                chat = _choose_chat(available, "Choose a group to add members:")
                selection = int(input("Enter 1 to add by username or 2 to add by ID: "))
                if selection == 1:
                    invitees = [user for user in invitees if user.username]
                elif selection == 2:
                    if any(user.user_id is None or user.access_hash is None for user in invitees):
                        raise ValueError("ID mode requires user ID and access hash for every row")
                else:
                    raise ValueError("Invalid mode; choose 1 or 2")
                invited, skipped = invite_members(client, chat, invitees, execute=True,
                                                  by_id=selection == 2)
                print(f"Invited {invited}; not invited {skipped}")
        finally:
            client.disconnect()
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("dialogs", help="list available group and channel IDs")
    export = commands.add_parser("export", help="export members visible to your account")
    export.add_argument("chat", help="chat ID, exact title, or public username")
    export.add_argument("--output", type=Path, help="CSV path; defaults to members-NAME-ID.csv")
    export.add_argument("--overwrite", action="store_true")
    preview = commands.add_parser("preview", help="validate an invite CSV without connecting")
    preview.add_argument("csv_file", type=Path)
    invite = commands.add_parser("invite", help="invite users to a supergroup or channel")
    invite.add_argument("chat", help="chat ID, exact title, or public username")
    invite.add_argument("csv_file", type=Path)
    invite.add_argument("--execute", action="store_true", help="send invitations; otherwise preview only")
    invite.add_argument("--delay", type=int, default=60, help="seconds between invitations (default: 60)")
    invite.add_argument("--progress", type=Path, help="write invite outcomes to a private CSV checkpoint")
    invite.add_argument("--resume", action="store_true", help="skip outcomes recorded in --progress")
    return parser


def main(argv=None, credentials=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0] not in COMMANDS and not argv[0].startswith("-")):
        return legacy_main(argv, credentials)
    args = build_parser().parse_args(argv)
    try:
        if args.command in {"preview", "invite"}:
            invitees = read_invitees(args.csv_file)
            print(f"Valid CSV: {len(invitees)} user(s)")
            if args.command == "preview" or not args.execute:
                return 0
        if args.command == "invite" and args.delay < 0:
            raise ValueError("--delay must be zero or greater")
        if args.command == "invite" and args.resume and args.progress is None:
            raise ValueError("--resume requires --progress")
        if args.command == "invite" and args.progress is not None:
            args.progress = args.progress.expanduser()
            if args.progress.suffix != ".csv":
                raise ValueError("Progress path must end in .csv so Git ignores it")
            if args.resume and not args.progress.is_file():
                raise ValueError(f"Progress CSV does not exist: {args.progress}")
            if not args.resume and args.progress.exists():
                raise FileExistsError(f"{args.progress} already exists; pass --resume to use it")

        client = connect_client(credentials)
        try:
            if args.command == "dialogs":
                for dialog in dialogs(client):
                    kind = "group" if dialog.is_group else "channel"
                    print(f"{dialog.id}\t{kind}\t{dialog.name}")
            else:
                chat = resolve_chat(client, args.chat)
                if args.command == "export":
                    output = args.output or default_output(chat)
                    count = export_members(client, chat, output, args.overwrite)
                    print(f"Exported {count} visible member(s) to {output}. "
                          "Telegram may hide others; completeness is unknown.")
                elif args.command == "invite":
                    if not getattr(chat, "megagroup", False) and not getattr(chat, "broadcast", False):
                        raise ValueError("Invites support supergroups and channels only")
                    invited, skipped = invite_members(client, chat, invitees, args.delay, True,
                                                      progress=args.progress, resume=args.resume)
                    print(f"Invited {invited}; not invited {skipped}")
        finally:
            client.disconnect()
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
