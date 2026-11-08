"""NB04: the partitioned executor dispatches deterministic bundles.

These tests cover the coordinator-side half of the distributed-bundles protocol:
one bundle per coordinator/shard group, every non-joint actor covered exactly
once, a complete dispatch/result/ack/commit log, idempotent duplicate dispatch,
stale/failed result rejection, node provenance, and serial-vs-partitioned
semantic equivalence.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from bigville.api import create_game
from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import CheapBackend
from bigville.bundle_checks import (bundle_execution_sha, bundle_output_sha,
                                    tick_payload_sha)
from bigville.bundles import (BundleResult, ExecutionNamespace,
                              LocalBundleTransport)
from bigville.sharding import (BundleResultError, PartitionedExecutor)
from bigville.tick_trace import (TurnTrace, first_divergence,
                                 semantic_world_state, step_semantic_trace)

TURNS = 8
SEEDS = (305000, 305002)

SMALL_SCENARIO = {
    "id": "nb04_bundle_room",
    "name": "NB04 bundle room",
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
        return ActorResponse(major_action=ProposedAction("rest", {"kind": "nb04_rest"}))


def _game(executor="serial", scenario=SMALL_SCENARIO, seed=305000):
    return create_game(scenario=scenario, seed=seed, default_backend="simple",
                       autonomous=True, llm_log=False, executor=executor,
                       affordance_mode="menu", snapshot_mode="on_demand")


def _fixed_rest_game(executor="partitioned"):
    """Three far-apart resting actors, so each lands in a distinct shard."""
    game = _game(executor=executor)
    for actor in game.characters:
        game.set_backend(actor, _FixedRestBackend(game.characters[actor]))
    game.world._actor_positions["Ada"] = (1, 1)
    game.world._actor_positions["Ben"] = (100, 100)
    game.world._actor_positions["Cy"] = (200, 200)
    return game


def _entries(game, executor=None):
    executor = executor or PartitionedExecutor(workers=2)
    units = executor.units(game, game.last_order, game.last_responses)
    plan = executor.plan(units, game.world)
    return executor, plan, executor.plan_bundles(
        game, game.last_order, game.last_responses, plan)


def _synthetic_result(bundle, *, status="ok", reason="", rows=()):
    """A checksum-valid result that does not touch the world."""
    provisional = BundleResult(
        bundle_id=bundle.bundle_id,
        namespace=bundle.namespace,
        base_version=bundle.base_version,
        status=status,
        effects=(),
        created_ids=(),
        result=tuple(rows),
        output_sha="pending",
        execution_sha="pending",
        reason=reason,
    )
    provisional = replace(provisional, output_sha=bundle_output_sha(provisional))
    return replace(provisional,
                   execution_sha=bundle_execution_sha(bundle, provisional))


class _ResultTransport:
    """A transport seam that returns fixed results and records acks."""

    def __init__(self, make_result):
        self._make_result = make_result
        self.acks = []

    def dispatch(self, bundle):
        return self._make_result(bundle)

    def acknowledge(self, ack):
        self.acks.append(ack)

    def replay(self, bundle_id):
        return None


# ---------------------------------------------------------------- bundle plan


def test_partitioned_turn_builds_one_bundle_per_non_joint_actor_group():
    game = _fixed_rest_game()
    assert game.step()["status"] == "advanced"

    log = game.last_bundle_log
    assert log is not None
    bundles = list(log.dispatched.values())
    assert len(bundles) >= 3, "three far-apart actors should form three shards"

    # Every non-joint order actor appears in exactly one bundle's operations.
    expected = {actor for actor in game.last_order
                if not game._is_joint(game.last_responses[actor])}
    seen: dict[str, set[str]] = {}
    for bundle in bundles:
        for operation in bundle.operations:
            if operation.actor is not None:
                seen.setdefault(operation.actor, set()).add(bundle.bundle_id)
    assert set(seen) == expected
    assert all(len(ids) == 1 for ids in seen.values())

    # Ids and namespaces are unique, and every bundle shares the turn version.
    assert len({bundle.bundle_id for bundle in bundles}) == len(bundles)
    namespaces = [bundle.namespace.name for bundle in bundles]
    assert len(set(namespaces)) == len(namespaces)
    version = int(game.world._turn)
    assert {bundle.base_version for bundle in bundles} == {version}
    assert {bundle.namespace.tick for bundle in bundles} == {version}
    assert {bundle.namespace.executor for bundle in bundles} == {"partitioned"}
    assert {bundle.namespace.run_id for bundle in bundles} == {game.run_id}
    assert log.tick == version
    # The plan's shard and bundle sequence are part of the namespace.
    assert [(bundle.shard, bundle.namespace.bundle_seq) for bundle in bundles] == [
        (bundle.shard, seq) for seq, bundle in enumerate(bundles)]


def test_idle_actors_are_represented_by_an_idle_operation():
    game = _game(executor="partitioned")
    # A response with no major action is an idle unit, not a missing bundle.
    for actor, backend in list(game.backends.items()):
        game.set_backend(actor, _FixedIdleBackend(game.characters[actor]))
    assert game.step()["status"] == "advanced"

    bundles = list(game.last_bundle_log.dispatched.values())
    idle = [operation for bundle in bundles for operation in bundle.operations
            if operation.kind == "idle"]
    assert {operation.actor for operation in idle} == set(game.last_order)
    for operation in idle:
        assert operation.writes == ()


class _FixedIdleBackend(CheapBackend):
    def decide(self, context):
        return ActorResponse(major_action=None)


# ------------------------------------------------------- dispatch/result/ack


def test_dispatch_result_ack_and_commit_order_are_complete_and_deterministic():
    games = [_fixed_rest_game(), _fixed_rest_game()]
    for game in games:
        assert game.step()["status"] == "advanced"

    orders = []
    for game in games:
        log = game.last_bundle_log
        ids = tuple(log.dispatched)
        assert tuple(log.results) == ids
        assert set(log.results) == set(ids)
        assert set(log.acks) == set(ids)
        assert log.committed_order == ids
        assert len(set(log.committed_order)) == len(log.committed_order)
        assert log.payload_sha() == tick_payload_sha(game.world)
        for bundle_id in ids:
            ack = log.acks[bundle_id]
            result = log.results[bundle_id]
            assert ack.outcome == "committed"
            assert ack.base_version == log.dispatched[bundle_id].base_version
            assert ack.committed_version == log.dispatched[bundle_id].base_version
            assert ack.execution_sha == result.execution_sha
        orders.append(log.committed_order)

    # Two identical runs commit the same plan order, not a worker order.
    assert orders[0] == orders[1]


def test_duplicate_dispatch_reuses_the_local_transport_cache():
    game = _fixed_rest_game()
    assert game.step()["status"] == "advanced"
    executor, _plan, entries = _entries(game)
    bundles = [bundle for bundle, _indices in entries]

    calls = []
    original = game._run_component

    def counted(*args, **kwargs):
        calls.append(args[2])
        return original(*args, **kwargs)

    game._run_component = counted
    callback = executor.make_bundle_executor(
        game, game.last_order, game.last_responses, {},
        {bundle.bundle_id: indices for bundle, indices in entries})
    transport = LocalBundleTransport(callback)

    first = executor.dispatch_bundles(bundles, transport)
    assert len(calls) == len(bundles)
    second = executor.dispatch_bundles(bundles, transport)

    assert second == first
    assert all(second[index] is first[index] for index in range(len(first)))
    assert len(calls) == len(bundles), "a duplicate dispatch must not re-run"
    assert len(transport.dispatch_order) == len(bundles)


def test_stale_base_version_is_rejected_and_never_committed():
    game = _fixed_rest_game()
    assert game.step()["status"] == "advanced"
    executor, _plan, entries = _entries(game)
    results_before = dict(game.last_results)

    def stale(bundle):
        return replace(_synthetic_result(bundle),
                       base_version=bundle.base_version + 1)

    transport = _ResultTransport(stale)
    with pytest.raises(BundleResultError, match="stale result"):
        executor.commit(game, game.last_order, game.last_responses,
                        plan=_plan, transport=transport)

    log = game.last_bundle_log
    assert log.committed_order == ()
    assert log.results == {}
    assert transport.acks and transport.acks[0].outcome == "rejected"
    assert transport.acks[0].committed_version is None
    # The synthetic transport never touched the world or the game result map.
    assert game.last_results == results_before


def test_mismatched_namespace_is_rejected():
    game = _fixed_rest_game()
    assert game.step()["status"] == "advanced"
    executor, plan, _entries_ = _entries(game)
    bundle = _entries_[0][0]
    other = ExecutionNamespace(
        run_id=bundle.namespace.run_id, executor="partitioned",
        shard=bundle.namespace.shard, tick=bundle.namespace.tick,
        bundle_seq=bundle.namespace.bundle_seq + 100)

    result = replace(_synthetic_result(bundle), namespace=other)
    transport = _ResultTransport(lambda _bundle: result)
    with pytest.raises(BundleResultError, match="namespace"):
        executor.commit(game, game.last_order, game.last_responses,
                        plan=plan, transport=transport)


def test_error_result_is_acked_rejected_without_committing_or_reapplying():
    game = _fixed_rest_game()
    assert game.step()["status"] == "advanced"
    executor, plan, _entries_ = _entries(game)
    before = semantic_world_state(game.world)

    transport = _ResultTransport(
        lambda bundle: _synthetic_result(bundle, status="error", reason="boom"))
    with pytest.raises(BundleResultError, match="not committed: rejected"):
        executor.commit(game, game.last_order, game.last_responses,
                        plan=plan, transport=transport)

    log = game.last_bundle_log
    assert log.committed_order == ()
    assert len(log.acks) == 1
    ack = next(iter(log.acks.values()))
    assert ack.outcome == "rejected"
    assert ack.committed_version is None
    assert "boom" in ack.reason
    assert semantic_world_state(game.world) == before


def test_retry_result_is_not_committed():
    game = _fixed_rest_game()
    assert game.step()["status"] == "advanced"
    executor, plan, _entries_ = _entries(game)

    transport = _ResultTransport(
        lambda bundle: _synthetic_result(bundle, status="retry", reason="later"))
    with pytest.raises(BundleResultError, match="not committed: retry"):
        executor.commit(game, game.last_order, game.last_responses,
                        plan=plan, transport=transport)

    assert game.last_bundle_log.committed_order == ()
    ack = next(iter(game.last_bundle_log.acks.values()))
    assert ack.outcome == "retry"


# ---------------------------------------------------------------- provenance


def test_nodes_created_by_a_bundle_carry_its_namespace():
    game = _fixed_rest_game()
    assert game.step()["status"] == "advanced"
    log = game.last_bundle_log
    namespaces = {bundle.namespace.name for bundle in log.dispatched.values()}

    known_types = {"MajorAction", "Effort", "Event", "Refusal"}
    for namespace in namespaces:
        created = game.world.eng.nodes_by_origin(namespace)
        assert created
        types = {game.world.eng.node(node)["type"] for node in created}
        assert types & known_types, types
        for node in created:
            assert game.world.eng.node_origin(node) == namespace
            assert game.world.eng.qualified_id(node).namespace == namespace


# ---------------------------------------------------------------- equivalence


@pytest.mark.parametrize("seed", SEEDS)
def test_serial_and_partitioned_match_over_eight_turns(seed):
    serial = _game("serial", scenario="town100", seed=seed)
    partitioned = _game("partitioned", scenario="town100", seed=seed)
    serial_trace = TurnTrace()
    partitioned_trace = TurnTrace()

    for _ in range(TURNS):
        assert serial.step()["status"] == "advanced"
        assert partitioned.step()["status"] == "advanced"
        serial_trace.add_record(step_semantic_trace(serial))
        partitioned_trace.add_record(step_semantic_trace(partitioned))

    assert first_divergence(serial_trace, partitioned_trace) is None
    assert serial_trace.digest == partitioned_trace.digest
    assert semantic_world_state(serial.world) == semantic_world_state(partitioned.world)
    assert serial.last_order == partitioned.last_order
    assert serial.last_results == partitioned.last_results
    assert serial.last_errors == partitioned.last_errors
    assert serial.last_bundle_log is None
    assert partitioned.last_shard_plan is not None

    log = partitioned.last_bundle_log
    assert log is not None
    assert len(log.dispatched) == len(set(log.dispatched))
    assert log.committed_order == tuple(log.dispatched)
    assert len(log.committed_order) == len(set(log.committed_order))


def _trace(game):
    from bigville.tick_trace import TurnTrace, step_semantic_trace
    trace = TurnTrace()
    trace.add_record(step_semantic_trace(game))
    return trace


def test_serial_and_threaded_paths_do_not_create_a_bundle_log():
    for executor in ("serial", "threaded"):
        game = _fixed_rest_game(executor=executor)
        assert game.step()["status"] == "advanced"
        assert game.last_bundle_log is None
        assert game.last_shard_plan is None
