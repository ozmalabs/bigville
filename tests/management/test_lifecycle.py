import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from bigville.management.drafts import resolve_draft
from bigville.management.runs import (InvalidTransition, RunConflict,
                                      RunRegistry)


@pytest.fixture
def authored_scenario(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    scenario = {
        "id": "lifecycle_fixture", "name": "Lifecycle Fixture",
        "map": {"grid": [["wall", "wall", "wall", "wall"],
                         ["wall", "floor", "floor", "wall"],
                         ["wall", "floor", "floor", "wall"],
                         ["wall", "wall", "wall", "wall"]],
                 "layout": {"w": 4, "h": 4, "homes": [[1, 1]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple",
                    "home_cell": [1, 1]}],
    }
    (root / "lifecycle_fixture.json").write_text(json.dumps(scenario))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    return scenario


def request_for(draft, key="life"):
    resolved = resolve_draft(draft)
    return {"draft": draft, "idempotency_key": key,
            "expected_config_hash": resolved["configuration_hash"],
            "expected_capability_revision": resolved["capability_revision"]}


def run_draft(turn_limit=None):
    return {"scenario_id": "lifecycle_fixture", "name": "Life test",
            "seed": 5, "autonomous": True, "default_backend": "simple",
            "ticks_per_period": "world", "turn_limit": turn_limit}


@pytest.fixture
def registry(tmp_path):
    return RunRegistry(tmp_path / "runs")


def create(registry, turn_limit=None, key="life"):
    return registry.create_run(request_for(run_draft(turn_limit), key))[0]


def wait_for(registry, run_id, status, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = registry.get_run(run_id)
        if record["status"] == status:
            return record
        if record["status"] in {"failed", "stopped", "completed"} and record["status"] != status:
            raise AssertionError(f"Run ended in {record['status']}: {record['error']}")
        time.sleep(0.01)
    raise AssertionError(f"Run did not reach {status}; latest={registry.get_run(run_id)}")


def test_real_step_from_created_and_turn_limit_completes_after_turn(registry, authored_scenario):
    record = create(registry, turn_limit=2)
    stepped = registry.command(record["id"], "step")
    assert stepped["status"] == "created"
    assert stepped["turn"] == 1
    with pytest.raises(InvalidTransition):
        registry.command(record["id"], "pause")

    completed = registry.command(record["id"], "step")
    assert completed["status"] == "completed"
    assert completed["turn"] == 2
    assert completed["error"] is None


def test_worker_runs_real_game_until_finite_limit(registry, authored_scenario):
    record = create(registry, turn_limit=2, key="finite")
    accepted = registry.command(record["id"], "start")
    assert accepted["status"] in {"starting", "running"}
    completed = wait_for(registry, record["id"], "completed")
    assert completed["turn"] == 2
    assert registry.get_run(record["id"])["status"] == "completed"


def test_pause_step_resume_stop_and_illegal_transitions(registry, authored_scenario):
    record = create(registry, key="controls")
    with pytest.raises(InvalidTransition):
        registry.command(record["id"], "resume")
    registry.command(record["id"], "start")
    wait_for(registry, record["id"], "running")
    paused = registry.command(record["id"], "pause")
    assert paused["status"] == "paused"
    before = paused["turn"]
    stepped = registry.command(record["id"], "step")
    assert stepped["status"] == "paused"
    assert stepped["turn"] == before + 1
    registry.command(record["id"], "resume")
    wait_for(registry, record["id"], "running")
    stopped = registry.command(record["id"], "stop")
    assert stopped["status"] == "stopped"
    with pytest.raises(InvalidTransition):
        registry.command(record["id"], "start")
    with pytest.raises(InvalidTransition):
        registry.command(record["id"], "resume")


def test_distinct_runs_have_independent_worlds_and_turn_counts(registry, authored_scenario):
    first = create(registry, turn_limit=5, key="isolated-a")
    second = create(registry, turn_limit=5, key="isolated-b")
    stepped = registry.command(first["id"], "step")
    assert stepped["turn"] == 1
    assert registry.get_run(second["id"])["turn"] == 0
    assert registry._runtime[first["id"]].game is not registry._runtime[second["id"]].game


def test_worker_exception_is_durable_and_truthful(registry, authored_scenario, monkeypatch):
    import bigville.management.runs as runs

    class BrokenGame:
        def step(self):
            raise RuntimeError("fixture worker failure")

    monkeypatch.setattr(runs, "create_game", lambda **kwargs: BrokenGame())
    record = create(registry, key="worker-failure")
    registry.command(record["id"], "start")
    failed = wait_for(registry, record["id"], "failed")
    assert failed["error"].startswith("worker failed: RuntimeError: fixture worker failure")


def test_waiting_is_not_completion_and_cannot_resume_without_input(registry,
                                                                    authored_scenario,
                                                                    monkeypatch):
    import bigville.management.runs as runs

    class WaitingGame:
        world = SimpleNamespace(_turn=0)

        def step(self):
            return {"status": "waiting", "actor": "Ada"}

    monkeypatch.setattr(runs, "create_game", lambda **kwargs: WaitingGame())
    record = create(registry, key="waiting")
    registry.command(record["id"], "start")
    waiting = wait_for(registry, record["id"], "waiting")
    assert waiting["status"] == "waiting"
    assert waiting["turn"] == 0
    with pytest.raises(InvalidTransition, match="waiting runs need input"):
        registry.command(record["id"], "resume")
    assert registry.command(record["id"], "stop")["status"] == "stopped"


def test_simultaneous_pause_and_stop_are_serialized_at_turn_boundary(
        registry, authored_scenario, monkeypatch):
    import bigville.management.runs as runs

    entered = threading.Event()
    release = threading.Event()

    class GatedGame:
        def __init__(self):
            self.world = SimpleNamespace(_turn=0)

        def step(self):
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("step gate timeout")
            self.world._turn += 1
            return {"status": "running"}

    monkeypatch.setattr(runs, "create_game", lambda **kwargs: GatedGame())
    record = create(registry, key="simultaneous")
    registry.command(record["id"], "start")
    assert entered.wait(timeout=5)

    barrier = threading.Barrier(3)

    def issue(command):
        barrier.wait(timeout=3)
        try:
            return registry.command(record["id"], command)["status"]
        except InvalidTransition:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        pause_future = pool.submit(issue, "pause")
        stop_future = pool.submit(issue, "stop")
        barrier.wait(timeout=3)
        time.sleep(0.02)
        release.set()
        outcomes = {pause_future.result(timeout=5), stop_future.result(timeout=5)}
    final = registry.get_run(record["id"])
    assert final["turn"] == 1
    assert final["status"] in {"paused", "stopped"}
    assert "conflict" in outcomes or final["status"] == "stopped"
    if final["status"] == "paused":
        assert registry.command(record["id"], "stop")["status"] == "stopped"


def test_restart_marks_unfinished_records_failed_without_resuming(tmp_path,
                                                                 registry,
                                                                 authored_scenario):
    progressed = create(registry, key="progressed")
    registry.command(progressed["id"], "step")
    active = create(registry, key="active")
    with registry._lock:
        registry._update(registry._record(active["id"]), status="running")

    restarted = RunRegistry(tmp_path / "runs")
    for run_id in (progressed["id"], active["id"]):
        record = restarted.get_run(run_id)
        assert record["status"] == "failed"
        assert "interrupted by service restart" in record["error"]
    assert restarted.get_run(progressed["id"])["turn"] == 1
    with pytest.raises(InvalidTransition):
        restarted.command(active["id"], "resume")


def test_created_unstarted_run_survives_restart(registry, tmp_path, authored_scenario):
    record = create(registry, key="not-started")
    restarted = RunRegistry(tmp_path / "runs")
    assert restarted.get_run(record["id"])["status"] == "created"


def test_start_refuses_authored_scenario_changed_after_creation(
        registry, authored_scenario, tmp_path):
    from bigville.scenarios import SCENARIO_ROOT

    record = create(registry, key="scenario-drift")
    authored_scenario["name"] = "Changed after creation"
    (SCENARIO_ROOT / "lifecycle_fixture.json").write_text(json.dumps(authored_scenario))
    failed = registry.command(record["id"], "start")
    assert failed["status"] == "failed"
    assert "identity changed" in failed["error"]
    assert failed["turn"] == 0


def test_start_refuses_engine_build_changed_after_creation(
        registry, authored_scenario, monkeypatch):
    from bigville.management import catalog

    record = create(registry, key="build-drift")
    original = catalog._build_identity
    monkeypatch.setattr(catalog, "_build_identity", lambda: {
        **original(), "engine_source_hash": "changed-build-hash",
    })
    failed = registry.command(record["id"], "start")
    assert failed["status"] == "failed"
    assert "identity changed" in failed["error"] or "Capability revision changed" in failed["error"]
