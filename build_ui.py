"""Build a platform-specific, relocatable folder including the UI runtime."""

from pathlib import Path
import shutil
import subprocess
import sys
import plistlib

root = Path(__file__).resolve().parent
mac = sys.platform == "darwin"
name = "Telegram CSV" if mac else "telegram-csv-ui"
command = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
    "--name", name, "--collect-all", "streamlit",
    "--copy-metadata", "streamlit", "--hidden-import", "telegram_csv_ui",
    "--add-data", f"{root / 'telegram_csv_ui.py'}:.",
]
if mac:
    command += ["--windowed", "--osx-bundle-identifier", "io.github.gsusi.telegram-csv"]
command.append(str(root / ("macos_app.py" if mac else "launch.py")))
subprocess.run(command, cwd=root, check=True)
if mac:
    bundle = root / "dist" / "Telegram CSV.app"
    info = bundle / "Contents" / "Info.plist"
    with info.open("rb") as handle:
        metadata = plistlib.load(handle)
    metadata["LSUIElement"] = True
    with info.open("wb") as handle:
        plistlib.dump(metadata, handle)
    # Seal the complete app after its final metadata change. No files inside the
    # app are modified at runtime, preserving macOS's per-app approval identity.
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
    raise SystemExit(0)
destination = root / "dist" / "telegram-csv-ui"
for filename in ("Start Telegram CSV.command", "Start Telegram CSV.bat", "PORTABLE.md"):
    shutil.copy2(root / filename, destination / filename)
