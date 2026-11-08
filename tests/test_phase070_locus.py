"""Phase 070: located harm, healing by place, silent and slow states, habituation, observable signs and screening.

The health scalar is unchanged by this phase: every test that harms a resident checks the one health_value. The
ledger, the signals and the screening live in the body (worlds/body.py) and the pure rules in domains/interoception.
Views are built from a real founding town (scenario town100, seed 305000)."""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                                     # noqa: E402
from domains import interoception as I                                   # noqa: E402
from domains import interoception_check as IC                           # noqa: E402
from domains.agent_view_check import felt_body_problems                 # noqa: E402
from worlds import body as B                                             # noqa: E402

SEED = 305000
PLAYER = "Verity Peaseblossom"
PACK = "bigville"
TABLES = B.pack_tables(PACK)
RATES = TABLES["rates"]
RECORD = {"acuity": 1.0, "attention": 1.0, "impairment": 0.0}
NO_READS = {name: 0.0 for name in I.READS}


@pytest.fixture
def town():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


def _adult(world):
    return next(name for name in world._actors
                if world.eng.node(world._actors[name])["attrs"].get("life_stage") == "adult")


def _row(derived, name):
    return next(row for row in derived["sources"] if row["source"] == name)


def _derive(located=None, reads=None, record=None, previous=None, habituation=None):
    return I.derive(TABLES, {**NO_READS, **(reads or {})}, dict(RECORD if record is None else record), SEED,
                    "Tester", 3, previous=previous, located=located, habituation=habituation)


# ------------------------------------------------------------------ located harm
def test_a_blow_to_the_arm_lowers_health_once_and_writes_the_arm_in_the_ledger(town):
    world = town.world
    name = _adult(world)
    before = world.health(name)
    assert world.harm(name, 0.1, "injury", locus="arm") is True
    assert world.health(name) == pytest.approx(before - 0.1)
    body = world.body_of(name)
    assert body.state["ledger"] == {"arm": pytest.approx(0.1)}
    assert body.located() == {"injury": {"arm": pytest.approx(0.1)}}


def test_a_harm_with_no_locus_draws_one_from_the_table_and_the_draw_is_stateless(town):
    world = town.world
    name = _adult(world)
    assert not hasattr(world, "_rng"), "the world keeps no shared RNG"
    picks = set()
    for _ in range(3):
        world.harm(name, 0.001, "violence")
        picks |= set(world.body_of(name).located()["injury"])
    assert not hasattr(world, "_rng"), "the locus draw must not create a world RNG"
    weights = TABLES["harm_locus"]["violence"]
    assert picks and picks <= set(weights)
    # The same turn gives the same node: the draw is keyed on the seed, the resident, the cause and the tick.
    assert world._body_harm_locus(name, "violence") == world._body_harm_locus(name, "violence")


def test_whole_body_causes_change_health_and_leave_no_located_entry(town):
    world = town.world
    name = _adult(world)
    before = world.health(name)
    world.harm(name, 0.05, "starvation")
    assert world.health(name) == pytest.approx(before - 0.05)
    assert world.body_of(name).state["ledger"] == {}


def test_an_unknown_locus_is_refused_and_the_health_is_not_touched(town):
    world = town.world
    name = _adult(world)
    before = world.health(name)
    with pytest.raises(ValueError):
        world.harm(name, 0.1, "injury", locus="tail")
    assert world.health(name) == before


def test_a_lower_acuity_resolves_a_blow_shallower_or_equal_and_the_channel_caps_the_place():
    located = {"injury": {"arm": 0.2}}
    low = _row(_derive(located, record={**RECORD, "acuity": 0.7}), "injury_sharp@arm")
    high = _row(_derive(located, record={**RECORD, "acuity": 1.3}), "injury_sharp@arm")
    assert low["quality_depth"] <= high["quality_depth"]
    assert low["locus_depth"] <= high["locus_depth"]
    cap = TABLES["channels"]["surface"]
    assert high["quality_depth"] <= cap["quality_cap"] and high["locus_depth"] <= cap["locus_cap"]
    assert high["locus_shown"] == "arm", "the arm is one step from the root, so the place is the arm"
    assert high["sound"] and high["where"] == "arm"


def test_a_blow_gives_a_sharp_and_a_dull_signal_at_its_locus_only():
    derived = _derive({"injury": {"leg": 0.2}})
    names = {row["source"] for row in derived["sources"]}
    assert {"injury_sharp@leg", "injury_dull@leg"} <= names
    assert all(row["locus_true"] == "leg" for row in derived["sources"] if "@" in row["source"])
    assert not any(name.endswith("@chest") for name in names)


def test_the_located_ledger_falls_by_its_rate_each_tick_and_care_lowers_it(town):
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    world.embodiment[name]["ledger"] = {"arm": 0.1}
    for _ in range(10):
        body.tick()
    assert body.state["ledger"]["arm"] == pytest.approx(0.1 - 10 * RATES["located_heal_per_tick"], abs=1e-6)
    before_health = world.health(name)
    body.apply({"kind": "heal", "amount": 0.02})
    assert body.state["ledger"]["arm"] == pytest.approx(0.1 - 10 * RATES["located_heal_per_tick"]
                                                         - 0.02 * RATES["care_share"], abs=1e-6)
    world._heal(name, 0.02)
    assert world.health(name) == pytest.approx(min(1.0, before_health + 0.02))


# ------------------------------------------------------------------ silent and slow states
def test_an_incubating_illness_is_felt_only_in_the_background_until_its_ramp_passes(town):
    world = town.world
    name = _adult(world)
    world.physical_subsystems["illness"] = True
    world.diagnose(None, name, "fever")
    node = world._bodies[name]
    world.eng.set_attr(node, "illness_days", 0.0)
    body = world.body_of(name)
    early = body.referee()
    row = next(r for r in early["sources"] if r["source"] == "illness")
    assert row["raw_intensity"] > 0.0 and row["felt"] is False
    assert early["feeling"] is not None, "the early course still counts toward the background feeling"
    assert all(s != "illness" for s in early["signals"])
    world.eng.set_attr(node, "illness_days", 6.0)
    late = body.referee()
    late_row = next(r for r in late["sources"] if r["source"] == "illness")
    assert late_row["felt"] is True and late_row["raw_intensity"] > row["raw_intensity"]


def test_a_deficiency_is_silent_below_its_awareness_and_felt_above_it(town):
    world = town.world
    name = _adult(world)
    node = world._bodies[name]
    world.eng.set_attr(node, "deficiency", 0.2)
    low = world.body_of(name).referee()
    assert _row_from(low, "deficiency")["felt"] is False
    assert _row_from(low, "deficiency")["raw_intensity"] > 0.0
    world.eng.set_attr(node, "deficiency", 0.9)
    high = world.body_of(name).referee()
    assert _row_from(high, "deficiency")["felt"] is True


def _row_from(block, name):
    return next(row for row in block["sources"] if row["source"] == name)


def test_chronic_short_sleep_builds_a_debt_that_a_full_night_balances(town):
    """Phase 070b: the debt is in hours of missing sleep against the life stage's need (BODY_RATES.sleep_need_hours).
    Seven hours a day holds an adult level, six hours builds one hour a day, no sleep adds one night's need, and a
    longer night pays the debt down. A day is 96 ticks; the asleep ticks come last in the day."""
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    assert body.sleep_need() == 7.0

    def run_day(asleep_hours, start):
        body.state["sleep_debt"] = float(start)
        asleep_ticks = int(round(asleep_hours * 4))           # 4 ticks an hour (TIME: 15 minutes a tick)
        for tick in range(96):
            asleep = tick >= 96 - asleep_ticks
            body.attention = (lambda a=asleep: "asleep" if a else "idle")
            body._sleep_step()
        return body.state["sleep_debt"]

    assert run_day(7, 4.0) == pytest.approx(4.0, abs=1e-3)    # seven hours holds the debt level
    assert run_day(6, 0.0) == pytest.approx(1.0, abs=1e-3)    # six hours builds one hour a day
    assert run_day(0, 0.0) == pytest.approx(7.0, abs=1e-3)    # a day with no sleep adds one night's need
    assert run_day(10, 7.0) == pytest.approx(4.0, abs=1e-3)   # ten hours pays three hours back
    body.state["sleep_debt"] = 7.0
    assert body.reads()["sleep_debt"] == pytest.approx(0.5)   # 7 / (2 x 7)
    body.state["sleep_debt"] = 40.0
    assert body.reads()["sleep_debt"] == 1.0                  # capped: two nights lost reads as full


def test_hangover_and_withdrawal_are_read_from_the_aftereffects_and_are_zero_when_off(town):
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    assert body.reads()["hangover"] == 0.0 and body.reads()["withdrawal"] == 0.0
    world.physical_subsystems["alcohol_aftereffects"] = True
    span = float(world.E.INTOXICATION["hangover_ticks"])
    world.eng.set_attr(world._bodies[name], "hangover_ticks", span / 2.0)
    reads = world.body_of(name).reads()
    assert reads["hangover"] == pytest.approx(0.5, abs=1e-6)


# ------------------------------------------------------------------ habituation
def test_a_steady_signal_fades_and_a_sudden_change_is_noticed_at_full_strength(town):
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    world.embodiment[name]["ledger"] = {"arm": 0.2}
    body.tick()                     # the first tick only sets the trend
    first = body.referee()
    raw = _row_from(first, "injury_sharp@arm")["raw_intensity"]
    for _ in range(20):
        body.tick()
    felt = body.referee()
    row = _row_from(felt, "injury_sharp@arm")
    assert row["raw_intensity"] == pytest.approx(raw, abs=0.05)
    assert row["intensity"] < row["raw_intensity"], "a steady signal habituates"
    world.embodiment[name]["ledger"] = {"arm": 0.9}     # a sudden, large change
    body.tick()
    assert body.state["habituation"].get("injury_sharp@arm") is None, "a sudden change resets the habituation"
    noticed = _row_from(body.referee(), "injury_sharp@arm")
    assert noticed["intensity"] == pytest.approx(noticed["raw_intensity"], abs=1e-6)


def test_the_habituation_and_the_trend_are_checkpointed(town):
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    world.embodiment[name]["ledger"] = {"chest": 0.15}
    for _ in range(5):
        body.tick()
    state = body.dump()
    again = B.WorldBackedBody.load(state, world=world, actor=name)
    assert again.referee() == body.referee()
    assert again.dump() == state


# ------------------------------------------------------------------ observable signs and screening
def test_a_bruise_shows_near_and_in_light_and_not_far_off(town):
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    world.embodiment[name]["ledger"] = {"chest": 0.4}
    near = [row.get("sign") for row in body.observable(distance=1, light=1.0)]
    far = [row.get("sign") for row in body.observable(distance=50, light=1.0)]
    dark = [row.get("sign") for row in body.observable(distance=1, light=0.0)]
    assert "bruise" in near and "bruise" not in far and "bruise" not in dark


def test_a_limp_shows_only_from_an_injured_leg(town):
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    world.embodiment[name]["ledger"] = {"chest": 0.4}
    assert "limp" not in [row.get("sign") for row in body.observable(distance=2, light=1.0)]
    world.embodiment[name]["ledger"] = {"leg": 0.3}
    assert "limp" in [row.get("sign") for row in body.observable(distance=2, light=1.0)]


def test_a_checkup_records_the_silent_deficiency_that_the_felt_view_does_not_show(town, monkeypatch):
    world = town.world
    name = _adult(world)
    carer = next(other for other in world._actors if other != name)
    world.eng.set_attr(world._bodies[name], "deficiency", 0.2)
    monkeypatch.setattr(world, "_care_act_refusal", lambda *args: None)
    assert world.checkup(carer, name) is True
    findings = world.screening_findings(name)
    assert findings and "deficiency" in findings[-1]["silent"]
    felt = world.body_of(name).afferents()
    assert "deficiency" not in str(felt), "the felt view names no source"


def test_the_leak_rule_still_holds_for_a_located_injury_and_a_deficiency(town):
    world = town.world
    name = _adult(world)
    body = world.body_of(name)
    world.embodiment[name]["ledger"] = {"arm": 0.3, "chest": 0.2}
    world.eng.set_attr(world._bodies[name], "deficiency", 0.9)
    view = body.afferents()
    assert felt_body_problems(view, PACK) == []


# ------------------------------------------------------------------ the rules and the self-test
def test_the_harm_loci_table_names_no_root_and_whole_body_causes_are_empty():
    assert "body" not in TABLES["harm_locus"]["injury"]
    assert TABLES["harm_locus"]["starvation"] == {}


def test_the_self_test_finds_a_harm_cause_with_no_row_and_a_root_locus():
    pack = {"HEALTH": {"causes": ["injury", "starvation"]},
            "HARM_LOCUS": {"injury": {"body": 1.0}},
            "BODY_RATES": dict(RATES), "OBSERVABLE_SIGNS": {}, "ANATOMY": TABLES["anatomy"]}
    errors = []
    IC._check_phase070(pack, IC._rows(TABLES["anatomy"]), True, errors)
    text = " ".join(errors)
    assert "starvation" in text and "root" in text


def test_the_self_test_passes_on_bigville_with_the_new_tables():
    errors, warnings, info = [], [], []
    IC.check_interoception(PACK, errors, warnings, info)
    assert errors == [] and warnings == []
    assert any("14 signal sources" in line for line in info)


def test_a_body_built_with_no_locus_draws_no_ledger_entry_for_whole_body_causes(town):
    world = town.world
    name = _adult(world)
    world.harm(name, 0.001, "age")
    assert world.body_of(name).state["ledger"] == {}


def test_the_injuries_report_counts_located_injury_by_locus(town):
    world = town.world
    name = _adult(world)
    world.embodiment[name]["ledger"] = {"arm": 0.1}
    report = world.injuries_by_locus()
    assert report["by_locus"].get("arm") == pytest.approx(0.1)
    assert report["residents"] >= 1
