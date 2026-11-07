"""TG02: the occupancy index must agree with a brute-force proximity scan.

The index is derived state: ``_actor_positions`` remains the canonical mapping
and checkpoints as a plain dict. These tests exercise the bucket map directly,
through direct mutations and after a simulated plain-dict restore, and compare
the indexed engine path with the brute-force debug path over whole traces.
"""
from __future__ import annotations

import pytest

from bigville.api import create_game, create_world
from bigville.tick_trace import TurnTrace
from worlds.bigville_world import _ActorPositions

TURNS = 4
TOWN_SEED = 305000

# A small authored map with walls and pockets so some Chebyshev neighbours are
# not walkable at all. Rows are y, columns are x.
SMALL_SCENARIO = {
    "id": "tg02_occupancy_room",
    "name": "TG02 occupancy room",
    "map": {"grid": [
        ["wall"] * 9,
        ["wall", "floor", "floor", "floor", "wall", "floor", "floor", "floor", "wall"],
        ["wall", "floor", "wall", "floor", "wall", "floor", "wall", "floor", "wall"],
        ["wall", "floor", "wall", "floor", "floor", "floor", "wall", "floor", "wall"],
        ["wall", "floor", "wall", "wall", "wall", "wall", "wall", "floor", "wall"],
        ["wall", "floor", "floor", "floor", "wall", "floor", "floor", "floor", "wall"],
        ["wall", "wall", "wall", "floor", "wall", "floor", "wall", "wall", "wall"],
        ["wall", "floor", "floor", "floor", "floor", "floor", "floor", "floor", "wall"],
        ["wall"] * 9,
    ]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [3, 1]},
        {"name": "Cy", "role": "resident", "backend": "simple", "home_cell": [7, 1]},
        {"name": "Dee", "role": "resident", "backend": "simple", "home_cell": [1, 3]},
        {"name": "Eli", "role": "resident", "backend": "simple", "home_cell": [5, 3]},
        {"name": "Fay", "role": "resident", "backend": "simple", "home_cell": [3, 6]},
        {"name": "Gus", "role": "resident", "backend": "simple", "home_cell": [7, 7]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [],
    "laws": [],
    "policies": [],
    "charters": [],
}


@pytest.fixture(scope="module")
def town_world():
    return create_world(scenario="town100", seed=TOWN_SEED)


def _small_world():
    return create_world(scenario=SMALL_SCENARIO, seed=TOWN_SEED)


def _town_game():
    return create_game(scenario="town100", seed=TOWN_SEED, default_backend="simple",
                       autonomous=True, llm_log=False)


def _small_game():
    return create_game(scenario=SMALL_SCENARIO, seed=TOWN_SEED, default_backend="simple",
                       autonomous=True, llm_log=False)


def _brute_force(world, position, radius, *, alive_only=True, exclude=None):
    """The exact answer, by scanning every actor and asking the world's distance."""
    names = []
    for name in world._actors:
        if exclude is not None and name == exclude:
            continue
        if alive_only and not world.is_alive(name):
            continue
        other = world.actor_position(name)
        distance = world.distance(position, other) if other is not None else None
        if distance is not None and distance <= radius:
            names.append(name)
    return sorted(names)


def _turns(world):
    """Map cells paired with radii, including cells behind walls and a wall itself."""
    cells = sorted(world._map_cells)
    chosen = [cells[0], cells[len(cells) // 3], cells[len(cells) // 2],
              cells[(2 * len(cells)) // 3], cells[-1]]
    # A wall cell is not walkable, so every distance to it is None.
    chosen.append((0, 0))
    return [(cell, radius) for cell in chosen for radius in (0, 1, 2, 4, 8)]


def test_actors_near_matches_brute_force_on_founding_map(town_world):
    for position, radius in _turns(town_world):
        expected = _brute_force(town_world, position, radius)
        assert town_world.actors_near(position, radius) == expected


def test_actors_near_matches_brute_force_on_authored_map():
    world = _small_world()
    assert isinstance(world._actor_positions, _ActorPositions)
    for position, radius in _turns(world):
        expected = _brute_force(world, position, radius)
        assert world.actors_near(position, radius) == expected, (position, radius)
        # The exclude filter and the alive flag are exact too.
        assert world.actors_near(position, radius, exclude="Ada") == \
            [name for name in expected if name != "Ada"]


def test_actors_near_rejects_missing_and_malformed_positions():
    world = _small_world()
    assert world.actors_near(None, 8) == []
    assert world.actors_near(3, 8) == []
    assert world.actors_near((1, 2, 3), 8) == []
    assert world.actors_near("Ada", 8) == []


def test_direct_mutations_keep_the_index_coherent():
    world = _small_world()
    positions = world._actor_positions
    assert isinstance(positions, _ActorPositions)

    positions["Ada"] = (1, 1)
    positions.update({"Ben": (1, 1), "Cy": (2, 1)})
    assert world.actors_near((1, 1), 0, exclude="Ada") == ["Ben"]
    assert world.actors_near((1, 1), 1, exclude="Ada") == ["Ben", "Cy"]

    positions.pop("Ben")
    assert world.actors_near((1, 1), 0, exclude="Ada") == []
    positions.setdefault("Visitor", (1, 1))
    assert "Visitor" in positions.near((1, 1), 0)
    positions["Fay"] = (1, 1)
    assert world.actors_near((1, 1), 0, exclude="Ada") == ["Fay"]

    # A checkpoint decodes the mapping as a plain dict. A query must rewrap it
    # and rebuild the index, and later direct mutations must stay coherent.
    world._actor_positions = dict(positions)
    assert not isinstance(world._actor_positions, _ActorPositions)
    assert world.actors_near((1, 1), 0, exclude="Ada") == ["Fay"]
    assert isinstance(world._actor_positions, _ActorPositions)
    world._actor_positions["Eli"] = (1, 1)
    assert world.actors_near((1, 1), 0, exclude="Ada") == ["Eli", "Fay"]

    world._actor_positions.clear()
    assert world.actors_near((1, 1), 8) == []


def test_dead_actors_are_excluded_unless_requested():
    world = _small_world()
    cell = world.actor_position("Ben")
    world.eng.set_attr(world._actors["Ben"], "alive", 0.0)

    assert "Ben" not in world.actors_near(cell, 0)
    assert "Ben" in world.actors_near(cell, 0, alive_only=False)


def _snapshot(game):
    return {
        "order": list(game.last_order),
        "results": dict(game.last_results),
        "errors": dict(game.last_errors),
        "proposals": {
            name: None if response.major_action is None else
            (response.major_action.action, dict(response.major_action.params))
            for name, response in game.last_responses.items()
        },
        "continuations": {
            name: active.request.to_dict() for name, active in game._continuations.items()
        },
    }


def _run(game, turns):
    trace = TurnTrace()
    snapshots = []
    for _ in range(turns):
        assert game.step()["status"] == "advanced"
        trace.add(game)
        snapshots.append(_snapshot(game))
    return trace, snapshots


def test_trace_digest_and_engine_paths_agree_on_town100():
    # Two ordinary runs prove the digest is stable within the test process.
    first, first_steps = _run(_town_game(), TURNS)
    second, second_steps = _run(_town_game(), TURNS)
    assert first.turns == second.turns == TURNS
    assert first.digest == second.digest
    assert first_steps == second_steps

    # A third run disables the index: the brute-force path must agree turn by turn.
    linear_game = _town_game()
    linear_game.world._force_linear_proximity = True
    try:
        linear, linear_steps = _run(linear_game, TURNS)
    finally:
        linear_game.world._force_linear_proximity = False

    assert linear.digest == first.digest
    assert linear.records == first.records
    assert linear_steps == first_steps


def test_trace_digest_and_engine_paths_agree_on_the_small_scenario():
    first, first_steps = _run(_small_game(), TURNS)

    linear_game = _small_game()
    linear_game.world._force_linear_proximity = True
    try:
        linear, linear_steps = _run(linear_game, TURNS)
    finally:
        linear_game.world._force_linear_proximity = False

    assert linear.digest == first.digest
    assert linear.records == first.records
    assert linear_steps == first_steps
