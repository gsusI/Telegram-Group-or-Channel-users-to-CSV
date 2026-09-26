"""Local Streamlit interface for the Telegram CSV tools."""

import asyncio
import csv
import io
import itertools
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

import telegram_csv as core


def _export_directory():
    return Path(os.environ.get("TELEGRAM_CSV_DATA_DIR", Path(__file__).resolve().parent / "data")) / "exports"


@dataclass(frozen=True)
class ChatOption:
    chat_id: str
    name: str
    kind: str

    @property
    def label(self):
        return f"{self.name} · {self.kind} · {self.chat_id}"


def _session_file(credentials):
    """Return configured Telethon session file without contacting Telegram."""
    _, _, _, session = core._client_settings(credentials)
    return session if str(session).endswith(".session") else Path(f"{session}.session")


def _run_async(awaitable):
    return asyncio.run(awaitable)


async def _request_login_code(credentials, phone):
    from telethon import TelegramClient

    api_id, api_hash, _, session = core._client_settings(credentials)
    session.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session), api_id, api_hash)
    try:
        await client.connect()
        if await client.is_user_authorized():
            return None
        sent_code = await client.send_code_request(phone)
        return sent_code.phone_code_hash
    finally:
        await client.disconnect()


async def _complete_login(credentials, phone, code, phone_code_hash):
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

    api_id, api_hash, _, session = core._client_settings(credentials)
    client = TelegramClient(str(session), api_id, api_hash)
    try:
        await client.connect()
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            return False
        return True
    finally:
        await client.disconnect()


async def _complete_password(credentials, password):
    from telethon import TelegramClient

    api_id, api_hash, _, session = core._client_settings(credentials)
    client = TelegramClient(str(session), api_id, api_hash)
    try:
        await client.connect()
        await client.sign_in(password=password)
    finally:
        await client.disconnect()


def _authorized_client(credentials):
    """Connect only when a saved session is authorized; never prompt in server logs."""
    from telethon.sync import TelegramClient

    api_id, api_hash, _, session = core._client_settings(credentials)
    session.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session), api_id, api_hash)
    try:
        client.connect()
        if not client.is_user_authorized():
            raise ValueError("Sign in from the account panel before connecting")
    except BaseException:
        client.disconnect()
        raise
    return client


def _fetch_chat_options(credentials):
    client = _authorized_client(credentials)
    try:
        return [ChatOption(str(dialog.id), dialog.name,
                           "Group" if dialog.is_group else "Channel")
                for dialog in core.dialogs(client)]
    finally:
        client.disconnect()


def _csv_preview(data, limit=20):
    rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    visible_columns = ("username", "user_id", "name", "group", "group_id", "change", "group_ids")
    return [{column: row[column] for column in visible_columns if column in row}
            for row in itertools.islice(rows, limit)]


def _uploaded_csv(upload):
    return upload.getvalue() if upload is not None else None


def _read_invitees_bytes(data):
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "invitees.csv"
        source.write_bytes(data)
        return core.read_invitees(source)


def _diff_bytes(earlier, later):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        earlier_path = root / "earlier.csv"
        later_path = root / "later.csv"
        output = root / "changes.csv"
        earlier_path.write_bytes(earlier)
        later_path.write_bytes(later)
        added, missing = core.diff_exports(earlier_path, later_path, output)
        return output.read_bytes(), added, missing


def _dedupe_bytes(exports):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        paths = []
        for index, data in enumerate(exports):
            path = root / f"export-{index}.csv"
            path.write_bytes(data)
            paths.append(path)
        output = root / "unique-members.csv"
        count = core.dedupe_exports(paths, output)
        return output.read_bytes(), count


def _clear_login_state():
    for key in ("login_phone", "login_code_hash", "login_needs_password"):
        st.session_state.pop(key, None)


def _clear_state(*keys):
    for key in keys:
        st.session_state.pop(key, None)


def _account_changed():
    _clear_login_state()
    _clear_state("chat_options", "export_chats", "invite_chat", "export_results",
                 "invite_consent")


def _invite_changed():
    st.session_state.invite_consent = False


def _account_panel():
    with st.sidebar:
        st.header("Telegram account")
        st.caption("Credentials stay in this local process. Session access stays on this computer.")
        st.link_button("Get API credentials", "https://my.telegram.org/apps")

        environment_has_id = bool(os.environ.get("TELEGRAM_API_ID"))
        environment_has_hash = bool(os.environ.get("TELEGRAM_API_HASH"))
        api_id = st.text_input(
            "API ID",
            value="" if not environment_has_id else "Configured in environment",
            disabled=environment_has_id,
            key="account_api_id",
            on_change=_account_changed,
        )
        api_hash = st.text_input(
            "API hash",
            value="" if not environment_has_hash else "Configured in environment",
            disabled=environment_has_hash,
            type="password",
            key="account_api_hash",
            on_change=_account_changed,
        )
        phone = st.text_input(
            "Phone number",
            value=os.environ.get("TELEGRAM_PHONE", ""),
            placeholder="+34…",
            key="account_phone",
            on_change=_account_changed,
        )
        credentials = (
            None if environment_has_id else api_id,
            None if environment_has_hash else api_hash,
            phone or None,
        )

        try:
            session = _session_file(credentials)
            if session.is_file():
                st.success("Local session found", icon=":material/check_circle:")
            else:
                st.info("Sign in once to create a local session.", icon=":material/info:")
        except ValueError as error:
            st.warning("Enter a valid API ID and API hash to connect.", icon=":material/key:")
            return credentials

        with st.expander("Sign in or reconnect", expanded=not session.is_file()):
            st.caption("Telegram sends the code to your Telegram app or phone. Two-step verification is supported.")
            if st.session_state.get("login_code_hash"):
                st.button("Start sign-in again", on_click=_clear_login_state,
                          key="account_restart_login")
            if not st.session_state.get("login_code_hash"):
                if st.button("Send login code", type="primary", width="stretch",
                             disabled=not bool(phone), key="account_send_code"):
                    try:
                        code_hash = _run_async(_request_login_code(credentials, phone))
                        if code_hash is None:
                            _clear_login_state()
                            st.toast("Already signed in", icon=":material/check_circle:")
                        else:
                            st.session_state.login_phone = phone
                            st.session_state.login_code_hash = code_hash
                            st.success("Code sent. Enter it below.")
                    except Exception as error:  # Telethon exposes many user-facing RPC errors.
                        st.error(str(error))

            if st.session_state.get("login_code_hash") and not st.session_state.get("login_needs_password"):
                with st.form("account_code_form"):
                    code = st.text_input("Login code", placeholder="12345")
                    verify = st.form_submit_button("Verify code", type="primary", width="stretch")
                if verify:
                    try:
                        complete = _run_async(_complete_login(
                            credentials,
                            st.session_state.login_phone,
                            code,
                            st.session_state.login_code_hash,
                        ))
                        if complete:
                            _clear_login_state()
                            st.toast("Signed in", icon=":material/check_circle:")
                            st.rerun()
                        st.session_state.login_needs_password = not complete
                    except Exception as error:
                        st.error(str(error))

            if st.session_state.get("login_needs_password"):
                with st.form("account_password_form"):
                    password = st.text_input("Two-step verification password", type="password")
                    verify_password = st.form_submit_button(
                        "Finish sign in", type="primary", width="stretch"
                    )
                if verify_password:
                    try:
                        _run_async(_complete_password(credentials, password))
                        _clear_login_state()
                        st.toast("Signed in", icon=":material/check_circle:")
                        st.rerun()
                    except Exception as error:
                        st.error(str(error))
            st.caption("Prefer QR? Run `python telegram_csv.py login --qr` once, then return here.")
        return credentials


def _chat_picker(credentials, *, multiple, key):
    try:
        core._client_settings(credentials)
        configured = True
    except ValueError:
        configured = False
    action_label = "Refresh chats" if st.session_state.get("chat_options") else "Load my chats"
    if st.button(action_label, icon=":material/refresh:", key=f"{key}_refresh", disabled=not configured):
        try:
            with st.spinner("Loading groups and channels…"):
                st.session_state.chat_options = _fetch_chat_options(credentials)
            st.toast(f"Loaded {len(st.session_state.chat_options)} chats")
        except Exception as error:
            st.error(str(error))

    options = st.session_state.get("chat_options", [])
    if not options:
        st.info("Load your groups and channels to continue." if configured else
                "Open the account panel, enter your API credentials, then sign in to load your chats.",
                icon=":material/forum:")
        return [] if multiple else None
    if multiple:
        return st.multiselect("Groups or channels", options, format_func=lambda item: item.label,
                              key=f"{key}_chats")
    return st.selectbox("Group or channel", options, format_func=lambda item: item.label,
                        key=f"{key}_chat", index=None, placeholder="Choose a destination",
                        on_change=_invite_changed)


def _show_export_results():
    results = st.session_state.get("export_results", [])
    if not results:
        return
    st.subheader("Latest export")
    for index, result in enumerate(results):
        label, count, path, data = result
        with st.container(border=True):
            name_col, count_col, action_col = st.columns([3, 1, 1.4], vertical_alignment="center")
            name_col.text(label)
            name_col.caption(path)
            count_col.metric("Observed", count)
            action_col.download_button(
                "Download CSV",
                data=data,
                file_name=Path(path).name,
                mime="text/csv",
                icon=":material/download:",
                width="stretch",
                key=f"export_download_{index}_{path}",
                on_click="ignore",
            )
            preview = _csv_preview(data)
            if preview:
                with st.expander("Preview first 20 rows"):
                    st.dataframe(preview, hide_index=True, width="stretch")


def _export_page(credentials):
    st.title("Export members")
    st.caption("Select one or more groups or channels. Exports remain private on this computer until you download or move them.")
    selected = _chat_picker(credentials, multiple=True, key="export")
    output_directory = st.text_input(
        "Save copies to",
        value=str(_export_directory()),
        help="CSV files and recovery checkpoints stay in this local folder.",
        key="export_output_directory",
    )
    option_col, overwrite_col = st.columns(2)
    resumable = option_col.toggle(
        "Keep a recovery checkpoint",
        value=True,
        help="Recommended for large exports. A retry rescans Telegram and deduplicates observations.",
        key="export_resumable",
    )
    overwrite = overwrite_col.toggle(
        "Replace completed files",
        value=False,
        help="Leave off to protect existing completed CSV files.",
        key="export_overwrite",
    )
    if st.button("Export selected chats", type="primary", icon=":material/download:",
                 disabled=not bool(selected), width="stretch", key="export_submit"):
        results = []
        failures = []
        client = None
        with st.status("Connecting to Telegram…", expanded=True) as status:
            try:
                client = _authorized_client(credentials)
                available = core.dialogs(client)
                root = Path(output_directory).expanduser()
                for option in selected:
                    status.update(label=f"Exporting {option.name}…")
                    st.write(f"Reading members visible in **{option.name}**")
                    try:
                        chat = core.resolve_chat(client, option.chat_id, available)
                        output = root / core.default_output(chat)
                        checkpoint = output.with_name(f"{output.name}.checkpoint.sqlite")
                        resume = resumable and checkpoint.exists()
                        count = (core.export_members_resumable(
                            client, chat, output, overwrite=overwrite, resume=resume
                        ) if resumable else core.export_members(
                            client, chat, output, overwrite=overwrite
                        ))
                        results.append((option.name, count, str(output), output.read_bytes()))
                    except Exception as error:
                        failures.append(f"{option.name}: {error}")
                if failures:
                    status.update(label="Export finished with errors", state="error", expanded=True)
                else:
                    status.update(label="Export complete", state="complete", expanded=False)
            except Exception as error:
                failures.append(str(error))
                status.update(label="Export failed", state="error", expanded=True)
            finally:
                if client is not None:
                    client.disconnect()
        st.session_state.export_results = results
        for failure in failures:
            st.error(failure)
        if results:
            st.success(f"Saved {len(results)} export{'s' if len(results) != 1 else ''}.")

    st.info(
        "Telegram can hide participants even when an export succeeds. Counts mean observed or visible members, not guaranteed completeness.",
        icon=":material/visibility:",
    )
    _show_export_results()


def _analysis_page():
    st.title("Compare local exports")
    st.caption("These tools stay local and never connect to Telegram.")
    compare_tab, combine_tab = st.tabs(["Find changes", "Combine observations"])

    with compare_tab:
        earlier_col, later_col = st.columns(2)
        earlier = earlier_col.file_uploader("Earlier export", type="csv", key="diff_earlier",
                                           on_change=_clear_state, args=("diff_result",))
        later = later_col.file_uploader("Later export", type="csv", key="diff_later",
                                       on_change=_clear_state, args=("diff_result",))
        if st.button("Compare exports", type="primary", disabled=not (earlier and later),
                     icon=":material/compare_arrows:", key="diff_submit"):
            _clear_state("diff_result")
            try:
                data, added, missing = _diff_bytes(_uploaded_csv(earlier), _uploaded_csv(later))
                st.session_state.diff_result = (data, added, missing)
            except Exception as error:
                st.error(str(error))
        if st.session_state.get("diff_result"):
            data, added, missing = st.session_state.diff_result
            added_col, missing_col = st.columns(2)
            added_col.metric("Newly observed", added)
            missing_col.metric("No longer visible", missing)
            preview = _csv_preview(data)
            if preview:
                st.dataframe(preview, hide_index=True, width="stretch")
            st.download_button("Download changes", data=data, file_name="changes.csv",
                               mime="text/csv", icon=":material/download:",
                               key="diff_download", on_click="ignore")
            st.caption("No longer visible does not prove someone left; Telegram visibility can change.")

    with combine_tab:
        uploads = st.file_uploader("Member exports", type="csv", accept_multiple_files=True,
                                   key="dedupe_exports", on_change=_clear_state,
                                   args=("dedupe_result",))
        if st.button("Combine and deduplicate", type="primary", disabled=len(uploads) < 2,
                     icon=":material/group_work:", key="dedupe_submit"):
            _clear_state("dedupe_result")
            try:
                data, count = _dedupe_bytes([_uploaded_csv(upload) for upload in uploads])
                st.session_state.dedupe_result = (data, count)
            except Exception as error:
                st.error(str(error))
        if st.session_state.get("dedupe_result"):
            data, count = st.session_state.dedupe_result
            st.metric("Unique observed users", count)
            preview = _csv_preview(data)
            if preview:
                st.dataframe(preview, hide_index=True, width="stretch")
            st.download_button("Download unique members", data=data,
                               file_name="unique-members.csv", mime="text/csv",
                               icon=":material/download:", key="dedupe_download",
                               on_click="ignore")
            st.caption("Combined files omit access hashes and are for local analysis, not ID-based invitations.")


def _invite_page(credentials):
    st.title("Invite from CSV")
    st.warning(core.INVITE_WARNING, icon=":material/warning:")
    upload = st.file_uploader("CSV containing usernames or user IDs and access hashes",
                              type="csv", key="invite_upload", on_change=_invite_changed)
    invitees = []
    if upload:
        try:
            invitees = _read_invitees_bytes(_uploaded_csv(upload))
            st.success(f"Valid CSV: {len(invitees)} user{'s' if len(invitees) != 1 else ''}")
        except Exception as error:
            st.error(str(error))

    target = _chat_picker(credentials, multiple=False, key="invite")
    delay = st.number_input("Seconds between attempts", min_value=0, value=60, step=5,
                            key="invite_delay")
    progress_path = st.text_input(
        "Progress file",
        value=str(_export_directory() / "invite-progress.csv"),
        help="Confirmed outcomes are written immediately so interrupted runs can resume.",
        key="invite_progress_path",
    )
    progress = Path(progress_path).expanduser()
    resume = st.toggle("Resume existing progress file", value=progress.exists(),
                       key="invite_resume")
    consent = st.checkbox(
        "These people expect this invitation, and I accept Telegram account restriction risk.",
        key="invite_consent",
    )
    disabled = not (invitees and target and consent)
    if st.button(f"Invite {len(invitees)} people", type="primary",
                 icon=":material/person_add:", disabled=disabled,
                 width="stretch", key="invite_submit"):
        client = None
        try:
            if progress.suffix != ".csv":
                raise ValueError("Progress path must end in .csv")
            if resume and not progress.is_file():
                raise ValueError("Resume is on, but the progress CSV does not exist")
            if not resume and progress.exists():
                raise FileExistsError("Progress CSV already exists; turn on resume or choose another path")
            progress.parent.mkdir(parents=True, exist_ok=True)
            with st.status("Inviting users…", expanded=True) as status:
                client = _authorized_client(credentials)
                chat = core.resolve_chat(client, target.chat_id)
                if (not core._is_basic_group(chat) and not getattr(chat, "megagroup", False)
                        and not getattr(chat, "broadcast", False)):
                    raise ValueError("Invites support groups, supergroups, and channels only")
                invited, skipped = core.invite_members(
                    client, chat, invitees, delay=int(delay), execute=True,
                    progress=progress, resume=resume,
                )
                status.update(label="Invite run complete", state="complete", expanded=False)
            st.success(f"Invited {invited}; not invited {skipped}.")
        except Exception as error:
            st.error(str(error))
        finally:
            if client is not None:
                client.disconnect()


def main():
    st.set_page_config(
        page_title="Telegram CSV",
        page_icon=":material/group:",
        layout="wide",
        initial_sidebar_state="auto",
    )
    credentials = _account_panel()
    navigation = st.navigation(
        [
            st.Page(lambda: _export_page(credentials), title="Export", url_path="export",
                    icon=":material/download:", default=True),
            st.Page(_analysis_page, title="Local tools", url_path="local-tools",
                    icon=":material/compare_arrows:"),
            st.Page(lambda: _invite_page(credentials), title="Invite", url_path="invite",
                    icon=":material/person_add:"),
        ],
        position="top",
    )
    navigation.run()


if __name__ == "__main__":
    main()
