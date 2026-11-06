import json
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from bigville.management.drafts import resolve_draft
from bigville.management.http import API_PREFIX, create_server
from bigville.reporting import game_report


@pytest.fixture
def report_scenario(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    (root / "report_fixture.json").write_text(json.dumps({
        "id": "report_fixture", "name": "Report Fixture",
        "map": {"grid": [["wall", "wall", "wall", "wall"],
                         ["wall", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "wall"],
                         ["wall", "wall", "wall", "wall"]],
                "layout": {"w": 4, "h": 4, "homes": [[1, 1]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [1, 1]}],
    }))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    return root


def create_record(server, *, name="Report fixture"):
    draft = {"scenario_id": "report_fixture", "name": name, "seed": 23,
             "autonomous": True, "default_backend": "simple", "ticks_per_period": "world", "turn_limit": 5}
    resolved = resolve_draft(draft)
    record, _ = server.run_registry.create_run({"draft": draft, "idempotency_key": name,
        "expected_config_hash": resolved["configuration_hash"],
        "expected_capability_revision": resolved["capability_revision"]})
    server.run_registry.command(record["id"], "step")
    return record


@pytest.fixture
def report_server(tmp_path, report_scenario):
    server = create_server(port=0, data_dir=tmp_path / "reports-data")
    record = create_record(server)
    game = server.run_registry._runtime_for(record["id"]).game
    for i in range(3):
        game.world.create_event("harvest" if i != 1 else "festival",
                                subject="Ada", detail=f"event-{i}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}{API_PREFIX}/runs/{record['id']}"
    try:
        yield server, record, game, base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_report_matches_engine_and_reads_do_not_advance_or_record(report_server):
    server, record, game, base = report_server
    world = game.world
    before_turn = world._turn
    before_events = len(world._events)
    before_nodes = len(world.eng.nodes())
    before_history = list(world._report_history)
    expected = game_report(game)
    actual = json.load(urlopen(base + "/report"))
    events = json.load(urlopen(base + "/events?limit=2"))
    assert actual["source"] == "live_snapshot"
    assert actual["run"]["turn"] == before_turn == 1
    assert actual["report"] == expected
    assert events["source"] == "recorded_history"
    assert events["pagination"] == {"offset": 0, "limit": 2, "total": 3, "next_offset": 2}
    assert len(events["events"]) == 2
    assert world._turn == before_turn
    assert len(world._events) == before_events
    assert len(world.eng.nodes()) == before_nodes
    assert world._report_history == before_history


def test_event_filters_pagination_trace_honesty_and_agent_separation(report_server):
    server, record, game, base = report_server
    harvest = json.load(urlopen(base + "/events?kind=harvest&actor=Ada&limit=1"))
    assert harvest["pagination"]["total"] == 2
    assert harvest["pagination"]["next_offset"] == 1
    assert harvest["events"][0]["kind"] == "harvest"
    second = json.load(urlopen(base + "/events?kind=harvest&actor=Ada&offset=1&limit=1"))
    assert second["events"][0]["id"] != harvest["events"][0]["id"]
    assert json.load(urlopen(base + "/report"))["report"].get("trace") is None
    # Referee reports are a separate endpoint; agent output stays exactly the engine's limited view.
    limited = server.run_registry.get_run_view(record["id"], perspective="agent", actor="Ada")
    assert "report" not in limited and "events" not in limited and "snapshot" not in limited


@pytest.mark.parametrize("query", ["offset=-1", "offset=1.5", "limit=0", "limit=201", "limit=true"])
def test_invalid_event_pagination_is_json_error(report_server, query):
    _, _, _, base = report_server
    with pytest.raises(HTTPError) as caught:
        urlopen(base + "/events?" + query)
    assert caught.value.code == 400
    assert json.load(caught.value)["error"]["code"] == "invalid_run_request"


def test_report_and_event_reads_are_unavailable_before_world_exists(tmp_path, report_scenario):
    server = create_server(port=0, data_dir=tmp_path / "empty-run")
    draft = {"scenario_id": "report_fixture", "name": "Not started", "seed": 2,
             "autonomous": True, "default_backend": "simple", "ticks_per_period": "world", "turn_limit": 1}
    resolved = resolve_draft(draft)
    record, _ = server.run_registry.create_run({"draft": draft, "idempotency_key": "not-started",
        "expected_config_hash": resolved["configuration_hash"],
        "expected_capability_revision": resolved["capability_revision"]})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}{API_PREFIX}/runs/{record['id']}"
    try:
        for resource in ("/report", "/events"):
            with pytest.raises(HTTPError) as caught:
                urlopen(base + resource)
            assert caught.value.code == 409
            assert json.load(caught.value)["error"]["code"] == "snapshot_unavailable"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
