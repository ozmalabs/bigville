"""Phase 053: the fog of the map, in three levels (domains/map_memory.py).

Covers the acceptance items of the brief: a farm labourer knows the fields in full and the tannery vaguely; a new
incomer does not know where the quarry is; walking reveals the cells in sight and they stay known; an old
observation is marked stale; a place told by speech becomes level 1; a level-0 target is absent from `can` and a
level-1 one is offered as 'toward'; a simple resident's affordances and view are unchanged; the memory survives a
checkpoint; the three levels render differently; replay is deterministic.
"""
from __future__ import annotations

import copy
import json
import re

import pytest

from bigville.api import create_game
from bigville.backends import ActorResponse, ProposedAction
from bigville.character import CharacterDefinition, MemoryRecord
from bigville.tui import render as tui_render
from domains import map_memory as mm
from domains.fog_check import check_fog
from domains.pack import load_pack

SEED = 305000
PLAYER = "Alby Marsh"           # a human resident (fogged), who knows the market, the church and the mill
FARMER = "Thaddeus Ramskin"     # a farmer on the farm routine: the fields are exact, the tannery rough
INCOMER = "Thaddeus Puddifoot"  # a newcomer of one year: the quarry (stone) is unknown


class _Fogged:
    """A stand-in backend: it only carries the flag, and makes no decisions."""
    fogged = True
    wants_agent_view = False


def _town():
    return create_game(scenario="town100", seed=SEED, player=PLAYER)


def _fog(game, name):
    game.backends[name] = _Fogged()
    return game


def _content(game, name):
    return mm.ensure_map(game, name)


def _label_words(view):
    return [label["word"] for label in view["map"].get("labels", [])]


@pytest.fixture
def every_label(monkeypatch):
    """The view lists the nearest known places, five at most (FOG_RULES.max_labels, which keeps the map within the
    prompt packet's cap). A test that looks for a far place lifts the cap, and nothing else."""
    original = mm._rules

    def lifted(world):
        return {**original(world), "max_labels": 999}

    monkeypatch.setattr(mm, "_rules", lifted)


def _stone_cell(game):
    return mm._registry(game)["stone"][0]


def _newcomer(game):
    """The one-year incomer, without the quarry on their routine. The seed's only one-year incomer is a labourer,
    whose routine is the quarry (Phase 019 makes that place exact for them), so this removes that one derived record.
    Phase 019's newcomer knows nothing of the quarry: no place, no cell, and no label."""
    character = game.characters[INCOMER]
    character.memories = [m for m in character.memories
                          if not (isinstance(m.content, dict) and m.content.get("item") == "place:stone")]
    return game


def test_the_fog_self_test_passes_for_both_packs():
    for pack in ("bigville", "test_hamlet"):
        errors, warnings, info = [], [], []
        check_fog(pack, errors, warnings, info)
        assert errors == [] and warnings == [], (pack, errors, warnings)
        assert info and "all fog checks pass" in info[0]


def test_the_farm_labourer_knows_the_fields_in_full_and_the_tannery_only_vaguely():
    game = _fog(_town(), FARMER)
    world = game.world
    assert world.eng.node(world._actors[FARMER])["attrs"]["role"] == "farmer"
    content = _content(game, FARMER)
    registry = mm._registry(game)
    assert content["places"]["field"]["level"] == mm.LEVEL_FULL
    assert registry["field"], "the founding town has fields"
    for cell in registry["field"]:
        assert mm._key(cell) in content["cells"], "every field is seen in full"
    assert content["places"]["tannery"]["level"] == mm.LEVEL_VAGUE
    assert "cells" not in content["places"]["tannery"], "a vague place carries no cell"
    view = game.agent_view(FARMER)
    tannery = [word for word in _label_words(view) if "the tannery" in word]
    assert tannery and "roughly" in tannery[0]


def test_a_new_incomer_does_not_know_where_the_quarry_is():
    game = _newcomer(_fog(_town(), INCOMER))
    content = _content(game, INCOMER)
    assert "stone" not in content["places"], "a one-year incomer holds no place for the stone deposit"
    stone = _stone_cell(game)
    assert mm.can_words(game, INCOMER, stone) is None
    view = game.agent_view(INCOMER)
    assert not any("quarry" in word for word in _label_words(view))
    assert all("quarry" not in row["what"] for row in view["can"])
    assert mm.route_plan(game, INCOMER, {"action": "move", "toward": "the quarry"}) == {"action": "move"}


def test_a_newcomer_knows_far_fewer_places_than_a_farm_labourer():
    game = _fog(_fog(_town(), FARMER), INCOMER)
    known = {name: sum(1 for entry in _content(game, name)["places"].values() if entry["level"] >= 1)
             for name in (FARMER, INCOMER)}
    assert known[INCOMER] < known[FARMER], known


def test_walking_reveals_the_cells_in_sight_and_they_stay_known():
    game = _town()
    world = game.world
    content = _content(game, PLAYER)
    before = set(content["cells"])
    start = world.actor_position(PLAYER)
    for direction in ("north", "north", "north"):
        game.submit_player_response(ActorResponse(major_action=ProposedAction("move", {"toward": direction})))
        assert game.step()["status"] == "advanced"
    here = world.actor_position(PLAYER)
    assert here != start, "the walk moved the resident"
    sight = int(load_pack("bigville")["HEARING"]["sight_range"])
    width, height = len(world._map_grid[0]), len(world._map_grid)
    for dy in range(-sight, sight + 1):
        for dx in range(-sight, sight + 1):
            x, y = here[0] + dx, here[1] + dy
            if 0 <= x < width and 0 <= y < height:
                assert f"{x},{y}" in content["cells"]
                assert content["cells"][f"{x},{y}"]["seen"] == int(world._turn)
    assert before <= set(content["cells"]), "no known cell is forgotten"


def test_an_old_observation_is_marked_as_remembered(every_label):
    game = _town()
    content = _content(game, PLAYER)
    world = game.world
    here = world.actor_position(PLAYER)
    sight = int(load_pack("bigville")["HEARING"]["sight_range"])
    far = [name for name, entry in content["places"].items() if entry["level"] == mm.LEVEL_FULL
           and all(mm._chebyshev(here, cell) > sight for cell in mm._cells_of(game, content, name))]
    assert far, "the player holds an exact place out of sight"
    shown = {name: mm._word(name, world.data_pack) for name in far}
    name = next(n for n in far if any(label["word"].startswith(shown[n])
                                     for label in mm.map_section(game, PLAYER)["labels"]))
    content["places"][name]["seen"] = -10_000
    word = shown[name]
    marked = [label["word"] for label in mm.map_section(game, PLAYER)["labels"]
              if label["word"].startswith(word)]
    assert marked and "as you remember it, a long time ago" in marked[0]
    content["places"][name]["seen"] = int(world._turn)
    fresh = [label["word"] for label in mm.map_section(game, PLAYER)["labels"]
             if label["word"].startswith(word)]
    assert fresh and "as you remember it" not in fresh[0]


def test_a_place_told_by_speech_becomes_level_1_and_is_offered_toward(every_label):
    game = _newcomer(_fog(_town(), INCOMER))
    content = _content(game, INCOMER)
    stone = _stone_cell(game)
    assert "stone" not in content["places"]
    game.characters[INCOMER].memories.append(MemoryRecord(
        memory_id="told:quarry:1", content={"text": "the quarry lies south of the mill"},
        kind="place_belief", source="someone", private=True))
    mm.refresh(game, INCOMER)
    assert content["places"]["stone"]["level"] == mm.LEVEL_VAGUE
    assert mm.can_words(game, INCOMER, stone) == ("toward", "quarry")
    assert any("quarry" in word for word in _label_words(game.agent_view(INCOMER)))
    mm.refresh(game, INCOMER)
    assert len([m for m in game.characters[INCOMER].memories if m.memory_id == "told:quarry:1"]) == 1


def test_a_place_told_with_a_position_becomes_level_2():
    game = _newcomer(_fog(_town(), INCOMER))
    content = _content(game, INCOMER)
    stone = _stone_cell(game)
    game.characters[INCOMER].memories.append(MemoryRecord(
        memory_id="told:quarry:2", content={"text": "the quarry", "position": list(stone)},
        kind="place_belief", source="someone", private=True))
    mm.refresh(game, INCOMER)
    assert content["places"]["stone"]["level"] == mm.LEVEL_FULL
    assert mm.can_words(game, INCOMER, stone) == ("to", "quarry")


def test_a_level_0_target_is_absent_from_can_and_a_level_1_one_is_offered_toward():
    game = _town()
    view = game.agent_view(PLAYER)
    whats = [row["what"] for row in view["can"]]
    assert "walk toward the market" in whats, "the market is public: level 1 for everyone"
    _newcomer(_fog(game, INCOMER))
    incomer = game.agent_view(INCOMER)
    assert all("quarry" not in row["what"] for row in incomer["can"])


def test_a_move_to_ground_the_resident_does_not_know_is_refused():
    game = _newcomer(_fog(_town(), INCOMER))
    content = _content(game, INCOMER)
    stone = _stone_cell(game)
    assert not mm.known_cell(game, content, stone)
    assert mm.route_plan(game, INCOMER, {"action": "move", "destination": stone}) == {"action": "move"}
    assert mm.route_plan(game, INCOMER, {"action": "move", "destination": [stone[0], stone[1]]}) == \
        {"action": "move"}


def test_toward_becomes_a_destination_the_world_walks_to():
    game = _town()
    world = game.world
    content = _content(game, PLAYER)
    here = world.actor_position(PLAYER)
    assert mm._known(content, "mill") >= mm.LEVEL_VAGUE
    plan = mm.route_plan(game, PLAYER, {"action": "move", "toward": "the mill"})
    assert plan["destination"] in set(mm._registry(game)["mill"])
    north = mm.route_plan(game, PLAYER, {"action": "move", "toward": "north"})
    assert north["destination"] is not None and north["destination"][1] < here[1]
    assert north["destination"] != here
    assert mm.route_plan(game, PLAYER, {"action": "move", "toward": "nowhere known"}) == {"action": "move"}


def test_a_simple_resident_is_not_fogged_and_keeps_the_patch_view():
    game = create_game(scenario="town100", seed=SEED, autonomous=True)
    name = next(iter(game.characters))
    assert not mm.is_fogged(game, name)
    assert getattr(game.backends[name], "fogged", False) is False
    view = game.agent_view(name)
    sight = int(load_pack("bigville")["HEARING"]["sight_range"])
    assert view["map"]["caption"] == load_pack("bigville")["VIEW_WORDS"]["map_level"]
    assert len(view["map"]["rows"]) == 2 * sight + 1
    assert "labels" not in view["map"]
    plan = {"action": "move", "destination": (1, 1)}
    assert mm.route_plan(game, name, plan) is plan
    for _ in range(3):
        game.step()
    assert game.agent_view(name)["map"]["caption"] == load_pack("bigville")["VIEW_WORDS"]["map_level"]
    assert not any(m.kind == "map_memory" for c in game.characters.values() for m in c.memories)


def test_the_map_is_one_memory_per_resident_and_survives_a_character_round_trip():
    game = _town()
    mm.refresh(game, PLAYER)
    mm.refresh(game, PLAYER)
    records = [m for m in game.characters[PLAYER].memories if m.kind == "map_memory"]
    assert len(records) == 1
    data = json.loads(json.dumps(game.characters[PLAYER].to_dict()))
    back = CharacterDefinition.from_dict(data)
    kept = [m for m in back.memories if m.kind == "map_memory"]
    assert len(kept) == 1 and kept[0].content == json.loads(json.dumps(records[0].content))


def test_the_map_survives_a_game_checkpoint(tmp_path):
    gp = pytest.importorskip("bigville.game_persistence")
    game = _town()
    mm.refresh(game, PLAYER)
    expected = json.loads(json.dumps(mm.ensure_map(game, PLAYER)))
    gp.save_game_checkpoint(game, tmp_path / "ck")
    restored = gp.load_game_checkpoint(tmp_path / "ck", llm_log=False)
    kept = [m for m in restored.characters[PLAYER].memories if m.kind == "map_memory"]
    assert len(kept) == 1
    assert json.loads(json.dumps(kept[0].content)) == expected


def test_the_prompt_selection_never_sends_the_map_record():
    from bigville.backends.prompts import PromptBuilder, select_knowledge
    from bigville.backends.protocol import ActorContext
    game = _town()
    mm.refresh(game, PLAYER)
    character = game.characters[PLAYER]
    context = ActorContext(character=character, turn=0, observations={}, affordances=[])
    _, memories, _, _ = select_knowledge(character, context, PromptBuilder().selection)
    assert all(entry["kind"] != "map_memory" for entry in memories)


def _three_views(game, name):
    view = game.agent_view(name)
    pack = load_pack("bigville")
    full = view
    vague = copy.deepcopy(view)
    vague["map"] = {"level": "vague", "caption": pack["VIEW_WORDS"]["map_vague"], "rows": [], "legend": {},
                    "labels": [{"glyph": "A", "word": "the mill, roughly a walk north"}]}
    hidden = copy.deepcopy(view)
    hidden["map"] = {"level": "hidden", "caption": pack["VIEW_WORDS"]["map_hidden"], "rows": [], "legend": {},
                     "labels": []}
    return full, vague, hidden


def test_the_three_levels_render_differently():
    game = _town()
    full, vague, hidden = _three_views(game, PLAYER)
    lines = {}
    for name, view in (("full", full), ("vague", vague), ("hidden", hidden)):
        rendered = tui_render._map_rows(view, "bigville", 12, 40)
        lines[name] = [line.rstrip() for line in rendered]
    assert lines["full"] != lines["vague"] != lines["hidden"] != lines["full"]
    assert any("@" in line for line in lines["full"])
    assert not any("@" in line for line in lines["vague"])
    assert any("roughly a walk north" in line for line in lines["vague"])
    assert not any("roughly" in line for line in lines["hidden"])
    assert any(ch != " " for line in lines["full"] for ch in line)


def test_the_view_map_keys_are_whitelisted_and_carry_no_digits():
    game = _town()
    pack = load_pack("bigville")
    for name in (PLAYER, FARMER, INCOMER):
        if name != PLAYER:
            _fog(game, name)
        view = game.agent_view(name)
        assert set(view["map"]) <= set(pack["AGENT_VIEW_WHITELIST"]["map"])
        for label in view["map"]["labels"]:
            assert set(label) == {"glyph", "word"}
            assert not re.search(r"\d", label["word"])


def test_the_map_section_fits_the_prompt_packet_cap():
    """The packet measures the whole `map` section against PROMPT_PACKET.caps.map (900 characters)."""
    game = _town()
    cap = int(load_pack("bigville")["PROMPT_PACKET"]["caps"]["map"])
    for name in (PLAYER, FARMER):
        if name != PLAYER:
            _fog(game, name)
        assert len(json.dumps(game.agent_view(name)["map"], ensure_ascii=False, sort_keys=True)) <= cap


def test_a_window_on_ground_nobody_holds_is_hidden():
    game = _town()
    content = _content(game, PLAYER)
    far = (0, 0)
    assert not mm.known_cell(game, content, far)
    section = mm.map_section(game, PLAYER, centre=far, radius=1)
    assert section["level"] == "hidden" and section["rows"] == [] and section["labels"] == []
    assert section["caption"] == load_pack("bigville")["VIEW_WORDS"]["map_hidden"]


def test_the_referee_view_overlays_the_true_patch_for_a_fogged_resident():
    game = _town()
    view = game.agent_view(PLAYER, mode="referee")
    true_map = view["referee"]["true_map"]
    assert len(true_map) == len(view["map"]["rows"])
    simple = create_game(scenario="town100", seed=SEED, autonomous=True)
    name = next(iter(simple.characters))
    assert "true_map" not in simple.agent_view(name, mode="referee").get("referee", {})


def test_replay_is_deterministic():
    def run():
        game = _town()
        views = []
        for direction in ("north", "east", "the mill", "north"):
            game.submit_player_response(ActorResponse(major_action=ProposedAction("move", {"toward": direction})))
            game.step()
            views.append(json.dumps(game.agent_view(PLAYER), sort_keys=True))
        return views, json.dumps(mm.ensure_map(game, PLAYER), sort_keys=True)

    assert run() == run()
