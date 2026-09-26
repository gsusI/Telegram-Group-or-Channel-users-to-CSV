"""Regression coverage for packaged startup errors, without running Telegram."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipIf(os.name == "nt", "POSIX shell shortcut")
class MacShortcutTests(unittest.TestCase):
    def test_packaged_failure_does_not_request_python(self):
        with tempfile.TemporaryDirectory(prefix="telegram shortcut ") as temporary:
            folder = Path(temporary)
            shortcut = folder / "Start Telegram CSV.command"
            shutil.copy2(Path(__file__).resolve().parents[1] / shortcut.name, shortcut)
            executable = folder / "telegram-csv-ui"
            executable.write_text("#!/bin/sh\nexit 137\n")
            executable.chmod(0o755)
            result = subprocess.run(
                ["/bin/sh", str(shortcut)], input="", text=True,
                capture_output=True, timeout=5,
            )
            self.assertEqual(result.returncode, 137)
            self.assertIn("Python is already included", result.stdout)
            self.assertIn("macOS terminated", result.stdout)
            self.assertNotIn("Source installs", result.stdout)
            self.assertNotIn("Press Enter", result.stdout)
