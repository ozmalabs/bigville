"""Phase 064: reading and numbers at the agent view. A written mark (a sign, a price, a notice) reads as the resident can
read it: the words it knows amid squiggles, the short text, or the whole text, by its literacy tier. A count or a price
is put into the words of its numeracy tier. A word is learned from use, and the truth is in the referee block only.

Each test names one acceptance item of the brief. The switches (PERCEPTION.enabled and READING.enabled) are forced on
inside a fixture and restored afterwards. The written marks are scripted: the world's physical objects are replaced by
the rows a test gives, since the 100-resident town has none.
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
from domains import numeracy, reading                      # noqa: E402
from domains import perceiver as P                         # noqa: E402
from domains.pack import load_pack                         # noqa: E402
from domains.reading_check import check_reading            # noqa: E402
from worlds import daynight as dn                          # noqa: E402

SEED = 305000
PLAYER = "Verity Peaseblossom"
PACK = load_pack("bigville")
DIGIT = re.compile(r"\d")
PATH_BIGVILLE = os.path.join(_ROOT, "packs", "bigville")
PATH_HAMLET = os.path.join(_ROOT, "packs", "test_hamlet")
KINDS = {"ale_sign": "sign", "ale_price": "price", "mill_notice": "notice"}
SIGN = "a sign: ALE sold here"


@pytest.fixture
def game():
    """A fresh 100-resident town (cheap to build, so each test gets its own)."""
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


@pytest.fixture
def reading_on():
    """PERCEPTION and READING forced on for one test, then restored (the pack tables are cached per process)."""
    previous = (PACK["PERCEPTION"]["enabled"], PACK["READING"]["enabled"])
    PACK["PERCEPTION"]["enabled"] = True
    PACK["READING"]["enabled"] = True
    try:
        yield
    finally:
        PACK["PERCEPTION"]["enabled"], PACK["READING"]["enabled"] = previous


@pytest.fixture
def tiers_restored():
    """Lets a test edit the LITERACY_TIERS rows in place; the rows are put back afterwards."""
    saved = copy.deepcopy(PACK["LITERACY_TIERS"])
    try:
        yield PACK["LITERACY_TIERS"]
    finally:
        PACK["LITERACY_TIERS"][:] = saved


def _resident(game):
    """A living resident other than the player."""
    return next(name for name in game.characters if name != game.player and game.world.is_alive(name))


def _as(game, name, *, literacy, role, capability):
    """Set a resident's reading and numbers. It takes the human backend's faculties (enforced), so the view degrades
    what the resident is shown; the simple backend would be 'represented' and read the full text."""
    world = game.world
    world.eng.set_attr(world._actors[name], "literacy", float(literacy))
    world.eng.set_attr(world._actors[name], "role", role)
    world.eng.set_attr(world._actors[name], "capability", float(capability))
    game.backends[name] = game.backends[game.player]
    return name


def _objects(monkeypatch, game, *ids):
    """Replace the physical objects in view with the given written marks (no cell, so every resident is at hand)."""
    rows = [{"id": i, "kind": KINDS[i], "location": "world"} for i in ids]
    monkeypatch.setattr(game.world, "physical_object_observations", lambda actor: [dict(r) for r in rows])


def _writing(game, name, mode="agent"):
    view = game.agent_view(name, mode=mode)
    return view["around"].get("writing"), view


def _referee_rows(game, name):
    view = game.agent_view(name, mode="referee")
    return [s for s in view["referee"]["perception"]["subjects"] if s["kind"] == "writing"]


# ------------------------------------------------------------------ the pack and the self-test
def test_the_pack_tables_are_clean_in_both_packs_and_reading_is_off():
    for name in ("bigville", "test_hamlet"):
        pack = load_pack(name)
        assert pack["READING"]["enabled"] is False
        errors, warnings, info = [], [], []
        check_reading(os.path.join(_ROOT, "packs", name), errors, warnings, info)
        assert errors == [] and warnings == []


def test_self_test_finds_a_written_kind_with_no_tier_text():
    errors, warnings, info = [], [], []
    kinds = copy.deepcopy(PACK["WRITTEN_KINDS"])
    del kinds["sign"]["tiers"]["words"]
    check_reading(PATH_BIGVILLE, errors, warnings, info, kinds=kinds)
    assert any("WRITTEN_KINDS[sign] has no tier text for 'words'" in e for e in errors), errors


def test_self_test_finds_a_mark_whose_kind_is_unknown():
    errors, warnings, info = [], [], []
    marks = copy.deepcopy(PACK["WRITTEN_MARKS"])
    marks["ale_sign"]["kind"] = "banner"
    check_reading(PATH_BIGVILLE, errors, warnings, info, marks=marks)
    assert any("kind 'banner' is not in WRITTEN_KINDS" in e for e in errors), errors


def test_self_test_finds_a_price_mark_with_no_unit():
    errors, warnings, info = [], [], []
    marks = copy.deepcopy(PACK["WRITTEN_MARKS"])
    del marks["ale_price"]["unit"]
    check_reading(PATH_BIGVILLE, errors, warnings, info, marks=marks)
    assert any("is not in NUMERACY_UNITS" in e for e in errors), errors


def test_the_hamlet_pack_passes_its_own_seed_and_tiers():
    errors, warnings, info = [], [], []
    check_reading(PATH_HAMLET, errors, warnings, info)
    assert errors == [] and warnings == []


# ------------------------------------------------------------------ the four residents of rising literacy
def test_the_same_sign_reads_as_squiggles_as_a_word_as_a_phrase_and_in_full(game, monkeypatch, reading_on):
    _objects(monkeypatch, game, "ale_sign")
    readings = []
    for literacy, role, capability in ((0.0, "smith", 0.55), (0.0, "labourer", 0.55),
                                       (0.55, "labourer", 0.55), (0.9, "labourer", 0.9)):
        name = _as(game, _resident(game), literacy=literacy, role=role, capability=capability)
        rows, _ = _writing(game, name)
        readings.append(rows[0]["percept"])
    assert readings == [
        "a sign: marks you cannot read",     # knows no word on it: squiggles only
        "a sign: ALE ~~~ ~~~",               # a labourer knows ALE from his trade, and the rest is squiggles
        "a sign: ALE, sold here",            # functional literacy: the short text
        "a sign: ALE sold here",             # educated literacy: all of it
    ]


def test_a_price_is_a_figure_for_a_numerate_resident_and_a_loaf_count_for_a_tally_resident(game, monkeypatch,
                                                                                         reading_on):
    _objects(monkeypatch, game, "ale_price")
    name = _resident(game)
    _as(game, name, literacy=0.9, role="labourer", capability=0.55)
    rows, _ = _writing(game, name)
    assert rows[0]["percept"] == "a price sign: ALE one loaf a pint"
    _as(game, name, literacy=0.9, role="labourer", capability=0.9)
    rows, _ = _writing(game, name)
    assert rows[0]["percept"] == "a price sign: ALE two coins a pint"


def test_a_word_learned_from_use_appears_from_the_next_view(game, monkeypatch, reading_on):
    _objects(monkeypatch, game, "ale_sign")
    name = _as(game, _resident(game), literacy=0.0, role="miller", capability=0.55)
    monkeypatch.setattr(game.world, "inventory", lambda actor: {"ale": 1.0} if actor == name else {})
    rows, _ = _writing(game, name)
    assert rows[0]["percept"] == "a sign: marks you cannot read"   # the view that sees ale carried teaches it
    learned = [m for m in game.characters[name].memories if m.kind == "learned_word"]
    assert [m.content["word"] for m in learned] == ["ale"]
    rows, _ = _writing(game, name)
    assert rows[0]["percept"] == "a sign: ALE ~~~ ~~~"
    rows, _ = _writing(game, name)
    assert len([m for m in game.characters[name].memories if m.kind == "learned_word"]) == 1   # learned once


def test_nothing_is_learned_in_the_dark_or_past_the_cap(game, monkeypatch, reading_on):
    _objects(monkeypatch, game, "ale_sign")
    name = _as(game, _resident(game), literacy=0.0, role="miller", capability=0.55)
    monkeypatch.setattr(game.world, "inventory", lambda actor: {"ale": 1.0} if actor == name else {})
    monkeypatch.setattr(dn, "view_light", lambda world, actor: "dark")
    rows, _ = _writing(game, name)
    assert not rows
    assert not [m for m in game.characters[name].memories if m.kind == "learned_word"]
    monkeypatch.undo()
    _objects(monkeypatch, game, "ale_sign")
    monkeypatch.setattr(game.world, "inventory", lambda actor: {"ale": 1.0} if actor == name else {})
    previous = PACK["READING"]["learned_max"]
    PACK["READING"]["learned_max"] = 0
    try:
        _writing(game, name)
    finally:
        PACK["READING"]["learned_max"] = previous
    assert not [m for m in game.characters[name].memories if m.kind == "learned_word"]


def test_recognition_is_the_trade_seed_the_own_name_and_the_common_numerals(game):
    name = _as(game, _resident(game), literacy=0.0, role="labourer", capability=0.55)
    known = reading.known_words(game, name, "bigville")
    assert {"ale", "bread", "one", "two", "three"} <= known
    assert "iron" not in known
    _as(game, name, literacy=0.0, role="smith", capability=0.55)
    known = reading.known_words(game, name, "bigville")
    assert "iron" in known and "ale" not in known


# ------------------------------------------------------------------ switches, the referee block, digits
def test_the_view_has_no_writing_section_unless_reading_is_on(game, monkeypatch):
    _objects(monkeypatch, game, "ale_sign")
    name = _resident(game)
    previous = (PACK["PERCEPTION"]["enabled"], PACK["READING"]["enabled"])
    try:
        PACK["PERCEPTION"]["enabled"], PACK["READING"]["enabled"] = True, False
        assert "writing" not in game.agent_view(name, mode="referee")["around"]
        PACK["PERCEPTION"]["enabled"], PACK["READING"]["enabled"] = False, True
        assert "writing" not in game.agent_view(name, mode="referee")["around"]
    finally:
        PACK["PERCEPTION"]["enabled"], PACK["READING"]["enabled"] = previous


def test_the_truth_is_in_the_referee_block_only(game, monkeypatch, reading_on):
    _objects(monkeypatch, game, "ale_sign")
    name = _as(game, _resident(game), literacy=0.0, role="smith", capability=0.55)
    agent = game.agent_view(name, mode="agent")
    assert "ALE" not in str(agent["around"].get("writing")) and "truth" not in str(agent)
    rows = _referee_rows(game, name)
    assert rows[0]["percept"] == "a sign: marks you cannot read"
    assert rows[0]["truth"] == SIGN and rows[0]["truth_tier"] == "educated"


def test_no_written_percept_carries_a_digit_at_any_tier(game, monkeypatch, reading_on):
    _objects(monkeypatch, game, "ale_sign", "ale_price", "mill_notice")
    for literacy, role, capability in ((0.0, "smith", 0.55), (0.0, "labourer", 0.55), (0.55, "labourer", 0.55),
                                       (0.9, "labourer", 0.9), (0.9, "labourer", 0.55)):
        name = _as(game, _resident(game), literacy=literacy, role=role, capability=capability)
        rows, _ = _writing(game, name, mode="referee")
        for row in rows:
            assert not DIGIT.search(row["percept"])
        for subject in _referee_rows(game, name):
            assert not DIGIT.search(subject["percept"])


def test_a_represented_literacy_gets_the_full_text(game, monkeypatch, reading_on):
    _objects(monkeypatch, game, "ale_sign")
    name = _resident(game)
    rec = P.record(game, name, {f: "represented" for f in P.FACULTIES}, "bigville")
    rows = reading.writing_rows(game, name, rec, "bigville", [])
    assert rows == [{"percept": SIGN}]


# ------------------------------------------------------------------ numbers as words, and the tiers are data
def test_counts_are_spelled_and_banded_by_the_tier(game):
    assert [numeracy.spell(n, "bigville") for n in (0, 7, 20, 42, 100, 105, 999)] == [
        "zero", "seven", "twenty", "forty-two", "one hundred", "one hundred and five",
        "nine hundred and ninety-nine"]
    tally = numeracy.tier_row(0.55, "bigville")
    commercial = numeracy.tier_row(0.9, "bigville")
    assert tally["tier"] == "tally" and commercial["tier"] == "commercial"
    assert numeracy.quantity_words(1, tally, "bigville", "loaf") == "one loaf"
    assert numeracy.quantity_words(5, tally, "bigville", "loaf") == "a few loaves"
    assert numeracy.quantity_words(9, tally, "bigville", "loaf") == "many loaves"
    assert numeracy.price_words(2.0, "loaf", tally, "bigville") == "one loaf"
    assert numeracy.price_words(2.0, "loaf", commercial, "bigville") == "two coins"
    with pytest.raises(ValueError):
        numeracy.spell(1000, "bigville")


def test_the_reading_mode_of_a_tier_is_data(game, monkeypatch, reading_on, tiers_restored):
    _objects(monkeypatch, game, "ale_sign")
    name = _as(game, _resident(game), literacy=0.0, role="labourer", capability=0.55)
    assert _writing(game, name)[0][0]["percept"] == "a sign: ALE ~~~ ~~~"
    tiers_restored[0]["reads"] = "short"
    assert _writing(game, name)[0][0]["percept"] == "a sign: ALE, sold here"
