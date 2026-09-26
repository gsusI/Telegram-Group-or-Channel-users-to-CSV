"""Portable browser UI launcher; also the entry point for frozen releases."""

import argparse
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile


def app_directory():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def resource_directory():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def select_port(requested=0):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", requested))
        return probe.getsockname()[1]


def prepare_data(directory):
    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    # Fail before starting the server if a USB drive or extracted folder is read-only.
    with tempfile.TemporaryFile(dir=directory):
        pass
    os.environ["TELEGRAM_CSV_DATA_DIR"] = str(directory)
    os.environ.setdefault("TELEGRAM_SESSION", str(directory / "session"))
    return directory


def main(argv=None):
    parser = argparse.ArgumentParser(description="Open Telegram CSV in your browser. Keep this window open while using it.")
    parser.add_argument("--data-dir", type=Path, help="Session and export folder (default: data beside the launcher)")
    parser.add_argument("--port", type=int, default=0, help="Local port; automatically choose an available port by default")
    parser.add_argument("--no-browser", action="store_true", help="Print the URL without opening a browser")
    parser.add_argument("--check", action="store_true", help="Check bundled resources and dependencies, then exit")
    args = parser.parse_args(argv)
    root = app_directory()
    if not getattr(sys, "frozen", False) and importlib.util.find_spec("streamlit") is None:
        environment = root / ".ui-venv"
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            print("First launch: preparing the local Python environment…", flush=True)
            subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(root / "requirements-ui.txt")], check=True)
        return subprocess.call([str(python), str(Path(__file__).resolve()), *(sys.argv[1:] if argv is None else argv)])

    from streamlit.web import bootstrap
    import telegram_csv_ui  # Included explicitly in frozen builds; validates dependencies.

    script = resource_directory() / "telegram_csv_ui.py"
    if not script.is_file():
        raise RuntimeError(f"Missing UI resource: {script}")
    if args.check:
        print("Telegram CSV UI: dependencies and resources OK")
        return 0
    data = prepare_data(args.data_dir or os.environ.get("TELEGRAM_CSV_DATA_DIR", root / "data"))
    port = select_port(args.port)
    print(f"Telegram CSV: http://127.0.0.1:{port}\nData folder: {data}\nKeep this window open. Press Ctrl+C to stop.", flush=True)
    # Explicit settings also work when launched by Finder, from another cwd, or frozen.
    options = {
        "global.developmentMode": False,
        "server.address": "127.0.0.1", "server.port": port,
        "server.headless": args.no_browser, "server.fileWatcherType": "none",
        "server.enableXsrfProtection": True, "browser.gatherUsageStats": False,
        "client.toolbarMode": "minimal", "theme.primaryColor": "#229ED9",
        "theme.backgroundColor": "#F7F9FC", "theme.secondaryBackgroundColor": "#EAF1F6",
        "theme.textColor": "#17212B",
    }
    bootstrap.load_config_options(options)
    bootstrap.run(str(script), False, [], options)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Could not launch Telegram CSV: {error}", file=sys.stderr)
        print("Use a writable folder, or pass --data-dir with another location.", file=sys.stderr)
        raise SystemExit(1)
