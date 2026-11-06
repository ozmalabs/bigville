import json
import threading
from urllib.request import urlopen

import pytest

from bigville.management.http import API_PREFIX, create_server

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def scenario_root(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    scenario = {
        "id": "browser_fixture", "name": "Browser Test World",
        "map": {"grid": [["wall", "wall", "wall", "wall", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "wall", "wall", "wall", "wall"]],
                 "layout": {"w": 5, "h": 5, "homes": [[2, 2]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "cheap",
                    "home_cell": [2, 2]}],
        "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
        "physical_subsystems": {"metabolism": True, "ecology": False},
    }
    (root / "browser_fixture.json").write_text(json.dumps(scenario))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    return root


@pytest.fixture
def management_server(tmp_path, scenario_root):
    server = create_server(port=0, data_dir=tmp_path / "management-data")
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


def open_new_run(page, base, *, seed="41", turn_limit="1"):
    page.goto(base, wait_until="domcontentloaded")
    page.get_by_role("button", name="New run").click()
    page.get_by_label("Run name").fill("Browser launch")
    page.get_by_label("Scenario", exact=True).select_option("browser_fixture")
    page.get_by_label("World seed").fill(seed)
    page.get_by_label("Turn limit Optional").fill(turn_limit)
    page.get_by_role("button", name="Validate & preview").click()
    page.locator("#review-panel:not([hidden])").wait_for()


def test_create_preview_start_and_list_keep_preview_hash_and_seed(page, management_server):
    launched_records = []

    def watch(response):
        if response.url.endswith(API_PREFIX + "/runs") and response.request.method == "POST":
            launched_records.append(response.json())

    page.on("response", watch)
    open_new_run(page, management_server, seed="41", turn_limit="1")
    preview_hash = page.locator("#config-hash").inner_text()
    assert page.get_by_text("Ada · simple (scenario override)").is_visible()
    assert "5 × 5 cells" in page.locator("#map-summary").inner_text()
    page.get_by_role("button", name="Create & start run").click()
    page.get_by_role("heading", name="Your simulations").wait_for()
    page.get_by_role("heading", name="Browser launch").wait_for()

    assert len(launched_records) == 1
    record = launched_records[0]
    assert record["config_hash"] == preview_hash
    assert record["config"]["seed"] == 41
    assert record["resolved_actor_backends"] == [
        {"actor": "Ada", "backend": "simple", "source": "scenario_override"}
    ]
    with urlopen(management_server + API_PREFIX + "/runs") as response:
        runs = json.load(response)["runs"]
    assert len(runs) == 1
    assert runs[0]["config_hash"] == preview_hash


def test_editing_any_input_invalidates_review_and_preserves_values(page, management_server):
    open_new_run(page, management_server)
    assert page.locator("#create-start").is_enabled()
    page.get_by_label("World seed").fill("92")
    assert page.locator("#review-panel").is_hidden()
    assert page.locator("#create-start").is_disabled()
    assert page.get_by_label("World seed").input_value() == "92"
    assert "not been reviewed" in page.locator("#validation-status").inner_text()


def test_server_rejection_for_unsupported_backend_is_shown_at_field(page, management_server):
    page.goto(management_server, wait_until="domcontentloaded")
    page.get_by_role("button", name="New run").click()
    page.get_by_label("Run name").fill("Unsupported choice")
    page.get_by_label("Scenario", exact=True).select_option("browser_fixture")
    page.locator("#default-backend").evaluate(
        "element => element.add(new Option('Ocelot', 'ocelot'))")
    page.get_by_label("Default backend").select_option("ocelot")
    page.get_by_role("button", name="Validate & preview").click()
    error = page.locator("#error-default_backend")
    error.wait_for(state="visible")
    assert "Only the simple backend" in error.inner_text()
    assert page.locator("#review-panel").is_hidden()


def test_stale_hash_conflict_is_field_addressed_and_preserves_draft(page, management_server):
    open_new_run(page, management_server)

    def reject_stale(route):
        if route.request.method == "POST":
            route.fulfill(status=409, content_type="application/json", body=json.dumps({
                "error": {"code": "run_conflict", "message": "Expected configuration hash is stale.",
                          "fields": {"expected_config_hash": "Revalidate the draft."}},
            }))
        else:
            route.continue_()

    page.route("**" + API_PREFIX + "/runs", reject_stale)
    page.get_by_role("button", name="Create & start run").click()
    error = page.locator("#error-review")
    error.wait_for(state="visible")
    assert "Revalidate the draft" in error.inner_text()
    assert page.locator("#review-panel").is_hidden()
    assert page.get_by_label("Run name").input_value() == "Browser launch"


def test_double_click_creates_only_one_run(page, management_server):
    open_new_run(page, management_server, seed="77", turn_limit="1")
    page.get_by_role("button", name="Create & start run").dblclick()
    page.get_by_role("heading", name="Your simulations").wait_for()
    with urlopen(management_server + API_PREFIX + "/runs") as response:
        runs = json.load(response)["runs"]
    assert len(runs) == 1
    assert runs[0]["config"]["seed"] == 77


def test_mobile_keyboard_navigation_and_seed_randomization(page, management_server):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(management_server, wait_until="domcontentloaded")
    runs_nav = page.get_by_role("button", name="Runs")
    runs_nav.focus()
    page.keyboard.press("Enter")
    page.get_by_role("button", name="New run").focus()
    page.keyboard.press("Enter")
    assert page.locator("#run-name").evaluate("el => el === document.activeElement")
    page.get_by_role("button", name="Random").focus()
    page.keyboard.press("Enter")
    seed = page.get_by_label("World seed").input_value()
    assert seed.isdigit()
    dimensions = page.evaluate("({viewport: innerWidth, document: document.documentElement.scrollWidth})")
    assert dimensions["document"] <= dimensions["viewport"]


@pytest.mark.parametrize("endpoint", ["/run-drafts/validate", "/run-drafts/preview"])
def test_delayed_response_cannot_restore_review_for_edited_draft(page, management_server, endpoint):
    page.add_init_script("""
      (() => {
        const originalFetch = window.fetch.bind(window);
        window.__fetchPaths = [];
        window.__holdPath = null;
        window.__releaseHeld = null;
        window.__heldCompleted = false;
        window.fetch = async (...args) => {
          const url = String(args[0]);
          window.__fetchPaths.push(url);
          let held = false;
          if (window.__holdPath && url.endsWith(window.__holdPath)) {
            held = true;
            window.__holdPath = null;
            await new Promise(resolve => { window.__releaseHeld = resolve; });
          }
          const response = await originalFetch(...args);
          if (held) window.__heldCompleted = true;
          return response;
        };
      })();
    """)
    page.goto(management_server, wait_until="domcontentloaded")
    page.get_by_role("button", name="New run").click()
    page.get_by_label("Run name").fill("Delayed draft")
    page.get_by_label("Scenario", exact=True).select_option("browser_fixture")
    page.get_by_label("World seed").fill("41")
    page.evaluate("endpoint => { window.__holdPath = endpoint; window.__heldCompleted = false; }", endpoint)
    page.get_by_role("button", name="Validate & preview").click()
    page.wait_for_function("window.__releaseHeld !== null")
    page.get_by_label("World seed").fill("99")
    page.evaluate("() => { const release = window.__releaseHeld; window.__releaseHeld = null; release(); }")
    page.wait_for_function("window.__heldCompleted === true")
    assert page.locator("#review-panel").is_hidden()
    assert page.locator("#create-start").is_disabled()
    assert page.get_by_label("World seed").input_value() == "99"
    assert page.get_by_role("status").filter(has_text="Changes have not been reviewed").is_visible()
    if endpoint.endswith("validate"):
        preview_requests = page.evaluate(
            "() => window.__fetchPaths.filter(path => path.endsWith('/run-drafts/preview')).length")
        assert preview_requests == 0


def test_delayed_validation_error_is_ignored_after_backend_edit(page, management_server):
    page.add_init_script("""
      (() => {
        const originalFetch = window.fetch.bind(window);
        window.__releaseHeld = null;
        window.__heldCompleted = false;
        window.fetch = async (...args) => {
          const url = String(args[0]);
          if (window.__holdValidation && url.endsWith('/run-drafts/validate')) {
            window.__holdValidation = false;
            await new Promise(resolve => { window.__releaseHeld = resolve; });
            const response = await originalFetch(...args);
            window.__heldCompleted = true;
            return response;
          }
          return originalFetch(...args);
        };
      })();
    """)
    page.goto(management_server, wait_until="domcontentloaded")
    page.get_by_role("button", name="New run").click()
    page.get_by_label("Run name").fill("Stale validation error")
    page.get_by_label("Scenario", exact=True).select_option("browser_fixture")
    page.locator("#default-backend").evaluate(
        "element => element.add(new Option('Ocelot', 'ocelot'))")
    page.get_by_label("Default backend").select_option("ocelot")
    page.evaluate("() => { window.__holdValidation = true; window.__heldCompleted = false; }")
    page.get_by_role("button", name="Validate & preview").click()
    page.wait_for_function("window.__releaseHeld !== null")
    page.get_by_label("Default backend").select_option("simple")
    page.evaluate("() => { const release = window.__releaseHeld; window.__releaseHeld = null; release(); }")
    page.wait_for_function("window.__heldCompleted === true")
    assert page.locator("#error-default_backend").is_hidden()
    assert page.locator("#review-panel").is_hidden()
    assert page.locator("#create-start").is_disabled()
