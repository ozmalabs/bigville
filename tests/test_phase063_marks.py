"""Phase 063: visible condition. Work and events leave marks on a resident (dirt, coal dust, blood, injury...),
time, rain, washing and changing clothes take them off, and the world publishes what an observer could see.
The levels and rates are APPROX design choices in packs/bigville/world/marks.json. Nothing here is random.
"""
from __future__ import annotations

import pytest

from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World


def _w():
    return World(autonomous_actors=False)


def _node(w, name):
    return w._actors[name]


def _set(w, name, kind, level):
    w.eng.set_attr(_node(w, name), f"mark_{kind}", float(level))


def _burn(w, name, ticks=400):
    """Run one charcoal burn to completion (the collier works its job with the world's own ticks)."""
    assert w.start(name, "burn_charcoal", tool="none")
    for _ in range(ticks):
        w.tick(1)
        if w.mark_level(name, "soot") > 0.0:
            return
    raise AssertionError("the charcoal burn never completed")


def _collier():
    w = _w()
    w.add_actor("Col", role="collier", skill=0.9)
    w.set_stock("wood", 20)
    return w


# ------------------------------------------------------------------ causes raise marks

def test_burning_charcoal_raises_soot_and_the_recipe_names_it():
    row = next(r for r in E.RECIPES if r["name"] == "burn_charcoal")
    assert row["marks"]["soot"] > 0
    w = _collier()
    assert w.marks("Col") == {}
    _burn(w, "Col")
    assert w.mark_level("Col", "soot") == pytest.approx(row["marks"]["soot"])
    assert w.mark_level("Col", "soiled_clothes") == pytest.approx(row["marks"]["soiled_clothes"])


def test_a_clean_resident_keeps_no_mark_attributes():
    w = _w()
    w.add_actor("Ada", role="hand")
    w._marks_period()
    w.harm("Ada", 0.0, "violence")
    assert not [k for k in w.eng.node(_node(w, "Ada"))["attrs"] if k.startswith("mark_")]
    assert w.marks("Ada") == {}


def test_violence_and_injury_leave_blood_and_visible_injury_and_illness_leaves_none():
    w = _w()
    w.add_actor("Ada", role="hand")
    w.harm("Ada", 0.2, "violence")
    assert w.mark_level("Ada", "blood") == pytest.approx(0.2 * E.MARK_HARM["violence"]["blood"])
    assert w.mark_level("Ada", "injury") == pytest.approx(0.2 * E.MARK_HARM["violence"]["injury"])
    before = w.marks("Ada")
    w.harm("Ada", 0.1, "illness")
    assert w.marks("Ada") == before


def test_a_flood_marks_every_living_resident_at_its_onset():
    w = _w()
    w.add_actor("Ada", role="hand")
    w.add_actor("Bob", role="hand")
    w.add_shock("flood_1", kind="flood")
    for name in ("Ada", "Bob"):
        assert w.mark_level(name, "mud") == pytest.approx(E.SHOCKS["flood"]["marks"]["mud"])
        assert w.mark_level(name, "wetness") == pytest.approx(E.SHOCKS["flood"]["marks"]["wetness"])


def test_a_dead_resident_gets_no_new_marks():
    w = _w()
    w.add_actor("Ada", role="hand")
    w.eng.set_attr(_node(w, "Ada"), "alive", 0.0)
    w.harm("Ada", 0.2, "violence")
    assert w.marks("Ada") == {}


# ------------------------------------------------------------------ marks fall

def test_washing_lowers_soot_and_needs_water_and_a_turn():
    w = _collier()
    _burn(w, "Col")
    w.tick(1)                                       # a new turn: the washer's slot is free
    soot = w.mark_level("Col", "soot")
    assert w.wash("Col") is False                   # no water in the store
    assert w.mark_level("Col", "soot") == pytest.approx(soot)
    w.set_stock("water", E.MARK_RULES["wash_water"] + 1.0)
    assert w.wash("Col") is True
    assert w.mark_level("Col", "soot") == pytest.approx(soot * (1.0 - E.MARK_RULES["wash_drop"]))
    assert w.qty("water") == pytest.approx(1.0)
    assert w.wash("Col") is False                   # the turn's slot is used
    assert w.mark_level("Col", "soot") == pytest.approx(soot * (1.0 - E.MARK_RULES["wash_drop"]))


def test_washing_leaves_visible_injury_alone():
    w = _w()
    w.add_actor("Ada", role="hand")
    _set(w, "Ada", "injury", 0.6)
    w.set_stock("water", E.MARK_RULES["wash_water"])
    w.tick(1)
    assert w.wash("Ada") is True
    assert w.mark_level("Ada", "injury") == pytest.approx(0.6)


def test_a_period_passing_decays_marks_through_the_period_effects():
    w = _w()
    w.add_actor("Col", role="collier")
    _set(w, "Col", "soot", 0.5)
    w.eng.set_attr(w._town, "wet", 0.0)
    w.eng.set_attr(w._town, "period", float(w._resolved_period) + 1.0)
    w._resolve_period_effects()
    assert w.mark_level("Col", "soot") == pytest.approx(0.5 - E.MARKS["soot"]["decay"])


def test_a_mark_decays_with_time_and_with_rain_but_wetness_rises_in_rain():
    w = _w()
    w.add_actor("Col", role="collier")
    _set(w, "Col", "soot", 0.5)
    w.eng.set_attr(w._town, "wet", 0.0)
    w._marks_period()                               # dry: time only
    assert w.mark_level("Col", "soot") == pytest.approx(0.5 - E.MARKS["soot"]["decay"])
    assert "wetness" not in w.marks("Col")
    w.eng.set_attr(w._town, "wet", 1.0)
    w._marks_period()                               # rain on bare skin: time and rain both take soot off
    expected = 0.5 - 2 * E.MARKS["soot"]["decay"] - E.MARKS["soot"]["rain_wash"]
    assert w.mark_level("Col", "soot") == pytest.approx(expected)
    assert w.mark_level("Col", "wetness") == pytest.approx(E.MARK_RULES["wet_gain"])


def test_a_rain_cover_that_keeps_the_rain_off_keeps_the_soot_on():
    w = _w()
    w.add_actor("Col", role="collier")
    _set(w, "Col", "soot", 0.5)
    w.eng.set_attr(_node(w, "Col"), "rain_cover", 1.0)
    w.eng.set_attr(w._town, "wet", 1.0)
    w._marks_period()
    assert w.mark_level("Col", "soot") == pytest.approx(0.5 - E.MARKS["soot"]["decay"])
    assert "wetness" not in w.marks("Col")


def test_putting_on_a_fresh_garment_drops_soiled_clothes():
    w = _w()
    w.add_actor("Ada", role="hand")
    _set(w, "Ada", "soiled_clothes", 0.8)
    coat = w.eng.add_node("ToolItem", {"kind": "coat", "quality": 1.0, "condition": 1.0, "broken": 0.0})
    assert w.wear("Ada", coat) is True
    assert w.mark_level("Ada", "soiled_clothes") == pytest.approx(0.8 - E.MARKS["soiled_clothes"]["clothes_change_drop"])


# ------------------------------------------------------------------ what the world publishes

def test_an_observer_sees_a_mark_only_within_its_range_and_light():
    w = _w()
    w.add_actor("Col", role="collier")
    _set(w, "Col", "soot", 0.5)
    _set(w, "Col", "injury", 0.5)
    near_day = {r["kind"]: r for r in w.observable_marks("Col", distance=1, light=1.0)}
    assert set(near_day) == {"soot", "injury"}
    assert near_day["soot"]["label"] == "coal dust"
    assert near_day["injury"]["notice_skill"] == "medicine"
    far = {r["kind"] for r in w.observable_marks("Col", distance=E.MARKS["soot"]["see_range"] + 1, light=1.0)}
    assert "soot" not in far and "injury" in far
    dark = {r["kind"] for r in w.observable_marks("Col", distance=1, light=0.0)}
    assert dark == set()
    assert w.observable_marks("Col", distance=None) == []


def test_a_mark_below_its_visible_level_is_not_seen_though_it_is_held():
    w = _w()
    w.add_actor("Col", role="collier")
    _set(w, "Col", "soot", E.MARKS["soot"]["visible_level"] - 0.05)
    assert w.marks("Col")["soot"] > 0
    assert w.observable_marks("Col", distance=0, light=1.0) == []


def test_the_world_publishes_the_worn_garment_kinds_beside_the_marks():
    w = _w()
    w.add_actor("Ada", role="hand")
    coat = w.eng.add_node("ToolItem", {"kind": "coat", "quality": 1.0, "condition": 1.0, "broken": 0.0})
    w.wear("Ada", coat)
    assert w.worn("Ada") == ["coat"]


# ------------------------------------------------------------------ the table and its self-test

def test_the_self_test_is_clean_for_bigville_and_the_hamlet_pack():
    errors, warnings, info = [], [], []
    E._check_marks(errors, warnings, info)
    assert errors == [] and warnings == []
    from domains.data_view import entities
    hamlet = entities("test_hamlet")
    assert hamlet.MARKS == {}
    h_errors, h_warnings, h_info = [], [], []
    hamlet._check_marks(h_errors, h_warnings, h_info)
    assert h_errors == [] and h_warnings == []


def test_the_self_test_finds_a_harm_cause_with_no_mark_row(monkeypatch):
    rows = {k: v for k, v in E.MARK_HARM.items() if k != "illness"}
    monkeypatch.setattr(E, "MARK_HARM", rows)
    errors, warnings, info = [], [], []
    E._check_marks(errors, warnings, info)
    assert any("'illness' has no row" in e for e in errors)


def test_the_self_test_finds_a_gate_no_skill_has_and_an_unknown_mark(monkeypatch):
    marks = {k: dict(v) for k, v in E.MARKS.items()}
    marks["soot"]["notice_skill"] = "not_a_skill"
    monkeypatch.setattr(E, "MARKS", marks)
    errors, warnings, info = [], [], []
    E._check_marks(errors, warnings, info)
    assert any("notice_skill" in e and "not_a_skill" in e for e in errors)


def test_the_self_test_finds_a_recipe_that_names_an_unknown_mark(monkeypatch):
    recipes = [dict(r) for r in E.RECIPES]
    recipes[0] = dict(recipes[0], marks={"soott": 0.3})
    monkeypatch.setattr(E, "RECIPES", recipes)
    errors, warnings, info = [], [], []
    E._check_marks(errors, warnings, info)
    assert any("'soott' is not a MARKS kind" in e for e in errors)
