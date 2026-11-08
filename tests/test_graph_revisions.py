"""DR01: graph/world revisions, bundle base versions and commit versions.

The canonical graph owns a monotonic mutation counter.  It is deterministic
(no wall clock), advances once per logical mutation call, survives checkpoints,
and is the bundle ``base_version``.  A result whose base does not match its
dispatch is stale and is rejected rather than merged.
"""
from __future__ import annotations

import json

import pytest

from bigville.api import create_game
from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import CheapBackend
from bigville.bundles import BundleResult
from bigville.runtime import BigvilleGraph
from bigville.sharding import (BundleResultError, PartitionedExecutor,
                               _base_version)

SMALL_SCENARIO = {
    "id": "dr01_revision_room",
    "name": "DR01 revision room",
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


class _FixedRestBackend(CheapBackend):
    def decide(self, context):
        return ActorResponse(major_action=ProposedAction("rest", {"kind": "dr01_rest"}))


# ---------------------------------------------------------------- graph revision


def test_revision_starts_at_zero_and_each_mutation_increments_once():
    graph = BigvilleGraph()
    assert graph.revision == 0

    a = graph.add_node("Agent", {"name": "a"})
    assert graph.revision == 1
    b = graph.add_node("Agent", {"name": "b"})
    assert graph.revision == 2

    graph.add_edge(a, "knows", b)
    assert graph.revision == 3
    graph.add_edge_unchecked(a, "likes", b)
    assert graph.revision == 4
    graph.set_attr(a, "mood", 1.0)
    assert graph.revision == 5
    graph.remove_edge_unchecked(a, "knows", b)
    assert graph.revision == 6

    # ``remove_node`` cleans up several incident edges internally; that is one
    # logical mutation, not one per edge.
    graph.add_edge_unchecked(b, "follows", a)
    assert graph.revision == 7
    graph.remove_node(a)
    assert graph.revision == 8
    assert not graph.has_node(a)


def test_reads_and_origin_stamps_do_not_change_the_revision():
    graph = BigvilleGraph()
    a = graph.add_node("Agent", {"name": "a"})
    b = graph.add_node("Agent", {"name": "b"})
    graph.add_edge(a, "knows", b)
    before = graph.revision

    assert graph.has_node(a)
    assert graph.node(a)["type"] == "Agent"
    assert graph.node_attrs(a)["name"] == "a"
    assert graph.node_origin(a) == "unqualified"
    assert graph.qualified_id(a).local_id == int(a)
    assert graph.nodes("Agent") == [a, b]
    assert graph.nodes_by_origin("unqualified") == (a, b)
    assert graph.has_edge(a, "knows", b)
    assert graph.neighbours(a, "knows") == [b]
    assert graph.in_neighbours(b, "knows") == [a]
    assert graph.current_origin == "unqualified"
    graph.graph_to_dict()
    graph.to_checkpoint_dict()
    graph.settle()
    graph.force_all_dirty()
    graph.set_read_locking(False)
    with graph.execution_namespace("dr01-read-only"):
        assert graph.current_origin == "dr01-read-only"

    assert graph.revision == before


def test_failed_mutations_do_not_increment_and_seed_manifest_counts_its_nodes():
    graph = BigvilleGraph()
    node = graph.add_node("Agent", {})
    before = graph.revision
    with pytest.raises(KeyError):
        graph.set_attr(99, "missing", 1)
    with pytest.raises(KeyError):
        graph.add_edge_unchecked(node, "knows", 99)
    assert graph.revision == before
    # Removing a node that is not there is a no-op, not a mutation.
    graph.remove_node(99)
    assert graph.revision == before

    # A seed manifest is not special-cased: it creates a Seed node (and an
    # edge when an agent is supplied), so it increments through those calls.
    graph.load_seed_manifest("dr01_seed")
    assert graph.revision == before + 1
    before_edge = graph.revision
    graph.load_seed_manifest("dr01_seed_two", node)
    assert graph.revision == before_edge + 2


# ---------------------------------------------------------------- checkpoints


def test_checkpoint_round_trip_preserves_revision():
    graph = BigvilleGraph()
    a = graph.add_node("Agent", {"name": "a"})
    b = graph.add_node("Item", {"name": "b"})
    graph.add_edge(a, "holds", b)
    graph.set_attr(a, "mood", 2.0)

    checkpoint = graph.to_checkpoint_dict()
    assert checkpoint["revision"] == graph.revision

    restored = BigvilleGraph.from_checkpoint_dict(
        json.loads(json.dumps(checkpoint)))
    assert restored.revision == graph.revision
    assert restored.to_checkpoint_dict() == checkpoint


def test_legacy_checkpoint_without_revision_loads_as_zero():
    graph = BigvilleGraph()
    a = graph.add_node("Agent", {})
    b = graph.add_node("Item", {})
    graph.add_edge(a, "holds", b)
    checkpoint = graph.to_checkpoint_dict()
    checkpoint.pop("revision")

    restored = BigvilleGraph.from_checkpoint_dict(checkpoint)
    assert restored.revision == 0
    # The restored graph is otherwise intact and its next mutation starts at 1.
    assert restored.has_edge(a, "holds", b)
    restored.set_attr(a, "mood", 1.0)
    assert restored.revision == 1


@pytest.mark.parametrize("revision", [-1, True, "3", 1.5, None])
def test_checkpoint_rejects_invalid_revision(revision):
    graph = BigvilleGraph()
    checkpoint = graph.to_checkpoint_dict()
    checkpoint["revision"] = revision
    with pytest.raises(ValueError, match="revision"):
        BigvilleGraph.from_checkpoint_dict(checkpoint)


# ---------------------------------------------------------------- world/bundle versions


def test_world_revision_is_the_graph_revision_and_base_version():
    graph = BigvilleGraph()
    graph.add_node("Agent", {})

    class _World:
        def __init__(self, eng):
            self.eng = eng

    world = _World(graph)
    assert world.eng.revision == 1
    assert _base_version(world) == 1


def test_serial_and_partitioned_revision_counts_match_for_four_turns():
    serial = create_game(scenario=SMALL_SCENARIO, seed=305000,
                         default_backend="simple", autonomous=True,
                         llm_log=False, executor="serial",
                         affordance_mode="menu", snapshot_mode="on_demand")
    partitioned = create_game(scenario=SMALL_SCENARIO, seed=305000,
                              default_backend="simple", autonomous=True,
                              llm_log=False, executor="partitioned",
                              affordance_mode="menu", snapshot_mode="on_demand")

    assert serial.world.revision == partitioned.world.revision
    for _ in range(4):
        assert serial.step()["status"] == "advanced"
        assert partitioned.step()["status"] == "advanced"

    assert serial.world.revision > 0
    assert serial.world.revision == partitioned.world.revision


def _fixed_rest_game():
    game = create_game(scenario=SMALL_SCENARIO, seed=305000,
                       default_backend="simple", autonomous=True,
                       llm_log=False, executor="partitioned",
                       affordance_mode="menu", snapshot_mode="on_demand")
    for actor in game.characters:
        game.set_backend(actor, _FixedRestBackend(game.characters[actor]))
    game.world._actor_positions["Ada"] = (1, 1)
    game.world._actor_positions["Ben"] = (100, 100)
    game.world._actor_positions["Cy"] = (200, 200)
    return game


def test_bundle_plan_uses_world_revision_and_acks_report_monotonic_commit_versions():
    game = _fixed_rest_game()
    assert game.step()["status"] == "advanced"

    executor = PartitionedExecutor(workers=2)
    units = executor.units(game, game.last_order, game.last_responses)
    plan = executor.plan(units, game.world)
    base = game.world.revision
    entries = executor.plan_bundles(game, game.last_order, game.last_responses, plan)

    assert entries
    assert {bundle.base_version for bundle, _indices in entries} == {base}
    assert {bundle.tick for bundle, _indices in entries} == {base}

    executor.commit(game, game.last_order, game.last_responses, plan=plan)
    log = game.last_bundle_log
    assert log is not None
    assert log.tick == base

    committed = []
    for bundle_id in log.committed_order:
        ack = log.acks[bundle_id]
        bundle = log.dispatched[bundle_id]
        assert ack.outcome == "committed"
        assert ack.base_version == bundle.base_version
        assert ack.committed_version is not None
        assert ack.committed_version >= ack.base_version
        committed.append(ack.committed_version)
    assert committed == sorted(committed)
    assert min(committed) >= base


def test_stale_base_version_is_rejected_by_validate_result():
    game = _fixed_rest_game()
    assert game.step()["status"] == "advanced"

    executor = PartitionedExecutor(workers=2)
    units = executor.units(game, game.last_order, game.last_responses)
    plan = executor.plan(units, game.world)
    bundle = executor.plan_bundles(
        game, game.last_order, game.last_responses, plan)[0][0]

    stale = BundleResult(
        bundle_id=bundle.bundle_id,
        namespace=bundle.namespace,
        base_version=bundle.base_version + 1,
        status="ok",
        effects=(),
        created_ids=(),
        result=(),
        output_sha="stale-output",
        execution_sha="stale-execution",
    )
    with pytest.raises(BundleResultError, match="stale result"):
        PartitionedExecutor.validate_result(bundle, stale)

    fresh = BundleResult(
        bundle_id=bundle.bundle_id,
        namespace=bundle.namespace,
        base_version=bundle.base_version,
        status="ok",
        effects=(),
        created_ids=(),
        result=(),
        output_sha="fresh-output",
        execution_sha="fresh-execution",
    )
    PartitionedExecutor.validate_result(bundle, fresh)
    with pytest.raises(BundleResultError, match="committed version"):
        PartitionedExecutor.validate_result(
            bundle, fresh, committed_version=bundle.base_version - 1)
