"""A connected browser journey through the local app for the sweep route.

Runs only when Playwright and a launchable Chromium are present; CI without
them skips. Responses come from the bundled deterministic fixture adapter, so
this checks the page, the form, the deck rendering and the served files, not
card quality.
"""

import json
import threading

import pytest

from lamina.production_example import FixtureAdapter
from lamina.studio_server import StudioServer
from test_project_api import _call, _upload_four

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def browser():
    with playwright.sync_playwright() as p:
        try:
            instance = p.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - environment without Chromium
            pytest.skip(f"Chromium not launchable: {exc}")
        yield instance
        instance.close()


def test_cards_journey_renders_deck_and_serves_the_anki_file(tmp_path, browser):
    server = StudioServer(tmp_path / "studio", port=0)
    server.provider = FixtureAdapter()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _upload_four(server)
        base = f"http://127.0.0.1:{server.server_port}"
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(base + "/", wait_until="networkidle")
        page.get_by_label("Output format").select_option("cards")
        boxes = page.locator(".pb-source input[type=checkbox]")
        boxes.first.wait_for(timeout=10_000)
        for box in boxes.all():
            if not box.is_checked() and box.is_enabled():
                box.check()
        page.get_by_label("Project goal").fill("Flashcards about lease safety.")
        page.get_by_role("button", name="Start project").click()
        deck = page.locator(".pb-deck")
        deck.wait_for(timeout=30_000)
        text = deck.inner_text()
        assert "cards" in text and "audited" in text
        link = page.get_by_role("link", name="Download Anki deck (TSV)")
        assert link.count() == 1
        href = link.get_attribute("href")
        code, raw = _call(server, href if href.startswith("/") else "/" + href.split(base, 1)[-1].lstrip("/"))
        assert code == 200 and raw.decode().count("\t") >= 2
        assert not errors, errors
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
