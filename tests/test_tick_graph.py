"""TG04: effect intents and the tick graph.

The graph is pure metadata.  The engine still applies responses in
``turn_order``; these tests prove the declared conflicts are the ones the
current serial rules depend on, and that enabling or disabling graph building
cannot be observed in a turn trace or a world checkpoint.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from bigville.api import create_game
from bigville.backends import ActorResponse, ProposedAction
from bigville.tick_trace import TurnTrace
from worlds.tick_graph import (Operation, Resource, TickGraph, TickGraphCycle,
                               build_tick_graph)

TURNS = 3

SMALL_SCENARIO = {
    "id": "tg04_tick_graph_room",
    "name": "TG04 tick graph room",
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
    """The read-only slice ``build_tick_graph`` needs, with no engine import."""

    def __init__(self, positions, objects=(), turn=7):
        self._turn = turn
        self._actors = {name: index for index, name in enumerate(positions)}
        self._physical_objects = {name: index for index, name in enumerate(objects)}
        self._actor_targets = {}
        self._positions = dict(positions)

    def actor_position(self, actor):
        return self._positions.get(actor)

    def _physical_location_cell(self, name):
        return self._positions.get(name)


def _response(action=None, params=None, *, utterances=(), memory=()):
    proposal = None if action is None else ProposedAction(action, dict(params or {}))
    return ActorResponse(major_action=proposal, utterances=list(utterances),
                         memory_updates=list(memory))


# ------------------------------------------------------------------ resource model


def test_resource_is_hashable_frozen_and_has_a_stable_string_form():
    left = Resource("cell", (1, 2))
    right = Resource("cell", (1, 2))
    assert left == right and hash(left) == hash(right)
    assert str(left) == "cell:(1, 2)"
    assert str(Resource("actor", "Ada")) == "actor:Ada"
    assert left.to_dict() == {"kind": "cell", "key": [1, 2]}
    with pytest.raises(Exception):
        left.kind = "changed"


def test_operation_is_read_only_and_serialises_for_diagnostics():
    operation = Operation("Ada", "Ada", "rest", (Resource("actor", "Ada"),),
                          (Resource("actor", "Ada"),), (0, "Ada", "Ada"),
                          {"params": {"kind": "x"}})
    assert operation.to_dict()["reads"] == [{"kind": "actor", "key": "Ada"}]
    with pytest.raises(TypeError):
        operation.payload["params"] = {}


# ------------------------------------------------------------------ conflicts


def test_two_moves_into_the_same_cell_conflict():
    world = _FakeWorld({"Ada": (0, 0), "Ben": (1, 1)})
    responses = {"Ada": _response("move", {"destination": (3, 3)}),
                 "Ben": _response("move", {"destination": (3, 3)})}

    graph = build_tick_graph(["Ada", "Ben"], responses, world)

    assert graph.conflicts("Ada") == ("Ben",)
    assert graph.predecessors("Ben") == ("Ada",)
    assert graph.successors("Ada") == ("Ben",)
    assert graph.operations[0].writes == (
        Resource("actor", "Ada"), Resource("cell", (0, 0)), Resource("cell", (3, 3)))
    assert graph.operations[0].reads == graph.operations[0].writes


def test_two_transfers_of_the_same_stock_conflict():
    world = _FakeWorld({"Ada": (0, 0), "Ben": (0, 0), "Cy": (1, 1), "Dee": (1, 1)})
    responses = {
        "Ada": _response("transfer", {"recipient": "Ben", "kind": "grain", "amount": 1}),
        "Cy": _response("transfer", {"recipient": "Dee", "kind": "grain", "amount": 1}),
    }

    graph = build_tick_graph(["Ada", "Cy"], responses, world)

    assert graph.conflicts("Ada") == ("Cy",)
    assert Resource("stock", "grain") in graph.operation("Ada").writes


def test_a_take_conflicts_with_the_targets_other_action():
    world = _FakeWorld({"Ada": (1, 1), "Ben": (1, 1)})
    responses = {"Ada": _response("take", {"source": "Ben", "kind": "coin", "amount": 2}),
                 "Ben": _response("rest", {"amount": 1})}

    graph = build_tick_graph(["Ada", "Ben"], responses, world)

    assert graph.conflicts("Ben") == ("Ada",)
    take = graph.operation("Ada")
    assert Resource("actor", "Ben") in take.reads
    assert Resource("actor", "Ben") in take.writes
    assert Resource("cell", (1, 1)) in take.writes
    assert Resource("relationship", ("Ada", "Ben")) in take.writes
    assert Resource("world", "contest") in take.writes


def test_a_malformed_contest_still_names_its_target():
    world = _FakeWorld({"Ada": (1, 1)})
    responses = {"Ada": _response("take", {"source": "Nobody", "kind": "coin"})}

    graph = build_tick_graph(["Ada"], responses, world)
    take = graph.operation("Ada")

    assert Resource("actor", "Nobody") in take.reads
    assert Resource("actor", "Nobody") in take.writes


def test_two_independent_rests_do_not_conflict():
    world = _FakeWorld({"Ada": (0, 0), "Ben": (4, 4)})
    responses = {"Ada": _response("rest", {"amount": 1}),
                 "Ben": _response("sleep", {})}

    graph = build_tick_graph(["Ada", "Ben"], responses, world)

    assert graph.conflicts("Ada") == ()
    assert graph.edges == ()


def test_unknown_verbs_write_world_global_and_serialise():
    world = _FakeWorld({"Ada": (0, 0), "Ben": (4, 4)})
    responses = {"Ada": _response("frobnicate", {"x": 1}),
                 "Ben": _response("mystify", {})}

    graph = build_tick_graph(["Ada", "Ben"], responses, world)

    assert Resource("world", "global") in graph.operation("Ada").writes
    assert Resource("world", "global") in graph.operation("Ben").writes
    assert graph.conflicts("Ada") == ("Ben",)


# ------------------------------------------------------------------ ordering


def test_graph_order_equals_the_supplied_turn_order():
    world = _FakeWorld({"Ada": (0, 0), "Ben": (4, 4), "Cy": (2, 2)})
    responses = {"Ada": _response("rest"), "Ben": _response("rest"),
                 "Cy": _response(None, utterances=[{"text": "hello"}])}

    graph = build_tick_graph(["Ben", "Cy", "Ada"], responses, world)

    assert graph.topological_order() == ("Ben", "Cy", "Ada")
    assert graph.to_dict()["order"] == ["Ben", "Cy", "Ada"]
    # Speech and memory are operations too, but not actor-order entries.
    full = graph.topological_order(include_auxiliary=True)
    assert tuple(name for name in full if "#" not in name) == ("Ben", "Cy", "Ada")


def test_cycle_detection_raises():
    world = _FakeWorld({"Ada": (0, 0), "Ben": (4, 4)})
    responses = {"Ada": _response("rest"), "Ben": _response("rest")}
    graph = build_tick_graph(["Ada", "Ben"], responses, world)

    graph.add_edge("Ada", "Ben")
    graph.add_edge("Ben", "Ada")

    with pytest.raises(TickGraphCycle):
        graph.topological_order()


def test_joint_members_form_one_compound_operation_but_keep_their_speech():
    task = {"task": "carry", "object": "crate", "toward": [1, 0]}
    world = _FakeWorld({"Ada": (1, 1), "Ben": (1, 1), "crate": (2, 1)},
                       objects=("crate",))
    responses = {
        "Ada": _response("joint", {"joint": dict(task)},
                         utterances=[{"text": "heave"}]),
        "Ben": _response("joint", {"joint": dict(task)}),
    }

    graph = build_tick_graph(["Ada", "Ben"], responses, world)

    joint = [op for op in graph.operations if op.kind == "joint"]
    assert len(joint) == 1
    assert joint[0].payload["members"] == ["Ada", "Ben"]
    assert graph.operation("Ada#speak").kind == "speak"
    assert {op.op_id for op in graph.operations if op.kind == "joint"} == {"joint:carry|crate|[1, 0]"}
    assert Resource("item", "crate") in joint[0].writes
    assert Resource("cell", (2, 1)) in joint[0].reads
    assert Resource("cell", (3, 1)) in joint[0].writes


def test_joint_crew_reads_and_writes_the_workers_job():
    task = {"task": "crew", "worker": "Sawyer"}
    world = _FakeWorld({"Helper": (1, 1), "Sawyer": (1, 1)})
    responses = {"Helper": _response("joint", {"joint": dict(task)})}

    graph = build_tick_graph(["Helper"], responses, world)
    joint = graph.operation("joint:crew|Sawyer|None")

    assert Resource("actor", "Sawyer") in joint.reads
    assert Resource("job", "Sawyer") in joint.writes
    assert Resource("world", "events") in joint.writes


# ------------------------------------------------------------------ engine integration


def _town():
    return create_game(scenario="town100", seed=305000, default_backend="simple",
                       autonomous=True, llm_log=False)


def _small():
    return create_game(scenario=SMALL_SCENARIO, seed=305000, default_backend="simple",
                       autonomous=True, llm_log=False)


def _check_engine_run(game, turns=TURNS, *, expect_graph=True):
    trace = TurnTrace()
    checkpoint_digests = []
    for _ in range(turns):
        result = game.step()
        assert result["status"] == "advanced"
        if expect_graph:
            assert game.last_tick_graph is not None
            assert game.last_tick_graph.topological_order() == tuple(game.last_order)
        else:
            assert game.last_tick_graph is None
        trace.add(game)
        checkpoint_digests.append(game.world.eng.to_checkpoint_dict())
    return trace, checkpoint_digests


def _run_with_flag(factory, enabled, turns=TURNS):
    game = factory()
    game.tick_graph_enabled = enabled
    trace, checkpoints = _check_engine_run(game, turns, expect_graph=enabled)
    return game, trace, checkpoints


@pytest.mark.parametrize("factory", [_town, _small], ids=["town100", "small"])
def test_three_turns_build_a_graph_in_turn_order_and_the_flag_is_unobservable(factory):
    enabled_game, enabled_trace, enabled_checkpoints = _run_with_flag(factory, True)
    disabled_game, disabled_trace, disabled_checkpoints = _run_with_flag(factory, False)

    assert enabled_game.last_tick_graph is not None
    assert disabled_game.last_tick_graph is None
    assert enabled_trace.records == disabled_trace.records
    assert enabled_trace.hexdigest() == disabled_trace.hexdigest()
    assert enabled_checkpoints == disabled_checkpoints
    assert enabled_game.last_order == disabled_game.last_order
    assert enabled_game.last_results == disabled_game.last_results
    assert enabled_game.last_errors == disabled_game.last_errors


def test_two_moves_that_share_a_step_cell_conflict():
    """A walk wears its next step cell, not only its final destination."""
    class _StepWorld(_FakeWorld):
        def _movement_step(self, current, destination):
            return (5, 5)

    world = _StepWorld({"Ada": (0, 0), "Ben": (1, 1)})
    responses = {
        "Ada": _response("move", {"destination": (10, 10)}),
        "Ben": _response("move", {"destination": (20, 20)}),
    }

    graph = build_tick_graph(["Ada", "Ben"], responses, world)

    assert Resource("cell", (5, 5)) in graph.operation("Ada").writes
    assert Resource("cell", (5, 5)) in graph.operation("Ben").writes
    assert graph.conflicts("Ada") == ("Ben",)
