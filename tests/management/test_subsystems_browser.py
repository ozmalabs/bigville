import threading
import json
import time

import pytest

from bigville.management.http import create_server

playwright = pytest.importorskip("playwright.sync_api")


def test_subsystem_controls_preview_and_launched_run_match(tmp_path):
    server = create_server(port=0, data_dir=tmp_path / "management-data")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    previews = []
    try:
        with playwright.sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:
                pytest.skip(f"Playwright Chromium is unavailable: {exc}")
            page = browser.new_page()
            page.on("response", lambda response: previews.append(response.json())
                    if response.url.endswith("/run-drafts/preview") and response.ok else None)
            page.goto(base, wait_until="domcontentloaded")
            page.get_by_role("button", name="New run").click()
            page.get_by_label("Scenario", exact=True).select_option("management_cast_demo")
            page.get_by_label("training", exact=True).select_option("false")
            page.get_by_role("button", name="Validate & preview").click()
            page.locator("#review-panel").wait_for(state="visible", timeout=15000)
            assert previews
            preview = previews[-1]
            config = preview["canonical_config"]
            assert config["physical_subsystems"]["training"] is False
            assert config["physical_subsystem_sources"]["training"] == "user_override"
            assert "training: off · user override" in page.locator("#review-subsystems").inner_text()
            page.get_by_role("button", name="Create & start run").click()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                records = server.run_registry.list_runs()
                if records and server.run_registry._runtime[records[0]["id"]].game is not None:
                    break
                time.sleep(0.1)
            assert records, page.locator("#launch-status").inner_text()
            record = server.run_registry.list_runs()[0]
            game = server.run_registry._runtime[record["id"]].game
            assert game is not None, (record["status"], record["error"], record["config"])
            assert game.world.physical_subsystems == config["physical_subsystems"]
            assert record["config_hash"] == preview["configuration_hash"]
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_scenario_switch_resets_overrides_and_refreshes_inherited_values(tmp_path, monkeypatch):
    from bigville import scenarios

    scenario_root = tmp_path / "scenarios"
    scenario_root.mkdir()
    common = {
        "map": {"grid": [["wall"] * 4, ["wall", "floor", "floor", "wall"],
                ["wall", "floor", "floor", "wall"], ["wall"] * 4],
                "layout": {"w": 4, "h": 4, "homes": [[1, 1]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [1, 1]}],
    }
    for scenario_id, switches in (("switches_a", {"training": True, "metabolism": False}),
                                  ("switches_b", {"training": False, "metabolism": True})):
        value = {**common, "id": scenario_id, "name": scenario_id, "physical_subsystems": switches}
        (scenario_root / f"{scenario_id}.json").write_text(json.dumps(value))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", scenario_root)
    server = create_server(port=0, data_dir=tmp_path / "management-data")
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
            page.get_by_role("button", name="New run").click()
            page.get_by_label("Scenario", exact=True).select_option("switches_a")
            training = page.get_by_label("training", exact=True)
            assert training.input_value() == ""
            assert "on (scenario)" in training.locator("option").nth(0).text_content()
            training.select_option("false")
            assert training.input_value() == "false"
            page.get_by_label("Scenario", exact=True).select_option("switches_b")
            training = page.get_by_label("training", exact=True)
            metabolism = page.get_by_label("metabolism", exact=True)
            assert training.input_value() == ""
            assert "off (scenario)" in training.locator("option").nth(0).text_content()
            assert "on (scenario)" in metabolism.locator("option").nth(0).text_content()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
