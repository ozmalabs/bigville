"""TG05: opt-in threaded commit of declared-independent tick-graph units.

The default executor stays serial and keeps the historical loop.  The
threaded executor may mint graph nodes in a different order, so equivalence is
proved on the semantic oracle (``step_semantic_trace``), never on node ids or
on the raw checkpoint digest.  These tests also force real overlap with a
small sleep and prove that contests, joint acts and shared attempt state keep
their serial behaviour.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from bigville.api import create_game, create_world
from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import CheapBackend
from bigville.game import BigvilleGame
from bigville.runtime import BigvilleGraph
from bigville.tick_trace import (TurnTrace, first_divergence, semantic_world_state,
                                 step_semantic_trace)
from worlds.tick_graph import Resource

TURNS = 4
SEED = 305000

SMALL_SCENARIO = {
    "id": "tg05_executor_room",
    "name": "TG05 executor room",
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


def _game(scenario=SMALL_SCENARIO, *, executor="serial", backend="simple"):
    game = create_game(scenario=scenario, seed=SEED, default_backend=backend,
                       autonomous=True, llm_log=False)
    game.executor = executor
    return game


def _set_backend(game, actor, factory):
    game.set_backend(actor, factory(game.characters[actor]))


def _run(game, turns=TURNS):
    trace = TurnTrace()
    for _ in range(turns):
        result = game.step()
        assert result["status"] == "advanced"
        trace.add_record(step_semantic_trace(game))
    return trace


class _FixedRestBackend(CheapBackend):
    """An independent resident that always rests and says nothing."""

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction("rest", {"kind": "tg05_rest"}))


class _FixedTakeBackend(CheapBackend):
    def __init__(self, character, target):
        super().__init__(character)
        self.target = target

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction(
            "take", {"source": self.target, "kind": "coin", "amount": 1}))


class _FixedJointBackend(CheapBackend):
    def __init__(self, character, task):
        super().__init__(character)
        self.task = dict(task)

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction("joint", {"joint": dict(self.task)}))


# ---------------------------------------------------------------- semantic equivalence


@pytest.mark.parametrize("scenario", ["town100", SMALL_SCENARIO], ids=["town100", "small"])
def test_serial_and_threaded_semantic_traces_match_over_four_turns(scenario):
    serial_a = _game(scenario, executor="serial")
    serial_b = _game(scenario, executor="serial")
    threaded = _game(scenario, executor="threaded")

    trace_a = _run(serial_a)
    trace_b = _run(serial_b)
    trace_threaded = _run(threaded)

    # The serial path is still deterministic and keeps the TG04 oracle behaviour.
    assert trace_a.records == trace_b.records
    assert trace_a.digest == trace_b.digest

    # Threaded equivalence is semantic: node ids and log order may differ.
    assert first_divergence(trace_a, trace_threaded) is None, (
        first_divergence(trace_a, trace_threaded))
    assert trace_a.digest == trace_threaded.digest
    assert semantic_world_state(serial_a.world) == semantic_world_state(threaded.world)
    assert serial_a.last_order == threaded.last_order
    assert serial_a.last_results == threaded.last_results
    assert serial_a.last_errors == threaded.last_errors


def test_threaded_and_serial_have_the_same_semantic_state_without_speech():
    """Many independent rests exercise actual concurrent units, not a serial fallback."""
    def build(executor):
        game = _game(executor=executor)
        for actor in game.characters:
            _set_backend(game, actor, _FixedRestBackend)
        return game

    serial, threaded = build("serial"), build("threaded")
    trace = _run(serial, turns=2)
    threaded_trace = _run(threaded, turns=2)

    assert first_divergence(trace, threaded_trace) is None
    assert semantic_world_state(serial.world) == semantic_world_state(threaded.world)


# ---------------------------------------------------------------- actual overlap


def _instrument_contained(game, counter):
    original = game._apply_response_contained
    lock = threading.Lock()

    def wrapped(actor, response):
        with lock:
            counter["active"] += 1
            counter["max"] = max(counter["max"], counter["active"])
        try:
            # Small, deliberately-visible overlap window.  The world work is
            # not inside this sleep, so the graph lock never hides it.
            time.sleep(0.05)
            return original(actor, response)
        finally:
            with lock:
                counter["active"] -= 1

    game._apply_response_contained = wrapped


def test_threaded_commit_actually_overlaps_independent_units():
    def build(executor):
        game = _game(executor=executor)
        for actor in game.characters:
            _set_backend(game, actor, _FixedRestBackend)
        counter = {"active": 0, "max": 0}
        _instrument_contained(game, counter)
        return game, counter

    serial, serial_counter = build("serial")
    threaded, threaded_counter = build("threaded")

    assert serial.step()["status"] == "advanced"
    assert threaded.step()["status"] == "advanced"

    assert serial_counter["max"] == 1
    assert threaded_counter["max"] > 1, threaded_counter
    assert serial.last_results == threaded.last_results
    assert serial.last_errors == threaded.last_errors


# ---------------------------------------------------------------- contests, joints, fallback


def test_contest_turn_falls_back_to_the_serial_loop():
    def build(executor):
        game = _game(executor=executor)
        _set_backend(game, "Ada", lambda character: _FixedTakeBackend(character, "Ben"))
        return game

    serial = build("serial")
    threaded = build("threaded")

    calls = []
    original = threaded._apply_turn_threaded

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    threaded._apply_turn_threaded = counted

    serial_result = serial.step()
    threaded_result = threaded.step()

    assert calls == [], "a contest must not enter the threaded commit path"
    assert serial_result["status"] == threaded_result["status"]
    assert serial.last_results == threaded.last_results
    assert serial.last_errors == threaded.last_errors
    assert semantic_world_state(serial.world) == semantic_world_state(threaded.world)


def test_joint_turn_is_resolved_before_a_threaded_commit():
    task = {"task": "carry", "object": "crate", "toward": [1, 0]}

    def build(executor):
        game = _game(executor=executor)
        _set_backend(game, "Ada", lambda character: _FixedJointBackend(character, task))
        _set_backend(game, "Ben", lambda character: _FixedJointBackend(character, task))
        return game

    serial = build("serial")
    threaded = build("threaded")

    calls = []
    original = threaded._apply_turn_threaded

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    threaded._apply_turn_threaded = counted

    serial_result = serial.step()
    threaded_result = threaded.step()

    assert calls == [1]
    assert serial_result["status"] == threaded_result["status"] == "advanced"
    assert serial.last_results == threaded.last_results
    assert serial.last_errors == threaded.last_errors
    assert semantic_world_state(serial.world) == semantic_world_state(threaded.world)


def test_threaded_mode_falls_back_when_the_tick_graph_is_disabled():
    game = _game(executor="threaded")
    game.tick_graph_enabled = False
    calls = []
    game._apply_turn_threaded = lambda *args, **kwargs: calls.append(1)
    game.executor_workers = 2

    assert game.step()["status"] == "advanced"
    assert calls == []
    assert game.last_tick_graph is None


def test_executor_options_are_validated():
    world = create_world(scenario=SMALL_SCENARIO, seed=SEED)
    with pytest.raises(ValueError):
        BigvilleGame(world, executor="parallel")
    with pytest.raises(ValueError):
        BigvilleGame(world, executor_workers=0)

    game = _game()
    with pytest.raises(ValueError):
        game.executor = "parallel"
    with pytest.raises(ValueError):
        game.executor_workers = -1


# ---------------------------------------------------------------- locks and per-attempt state


def test_graph_lock_makes_concurrent_add_node_unique_and_consistent():
    graph = BigvilleGraph()
    threads, per_thread = 12, 200

    def add_many(_index):
        return [int(graph.add_node("Probe", {"n": _index})) for _index in range(per_thread)]

    with ThreadPoolExecutor(max_workers=threads) as pool:
        batches = list(pool.map(add_many, range(threads)))

    ids = [node for batch in batches for node in batch]
    assert len(ids) == threads * per_thread
    assert len(set(ids)) == len(ids)
    assert min(ids) == 1
    assert max(ids) == threads * per_thread
    assert graph._next_id == threads * per_thread + 1


def test_attempt_state_is_thread_local_and_does_not_leak_between_actors():
    world = create_world(scenario=SMALL_SCENARIO, seed=SEED)
    barrier = threading.Barrier(2, timeout=5)
    seen = {}

    def make_run(actor, code):
        def run():
            world._refusal_code = code
            world._major_dispatch = True
            barrier.wait()
            seen[actor] = (world._refusal_code, world._major_dispatch, world._outcome_open)
            return True
        return run

    with ThreadPoolExecutor(max_workers=2) as pool:
        ada = pool.submit(world._attempt, "Ada", "rest", make_run("Ada", "ada_refusal"))
        ben = pool.submit(world._attempt, "Ben", "rest", make_run("Ben", "ben_refusal"))
        assert ada.result() is True
        assert ben.result() is True

    # Each thread read its own refusal code and dispatch guard while both
    # attempts were open.  A shared instance flag would show the last writer.
    assert seen["Ada"][0] == "ada_refusal"
    assert seen["Ben"][0] == "ben_refusal"
    assert seen["Ada"][1] and seen["Ben"][1]
    assert seen["Ada"][2] and seen["Ben"][2]
    # Both attempts published their own outcome, so neither treated the other
    # thread's open attempt as its own nested attempt.
    assert world.last_outcome("Ada")["applied"] is True
    assert world.last_outcome("Ben")["applied"] is True

    # The main thread starts with fresh per-attempt defaults.
    assert world._outcome_open is False
    assert world._refusal_code is None
    assert world._major_dispatch is False


def test_nearby_object_witnesses_are_a_conflict_resource():
    """Two units near one observer must never race their witness records."""
    scenario = dict(SMALL_SCENARIO)
    scenario["physical_objects"] = [
        {"id": "crate", "name": "crate", "kind": "crate", "location": "world"},
    ]
    game = _game(scenario, executor="threaded")
    game.world._actor_positions["Ben"] = (2, 1)   # adjacent to Ada at (1, 1)
    for actor in game.characters:
        _set_backend(game, actor, _FixedRestBackend)

    assert game.step()["status"] == "advanced"
    resources, global_write = game._unit_resources(
        game.last_tick_graph, "Ada", game.last_responses["Ada"])

    assert not global_write
    assert Resource("witness", "Ada") in resources
    assert Resource("witness", "Ben") in resources
