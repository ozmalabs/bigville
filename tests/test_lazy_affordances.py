"""LA01: the affordance-mode seam and the menu-vs-observation baseline.

LA01 adds no lazy play path: ``affordance_mode="lazy"`` is a placeholder that
still builds the menu.  What this file locks down is the option validation, the
default ``menu`` trace, and the ``skip_affordances`` measurement seam.
"""
from __future__ import annotations

import importlib

import pytest

from bigville.api import create_game, create_world
from bigville.game import BigvilleGame
from bigville.tick_trace import TurnTrace

TURNS = 2

# The small TG01/TG03 scenario: three residents on a six-by-six floor.
SMALL_SCENARIO = {
    "id": "la01_mode_room",
    "name": "LA01 mode room",
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


def _small(**kwargs):
    return create_game(scenario=SMALL_SCENARIO, seed=305000,
                       default_backend="simple", autonomous=True,
                       llm_log=False, **kwargs)


def _town(**kwargs):
    return create_game(scenario="town100", seed=305000,
                       default_backend="simple", autonomous=True,
                       llm_log=False, **kwargs)


def _run(game, turns=TURNS):
    trace = TurnTrace()
    for _ in range(turns):
        assert game.step()["status"] == "advanced"
        trace.add(game)
    return trace


def test_affordance_mode_defaults_to_menu():
    game = _small()
    assert game.affordance_mode == "menu"

    # The option is a validated property, not just a stored string.
    with pytest.raises(ValueError):
        game.affordance_mode = "bogus"


def test_create_game_rejects_unknown_affordance_mode():
    with pytest.raises(ValueError):
        _small(affordance_mode="eager")


def test_bigville_game_rejects_unknown_affordance_mode():
    world = create_world(scenario=SMALL_SCENARIO, seed=305000)
    with pytest.raises(ValueError):
        BigvilleGame(world, autonomous=True, affordance_mode="bogus")

    game = BigvilleGame(world, autonomous=True)
    assert game.affordance_mode == "menu"


def test_create_game_exposes_lazy_mode():
    game = _small(affordance_mode="lazy")
    assert game.affordance_mode == "lazy"


def test_default_menu_mode_trace_digest_is_unchanged_across_runs():
    first, second = _run(_small()), _run(_small())
    assert first.turns == second.turns == TURNS
    assert first.records == second.records
    assert first.hexdigest() == second.hexdigest()


def test_skip_affordances_omits_the_menu_and_never_calls_the_world():
    # town100 gives the resident a non-empty menu (store, travel, ...).
    game = _town()
    calls: list[str] = []
    original = game.world.actor_affordances

    def counted(actor):
        calls.append(actor)
        return original(actor)

    game.world.actor_affordances = counted
    actor = next(iter(game.characters))
    # A sentinel proves the skipped path does not populate ``_actor_targets``.
    sentinel = {"sentinel": ("unset",)}
    game.world._actor_targets[actor] = sentinel

    skipped = game._context(actor, skip_affordances=True)
    assert calls == []
    assert skipped.affordances == []
    assert game.world._actor_targets[actor] is sentinel

    normal = game._context(actor)
    assert calls == [actor]
    assert normal.affordances  # a resident in the town has options


def test_benchmark_builder_imports_without_running_the_benchmark(monkeypatch):
    bench = importlib.import_module("tools.benchmark_affordances")
    assert callable(bench.benchmark)
    assert callable(bench.main)
    assert callable(bench.measure_size)

    # Building the scenario must not construct a world (or a game).
    import bigville.api as api

    def boom(*args, **kwargs):
        raise AssertionError("build_scenario constructed a world or a game")

    monkeypatch.setattr(api, "create_game", boom)
    scenario = bench.build_scenario(5)
    assert scenario["id"] == "tg07_bench_5"
    assert len(scenario["actors"]) == 5
    assert "map" in scenario
