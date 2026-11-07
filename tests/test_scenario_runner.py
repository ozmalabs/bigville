import json

from bigville.api import create_game
from bigville.scenario_runner import _compact_state, _observed_contexts, run_scenario
from bigville.scenario_runner import _delta
from bigville.scenarios import load_scenario


def _simple_scenario():
    definition = load_scenario("house_argument").to_dict()
    definition["actors"] = [dict(actor, backend="simple") for actor in definition["actors"]]
    return definition


def test_runner_replays_identically_and_records_seed_and_causal_trace():
    scenario = _simple_scenario()
    scenario["physical_subsystems"] = {"metabolism": False, "decay": True}
    first = run_scenario(scenario, seed=17, turns=3, ticks_per_period=2)
    replay = run_scenario(scenario, seed=17, turns=3, ticks_per_period=2)
    different_seed = run_scenario(scenario, seed=18, turns=1)

    assert first == replay
    assert different_seed["seed"] == 18
    assert first["initial_state"]["turn"] == 0
    assert first["physical_subsystems"] == {
        "metabolism": False, "ecology": True, "decay": True, "practice": True, "cognitive_practice": False,
        "loudness": True, "training": True, "illness": False, "joint_actions": False, "monotony": False,
        "alcohol_aftereffects": False, "object_force": False}
    assert [step["turn"] for step in first["steps"]] == [1, 2, 3]
    assert first["steps"][1]["period_transition"]["period"] == 1
    actor = first["steps"][0]["actors"][0]
    assert {"observations", "affordances", "selected_action", "result"} <= actor.keys()
    assert "state_delta" in first["steps"][0]
    json.dumps(first)


def test_compact_trace_observation_does_not_mutate_world():
    game = create_game(scenario=_simple_scenario(), seed=17, autonomous=True)
    before = game.world.export_state()
    compact = _compact_state(game.world)
    after = game.world.export_state()
    assert compact["turn"] == 0
    assert before == after


def test_context_trace_restores_temporary_affordance_targets():
    game = create_game(scenario=_simple_scenario(), seed=17, autonomous=True)
    before = {actor: dict(targets)
              for actor, targets in game.world._actor_targets.items()}
    contexts = _observed_contexts(game)
    after = {actor: dict(targets)
             for actor, targets in game.world._actor_targets.items()}
    assert contexts.keys() == game.backends.keys()
    assert after == before


def test_trace_delta_records_object_and_stock_transfers():
    scenario = _simple_scenario()
    scenario["stocks"] = {"bread": 2}
    scenario["physical_objects"] = [{"id": "ledger", "kind": "book",
                                     "location": "world"}]
    game = create_game(scenario=scenario, seed=17, autonomous=True)
    before = _compact_state(game.world)

    assert game.world.fetch("Mara", "bread", 1)
    assert game.world.move_physical_object_as_actor("Mara", "ledger", "Mara")
    after = _compact_state(game.world)
    delta = _delta(before, after)

    assert delta["stocks"]["bread"] == {"before": 2.0, "after": 1.0}
    assert delta["physical_objects"]["ledger"]["before"]["location"] == "world"
    assert delta["physical_objects"]["ledger"]["after"]["location"] == "Mara"
    assert delta["actors"]["Mara"]["inventory"]["before"] != delta["actors"]["Mara"]["inventory"]["after"]


def test_town100_is_supported_and_backend_override_is_explicit():
    trace = run_scenario("town100", turns=0, backend="simple")
    assert trace["scenario"] == "bigville"
    assert trace["backend_override"] == "simple"


def test_authored_backend_is_preserved_unless_override_is_set():
    scenario = _simple_scenario()
    scenario["actors"][0]["backend"] = "unsupported-authored-backend"
    import pytest
    with pytest.raises(ValueError, match="Unknown backend"):
        run_scenario(scenario, turns=0)
    trace = run_scenario(scenario, turns=0, backend="simple")
    assert trace["backend_override"] == "simple"


def test_waiting_human_does_not_advance_time_or_period():
    game = create_game(scenario=_simple_scenario(), seed=17, player="Mara",
                       ticks_per_period=1)
    before = game.world.export_state()
    result = game.step()
    assert result["status"] == "waiting"
    assert game.world._turn == 0
    assert game.world.export_state() == before
