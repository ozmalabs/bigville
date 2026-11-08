"""DR03: graph change deltas, replay and bundle effect results.

A bundle executes against the live in-process world, but it also records the
mutations it made as a ``GraphDelta``.  The delta is JSON-safe, can be applied
to a graph at the same base revision, and is exposed through
``BundleResult.effects`` as the transport/replay form a worker could return.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from bigville.api import create_game
from bigville.backends import ActorResponse
from bigville.backends.cheap import CheapBackend
from bigville.runtime import BigvilleGraph, GraphDelta, NodeRef
from bigville.sharding import PartitionedExecutor


SMALL_SCENARIO = {
    "id": "dr03_delta_room",
    "name": "DR03 delta room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [2, 2]},
        {"name": "Cy", "role": "farmer", "backend": "simple", "home_cell": [3, 3]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [],
    "laws": [],
    "policies": [],
    "charters": [],
}

ONE_ACTOR_SCENARIO = {
    "id": "dr03_one_actor",
    "name": "DR03 one actor room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [],
    "laws": [],
    "policies": [],
    "charters": [],
}


class _SpeakerBackend(CheapBackend):
    """Speak without taking a major action: one Utterance node per turn."""

    def decide(self, context):
        return ActorResponse(utterances=[{"text": "hello there"}])


class _IdleBackend(CheapBackend):
    def decide(self, context):
        return ActorResponse()


# ---------------------------------------------------------------- recording


def test_record_and_apply_every_mutation_type():
    graph = BigvilleGraph()
    a = graph.add_node("Agent", {"name": "a"})
    b = graph.add_node("Item", {"name": "b"})
    graph.add_edge(a, "holds", b)
    base = graph.revision
    base_checkpoint = graph.to_checkpoint_dict()

    with graph.record_changes() as delta:
        c = graph.add_node("Tool", {"name": "c"})
        graph.add_edge(c, "part_of", a)
        graph.set_attr(a, "mood", 2.0)
        graph.set_attr(a, "mood", 3.0)
        graph.remove_edge_unchecked(a, "holds", b)
        graph.remove_node(a)

    assert delta.base_revision == base
    assert delta.end_revision == graph.revision
    assert delta.nodes_added == [(int(c), "Tool", {"name": "c"}, "unqualified")]
    assert delta.nodes_removed == [int(a)]
    assert delta.edges_added == [(int(c), "part_of", int(a))]
    # The explicit edge removal is recorded at its own mutation point; the
    # later node removal records only the incident edge still present (c->a).
    assert delta.edges_removed == [(int(a), "holds", int(b)),
                                   (int(c), "part_of", int(a))]
    assert delta.attrs == [(int(a), "mood", None, 2.0),
                           (int(a), "mood", 2.0, 3.0)]

    restored = BigvilleGraph.from_checkpoint_dict(base_checkpoint)
    assert delta.apply_to(restored) is restored
    assert restored.to_checkpoint_dict() == graph.to_checkpoint_dict()
    assert restored.revision == delta.end_revision


def test_remove_node_records_every_incident_edge_once_in_sorted_order():
    graph = BigvilleGraph()
    a = graph.add_node("Agent", {})
    b = graph.add_node("Agent", {})
    c = graph.add_node("Agent", {})
    graph.add_edge(a, "knows", b)
    graph.add_edge(b, "likes", a)
    graph.add_edge(c, "follows", a)
    graph.add_edge(b, "knows", c)
    base = graph.revision
    checkpoint = graph.to_checkpoint_dict()

    with graph.record_changes() as delta:
        graph.remove_node(a)

    assert delta.nodes_removed == [int(a)]
    assert delta.edges_removed == [
        (int(a), "knows", int(b)),
        (int(b), "likes", int(a)),
        (int(c), "follows", int(a)),
    ]
    assert len(delta.edges_removed) == len(set(delta.edges_removed))

    restored = BigvilleGraph.from_checkpoint_dict(checkpoint)
    delta.apply_to(restored)
    assert restored.to_checkpoint_dict() == graph.to_checkpoint_dict()


def test_added_node_origin_is_preserved_by_replay():
    graph = BigvilleGraph()
    base = graph.to_checkpoint_dict()

    with graph.record_changes() as delta:
        with graph.execution_namespace("rrun/t1/partitioned/s0/b0/a1"):
            node = graph.add_node("Memory", {"text": "recorded"})

    assert delta.nodes_added[0][3] == "rrun/t1/partitioned/s0/b0/a1"
    restored = BigvilleGraph.from_checkpoint_dict(base)
    delta.apply_to(restored)
    assert restored.node_origin(node) == "rrun/t1/partitioned/s0/b0/a1"
    assert restored.to_checkpoint_dict() == graph.to_checkpoint_dict()


def test_failed_mutations_are_not_recorded():
    graph = BigvilleGraph()
    node = graph.add_node("Agent", {})
    base = graph.revision

    with graph.record_changes() as delta:
        with pytest.raises(KeyError):
            graph.set_attr(999, "missing", 1)
        with pytest.raises(KeyError):
            graph.add_edge_unchecked(node, "knows", 999)
        # An absent-node removal is a documented no-op, not a mutation.
        graph.remove_node(999)

    assert delta.nodes_added == []
    assert delta.nodes_removed == []
    assert delta.edges_added == []
    assert delta.edges_removed == []
    assert delta.attrs == []
    assert delta.operations == []
    assert delta.base_revision == base
    assert delta.end_revision == base
    assert delta.to_effects() == ()


# ---------------------------------------------------------------- serialization


def test_json_round_trip_delta_and_effects_reproduce_the_same_state():
    graph = BigvilleGraph()
    a = graph.add_node("Agent", {"name": "a", "tags": ("x", "y")})
    b = graph.add_node("Item", {"name": "b"})
    graph.add_edge(a, "holds", b)
    base = graph.revision
    checkpoint = graph.to_checkpoint_dict()

    with graph.record_changes() as delta:
        c = graph.add_node("Tool", {"name": "c", "parts": {"metal", "wood"},
                                     "owner": NodeRef(a)})
        graph.add_edge(c, "belongs_to", a)
        graph.set_attr(b, "count", 2)
        graph.remove_edge_unchecked(a, "holds", b)

    encoded = json.loads(json.dumps(delta.to_dict()))
    restored_delta = GraphDelta.from_dict(encoded)
    assert restored_delta.to_dict() == encoded
    assert restored_delta == delta

    effects = delta.to_effects()
    assert json.loads(json.dumps(list(effects))) == [dict(effect) for effect in effects]
    from_effects = GraphDelta.from_effects(
        effects, base_revision=delta.base_revision,
        end_revision=delta.end_revision)
    assert from_effects.to_dict() == delta.to_dict()
    assert from_effects.to_effects() == effects

    from_delta = BigvilleGraph.from_checkpoint_dict(checkpoint)
    delta.apply_to(from_delta)
    from_effect = BigvilleGraph.from_checkpoint_dict(checkpoint)
    from_effects.apply_to(from_effect)
    assert from_delta.to_checkpoint_dict() == graph.to_checkpoint_dict()
    assert from_effect.to_checkpoint_dict() == graph.to_checkpoint_dict()
    assert from_delta.revision == delta.end_revision


def test_delta_rejects_the_wrong_base_revision():
    graph = BigvilleGraph()
    base = graph.revision
    base_checkpoint = graph.to_checkpoint_dict()
    with graph.record_changes() as delta:
        graph.add_node("Agent", {})
    checkpoint = graph.to_checkpoint_dict()

    graph.add_node("Agent", {})  # move the live graph past the delta base
    with pytest.raises(ValueError, match="base revision"):
        delta.apply_to(graph)

    # A same-base clone still accepts it.
    rebuilt = BigvilleGraph.from_checkpoint_dict(base_checkpoint)
    assert rebuilt.revision == base
    delta.apply_to(rebuilt)
    assert rebuilt.to_checkpoint_dict() == checkpoint
    assert rebuilt.revision == delta.end_revision


def test_invalid_delta_endpoints_are_rejected_without_partial_application():
    graph = BigvilleGraph()
    node = graph.add_node("Agent", {})
    checkpoint = graph.to_checkpoint_dict()

    delta = GraphDelta(base_revision=graph.revision,
                       end_revision=graph.revision + 1)
    delta.operations = [
        {"op": "add_node", "node": int(node) + 1, "type": "Tool",
         "attrs": {}, "origin": "unqualified"},
        {"op": "add_edge", "source": int(node) + 1, "kind": "uses",
         "target": 12345},
    ]
    with pytest.raises(ValueError, match="missing node endpoint"):
        delta.apply_to(graph)
    assert graph.to_checkpoint_dict() == checkpoint

    duplicate = GraphDelta(base_revision=graph.revision,
                           end_revision=graph.revision + 1)
    duplicate.operations = [
        {"op": "add_node", "node": int(node), "type": "Tool",
         "attrs": {}, "origin": "unqualified"},
    ]
    with pytest.raises(ValueError, match="duplicate node"):
        duplicate.apply_to(graph)
    assert graph.to_checkpoint_dict() == checkpoint


# ---------------------------------------------------------------- isolation


def test_nested_recording_shares_the_outer_delta_and_restores_it():
    graph = BigvilleGraph()
    with graph.record_changes() as outer:
        graph.add_node("Agent", {})
        with graph.record_changes() as inner:
            assert inner is outer
            graph.add_node("Item", {})
        graph.add_node("Tool", {})
    assert len(outer.nodes_added) == 3
    assert outer.end_revision == graph.revision


def test_threads_get_separate_deltas():
    graph = BigvilleGraph()
    barrier = threading.Barrier(2)
    deltas: list[GraphDelta] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        with graph.record_changes() as delta:
            barrier.wait()
            graph.add_node("ThreadNode", {"index": index})
        with lock:
            deltas.append(delta)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, index) for index in range(2)]
        for future in futures:
            future.result(timeout=10)

    assert len(deltas) == 2
    assert all(len(delta.nodes_added) == 1 for delta in deltas)
    assert {delta.nodes_added[0][2]["index"] for delta in deltas} == {0, 1}
    assert {delta.nodes_added[0][0] for delta in deltas} == {1, 2}


# ---------------------------------------------------------------- bundles


def test_bundle_turn_effects_replay_to_the_same_graph_state():
    game = create_game(scenario=ONE_ACTOR_SCENARIO, seed=305000,
                       default_backend="simple", autonomous=True,
                       llm_log=False, executor="partitioned",
                       affordance_mode="menu", snapshot_mode="on_demand")
    game.set_backend("Ada", _SpeakerBackend(game.characters["Ada"]))
    assert game.step()["status"] == "advanced"

    # Populate the turn's order/responses, then run one bundle-only commit so
    # the graph changes are exactly the bundle's delta (no _finish_turn work).
    snapshot = game.world.eng.to_checkpoint_dict()
    executor = PartitionedExecutor(workers=1)
    executor.commit(game, game.last_order, game.last_responses)

    log = game.last_bundle_log
    assert log is not None
    assert len(log.results) == 1
    result = next(iter(log.results.values()))
    assert result.effects
    assert any(effect["op"] == "add_node" for effect in result.effects)
    assert json.loads(json.dumps(result.to_dict()))["effects"]

    effects = [effect for row in log.results.values()
               for effect in row.effects]
    delta = GraphDelta.from_effects(
        effects, base_revision=snapshot["revision"],
        end_revision=game.world.eng.revision)
    replayed = BigvilleGraph.from_checkpoint_dict(snapshot)
    delta.apply_to(replayed)

    assert replayed.to_checkpoint_dict() == game.world.eng.to_checkpoint_dict()
    assert replayed.revision == game.world.eng.revision


def test_bundle_with_no_mutations_has_empty_effects():
    game = create_game(scenario=ONE_ACTOR_SCENARIO, seed=305000,
                       default_backend="simple", autonomous=True,
                       llm_log=False, executor="partitioned",
                       affordance_mode="menu", snapshot_mode="on_demand")
    game.set_backend("Ada", _IdleBackend(game.characters["Ada"]))
    assert game.step()["status"] == "advanced"

    log = game.last_bundle_log
    assert log is not None and log.results
    assert all(result.effects == () for result in log.results.values())


# ---------------------------------------------------------------- equivalence


def test_serial_and_partitioned_state_remains_equal_with_recording():
    serial = create_game(scenario=SMALL_SCENARIO, seed=305000,
                         default_backend="simple", autonomous=True,
                         llm_log=False, executor="serial",
                         affordance_mode="menu", snapshot_mode="on_demand")
    partitioned = create_game(scenario=SMALL_SCENARIO, seed=305000,
                              default_backend="simple", autonomous=True,
                              llm_log=False, executor="partitioned",
                              affordance_mode="menu", snapshot_mode="on_demand")

    for _ in range(3):
        assert serial.step()["status"] == "advanced"
        assert partitioned.step()["status"] == "advanced"

    # Origin provenance intentionally differs: partitioned nodes are stamped
    # with their bundle namespace while serial nodes are "unqualified".  The
    # semantic graph (ids, types, attrs, edges, seeds) and the revision count
    # must still match.
    assert serial.world.eng.revision == partitioned.world.eng.revision
    assert serial.world.eng.graph_to_dict() == \
        partitioned.world.eng.graph_to_dict()
