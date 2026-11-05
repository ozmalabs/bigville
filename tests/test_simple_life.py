from bigville.backends import ActorContext, DeterministicBackend, SimplePolicy
from bigville.backends import register_simple_profile, simple_policy_for
from bigville.character import CharacterDefinition, MemoryRecord
from bigville.game import BigvilleGame
from worlds.bigville_world import BigvilleWorld


def test_simple_resident_fetches_and_eats_physical_food_across_periods():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.set_stock("apple", 10)
    world.add_container("pantry", holds=["apple"], cell=(1, 1))
    world.fill("Ada", "pantry", "apple", 10)
    game = BigvilleGame(world, autonomous=True, ticks_per_period=8)

    actions = []
    for _ in range(18):
        result = game.step()
        response = game.last_responses["Ada"]
        if response.major_action:
            actions.append(response.major_action.action)
            assert result["results"]["Ada"]
    assert actions[:4] == ["fetch", "eat", "fetch", "eat"]
    assert world.is_alive("Ada")
    assert world.hunger("Ada") == 0
    assert world.contents("pantry", "apple") == 8
    assert world.inventory_qty("Ada", "apple") == 0


def test_simple_resident_rests_even_when_work_is_available():
    character = CharacterDefinition("Ada", "Ada")
    backend = DeterministicBackend(character)
    context = ActorContext(character, 0, {"energy": 20, "hunger": 0}, [
        {"action": "work", "score": 30}, {"action": "rest", "score": 0},
    ])
    assert backend.decide(context).major_action.action == "rest"
    assert backend.last_choice["psi"]["fatigue"] == 0.8


def test_backend_values_household_food_only_when_hungry_and_not_holding_food():
    character = CharacterDefinition("Ada", "Ada")
    backend = DeterministicBackend(character)
    affordances = [
        {"action": "fetch", "kind": "apple", "physical_source": "container",
         "source_container": "pantry", "score": 0},
        {"action": "put", "kind": "apple", "score": 5},
        {"action": "rest", "score": 0},
    ]
    hungry = ActorContext(character, 0, {"energy": 100, "hunger": 1}, affordances)
    assert backend.decide(hungry).major_action.action == "fetch"

    satisfied = ActorContext(character, 1, {"energy": 100, "hunger": 0}, affordances)
    assert backend.decide(satisfied).major_action.action == "put"

    fed_but_hungry = ActorContext(character, 2, {"energy": 100, "hunger": 1}, [
        *affordances, {"action": "eat", "kind": "apple", "score": 0},
    ])
    assert backend.decide(fed_but_hungry).major_action.action == "eat"


def test_simple_resident_physically_recovers_stamina():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.eng.set_attr(world._bodies["Ada"], "stamina_reserve", 0.2)
    game = BigvilleGame(world, autonomous=True, ticks_per_period=None)
    result = game.step()
    assert game.last_responses["Ada"].major_action.action == "rest"
    assert result["results"]["Ada"]
    assert world.energy("Ada") > 20


def test_without_food_resident_starves_as_periods_pass():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    game = BigvilleGame(world, autonomous=True, ticks_per_period=2)
    for _ in range(10):
        game.step()
    assert not world.is_alive("Ada")


def test_simple_policy_can_prefer_a_scenario_action():
    character = CharacterDefinition("Ada", "Ada")
    backend = DeterministicBackend(character, policy=SimplePolicy(
        action_bonuses={"inspect": 50}))
    context = ActorContext(character, 0, {"energy": 100}, [
        {"action": "work", "score": 10}, {"action": "inspect", "score": 5},
    ])
    assert backend.decide(context).major_action.action == "inspect"


def test_waiting_for_human_does_not_advance_periods():
    world = BigvilleWorld(autonomous_actors=False)
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    game = BigvilleGame(world, player="Ada", ticks_per_period=1)
    assert game.step()["status"] == "waiting"
    assert world.hunger("Ada") == 0


def test_registered_profiles_choose_differently_and_replay_deterministically():
    character = CharacterDefinition("Ada", "Ada", memories=[MemoryRecord(
        "recipe:bake_bread", {"recipe": "bake_bread"}, kind="recipe_knowledge",
        source="scenario_prior")])
    context = ActorContext(character, 4, {"energy": 100, "hunger": 0}, [
        {"action": "work", "recipe": "bake_bread", "score": 10},
        {"action": "inspect", "score": 5},
    ])
    register_simple_profile("test.work", SimplePolicy(action_bonuses={"work": 20}), replace=True)
    register_simple_profile("test.inspect", lambda: SimplePolicy(action_bonuses={"inspect": 1000}), replace=True)
    choices = []
    for name in ("test.work", "test.inspect", "test.work", "test.inspect"):
        backend = DeterministicBackend(character, policy=simple_policy_for(name))
        action = backend.decide(context).major_action.action
        assert action in {option["action"] for option in context.affordances}
        choices.append(action)
    assert choices == ["work", "inspect", "work", "inspect"]


def test_stateful_profile_hook_only_scores_existing_affordances():
    class FirstChoiceHook:
        def __init__(self):
            self.calls = 0

        def score_adjustment(self, backend, context, option):
            self.calls += 1
            return 100 if option["action"] == "inspect" else 0

    character = CharacterDefinition("Ada", "Ada", memories=[MemoryRecord(
        "recipe:bake_bread", {"recipe": "bake_bread"}, kind="recipe_knowledge",
        source="scenario_prior")])
    policy = SimplePolicy(hook=FirstChoiceHook())
    context = ActorContext(character, 0, {"energy": 100}, [
        {"action": "work", "recipe": "bake_bread", "score": 10},
        {"action": "inspect", "score": 0},
    ])
    backend = DeterministicBackend(character, policy=policy)
    response = backend.decide(context)
    assert response.major_action.action == "inspect"
    assert policy.hook.calls == 2


def test_unknown_simple_profile_fails_clearly():
    import pytest

    with pytest.raises(ValueError, match="Unknown simple policy profile: absent"):
        simple_policy_for("absent")


def test_physical_subsystems_default_on_and_reject_invalid_configuration():
    import pytest

    world = BigvilleWorld(autonomous_actors=False)
    assert world.physical_subsystems == {"metabolism": True, "ecology": True, "decay": True, "practice": True,
                                         "cognitive_practice": False}
    with pytest.raises(ValueError, match="Unknown physical subsystem"):
        BigvilleWorld(autonomous_actors=False,
                      physical_subsystems={"gravity": False})
    with pytest.raises(TypeError, match="must be a boolean"):
        BigvilleWorld(autonomous_actors=False,
                      physical_subsystems={"metabolism": "off"})


def test_metabolism_switch_suppresses_hunger_without_disabling_decay():
    world = BigvilleWorld(autonomous_actors=False,
                          physical_subsystems={"metabolism": False})
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.set_stock("apple", 3)
    start_condition = world.stock_condition("apple")
    world.pass_period(1)
    assert world.hunger("Ada") == 0
    assert world.stock_condition("apple") < start_condition
    assert world.qty("apple") == 3


def test_decay_switch_preserves_food_and_metabolism_still_runs():
    world = BigvilleWorld(autonomous_actors=False,
                          physical_subsystems={"decay": False})
    world.add_actor("Ada", role="hand", home_cell=(1, 1))
    world.set_stock("apple", 3)
    start_condition = world.stock_condition("apple")
    world.pass_period(1)
    assert world.hunger("Ada") == 1
    assert world.stock_condition("apple") == start_condition
    assert world.qty("apple") == 3


def test_ecology_switch_stops_crop_growth_but_keeps_metabolism():
    world = BigvilleWorld(autonomous_actors=False,
                          physical_subsystems={"ecology": False})
    world.add_actor("Ada", role="farmer", home_cell=(1, 1))
    world.set_stock("carrot_seed", 1)
    crop = world.sow("Ada", "carrot")
    assert crop is not None
    world.pass_period(1)
    assert world.crop_age(crop) == 0
    assert world.hunger("Ada") == 1


def test_custom_physical_subsystem_extension_runs_only_when_enabled():
    calls = []
    world = BigvilleWorld(
        autonomous_actors=False,
        physical_subsystems={"test_climate": True},
        physical_subsystem_extensions={
            "test_climate": lambda active_world, periods: calls.append(
                (active_world, periods))})
    world.pass_period(2)
    assert calls == [(world, 1), (world, 1)]


def test_scenario_actor_selects_registered_simple_profile():
    from bigville.api import create_game
    from bigville.scenarios import load_scenario

    register_simple_profile("test.scenario", SimplePolicy(action_bonuses={"work": 11}), replace=True)
    scenario = load_scenario("house_argument").to_dict()
    actors = [dict(entry, backend="simple") for entry in scenario["actors"]]
    actor = dict(actors[0], simple_profile="test.scenario")
    scenario["actors"] = [actor, *actors[1:]]
    game = create_game(scenario=scenario, autonomous=True)
    assert game.backends[actor["name"]].policy.action_bonuses == {"work": 11}
