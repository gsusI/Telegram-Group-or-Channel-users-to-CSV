import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import launch


class LauncherTests(unittest.TestCase):
    def test_launcher_applies_loopback_configuration_before_server_start(self):
        try:
            from streamlit.web import bootstrap
        except ImportError:
            self.skipTest("UI dependencies are optional")
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True), \
                patch.object(launch, "select_port", return_value=8519), \
                patch.object(bootstrap, "load_config_options") as configure, \
                patch.object(bootstrap, "run") as run:
            run.side_effect = lambda *args: self.assertTrue(configure.called)
            self.assertEqual(launch.main(["--no-browser", "--data-dir", folder]), 0)
            options = configure.call_args.args[0]
            self.assertEqual(options["server.address"], "127.0.0.1")
            self.assertEqual(options["server.port"], 8519)
            self.assertFalse(options["global.developmentMode"])
            self.assertTrue(options["server.headless"])

    def test_portable_paths_do_not_depend_on_working_directory(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            data = launch.prepare_data(Path(folder) / "portable data")
            self.assertEqual(Path(os.environ["TELEGRAM_SESSION"]), data / "session")
            self.assertTrue(data.is_dir())

    def test_explicit_session_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"TELEGRAM_SESSION": "custom"}):
            launch.prepare_data(folder)
            self.assertEqual(os.environ["TELEGRAM_SESSION"], "custom")

    def test_frozen_resources_and_writable_data_have_separate_roots(self):
        with patch.object(launch.sys, "frozen", True, create=True), \
                patch.object(launch.sys, "executable", "/tmp/portable/app"), \
                patch.object(launch.sys, "_MEIPASS", "/tmp/portable/_internal", create=True):
            self.assertEqual(launch.app_directory(), Path("/tmp/portable").resolve())
            self.assertEqual(launch.resource_directory(), Path("/tmp/portable/_internal"))
