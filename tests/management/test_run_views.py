import json
import threading
from urllib.request import urlopen

from bigville.management.drafts import resolve_draft
from bigville.management.http import API_PREFIX, create_server
from bigville.management.runs import RunRegistry, RunViewUnavailable


def test_agent_view_never_serializes_referee_snapshot(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "views_fixture.json").write_text(json.dumps({
        "id": "views_fixture", "name": "View Fixture",
        "map": {"grid": [["wall", "wall", "wall"], ["wall", "floor", "wall"], ["wall", "wall", "wall"]],
                "layout": {"w": 3, "h": 3, "homes": [[1, 1]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [1, 1]}],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    registry = RunRegistry(tmp_path / "registry")
    draft = {"scenario_id": "views_fixture", "name": "Views", "seed": 1,
             "autonomous": True, "default_backend": "simple", "ticks_per_period": "world", "turn_limit": 2}
    resolved = resolve_draft(draft)
    record, _ = registry.create_run({"draft": draft, "idempotency_key": "views",
        "expected_config_hash": resolved["configuration_hash"],
        "expected_capability_revision": resolved["capability_revision"]})
    try:
        registry.get_run_view(record["id"], perspective="referee")
    except RunViewUnavailable:
        pass
    else:
        raise AssertionError("unstarted run unexpectedly exposed a snapshot")
    registry.command(record["id"], "step")
    runtime = registry._runtime_for(record["id"])
    original_snapshot = runtime.game.snapshot
    calls = []

    def secret_snapshot():
        calls.append("snapshot")
        result = original_snapshot()
        result["private_sentinel"] = "referee-only-secret"
        return result

    runtime.game.snapshot = secret_snapshot
    referee = registry.get_run_view(record["id"], perspective="referee")
    assert referee["snapshot"]["private_sentinel"] == "referee-only-secret"
    before = len(calls)
    agent = registry.get_run_view(record["id"], perspective="agent", actor="Ada")
    assert len(calls) == before
    assert agent["perspective"] == "agent"
    assert "snapshot" not in agent and "world" not in agent and "characters" not in agent
    assert "referee-only-secret" not in json.dumps(agent)


def test_http_views_are_run_scoped_and_isolated(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "views_fixture.json").write_text(json.dumps({
        "id": "views_fixture", "name": "View Fixture",
        "map": {"grid": [["wall", "wall", "wall"], ["wall", "floor", "wall"], ["wall", "wall", "wall"]],
                "layout": {"w": 3, "h": 3, "homes": [[1, 1]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [1, 1]}],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    server = create_server(port=0, data_dir=tmp_path / "http-data")
    records = []
    for name in ("First", "Second"):
        draft = {"scenario_id": "views_fixture", "name": name, "seed": 1,
                 "autonomous": True, "default_backend": "simple", "ticks_per_period": "world", "turn_limit": 2}
        resolved = resolve_draft(draft)
        record, _ = server.run_registry.create_run({"draft": draft, "idempotency_key": name,
            "expected_config_hash": resolved["configuration_hash"],
            "expected_capability_revision": resolved["capability_revision"]})
        records.append(record)
    server.run_registry.command(records[0]["id"], "step")
    server.run_registry.command(records[1]["id"], "step")
    first_runtime = server.run_registry._runtime_for(records[0]["id"])
    first_runtime.game.snapshot = lambda: {"world": {"marker": "first-only"}, "private": "secret"}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}{API_PREFIX}/runs"
    try:
        first = records[0]["id"]
        second = records[1]["id"]
        referee = json.load(urlopen(f"{base}/{first}/views/referee"))
        agent = json.load(urlopen(f"{base}/{first}/views/agent?actor=Ada"))
        other = json.load(urlopen(f"{base}/{second}/views/referee"))
        assert referee["snapshot"]["world"]["marker"] == "first-only"
        assert "first-only" not in json.dumps(agent)
        assert "first-only" not in json.dumps(other)
        assert agent["perspective"] == "agent"
        assert agent["view"]["actor"] == "Ada"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
