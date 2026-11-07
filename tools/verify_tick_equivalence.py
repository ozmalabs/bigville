#!/usr/bin/env python3
"""Compare Bigville's commit executors over a multi-turn run.

This is the final-gate replay for the tick-graph work.  It runs the same
scenario, seed, turn count and sequential turn semantics through the serial,
threaded and partitioned executors, then compares the semantic trace of every
turn (proposals, results, errors, continuations and the normalised world
state).  Node ids are deliberately not compared: they are an internal
allocation detail of concurrent commit.

Usage:

    python3 tools/verify_tick_equivalence.py --turns 32
    python3 tools/verify_tick_equivalence.py --turns 32 --scenario small

Exit code 0 means every executor produced the same semantic trace.  A
divergence prints the first differing turn and field.
"""
from __future__ import annotations

import argparse
import json
import sys

from bigville.api import create_game
from bigville.tick_trace import TurnTrace, first_divergence, semantic_step_trace


SMALL_SCENARIO = {
    "id": "tick_equivalence_room",
    "name": "Tick equivalence room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [2, 2]},
        {"name": "Cy", "role": "farmer", "backend": "simple", "home_cell": [3, 3]},
    ],
    "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {"metabolism": True, "ecology": False, "decay": False},
    "buildings": [],
    "laws": [],
    "policies": [],
    "charters": [],
}


def run_executor(*, scenario, seed: int, turns: int, executor: str) -> TurnTrace:
    game = create_game(scenario=scenario, seed=seed, default_backend="simple",
                       autonomous=True, llm_log=False, executor=executor,
                       turn_semantics="sequential")
    trace = TurnTrace()
    for _ in range(turns):
        result = game.step()
        if result.get("status") != "advanced":
            raise RuntimeError(f"{executor}: turn {trace.turns + 1} returned "
                               f"{result.get('status')!r}: {result}")
        trace.add_record(semantic_step_trace(game))
    return trace


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=int, default=32)
    parser.add_argument("--seed", type=int, default=305000)
    parser.add_argument("--scenario", default="town100",
                        help="'town100' or 'small'")
    parser.add_argument("--executors", default="serial,threaded,partitioned")
    args = parser.parse_args(argv)

    scenario = SMALL_SCENARIO if args.scenario == "small" else "town100"
    names = [name.strip() for name in args.executors.split(",") if name.strip()]
    if "serial" not in names:
        names.insert(0, "serial")

    traces = {}
    for name in names:
        traces[name] = run_executor(scenario=scenario, seed=args.seed,
                                    turns=args.turns, executor=name)

    baseline = traces["serial"]
    report = {"scenario": args.scenario, "seed": args.seed, "turns": args.turns,
              "digests": {name: trace.hexdigest() for name, trace in traces.items()},
              "comparisons": {}}
    ok = True
    for name, trace in traces.items():
        difference = first_divergence(baseline, trace)
        report["comparisons"][name] = difference
        if difference is not None:
            ok = False
    report["equivalent"] = ok
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
