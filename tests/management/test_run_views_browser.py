import json
import threading

import pytest

from bigville.management.drafts import resolve_draft
from bigville.management.http import create_server

playwright = pytest.importorskip("playwright.sync_api")


def test_switch_to_agent_ignores_delayed_referee_response(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "browser_fixture.json").write_text(json.dumps({
        "id": "browser_fixture", "name": "Browser Test World",
        "map": {"grid": [["wall", "wall", "wall", "wall", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "wall", "wall", "wall", "wall"]],
                "layout": {"w": 5, "h": 5, "homes": [[2, 2]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [2, 2]}],
        "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
        "physical_subsystems": {"metabolism": True, "ecology": False},
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    server = create_server(port=0, data_dir=tmp_path / "data")
    draft = {"scenario_id": "browser_fixture", "name": "Race run", "seed": 41,
             "autonomous": True, "default_backend": "simple", "ticks_per_period": "world", "turn_limit": 2}
    resolved = resolve_draft(draft)
    record, _ = server.run_registry.create_run({"draft": draft, "idempotency_key": "race-test",
        "expected_config_hash": resolved["configuration_hash"],
        "expected_capability_revision": resolved["capability_revision"]})
    server.run_registry.command(record["id"], "step")
    entered, release = threading.Event(), threading.Event()
    original = server.run_registry.get_run_view

    def delayed(run_id, *, perspective, actor=None):
        result = original(run_id, perspective=perspective, actor=actor)
        if perspective == "referee":
            result["snapshot"]["private_sentinel"] = "STALE_REFEREE_SECRET"
            entered.set()
            release.wait(5)
        return result

    server.run_registry.get_run_view = delayed
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
            managed_view_requests = []
            page.on("request", lambda request: managed_view_requests.append(request.url)
                    if "/views/" in request.url else None)
            page.goto(base, wait_until="domcontentloaded")
            page.get_by_role("button", name="Runs").click()
            page.get_by_role("button", name="Open run").click()
            assert entered.wait(5), "referee request did not reach server"
            assert page.get_by_role("button", name="Start").is_visible()
            assert page.get_by_role("button", name="Step").is_visible()
            assert page.get_by_role("button", name="Stop").is_visible()
            page.get_by_label("Perspective", exact=True).select_option("agent")
            page.get_by_text("Ada · resident perspective", exact=False).wait_for(timeout=5000)
            assert page.locator("#referee-renderer").get_attribute("src") is None
            assert page.locator("#resident-rows").inner_text() == ""
            release.set()
            page.wait_for_timeout(250)
            assert "STALE_REFEREE_SECRET" not in page.locator("body").inner_text()
            assert page.locator("#agent-view").is_visible()
            assert page.locator("#referee-view").is_hidden()
            switch_index = len(managed_view_requests)
            page.wait_for_timeout(1800)  # include at least one active-run poll
            assert not any("/views/referee" in url for url in managed_view_requests[switch_index:])
            assert any("/views/agent" in url for url in managed_view_requests[switch_index:])
            browser.close()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_referee_view_loads_existing_renderer_canvas(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "renderer_fixture.json").write_text(json.dumps({
        "id": "renderer_fixture", "name": "Renderer Fixture",
        "map": {"grid": [["wall", "wall", "wall", "wall"],
                         ["wall", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "wall"],
                         ["wall", "wall", "wall", "wall"]],
                "layout": {"w": 4, "h": 4, "homes": [[1, 1]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [1, 1]}],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    server = create_server(port=0, data_dir=tmp_path / "renderer-data")
    draft = {"scenario_id": "renderer_fixture", "name": "Renderer run", "seed": 9,
             "autonomous": True, "default_backend": "simple", "ticks_per_period": "world", "turn_limit": None}
    resolved = resolve_draft(draft)
    record, _ = server.run_registry.create_run({"draft": draft, "idempotency_key": "renderer-test",
        "expected_config_hash": resolved["configuration_hash"],
        "expected_capability_revision": resolved["capability_revision"]})
    server.run_registry.command(record["id"], "step")
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
            page.get_by_role("button", name="Runs").click()
            page.get_by_role("button", name="Open run").click()
            frame = page.frame_locator("#referee-renderer")
            frame.locator("canvas").wait_for(state="visible", timeout=15000)
            assert page.locator("#referee-renderer").is_visible()
            assert page.locator("#resident-rows").get_by_role("button", name="Ada").is_visible()
            page.get_by_role("button", name="Start").click()
            page.get_by_role("button", name="Pause").wait_for(state="visible", timeout=10000)
            page.get_by_role("button", name="Pause").click()
            page.get_by_role("button", name="Resume").wait_for(state="visible", timeout=10000)
            turn_before_step = page.locator("#run-view-meta").inner_text()
            page.get_by_role("button", name="Step").click()
            page.wait_for_function("text => document.querySelector('#run-view-meta').textContent !== text",
                                   arg=turn_before_step, timeout=10000)
            page.get_by_role("button", name="Resume").click()
            page.get_by_role("button", name="Pause").wait_for(state="visible", timeout=10000)
            page.get_by_role("button", name="Stop").click()
            page.get_by_text("stopped · turn", exact=False).wait_for(timeout=10000)
            assert page.get_by_role("button", name="Start").count() == 0
            assert page.get_by_role("button", name="Pause").count() == 0
            assert page.get_by_role("button", name="Resume").count() == 0
            original_view = server.run_registry.get_run_view

            def mapless_view(run_id, *, perspective, actor=None):
                result = original_view(run_id, perspective=perspective, actor=actor)
                if perspective == "referee":
                    result["snapshot"]["world"]["map"] = {"width": 0, "height": 0, "grid": []}
                return result

            server.run_registry.get_run_view = mapless_view
            page.get_by_label("Perspective", exact=True).select_option("agent")
            page.locator("#agent-view-status").wait_for(state="visible")
            page.get_by_label("Perspective", exact=True).select_option("referee")
            page.locator("#mapless-fallback").wait_for(state="visible")
            assert page.locator("#referee-renderer").get_attribute("src") is None
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
