"""Phase 044: pregnancy and birth, behind the births switch (physical_subsystems.births, off by default).

Figures come from the BIRTHS pack table (APPROX). The tests that need a birth to happen on a day set the
delivery's three chances (stillbirth, maternal and first-year death) so the outcome is fixed, or read the
seeded draw the world itself uses, so each test says exactly what it checks.
"""
from __future__ import annotations

import math

import pytest

from bigville.backends.protocol import ActorResponse
from domains import bigville_entities as E
from domains import fertility_check as FC
from worlds.bigville_world import BigvilleWorld as World

TABLE = E.BIRTHS


def _w(*, births=True, seed=305000):
    return World.from_town100(seed=seed, physical_subsystems={"births": births})


def _attrs(w, name):
    return w.eng.node(w._actors[name])["attrs"]


def _day(w):
    return int(float(w.calendar()["day"]))


def _set_day(w, day):
    w.eng.set_attr(w._town, "day", float(day))


def _union_women(w, low=25, high=40):
    out = []
    for name in w._actors:
        a = _attrs(w, name)
        if a.get("kin_sex") == "female" and low <= float(a["age"]) <= high and w._union_partner(name) is not None:
            out.append(name)
    return out


def _fixed_delivery(w, monkeypatch, **chances):
    """Set the delivery chances. Anything not named is zero, so a birth is a live birth with no deaths."""
    values = {"stillbirth": 0.0, "maternal_death": 0.0, "infant_first_year_death": 0.0}
    values.update(chances)
    for key, value in values.items():
        monkeypatch.setitem(w.E.BIRTHS, key, value)


def _pregnant_woman(w):
    mother = _union_women(w)[0]
    _set_day(w, 100)
    w._conceive(mother, w._union_partner(mother), _day(w))
    return mother


# ------------------------------------------------------------------ the table, the switch, the self-test

def test_the_switch_is_off_by_default_and_the_table_is_in_both_packs():
    assert World().physical_subsystems["births"] is False
    assert TABLE["gestation_days"] == 270
    assert TABLE["fertile_age_min"] == 15 and TABLE["fertile_age_max"] == 49
    from domains.data_view import entities
    assert entities("test_hamlet").BIRTHS["gestation_days"] == 270


def test_the_self_test_reports_zero_errors_and_the_births_rows():
    report = E.check_consistency()
    assert report["errors"] == []
    assert report["warnings"] == []
    births = [line for line in report["info"] if line.startswith("BIRTHS")]
    assert any("entering at 25.5" in line for line in births)


def test_with_the_switch_off_the_population_is_fixed_and_no_one_conceives(monkeypatch):
    w = _w(births=False)
    monkeypatch.setitem(w.E.BIRTHS, "conception_per_year", [{"age_min": 15, "age_max": 49, "rate": 1.0}])
    before = len(w._actors)
    for _ in range(120):
        w._births_day()
    assert len(w._actors) == before
    assert not any(float(_attrs(w, n).get("pregnant", 0.0)) == 1.0 for n in w._actors)


def test_the_switch_off_leaves_the_body_read_offs_and_the_rates_alone():
    w = _w(births=False)
    mother = _union_women(w)[0]
    w.eng.set_attr(w._actors[mother], "pregnant", 1.0)
    w.eng.set_attr(w._actors[mother], "conceived_day", 0.0)
    assert w._hunger_rate(mother) == 1.0
    assert w._capacity_factor(mother) == 1.0
    assert set(w.body_state(mother)).isdisjoint({"pregnant", "term_fraction", "nursed"})


# ------------------------------------------------------------------ fertility and the seeded stream

def test_conception_rate_follows_the_table_for_a_seeded_stream(monkeypatch):
    """With a conception rate of 1 a year, each union woman conceives in a year with chance 1 - e^-1 (about 0.63).
    Over the union women of one seed, the count of first conceptions in 360 days is within three standard
    deviations of n x 0.632."""
    w = _w()
    monkeypatch.setitem(w.E.BIRTHS, "conception_per_year", [{"age_min": 15, "age_max": 49, "rate": 1.0}])
    women = _union_women(w)
    conceived = set()
    for day in range(360):
        _set_day(w, day)
        w._births_day()
        for name in women:
            if float(_attrs(w, name).get("pregnant", 0.0)) == 1.0 and name not in conceived:
                conceived.add(name)
    p = 1.0 - math.exp(-1.0)
    expected, sd = len(women) * p, math.sqrt(len(women) * p * (1.0 - p))
    assert abs(len(conceived) - expected) <= 3 * sd, (len(conceived), expected)


def test_the_world_stream_is_seeded_and_does_not_use_the_world_rng():
    a, b = _w(), _w()
    key = ("births", "conceive", "Ada", 17)
    assert a._stable_draw(*key) == b._stable_draw(*key)
    assert a._stable_draw(*key) != _w(seed=305001)._stable_draw(*key)
    assert not hasattr(a, "_rng"), "the world keeps no shared RNG"
    a._births_day()
    assert not hasattr(a, "_rng")


def test_only_a_union_woman_of_fertile_age_with_a_living_partner_can_conceive():
    w = _w()
    woman = _union_women(w)[0]
    assert w._conception_rate(12.0) == 0.0 and w._conception_rate(50.0) == 0.0
    assert w._conception_rate(float(_attrs(w, woman)["age"])) > 0.0
    partner = w._union_partner(woman)
    if w.eng.node(partner)["type"] == "Agent":
        w.record_death(w._partner_name(partner), cause="age")
    else:
        w.eng.set_attr(partner, "kin_dead", 1.0)
    assert w._union_partner(woman) is None


# ------------------------------------------------------------------ pregnancy, delivery and birth

def test_a_pregnancy_carries_to_the_due_day_and_delivers_a_newborn(monkeypatch):
    w = _w()
    _fixed_delivery(w, monkeypatch)
    mother = _pregnant_woman(w)
    partner = w._union_partner(mother)
    due = float(_attrs(w, mother)["due_day"])
    assert due == 100.0 + TABLE["gestation_days"]
    readoff = w.body_state(mother)
    assert readoff["pregnant"] == 1 and readoff["term_fraction"] == 0.0
    assert w.pregnancy(mother)["due_day"] == due
    n0 = len(w._actors)
    _set_day(w, due - 1)
    w._births_day()
    assert len(w._actors) == n0 and w.pregnancy(mother) is not None
    _set_day(w, due)
    w._births_day()
    assert len(w._actors) == n0 + 1
    assert w.pregnancy(mother) is None
    child = w._births[-1]["child"]
    attrs = _attrs(w, child)
    assert attrs["life_stage"] == "infant" and attrs["age"] == 0.0
    assert attrs["mother"] == mother and attrs["kin_sex"] in ("female", "male")
    assert float(attrs["kin_birth"]) == pytest.approx(w._kin_clock())
    assert w.eng.has_node(partner) and w.eng.node(partner)["type"] != "Agent"
    assert w.genealogical_kin(mother, child)[0] == "child"
    assert attrs["household"] == _attrs(w, mother)["household"]
    assert float(_attrs(w, mother)["birth_block_until"]) == due + TABLE["postpartum_block_days"]


def test_a_newborn_keeps_the_mothers_surname_and_is_not_already_a_resident(monkeypatch):
    w = _w()
    _fixed_delivery(w, monkeypatch)
    mother = _pregnant_woman(w)
    name = w._newborn_name(mother, 100)
    assert name not in w._actors
    assert name.split()[-1] == mother.split()[-1]


def test_a_stillbirth_is_recorded_and_adds_no_resident(monkeypatch):
    w = _w()
    _fixed_delivery(w, monkeypatch, stillbirth=1.0)
    mother = _pregnant_woman(w)
    n0 = len(w._actors)
    _set_day(w, float(_attrs(w, mother)["due_day"]))
    w._births_day()
    assert len(w._actors) == n0
    assert w._stillbirth_log[-1]["mother"] == mother
    assert w.pregnancy(mother) is None and w.is_alive(mother)


def test_a_maternal_death_is_recorded_with_cause_childbirth(monkeypatch):
    w = _w()
    _fixed_delivery(w, monkeypatch, maternal_death=1.0)
    mother = _pregnant_woman(w)
    _set_day(w, float(_attrs(w, mother)["due_day"]))
    w._births_day()
    assert not w.is_alive(mother)
    assert w._deaths[-1]["cause"] == "childbirth"
    assert "childbirth" in E.HEALTH["causes"] and "childbirth" in E.MARK_HARM


def test_a_midwife_in_reach_halves_the_maternal_risk(monkeypatch):
    """The maternal draw is fixed by the seed. Set the risk just above it: a mother with no midwife dies, and a
    mother with one in reach (midwife_factor 0.5) lives, because her risk is then below the same draw."""
    base = _w()
    mother = _union_women(base)[0]
    due = 100 + TABLE["gestation_days"]
    draw = base._stable_draw("births", "maternal", mother, due)
    assert draw > 0.0
    outcomes = {}
    for with_midwife in (False, True):
        w = _w()
        _fixed_delivery(w, monkeypatch, maternal_death=draw + 1e-6)
        cell = w.actor_position(mother)
        if with_midwife:
            w.add_actor("Mid", role="midwife", home_cell=cell)
            w._move_actor_to("Mid", cell)
            assert w.skill_level("Mid", "midwifery") > 0.0
        mother_w = _pregnant_woman(w)
        assert mother_w == mother
        _set_day(w, due)
        w._births_day()
        outcomes[with_midwife] = w.is_alive(mother)
    assert outcomes == {False: False, True: True}


def test_a_deliveries_draws_are_repeatable_for_a_seed(monkeypatch):
    first, second = _w(), _w()
    for w in (first, second):
        _fixed_delivery(w, monkeypatch)
    m1, m2 = _pregnant_woman(first), _pregnant_woman(second)
    assert m1 == m2 and first._newborn_name(m1, 100) == second._newborn_name(m2, 100)


# ------------------------------------------------------------------ the costs of pregnancy

def test_a_pregnancy_raises_food_need_and_lowers_work_capacity_late_in_term(monkeypatch):
    w = _w()
    mother = _pregnant_woman(w)
    _set_day(w, 100)
    assert w._hunger_rate(mother) == pytest.approx(TABLE["pregnancy_food"])
    base = w._effective_body_stat(mother, "str_base", "str_train")
    assert w._capacity_factor(mother) == pytest.approx(1.0)
    load = TABLE["pregnancy_load"]
    w.eng.set_attr(w._actors[mother], "conceived_day", 100.0 - 0.75 * TABLE["gestation_days"])
    expected = 1.0 - load["max_load"] * (0.75 - load["from_term"]) / (1.0 - load["from_term"])
    assert w._capacity_factor(mother) == pytest.approx(expected)
    assert w._effective_body_stat(mother, "str_base", "str_train") == pytest.approx(base * expected)


def test_a_nursed_infant_takes_no_food_and_an_orphan_takes_its_life_stage_food(monkeypatch):
    w = _w()
    _fixed_delivery(w, monkeypatch)
    mother = _pregnant_woman(w)
    _set_day(w, float(_attrs(w, mother)["due_day"]))
    w._births_day()
    child = w._births[-1]["child"]
    assert w._hunger_rate(child) == TABLE["nursed_hunger"]
    w.eng.set_attr(w._actors[mother], "alive", 0.0)
    assert w._hunger_rate(child) == pytest.approx(E.LIFE_STAGES["infant"]["food"])


# ------------------------------------------------------------------ persistence and the game

def test_a_checkpoint_round_trip_keeps_a_pregnancy_and_a_newborn(monkeypatch, tmp_path):
    from bigville.world_persistence import load_world_checkpoint, save_world_checkpoint
    w = _w()
    _fixed_delivery(w, monkeypatch)
    mother = _pregnant_woman(w)
    save_world_checkpoint(w, tmp_path / "pregnant")
    restored = load_world_checkpoint(tmp_path / "pregnant")
    assert restored.pregnancy(mother) == w.pregnancy(mother)
    assert restored.physical_subsystems["births"] is True
    _set_day(restored, float(_attrs(restored, mother)["due_day"]))
    restored._births_day()
    child = restored._births[-1]["child"]
    save_world_checkpoint(restored, tmp_path / "newborn")
    back = load_world_checkpoint(tmp_path / "newborn")
    assert child in back._actors and child in back._actor_minds
    assert back.genealogical_kin(mother, child)[0] == "child"
    assert back.pregnancy(mother) is None


def test_the_game_gives_a_newborn_a_character_and_a_dependent_backend(monkeypatch):
    from bigville.game import BigvilleGame
    from bigville.resident_births import DependentBackend
    w = _w()
    _fixed_delivery(w, monkeypatch)
    game = BigvilleGame(w, autonomous=True, ticks_per_period="world")
    mother = _pregnant_woman(w)
    _set_day(w, float(_attrs(w, mother)["due_day"]))
    w._births_day()
    child = w._births[-1]["child"]
    game.step()
    assert child in game.characters and isinstance(game.backends[child], DependentBackend)
    response = game.backends[child].decide(None)
    assert isinstance(response, ActorResponse) and response.major_action is None
    assert game.backends[child].dump_held_state().character_id == child


# ------------------------------------------------------------------ the arithmetic

def test_the_completed_family_arithmetic_matches_its_limits():
    bands = [{"age_min": 15, "age_max": 49, "rate": 0.0}]
    assert FC.completed_family(bands, gestation_days=270, postpartum_days=360, entry_age=25, end_age=50,
                               days_per_year=360) == 0.0
    fast = [{"age_min": 15, "age_max": 49, "rate": 1000.0}]
    slow = [{"age_min": 15, "age_max": 49, "rate": 1.0}]
    kw = dict(gestation_days=270, postpartum_days=360, entry_age=25, end_age=50, days_per_year=360)
    assert FC.completed_family(fast, **kw) > FC.completed_family(slow, **kw) > 0.0
    assert FC.births_per_union_year(slow, age=30, days_per_year=360, gestation_days=270,
                                    postpartum_days=360) < 1.0 / (630 / 360.0)
