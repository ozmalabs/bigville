"""Phase 052: the agent view, the one limited interface.

The view is built by domains/agent_view.py from the whitelist in the pack (world/agent_view.json). These tests
hold the leak rules: every key is whitelisted for its section, no value is a raw number, and no referee-only
name appears. They also cover the words and the map patch, the knowledge and reach rules, determinism, the
simple backends' unchanged context, the HTTP routes (403 for /api/state in agent mode), and the self-test.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import sys
import threading
import unittest.mock as mock
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bigville.api import create_game                     # noqa: E402
from bigville.backends import ActorResponse, ProposedAction   # noqa: E402
from bigville.server import BigvilleHandler, GameService, main   # noqa: E402
from domains.agent_view_check import check_agent_view    # noqa: E402
from domains.lexicon import describe                     # noqa: E402
from domains.pack import load_pack                       # noqa: E402

SEED = 305000
PLAYER = "Verity Peaseblossom"
DIGIT = re.compile(r"\d")
PACK = load_pack("bigville")
WHITELIST = PACK["AGENT_VIEW_WHITELIST"]
REFEREE_ONLY = set(PACK["AGENT_VIEW_REFEREE_ONLY"])
GLYPHS = {spec["glyph"] for name, spec in PACK["MAP_GLYPHS"].items() if not name.startswith("_")}


# ------------------------------------------------------------------ the leak test
def _sections(view):
    """(section name, dict) for every dict the agent view carries, in the section its keys belong to."""
    out = [("top", view)]
    s = view["self"]
    out.append(("self", s))
    for name in ("persona", "body", "carrying"):
        if name in s:
            out.append((name, s[name]))
    out += [("knows", row) for row in s.get("knows", [])]
    out += [("places", row) for row in s.get("places", [])]
    out.append(("now", view["now"]))
    around = view["around"]
    out.append(("around", around))
    out += [("person", row) for row in around["people"]]
    out += [("heard", row) for row in around["heard"]]
    out += [("seen", row) for row in around["seen"]]
    if "map" in view:
        out.append(("map", {k: v for k, v in view["map"].items() if k != "legend"}))
    out += [("can", row) for row in view["can"]]
    out.append(("last", view["last"]))
    return out


def _leaves(obj, key=None):
    """(key, value) for every leaf, with the key it sits under."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "legend":
                continue
            yield from _leaves(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _leaves(v, key)
    else:
        yield key, obj


def assert_agent_safe(view):
    """The leak test. Fails on a key outside its section's whitelist, a referee-only key, a number of any kind,
    a digit in a phrase (a handle is the one exception), or a non-glyph in the map."""
    assert view["mode"] == "agent"
    assert "referee" not in view
    for section, mapping in _sections(view):
        allowed = set(WHITELIST[section])
        extra = set(mapping) - allowed
        assert not extra, f"section '{section}' carries keys outside its whitelist: {sorted(extra)}"
    for key, value in _leaves(view):
        assert not isinstance(value, (int, float)), f"a raw number under '{key}': {value!r}"
        if isinstance(value, str) and key != "handle":
            assert not DIGIT.search(value), f"a digit in the phrase under '{key}': {value!r}"
    for key in _all_keys(view):
        assert key not in REFEREE_ONLY, f"a referee-only field '{key}' is in the agent view"
    if "map" in view:
        assert set(view["map"]["legend"]) <= GLYPHS
        assert all(set(row) <= GLYPHS for row in view["map"]["rows"])


def test_the_leak_test_itself_catches_a_number_a_digit_and_a_referee_field(founder_game):
    clean = founder_game.agent_view(founder_game.player)
    for mutate, message in (
        (lambda v: v["self"]["body"].update(energy=42.0), "a raw number"),
        (lambda v: v["self"]["persona"].update(traits="aged 42"), "a digit"),
        (lambda v: v["self"].update(score="0.0"), "outside its whitelist"),
        (lambda v: v["self"]["persona"].update(score="fine"), "outside its whitelist"),
    ):
        broken = copy.deepcopy(clean)
        mutate(broken)
        with pytest.raises(AssertionError, match=message):
            assert_agent_safe(broken)


def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "legend":
                continue
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_keys(v)


@pytest.fixture(scope="module")
def founder_game():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


# ------------------------------------------------------------------ the self-test and its rules
def test_the_self_test_passes_for_bigville_and_for_the_hamlet_pack():
    for pack in ("bigville", "test_hamlet"):
        errors, warnings, info = [], [], []
        check_agent_view(pack, errors, warnings, info)
        assert errors == [] and warnings == [], (pack, errors, warnings)
        assert any("all agent view checks pass" in line for line in info)


def test_the_hamlet_pack_omits_the_fields_its_lexicon_cannot_word_and_says_so():
    errors, warnings, info = [], [], []
    check_agent_view("test_hamlet", errors, warnings, info)
    omitted = [line for line in info if "omits them in this pack" in line]
    assert omitted and "health" in omitted[0] and "weather" in omitted[0]


def _pack_copy(tmp_path, edit):
    """A copy of the bigville pack directory with `edit(agent_view_tables)` applied to its agent view file."""
    src = os.path.join(_ROOT, "packs", "bigville")
    dst = tmp_path / "pack"
    shutil.copytree(src, dst)
    path = dst / "world" / "agent_view.json"
    data = json.loads(path.read_text())
    edit(data["tables"])
    path.write_text(json.dumps(data))
    return str(dst)


def test_the_self_test_rejects_a_referee_name_whitelisted_for_the_agent(tmp_path):
    def edit(tables):
        tables["AGENT_VIEW_WHITELIST"]["self"].append("score")
    errors, warnings, info = [], [], []
    check_agent_view(_pack_copy(tmp_path, edit), errors, warnings, info)
    assert any("referee-only names" in e and "score" in e for e in errors)


def test_the_self_test_rejects_a_terrain_with_no_glyph(tmp_path):
    def edit(tables):
        del tables["MAP_GLYPHS"]["tree"]
    errors, warnings, info = [], [], []
    check_agent_view(_pack_copy(tmp_path, edit), errors, warnings, info)
    assert any("no glyph for" in e and "tree" in e for e in errors)


def test_the_self_test_rejects_a_digit_in_a_fixed_phrase(tmp_path):
    def edit(tables):
        tables["VIEW_WORDS"]["you"] = "you, aged 40"
    errors, warnings, info = [], [], []
    check_agent_view(_pack_copy(tmp_path, edit), errors, warnings, info)
    assert any("VIEW_WORDS[you]" in e and "digit" in e for e in errors)


# ------------------------------------------------------------------ the leak test on live views
def test_a_founding_resident_view_passes_the_leak_test(founder_game):
    view = founder_game.agent_view(founder_game.player)
    assert_agent_safe(view)
    assert view["actor"] == PLAYER
    assert set(view) <= set(WHITELIST["top"]) and "referee" not in view


def test_every_founding_resident_passes_the_leak_test(founder_game):
    for name in list(founder_game.characters)[:25]:
        assert_agent_safe(founder_game.agent_view(name))


def test_the_view_after_a_run_passes_the_leak_test():
    game = create_game(scenario="town100", seed=SEED, player=PLAYER)
    for _ in range(4):
        game.submit_player_response(ActorResponse())
        game.step()
    assert_agent_safe(game.agent_view(game.player))
    assert_agent_safe(game.agent_view("Alby Harkness"))


def test_numbers_are_in_the_words_and_never_as_numbers(founder_game):
    view = founder_game.agent_view(founder_game.player)
    body = view["self"]["body"]
    assert body["energy"] == describe("energy", founder_game.world.energy(PLAYER), "self")["phrase"]
    assert body["hunger"] == describe("hunger", 0.0, "self")["phrase"]
    assert all(not isinstance(v, (int, float)) for v in body.values())


def test_the_referee_mode_adds_numbers_and_the_agent_mode_does_not(founder_game):
    referee = founder_game.agent_view(founder_game.player, mode="referee")
    agent = founder_game.agent_view(founder_game.player, mode="agent")
    assert referee["mode"] == "referee" and "referee" in referee
    assert isinstance(referee["referee"]["body"]["stamina_reserve"], float)
    assert "referee" not in agent
    assert agent["self"] == referee["self"]
    with pytest.raises(ValueError, match="mode must be one of"):
        founder_game.agent_view(founder_game.player, mode="omniscient")


# ------------------------------------------------------------------ two people, two views
def _near(world, a, b):
    pa, pb = world.actor_position(a), world.actor_position(b)
    return pa is not None and pb is not None and \
        max(abs(pa[0] - pb[0]), abs(pa[1] - pb[1])) <= int(PACK["HEARING"]["sight_range"])


def test_two_residents_standing_together_get_different_views(founder_game):
    world = founder_game.world
    a = founder_game.player
    b = next(name for name in founder_game.characters if name != a and _near(world, a, name))
    va, vb = founder_game.agent_view(a), founder_game.agent_view(b)
    assert va["self"]["name"] == a and vb["self"]["name"] == b
    assert va["self"]["persona"] != vb["self"]["persona"]
    assert va["self"]["skills"] != vb["self"]["skills"] or va["self"]["job"] != vb["self"]["job"]


def test_a_stranger_is_a_description_and_a_known_resident_a_name():
    game = create_game(scenario="town100", seed=SEED, player=PLAYER)
    world = game.world
    view = game.agent_view(game.player)
    strangers = [p for p in view["around"]["people"] if "description" in p]
    assert strangers, "the founding town has strangers within sight"
    assert all("name" not in p and p["description"].startswith("a stranger (") for p in strangers)
    # A nearby resident the player has no record of is a stranger. Give the player an awareness record of
    # that person (the record shape Phase 019 writes), and the same person now appears by name.
    from bigville.character import MemoryRecord
    near = sorted(name for name in game.characters if name != game.player and _near(world, game.player, name))
    assert near
    target = near[0]
    assert target not in {p.get("name") for p in view["around"]["people"]}
    game.characters[game.player].memories.append(MemoryRecord(
        memory_id="test:known", kind="awareness", source="derived_prior", private=True,
        content={"item": f"resident:{target}", "type": "resident", "name": target,
                 "aware": True, "understands": 0.0, "basis": [], "source": "derived"}))
    after = game.agent_view(game.player)
    assert target in {p.get("name") for p in after["around"]["people"]}
    assert_agent_safe(after)


def test_the_view_is_deterministic_for_a_state_and_across_identical_sessions(founder_game):
    first = founder_game.agent_view(founder_game.player)
    assert first == founder_game.agent_view(founder_game.player)
    again = create_game(scenario="town100", seed=SEED, player=PLAYER)
    assert json.dumps(first, sort_keys=True) == json.dumps(again.agent_view(PLAYER), sort_keys=True)


# ------------------------------------------------------------------ what the character knows and can reach
def test_knowledge_entries_carry_a_gist_and_no_basis(founder_game):
    view = founder_game.agent_view(founder_game.player)
    knows = view["self"]["knows"]
    assert knows and len(knows) <= int(PACK["AGENT_VIEW_KNOWS_LIMIT"])
    assert all(set(row) == {"name", "understood", "gist"} for row in knows)
    assert "basis" not in json.dumps(view)


def test_moves_are_offered_only_to_places_the_resident_knows(founder_game):
    game = founder_game
    view = game.agent_view(game.player)
    from domains.agent_view import _known_positions
    known = _known_positions(game.characters[game.player], "bigville")
    moves = [a for a in game.world.actor_affordances(game.player) if a["action"] == "move"]
    offered = [row for row in view["can"] if row["action"] == "walk"]
    assert offered and len(offered) <= len(moves)
    handles = {a["target"] for a in moves if tuple(a["destination"]) in known}
    assert {row["handle"] for row in offered} == handles
    assert all(row["what"].startswith("walk to the ") for row in offered)
    assert all("destination" not in row for row in view["can"])


def test_the_map_patch_is_centred_within_sight_and_shows_terrain_only(founder_game):
    view = founder_game.agent_view(founder_game.player)
    sight = int(PACK["HEARING"]["sight_range"])
    rows = view["map"]["rows"]
    assert len(rows) == 2 * sight + 1 and all(len(row) == 2 * sight + 1 for row in rows)
    assert sum(row.count("@") for row in rows) == 1
    assert rows[sight][sight] == "@"
    assert set(view["map"]["legend"]) <= GLYPHS and view["map"]["legend"]["@"] == "you"


def test_last_quotes_the_outcome_and_the_refusal_meaning():
    game = create_game(scenario="town100", seed=SEED, player=PLAYER)
    game.submit_player_response(ActorResponse(major_action=ProposedAction("levitate", {})))
    game.step()
    outcome = game.world.last_outcome(game.player)
    view = game.agent_view(game.player)
    assert outcome is not None
    if outcome["applied"]:
        assert view["last"]["outcome"] == PACK["VIEW_WORDS"]["done"]
    else:
        assert view["last"]["outcome"] == PACK["VIEW_WORDS"]["not_done"]
        assert view["last"]["reason"] == PACK["REFUSAL_REASONS"][outcome["reason"]]["description"]
    assert_agent_safe(view)


def test_building_the_view_leaves_the_practice_window_for_the_backend_unchanged():
    game = create_game(scenario="town100", seed=SEED, player=PLAYER)
    before = dict(game._published_practice)
    game.agent_view(game.player)
    assert game._published_practice == before


def test_a_simple_backend_keeps_its_raw_context():
    game = create_game(scenario="town100", seed=SEED, player=PLAYER)
    npc = next(name for name in game.characters if name != PLAYER)
    context = game._context(npc)
    assert context.agent_view is None
    assert {"terrain_movement", "nearby_residents", "turn_state", "calendar"} <= set(context.observations)


def test_the_hamlet_pack_gives_a_view_with_its_own_words():
    from worlds.bigville_world import BigvilleWorld
    from bigville.game import BigvilleGame
    world = BigvilleWorld(data_pack="test_hamlet")
    world.add_actor("Bram Smith", role="baker")
    game = BigvilleGame(world, player="Bram Smith")
    view = game.agent_view("Bram Smith")
    assert view["self"]["job"] == "baker"
    assert "health" not in view["self"]["body"]           # the hamlet lexicon has no health words
    assert "energy" in view["self"]["body"]
    assert_agent_safe(view)


# ------------------------------------------------------------------ the server
@pytest.fixture
def http_server():
    servers = []

    def start(mode):
        service = GameService(scenario="town100", seed=SEED, player=PLAYER, mode=mode)

        class Handler(BigvilleHandler):
            pass

        Handler.service = service
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_port}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _get(url):
    try:
        with urllib.request.urlopen(url) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post(url, payload):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request) as response:
        return response.status, json.loads(response.read())


def test_agent_mode_refuses_the_state_and_serves_the_view(http_server):
    base = http_server("agent")
    status, body = _get(base + "/api/state")
    assert status == 403 and "api/view" in body["error"]
    status, view = _get(base + "/api/view")
    assert status == 200 and view["actor"] == PLAYER
    assert_agent_safe(view)
    status, _ = _get(base + "/api/view?actor=Nobody%20Here")
    assert status == 404


def test_agent_mode_turn_answers_with_the_view_not_the_snapshot(http_server):
    base = http_server("agent")
    status, result = _post(base + "/api/turn", {})
    assert status == 200
    assert "state" not in result
    assert_agent_safe(result["view"])


def test_referee_mode_serves_the_state_and_the_view(http_server):
    base = http_server("referee")
    status, state = _get(base + "/api/state")
    assert status == 200 and state["schema"] == "bigville/game/1"
    status, view = _get(base + "/api/view")
    assert status == 200 and view["mode"] == "agent"


def test_the_service_refuses_agent_mode_without_a_player():
    with pytest.raises(ValueError, match="agent mode needs a player"):
        GameService(scenario="town100", seed=SEED, player=None, mode="agent")


def test_the_command_line_is_agent_mode_when_a_player_is_named():
    with mock.patch("bigville.server.serve") as serve:
        main(["--player", PLAYER])
        assert serve.call_args.kwargs["mode"] == "agent"
    with mock.patch("bigville.server.serve") as serve:
        main(["--player", PLAYER, "--referee"])
        assert serve.call_args.kwargs["mode"] == "referee"
    with mock.patch("bigville.server.serve") as serve:
        main([])
        assert serve.call_args.kwargs["mode"] == "referee"
