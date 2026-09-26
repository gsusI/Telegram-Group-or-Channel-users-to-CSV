"""One macOS application owns the bundled server and its native menu bar UI."""

import os
from pathlib import Path
import subprocess
import signal
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from launch import main as serve, prepare_data, select_port


def data_directory():
    return Path(os.environ.get(
        "TELEGRAM_CSV_DATA_DIR",
        Path.home() / "Library" / "Application Support" / "Telegram CSV",
    )).expanduser()


def server_command(port, data):
    prefix = [sys.executable]
    if not getattr(sys, "frozen", False):
        prefix.append(str(Path(__file__).resolve()))
    return [*prefix, "--serve", "--no-browser", "--port", str(port), "--data-dir", str(data)]


def stop_server(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_app():
    import rumps

    class TelegramApp(rumps.App):
        def __init__(self):
            super().__init__("Telegram CSV", title="Telegram CSV", quit_button=None)
            self.process = None
            self.log = None
            self.ready = False
            self.stopping = False
            self.menu = [
                rumps.MenuItem("Starting…"),
                rumps.MenuItem("Open Telegram CSV", callback=self.open_browser),
                rumps.MenuItem("Open data folder", callback=self.open_data),
                rumps.MenuItem("Quit Telegram CSV", callback=self.quit),
            ]
            self.data = prepare_data(data_directory())
            self.port = select_port()
            self.url = f"http://127.0.0.1:{self.port}"
            self.log = (self.data / "launcher.log").open("w", encoding="utf-8")
            try:
                self.process = subprocess.Popen(
                    server_command(self.port, self.data), cwd=self.data,
                    stdout=self.log, stderr=subprocess.STDOUT,
                )
            except BaseException:
                self.log.close()
                raise
            self.deadline = time.monotonic() + 90
            self.timer = rumps.Timer(self.check_server, 0.5)
            self.timer.start()
            signal.signal(signal.SIGTERM, self.request_quit)
            signal.signal(signal.SIGINT, self.request_quit)

        def request_quit(self, *_):
            # Cocoa and subprocess cleanup run on the next main-loop tick.
            self.stopping = True

        def check_server(self, _):
            if self.stopping:
                self.quit(None)
                return
            if self.process.poll() is not None:
                self.fail("The local server stopped. See launcher.log in the data folder.")
                return
            if self.ready:
                return
            try:
                with urllib.request.urlopen(self.url + "/_stcore/health", timeout=0.2) as response:
                    if response.status != 200:
                        return
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() > self.deadline:
                    self.fail("The local server did not start within 90 seconds. See launcher.log in the data folder.")
                return
            self.ready = True
            self.menu["Starting…"].title = "Running locally"
            self.open_browser(None)

        def open_browser(self, _):
            if self.ready:
                webbrowser.open(self.url)

        def open_data(self, _):
            subprocess.run(["/usr/bin/open", str(self.data)], check=False)

        def fail(self, message):
            self.timer.stop()
            stop_server(self.process)
            self.ready = False
            self.menu["Starting…"].title = "Startup failed"
            rumps.alert("Telegram CSV could not run", message)

        def quit(self, _):
            self.timer.stop()
            stop_server(self.process)
            if self.log:
                self.log.close()
            rumps.quit_application()

    app = None
    try:
        app = TelegramApp()
        app.run()
    except Exception as error:
        rumps.alert("Telegram CSV could not start", str(error))
        raise
    finally:
        if app is not None:
            stop_server(app.process)
            if app.log:
                app.log.close()


if __name__ == "__main__":
    if "--serve" in sys.argv:
        arguments = sys.argv[1:]
        arguments.remove("--serve")
        raise SystemExit(serve(arguments))
    elif len(sys.argv) > 1:
        raise SystemExit(serve())
    else:
        run_app()
