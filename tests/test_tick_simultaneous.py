"""TG06: opt-in simultaneous turn semantics and pure claim resolution.

``turn_semantics="sequential"`` remains the default and keeps the historical
first-committer-wins behaviour.  ``"simultaneous"`` resolves contested
exclusive item claims from the frozen responses before either commit path
applies anything, then suppresses every loser.

One engine detail shapes these tests: a scenario-authored physical object is
moved by the ``move_object`` verb (destination = the resident).  A raw
``pick_up`` major action only reaches ``World.pick_up`` for ``ToolItem`` nodes
and is not routed for scenario physical objects by ``enact_plan``.  The claim
layer itself is action-agnostic and a dedicated test proves ``pick_up``
proposals mint the same ``Resource("item", ...)`` claims.
"""
from __future__ import annotations

import pytest

from bigville.api import create_game
from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import CheapBackend
from bigville.game import BigvilleGame
from bigville.tick_trace import TurnTrace, semantic_world_state, step_trace
from worlds.tick_graph import Claim, Resource, resolve_claims

SEED = 305000
CRATE = "crate"

BASE_SCENARIO = {
    "id": "tg06_simultaneous_room",
    "name": "TG06 simultaneous room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [2, 2]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [],
    "laws": [],
    "policies": [],
    "charters": [],
}


def _scenario(*objects):
    scenario = dict(BASE_SCENARIO)
    scenario["physical_objects"] = list(objects)
    return scenario


class _PickUpCrateBackend(CheapBackend):
    """Always try to take one scenario object into the resident's hands.

    ``move_object`` with the actor as destination is this engine's physical
    pick-up for scenario objects; see the module docstring.
    """

    def __init__(self, character, object_id=CRATE):
        super().__init__(character)
        self.object_id = object_id

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction(
            "move_object",
            {"object_id": self.object_id, "destination": self.character.name}))


class _SpeakingPickUpBackend(_PickUpCrateBackend):
    def decide(self, context):
        response = super().decide(context)
        response.utterances = [{"target": None,
                                "text": f"{self.character.name} reaches for the crate"}]
        response.memory_updates = [{"content": f"{self.character.name} tried the crate",
                                    "kind": "episodic"}]
        return response


def _game(objects, *, semantics="sequential", executor="serial", workers=4,
          priority=None):
    game = create_game(
        scenario=_scenario(*objects), seed=SEED, default_backend="simple",
        autonomous=True, llm_log=False, turn_semantics=semantics,
        executor=executor, executor_workers=workers,
        simultaneous_priority=priority)
    return game


def _use(game, factory, *args):
    for actor in list(game.characters):
        game.set_backend(actor, factory(game.characters[actor], *args))


def _pre_step_order(game):
    """The order the next step will use (the graph seed depends only on the turn)."""
    return game.turn_order(list(game.characters), 1)


def _object_location(game, object_id=CRATE):
    return next(item for item in game.world.physical_objects()
                if item["id"] == object_id)["location"]


def _utterance_texts(world):
    return [world.eng.node(node)["attrs"].get("content", "")
            for node in world.utterances_from(0)]


# ------------------------------------------------------------------ pure claim resolution


def test_resolve_claims_returns_the_only_claimant_as_winner():
    resource = Resource("item", CRATE)
    claim = Claim(resource, "Ada", 0, 1.0)

    winners, losers = resolve_claims([claim])

    assert winners == {resource: claim}
    assert losers == {}


def test_resolve_claims_higher_priority_wins_regardless_of_input_order():
    resource = Resource("item", CRATE)
    low = Claim(resource, "Ada", 0, 1.0)
    high = Claim(resource, "Ben", 1, 9.0)

    first, first_losers = resolve_claims([low, high])
    second, second_losers = resolve_claims([high, low])

    assert first[resource].actor == "Ben"
    assert second[resource].actor == "Ben"
    assert first_losers[resource] == (low,)
    assert second_losers[resource] == (low,)


def test_resolve_claims_ties_use_earlier_index_then_actor_id_deterministically():
    resource = Resource("item", CRATE)
    earlier = Claim(resource, "Cy", 1, 2.0)
    later = Claim(resource, "Ada", 3, 2.0)

    winners, losers = resolve_claims([later, earlier])
    assert winners[resource] is earlier
    assert losers[resource] == (later,)

    # Same priority and index can only happen outside a real turn; the actor id
    # still makes the result independent of input order.
    ada = Claim(resource, "Ada", 0, 5.0)
    ben = Claim(resource, "Ben", 0, 5.0)
    winners_a, losers_a = resolve_claims([ada, ben])
    winners_b, losers_b = resolve_claims([ben, ada])
    assert winners_a[resource].actor == winners_b[resource].actor == "Ben"
    assert losers_a[resource][0].actor == losers_b[resource][0].actor == "Ada"


def test_resolve_claims_groups_by_resource_and_reports_each_contest():
    crate_a = Resource("item", "crate_a")
    crate_b = Resource("item", "crate_b")
    claims = [
        Claim(crate_a, "Ada", 0, 1.0),
        Claim(crate_a, "Ben", 1, 2.0),
        Claim(crate_b, "Cy", 2, 1.0),
        Claim(crate_b, "Dee", 3, 3.0),
    ]

    winners, losers = resolve_claims(claims)

    assert {resource: claim.actor for resource, claim in winners.items()} == {
        crate_a: "Ben", crate_b: "Dee"}
    assert {resource: tuple(claim.actor for claim in defeated)
            for resource, defeated in losers.items()} == {
        crate_a: ("Ada",), crate_b: ("Cy",)}


def test_pick_up_proposals_mint_the_same_item_claims_for_contest_detection():
    game = _game([{"id": CRATE, "kind": "crate", "location": "world"}])
    order = _pre_step_order(game)
    responses = {actor: ActorResponse(major_action=ProposedAction(
        "pick_up", {"item": CRATE})) for actor in order}

    claims = game._item_claims(order, responses)

    assert {claim.resource for claim in claims} == {Resource("item", CRATE)}
    assert {claim.actor for claim in claims} == set(order)


# ------------------------------------------------------------------ sequential baseline


def test_sequential_first_in_turn_order_takes_the_crate_and_the_other_is_refused():
    game = _game([{"id": CRATE, "kind": "crate", "location": "world"}],
                 semantics="sequential", executor="serial")
    _use(game, _PickUpCrateBackend)
    order = _pre_step_order(game)

    result = game.step()

    assert result["status"] == "advanced"
    assert game.last_order == order
    winner, loser = order[0], order[1]
    assert game.last_results == {winner: True, loser: False}
    assert _object_location(game) == winner
    assert loser in game.last_rejections
    assert game.last_rejections[loser]["action"] == "move_object"


# ------------------------------------------------------------------ simultaneous policy


def test_simultaneous_priority_picks_the_later_actor_and_suppresses_the_other():
    game = _game([{"id": CRATE, "kind": "crate", "location": "world"}],
                 semantics="simultaneous", executor="serial")
    _use(game, _PickUpCrateBackend)
    order = _pre_step_order(game)
    later = order[-1]
    game.simultaneous_priority = lambda _game, actor, _index: 1.0 if actor == later else 0.0

    result = game.step()

    assert result["status"] == "advanced"
    assert game.last_results == {order[0]: False, later: True}
    assert _object_location(game) == later
    assert order[0] in game.last_rejections
    assert game.last_rejections[order[0]]["reason"] == "not_possible"
    assert game.last_rejections[order[0]]["action"] == "move_object"


@pytest.mark.parametrize("run", range(3))
def test_simultaneous_result_is_stable_across_runs_executors_and_workers(run):
    order_game = _game([{"id": CRATE, "kind": "crate", "location": "world"}],
                       semantics="simultaneous")
    order = _pre_step_order(order_game)
    later = order[-1]
    priority = lambda _game, actor, _index: 1.0 if actor == later else 0.0

    observed = []
    for executor, workers in (("serial", 1), ("threaded", 1), ("threaded", 3)):
        game = _game([{"id": CRATE, "kind": "crate", "location": "world"}],
                     semantics="simultaneous", executor=executor, workers=workers,
                     priority=priority)
        _use(game, _PickUpCrateBackend)
        assert game.step()["status"] == "advanced"
        observed.append((
            tuple(sorted(game.last_results.items())),
            _object_location(game),
            repr(sorted(game.last_rejections.items())),
            repr(sorted(semantic_world_state(game.world).items())),
        ))

    assert all(entry == observed[0] for entry in observed)
    assert dict(observed[0][0]) == {order[0]: False, later: True}
    assert observed[0][1] == later


def test_simultaneous_claims_use_a_local_graph_when_graph_storage_is_disabled():
    game = _game([{"id": CRATE, "kind": "crate", "location": "world"}],
                 semantics="simultaneous", executor="serial")
    game.tick_graph_enabled = False
    _use(game, _PickUpCrateBackend)
    order = _pre_step_order(game)
    later = order[-1]
    game.simultaneous_priority = lambda _game, actor, _index: 1.0 if actor == later else 0.0

    assert game.step()["status"] == "advanced"

    assert game.last_tick_graph is None
    assert game.last_results == {order[0]: False, later: True}
    assert _object_location(game) == later


def test_two_actors_claiming_different_objects_are_both_applied():
    game = _game([
        {"id": "crate_a", "kind": "crate", "location": "world"},
        {"id": "crate_b", "kind": "crate", "location": "world"},
    ], semantics="simultaneous", executor="serial")
    order = _pre_step_order(game)
    first, second = order[0], order[1]
    game.set_backend(first, _PickUpCrateBackend(game.characters[first], "crate_a"))
    game.set_backend(second, _PickUpCrateBackend(game.characters[second], "crate_b"))

    result = game.step()

    assert result["status"] == "advanced"
    assert game.last_results == {first: True, second: True}
    assert _object_location(game, "crate_a") == first
    assert _object_location(game, "crate_b") == second
    assert game.last_rejections == {}


def test_suppressed_actor_still_speaks_and_records_memory():
    game = _game([{"id": CRATE, "kind": "crate", "location": "world"}],
                 semantics="simultaneous", executor="serial")
    _use(game, _SpeakingPickUpBackend)
    order = _pre_step_order(game)
    later = order[-1]
    game.simultaneous_priority = lambda _game, actor, _index: 1.0 if actor == later else 0.0

    game.step()

    loser = order[0]
    assert game.last_results[loser] is False
    assert game.last_rejections[loser]["reason"] == "not_possible"
    assert f"{loser} reaches for the crate" in _utterance_texts(game.world)
    assert any(memory.content == f"{loser} tried the crate"
               for memory in game.characters[loser].memories)


# ------------------------------------------------------------------ options and sequential purity


def test_turn_semantics_and_priority_are_validated():
    with pytest.raises(ValueError):
        _game([{"id": CRATE, "kind": "crate", "location": "world"}],
              semantics="parallel")

    game = _game([{"id": CRATE, "kind": "crate", "location": "world"}])
    with pytest.raises(ValueError):
        game.turn_semantics = "nonsense"
    with pytest.raises(ValueError):
        game.simultaneous_priority = "not callable"


def test_create_game_passes_through_simultaneous_options():
    priority = lambda _game, _actor, _index: 0.0
    game = _game([{"id": CRATE, "kind": "crate", "location": "world"}],
                 semantics="simultaneous", executor="threaded", workers=2,
                 priority=priority)

    assert isinstance(game, BigvilleGame)
    assert game.turn_semantics == "simultaneous"
    assert game.simultaneous_priority is priority
    assert game.executor == "threaded"
    assert game.executor_workers == 2


def test_sequential_trace_is_stable_and_never_calls_claim_resolution(monkeypatch):
    calls = []

    def recorder(claims):
        calls.append(tuple(claims))
        return {}, {}

    monkeypatch.setattr("bigville.game.resolve_claims", recorder)

    def run():
        game = _game([{"id": CRATE, "kind": "crate", "location": "world"}],
                     semantics="sequential", executor="serial")
        _use(game, _PickUpCrateBackend)
        trace = TurnTrace()
        for _ in range(2):
            assert game.step()["status"] == "advanced"
            trace.add_record(step_trace(game))
        return trace

    first = run()
    second = run()

    assert calls == []
    assert first.records == second.records
    assert first.digest == second.digest
