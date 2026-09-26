"""Check a frozen UI starts from another cwd, serves HTTP, and stops cleanly."""

import argparse
import csv
import io
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from launch import select_port


def check_browser(url):
    """Exercise the bundled app using invented CSVs, without Telegram access."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url)
            page.get_by_role("heading", name="Export members", exact=True).wait_for()
            assert page.get_by_role("button", name="Load my chats").is_disabled()
            page.get_by_role("link", name="Local tools").click()
            page.get_by_role("heading", name="Compare local exports").wait_for()
            header = "username,user_id,user_access_hash,name,group,group_id\n"
            earlier = (header + "alice,1,11,Alice,Example,9\n").encode()
            later = (header + "bob,2,22,Bob,Example,9\n").encode()
            for label, data in (("Earlier export", earlier), ("Later export", later)):
                page.get_by_test_id("stFileUploader").filter(has_text=label).locator(
                    "input[type=file]").set_input_files({
                        "name": label + ".csv", "mimeType": "text/csv", "buffer": data,
                    })
            page.get_by_role("button", name="Compare exports").click()
            download_button = page.get_by_role("button", name="Download changes")
            download_button.wait_for()
            with page.expect_download() as event:
                download_button.click()
            rows = list(csv.DictReader(io.StringIO(Path(event.value.path()).read_text(encoding="utf-8-sig"))))
            assert {row["change"] for row in rows} == {"newly_observed", "no_longer_visible"}, rows
            page.get_by_role("tab", name="Combine observations").click()
            page.get_by_test_id("stFileUploader").filter(has_text="Member exports").locator(
                "input[type=file]").set_input_files([
                    {"name": "earlier.csv", "mimeType": "text/csv", "buffer": earlier},
                    {"name": "later.csv", "mimeType": "text/csv", "buffer": later},
                ])
            page.get_by_role("button", name="Combine and deduplicate").click()
            with page.expect_download() as event:
                page.get_by_role("button", name="Download unique members").click()
            rows = list(csv.DictReader(io.StringIO(Path(event.value.path()).read_text(encoding="utf-8-sig"))))
            assert len(rows) == 2 and "user_access_hash" not in rows[0], rows
            page.get_by_role("link", name="Invite", exact=False).click()
            page.get_by_role("heading", name="Invite from CSV").wait_for()
            assert page.get_by_role("button", name="Invite 0 people", exact=False).is_disabled()
            assert page.get_by_test_id("stException").count() == 0
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.locator("body").evaluate("el => el.scrollWidth <= window.innerWidth"), "Horizontal overflow"
            print("Portable browser UI: navigation, uploads, comparison, dedupe, downloads and mobile layout OK")
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--browser", action="store_true", help="Also verify rendered workflows using Playwright Chromium")
    args = parser.parse_args()
    executable = args.executable.resolve()
    subprocess.run([str(executable), "--check"], check=True, timeout=90)
    with tempfile.TemporaryDirectory(prefix="telegram-ui-smoke-") as temporary:
        root = Path(temporary)
        port = select_port()
        with (root / "startup.log").open("w+") as log:
            process = subprocess.Popen([
                str(executable), "--no-browser", "--port", str(port),
                "--data-dir", str(root / "portable data"),
            ], cwd=root, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("Portable UI exited before becoming ready")
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1) as response:
                            if response.status == 200:
                                break
                    except (urllib.error.URLError, TimeoutError):
                        time.sleep(0.2)
                else:
                    raise RuntimeError("Portable UI did not become ready within 45 seconds")
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                    assert b"<html" in response.read().lower(), "Missing browser entry page"
                assert (root / "portable data").is_dir(), "Missing portable data directory"
                print("Portable UI: alternate cwd, spaced data path, health and browser entry OK")
                if args.browser:
                    check_browser(f"http://127.0.0.1:{port}")
            except BaseException:
                log.seek(0)
                print(log.read())
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


if __name__ == "__main__":
    main()
