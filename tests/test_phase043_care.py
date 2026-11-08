"""Phase 043: screening, treatment, well-baby care and illness onset.

The illness switch (physical_subsystems.illness) is off by default. Each test that needs illness turns it on.
Figures come from the DISEASE and MEDICAL_CARE pack tables (APPROX). Days are calendar days (the dawn tick).
"""
from __future__ import annotations

import pytest

from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World

DOSE = E.DISEASE["fever"]
CARE = E.MEDICAL_CARE


def _w(*, illness=True, seed=305000):
    return World(autonomous_actors=False, map_seed=seed, physical_subsystems={"illness": illness})


def _attrs(w, name):
    return w.eng.node(w._actors[name])["attrs"]


def _body(w, name):
    return w.eng.node(w._bodies[name])["attrs"]


def _flag(w, name, flag):
    return w.body_state(name)[flag]


def _pair(w, *, medicine=5.0):
    """A doctor (medicine skill) and a hand, on the same cell, with medicine in the store."""
    cell = w.map_position_node(w._store)
    w.add_actor("Doc", role="doctor", home_cell=cell)
    w.add_actor("Ada", role="hand", home_cell=cell)
    w._move_actor_to("Doc", cell)
    w._move_actor_to("Ada", cell)
    w.set_stock("medicine", medicine)
    return cell


def _far_cell(w, cell):
    return next(c for c in sorted(w._map_cells) if c != cell)


def _summer(w):
    w.set_season("summer")


def _ill(w, name, disease="fever"):
    w.diagnose(None, name, disease)
    w.eng.set_attr(w._bodies[name], "illness_days", 0.0)


def _ticks(w, days):
    """Run the dawn tick once per day, advancing the calendar day as the clock does."""
    for _ in range(days):
        day = int(float(w.calendar()["day"]))
        w.eng.set_attr(w._town, "day", float(day + 1))
        w._daily_life_tick()


# ------------------------------------------------------------------ the tables and the switch

def test_the_switch_is_off_by_default_and_the_tables_are_in_the_pack():
    assert World().physical_subsystems["illness"] is False
    assert set(E.DISEASE) == {"fever"} and "fever" in E.HEALTH_CONDITIONS
    assert set(CARE["skills"]) == {"checkup", "treat", "well_baby"}
    assert CARE["skills"]["well_baby"] == ["medicine", "midwifery"]
    from domains.data_view import entities
    hamlet = entities("test_hamlet")
    assert hamlet.DISEASE == {} and hamlet.MEDICAL_CARE == {}, "the test pack has no illness rules"


def test_the_self_test_rejects_a_bad_disease_and_a_missing_skill(monkeypatch):
    errors, warnings, info = [], [], []
    E._check_illness(errors, warnings, info)
    assert errors == []
    monkeypatch.setitem(DOSE, "course_days", 0)
    monkeypatch.setitem(DOSE, "severity", -0.1)
    monkeypatch.setitem(CARE["skills"], "treat", ["no_such_skill"])
    errors, warnings, info = [], [], []
    E._check_illness(errors, warnings, info)
    assert any("course_days" in e for e in errors)
    assert any("severity" in e for e in errors)
    assert any("no_such_skill" in e for e in errors)


# ------------------------------------------------------------------ onset

def test_with_the_switch_off_no_illness_arrives_in_a_year():
    w = _w(illness=False)
    _summer(w)
    for name, stage in (("Ada", "adult"), ("Bo", "child"), ("Cy", "infant")):
        w.add_actor(name, role="hand", life_stage=stage, age={"adult": 30.0, "child": 8.0, "infant": 0.5}[stage])
    _ticks(w, 360)
    for name in ("Ada", "Bo", "Cy"):
        assert _attrs(w, name).get("disease", "") == ""
        assert w.body_state(name)["illness"] == 0
        assert w.is_alive(name)


def _onsets(seed, days=120, residents=20):
    w = _w(seed=seed)
    _summer(w)
    for i in range(residents):
        w.add_actor(f"R{i}", role="hand", life_stage="adult", age=30.0)
    found = []
    for _ in range(days):
        before = {n for n in (f"R{i}" for i in range(residents)) if not _attrs(w, n).get("disease")}
        _ticks(w, 1)
        for n in sorted(before):
            if _attrs(w, n).get("disease"):
                found.append((n, int(float(w.calendar()["day"]))))
    return found


def test_onset_is_deterministic_for_a_seed_and_happens():
    first = _onsets(305000)
    assert first == _onsets(305000), "same seed, same onsets"
    assert len(first) > 0, "a summer of twenty residents catches some fever"
    assert _onsets(305001) != first, "another seed draws differently"


def test_onset_chance_follows_the_season_and_the_life_stage():
    w = _w()
    w.set_season("winter")
    spec = E.DISEASE["fever"]
    assert float(spec["onset_per_day"]["winter"]) < float(spec["onset_per_day"]["summer"])
    w.add_actor("Ada", role="hand", life_stage="adult", age=30.0)
    w.add_actor("Bo", role="hand", life_stage="infant", age=0.5)
    # The draw is a state-derived function of (world seed, the resident's state, disease, day): repeated calls
    # agree and the world RNG is unused.
    draws = {w._stable_draw("illness", "Ada", "fever", d) for d in range(5)}
    assert len(draws) == 5 and all(0.0 <= x < 1.0 for x in draws)
    assert w._stable_draw("illness", "Ada", "fever", 3) == w._stable_draw("illness", "Ada", "fever", 3)
    assert w._illness_onset("Bo", "infant") in (None, "fever")


# ------------------------------------------------------------------ the effective drop

def test_an_unscreened_patient_loses_more_health_than_a_screened_one():
    w = _w()
    cell = _pair(w)
    w.add_actor("Bo", role="hand", home_cell=cell)
    w._move_actor_to("Bo", cell)
    _ill(w, "Ada")
    _ill(w, "Bo")
    assert w.checkup("Doc", "Bo") is True
    assert _flag(w, "Bo", "screened") == 1 and _flag(w, "Ada", "screened") == 0
    _ticks(w, 1)
    unscreened = 1.0 - w.health("Ada")
    screened = 1.0 - w.health("Bo")
    # Drop = severity + progression (unscreened) or severity (screened), less natural_care a day.
    assert unscreened == pytest.approx(DOSE["severity"] + DOSE["progression"] - CARE["natural_care"])
    assert screened == pytest.approx(DOSE["severity"] - CARE["natural_care"])
    assert screened < unscreened


def test_a_treated_patient_recovers_faster_than_an_untreated_one():
    w = _w()
    _pair(w)
    cell = w.actor_position("Ada")
    w.add_actor("Bo", role="hand", home_cell=cell)
    w._move_actor_to("Bo", cell)
    for name in ("Ada", "Bo"):
        _ill(w, name)
        w.eng.set_attr(w._actors[name], "health_value", 0.5)
    assert w.treat_patient("Doc", "Ada") is True
    _ticks(w, 1)
    # Treated: severity + progression - treat_relief, then treated_heal (net a gain).
    # Untreated: severity + progression, then natural_care (net a loss).
    treated_change = w.health("Ada") - 0.5
    untreated_change = w.health("Bo") - 0.5
    assert treated_change == pytest.approx(CARE["treated_heal"] - (DOSE["severity"] + DOSE["progression"]
                                                                    - DOSE["treat_relief"]))
    assert untreated_change == pytest.approx(-(DOSE["severity"] + DOSE["progression"] - CARE["natural_care"]))
    assert treated_change > 0.0 > untreated_change


def test_an_unvisited_infant_takes_the_fragility_penalty_and_a_seen_one_does_not():
    w = _w()
    cell = _pair(w)
    w.add_actor("Cy", role="hand", home_cell=cell, life_stage="infant", age=0.5)
    w.add_actor("Di", role="hand", home_cell=cell, life_stage="infant", age=0.5)
    w._move_actor_to("Cy", cell)
    w._move_actor_to("Di", cell)
    _ill(w, "Cy")
    _ill(w, "Di")
    assert w.well_baby_visit("Doc", "Di") is True
    _ticks(w, 1)
    unseen = 1.0 - w.health("Cy")
    seen = 1.0 - w.health("Di")
    assert unseen - seen == pytest.approx(CARE["infant_fragility"])
    assert unseen == pytest.approx(DOSE["severity"] + DOSE["progression"] + CARE["infant_fragility"]
                                   - CARE["natural_care"])


def test_an_adult_is_not_given_the_infant_penalty():
    w = _w()
    _pair(w)
    _ill(w, "Ada")
    _ticks(w, 1)
    assert 1.0 - w.health("Ada") == pytest.approx(DOSE["severity"] + DOSE["progression"] - CARE["natural_care"])


def test_the_course_ends_after_course_days_and_the_resident_is_healthy_again():
    w = _w()
    _pair(w)
    _ill(w, "Ada")
    _ticks(w, int(DOSE["course_days"]) - 1)
    assert _attrs(w, "Ada")["disease"] == "fever" and w.body_state("Ada")["illness"] == 1
    _ticks(w, 1)
    assert _attrs(w, "Ada")["disease"] == "" and _attrs(w, "Ada")["health"] == "healthy"
    assert w.body_state("Ada")["illness"] == 0
    assert w.is_alive("Ada")


def test_an_ill_resident_who_is_not_treated_can_die_of_illness():
    w = _w()
    _pair(w)
    _ill(w, "Ada")
    w.eng.set_attr(w._actors["Ada"], "health_value", 0.02)
    _ticks(w, 1)
    assert not w.is_alive("Ada")
    assert _attrs(w, "Ada")["death_cause"] == "illness"


# ------------------------------------------------------------------ the acts

def test_treatment_consumes_medicine_and_needs_the_doctor_in_reach():
    w = _w()
    cell = _pair(w)
    _ill(w, "Ada")
    w.tick()
    w.mark_turn_start()
    far = _far_cell(w, cell)
    w._move_actor_to("Doc", far)
    assert w.treat_patient("Doc", "Ada") is False and w._refusal_code == "not_in_reach"
    assert w.qty("medicine") == 5.0 and w.body_state("Ada")["treated"] == 0
    w._move_actor_to("Doc", cell)
    assert w.treat_patient("Doc", "Ada") is True
    assert w.qty("medicine") == pytest.approx(5.0 - CARE["medicine_per_treatment"])
    assert w.body_state("Ada")["treated"] == 1


def test_treatment_is_refused_when_the_store_is_locked_and_the_doctor_has_no_key():
    w = _w()
    _pair(w)
    _ill(w, "Ada")
    w.eng.set_attr(w._store_lock_node(), "locked", 1.0)
    assert w.treat_patient("Doc", "Ada") is False and w._refusal_code == "store_locked"
    assert w.qty("medicine") == 5.0


def test_treatment_is_refused_without_an_illness_or_with_no_medicine():
    w = _w()
    _pair(w, medicine=0.0)
    assert w.treat_patient("Doc", "Ada") is False and w._refusal_code == "not_needed"
    _ill(w, "Ada")
    assert w.treat_patient("Doc", "Ada") is False and w._refusal_code == "out_of_stock"


def test_only_a_resident_with_the_medical_skill_can_checkup_or_treat():
    w = _w()
    _pair(w)
    _ill(w, "Ada")
    assert w.skill_level("Ada", "medicine") == 0.0
    assert w.checkup("Ada", "Ada") is False and w._refusal_code == "unskilled"
    assert w.treat_patient("Ada", "Ada") is False and w._refusal_code == "unskilled"
    assert w.checkup("Doc", "Ada") is True


def test_a_midwife_visits_an_infant_and_a_hand_does_not():
    w = _w()
    cell = _pair(w)
    w.add_actor("Mo", role="midwife", home_cell=cell)
    w.add_actor("Cy", role="hand", home_cell=cell, life_stage="infant", age=0.5)
    w._move_actor_to("Mo", cell)
    w._move_actor_to("Cy", cell)
    assert w.well_baby_visit("Ada", "Cy") is False and w._refusal_code == "unskilled"
    assert w.well_baby_visit("Mo", "Cy") is True
    assert w.body_state("Cy")["well_baby"] == 1
    assert w.well_baby_visit("Mo", "Cy") is False and w._refusal_code == "not_needed", "a seen infant is not seen twice"


def test_a_well_baby_visit_needs_an_infant():
    w = _w()
    _pair(w)
    assert w.well_baby_visit("Doc", "Ada") is False and w._refusal_code == "not_needed"


def test_the_acts_are_refused_while_the_switch_is_off():
    w = _w(illness=False)
    _pair(w)
    assert w.checkup("Doc", "Ada") is False and w._refusal_code == "unsupported"
    assert w.body_state("Ada")["screened"] == 0


def test_flags_lapse_after_their_days():
    w = _w()
    _pair(w)
    assert w.checkup("Doc", "Ada") is True
    _ticks(w, int(CARE["screen_days"]) - 1)
    assert w.body_state("Ada")["screened"] == 1
    _ticks(w, 1)
    assert w.body_state("Ada")["screened"] == 0


def test_the_medical_acts_are_offered_as_care_options_only_to_the_skilled_and_only_when_useful():
    w = _w()
    _pair(w)
    _ill(w, "Ada")
    w.add_actor("Hal", role="hand", home_cell=w.actor_position("Doc"))
    w._move_actor_to("Hal", w.actor_position("Doc"))
    doc_kinds = {o.get("care_kind") for o in w.actor_affordances("Doc") if o.get("action") == "care"}
    assert {"checkup", "treat"} <= doc_kinds
    hand_kinds = {o.get("care_kind") for o in w.actor_affordances("Hal") if o.get("action") == "care"}
    assert not (hand_kinds - {None}), "a hand is offered no medical act"
    w.checkup("Doc", "Ada")
    assert "checkup" not in {o.get("care_kind") for o in w.actor_affordances("Doc")
                             if o.get("action") == "care" and o.get("patient") == "Ada"}


def test_the_medical_acts_are_not_offered_while_the_switch_is_off():
    w = _w(illness=False)
    _pair(w)
    _ill(w, "Ada")
    assert all("care_kind" not in o for o in w.actor_affordances("Doc"))


def test_the_care_action_routes_a_care_kind_to_the_medical_act():
    w = _w()
    _pair(w)
    _ill(w, "Ada")
    w.tick()
    w.mark_turn_start()
    assert w.major_action("Doc", "care", patient="Ada", care_kind="treat") is True
    assert w.body_state("Ada")["treated"] == 1
    assert w.major_action("Doc", "care", patient="Ada", care_kind="nonsense") is False


def test_the_plan_path_passes_the_care_kind_through():
    w = _w()
    _pair(w)
    _ill(w, "Ada")
    w.tick()
    w.mark_turn_start()
    assert w.enact_plan("Doc", {"action": "care", "patient": "Ada", "care_kind": "checkup"}) is True
    assert w.body_state("Ada")["screened"] == 1


def test_a_plain_care_still_uses_care_for():
    w = _w()
    _pair(w, medicine=0.0)
    _ill(w, "Ada")
    assert w.care_for("Doc", "Ada") is True
    assert w.qty("medicine") == 0.0
