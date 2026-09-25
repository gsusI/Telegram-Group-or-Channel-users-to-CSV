import csv
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import telegram_csv as tool


def basic_chat(chat_id=9):
    from telethon.tl.types import Chat
    return Chat(chat_id, "Basic Group", photo=None, participants_count=0,
                date=None, version=1)


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

    def test_resumable_export_keeps_checkpoint_and_old_output(self):
        output = Path(self.directory.name) / "members.csv"
        output.write_text("previous", encoding="utf-8")
        chat = SimpleNamespace(id=9, title="Group", participants_count=5)
        alice = SimpleNamespace(username="alice", id=1, access_hash=11,
                                first_name="Alice", last_name=None)
        bob = SimpleNamespace(username="bob", id=2, access_hash=22,
                              first_name="Bob", last_name=None)

        def interrupted():
            yield alice
            raise RuntimeError("interrupted")

        client = Mock()
        client.get_me.return_value.id = 100
        client.iter_participants.side_effect = lambda chat: interrupted()
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            tool.export_members_resumable(client, chat, output, overwrite=True)
        checkpoint = output.with_name(output.name + ".checkpoint.sqlite")
        self.assertTrue(checkpoint.is_file())
        self.assertEqual(output.read_text(encoding="utf-8"), "previous")
        with self.assertRaises(FileExistsError):
            tool.export_members_resumable(client, chat, output, overwrite=True)
        with self.assertRaisesRegex(ValueError, "different chat"):
            tool.export_members_resumable(client, SimpleNamespace(id=10, title="Other"),
                                          output, overwrite=True, resume=True)
        other_account = Mock()
        other_account.get_me.return_value.id = 200
        with self.assertRaisesRegex(ValueError, "different Telegram account"):
            tool.export_members_resumable(other_account, chat, output,
                                          overwrite=True, resume=True)

        client.iter_participants.side_effect = lambda chat: iter([alice, bob])
        self.assertEqual(tool.export_members_resumable(client, chat, output,
                                                        overwrite=True, resume=True), 2)
        self.assertFalse(checkpoint.exists())
        with output.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[0], list(tool.CSV_COLUMNS))
        self.assertEqual([row[1] for row in rows[1:]], ["1", "2"])

    def test_local_diff_and_dedupe_never_connect(self):
        old = Path(self.directory.name) / "old.csv"
        new = Path(self.directory.name) / "new.csv"
        header = ",".join(tool.CSV_COLUMNS) + "\n"
        old.write_text(header + "alice,1,11,Alice,Group,9\n"
                       "bob,2,22,Bob,Group,9\n", encoding="utf-8")
        new.write_text(header + "bob,2,22,Bob,Group,9\n"
                       "carol,3,33,Carol,Group,9\n", encoding="utf-8")
        difference = Path(self.directory.name) / "difference.csv"
        unique = Path(self.directory.name) / "unique.csv"
        with patch.object(tool, "connect_client") as connect:
            self.assertEqual(tool.main(["diff", str(old), str(new),
                                        "--output", str(difference)]), 0)
            self.assertEqual(tool.main(["dedupe", str(old), str(new),
                                        "--output", str(unique)]), 0)
        connect.assert_not_called()
        with difference.open(encoding="utf-8-sig", newline="") as stream:
            changes = list(csv.DictReader(stream))
        self.assertEqual([(row["user_id"], row["change"]) for row in changes],
                         [("3", "newly_observed"), ("1", "no_longer_visible")])
        with unique.open(encoding="utf-8-sig", newline="") as stream:
            members = list(csv.DictReader(stream))
        self.assertEqual([row["user_id"] for row in members], ["1", "2", "3"])
        self.assertNotIn("user_access_hash", members[0])
        with self.assertRaises(FileExistsError):
            tool.dedupe_exports([old, new], unique)

    def test_export_many_continues_after_one_failure(self):
        first = SimpleNamespace(id=1, title="First")
        second = SimpleNamespace(id=2, title="Second")
        client = Mock()
        client.iter_dialogs.return_value = iter([])
        with patch.object(tool, "connect_client", return_value=client), \
             patch.object(tool, "resolve_chat", side_effect=[first, second]), \
             patch.object(tool, "export_members", side_effect=[ValueError("denied"), 2]) as export, \
             patch("sys.stderr", io.StringIO()):
            result = tool.main(["export-many", "first", "second", "--output-dir",
                                self.directory.name])
        self.assertEqual(result, 1)
        self.assertEqual(export.call_count, 2)
        client.disconnect.assert_called_once()

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
    def test_basic_group_uses_chat_request_without_forwarding_history(self):
        from telethon.tl.functions.messages import AddChatUserRequest
        from telethon.tl.types import InputPeerUser
        from telethon.tl.types.messages import InvitedUsers

        client = Mock()
        client.return_value = InvitedUsers(updates=None, missing_invitees=[])
        invitee = tool.Invitee("alice", 1, 11)
        self.assertEqual(tool.invite_members(client, basic_chat(), [invitee], delay=0,
                                             execute=True, by_id=True), (1, 0))
        request = client.call_args.args[0]
        self.assertIsInstance(request, AddChatUserRequest)
        self.assertEqual(request.chat_id, 9)
        self.assertEqual(request.fwd_limit, 0)
        self.assertIsInstance(request.user_id, InputPeerUser)
        client.get_input_entity.assert_not_called()

    def test_cli_executes_basic_group_invite(self):
        from telethon.tl.functions.messages import AddChatUserRequest
        from telethon.tl.types.messages import InvitedUsers

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "users.csv"
            path.write_text("alice\n", encoding="utf-8")
            client = Mock()
            client.get_input_entity.return_value = "alice"
            client.return_value = InvitedUsers(updates=None, missing_invitees=[])
            with patch.object(tool, "connect_client", return_value=client), \
                 patch.object(tool, "resolve_chat", return_value=basic_chat()), \
                 patch("sys.stderr", io.StringIO()):
                self.assertEqual(tool.main(["invite", "9", str(path), "--execute",
                                            "--delay", "0"]), 0)
            self.assertIsInstance(client.call_args.args[0], AddChatUserRequest)
            client.disconnect.assert_called_once()

    def test_basic_group_decline_and_already_member_are_not_success(self):
        from telethon.errors import UserAlreadyParticipantError
        from telethon.tl.types import MissingInvitee
        from telethon.tl.types.messages import InvitedUsers

        client = Mock()
        client.get_input_entity.side_effect = ["alice", "bob"]
        client.side_effect = [InvitedUsers(updates=None,
                                          missing_invitees=[MissingInvitee(user_id=1)]),
                              UserAlreadyParticipantError(request=None)]
        invitees = [tool.Invitee("alice"), tool.Invitee("bob")]
        self.assertEqual(tool.invite_members(client, basic_chat(), invitees,
                                             delay=0, execute=True), (0, 2))

    def test_basic_group_checkpoint_is_separate_from_channel_id(self):
        from telethon.tl.types.messages import InvitedUsers

        with tempfile.TemporaryDirectory() as directory:
            progress = Path(directory) / "progress.csv"
            client = Mock()
            client.get_input_entity.return_value = "alice"
            client.return_value = InvitedUsers(updates=None, missing_invitees=[])
            invitees = [tool.Invitee("alice")]
            self.assertEqual(tool.invite_members(client, basic_chat(), invitees,
                                                 delay=0, execute=True,
                                                 progress=progress), (1, 0))
            with progress.open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(next(csv.DictReader(stream))["chat_id"], "basic:9")
            resumed = Mock()
            self.assertEqual(tool.invite_members(resumed, basic_chat(), invitees,
                                                 delay=0, execute=True,
                                                 progress=progress, resume=True), (0, 0))
            resumed.assert_not_called()
            with self.assertRaisesRegex(ValueError, "different chat"):
                tool.invite_members(Mock(), SimpleNamespace(id=9, megagroup=True),
                                    invitees, delay=0, execute=True,
                                    progress=progress, resume=True)

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
        from telethon.tl.functions.channels import InviteToChannelRequest

        client = Mock()
        client.get_input_entity.side_effect = ["first", "second"]
        client.side_effect = [SimpleNamespace(missing_invitees=[]),
                              PeerFloodError(request=None)]
        invitees = [tool.Invitee(name) for name in ("alice", "bob", "carol")]
        with self.assertRaisesRegex(RuntimeError, "stopped after 1 invites"):
            tool.invite_members(client, object(), invitees, delay=0, execute=True)
        self.assertEqual(client.call_count, 2)
        self.assertIsInstance(client.call_args_list[0].args[0], InviteToChannelRequest)

    def test_basic_group_admin_error_stops_without_checkpoint(self):
        from telethon.errors import ChatAdminRequiredError

        with tempfile.TemporaryDirectory() as directory:
            progress = Path(directory) / "progress.csv"
            client = Mock()
            client.get_input_entity.return_value = "alice"
            client.side_effect = ChatAdminRequiredError(request=None)
            with self.assertRaisesRegex(RuntimeError, "admin permission"):
                tool.invite_members(client, basic_chat(), [tool.Invitee("alice")],
                                    delay=0, execute=True, progress=progress)
            self.assertFalse(progress.exists())

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
    def test_qr_login_uses_local_session_without_phone_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / "login"
            client = Mock()
            client.connect = AsyncMock()
            client.disconnect = AsyncMock()
            client.is_user_authorized = AsyncMock(return_value=False)
            login = Mock(url="tg://login?token=fake")
            login.wait = AsyncMock()
            client.qr_login = AsyncMock(return_value=login)
            with patch.dict(os.environ, {"TELEGRAM_API_ID": "123",
                                      "TELEGRAM_API_HASH": "fake",
                                      "TELEGRAM_SESSION": str(session)}), \
                 patch("telethon.TelegramClient", return_value=client) as client_class, \
                 patch("qrcode.QRCode") as qr_class:
                self.assertEqual(tool.main(["login", "--qr"]), 0)
            client_class.assert_called_once_with(str(session), 123, "fake")
            client.qr_login.assert_awaited_once()
            login.wait.assert_awaited_once()
            client.disconnect.assert_awaited_once()
            qr_class.return_value.add_data.assert_called_once_with(login.url)

    def test_doctor_never_contacts_telegram_or_prints_secret(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / "custom.name"
            Path(str(session) + ".session").write_text("fake", encoding="utf-8")
            with patch.dict(os.environ, {"TELEGRAM_API_ID": "123",
                                      "TELEGRAM_API_HASH": "private-value",
                                      "TELEGRAM_SESSION": str(session)}), \
                 patch.object(tool, "connect_client") as connect, \
                 patch("sys.stdout", output):
                self.assertEqual(tool.main(["doctor"]), 0)
            connect.assert_not_called()
        self.assertIn("Session: present", output.getvalue())
        self.assertNotIn("private-value", output.getvalue())

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

    def test_numbered_invite_flow_lists_basic_group(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "users.csv"
            path.write_text("alice\n", encoding="utf-8")
            client = Mock()
            chat = basic_chat()
            item = SimpleNamespace(id=9, name="Basic Group", entity=chat,
                                   is_group=True, is_channel=False)
            client.iter_dialogs.return_value = iter([item])
            with patch("builtins.input", side_effect=["2", "0", "1"]), \
                 patch.object(tool, "connect_client", return_value=client), \
                 patch.object(tool, "invite_members", return_value=(1, 0)) as invite, \
                 patch("sys.stderr", io.StringIO()):
                self.assertEqual(tool.main([str(path)]), 0)
            self.assertIs(invite.call_args.args[1], chat)
            client.disconnect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
