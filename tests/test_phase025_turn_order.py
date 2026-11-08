"""Phase 025: fair turn order.

Responses are applied in a permutation of the actors that varies by turn. The permutation is
derived from the map seed and the turn number with a generator of its own, so the same seed gives
the same order on replay, the world's RNG stream is untouched, and checkpoints need no new state.
"""
from __future__ import annotations

import random

from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import DeterministicBackend
from bigville.game import BigvilleGame
from worlds.bigville_world import BigvilleWorld


def _town(seed=None):
    kwargs = {"autonomous_actors": False}
    if seed is not None:
        kwargs["seed"] = seed
    world = BigvilleWorld.from_town100(**kwargs)
    world.tick()
    return world


class _Fetcher(DeterministicBackend):
    """Proposes to fetch one unit of bread every turn."""

    def decide(self, context):
        return ActorResponse(major_action=ProposedAction("fetch", {"kind": "bread", "amount": 1.0}))


def _at_store(world, actor):
    world._move_actor_to(actor, world.map_position_node(world._store))


def test_same_seed_and_turn_give_the_same_order_on_replay():
    first = _town(seed=305000)
    second = _town(seed=305000)
    names = sorted(first._actors)
    game_a = BigvilleGame(first, autonomous=True)
    game_b = BigvilleGame(second, autonomous=True)
    for turn in range(1, 60):
        assert game_a.turn_order(names, turn) == game_b.turn_order(names, turn)


def test_the_order_is_a_permutation_of_the_actors_and_changes_between_turns():
    world = _town()
    game = BigvilleGame(world, autonomous=True)
    names = sorted(world._actors)
    orders = [game.turn_order(names, turn) for turn in range(1, 40)]
    for order in orders:
        assert sorted(order) == names
    assert len({tuple(order) for order in orders}) > 1


def test_the_order_depends_on_the_map_seed():
    game_a = BigvilleGame(_town(seed=305000), autonomous=True)
    game_b = BigvilleGame(_town(seed=7), autonomous=True)
    names = sorted(game_a.world._actors)
    assert any(game_a.turn_order(names, turn) != game_b.turn_order(names, turn)
               for turn in range(1, 20))


def test_the_order_does_not_depend_on_the_order_the_actors_are_listed():
    world = _town()
    game = BigvilleGame(world, autonomous=True)
    names = sorted(world._actors)
    assert game.turn_order(names, 5) == game.turn_order(list(reversed(names)), 5)


def test_the_order_generator_needs_no_world_rng_state():
    world = _town()
    game = BigvilleGame(world, autonomous=True)
    names = sorted(world._actors)
    assert not hasattr(world, "_rng"), "the world keeps no shared RNG"
    for turn in range(1, 50):
        game.turn_order(names, turn)
    assert not hasattr(world, "_rng")


def test_a_turn_records_the_order_it_applied():
    world = _town()
    game = BigvilleGame(world, autonomous=True)
    names = sorted(world._actors)
    assert game.last_order == []
    game.step()
    assert sorted(game.last_order) == sorted(game.last_responses)
    assert game.last_order == game.turn_order(list(game.last_responses), int(world._turn))


def test_two_residents_who_want_the_last_unit_each_win_about_half_the_time():
    world = _town()
    names = sorted(world._actors)
    first, second = names[0], names[1]
    # Only the two contenders decide: step() builds a context for every backend, and a
    # 100-resident decision pass per turn would make 200 turns take minutes.
    game = BigvilleGame(world, autonomous=True)
    characters = game.characters
    game.backends = {first: _Fetcher(characters[first]), second: _Fetcher(characters[second])}

    turns = 120
    wins = {first: 0, second: 0}
    for _ in range(turns):
        for name in (first, second):
            _at_store(world, name)
            # Test fixture: empty last turn's winner so the bag's volume does not refuse the next
            # fetch as no_capacity. This is not a game action.
            if world.inventory_qty(name, "bread"):
                world.eng.set_attr(world._inventory_stock(name, "bread"), "qty", 0.0)
        world.set_stock("bread", 1.0)
        game.step()
        applied = [name for name in (first, second) if game.last_results.get(name)]
        assert len(applied) == 1, game.last_results
        wins[applied[0]] += 1

    assert wins[first] + wins[second] == turns
    assert 0.35 * turns <= wins[first] <= 0.65 * turns, wins

