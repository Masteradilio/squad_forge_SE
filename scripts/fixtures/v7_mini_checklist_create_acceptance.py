"""Browser acceptance fixture for checklist creation and listing."""

from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


APP_PATH = Path(__file__).resolve().parents[1] / "app"


def test_create_and_list_item() -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(APP_PATH))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(
                    f"http://127.0.0.1:{server.server_address[1]}/mini_checklist.html",
                    wait_until="networkidle",
                )
                page.evaluate("localStorage.clear(); location.reload()")
                page.wait_for_load_state("networkidle")
                items = page.locator("#checklist li")
                baseline = items.count()
                page.locator("#title-input").fill("First item")
                page.locator("#add-form button[type=submit]").click()
                assert items.count() == baseline + 1
                item = page.locator("#checklist li", has_text="First item")
                assert item.count() == 1
                assert item.locator("input[type=checkbox]").count() == 1
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
