"""Phase 071c, decision 2: the terminal interface shows the body and takes the attend words.

* the felt body (Phase 069) is drawn in the sheet's body tab and in the room (text mode), and the labelled body
  keeps its lines when the view is labelled;
* `glance [N]`, `attend [N]`, `press <region>` and `strike NAME [at REGION]` are typed words: a glance is a free
  action (no slot, no tick, sent without a turn), the rest are major actions;
* `last` shows the sound and the place an attend, press or glance answered with, never a cause;
* the help lists the new words, and `placed` accepts them.

Embedded games only (town100, seed 305000); the HTTP client raises UnsupportedOverHttp for a free action.
"""
from __future__ import annotations

import io
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                                   # noqa: E402
from bigville.backends import reply_schema                             # noqa: E402
from bigville.tui import commands, narrate, prose                      # noqa: E402
from bigville.tui.app import Session, run_text                         # noqa: E402
from bigville.tui.client import EmbeddedClient, HttpClient, UnsupportedOverHttp  # noqa: E402
from bigville.tui.render import sheet_lines                            # noqa: E402
from domains.pack import load_pack                                     # noqa: E402

PACK = "bigville"
SEED = 305000
PLAYER = "Verity Peaseblossom"
WORDS = load_pack(PACK)["NARRATION"]


def _adult(world):
    return next(name for name in world._actors
                if world.eng.node(world._actors[name])["attrs"].get("life_stage") == "adult")


def _felt_player(world, name, locus="arm", amount=0.4):
    world.body_of(name).state["ledger"][locus] = amount


def _neighbour(world, name):
    return next(other for other in world._actors if other != name)


@pytest.fixture
def game():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


def _view(people=("Bram Smith",), can=()):
    """A small hand-written view for the parser: the people the view names and its can rows."""
    return {"mode": "agent", "actor": PLAYER, "self": {"name": PLAYER, "body": {}},
            "around": {"people": [{"name": name, "distance": "beside you"} for name in people], "things": []},
            "can": list(can), "last": {}}


# ------------------------------------------------------------------ the words
def test_glance_parses_to_a_free_action_on_the_signal_handle_and_takes_a_number():
    assert commands.parse("glance", _view(), PACK).reply == {"free_actions": [{"action": "glance",
                                                                             "target": "signal:1"}]}
    assert commands.parse("glance 2", _view(), PACK).reply == {"free_actions": [{"action": "glance",
                                                                               "target": "signal:2"}]}


def test_attend_and_press_parse_to_major_actions():
    assert commands.parse("attend 2", _view(), PACK).reply == {"major_action": {"action": "attend",
                                                                              "target": "signal:2"}}
    assert commands.parse("press upper belly", _view(), PACK).reply == {"major_action": {
        "action": "press", "target": "upper_belly"}}
    # press with no region is not a body probe: the physical verb push is kept, as before.
    assert commands.parse("press", _view(), PACK).reply["major_action"]["action"] == "attempt"


def test_strike_names_a_person_and_an_optional_region_and_intensity():
    reply = commands.parse("strike Bram at head", _view(), PACK).reply
    assert reply == {"major_action": {"action": "strike", "target": "Bram Smith", "params": {"region": "head"}}}
    reply = commands.parse("punch Bram hard", _view(), PACK).reply
    assert reply == {"major_action": {"action": "strike", "target": "Bram Smith", "intensity": "hard"}}


def test_a_strike_with_no_person_named_stays_a_physical_attempt():
    reply = commands.parse("hit the lock", _view(), PACK).reply
    assert reply["major_action"]["action"] == "attempt"


def test_an_unknown_region_is_passed_as_words_for_the_world_to_refuse():
    reply = commands.parse("strike Bram at elbow", _view(), PACK).reply
    assert reply["major_action"]["params"] == {"region": "elbow"}
    assert reply_schema.check(reply, PACK) == []


def test_the_new_words_are_placed_and_a_nonsense_line_is_not():
    for line in ("glance", "glance 2", "attend", "attend 2", "press upper belly", "strike Bram at head", "hit Bram"):
        assert commands.placed(line, PACK), line
    assert not commands.placed("flibbertigibbet about", PACK)


def test_the_new_words_are_in_the_help_of_both_modes():
    lines = narrate.help_lines(PACK)
    text = " ".join(lines)
    for word in ("glance", "attend", "press", "strike"):
        assert word in text, word
    assert any("glance" in line for line in load_pack(PACK)["TUI_PROSE"]["help"])


# ------------------------------------------------------------------ the felt body
def test_the_sheet_draws_the_felt_body_and_the_labelled_body_keeps_its_words(game):
    world = game.world
    name = _adult(world)
    _felt_player(world, name)
    felt = game.agent_view(name, mode="agent")
    lines = sheet_lines(felt, "body", PACK)
    assert any(" -- " in line for line in lines), lines
    assert not any(line.lower().startswith("hunger:") or line.lower().startswith("energy:") for line in lines)
    labelled = game.agent_view(name, mode="agent", interoception="labelled")
    words = sheet_lines(labelled, "body", PACK)
    assert any(line.startswith("Energy:") or line.startswith("Hunger:") for line in words), words


def test_the_felt_body_lines_are_the_same_in_both_modes_and_come_from_the_body_renderer(game):
    from domains.interoception import render_felt_body
    world = game.world
    name = _adult(world)
    _felt_player(world, name)
    body = game.agent_view(name, mode="agent")["self"]["body"]
    expected = render_felt_body(body)
    assert expected and narrate.body_lines({"self": {"body": body}}, PACK)[:len(expected)] == expected
    record = {"context": {"private": {"body": body}, "public": {}}}
    assert all(line in prose.room_lines(record, {"self": {"name": name}}, PACK) for line in expected)


def test_the_outcome_names_a_sound_and_a_place_and_says_nothing_when_silent():
    done = {"action": "glance", "outcome": "done", "place": "arm", "sound": "hnnnn"}
    assert narrate.outcome_lines({"last": done}, PACK)[-1] == "From your arm: hnnnn."
    silent = {"action": "press", "outcome": "done", "place": "upper belly", "sound": "nothing"}
    assert narrate.outcome_lines({"last": silent}, PACK)[-1] == "Nothing answers from your upper belly."


# ------------------------------------------------------------------ the session: a glance is no turn
def test_a_glance_is_sent_without_a_turn_and_its_sound_and_place_show_in_last(game):
    world = game.world
    client = EmbeddedClient(game, PLAYER)
    _felt_player(world, PLAYER)
    session = Session(client, PACK)
    turn = world._turn
    lines = session.line("glance")
    assert world._turn == turn                       # no tick: the world did not move
    assert session.view["last"]["action"] == "glance" and session.view["last"]["place"] == "arm"
    assert any(line.startswith("From your arm") or line.startswith("Nothing answers") for line in lines), lines


def test_an_attend_from_the_session_is_a_major_action_and_shows_its_sound(game):
    world = game.world
    _felt_player(world, PLAYER)
    session = Session(EmbeddedClient(game, PLAYER), PACK)
    session.line("attend")
    last = session.view["last"]
    assert last.get("action") == "attend", last
    if last.get("outcome") == load_pack(PACK)["VIEW_WORDS"]["done"]:
        assert last["place"] == "arm" and "sound" in last


def test_a_press_from_the_session_names_its_place(game):
    world = game.world
    _felt_player(world, PLAYER)
    session = Session(EmbeddedClient(game, PLAYER), PACK)
    session.line("press arm")
    last = session.view["last"]
    assert last.get("action") == "press", last
    assert last.get("place") == "arm" and "sound" in last


def test_a_strike_from_the_session_sends_the_region_to_the_world(game):
    world = game.world
    victim = _neighbour(world, PLAYER)
    session = Session(EmbeddedClient(game, PLAYER), PACK)
    session.line(f"strike {victim} at arm")
    assert session.last_reply["major_action"]["params"] == {"region": "arm"}
    assert game.last_responses[PLAYER].major_action.params.get("region") == "arm"


def test_text_mode_writes_the_glance_outcome_into_the_room_stream(game):
    world = game.world
    _felt_player(world, PLAYER)
    session = Session(EmbeddedClient(game, PLAYER), PACK, text=True)
    out = io.StringIO()
    run_text(session, io.StringIO("glance\nquit\n"), out, echo=False)
    text = out.getvalue()
    assert "Last action: glance" in text
    assert "From your arm" in text or "Nothing answers from your arm" in text


def test_over_http_a_glance_on_its_own_runs_with_no_turn():
    """Phase 071d (was: raises UnsupportedOverHttp). A glance alone goes to /api/free over HTTP: it runs with no step,
    so the turn does not advance, and the server returns the player's view."""
    import threading
    from http.server import HTTPServer
    from bigville.server import BigvilleHandler, GameService
    service = GameService(scenario="town100", seed=SEED, player=PLAYER, mode="agent")
    server = HTTPServer(("127.0.0.1", 0), type("Handler", (BigvilleHandler,), {"service": service}))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        turn = service.game.world._turn
        result = HttpClient(f"http://127.0.0.1:{server.server_address[1]}", PLAYER).apply_free(
            {"free_actions": [{"action": "glance", "target": "signal:1"}]})
    finally:
        server.shutdown()
        server.server_close()
    assert result["status"] == "free" and "view" in result
    assert service.game.world._turn == turn
    assert service.game.free_outcomes[PLAYER]["action"] == "glance"
