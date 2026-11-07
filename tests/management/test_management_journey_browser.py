import json
import threading

import pytest
from playwright.sync_api import sync_playwright

from bigville.management.http import create_server
import bigville.scenarios as scenarios


def test_browser_configure_preview_run_pause_report_checkpoint_fork_template_compare(tmp_path, monkeypatch):
    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "journey_fixture.json").write_text(json.dumps({
        "id": "journey_fixture", "name": "Journey fixture",
        "map": {"grid": [["wall", "wall", "wall", "wall", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "wall", "wall", "wall", "wall"]],
                "layout": {"w": 5, "h": 5, "homes": [[2, 2]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [2, 2]}],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    server = create_server(port=0, data_dir=tmp_path / "journey-data")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:
                pytest.skip(f"Playwright Chromium is unavailable: {exc}")
            page = browser.new_page(accept_downloads=True, viewport={"width": 1100, "height": 900})
            page.set_default_timeout(10000)
            page.goto(base, wait_until="domcontentloaded")
            page.get_by_role("button", name="New run").click()
            page.locator("#scenario-id").select_option("journey_fixture")
            page.locator("#run-name").fill("M12 journey")
            page.locator("#world-seed").fill("244")
            page.locator("#turn-limit").fill("10000")
            page.get_by_role("button", name="Validate & preview").click()
            page.locator("#config-hash").wait_for()
            assert page.locator("#config-hash").inner_text()
            page.locator("#template-name").fill("Journey template")
            page.get_by_role("button", name="Save this version").click()
            page.wait_for_function("document.querySelector('#template-save-status').textContent.includes('Saved Journey template')")
            page.get_by_role("button", name="Create & start run").click()
            page.get_by_role("button", name="Open run").click()
            pause = page.get_by_role("button", name="Pause")
            pause.wait_for(state="visible")
            pause.click()
            page.wait_for_function("document.querySelector('#run-view-status').textContent.includes('paused')")
            page.get_by_role("button", name="Reports & events").click()
            page.locator("#report-json").wait_for()
            page.get_by_role("button", name="Record report snapshot").click()
            page.get_by_text("Recorded report_", exact=False).wait_for()
            page.locator("#back-from-reports").click()
            page.get_by_role("button", name="Create checkpoint").click()
            page.locator("#checkpoint-list li").wait_for()
            parent_id = next(run["id"] for run in server.run_registry.list_runs() if run["name"] == "M12 journey")
            page.locator("#checkpoint-list li").get_by_role("button", name="Fork").click()
            page.locator("#run-view-heading").get_by_text("M12 journey · fork", exact=True).wait_for()
            child_id = next(run["id"] for run in server.run_registry.list_runs() if run.get("forked_from", {}).get("run_id") == parent_id)
            # A fork is a real saved world; capture its own report before comparing.
            page.get_by_role("button", name="Reports & events").click()
            page.get_by_role("button", name="Record report snapshot").click()
            page.get_by_text("Recorded report_", exact=False).wait_for()
            page.locator("#back-from-reports").click()
            page.locator("#back-from-run-view").click()
            page.locator("#compare-runs").select_option([parent_id])
            page.get_by_role("button", name="Compare latest recorded reports").click()
            page.get_by_text("Choose between 2 and 10", exact=False).wait_for()
            page.locator("#compare-runs").select_option([parent_id, child_id])
            page.get_by_role("button", name="Compare latest recorded reports").click()
            page.locator(".comparison-table").wait_for()
            assert "population.alive" in page.locator(".comparison-table").inner_text()
            assert server.template_registry.list_templates()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
