"""Phase 067: the terminal interface in two modes. The map mode draws the character art, and the text mode is a text
adventure whose room is written from the prompt packet (Phase 054) the LLM resident would get. Both modes play through
the same Session, the same perceiver and the same reply binder (reply_schema.check and to_wire, as the LLM path uses).

Each test names one acceptance item of the brief. The switches (PERCEPTION.enabled and READING.enabled) are forced on
inside a fixture and restored. Written marks are scripted, since the 100-resident town has none.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                                  # noqa: E402
from bigville.backends import reply_schema                            # noqa: E402
from bigville.backends.prompts import PromptBuilder                   # noqa: E402
from bigville.backends.llm import _check_reply                        # noqa: E402
from bigville.llm_log import verify_log                               # noqa: E402
from bigville.tui import art, narrate, prose                          # noqa: E402
from bigville.tui.__main__ import main                                # noqa: E402
from bigville.tui.app import Session, run_text                        # noqa: E402
from bigville.tui.client import EmbeddedClient                        # noqa: E402
from bigville.tui.commands import placed                              # noqa: E402
from bigville.tui.render import render                                # noqa: E402
from domains.pack import load_pack                                    # noqa: E402
from domains.tui_check import _check_art, _check_prose, check_tui     # noqa: E402
from worlds import daynight as dn                                     # noqa: E402

SEED = 305000
PLAYER = "Alby Marsh"
PACK_NAME = "bigville"
PACK = load_pack(PACK_NAME)
DIGIT = re.compile(r"\d")
MENU_NUMBER = re.compile(r"^\d+\. ")
KINDS = {"ale_sign": "sign"}


@pytest.fixture
def game():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


@pytest.fixture
def perception_and_reading():
    """PERCEPTION and READING forced on for one test, then restored (the pack tables are cached per process)."""
    previous = (PACK["PERCEPTION"]["enabled"], PACK["READING"]["enabled"])
    PACK["PERCEPTION"]["enabled"] = True
    PACK["READING"]["enabled"] = True
    try:
        yield
    finally:
        PACK["PERCEPTION"]["enabled"], PACK["READING"]["enabled"] = previous


@pytest.fixture
def perception_on():
    previous = PACK["PERCEPTION"]["enabled"]
    PACK["PERCEPTION"]["enabled"] = True
    try:
        yield
    finally:
        PACK["PERCEPTION"]["enabled"] = previous


class Recorder:
    """A log that keeps the records in memory (the same append() as bigville.llm_log.LLMLog)."""

    def __init__(self):
        self.records = []

    def append(self, record):
        self.records.append(record)
        return len(self.records)


def _text_run(game, lines, *, show_packet=False, log=None):
    session = Session(EmbeddedClient(game, PLAYER), text=True)
    out = io.StringIO()
    run_text(session, io.StringIO("".join(f"{line}\n" for line in lines)), out, show_packet=show_packet, log=log)
    return session, out.getvalue()


def _llm_reply(reply, affordances):
    """The wire reply a model's JSON reply gives through the LLM path: llm._check_reply (the structural and schema
    checks), then reply_schema.to_wire with the context's affordances, as LLMBackend._check does."""
    fields = tuple(PACK["PROMPT_RESPONSE_FIELDS"])
    parsed = json.loads(json.dumps(reply))
    errors = _check_reply(parsed, fields, PACK_NAME, None)
    assert errors == [], errors
    return reply_schema.to_wire(parsed, PACK_NAME, affordances=affordances)


def _resident(game):
    return next(name for name in game.characters if name != game.player and game.world.is_alive(name))


def _as(game, name, *, literacy, role, capability):
    world = game.world
    world.eng.set_attr(world._actors[name], "literacy", float(literacy))
    world.eng.set_attr(world._actors[name], "role", role)
    world.eng.set_attr(world._actors[name], "capability", float(capability))
    game.backends[name] = game.backends[game.player]
    return name


def _objects(monkeypatch, game, *ids):
    rows = [{"id": i, "kind": KINDS[i], "location": "world"} for i in ids]
    monkeypatch.setattr(game.world, "physical_object_observations", lambda actor: [dict(r) for r in rows])


# ------------------------------------------------------------------ the tables and the self-test
def test_the_pack_tables_are_clean_in_both_packs():
    for pack in ("bigville", "test_hamlet"):
        errors, warnings, info = [], [], []
        check_tui(pack, errors, warnings, info)
        assert errors == [] and info, (pack, errors)


def test_self_test_finds_a_map_glyph_with_no_tile():
    pack = copy.deepcopy({"TUI_ART": PACK["TUI_ART"], "MAP_GLYPHS": PACK["MAP_GLYPHS"]})
    del pack["TUI_ART"]["tiles"]["T"]
    errors = []
    _check_art(pack, errors)
    assert any("'T'" in error and "no tile" in error for error in errors), errors


def test_self_test_finds_a_tile_of_the_wrong_width_and_an_unknown_colour():
    pack = copy.deepcopy({"TUI_ART": PACK["TUI_ART"], "MAP_GLYPHS": PACK["MAP_GLYPHS"]})
    pack["TUI_ART"]["tiles"]["="]["tile"] = ":::"
    pack["TUI_ART"]["tiles"]["~"]["colour"] = "puce"
    errors = []
    _check_art(pack, errors)
    assert any("two characters" in error for error in errors)
    assert any("not in colours" in error for error in errors)


def test_self_test_finds_a_prose_sentence_with_a_missing_field_and_a_digit():
    pack = copy.deepcopy({"TUI_PROSE": PACK["TUI_PROSE"]})
    pack["TUI_PROSE"]["exits"] = "Ways on: {places}."
    pack["TUI_PROSE"]["nobody"] = "Nobody is in sight, room 3."
    errors = []
    _check_prose(pack, errors)
    assert any("exits names fields" in error for error in errors)
    assert any("nobody carries a digit" in error for error in errors)


def test_the_art_glyphs_and_the_prose_are_one_character_and_no_digit_in_the_pack():
    for glyph, row in PACK["TUI_ART"]["tiles"].items():
        assert len(row["tile"]) == 2 and not DIGIT.search(row["tile"]), glyph
    for line in PACK["TUI_PROSE"]["help"]:
        assert not DIGIT.search(line)


# ------------------------------------------------------------------ the modes and the defaults
def test_with_no_mode_the_screen_has_no_art_and_no_mode_flag_changes_it(game, capsys):
    session = Session(EmbeddedClient(game, PLAYER))
    default = session.screen()
    assert "known" not in default[16] and "stranger" not in default[16]
    assert session.art is False and session.text is False
    out = io.StringIO()
    assert main(["--player", PLAYER, "--snapshot"], stdout=out) == 0
    assert out.getvalue().splitlines()[:len(default)] == default


def test_the_map_mode_draws_two_character_tiles_and_a_glyph_beside_each_person(game):
    session = Session(EmbeddedClient(game, PLAYER), art=True)
    screen = session.screen()
    map_rows = [line[:30] for line in screen[1:16]]
    assert all(len(row) == 30 for row in map_rows)
    assert any("@@" in row for row in map_rows), map_rows
    people = session.view["around"]["people"]
    assert people, "the test town has people in sight"
    tab = art.mark_people(session.view, PACK_NAME, [narrate._cap(narrate.person_line(p, PACK_NAME)) for p in people])
    for person, line in zip(people, tab):
        expected = PACK["TUI_ART"]["people"]["known" if person.get("name") else "stranger"]["glyph"]
        assert line.startswith(expected + " ")
    assert "known" in "\n".join(screen) or "stranger" in "\n".join(screen)


def test_the_map_mode_draws_the_percept_label_for_a_low_tier_resident_and_not_the_true_name(game, monkeypatch,
                                                                                            perception_on):
    day = Session(EmbeddedClient(game, PLAYER), art=True)
    named = [p["name"] for p in day.view["around"]["people"] if p.get("name")]
    assert named, "in daylight some resident is known by name"
    monkeypatch.setattr(dn, "view_light", lambda world, actor: "dark")
    dim = Session(EmbeddedClient(game, PLAYER), art=True)
    text = "\n".join(dim.screen())
    for name in named:
        assert name not in text, f"{name} is on the dark screen"
    assert "a person" in text or "stranger" in text or "someone" in text


# ------------------------------------------------------------------ the text mode: one machinery
def test_the_text_mode_plays_scripted_turns_and_each_reply_is_the_one_the_llm_binder_makes(game):
    client = EmbeddedClient(game, PLAYER)
    view = client.view()
    named = [p["name"] for p in view["around"]["people"] if p.get("name")]
    walk = next(row for row in view["can"] if row["action"] == "walk")
    place = " ".join(walk["what"].split()[1:])
    assert named, "the test town has a known resident in sight"
    lines = ["look", "wait", f"say {named[0]}: hello", f"go {place}", "wait"]
    turn_before = game.world._turn
    recorder = Recorder()
    _, output = _text_run(game, lines, log=recorder)
    assert game.world._turn - turn_before == 4, "four lines spoke to the world: wait, say, walk, wait"
    replies = [record["reply"] for record in recorder.records if record["reply"] is not None]
    assert len(replies) == 2
    affordances = client.affordances()
    expected = [
        _llm_reply({"utterances": [{"to": named[0], "text": "hello"}]}, affordances),
        _llm_reply({"major_action": {"action": "walk", "target": walk["handle"]}}, affordances),
    ]
    for reply, want in zip(replies, expected):
        got = reply_schema.to_wire(reply, PACK_NAME, affordances=affordances)
        assert got == want, (got, want)
    assert "Ways on:" in output and "Time passes." in output


def test_a_line_the_grammar_cannot_place_asks_again_and_the_world_does_not_move(game):
    turn_before = game.world._turn
    recorder = Recorder()
    _, output = _text_run(game, ["hello there", "dance wildly"], log=recorder)
    assert game.world._turn == turn_before
    assert output.count(PACK["TUI_PROSE"]["unplaced"]) == 2, "both lines are asked again: no lexicon verb in either"
    assert all(record["reply"] is None for record in recorder.records)


def test_the_grammar_places_the_command_words_and_asks_again_for_the_rest():
    for line in ("look", "wait", "say Bram: hi", "go to the mill", "take a few bread", "smash lock with hammer hard",
                 "eat", "work burn charcoal", "sleep", "3", "quit"):
        assert placed(line, PACK_NAME), line
    for line in ("hello there", "dance", "xyzzy plugh"):
        assert not placed(line, PACK_NAME), line


def test_look_writes_the_room_again_from_the_packet(game):
    _, output = _text_run(game, ["look"])
    assert output.count("Ways on:") == 2, "the room is written on arrival and again after look"


def test_the_packet_the_mode_prints_is_the_packet_an_llm_resident_gets(game):
    client = EmbeddedClient(game, PLAYER)
    printed = client.packet()
    context = game._context(PLAYER)
    context.agent_view = game.agent_view(PLAYER)
    llm_side = PromptBuilder(pack=PACK_NAME).build(context)
    assert printed == llm_side.as_dict()
    assert printed["context"]["public"].keys() <= {"now", "around", "map", "can", "last", "heard", "consult"}


def test_show_packet_prints_the_packet_after_the_room_and_it_parses_back(game):
    session = Session(EmbeddedClient(game, PLAYER), text=True)
    out = io.StringIO()
    run_text(session, io.StringIO(""), out, show_packet=True)
    text = out.getvalue()
    title = PACK["TUI_PROSE"]["packet"]
    start = text.index(title) + len(title) + 1
    parsed, _ = json.JSONDecoder().raw_decode(text[start:])
    assert parsed == EmbeddedClient(game, PLAYER).packet()


def test_the_turn_log_is_hash_chained_and_holds_each_turn_with_the_packet_it_was_given(game, tmp_path):
    out = io.StringIO()
    code = main(["--player", PLAYER, "--mode", "text", "--log-dir", str(tmp_path)],
                stdin=io.StringIO("look\nwait\nquit\n"), stdout=out)
    assert code == 0
    files = [p for p in os.listdir(tmp_path) if p.endswith(".jsonl")]
    assert len(files) == 1
    path = os.path.join(tmp_path, files[0])
    check = verify_log(path)
    assert check.ok, check.problems
    from bigville.llm_log import read_log
    records = [row.get("record", row) for row in read_log(path)]
    assert [r["typed"] for r in records] == ["look", "wait", "quit"]
    for record in records:
        packet_bytes = prose.packet_text(record["packet"]).encode("utf-8")
        assert record["packet_sha256"] == hashlib.sha256(packet_bytes).hexdigest()
        assert "reasoning" not in json.dumps(record)


def test_text_mode_has_no_url_and_the_packet_flags_need_text_mode(capsys):
    with pytest.raises(SystemExit) as refused:
        main(["--player", PLAYER, "--mode", "text", "--url", "http://127.0.0.1:9"])
    assert refused.value.code == 2
    with pytest.raises(SystemExit) as refused:
        main(["--player", PLAYER, "--show-packet"])
    assert refused.value.code == 2


# ------------------------------------------------------------------ the writing and the perceiver's words
def test_with_reading_off_the_packet_has_no_writing_key_and_is_as_before(game):
    packet = EmbeddedClient(game, PLAYER).packet()
    assert "writing" not in packet["context"]["public"]["around"]
    assert set(packet["context"]["public"]["around"]) == {"people", "seen", "things"}


def test_writing_reaches_the_packet_the_room_and_the_narrator_with_reading_on(game, monkeypatch,
                                                                             perception_and_reading):
    _objects(monkeypatch, game, "ale_sign")
    name = _as(game, _resident(game), literacy=0.55, role="labourer", capability=0.55)
    client = EmbeddedClient(game, name)
    view = client.view()
    percept = view["around"]["writing"][0]["percept"]
    assert percept == "a sign: ALE, sold here"
    packet = client.packet()
    assert packet["context"]["public"]["around"]["writing"] == [{"percept": percept}]
    assert packet["context"]["sizes"]["writing"] > 0
    room = prose.room_lines(packet, view, PACK_NAME)
    assert "A sign: ALE, sold here." in room
    assert "A sign: ALE, sold here." in narrate.arrival_lines(view, PACK_NAME)


# ------------------------------------------------------------------ the leak rules
def _referee_names():
    return load_pack(PACK_NAME)["AGENT_VIEW_REFEREE_ONLY"]


def test_no_text_or_map_line_carries_a_raw_number_or_a_referee_name_in_a_short_run(game):
    _, output = _text_run(game, ["look", "wait", "wait", "look", "wait"])
    lines = [line for line in output.splitlines() if not line.startswith(">")]
    for line in lines:
        stripped = MENU_NUMBER.sub("", line)
        assert not DIGIT.search(stripped), f"a raw number in the text mode: {line!r}"
    body = output
    for name in _referee_names():
        assert not re.search(rf"\b{re.escape(name)}\b", body), f"a referee-only name in the text mode: {name}"
    client = EmbeddedClient(game, PLAYER)
    session_map = Session(client, art=True)
    for _ in range(2):
        screen = session_map.screen()
        for line in screen:
            stripped = MENU_NUMBER.sub("", line)
            assert not DIGIT.search(stripped), f"a raw number on the map screen: {line!r}"
        for name in _referee_names():
            assert not re.search(rf"\b{re.escape(name)}\b", "\n".join(screen)), name
        session_map.line("wait")


def test_the_text_mode_shows_only_what_the_packet_and_the_view_carry(game):
    client = EmbeddedClient(game, PLAYER)
    packet = client.packet()
    view = client.view()
    allowed_top = set(load_pack(PACK_NAME)["AGENT_VIEW_WHITELIST"]["top"])
    assert set(view) <= allowed_top
    public = packet["context"]["public"]
    assert set(public) <= {"now", "around", "map", "can", "last", "heard", "consult"}
    assert set(public["around"]) <= {"people", "seen", "things", "writing"}
    assert set(packet["context"]["private"]) <= {"lead", "body", "skills", "carrying", "knows", "places", "kin",
                                                  "lessons", "notes"}
    room = "\n".join(prose.room_lines(packet, view, PACK_NAME))
    assert "sizes" not in room and "omitted" not in room
