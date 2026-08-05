"""Browser acceptance fixture for the checklist JSON export."""

from __future__ import annotations

import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


APP_PATH = Path(__file__).resolve().parents[1] / "app"


def test_export_counts() -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(APP_PATH))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                url = f"http://127.0.0.1:{server.server_address[1]}/mini_checklist.html"
                page.goto(url, wait_until="networkidle")
                page.evaluate("localStorage.clear(); location.reload()")
                page.wait_for_load_state("networkidle")
                for title in ("Export A", "Export B"):
                    page.locator("#title-input").fill(title)
                    page.locator("#add-form button[type=submit]").click()
                page.locator("#checklist li", has_text="Export A").locator(
                    "input[type=checkbox]"
                ).check()
                page.locator("#exportBtn").click()
                assert json.loads(page.locator("#export-output").inner_text()) == {
                    "total": 2,
                    "completed": 1,
                    "pending": 1,
                }
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
