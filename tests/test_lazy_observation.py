"""LA03: the observation model, derived indices and the lazy context.

The observation publishes entities and capabilities, never a legal menu.  The
tests compare it with the existing brute-force reads, exercise the object and
utterance indices (including the rebuild fallback when the location mapping is
replaced), and show that lazy ``_context`` never calls the exhaustive builder.
Menu-mode context and the TG01 trace digest stay unchanged.
"""
from __future__ import annotations

import json

from bigville.api import create_game, create_world
from bigville.backends.protocol import ActorContinuation
from bigville.tick_trace import TurnTrace, semantic_step_trace
from worlds.bigville_world import _PhysicalObjectLocations


SMALL_SCENARIO = {
    "id": "la03_observation_room",
    "name": "LA03 observation room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [2, 2]},
        {"name": "Cy", "role": "farmer", "backend": "simple", "home_cell": [3, 3]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [], "laws": [], "policies": [], "charters": [],
    "physical_objects": [
        {"id": "box", "name": "box", "kind": "box", "location": "table", "open": False},
        {"id": "apple", "name": "apple", "kind": "apple", "location": "table"},
        {"id": "hammer", "name": "hammer", "kind": "hammer", "location": "world"},
        {"id": "coin", "name": "coin", "kind": "coin", "contains": "box"},
    ],
}

# The exact LA01/TG01 scenario used by the LA02 digest oracle.
MENU_SCENARIO = {
    "id": "la01_mode_room",
    "name": "LA01 mode room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [2, 2]},
        {"name": "Cy", "role": "farmer", "backend": "simple", "home_cell": [3, 3]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [], "laws": [], "policies": [], "charters": [],
}
MENU_DIGEST_AT_LA01 = "a89d51d00f96547d2c86e19e84784c2e61eb2b9f1c1da3f36fbff1e0d3b6282f"


def _world():
    return create_world(scenario=SMALL_SCENARIO, seed=305000)


def _game(mode="lazy"):
    return create_game(scenario=SMALL_SCENARIO, seed=305000,
                       default_backend="simple", autonomous=True,
                       llm_log=False, affordance_mode=mode)


def test_observation_is_json_safe_deterministic_and_does_not_change_world_state():
    world = _world()
    before = world.export_state()

    first = world.observe("Ada")
    second = world.observe("Ada")

    assert first == second
    # Tuples are JSON arrays; no sets, NodeRefs or non-finite numbers leak.
    json.dumps(first, sort_keys=True, allow_nan=False)
    assert world.export_state() == before

    assert first["turn"] == 0
    assert "calendar" in first
    assert "terrain_movement" in first
    assert first["position"] == world.actor_position("Ada")
    for key in ("health", "hunger", "energy", "intoxication",
                "intoxication_band", "inventory", "held_items", "worn",
                "carrying", "carried_weight", "carry_ratio", "turn_state",
                "job", "known_recipes", "last_outcome", "nearby_actors",
                "visible_objects", "containers_in_reach", "cell", "heard"):
        assert key in first


def test_observation_matches_the_brute_force_reads():
    world = _world()
    assert world.open_physical_object_as_actor("Ada", "box")

    observation = world.observe("Ada")
    reference = world.physical_object_observations("Ada")

    # Visible objects: the same ids as the exhaustive containment walk.
    assert [item["id"] for item in observation["visible_objects"]] == \
        [item["id"] for item in reference]
    by_id = {item["id"]: item for item in observation["visible_objects"]}
    assert by_id["apple"]["edible"] is True
    assert by_id["hammer"]["tool"] is True
    assert by_id["box"]["container"] is True
    assert by_id["box"]["open"] is True
    assert by_id["coin"]["reachable"] is True
    for item in observation["visible_objects"]:
        for tag in ("reachable", "grabbable", "container", "open",
                    "locked", "edible", "tool"):
            assert isinstance(item[tag], bool)

    # Containers in reach carry an open/locked/contents summary.
    box = next(item for item in observation["containers_in_reach"]
               if item["id"] == "box")
    assert box["open"] is True
    assert [child["id"] for child in box["contents"]] == ["coin"]

    # Nearby actors: exactly the full scan within the same radius 8.
    position = world.actor_position("Ada")
    expected = sorted(
        name for name in world._actors
        if name != "Ada" and world.is_alive(name)
        and world.actor_position(name) is not None
        and world.distance(position, world.actor_position(name)) <= 8)
    assert [item["id"] for item in observation["nearby_actors"]] == expected
    for item in observation["nearby_actors"]:
        assert isinstance(item["shared_bucket_count"], int)
        assert isinstance(item["band_code"], float)

    # Speech: the same bounded projection as heard_utterances.
    world.speak("Ben", "Ada", "hello Ada")
    world.speak("Ben", None, "hello everyone")
    world.speak("Cy", "Ben", "not for Ada")
    assert observation["heard"] == []  # captured before the speech
    assert world.observe("Ada")["heard"] == world.heard_utterances("Ada", limit=20)
    assert [record["text"] for record in world.observe("Ada")["heard"]] == \
        ["hello Ada", "hello everyone"]


def test_object_and_utterance_indices_follow_moves_without_a_rescan():
    world = _world()
    assert "apple" in world._physical_object_index["table"]

    # Moving an object updates the index and the observation.
    assert world.move_physical_object("apple", "world")
    assert "apple" not in world._physical_object_index["table"]
    assert "apple" in world._physical_object_index["world"]
    visible = {item["id"]: item for item in world.observe("Ada")["visible_objects"]}
    assert visible["apple"]["location"] == "world"

    # Moving an actor updates the TG02 occupancy buckets used by nearby actors.
    ada_cell = world.actor_position("Ada")
    world._move_actor_to("Ben", ada_cell)
    assert "Ben" in world._actor_positions.near(ada_cell, 0)
    ben = next(item for item in world.observe("Ada")["nearby_actors"]
               if item["id"] == "Ben")
    assert ben["distance"] == 0

    # Speaking updates the recipient index; the observation uses it without
    # rebuilding from the whole utterance log.
    utterance = world.speak("Ben", "Ada", "indexed hello")
    assert world._heard_utterance_index["Ada"][-1] == utterance

    def _no_rebuild():
        raise AssertionError("heard index was rebuilt on the indexed path")

    world._rebuild_heard_utterance_index = _no_rebuild
    assert world.observe("Ada")["heard"][-1]["text"] == "indexed hello"


def test_heard_index_falls_back_to_the_log_when_absent_or_stale():
    world = _world()
    world.speak("Ben", "Ada", "fallback hello")

    world._heard_utterance_index = {}
    world._heard_utterance_log_size = -1
    assert world.heard_utterances("Ada")[-1]["text"] == "fallback hello"
    assert "Ada" in world._heard_utterance_index


def test_replaced_or_directly_mutated_location_mapping_rebuilds_the_index():
    # Direct mutation of the indexed mapping keeps the index in sync.
    world = _world()
    assert isinstance(world._physical_object_locations, _PhysicalObjectLocations)
    world._physical_object_locations["apple"] = "Ada"
    assert "apple" in world._physical_object_index["Ada"]
    assert any(item["id"] == "apple"
               for item in world.observe("Ada")["visible_objects"])

    # Replacing the mapping with a plain dict must rebuild it on read.
    replaced = _world()
    mapping = dict(replaced._physical_object_locations)
    mapping["hammer"] = "Ada"
    replaced._physical_object_locations = mapping
    assert any(item["id"] == "hammer"
               for item in replaced.observe("Ada")["visible_objects"])
    assert isinstance(replaced._physical_object_locations, _PhysicalObjectLocations)

    # A registry that grew unexpectedly is rebuilt too.
    grown = _world()
    mapping = dict(grown._physical_object_locations)
    node = grown.eng.add_node("PhysicalObject", {
        "object_id": "new_token", "name": "new token", "kind": "token",
        "location": "table"})
    grown._physical_objects["new_token"] = node
    mapping["new_token"] = "table"
    grown._physical_object_locations = mapping
    assert any(item["id"] == "new_token"
               for item in grown.observe("Ada")["visible_objects"])


def test_lazy_context_uses_the_observation_and_never_builds_the_menu():
    game = _game("lazy")

    def _forbidden(*args, **kwargs):
        raise AssertionError("lazy context called the exhaustive menu builder")

    game.world.actor_affordances = _forbidden
    game.world._actor_options = _forbidden
    actor = "Ada"
    game._physical_events[actor] = [{"text": "saw a box move"}]
    game.world.record_observation(actor, "practice", skill="carpentry", minutes=1.0)
    game.world.eng.set_attr(game.world._actors[actor], "last_outcome", {
        "turn": 0, "action": "rest", "applied": True, "reason": ""})

    context = game._context(actor)

    assert context.affordances == []
    assert context.recipient_interfaces == {}
    assert context.agent_view is None
    observations = context.observations
    assert "entities" in observations
    assert observations["entities"] == game.world.observe(actor)
    assert observations["physical_events"] == [{"text": "saw a box move"}]
    assert observations["practice"]
    assert observations["world_frames"]["laws"] == []
    assert observations["world_frames"]["policies"] == []
    assert "documents" in observations["world_frames"]
    assert observations["known_references"] == []
    assert observations["last_outcome"]["action"] == "rest"

    game._activate_continuation(
        actor, ActorContinuation(destination=game.world.actor_position(actor)),
        action_ok=True)
    with_continuation = game._context(actor)
    assert with_continuation.observations["continuation"]["destination"] == \
        game.world.actor_position(actor)


def test_menu_context_and_trace_digest_are_unchanged():
    game = _game("menu")
    context = game._context("Ada")
    assert context.affordances  # the room publishes object movement
    assert context.recipient_interfaces
    assert "nearby_residents" in context.observations
    assert "entities" not in context.observations
    assert context.observations["physical_objects"] == \
        game.world.physical_object_observations("Ada")

    def _trace():
        menu_game = create_game(
            scenario=MENU_SCENARIO, seed=305000, default_backend="simple",
            autonomous=True, llm_log=False, affordance_mode="menu")
        trace = TurnTrace()
        for _ in range(2):
            assert menu_game.step()["status"] == "advanced"
            trace.add_record(semantic_step_trace(menu_game))
        return trace

    trace = _trace()
    assert trace.turns == 2
    assert trace.hexdigest() == MENU_DIGEST_AT_LA01
