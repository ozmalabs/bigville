"""Package 10: real simple-backend turns for storage, decay and construction."""
from __future__ import annotations

from bigville.api import create_game
from bigville.backends import SimplePolicy, register_simple_profile
from bigville.scenarios import load_scenario


class _ChooseAction:
    def __init__(self, action, *, recipe=None):
        self.action = action
        self.recipe = recipe

    def score_adjustment(self, backend, context, option):
        return (1000.0 if option.get("action") == self.action
                and (self.recipe is None or option.get("recipe") == self.recipe)
                else -1000.0)


def _game(*, role="hand", action="put", decay=True):
    profile = f"pkg10.{role}.{action}"
    register_simple_profile(profile, SimplePolicy(hook=_ChooseAction(action)), replace=True)
    scenario = load_scenario("simple_resident_food").to_dict()
    scenario["actors"][0]["role"] = role
    scenario["actors"][0]["simple_profile"] = profile
    scenario["physical_subsystems"] = {"metabolism": False, "ecology": False, "decay": decay}
    return create_game(scenario=scenario, seed=701, autonomous=True,
                       ticks_per_period=None, affordance_mode="menu")


def test_real_turn_put_moves_food_without_minting_or_losing_it():
    game = _game()
    world = game.world
    world.add_container("pantry", kind="pantry", holds=(), cell=(2, 2))
    world.set_stock("bread", 3)
    assert world._move_stock_to_inventory("Ada", "bread", 2)
    before_total = world.qty("bread") + world.inventory_qty("Ada", "bread") + world.contents("pantry", "bread")
    context = game._context("Ada")
    assert any(o.get("action") == "put" and o.get("kind") == "bread" for o in context.affordances)

    result = game.step()

    proposal = game.last_responses["Ada"].major_action
    assert proposal.action == "put"
    assert result["results"]["Ada"] is True
    assert world.inventory_qty("Ada", "bread") == 1.0
    assert world.contents("pantry", "bread") == 1.0
    assert world.qty("bread") == 1.0
    assert world.qty("bread") + world.inventory_qty("Ada", "bread") + world.contents("pantry", "bread") == before_total


def test_capacity_and_lock_controls_refuse_put_without_changing_stocks():
    full = _game()
    wf = full.world
    wf.add_container("tiny", kind="pantry", holds=(), cell=(2, 2))
    wf.eng.set_attr(wf._containers["tiny"][0], "capacity", 0.5)
    wf.set_stock("bread", 1)
    wf._move_stock_to_inventory("Ada", "bread", 1)
    assert not any(o.get("action") == "put" and o.get("target") == "tiny"
                   for o in full._context("Ada").affordances)
    assert wf.inventory_qty("Ada", "bread") == 1.0 and wf.contents("tiny", "bread") == 0.0

    locked = _game()
    wl = locked.world
    wl.add_container("locked_pantry", kind="pantry", holds=(), lock_id=27, locked=True, cell=(2, 2))
    wl.set_stock("bread", 1)
    wl._move_stock_to_inventory("Ada", "bread", 1)
    assert not wl.put("Ada", "locked_pantry", "bread", 1)
    assert wl.inventory_qty("Ada", "bread") == 1.0 and wl.contents("locked_pantry", "bread") == 0.0
    wl.give_key("Ada", opens=27)
    assert wl.put("Ada", "locked_pantry", "bread", 1)
    assert wl.contents("locked_pantry", "bread") == 1.0


def test_decay_prefers_suitable_granary_storage_and_decay_off_is_control():
    game = _game(decay=True)
    world = game.world
    world.add_actor("Tester", role="hand")
    world.set_stock("grain", 20)
    world.set_stock("bread", 20)
    world.add_container("grain_bin", kind="granary", holds=())
    world.add_container("mismatch_bin", kind="granary", holds=())
    assert world.fill("Tester", "grain_bin", "grain", 10)
    assert world.fill("Tester", "mismatch_bin", "bread", 10)
    before = world.qty("grain") + world.qty("bread") + world.contents("grain_bin", "grain") + world.contents("mismatch_bin", "bread")
    world.pass_period(2)
    assert world.contents("grain_bin", "grain") == 10.0
    assert world.contents("mismatch_bin", "bread") == 10.0
    assert world.stored_condition("grain_bin", "grain") > world.stored_condition("mismatch_bin", "bread")
    # Decay changes condition first; quantity is conserved until spoilage.
    after = world.qty("grain") + world.qty("bread") + world.contents("grain_bin", "grain") + world.contents("mismatch_bin", "bread")
    assert after == before

    control = _game(decay=False).world
    control.add_actor("Tester", role="hand")
    control.set_stock("bread", 10)
    control.add_container("cold", kind="larder", holds=())
    control.fill("Tester", "cold", "bread", 5)
    condition = control.stored_condition("cold", "bread")
    control.pass_period(4)
    assert control.stored_condition("cold", "bread") == condition
    assert control.contents("cold", "bread") == 5.0


def test_simple_backend_constructs_only_with_inputs_and_labor():
    profile = "pkg10.builder.build"
    register_simple_profile(profile, SimplePolicy(hook=_ChooseAction("build", recipe="house_pkg10")), replace=True)
    scenario = load_scenario("simple_resident_food").to_dict()
    scenario["actors"][0].update(role="mason", simple_profile=profile)
    scenario["physical_subsystems"] = {"metabolism": False, "ecology": False, "decay": False}
    game = create_game(scenario=scenario, seed=702, autonomous=True,
                       ticks_per_period=None, affordance_mode="menu")
    world = game.world
    world.set_stock("timber", 12)
    world.set_stock("thatch", 8)
    world.propose_building("house", site=(2, 2), name="house_pkg10")

    trace = []
    for _ in range(12):
        if world.building_project_data("house_pkg10")["status"] == "complete":
            break
        context = game._context("Ada")
        assert any(option.get("action") == "build" and option.get("recipe") == "house_pkg10"
                   for option in context.affordances)
        result = game.step()
        response = game.last_responses["Ada"].major_action
        trace.append((response.action, result["results"]["Ada"], world.qty("timber"),
                      world.qty("thatch"), world.building_project_data("house_pkg10")["progress"]))

    assert all(action == "build" for action, *_ in trace)
    assert trace[0][2:4] == (10.8, 7.2)
    assert world.building_project_data("house_pkg10")["status"] == "complete"
    assert world.building("house_pkg10") is not None
    assert all(result is True for _, result, *_ in trace)
    assert [progress for *_, progress in trace] == list(range(1, 11))
    # The project spends its full declared inputs over exactly ten accepted
    # work turns; each intermediate turn is a successful action as well.
    assert world.qty("timber") == 0.0 and world.qty("thatch") == 0.0
    assert len(trace) == 10

    missing = create_game(scenario=scenario, seed=703, autonomous=True,
                          ticks_per_period=None, affordance_mode="menu")
    missing.world.propose_building("house", site=(2, 2), name="unfinished")
    missing_trace = [missing.step() for _ in range(3)]
    assert not any(o.get("action") == "build" for o in missing._context("Ada").affordances)
    assert missing.world.building_project_data("unfinished")["progress"] == 0.0
    assert missing.world.building_project_data("unfinished")["status"] == "proposed"
    assert all(step["results"]["Ada"] is True for step in missing_trace)  # valid idle turns
