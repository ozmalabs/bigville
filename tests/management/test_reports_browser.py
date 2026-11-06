import json
import threading
import time

import pytest

from bigville.management.drafts import resolve_draft
from bigville.management.http import create_server

playwright = pytest.importorskip("playwright.sync_api")


def test_reports_events_pagination_and_json_download_without_advancing(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "reports_browser.json").write_text(json.dumps({
        "id": "reports_browser", "name": "Reports Browser",
        "map": {"grid": [["wall", "wall", "wall", "wall"],
                         ["wall", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "wall"],
                         ["wall", "wall", "wall", "wall"]],
                "layout": {"w": 4, "h": 4, "homes": [[1, 1]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [1, 1]}],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    server = create_server(port=0, data_dir=tmp_path / "browser-data")
    draft = {"scenario_id": "reports_browser", "name": "Browser report", "seed": 31,
             "autonomous": True, "default_backend": "simple", "ticks_per_period": "world", "turn_limit": 3}
    resolved = resolve_draft(draft)
    record, _ = server.run_registry.create_run({"draft": draft, "idempotency_key": "reports-browser",
        "expected_config_hash": resolved["configuration_hash"],
        "expected_capability_revision": resolved["capability_revision"]})
    server.run_registry.command(record["id"], "step")
    game = server.run_registry._runtime_for(record["id"]).game
    for index in range(53):
        game.world.create_event("festival" if index % 3 == 0 else "harvest",
                                subject="Ada", detail=f"browser-event-{index}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    try:
        with playwright.sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:
                pytest.skip(f"Playwright Chromium is unavailable: {exc}")
            page = browser.new_page(accept_downloads=True)
            requests_seen = []
            page.on("request", lambda request: requests_seen.append(request.url))
            page.goto(base, wait_until="domcontentloaded")
            page.get_by_role("button", name="Runs").click()
            page.get_by_role("button", name="Open run").click()
            page.get_by_role("button", name="Reports & events").click()
            page.locator("#report-json").wait_for()
            assert "Live state · captured" in page.locator("#report-provenance").inner_text()
            assert "complete_census" in page.locator("#report-json").inner_text()
            assert "Recorded world history · as of turn 1" in page.locator("#events-provenance").inner_text()
            assert page.locator("#events-page-status").inner_text() == "1–50 of 53"
            assert "Unavailable: this engine does not retain" in page.get_by_role("heading", name="Decision trace").locator("..").inner_text()
            turn_before = page.locator("#reports-run-status").inner_text()
            page.get_by_role("button", name="Next").click()
            page.wait_for_function("document.querySelector('#events-page-status').textContent === '51–53 of 53'")
            page.get_by_label("Kind").fill("festival")
            page.get_by_role("button", name="Apply filters").click()
            page.wait_for_function("document.querySelector('#events-page-status').textContent === '1–18 of 18'")
            with page.expect_download() as report_download:
                page.get_by_role("button", name="Download report JSON").click()
            report_file = report_download.value.path()
            assert json.loads(open(report_file, encoding="utf-8").read())["source"] == "live_snapshot"
            with page.expect_download() as event_download:
                page.get_by_role("button", name="Download events JSON").click()
            event_file = event_download.value.path()
            exported = json.loads(open(event_file, encoding="utf-8").read())
            assert exported["events"][0]["kind"] == "festival"
            assert page.locator("#reports-run-status").inner_text() == turn_before
            page.locator("#back-from-reports").click()
            page.get_by_label("Perspective", exact=True).select_option("agent")
            page.get_by_text("Ada · resident perspective", exact=False).wait_for()
            assert page.get_by_role("button", name="Reports & events").count() == 0

            # A report still in flight when the user returns and switches perspective
            # must not paint its referee payload into the agent view.
            entered, release = threading.Event(), threading.Event()
            original_report = server.run_registry.get_run_report

            def delayed_report(run_id):
                result = original_report(run_id)
                result["report"]["stale_referee_sentinel"] = "STALE_REPORT_SECRET"
                entered.set()
                release.wait(5)
                return result

            server.run_registry.get_run_report = delayed_report
            page.locator("#perspective-choice").select_option("referee")
            page.get_by_role("button", name="Reports & events").click()
            assert entered.wait(5)
            page.locator("#back-from-reports").click()
            page.locator("#perspective-choice").select_option("agent")
            page.get_by_text("Ada · resident perspective", exact=False).wait_for()
            request_boundary = len(requests_seen)
            release.set()
            page.wait_for_timeout(1700)
            assert "STALE_REPORT_SECRET" not in page.locator("body").inner_text()
            assert page.locator("#agent-view").is_visible()
            assert page.locator("#reports-panel").is_hidden()
            assert not any("/report" in url or "/events?" in url for url in requests_seen[request_boundary:])
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
