"""Phase 042b: the lamplighter's lamp work, as the world offers it. A lamp is lit at dusk and doused at dawn, a
sleeper is offered no lamp work, and a backend's `light` reaches the lamp code.

1. The world's offers: lamps are reached with a pole from the station, and a sleeper is offered no lamp work.
2. The world's plan dispatch: a backend's `light` reaches the lamp code (it was refused `malformed` before 042b).

Phase 042c replaced the hard-coded round (its choices, and its tests of them) with a duty drive: those tests now
live in tests/test_phase042c_duty.py. The three-day run (lamps lit at dusk and doused at dawn, counts per day) is a
script, not a test: docs/phases/phase042b/three_day_run.py, and docs/phases/phase042c/ for the duty.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from domains import bigville_entities as E  # noqa: E402
from worlds import daynight as dn  # noqa: E402
from worlds.bigville_world import BigvilleWorld as World  # noqa: E402

DN = E.DAYNIGHT
TIME = E.TIME
TPD = int(TIME["ticks_per_day"])


def _clock_at(day, hour):
    offset = (hour - float(TIME["start_hour"])) % 24.0
    return day * TPD + int(round(offset * TPD / 24.0))


def _set_clock(w, clock):
    w.eng.set_attr(w._town, "clock", float(clock))
    w._advance_calendar()


def _on():
    """A world with day and night on. Bob is first in the founding order, so he takes the lamplighter's job."""
    w = World()
    w.add_actor("Bob", role="labourer", skill=0.9)
    w.add_actor("Ada", role="labourer", skill=0.9)
    dn.switch_on(w)
    return w


# ------------------------------------------------------------- 2. the world's offers

def test_the_station_reaches_every_lamp_with_the_pole():
    w = _on()
    station = dn.station_cell(w)
    reach = int(DN["lamp_pole_reach"])
    for cell in w._dn_lamps:
        assert max(abs(cell[0] - station[0]), abs(cell[1] - station[1])) <= reach


def test_the_lamplighter_is_offered_a_light_from_the_station_at_night(monkeypatch):
    w = _on()
    lamplighter = dn.lamplighters(w)[0]
    _set_clock(w, _clock_at(0, 22.0))
    w._move_actor_to(lamplighter, dn.station_cell(w))
    lights = [o for o in dn.lamp_options(w, lamplighter) if o["action"] == "light"]
    assert len(lights) == 1 and lights[0]["lamplighter"] is True and lights[0]["night"] is True


def test_a_sleeper_is_offered_no_lamp_work(monkeypatch):
    w = _on()
    lamplighter = dn.lamplighters(w)[0]
    _set_clock(w, _clock_at(0, 22.0))
    w._move_actor_to(lamplighter, dn.station_cell(w))
    monkeypatch.setattr(w, "asleep", lambda actor: True)
    assert dn.lamp_options(w, lamplighter) == []


def test_the_station_walk_is_offered_away_from_the_station_and_is_marked_due_at_night():
    w = _on()
    lamplighter = dn.lamplighters(w)[0]
    _set_clock(w, _clock_at(0, 22.0))
    far = next(c for c in sorted(w._map_cells) if c != dn.station_cell(w)
               and max(abs(c[0] - dn.station_cell(w)[0]), abs(c[1] - dn.station_cell(w)[1])) > 3
               and not dn.indoors(w, c))
    w._move_actor_to(lamplighter, far)
    walks = [o for o in dn.lamp_options(w, lamplighter) if o["action"] == "move"]
    assert len(walks) == 1 and walks[0]["purpose"] == "station" and walks[0]["destination"] == dn.station_cell(w)
    assert walks[0]["due"] is True


# ------------------------------------------------------------- 3. the world's plan dispatch

def test_a_plan_to_light_reaches_the_lamp_code_at_the_station():
    w = _on()
    lamplighter = dn.lamplighters(w)[0]
    _set_clock(w, _clock_at(0, 22.0))
    w._move_actor_to(lamplighter, dn.station_cell(w))
    assert w.enact_plan(lamplighter, {"action": "light"}) is True
    assert sum(1 for n in w._dn_lamps.values() if float(w.eng.node(n)["attrs"]["lit"]) == 1.0) == 1


def test_a_plan_to_light_far_from_every_lamp_is_refused_not_as_malformed():
    w = _on()
    lamplighter = dn.lamplighters(w)[0]
    _set_clock(w, _clock_at(0, 22.0))
    reach = int(DN["lamp_pole_reach"])
    far = next(c for c in sorted(w._map_cells)
               if all(max(abs(c[0] - l[0]), abs(c[1] - l[1])) > reach for l in w._dn_lamps))
    w._move_actor_to(lamplighter, far)
    assert w.enact_plan(lamplighter, {"action": "light"}) is False
    outcome = w.eng.node(w._actor(lamplighter))["attrs"]["last_outcome"]
    assert outcome["reason"] == "not_at_site"
