import threading

import pytest

from bigville.management import http
from bigville.management.http import create_server

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def browser_server(monkeypatch):
    catalog = {
        "schema_version": 1, "engine_build": {"git_commit": None},
        "scenarios": [{
            "id": "town100", "name": "Town 100", "source": "built_in",
            "type": "village", "physical_subsystems": {"metabolism": True},
        }],
        "backends": [
            {"kind": "simple", "available": True},
            {"kind": "ocelot", "available": False, "reason": "Install the Ocelot adapter."},
        ],
    }
    monkeypatch.setattr(http, "build_capability_catalog", lambda: catalog)
    # The Backends page now renders the dedicated profile catalog. Keep the
    # unavailable integration deterministic without relying on whether Ocelot
    # happens to be installed in the developer's environment.
    class ProfileRegistryFixture:
        def __init__(self, *_args, **_kwargs):
            pass

        def public_profiles(self):
            return {
                "schema_version": 1,
                "revision": "test-profile-revision",
                "profiles": [
                    {"id": "simple.default", "name": "Simple default",
                     "kind": "simple", "revision": "builtin-1",
                     "available": True, "reason": None},
                    {"id": "ocelot.default", "name": "Ocelot default",
                     "kind": "ocelot", "revision": "builtin-1",
                     "available": False, "reason": "Install the Ocelot adapter."},
                ],
            }

    monkeypatch.setattr(http, "BackendProfileRegistry", ProfileRegistryFixture)
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{server.server_address[0]}:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def page():
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright Chromium is unavailable: {exc}")
        test_page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            yield test_page
        finally:
            browser.close()


def test_keyboard_navigation_and_backend_unavailable_state(page, browser_server):
    page.goto(browser_server, wait_until="networkidle")
    page.locator("button[aria-controls='backends-panel']").focus()
    page.keyboard.press("Enter")
    assert page.locator("#page-title").inner_text() == "Backends"
    assert page.locator("button[aria-controls='backends-panel']").get_attribute("aria-current") == "page"
    assert page.get_by_text("Unavailable", exact=True).count() == 1
    assert page.get_by_text("Install the Ocelot adapter.").is_visible()


def test_mobile_layout_has_no_horizontal_page_overflow(page, browser_server):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(browser_server, wait_until="networkidle")
    dimensions = page.evaluate("({viewport: innerWidth, document: document.documentElement.scrollWidth})")
    assert dimensions["document"] <= dimensions["viewport"]


def test_failed_catalog_request_shows_accessible_retry(page, browser_server, monkeypatch):
    monkeypatch.setattr(http, "build_capability_catalog", lambda: (_ for _ in ()).throw(RuntimeError("catalog test failure")))
    page.goto(browser_server, wait_until="domcontentloaded")
    assert page.get_by_role("alert").is_visible()
    assert page.get_by_text("Catalog could not be loaded").is_visible()
    assert page.get_by_role("button", name="Retry catalog").is_visible()
