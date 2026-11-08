"""Phase 037: one health variable, and the routes that take it down and bring it back.

Health is the actor's health_value (0 to 1). Acute harm goes through harm(), age is a daily decline, and
death is health at or below 0, recorded with its cause. The figures are the HEALTH pack table (APPROX).
"""
from __future__ import annotations

import json

import pytest

from bigville.reporting import SimulationReporter
from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World

H = E.HEALTH
DAYS = int(E.TIME["days_per_year"])
SEVEN_CAUSES = {"age", "illness", "injury", "starvation", "exhaustion", "violence", "intoxication"}


def _w(**kwargs):
    return World(autonomous_actors=False, **kwargs)


def _attrs(w, name):
    return w.eng.node(w._actors[name])["attrs"]


def _set_reserve(w, name, value):
    w.eng.set_attr(w._bodies[name], "stamina_reserve", float(value))


def _child(tmp_path, tables):
    """A child pack of bigville with the given table overrides (replaced, not merged)."""
    root = tmp_path / "child_pack"
    (root / "world").mkdir(parents=True)
    (root / "frames").mkdir()
    entries = []
    for name, value in tables.items():
        rel = f"world/{name.lower()}.json"
        (root / rel).write_text(json.dumps({"_doc": "phase 037 test override", "_types": {},
                                            "tables": {name: value}}), encoding="utf-8")
        entries.append({"name": name, "file": rel})
    (root / "pack.json").write_text(json.dumps({
        "format": 1, "name": "child_pack", "version": 1, "description": "phase 037 test child of bigville",
        "extends": "bigville", "tables": entries}), encoding="utf-8")
    return str(root)


# ------------------------------------------------------------------ one variable and its table

def test_the_table_names_the_seven_causes_and_health_has_one_home():
    assert SEVEN_CAUSES <= set(H["causes"])
    assert set(H["age_rate"]) == set(E.LIFE_STAGES) == set(H["fragility"])
    w = _w()
    w.add_actor("Ada", role="hand")
    assert "health" not in w.eng.node(w._bodies["Ada"])["attrs"], "the body keeps no copy of health"
    assert "health" not in E.ACTOR_DEFAULTS["body"]
    assert w.health("Ada") == 1.0 == w.body_state("Ada")["health"]


def test_harm_refuses_a_cause_the_table_does_not_name():
    w = _w()
    w.add_actor("Ada", role="hand")
    with pytest.raises(ValueError):
        w.harm("Ada", 0.1, "boredom")
    assert w.harm("Ada", 0.1, "violence") and w.health("Ada") == pytest.approx(0.9)


# ------------------------------------------------------------------ acute harm and death

def test_a_large_injury_kills_and_records_injury():
    w = _w()
    w.add_actor("Ada", role="hand")
    w.injure("Ada", severity=1.0, cause="a fall")
    assert not w.is_alive("Ada")
    assert _attrs(w, "Ada")["death_cause"] == "injury" and _attrs(w, "Ada")["last_cause"] == "injury"
    assert w._deaths[-1]["cause"] == "injury" and w._deaths[-1]["actor"] == "Ada"


def test_a_small_injury_does_not_kill_an_adult():
    w = _w()
    w.add_actor("Ada", role="hand")
    w.injure("Ada", severity=0.25)
    assert w.is_alive("Ada") and w.health("Ada") == pytest.approx(0.75)
    assert _attrs(w, "Ada")["health"] == "injured" and _attrs(w, "Ada")["injury"] == pytest.approx(0.25)


def test_an_infant_takes_double_the_acute_harm_and_can_die_of_what_an_adult_survives():
    assert H["fragility"]["infant"] > H["fragility"]["adult"]
    w = _w()
    w.add_actor("Bea", role="hand", life_stage="infant")
    w.add_actor("Tom", role="hand", life_stage="adult")
    w.injure("Bea", severity=0.4)
    w.injure("Tom", severity=0.4)
    assert w.health("Bea") == pytest.approx(1.0 - 0.4 * H["fragility"]["infant"])
    assert w.health("Tom") == pytest.approx(0.6)
    w.injure("Bea", severity=0.6)
    assert not w.is_alive("Bea") and w._deaths[-1]["cause"] == "injury"
    assert w.is_alive("Tom")


def test_an_elder_declines_with_age_and_dies_of_age_while_a_young_adult_does_not():
    w = _w()
    w.add_actor("Old", role="hand", life_stage="elder", age=80.0)
    w.add_actor("Young", role="hand", life_stage="adult", age=30.0)
    rate = H["age_rate"]["elder"]
    for day in range(int(round(20 * DAYS)) + 10):
        if day == DAYS:
            assert w.health("Old") == pytest.approx(1.0 - rate, abs=1e-9), "one year of elder decline"
        w._daily_life_tick()
        if not w.is_alive("Old"):
            break
    assert not w.is_alive("Old") and _attrs(w, "Old")["death_cause"] == "age"
    assert abs(day + 1 - 20 * DAYS) <= 2, f"a healthy elder at {rate} a year dies in about 20 years, not {day + 1} days"
    assert w.is_alive("Young") and w.health("Young") == 1.0, "an adult of 30 to 50 years of age does not decline"


def test_starvation_kills_at_once_by_default_and_so_the_timeline_holds():
    w = _w()
    w.add_actor("Nell", role="hand")
    for _ in range(int(E.CARE["starve_limit"])):
        w.pass_period()
    assert w.is_alive("Nell") and w.health("Nell") == 1.0, "at the limit, not past it"
    w.pass_period()
    assert not w.is_alive("Nell") and _attrs(w, "Nell")["death_cause"] == "starvation"


def test_a_softer_starvation_harm_takes_several_periods_past_the_limit(tmp_path):
    child = World(data_pack=_child(tmp_path, {"HEALTH": {**H, "starve_harm": 0.5}}), autonomous_actors=False)
    child.add_actor("Nell", role="hand")
    for _ in range(int(E.CARE["starve_limit"]) + 1):
        child.pass_period()
    assert child.is_alive("Nell") and child.health("Nell") == pytest.approx(0.5), "one period past the limit"
    child.pass_period()
    assert not child.is_alive("Nell") and _attrs(child, "Nell")["death_cause"] == "starvation"


def test_disease_drains_health_each_day_and_its_death_is_recorded_as_illness():
    w = _w()
    w.add_actor("Ada", role="hand")
    w.diagnose(None, "Ada", "fever")
    days = 0
    while w.is_alive("Ada") and days < 40:
        w._daily_life_tick()
        days += 1
    assert not w.is_alive("Ada") and _attrs(w, "Ada")["death_cause"] == "illness"
    assert w._deaths[-1]["cause"] == "illness"


# ------------------------------------------------------------------ recovery

def test_care_and_rest_recover_health_and_recovery_stops_at_the_cap():
    w = _w()
    w.add_actor("Ada", role="hand")
    w.injure("Ada", severity=0.4)
    assert w.care_for("Ada", "Ada")
    assert w.health("Ada") == pytest.approx(0.6 + E.CARE["care_health_gain"])
    w._heal("Ada", 5.0)
    assert w.health("Ada") == H["max_health"], "recovery stops at max_health"
    w._heal("Ada", 5.0)
    assert w.health("Ada") == H["max_health"]


def test_an_ordinary_sleep_restores_health_a_tick_at_a_time_and_wakes_at_the_capacity_it_has():
    w = _w()
    w.add_actor("Ada", role="hand")
    w.injure("Ada", severity=0.4)              # health 0.6, so the stamina capacity is 0.6, not 1.0
    # This test isolates the health-scaled capacity from Phase 070b's located injury: an unaimed injury lands on a
    # locus by the state-derived draw, and a back/chest/head locus also lowers stamina. Keep the ledger empty so the
    # only stamina effect here is the health scalar.
    w.embodiment["Ada"]["ledger"] = {}
    _set_reserve(w, "Ada", 0.5)
    before = w.health("Ada")
    assert w.major_action("Ada", "sleep")
    ticks = 0
    while w.asleep("Ada") and ticks < 100:
        w.tick()
        ticks += 1
    assert ticks == 4, "the reserve rises 0.03 a tick from 0.5 to the capacity of 0.6"
    assert w.stamina_reserve("Ada") == pytest.approx(w.effective_stamina("Ada"), abs=0.01), "wakes at its capacity"
    assert w.stamina_reserve("Ada") < 1.0
    gained = w.health("Ada") - before
    assert 0.0 < gained <= ticks * H["rest_health_gain"] + 1e-9, "sleep heals, at most rest_health_gain a tick"


# ------------------------------------------------------------------ exhaustion

def test_a_second_collapse_without_a_full_rest_harms_and_a_rest_ends_the_run():
    w = _w()
    w.add_actor("Ada", role="hand")
    _set_reserve(w, "Ada", 0.01)
    w._run()
    assert w.collapsed("Ada") and w.health("Ada") == 1.0, "the first collapse in a run is free"
    w._wake("Ada")
    _set_reserve(w, "Ada", 0.01)
    w._run()
    assert w.health("Ada") == pytest.approx(1.0 - H["exhaustion_harm"]) and _attrs(w, "Ada")["last_cause"] == "exhaustion"
    w._wake("Ada")
    _set_reserve(w, "Ada", 0.5)
    assert w.major_action("Ada", "sleep")
    ticks = 0
    while w.asleep("Ada") and ticks < 100:
        w.tick()
        ticks += 1
    assert _attrs(w, "Ada")["collapse_run"] == 0.0, "a full rest ends the run"
    _set_reserve(w, "Ada", 0.01)
    before = w.health("Ada")
    w._run()
    assert w.collapsed("Ada") and w.health("Ada") == pytest.approx(before), "a collapse after rest is free again"


def test_collapses_outside_the_window_do_not_count_as_a_run():
    w = _w()
    w.add_actor("Ada", role="hand")
    _set_reserve(w, "Ada", 0.01)
    w._run()
    w._wake("Ada")
    w.eng.set_attr(w._town, "period", w._town_period() + H["exhaustion_window_periods"] + 1)
    _set_reserve(w, "Ada", 0.01)
    w._run()
    assert w.collapsed("Ada") and w.health("Ada") == 1.0


def test_repeated_collapse_can_kill_with_cause_exhaustion():
    w = _w()
    w.add_actor("Ada", role="hand")
    w.eng.set_attr(w._actors["Ada"], "health_value", H["exhaustion_harm"] / 2.0)
    _set_reserve(w, "Ada", 0.01)
    w._run()
    w._wake("Ada")
    _set_reserve(w, "Ada", 0.01)
    w._run()
    assert not w.is_alive("Ada") and _attrs(w, "Ada")["death_cause"] == "exhaustion"


# ------------------------------------------------------------------ spoiled food

def _landings(seed_world_factory, meals=300):
    """Count the illness harms that spoiled meals cause, with the eater's health reset before each meal."""
    w = seed_world_factory()
    w.add_actor("Ada", role="hand")
    node = w._actors["Ada"]
    calls = []
    original = w.harm

    def counting(actor, amount, cause):
        calls.append(cause)
        return original(actor, amount, cause)

    w.harm = counting
    for _ in range(meals):
        w.eng.set_attr(node, "health_value", 1.0)
        w._record_meal("Ada", "bread", 0.0, 0.0)
    return calls


def test_a_spoiled_meal_makes_its_eater_ill_by_a_seeded_draw_at_its_risk():
    calls = _landings(_w)
    risk = float(E.meal_illness_risk("bread", 0.0))
    assert risk == pytest.approx(0.3)
    assert set(calls) == {"illness"}
    assert 0.3 * 300 - 25 <= len(calls) <= 0.3 * 300 + 25, f"{len(calls)} illnesses from 300 meals at risk {risk}"
    assert _landings(_w) == calls, "the same world draws the same meals"


def test_a_fresh_meal_never_makes_its_eater_ill():
    w = _w()
    w.add_actor("Ada", role="hand")
    original = w.harm
    calls = []
    w.harm = lambda actor, amount, cause: calls.append(cause) or original(actor, amount, cause)
    for _ in range(200):
        w._record_meal("Ada", "bread", 1.0, 1.0)
        w.eng.set_attr(w._actors["Ada"], "health_value", 1.0)
    assert calls == []


# ------------------------------------------------------------------ the report counts deaths by cause

def test_every_death_has_a_cause_and_the_report_counts_them_by_cause():
    w = _w()
    w.add_actor("Ada", role="hand")
    w.add_actor("Nell", role="hand")
    w.injure("Ada", severity=1.0)
    for _ in range(int(E.CARE["starve_limit"]) + 1):
        w.pass_period()
    assert not w.is_alive("Nell") and not w.is_alive("Ada")
    assert all(death["cause"] in H["causes"] for death in w._deaths)
    assert SimulationReporter(w).deaths_by_cause() == {"injury": 1, "starvation": 1}
