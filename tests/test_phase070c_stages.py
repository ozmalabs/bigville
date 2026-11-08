"""Phase 070c: a life stage may inherit from a parent (LIFE_STAGES.inherits). The preschooler (3 to 5 years) inherits
every value from child and overlays only the sleep need (10 h). Resolution is one place (domains/pack.py); the
comparisons by name read the stage's chain (LIFE_STAGE_CHAIN).
"""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                       # noqa: E402
from domains import life_stage_check as LSC               # noqa: E402
from domains.pack import compile_tables, load_pack, stage_dicts   # noqa: E402

SEED = 305000
PLAYER = "Verity Peaseblossom"
PACK = load_pack("bigville")
PATHS = PACK["STAGE_KEYED"]["paths"]
OWN_WORDS = {"LEXICON_QUANTITIES.life_stage.self", "LEXICON_QUANTITIES.life_stage.other"}   # explicit phrases
OWN_NEEDS = {"BODY_RATES.sleep_need_hours"}                                                # the one overlay


@pytest.fixture
def town():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


def _adult(world):
    return next(name for name in world._actors
                if world.eng.node(world._actors[name])["attrs"].get("life_stage") == "adult")


def test_the_preschooler_takes_every_stage_keyed_value_of_child_except_the_sleep_need_and_its_words():
    for path in PATHS:
        if path in OWN_WORDS or path in OWN_NEEDS:
            continue
        for table in stage_dicts(PACK.tables, path):
            if "preschooler" not in table:
                assert "child" not in table, path
                continue
            assert table["preschooler"] == table["child"], path


def test_the_preschooler_takes_child_band_values_except_its_own_band():
    child, pre = PACK["LIFE_STAGES"]["child"], PACK["LIFE_STAGES"]["preschooler"]
    for field in ("work_fraction", "care", "food"):
        assert pre[field] == child[field], field
    assert (pre["age_min"], pre["age_max"]) == (3, 5)
    assert (child["age_min"], child["age_max"]) == (6, 12)


def test_the_sleep_need_of_a_preschooler_is_the_low_end_of_the_nsf_range_ten_hours():
    rates = PACK["BODY_RATES"]["sleep_need_hours"]
    assert rates["preschooler"] == 10                       # NSF preschoolers 10 to 13 h (Hirshkowitz et al. 2015)
    assert rates["child"] == 9                              # the school-aged value is unchanged


def test_the_sleep_need_a_resident_body_reads_follows_the_life_stage(town):
    world = town.world
    name = _adult(world)
    node = world._actors[name]
    world.eng.set_attr(node, "life_stage", "preschooler")
    assert world.body_of(name).sleep_need() == 10.0
    world.eng.set_attr(node, "life_stage", "child")
    assert world.body_of(name).sleep_need() == 9.0


def test_the_chain_names_a_stage_and_its_ancestors_nearest_first():
    chain = PACK["LIFE_STAGE_CHAIN"]
    assert chain["preschooler"] == ["preschooler", "child"]
    assert chain["child"] == ["child"]
    assert chain["infant"] == ["infant"]


def test_a_preschooler_is_a_child_for_membership_but_not_an_infant(town, monkeypatch):
    world = town.world
    name = _adult(world)
    world.eng.set_attr(world._actors[name], "life_stage", "preschooler")
    monkeypatch.setitem(world.E.DEPENDANTS, "enabled", True)
    assert world._life_stage_is("preschooler", "child")
    assert not world._life_stage_is("preschooler", "infant")
    assert world._is_dependant(name)                       # its chain holds child, a dependant stage
    assert world._dependant_refusal(name) is None         # an infant is refused major actions; a preschooler is not
    world.eng.set_attr(world._actors[name], "life_stage", "infant")
    assert world._dependant_refusal(name) == "infant"


def test_the_bands_are_contiguous_whole_years_from_zero():
    bands = sorted(PACK["LIFE_STAGES"].items(), key=lambda item: item[1]["age_min"])
    assert bands[0][1]["age_min"] == 0
    for (_, lower), (_, upper) in zip(bands, bands[1:]):
        assert lower["age_max"] + 1 == upper["age_min"]
    assert [stage for stage, _ in bands] == ["infant", "preschooler", "child", "youth", "adult", "elder"]


def test_an_inheritance_cycle_and_an_unknown_parent_are_refused():
    cycle = {"LIFE_STAGES": {"a": {"inherits": "b", "age_min": 0, "age_max": 1},
                             "b": {"inherits": "a", "age_min": 2, "age_max": 3}}}
    with pytest.raises(ValueError, match="cycle"):
        compile_tables(cycle)
    unknown = {"LIFE_STAGES": {"a": {"inherits": "zzz", "age_min": 0, "age_max": 1}}}
    with pytest.raises(ValueError, match="zzz"):
        compile_tables(unknown)


def test_the_self_test_reports_a_cycle_and_an_unknown_parent_as_errors():
    errors = []
    chain = LSC._chain_problems({"a": {"inherits": "b"}, "b": {"inherits": "a"}, "c": {"inherits": "nope"}}, errors)
    assert chain == {}
    assert any("cycle" in message for message in errors)
    assert any("nope" in message for message in errors)


def test_the_age_of_a_preschooler_under_the_dependants_switch_on(town, monkeypatch):
    world = town.world
    monkeypatch.setitem(world.E.DEPENDANTS, "enabled", True)
    assert world._age_stage(2.5) == "infant"
    assert world._age_stage(3.0) == "preschooler"
    assert world._age_stage(3.5) == "preschooler"
    assert world._age_stage(5.9) == "preschooler"
    assert world._age_stage(6.0) == "child"
    assert world._age_stage(12.5) == "child"
    assert world._age_stage(13.0) == "youth"


def test_the_whole_year_rule_with_the_switch_off_is_unchanged_and_gap_ages_read_elder(town, monkeypatch):
    world = town.world
    monkeypatch.setitem(world.E.DEPENDANTS, "enabled", False)
    assert world._age_stage(3.0) == "preschooler"
    assert world._age_stage(5.0) == "preschooler"
    assert world._age_stage(6.0) == "child"
    assert world._age_stage(2.5) == "elder"                # the gap between infant (0 to 2) and preschooler (3 to 5)


def test_the_preschooler_has_its_own_phrase_for_self_and_other():
    lexicon = PACK["LEXICON_QUANTITIES"]["life_stage"]
    assert lexicon["self"]["preschooler"] == "a young child"
    assert lexicon["other"]["preschooler"] == "a young child"
    ages = {band["label"]: band["min"] for band in PACK["LEXICON_QUANTITIES"]["age"]["self"]}
    assert ages["preschooler"] == PACK["LIFE_STAGES"]["preschooler"]["age_min"]
    assert ages["child"] == PACK["LIFE_STAGES"]["child"]["age_min"]


def test_the_interoception_acuity_of_a_preschooler_is_the_childs():
    acuity = PACK["INTEROCEPTION"]["acuity"]["life_stage"]
    assert acuity["preschooler"] == acuity["child"] == 0.9


def test_the_self_test_has_no_life_stage_errors_for_the_pack():
    errors, warnings, info = [], [], []
    LSC.check_life_stages(PACK.path, errors, warnings, info)
    assert errors == [] and warnings == []
    assert any("inheritance" in line for line in info)
