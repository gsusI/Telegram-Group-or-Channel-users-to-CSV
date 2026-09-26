import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import macos_app


class MacAppTests(unittest.TestCase):
    def test_controller_waits_for_health_opens_once_and_quits_cleanly(self):
        class FakeApp:
            def __init__(self, *args, **kwargs):
                pass

            @property
            def menu(self):
                return self._menu

            @menu.setter
            def menu(self, items):
                self._menu = {item.title: item for item in items}

            def run(self):
                self.check_server(None)
                self.check_server(None)
                self.request_quit()
                self.check_server(None)

        fake = SimpleNamespace(
            App=FakeApp,
            MenuItem=lambda title, callback=None: SimpleNamespace(title=title, callback=callback),
            Timer=Mock(), alert=Mock(), quit_application=Mock(),
        )
        process = Mock()
        process.poll.side_effect = [None, None, None, 0]
        response = Mock()
        response.__enter__ = Mock(return_value=SimpleNamespace(status=200))
        response.__exit__ = Mock(return_value=False)
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(macos_app.sys.modules, {"rumps": fake}), \
                patch.object(macos_app, "data_directory", return_value=Path(folder)), \
                patch.object(macos_app, "prepare_data", return_value=Path(folder)), \
                patch.object(macos_app, "select_port", return_value=8510), \
                patch.object(macos_app.subprocess, "Popen", return_value=process), \
                patch.object(macos_app.signal, "signal"), \
                patch.object(macos_app.urllib.request, "urlopen", return_value=response), \
                patch.object(macos_app.webbrowser, "open") as browser:
            macos_app.run_app()
        browser.assert_called_once_with("http://127.0.0.1:8510")
        process.terminate.assert_called_once()
        fake.quit_application.assert_called_once()
        fake.alert.assert_not_called()

    def test_data_outside_bundle_and_downloads(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "home", return_value=Path("/Users/test")):
            self.assertEqual(macos_app.data_directory(), Path("/Users/test/Library/Application Support/Telegram CSV"))

    def test_explicit_portable_data_directory(self):
        with patch.dict(os.environ, {"TELEGRAM_CSV_DATA_DIR": "/Volumes/USB/Telegram Data"}):
            self.assertEqual(macos_app.data_directory(), Path("/Volumes/USB/Telegram Data"))

    def test_child_uses_same_bundled_executable_and_no_browser(self):
        with patch.object(macos_app.sys, "frozen", True, create=True), patch.object(macos_app.sys, "executable", "/tmp/Telegram CSV.app/Contents/MacOS/Telegram CSV"):
            command = macos_app.server_command(8510, Path("/tmp/data folder"))
        self.assertEqual(command, ["/tmp/Telegram CSV.app/Contents/MacOS/Telegram CSV", "--serve", "--no-browser", "--port", "8510", "--data-dir", str(Path("/tmp/data folder"))])

    def test_quit_stops_owned_server(self):
        process = Mock()
        process.poll.return_value = None
        macos_app.stop_server(process)
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)

    def test_quit_kills_server_only_after_timeout(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("server", 5), None]
        macos_app.stop_server(process)
        process.kill.assert_called_once()

    def test_exited_server_is_not_signalled(self):
        process = Mock()
        process.poll.return_value = 1
        macos_app.stop_server(process)
        process.terminate.assert_not_called()
