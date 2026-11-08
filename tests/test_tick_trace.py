"""TG01: the tick-graph equivalence oracle and provenance trace.

The oracle is deliberately exercised two ways: on the standard ``town100``
scenario (seed 305000) for a realistic four-turn run, and on a three-resident
room for the cheap single-change probes. Tracing must only observe.
"""
from __future__ import annotations

from bigville.api import create_game
from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import CheapBackend
from bigville.runtime import NodeRef
from bigville.tick_trace import (TurnTrace, canonical, canonical_json, first_divergence,
                                 step_trace)

TURNS = 4

SMALL_SCENARIO = {
    "id": "tg01_trace_room",
    "name": "TG01 trace room",
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


def _town():
    # TG01 oracle: pin the historical menu path (the default became lazy later).
    return create_game(scenario="town100", seed=305000, default_backend="simple",
                       autonomous=True, llm_log=False, affordance_mode="menu")


def _small():
    return create_game(scenario=SMALL_SCENARIO, seed=305000, default_backend="simple",
                       autonomous=True, llm_log=False, affordance_mode="menu")


def _run(game, turns=TURNS):
    trace = TurnTrace()
    for _ in range(turns):
        assert game.step()["status"] == "advanced"
        trace.add(game)
    return trace


class _FixedRestBackend(CheapBackend):
    """A simple resident that always proposes one fixed action."""

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction("rest", {"kind": "tg01_probe"}))


def test_identical_town_runs_produce_identical_trace_digests_over_four_turns():
    first, second = _town(), _town()
    left, right = _run(first, TURNS), _run(second, TURNS)

    assert left.turns == right.turns == TURNS
    assert left.records == right.records
    assert left.digest == left.hexdigest() == right.hexdigest()

    # Continuation requests are part of the record, not just the world digest.
    assert any(record["continuations"] for record in left.records)
    expected = {str(actor): canonical(active.request.to_dict())
                for actor, active in first._continuations.items()}
    assert left.records[-1]["continuations"] == expected


def test_changing_one_world_fact_changes_the_digest_and_is_reported():
    game = _small()
    game.step()
    before = step_trace(game)

    node = game.world._actors["Ada"]
    hunger = float(game.world.eng.node(node)["attrs"].get("hunger", 0.0))
    game.world.eng.set_attr(node, "hunger", hunger + 1.0)
    after = step_trace(game)

    assert before["responses"] == after["responses"]
    assert before["world_sha256"] != after["world_sha256"]

    left, right = TurnTrace(), TurnTrace()
    left.add_record(before)
    right.add_record(after)
    assert left.hexdigest() != right.hexdigest()
    assert first_divergence(left, right) == (before["turn"], "world_sha256")


def test_changing_one_proposal_changes_the_digest_and_is_reported():
    plain, altered = _small(), _small()
    altered.set_backend("Ada", _FixedRestBackend(altered.characters["Ada"]))

    left, right = _run(plain, 1), _run(altered, 1)

    assert left.records[0]["responses"]["Ada"]["action"] is None
    assert right.records[0]["responses"]["Ada"]["action"] == "rest"
    assert left.hexdigest() != right.hexdigest()
    assert first_divergence(left, right) == (1, "responses.Ada.action")


def test_first_divergence_reports_the_first_turn_and_nested_field():
    def record(turn, destination):
        return {"turn": turn,
                "responses": {"Ben": {"action": "move",
                                      "params": {"destination": destination}}}}

    left, right = TurnTrace(), TurnTrace()
    for turn in (1, 2, 3):
        left.add_record(record(turn, ["home", turn]))
        right.add_record(record(turn, ["home", turn if turn < 3 else 99]))

    assert first_divergence(left, right) == (3, "responses.Ben.params.destination[1]")
    assert first_divergence(left, left) is None
    assert first_divergence(left.records, left.records[:2]) == (3, "<missing>")


def test_canonical_encoder_handles_tuples_sets_and_node_refs():
    value = {"tuple": (1, 2), "set": {3, 1, 2}, "frozenset": frozenset({"b", "a"}),
             "ref": NodeRef(7)}
    encoded = canonical(value)

    assert encoded["tuple"] == {"$tuple": [1, 2]}
    assert encoded["set"] == {"$set": [1, 2, 3]}
    assert encoded["frozenset"] == {"$frozenset": ["a", "b"]}
    assert encoded["ref"] == {"$node_ref": 7}
    # Set iteration order cannot leak into the digest.
    reordered = {"ref": NodeRef(7), "frozenset": frozenset({"a", "b"}),
                 "set": {1, 2, 3}, "tuple": (1, 2)}
    assert canonical_json(value) == canonical_json(reordered)


def test_tracing_wraps_step_without_changing_normal_game_behaviour():
    plain, traced = _town(), _town()
    trace = TurnTrace()

    for _ in range(2):
        expected = plain.step()
        actual = traced.step()
        trace.add(traced)

        assert actual == expected
        assert traced.last_order == plain.last_order
        assert traced.last_results == plain.last_results
        assert traced.last_errors == plain.last_errors
        assert traced._continuations.keys() == plain._continuations.keys()
        for actor in plain._continuations:
            assert (traced._continuations[actor].request.to_dict()
                    == plain._continuations[actor].request.to_dict())
        assert (traced.world.eng.to_checkpoint_dict()
                == plain.world.eng.to_checkpoint_dict())

    assert trace.turns == 2
    assert [record["turn"] for record in trace.records] == [1, 2]
