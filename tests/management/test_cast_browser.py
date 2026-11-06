import pytest

from bigville.management.http import create_server

playwright = pytest.importorskip("playwright.sync_api")


def test_cast_groups_preview_and_launch_match_actual_world(tmp_path):
    server = create_server(port=0, data_dir=tmp_path / "management-data")
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
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
            page.get_by_label("Generate residents for this scenario").check()
            page.locator("#cast-generation-groups input[data-cast-field=id]").fill("gardeners")
            page.locator("#cast-generation-groups input[data-cast-field=count]").fill("3")
            page.locator("#cast-generation-groups select[data-cast-field=role]").select_option("farmer")
            page.locator("#cast-generation-groups input[data-cast-field='skill-min']").fill("0.25")
            page.locator("#cast-generation-groups input[data-cast-field='skill-max']").fill("0.75")
            page.get_by_role("button", name="Validate & preview").click()
            page.locator("#review-panel").wait_for(state="visible", timeout=15000)
            page.get_by_text("gardeners · farmer · 3 · simple.default").wait_for()
            page.locator("#review-cast details summary").click()
            page.get_by_text("gardeners-001", exact=True).wait_for()
            assert len(previews) >= 1
            preview = previews[-1]
            generated_preview = {actor["name"]: actor for actor in preview["cast"]["actors"]
                                 if actor["name"].startswith("gardeners-")}
            assert preview["cast"]["groups"][0]["actors"] == sorted(generated_preview)
            assert set(generated_preview) == {"gardeners-001", "gardeners-002", "gardeners-003"}
            page.get_by_role("button", name="Create & start run").click()
            page.get_by_role("heading", name="Your simulations").wait_for(timeout=15000)
            runs = server.run_registry.list_runs()
            assert len(runs) == 1
            record = runs[0]
            game = server.run_registry._runtime[record["id"]].game
            assert game is not None
            generated_actual = {name: game.world.eng.node(game.world._actors[name])["attrs"]
                                for name in game.characters if name.startswith("gardeners-")}
            assert set(generated_actual) == set(generated_preview)
            for name, actor in generated_preview.items():
                assert generated_actual[name]["role"] == actor["role"] == "farmer"
                assert list(game.world.actor_position(name)) == actor["position"]
                assert generated_actual[name]["age"] == record["config"]["generated_cast"][
                    int(name.rsplit("-", 1)[1]) - 1]["age"]
            assert record["config"]["cast_generation_version"] == 1
            assert record["config"]["cast_generation_hash"]
            assert record["config_hash"] == preview["configuration_hash"]
            assert server.run_registry.get_run(record["id"])["turn"] <= 2
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
