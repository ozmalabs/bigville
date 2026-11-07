"""Benchmark the TG07 tick-graph executors on a synthetic grid town.

The scenario builder is import-safe: ``build_scenario(size)`` returns a scenario
dictionary without constructing a world, so tests can import this module without
running a benchmark.  ``main()`` builds ``N`` simple-backed residents on a
square grid, runs ``serial``, ``threaded`` and ``partitioned`` for the requested
sizes and prints both JSON and a compact markdown table.

Measurements (all with ``time.perf_counter``, construction excluded):

- ``step``: the whole ``BigvilleGame.step()`` call;
- ``context``: ``BigvilleGame._build_contexts`` (the frozen decision snapshot);
- ``world_tick``: ``BigvilleWorld.tick``;
- ``commit``: ``BigvilleGame._apply_turn`` (graph commit only).

Physical subsystems are off in the scenario for speed.  This is a local,
in-process benchmark; it does not measure network or process distribution.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

# Allow ``python3 tools/benchmark_tick_graph.py`` from the repository root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEFAULT_SEED = 305000
DEFAULT_SIZES = (50, 100, 200)
DEFAULT_TURNS = 2
DEFAULT_TIME_BUDGET = 120.0
DEFAULT_CELL_SIZE = 8

DISABLED_SUBSYSTEMS = {
    "metabolism": False,
    "ecology": False,
    "decay": False,
    "cognitive_practice": False,
    "training": False,
    "practice": False,
    "joint_actions": False,
}


def build_scenario(size: int, *, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """A deterministic ``size``-resident grid scenario for the benchmark.

    Residents are placed one per cell row-major on the smallest square grid
    that fits them.  Roles are ``resident`` and backends are the built-in
    ``simple`` policy, so no external service or model is involved.
    """
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ValueError("size must be a positive integer")
    side = 1
    while side * side < size:
        side += 1
    grid = [["floor"] * side for _ in range(side)]
    actors = []
    for index in range(size):
        actors.append({
            "name": f"Resident {index:04d}",
            "role": "resident",
            "backend": "simple",
            "home_cell": [index % side, index // side],
        })
    return {
        "id": f"tg07_bench_{size}",
        "name": f"TG07 benchmark town ({size} residents, seed {seed})",
        "map": {"grid": grid},
        "actors": actors,
        "initial": {"hour": 7.0, "weather": "clear", "temperature": 18.0},
        "physical_subsystems": dict(DISABLED_SUBSYSTEMS),
        "buildings": [],
        "laws": [],
        "policies": [],
        "charters": [],
    }


def build_game(size: int, executor: str = "serial", *, seed: int = DEFAULT_SEED):
    """Build one benchmark game without timing it."""
    from bigville.api import create_game

    return create_game(scenario=build_scenario(size, seed=seed), seed=seed,
                       default_backend="simple", autonomous=True, llm_log=False,
                       executor=executor)


class _Timer:
    """A cumulative wall-clock counter around one bound method."""

    def __init__(self) -> None:
        self.seconds = 0.0
        self.calls = 0

    def wrap(self, target: Any, name: str) -> None:
        original = getattr(target, name)

        def measured(*args, **kwargs):
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.seconds += time.perf_counter() - started
                self.calls += 1

        setattr(target, name, measured)


def _instrument(game: Any) -> dict[str, _Timer]:
    timers = {"context": _Timer(), "world_tick": _Timer(), "commit": _Timer()}
    timers["context"].wrap(game, "_build_contexts")
    timers["world_tick"].wrap(game.world, "tick")
    timers["commit"].wrap(game, "_apply_turn")
    return timers


def run_one(size: int, executor: str, *, turns: int, seed: int,
            time_budget: float) -> dict[str, Any]:
    """Run one ``(size, executor)`` cell and return its measurements."""
    game = build_game(size, executor, seed=seed)
    timers = _instrument(game)
    completed = 0
    step_seconds = 0.0
    started = time.perf_counter()
    skipped_reason = None
    for _ in range(max(1, turns)):
        turn_started = time.perf_counter()
        result = game.step()
        step_seconds += time.perf_counter() - turn_started
        if result.get("status") != "advanced":
            skipped_reason = f"status={result.get('status')}"
            break
        completed += 1
        if time.perf_counter() - started > time_budget:
            skipped_reason = f"time budget {time_budget:.1f}s exceeded"
            break

    plan = getattr(game, "last_shard_plan", None)
    row = {
        "size": size,
        "executor": executor,
        "turns_completed": completed,
        "turns_requested": max(1, turns),
        "step_seconds": round(step_seconds, 6),
        "per_turn_ms": round(1000.0 * step_seconds / max(1, completed), 3),
        "context_ms": round(1000.0 * timers["context"].seconds, 3),
        "world_tick_ms": round(1000.0 * timers["world_tick"].seconds, 3),
        "commit_ms": round(1000.0 * timers["commit"].seconds, 3),
        "actors": len(game.last_order) if game.last_order else size,
        "shards": (len(plan.by_shard) if plan is not None else None),
        "coordinator_units": (len(plan.coordinator_units) if plan is not None else None),
        "cross_shard_units": (len(plan.cross_shard) if plan is not None else None),
        "status": "skipped" if skipped_reason else "ok",
    }
    if skipped_reason:
        row["note"] = skipped_reason
    return row


def benchmark(sizes: Iterable[int], *, turns: int = DEFAULT_TURNS,
              seed: int = DEFAULT_SEED, time_budget: float = DEFAULT_TIME_BUDGET,
              executors: Iterable[str] = ("serial", "threaded", "partitioned"),
              progress: bool = False) -> dict[str, Any]:
    """Run every size/executor cell and return a JSON-friendly document."""
    results = []
    for size in sizes:
        for executor in executors:
            if progress:
                print(f"running size={size} executor={executor} turns={turns}",
                      file=sys.stderr, flush=True)
            row = run_one(size, executor, turns=turns, seed=seed,
                          time_budget=time_budget)
            results.append(row)
            if progress:
                print(f"  {row['status']}: {row['per_turn_ms']} ms/turn",
                      file=sys.stderr, flush=True)
    return {
        "seed": seed,
        "turns": turns,
        "time_budget_seconds": time_budget,
        "physical_subsystems": dict(DISABLED_SUBSYSTEMS),
        "results": results,
    }


def markdown_table(document: dict[str, Any]) -> str:
    """A compact table for the phase report."""
    lines = [
        "| size | executor | turns | ms/turn | context ms | world tick ms | commit ms | shards | coordinator | cross-shard | note |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in document["results"]:
        lines.append(
            "| {size} | {executor} | {turns_completed}/{turns_requested} | "
            "{per_turn_ms} | {context_ms} | {world_tick_ms} | {commit_ms} | "
            "{shards} | {coordinator_units} | {cross_shard_units} | {note} |".format(
                note=row.get("note", ""), **{key: row.get(key, "")
                                              for key in (
                                                  "size", "executor",
                                                  "turns_completed", "turns_requested",
                                                  "per_turn_ms", "context_ms",
                                                  "world_tick_ms", "commit_ms",
                                                  "shards", "coordinator_units",
                                                  "cross_shard_units")}))
    return "\n".join(lines)


def _parse_sizes(text: str) -> list[int]:
    sizes = [int(part) for part in text.split(",") if part.strip()]
    if not sizes or any(size < 1 for size in sizes):
        raise argparse.ArgumentTypeError("sizes must be positive integers")
    return sizes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=_parse_sizes,
                        default=list(DEFAULT_SIZES),
                        help="comma-separated resident counts (default 50,100,200)")
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS,
                        help="turns per cell (default 2)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--time-budget", type=float, default=DEFAULT_TIME_BUDGET,
                        help="seconds per size/executor cell before it is marked skipped")
    parser.add_argument("--json-only", action="store_true",
                        help="print the JSON document only")
    parser.add_argument("--progress", action="store_true",
                        help="print progress to stderr")
    args = parser.parse_args(argv)
    if args.turns < 1:
        parser.error("--turns must be positive")

    document = benchmark(args.sizes, turns=args.turns, seed=args.seed,
                         time_budget=args.time_budget, progress=args.progress)
    print(json.dumps(document, indent=2, sort_keys=True))
    if not args.json_only:
        print()
        print(markdown_table(document))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
