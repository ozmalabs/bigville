import json
import threading

import pytest

from bigville.management.drafts import resolve_draft
from bigville.management.http import create_server

playwright = pytest.importorskip("playwright.sync_api")


def test_checkpoint_and_fork_controls_restore_distinct_run(tmp_path, monkeypatch):
    from bigville import scenarios
    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "checkpoint_browser.json").write_text(json.dumps({
        "id": "checkpoint_browser", "name": "Checkpoint Browser Fixture",
        "map": {"grid": [["wall", "wall", "wall", "wall", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "wall", "wall", "wall", "wall"]],
                "layout": {"w": 5, "h": 5, "homes": [[2, 2]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [2, 2]}],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    server = create_server(port=0, data_dir=tmp_path / "management-data")
    draft = {"scenario_id": "checkpoint_browser", "name": "Browser checkpoint run",
             "seed": 71, "autonomous": True, "default_backend": "simple",
             "ticks_per_period": "world", "turn_limit": 5}
    resolved = resolve_draft(draft)
    parent, _ = server.run_registry.create_run({"draft": draft, "idempotency_key": "browser-checkpoint",
        "expected_config_hash": resolved["configuration_hash"],
        "expected_capability_revision": resolved["capability_revision"]})
    server.run_registry.command(parent["id"], "step")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    try:
        with playwright.sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:
                pytest.skip(f"Playwright Chromium is unavailable: {exc}")
            page = browser.new_page()
            page.goto(base, wait_until="domcontentloaded")
            page.get_by_role("button", name="Open run").click()
            create_button = page.get_by_role("button", name="Create checkpoint")
            create_button.wait_for(state="visible")
            create_button.click()
            checkpoint_row = page.locator("#checkpoint-list li")
            checkpoint_row.wait_for(timeout=10000)
            assert "Turn 1" in checkpoint_row.inner_text()
            checkpoint_row.get_by_role("button", name="Fork").click()
            page.locator("#run-view-heading").get_by_text("Browser checkpoint run · fork").wait_for(timeout=10000)
            assert "Paused · Turn 1" in page.locator("#run-view-status").inner_text()
            assert page.get_by_role("button", name="Resume").is_visible()
            child = next(run for run in server.run_registry.list_runs() if run["id"] != parent["id"])
            assert child["forked_from"]["run_id"] == parent["id"]
            page.get_by_role("button", name="Step").click()
            page.wait_for_function("text => document.querySelector('#run-view-meta').textContent.includes('turn 2')",
                                   arg="turn 2", timeout=10000)
            assert server.run_registry.get_run(parent["id"])["turn"] == 1
            assert server.run_registry.get_run(child["id"])["turn"] == 2
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
