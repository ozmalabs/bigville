"""End-to-end body, food and time loop for a single simple resident."""
from bigville.api import create_game
from bigville.scenarios import load_scenario


def _food_game(*, food=10, ticks_per_period=8, metabolism=True):
    scenario = load_scenario("simple_resident_food").to_dict()
    scenario["physical_subsystems"] = {
        "metabolism": metabolism, "ecology": False, "decay": False,
    }
    game = create_game(scenario=scenario, seed=305006, autonomous=True,
                       ticks_per_period=ticks_per_period, affordance_mode="menu")
    world = game.world
    if food:
        world.set_stock("apple", float(food))
        world.add_container("home_pantry", holds=["apple"], cell=(2, 2))
        world.fill("Ada", "home_pantry", "apple", float(food))
    return game


def _step_record(game):
    world = game.world
    context = game._context("Ada")
    period_before = float(world.eng.node(world._town)["attrs"].get("period", 0))
    before = {
        "hunger": world.hunger("Ada"),
        "energy": world.energy("Ada"),
        "pantry": world.contents("home_pantry", "apple") if "home_pantry" in world._containers else 0.0,
        "inventory": world.inventory_qty("Ada", "apple"),
        "alive": world.is_alive("Ada"),
    }
    result = game.step()
    response = game.last_responses.get("Ada")
    selected = response.major_action if response else None
    after = {
        "hunger": world.hunger("Ada"),
        "energy": world.energy("Ada"),
        "pantry": world.contents("home_pantry", "apple") if "home_pantry" in world._containers else 0.0,
        "inventory": world.inventory_qty("Ada", "apple"),
        "alive": world.is_alive("Ada"),
    }
    period_after = float(world.eng.node(world._town)["attrs"].get("period", 0))
    return {
        "turn": int(world._turn), "period": float(world.eng.node(world._town)["attrs"].get("period", 0)),
        "period_transition": ({"from": period_before, "to": period_after}
                              if period_after != period_before else None),
        "observations": {"hunger": context.observations["hunger"],
                         "energy": context.observations["energy"],
                         "inventory": context.observations["inventory"]},
        "affordances": [option["action"] for option in context.affordances],
        "selected_action": ({"action": selected.action, "reason": selected.reason}
                            if selected else None),
        "result": result["results"]["Ada"], "before": before, "after": after,
    }


def test_simple_resident_observes_hunger_fetches_eats_and_conserves_food():
    game = _food_game()
    world = game.world
    trace = [_step_record(game) for _ in range(18)]

    actions = [step["selected_action"]["action"] for step in trace
               if step["selected_action"]]
    assert actions[:4] == ["fetch", "eat", "fetch", "eat"]
    assert any(step["observations"]["hunger"] > 0 and "fetch" in step["affordances"]
               for step in trace)
    assert any(step["selected_action"] and step["selected_action"]["action"] == "eat"
               and step["result"] and step["after"]["hunger"] == 0
               for step in trace)
    eaten = sum(1 for step in trace if step["selected_action"]
                and step["selected_action"]["action"] == "eat" and step["result"])
    assert world.contents("home_pantry", "apple") + world.inventory_qty("Ada", "apple") + eaten == 10
    # Phase 027: an apple relieves 0.5 of hunger, so the resident eats three apples in these 18 steps.
    assert world.contents("home_pantry", "apple") == 7
    assert world.inventory_qty("Ada", "apple") == 0
    assert world.is_alive("Ada")
    # Phase 027: decay is off here, so three fresh apples (0.5 each) leave 0.5 of hunger.
    assert world.hunger("Ada") == 0.5
    # Keep a compact reproducible audit trail in pytest's assertion context.
    assert all(step["result"] for step in trace)


def test_food_absent_control_starves_after_configured_period_horizon():
    game = _food_game(food=0, ticks_per_period=2)
    world = game.world
    trace = [_step_record(game) for _ in range(10)]
    assert trace[-1]["period"] == 5
    assert not world.is_alive("Ada")
    assert world.hunger("Ada") == 5
    assert all(step["after"]["pantry"] == 0 and step["after"]["inventory"] == 0
               for step in trace)


def test_metabolism_disabled_control_keeps_resident_alive_without_hunger():
    game = _food_game(food=0, ticks_per_period=2, metabolism=False)
    world = game.world
    trace = [_step_record(game) for _ in range(10)]
    assert trace[-1]["period"] == 5
    assert all(step["after"]["hunger"] == 0 for step in trace)
    assert world.is_alive("Ada")
    assert world.physical_subsystems["metabolism"] is False


def test_resident_rest_choice_and_body_stamina_recovery_are_physical():
    game = _food_game(food=0, ticks_per_period=None)
    world = game.world
    world.eng.set_attr(world._bodies["Ada"], "stamina_reserve", 0.2)
    before = world.energy("Ada")
    result = game.step()
    selected = game.last_responses["Ada"].major_action
    assert selected.action == "rest"
    assert result["results"]["Ada"]
    assert world.energy("Ada") > before

