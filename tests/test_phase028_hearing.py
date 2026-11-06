"""Phase 028: loudness is the hearing radius; hearing is not witnessing.

Content is delivered to the target (or to every listener for a broadcast) within the effective loudness,
in Chebyshev cells, and not through a hear occluder. A resident with sight of the speaker witnesses that a
speech act happened, and never its content. Seed: seeds/bigville_loud_comm.json.

Most distance tests clear the map grid (``_map_grid = None``), so distance alone decides. The occlusion tests
use the default founding map, which has tree cells (occluders) in it.
"""
from __future__ import annotations

from bigville.backends import ActorResponse, DeterministicBackend
from bigville.game import BigvilleGame
from worlds.bigville_sim_world import TILE_NAME, TREE
from worlds.bigville_world import BigvilleWorld


def _open_world(**kwargs):
    """A world whose map has no occluders: distance alone decides who hears and sees."""
    world = BigvilleWorld(autonomous_actors=False, **kwargs)
    world._map_grid = None
    return world


def _place(world, name, cell, role="hand"):
    if name not in world._actors:
        world.add_actor(name, role=role, home_cell=cell)
    world._actor_positions[name] = cell


def _speak(world, speaker, target, loudness, content="Hello there."):
    return world.speak(speaker, target, content, loudness=loudness)


def _heard(world, actor):
    return [item["text"] for item in world.heard_utterances(actor)]


def test_loudness_five_is_heard_at_five_cells_and_not_at_six():
    world = _open_world()
    _place(world, "Ada", (0, 0))
    _place(world, "Ben", (5, 0))
    _place(world, "Cy", (6, 0))
    _speak(world, "Ada", "Ben", loudness=5.0, content="Five cells.")
    _speak(world, "Ada", "Cy", loudness=5.0, content="Six cells.")
    assert _heard(world, "Ben") == ["Five cells."]
    assert _heard(world, "Cy") == []


def test_louder_speech_carries_farther_and_a_targeted_utterance_needs_no_shared_cell():
    world = _open_world()
    _place(world, "Ada", (0, 0))
    _place(world, "Ben", (3, 0))
    _speak(world, "Ada", "Ben", loudness=2.0, content="Quiet.")
    assert _heard(world, "Ben") == []
    _speak(world, "Ada", "Ben", loudness=3.0, content="Loud enough.")
    assert _heard(world, "Ben") == ["Loud enough."]


def test_ordinary_speech_carries_one_cell_so_an_adjacent_target_hears_and_a_distant_one_does_not():
    world = _open_world()
    _place(world, "Ada", (0, 0))
    _place(world, "Ben", (1, 0))
    _place(world, "Cy", (2, 0))
    _speak(world, "Ada", "Ben", loudness=1.0, content="Next door.")
    _speak(world, "Ada", "Cy", loudness=1.0, content="Two doors.")
    assert _heard(world, "Ben") == ["Next door."]
    assert _heard(world, "Cy") == []


def test_broadcast_reaches_every_listener_within_the_radius_and_no_further():
    world = _open_world()
    _place(world, "Ada", (0, 0))
    _place(world, "Ben", (1, 0))
    _place(world, "Cy", (4, 0))
    _place(world, "Dee", (9, 0))
    utterance = _speak(world, "Ada", None, loudness=4.0, content="Everyone.")
    assert _heard(world, "Ben") == ["Everyone."]
    assert _heard(world, "Cy") == ["Everyone."]
    assert _heard(world, "Dee") == []
    deliveries = world.eng.node(utterance)["attrs"]["deliveries"]
    assert "Dee" not in deliveries, "a resident beyond hearing and sight gets no record at all"


def test_loudness_is_clamped_to_the_table_maximum_and_a_bad_value_is_normal_speech():
    world = _open_world()
    maximum = float(world.E.HEARING["max_loudness"])
    normal = float(world.E.HEARING["normal_loudness"])
    assert world.speech_radius(maximum * 10) == maximum
    assert world.speech_radius(-3.0) == 0.0
    assert world.speech_radius(float("nan")) == normal
    assert world.speech_radius(float("inf")) == maximum
    assert world.speech_radius(5.0) == 5.0


def test_with_the_loudness_switch_off_a_flat_radius_applies_whatever_is_chosen():
    world = _open_world(physical_subsystems={"loudness": False})
    flat = int(world.E.HEARING["flat_radius"])
    _place(world, "Ada", (0, 0))
    _place(world, "Near", (flat, 0))
    _place(world, "Far", (flat + 1, 0))
    assert world.speech_radius(1.0) == float(flat)
    _speak(world, "Ada", "Near", loudness=1.0, content="Whisper.")
    _speak(world, "Ada", "Far", loudness=1.0, content="Whisper again.")
    assert _heard(world, "Near") == ["Whisper."]
    assert _heard(world, "Far") == []


def test_a_wall_that_muffles_hearing_stops_content_but_the_witnessed_act_still_reaches_a_sighted_listener(
        monkeypatch):
    """The seed's split: a hear occluder stops content; with sight clear, the act is still witnessed.

    The map has no tile that stops sound and passes light, so the split is set here in the pack table: trees
    muffle hearing only. The same geometry with the real tables is in the next test.
    """
    world = BigvilleWorld(autonomous_actors=False)
    grid = world._map_grid
    tree = next((x, y) for y, row in enumerate(grid) for x, tile in enumerate(row) if tile == TREE
                and 0 < x < len(row) - 1)
    left, right = (tree[0] - 1, tree[1]), (tree[0] + 1, tree[1])
    assert TILE_NAME[TREE] == "tree"
    monkeypatch.setitem(world.E.HEARING, "hear_occluders", ["tree"])
    monkeypatch.setitem(world.E.HEARING, "sight_occluders", [])
    _place(world, "Ada", left)
    _place(world, "Ben", right)
    utterance = _speak(world, "Ada", "Ben", loudness=5.0, content="Behind the tree.")
    assert _heard(world, "Ben") == []
    assert world.eng.node(utterance)["attrs"]["deliveries"]["Ben"] == {"heard": 0.0, "seen": 1.0}


def test_on_the_real_map_a_tree_between_two_residents_stops_both_content_and_sight():
    world = BigvilleWorld(autonomous_actors=False)
    grid = world._map_grid
    tree = next((x, y) for y, row in enumerate(grid) for x, tile in enumerate(row) if tile == TREE
                and 0 < x < len(row) - 1)
    _place(world, "Ada", (tree[0] - 1, tree[1]))
    _place(world, "Ben", (tree[0] + 1, tree[1]))
    utterance = _speak(world, "Ada", "Ben", loudness=5.0, content="Behind the tree.")
    assert _heard(world, "Ben") == []
    assert "Ben" not in world.eng.node(utterance)["attrs"]["deliveries"]
    status = world.speech_occlusion_status()
    assert status["map_installed"] and status["sight_occluder_cells"] > 0
    assert status["hear_occluder_cells"] == status["sight_occluder_cells"]


def test_without_occluder_cells_distance_alone_decides():
    world = _open_world()
    assert world.speech_occlusion_status() == {"map_installed": False, "sight_occluder_cells": 0,
                                               "hear_occluder_cells": 0}
    _place(world, "Ada", (0, 0))
    _place(world, "Ben", (1, 0))
    _speak(world, "Ada", "Ben", loudness=1.0, content="Adjacent.")
    assert _heard(world, "Ben") == ["Adjacent."]


class _Quiet(DeterministicBackend):
    kind = "simple"

    def decide(self, context):
        return ActorResponse()


class _SpeaksOnce(DeterministicBackend):
    kind = "simple"

    def __init__(self, character, *, target, loudness):
        super().__init__(character)
        self.target, self.loudness, self.done = target, loudness, False

    def decide(self, context):
        if self.done:
            return ActorResponse()
        self.done = True
        return ActorResponse(utterances=[{"target": self.target, "text": "Secret words.",
                                          "raw": {"act": "inform"}, "loudness": self.loudness}])


def _game(loudness=1.0):
    world = _open_world()
    _place(world, "Ada", (0, 0))
    _place(world, "Ben", (5, 0))      # target: five cells away, beyond normal speech
    _place(world, "Cy", (3, 0))       # witness: three cells from the speaker, sees the target too
    _place(world, "Dee", (9, 0))      # beyond sight range (7)
    game = BigvilleGame(world, autonomous=True, ticks_per_period=None)
    game.set_backend("Ada", _SpeaksOnce(game.characters["Ada"], target="Ben", loudness=loudness))
    for name in ("Ben", "Cy", "Dee"):
        game.set_backend(name, _Quiet(game.characters[name]))
    return world, game


def test_a_witness_learns_that_speech_happened_and_never_what_was_said():
    world, game = _game(loudness=1.0)
    game.step()
    seen = game._context("Cy").observations["physical_events"]
    assert seen == [{"actor": "Ada", "action": "spoke", "turn": int(world._turn),
                     "expires_turn": int(world._turn), "target": "Ben"}]
    assert "Secret words." not in repr(seen)
    assert _heard(world, "Cy") == [] and _heard(world, "Ben") == []


def test_the_target_is_named_to_a_witness_only_when_that_witness_can_see_the_target():
    world, game = _game(loudness=1.0)
    _place(world, "Dee", (12, 0))     # out of sight of the speaker, and far from the target
    game.step()
    events = game._context("Dee").observations["physical_events"]
    assert events == []
    seen_by_ben = game._context("Ben").observations["physical_events"]
    assert seen_by_ben == [{"actor": "Ada", "action": "spoke", "turn": int(world._turn),
                            "expires_turn": int(world._turn)}], "the target sees the act but not itself as target"


def test_the_speaker_gets_no_record_of_the_act_and_events_expire_after_one_decision():
    world, game = _game(loudness=1.0)
    game.step()
    assert game._context("Ada").observations["physical_events"] == []
    game.step()
    assert game._context("Cy").observations["physical_events"] == []


def test_each_listener_has_a_delivery_record_heard_or_witnessed():
    world, game = _game(loudness=5.0)
    game.step()
    utterance = list(world._utterances.values())[-1]
    deliveries = world.eng.node(utterance)["attrs"]["deliveries"]
    assert deliveries["Ben"]["heard"] == 1.0 and deliveries["Ben"]["seen"] == 1.0
    assert deliveries["Cy"] == {"heard": 0.0, "seen": 1.0, "target_seen": 1.0}
    assert "Dee" not in deliveries
    assert _heard(world, "Ben") == ["Secret words."]
    assert _heard(world, "Cy") == []


def test_the_real_map_has_tree_and_wall_cells_for_the_occluder_tables():
    world = BigvilleWorld(autonomous_actors=False)
    names = {TILE_NAME[code] for row in world._map_grid for code in set(row) if code in TILE_NAME}
    assert {"tree", "wall"} <= names
    assert "tree" in world.E.HEARING["hear_occluders"] and "wall" in world.E.HEARING["sight_occluders"]
