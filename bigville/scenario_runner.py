"""Unattended authored-scenario runs with compact observational traces."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .api import create_game
from .scenarios import load_scenario


def _jsonable(value: Any):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _compact_state(world):
    state = world.export_state(event_tail=20)
    actors = {}
    for actor in state.get("residents", []):
        actors[actor["id"]] = {key: actor.get(key) for key in (
            "alive", "health", "hunger", "energy", "position", "inventory", "held_items")}
    return {"turn": int(world._turn),
            "period": float(world.eng.node(world._town)["attrs"].get("period", 0.0)),
            "calendar": _jsonable(world.calendar()),
            "actors": actors,
            "stocks": _jsonable(state.get("stocks", {})),
            "physical_objects": {
                str(item["id"]): _jsonable(item)
                for item in state.get("physical_objects", []) if "id" in item
            },
            "events": {str(item["id"]): _jsonable(item)
                       for item in state.get("events", []) if "id" in item}}


def _delta(before, after):
    def changed(before_map, after_map):
        return {key: {"before": before_map.get(key), "after": after_map.get(key)}
                for key in sorted(set(before_map) | set(after_map))
                if before_map.get(key) != after_map.get(key)}

    actor_changes = {}
    for actor in sorted(set(before["actors"]) | set(after["actors"])):
        fields = changed(before["actors"].get(actor, {}), after["actors"].get(actor, {}))
        if fields:
            actor_changes[actor] = fields
    return {"actors": actor_changes,
            "stocks": changed(before.get("stocks", {}), after.get("stocks", {})),
            "physical_objects": changed(before.get("physical_objects", {}),
                                         after.get("physical_objects", {})),
            "events": changed(before.get("events", {}), after.get("events", {}))}


def _observed_contexts(game):
    """Capture backend inputs without leaving affordance target caches changed."""
    world = game.world
    actor_targets = {actor: dict(targets)
                     for actor, targets in world._actor_targets.items()}
    try:
        return {actor: game._context(actor) for actor in game.backends
                if world.is_alive(actor)}
    finally:
        world._actor_targets.clear()
        world._actor_targets.update(actor_targets)


def run_scenario(scenario, *, seed=305000, turns=1, ticks_per_period="world",
                 backend=None, default_backend="simple"):
    """Run a fixed number of real game turns and return a JSON-safe trace.

    The runner always creates an unattended game. It records each backend's
    input and proposal around the existing game step, then reads physical state;
    tracing adds no actions or state updates to the game.
    """
    if not isinstance(turns, int) or isinstance(turns, bool) or turns < 0:
        raise ValueError("turns must be a non-negative integer")
    scenario_arg = scenario
    if backend is not None and not (isinstance(scenario, str)
                                    and scenario in {"town100", "default"}):
        definition = load_scenario(scenario).to_dict()
        definition["actors"] = [dict(actor, backend=backend)
                                for actor in definition.get("actors", [])]
        scenario_arg = definition
    game = create_game(scenario=scenario_arg, seed=seed, autonomous=True,
                       default_backend=default_backend,
                       ticks_per_period=ticks_per_period)
    world = game.world
    initial = _compact_state(world)
    initial_state = initial
    steps = []
    for _ in range(turns):
        # _context publishes affordances, which rebuilds temporary target-key
        # maps used by action enactment. Save and restore those derived caches
        # so collecting the trace is observational.
        contexts = _observed_contexts(game)
        result = game.step()
        if result["status"] == "waiting":
            # An unattended run must never silently stop on a human decision.
            raise RuntimeError(f"unattended scenario is waiting for {result['actor']}")
        final = _compact_state(world)
        records = []
        for actor, context in contexts.items():
            response = game.last_responses.get(actor)
            proposal = response.major_action if response else None
            records.append({
                "actor": actor,
                "observations": _jsonable(context.observations),
                "affordances": _jsonable(context.affordances),
                "selected_action": ({"action": proposal.action,
                                     "params": _jsonable(proposal.params),
                                     "reason": proposal.reason} if proposal else None),
                "result": game.last_results.get(actor),
            })
        period_changed = final["period"] != initial["period"]
        steps.append({"turn": final["turn"], "actors": records,
                      "state_delta": _delta(initial, final),
                      "period_transition": ({"period": final["period"],
                                             "calendar": final["calendar"]}
                                            if period_changed else None)})
        initial = final
    trace = {"schema": "bigville/scenario-trace/1", "scenario": world._scenario_data.get("id"),
            "seed": seed, "turns_requested": turns, "ticks_per_period": game.ticks_per_period,
            "backend_override": backend, "default_backend": default_backend,
            "initial_state": initial_state,
            "steps": steps, "final_state": _compact_state(world)}
    if hasattr(world, "physical_subsystems"):
        trace["physical_subsystems"] = _jsonable(world.physical_subsystems)
    return trace


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run an authored Bigville scenario unattended")
    parser.add_argument("scenario", help="scenario id or JSON path")
    parser.add_argument("--seed", type=int, default=305000)
    parser.add_argument("--turns", type=int, default=1)
    parser.add_argument("--ticks-per-period", type=int, default=None,
                        help="clock ticks per period (default: the world's TIME table)")
    parser.add_argument("--backend", help="override every actor backend")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    trace = run_scenario(args.scenario, seed=args.seed, turns=args.turns,
                         ticks_per_period=(args.ticks_per_period
                                           if args.ticks_per_period is not None else "world"),
                         backend=args.backend)
    encoded = json.dumps(trace, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
