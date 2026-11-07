import json
import threading

import pytest
from playwright.sync_api import sync_playwright

from bigville.management.drafts import resolve_draft
from bigville.management.http import API_PREFIX, create_server
import bigville.scenarios as scenarios


def test_browser_records_exports_and_compares_real_run_reports(tmp_path, monkeypatch):
    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "compare_fixture.json").write_text(json.dumps({
        "id": "compare_fixture", "name": "Compare fixture",
        "terrain": [["wall", "wall", "wall", "wall"], ["wall", "grass", "grass", "wall"],
                    ["wall", "grass", "grass", "wall"], ["wall", "wall", "wall", "wall"]],
        "layout": {"w": 4, "h": 4, "homes": [[1, 1], [2, 1]]},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [1, 1]},
                   {"name": "Bo", "role": "hand", "backend": "simple", "home_cell": [2, 1]}],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    server = create_server(port=0, data_dir=tmp_path / "compare-data")
    ids = []
    for index in range(2):
        draft = {"scenario_id": "compare_fixture", "name": f"Compare {index}", "seed": 100 + index,
                 "autonomous": True, "default_backend": "simple", "ticks_per_period": "world", "turn_limit": 2}
        resolved = resolve_draft(draft)
        record, _ = server.run_registry.create_run({"draft": draft, "idempotency_key": f"compare-{index}",
            "expected_config_hash": resolved["configuration_hash"],
            "expected_capability_revision": resolved["capability_revision"]})
        server.run_registry.command(record["id"], "step")
        ids.append(record["id"])
        server.run_registry.capture_run_report(record["id"])
    assert server.run_registry.compare_recorded_reports(ids)["compatible"]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:
                pytest.skip(f"Playwright Chromium is unavailable: {exc}")
            page = browser.new_page(accept_downloads=True, viewport={"width": 375, "height": 812})
            page.set_default_timeout(5000)
            page.goto(base, wait_until="domcontentloaded")
            page.get_by_role("button", name="Runs").click()
            page.get_by_role("button", name="Open run").first.click()
            page.get_by_role("button", name="Reports & events").click()
            page.get_by_role("button", name="Record report snapshot").click()
            page.get_by_text("Recorded report_", exact=False).wait_for()
            with page.expect_download() as download:
                page.get_by_role("button", name="Download reproducibility metadata").click()
            metadata = json.loads(open(download.value.path(), encoding="utf-8").read())
            assert metadata["schema"] == "bigville/reproducibility/1"
            page.locator("#back-from-reports").click()
            page.locator("#back-from-run-view").click()
            page.locator("#compare-runs").select_option(ids)
            page.get_by_role("button", name="Compare latest recorded reports").click()
            page.locator("#compare-status").wait_for()
            page.get_by_text("Compatible recorded report schema", exact=False).wait_for()
            assert page.locator(".comparison-table").is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
