"""Phase 042b: the lamplighter's round. A lamp is lit at dusk and doused at dawn, the round does not walk a
tired lamplighter into `exhausted`, and food comes first when a meal is held.

1. The round's choices, from the backend's view (`lamplighter_choice`).
2. The world's offers: lamps are reached with a pole from the station, and a sleeper is offered no lamp work.
3. The world's plan dispatch: a backend's `light` reaches the lamp code (it was refused `malformed` before 042b).

The three-day run (lamps lit at dusk and doused at dawn, counts per day) is a script, not a test:
docs/phases/phase042b/three_day_run.py.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from domains import bigville_entities as E  # noqa: E402
from bigville.backends.lamplighter import (  # noqa: E402
    DUSK_READY_ENERGY, ROUND_REST_ENERGY, STARVE_GUARD, WALK_ENERGY, lamplighter_choice)
from worlds import daynight as dn  # noqa: E402
from worlds.bigville_world import BigvilleWorld as World  # noqa: E402

DN = E.DAYNIGHT
TIME = E.TIME
TPD = int(TIME["ticks_per_day"])

LIGHT = {"action": "light", "lamplighter": True, "night": True, "lit": False, "lamp": "square_north_west"}
DOUSE = {"action": "douse", "lamplighter": True, "night": False, "lit": True, "lamp": "square_north_west"}
EAT = {"action": "eat", "kind": "bread"}
STATION_DAY = {"action": "move", "destination": (22, 14), "lamplighter": True, "night": False,
               "purpose": "station", "due": True}
STATION_NIGHT = {**STATION_DAY, "night": True}
DUSK_REST = {"action": "rest", "lamplighter": True, "night": False, "purpose": "dusk_ready"}
POST_REST = {"action": "rest", "lamplighter": True, "night": False, "purpose": "post"}


def ctx(options, hunger=0.0, energy=100.0):
    return SimpleNamespace(affordances=options, observations={"hunger": hunger, "energy": energy})


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


# ------------------------------------------------------------- 1. the round's choices (backend)

def test_the_round_is_empty_for_a_resident_who_is_not_the_lamplighter():
    assert lamplighter_choice(ctx([{"action": "move", "destination": (1, 1)}, EAT])) is None


def test_lamp_work_is_done_at_once_when_it_is_offered():
    assert lamplighter_choice(ctx([LIGHT])) == ("light", {}, None)
    assert lamplighter_choice(ctx([DOUSE])) == ("douse", {}, None)


def test_a_held_meal_comes_first_when_hungry():
    assert lamplighter_choice(ctx([LIGHT, EAT], hunger=2.0)) is None
    assert lamplighter_choice(ctx([LIGHT, EAT], hunger=0.5)) == ("light", {}, None)


def test_lamp_work_comes_before_food_when_hungry_and_no_meal_is_held():
    assert lamplighter_choice(ctx([LIGHT], hunger=2.0)) == ("light", {}, None)


def test_the_starvation_guard_yields_to_the_ordinary_policy_whatever_is_offered():
    assert lamplighter_choice(ctx([LIGHT], hunger=STARVE_GUARD)) is None
    assert lamplighter_choice(ctx([STATION_DAY], hunger=STARVE_GUARD)) is None


def test_by_day_a_tired_lamplighter_rests_before_any_walk():
    assert lamplighter_choice(ctx([STATION_DAY], energy=ROUND_REST_ENERGY - 1)) == ("rest", {}, None)


def test_at_night_a_tired_lamplighter_yields_to_the_ordinary_sleep():
    assert lamplighter_choice(ctx([STATION_NIGHT], energy=ROUND_REST_ENERGY - 1)) is None


def test_a_walk_to_the_station_starts_only_with_energy_to_spare():
    assert lamplighter_choice(ctx([STATION_DAY], energy=WALK_ENERGY - 1)) == ("rest", {}, None)
    action, params, continuation = lamplighter_choice(ctx([STATION_DAY], energy=WALK_ENERGY + 5))
    assert action == "move" and params == {"destination": (22, 14)} and continuation.destination == (22, 14)


def test_a_hungry_lamplighter_walks_to_the_station_only_when_lamp_work_is_due():
    not_due = {**STATION_DAY, "due": False}
    assert lamplighter_choice(ctx([not_due], hunger=1.5, energy=90.0)) is None
    assert lamplighter_choice(ctx([STATION_DAY], hunger=1.5, energy=90.0))[0] == "move"


def test_at_the_station_the_lamplighter_rests_until_he_is_ready_for_dusk():
    assert lamplighter_choice(ctx([DUSK_REST], energy=DUSK_READY_ENERGY - 10)) == ("rest", {}, None)
    assert lamplighter_choice(ctx([DUSK_REST], energy=DUSK_READY_ENERGY + 5)) is None
    assert lamplighter_choice(ctx([POST_REST], energy=DUSK_READY_ENERGY - 10)) == ("rest", {}, None)


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
