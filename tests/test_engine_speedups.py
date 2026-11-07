"""EN01: the engine profiling harness is import-safe and measures components.

The tiny run here (five residents, one turn) exists to prove the wrapper
accounting and the scenario builder, not to benchmark the engine.  The recorded
baseline lives in ``docs/phases/engine-speedups/``.
"""
from __future__ import annotations

import importlib
import sys

import pytest

from tools import profile_engine


@pytest.fixture(scope="module")
def tiny_run():
    return profile_engine.run_one(5, turns=1, seed=305000,
                                  affordance_mode="lazy", executor="serial")


def test_import_does_not_build_or_run(monkeypatch):
    """Importing the module must not call ``create_game``."""
    import bigville.api as api

    calls: list[tuple] = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("importing profile_engine built a game")

    monkeypatch.setattr(api, "create_game", forbidden)
    sys.modules.pop("tools.profile_engine", None)
    module = importlib.import_module("tools.profile_engine")
    assert calls == []
    assert callable(module.profile)
    assert callable(module.run_one)
    assert callable(module.profile_run)


def test_build_scenario_is_a_plain_dictionary():
    scenario = profile_engine.build_scenario(5)
    assert isinstance(scenario, dict)
    assert len(scenario["actors"]) == 5
    assert scenario["physical_subsystems"]["metabolism"] is False
    assert {actor["backend"] for actor in scenario["actors"]} == {"simple"}


def test_tiny_run_component_keys_and_counts(tiny_run):
    assert tiny_run["status"] == "ok"
    assert tiny_run["turns_completed"] == 1
    per_turn = tiny_run["per_turn"]
    for key in ("step_ms", "context_ms", "world_tick_ms", "commit_ms",
                "commit_total_ms", "finish_ms", "snapshot_ms", "other_ms",
                "run_calls", "node_calls", "actors_near_calls",
                "proposed", "applied"):
        assert key in per_turn, key
        assert per_turn[key] >= 0, key
    totals = tiny_run["totals"]
    assert totals["run_calls"] > 0
    assert totals["node_calls"] > 0
    assert totals["actors_near_calls"] > 0
    assert totals["step_seconds"] > 0
    # Subset sanity only: do not assert a tight additive sum.
    assert totals["step_seconds"] >= totals["context_seconds"]
    assert totals["step_seconds"] >= totals["commit_total_seconds"]
    assert totals["commit_total_seconds"] >= totals["finish_seconds"]
    assert totals["finish_seconds"] >= totals["snapshot_seconds"]


def test_wrappers_advance_one_turn():
    game = profile_engine.build_game(5, seed=305000)
    timers = profile_engine.instrument(game)
    before = int(game.world._turn)
    result = game.step()
    assert result.get("status") == "advanced"
    assert int(game.world._turn) == before + 1
    assert timers["context"].calls >= 1
    assert timers["world_tick"].calls == 1
    assert timers["commit"].calls >= 1
    assert timers["finish"].calls == 1
    assert timers["snapshot"].calls == 1
    assert timers["run"].calls > 0
    assert timers["node"].calls > 0
    assert timers["actors_near"].calls > 0
    assert timers["context"].seconds >= 0
    assert timers["commit"].seconds >= timers["finish"].seconds


def test_markdown_table_mentions_the_components(tiny_run):
    document = {
        "results": [tiny_run],
        "components_note": profile_engine.COMPONENTS_NOTE,
    }
    table = profile_engine.markdown_table(document)
    assert "step ms/turn" in table
    assert "snapshot ms (subset)" in table
    assert "| 5 |" in table
