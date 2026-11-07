"""Fix simple village: founding ties are on record, and a resident who is down proposes nothing.

1. Founding ties (Phase 058, switched on for the bigville pack): a bare town100 holds 845 directed ties, by kind.
2. A simple resident who is asleep, passed out or collapsed, and holds a stored walk (a backend continuation),
   gets no proposal that turn. The game replays a continuation without asking the backend, so the continuation
   names `body_down` as an interrupt (bigville/backends/cheap.py), and game.py stops the replay for a down body.
3. The Phase 049 refusals stay: a walk below e_low (exhausted) is still refused for a backend plan.
4. Over 60 simple turns no resident is refused for a body-state reason (asleep, collapsed, passed out).
"""
from __future__ import annotations

import pytest

from bigville.backends.protocol import ActorContinuation

SEED = 305000

DOWN_STATES = {
    "asleep": {"asleep": 1.0, "collapsed": 0.0, "sleep_kind": 1.0},
    "passed_out": {"asleep": 1.0, "collapsed": 0.0, "sleep_kind": 3.0},
    "collapsed": {"asleep": 1.0, "collapsed": 1.0, "sleep_kind": 2.0},
}


def _game():
    from bigville.api import create_game
    return create_game(scenario="town100", seed=SEED, default_backend="simple", autonomous=True,
                       ticks_per_period="world")


def _awake_walker(game):
    """Run turns until an awake resident holds a stored walk (a backend continuation)."""
    for _ in range(40):
        game.step()
        for name in game._continuations:
            if game.world.is_alive(name) and game.world._sleep_code(name) is None:
                return name
    raise AssertionError("no awake resident held a walk in 40 turns")


def _refusals(world, name):
    return dict(world.eng.node(world._actors[name])["attrs"].get("refusal_counts", {}))


# ----------------------------------------------------------------- 1. founding ties
def test_the_founding_ties_are_on_record_after_a_bare_town100():
    from worlds.bigville_world import BigvilleWorld
    world = BigvilleWorld.from_town100(seed=SEED, autonomous_actors=False)
    assert len(world._relationships) == 845
    kinds = {}
    for bond in world._relationships.values():
        kind = world.eng.node(bond)["attrs"]["kind"]
        kinds[kind] = kinds.get(kind, 0) + 1
    assert kinds == {"blood_kin": 258, "spouse": 10, "friend": 200, "neighbour": 200,
                     "workmate": 160, "feud": 17}
    holders = {holder for holder, _target in world._relationships}
    assert len(holders) == 100, "every resident holds at least one founding tie"


# ----------------------------------------------------------------- 2. a down resident proposes nothing
@pytest.mark.parametrize("state", sorted(DOWN_STATES))
def test_a_resident_down_with_a_stored_walk_proposes_nothing(state):
    game = _game()
    world = game.world
    walker = _awake_walker(game)
    node = world._actors[walker]
    for key, value in DOWN_STATES[state].items():
        world.eng.set_attr(node, key, value)
    assert world._sleep_code(walker) == state
    refused_before = _refusals(world, walker)

    game.step()

    response = game.last_responses[walker]
    assert response.major_action is None, "a down resident makes no major action"
    assert response.backend_state.get("continuation_interrupted") == "body_down"
    assert walker not in game._continuations, "the stored walk ends"
    assert _refusals(world, walker) == refused_before, "nothing was proposed, so nothing was refused"


def test_an_awake_resident_is_not_stopped_by_the_body_down_interrupt():
    game = _game()
    walker = _awake_walker(game)
    game.step()
    response = game.last_responses.get(walker)
    if response is not None:
        assert response.backend_state.get("continuation_interrupted") != "body_down"


def test_the_body_down_interrupt_is_not_in_the_default_continuation():
    """Other backends' continuations keep the default interrupts; only the simple walk names body_down."""
    assert "body_down" not in ActorContinuation().interrupt_on


# ----------------------------------------------------------------- 3. Phase 049's refusal stays
def test_an_exhausted_walk_is_still_refused_for_a_backend_plan():
    game = _game()
    world = game.world
    walker = _awake_walker(game)
    position = world.actor_position(walker)
    destination = (position[0] + 2, position[1])
    world.eng.set_attr(world._bodies[walker], "stamina_reserve", 0.10)   # below e_low (0.15), above e_collapse (0.05)
    game._activate_continuation(walker, ActorContinuation(destination=destination), action_ok=True)
    assert world._sleep_code(walker) is None

    game.step()

    refused = _refusals(world, walker)
    assert refused.get("move", {}).get("exhausted", 0) == 1, refused


# ----------------------------------------------------------------- 4. the 60-turn run
def test_a_sixty_turn_simple_run_refuses_no_resident_for_a_body_state():
    game = _game()
    for _ in range(60):
        result = game.step()
        assert result.get("status") != "waiting"
    by_reason = game.world.refusal_counts()["by_reason"]
    for code in ("asleep", "collapsed", "passed_out"):
        assert by_reason.get(code, 0) == 0, (code, by_reason)
