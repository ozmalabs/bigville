"""DS04: deterministic chance across shards, reordering and checkpoint restore.

The tests exercise the same rule as ``tools/verify_deterministic_chance.py``
on a small scenario so the suite stays fast:

* the same weather/infrastructure/birth/illness/meal/strike draw values under a
  fixed ascending vs descending evaluation order;
* serial vs partitioned semantic state, payload checksum and revision equality;
* two partitioned replays with equal execution/payload checksums and commits;
* checkpoint at turn 3, restore, continue two turns, equal to the uninterrupted
  run;
* no ``world._rng`` and a clean DS03 production source audit.

No probability table or threshold is asserted here; DS02 covers those.
"""
from __future__ import annotations

import pytest

from tools.verify_deterministic_chance import (
    SMALL_SCENARIO,
    _draw_events,
    _run_checkpoint,
    _run_serial_partitioned,
    build_game,
    prime_chance,
    reorder_check,
    source_audit,
)

SEEDS = (305000, 305002)
TURNS = 8


def _game(seed=305000, executor="serial"):
    game = build_game(scenario="small", seed=seed, executor=executor)
    prime_chance(game.world)
    return game


# ------------------------------------------------------------------ reordering


def test_same_draws_under_a_didactic_ascending_vs_descending_order():
    world = _game().world
    names = sorted(world._actors)
    ascending = _draw_events(world, names)
    descending = _draw_events(world, list(reversed(names)), reverse=True)

    # Every family named by the plan participates.
    for prefix in ("weather:", "infrastructure:", "birth:", "illness:",
                   "meal:", "strike:"):
        assert any(key.startswith(prefix) for key in ascending), prefix

    assert ascending == descending
    check = reorder_check(world)
    assert check["ok"] and check["events"] == len(ascending)
    assert check["mismatches"] == {}


# ------------------------------------------------------- serial vs partitioned


@pytest.mark.parametrize("seed", SEEDS)
def test_serial_and_partitioned_match_semantically_for_eight_turns(seed):
    result = _run_serial_partitioned(
        seed, TURNS, "small", "menu",
        run_serial=True, run_partitioned=True, chance_heavy=True)

    assert result["semantic_state_equal"]
    assert result["payload_equal"]
    assert result["revision_equal"]
    assert result["execution_stable"]
    assert result["first_state_divergence"] is None
    assert result["first_payload_divergence"] is None
    assert result["first_execution_divergence"] is None
    assert result["first_revision_divergence"] is None
    assert result["revisions"] == sorted(result["revisions"])

    # The chance-heavy setup really exercised the non-actor streams.
    assert result["chance_heavy"]["infrastructure_failed"]
    assert result["chance_heavy"]["animal_birth_drawn"]
    assert result["draw_counts"].get("illness", 0) > 0


@pytest.mark.parametrize("seed", SEEDS)
def test_two_partitioned_replays_have_equal_execution_and_payload_hashes(seed):
    result = _run_serial_partitioned(
        seed, TURNS, "small", "menu",
        run_serial=False, run_partitioned=True, chance_heavy=True)

    assert result["execution_stable"]
    assert result["payload_equal"]
    assert result["revision_equal"]
    assert result["partitioned_run_execution_sha"] == result["replay_run_execution_sha"]
    assert result["first_execution_divergence"] is None


# ------------------------------------------------------- checkpoint continuity


def test_checkpoint_at_turn_three_restore_and_continue_two_turns():
    seed = 305000
    baseline = _run_serial_partitioned(
        seed, 5, "small", "menu",
        run_serial=True, run_partitioned=False, chance_heavy=True)
    restored = _run_checkpoint(
        seed, 5, "small", "menu", 3, baseline["trajectory"],
        chance_heavy=True)

    assert restored["ok"]
    assert restored["checkpoint_turn"] == 3
    assert restored["continued_turns"] == 2
    assert restored["prefix_equal"]
    assert restored["restored_equal"]
    assert restored["first_divergence"] is None
    assert restored["prefix"] == baseline["trajectory"][:3]
    assert restored["continued"] == baseline["trajectory"][3:5]


# ------------------------------------------------------------ shared RNG audit


def test_no_world_rng_and_the_production_source_audit_passes():
    game = _game(seed=305000)
    assert not hasattr(game.world, "_rng")
    audit = source_audit()
    assert audit["ok"], audit["findings"]
    assert audit["findings"] == []
    assert audit["files"] > 0


def test_small_scenario_is_the_documented_ds04_room():
    # Guard against the test accidentally drifting onto the 100-resident town.
    assert SMALL_SCENARIO["id"] == "ds04_chance_room"
    assert len(SMALL_SCENARIO["actors"]) == 3
