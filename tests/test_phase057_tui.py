"""Phase 057: the terminal interface, built on the agent view.

Covers: the 80 by 24 render (a snapshot of a fixed view), the three map levels, the command parser (verbs,
aliases, intensity and amount words, handles, ambiguity, unknown verbs passed to the world), the plain-mode
session on an embedded town100 game (five turns on StringIO), reactions (Phase 029) in the view and the
session, the HTTP client against a loopback stub and a real agent-mode server (it never fetches /api/state),
the curses fallback, and the leak test over the rendered lines of a town100 resident.

No test opens a network port except on 127.0.0.1 with port 0.
"""
from __future__ import annotations

import inspect
import io
import json
import re
import threading
from http.server import ThreadingHTTPServer
from urllib import request as urlrequest

import pytest

from bigville.api import create_game
from bigville.backends import ActorResponse, ProposedAction
from bigville.backends.cheap import DeterministicBackend
from bigville.backends.reply_schema import check, to_wire
from bigville.tui import client as tui_client
from bigville.tui import commands, narrate
from bigville.tui.app import Session, choose_front_end, run_curses, run_plain
from bigville.tui.client import EmbeddedClient, HttpClient, UnsupportedOverHttp
from bigville.tui.render import render
from domains.pack import load_pack

PACK = "bigville"
PLAYER = "Alby Marsh"
DIGIT = re.compile(r"\d")
MENU_NUMBER = re.compile(r"^\d+\. ")


# ------------------------------------------------------------------ fixtures

def _rows():
    """A 15 by 15 patch: grass, a path, a floor and a tree in a fixed pattern, the player at the centre."""
    rows = []
    for y in range(15):
        row = ["=" if (x + y) % 7 == 0 else "_" if (x * y) % 11 == 3 else "T" if (x + 2 * y) % 13 == 5 else "."
               for x in range(15)]
        if y == 7:
            row[7] = "@"
        rows.append("".join(row))
    return rows


def fixed_view():
    """A hand-written view that has every section a panel reads. Built from words only."""
    return {
        "mode": "agent",
        "actor": "Mara Quill",
        "self": {
            "name": "Mara Quill", "job": "miller", "life_stage": "an adult", "age": "grown",
            "persona": {"name": "Mara Quill", "traits": "quick to laugh; careful with money",
                        "as_others_see": "looks cheerful", "life": "You were born in Bigville.",
                        "usual_day": "Today is spring.", "ties": "Bram Smith (friend)"},
            "body": {"health": "in good health", "health_status": "in good health", "energy": "fresh",
                     "hunger": "a little hungry", "strength": "of ordinary strength",
                     "stamina": "you have good wind", "mood": "content"},
            "skills": ["competent at milling", "a novice at fighting"],
            "carrying": {"inventory": ["flour (a handful)"], "held": ["wooden scoop (sound)"],
                         "worn": ["apron"], "load": "you carry it easily"},
            "knows": [{"name": "Bram Smith", "understood": "you understand it", "gist": "someone you know"},
                      {"name": "well provides clean water", "understood": "you understand it",
                       "gist": "an idea you have heard of"}],
            "places": [{"name": "mill", "precision": "you know where it is"}],
            "kin": ["parent: Ida Smith"],
        },
        "now": {"time": "at dawn", "season": "spring", "weather": "clear skies"},
        "around": {
            "people": [
                {"name": "Bram Smith", "job": "labourer", "distance": "right beside you",
                 "looks": ["looks tired", "looks gaunt"]},
                {"description": "a stranger (carter)", "distance": "a few steps off", "looks": ["looks calm"]},
            ],
            "heard": [{"from": "Bram Smith", "text": "morning, Mara"}],
            "seen": [{"who": "someone", "did": "moved something you could see"}],
            "things": [{"handle": "chest_1", "what": "wooden chest"}],
        },
        "map": {"level": "full", "caption": "a patch of ground around you", "rows": _rows(),
                "legend": {".": "open grass", "=": "a path", "_": "a floor", "T": "a tree", "@": "you"}},
        "can": [
            {"handle": "work:grind_flour", "action": "work", "what": "grind flour"},
            {"handle": "target:4", "action": "walk", "what": "walk to the mill"},
        ],
        "last": {"action": "work", "outcome": "it happened"},
    }


def _menu_view():
    view = fixed_view()
    view["around"]["things"] = [{"handle": "chest_1", "what": "wooden chest"},
                                {"handle": "chest_2", "what": "oak chest"}]
    return view


def _game(player=PLAYER):
    return create_game(scenario="town100", seed=305000, player=player)


def _digit_leaks(lines, handles):
    """Digits a rendered line may carry: a handle the world uses, or a menu number at the start of a line.
    Anything else is a raw number (the rule the agent view's leak test uses, see tests/test_phase052)."""
    leaks = []
    for line in lines:
        text = MENU_NUMBER.sub("", line)
        for handle in handles:
            text = text.replace(handle, "")
        if DIGIT.search(text):
            leaks.append(line.rstrip())
    return leaks


def _handles(view):
    out = [row["handle"] for row in view.get("can") or []]
    out += [row["handle"] for row in (view.get("around") or {}).get("things") or []]
    return out


# ------------------------------------------------------------------ render

SNAPSHOT_80x24 = [
    'Bigville   at dawn, spring, clear skies                                         ',
    '=....T.=......=  [Body] Skills Knows Carrying People                            ',
    '..._..=......=_  Work: miller                                                   ',
    '.T...=._....=.T  Life: an adult, grown                                          ',
    '._..=......=_..  Health: in good health                                         ',
    '...=....._=....  Energy: fresh                                                  ',
    '..=.._..T=.....  Hunger: a little hungry                                        ',
    '.=...._.=......  Strength: of ordinary strength                                 ',
    '=._.T..@....._=  Stamina: you have good wind                                    ',
    '..T...=..._..=.  Mood: content                                                  ',
    'T..._=......=T.  Traits: quick to laugh; careful with money                     ',
    '....=..._..=...  Others see: looks cheerful                                     ',
    '...=.....T=....                                                                 ',
    '..=_...T.=...._                                                                 ',
    '.=...T._=......                                                                 ',
    '=_.T...=...._.=                                                                 ',
    '. open grass   = a path   _ a floor   T a tree   @ you                          ',
    'Your move                                                                       ',
    'Bram Smith is right beside you, looking tired and gaunt.                        ',
    'A stranger (carter) is a few steps off, looking calm.                           ',
    'Bram Smith says: "morning, Mara"                                                ',
    'Someone moved something you could see.                                          ',
    'Last action: work. It happened.                                                 ',
    '>                                                                               ',
]


def test_the_render_of_a_fixed_view_at_80_by_24_matches_its_snapshot():
    log = ["Bram Smith is right beside you, looking tired and gaunt.",
           "A stranger (carter) is a few steps off, looking calm.",
           "Bram Smith says: \"morning, Mara\"",
           "Someone moved something you could see.",
           "Last action: work. It happened."]
    screen = render(fixed_view(), 80, 24, log=log, pack=PACK)
    assert len(screen) == 24
    assert all(len(line) == 80 for line in screen)
    assert screen == SNAPSHOT_80x24


def test_the_render_is_pure_and_repeats_exactly():
    view = fixed_view()
    assert render(view, 80, 24, pack=PACK) == render(view, 80, 24, pack=PACK)


def test_the_same_screen_renders_with_the_test_pack_words():
    screen = render(fixed_view(), 80, 24, pack="test_hamlet")
    assert len(screen) == 24 and screen[0].startswith(narrate.words("test_hamlet")["title"])
    assert screen[16].split()[-1] in ("you", "a", "path", "tree", "floor", "ground")


def test_each_sheet_tab_renders_in_words_and_the_active_tab_is_bracketed():
    view = fixed_view()
    for tab in ("body", "skills", "knows", "carrying", "people"):
        screen = render(view, 80, 24, tab=tab, pack=PACK)
        header = screen[1]
        assert header.count("[") == 1 and f"[{narrate.words(PACK)['tab_' + tab]}]" in header
    assert "competent at milling" in render(view, 80, 24, tab="skills", pack=PACK)[2]
    assert "Bram Smith (someone you know)" in render(view, 80, 24, tab="knows", pack=PACK)[2]


def test_the_map_is_drawn_by_its_level_hidden_vague_and_full():
    full = render(fixed_view(), 80, 24, pack=PACK)
    assert full[8][:15] == _rows()[7]
    hidden = fixed_view()
    hidden["map"] = {"level": "hidden"}
    screen = render(hidden, 80, 24, pack=PACK)
    panel = [line[:15] for line in screen[1:16]]
    assert "You have not seen this ground yet." in " ".join(part.strip() for part in panel)
    assert not any(glyph in "".join(panel) for glyph in "=@T_")  # no terrain drawn, only the words
    vague = fixed_view()
    vague["map"] = {"level": "vague", "rows": [], "labels": [{"glyph": "M", "word": "the mill"}]}
    screen = render(vague, 80, 24, pack=PACK)
    assert "Landmarks you remember: M the mill." in " ".join(line[:15].strip() for line in screen[1:16])


def test_a_view_without_a_map_is_drawn_as_hidden():
    view = fixed_view()
    view.pop("map")
    panel = " ".join(line[:15].strip() for line in render(view, 80, 24, pack=PACK)[1:16])
    assert "You have not seen this ground yet." in panel


def test_the_screen_refuses_a_size_too_small_to_draw():
    with pytest.raises(ValueError, match="at least"):
        render(fixed_view(), 30, 10, pack=PACK)


def test_a_real_resident_renders_at_80_by_24_with_the_status_and_the_menu():
    game = _game()
    session = Session(EmbeddedClient(game, PLAYER))
    screen = session.screen(80, 24)
    assert len(screen) == 24 and all(len(line) == 80 for line in screen)
    assert screen[0].startswith("Bigville")
    session.line("look")
    text = "\n".join(session.screen(80, 24))
    assert "You can" in text


# ------------------------------------------------------------------ commands

def _parse(text, view=None, pack=PACK):
    return commands.parse(text, view if view is not None else fixed_view(), pack)


def test_a_smash_with_a_tool_and_a_word_of_intensity_becomes_an_attempt_with_the_world_words():
    view = fixed_view()
    view["around"]["things"] = [{"handle": "lock_1", "what": "iron lock"}]
    view["self"]["carrying"]["held"] = ["hammer (sound)"]
    parsed = _parse("smash the lock with the hammer hard", view)
    assert parsed.kind == "propose"
    assert check(parsed.reply, PACK) == []
    wire = to_wire(parsed.reply, PACK, affordances=[])
    action = wire["major_action"]
    assert action["action"] == "attempt"
    assert action["params"]["verb"] == "smash"
    assert action["params"]["target"] == "lock_1"
    assert action["params"]["with"] == "hammer"
    assert action["params"]["intensity"] == load_pack(PACK)["INTENSITY_WORDS"]["hard"]


@pytest.mark.parametrize("text, verb", [("bash the lock", "smash"), ("batter the lock", "smash"),
                                        ("pry the lock", "pry"), ("push the cart", "push")])
def test_verb_aliases_resolve_to_the_canonical_verb(text, verb):
    parsed = _parse(text)
    assert parsed.kind == "propose"
    assert parsed.reply["major_action"]["params"]["verb"] == verb


@pytest.mark.parametrize("word", ["gently", "carefully", "normally", "hard", "with all your strength"])
def test_every_intensity_word_is_read_as_its_lexicon_value(word):
    parsed = _parse(f"push the cart {word}")
    wire = to_wire(parsed.reply, PACK, affordances=[])
    assert wire["major_action"]["params"]["intensity"] == pytest.approx(
        load_pack(PACK)["INTENSITY_WORDS"][word])


def test_a_number_is_accepted_where_an_intensity_word_would_be():
    parsed = _parse("push the cart 0.5")
    assert check(parsed.reply, PACK) == []
    assert to_wire(parsed.reply, PACK, affordances=[])["major_action"]["params"]["intensity"] == 0.5


def test_an_ambiguous_thing_asks_and_lists_the_handles():
    view = _menu_view()
    parsed = _parse("open the chest", view)
    assert parsed.kind == "ask"
    assert [handle for handle, _, _ in parsed.choices] == ["chest_1", "chest_2"]
    assert [what for _, what, _ in parsed.choices] == ["wooden chest", "oak chest"]


def test_a_named_thing_that_is_one_of_several_is_chosen_by_its_handle_words():
    view = _menu_view()
    parsed = _parse("open the wooden chest", view)
    assert parsed.kind == "propose"
    assert parsed.reply["major_action"]["target"] == "chest_1"


def test_walking_toward_a_known_place_binds_the_move_row_by_its_handle():
    view = fixed_view()
    parsed = _parse("walk toward the mill")
    assert parsed.kind == "propose"
    assert parsed.reply["major_action"] == {"action": "walk", "target": "target:4"}
    affordances = [{"action": "move", "target": "target:4", "destination": [3, 4], "trade": "mill",
                    "recipe": "", "kind": "", "sow_kind": ""}]
    wire = to_wire(parsed.reply, PACK, affordances=affordances)
    assert wire["major_action"]["action"] == "move"
    assert wire["major_action"]["params"]["destination"] == [3, 4]
    assert view["can"]


def test_walking_to_a_place_the_view_does_not_offer_passes_it_to_the_world():
    parsed = _parse("walk toward the quarry")
    assert parsed.kind == "propose"
    assert parsed.reply["major_action"] == {"action": "move", "params": {"toward": "quarry"}}


def test_a_work_line_matches_the_menu_row_by_its_words():
    parsed = _parse("make grind flour")
    assert parsed.kind == "propose"
    assert parsed.reply["major_action"] == {"action": "work", "target": "work:grind_flour"}


def test_say_addresses_a_known_resident_and_keeps_the_words():
    view = fixed_view()
    parsed = _parse("say Bram: good morning", view)
    assert parsed.reply == {"utterances": [{"to": "Bram Smith", "text": "good morning"}]}
    assert check(parsed.reply, PACK) == []


def test_take_reads_an_amount_word_a_kind_and_a_source():
    parsed = _parse("take a few bread from Bram")
    assert parsed.reply["major_action"] == {"action": "take", "params": {
        "kind": "bread", "amount": "a few", "source": "Bram Smith"}}
    assert check(parsed.reply, PACK) == []
    wire = to_wire(parsed.reply, PACK, affordances=[])
    assert wire["major_action"]["params"]["amount"] == load_pack(PACK)["AMOUNT_WORDS"]["a few"]


def test_wait_and_stop_pass_the_turn_and_quit_and_look_are_screen_commands():
    assert _parse("wait").kind == "pass"
    assert _parse(".").kind == "pass"
    assert _parse("stop").kind == "pass"
    assert _parse("quit").name == "quit"
    assert _parse("look").name == "look"
    assert _parse("sheet").name == "sheet"
    assert _parse("help").name == "help"


def test_an_unknown_verb_is_passed_to_the_world_not_refused_here():
    parsed = _parse("dance wildly")
    assert parsed.kind == "propose"
    assert parsed.reply["major_action"]["action"] == "attempt"
    assert parsed.reply["major_action"]["params"]["verb"] == "dance"
    assert check(parsed.reply, PACK) == []


def test_only_a_line_with_no_letters_is_unparseable_and_a_menu_number_selects():
    assert _parse("!!!").kind == "unparsed"
    assert _parse("").kind == "empty"
    picked = _parse("2")
    assert picked.kind == "select" and picked.index == 2


def test_a_reaction_answer_is_a_number_a_choice_or_its_words():
    view = fixed_view()
    view["reaction"] = {"from": "Bram Smith", "what": "coin", "options": [
        {"choice": "resist", "words": "hold on and resist"}, {"choice": "yield", "words": "let it go"}]}
    assert commands.parse_reaction("1", view) == "resist"
    assert commands.parse_reaction("yield", view) == "yield"
    assert commands.parse_reaction("let it go", view) == "yield"
    assert commands.parse_reaction("3", view) is None
    assert commands.parse_reaction("dance", view) is None


# ------------------------------------------------------------------ plain session

def test_a_scripted_plain_session_plays_five_turns_on_an_embedded_game():
    game = _game()
    start = game.world._turn
    session = Session(EmbeddedClient(game, PLAYER))
    script = ["look", "wait", "say Bram: good morning", "wait", "work burn charcoal", "wait", "quit"]
    out = io.StringIO()
    run_plain(session, io.StringIO("\n".join(script) + "\n"), out)
    text = out.getvalue()
    assert game.world._turn == start + 5
    assert text.count("Time passes.") + text.count("Last action:") + text.count("You say") >= 5
    assert "> wait" in text and text.rstrip().endswith("> quit")
    assert session.done


def test_plain_mode_ends_cleanly_at_the_end_of_input():
    session = Session(EmbeddedClient(_game(), PLAYER))
    out = io.StringIO()
    run_plain(session, io.StringIO(""), out)
    assert "at dawn" in out.getvalue() or "clear skies" in out.getvalue()
    assert not session.done


def test_a_contest_appears_as_a_reaction_and_a_word_answers_it():
    game = _game()
    taker = "Kester Furlong"
    game.world._move_actor_to(taker, game.world.actor_position(PLAYER))
    game.world.set_coin(PLAYER, 9.0)

    class Taker(DeterministicBackend):
        def decide(self, context):
            return ActorResponse(major_action=ProposedAction(
                "take", {"source": PLAYER, "kind": "coin", "amount": 3.0}))

    game.set_backend(taker, Taker(game.characters[taker]))
    for name in game.characters:
        if name not in (PLAYER, taker):
            game.set_backend(name, DeterministicBackend(game.characters[name]))
    session = Session(EmbeddedClient(game, PLAYER))
    out = session.line("wait")
    assert session.view.get("reaction"), "the holder should be asked to react"
    assert any("trying to take coin from you" in line for line in out)
    assert session.line("nonsense") == [narrate.words(PACK)["reaction_pick"]]
    answer = session.line("resist")
    assert answer[0] == "You hold on and resist."
    assert session.view.get("reaction") is None
    assert answer and not any(narrate.words(PACK)["reaction_pick"] == line for line in answer)
    assert game.contest_log and game.contest_log[-1]["reaction"] == "resist"


def test_a_client_error_is_shown_as_its_message_and_the_session_goes_on():
    class Stub(HttpClient):
        def react(self, choice):
            raise UnsupportedOverHttp("the server said no")

    client = Stub("http://127.0.0.1:9", PLAYER)
    client.view = lambda: dict(fixed_view(), reaction={"from": "x", "what": "y", "options": [
        {"choice": "resist", "words": "hold on"}]})
    session = Session(client)
    assert session.line("resist") == ["the server said no"]


# ------------------------------------------------------------------ connection

def test_the_client_classes_have_no_state_fetch_and_no_referee_option():
    for cls in (EmbeddedClient, HttpClient):
        names = " ".join(name for name in dir(cls) if not name.startswith("_")).lower()
        assert "state" not in names and "referee" not in names
    source = inspect.getsource(EmbeddedClient) + inspect.getsource(HttpClient)
    assert "/api/state" not in source and "referee" not in source.lower()


class _Recorder:
    def __init__(self):
        self.paths = []


def _serve_agent_mode():
    from bigville.server import BigvilleHandler, GameService
    recorder = _Recorder()

    class Recording(BigvilleHandler):
        def do_GET(self):  # noqa: N802
            recorder.paths.append(self.path)
            super().do_GET()

        def do_POST(self):  # noqa: N802
            recorder.paths.append(self.path)
            super().do_POST()

    Recording.service = GameService(scenario="town100", seed=305000, player=PLAYER, mode="agent")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Recording)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, recorder


def test_over_http_the_client_reads_the_view_and_takes_turns_and_never_asks_for_the_state():
    server, recorder = _serve_agent_mode()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        session = Session(HttpClient(url, PLAYER))
        assert session.view["mode"] == "agent" and session.view["actor"] == PLAYER
        session.line("wait")
        session.line("say Bram: good morning")
        session.line("look")
        client_paths = list(recorder.paths)
        with pytest.raises(urlrequest.HTTPError) as refused:  # a probe of our own, not the client
            urlrequest.urlopen(f"{url}/api/state")
        assert refused.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
    assert client_paths, "the client made requests"
    assert not [path for path in client_paths if path.startswith("/api/state")]
    assert {path.split("?")[0] for path in client_paths} <= {"/api/view", "/api/turn"}


def test_a_stub_server_records_only_view_and_turn_paths_from_the_client():
    seen = []
    view = fixed_view()
    from http.server import BaseHTTPRequestHandler

    class StubHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_GET(self):  # noqa: N802
            seen.append(self.path)
            body = json.dumps(view).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            seen.append(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            body = json.dumps({"status": "advanced", "view": view}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        session = Session(HttpClient(f"http://127.0.0.1:{server.server_port}", PLAYER))
        session.line("wait")
        session.line("look")
    finally:
        server.shutdown()
        server.server_close()
    assert seen and all(path.startswith(("/api/view", "/api/turn")) for path in seen)


# ------------------------------------------------------------------ front ends

class _FakeScreen:
    def __init__(self, height=24, width=80):
        self._size = (height, width)
        self.lines = {}
        self.refreshes = 0

    def getmaxyx(self):
        return self._size

    def erase(self):
        self.lines = {}

    def addnstr(self, y, x, text, n):
        self.lines[y] = text[:n]

    def refresh(self):
        self.refreshes += 1


def test_the_curses_loop_draws_and_takes_keys_on_a_fake_screen():
    curses = pytest.importorskip("curses")
    session = Session(EmbeddedClient(_game(), PLAYER))
    screen = _FakeScreen()
    keys = iter(["l", "\t", ":", "w", "a", "i", "t", "\n", "?", "q"])
    run_curses(session, screen, lambda: next(keys))
    assert session.done
    assert screen.refreshes >= 2
    assert screen.lines[0].startswith("Bigville")
    assert "Time passes." in session.log
    assert curses.KEY_LEFT is not None


def test_the_front_end_falls_back_to_plain_when_asked_or_not_on_a_terminal():
    assert choose_front_end(plain=True) == "plain"
    assert choose_front_end(stdout=io.StringIO()) == "plain"


def test_the_plain_front_end_runs_from_the_entry_point_and_the_snapshot_prints_a_screen(capsys):
    from bigville.tui.__main__ import main
    out = io.StringIO()
    code = main(["--player", PLAYER, "--snapshot"], stdout=out)
    lines = out.getvalue().splitlines()
    assert code == 0 and len(lines) == 24 and lines[0].startswith("Bigville")


def test_the_entry_point_has_no_referee_option(capsys):
    from bigville.tui.__main__ import main
    with pytest.raises(SystemExit):
        main(["--player", PLAYER, "--referee"])
    assert "unrecognized arguments" in capsys.readouterr().err


# ------------------------------------------------------------------ leak test

def test_no_rendered_line_carries_a_raw_number_or_a_referee_field_in_a_short_town100_run():
    game = _game()
    session = Session(EmbeddedClient(game, PLAYER))
    script = ["look", "wait", "say Bram: good morning", "wait", "work burn charcoal", "wait", "look", "wait"]
    transcript = io.StringIO()
    run_plain(session, io.StringIO("\n".join(script) + "\n"), transcript)
    screens = []
    for _ in range(2):
        screens.append(session.screen(80, 24))
        session.line("wait")
        screens.append(session.screen(80, 24))
    lines = [line for screen in screens for line in screen] + transcript.getvalue().splitlines()
    handles = [handle for screen in screens for handle in _handles(session.view)]
    leaks = _digit_leaks(lines, handles)
    assert leaks == [], f"a rendered line carries a digit: {leaks[:3]}"
    referee = load_pack(PACK)["AGENT_VIEW_REFEREE_ONLY"]
    text = "\n".join(lines)
    for name in referee:
        assert not re.search(rf"\b{re.escape(name)}\b", text), f"a referee-only name is on screen: {name}"
    assert game.world._turn > 0


def test_the_leak_check_itself_flags_a_number_and_allows_a_handle_and_a_menu_number():
    assert _digit_leaks(["energy: 42"], []) == ["energy: 42"]
    assert _digit_leaks(["1. burn charcoal"], []) == []
    assert _digit_leaks(["open chest_1 now"], ["chest_1"]) == []
    assert _digit_leaks(["hunger 0.5"], []) == ["hunger 0.5"]


def test_the_narration_templates_fill_without_a_digit_in_the_pack():
    table = narrate.words(PACK)
    for key, text in table.items():
        if isinstance(text, str) and key not in ("prompt",):
            literal = re.sub(r"\{[^{}]*\}", "", text)
            assert not DIGIT.search(literal), key


# ------------------------------------------------------------------ the server binds handles and delivers reactions

def _serve_with_service(player=PLAYER):
    from bigville.server import BigvilleHandler, GameService

    class Handler(BigvilleHandler):
        pass

    Handler.service = GameService(scenario="town100", seed=305000, player=player, mode="agent")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, Handler.service


def test_over_http_a_menu_row_is_bound_by_the_server_and_the_world_enacts_it():
    server, service = _serve_with_service()
    try:
        session = Session(HttpClient(f"http://127.0.0.1:{server.server_port}", PLAYER))
        row = next(r for r in session.view["can"] if r["action"] == "work")
        before = service.game.world._turn
        session.line("look")
        out = session.line(str([r["handle"] for r in session.view["can"]].index(row["handle"]) + 1))
    finally:
        server.shutdown()
        server.server_close()
    assert service.game.world._turn == before + 1
    assert service.game.last_responses[PLAYER].major_action.action == "work"
    assert service.game.last_responses[PLAYER].major_action.params.get("recipe")
    assert service.game.last_results[PLAYER] is True
    assert any("Last action: work" in line for line in out), out


def test_over_http_walking_to_a_known_place_sends_the_rows_destination():
    walker = "Verity Peaseblossom"                      # a resident who knows exact places at the start
    server, service = _serve_with_service(walker)
    try:
        session = Session(HttpClient(f"http://127.0.0.1:{server.server_port}", walker))
        walk = next((r for r in session.view["can"] if r["action"] == "walk"), None)
        assert walk is not None
        session.line("walk to " + walk["what"].replace("walk to the ", ""))
    finally:
        server.shutdown()
        server.server_close()
    proposal = service.game.last_responses[walker].major_action
    assert proposal.action == "move" and proposal.params.get("destination") is not None


def test_over_http_a_reaction_is_delivered_to_the_holder():
    server, service = _serve_with_service()
    game = service.game
    taker = "Kester Furlong"
    game.world._move_actor_to(taker, game.world.actor_position(PLAYER))
    game.world.set_coin(PLAYER, 9.0)

    class Taker(DeterministicBackend):
        def decide(self, context):
            return ActorResponse(major_action=ProposedAction(
                "take", {"source": PLAYER, "kind": "coin", "amount": 3.0}))

    game.set_backend(taker, Taker(game.characters[taker]))
    for name in game.characters:
        if name not in (PLAYER, taker):
            game.set_backend(name, DeterministicBackend(game.characters[name]))
    try:
        session = Session(HttpClient(f"http://127.0.0.1:{server.server_port}", PLAYER))
        out = session.line("wait")
        assert session.view.get("reaction"), out
        answer = session.line("resist")
    finally:
        server.shutdown()
        server.server_close()
    assert answer[0] == "You hold on and resist."
    assert game.contest_log and game.contest_log[-1]["reaction"] == "resist"


def test_the_server_refuses_a_bad_reply_and_a_reaction_nobody_is_waiting_for():
    server, service = _serve_with_service()
    try:
        url = f"http://127.0.0.1:{server.server_port}/api/turn"

        def post(body):
            req = urlrequest.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
            try:
                with urlrequest.urlopen(req) as response:
                    return response.status, json.loads(response.read())
            except urlrequest.HTTPError as exc:
                return exc.code, json.loads(exc.read())

        # Phase 071d: an unknown intensity word is the world's to refuse; a list is the malformed case.
        status, body = post({"reply": {"major_action": {"action": "attempt", "intensity": ["very very hard"]}}})
        assert status == 400 and "intensity must be" in body["error"]
        status, body = post({"reply": "work"})
        assert status == 400
        status, body = post({"reaction": "resist"})
        assert status == 400 and "no reaction is pending" in body["error"]
        status, body = post({"reply": {"major_action": None}})
        assert status == 200 and "view" in body and "state" not in body
    finally:
        server.shutdown()
        server.server_close()
