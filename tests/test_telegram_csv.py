import csv
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import telegram_csv as tool


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "users.csv"

    def write(self, content):
        self.path.write_text(content, encoding="utf-8")
        return self.path

    def test_headerless_username_keeps_first_row(self):
        invitees = tool.read_invitees(self.write("@alice\nbob\n"))
        self.assertEqual([user.username for user in invitees], ["alice", "bob"])

    def test_exported_csv_and_legacy_header(self):
        self.write("username,user_id,user_access_hash,name,group,group_id\n"
                   ",123,456,Example,Group,5\n")
        self.assertEqual(tool.read_invitees(self.path), [tool.Invitee("", 123, 456)])
        self.write("username,user id,access hash\nalice,123,456\n")
        self.assertEqual(tool.read_invitees(self.path), [tool.Invitee("alice", 123, 456)])

    def test_invalid_rows_report_line(self):
        self.write("username,user_id,user_access_hash\nalice,invalid,456\n")
        with self.assertRaisesRegex(ValueError, "line 2"):
            tool.read_invitees(self.path)

    def test_export_is_readable_and_no_partial_result(self):
        output = Path(self.directory.name) / "members.csv"
        chat = SimpleNamespace(id=9, title="España")
        users = [SimpleNamespace(username="alice", id=1, access_hash=2,
                                 first_name="Ana", last_name="López")]
        client = Mock()
        client.iter_participants.return_value = iter(users)
        self.assertEqual(tool.export_members(client, chat, output), 1)
        with output.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[0], list(tool.CSV_COLUMNS))
        self.assertEqual(rows[1], ["alice", "1", "2", "Ana López", "España", "9"])
        self.assertEqual(tool.read_invitees(output), [tool.Invitee("alice", 1, 2)])

        def fail():
            yield users[0]
            raise RuntimeError("Telegram interrupted")

        client.iter_participants.return_value = fail()
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            tool.export_members(client, chat, output, overwrite=True)
        with output.open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(len(list(csv.reader(stream))), 2)
        self.assertEqual(list(Path(self.directory.name).glob("*.tmp")), [])

    def test_legacy_export_keeps_filename_header_and_no_bom(self):
        chat = SimpleNamespace(id=9, title="Hello World")
        self.assertEqual(tool.legacy_output(chat), Path("members-hello-world.csv"))
        output = Path(self.directory.name) / tool.legacy_output(chat)
        client = Mock()
        client.iter_participants.return_value = iter([SimpleNamespace(
            username="alice", id=1, access_hash=2, first_name="Ana", last_name=None)])
        tool.export_members(client, chat, output, legacy=True)
        self.assertFalse(output.read_bytes().startswith(b"\xef\xbb\xbf"))
        with output.open(encoding="utf-8", newline="") as stream:
            self.assertEqual(next(csv.reader(stream)), list(tool.LEGACY_CSV_COLUMNS))
        self.assertEqual(tool.read_invitees(output), [tool.Invitee("alice", 1, 2)])

    def test_admin_required_keeps_existing_export(self):
        from telethon.errors import ChatAdminRequiredError

        output = Path(self.directory.name) / "members.csv"
        output.write_text("existing", encoding="utf-8")
        client = Mock()
        client.iter_participants.side_effect = ChatAdminRequiredError(request=None)
        with self.assertRaisesRegex(ValueError, "admin access"):
            tool.export_members(client, SimpleNamespace(id=9, title="Group"), output,
                                overwrite=True)
        self.assertEqual(output.read_text(encoding="utf-8"), "existing")

    def test_wrapped_admin_error_keeps_existing_export(self):
        from telethon.errors import ChatAdminRequiredError
        from telethon.errors.common import MultiError
        from telethon.tl.functions.channels import GetParticipantsRequest
        from telethon.tl.types import ChannelParticipantsRecent, InputChannel

        request = GetParticipantsRequest(InputChannel(9, 10), ChannelParticipantsRecent(),
                                         offset=0, limit=1, hash=0)
        error = MultiError([ChatAdminRequiredError(request), None],
                           [None, None], [request, request])
        output = Path(self.directory.name) / "members.csv"
        output.write_text("existing", encoding="utf-8")
        client = Mock()
        client.iter_participants.side_effect = error
        with self.assertRaisesRegex(ValueError, "admin access"):
            tool.export_members(client, SimpleNamespace(id=9, title="Group"), output,
                                overwrite=True)
        self.assertEqual(output.read_text(encoding="utf-8"), "existing")
        self.assertEqual(list(Path(self.directory.name).glob("*.tmp")), [])

    def test_all_dialogs_and_duplicate_names(self):
        items = [SimpleNamespace(id=index, name="same", entity=object(),
                                 is_group=True, is_channel=False) for index in range(250)]
        client = Mock()
        client.iter_dialogs.return_value = iter(items)
        self.assertEqual(len(tool.dialogs(client)), 250)
        client.iter_dialogs.return_value = iter(items)
        self.assertIs(tool.resolve_chat(client, "249"), items[249].entity)
        client.iter_dialogs.return_value = iter(items)
        with self.assertRaisesRegex(ValueError, "Multiple chats"):
            tool.resolve_chat(client, "same")


class InviteTests(unittest.TestCase):
    def test_execute_warns_before_connecting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "users.csv"
            path.write_text("alice\n", encoding="utf-8")
            stderr = io.StringIO()
            client = Mock()
            chat = SimpleNamespace(id=9, megagroup=True)
            with patch.object(tool, "connect_client", return_value=client) as connect, \
                 patch.object(tool, "resolve_chat", return_value=chat), \
                 patch.object(tool, "invite_members", return_value=(0, 0)), \
                 patch("sys.stderr", stderr):
                self.assertEqual(tool.main(["invite", "9", str(path), "--execute"]), 0)
            connect.assert_called_once()
            self.assertIn("restrict or ban", stderr.getvalue())

    def test_preview_never_calls_telegram(self):
        client = Mock()
        self.assertEqual(tool.invite_members(client, object(), [tool.Invitee("alice")]), (0, 0))
        client.assert_not_called()

    def test_rate_limit_stops_remaining_invites(self):
        from telethon.errors import PeerFloodError

        client = Mock()
        client.get_input_entity.side_effect = ["first", "second"]
        client.side_effect = [SimpleNamespace(missing_invitees=[]),
                              PeerFloodError(request=None)]
        invitees = [tool.Invitee(name) for name in ("alice", "bob", "carol")]
        with self.assertRaisesRegex(RuntimeError, "stopped after 1 invites"):
            tool.invite_members(client, object(), invitees, delay=0, execute=True)
        self.assertEqual(client.call_count, 2)

    def test_missing_invitee_is_not_reported_as_success(self):
        from telethon.tl.types import MissingInvitee
        from telethon.tl.types.messages import InvitedUsers

        client = Mock()
        client.get_input_entity.return_value = "alice"
        client.return_value = InvitedUsers(updates=None,
                                           missing_invitees=[MissingInvitee(user_id=1)])
        self.assertEqual(tool.invite_members(client, SimpleNamespace(id=9),
                                             [tool.Invitee("alice")], delay=0, execute=True),
                         (0, 1))

    def test_unknown_invite_result_is_not_reported_as_success(self):
        client = Mock()
        client.get_input_entity.return_value = "alice"
        client.return_value = None
        with self.assertRaisesRegex(RuntimeError, "outcome was not recorded"):
            tool.invite_members(client, SimpleNamespace(id=9), [tool.Invitee("alice")],
                                delay=0, execute=True)

    def test_checkpoint_resumes_without_reinviting_recorded_users(self):
        from telethon.errors import PeerFloodError

        with tempfile.TemporaryDirectory() as directory:
            progress = Path(directory) / "progress.csv"
            chat = SimpleNamespace(id=9)
            invitees = [tool.Invitee("alice", 1, 11), tool.Invitee("bob", 2, 22),
                        tool.Invitee("carol", 3, 33)]
            client = Mock()
            client.get_input_entity.side_effect = ["alice", "bob", "carol"]
            client.side_effect = [SimpleNamespace(missing_invitees=[]),
                                  PeerFloodError(request=None)]
            with self.assertRaisesRegex(RuntimeError, "stopped after 1 invites"):
                tool.invite_members(client, chat, invitees, delay=0, execute=True,
                                    progress=progress)
            with progress.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([(row["user_id"], row["status"]) for row in rows],
                             [("1", "invited")])

            resumed = Mock()
            resumed.get_input_entity.side_effect = ["bob", "carol"]
            resumed.side_effect = [SimpleNamespace(missing_invitees=[object()]),
                                   SimpleNamespace(missing_invitees=[])]
            self.assertEqual(tool.invite_members(resumed, chat, invitees, delay=0,
                                                 execute=True, progress=progress,
                                                 resume=True), (1, 1))
            self.assertEqual(resumed.call_count, 2)
            with progress.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["status"] for row in rows],
                             ["invited", "not_invited", "invited"])
            self.assertEqual(tool.invite_members(Mock(), chat, invitees, delay=0,
                                                 execute=True, progress=progress,
                                                 resume=True), (0, 0))
            with self.assertRaisesRegex(ValueError, "different chat"):
                tool.invite_members(Mock(), SimpleNamespace(id=10), invitees,
                                    delay=0, execute=True, progress=progress, resume=True)

    def test_checkpoint_never_overwrites_without_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            progress = Path(directory) / "progress.csv"
            progress.write_text("existing", encoding="utf-8")
            client = Mock()
            with self.assertRaises(FileExistsError):
                tool.invite_members(client, SimpleNamespace(id=9), [tool.Invitee("alice")],
                                    execute=True, progress=progress)
            client.assert_not_called()
            self.assertEqual(progress.read_text(encoding="utf-8"), "existing")


class LegacyMenuTests(unittest.TestCase):
    def test_original_credentials_and_session_name_still_work(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch("telethon.sync.TelegramClient") as client_class:
            client = tool.connect_client((123, "hash", "+34111"), legacy=True)
        self.assertIs(client, client_class.return_value)
        client_class.assert_called_once_with("+34111", 123, "hash")
        client.start.assert_called_once_with(phone="+34111")

    def test_original_no_arg_invocation_shows_export_menu(self):
        client = Mock()
        chat = SimpleNamespace(id=9, title="Legacy Group")
        item = SimpleNamespace(id=9, name="Legacy Group", entity=chat,
                               is_group=True, is_channel=False)
        client.iter_dialogs.return_value = iter([item])
        client.iter_participants.return_value = iter([])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "members-legacy-group.csv"
            with patch("builtins.input", side_effect=["1", "0"]), \
                 patch.object(tool, "connect_client", return_value=client), \
                 patch.object(tool, "legacy_output", return_value=output):
                self.assertEqual(tool.main([], credentials=(123, "hash", "+34111")), 0)
            with output.open(encoding="utf-8", newline="") as stream:
                self.assertEqual(next(csv.reader(stream)), list(tool.LEGACY_CSV_COLUMNS))
        client.disconnect.assert_called_once()

    def test_original_csv_argument_reaches_numbered_invite_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "users.csv"
            path.write_text("alice\n", encoding="utf-8")
            client = Mock()
            chat = SimpleNamespace(id=9, title="Legacy Group", megagroup=True)
            item = SimpleNamespace(id=9, name="Legacy Group", entity=chat,
                                   is_group=True, is_channel=False)
            client.iter_dialogs.return_value = iter([item])
            with patch("builtins.input", side_effect=["2", "0", "1"]), \
                 patch.object(tool, "connect_client", return_value=client), \
                 patch.object(tool, "invite_members", return_value=(1, 0)) as invite, \
                 patch("sys.stderr", io.StringIO()) as stderr:
                self.assertEqual(tool.main([str(path)], credentials=(123, "hash", "+34111")), 0)
            self.assertIn("restrict or ban", stderr.getvalue())
            self.assertEqual(invite.call_args.args[2], [tool.Invitee("alice")])
            self.assertTrue(invite.call_args.kwargs["execute"])
            client.disconnect.assert_called_once()

    def test_numbered_invite_flow_lists_broadcast_channel(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "users.csv"
            path.write_text("alice\n", encoding="utf-8")
            client = Mock()
            channel = SimpleNamespace(id=10, title="Channel", broadcast=True)
            item = SimpleNamespace(id=10, name="Channel", entity=channel,
                                   is_group=False, is_channel=True)
            client.iter_dialogs.return_value = iter([item])
            with patch("builtins.input", side_effect=["2", "0", "1"]), \
                 patch.object(tool, "connect_client", return_value=client), \
                 patch.object(tool, "invite_members", return_value=(1, 0)) as invite, \
                 patch("sys.stderr", io.StringIO()):
                self.assertEqual(tool.main([str(path)]), 0)
            self.assertIs(invite.call_args.args[1], channel)
            client.disconnect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
