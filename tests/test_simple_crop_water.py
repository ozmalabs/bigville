"""Package 8: crop/water loop through actual simple-backend game turns."""
from __future__ import annotations

from bigville.api import create_game
from bigville.backends import SimplePolicy, register_simple_profile
from bigville.scenarios import load_scenario
from domains import bigville_entities as E


class _FarmChoice:
    """Choose the strongest currently published crop task, without inventing one."""

    def score_adjustment(self, backend, context, option):
        priorities = {"water": 3000.0, "harvest": 2000.0, "sow": 1000.0}
        return priorities.get(option.get("action"), -1000.0)


def _game(*, water=6.0, season="spring"):
    register_simple_profile("pkg8.crop_water", SimplePolicy(hook=_FarmChoice()), replace=True)
    definition = load_scenario("crop_water").to_dict()
    definition["stocks"] = {"wheat_seed": 1.0, "water": float(water)}
    definition["initial"]["season"] = season
    game = create_game(scenario=definition, seed=808, autonomous=True,
                       ticks_per_period=2, affordance_mode="menu")
    # The scenario has one physical farm cell. Land remains a world object, so
    # install its parcel on that cell before the first game turn.
    game.world.add_land("farm_plot_00", use="arable", soil="loam", cell=(1, 1))
    return game


def _crop_state(world, crop):
    attrs = world.eng.node(crop)["attrs"]
    return {key: attrs.get(key) for key in ("age", "thirst", "alive", "water_armed")}


def _run(game, turns=14):
    world = game.world
    trace = []
    for _ in range(turns):
        before_crop = next(iter(world._crops.values()), None)
        before = _crop_state(world, before_crop) if before_crop is not None else None
        before_stock = {"seed": world.qty("wheat_seed"), "water": world.qty("water"),
                        "grain": world.qty("grain")}
        context = game._context("Farmer")
        result = game.step()
        crop = next(iter(world._crops.values()), None)
        response = game.last_responses.get("Farmer")
        proposal = response.major_action if response else None
        trace.append({
            "turn": world._turn,
            "period": world.eng.node(world._town)["attrs"]["period"],
            "observations": context.observations,
            "affordances": context.affordances,
            "selected_action": ({"action": proposal.action, "params": proposal.params,
                                 "reason": proposal.reason} if proposal else None),
            "result": game.last_results.get("Farmer", result["status"]),
            "crop_before": before,
            "crop_after": _crop_state(world, crop) if crop is not None else None,
            "stocks_before": before_stock,
            "stocks_after": {"seed": world.qty("wheat_seed"), "water": world.qty("water"),
                             "grain": world.qty("grain")},
        })
    return trace


def test_crop_sow_water_grow_harvest_and_no_water_control():
    watered = _game()
    trace = _run(watered)
    world = watered.world
    assert [entry["selected_action"]["action"] for entry in trace
            if entry["selected_action"] and entry["selected_action"]["action"] in
            {"sow", "water", "harvest"}][:1] == ["sow"]
    assert any(entry["selected_action"] and entry["selected_action"]["action"] == "water"
               and entry["result"] is True for entry in trace)
    assert any(entry["period"] > 0 for entry in trace)
    assert world.qty("grain") == 8.0
    assert world.qty("water") < 6.0
    assert any(entry["selected_action"] and entry["selected_action"]["action"] == "harvest"
               and entry["result"] is True for entry in trace)
    assert all(entry["stocks_after"]["grain"] == 0.0
               for entry in trace if entry["crop_after"] is not None
               and float(entry["crop_after"]["age"]) < 4.0)
    first_harvest = next(entry for entry in trace if entry["stocks_after"]["grain"] > 0)
    assert first_harvest["crop_before"]["age"] >= 4.0
    # Harvest returns the crop's data-defined seed; the backend then chooses to sow it again.
    seed_return = float(E.CROPS["wheat"].get("seed_return", 1.0))
    assert any(entry["stocks_after"]["seed"] == seed_return for entry in trace)

    dry = _game(water=0.0)
    dry_trace = _run(dry, turns=8)
    dry_world = dry.world
    crop = next(iter(dry_world._crops.values()))
    assert not dry_world.crop_alive(crop)
    assert dry_world.crop_age(crop) == 2.0
    assert dry_world.qty("grain") == 0.0
    assert not any(entry["selected_action"] and entry["selected_action"]["action"] == "water"
                   for entry in dry_trace)


def test_crop_loop_trace_replays_and_sowing_respects_season():
    assert _run(_game()) == _run(_game())
    out_of_season = _game(season="summer")
    context = out_of_season._context("Farmer")
    assert not any(option.get("action") == "sow" for option in context.affordances)
    crop = out_of_season.world.sow("Farmer", "wheat", land="farm_plot_00")
    assert crop is not None, "a sowing out of season is allowed (Phase 049): the seed is used"
    assert out_of_season.world.qty("wheat_seed") == 0.0
    out_of_season.world.pass_period()
    assert not out_of_season.world.crop_alive(crop), "the out-of-season crop fails to the season's weather"

