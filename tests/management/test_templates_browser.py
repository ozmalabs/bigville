import json
import threading
from urllib.request import urlopen

import pytest

from bigville.management.http import API_PREFIX, create_server

playwright = pytest.importorskip("playwright.sync_api")


def test_template_save_inspect_dirty_confirmation_load_and_run_provenance(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "template_browser.json").write_text(json.dumps({
        "id": "template_browser", "name": "Template Browser",
        "map": {"grid": [["wall", "wall", "wall", "wall"],
                         ["wall", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "wall"],
                         ["wall", "wall", "wall", "wall"]],
                "layout": {"w": 4, "h": 4, "homes": [[1, 1]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [1, 1]}],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    server = create_server(port=0, data_dir=tmp_path / "browser-data")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    created_runs = []
    try:
        with playwright.sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:
                pytest.skip(f"Playwright Chromium is unavailable: {exc}")
            page = browser.new_page()
            page.on("response", lambda response: created_runs.append(response.json())
                    if response.url.endswith(API_PREFIX + "/runs") and response.request.method == "POST"
                    else None)
            page.goto(base, wait_until="domcontentloaded")
            page.get_by_role("button", name="New run").click()
            page.get_by_label("Run name").fill("Template origin")
            page.get_by_label("Scenario", exact=True).select_option("template_browser")
            page.get_by_label("World seed").fill("33")
            page.get_by_label("Turn limit Optional").fill("2")
            page.get_by_role("button", name="Validate & preview").click()
            page.locator("#review-panel:not([hidden])").wait_for()
            page.get_by_label("Template name").fill("Browser template")
            page.get_by_role("button", name="Save this version").click()
            page.get_by_text("Saved Browser template · version 1.", exact=True).wait_for()
            template_id = page.locator("#template-choice").evaluate("select => select.options[0].value.split('|')[0]")
            page.locator("#back-to-runs").click()
            page.get_by_role("button", name="Inspect").click()
            page.locator("#template-inspection").wait_for(state="visible")
            page.wait_for_function("document.querySelector('#template-inspection').textContent.includes('version')")
            assert '"version": 1' in page.locator("#template-inspection").inner_text()
            page.get_by_role("button", name="New run").click()
            page.get_by_label("Run name").fill("Temporary changed draft")
            page.get_by_label("Scenario", exact=True).select_option("template_browser")
            page.get_by_label("World seed").fill("44")
            page.locator("#back-to-runs").click()
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.get_by_role("button", name="Load into draft").click()
            assert page.get_by_label("World seed").input_value() == "44"
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="Load into draft").click()
            page.wait_for_function("document.querySelector('#world-seed').value === '33'")
            page.locator("#review-panel:not([hidden])").wait_for()
            page.get_by_role("button", name="Create & start run").click()
            page.get_by_role("heading", name="Your simulations").wait_for()
            assert len(created_runs) == 1
            run = created_runs[0]
            saved_run = json.load(urlopen(f"{base}{API_PREFIX}/runs/{run['id']}"))
            assert saved_run["template"]["id"] == template_id
            assert saved_run["template"]["version"] == 1
            assert saved_run["template"]["run_configuration_hash"] == saved_run["config_hash"]

            page.get_by_role("button", name="New run").click()
            page.locator("#back-to-runs").click()
            page.get_by_role("button", name="Load into draft").click()
            page.locator("#review-panel:not([hidden])").wait_for()
            page.get_by_label("World seed").fill("77")
            page.get_by_role("button", name="Validate & preview").click()
            page.locator("#review-panel:not([hidden])").wait_for()
            page.get_by_role("button", name="Save this version").click()
            page.get_by_text("Saved Browser template · version 2.", exact=True).wait_for()
            assert saved_run["template"]["version"] == 1
            assert json.load(urlopen(f"{base}{API_PREFIX}/runs/{run['id']}"))["template"]["version"] == 1
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
