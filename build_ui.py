"""Build a platform-specific, relocatable folder including the UI runtime."""

from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent
subprocess.run([
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
    "--name", "telegram-csv-ui", "--collect-all", "streamlit",
    "--copy-metadata", "streamlit", "--hidden-import", "telegram_csv_ui",
    "--add-data", f"{root / 'telegram_csv_ui.py'}:.", str(root / "launch.py"),
], cwd=root, check=True)
destination = root / "dist" / "telegram-csv-ui"
for filename in ("Start Telegram CSV.command", "Start Telegram CSV.bat", "PORTABLE.md"):
    shutil.copy2(root / filename, destination / filename)
