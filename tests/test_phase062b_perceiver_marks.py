"""Phase 062B: the perceiver reads Phase 063's marks. The mark gate sees the marks the world shows the observer at its
distance and light (observable_marks), with the observer's notice_skill; the truth reads the subject's own marks.
A smith who has really smelted iron (a world action, no scripted marks) is covered in coal dust near at hand in
daylight once the soot reaches mark_min_level. The life-stage noun 'elder' reads as 'a senior'.

The founding town has smiths and no colliers. A 'collier' role exists only in the tests and in the burn recipe, so
the charcoal test uses that role for the burn and the decay only. The levels, rates and ranges are the APPROX values in
packs/bigville/world/marks.json and perception.json; the tests use them, they do not check them against a source.
"""
from __future__ import annotations

import copy
import os
import re
import sys
from types import SimpleNamespace

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from domains import bigville_entities as E                 # noqa: E402
from domains import perceiver as P                         # noqa: E402
from domains import perception_check as PC                 # noqa: E402
from domains.pack import load_pack                         # noqa: E402
from worlds.bigville_world import BigvilleWorld as World   # noqa: E402

PACK_NAME = "bigville"
PACK = load_pack(PACK_NAME)
TABLE = PACK["PERCEPTION"]
VOWEL_NOUN = re.compile(r"\ba [aeiou]")


def _game(world):
    return SimpleNamespace(world=world)


def _rec(*, light="day", skills=None, skill_full=False, band="sober"):
    return {"light": light, "light_known": True, "sight": 7, "band": band, "skills": dict(skills or {}),
            "skill_full": skill_full, "literacy": "labouring", "modes": {f: "enforced" for f in P.FACULTIES}}


def _smelt(w, name):
    """One iron smelt by a smith, run to completion with the world's own ticks."""
    before = w.mark_level(name, "soot")
    assert w.start(name, "smelt_iron", tool="none")
    for _ in range(400):
        w.tick(1)
        if w.mark_level(name, "soot") > before + 1e-9:
            return
    raise AssertionError("the smelt never completed")


def _smith(smelts):
    w = World(autonomous_actors=False)
    w.add_actor("Sm", role="smith", skill=0.9)
    w.set_stock("ore", 8)
    w.set_stock("charcoal", 4)
    for _ in range(smelts):
        _smelt(w, "Sm")
    return w


def _burned_collier():
    """A collier role runs one charcoal burn to completion with the world's own ticks (no scripted marks)."""
    w = World(autonomous_actors=False)
    w.add_actor("Col", role="collier", skill=0.9)
    w.set_stock("wood", 20)
    assert w.start("Col", "burn_charcoal", tool="none")
    for _ in range(400):
        w.tick(1)
        if w.mark_level("Col", "soot") > 0.0:
            return w
    raise AssertionError("the charcoal burn never completed")


# ------------------------------------------------------------------ the mark gate reads the world's marks
def test_a_smith_who_has_smelted_twice_is_covered_in_coal_dust_near_in_daylight():
    w = _smith(2)
    row = next(r for r in E.RECIPES if r["name"] == "smelt_iron")
    assert w.mark_level("Sm", "soot") == pytest.approx(2 * row["marks"]["soot"])
    subject = P.person_subject(_game(w), "Sm", PACK_NAME)
    assert subject["marks"]["soot"] == pytest.approx(2 * row["marks"]["soot"])
    out = P.percept("person", subject, 1, _rec(), PACK_NAME)
    assert out["words"] == "a grown person covered in coal dust" and out["tier"] == 3


def test_one_smelt_leaves_soot_the_world_shows_but_the_tier_does_not_take():
    """One smelt leaves 0.3 soot. The world shows it (visible_level 0.3), but mark_min_level is 0.5, so the
    perceiver does not describe the coal dust."""
    w = _smith(1)
    assert w.mark_level("Sm", "soot") == pytest.approx(0.3)
    assert [r["kind"] for r in w.observable_marks("Sm", distance=1, light=1.0)] == ["soot"]
    out = P.percept("person", P.person_subject(_game(w), "Sm", PACK_NAME), 1, _rec(), PACK_NAME)
    assert out["words"] == "a grown person"


def test_a_collier_who_has_burned_charcoal_carries_the_soot_the_recipe_names():
    w = _burned_collier()
    row = next(r for r in E.RECIPES if r["name"] == "burn_charcoal")
    assert w.mark_level("Col", "soot") == pytest.approx(row["marks"]["soot"])
    out = P.percept("person", P.person_subject(_game(w), "Col", PACK_NAME), 1, _rec(), PACK_NAME)
    assert out["words"] == "a grown person covered in coal dust" and out["tier"] == 3


def test_the_coal_dust_leaves_the_tier_after_one_period_of_decay():
    """A collier's burn leaves soot 0.5, exactly mark_min_level. One period of decay (0.03) takes it under."""
    w = _burned_collier()
    w._marks_period()
    assert w.mark_level("Col", "soot") < TABLE["mark_min_level"]
    out = P.percept("person", P.person_subject(_game(w), "Col", PACK_NAME), 1, _rec(), PACK_NAME)
    assert out["words"] == "a grown person"


def test_a_mark_the_world_hides_at_this_distance_is_not_seen_though_the_near_band_allows_it():
    """soot's see_range is 1 cell and the near band is 2: at 2 cells the world hides the soot."""
    w = _smith(2)
    assert [r["kind"] for r in w.observable_marks("Sm", distance=2, light=1.0)] == []
    out = P.percept("person", P.person_subject(_game(w), "Sm", PACK_NAME), 2, _rec(), PACK_NAME)
    assert out["words"] == "a grown person"
    assert out["truth_tier"] == 4 and out["truth"] == "smith, judging by the work"


def test_dim_light_shows_the_coal_dust_and_the_dark_hides_it():
    w = _smith(2)
    subject = P.person_subject(_game(w), "Sm", PACK_NAME)
    assert P.percept("person", subject, 1, _rec(light="dim"), PACK_NAME)["words"] == \
        "a grown person covered in coal dust"
    assert P.percept("person", subject, 1, _rec(light="dark"), PACK_NAME)["words"] == "a person"


def test_the_truth_ignores_the_observers_light_and_distance():
    w = _smith(2)
    subject = P.person_subject(_game(w), "Sm", PACK_NAME)
    blind = P.percept("person", subject, 6, _rec(light="dark"), PACK_NAME)
    assert blind["truth"] == "smith, judging by the work"
    assert blind["truth_tier"] == 4 and blind["tier"] == 0


def test_the_observers_skill_gates_a_row_that_names_a_notice_skill():
    """injury's notice_skill is medicine: a row is seen only by a resident with medicine at notice_min_level."""
    assert E.MARKS["injury"]["notice_skill"] == "medicine"
    rows = [{"kind": "injury", "level": 0.9, "notice_skill": "medicine"},
            {"kind": "dirt", "level": 0.6, "notice_skill": None}]
    subject = {"stage": "grown person", "job": "", "trade_skills": [], "marks": {},
               "observe": lambda distance, light: rows}
    ctx = {"light": "day", "distance": 1, "skills": {}, "skill_full": False}
    assert P._seen_marks(subject, ctx, PACK_NAME) == {"dirt": 0.6}
    ctx["skills"] = {"medicine": TABLE["notice_min_level"]}
    assert P._seen_marks(subject, ctx, PACK_NAME) == {"dirt": 0.6, "injury": 0.9}
    ctx = {"light": "day", "distance": 1, "skills": {}, "skill_full": True}
    assert P._seen_marks(subject, ctx, PACK_NAME) == {"dirt": 0.6, "injury": 0.9}


def test_a_subject_built_by_hand_shows_its_marks_as_given():
    subject = {"stage": "child", "job": "", "trade_skills": [], "marks": {"dirt": 0.9}}
    ctx = {"light": "day", "distance": 2, "skills": {}, "skill_full": False}
    assert P._seen_marks(subject, ctx, PACK_NAME) == {"dirt": 0.9}


def test_the_light_levels_put_dark_below_every_see_light_and_the_rest_above():
    assert TABLE["light_level"]["dark"] == 0.0
    see = [spec["see_light"] for spec in PACK["MARKS"].values()]
    for light, value in TABLE["light_level"].items():
        if light != "dark":
            assert value >= max(see), light


# ------------------------------------------------------------------ the stage nouns
def test_every_life_stage_noun_reads_with_a_in_front_and_none_takes_an_article_wrongly():
    for stage in PACK["LIFE_STAGES"]:
        noun = TABLE["stage_nouns"][stage]
        subject = {"stage": noun, "job": "", "trade_skills": [], "marks": {}}
        words = P.percept("person", subject, 5, _rec(), PACK_NAME)["words"]
        assert words == f"a {noun}", (stage, words)
        assert not VOWEL_NOUN.search(words), (stage, words)


def test_an_elder_is_a_senior_in_the_view():
    w = World(autonomous_actors=False)
    w.add_actor("Old", role="hand", life_stage="elder", age=80.0)
    subject = P.person_subject(_game(w), "Old", PACK_NAME)
    assert subject["stage"] == "senior"
    assert P.percept("person", subject, 5, _rec(), PACK_NAME)["words"] == "a senior"


def test_the_self_test_refuses_a_vowel_noun_and_a_light_that_disagrees_with_the_marks():
    errors = []
    PC._check_articles({"elder": "elder"}, errors)
    assert errors and "starts with a vowel" in errors[0]
    errors = []
    PC._check_articles({"elder": "senior"}, errors)
    assert errors == []
    pk = copy.deepcopy(TABLE)
    pk["light_level"]["dark"] = 0.5
    errors = []
    PC._check_light_levels(pk, PACK, errors)
    assert any("light_level[dark]" in e for e in errors), errors
    pk = copy.deepcopy(TABLE)
    pk["light_level"]["dim"] = 0.1
    errors = []
    PC._check_light_levels(pk, PACK, errors)
    assert any("light_level[dim]" in e for e in errors), errors


def test_a_tier_whose_mark_is_not_a_world_mark_is_refused():
    tiers = copy.deepcopy(PACK["PERCEIVER_TIERS"])
    tiers["person"][2]["gate"]["mark"] = "tar"
    errors = []
    PC._check_marks_named(tiers, PACK, errors)
    assert any("mark 'tar' is not a MARKS kind" in e for e in errors), errors
    errors = []
    PC._check_marks_named(PACK["PERCEIVER_TIERS"], PACK, errors)
    assert errors == []
