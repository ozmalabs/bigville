"""Professional identity steers simple cognition, not physical access."""

from bigville.api import create_game
from bigville.scenarios import load_scenario
from bigville.backends.protocol import ActorContext


def _game(role):
    scenario = load_scenario("simple_resident_food").to_dict()
    scenario["actors"] = [{"name": "Ada", "role": role, "backend": "simple",
                           "home_cell": [2, 2]}]
    scenario["physical_subsystems"] = {"metabolism": False, "ecology": False, "decay": False}
    game = create_game(scenario=scenario, seed=612, autonomous=True,
                       ticks_per_period=None, affordance_mode="menu")
    world = game.world
    world.add_enclosure("pen", [(2, 2), (2, 3), (3, 2), (3, 3)])
    world.add_animal("Daisy", "cow", cell=(2, 2), enclosure="pen")
    world.set_stock("grass", 8)
    return game


def test_husbandry_opportunity_is_role_invariant_and_farmer_preference_is_cognitive():
    farmer = _game("farmer")
    resident = _game("hand")

    def task_options(game):
        return [option for option in game._context("Ada").affordances
                if option.get("action") == "tend_animals"]

    farmer_options = task_options(farmer)
    resident_options = task_options(resident)
    assert farmer_options and resident_options
    assert [(o["kind"], o["score"]) for o in farmer_options] == [
        (o["kind"], o["score"]) for o in resident_options]

    result = farmer.step()
    assert farmer.last_responses["Ada"].major_action.action == "tend_animals"
    assert result["results"]["Ada"] is True
    assert farmer.world.qty("milk") == 3.0


def test_hunger_and_authored_work_coordinates_do_not_change_physical_affordances():
    game = _game("hand")
    world = game.world
    world.add_container("pantry", kind="pantry", holds=(), cell=(3, 2))
    world.set_stock("bread", 2)
    assert world._move_stock_to_inventory("Ada", "bread", 1)
    world.eng.set_attr(world._actors["Ada"], "skill", 0.5)

    def options():
        return sorted((option["action"], option.get("kind", ""), option.get("recipe", ""),
                       option.get("destination"), option.get("score"))
                      for option in world.actor_affordances("Ada"))

    before = options()
    world.eng.set_attr(world._actors["Ada"], "hunger", 2.0)
    existing_destinations = {row[3] for row in before if row[3] is not None}
    work_cell = next(cell for cell in world._map_cells
                     if cell != world.actor_position("Ada")
                     and cell not in existing_destinations
                     and world.distance(world.actor_position("Ada"), cell) is not None)
    world.eng.set_attr(world._actors["Ada"], "work_x", float(work_cell[0]))
    world.eng.set_attr(world._actors["Ada"], "work_y", float(work_cell[1]))
    assert options() == before
    assert all(row[-1] == 0.0 for row in before)


def test_simple_backend_uses_situated_hunger_to_choose_among_same_affordances():
    game = _game("hand")
    backend = game.backends["Ada"]
    character = game.characters["Ada"]
    affordances = [
        {"action": "eat", "kind": "bread", "score": 0.0},
        {"action": "inspect", "score": 0.0},
        {"action": "rest", "score": 0.0},
    ]
    satiated = ActorContext(character, 0, {"hunger": 0.0, "energy": 100.0}, affordances)
    hungry = ActorContext(character, 1, {"hunger": 1.0, "energy": 100.0}, affordances)
    assert backend.decide(satiated).major_action.action == "inspect"
    assert backend.decide(hungry).major_action.action == "eat"


def test_distant_husbandry_publishes_move_and_non_farmer_does_not_adopt_animal_goal():
    farmer = _game("farmer")
    baker = _game("baker")
    for game in (farmer, baker):
        game.world._move_animal_to("Daisy", (3, 3))

    farmer_opts = [o for o in farmer._context("Ada").affordances if o.get("animal") == "Daisy"]
    baker_opts = [o for o in baker._context("Ada").affordances if o.get("animal") == "Daisy"]
    assert len(farmer_opts) == 1 and len(baker_opts) == 1
    assert farmer_opts[0]["action"] == "move" and farmer_opts[0]["destination"] == (3, 3)
    assert baker_opts[0]["action"] == "move" and baker_opts[0]["destination"] == (3, 3)

    baker_ctx = ActorContext(
        baker.characters["Ada"], 0, {"hunger": 0.0, "energy": 100.0, "calendar": {"hour": 8.0}},
        [{"action": "tend_animals", "kind": "milk", "animal": "Daisy", "score": 0.0},
         {"action": "work", "recipe": "bake_bread", "score": 0.0},
         {"action": "rest", "score": 0.0}],
    )
    decision = baker.backends["Ada"].decide(baker_ctx)
    assert baker.backends["Ada"].current_goal.kind == "work"
    assert decision.major_action.action == "work"
