"""Phase 061: the speech parser. A small model places what the grammar cannot, behind a cache and a budget.

Each test names one acceptance item of the brief. No test reaches the network: the fake provider is in process,
and the provider class is run against the loopback stub (tests/llm_stub.py on 127.0.0.1). The labelled set is
tests/fixtures/speech_labelled.json (200 utterances). Its scores are pinned here, and the report gives the same
numbers. Run `python3 tests/test_phase061_speech_parser.py` to print the table.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from bigville.backends import ActorContext, DeterministicBackend, speech_in
from bigville.backends.speech_parser import (CAUSES, SpeechParser, check_reply, fixed_prefix, frame,
                                              reference_hash, vocabulary)
from bigville.character import CharacterDefinition
from bigville.llm_transcript import RecordingProvider, ReplayProvider, Transcript
from bigville.providers import OpenAICompatibleProvider, ProviderError
from domains.speech_parser_check import check_speech_parser
from llm_stub import FakeProvider, StubServer, completion

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "speech_labelled.json"
ITEMS = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]
KEY = "sk-test-0123456789abcdefghijklmnopqrstuvwxyz"   # a fake key; the loopback stub checks nothing


@pytest.fixture(autouse=True)
def _switch_off_by_default():
    with speech_in.switched(False):
        with speech_in.using_parser(None):
            yield


def _listener(name="ada", kind_role="villager"):
    return DeterministicBackend(CharacterDefinition(character_id=name, name=name, identity={"role": kind_role}))


def _scripted(reply_for):
    """A FakeProvider whose reply is `reply_for(utterance)` (an object or a string). A dict or a string is a
    constant reply."""
    def reply(payload):
        value = reply_for(payload["utterance"]) if callable(reply_for) else reply_for
        return value if isinstance(value, str) else json.dumps(value)
    return FakeProvider(reply=reply)


def _item_reply(item, errors):
    if errors and "error" in item:
        return item["error"]
    return {"act": item["label"], "slots": {}}


def _context(**extra):
    return dict({"names": [], "listener_name": "ada", "turn": 1}, **extra)


# ---------------------------------------------------------------- the frame and the normalised key

def test_a_normalised_frame_joins_names_and_counts():
    vocab = vocabulary("bigville")
    one, _ = frame("Bram, bring me two loaves", ["bram", "ada"], vocab)
    other, values = frame("Ada, bring me three loaves", ["bram", "ada"], vocab)
    assert one == other == "{name1} bring me {n1} loaves"
    assert values == {"name1": "ada", "n1": "three"}


def test_a_greeting_word_is_not_a_name():
    vocab = vocabulary("bigville")
    assert frame("Hello, Ada", [], vocab)[0] != frame("Thanks, Ivo", [], vocab)[0]
    assert frame("Thanks, Ivo.", [], vocab)[0] == "thanks {name1}"


# ---------------------------------------------------------------- the cache

def test_a_normalised_duplicate_hits_the_cache_and_makes_no_call(tmp_path):
    fake = _scripted(lambda text: {"act": "request", "slots": {"request": "bring me two loaves"}})
    parser = SpeechParser(fake, cache_path=tmp_path / "cache.jsonl")
    first = parser.parse("Bram, bring me two loaves", "ada", _listener("bram"),
                         _context(names=["bram", "ada"], listener_name="bram"))
    second = parser.parse("Ada, bring me three loaves", "tam", _listener("ada"),
                          _context(names=["ada", "tam"], listener_name="ada"))
    assert first["source"] == "model" and second["source"] == "cache"
    assert second["slots"] == {"request": "bring me three loaves"}
    assert len(fake.calls) == 1
    assert parser.summary()["cache_hits"] == 1


def test_the_cache_is_loaded_at_start_and_a_stale_line_is_skipped(tmp_path):
    path = tmp_path / "cache.jsonl"
    fake = _scripted({"act": "share", "slots": {"news": "smoke is up from the forge"}})
    SpeechParser(fake, cache_path=path).parse("Smoke is up from the forge, I hear", "nell", _listener(),
                                             _context())
    fresh = SpeechParser(_scripted({"act": None, "slots": {}}), cache_path=path)
    assert fresh.parse("Smoke is up from the forge, I hear", "nell", _listener(), _context())["source"] == "cache"
    assert fresh.calls == 0
    lines = path.read_text(encoding="utf-8").splitlines()
    stale = json.loads(lines[0])
    stale["schema"] = 0
    path.write_text(json.dumps(stale) + "\n", encoding="utf-8")
    reloaded = SpeechParser(_scripted({"act": None, "slots": {}}), cache_path=path)
    assert reloaded.stats["cache_stale"] == 1 and reloaded.cache_size == 0


def test_a_null_answer_is_cached_so_a_repeat_costs_nothing():
    fake = _scripted({"act": None, "slots": {}})
    parser = SpeechParser(fake)
    assert parser.parse("Two carts went past the church.", "hester", _listener(), _context()) is None
    assert parser.parse("Two carts went past the church.", "hester", _listener(), _context()) is None
    assert len(fake.calls) == 1
    assert parser.summary()["causes"]["cache_declined"] == 1


# ---------------------------------------------------------------- the fixed prefix

def test_the_fixed_prefix_is_byte_identical_across_calls():
    fake = _scripted(lambda text: {"act": None, "slots": {}})
    parser = SpeechParser(fake)
    for turn, text in enumerate(["Two carts went past the church.", "Bell rang at noon.", "Eight geese on the green."]):
        parser.parse(text, "nell", _listener(), _context(turn=turn))
    systems = [call["payload"]["system"] for call in fake.calls]
    assert len(systems) == 3
    assert all(system == systems[0] for system in systems)
    assert systems[0].encode("utf-8") == fixed_prefix("bigville").encode("utf-8")
    assert parser.reference_hash == reference_hash(fixed_prefix("bigville"))
    assert "Bell rang" not in systems[0] and "Eight geese" not in systems[0]


def test_the_prefix_names_every_understood_act_and_the_variable_part_is_the_line_only():
    prefix = fixed_prefix("bigville")
    for act in ("greeting", "request", "question", "share", "accept", "decline"):
        assert f"- {act}:" in prefix
    assert "- inform:" not in prefix          # understood_by none
    fake = _scripted({"act": None, "slots": {}})
    SpeechParser(fake).parse("Morning, Tam.", "nell", _listener(), _context())
    payload = fake.calls[0]["payload"]
    assert set(payload) == {"system", "utterance", "speaker", "listener_knows_speaker", "topic_words"}
    assert payload["utterance"] == "Morning, Tam."


# ---------------------------------------------------------------- validation

def test_an_invented_name_is_rejected_and_the_repair_is_counted_too():
    replies = iter([{"act": "greeting", "slots": {"target": "martha"}},
                    {"act": "greeting", "slots": {"target": "martha"}}])
    fake = FakeProvider(reply=lambda payload: json.dumps(next(replies)))
    parser = SpeechParser(fake)
    placed = parser.parse("Bright morning for it, Tam", "tam", _listener(), _context(names=["bram"]))
    assert placed is None
    summary = parser.summary()
    assert summary["rejections"] == {"invented_name": 2}
    assert summary["causes"]["invalid_output"] == 1 and summary["repairs"] == 1
    assert len(fake.calls) == 2 and "repair" in fake.calls[1]["payload"]


def test_an_unknown_act_is_rejected():
    parser = SpeechParser(FakeProvider(reply=json.dumps({"act": "salutation", "slots": {}}), ))
    assert parser.parse("Hullo", "ada", _listener(), _context()) is None
    assert parser.summary()["rejections"]["unknown_act"] == 2


def test_a_name_the_listener_could_know_is_accepted():
    answer, reason = check_reply({"act": "greeting", "slots": {"target": "ada"}}, text="Hallo, Ada",
                                 allowed_names=["bram", "ada"])
    assert reason is None and answer == {"act": "greeting", "slots": {"target": "ada"}}


def test_a_slot_must_come_from_the_line():
    answer, reason = check_reply({"act": "share", "slots": {"news": "the bridge fell"}},
                                 text="I heard the mill burned", allowed_names=[])
    assert answer is None and reason == "slot_not_in_line"


# ---------------------------------------------------------------- provider errors, caps, timeouts

def test_a_provider_error_leaves_the_utterance_unplaced_and_counted():
    fake = FakeProvider(error=ProviderError("HTTP 500 from the provider"))
    parser = SpeechParser(fake)
    assert parser.parse("Two carts went past the church.", "hester", _listener(), _context()) is None
    summary = parser.summary()
    assert summary["causes"]["provider_error"] == 1 and summary["unplaced"] == 1
    assert parser.cache_size == 0           # a failure is not stored


def test_a_slow_call_times_out_and_is_counted():
    fake = FakeProvider(reply=json.dumps({"act": None, "slots": {}}), delay=0.5)
    parser = SpeechParser(fake, timeout_s=0.05)
    assert parser.parse("Bell rang at noon.", "oswin", _listener(), _context()) is None
    assert parser.summary()["causes"]["timeout"] == 1


def test_the_call_cap_stops_calls_and_is_counted():
    fake = FakeProvider(reply=json.dumps({"act": None, "slots": {}}))
    parser = SpeechParser(fake, max_calls=1)
    parser.parse("Bell rang at noon.", "oswin", _listener(), _context())
    assert parser.parse("Eight geese on the green.", "oswin", _listener(), _context()) is None
    assert len(fake.calls) == 1 and parser.summary()["causes"]["call_cap"] == 1


def test_the_spend_cap_stops_calls_once_the_reported_cost_reaches_it():
    fake = FakeProvider(reply=json.dumps({"act": None, "slots": {}}), cost=0.5)
    parser = SpeechParser(fake, max_spend=0.5)
    parser.parse("Bell rang at noon.", "oswin", _listener(), _context())
    assert parser.parse("Eight geese on the green.", "oswin", _listener(), _context()) is None
    assert len(fake.calls) == 1 and parser.summary()["causes"]["spend_cap"] == 1


def test_only_a_simple_listener_with_no_structure_is_asked():
    fake = FakeProvider(reply=json.dumps({"act": "thanks", "slots": {}}))
    parser = SpeechParser(fake)

    class _Human:
        kind = "human"
        understands_raw_speech = True

    assert parser.parse("Cheers for everything", "ada", _Human(), _context()) is None
    assert parser.parse("Cheers for everything", "ada", _listener(), _context(raw_data={"act": "x"})) is None
    assert parser.parse("Cheers for everything " * 20, "ada", _listener(), _context()) is None
    summary = parser.summary()
    assert summary["causes"]["not_eligible"] == 2 and summary["causes"]["too_long"] == 1
    assert fake.calls == []


def test_a_grammar_placement_is_kept_and_no_call_is_made():
    fake = FakeProvider(reply=json.dumps({"act": "share", "slots": {}}))
    parser = SpeechParser(fake)
    placed = parser.parse("Thank you.", "ivo", _listener(), _context())
    assert placed["source"] == "grammar" and fake.calls == []


# ---------------------------------------------------------------- the loopback provider

def test_the_parser_runs_on_the_provider_class_against_the_loopback_stub():
    seen = []

    def script(index, body, headers):
        seen.append(body)
        return 200, {}, completion(json.dumps({"act": "share",
                                               "slots": {"news": "the forge fire is lit this morning"}}))

    with StubServer(script) as stub:
        provider = OpenAICompatibleProvider(base_url=stub.base_url, api_key=KEY, model="glm-5.3-flash",
                                            run_id="run61", sleep=lambda s: None, max_retries=0)
        parser = SpeechParser(provider)
        placed = parser.parse("The forge fire is lit this morning, I hear", "nell", _listener(), _context())
    assert placed == {"act": "share", "slots": {"news": "the forge fire is lit this morning"},
                      "confidence": 0.6, "source": "model"}
    system = seen[0]["messages"][0]
    assert system["role"] == "system" and system["content"] == fixed_prefix("bigville")
    assert KEY not in json.dumps(parser.summary())


def test_a_loopback_error_is_a_provider_error_and_a_bad_reply_is_repaired_once():
    def server_error(index, body, headers):
        return 500, {}, {"error": "down"}

    with StubServer(server_error) as stub:
        provider = OpenAICompatibleProvider(base_url=stub.base_url, api_key=KEY, model="glm-5.3-flash",
                                            run_id="run61", sleep=lambda s: None, max_retries=0)
        parser = SpeechParser(provider)
        assert parser.parse("Bell rang at noon.", "oswin", _listener(), _context()) is None
    assert parser.summary()["causes"]["provider_error"] == 1

    replies = ["Sure, that is a sound thing.", json.dumps({"act": None, "slots": {}})]

    def bad_then_good(index, body, headers):
        return 200, {}, completion(replies[min(index, 1)])

    with StubServer(bad_then_good) as stub:
        provider = OpenAICompatibleProvider(base_url=stub.base_url, api_key=KEY, model="glm-5.3-flash",
                                            run_id="run61", sleep=lambda s: None, max_retries=0)
        parser = SpeechParser(provider)
        assert parser.parse("Bell rang at noon.", "oswin", _listener(), _context()) is None
    summary = parser.summary()
    assert summary["repairs"] == 1 and summary["rejections"] == {"bad_json": 1}
    assert summary["causes"]["model_none"] == 1


# ---------------------------------------------------------------- the record and the replay

def test_a_recorded_run_replays_with_the_same_placements(tmp_path):
    scripted = {item["text"]: _item_reply(item, errors=True) for item in ITEMS}
    transcript = Transcript(tmp_path / "transcript.jsonl", run_id="rec61")
    recording = RecordingProvider(_scripted(lambda text: scripted[text]), transcript)
    recorded = SpeechParser(recording, cache_path=tmp_path / "cache.jsonl")
    first = _place_all(recorded, ITEMS)

    replayed = SpeechParser(ReplayProvider(tmp_path / "transcript.jsonl"))
    second = _place_all(replayed, ITEMS)
    assert _acts(second) == _acts(first)
    assert replayed.summary()["calls"] > 0

    # The recorded cache is part of the record. With it, a cached answer needs no provider reply: only the answers
    # that were never stored (the invalid replies) are asked again.
    cached = SpeechParser(ReplayProvider(tmp_path / "transcript.jsonl"), cache_path=tmp_path / "cache.jsonl")
    assert _acts(_place_all(cached, ITEMS)) == _acts(first)
    assert cached.summary()["calls"] < replayed.summary()["calls"]


def _acts(placed):
    """The placement of each utterance as (act, slots); the source is left out, since a cache hit has its own."""
    return [None if p is None else (p["act"], p["slots"]) for p in placed]

def _place_all(parser, items):
    placed = []
    for turn, item in enumerate(items):
        placed.append(parser.parse(item["text"], item["speaker"], _listener(item["listener"]),
                                   _context(names=item["names"], listener_name=item["listener"], turn=turn)))
    return placed


# ---------------------------------------------------------------- the hook in the listener

def test_the_listener_places_an_utterance_only_when_a_parser_is_given():
    backend = _listener("ada", "baker")
    heard = [{"speaker": "bram", "target": "ada", "text": "Hallo, Ada", "raw_data": None, "turn": 99.0,
              "loudness": 1.0}]
    nearby = [{"id": "bram", "name": "bram", "distance": 2, "tie_strength": 0.6, "band_code": 1.0}]

    def context():
        return ActorContext(character=backend.character, turn=100,
                            observations={"calendar": {"hour": 10.0}, "hunger": 0.0, "energy": 100.0,
                                          "nearby_residents": nearby, "heard_utterances": heard, "inventory": {}},
                            affordances=[])

    with speech_in.switched(True):
        speech_in.hear(backend, context())
        assert speech_in.next_reply(backend, context()) is None
        parser = SpeechParser(FakeProvider(reply=json.dumps({"act": "greeting", "slots": {"target": "ada"}})))
        backend = _listener("ada", "baker")
        with speech_in.using_parser(parser):
            speech_in.hear(backend, context())
            reply = speech_in.next_reply(backend, context())
    assert reply is not None and reply["act"] == "greeting"
    assert parser.summary()["placed"]["model"] == 1


def test_the_self_test_is_clean_for_both_packs():
    for pack in ("packs/bigville", "packs/test_hamlet"):
        errors, warnings, info = [], [], []
        check_speech_parser(pack, errors, warnings, info)
        assert errors == [] and warnings == [], (pack, errors, warnings)


# ---------------------------------------------------------------- the labelled set

def _grade(items, placed):
    rows = []
    for item, got in zip(items, placed):
        act = got["act"] if got else None
        rows.append((act, item["label"], got["source"] if got else None))
    n = len(items)
    placed_n = sum(1 for act, _, _ in rows if act is not None)
    correct = sum(1 for act, label, _ in rows if act == label)
    placed_correct = sum(1 for act, label, _ in rows if act is not None and act == label)
    misplaced = sum(1 for act, label, _ in rows if act is not None and act != label)
    labelled = sum(1 for _, label, _ in rows if label is not None)
    return {"placed": placed_n, "correct": correct, "misplaced": misplaced,
            "placed_share": round(placed_n / n, 3), "correct_share": round(correct / n, 3),
            "misplaced_share": round(misplaced / n, 3), "precision": round(placed_correct / max(1, placed_n), 3),
            "recall": round(sum(1 for act, label, _ in rows if label and act == label) / labelled, 3),
            "by_source": {s: sum(1 for _, _, src in rows if src == s) for s in ("raw", "grammar", "cache", "model")}}


def grammar_arm(items):
    placed = []
    for item in items:
        found = speech_in.understand({"text": item["text"], "speaker": item["speaker"], "raw_data": None},
                                     {"stranger": False})
        placed.append(found)
    return placed


def model_arm(items, *, errors, passes=1):
    """(parser, placements of the last pass). Each pass runs the whole set through one parser, so a second pass
    shows what the cache does."""
    scripted = {item["text"]: _item_reply(item, errors) for item in items}
    parser = SpeechParser(_scripted(lambda text: scripted[text]))
    placed = []
    for _ in range(passes):
        placed = _place_all(parser, items)
    return parser, placed


def measure():
    """The score table: grammar only, and grammar plus the model in two scripted arms (see the report)."""
    grammar = _grade(ITEMS, grammar_arm(ITEMS))
    perfect_parser, perfect_placed = model_arm(ITEMS, errors=False)
    errors_parser, errors_placed = model_arm(ITEMS, errors=True)
    repeat_parser, _ = model_arm(ITEMS, errors=False, passes=2)
    return {
        "grammar": dict(grammar, calls=0, summary=None),
        "perfect": dict(_grade(ITEMS, perfect_placed), calls=perfect_parser.calls,
                        summary=perfect_parser.summary()),
        "errors": dict(_grade(ITEMS, errors_placed), calls=errors_parser.calls, summary=errors_parser.summary()),
        "second_pass_calls": repeat_parser.calls - perfect_parser.calls,
        "second_pass_cache_hits": repeat_parser.summary()["cache_hits"] - perfect_parser.summary()["cache_hits"],
    }


def test_the_labelled_set_has_200_utterances_and_some_that_nothing_should_place():
    assert len(ITEMS) == 200
    assert len({item["text"] for item in ITEMS}) == 200
    assert sum(1 for item in ITEMS if item["label"] is None) == 45


def test_the_scores_on_the_labelled_set_with_and_without_the_model():
    scores = measure()
    grammar, perfect, errors = scores["grammar"], scores["perfect"], scores["errors"]
    # Grammar only (no call): these are the numbers the report gives.
    assert (grammar["placed"], grammar["correct"], grammar["misplaced"]) == (47, 85, 7)
    # Grammar plus a model that gives each line's label (the ceiling for this prompt).
    assert (perfect["placed"], perfect["correct"], perfect["misplaced"]) == (155, 193, 7)
    assert perfect["calls"] == 153
    # Grammar plus the scripted model with its 14 hand-picked mistakes.
    assert (errors["placed"], errors["correct"], errors["misplaced"]) == (151, 179, 14)
    assert errors["calls"] == 160
    # The model adds placements; it does not change what the grammar placed.
    assert perfect["correct"] > grammar["correct"] and errors["correct"] > grammar["correct"]
    # A second pass over the same set makes no new call for an answer already cached (valid or null).
    assert scores["second_pass_calls"] == 0 and scores["second_pass_cache_hits"] > 0


def test_the_cause_names_are_the_ones_the_report_lists():
    assert set(CAUSES) >= {"provider_error", "timeout", "invalid_output", "call_cap", "spend_cap"}


if __name__ == "__main__":
    out = measure()
    target = ROOT / "docs" / "phases" / "phase061" / "scores.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for name in ("grammar", "perfect", "errors"):
        row = out[name]
        print(f"{name:8s} placed {row['placed']:3d}  correct {row['correct']:3d}  misplaced {row['misplaced']:3d}  "
              f"precision {row['precision']:.3f}  recall {row['recall']:.3f}  calls {row['calls']}")
    print(f"second pass over the set (perfect arm): calls {out['second_pass_calls']}, "
          f"cache hits {out['second_pass_cache_hits']}")
    sys.exit(0)
