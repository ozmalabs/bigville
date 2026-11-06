import json
import threading
from urllib.request import urlopen

import pytest

from bigville.backends.llm import LLMBackend
from bigville.management.http import API_PREFIX, create_server

playwright = pytest.importorskip("playwright.sync_api")


def test_ui_previews_launches_and_reports_server_profile_assignments_without_secrets(tmp_path, monkeypatch):
    from bigville import scenarios

    scenario_root = tmp_path / "scenarios"
    scenario_root.mkdir()
    (scenario_root / "backend_browser.json").write_text(json.dumps({
        "id": "backend_browser", "name": "Backend Browser",
        "map": {"grid": [["wall", "wall", "wall", "wall", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "floor", "wall"],
                         ["wall", "wall", "wall", "wall", "wall"]],
                "layout": {"w": 5, "h": 4, "homes": [[1, 1], [3, 1]]}},
        "actors": [
            {"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [1, 1]},
            {"name": "Ben", "role": "hand", "home_cell": [3, 1]},
        ],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", scenario_root)
    data_dir = tmp_path / "management-data"
    data_dir.mkdir()
    (data_dir / "backend_profiles.json").write_text(json.dumps({"schema_version": 1, "profiles": [
        {"id": "llm.alpha", "name": "Alpha model", "kind": "llm", "revision": "a1",
         "adapter": "provider.alpha", "secret_ref": "env:ALPHA_SECRET"},
        {"id": "llm.beta", "name": "Beta model", "kind": "llm", "revision": "b1",
         "adapter": "provider.beta", "secret_ref": "env:BETA_SECRET"},
        {"id": "llm.unready", "name": "Unready model", "kind": "llm", "revision": "x1",
         "adapter": "provider.missing", "secret_ref": "env:UNREADY_SECRET"},
    ]}))
    server = create_server(port=0, data_dir=data_dir)
    calls = []

    class Fake:
        def __init__(self, actor):
            self.actor = actor

        def complete(self, prompt):
            calls.append(self.actor)
            raise RuntimeError("offline test provider")

    for adapter_id in ("provider.alpha", "provider.beta"):
        server.profile_registry.adapters.register(
            adapter_id,
            lambda world, character, profile: LLMBackend(
                character, Fake(character.character_id), autopilot=False))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    posted_runs = []
    response_bodies = []
    try:
        with playwright.sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:
                pytest.skip(f"Playwright Chromium is unavailable: {exc}")
            page = browser.new_page()
            page.on("request", lambda request: posted_runs.append(json.loads(request.post_data))
                    if request.url.endswith(API_PREFIX + "/runs") and request.method == "POST"
                    else None)
            page.goto(base, wait_until="domcontentloaded")
            page.get_by_role("button", name="Backends").click()
            page.get_by_role("heading", name="Unready model · llm").wait_for()
            assert "No server-side provider adapter" in page.locator("#backend-list").inner_text()
            page.get_by_role("button", name="Runs").click()
            page.get_by_role("button", name="New run").click()
            page.get_by_label("Run name").fill("Profile assignments")
            page.get_by_label("Scenario", exact=True).select_option("backend_browser")
            page.get_by_label("World seed").fill("63")
            page.get_by_label("Turn limit Optional").fill("1")
            page.get_by_label("Ada").select_option("llm.alpha")
            page.get_by_label("Ben").select_option("llm.beta")
            page.get_by_role("button", name="Validate & preview").click()
            page.locator("#review-panel:not([hidden])").wait_for()
            assert page.get_by_text("Ada · llm (user override)", exact=True).is_visible()
            assert page.get_by_text("Ben · llm (user override)", exact=True).is_visible()
            page.get_by_role("button", name="Create & start run").click()
            page.get_by_role("heading", name="Your simulations").wait_for()
            assert len(posted_runs) == 1
            submitted = posted_runs[0]
            assert submitted["draft"]["actor_backend_profiles"] == {
                "Ada": "llm.alpha", "Ben": "llm.beta"}
            assert "secret_ref" not in json.dumps(submitted)
            # Read the public resources after they have completed instead of
            # consuming response bodies in an asynchronous Playwright event callback.
            response_bodies.extend([
                json.load(urlopen(f"{base}{API_PREFIX}/backend-profiles")),
                json.load(urlopen(f"{base}{API_PREFIX}/runs")),
            ])
            assert "ALPHA_SECRET" not in json.dumps(response_bodies)
            assert "BETA_SECRET" not in json.dumps(response_bodies)
            run_records = json.load(urlopen(f"{base}{API_PREFIX}/runs"))["runs"]
            assert run_records[0]["resolved_actor_profiles"]
            assert set(calls) == {"Ada", "Ben"}
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
