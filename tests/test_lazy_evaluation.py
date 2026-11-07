"""LA06: the mode evaluation tool and the declined default switch.

The evaluation compares menu and lazy on the same scenario and seed.  The
evidence (see ``docs/phases/lazy-affordances/LA06_REPORT.md``) shows lazy mode
causing improvised jobs and accidents, and so a materially worse health
outcome.  The default therefore stays ``"menu"``; ``"auto"`` was considered and
declined.  These tests lock the tool's shape and that decision down without
re-running a long scenario.
"""
from __future__ import annotations

import importlib
import json

import pytest

from bigville.api import create_game
from bigville.game import BigvilleGame


SMALL_SCENARIO = {
    "id": "la06_test_room",
    "name": "LA06 test room",
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


def _evaluation_module():
    return importlib.import_module("tools.evaluate_affordance_modes")


def _benchmark_module():
    return importlib.import_module("tools.benchmark_affordances")


def _small(**kwargs):
    return create_game(scenario=SMALL_SCENARIO, seed=305000,
                       default_backend="simple", autonomous=True,
                       llm_log=False, **kwargs)


# --------------------------------------------------------------- builders
def test_evaluation_builder_is_import_safe(monkeypatch):
    evaluate = _evaluation_module()
    assert callable(evaluate.evaluate)
    assert callable(evaluate.main)
    assert callable(evaluate.run_mode)

    import bigville.api as api

    def boom(*args, **kwargs):
        raise AssertionError("importing the tool constructed a game")

    monkeypatch.setattr(api, "create_game", boom)
    scenario = evaluate.scenario_definition("small")
    assert scenario["id"] == "la06_small_room"
    assert len(scenario["actors"]) == 3
    assert evaluate.scenario_definition("town100") == "town100"


def test_evaluation_rejects_unknown_scenario_and_mode():
    evaluate = _evaluation_module()
    with pytest.raises(ValueError):
        evaluate.scenario_definition("not_a_scenario")
    with pytest.raises(ValueError):
        evaluate.evaluate("small", turns=0, modes=["menu", "bogus"])


# --------------------------------------------------------------- evaluation output
def test_small_evaluation_records_both_modes_and_comparison():
    evaluate = _evaluation_module()
    document = evaluate.evaluate("small", seed=305000, turns=2,
                                 modes=["menu", "lazy"])
    json.dumps(document)  # the printed document is JSON-safe

    assert document["scenario"] == "small"
    assert document["seed"] == 305000
    assert [row["mode"] for row in document["results"]] == ["menu", "lazy"]
    for row in document["results"]:
        assert row["status"] == "completed"
        assert row["turns_completed"] == 2
        assert len(row["steps"]) == 2
        step = row["steps"][0]
        for key in ("turn", "status", "proposed", "applied", "refused",
                    "no_action", "proposed_by_action", "applied_by_action",
                    "refusals_by_reason", "step_seconds", "context_seconds",
                    "alive", "hunger_mean", "energy_mean", "health_mean",
                    "health_min", "health_states"):
            assert key in step, key
        totals = row["totals"]
        assert totals["applied"] + totals["refused"] <= totals["proposed"]
        for key in ("work", "tool_tally"):
            assert key in row["final"]["attempts"]
        assert row["final"]["report"]["available"] is True
        assert row["final"]["sanity"]["available"] is True

    comparison = document["comparison"]
    for key in ("turns", "applied_per_turn", "refusal_rate", "alive",
                "hunger_mean", "energy_mean", "health_mean", "health_min",
                "tool_tally", "work_applied", "handovers",
                "context_seconds", "wall_seconds"):
        assert key in comparison, key
    assert comparison["turns"] == {"menu": 2, "lazy": 2}


def test_evaluation_timeout_is_recorded_not_faked():
    evaluate = _evaluation_module()
    document = evaluate.evaluate("small", turns=4, modes=["menu"],
                                 timeout=0.0)
    row = document["results"][0]
    assert row["status"] == "timeout"
    assert row["turns_completed"] == 0
    assert row["totals"]["applied"] == 0


# --------------------------------------------------------------- benchmark
def test_benchmark_reports_lazy_context_and_turn_time():
    bench = _benchmark_module()
    document = bench.benchmark([3], repeats=1, turns=0)
    row = document["results"][0]
    assert row["actors"] == 3
    for key in ("menu_seconds", "lazy_seconds", "observe_only_seconds",
                "menu_turn_seconds", "lazy_turn_seconds",
                "ratio_menu_over_lazy", "ratio_menu_turn_over_lazy_turn"):
        assert key in row, key
    assert row["turns"] == 0


# --------------------------------------------------------------- default decision
def test_default_is_auto_lazy_and_explicit_modes_win():
    game = _small()
    assert game.affordance_mode_requested == "auto"
    assert game.affordance_mode == "lazy"
    assert _small(affordance_mode="lazy").affordance_mode == "lazy"
    assert _small(affordance_mode="menu").affordance_mode == "menu"


def test_auto_mode_is_accepted_and_resolves_for_the_session():
    game = _small(affordance_mode="auto")
    assert game.affordance_mode_requested == "auto"
    assert game.affordance_mode == "lazy"


def test_direct_constructor_default_stays_menu():
    from bigville.api import create_world

    world = create_world(scenario=SMALL_SCENARIO, seed=305000)
    game = BigvilleGame(world, autonomous=True)
    assert game.affordance_mode == "menu"
