"""Phase 060: structured speech in. The simple backend places what it hears and acts on a few acts.

Each test names one acceptance item of the brief. The contexts are built by hand (no network, no provider).
The village tests run the simple town for a few turns, and the full 60-turn comparison is in
docs/phases/phase060 (a script, not a test: it takes minutes).
"""
from __future__ import annotations

import pytest

from bigville.backends import ActorContext, DeterministicBackend, speech_in
from bigville.backends.conversation import DEFAULT_TEMPLATES, ConversationMessage, TemplateConversationInterface
from bigville.backends.speech import DeterministicSpeechBackend
from bigville.character import CharacterDefinition, MemoryRecord
from bigville.runtime import _realize_meaning
from domains import speech_grammar as G
from domains.pack import load_pack
from domains.speech_acts_check import check_speech_acts

PACK = "packs/bigville"
PACK_TABLE = load_pack("bigville")
ROWS = {row["act"]: row for row in PACK_TABLE["SPEECH_ACTS"]}
UNDERSTOOD = [row["act"] for row in PACK_TABLE["SPEECH_ACTS"] if row["understood_by"] == "simple"]
TABLES = {name: PACK_TABLE[name] for name in ("SPEECH_CHATTER", "SPEECH_WEATHER")}
RULES = G.rules_for(PACK_TABLE["SPEECH_ACTS"], DEFAULT_TEMPLATES, TABLES)

# Realistic slot values for rendering a template. Each slot kind has one value that places as its own act.
SLOTS = {"target": "bram", "reason": "the ale", "subject": "the ale", "commitment": "mend the gate",
         "request": "give me the bread", "item": "bread", "recipient": "bram", "thing": "bread",
         "answer": "I am managing, thank you", "news": "the mill burned", "question": "how was your day",
         "content": "the weather is clear", "quantity": "2", "seller": "bram", "container": "the chest",
         "topic": "work"}


@pytest.fixture(autouse=True)
def _switch_off_by_default():
    """Every test starts with the pack's switch (off) unless it forces it."""
    with speech_in.switched(False):
        yield


def _character(name="ada", role="baker", **identity):
    return CharacterDefinition(character_id=name, name=name, identity={"role": role, **identity})


def _context(character, *, turn=100, nearby=(), heard=(), inventory=None, hunger=0.0, affordances=(),
             hour=10.0):
    observations = {
        "calendar": {"hour": hour, "weather": "clear"},
        "hunger": hunger, "energy": 100.0,
        "nearby_residents": list(nearby),
        "heard_utterances": list(heard),
        "inventory": dict(inventory or {}),
    }
    return ActorContext(character=character, turn=turn, observations=observations,
                        affordances=list(affordances))


def _record(text, *, speaker="bram", turn=99.0, raw=None):
    return {"speaker": speaker, "target": "ada", "text": text, "raw_data": raw, "turn": turn, "loudness": 1.0}


def _near(name="bram", tie=0.6):
    return {"id": name, "name": name, "distance": 2, "tie_strength": tie, "band_code": 1.0}


# ---------------------------------------------------------------- the table and the self-test

def test_pack_table_is_clean_in_both_packs():
    for pack in (PACK, "packs/test_hamlet"):
        errors, warnings, info = [], [], []
        check_speech_acts(pack, errors, warnings, info)
        assert errors == [] and warnings == [], (pack, errors, warnings)


def test_switch_is_off_in_the_pack():
    assert PACK_TABLE["SPEECH_UNDERSTANDING"]["enabled"] is False
    assert load_pack("test_hamlet")["SPEECH_UNDERSTANDING"]["enabled"] is False


def test_self_test_finds_a_template_with_no_act():
    errors, warnings, info = [], [], []
    templates = dict(DEFAULT_TEMPLATES, wave="Hello there, {target}.")
    check_speech_acts(PACK, errors, warnings, info, templates=templates)
    assert any("DEFAULT_TEMPLATES[wave]: a template with no act" in e for e in errors), errors


def test_self_test_finds_an_act_with_no_template():
    errors, warnings, info = [], [], []
    rows = [dict(row) for row in PACK_TABLE["SPEECH_ACTS"]]
    greeting = next(row for row in rows if row["act"] == "greeting")
    greeting.update(template=None, meaning=[])
    check_speech_acts(PACK, errors, warnings, info, acts=rows)
    assert any("SPEECH_ACTS[greeting]" in e and "no template" in e for e in errors), errors


def test_self_test_finds_a_row_that_no_speaker_emits_as_meaning():
    errors, warnings, info = [], [], []
    rows = [dict(row) for row in PACK_TABLE["SPEECH_ACTS"]]
    next(row for row in rows if row["act"] == "promise")["emitted_by"] = ["simple_message"]
    check_speech_acts(PACK, errors, warnings, info, acts=rows)
    assert any("DeterministicSpeechBackend emits 'promise'" in e for e in errors), errors


# ---------------------------------------------------------------- round trips through the grammar

MEANING_CASES = [
    ("greeting", {}), ("thanks", {}), ("apology", {}), ("farewell", {}), ("promise", {}),
    ("complaint", {}), ("barb", {}), ("hedged", {}), ("answer", {}), ("request", {}), ("offer", {}),
    ("question", {}), ("smalltalk", {"trade": "smith"}), ("smalltalk", {"trade": "pilot"}),
    ("smalltalk", {"trade": "", "weather": "rain"}),
    ("share", {"event": None, "weather": "rain"}),
    ("share", {"event": {"kind": "injury", "subject": "bram", "detail": "bram was hurt at the mill",
                         "self": False}}),
]


@pytest.mark.parametrize("kind, context", MEANING_CASES, ids=lambda v: str(v)[:40])
def test_round_trip_of_each_emitted_meaning(kind, context):
    """A simple speaker's meaning, realised as text, is placed as the same act from the text alone."""
    meaning = DeterministicSpeechBackend._meaning("bram", kind, context=context)
    text = _realize_meaning(meaning)
    placed = G.place(text, RULES)
    assert placed is not None, f"{kind}: {text!r} is not placed"
    assert placed["act"] == kind, (kind, text, placed)


@pytest.mark.parametrize("act", [a for a in UNDERSTOOD if ROWS[a]["template"] is not None])
def test_round_trip_of_each_template_wording(act):
    """A template the pack names, rendered with sample slots, is placed as that act."""
    row = ROWS[act]
    if G.template_pattern(DEFAULT_TEMPLATES[row["template"]]) is None:
        pytest.skip("the template is only a slot; it is placed by its explicit patterns")
    slots = {name: SLOTS[name] for name in row["slots"]}
    text = TemplateConversationInterface().render(ConversationMessage(
        act=act, template_id=row["template"], slots=slots))
    placed = G.place(text, RULES)
    assert placed is not None and placed["act"] == act, (act, text, placed)


@pytest.mark.parametrize("text, act", [
    ("the weather is clear.", "smalltalk"),        # the simple village's own inform wording
    ("farmer work is underway.", "share"),         # the simple village's share wording (role + work)
    ("how was your day?", "question"),              # the simple village's question wording
    ("Hello, Cask Thistlewood.", "greeting"),      # a two-word name
    ("Could you give me the bread?", "request"),
    ("Yes, I accept bread.", "accept"),
    ("No, I cannot accept bread.", "decline"),
])
def test_wordings_the_village_actually_sends_are_placed(text, act):
    placed = G.place(text, RULES)
    assert placed is not None and placed["act"] == act, (text, placed)


def test_a_slot_only_template_is_not_a_pattern():
    assert G.template_pattern("{answer}") is None
    assert G.template_pattern("Could you {request}?") == "Could you {request}"


def test_generic_pattern_is_refused():
    with pytest.raises(ValueError):
        G.compile_pattern("x", "{text}", {"text": "text"})
    with pytest.raises(ValueError):
        G.compile_pattern("x", "{q}", {"q": "unknown-kind"})


# ---------------------------------------------------------------- what the listener makes of an utterance

def test_a_well_formed_raw_payload_is_placed_as_raw():
    placed = speech_in.understand(_record("something else entirely", raw={"act": "greeting", "target": "ada"}))
    assert placed["act"] == "greeting" and placed["source"] == "raw"
    assert placed["slots"] == {"target": "ada"}


def test_a_malformed_raw_payload_falls_back_to_the_grammar():
    placed = speech_in.understand(_record("Hello, Ada.", raw={"act": "nonsense"}))
    assert placed["act"] == "greeting" and placed["source"] == "grammar"


def test_raw_with_an_unknown_slot_is_not_well_formed():
    placed = speech_in.understand(_record("Thank you.", raw={"act": "thanks", "slots": {"zz": "x"}}))
    assert placed["source"] == "grammar"


def test_unplaced_text_gives_none():
    assert speech_in.understand(_record("xyzzy plugh frobnicate")) is None


def test_a_stranger_gets_a_lower_confidence():
    record = _record("Hello, Ada.")
    tied = speech_in.understand(record, {"stranger": False})
    stranger = speech_in.understand(record, {"stranger": True})
    assert stranger["confidence"] < tied["confidence"]
    assert stranger["act"] == tied["act"]


def test_a_human_say_of_a_plain_sentence_is_placed_by_the_grammar():
    from bigville.api import create_game
    game = create_game(scenario="town100", seed=305000, default_backend="simple", autonomous=True,
                       ticks_per_period="world")
    speaker, listener = sorted(game.backends)[:2]
    game.world.utter(speaker, "Could you give me the bread?", target=None, loudness=100.0)
    heard = [r for r in game.world.heard_utterances(listener) if r["text"] == "Could you give me the bread?"]
    assert heard, "the listener should hear a broadcast at full loudness"
    assert heard[0]["raw_data"] is None
    placed = speech_in.understand(heard[0], {})
    assert placed["act"] == "request" and placed["source"] == "grammar"
    assert placed["slots"]["request"] == "give me the bread"


# ---------------------------------------------------------------- the effects, switch on

def _backend(name="ada", role="baker"):
    return DeterministicBackend(_character(name, role))


def test_a_tied_neighbours_request_becomes_a_give_goal_and_is_met():
    backend = _backend()
    transfer = {"action": "transfer", "kind": "bread", "recipient": "bram", "target": "bram", "score": 0.0}
    with speech_in.switched(True):
        context = _context(backend.character, nearby=[_near("bram", tie=0.6)], inventory={"bread": 2.0},
                           heard=[_record("Could you give me the bread?")], affordances=[transfer])
        response = backend.decide(context)
    assert speech_in.stats(backend)["effect_request_goal"] == 1
    assert backend.last_choice.get("action") == "transfer"
    assert backend.last_choice.get("recipient") == "bram" and backend.last_choice.get("kind") == "bread"
    assert response.major_action.action == "transfer"


def test_a_stranger_request_is_declined_in_words_and_not_met():
    backend = _backend()
    transfer = {"action": "transfer", "kind": "bread", "recipient": "bram", "target": "bram", "score": 0.0}
    with speech_in.switched(True):
        context = _context(backend.character, nearby=[_near("bram", tie=0.0)], inventory={"bread": 2.0},
                           heard=[_record("Could you give me the bread?")], affordances=[transfer])
        response = backend.decide(context)
    stats = speech_in.stats(backend)
    assert stats.get("effect_request_goal", 0) == 0
    assert stats["effect_request_declined_stranger"] == 1
    assert backend.last_choice.get("action") != "transfer"
    answer = next(u for u in response.utterances if u["act"] == "answer")
    assert answer["slots"]["answer"] == speech_in._settings()["words"]["stranger"]


def test_a_tied_neighbour_without_the_item_is_declined_in_words():
    backend = _backend()
    with speech_in.switched(True):
        context = _context(backend.character, nearby=[_near("bram", tie=0.6)], inventory={},
                           heard=[_record("Could you give me the bread?")])
        response = backend.decide(context)
    assert speech_in.stats(backend)["effect_request_declined_cannot"] == 1
    assert any(u["act"] == "answer" for u in response.utterances)


def test_a_greeting_is_answered_once_within_the_gap():
    backend = _backend()
    with speech_in.switched(True):
        first = backend.decide(_context(backend.character, turn=100, nearby=[_near("bram")],
                                        heard=[_record("Hello, Ada.", turn=99.0)]))
        again = backend.decide(_context(backend.character, turn=105, nearby=[_near("bram")],
                                        heard=[_record("Hello, Ada.", turn=104.0)]))
    greeting = [u for u in first.utterances if u["act"] == "greeting"]
    assert greeting and greeting[0]["target"] == "bram"
    assert not [u for u in again.utterances if u["act"] == "greeting"]


def test_a_question_is_answered_with_the_managing_words():
    backend = _backend()
    with speech_in.switched(True):
        response = backend.decide(_context(backend.character, nearby=[_near("bram")],
                                           heard=[_record("How was your day?")]))
    answer = [u for u in response.utterances if u["act"] == "answer"]
    assert answer and answer[0]["slots"]["answer"] == speech_in._settings()["words"]["managing"]


def test_an_offer_of_food_is_accepted_when_hungry_and_declined_when_not():
    hungry, fed = _backend("ada"), _backend("eve")
    with speech_in.switched(True):
        a = hungry.decide(_context(hungry.character, nearby=[_near("bram")], hunger=0.5,
                                   heard=[_record("I can offer bread to ada.")]))
        b = fed.decide(_context(fed.character, nearby=[_near("bram")], hunger=0.0,
                                heard=[_record("I can offer bread to eve.")]))
    assert [u["act"] for u in a.utterances if u["act"] in {"accept", "decline"}] == ["accept"]
    assert [u["act"] for u in b.utterances if u["act"] in {"accept", "decline"}] == ["decline"]


def test_a_warning_raises_caution_and_stops_travel_for_a_while():
    backend = _backend()
    with speech_in.switched(True):
        backend.decide(_context(backend.character, turn=100, nearby=[_near("bram")],
                                heard=[_record("Be careful, ada.", turn=99.0)]))
        assert speech_in.stats(backend)["effect_caution"] == 1
        assert backend.current_goal is None or backend.current_goal.kind != "travel"
        backend._update_goals(_context(backend.character, turn=101))
        assert "travel" not in [backend.current_goal.kind] + [g.kind for g in backend.goals]


def test_a_warning_from_a_stranger_at_grammar_confidence_raises_no_caution():
    backend = _backend()
    with speech_in.switched(True):
        backend.decide(_context(backend.character, turn=100, nearby=[_near("bram", tie=0.0)],
                                heard=[_record("Be careful, ada.", turn=99.0)]))
    assert speech_in.stats(backend).get("effect_caution", 0) == 0


def test_news_is_kept_as_a_place_belief_and_a_place_it_names_is_raised_by_the_fog():
    backend = _backend()
    with speech_in.switched(True):
        backend.decide(_context(backend.character, turn=100, nearby=[_near("bram")],
                                heard=[_record("I heard that the market is busy.", turn=99.0),
                                       _record("I heard that bram was hurt.", turn=99.5)]))
    beliefs = [m for m in backend.character.memories if m.kind == "place_belief"]
    assert [m.content["text"] for m in beliefs] == ["I heard that the market is busy.",
                                                    "I heard that bram was hurt."]
    assert all(m.content["speaker"] == "bram" for m in beliefs)
    stats = speech_in.stats(backend)
    assert stats["effect_news_stored_place"] == 1 and stats["effect_news_stored_person"] == 1


def test_the_fog_reader_raises_the_place_a_heard_news_names():
    from bigville.api import create_game
    from domains import map_memory
    game = create_game(scenario="town100", seed=305000, default_backend="simple", autonomous=True,
                       ticks_per_period="world")
    actor = sorted(game.backends)[0]
    game.characters[actor].memories.append(MemoryRecord(
        memory_id="speech:test:1", content={"text": "I heard that the market is busy.", "speaker": "x", "turn": 1},
        kind="place_belief", source="x", confidence=0.8, salience=0.5, turn=1, private=True))
    content = {"type": "map", "cells": {}, "places": {}, "routes": [], "told": [], "founded": 0}
    map_memory._tell(game, actor, content)
    assert content["places"]["market"]["level"] == 1
    assert content["told"] == ["speech:test:1"]


def test_the_same_record_is_read_once_over_several_turns():
    backend = _backend()
    record = _record("Hello, Ada.", turn=99.0)
    with speech_in.switched(True):
        for turn in (100, 101, 102):
            backend.decide(_context(backend.character, turn=turn, nearby=[_near("bram")], heard=[record]))
    assert speech_in.stats(backend)["heard"] == 1


# ---------------------------------------------------------------- the switch off

def test_with_the_switch_off_the_listener_never_touches_its_state(monkeypatch):
    """The hooks return before reading the resident's state, so an off switch leaves the resident as it was."""
    def boom(*args, **kwargs):
        raise AssertionError("speech_in state read with the switch off")
    monkeypatch.setattr(speech_in, "_state", boom)
    backend = _backend()
    transfer = {"action": "transfer", "kind": "bread", "recipient": "bram", "target": "bram", "score": 0.0}
    with speech_in.switched(False):
        backend.decide(_context(backend.character, nearby=[_near("bram")], inventory={"bread": 2.0},
                                heard=[_record("Could you give me the bread?"), _record("Hello, Ada.")],
                                affordances=[transfer]))
    assert not hasattr(backend, "_speech_in")


def test_the_pack_switch_is_what_turns_it_on():
    with speech_in.switched(False):
        assert speech_in.enabled() is False
    assert speech_in.enabled() is False


def test_a_short_village_run_with_the_switch_on_places_and_counts_what_it_hears():
    from bigville.api import create_game
    with speech_in.switched(True):
        game = create_game(scenario="town100", seed=305000, default_backend="simple", autonomous=True,
                           ticks_per_period="world")
        for _ in range(12):
            game.step()
        totals = {}
        for backend in game.backends.values():
            for key, value in speech_in.stats(backend).items():
                totals[key] = totals.get(key, 0) + value
    assert totals.get("heard", 0) > 0
    assert totals.get("placed_grammar", 0) > 0
    assert totals.get("placed_raw", 0) == 0    # the simple village's speech carries no raw payload
