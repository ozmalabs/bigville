"""DR05: integration of revisions, journal, deltas and the process transport.

These are cross-phase tests.  They do not re-test every DR01-DR04 unit rule;
they prove the pieces work together on a real partitioned game turn:

* serial vs partitioned payload and graph-revision equality;
* a durable journal that replays to the live tick log;
* result effects that reconstruct a ``GraphDelta`` on a mutating turn;
* a bundle round trip through a real process worker.

The scenario is the small three-actor room so the suite stays bounded.  The
process test skips cleanly when this platform has no usable worker start method.
"""
from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import pytest

from bigville.api import create_game
from bigville.backends import ActorResponse
from bigville.backends.cheap import CheapBackend
from bigville.bundle_checks import tick_payload_sha
from bigville.bundles import (Bundle, BundleAck, BundleOperation,
                              ExecutionNamespace)
from bigville.process_transport import (ProcessBundleTransport,
                                        ProcessTransportClosedError,
                                        delta_executor)
from bigville.runtime import GraphDelta
from bigville.tick_trace import semantic_world_state
from worlds.tick_graph import Resource


SMALL_SCENARIO = {
    "id": "dr05_runtime_room",
    "name": "DR05 runtime room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple",
         "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple",
         "home_cell": [2, 2]},
        {"name": "Cy", "role": "farmer", "backend": "simple",
         "home_cell": [3, 3]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False,
                            "decay": False},
    "buildings": [],
    "laws": [],
    "policies": [],
    "charters": [],
}

ONE_ACTOR_SCENARIO = {
    "id": "dr05_one_actor",
    "name": "DR05 one actor room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple",
         "home_cell": [1, 1]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False,
                            "decay": False},
    "buildings": [],
    "laws": [],
    "policies": [],
    "charters": [],
}


class _SpeakerBackend(CheapBackend):
    """Speak without a major action: one Utterance node per turn."""

    def decide(self, context):
        return ActorResponse(utterances=[{"text": "hello there"}])


def _game(executor: str, *, scenario: dict = SMALL_SCENARIO,
          seed: int = 305000, bundle_log_path: str | None = None):
    return create_game(
        scenario=scenario,
        seed=seed,
        default_backend="simple",
        autonomous=True,
        llm_log=False,
        executor=executor,
        affordance_mode="menu",
        snapshot_mode="on_demand",
        bundle_log_path=bundle_log_path,
    )


# ---------------------------------------------------------------- equivalence


def test_serial_and_partitioned_payload_revision_equivalence():
    serial = _game("serial")
    partitioned = _game("partitioned")
    previous_revision = partitioned.world.revision

    for turn in range(1, 7):
        assert serial.step()["status"] == "advanced"
        assert partitioned.step()["status"] == "advanced"

        assert tick_payload_sha(serial.world) == tick_payload_sha(
            partitioned.world), f"turn {turn}: payload checksum differs"
        assert semantic_world_state(serial.world) == semantic_world_state(
            partitioned.world), f"turn {turn}: semantic world differs"
        assert serial.world.revision == partitioned.world.revision, (
            f"turn {turn}: revision differs")
        assert partitioned.world.revision >= previous_revision
        previous_revision = partitioned.world.revision

        log = partitioned.last_bundle_log
        assert log is not None
        ids = tuple(log.dispatched)
        assert ids and len(ids) == len(set(ids))
        assert set(log.results) == set(ids)
        assert set(log.acks) == set(ids)
        assert log.committed_order == ids
        for bundle_id in ids:
            bundle = log.dispatched[bundle_id]
            result = log.results[bundle_id]
            ack = log.acks[bundle_id]
            assert result.base_version == bundle.base_version
            assert ack.outcome == "committed"
            assert ack.base_version == bundle.base_version
            assert ack.committed_version >= ack.base_version
            assert ack.execution_sha == result.execution_sha


# -------------------------------------------------------------------- journal


def test_partitioned_journal_replays_to_live_tick_log(tmp_path):
    path = tmp_path / "dr05_journal.jsonl"
    game = _game("partitioned", bundle_log_path=str(path))
    live_logs = []

    for _ in range(3):
        assert game.step()["status"] == "advanced"
        live_logs.append(game.last_bundle_log.to_dict())

    assert path.is_file()
    journal = game.bundle_journal
    report = journal.verify()
    assert report.ticks == 3
    assert report.aborted_ticks == 0
    assert report.bundles >= 3
    assert report.truncated_tail is False
    assert report.byte_size == path.stat().st_size

    replayed = journal.replay()
    assert len(replayed) == 3
    for live, rebuilt in zip(live_logs, replayed):
        assert rebuilt.to_dict() == live
        assert rebuilt.committed_order == tuple(rebuilt.dispatched)
        assert set(rebuilt.acks) == set(rebuilt.dispatched)
    assert replayed[-1].to_dict() == game.last_bundle_log.to_dict()
    assert replayed[-1].execution_sha == game.last_bundle_log.execution_sha
    assert replayed[-1].payload_sha() == tick_payload_sha(game.world)
    journal.close()


def test_serial_game_writes_no_journal(tmp_path):
    path = tmp_path / "serial.jsonl"
    game = _game("serial", bundle_log_path=str(path))
    for _ in range(2):
        assert game.step()["status"] == "advanced"

    assert game.last_bundle_log is None
    assert game.bundle_journal is not None
    assert not path.exists()
    assert list(game.bundle_journal.read()) == []
    game.bundle_journal.close()


# --------------------------------------------------------------------- deltas


def test_bundle_effects_reconstruct_a_json_graph_delta():
    game = _game("partitioned", scenario=ONE_ACTOR_SCENARIO)
    game.set_backend("Ada", _SpeakerBackend(game.characters["Ada"]))
    assert game.step()["status"] == "advanced"

    log = game.last_bundle_log
    assert log is not None and log.results
    results_with_effects = [result for result in log.results.values()
                            if result.effects]
    assert results_with_effects, "a node-creating turn must report effects"

    result = results_with_effects[0]
    bundle = log.dispatched[result.bundle_id]
    ack = log.acks[result.bundle_id]
    assert any(effect.get("op") == "add_node"
               for effect in result.effects)
    assert result.base_version == bundle.base_version

    delta = GraphDelta.from_effects(
        result.effects, base_revision=result.base_version)
    assert delta.base_revision == result.base_version
    assert delta.to_effects() == result.effects
    assert ack.committed_version is not None
    assert delta.base_revision <= ack.committed_version <= game.world.revision

    end_revision = ack.committed_version
    enveloped = GraphDelta.from_effects(
        result.effects, base_revision=result.base_version,
        end_revision=end_revision)
    wire = json.loads(json.dumps(enveloped.to_dict(), sort_keys=True,
                                 allow_nan=False))
    rebuilt = GraphDelta.from_dict(wire)
    assert rebuilt.to_dict() == enveloped.to_dict()
    assert rebuilt.base_revision == result.base_version
    assert rebuilt.end_revision == end_revision


# -------------------------------------------------------------------- process


def _process_bundle(marker: Path) -> Bundle:
    namespace = ExecutionNamespace(
        run_id="dr05", executor="process", shard=0, tick=1, bundle_seq=0)
    operations = (
        BundleOperation(
            op_id="add", actor="Ada", kind="add_node",
            params={"node": 1, "type": "Agent", "attrs": {"name": "Ada"},
                    "mode": "sleep_once", "seconds": 0.6,
                    "marker": str(marker)},
            reads=(), writes=(Resource("actor", "Ada"),),
            tiebreak=(0, "Ada", "add")),
        BundleOperation(
            op_id="attr", actor="Ada", kind="set_attr",
            params={"node": 1, "key": "mood", "value": 2},
            reads=(), writes=(Resource("actor", "Ada"),),
            tiebreak=(1, "Ada", "attr")),
    )
    return Bundle(
        bundle_id=namespace.name,
        namespace=namespace,
        run_id=namespace.run_id,
        tick=namespace.tick,
        shard=namespace.shard,
        base_version=0,
        operations=operations,
        reads=(),
        writes=(Resource("actor", "Ada"),),
        tiebreak=(0, "Ada"),
    )


def test_process_transport_dispatch_timeout_ack_and_close(tmp_path):
    mp = pytest.importorskip("multiprocessing")
    if "fork" not in mp.get_all_start_methods():
        pytest.skip("fork start method is not available")

    bundle = _process_bundle(tmp_path / "sleep_once.marker")
    try:
        transport = ProcessBundleTransport(
            executor="test", workers=1, timeout=0.2, retries=1,
            start_method="fork")
    except Exception as exc:  # no usable process workers in this environment
        pytest.skip(f"process workers unavailable: {type(exc).__name__}: {exc}")

    try:
        result = transport.dispatch(bundle)
        # The first attempt slept past the timeout, the worker was replaced and
        # the retry observed the marker and completed deterministically.
        assert transport.executions == 2
        expected = delta_executor(bundle)
        assert result.output_sha == expected.output_sha
        assert result.execution_sha == expected.execution_sha

        duplicate = transport.dispatch(Bundle.from_dict(json.loads(json.dumps(
            bundle.to_dict(), sort_keys=True, allow_nan=False))))
        assert duplicate is result
        assert transport.executions == 2

        ack = BundleAck(
            bundle_id=bundle.bundle_id,
            base_version=bundle.base_version,
            outcome="committed",
            committed_version=bundle.base_version,
            execution_sha=result.execution_sha,
        )
        transport.acknowledge(ack)
        assert transport.replay(bundle.bundle_id) is result
        assert transport.acknowledgement(bundle.bundle_id) == ack
        assert transport.dispatch_order == (bundle.bundle_id,)
    finally:
        transport.close()

    assert transport.worker_processes == ()
    with pytest.raises(ProcessTransportClosedError):
        transport.dispatch(bundle)
