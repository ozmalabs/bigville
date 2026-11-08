"""Phase 065b: the parts of impairment that Phase 065 left out. A distorted listener mishears a word, a name or a number;
a reader takes a written price one unit off; the simple listener mishears under its own represented impairment. Each
test names one acceptance item. The impairment switch is forced on through the game's scenario (no global change) or,
for the pack-wide simple listener, through a monkeypatched table value that monkeypatch restores.

The agent-view tests need the hunks of docs/phases/phase065b/hunks.json applied: they run in the scratch tree built by
build_clean_tree.py, not in the shared working tree.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                           # noqa: E402
from bigville.backends import speech_in                        # noqa: E402
from domains import agent_view, impairment as I, impairment_check as IC, numeracy  # noqa: E402
from domains import perceiver as P                             # noqa: E402
from domains import reading                                    # noqa: E402
from domains.pack import load_pack                             # noqa: E402

SEED = 305000
PLAYER = "Verity Peaseblossom"
PACK = load_pack("bigville")
PATH = os.path.join(_ROOT, "packs")
ALL_ENFORCED = {faculty: "enforced" for faculty in P.FACULTIES}


@pytest.fixture(scope="module")
def town():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


@pytest.fixture
def perception_on(monkeypatch):
    """The Phase 062 perceiver on for one test (the percept is what impairment distorts)."""
    monkeypatch.setitem(PACK["PERCEPTION"], "enabled", True)


def _neighbour(game, actor):
    world = game.world
    pos = world.actor_position(actor)
    for other in world._actors:
        if other == actor or not world.is_alive(other):
            continue
        p = world.actor_position(other)
        if p is not None and max(abs(p[0] - pos[0]), abs(p[1] - pos[1])) <= 1:
            return other
    return None


def _resident_with_neighbour(game):
    for name in sorted(game.characters):
        if game.world.is_alive(name) and _neighbour(game, name):
            return name
    raise AssertionError("the town has no resident with a neighbour")


@pytest.fixture
def drunk_town(town, perception_on):
    """A resident with a neighbour, at intoxication 0.5 (band drunk), with enforced faculties and the impairment
    switch on through the game's scenario. Restores the body, the turn, the faculties and the scenario afterwards."""
    world = town.world
    actor = _resident_with_neighbour(town)
    body = world._bodies[actor]
    old_level = world.eng.node(body)["attrs"].get("intoxication", 0.0)
    old_turn = world._turn
    world.eng.set_attr(body, "intoxication", 0.5)
    backend = town.backends[actor]
    had = "faculties" in vars(backend)
    old_faculties = vars(backend).get("faculties")
    backend.faculties = dict(ALL_ENFORCED)
    town.impairment_scenario = {"enabled": True, "strength": 1.0, "sources": ["intoxication"]}
    try:
        yield town, actor
    finally:
        town.impairment_scenario = None
        if had:
            backend.faculties = old_faculties
        else:
            del backend.faculties
        world.eng.set_attr(body, "intoxication", old_level)
        world._turn = old_turn


def _record(band, literacy="educated"):
    return {"light": "day", "sight": 5, "band": band, "literacy": literacy,
            "modes": {"impairment": "enforced", "numeracy": "enforced"}}


def _utterance(text, turn=1.0, speaker="Tom Baker", raw=None):
    return {"speaker": speaker, "target": "x", "text": text, "raw_data": raw, "turn": turn, "loudness": 1.0}


# ------------------------------------------------------------------ the tables and the self-test

def test_the_tables_are_clean_in_both_packs_and_the_switch_is_still_off():
    for name in ("bigville", "test_hamlet"):
        pack = load_pack(name)
        assert pack["IMPAIRMENT"]["enabled"] is False
        assert pack["IMPAIRMENT"]["mishearing"], name
        errors, warnings, info = [], [], []
        IC.check_impairment(os.path.join(PATH, name), errors, warnings, info)
        assert errors == [] and warnings == [], (name, errors, warnings)


def test_a_mechanism_on_a_kind_it_does_not_apply_to_is_an_error():
    rows = [dict(row) for row in PACK["DISTORTION"]]
    rows[0] = {**rows[0], "kinds": {**rows[0]["kinds"], "person": ["shift_quantity"]}}
    errors, warnings, info = [], [], []
    IC.check_impairment(os.path.join(PATH, "bigville"), errors, warnings, info, rows=rows)
    assert any("'shift_quantity' applies to" in error for error in errors), errors


def test_a_kind_the_code_does_not_know_is_an_error():
    rows = [dict(row) for row in PACK["DISTORTION"]]
    rows[0] = {**rows[0], "kinds": {**rows[0]["kinds"], "smell": ["mishear_word"]}}
    errors, warnings, info = [], [], []
    IC.check_impairment(os.path.join(PATH, "bigville"), errors, warnings, info, rows=rows)
    assert any("kind 'smell' is not one of" in error for error in errors), errors


def test_a_mishearing_pair_must_be_a_lowercase_word_other_than_the_heard_one():
    for bad in ({"Ale": ["ail"]}, {"ale": ["ale"]}, {"ale": []}, {"ale": ["ail", "ail"]}):
        errors = []
        IC._check_mishearing(bad, {"words": PACK["NUMERAL_WORDS"]["words"]}, errors)
        assert errors, bad


def test_the_numeral_words_must_run_in_order_so_a_count_can_shift_one_word():
    errors = []
    IC._check_mishearing({"ale": ["ail"]}, {"words": ["zero", "two", "one"]}, errors)
    assert any("NUMERAL_WORDS" in error for error in errors), errors


# ------------------------------------------------------------------ the switch is off by default

def test_with_the_switch_off_nothing_is_heard_wrongly_or_read_wrongly(town):
    actor = next(name for name in sorted(town.characters) if town.world.is_alive(name))
    rec = P.record(town, actor, {**{f: "enforced" for f in P.FACULTIES}}, "bigville")
    cfg = I.settings(None, "bigville")
    assert cfg["enabled"] is False
    assert I.mishear_simple(cfg, "bigville", "drunk", "Ada", 3, _utterance("two loaves"), []) is None
    assert I.mishear(town, actor, rec, _utterance("two loaves"), [], "bigville") is None
    assert I.quantity_shift(town, actor, rec, "ale_price", PACK["WRITTEN_MARKS"]["ale_price"], "bigville") is None
    assert I.quantity_referee(None) == {}


# ------------------------------------------------------------------ the heard words

def test_the_word_swaps_are_near_words_names_and_numbers():
    text = "Verity Peaseblossom says I have ale and two loaves"
    found = I._swaps(text, ["Verity Peaseblossom", "Tom Baker"], "bigville")
    assert ("mishear_word", "Tom Baker says I have ale and two loaves") in found
    assert ("mishear_word", "Tom Baker says I have ail and two loaves") not in found
    assert ("mishear_word", "Verity Peaseblossom says I have ail and two loaves") in found
    assert ("mishear_word", "Verity Peaseblossom says I have all and two loaves") in found
    assert ("shift_quantity", "Verity Peaseblossom says I have ale and one loaves") in found
    assert ("shift_quantity", "Verity Peaseblossom says I have ale and three loaves") in found


def test_a_number_word_at_the_end_of_the_list_shifts_one_way_only():
    found = I._swaps("twenty", [], "bigville")
    assert found == [("shift_quantity", "nineteen")]


def test_a_drunk_listener_mishears_about_its_rate_and_the_same_draw_repeats():
    cfg = dict(I.settings(None, "bigville"), enabled=True)
    text = "I have bread and two loaves for ale"
    outcomes = [I.mishear_simple(cfg, "bigville", "drunk", "Ada Smith", 3, _utterance(text, turn=float(t)), ["Tom Baker"])
                for t in range(300)]
    distorted = [out for out in outcomes if out["distorted"]]
    assert 60 <= len(distorted) <= 120, len(distorted)              # rate 0.3 over 300 draws
    assert all(out["text"] != text for out in distorted)
    assert all(out["mechanism"] in ("mishear_word", "shift_quantity") for out in distorted)
    again = [I.mishear_simple(cfg, "bigville", "drunk", "Ada Smith", 3, _utterance(text, turn=float(t)), ["Tom Baker"])
             for t in range(300)]
    assert again == outcomes


def test_a_sober_listener_hears_every_word_as_said():
    cfg = dict(I.settings(None, "bigville"), enabled=True)
    text = "I have bread and two loaves for ale"
    for t in range(200):
        out = I.mishear_simple(cfg, "bigville", "sober", "Ada Smith", 3, _utterance(text, turn=float(t)), ["Tom Baker"])
        assert out["distorted"] is False and out["text"] == text


def test_the_referee_row_keeps_the_truth_beside_what_was_heard():
    record = _utterance("I have ale")
    heard = {"text": "I have ail", "distorted": True, "sources": ["intoxication"], "subject": "speech:Tom Baker:1.0",
             "mechanism": "mishear_word"}
    row = I.utterance_referee(record, heard)
    assert row["kind"] == "utterance" and row["percept"] == "I have ail" and row["truth"] == "I have ale"
    assert row["distorted"] is True and row["mechanism"] == "mishear_word"


# ------------------------------------------------------------------ counts and written prices

def _fake_game(actor, turn, capability=0.3):
    """A game with one resident, one written price in sight (ale_price), and no real world. The resident's
    capability sets its numeracy tier: 0.3 is the tally tier, where one loaf is 'one loaf' and counts run to three."""
    node = {"attrs": {"role": "labourer", "capability": capability}}
    world = SimpleNamespace(
        _turn=turn, _map_node=None, _actors={actor: "node"},
        eng=SimpleNamespace(node=lambda _n: node),
        actor_position=lambda _a: (0, 0),
        physical_object_observations=lambda _a: [{"id": "ale_price", "kind": "price"}],
        _physical_location_cell=lambda _o: (0, 0),
        inventory=lambda _a: {},
        body_state=lambda _a: {"stamina_reserve": 1.0, "illness": 0.0},
    )
    return SimpleNamespace(world=world, characters={actor: SimpleNamespace(memories=[])},
                           impairment_scenario={"enabled": True, "strength": 1.0, "sources": ["intoxication"]})


def test_the_price_words_shift_one_loaf_up_for_a_tally_reader():
    mark = PACK["WRITTEN_MARKS"]["ale_price"]
    tally = numeracy.tier_row(0.3, "bigville")
    known = set()
    assert reading.percept(mark, "educated", known, tally, "bigville")["words"] == "a price sign: ALE one loaf a pint"
    assert reading.percept(mark, "educated", known, tally, "bigville", shift=1)["words"] == \
        "a price sign: ALE two loaves a pint"


def test_a_count_of_one_is_never_shifted_down_and_a_count_of_two_is_shifted_either_way():
    game = _fake_game("Ada", 1)
    rec = _record("drunk")
    seen_down = seen_up = False
    for turn in range(1, 400):
        game.world._turn = turn
        shift = I.quantity_shift(game, "Ada", rec, "ale_price", PACK["WRITTEN_MARKS"]["ale_price"], "bigville")
        assert shift is not None and shift["delta"] in (0, 1), shift
        seen_up = seen_up or shift["delta"] == 1
    assert seen_up
    two = dict(PACK["WRITTEN_MARKS"]["ale_price"], price=4.0)
    for turn in range(1, 400):
        game.world._turn = turn
        delta = I.quantity_shift(game, "Ada", rec, "ale_price", two, "bigville")["delta"]
        seen_down = seen_down or delta == -1
    assert seen_down


def test_a_reader_who_is_drunk_sees_a_price_one_loaf_off_and_the_referee_row_has_the_truth(monkeypatch):
    monkeypatch.setitem(PACK["READING"], "enabled", True)
    game = _fake_game("Ada", 1)
    rec = _record("drunk")
    shown, truths = [], []
    for turn in range(1, 300):
        game.world._turn = turn
        log = []
        rows = reading.writing_rows(game, "Ada", rec, "bigville", log)
        if log and log[0].get("distorted"):
            shown.append(rows[0]["percept"])
            truths.append(log[0]["truth"])
            assert log[0]["distortion_kind"] == "quantity" and log[0]["mechanism"] == "shift_quantity"
            assert log[0]["shift"] == 1
    assert shown and set(shown) == {"a price sign: ALE two loaves a pint"}
    # The referee's truth is the figure in coins (Phase 064: the represented reader reads the price as a figure).
    assert set(truths) == {"a price sign: ALE two coins a pint"}


def test_the_ledger_counts_a_wrong_price_by_its_kind_and_a_wrong_heard_sentence_too(monkeypatch):
    monkeypatch.setitem(PACK["READING"], "enabled", True)
    game = _fake_game("Ada", 1)
    rec = _record("drunk")
    for turn in range(1, 200):
        game.world._turn = turn
        log = []
        reading.writing_rows(game, "Ada", rec, "bigville", log)
        I.note_view(game, "Ada", rec, log, "bigville")
    game.world._turn = 1000
    I.note_view(game, "Ada", rec, [{"subject": "speech:Tom:1.0", "kind": "utterance", "distorted": True,
                                    "sources": ["intoxication"]}], "bigville")
    block = I.report_block(game, "bigville")["impairment"]
    assert set(block["by_kind"]) == {"quantity", "utterance"}
    assert block["by_kind"]["utterance"] == 1
    assert block["by_kind"]["quantity"] == block["percepts_shown_wrong"] - 1
    assert block["percepts_shown_wrong"] == sum(block["by_kind"].values())


# ------------------------------------------------------------------ the agent view (scratch tree: hunks applied)

def test_the_agent_view_gives_a_drunk_enforced_listener_a_wrong_heard_sentence_with_the_truth_in_the_referee(
        drunk_town, monkeypatch):
    drunk_game, actor = drunk_town
    world = drunk_game.world
    speaker = _neighbour(drunk_game, actor)
    record = _utterance("I have ale and two loaves", speaker=speaker, turn=1.0)
    monkeypatch.setattr(world, "heard_utterances", lambda who, **kw: [record] if who == actor else [])
    old_turn = world._turn
    wrong, truths = 0, []
    try:
        for turn in range(1, 80):
            world._turn = turn
            view = agent_view.build_agent_view(drunk_game, actor, mode="referee")
            heard = view["around"]["heard"][0]["text"]
            rows = [row for row in view["referee"]["perception"]["subjects"] if row["kind"] == "utterance"]
            assert len(rows) == 1 and rows[0]["truth"] == record["text"]
            if rows[0]["distorted"]:
                wrong += 1
                assert heard == rows[0]["percept"] and heard != record["text"]
                truths.append(rows[0]["truth"])
            else:
                assert heard == record["text"]
    finally:
        world._turn = old_turn
    assert 10 <= wrong <= 50, wrong                                   # rate 0.3 over 79 turns
    assert set(truths) == {record["text"]}


def test_a_listener_that_holds_the_faculty_itself_is_given_the_words_as_said(drunk_town, monkeypatch):
    drunk_game, actor = drunk_town
    rec = P.record(drunk_game, actor, {**{f: "enforced" for f in P.FACULTIES}, "impairment": "represented"}, "bigville")
    assert I.mishear(drunk_game, actor, rec, _utterance("I have ale"), [], "bigville") is None


# ------------------------------------------------------------------ the simple listener (its own represented impairment)

def _simple_backend():
    return SimpleNamespace(character=SimpleNamespace(name="Ada Smith", memories=[]), last_choice=None,
                           last_speech_turn=-1)


def _observations(records, band):
    return {"heard_utterances": records, "nearby_residents": [], "inventory": {}, "hunger": 0.0,
            "intoxication_band": band}


def test_the_simple_listener_mishears_only_when_its_switch_is_on_and_it_is_drunk(monkeypatch):
    backend = _simple_backend()
    with speech_in.switched(True):
        ctx = SimpleNamespace(observations=_observations([_utterance("I have bread", turn=0.5)], "drunk"), turn=1,
                              affordances=[])
        speech_in.hear(backend, ctx)
        assert speech_in.stats(backend).get("mishear_checked", 0) == 0    # the impairment switch is off
        monkeypatch.setitem(PACK["IMPAIRMENT"], "enabled", True)
        backend = _simple_backend()
        for turn in range(1, 61):
            records = [_utterance("I have bread and two loaves", turn=float(turn))]
            speech_in.hear(backend, SimpleNamespace(observations=_observations(records, "drunk"), turn=turn,
                                                    affordances=[]))
        stats = speech_in.stats(backend)
        assert stats["mishear_checked"] == 60
        assert 8 <= stats["mishear_distorted"] <= 30, stats


def test_the_simple_listener_sober_and_switch_on_hears_the_same_act_as_before(monkeypatch):
    monkeypatch.setitem(PACK["IMPAIRMENT"], "enabled", True)
    backend = _simple_backend()
    with speech_in.switched(True):
        for turn in range(1, 41):
            records = [_utterance("Good morning", turn=float(turn), raw={"act": "greeting", "slots": {}})]
            speech_in.hear(backend, SimpleNamespace(observations=_observations(records, "sober"), turn=turn,
                                                    affordances=[]))
    stats = speech_in.stats(backend)
    assert stats.get("mishear_distorted", 0) == 0
    assert stats["placed_raw"] == 40
