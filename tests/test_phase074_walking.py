"""Phase 074: the walking energy is charged only on a tick that takes a step, and its per-step cost comes
from the pack (CARRYING.stamina_per_move_unit), not a literal in the world."""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from worlds.bigville_world import BigvilleWorld as World      # noqa: E402
from domains import bigville_entities as E                    # noqa: E402


def _walker():
    w = World()
    w.add_actor("Walker", role="hand", home_cell=(1, 1))
    node = w._actors["Walker"]
    here = w.actor_position("Walker")
    nxt = next(cell for cell in sorted(w._map_cells)
               if abs(cell[0] - here[0]) + abs(cell[1] - here[1]) == 1
               and w.terrain_state(cell)["speed"] > 0.0)
    return w, node, here, nxt


def test_a_waiting_tick_costs_no_energy_and_a_stepping_tick_does():
    w, node, here, nxt = _walker()
    # A tired walker's cooldown is above 1: the first two calls are waiting ticks that move nobody.
    w.eng.set_attr(node, "carry_move_cooldown", 2.0)
    before = w.energy("Walker")
    w.move_actor("Walker", nxt)
    assert w.actor_position("Walker") == here
    assert w.energy("Walker") == before, "a waiting tick moves nobody, so it costs no energy"
    w.move_actor("Walker", nxt)
    assert w.actor_position("Walker") == here
    assert w.energy("Walker") == before, "the second waiting tick also costs no energy"
    # The cooldown is spent, so this call takes the step and pays for it.
    w.move_actor("Walker", nxt)
    assert w.actor_position("Walker") == nxt
    assert w.energy("Walker") < before, "a stepping tick is charged the step's energy"


def test_a_flat_step_costs_the_pack_factor_times_the_terrain_multiplier():
    w, node, here, nxt = _walker()
    w.eng.set_attr(node, "carry_move_cooldown", 0.0)
    multiplier = float(w.terrain_state(nxt)["stamina_multiplier"])
    before = w.energy("Walker")
    w.move_actor("Walker", nxt)
    spent = before - w.energy("Walker")
    expected = 100.0 * float(E.CARRYING["stamina_per_move_unit"]) * float(E.CARRYING["base_move_energy"]) * multiplier
    assert spent == pytest.approx(expected, rel=1e-6, abs=1e-9)


def test_the_per_step_factor_is_read_from_the_pack_table(monkeypatch):
    w, node, here, nxt = _walker()
    w.eng.set_attr(node, "carry_move_cooldown", 0.0)
    monkeypatch.setitem(E.CARRYING, "stamina_per_move_unit", 0.2)
    multiplier = float(w.terrain_state(nxt)["stamina_multiplier"])
    before = w.energy("Walker")
    w.move_actor("Walker", nxt)
    assert before - w.energy("Walker") == pytest.approx(20.0 * multiplier, rel=1e-6, abs=1e-9)
