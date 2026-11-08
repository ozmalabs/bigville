"""Phase 046: detraining and ageing of the body, behind the DETRAIN.enabled switch (off by default).

The figures come from the DETRAIN and BODY_AGE pack tables (APPROX design figures; see the pack's _doc). Tests that
need the switch on set DETRAIN.enabled with monkeypatch (the same way Phase 045 switches DEPENDANTS), so the shared
pack table is restored after each test. Each test builds a small world by hand and sets the calendar day. The daily
step is called directly (world._detraining_day), which is the call the dawn tick makes once a day.
"""
from __future__ import annotations

import pytest

from bigville import reporting
from bigville.world_persistence import load_world_checkpoint, save_world_checkpoint
from domains import bigville_entities as E
from domains.data_view import entities
from domains.detraining import aged_base, detrained, trained_share_left
from worlds.bigville_world import BigvilleWorld as World

TOL = 1e-9
STR = E.DETRAIN["strength"]
STA = E.DETRAIN["stamina"]
AGE = E.BODY_AGE


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setitem(E.DETRAIN, "enabled", True)
    return True


def _smith():
    w = World(exhaustion_slow_on=False)
    w.add_tradesperson("Smith", "smith")
    w.set_stock("iron", 2000)
    w.set_stock("charcoal", 2000)
    x, y, _fw, _fh = w._building_sites["forge"]
    w._move_actor_to("Smith", (x, y))
    return w


def _set_day(w, day):
    w.eng.set_attr(w._town, "day", float(day))


def _body(w, name):
    return w.eng.node(w._bodies[name])["attrs"]


def _mend_hammers(w):
    for item in list(w.eng.nodes("ToolItem")):
        if w.eng.node(item)["attrs"].get("kind") == "hammer":
            w.eng.set_attr(item, "condition", 1.0)
            w.eng.set_attr(item, "broken", 0.0)


def _forge(w, batches=1, name="Smith"):
    """Real forging batches (each one is an Effort that uses strength and stamina), with the reserve and hunger held."""
    for _ in range(batches):
        w.eng.set_attr(w._bodies[name], "stamina_reserve", 1.0)
        w.eng.set_attr(w._actors[name], "hunger", 0.0)
        _mend_hammers(w)
        assert w.do(name, "forge_knife")


def _train_smith(w, day, batches=20):
    _set_day(w, day)
    _forge(w, batches)
    return float(_body(w, "Smith")["str_train"])


# ------------------------------------------------------------------ the switch, the tables, the self-test

def test_the_switch_is_off_by_default_and_the_physical_subsystems_are_unchanged():
    assert E.DETRAIN["enabled"] is False
    assert "detraining" not in World().physical_subsystems


def test_both_packs_carry_the_tables():
    assert entities("test_hamlet").DETRAIN == E.DETRAIN
    assert entities("test_hamlet").BODY_AGE == E.BODY_AGE


def test_the_self_test_has_no_errors_or_warnings_and_reports_the_curves():
    report = E.check_consistency()
    assert report["errors"] == []
    assert report["warnings"] == []
    lines = [line for line in report["info"] if line.startswith(("DETRAIN", "BODY_AGE", "TRAINING band"))]
    assert any(line.startswith("DETRAIN: a strength trained part") for line in lines)
    assert any(line.startswith("DETRAIN: a stamina trained part") for line in lines)
    assert any("holds to age 30" in line for line in lines)


# ------------------------------------------------------------------ the switch off changes nothing

def test_with_the_switch_off_nothing_detrains_ages_or_is_recorded():
    w = _smith()
    trained = _train_smith(w, 0, batches=5)
    w.eng.set_attr(w._actors["Smith"], "age", 80.0)
    base_before = float(_body(w, "Smith")["str_base"])
    _set_day(w, 400)
    w._detraining_day()
    body = _body(w, "Smith")
    assert float(body["str_train"]) == pytest.approx(trained, abs=TOL)
    assert float(body["str_base"]) == base_before
    assert "str_effort_day" not in body and "str_base_peak" not in body


# ------------------------------------------------------------------ detraining

def test_a_smith_who_stops_forging_keeps_the_trained_part_through_the_grace_then_loses_it_and_never_falls_below_base(on):
    w = _smith()
    trained0 = _train_smith(w, 10, batches=20)
    assert trained0 > 0.1                         # a knife batch (stamina 0.15) closes 0.12 * 0.15 of the gap to 0.4
    grace = int(STR["grace_days"])
    _set_day(w, 10 + grace)                       # idle for exactly the grace: held
    w._detraining_day()
    assert float(_body(w, "Smith")["str_train"]) == pytest.approx(trained0, abs=TOL)
    now = trained0
    for k in range(1, 61):
        _set_day(w, 10 + grace + k)
        w._detraining_day()
        after = float(_body(w, "Smith")["str_train"])
        assert after == pytest.approx(trained0 * (1.0 - float(STR["rate"])) ** k, abs=1e-7)
        assert after < now, "the trained part falls each day past the grace"
        assert after >= 0.0
        assert w.effective_strength("Smith") >= float(_body(w, "Smith")["str_base"]) - TOL, "never below the base"
        now = after
    assert now < 0.5 * trained0


def test_a_smith_who_keeps_forging_keeps_the_trained_part(on):
    w = _smith()
    trained = 0.0
    for day in range(0, 40):
        trained = _train_smith(w, day, batches=1)
        w._detraining_day()
        assert float(_body(w, "Smith")["str_train"]) == pytest.approx(trained, abs=TOL), "no decay while working"
    assert trained > 0.0


def test_stamina_is_lost_faster_than_strength_over_the_same_idle_time(on):
    w = _smith()
    w.eng.set_attr(w._bodies["Smith"], "str_train", 0.2)
    w.eng.set_attr(w._bodies["Smith"], "sta_train", 0.2)
    w.eng.set_attr(w._bodies["Smith"], "str_effort_day", 0.0)
    w.eng.set_attr(w._bodies["Smith"], "sta_effort_day", 0.0)
    for day in range(1, 41):
        _set_day(w, day)
        w._detraining_day()
    body = _body(w, "Smith")
    assert float(body["str_train"]) == pytest.approx(0.2 * trained_share_left(40, STR["grace_days"], STR["rate"]), abs=1e-7)
    assert float(body["sta_train"]) == pytest.approx(0.2 * trained_share_left(40, STA["grace_days"], STA["rate"]), abs=1e-7)
    assert float(body["sta_train"]) < float(body["str_train"])


def test_a_confined_resident_with_no_effort_detrains_by_the_same_rule(on):
    w = _smith()
    w.eng.set_attr(w._bodies["Smith"], "str_train", 0.3)
    w.eng.set_attr(w._bodies["Smith"], "str_effort_day", 0.0)
    _set_day(w, 1000)
    w._detraining_day()
    assert float(_body(w, "Smith")["str_train"]) < 0.3


def test_detrained_arithmetic_holds_then_decays_and_snaps_to_zero():
    assert detrained(0.5, 21, 21, 0.02) == 0.5
    assert detrained(0.5, 22, 21, 0.02) == pytest.approx(0.49)
    assert detrained(0.0, 10_000, 21, 0.02) == 0.0
    assert detrained(1e-10, 100, 21, 0.5) == 0.0
    assert detrained(0.4, float("inf"), 21, 0.02) == pytest.approx(0.392)


# ------------------------------------------------------------------ ageing

def test_an_elders_base_falls_past_peak_until_and_a_young_adults_does_not(on):
    w = _smith()
    w.add_actor("Elder", role="hand", age=65.0)
    w.add_actor("Young", role="hand", age=30.0)
    elder = w._bodies["Elder"]
    young_base = float(w.eng.node(w._bodies["Young"])["attrs"]["str_base"])
    _set_day(w, 1)
    w._detraining_day()
    assert float(w.eng.node(elder)["attrs"]["str_base"]) == pytest.approx(
        aged_base(float(w.eng.node(elder)["attrs"]["str_base_peak"]), 65.0, AGE["peak_until"],
                  AGE["strength"]["decline_per_year"], AGE["strength"]["floor"]), abs=TOL)
    assert float(w.eng.node(w._bodies["Young"])["attrs"]["str_base"]) == young_base
    assert "str_base_peak" not in w.eng.node(w._bodies["Young"])["attrs"], "a young adult is never written"


def test_ageing_holds_at_the_floor_and_scales_the_residents_own_peak_base(on):
    w = _smith()
    body = w._bodies["Smith"]
    w.eng.set_attr(body, "str_base", 1.3)               # a founder drawn strong, not the pack default
    w.eng.set_attr(body, "sta_base", 0.8)
    w.eng.set_attr(w._actors["Smith"], "age", 95.0)
    _set_day(w, 1)
    w._detraining_day()
    attrs = _body(w, "Smith")
    assert float(attrs["str_base"]) == pytest.approx(1.3 * AGE["strength"]["floor"], abs=TOL)
    assert float(attrs["sta_base"]) == pytest.approx(0.8 * AGE["stamina"]["floor"], abs=TOL)
    assert float(attrs["str_base_peak"]) == pytest.approx(1.3, abs=TOL)


def test_ageing_does_not_change_the_trained_part_and_detraining_does_not_change_the_base(on):
    w = _smith()
    w.eng.set_attr(w._bodies["Smith"], "str_train", 0.3)
    w.eng.set_attr(w._bodies["Smith"], "str_effort_day", 0.0)
    w.eng.set_attr(w._actors["Smith"], "age", 60.0)
    _set_day(w, 1000)
    base0 = float(_body(w, "Smith")["str_base"])
    w._detraining_day()
    attrs = _body(w, "Smith")
    assert float(attrs["str_base"]) < base0               # ageing acts on the base
    assert float(attrs["str_train"]) < 0.3                # detraining acts on the trained part


# ------------------------------------------------------------------ growth (Phase 045) does not fight detraining

def _village(monkeypatch, seed=305000):
    monkeypatch.setitem(E.DETRAIN, "enabled", True)
    monkeypatch.setitem(E.DEPENDANTS, "enabled", True)
    w = World(autonomous_actors=False, map_seed=seed)
    cells = sorted(w._map_cells)
    home = cells[0]
    w.add_household("H1", home_cell=home)
    w.add_actor("Mum", role="hand", home_cell=home, age=30.0)
    w.assign_household("Mum", "H1")
    w._move_actor_to("Mum", home)
    w.add_actor("Kid", role="child", home_cell=home, life_stage="child", age=10.0)
    w.assign_household("Kid", "H1")
    w._move_actor_to("Kid", home)
    return w


def test_growth_writes_the_base_of_a_child_and_detraining_writes_only_its_trained_part(monkeypatch):
    w = _village(monkeypatch)
    kid = w._bodies["Kid"]
    w.eng.set_attr(kid, "str_train", 0.3)
    w.eng.set_attr(kid, "str_effort_day", 0.0)
    for day in range(1, 60):
        _set_day(w, day)
        w._dependants_day()                                # growth: the base, each dawn
        w._detraining_day()                                # detraining: the trained part only
        attrs = w.eng.node(kid)["attrs"]
        assert float(attrs["str_base"]) == pytest.approx(w._growth_base(10.0, "str_base"), abs=TOL)
        assert "str_base_peak" not in attrs, "ageing never writes a child"
    assert 0.0 <= float(w.eng.node(kid)["attrs"]["str_train"]) < 0.3


# ------------------------------------------------------------------ determinism and checkpoints

def _run_script():
    w = _smith()
    _train_smith(w, 2, batches=8)
    w.eng.set_attr(w._actors["Smith"], "age", 70.0)
    for day in range(3, 123):
        _set_day(w, day)
        w._detraining_day()
    return {k: float(_body(w, "Smith")[k]) for k in ("str_train", "sta_train", "str_base", "sta_base")}


def test_the_run_is_deterministic(on):
    assert _run_script() == _run_script()


def test_a_checkpoint_round_trip_keeps_the_detraining_state(on, tmp_path):
    w = _smith()
    _train_smith(w, 5, batches=10)
    w.eng.set_attr(w._actors["Smith"], "age", 70.0)
    _set_day(w, 9)
    w._detraining_day()
    path = tmp_path / "town"
    save_world_checkpoint(w, path)
    restored = load_world_checkpoint(path)
    for key in ("str_train", "sta_train", "str_base", "str_effort_day", "sta_effort_day", "str_base_peak"):
        assert float(_body(restored, "Smith")[key]) == pytest.approx(float(_body(w, "Smith")[key]), abs=TOL)
    _set_day(w, 80)
    _set_day(restored, 80)
    w._detraining_day()
    restored._detraining_day()
    assert float(_body(restored, "Smith")["str_train"]) == pytest.approx(float(_body(w, "Smith")["str_train"]), abs=TOL)


# ------------------------------------------------------------------ the report

def test_the_report_gives_strength_and_stamina_by_age_band_and_the_share_trained():
    w = _smith()
    _train_smith(w, 0, batches=5)
    w.add_actor("Elder", role="hand", age=72.0)
    report = reporting.body_by_age(w)
    assert report["30-39"]["residents"] == 1
    assert report["70+"]["residents"] == 1
    assert report["30-39"]["share_trained_strength"] == 1.0
    assert report["70+"]["share_trained_strength"] == 0.0
    assert 0.0 < report["30-39"]["mean_strength"] <= 2.0
