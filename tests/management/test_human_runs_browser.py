import json
import threading
import time

import pytest

from bigville.management.http import create_server

playwright = pytest.importorskip("playwright.sync_api")


def test_human_run_selects_player_uses_agent_view_and_submits_legal_action(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    scenario = {
        "id": "human_browser", "name": "Human Browser",
        "map": {"grid": [["wall"] * 6] + [["wall"] + ["floor"] * 4 + ["wall"] for _ in range(4)] + [["wall"] * 6],
                "layout": {"w": 6, "h": 6, "homes": [[2, 2], [3, 2]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [2, 2]},
                   {"name": "Bob", "role": "hand", "backend": "simple", "home_cell": [3, 2]}],
    }
    (root / "human_browser.json").write_text(json.dumps(scenario))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    server = create_server(port=0, data_dir=tmp_path / "management-data")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    prompts = []
    referee_requests = []
    try:
        with playwright.sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:
                pytest.skip(f"Playwright Chromium is unavailable: {exc}")
            page = browser.new_page()
            page.on("response", lambda response: prompts.append(response.json())
                    if response.url.endswith("/player-prompt") and response.ok else None)
            page.on("request", lambda request: referee_requests.append(request.url)
                    if "/views/referee" in request.url else None)
            page.goto(base, wait_until="domcontentloaded")
            page.get_by_role("button", name="New run").click()
            page.get_by_label("Scenario", exact=True).select_option("human_browser")
            page.get_by_label("Run mode", exact=True).select_option("human")
            page.get_by_role("button", name="Load players from preview").click()
            page.get_by_label("Choose a resident", exact=True).select_option("Ada")
            page.get_by_label("Run name", exact=True).fill("Human Browser Run")
            page.get_by_role("button", name="Validate & preview").click()
            page.locator("#review-panel").wait_for(state="visible", timeout=15000)
            assert "Human-controlled · Ada" in page.locator("#review-summary").inner_text()
            page.get_by_role("button", name="Create & start run").click()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                runs = server.run_registry.list_runs()
                if runs and runs[0]["status"] == "waiting":
                    break
                time.sleep(0.1)
            assert runs and runs[0]["status"] == "waiting"
            run = runs[0]
            game = server.run_registry._runtime[run["id"]].game
            game.world.eng.set_attr(game.world._bodies["Ada"], "stamina_reserve", 0.1)
            page.get_by_role("button", name="Open run").click()
            page.locator("#human-turn-panel").wait_for(state="visible", timeout=15000)
            page.get_by_role("button", name="rest", exact=True).click()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                current = server.run_registry.get_run(run["id"])
                if current["turn"] >= 1 and current["status"] == "waiting":
                    break
                time.sleep(0.1)
            assert current["status"] == "waiting" and current["turn"] == 1
            assert prompts and prompts[0]["view"]["mode"] == "agent"
            assert "referee" not in prompts[0]["view"] and "snapshot" not in prompts[0]
            assert not referee_requests, "human player view must not request a referee snapshot by default"
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
