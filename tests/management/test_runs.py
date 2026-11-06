import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from bigville.management.drafts import resolve_draft
from bigville.management.http import API_PREFIX, create_server
from bigville.management.runs import InvalidRunRequest, RunConflict, RunRegistry


@pytest.fixture
def draft_scenario(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    value = {
        "id": "registry_fixture", "name": "Registry Fixture",
        "map": {"grid": [["wall", "wall", "wall"],
                         ["wall", "floor", "wall"],
                         ["wall", "wall", "wall"]],
                 "layout": {"w": 3, "h": 3, "homes": [[1, 1]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple",
                    "home_cell": [1, 1]}],
    }
    path = root / "registry_fixture.json"
    path.write_text(json.dumps(value))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    return value


def make_draft(**changes):
    value = {"scenario_id": "registry_fixture", "name": "Registry test",
             "seed": 42, "autonomous": True, "default_backend": "simple",
             "ticks_per_period": "world", "turn_limit": 3}
    value.update(changes)
    return value


def create_request(draft, key="request-1"):
    resolved = resolve_draft(draft)
    return {
        "draft": draft,
        "idempotency_key": key,
        "expected_config_hash": resolved["configuration_hash"],
        "expected_capability_revision": resolved["capability_revision"],
    }


@pytest.fixture
def registry(tmp_path):
    return RunRegistry(tmp_path / "registry")


def test_create_list_reload_persists_immutable_config_and_assignments(
        draft_scenario, registry, tmp_path):
    request = create_request(make_draft())
    record, created = registry.create_run(request)
    assert created is True
    assert record["status"] == "created"
    assert record["turn"] == 0
    assert record["config_hash"] == request["expected_config_hash"]
    assert record["resolved_actor_backends"] == [
        {"actor": "Ada", "backend": "simple", "source": "scenario_override"}
    ]
    assert registry.list_runs()[0]["id"] == record["id"]

    reloaded = RunRegistry(tmp_path / "registry")
    assert reloaded.get_run(record["id"]) == record
    assert reloaded.list_runs() == [record]


def test_invalid_draft_and_stale_hash_or_capability_revision_are_rejected(
        draft_scenario, registry):
    bad = create_request(make_draft(seed=True))
    with pytest.raises(InvalidRunRequest) as invalid:
        registry.create_run(bad)
    assert "seed" in invalid.value.fields

    stale_hash = create_request(make_draft())
    stale_hash["expected_config_hash"] = "0" * 64
    with pytest.raises(RunConflict, match="configuration hash"):
        registry.create_run(stale_hash)

    stale_revision = create_request(make_draft())
    stale_revision["expected_capability_revision"] = "stale"
    with pytest.raises(RunConflict, match="Capability revision"):
        registry.create_run(stale_revision)
    assert registry.list_runs() == []


def test_idempotency_returns_original_and_reuse_with_different_request_conflicts(
        draft_scenario, registry):
    request = create_request(make_draft(), key="same-key")
    first, created = registry.create_run(request)
    again, created_again = registry.create_run(request)
    assert created is True and created_again is False
    assert first["id"] == again["id"]

    changed = create_request(make_draft(seed=43), key="same-key")
    with pytest.raises(RunConflict, match="different configuration"):
        registry.create_run(changed)
    assert len(registry.list_runs()) == 1


def test_api_create_list_get_and_not_found_are_json_and_durable(
        draft_scenario, tmp_path):
    server = create_server(port=0, data_dir=tmp_path / "api-data")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    try:
        request = Request(base + API_PREFIX + "/runs",
                          data=json.dumps(create_request(make_draft(), "http-key")).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request) as response:
            assert response.status == 201
            record = json.load(response)
        with urlopen(base + API_PREFIX + "/runs") as response:
            assert json.load(response)["runs"] == [record]
        with urlopen(base + API_PREFIX + "/runs/" + record["id"]) as response:
            assert json.load(response) == record

        with pytest.raises(HTTPError) as caught:
            urlopen(base + API_PREFIX + "/runs/missing")
        assert caught.value.code == 404
        assert json.load(caught.value)["error"]["code"] == "run_not_found"

        command = Request(base + API_PREFIX + "/runs/" + record["id"] + "/commands",
                          data=json.dumps({"command": "step"}).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(command) as response:
            stepped = json.load(response)
        assert stepped["status"] == "created"
        assert stepped["turn"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_malformed_registry_is_rejected_without_overwrite(tmp_path):
    directory = tmp_path / "broken"
    directory.mkdir()
    path = directory / "registry.json"
    path.write_text("{bad json")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        RunRegistry(directory)
    assert path.read_text() == "{bad json"


def test_api_run_creation_preview_failure_returns_shared_json_error(
        draft_scenario, tmp_path, monkeypatch):
    import bigville.management.runs as runs

    server = create_server(port=0, data_dir=tmp_path / "preview-failure")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"
    monkeypatch.setattr(runs, "preview_draft", lambda draft: (_ for _ in ()).throw(RuntimeError("engine issue")))
    try:
        request = Request(base + API_PREFIX + "/runs",
                          data=json.dumps(create_request(make_draft(), "preview-failure")).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(HTTPError) as caught:
            urlopen(request)
        assert caught.value.code == 422
        body = json.load(caught.value)
        assert body["error"]["code"] == "invalid_run_request"
        assert body["error"]["fields"]["scenario_id"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
