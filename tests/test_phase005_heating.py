"""Phase 005: household heating and fuel use.

Each household burns fuel for space heat once per period (a day): HEATING base_burn x the day's weather
firewood_demand. It draws its own fuel first (member inventories, then containers at its home cell), then
the town store, and leaves the fuel's ash in the store. A household that cannot burn its need is cold: its
members' chill rises by unheated_chill x the unmet share. The balance model's fuel line carries the same
heating demand.
"""
from __future__ import annotations

import re

import pytest

from domains import bigville_entities as E
from domains import population as POP
from worlds.bigville_town100_world import SEED_DEFAULT
from worlds.bigville_world import BigvilleWorld

HOUSEHOLD = "household_000"
FUEL_KINDS = tuple(kind for kind, _units in E.type_members(E.HEATING["fuel_type"]))


@pytest.fixture
def town():
    return BigvilleWorld.from_town100(SEED_DEFAULT)


def _members(w, household=HOUSEHOLD):
    return sorted(w.household_members(household))


def _fuel_units(w, household=HOUSEHOLD):
    """Fuel units (slot units) the household can draw on: its own sources plus the town store."""
    units = dict(E.type_members(E.HEATING["fuel_type"]))
    total = sum(w._source_qty(src, kind) * units[kind]
                for _, src in w._household_fuel_sources(household) for kind in FUEL_KINDS)
    return total + sum(w.qty(kind) * units[kind] for kind in FUEL_KINDS)


def _clear_fuel(w, household=HOUSEHOLD):
    """Remove every fuel unit the household could draw on: the store, its members' inventories, and
    the containers at its home cell."""
    for kind in FUEL_KINDS:
        w.set_stock(kind, 0.0)
    for _, (_label, name) in w._household_fuel_sources(household):
        for kind in FUEL_KINDS:
            if kind in w._containers[name][1]:
                w.eng.set_attr(w._containers[name][1][kind], "qty", 0.0)


def _state(w, household=HOUSEHOLD):
    attrs = w.eng.node(w._households[household])["attrs"]
    return float(attrs["fuel_need"]), float(attrs["fuel_short"])


def _burn_and_settle(w, households=None):
    """One period's heating burn, then the body update that reads it (the chill term)."""
    w._burn_household_heat(households)
    w._run()


# ------------------------------------------------------------------ the balance model
def test_the_fuel_line_demand_grows_by_exactly_the_heating_demand():
    sc = E.BALANCE_SCENARIO
    flows_on, _, _ = E._balance_flows(sc)
    flows_off, _, _ = E._balance_flows(dict(sc, households=0))
    heat = E.heating_demand(sc)
    assert heat == pytest.approx(sc["households"] * E.HEATING["base_burn"] * E.mean_firewood_demand())
    assert heat > 0
    supply_on, demand_on = flows_on["fuel (heat)"]
    supply_off, demand_off = flows_off["fuel (heat)"]
    assert supply_on == pytest.approx(supply_off), "heating adds demand, not supply"
    assert demand_on - demand_off == pytest.approx(heat)


def test_the_balance_report_fuel_line_includes_heating():
    text = E.format_systems_report(E.analyse_systems())
    match = re.search(r"fuel \(heat\)\s+supply\s+([\d.]+)\s+demand\s+([\d.]+)", text)
    assert match, "the balance report has a fuel (heat) line"
    cooking = _cooking_fuel()
    assert float(match.group(2)) == pytest.approx(cooking + E.heating_demand(E.BALANCE_SCENARIO), abs=0.06)
    assert f"heating: {E.BALANCE_SCENARIO['households']} households burn" in text


def _cooking_fuel():
    """The fuel the staple chain alone burns per period (the balance model without heating)."""
    flows, _, _ = E._balance_flows(dict(E.BALANCE_SCENARIO, households=0))
    return flows["fuel (heat)"][1]


def test_heated_households_scale_with_the_town():
    assert POP.scale_scenario(100)["households"] == E.BALANCE_SCENARIO["households"] == 46
    assert POP.scale_scenario(30)["households"] == round(46 * 30 / 100)


def test_the_mean_firewood_demand_is_the_average_over_the_seasons_weather():
    per_season = []
    for season in E.SEASONS.values():
        values = [E.WEATHER[w]["firewood_demand"] for w in season["weather"]]
        per_season.append(sum(values) / len(values))
    assert E.mean_firewood_demand() == pytest.approx(sum(per_season) / len(per_season))


# ------------------------------------------------------------------ the burn in the world
def test_each_period_burns_base_burn_times_the_weather_and_scales_with_it(town):
    _clear_fuel(town)
    town.set_stock("wood", 500.0)
    burns = {}
    for weather in ("hot", "clear", "frost"):
        town.set_weather(weather)
        before = _fuel_units(town)
        town._burn_household_heat([HOUSEHOLD])
        need, short = _state(town)
        assert need == pytest.approx(E.HEATING["base_burn"] * E.WEATHER[weather]["firewood_demand"])
        assert short == pytest.approx(0.0, abs=1e-9), "the store covers the need"
        burns[weather] = before - _fuel_units(town)
        assert burns[weather] == pytest.approx(need), "the burnt fuel is the need"
    assert burns["hot"] < burns["clear"] < burns["frost"]


def test_a_period_burns_fuel_through_the_period_clock(town):
    _clear_fuel(town)
    town.set_stock("wood", 500.0)
    town.set_weather("frost")
    town.pass_period()
    need, short = _state(town)
    assert need == pytest.approx(E.HEATING["base_burn"] * E.WEATHER["frost"]["firewood_demand"])
    assert short == pytest.approx(0.0, abs=1e-9)


def test_a_household_draws_its_own_fuel_before_the_town_store(town):
    _clear_fuel(town)
    member = _members(town)[0]
    town.set_stock("wood", 0.1)
    assert town.fetch(member, "wood", 0.1)            # the store -> the member's own inventory
    town.set_stock("wood", 50.0)
    town.set_weather("clear")
    need = E.HEATING["base_burn"] * E.WEATHER["clear"]["firewood_demand"]

    town._burn_household_heat([HOUSEHOLD])

    assert town.inventory_qty(member, "wood") == pytest.approx(0.0), "the own fuel was burnt first"
    assert town.qty("wood") == pytest.approx(50.0 - (need - 0.1)), "only the rest came from the store"
    need_now, short = _state(town)
    assert need_now == pytest.approx(need) and short == pytest.approx(0.0, abs=1e-9)


def test_a_container_at_the_home_cell_counts_as_the_households_own_fuel(town):
    _clear_fuel(town)
    home = town.map_position(HOUSEHOLD)
    assert home is not None, "the founding household has a home cell"
    member = _members(town)[0]
    town.add_container("home_barrel", kind="barrel", holds=["wood"], cell=home)
    town._move_actor_to(member, home)
    town.set_stock("wood", 0.1)
    assert town.fill(member, "home_barrel", "wood", 0.1)
    assert town.contents("home_barrel", "wood") == pytest.approx(0.1)
    town.set_stock("wood", 50.0)
    town.set_weather("clear")

    town._burn_household_heat([HOUSEHOLD])

    assert town.contents("home_barrel", "wood") == pytest.approx(0.0)
    assert town.qty("wood") == pytest.approx(50.0 - (E.HEATING["base_burn"] * E.WEATHER["clear"]["firewood_demand"] - 0.1))


def test_a_container_at_another_cell_is_not_the_households_fuel(town):
    home = town.map_position(HOUSEHOLD)
    other = next(tuple(c) for c in town._map_cells if tuple(c) != home)
    town.add_container("far_barrel", kind="barrel", holds=["wood"], cell=other)
    sources = [src for _, src in town._household_fuel_sources(HOUSEHOLD)]
    assert ("box", "far_barrel") not in sources
    assert all(label == "own" or town.container_position(name) == home for label, name in sources if label == "box")


def test_heating_leaves_the_fuels_ash_and_soot_in_the_store(town):
    _clear_fuel(town)
    town.set_stock("wood", 50.0)
    town.set_weather("clear")
    ash0, soot0 = town.qty("ash"), town.qty("soot")
    burnt = E.HEATING["base_burn"] * E.WEATHER["clear"]["firewood_demand"]

    town._burn_household_heat([HOUSEHOLD])

    byproducts = E.INPUT_TYPES["fuel"]["byproducts"]
    assert town.qty("ash") - ash0 == pytest.approx(burnt * byproducts["ash"])
    assert town.qty("soot") - soot0 == pytest.approx(burnt * byproducts["soot"])
    assert town.qty("ash") > 0


def test_a_household_with_no_fuel_is_cold_and_its_members_chill_rises(town):
    _clear_fuel(town)
    town.set_weather("clear")                          # no town cold: the chill is the household's alone
    _burn_and_settle(town)
    need_now, short = _state(town)
    assert need_now == pytest.approx(E.HEATING["base_burn"] * E.WEATHER["clear"]["firewood_demand"])
    assert short == pytest.approx(1.0, abs=1e-9)
    for member in _members(town):
        assert town.chill(member) == pytest.approx(E.HEATING["unheated_chill"])

    town.set_stock("wood", 50.0)                       # fuel arrives: the next burn is complete
    _burn_and_settle(town)
    assert _state(town)[1] == pytest.approx(0.0, abs=1e-9)
    for member in _members(town):
        assert town.chill(member) == pytest.approx(0.0)


def test_the_chill_rises_with_the_unmet_share_of_the_need(town):
    _clear_fuel(town)
    town.set_weather("clear")
    need = E.HEATING["base_burn"] * E.WEATHER["clear"]["firewood_demand"]
    member = _members(town)[0]
    half = round(need / 2, 4)                          # qty() rounds to 4 places
    town.set_stock("wood", half)
    assert town.fetch(member, "wood", half)        # half the need, held in one member's inventory
    town.set_stock("wood", 0.0)

    _burn_and_settle(town)

    assert _state(town)[1] == pytest.approx(0.5)
    assert town.chill(member) == pytest.approx(0.5 * E.HEATING["unheated_chill"])


def test_a_pack_with_no_fuel_economy_burns_nothing(town, monkeypatch):
    monkeypatch.setitem(E.HEATING, "base_burn", 0.0)
    _clear_fuel(town)
    town.set_weather("frost")
    before = _fuel_units(town)
    town._burn_household_heat()
    assert _fuel_units(town) == pytest.approx(before)
    assert _state(town) == (0.0, 0.0)


def test_the_town_cold_adds_to_the_heating_chill(town):
    _clear_fuel(town)
    town.set_weather("frost")                          # cold = 1 on a frost day
    _burn_and_settle(town)
    member = _members(town)[0]
    assert town.chill(member) == pytest.approx(max(0.0, 1.0 - town.warmth(member)) + E.HEATING["unheated_chill"])
    town.set_stock("wood", 500.0)
    _burn_and_settle(town)
    assert town.chill(member) == pytest.approx(max(0.0, 1.0 - town.warmth(member)))
