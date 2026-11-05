"""Package 5: movement/access checks through real BigvilleGame turns."""
from bigville.backends import ActorResponse, DeterministicBackend, ProposedAction
from bigville import create_world
from bigville.game import BigvilleGame
from worlds.bigville_world import BigvilleWorld


class ActionBackend(DeterministicBackend):
    def __init__(self, character, action):
        super().__init__(character)
        self.action = action
        self.contexts = []

    def decide(self, context):
        self.contexts.append(context)
        return ActorResponse(major_action=self.action)


def _session(action):
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    game = BigvilleGame(world, autonomous=True, ticks_per_period=None)
    backend = ActionBackend(game.characters["Ada"], action)
    game.set_backend("Ada", backend)
    return world, game, backend


def test_game_turn_moves_around_obstacle_and_reports_unreachable_failure():
    world, game, backend = _session(ProposedAction("move", {"destination": (3, 1)}))
    # Remove the direct tile from the walkable graph to model a blocked route;
    # the world must choose a legal detour around it.
    direct = world._map_cells.pop((2, 1))
    world.eng.remove_edge_unchecked(world._map_node, "has_cell", direct)
    for cell in world._map_cells.values():
        if world.eng.has_edge(cell, "adjacent", direct):
            world.eng.remove_edge_unchecked(cell, "adjacent", direct)
    world._distance_fields.clear()
    before = world.actor_position("Ada")
    result = game.step()
    assert result["status"] == "advanced"
    assert game.last_results["Ada"] is True
    assert world.actor_position("Ada") != before
    assert world.actor_position("Ada") in world._map_cells
    assert backend.contexts[0].observations["position"] == before

    # A valid but disconnected cell is a failed action, visible in the turn
    # result, and cannot move the actor or any physical object.
    isolated = (2, 1)
    assert isolated not in world._map_cells
    backend.action = ProposedAction("move", {"destination": isolated})
    position = world.actor_position("Ada")
    game.step()
    assert game.last_results["Ada"] is False
    assert world.actor_position("Ada") == position


def test_object_movement_failure_does_not_change_object_location():
    world, game, backend = _session(ProposedAction(
        "move_object", {"object_id": "missing", "destination": "Ada"}))
    game.step()
    assert game.last_results["Ada"] is False


def test_actor_cannot_move_an_inaccessible_object_or_into_itself():
    world = create_world(scenario="monopoly_four_players", autonomous_actors=False)
    before = {item["id"]: item["location"] for item in world.physical_objects()}
    # Contents of the closed box are not reachable, while the box itself is.
    assert not world.move_physical_object_as_actor("Alice", "rulebook", "Alice")
    assert not world.move_physical_object_as_actor("Alice", "game_box", "game_box")
    assert not world.move_physical_object_as_actor("Alice", "game_box", "unknown")
    assert {item["id"]: item["location"] for item in world.physical_objects()} == before


def test_coordinate_placed_objects_and_actor_destinations_require_reach():
    world = create_world(scenario="monopoly_four_players", autonomous_actors=False)
    alice = world.actor_position("Alice")
    far = max(world._map_cells, key=lambda cell: world.distance(alice, cell) or 0)
    assert world.distance(alice, far) > 1
    box_node = world._physical_objects["game_box"]
    world.eng.set_attr(box_node, "cell", list(far))
    before = next(item for item in world.physical_objects() if item["id"] == "game_box")
    assert not any(item["id"] == "game_box"
                   for item in world.physical_object_observations("Alice"))
    assert not world.move_physical_object_as_actor("Alice", "game_box", "Alice")
    assert not any(option.get("object_id") == "game_box"
                   for option in world.physical_object_affordances("Alice"))
    after = next(item for item in world.physical_objects() if item["id"] == "game_box")
    assert after["location"] == before["location"]

    # A locally placed object cannot be handed directly to a distant resident.
    world.eng.set_attr(box_node, "cell", list(alice))
    assert not world.move_physical_object_as_actor("Alice", "game_box", "Dan")
    assert next(item for item in world.physical_objects() if item["id"] == "game_box")["location"] == "table"


def test_coordinate_placed_container_cannot_be_opened_remotely():
    world = create_world(scenario="monopoly_four_players", autonomous_actors=False)
    alice = world.actor_position("Alice")
    far = max(world._map_cells, key=lambda cell: world.distance(alice, cell) or 0)
    box = world._physical_objects["game_box"]
    world.eng.set_attr(box, "cell", list(far))
    assert not world.open_physical_object_as_actor("Alice", "game_box")
    assert world.eng.node(box)["attrs"]["open"] is False


def test_carried_object_tracks_mover_and_can_be_placed_in_reached_container():
    world = create_world(scenario="monopoly_four_players", autonomous_actors=False)
    alice = world.actor_position("Alice")
    box = world._physical_objects["game_box"]
    # Pick up the box at Alice's cell, then author a nearby open container.
    world.eng.set_attr(box, "cell", list(alice))
    assert world.move_physical_object_as_actor("Alice", "game_box", "Alice")
    options = world.physical_object_affordances("Alice")
    assert not any(option.get("object_id") == "game_box"
                   and option.get("destination") == "game_box" for option in options)
    assert not any(option.get("object_id") == "game_box"
                   and option.get("destination") == "Dan" for option in options)
    next_cell = next(cell for cell in world._map_cells
                     if world.distance(alice, cell) == 1)
    world.move_actor("Alice", next_cell)
    assert world._physical_location_cell("game_box") == world.actor_position("Alice")
    assert any(item["id"] == "game_box"
               for item in world.physical_object_observations("Alice"))

    container_id = "nearby_container"
    container = world.eng.add_node("PhysicalObject", {
        "object_id": container_id, "name": container_id, "kind": "container",
        "open": True, "cell": list(next_cell), "location": "table"})
    world._physical_objects[container_id] = container
    world._physical_object_locations[container_id] = "table"
    assert world.move_physical_object_as_actor("Alice", "game_box", container_id)
    assert next(item for item in world.physical_objects()
                if item["id"] == "game_box")["location"] == container_id
    assert world.eng.has_edge(container, "contains_object", box)


def test_drop_after_turn_movement_keeps_object_at_dropper_location():
    world = create_world(scenario="monopoly_four_players", autonomous_actors=False)
    alice = world.actor_position("Alice")
    box = world._physical_objects["game_box"]
    world.eng.set_attr(box, "cell", list(alice))
    game = BigvilleGame(world, autonomous=True, ticks_per_period=None)
    for name, character in game.characters.items():
        game.set_backend(name, ActionBackend(character, None))

    alice_backend = game.backends["Alice"]
    alice_backend.action = ProposedAction(
        "move_object", {"object_id": "game_box", "destination": "Alice"})
    assert game.step()["status"] == "advanced"
    assert game.last_results["Alice"] is True

    destination = next(cell for cell in world._map_cells
                       if world.distance(alice, cell) == 1)
    alice_backend.action = ProposedAction("move", {"destination": destination})
    assert game.step()["status"] == "advanced"
    assert game.last_results["Alice"] is True
    drop_cell = world.actor_position("Alice")
    assert drop_cell != alice

    alice_backend.action = ProposedAction(
        "move_object", {"object_id": "game_box", "destination": "table"})
    assert game.step()["status"] == "advanced"
    assert game.last_results["Alice"] is True
    assert world._physical_location_cell("game_box") == drop_cell
    assert world.eng.node(box)["attrs"]["cell"] == list(drop_cell)
