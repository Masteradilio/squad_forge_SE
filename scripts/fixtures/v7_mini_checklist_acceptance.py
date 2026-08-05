"""Deterministic browser acceptance fixture for the V7 Mini Checklist PRD."""

from __future__ import annotations

import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


APP_PATH = Path(__file__).resolve().parents[1] / "app"


def _serve_app() -> tuple[ThreadingHTTPServer, str]:
    handler = partial(SimpleHTTPRequestHandler, directory=str(APP_PATH))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}/mini_checklist.html"


def _fresh_page(page: Page, url: str) -> None:
    page.goto(url, wait_until="networkidle")
    page.evaluate("localStorage.clear(); location.reload()")
    page.wait_for_load_state("networkidle")


def test_create_reject_and_persist(page: Page) -> None:
    server, url = _serve_app()
    try:
        _fresh_page(page, url)
        checklist = page.locator("#checklist li")
        baseline = checklist.count()
        page.locator("#title-input").fill("Persist me")
        page.locator("#add-form button[type=submit]").click()
        assert checklist.count() == baseline + 1
        item = page.locator("#checklist li", has_text="Persist me")
        assert item.count() == 1
        checkbox = item.locator("input[type=checkbox]")
        checkbox.check()
        assert checkbox.is_checked()

        page.locator("#title-input").fill("")
        page.locator("#add-form button[type=submit]").click()
        assert checklist.count() == baseline + 1

        page.reload(wait_until="networkidle")
        persisted = page.locator("#checklist li", has_text="Persist me")
        assert persisted.locator("input[type=checkbox]").is_checked()
    finally:
        server.shutdown()
        server.server_close()


def test_export_counts(page: Page) -> None:
    server, url = _serve_app()
    try:
        _fresh_page(page, url)
        page.locator("#title-input").fill("Export A")
        page.locator("#add-form button[type=submit]").click()
        page.locator("#title-input").fill("Export B")
        page.locator("#add-form button[type=submit]").click()
        page.locator("#checklist li", has_text="Export A").locator("input[type=checkbox]").check()
        page.locator("#exportBtn").click()
        summary = json.loads(page.locator("#export-output").inner_text())
        assert summary == {"total": 2, "completed": 1, "pending": 1}
    finally:
        server.shutdown()
        server.server_close()
