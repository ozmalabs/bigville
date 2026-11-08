"""Phase 062: the perceiver. What a resident perceives of a person or a thing depends on its light, its distance,
its intoxication, and its skill in the subject's trade, in tiers. The percept is the highest tier whose gates the
resident meets; the truth (referee block only) is the highest tier the subject's own facts allow.

Each test names one acceptance item of the brief. The switch (PERCEPTION.enabled) is forced on inside a fixture and
restored afterwards. Light is patched where the view reads it, since day and night is off by default.
"""
from __future__ import annotations

import copy
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                       # noqa: E402
from bigville.backends.cheap import DeterministicBackend   # noqa: E402
from bigville.backends.human import HumanBackend           # noqa: E402
from bigville.backends.llm import LLMBackend               # noqa: E402
from domains import perceiver as P                         # noqa: E402
from domains.perception_check import check_perception      # noqa: E402
from domains.pack import load_pack                         # noqa: E402
from worlds import daynight as dn                          # noqa: E402

SEED = 305000
PLAYER = "Verity Peaseblossom"
PACK = load_pack("bigville")
PACK_NAME = "bigville"
DIGIT = re.compile(r"\d")
REFEREE_ONLY = set(PACK["AGENT_VIEW_REFEREE_ONLY"])
PERSON_TIERS = PACK["PERCEIVER_TIERS"]["person"]
THING_TIERS = PACK["PERCEIVER_TIERS"]["thing"]
PATH_BIGVILLE = os.path.join(_ROOT, "packs", "bigville")
PATH_HAMLET = os.path.join(_ROOT, "packs", "test_hamlet")


@pytest.fixture(scope="module")
def town():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


@pytest.fixture
def perception_on():
    """The pack switch forced on for one test, then restored (the pack tables are cached per process)."""
    table = PACK["PERCEPTION"]
    previous = table["enabled"]
    table["enabled"] = True
    try:
        yield
    finally:
        table["enabled"] = previous


def _rec(*, light="day", band="sober", skills=None, skill_full=False, sight=7, literacy="labouring"):
    return {"light": light, "light_known": True, "sight": sight, "band": band, "skills": dict(skills or {}),
            "skill_full": skill_full, "literacy": literacy,
            "modes": {f: "enforced" for f in P.FACULTIES}}


def _smith(marks=None):
    return {"stage": "grown person", "job": "smith", "trade_skills": ["smithing"], "marks": dict(marks or {})}


def _labourer():
    return {"stage": "grown person", "job": "labourer", "trade_skills": [], "marks": {}}


def _neighbour(game, actor):
    """A living resident within one cell of `actor`, or None."""
    world = game.world
    pos = world.actor_position(actor)
    for other in world._actors:
        if other == actor or not world.is_alive(other):
            continue
        p = world.actor_position(other)
        if p is not None and max(abs(p[0] - pos[0]), abs(p[1] - pos[1])) <= 1:
            return other
    return None


# ------------------------------------------------------------------ the pack, the switch, the self-test
def test_pack_table_is_clean_in_both_packs_and_the_switch_is_off():
    for name in ("bigville", "test_hamlet"):
        pack = load_pack(name)
        assert pack["PERCEPTION"]["enabled"] is False
        assert set(pack["PERCEIVER_TIERS"]) == set(P.KINDS)
        errors, warnings, info = [], [], []
        check_perception(os.path.join(_ROOT, "packs", name), errors, warnings, info)
        assert errors == [] and warnings == []


def test_self_test_finds_a_kind_with_no_tier_0():
    errors, warnings, info = [], [], []
    tiers = copy.deepcopy(PACK["PERCEIVER_TIERS"])
    tiers["thing"] = tiers["thing"][1:]          # the thing kind now starts at tier 1
    check_perception(PATH_BIGVILLE, errors, warnings, info, tiers=tiers)
    assert any("PERCEIVER_TIERS[thing] has no tier 0" in e for e in errors), errors


def test_self_test_finds_a_tier_with_an_unknown_gate():
    errors, warnings, info = [], [], []
    tiers = copy.deepcopy(PACK["PERCEIVER_TIERS"])
    tiers["person"][2]["gate"]["weather_clear"] = True
    check_perception(PATH_BIGVILLE, errors, warnings, info, tiers=tiers)
    assert any("gate 'weather_clear' is unknown" in e for e in errors), errors


def test_self_test_finds_a_word_that_names_a_field_its_kind_does_not_fill():
    errors, warnings, info = [], [], []
    tiers = copy.deepcopy(PACK["PERCEIVER_TIERS"])
    tiers["thing"][1]["words"] = "{stage}"
    check_perception(PATH_BIGVILLE, errors, warnings, info, tiers=tiers)
    assert any("does not fill" in e for e in errors), errors


# ------------------------------------------------------------------ the tiers and the gates
def test_the_same_man_is_described_differently_by_a_smith_and_by_a_labourer_in_daylight_near_and_far():
    subject = _smith()
    smith_eye = _rec(skills={"smithing": 0.8})
    plain_eye = _rec(skills={})
    near_smith = P.percept("person", subject, 1, smith_eye, PACK_NAME)
    near_plain = P.percept("person", subject, 1, plain_eye, PACK_NAME)
    far_smith = P.percept("person", subject, 5, smith_eye, PACK_NAME)
    far_plain = P.percept("person", subject, 5, plain_eye, PACK_NAME)
    assert near_smith["words"] == "smith, judging by the work"
    assert near_plain["words"] == "a grown person"
    assert far_smith["words"] == "smith, judging by the work"      # the trade gate has no distance
    assert far_plain["words"] == "a grown person"


def test_in_the_dark_the_same_man_is_a_person_whatever_the_skill():
    subject = _smith()
    for skills in ({}, {"smithing": 0.8}):
        for distance in (1, 5):
            out = P.percept("person", subject, distance, _rec(light="dark", skills=skills), PACK_NAME)
            assert out["words"] == "a person" and out["tier"] == 0


def test_a_drunk_smith_does_not_recognise_the_trade():
    out = P.percept("person", _smith(), 1, _rec(band="drunk", skills={"smithing": 0.8}), PACK_NAME)
    assert out["words"] == "a grown person"
    out = P.percept("person", _smith(), 1, _rec(band="tipsy", skills={"smithing": 0.8}), PACK_NAME)
    assert out["tier"] == 4


def test_a_subject_with_no_trade_is_never_given_the_trade_tier():
    out = P.percept("person", _labourer(), 1, _rec(skills={"smithing": 1.0}), PACK_NAME)
    assert out["tier"] < 4 and "judging by the work" not in out["words"]
    assert out["truth_tier"] < 4


def test_marks_need_the_mark_and_the_near_range_and_the_light():
    dirty = P.percept("person", _smith({"dirt": 1.0}), 1, _rec(), PACK_NAME)
    assert dirty["words"] == "a dirty grown person"
    assert dirty["truth"] == "smith, judging by the work"          # the trade is the truth at the top tier
    sooty = _smith({"soot": 1.0})
    near = P.percept("person", sooty, 1, _rec(skills={}), PACK_NAME)
    assert near["words"] == "a grown person covered in coal dust"
    far = P.percept("person", sooty, 5, _rec(skills={}), PACK_NAME)
    assert far["words"] == "a grown person"                        # too far to see the coal dust
    dark = P.percept("person", sooty, 1, _rec(light="dark", skills={}), PACK_NAME)
    assert dark["words"] == "a person"                             # no light, no detail
    dirt_only = P.percept("person", {"stage": "child", "job": "", "trade_skills": [], "marks": {"dirt": 0.9}},
                          2, _rec(), PACK_NAME)
    assert dirt_only["words"] == "a dirty child"
    assert P.percept("person", {"stage": "child", "job": "", "trade_skills": [], "marks": {"dirt": 0.2}},
                     2, _rec(), PACK_NAME)["words"] == "a child"      # below mark_min_level


def test_the_chosen_tier_never_exceeds_what_its_gates_allow():
    """For every combination of light, band, skill and distance: no tier above the chosen one has all its gates met."""
    subject = _smith({"soot": 1.0})
    for light in ("day", "dim", "dark", "lamplight"):
        for band in ("sober", "tipsy", "drunk"):
            for level in (0.0, 0.8):
                for distance in (0, 2, 5):
                    rec = _rec(light=light, band=band, skills={"smithing": level})
                    out = P.percept("person", subject, distance, rec, PACK_NAME)
                    ctx = {"light": light, "band": band, "skills": rec["skills"], "skill_full": False,
                           "distance": distance}
                    for row in PERSON_TIERS:
                        if row["tier"] > out["tier"]:
                            assert not P._passes(row["gate"], ctx, subject, PACK_NAME, False)


def test_the_truth_is_the_subjects_own_facts_and_ignores_the_observer():
    subject = _smith({"soot": 1.0})
    blind = P.percept("person", subject, 6, _rec(light="dark", band="stupefied"), PACK_NAME)
    keen = P.percept("person", subject, 1, _rec(skills={"smithing": 1.0}), PACK_NAME)
    assert blind["truth"] == keen["truth"] == "smith, judging by the work"
    assert blind["tier"] == 0 and keen["tier"] == 4


def test_the_things_are_something_in_the_dark_and_their_kind_in_the_light():
    assert P.percept("thing", P.thing_subject("bucket"), 0, _rec(light="dark"), PACK_NAME) == {
        "tier": 0, "words": "something", "truth_tier": 1, "truth": "bucket"}
    assert P.percept("thing", P.thing_subject("bucket"), 0, _rec(), PACK_NAME)["words"] == "bucket"


# ------------------------------------------------------------------ the declaration
def test_the_backends_declare_their_faculties_and_an_undeclared_one_takes_the_fallback():
    assert set(P.declared(DeterministicBackend, PACK_NAME)) == set(P.FACULTIES)
    assert set(P.declared(DeterministicBackend, PACK_NAME).values()) == {"represented"}
    assert set(P.declared(LLMBackend, PACK_NAME).values()) == {"enforced"}
    assert set(P.declared(HumanBackend, PACK_NAME).values()) == {"enforced"}
    assert set(P.declared(None, PACK_NAME).values()) == {PACK["PERCEPTION"]["fallback"]}


def test_a_bad_declaration_is_refused():
    class Bad:
        faculties = {"senses": "sometimes"}
    with pytest.raises(ValueError):
        P.declared(Bad, PACK_NAME)

    class Unknown:
        faculties = {"telepathy": "enforced"}
    with pytest.raises(ValueError):
        P.declared(Unknown, PACK_NAME)


# ------------------------------------------------------------------ the game: the view and the referee block
def test_with_the_switch_off_the_view_has_no_perception_block_and_the_words_are_as_before(town):
    view = town.agent_view(town.player, mode="referee")
    assert "perception" not in view["referee"]
    assert all("tier" not in row for row in view["around"]["people"])


def test_the_truth_reaches_the_referee_block_and_not_the_agent_view(town, perception_on, monkeypatch):
    """A neighbour with soot on it, seen in the dark: the agent view says 'a person'; the referee block says what is there."""
    world = town.world
    other = _neighbour(town, town.player)
    assert other is not None, "the founding town has a resident beside the player"
    monkeypatch.setattr(world, "visible_marks", lambda actor: {"soot": 1.0} if actor == other else {}, raising=False)
    original = P.person_subject

    def no_trade(game, name, pack):
        subject = original(game, name, pack)
        return {**subject, "job": "", "trade_skills": []} if name == other else subject
    monkeypatch.setattr(P, "person_subject", no_trade)
    monkeypatch.setattr(dn, "view_light", lambda w, a: "dark")
    agent = town.agent_view(town.player)
    referee = town.agent_view(town.player, mode="referee")
    assert "referee" not in agent
    assert "coal dust" not in repr(agent), "the truth must not reach the agent view"
    rows = [row for row in referee["referee"]["perception"]["subjects"] if row["subject"] == other]
    assert rows, "the neighbour is in the referee block"
    assert rows[0]["percept"] == "a person" and rows[0]["tier"] == 0
    assert rows[0]["truth"] == "a grown person covered in coal dust" and rows[0]["truth_tier"] == 3


def test_the_percept_in_the_view_is_the_percept_in_the_referee_block(town, perception_on):
    agent = town.agent_view(town.player)
    referee = town.agent_view(town.player, mode="referee")
    logged = {row["subject"]: row["percept"] for row in referee["referee"]["perception"]["subjects"]
              if row["kind"] == "person"}
    for person in agent["around"]["people"]:
        if "name" in person:
            assert person["name"] in logged
        else:
            assert person["description"] in set(logged.values())


def test_a_resident_in_the_dark_sees_a_person_and_a_known_name_is_withheld(town, perception_on, monkeypatch):
    other = _neighbour(town, town.player)
    monkeypatch.setattr(dn, "view_light", lambda w, a: "dark")
    view = town.agent_view(town.player)
    beside = [p for p in view["around"]["people"] if p.get("distance") and "looks" not in p]
    assert beside, "a person beside the player in the dark has no looks"
    assert all("name" not in p for p in beside)
    assert all(p.get("description") == "a person" for p in beside)


def test_day_and_night_off_gives_the_light_as_the_daylight_by_default(town, perception_on):
    view = town.agent_view(town.player, mode="referee")
    summary = view["referee"]["perception"]["perceiver"]
    assert summary["light"] == "day" and summary["light_known"] is False


def test_the_simple_backend_is_represented_so_its_record_is_the_full_value(town, perception_on):
    modes = P.declared(DeterministicBackend, PACK_NAME)
    rec = P.record(town, town.player, modes, PACK_NAME)
    assert rec["light"] == "day" and rec["band"] == "sober" and rec["skill_full"] is True
    assert rec["sight"] == int(PACK["HEARING"]["sight_range"])


def test_a_thing_seen_at_tier_0_has_no_handle_and_its_option_is_not_offered(town, perception_on, monkeypatch):
    world = town.world
    fake = {"id": "hidden_cup", "kind": "cup", "location": "world"}
    option = {"action": "work", "kind": "cup", "recipe": "cup", "target": "hidden_cup", "score": 1.0, "trade": "smith"}
    original = world.actor_affordances
    monkeypatch.setattr(world, "physical_object_observations", lambda actor: [fake])
    monkeypatch.setattr(world, "_physical_location_cell", lambda *a, **k: None)
    monkeypatch.setattr(world, "actor_affordances", lambda actor: [*original(actor), option])
    monkeypatch.setattr(dn, "view_light", lambda w, a: "dark")
    view = town.agent_view(town.player)
    assert view["around"]["things"] == [{"what": "something"}]
    assert "cup" not in repr(view["can"])
    monkeypatch.setattr(dn, "view_light", lambda w, a: "day")
    assert any(row.get("handle") == "hidden_cup" for row in town.agent_view(town.player)["around"]["things"])


def test_a_thing_in_the_light_is_named_with_its_handle(town, perception_on, monkeypatch):
    world = town.world
    fake = {"id": "shiny_cup", "kind": "cup", "location": "world"}
    monkeypatch.setattr(world, "physical_object_observations", lambda actor: [fake])
    monkeypatch.setattr(world, "_physical_location_cell", lambda *a, **k: None)
    view = town.agent_view(town.player)
    assert {"handle": "shiny_cup", "what": "cup"} in view["around"]["things"]


def test_the_leak_rules_hold_with_the_switch_on_for_founding_residents(town, perception_on):
    for actor in list(town.characters)[:25]:
        view = town.agent_view(actor)
        assert "referee" not in view
        assert set(view["around"]) <= set(PACK["AGENT_VIEW_WHITELIST"]["around"])
        for person in view["around"]["people"]:
            assert set(person) <= set(PACK["AGENT_VIEW_WHITELIST"]["person"])
            for value in person.values():
                if isinstance(value, str):
                    assert not DIGIT.search(value)
                assert not isinstance(value, (int, float))


def test_the_simple_backend_never_gets_a_view_so_the_perceiver_does_not_touch_its_context(town, perception_on):
    actor = next(name for name in town.characters if name != town.player and town.world.is_alive(name))
    assert isinstance(town.backends[actor], DeterministicBackend)
    assert town._context(actor).agent_view is None


def test_with_day_and_night_on_the_perceiver_reads_the_light_the_resident_sees(perception_on):
    game = create_game(scenario="town100", seed=SEED, player=PLAYER)
    dn.switch_on(game.world)
    view = game.agent_view(game.player, mode="referee")
    summary = view["referee"]["perception"]["perceiver"]
    assert summary["light_known"] is True
    assert summary["light"] in P.LIGHTS
    assert summary["light"] == dn.view_light(game.world, game.player)
