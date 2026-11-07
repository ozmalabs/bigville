"""Phase 042: day, night and lamps. One test (or more) for each acceptance item in docs/FEATURE_PHASES.md.

1. Daylight is longer in summer than in winter at the pack's latitude.
2. A clear full-moon night is bright enough to see by; a new-moon or an overcast night is not.
3. An outdoor resident sees in the dark beside a lit lamp, and not beside an unlit one.
4. Lamps burn oil and go out when it runs out.
5. Field work in the dark is slow, wasteful and risky, and goes normally at dawn.
6. Witnessing range shortens at night.
7. The balance report includes lamp oil.
Plus: the default is off and changes nothing; the lamplighter's round is a backend choice; lateness
comes from the real sunset; the lexicon words; the self-test.
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
from domains import daynight as D  # noqa: E402
from domains import world_affordances as WA  # noqa: E402
from domains.population import scale_scenario  # noqa: E402
from worlds import daynight as dn  # noqa: E402
from worlds.bigville_world import BigvilleWorld as World  # noqa: E402
from bigville.backends.lamplighter import lamplighter_choice  # noqa: E402

DN = E.DAYNIGHT
TIME = E.TIME
TPD = int(TIME["ticks_per_day"])


def _clock_at(day, hour):
    """The clock tick on a calendar day at an hour of day (quarter-hour ticks from TIME.start_hour)."""
    offset = (hour - float(TIME["start_hour"])) % 24.0
    return day * TPD + int(round(offset * TPD / 24.0))


def _set_clock(w, clock):
    w.eng.set_attr(w._town, "clock", float(clock))
    w._advance_calendar()


def _set_weather(w, weather):
    w.set_weather(weather)


def _outdoor_cell(w):
    """A walkable cell outside every building footprint, away from the square's lamps."""
    for cell in sorted(w._map_cells):
        if not dn.indoors(w, cell) and cell[0] < 12 and cell[1] < 12 and cell not in w._dn_lamps:
            return cell
    raise AssertionError("no outdoor cell")


def _beside(w, lamp_cell):
    """An outdoor walkable cell next to a lamp (the lamp reaches it, DAYNIGHT.lamp_reach 1)."""
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        cell = (lamp_cell[0] + dx, lamp_cell[1] + dy)
        if cell in w._map_cells and not dn.indoors(w, cell) and cell not in w._dn_lamps:
            return cell
    raise AssertionError("no outdoor cell beside the lamp")


def _on(monkeypatch=None):
    """A world with day and night on. Bob is first in the founding order, so he takes the lamplighter's job; Ada is not."""
    w = World()
    w.add_actor("Bob", role="labourer", skill=0.9)
    w.add_actor("Ada", role="labourer", skill=0.9)
    dn.switch_on(w)
    return w


# ------------------------------------------------------------- the pure sky

def test_daylight_is_longer_in_summer_than_in_winter_at_the_packs_latitude():
    summer = D.sunrise_sunset(DN["summer_solstice_day"], DN)
    winter_day = (int(DN["summer_solstice_day"]) + int(TIME["days_per_year"]) // 2) % int(TIME["days_per_year"])
    winter = D.sunrise_sunset(winter_day, DN)
    assert summer[2] > winter[2]
    # The formula is in range: a northern latitude gives about 16.5 h at midsummer and 7.5 h at midwinter.
    assert 15.0 < summer[2] < 18.0
    assert 6.0 < winter[2] < 9.0


def test_a_clear_full_moon_night_is_bright_enough_to_see_and_a_new_moon_or_overcast_one_is_not():
    period = float(DN["synodic_month_days"])
    full_day = round(period / 2.0 + float(DN["new_moon_day"]))
    full = D.sky(_clock_at(full_day, 1.0), "clear", E.WEATHER, TIME, DN)
    assert full["is_night"] and full["moon_illum"] > 0.9
    assert not D.sees_dark_level(full["light_level"], DN["see_threshold"])
    new = D.sky(_clock_at(0, 1.0), "clear", E.WEATHER, TIME, DN)
    assert new["is_night"] and new["moon_illum"] < 0.01
    assert D.sees_dark_level(new["light_level"], DN["see_threshold"])
    overcast = D.sky(_clock_at(full_day, 1.0), "storm", E.WEATHER, TIME, DN)
    assert overcast["cloud"] >= 0.9
    assert D.sees_dark_level(overcast["light_level"], DN["see_threshold"])


def test_the_sky_is_a_plain_query_that_works_without_the_switch():
    w = World()
    assert not dn.on(w)
    s = dn.sky(w)
    assert set(["sunrise", "sunset", "is_night", "moon_illum", "light_level", "cloud"]) <= set(s)
    assert 0.0 <= dn.light_level(w) <= 1.0


def test_the_sky_is_written_each_tick_once_switched_on():
    w = _on()
    _set_clock(w, _clock_at(3, 12.0))
    w.tick(1)
    attrs = w.eng.node(w._town)["attrs"]
    assert attrs["sky_light"] == pytest.approx(dn.light_level(w), abs=1e-3)
    assert attrs["sky_night"] == 0.0


# ------------------------------------------------------------- seeing

def test_an_outdoor_resident_sees_beside_a_lit_lamp_and_not_beside_an_unlit_one():
    w = _on()
    _set_clock(w, _clock_at(0, 1.0))          # a new-moon night: light 0
    _set_weather(w, "clear")
    lamp_cell = next(iter(w._dn_lamps))
    beside = _beside(w, lamp_cell)
    assert not dn.indoors(w, beside)
    w._move_actor_to("Ada", beside)
    assert dn.sees_dark(w, "Ada")
    lamp = w._dn_lamps[lamp_cell]
    w.eng.set_attr(lamp, "lit", 1.0)
    w.eng.set_attr(lamp, "fuel", 1.0)
    assert not dn.sees_dark(w, "Ada")
    assert dn.view_light(w, "Ada") == "lamplight"
    w.eng.set_attr(lamp, "lit", 0.0)
    assert dn.sees_dark(w, "Ada")


def test_an_indoor_resident_never_sees_dark():
    w = _on()
    _set_clock(w, _clock_at(0, 1.0))
    site = next(iter(w._building_sites.values()))
    x, y = site[0], site[1]
    assert dn.indoors(w, (x, y))
    w._move_actor_to("Ada", (x, y))
    assert not dn.sees_dark(w, "Ada")


def test_a_lit_candle_in_hand_lets_its_holder_see():
    w = _on()
    _set_clock(w, _clock_at(0, 1.0))
    w._move_actor_to("Ada", _outdoor_cell(w))
    assert dn.sees_dark(w, "Ada")
    w.give_tool("Ada", "candle")
    candle = w._held_tool("Ada", "candle")
    assert candle is not None
    w.eng.set_attr(candle, "lit", 1.0)
    w.eng.set_attr(candle, "fuel", 1.0)
    assert not dn.sees_dark(w, "Ada")


# ------------------------------------------------------------- lamps

def test_lamps_burn_oil_and_go_out_when_it_runs_out():
    w = _on()
    lamp_cell = next(iter(w._dn_lamps))
    lamp = w._dn_lamps[lamp_cell]
    stock_before = w.qty("oil")
    w._move_actor_to("Ada", lamp_cell)
    _rest_ada(w)
    assert w.major_action("Ada", "light") is True
    attrs = w.eng.node(lamp)["attrs"]
    assert attrs["lit"] == 1.0
    assert attrs["fuel"] == pytest.approx(float(DN["lamp_fuel_capacity"]))
    assert w.qty("oil") == pytest.approx(stock_before - float(DN["lamp_fuel_capacity"]))
    burn = float(DN["lamp_burn_per_tick"])
    dn.tick(w)
    assert w.eng.node(lamp)["attrs"]["fuel"] == pytest.approx(float(DN["lamp_fuel_capacity"]) - burn)
    w.eng.set_attr(lamp, "fuel", burn / 2.0)
    dn.tick(w)
    assert w.eng.node(lamp)["attrs"]["lit"] == 0.0           # the oil is gone: the lamp is out
    assert w.eng.node(lamp)["attrs"]["fuel"] == 0.0


def test_douse_puts_a_lamp_out_and_keeps_its_oil():
    w = _on()
    lamp_cell = next(iter(w._dn_lamps))
    lamp = w._dn_lamps[lamp_cell]
    w._move_actor_to("Ada", lamp_cell)
    _rest_ada(w)
    assert w.major_action("Ada", "light") is True
    fuel = w.eng.node(lamp)["attrs"]["fuel"]
    w.tick(1)                                   # a new turn: a fresh action slot (the lamp burns one tick)
    _rest_ada(w)
    assert w.major_action("Ada", "douse") is True
    assert w.eng.node(lamp)["attrs"]["lit"] == 0.0
    # The one tick between the two actions burned a tick of oil; dousing itself takes none, and keeps the rest.
    assert w.eng.node(lamp)["attrs"]["fuel"] == pytest.approx(fuel - float(DN["lamp_burn_per_tick"]))


def test_a_lamp_with_no_oil_in_the_store_is_refused_out_of_stock():
    w = _on()
    lamp_cell = next(iter(w._dn_lamps))
    w.set_stock("oil", 0.0)
    w._move_actor_to("Ada", lamp_cell)
    _rest_ada(w)
    assert w.major_action("Ada", "light") is False
    assert w.eng.node(w._dn_lamps[lamp_cell])["attrs"]["lit"] == 0.0


def test_a_light_is_offered_only_at_a_lamp_and_only_to_a_lamplighter():
    w = _on()
    lamp_cell = next(iter(w._dn_lamps))
    w._move_actor_to("Ada", lamp_cell)
    _set_clock(w, _clock_at(0, 1.0))
    assert dn.lamp_options(w, "Ada") == []          # Ada is not the lamplighter
    lamplighter = dn.lamplighters(w)[0]
    assert lamplighter == "Bob"
    w._move_actor_to(lamplighter, lamp_cell)
    offers = dn.lamp_options(w, lamplighter)
    lights = [o for o in offers if o["action"] == "light"]
    assert len(lights) == 1 and lights[0]["lamplighter"] is True
    walks = [o["destination"] for o in offers if o["action"] == "move"]
    assert lamp_cell not in walks and len(walks) == len(w._dn_lamps) - 1   # the other unlit lamps, by walking


def test_the_lamplighter_is_appointed_and_only_the_appointed_resident_may_round():
    w = _on()
    holders = dn.lamplighters(w)
    assert len(holders) == int(DN["lamplighters"]) == 1
    assert holders[0] in w._actors
    assert w.E.DAYNIGHT["lamplighter_job"] in E.JOBS
    assert E.JOBS["lamplighter"]["fixed"] == 0.0            # not in the founding draw: appointed on switch-on


def test_the_backend_chooses_the_lamp_round_and_the_world_does_not():
    def ctx(options, hunger=0.0):
        return SimpleNamespace(affordances=options, observations={"hunger": hunger})
    assert lamplighter_choice(ctx([{"action": "move", "destination": (1, 1)}])) is None
    light = {"action": "light", "lamplighter": True}
    assert lamplighter_choice(ctx([light])) == ("light", {}, None)
    walk = {"action": "move", "destination": (18, 15), "lamplighter": True}
    action, params, continuation = lamplighter_choice(ctx([walk]))
    assert action == "move" and params == {"destination": (18, 15)} and continuation.destination == (18, 15)
    assert lamplighter_choice(ctx([light], hunger=2.0)) is None      # food first


def test_a_lamp_round_is_not_offered_to_a_resident_who_is_too_exhausted_to_walk():
    w = _on()
    lamplighter = dn.lamplighters(w)[0]
    _set_clock(w, _clock_at(0, 1.0))
    w.eng.set_attr(w._bodies[lamplighter], "stamina_reserve", 0.0)
    assert all(o["action"] != "move" for o in dn.lamp_options(w, lamplighter))


# ------------------------------------------------------------- work, travel, sight, lateness

def _carver():
    w = World()
    w.add_actor("Carver", role="woodworker", skill=0.9)
    w.set_stock("timber", 10)
    w._move_actor_to("Carver", _inside(w, "woodshop"))
    return w


def _inside(w, key):
    x, y, fw, fh = w._building_sites[key]
    return next((x + dx, y + dy) for dy in range(fh) for dx in range(fw) if (x + dx, y + dy) in w._map_cells)


def _rest_ada(w, name="Ada"):
    w.eng.set_attr(w._bodies[name], "stamina_reserve", 1.0)
    w.eng.set_attr(w._actors[name], "collapsed", 0.0)
    w.eng.set_attr(w._actors[name], "asleep", 0.0)


def _rest(w, name):
    w.eng.set_attr(w._bodies[name], "stamina_reserve", 1.0)
    w.eng.set_attr(w._actors[name], "collapsed", 0.0)
    w.eng.set_attr(w._actors[name], "asleep", 0.0)


def _ticks_to_finish(w, name, cap=2000):
    ticks = 0
    while w.busy(name) and ticks < cap:
        _rest(w, name)
        w.tick(1)
        ticks += 1
    return ticks


def _cutter():
    """A forester with an axe, on a cell in the open (split_firewood is an open recipe, no building)."""
    w = World()
    w.add_actor("Cutter", role="forester", skill=0.9)
    w.set_stock("lumber", 10)
    dn.switch_on(w)
    w._move_actor_to("Cutter", _outdoor_cell(w))
    w.give_tool("Cutter", "axe")
    return w


def _work_outdoors(clock):
    """A forester splits firewood outdoors at `clock`. Returns (ticks taken, the job's lowest fit)."""
    w = _cutter()
    _set_clock(w, clock)
    assert w.start("Cutter", "split_firewood", tool="axe")
    job = w._job_of("Cutter")
    ticks = _ticks_to_finish(w, "Cutter")
    fit_low = float(w.eng.node(job)["attrs"].get("fit_low", 1.0))
    return ticks, fit_low


def test_field_work_in_the_dark_is_slow_and_goes_normally_at_dawn():
    day_ticks, day_fit = _work_outdoors(_clock_at(4, 12.0))
    dark_ticks, dark_fit = _work_outdoors(_clock_at(0, 1.0))
    assert day_fit == pytest.approx(1.0)
    assert dark_fit == pytest.approx(float(DN["dark_work_fit"]))
    assert dark_ticks > day_ticks * 2           # progress is slowed by the visibility factor (0.3)


def test_dark_work_is_risky_and_strains_the_worker():
    w = _cutter()
    _set_clock(w, _clock_at(0, 1.0))
    assert w.start("Cutter", "split_firewood", tool="axe")
    strain = 0.0
    for _ in range(3):
        _rest(w, "Cutter")
        w.tick(1)
        strain = max(strain, float(w.eng.node(w._actors["Cutter"])["attrs"].get("strain", 0.0)))
    assert strain > 0.0                        # a poor fit strains the worker (Phase 048 path)


def test_darkness_does_not_change_a_job_indoors():
    w = _carver()
    dn.switch_on(w)
    _set_clock(w, _clock_at(0, 1.0))
    assert dn.work_visibility(w, "Carver") == 1.0


def test_witnessing_range_shortens_at_night_and_not_by_day():
    w = _on()
    _set_weather(w, "clear")
    _set_clock(w, _clock_at(0, 1.0))
    w._move_actor_to("Ada", _outdoor_cell(w))
    assert dn.sight_range(w, "Ada", 7) == int(DN["dark_sight_range"]) < 7
    _set_clock(w, _clock_at(4, 12.0))
    assert dn.sight_range(w, "Ada", 7) == 7


def test_travel_in_the_dark_is_a_table_factor_and_the_default_is_the_seed():
    w = _on()
    _set_clock(w, _clock_at(0, 1.0))
    w._move_actor_to("Ada", _outdoor_cell(w))
    assert dn.travel_factor(w, "Ada") == 1.0          # the table default: the seed's speed
    original = DN["travel_dark_factor"]
    try:
        DN["travel_dark_factor"] = 2.0
        assert dn.travel_factor(w, "Ada") == 2.0
    finally:
        DN["travel_dark_factor"] = original


def test_lateness_comes_from_the_real_sunset_while_it_is_night():
    w = _on()
    summer = int(DN["summer_solstice_day"])
    sunrise, sunset, _ = D.sunrise_sunset(summer, DN)
    _set_clock(w, _clock_at(summer, sunset + 1.5))
    facts = w.sleep_facts("Ada")
    assert facts["lateness"] == pytest.approx(1.5, abs=0.01)
    _set_clock(w, _clock_at(summer, 12.0))
    assert w.sleep_facts("Ada")["lateness"] == 0.0


def test_with_the_switch_off_lateness_is_the_hours_and_nothing_changes():
    w = World()
    _set_clock(w, _clock_at(0, 23.0))
    assert not dn.on(w)
    assert dn.lateness(w, 2.0) == 2.0
    assert dn.sight_range(w, "nobody", 7) == 7
    assert dn.work_visibility(w, "nobody") == 1.0
    assert dn.travel_factor(w, "nobody") == 1.0
    assert dn.lamp_options(w, "nobody") == []


# ------------------------------------------------------------- carried light and the view

def test_a_lexicon_view_gives_words_not_numbers_for_the_light():
    from domains.lexicon import describe
    assert describe("daylight", "dark", "self", pack="bigville")["phrase"] == "it is dark"
    assert describe("daylight", "lamplight", "self", pack="bigville")["phrase"] == "by lamplight"
    for key in ("day", "dim", "dark", "lamplight", "unknown"):
        phrase = describe("daylight", key, "other", pack="bigville")["phrase"]
        assert not any(ch.isdigit() for ch in phrase)


def test_the_agent_view_says_it_is_dark_and_by_lamplight_for_a_fogged_resident():
    from bigville.api import create_game
    game = create_game(scenario="town100", seed=305000, default_backend="simple", autonomous=True,
                       ticks_per_period="world")
    w = game.world
    dn.switch_on(w)
    actor = next(a for a in w._actors if w.is_alive(a))
    _set_clock(w, _clock_at(0, 1.0))
    w._move_actor_to(actor, _outdoor_cell(w))
    view = game.agent_view(actor)
    assert view["now"]["light"] == "it is dark"
    lamp_cell = next(iter(w._dn_lamps))
    w._move_actor_to(actor, _beside(w, lamp_cell))
    w.eng.set_attr(w._dn_lamps[lamp_cell], "lit", 1.0)
    w.eng.set_attr(w._dn_lamps[lamp_cell], "fuel", 1.0)
    assert game.agent_view(actor)["now"]["light"] == "by lamplight"


def test_with_day_and_night_off_the_agent_view_is_unchanged():
    from bigville.api import create_game
    game = create_game(scenario="town100", seed=305000, default_backend="simple", autonomous=True,
                       ticks_per_period="world")
    actor = next(a for a in game.world._actors if game.world.is_alive(a))
    assert "light" not in game.agent_view(actor)["now"]


# ------------------------------------------------------------- the balance report and the self-test

def test_the_balance_report_includes_lamp_oil_when_day_and_night_is_on(monkeypatch):
    monkeypatch.setitem(WA.DAYNIGHT, "enabled", True)
    sc = scale_scenario(100)
    flows, _, _ = WA._balance_flows(sc)
    have, need = flows["lamp oil (stock vs one period)"]
    assert have == pytest.approx(float(DN["starting_oil"]))
    assert need > 0.0


def test_the_balance_report_has_no_lamp_oil_when_day_and_night_is_off():
    sc = scale_scenario(100)
    flows, _, _ = WA._balance_flows(sc)
    assert "lamp oil (stock vs one period)" not in flows


def test_the_entity_self_test_is_clean_with_day_and_night_in_the_pack():
    report = E.check_consistency()
    assert report["errors"] == []
    assert report["warnings"] == []


def test_the_test_pack_loads_the_day_and_night_tables():
    from domains.pack import load_pack
    for name in ("bigville", "test_hamlet"):
        pack = load_pack(name)
        assert "DAYNIGHT" in pack and "DAYNIGHT_LAMPS" in pack and "DAYNIGHT_MAJOR_ACTIONS" in pack
        assert pack["DAYNIGHT"]["enabled"] is False


def test_a_pack_switched_on_must_name_its_lamp_oil_and_lamplighter():
    from domains import daynight_check as C
    dn_table = dict(E.DAYNIGHT)
    dn_table["enabled"] = True
    dn_table["oil_item"] = ""
    dn_table["lamplighter_job"] = ""
    errors, warnings, info = [], [], []
    C.check(errors, warnings, info, daynight=dn_table, lamps=E.DAYNIGHT_LAMPS, weather=E.WEATHER, jobs=E.JOBS,
            labour_tasks=E.LABOUR_TASKS, items=E.ITEMS, major_actions=E.MAJOR_ACTIONS,
            founding_map=E.FOUNDING_MAP, time=E.TIME)
    assert any("oil_item" in e for e in errors)
    assert any("lamplighter_job" in e for e in errors)
