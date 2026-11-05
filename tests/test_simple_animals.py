"""Package 9: animal metabolism, caregiver action and enclosure controls."""
from bigville.api import create_game
from bigville.scenarios import load_scenario


def _animal_game(*, grass=8.0, ticks_per_period=1, animal_cell=(2, 2)):
    scenario = load_scenario("simple_resident_food").to_dict()
    scenario["actors"] = [{"name": "Ada", "role": "farmer", "backend": "simple",
                          "home_cell": [2, 2]}]
    scenario["physical_subsystems"] = {
        "metabolism": True, "ecology": False, "decay": False,
    }
    game = create_game(scenario=scenario, seed=309009, autonomous=True,
                       ticks_per_period=ticks_per_period)
    world = game.world
    world.add_enclosure("small_pen", [(2, 2), (2, 3), (3, 2), (3, 3)])
    world.add_animal("Daisy", "cow", cell=animal_cell, enclosure="small_pen")
    world.set_stock("grass", grass)
    return game


def _turn(game):
    world = game.world
    context = game._context("Ada")
    before = {"grass": world.qty("grass"), "milk": world.qty("milk"),
              "hunger": world.animal_hunger("Daisy"),
              "alive": world.animal_alive("Daisy"),
              "position": world.animal_position("Daisy")}
    result = game.step()
    response = game.last_responses["Ada"].major_action
    after = {"grass": world.qty("grass"), "milk": world.qty("milk"),
             "hunger": world.animal_hunger("Daisy"),
             "alive": world.animal_alive("Daisy"),
             "position": world.animal_position("Daisy")}
    animal_attrs = world.eng.node(world._animals["Daisy"])["attrs"]
    return {
        "turn": world._turn,
        "period": world.eng.node(world._town)["attrs"]["period"],
        "observations": context.observations,
        "affordances": context.affordances,
        "care_action": ({"action": response.action, "params": response.params,
                         "reason": response.reason} if response else None),
        "care_result": result["results"]["Ada"],
        "animal_action": animal_attrs["last_npc_action"],
        "animal_decision": game._animal_decisions["Daisy"],
        "before": before,
        "after": after,
    }


def test_caregiver_milks_through_game_turns_without_hidden_feed_consumption():
    game = _animal_game(grass=8.0)
    world = game.world
    trace = [_turn(game) for _ in range(2)]

    assert [step["care_action"]["action"] for step in trace] == [
        "tend_animals", "tend_animals"]
    assert all(step["care_result"] for step in trace)
    assert all(step["animal_action"] == "stay" for step in trace)
    assert all(step["animal_decision"]["action"] == "stay" for step in trace)
    # With no accessible land feeding action, metabolism raises hunger and leaves stock alone.
    assert [step["after"]["grass"] for step in trace] == [8.0, 8.0]
    assert [step["after"]["milk"] for step in trace] == [3.0, 6.0]
    assert [step["after"]["hunger"] for step in trace] == [1.0, 2.0]
    assert world.animal_alive("Daisy")
    assert world.qty("grass") == 8.0
    assert world.qty("milk") == 6.0
    assert world.animal_enclosure("Daisy") == "small_pen"
    assert world.enclosure_intact("small_pen")
    assert world.physical_subsystems["metabolism"] is True


def _animal_at_store(*, grass):
    game = _animal_game(grass=grass)
    world = game.world
    # The animal has no enclosure restriction in this focused feeding test.
    animal = world._animals["Daisy"]
    for enclosure in list(world.eng.neighbours(animal, "kept_in")):
        world.eng.remove_edge_unchecked(animal, "kept_in", enclosure)
    world._enclosure_cells.clear()
    world._enclosures.clear()
    # The scenario's abstract store fixture is unlocated; give this test's
    # feed pile a concrete map location to exercise physical reach.
    store_cell = (2, 2)
    world.eng.add_edge_unchecked(world._store, "at_cell", world._map_cells[store_cell])
    return game


def test_animal_eats_nearby_feed_as_an_explicit_action_and_conserves_stock():
    game = _animal_at_store(grass=6.0)
    world = game.world
    store_cell = world.map_position_node(world._store)
    world.eng.set_attr(world._animals["Daisy"], "hunger", 1.0)
    world._move_animal_to("Daisy", store_cell)

    decision = game.animal_turn()["Daisy"]

    assert decision["action"] == "eat"
    assert world.eng.node(world._animals["Daisy"])["attrs"]["last_npc_action"] == "eat"
    assert world.qty("grass") == 2.0
    assert world.animal_hunger("Daisy") == 0.0
    assert world.qty("grass") + 4.0 == 6.0


def test_physical_affordances_ignore_hunger_and_species_motivation():
    cow = _animal_at_store(grass=8.0).world
    sheep = _animal_at_store(grass=8.0).world
    cow.eng.set_attr(cow._animals["Daisy"], "hunger", 0.0)
    sheep.eng.set_attr(sheep._animals["Daisy"], "hunger", 2.0)
    sheep.eng.set_attr(sheep._animals["Daisy"], "species", "sheep")
    sheep.eng.set_attr(sheep._animals["Daisy"], "eats", "grass")
    sheep.eng.set_attr(sheep._animals["Daisy"], "ration", 4.0)
    assert cow.animal_affordances("Daisy") == sheep.animal_affordances("Daisy")


def test_animal_backend_eats_when_hungry_and_stays_when_satisfied():
    game = _animal_at_store(grass=8.0)
    world = game.world
    animal = world._animals["Daisy"]
    world._move_animal_to("Daisy", world.map_position_node(world._store))
    world.eng.set_attr(animal, "hunger", 0.0)
    actions = {option["action"] for option in world.animal_affordances("Daisy")}
    assert "eat" in actions
    assert game.animal_turn()["Daisy"]["action"] == "stay"
    world.eng.set_attr(animal, "hunger", 2.0)
    assert game.animal_turn()["Daisy"]["action"] == "eat"


def test_game_turn_animal_backend_eats_located_feed_and_conserves_stock():
    game = _animal_at_store(grass=6.0)
    world = game.world
    # Prevent a later resident period transition from obscuring the animal's
    # eat result; the game turn still advances and invokes the animal backend.
    game.ticks_per_period = None
    animal = world._animals["Daisy"]
    world.eng.set_attr(animal, "hunger", 1.0)
    before = world.qty("grass")
    feed_cell = world.map_position_node(world._store)
    assert feed_cell == world.animal_position("Daisy")
    assert world.distance(world.animal_position("Daisy"), feed_cell) == 0

    result = game.step()

    mind = game._animal_backends["Daisy"]
    assert result["status"] == "advanced"
    assert mind.last_choice["action"] == "eat"
    assert game._animal_decisions["Daisy"]["action"] == "eat"
    assert world.eng.node(animal)["attrs"]["last_npc_action"] == "eat"
    assert world.qty("grass") == before - 4.0
    assert world.qty("grass") + 4.0 == before
    assert world.animal_hunger("Daisy") == 0.0

    # Same game-turn path, but the physically located store is unreachable.
    distant = _animal_at_store(grass=6.0)
    distant.world.eng.set_attr(distant.world._animals["Daisy"], "hunger", 1.0)
    store_cell = distant.world.map_position_node(distant.world._store)
    far_cell = max(distant.world._map_cells,
                   key=lambda cell: distant.world.distance(cell, store_cell) or 0)
    distant.world._move_animal_to("Daisy", far_cell)
    distant.ticks_per_period = None
    distant_world = distant.world
    distant_before = distant_world.qty("grass")

    distant.step()

    assert distant._animal_backends["Daisy"].last_choice["action"] != "eat"
    assert distant_world.qty("grass") == distant_before
    assert distant_world.animal_hunger("Daisy") == 1.0


def test_animal_cannot_eat_distant_or_absent_feed():
    game = _animal_at_store(grass=6.0)
    world = game.world
    store_cell = world.map_position_node(world._store)
    far_cell = max(world._map_cells, key=lambda cell: world.distance(cell, store_cell) or 0)
    world._move_animal_to("Daisy", far_cell)
    world.eng.set_attr(world._animals["Daisy"], "hunger", 1.0)

    decision = game.animal_turn()["Daisy"]
    assert decision["action"] != "eat"
    assert world.qty("grass") == 6.0
    assert world.animal_hunger("Daisy") == 1.0
    world._move_animal_to("Daisy", store_cell)
    world.set_stock("grass", 0.0)
    decision = game.animal_turn()["Daisy"]
    assert decision["action"] != "eat"
    assert world.qty("grass") == 0.0
    assert world.animal_hunger("Daisy") == 1.0


def test_world_tick_advances_animal_physics_without_running_backend():
    game = _animal_at_store(grass=8.0)
    world = game.world
    animal = world._animals["Daisy"]
    world.eng.set_attr(animal, "hunger", 1.0)
    before = world.qty("grass")

    world.tick()

    assert world.qty("grass") == before
    assert world.animal_hunger("Daisy") == 1.0
    assert world.eng.node(animal)["attrs"]["last_npc_action"] == ""
    assert "Daisy" not in game._animal_backends
    assert "Daisy" not in game._animal_decisions

def test_game_periods_expose_no_feed_starvation_control():
    game = _animal_game(grass=0.0)
    world = game.world
    trace = [_turn(game) for _ in range(4)]

    assert [step["period"] for step in trace] == [1.0, 2.0, 3.0, 4.0]
    assert all(step["after"]["grass"] == 0.0 for step in trace)
    assert [step["after"]["hunger"] for step in trace] == [1.0, 2.0, 3.0, 3.0]
    assert not world.animal_alive("Daisy")
    assert world.qty("grass") == 0.0
    assert [step["after"]["milk"] for step in trace] == [3.0, 6.0, 9.0, 9.0]
    assert [step["care_result"] for step in trace] == [True, True, True, True]


def test_animal_turn_moves_toward_intact_pen_and_broken_barrier_allows_escape():
    game = _animal_game(grass=0.0, ticks_per_period=None, animal_cell=(1, 2))
    world = game.world
    # Start just beyond the pen. The animal NPC gets a real turn and chooses
    # an adjacent permitted cell; the world does not publish a remote goal.
    before = world.animal_position("Daisy")
    move_targets = [tuple(option["target"])
                    for option in world.animal_affordances("Daisy")
                    if option.get("action") == "move"]
    assert move_targets
    assert all(abs(before[0] - target[0]) + abs(before[1] - target[1]) == 1
               for target in move_targets)
    trace = _turn(game)
    after = world.animal_position("Daisy")
    assert trace["animal_action"] == "move"
    assert trace["animal_decision"]["action"] == "move"
    assert before == (1, 2)
    assert after in world.enclosure_cells("small_pen")
    assert world.enclosure_intact("small_pen")

    outside = (1, 2)
    assert world._move_animal_to("Daisy", outside) == after
    fence = next(name for name in world._fences if name.startswith("small_pen:fence:"))
    world.break_fence(fence)
    assert not world.enclosure_intact("small_pen")
    assert world._move_animal_to("Daisy", outside) == outside
