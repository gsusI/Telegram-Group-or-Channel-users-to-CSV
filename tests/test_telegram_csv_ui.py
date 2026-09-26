import unittest
import asyncio
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

try:
    from streamlit.testing.v1 import AppTest
except ModuleNotFoundError as error:
    if error.name != "streamlit":
        raise
    raise unittest.SkipTest("Install requirements-ui.txt to run UI tests") from error

import telegram_csv_ui as ui


class UiHelperTests(unittest.TestCase):
    def test_csv_preview_excludes_access_hash(self):
        data = (b"username,user_id,user_access_hash,name,group,group_id\n"
                b"alice,1,secret,Alice,Example,9\n")
        self.assertEqual(ui._csv_preview(data), [{
            "username": "alice",
            "user_id": "1",
            "name": "Alice",
            "group": "Example",
            "group_id": "9",
        }])

    def test_local_diff_and_dedupe_helpers(self):
        header = b"username,user_id,user_access_hash,name,group,group_id\n"
        earlier = header + b"alice,1,11,Alice,Example,9\n"
        later = header + b"bob,2,22,Bob,Example,9\n"
        changes, added, missing = ui._diff_bytes(earlier, later)
        self.assertEqual((added, missing), (1, 1))
        self.assertIn(b"newly_observed", changes)
        unique, count = ui._dedupe_bytes([earlier, later])
        self.assertEqual(count, 2)
        self.assertNotIn(b"user_access_hash", unique)
        self.assertEqual(ui._csv_preview(unique)[0]["group_ids"], "9")

    def test_connection_failure_disconnects_client(self):
        client = Mock()
        client.connect.side_effect = OSError("connection failed")
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(ui.core, "_client_settings", return_value=(1, "hash", None, Path(directory) / "session")), \
                patch("telethon.sync.TelegramClient", return_value=client):
            with self.assertRaisesRegex(OSError, "connection failed"):
                ui._authorized_client(None)
        client.disconnect.assert_called_once()

    def test_failed_login_connection_disconnects_client(self):
        client = Mock(connect=AsyncMock(side_effect=OSError("offline")),
                      disconnect=AsyncMock())
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(ui.core, "_client_settings", return_value=(1, "hash", None, Path(directory) / "session")), \
                patch("telethon.TelegramClient", return_value=client):
            with self.assertRaisesRegex(OSError, "offline"):
                asyncio.run(ui._request_login_code(None, "+123"))
        client.disconnect.assert_awaited_once()

    def test_account_and_recipient_changes_clear_stale_state(self):
        state = {"login_phone": "+123", "login_code_hash": "expired",
                 "chat_options": ["old"], "export_results": ["old"],
                 "invite_consent": True, "diff_result": b"old"}
        with patch.object(ui.st, "session_state", state):
            ui._account_changed()
            self.assertEqual(state, {"diff_result": b"old"})
            ui._clear_state("diff_result")
            self.assertEqual(state, {})


class UiSmokeTests(unittest.TestCase):
    def test_app_opens_without_credentials_or_network(self):
        app_path = Path(__file__).parents[1] / "telegram_csv_ui.py"
        with patch.dict(os.environ, {"TELEGRAM_API_ID": "", "TELEGRAM_API_HASH": "",
                                     "TELEGRAM_PHONE": ""}), patch("telethon.TelegramClient") as connect:
            app = AppTest.from_file(app_path, default_timeout=10).run()
        connect.assert_not_called()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Export members")
        self.assertTrue(any("account panel" in info.value for info in app.info))

    def test_export_button_writes_csv_and_disconnects(self):
        client = Mock()
        chat = SimpleNamespace(id=9, title="Example")
        client.iter_participants.return_value = iter([SimpleNamespace(
            id=1, username="alice", access_hash=11, first_name="Alice", last_name=None)])
        app = AppTest.from_file(Path(__file__).parents[1] / "telegram_csv_ui.py",
                                default_timeout=10).run()
        app.session_state["chat_options"] = [ui.ChatOption("9", "Example", "Group")]
        app.run()
        app.multiselect(key="export_chats").set_value(
            [ui.ChatOption("9", "Example", "Group")]).run()
        with tempfile.TemporaryDirectory() as directory, \
                patch("telethon.sync.TelegramClient", return_value=client), \
                patch.object(ui.core, "_client_settings", return_value=(1, "hash", None, Path(directory) / "session")), \
                patch.object(ui.core, "dialogs", return_value=[]), \
                patch.object(ui.core, "resolve_chat", return_value=chat):
            app.text_input(key="export_output_directory").set_value(directory)
            app.toggle(key="export_resumable").set_value(False)
            app.button(key="export_submit").click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error, [error.value for error in app.error])
            self.assertIn("alice", (Path(directory) / ui.core.default_output(chat)).read_text())
        client.disconnect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
