"""Phase 054b: the handles an LLM resident sees are the harness's own tokens.

A token is ``hx`` plus letters, assigned per resident in order of first appearance and kept for the run. The model's
reply is read back to the world's handle the view showed before the game sees it. These tests hold:

* the prompt the provider receives has no world handle, no ``cell:``, no ``target:``, no coordinate and no digit in a
  handle, in the lazy view and in the menu view, with perception on and off;
* a wrong percept of an object whose id is its kind word shows neither the id nor the true kind;
* a token keeps its number across turns, and a menu row keeps its token when its ``target:N`` index changes;
* a reply's token is read back to the handle the view showed, and a token or a world handle the view did not show is an
  error (the repair path), whose text names no id;
* the checkpoint round trip keeps the tokens; the LLM log keeps token -> world handle beside each call; a recorded run
  replays with the same prompts and replies.

The provider is the in-process FakeProvider (tests/llm_stub.py). No network is used.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest.mock as mock

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                                  # noqa: E402
from bigville.backends import LLMBackend                              # noqa: E402
from bigville.backends.handle_map import HandleMap, UNKNOWN_HANDLE, TOKEN, letters  # noqa: E402
from bigville.backends.prompt_packet import PACKET_SCHEMA, packet_system  # noqa: E402
from bigville.backends.protocol import ActorContext                  # noqa: E402
from bigville.backends.reply_schema import to_wire                   # noqa: E402
from bigville.llm_checkpoint import checkpoint_llm_backend, restore_llm_backend  # noqa: E402
from bigville.llm_log import LLMLog, read_log                         # noqa: E402
from bigville.llm_transcript import RecordingProvider, ReplayProvider, Transcript  # noqa: E402
from domains import agent_view, reading                              # noqa: E402
from domains.affordance_handles import handle_pairs                  # noqa: E402
from domains.agent_view import build_lazy_agent_view                 # noqa: E402
from domains.pack import load_pack                                   # noqa: E402
from tests.llm_stub import FakeProvider                              # noqa: E402
from worlds import daynight as dn                                    # noqa: E402

PACK = load_pack("bigville")

# Ada is the LLM resident under test; Ben is the simple resident in the same room. The knife's id is its kind word, the
# case the 065c leak used (a wrong percept of it is the test below).
SCENARIO = {
    "id": "p054b_handles",
    "name": "Phase 054b handle room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "llm", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [], "laws": [], "policies": [], "charters": [],
    "physical_objects": [
        {"id": "knife", "name": "knife", "kind": "knife", "location": "table"},
        {"id": "spade_1", "name": "spade", "kind": "spade", "location": "table"},
        {"id": "box", "name": "box", "kind": "box", "location": "table", "open": True},
    ],
}
WORLD_IDS = ("knife", "spade_1", "box")
KNIFE_SPADE = [{"id": "knife", "kind": "knife", "location": "world"},
               {"id": "spade_1", "kind": "spade", "location": "world"}]
RE_COORDINATE = re.compile(r"\d+\s*,\s*\d+")


def _reply(action=None, **params):
    major = None if action is None else {"action": action, "params": params}
    return json.dumps({"major_action": major, "utterances": [], "memory_updates": [], "continuation": None})


def _game(provider=None, *, affordance_mode="lazy"):
    """The small room with Ada on the LLM backend (autopilot off: she is consulted every turn)."""
    provider = provider if provider is not None else FakeProvider(_reply("rest"))
    factory = lambda world, character: LLMBackend(character, provider, autopilot=False)
    game = create_game(scenario=SCENARIO, seed=305165, player=None, default_backend="simple",
                       backend_factories={"llm": factory}, autonomous=True, llm_log=False,
                       affordance_mode=affordance_mode)
    game._test_provider = provider
    return game


@pytest.fixture
def perception_on():
    saved = {name: dict(PACK[name]) for name in ("PERCEPTION", "IMPAIRMENT")}
    PACK["PERCEPTION"]["enabled"] = True
    PACK["IMPAIRMENT"]["enabled"] = True
    try:
        yield
    finally:
        for name, values in saved.items():
            PACK[name].clear()
            PACK[name].update(values)


@pytest.fixture
def perception_off():
    saved = dict(PACK["PERCEPTION"])
    PACK["PERCEPTION"]["enabled"] = False
    try:
        yield
    finally:
        PACK["PERCEPTION"].clear()
        PACK["PERCEPTION"].update(saved)


def _sent(game) -> dict:
    return game._test_provider.calls[-1]["payload"]


def _bodies(messages: list[dict]) -> list[dict]:
    """The JSON bodies of the user messages (each is the pack's text, a newline, then the JSON)."""
    out = []
    for message in messages:
        if message["role"] == "user" and "\n" in message["content"]:
            out.append(json.loads(message["content"].split("\n", 1)[1]))
    return out


def _walk(value, found: list[tuple[str, object]]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("handle", "choices") or key == "choice":
                found.append((key, item))
            _walk(item, found)
    elif isinstance(value, list):
        for item in value:
            _walk(item, found)


def _handles_sent(sent: dict) -> list[str]:
    """Every value the model reads as a handle in what was sent: a row handle, a reaction choice or a consult choice."""
    found: list[tuple[str, object]] = []
    for body in _bodies(sent["messages"]):
        _walk(body, found)
    values: list[str] = []
    for key, item in found:
        if isinstance(item, list):
            values += [str(one) for one in item]
        elif item is not None and item != "":
            values.append(str(item))
    return values


def _assert_opaque(sent: dict) -> None:
    text = json.dumps(sent["messages"], ensure_ascii=False)
    assert "cell:" not in text, "a place's cell handle reached the prompt"
    assert "target:" not in text, "a legacy target key reached the prompt"
    assert not RE_COORDINATE.search(text), "a coordinate reached the prompt"
    # An id with a digit is never a kind word, so its text would show the id itself; the kind words stay in `what`.
    assert "spade_1" not in text
    for handle in _handles_sent(sent):
        assert TOKEN.match(handle), f"a handle is not a token: {handle!r}"
        assert not re.search(r"\d", handle)


# ------------------------------------------------------------------ the prompt carries tokens only
@pytest.mark.parametrize("affordance_mode", ["lazy", "menu"])
@pytest.mark.parametrize("perception", ["on", "off"])
def test_no_prompt_carries_a_world_handle_a_coordinate_or_a_target_key(affordance_mode, perception, request):
    if perception == "on":
        request.getfixturevalue("perception_on")
    else:
        request.getfixturevalue("perception_off")
    game = _game(affordance_mode=affordance_mode)
    for _ in range(4):
        game.step()
        _assert_opaque(_sent(game))
    assert _handles_sent(_sent(game)), "the prompt should list at least one handle"


def test_the_view_api_keeps_its_readable_handles_and_the_prompt_gets_tokens(perception_off):
    game = _game()
    view = build_lazy_agent_view(game, "Ada")
    assert any(thing.get("handle") == "knife" for thing in view["around"]["things"]), \
        "the view API keeps the world's handles (the TUI and the human path read them)"
    game.step()
    handles = _handles_sent(_sent(game))
    assert handles and "knife" not in handles and "spade_1" not in handles


def test_the_lazy_packet_text_names_no_cell_and_no_id(perception_off):
    text = packet_system("bigville", lazy=True)
    assert "cell number" not in text and "stable name or id" not in text
    assert "handle from public.around.things" in text


def test_the_packet_schema_is_prompt_7():
    # Phase 071d: the packet's private part lists giveable_notes and requests (054b asserted prompt/6).
    assert PACKET_SCHEMA == "bigville/prompt/7"


def test_letters_are_bijective_and_digit_free():
    assert [letters(n) for n in (1, 2, 26, 27, 28, 52, 53)] == ["a", "b", "z", "aa", "ab", "az", "ba"]
    assert all(TOKEN.match("hx" + letters(n)) and not re.search(r"\d", letters(n)) for n in range(1, 400))


# ------------------------------------------------------------------ the wrong percept (the 065c leak)
def _drunk(game, actor, level=0.5):
    world = game.world
    body = world._bodies[actor]
    old = world.eng.node(body)["attrs"].get("intoxication", 0.0)
    world.eng.set_attr(body, "intoxication", level)
    return old


def test_a_wrong_percept_of_an_object_whose_id_is_its_kind_word_shows_neither_the_id_nor_the_true_kind(
        perception_on, monkeypatch, tmp_path):
    game = _game()
    world = game.world
    monkeypatch.setattr(world, "physical_object_observations", lambda actor: KNIFE_SPADE)
    monkeypatch.setattr(world, "_physical_location_cell", lambda *a, **k: None)
    monkeypatch.setattr(dn, "view_light", lambda w, a: "day")
    old_level = _drunk(game, "Ada", 0.5)
    old_turn = world._turn
    backend = game.backends["Ada"]
    log = LLMLog(tmp_path / "llm.jsonl", run_id="p054b")
    backend.log = log
    try:
        wrong = None
        for turn in range(300):
            world._turn = turn
            rows = [row for row in build_lazy_agent_view(game, "Ada", mode="referee")["referee"]["perception"]["subjects"]
                    if row["kind"] == "thing" and row.get("distorted") and row["percept"] != row["truth"]
                    and row["tier"] >= 1]
            knife = [row for row in rows if row["subject"] == "knife"]
            # The percept of the knife must not be the kind of another thing in view, or the true kind would show again.
            if knife and not any(row["percept"] == knife[0]["truth"] for row in rows if row["subject"] != "knife"):
                wrong = knife[0]
                break
        assert wrong is not None, "a drunk resident should be shown a wrong knife in 300 turns"
        truth, percept = wrong["truth"], wrong["percept"]
        assert truth == "knife" and percept != "knife"

        context = game._context("Ada")
        assert backend.decide(context) is not None
        sent = _sent(game)
        text = json.dumps(sent["messages"], ensure_ascii=False)
        assert percept in text, "the wrong percept is what the resident sees"
        assert "knife" not in text, "neither the id nor the true kind reached the prompt"
        _assert_opaque(sent)

        # The LLM log holds the same prompt, and beside the call the token of the knife and the world handle it stands for.
        record = [r for r in read_log(tmp_path / "llm.jsonl") if r.get("kind") == "call"][-1]
        assert record["messages"] == sent["messages"]
        assert "knife" in record["referee"]["handles"].values()
        token = [t for t, label in record["referee"]["handles"].items() if label == "knife"][0]
        assert TOKEN.match(token) and token in _handles_sent(sent)
    finally:
        world._turn = old_turn
        world.eng.set_attr(world._bodies["Ada"], "intoxication", old_level)


# ------------------------------------------------------------------ stable tokens
def test_a_thing_keeps_its_token_across_turns_and_a_new_thing_takes_the_next_one(perception_off):
    game = _game()
    backend = game.backends["Ada"]
    game.step()
    first = dict(backend.handles.labels)
    for _ in range(3):
        game.step()
    later = backend.handles.labels
    assert all(later[token] == label for token, label in first.items()), "a token was reassigned"
    assert "knife" in first.values() and "spade_1" in first.values()
    # Masking the same things again mints nothing.
    backend.handles.mask_context(game._context("Ada"))
    assert backend.handles.count == len(first)


def test_a_menu_row_keeps_its_token_when_its_target_index_changes():
    """Two strike rows: Ben is target:0 on the first turn and target:1 on the second. The identity is the row's
    recipient, not the index, so Ben keeps the token and the reply's token still names Ben's row."""
    def row(recipient, index):
        return {"action": "strike", "target": f"target:{index}", "recipient": recipient, "with": "knife",
                "score": float(index)}

    def context(rows):
        view = {"can": [{"handle": handle, "action": "strike", "what": "someone here"}
                        for handle, _ in handle_pairs(rows)], "around": {"things": []}}
        return ActorContext(character=None, turn=1, observations={}, affordances=rows, agent_view=view)

    backend = HandleMap()
    first = [row("Ben", 0), row("Cy", 1)]
    second = [row("Cy", 0), row("Ben", 1)]
    masked_1 = backend.mask_context(context(first)).agent_view["can"]
    masked_2 = backend.mask_context(context(second)).agent_view["can"]
    ben_1 = masked_1[0]["handle"]
    ben_2 = masked_2[1]["handle"]
    assert ben_1 == ben_2, "Ben's row changed token when its index changed"
    assert masked_2[0]["handle"] != ben_2
    translated, errors = backend.translate({"major_action": {"action": "strike", "target": ben_2, "params": {}}})
    assert errors == [] and translated["major_action"]["target"] == "target:1"
    wire = to_wire(translated, "bigville", affordances=second)
    assert wire["major_action"]["params"]["recipient"] == "Ben"


# ------------------------------------------------------------------ reply translation
def test_a_lazy_place_token_reads_back_to_its_cell_for_a_move():
    game = _game()
    backend = game.backends["Ada"]
    game.step()
    place = [token for token, label in backend.handles.labels.items() if label.startswith("cell:")][0]
    label = backend.handles.labels[place]
    translated, errors = backend.handles.translate({"major_action": {"action": "move", "target": place, "params": {}}})
    assert errors == []
    assert translated["major_action"]["target"] == label
    wire = to_wire(translated, "bigville", affordances=[])
    x, y = (int(part) for part in label.split(":", 1)[1].split(","))
    assert wire["major_action"]["params"]["destination"] == (x, y)


def test_a_menu_token_reads_back_to_the_row_the_view_showed(perception_off):
    game = _game(affordance_mode="menu")
    backend = game.backends["Ada"]
    context = game._context("Ada")
    masked = backend.handles.mask_context(context)
    rows = masked.agent_view["can"]
    row = [r for r in rows if r["action"] == "move something"][0]
    translated, errors = backend.handles.translate({"major_action": {"action": "move something",
                                                                    "target": row["handle"], "params": {}}})
    assert errors == []
    wire = to_wire(translated, "bigville", affordances=context.affordances)
    assert wire["major_action"]["action"] == "move_object"
    assert wire["major_action"]["params"]["object_id"] in ("knife", "spade_1", "box")


def test_a_token_the_view_did_not_offer_is_an_error_and_a_world_handle_copied_from_a_view_is_too(perception_off):
    game = _game()
    backend = game.backends["Ada"]
    game.step()
    _, errors = backend.handles.translate({"major_action": {"action": "rest", "target": "hxzz", "params": {}}})
    assert errors == [UNKNOWN_HANDLE]
    shown = [label for label in backend.handles.labels.values()][0]
    _, errors = backend.handles.translate({"major_action": {"action": "strike", "target": shown, "params": {}}})
    assert errors == [UNKNOWN_HANDLE], "a world handle is not a valid reply once the model is shown its token"


def test_a_reply_with_a_token_the_view_did_not_offer_is_repaired_with_a_fixed_message(perception_off):
    calls = []

    def provider(payload, meta=None):
        calls.append(payload)
        if payload.get("repair") is None:
            return _reply("strike", target="hxzz")
        return _reply("rest")

    game = _game(FakeProvider(provider))
    backend = game.backends["Ada"]
    game.step()
    assert len(calls) == 2
    repair = calls[1]["repair"]["errors"]
    assert repair == [UNKNOWN_HANDLE]
    text = json.dumps(calls[1]["messages"], ensure_ascii=False)
    assert "hxzz" not in json.dumps(repair) and "knife" not in json.dumps(repair)
    assert backend.counts["repaired_successes"] == 1


def test_a_reply_that_keeps_naming_an_unknown_token_is_an_invalid_output(perception_off):
    game = _game(FakeProvider(_reply("strike", target="hxzz")))
    backend = game.backends["Ada"]
    game.step()
    assert backend.counts["invalid_outputs"] == 1
    assert backend.fallbacks["invalid_output"] == 1


def test_a_free_action_target_reads_back_to_the_handle_the_view_showed():
    """Phase 071c: a free action's target is read back like a major action's target (a glance names a signal's row)."""
    backend = HandleMap()
    rows = [{"action": "glance", "target": "signal:0", "score": 0.0}]
    view = {"can": [{"handle": "signal:0", "action": "glance", "what": "a stomach ache"}], "around": {"things": []}}
    context = ActorContext(character=None, turn=1, observations={}, affordances=rows, agent_view=view)
    token = backend.mask_context(context).agent_view["can"][0]["handle"]
    reply = {"major_action": None, "free_actions": [{"action": "glance", "target": token, "params": {}}]}
    translated, errors = backend.translate(reply)
    assert errors == []
    assert translated["free_actions"][0]["target"] == "signal:0"
    _, errors = backend.translate({"free_actions": [{"action": "glance", "target": "hxzz", "params": {}}]})
    assert errors == [UNKNOWN_HANDLE]


def test_a_token_from_an_earlier_view_is_refused_when_the_current_view_does_not_offer_it():
    backend = HandleMap()
    view = {"around": {"things": [{"handle": "knife", "what": "knife"}]}}
    first = ActorContext(character=None, turn=1, observations={}, affordances=[], agent_view=view)
    token = backend.mask_context(first).agent_view["around"]["things"][0]["handle"]
    later = ActorContext(character=None, turn=2, observations={}, affordances=[],
                         agent_view={"around": {"things": []}})
    backend.mask_context(later)
    _, errors = backend.translate({"major_action": {"action": "strike", "target": token, "params": {}}})
    assert errors == [UNKNOWN_HANDLE], "a thing no longer in view cannot be named by its old token"
    assert backend.labels[token] == "knife", "the mapping keeps the token for when the thing is seen again"


def test_a_note_or_request_handle_in_the_private_part_is_a_token_and_reads_back():
    """The private rows that carry handles (a note held, a request made to the resident) are masked first, as the packet
    lists the private part first, and a give_note names its note by the token."""
    backend = HandleMap()
    view = {"self": {"giveable_notes": [{"handle": "note_7", "what": "a list"}],
                     "requests": [{"handle": "req_2", "who": "Ben", "what": "a loan"}]},
            "around": {"things": [{"handle": "knife", "what": "knife"}]}}
    context = ActorContext(character=None, turn=1, observations={}, affordances=[], agent_view=view)
    masked = backend.mask_context(context).agent_view
    note, request = masked["self"]["giveable_notes"][0]["handle"], masked["self"]["requests"][0]["handle"]
    assert [note, request] == ["hxa", "hxb"], "the private rows are numbered before the things"
    assert masked["self"]["requests"][0]["who"] == "Ben"
    translated, errors = backend.translate({"free_actions": [
        {"action": "give_note", "target": "Ben", "params": {"note": note}},
        {"action": "decline", "target": request, "params": {}}]})
    assert errors == []
    assert translated["free_actions"][0]["params"]["note"] == "note_7"
    assert translated["free_actions"][1]["target"] == "req_2"


def test_a_reaction_choice_reads_back_from_its_token():
    backend = HandleMap()
    tokens = backend.mask_choices(["yield", "resist"])
    assert [backend.labels[t] for t in tokens] == ["yield", "resist"]
    translated, errors = backend.translate({"major_action": {"action": tokens[1], "params": {}}}, reaction=True)
    assert errors == [] and translated["major_action"]["action"] == "resist"
    _, errors = backend.translate({"major_action": {"action": "resist", "params": {}}}, reaction=True)
    assert errors == [UNKNOWN_HANDLE], "a reaction must name the choice by its token"


# ------------------------------------------------------------------ stop and resume, the log, replay
def test_the_checkpoint_round_trip_keeps_the_tokens(perception_off):
    game = _game()
    backend = game.backends["Ada"]
    for _ in range(2):
        game.step()
    data = json.loads(json.dumps(checkpoint_llm_backend(backend)))
    restored = restore_llm_backend(data, game.characters["Ada"], FakeProvider(_reply("rest")))
    assert restored.handles.to_dict() == backend.handles.to_dict()
    context = game._context("Ada")
    before = backend.handles.mask_context(context).agent_view["around"]["things"]
    after = restored.handles.mask_context(context).agent_view["around"]["things"]
    assert before == after


def test_the_log_holds_token_to_world_handle_beside_each_call_and_the_prompt_as_sent(perception_off, tmp_path):
    game = _game()
    backend = game.backends["Ada"]
    backend.log = LLMLog(tmp_path / "llm.jsonl", run_id="p054b")
    game.step()
    sent = _sent(game)
    record = [r for r in read_log(tmp_path / "llm.jsonl") if r.get("kind") == "call"][-1]
    assert record["messages"] == sent["messages"]
    referee = record["referee"]["handles"]
    assert referee and all(TOKEN.match(token) for token in referee)
    # Every token the prompt carries is in the referee field, with the world handle it stands for.
    assert set(_handles_sent(sent)) <= set(referee)
    assert set(referee.values()) <= set(backend.handles.labels.values())
    assert {"knife", "spade_1"} & set(referee.values())


def test_a_recorded_run_replays_with_the_same_prompts_and_replies(perception_off, tmp_path):
    path = tmp_path / "run.jsonl"
    provider = FakeProvider(_reply("rest"))
    game = _game(RecordingProvider(provider, Transcript(path, run_id="p054b")))
    recorded = []
    for _ in range(3):
        game.step()
        recorded.append(game.backends["Ada"].last_backend_state.get("prompt_hash"))
    replay = ReplayProvider(path)
    replayed_game = _game(replay)
    replayed = []
    for _ in range(3):
        replayed_game.step()
        replayed.append(replayed_game.backends["Ada"].last_backend_state.get("prompt_hash"))
    assert replay.mismatches == []
    assert replayed == recorded
    assert replayed_game.backends["Ada"].llm_counts["successes"] == 3


def test_a_masked_context_leaves_the_world_view_unchanged(perception_off):
    game = _game()
    context = game._context("Ada")
    before = json.dumps(context.agent_view, sort_keys=True, default=str)
    game.backends["Ada"].handles.mask_context(context)
    assert json.dumps(context.agent_view, sort_keys=True, default=str) == before
