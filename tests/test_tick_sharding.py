"""TG07: in-process shard assignment and partitioned commit.

The shard map is pure metadata: cells and actors to shard ids, everything else
to the coordinator.  The partitioned executor must reproduce the serial
semantic trace while running independent shards through the TG05 component
seam.  These tests also prove the conservative fallbacks (cross-shard units,
contests) and that importing the benchmark builder has no side effects.
"""
from __future__ import annotations

import threading
import time

import pytest

from bigville.api import create_game
from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import CheapBackend
from bigville.sharding import (PartitionedExecutor, ShardMap, partition_units,
                               ShardPlan)
from bigville.tick_trace import (TurnTrace, first_divergence, semantic_world_state,
                                 step_semantic_trace)
from worlds.tick_graph import Resource

TURNS = 4
SEED = 305000

SMALL_SCENARIO = {
    "id": "tg07_sharding_room",
    "name": "TG07 sharding room",
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


class _FakeWorld:
    """The read-only position slice the shard map needs."""

    def __init__(self, positions):
        self._actor_positions = dict(positions)
        self._actors = {name: index for index, name in enumerate(positions)}

    def actor_position(self, actor):
        return self._actor_positions.get(actor)


def _game(scenario=SMALL_SCENARIO, *, executor="serial"):
    game = create_game(scenario=scenario, seed=SEED, default_backend="simple",
                       autonomous=True, llm_log=False, executor=executor,
                       affordance_mode="menu")
    return game


def _set_backend(game, actor, factory):
    game.set_backend(actor, factory(game.characters[actor]))


def _run(game, turns=TURNS):
    trace = TurnTrace()
    for _ in range(turns):
        assert game.step()["status"] == "advanced"
        trace.add_record(step_semantic_trace(game))
    return trace


class _FixedRestBackend(CheapBackend):
    def decide(self, context):
        return ActorResponse(major_action=ProposedAction("rest", {"kind": "tg07_rest"}))


class _FixedTakeBackend(CheapBackend):
    def __init__(self, character, target):
        super().__init__(character)
        self.target = target

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction(
            "take", {"source": self.target, "kind": "coin", "amount": 1}))


# ---------------------------------------------------------------- shard map


def test_cell_shards_are_deterministic_for_positive_negative_and_edge_cells():
    first, second = ShardMap(cell_size=8), ShardMap(cell_size=8)
    cells = [(0, 0), (7, 7), (8, 8), (-1, -1), (-8, -8), (-9, 0), (100, 100)]

    for cell in cells:
        assert first.cell_shard(cell) == second.cell_shard(cell)
        assert first.cell_shard(cell) >= 1        # 0 is the coordinator
        assert first.cell_shard(list(cell)) == first.cell_shard(cell)

    # Adjacent grid blocks differ; the same block shares one shard.
    assert first.cell_shard((0, 0)) != first.cell_shard((8, 8))
    assert first.cell_shard((-1, -1)) == first.cell_shard((-8, -8))
    assert first.cell_shard((-9, 0)) != first.cell_shard((0, 0))
    assert first.to_dict() == {"cell_size": 8, "coordinator": 0}


def test_actor_and_resource_shard_mapping_uses_position_or_coordinator():
    world = _FakeWorld({"Ada": (1, 1), "Ben": (100, 100)})
    shard_map = ShardMap(cell_size=8)

    assert shard_map.actor_shard("Ada", world) == shard_map.cell_shard((1, 1))
    assert shard_map.actor_shard("Ghost", world) == shard_map.coordinator
    assert shard_map.actor_shard(None, world) == shard_map.coordinator

    assert shard_map.resource_shard(Resource("actor", "Ben"), world) == shard_map.cell_shard((100, 100))
    assert shard_map.resource_shard(Resource("cell", (-9, 4)), world) == shard_map.cell_shard((-9, 4))
    for kind, key in (("stock", "grain"), ("container", "crate"), ("item", "coin"),
                      ("building", "mill"), ("job", "bake"), ("utterance", 3),
                      ("memory", "Ada"), ("world", "global")):
        assert shard_map.resource_shard(Resource(kind, key), world) == shard_map.coordinator
    # EN04 follow-up: co-location witnesses are spatial resources.
    assert shard_map.resource_shard(Resource("witness", (1, 1)), world) == \
        shard_map.cell_shard((1, 1))
    assert shard_map.resource_shard(Resource("witness", "Ada"), world) == \
        shard_map.actor_shard("Ada", world)


def test_unit_shards_and_cross_shard_detection():
    world = _FakeWorld({"Ada": (1, 1)})
    shard_map = ShardMap(cell_size=8)
    local = [Resource("actor", "Ada"), Resource("cell", (1, 1))]
    far = [Resource("actor", "Ada"), Resource("cell", (100, 100))]

    assert shard_map.unit_shards(local, world) == frozenset({shard_map.cell_shard((1, 1))})
    assert not shard_map.is_cross_shard(local, world)
    assert shard_map.is_cross_shard(far, world)
    assert shard_map.is_cross_shard([Resource("actor", "Ada"), Resource("stock", "grain")],
                                    world)


# ---------------------------------------------------------------- planning


def test_partition_units_places_every_actor_exactly_once():
    world = _FakeWorld({"Ada": (1, 1), "Ben": (100, 100), "Cy": (1, 2)})
    units = {
        "Ada": {Resource("actor", "Ada"), Resource("cell", (1, 1))},
        "Ben": {Resource("actor", "Ben"), Resource("cell", (100, 100))},
        "Cy": {Resource("actor", "Cy"), Resource("stock", "grain")},
    }
    plan = partition_units(units, world, ShardMap(cell_size=8))

    flat = [actor for actors in plan.by_shard.values() for actor in actors]
    assert sorted(flat) == ["Ada", "Ben", "Cy"]
    assert len(flat) == len(set(flat))
    assert plan.shard_of("Cy") == 0
    assert "Cy" in plan.coordinator_units
    assert "Cy" in plan.cross_shard


def test_far_apart_actors_land_in_different_shards():
    world = _FakeWorld({"Ada": (0, 0), "Ben": (100, 100)})
    plan = partition_units({
        "Ada": {Resource("actor", "Ada")},
        "Ben": {Resource("actor", "Ben")},
    }, world, ShardMap(cell_size=8))

    assert plan.shard_of("Ada") != plan.shard_of("Ben")
    assert plan.cross_shard == ()
    assert plan.coordinator_units == ()


def test_a_non_spatial_resource_forces_the_coordinator_barrier():
    world = _FakeWorld({"Ada": (1, 1)})
    plan = partition_units({
        "Ada": {Resource("actor", "Ada"), Resource("interview", "mayor")},
    }, world, ShardMap(cell_size=8))

    assert plan.cross_shard == ("Ada",)
    assert plan.coordinator_units == ("Ada",)
    assert plan.by_shard[0] == ("Ada",)


def test_plan_is_independent_of_dict_insertion_order():
    world = _FakeWorld({"Ada": (1, 1), "Ben": (100, 100), "Cy": (200, 5)})
    resources = {
        "Ada": {Resource("actor", "Ada")},
        "Ben": {Resource("actor", "Ben")},
        "Cy": {Resource("actor", "Cy"), Resource("world", "global")},
    }
    forward = partition_units(resources, world, ShardMap(cell_size=8))
    backward = partition_units(dict(reversed(list(resources.items()))), world,
                               ShardMap(cell_size=8))

    assert forward.by_shard == backward.by_shard
    assert forward.cross_shard == backward.cross_shard
    assert forward.coordinator_units == backward.coordinator_units
    assert forward.to_dict() == backward.to_dict()


def test_shard_plan_is_a_stable_dataclass_view():
    plan = ShardPlan(by_shard={1: ("Ada",), 0: ("Ben",)}, cross_shard=(),
                     coordinator_units=("Ben",))
    assert plan.shard_of("Ada") == 1
    assert plan.shard_of("Ben") == 0
    assert plan.shard_of("Nobody") is None
    assert plan.to_dict()["by_shard"] == {"0": ["Ben"], "1": ["Ada"]}


# ---------------------------------------------------------------- semantic equivalence


@pytest.mark.parametrize("scenario", ["town100", SMALL_SCENARIO], ids=["town100", "small"])
def test_partitioned_matches_the_serial_semantic_trace_over_four_turns(scenario):
    serial_a = _game(scenario, executor="serial")
    serial_b = _game(scenario, executor="serial")
    partitioned_a = _game(scenario, executor="partitioned")
    partitioned_b = _game(scenario, executor="partitioned")

    trace_a = _run(serial_a)
    trace_b = _run(serial_b)
    trace_pa = _run(partitioned_a)
    trace_pb = _run(partitioned_b)

    # The serial path stays deterministic and unchanged.
    assert trace_a.records == trace_b.records
    assert trace_a.digest == trace_b.digest

    # Partitioned equivalence is semantic, exactly as for the threaded path.
    assert first_divergence(trace_a, trace_pa) is None, (
        first_divergence(trace_a, trace_pa))
    assert trace_a.digest == trace_pa.digest
    assert trace_pa.digest == trace_pb.digest
    assert semantic_world_state(serial_a.world) == semantic_world_state(partitioned_a.world)
    assert serial_a.last_order == partitioned_a.last_order
    assert serial_a.last_results == partitioned_a.last_results
    assert serial_a.last_errors == partitioned_a.last_errors
    assert partitioned_a.last_shard_plan is not None


def test_partitioned_contest_turn_falls_back_to_the_serial_loop():
    def build(executor):
        game = _game(executor=executor)
        _set_backend(game, "Ada", lambda character: _FixedTakeBackend(character, "Ben"))
        return game

    serial = build("serial")
    partitioned = build("partitioned")

    calls = []
    original = partitioned._apply_turn_partitioned

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    partitioned._apply_turn_partitioned = counted
    serial_result = serial.step()
    partitioned_result = partitioned.step()

    assert calls == [], "a contest must not enter the partitioned commit path"
    assert serial_result["status"] == partitioned_result["status"] == "advanced"
    assert serial.last_results == partitioned.last_results
    assert serial.last_errors == partitioned.last_errors
    assert semantic_world_state(serial.world) == semantic_world_state(partitioned.world)
    assert partitioned.last_shard_plan is None


def test_a_forced_cross_shard_unit_still_produces_the_same_results():
    """A unit spanning two spatial shards moves to the coordinator and applies once."""
    def build(executor):
        game = _game(executor=executor)
        for actor in game.characters:
            _set_backend(game, actor, _FixedRestBackend)
        original = game._unit_resources

        def forced(graph, actor, response=None):
            resources, global_write = original(graph, actor, response)
            if actor == "Ada":
                resources = set(resources) | {Resource("cell", (100, 100))}
            return resources, global_write

        game._unit_resources = forced
        return game

    serial = build("serial")
    partitioned = build("partitioned")
    serial_trace = _run(serial, turns=2)
    partitioned_trace = _run(partitioned, turns=2)

    assert first_divergence(serial_trace, partitioned_trace) is None
    assert semantic_world_state(serial.world) == semantic_world_state(partitioned.world)
    assert serial.last_results == partitioned.last_results
    assert serial.last_errors == partitioned.last_errors
    assert "Ada" in partitioned.last_shard_plan.cross_shard
    assert "Ada" in partitioned.last_shard_plan.coordinator_units


def test_partitioned_executor_returns_only_the_completed_actor_map():
    game = _game(executor="partitioned")
    game.step()
    executor = PartitionedExecutor(workers=2)
    units = executor.units(game, game.last_order, game.last_responses)
    plan = executor.plan(units, game.world)
    completed = executor.commit(game, game.last_order, game.last_responses, plan=plan)

    assert set(completed) == set(game.last_order)
    for actor, entry in completed.items():
        assert entry[0] == actor
        assert len(entry) == 3


def test_partitioned_shards_actually_overlap_independent_units():
    """Far-apart resting units must run in different shard workers."""
    def build(executor):
        game = _game(executor=executor)
        for actor in game.characters:
            _set_backend(game, actor, _FixedRestBackend)
        # One actor per distant cell block, so each unit owns its own shard.
        game.world._actor_positions["Ada"] = (1, 1)
        game.world._actor_positions["Ben"] = (100, 100)
        game.world._actor_positions["Cy"] = (200, 200)
        counter = {"active": 0, "max": 0}
        lock = threading.Lock()
        original = game._apply_response_contained

        def wrapped(actor, response):
            with lock:
                counter["active"] += 1
                counter["max"] = max(counter["max"], counter["active"])
            try:
                time.sleep(0.05)
                return original(actor, response)
            finally:
                with lock:
                    counter["active"] -= 1

        game._apply_response_contained = wrapped
        return game, counter

    serial, serial_counter = build("serial")
    partitioned, partitioned_counter = build("partitioned")
    assert serial.step()["status"] == "advanced"
    assert partitioned.step()["status"] == "advanced"

    assert serial_counter["max"] == 1
    assert partitioned_counter["max"] > 1, partitioned_counter
    assert serial.last_results == partitioned.last_results
    assert serial.last_errors == partitioned.last_errors
    assert len(partitioned.last_shard_plan.by_shard) >= 3


# ---------------------------------------------------------------- benchmark builder


def test_benchmark_builder_is_importable_without_running_the_benchmark():
    from tools.benchmark_tick_graph import (DEFAULT_SEED, build_scenario,
                                            markdown_table)

    scenario = build_scenario(12)
    assert len(scenario["actors"]) == 12
    assert scenario["map"]["grid"] == [["floor"] * 4 for _ in range(4)]
    assert scenario["physical_subsystems"]["metabolism"] is False
    assert DEFAULT_SEED == 305000
    assert "| size | executor |" in markdown_table({"results": []})


def test_units_sharing_a_resource_are_merged_into_one_component():
    """TG07 follow-up: shared resources cross shard boundaries, not just units."""
    world = _FakeWorld({"Ada": (1, 1), "Ben": (1, 2)})
    shared = Resource("cell", (1, 1))
    plan = partition_units({
        "Ada": {Resource("actor", "Ada"), shared},
        "Ben": {Resource("actor", "Ben"), shared},
    }, world, ShardMap(cell_size=8))

    assert plan.shard_of("Ada") == plan.shard_of("Ben")
    assert plan.coordinator_units == ()
    assert any({"Ada", "Ben"} <= set(actors) for actors in plan.by_shard.values())


def test_partitioned_matches_serial_after_same_cell_movement():
    """Regression: two same-cell movers must keep the turn order in a shard.

    Seed 305002 diverged at turn 8 when the shard commit sorted members
    lexicographically instead of by ``turn_order``: Cask Kindle and Erasmus
    Codling wore the same step cell in the opposite order.
    """
    seed = 305002
    games = {}
    for executor in ("serial", "partitioned"):
        games[executor] = create_game(
            scenario="town100", seed=seed, default_backend="simple",
            autonomous=True, llm_log=False, executor=executor,
            affordance_mode="menu")
    for _ in range(8):
        for executor in ("serial", "partitioned"):
            assert games[executor].step()["status"] == "advanced"
    assert semantic_world_state(games["serial"].world) == \
        semantic_world_state(games["partitioned"].world)


def test_semantic_state_ignores_event_allocation_ids():
    """Event:1/Event:2 order is internal; the semantic state compares content."""
    from bigville.api import create_world

    def build(reverse):
        world = create_world(scenario=SMALL_SCENARIO, seed=SEED)
        events = [("sleep", "Ada"), ("wake", "Ben")]
        if reverse:
            events.reverse()
        for kind, subject in events:
            world.create_event(kind, subject=subject, detail=f"{subject} {kind}")
        return semantic_world_state(world)

    assert build(False) == build(True)
