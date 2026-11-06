import json
import threading

import pytest

from bigville.management.drafts import resolve_draft
from bigville.management.http import API_PREFIX, create_server
from bigville.management.runs import CheckpointUnavailable, RunNotFound, RunRegistry
from bigville.management.profiles import BackendAdapterRegistry


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    from bigville import scenarios
    root = tmp_path / "scenarios"
    root.mkdir()
    value = {
        "id": "checkpoint_fixture", "name": "Checkpoint Fixture",
        "map": {"grid": [["wall", "wall", "wall", "wall", "wall"],
                          ["wall", "floor", "floor", "floor", "wall"],
                          ["wall", "floor", "floor", "floor", "wall"],
                          ["wall", "floor", "floor", "floor", "wall"],
                          ["wall", "wall", "wall", "wall", "wall"]],
                "layout": {"w": 5, "h": 5, "homes": [[2, 2]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [2, 2]}],
        "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
        "physical_subsystems": {"metabolism": True, "ecology": False},
    }
    (root / "checkpoint_fixture.json").write_text(json.dumps(value))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    return value


def create(registry, turn_limit=10):
    draft = {"scenario_id": "checkpoint_fixture", "name": "Checkpoint run", "seed": 41,
             "autonomous": True, "default_backend": "simple", "ticks_per_period": "world",
             "turn_limit": turn_limit}
    resolved = resolve_draft(draft)
    record, _ = registry.create_run({"draft": draft, "idempotency_key": "checkpoint-test",
        "expected_config_hash": resolved["configuration_hash"],
        "expected_capability_revision": resolved["capability_revision"]})
    return record


@pytest.fixture
def registry(tmp_path, scenario):
    return RunRegistry(tmp_path / "management-data")


def test_real_game_checkpoint_fork_parity_and_independent_progress(registry):
    parent = create(registry)
    registry.command(parent["id"], "step")
    original_game = registry._runtime[parent["id"]].game
    checkpoint = registry.create_checkpoint(parent["id"])
    listed = registry.list_checkpoints(parent["id"])
    assert listed == [checkpoint]
    child = registry.fork_checkpoint(parent["id"], checkpoint["id"])
    assert child["id"] != parent["id"]
    assert child["status"] == "paused"
    assert child["turn"] == checkpoint["turn"] == 1
    assert child["forked_from"] == {"run_id": parent["id"],
        "checkpoint_id": checkpoint["id"], "config_hash": parent["config_hash"], "turn": 1}
    child_game = registry._runtime[child["id"]].game
    assert child_game is not original_game
    assert child_game.snapshot() == original_game.snapshot()

    registry.command(child["id"], "step")
    assert registry.get_run(child["id"])["turn"] == 2
    assert registry.get_run(parent["id"])["turn"] == 1
    assert int(original_game.world._turn) == 1
    registry.command(parent["id"], "step")
    assert registry.get_run(parent["id"])["turn"] == 2
    assert registry.get_run(child["id"])["turn"] == 2
    assert registry._runtime[child["id"]].game is not registry._runtime[parent["id"]].game


def test_checkpoint_rejects_missing_game_and_unsupported_backend(registry):
    parent = create(registry)
    with pytest.raises(CheckpointUnavailable, match="Step or start"):
        registry.create_checkpoint(parent["id"])
    registry.command(parent["id"], "step")
    registry._runtime[parent["id"]].game.backends["Ada"] = object()
    with pytest.raises(CheckpointUnavailable, match="Unsupported backend object"):
        registry.create_checkpoint(parent["id"])
    assert registry.list_checkpoints(parent["id"]) == []


def test_provider_owned_resident_mind_is_rejected_before_any_artifact(registry, tmp_path):
    parent = create(registry)
    registry.command(parent["id"], "step")

    class ProviderMind:
        name = "Ada"
        saved = False

        def save(self, path):
            self.saved = True
            raise RuntimeError("DO_NOT_LEAK /private/provider/secret-state")

    provider_mind = ProviderMind()
    game = registry._runtime[parent["id"]].game
    game.world._actor_minds["Ada"] = provider_mind
    with pytest.raises(CheckpointUnavailable, match="provider-owned resident cognition") as rejected:
        registry.create_checkpoint(parent["id"])
    assert "DO_NOT_LEAK" not in str(rejected.value)
    assert "/private/provider/secret-state" not in str(rejected.value)
    assert provider_mind.saved is False
    assert registry.list_checkpoints(parent["id"]) == []
    assert not (tmp_path / "management-data" / "checkpoints" / parent["id"]).exists()


def test_checkpoint_adapter_errors_are_sanitized(registry, monkeypatch, tmp_path):
    import bigville.game_persistence as persistence

    parent = create(registry)
    registry.command(parent["id"], "step")
    monkeypatch.setattr(persistence, "save_game_checkpoint",
                        lambda game, path: (_ for _ in ()).throw(
                            RuntimeError("DO_NOT_LEAK /private/provider/key")))
    with pytest.raises(CheckpointUnavailable) as rejected:
        registry.create_checkpoint(parent["id"])
    assert "RuntimeError" in str(rejected.value)
    assert "DO_NOT_LEAK" not in str(rejected.value)
    assert "/private/provider/key" not in str(rejected.value)
    assert registry.list_checkpoints(parent["id"]) == []
    assert not (tmp_path / "management-data" / "checkpoints" / parent["id"]).exists()


def test_m10_llm_profile_is_rejected_without_checkpoint_adapter(tmp_path, scenario):
    from bigville.backends.llm import LLMBackend

    profile_file = tmp_path / "management-data" / "backend_profiles.json"
    profile_file.parent.mkdir(parents=True)
    profile_file.write_text(json.dumps({"schema_version": 1, "profiles": [{
        "id": "llm.fixture", "name": "Fixture LLM", "kind": "llm",
        "revision": "r1", "adapter": "adapter.fixture",
    }]}))

    class FakeProvider:
        def complete(self, payload):
            return "{}"

    adapters = BackendAdapterRegistry()
    adapters.register("adapter.fixture", lambda world, character, profile:
                      LLMBackend(character, FakeProvider(), autopilot=False))
    server = create_server(port=0, data_dir=profile_file.parent, profile_adapters=adapters)
    try:
        draft = {"scenario_id": "checkpoint_fixture", "name": "LLM checkpoint run", "seed": 41,
                 "autonomous": True, "default_backend": "simple", "ticks_per_period": "world",
                 "turn_limit": 10, "actor_backend_profiles": {"Ada": "llm.fixture"}}
        resolved = resolve_draft(draft, profile_registry=server.profile_registry)
        parent, _ = server.run_registry.create_run({"draft": draft, "idempotency_key": "llm-checkpoint",
            "expected_config_hash": resolved["configuration_hash"],
            "expected_capability_revision": resolved["capability_revision"]})
        runtime = server.run_registry._runtime[parent["id"]]
        server.run_registry._ensure_game(runtime, server.run_registry.get_run(parent["id"]))
        with pytest.raises(CheckpointUnavailable, match="Unsupported backend LLMBackend"):
            server.run_registry.create_checkpoint(parent["id"])
    finally:
        server.server_close()


def test_corrupt_checkpoint_is_not_forked_and_metadata_is_immutable(registry, tmp_path):
    parent = create(registry)
    registry.command(parent["id"], "step")
    checkpoint = registry.create_checkpoint(parent["id"])
    original_metadata = registry.list_checkpoints(parent["id"])[0]
    artifact = tmp_path / "management-data" / "checkpoints" / parent["id"] / checkpoint["id"]
    generation = json.loads((artifact / "manifest.json").read_text())["generation"]
    game_file = artifact / generation / "game.json"
    game_file.write_text("{} corrupted")
    with pytest.raises(CheckpointUnavailable, match="restoration failed"):
        registry.fork_checkpoint(parent["id"], checkpoint["id"])
    assert registry.get_run(parent["id"])["checkpoints"] == [original_metadata]
    assert len(registry.list_runs()) == 1
    with pytest.raises(RunNotFound):
        registry.fork_checkpoint(parent["id"], "../registry.json")


def test_fork_restore_errors_do_not_expose_artifact_paths_or_provider_text(registry, monkeypatch):
    import bigville.game_persistence as persistence

    parent = create(registry)
    registry.command(parent["id"], "step")
    checkpoint = registry.create_checkpoint(parent["id"])
    monkeypatch.setattr(persistence, "load_game_checkpoint",
                        lambda path: (_ for _ in ()).throw(
                            ValueError("DO_NOT_LEAK /private/checkpoint/provider-key")))
    with pytest.raises(CheckpointUnavailable) as rejected:
        registry.fork_checkpoint(parent["id"], checkpoint["id"])
    assert "ValueError" in str(rejected.value)
    assert "DO_NOT_LEAK" not in str(rejected.value)
    assert "/private/checkpoint/provider-key" not in str(rejected.value)
    assert len(registry.list_runs()) == 1


def test_malformed_checkpoint_metadata_is_rejected_without_overwrite(registry, tmp_path):
    parent = create(registry)
    registry.command(parent["id"], "step")
    registry.create_checkpoint(parent["id"])
    registry_path = tmp_path / "management-data" / "registry.json"
    state = json.loads(registry_path.read_text())
    state["runs"][parent["id"]]["checkpoints"][0]["id"] = "../registry.json"
    malformed = json.dumps(state)
    registry_path.write_text(malformed)
    with pytest.raises(ValueError, match="invalid checkpoint metadata"):
        RunRegistry(tmp_path / "management-data")
    assert registry_path.read_text() == malformed


def test_malformed_run_id_cannot_escape_checkpoint_root(registry, tmp_path):
    parent = create(registry)
    registry_path = tmp_path / "management-data" / "registry.json"
    state = json.loads(registry_path.read_text())
    record = state["runs"].pop(parent["id"])
    record["id"] = "../escaped"
    state["runs"]["../escaped"] = record
    malformed = json.dumps(state)
    registry_path.write_text(malformed)
    with pytest.raises(ValueError, match="invalid record"):
        RunRegistry(tmp_path / "management-data")
    assert registry_path.read_text() == malformed
    assert not (tmp_path / "escaped").exists()


def test_checkpoint_waits_for_turn_boundary(registry, monkeypatch):
    parent = create(registry)
    runtime = registry._runtime[parent["id"]]
    registry._ensure_game(runtime, registry.get_run(parent["id"]))
    game = runtime.game
    entered, release = threading.Event(), threading.Event()
    real_step = game.step

    def slow_step():
        entered.set()
        assert release.wait(5)
        return real_step()

    monkeypatch.setattr(game, "step", slow_step)
    step_thread = threading.Thread(target=lambda: registry.command(parent["id"], "step"))
    step_thread.start()
    assert entered.wait(3)
    results = []
    checkpoint_thread = threading.Thread(
        target=lambda: results.append(registry.create_checkpoint(parent["id"])))
    checkpoint_thread.start()
    assert checkpoint_thread.is_alive()
    release.set()
    step_thread.join(timeout=5)
    checkpoint_thread.join(timeout=5)
    assert not step_thread.is_alive() and not checkpoint_thread.is_alive()
    assert results[0]["turn"] == registry.get_run(parent["id"])["turn"] == 1


def test_checkpoint_and_fork_http_endpoints_and_restart_recovery(scenario, tmp_path):
    data = tmp_path / "api-data"
    server = create_server(port=0, data_dir=data)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    from urllib.request import Request, urlopen
    base = f"http://{server.server_address[0]}:{server.server_address[1]}{API_PREFIX}"
    try:
        parent = create(server.run_registry)
        server.run_registry.command(parent["id"], "step")
        request = Request(f"{base}/runs/{parent['id']}/checkpoints", data=b"{}",
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request) as response:
            checkpoint = json.load(response)
            assert response.status == 201
        with urlopen(f"{base}/runs/{parent['id']}/checkpoints") as response:
            assert json.load(response)["checkpoints"] == [checkpoint]
        fork_request = Request(
            f"{base}/runs/{parent['id']}/checkpoints/{checkpoint['id']}/fork", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(fork_request) as response:
            child = json.load(response)
            assert response.status == 201
        assert child["forked_from"]["checkpoint_id"] == checkpoint["id"]
        registry_path = data / "registry.json"
        registry_before = registry_path.read_bytes()
        traversal = Request(
            f"{base}/runs/{parent['id']}/checkpoints/%2e%2e%2fregistry.json/fork", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST")
        from urllib.error import HTTPError
        with pytest.raises(HTTPError) as rejected:
            urlopen(traversal)
        assert rejected.value.code == 404
        assert registry_path.read_bytes() == registry_before

        # Restart recovery drops the runtime but retains verified checkpoints for forks.
        recovered = RunRegistry(data)
        assert recovered.get_run(parent["id"])["status"] == "failed"
        assert "service restart" in recovered.get_run(parent["id"])["error"]
        recovered_child = recovered.fork_checkpoint(parent["id"], checkpoint["id"])
        assert recovered_child["turn"] == checkpoint["turn"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_checkpoint_http_error_redacts_adapter_exception(scenario, tmp_path, monkeypatch):
    import bigville.game_persistence as persistence
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    data = tmp_path / "redaction-data"
    server = create_server(port=0, data_dir=data)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}{API_PREFIX}"
    try:
        parent = create(server.run_registry)
        server.run_registry.command(parent["id"], "step")
        monkeypatch.setattr(persistence, "save_game_checkpoint",
                            lambda game, path: (_ for _ in ()).throw(
                                RuntimeError("DO_NOT_LEAK /private/adapter/credential")))
        request = Request(f"{base}/runs/{parent['id']}/checkpoints", data=b"{}",
                          headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(HTTPError) as rejected:
            urlopen(request)
        body = json.load(rejected.value)
        encoded = json.dumps(body)
        assert rejected.value.code == 409
        assert body["error"]["code"] == "checkpoint_unavailable"
        assert "RuntimeError" in body["error"]["message"]
        assert "DO_NOT_LEAK" not in encoded
        assert "/private/adapter/credential" not in encoded
        assert server.run_registry.list_checkpoints(parent["id"]) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
