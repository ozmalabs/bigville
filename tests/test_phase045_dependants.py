"""Phase 045: infants, dependants and coming of age, behind the dependants switch (DEPENDANTS.enabled, off by
default). The figures come from the DEPENDANTS pack table (APPROX, design figures). Each test builds a small
village by hand (a mother, a household, and the dependants the test needs) so it says exactly what it checks.
"""
from __future__ import annotations

import pytest

from domains import bigville_entities as E
from domains.data_view import entities
from domains.dependants import growth_fraction, neglect_harm
from worlds.bigville_world import BigvilleWorld as World

TABLE = E.DEPENDANTS


def _village(monkeypatch, *, on=True, seed=305000):
    """A world with a household H1 whose mother Mum stands on the home cell. Returns (world, home, far cell)."""
    w = World(autonomous_actors=False, map_seed=seed, physical_subsystems={})
    monkeypatch.setitem(w.E.DEPENDANTS, "enabled", on)
    cells = sorted(w._map_cells)
    home = cells[0]
    far = next(c for c in cells if c != home)
    w.add_household("H1", home_cell=home)
    w.add_actor("Mum", role="hand", home_cell=home, age=30.0)
    w.assign_household("Mum", "H1")
    w._move_actor_to("Mum", home)
    return w, home, far


def _dependant(w, name, cell, stage, age):
    w.add_actor(name, role="child", home_cell=cell, life_stage=stage, age=age)
    w.assign_household(name, "H1")
    w._move_actor_to(name, cell)


def _attrs(w, name):
    return w.eng.node(w._actors[name])["attrs"]


def _body(w, name):
    return w.eng.node(w._bodies[name])["attrs"]


def _stock_bread(w, who, qty):
    stock = w._inventory_stock(who, "bread", create=True)
    w.eng.set_attr(stock, "qty", float(qty))


def _events(w, kind):
    return [w.eng.node(e)["attrs"]["kind"] for e in w._events.values()].count(kind)


# ------------------------------------------------------------------ the table, the switch, the self-test

def test_the_switch_is_off_by_default_and_both_packs_carry_the_table():
    assert World().E.DEPENDANTS["enabled"] is False
    assert entities("test_hamlet").DEPENDANTS["stages"] == ["infant", "child", "youth"]
    assert TABLE["stages"] == ["infant", "child", "youth"]


def test_the_self_test_has_no_errors_or_warnings_and_reports_the_growth_curve():
    report = E.check_consistency()
    assert report["errors"] == []
    assert report["warnings"] == []
    lines = [line for line in report["info"] if line.startswith("DEPENDANTS")]
    assert any("at age 0 strength is 0.300" in line for line in lines)
    assert any("at age 18 strength is 1.000" in line for line in lines)


def test_the_self_test_rejects_a_neglect_span_with_no_stage(monkeypatch):
    monkeypatch.setitem(TABLE["neglect_after_days"], "infant", -1)
    report = E.check_consistency()
    assert any("neglect_after_days" in err for err in report["errors"])


# ------------------------------------------------------------------ the pure arithmetic

def test_growth_is_linear_from_the_start_value_to_the_adult_value_and_holds_there():
    assert growth_fraction(0.0, 0.3, 18.0) == pytest.approx(0.3)
    assert growth_fraction(9.0, 0.3, 18.0) == pytest.approx(0.65)
    assert growth_fraction(18.0, 0.3, 18.0) == pytest.approx(1.0)
    assert growth_fraction(40.0, 0.3, 18.0) == pytest.approx(1.0)


def test_neglect_harm_waits_out_its_span_and_scales_with_the_care_need():
    assert neglect_harm(1.0, 1, 1, 0.02) == 0.0
    assert neglect_harm(1.0, 2, 1, 0.02) == pytest.approx(0.02)
    assert neglect_harm(0.5, 2, 1, 0.02) == pytest.approx(0.01)


# ------------------------------------------------------------------ the switch off

def test_with_the_switch_off_an_infant_acts_nothing_grows_and_no_dependant_act_is_offered(monkeypatch):
    w, home, far = _village(monkeypatch, on=False)
    _dependant(w, "Baby", home, "infant", 0.5)
    before = _body(w, "Baby")["str_base"]
    w._dependants_day()
    assert _body(w, "Baby")["str_base"] == before
    assert w._dependant_refusal("Baby") is None
    assert w._dependant_work_factor("Baby") == 1.0
    assert w._dependant_options("Mum") == []
    assert "dependant" not in w.body_state("Baby")
    assert w.major_action("Baby", "move", destination=far) is True


# ------------------------------------------------------------------ infants and children

def test_an_infant_is_refused_every_major_action_with_the_reason_infant(monkeypatch):
    w, home, far = _village(monkeypatch)
    _dependant(w, "Baby", home, "infant", 0.5)
    assert w.major_action("Baby", "move", destination=far) is False
    assert w.last_outcome("Baby")["reason"] == "infant"
    assert w.enact_plan("Baby", {"action": "move", "destination": far}) is False
    assert w.last_outcome("Baby")["reason"] == "infant"
    assert w.refusals("Baby")[-1]["reason"] == "infant"
    assert w.actor_position("Baby") == home


def test_an_age_in_the_gap_between_two_bands_is_the_band_below_only_with_the_switch_on(monkeypatch):
    w, home, far = _village(monkeypatch, on=False)
    assert w._age_stage(3.5) == "elder"                    # HEAD's whole-year rule, switch off
    monkeypatch.setitem(w.E.DEPENDANTS, "enabled", True)
    assert w._age_stage(3.5) == "infant"
    assert w._age_stage(3.0) == "infant"
    assert w._age_stage(12.5) == "child"
    assert w._age_stage(17.5) == "youth"
    assert w._age_stage(18.0) == "adult"
    assert w._age_stage(64.5) == "adult"
    assert w._age_stage(65.0) == "elder"


def test_a_child_aged_three_and_a_half_is_not_treated_as_an_elder_at_the_dawn_tick(monkeypatch):
    w, home, far = _village(monkeypatch)
    _dependant(w, "Baby", home, "infant", 3.5)
    w.eng.set_attr(w._town, "day", float(int(float(w.calendar()["day"])) + 1))
    w._daily_life_tick()
    assert _attrs(w, "Baby")["life_stage"] == "infant"
    assert w._is_dependant("Baby")
    assert w.health("Baby") == pytest.approx(1.0)


def test_a_child_acts_and_its_force_scales_with_its_work_fraction(monkeypatch):
    w, home, far = _village(monkeypatch)
    _dependant(w, "Kid", home, "child", 6.0)
    assert w.major_action("Kid", "move", destination=far) is True
    assert w.actor_position("Kid") == far
    on = w.effective_strength("Kid")
    adult = w.effective_strength("Mum")
    monkeypatch.setitem(w.E.DEPENDANTS, "enabled", False)
    assert on == pytest.approx(0.25 * w.effective_strength("Kid"))
    assert adult == pytest.approx(w.effective_strength("Mum"))


def test_growth_runs_from_the_infant_value_to_the_adult_default(monkeypatch):
    w, home, far = _village(monkeypatch)
    adult_default = float(E.ACTOR_DEFAULTS["body"]["str_base"])
    _dependant(w, "Baby", home, "infant", 0.0)
    values = []
    for age in (0.0, 4.0, 12.0, 17.9):
        w.eng.set_attr(w._actors["Baby"], "age", age)
        w._dependants_day()
        values.append(_body(w, "Baby")["str_base"])
    assert values == sorted(values)
    assert values[0] == pytest.approx(adult_default * 0.3)
    assert values[-1] == pytest.approx(adult_default * growth_fraction(17.9, 0.3, 18.0))
    assert _body(w, "Mum")["str_base"] == pytest.approx(adult_default)


# ------------------------------------------------------------------ care and neglect

def test_an_attended_infant_is_not_harmed_and_an_unattended_one_is_after_its_span(monkeypatch):
    w, home, far = _village(monkeypatch)
    _dependant(w, "Baby", home, "infant", 0.5)
    for _ in range(5):
        w._dependants_day()
    assert w.health("Baby") == pytest.approx(1.0)
    assert _attrs(w, "Baby")["care_days"] == pytest.approx(5.0)
    w._move_actor_to("Mum", far)
    w._dependants_day()                     # first day unattended: within the infant's one-day span
    assert w.health("Baby") == pytest.approx(1.0)
    w._dependants_day()                     # second day: neglect harm, doubled by the infant's fragility
    assert w.health("Baby") < 1.0
    assert w.eng.node(w._actors["Baby"])["attrs"]["last_cause"] == "neglect"
    assert _attrs(w, "Baby")["neglect_days"] == pytest.approx(2.0)


def test_a_caregiver_feeds_a_hungry_dependant_on_its_cell_and_not_from_afar(monkeypatch):
    w, home, far = _village(monkeypatch)
    _dependant(w, "Baby", home, "infant", 0.5)
    _stock_bread(w, "Mum", 2)
    w.eng.set_attr(w._actors["Baby"], "hunger", 0.8)
    w._turn = 1
    w._move_actor_to("Mum", far)
    assert w.major_action("Mum", "care", patient="Baby", care_kind="feed") is False
    assert w.last_outcome("Mum")["reason"] == "not_in_reach"
    assert _attrs(w, "Baby")["hunger"] == pytest.approx(0.8)
    w._move_actor_to("Mum", home)
    assert w.major_action("Mum", "care", patient="Baby", care_kind="feed") is True
    assert _attrs(w, "Baby")["hunger"] < 0.8
    assert w.inventory_qty("Mum", "bread") == pytest.approx(1.0)


def test_a_caregiver_is_offered_the_walk_to_a_dependant_only_when_no_one_attends_it(monkeypatch):
    w, home, far = _village(monkeypatch)
    _dependant(w, "Kid", far, "child", 6.0)
    walks = [o for o in w.actor_affordances("Mum") if o.get("dependant") == "Kid"]
    assert [o["action"] for o in walks] == ["move"]
    assert walks[0]["destination"] == far
    w.add_actor("Aunt", role="hand", home_cell=far, age=40.0)
    w.assign_household("Aunt", "H1")
    w._move_actor_to("Aunt", far)
    assert [o for o in w.actor_affordances("Mum") if o.get("dependant") == "Kid"] == []


def test_a_youth_who_grows_up_comes_of_age_once_and_is_announced(monkeypatch):
    w, home, far = _village(monkeypatch)
    _dependant(w, "Teo", home, "youth", 17.9)
    w._dependants_day()
    w.eng.set_attr(w._actors["Teo"], "age", 18.0)
    w._dependants_day()
    w._dependants_day()
    assert _attrs(w, "Teo")["adult"] == 1.0
    assert _events(w, "coming_of_age") == 1
    assert _attrs(w, "Mum").get("adult", 0.0) != 1.0
    assert _events(w, "coming_of_age") == 1


# ------------------------------------------------------------------ the backends

def test_the_simple_caregiver_feeds_its_infant_without_help(monkeypatch):
    from bigville.game import BigvilleGame
    w, home, far = _village(monkeypatch)
    _dependant(w, "Baby", home, "infant", 0.5)
    _stock_bread(w, "Mum", 2)
    w.eng.set_attr(w._actors["Baby"], "hunger", 0.9)
    game = BigvilleGame(w, autonomous=True, ticks_per_period="world")
    game.step()
    assert game.backends["Mum"].last_choice["reason"] == "feed_dependant"
    assert w.last_outcome("Mum")["action"] == "care"
    assert w.inventory_qty("Mum", "bread") == pytest.approx(1.0)


def test_a_newborn_is_dependent_until_it_is_a_child_and_then_acts(monkeypatch):
    from bigville.game import BigvilleGame
    from bigville.resident_births import DependentBackend
    from bigville.backends.cheap import CheapBackend
    w, home, far = _village(monkeypatch)
    game = BigvilleGame(w, autonomous=True, ticks_per_period="world")
    _dependant(w, "Newb", home, "infant", 0.1)
    game.step()
    assert isinstance(game.backends["Newb"], DependentBackend)
    assert game.backends["Newb"].decide(None).major_action is None
    w.eng.set_attr(w._actors["Newb"], "life_stage", "child")
    w.eng.set_attr(w._actors["Newb"], "age", 4.0)
    game.step()
    assert isinstance(game.backends["Newb"], CheapBackend)
    _dependant(w, "Tiny", home, "infant", 0.1)
    game.step()
    assert isinstance(game.backends["Tiny"], DependentBackend)
