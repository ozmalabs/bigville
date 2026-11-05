"""Package 7: simple-backend timed smithing with physical input controls."""
from __future__ import annotations

from bigville.api import create_game
from bigville.backends import SimplePolicy, register_simple_profile
from bigville.scenarios import load_scenario
from worlds.bigville_world import BigvilleWorld


class _ChooseNails:
    def score_adjustment(self, backend, context, option):
        return 1000.0 if option.get("recipe") == "forge_nails" else -1000.0


def _game(*, iron=1.0, charcoal=1.0, hammer_condition=1.0):
    register_simple_profile("pkg7.smith", SimplePolicy(hook=_ChooseNails()), replace=True)
    scenario = load_scenario("tools_materials_job")
    game = create_game(scenario=scenario, seed=701, autonomous=True,
                       ticks_per_period=2)
    world = game.world
    world.set_stock("iron", iron)
    world.set_stock("charcoal", charcoal)
    world.eng.set_attr(world._tools["hammer"], "condition", hammer_condition)
    return game


def _run(game, count=8):
    world = game.world
    trace = []
    for _ in range(count):
        before = {"iron": world.qty("iron"), "charcoal": world.qty("charcoal"),
                  "nails": world.qty("nails"), "busy": world.busy("Smith"),
                  "hammer_condition": world.instrument_condition("hammer")}
        context = game._context("Smith")
        result = game.step()
        after = {"iron": world.qty("iron"), "charcoal": world.qty("charcoal"),
                 "nails": world.qty("nails"), "busy": world.busy("Smith"),
                 "hammer_condition": world.instrument_condition("hammer")}
        response = game.last_responses.get("Smith")
        proposal = response.major_action if response else None
        trace.append({"turn": world._turn,
                      "observations": context.observations,
                      "affordances": context.affordances,
                      "selected_action": ({"action": proposal.action,
                                           "params": proposal.params,
                                           "reason": proposal.reason} if proposal else None),
                      "result": game.last_results.get("Smith", result["status"]),
                      "state_delta": {key: {"before": before[key], "after": after[key]}
                                      for key in before if before[key] != after[key]},
                      "state": after})
    return trace


def test_timed_smithing_conserves_inputs_and_has_material_and_tool_controls():
    working = _game()
    trace = _run(working)
    world = working.world
    assert any(step["selected_action"] and step["selected_action"]["action"] == "work"
               for step in trace)
    assert world.qty("nails") == 5.0
    assert world.qty("iron") == 0.0 and world.qty("charcoal") == 0.0
    assert not world.busy("Smith")
    assert world.instrument_condition("hammer") < 1.0
    assert any(step["state_delta"] for step in trace)

    no_iron = _game(iron=0.0)
    material_trace = _run(no_iron, count=3)
    assert no_iron.world.qty("nails") == 0.0
    assert no_iron.world.qty("charcoal") == 1.0
    assert all(not any(option.get("recipe") == "forge_nails"
                       for option in step["affordances"])
               for step in material_trace)

    broken_hammer = _game(hammer_condition=0.0)
    tool_trace = _run(broken_hammer)
    assert broken_hammer.world.qty("nails") == 0.0, (
        "forge_nails produced output with its required hammer broken; "
        "tool condition is not enforced by job execution")
    assert broken_hammer.world.qty("iron") == 1.0
    assert broken_hammer.world.qty("charcoal") == 1.0
    assert all(not any(option.get("recipe") == "forge_nails"
                       for option in step["affordances"])
               for step in tool_trace)


def test_job_trace_is_reproducible_for_fixed_seed():
    assert _run(_game()) == _run(_game())


def test_missing_tool_rejects_start_without_consuming_inputs():
    world = BigvilleWorld()
    world.add_actor("Smith", role="smith", skill=0.9)
    world.set_stock("iron", 1)
    world.set_stock("charcoal", 1)
    hammer = world._tools["hammer"]
    world.eng.remove_edge_unchecked(world._town, "has_tool", hammer)

    assert not world.start("Smith", "forge_nails")
    assert not world.do("Smith", "forge_nails")
    assert world.qty("iron") == 1.0 and world.qty("charcoal") == 1.0
    assert world.qty("nails") == 0.0 and not world.busy("Smith")


def test_tool_lost_during_timed_job_blocks_completion_without_consuming_inputs():
    world = BigvilleWorld()
    world.add_actor("Smith", role="smith", skill=0.9)
    world.set_stock("iron", 1)
    world.set_stock("charcoal", 1)
    hammer = world._tools["hammer"]

    assert world.start("Smith", "forge_nails")
    world.eng.remove_edge_unchecked(world._town, "has_tool", hammer)
    world.tick(1)
    assert world.busy("Smith")
    assert world.qty("iron") == 1.0 and world.qty("charcoal") == 1.0
    assert world.qty("nails") == 0.0

    world.eng.add_edge_unchecked(world._town, "has_tool", hammer)
    world.tick(1)
    assert not world.busy("Smith")
    assert world.qty("iron") == 0.0 and world.qty("charcoal") == 0.0
    assert world.qty("nails") == 5.0
