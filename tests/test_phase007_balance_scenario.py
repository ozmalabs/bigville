"""Phase 007: the balance model's founding-town scenario agrees with the town the world builds.

`population.BALANCE_SCENARIO` (packs/bigville/population/balance_scenario.json) describes the founding
town the balance model assumes. `BigvilleWorld.balance_scenario()` reports the same shape from a built
world. Counts and fixed values must agree exactly. Parameters of the model (food per resident, the
staple, the working minutes) are not facts of the world; they are checked against their pack source.

The grain beds once disagreed (61 built against 80 described); the supervisor fixed the world
(`_seed_village_crops` sows the scenario's beds) and the barley and oats seed (27 and 26), see
docs/phases/phase007/PHASE007_REPORT.md.
"""
from __future__ import annotations

import copy
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from worlds.bigville_world import BigvilleWorld  # noqa: E402

GRAIN_KEYS = ("wheat", "barley", "oats")
# Facts of the built world that the table states (exact agreement).
FACT_KEYS = ("residents", "households", "beds", "plots", "plot_area", "soil", "animals",
             "pasture_area", "water_sources")
# Parameters of the balance model: not facts of the world.
PARAMETER_KEYS = ("food_per_resident", "staple", "work_minutes_per_resident")
# Read by the balance model with a default when absent from the table (world_affordances: sc.get).
OPTIONAL_KEYS = ("woodland",)
EXACT_KEYS = ("residents", "households", "plots", "plot_area", "soil", "pasture_area",
              "water_sources", "animals", "woodland")


def compare(scenario, built):
    """Disagreements between a BALANCE_SCENARIO table and a built world's balance_scenario().

    Returns {key: (scenario value, built value)} for each differing key. Beds are compared for the
    scenario's own crops only. A table without `woodland` means the model's default of 1.0 woodlot.
    """
    out = {}
    for key in EXACT_KEYS:
        if key == "woodland":
            want, got = float(scenario.get("woodland", 1.0)), float(built["woodland"])
        else:
            want, got = scenario[key], built[key]
        if want != got:
            out[key] = (want, got)
    beds = {c: (n, built["beds"].get(c, 0)) for c, n in scenario["beds"].items()
            if n != built["beds"].get(c, 0)}
    if beds:
        out["beds"] = beds
    return out


@pytest.fixture(scope="module")
def town():
    return BigvilleWorld.from_town100()


@pytest.fixture(scope="module")
def built(town):
    return town.balance_scenario()


@pytest.fixture(scope="module")
def scenario(town):
    return town.E.BALANCE_SCENARIO


def test_the_world_reports_the_fact_keys_and_the_table_has_no_others(built, scenario):
    assert set(built) == set(FACT_KEYS) | set(OPTIONAL_KEYS)
    assert set(scenario) == set(FACT_KEYS) | set(PARAMETER_KEYS)


def test_counts_and_fixed_values_agree_exactly_for_the_100_town(built, scenario, town):
    assert compare(scenario, built) == {}
    assert built["residents"] == scenario["residents"] == len(town._actors) == 100
    assert built["households"] == scenario["households"] == 46
    assert built["plots"] == scenario["plots"] == 8
    assert built["plot_area"] == scenario["plot_area"] == 1.0
    assert built["soil"] == scenario["soil"] == "loam"
    assert built["pasture_area"] == scenario["pasture_area"] == 4.0
    assert built["animals"] == scenario["animals"]
    assert built["water_sources"] == scenario["water_sources"]
    assert built["woodland"] == 1


def test_grain_beds_agree_with_the_scenario(built, scenario):
    assert {c: built["beds"].get(c, 0) for c in GRAIN_KEYS} == {c: scenario["beds"][c] for c in GRAIN_KEYS}


def test_the_built_beds_outside_the_scenario_are_one_garden_bed_per_starting_crop(built, scenario, town):
    garden = {c: n for c, n in built["beds"].items() if c not in scenario["beds"]}
    assert set(garden) == set(town.E.STARTING_CROPS) - set(scenario["beds"])
    assert set(garden.values()) == {1}


def test_parameters_are_checked_against_their_pack_source(town, scenario):
    # food_per_resident: the recipes doc in the pack defines one loaf as one resident's bread per period.
    with open(os.path.join(_ROOT, "packs", "bigville", "world", "recipes.json"), encoding="utf-8") as fh:
        recipes_doc = json.load(fh)["_doc"]
    assert "a loaf is one resident's bread for a period" in recipes_doc
    assert scenario["food_per_resident"] == 1.0
    # staple: the built town defines that recipe, and it bakes 60 loaves of bread per batch.
    staple = town._recipe_specs.get(scenario["staple"])
    assert staple is not None and list(staple["out"]) == ["bread", 60]
    # work_minutes_per_resident: no pack source (APPROX). Checked against the length of one period.
    time = town.E.TIME
    period_minutes = float(time["minutes_per_tick"]) * float(time["ticks_per_period"])
    assert 0 < scenario["work_minutes_per_resident"] <= period_minutes


def test_a_drifting_scenario_is_reported(built, scenario):
    assert compare(scenario, built) == {}
    drifted = copy.deepcopy(scenario)
    drifted["residents"] = 99
    drifted["animals"]["cow"] = 2
    drifted["water_sources"] = drifted["water_sources"][:-1]
    drifted["plots"] = 9
    report = compare(drifted, built)
    assert report["residents"] == (99, 100)
    assert report["animals"] == (drifted["animals"], built["animals"])
    assert report["water_sources"] == (drifted["water_sources"], built["water_sources"])
    assert report["plots"] == (9, 8)
