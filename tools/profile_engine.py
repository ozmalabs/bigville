#!/usr/bin/env python3
"""Profile one Bigville turn as the components later ENGINE_SPEEDUPS phases change.

The tool builds the deterministic synthetic town from
``tools.benchmark_tick_graph.build_scenario(size)`` and runs autonomous
``simple``-backed residents.  Construction is excluded from every measurement.
An optional cProfile pass prints the top cumulative functions for the same
size/turns request.

Measured with ``time.perf_counter``, per turn and cumulated over the run:

- ``step``: the whole ``BigvilleGame.step()`` call (measured around the call);
- ``context``: ``BigvilleGame._build_contexts`` (the frozen decision snapshot);
- ``world_tick``: ``BigvilleWorld.tick``, including its own ``_run`` passes;
- ``commit``: ``BigvilleGame._apply_turn``.  This **includes** ``finish``
  because the serial commit calls ``_finish_turn`` at its end;
- ``finish``: ``BigvilleGame._finish_turn`` (turn bookkeeping, report and
  snapshot), a subset of ``commit``;
- ``snapshot``: ``BigvilleGame.snapshot``, a subset of ``finish``.  It is shown
  separately and must not be added to the component total.

``commit_excluding_finish = commit - finish`` is derived so the components add
up: ``step = context + world_tick + commit_excluding_finish + finish + other``
where ``other`` is the residual (backend decisions, ordering, tick graph and
joint resolution, animal turn, and timer overhead).  Counts are deltas of calls
made in the turn: ``world._run``, ``eng.node``, ``world.actors_near``, plus
proposals/applied actions from the turn result.

Physical subsystems are off in the scenario for speed; this is an in-process
local measurement with no external service or model.

Usage::

    python3 tools/profile_engine.py --sizes 50,100 --turns 2
    python3 tools/profile_engine.py --size 50 --turns 1 --profile
"""
from __future__ import annotations

import argparse
import cProfile
import functools
import io
import json
import pstats
import sys
import time
from pathlib import Path
from typing import Any, Iterable

# Allow ``python3 tools/profile_engine.py`` from the repository root and let
# tests import this module without building anything.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.benchmark_tick_graph import (  # noqa: E402  (path setup first)
    DEFAULT_SEED,
    DISABLED_SUBSYSTEMS,
    build_scenario,
)

DEFAULT_SIZE = 50
DEFAULT_TURNS = 2
DEFAULT_AFFORDANCE_MODE = "lazy"
DEFAULT_SNAPSHOT_MODE = "every_turn"
DEFAULT_RULE_BATCHING = "action"
DEFAULT_EXECUTOR = "serial"
DEFAULT_TIME_BUDGET = 120.0
PROFILE_FUNCTIONS = 35

COMPONENTS_NOTE = (
    "Per turn, construction excluded. step is the whole game.step(). "
    "context=_build_contexts, world_tick=world.tick (its _run passes "
    "included), commit=_apply_turn. commit includes finish (_finish_turn); "
    "commit_excluding_finish=commit-finish gives the additive split. finish "
    "includes snapshot; snapshot is a subset of finish and is not added to the "
    "total. other=step-context-world_tick-commit (backend decisions, ordering, "
    "tick graph, joint resolution, animal turn, wrapper overhead). Counts are "
    "call deltas during the turn."
)


def build_game(size: int, *, seed: int = DEFAULT_SEED,
               affordance_mode: str = DEFAULT_AFFORDANCE_MODE,
               snapshot_mode: str = DEFAULT_SNAPSHOT_MODE,
               rule_batching: str = DEFAULT_RULE_BATCHING,
               executor: str = DEFAULT_EXECUTOR):
    """Build one benchmark game without timing it."""
    from bigville.api import create_game

    return create_game(scenario=build_scenario(size, seed=seed), seed=seed,
                       default_backend="simple", autonomous=True, llm_log=False,
                       affordance_mode=affordance_mode,
                       snapshot_mode=snapshot_mode,
                       rule_batching=rule_batching, executor=executor)


class _Timer:
    """A cumulative wall-clock counter and call count around one method."""

    def __init__(self) -> None:
        self.seconds = 0.0
        self.calls = 0

    def wrap(self, target: Any, name: str) -> None:
        original = getattr(target, name)

        @functools.wraps(original)
        def measured(*args, **kwargs):
            started = time.perf_counter()
            self.calls += 1
            try:
                return original(*args, **kwargs)
            finally:
                self.seconds += time.perf_counter() - started

        setattr(target, name, measured)

    def state(self) -> tuple[float, int]:
        return self.seconds, self.calls


INSTRUMENTED = {
    "context": ("game", "_build_contexts"),
    "world_tick": ("world", "tick"),
    "commit": ("game", "_apply_turn"),
    "finish": ("game", "_finish_turn"),
    "snapshot": ("game", "snapshot"),
    "run": ("world", "_run"),
    "node": ("eng", "node"),
    "actors_near": ("world", "actors_near"),
}


def instrument(game: Any) -> dict[str, _Timer]:
    """Wrap each component method once; return the timers by component name."""
    targets = {"game": game, "world": game.world, "eng": game.world.eng}
    timers = {name: _Timer() for name in INSTRUMENTED}
    for name, (target_name, method) in INSTRUMENTED.items():
        timers[name].wrap(targets[target_name], method)
    return timers


def _state(timers: dict[str, _Timer]) -> dict[str, tuple[float, int]]:
    return {name: timer.state() for name, timer in timers.items()}


def _delta(before: dict[str, tuple[float, int]],
           after: dict[str, tuple[float, int]]) -> dict[str, tuple[float, int]]:
    return {name: (after[name][0] - before[name][0],
                   after[name][1] - before[name][1])
            for name in after}


def _applied(result: dict[str, Any], game: Any) -> int:
    """Actors whose major action the turn applied (truthy last_results)."""
    return sum(1 for value in dict(getattr(game, "last_results", {}) or {}).values()
               if value)


def _proposed(game: Any) -> int:
    return sum(1 for response in dict(getattr(game, "last_responses", {}) or {}).values()
               if getattr(response, "major_action", None) is not None)


def run_one(size: int, *, turns: int = DEFAULT_TURNS, seed: int = DEFAULT_SEED,
            affordance_mode: str = DEFAULT_AFFORDANCE_MODE,
            snapshot_mode: str = DEFAULT_SNAPSHOT_MODE,
            rule_batching: str = DEFAULT_RULE_BATCHING,
            executor: str = DEFAULT_EXECUTOR,
            time_budget: float = DEFAULT_TIME_BUDGET) -> dict[str, Any]:
    """Run one size and return per-turn component measurements."""
    game = build_game(size, seed=seed, affordance_mode=affordance_mode,
                      snapshot_mode=snapshot_mode, rule_batching=rule_batching,
                      executor=executor)
    timers = instrument(game)
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    skipped_reason: str | None = None
    for index in range(max(1, int(turns))):
        if time.perf_counter() - started > time_budget:
            skipped_reason = f"time budget {time_budget:.1f}s exceeded"
            break
        before = _state(timers)
        step_started = time.perf_counter()
        result = game.step()
        step_seconds = time.perf_counter() - step_started
        delta = _delta(before, _state(timers))
        status = str(result.get("status", "unknown"))
        context = delta["context"][0]
        world_tick = delta["world_tick"][0]
        commit = delta["commit"][0]
        finish = delta["finish"][0]
        snapshot = delta["snapshot"][0]
        commit_excluding_finish = max(0.0, commit - finish)
        other = max(0.0, step_seconds - context - world_tick - commit)
        rows.append({
            "turn": index + 1,
            "world_turn": int(getattr(game.world, "_turn", 0)),
            "status": status,
            "step_seconds": round(step_seconds, 6),
            "context_seconds": round(context, 6),
            "world_tick_seconds": round(world_tick, 6),
            "commit_total_seconds": round(commit, 6),
            "commit_excluding_finish_seconds": round(commit_excluding_finish, 6),
            "finish_seconds": round(finish, 6),
            "snapshot_seconds": round(snapshot, 6),
            "other_seconds": round(other, 6),
            "run_calls": int(delta["run"][1]),
            "node_calls": int(delta["node"][1]),
            "actors_near_calls": int(delta["actors_near"][1]),
            "proposed": _proposed(game),
            "applied": _applied(result, game),
        })
        if status != "advanced":
            skipped_reason = f"status={status}"
            break

    completed = len(rows)
    sums = {
        "step": sum(row["step_seconds"] for row in rows),
        "context": sum(row["context_seconds"] for row in rows),
        "world_tick": sum(row["world_tick_seconds"] for row in rows),
        "commit_total": sum(row["commit_total_seconds"] for row in rows),
        "commit_excluding_finish": sum(
            row["commit_excluding_finish_seconds"] for row in rows),
        "finish": sum(row["finish_seconds"] for row in rows),
        "snapshot": sum(row["snapshot_seconds"] for row in rows),
        "other": sum(row["other_seconds"] for row in rows),
    }
    counts = {
        "run_calls": sum(row["run_calls"] for row in rows),
        "node_calls": sum(row["node_calls"] for row in rows),
        "actors_near_calls": sum(row["actors_near_calls"] for row in rows),
        "proposed": sum(row["proposed"] for row in rows),
        "applied": sum(row["applied"] for row in rows),
    }
    denominator = max(1, completed)

    def ms(value: float) -> float:
        return round(1000.0 * value, 3)

    per_turn = {
        "step_ms": ms(sums["step"] / denominator),
        "context_ms": ms(sums["context"] / denominator),
        "world_tick_ms": ms(sums["world_tick"] / denominator),
        "commit_ms": ms(sums["commit_excluding_finish"] / denominator),
        "commit_total_ms": ms(sums["commit_total"] / denominator),
        "finish_ms": ms(sums["finish"] / denominator),
        "snapshot_ms": ms(sums["snapshot"] / denominator),
        "other_ms": ms(sums["other"] / denominator),
        "run_calls": round(counts["run_calls"] / denominator, 3),
        "node_calls": round(counts["node_calls"] / denominator, 3),
        "actors_near_calls": round(counts["actors_near_calls"] / denominator, 3),
        "proposed": round(counts["proposed"] / denominator, 3),
        "applied": round(counts["applied"] / denominator, 3),
    }
    return {
        "size": size,
        "affordance_mode": affordance_mode,
        "snapshot_mode": snapshot_mode,
        "rule_batching": rule_batching,
        "executor": executor,
        "turns_completed": completed,
        "turns_requested": max(1, int(turns)),
        "status": "skipped" if skipped_reason else "ok",
        "note": skipped_reason or "",
        "total_seconds": round(sums["step"], 6),
        "per_turn": per_turn,
        "totals": {
            "step_seconds": round(sums["step"], 6),
            "context_seconds": round(sums["context"], 6),
            "world_tick_seconds": round(sums["world_tick"], 6),
            "commit_total_seconds": round(sums["commit_total"], 6),
            "commit_excluding_finish_seconds": round(
                sums["commit_excluding_finish"], 6),
            "finish_seconds": round(sums["finish"], 6),
            "snapshot_seconds": round(sums["snapshot"], 6),
            "other_seconds": round(sums["other"], 6),
            **counts,
        },
        "turns": rows,
    }


def profile_run(size: int, *, turns: int = DEFAULT_TURNS, seed: int = DEFAULT_SEED,
                affordance_mode: str = DEFAULT_AFFORDANCE_MODE,
                snapshot_mode: str = DEFAULT_SNAPSHOT_MODE,
                rule_batching: str = DEFAULT_RULE_BATCHING,
                executor: str = DEFAULT_EXECUTOR,
                limit: int = PROFILE_FUNCTIONS) -> dict[str, Any]:
    """cProfile the same size/turns request and return the top functions."""
    game = build_game(size, seed=seed, affordance_mode=affordance_mode,
                      snapshot_mode=snapshot_mode, rule_batching=rule_batching,
                      executor=executor)
    profiler = cProfile.Profile()
    profiler.enable()
    completed = 0
    try:
        for _ in range(max(1, int(turns))):
            result = game.step()
            completed += 1
            if result.get("status") != "advanced":
                break
    finally:
        profiler.disable()
    stream = io.StringIO()
    try:
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats("cumulative").print_stats(limit)
        text = stream.getvalue()
    finally:
        stream.close()
    return {
        "size": size,
        "turns_completed": completed,
        "affordance_mode": affordance_mode,
        "snapshot_mode": snapshot_mode,
        "rule_batching": rule_batching,
        "executor": executor,
        "functions": limit,
        "text": text,
    }


def profile(sizes: Iterable[int], *, turns: int = DEFAULT_TURNS,
            seed: int = DEFAULT_SEED,
            affordance_mode: str = DEFAULT_AFFORDANCE_MODE,
            snapshot_mode: str = DEFAULT_SNAPSHOT_MODE,
            rule_batching: str = DEFAULT_RULE_BATCHING,
            executor: str = DEFAULT_EXECUTOR,
            time_budget: float = DEFAULT_TIME_BUDGET) -> dict[str, Any]:
    """Run every size and return a JSON-friendly document."""
    return {
        "seed": seed,
        "turns": max(1, int(turns)),
        "affordance_mode": affordance_mode,
        "snapshot_mode": snapshot_mode,
        "rule_batching": rule_batching,
        "executor": executor,
        "time_budget_seconds": time_budget,
        "physical_subsystems": dict(DISABLED_SUBSYSTEMS),
        "components_note": COMPONENTS_NOTE,
        "results": [run_one(size, turns=turns, seed=seed,
                            affordance_mode=affordance_mode,
                            snapshot_mode=snapshot_mode,
                            rule_batching=rule_batching,
                            executor=executor, time_budget=time_budget)
                    for size in sizes],
    }


def markdown_table(document: dict[str, Any]) -> str:
    """A compact table for the phase report."""
    lines = [
        "| size | mode | batching | snapshot | turns | step ms/turn | context ms | world tick ms | "
        "commit ms | finish ms | snapshot ms (subset) | other ms | "
        "_run/turn | node/turn | near/turn | applied/turn | note |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in document["results"]:
        cell = row["per_turn"]
        lines.append(
            "| {size} | {mode} | {batching} | {snap_mode} | {done}/{asked} | {step} | {context} | "
            "{tick} | {commit} | {finish} | {snapshot} | {other} | {run} | "
            "{node} | {near} | {applied} | {note} |".format(
                size=row["size"], mode=row["affordance_mode"],
                batching=row.get("rule_batching", DEFAULT_RULE_BATCHING),
                snap_mode=row.get("snapshot_mode", DEFAULT_SNAPSHOT_MODE),
                done=row["turns_completed"], asked=row["turns_requested"],
                step=cell["step_ms"], context=cell["context_ms"],
                tick=cell["world_tick_ms"], commit=cell["commit_ms"],
                finish=cell["finish_ms"], snapshot=cell["snapshot_ms"],
                other=cell["other_ms"], run=cell["run_calls"],
                node=cell["node_calls"], near=cell["actors_near_calls"],
                applied=cell["applied"], note=row.get("note", "")))
    return "\n".join(lines)


def _parse_sizes(text: str) -> list[int]:
    sizes = [int(part) for part in text.split(",") if part.strip()]
    if not sizes or any(size < 1 for size in sizes):
        raise argparse.ArgumentTypeError("sizes must be positive integers")
    return sizes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE,
                        help=f"single resident count (default {DEFAULT_SIZE})")
    parser.add_argument("--sizes", type=_parse_sizes, default=None,
                        help="comma-separated resident counts (overrides --size)")
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS,
                        help=f"turns per size (default {DEFAULT_TURNS})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--affordance-mode", default=DEFAULT_AFFORDANCE_MODE,
                        choices=["lazy", "menu"],
                        help="lazy (default) or the exhaustive menu")
    parser.add_argument("--snapshot-mode", default=DEFAULT_SNAPSHOT_MODE,
                        choices=["every_turn", "on_demand", "auto"],
                        help="snapshot mode (default every_turn)")
    parser.add_argument("--rule-batching", default=DEFAULT_RULE_BATCHING,
                        choices=["action", "turn"],
                        help="world-rule batching (default action)")
    parser.add_argument("--executor", default=DEFAULT_EXECUTOR,
                        choices=["serial", "threaded", "partitioned"],
                        help="commit executor (default serial)")
    parser.add_argument("--profile", action="store_true",
                        help="also cProfile the run and print top cumulative functions")
    parser.add_argument("--profile-size", type=int, default=None,
                        help="size for the cProfile pass (default: first size)")
    parser.add_argument("--profile-limit", type=int, default=PROFILE_FUNCTIONS,
                        help=f"functions to print (default {PROFILE_FUNCTIONS})")
    parser.add_argument("--time-budget", type=float, default=DEFAULT_TIME_BUDGET,
                        help="seconds per size before it is marked skipped")
    parser.add_argument("--json", action="store_true",
                        help="print only the JSON document (skip the markdown table)")
    args = parser.parse_args(argv)
    if args.turns < 1:
        parser.error("--turns must be positive")
    if args.size < 1:
        parser.error("--size must be positive")
    if args.time_budget <= 0:
        parser.error("--time-budget must be positive")

    sizes = args.sizes if args.sizes is not None else [args.size]
    document = profile(sizes, turns=args.turns, seed=args.seed,
                       affordance_mode=args.affordance_mode,
                       snapshot_mode=args.snapshot_mode,
                       rule_batching=args.rule_batching,
                       executor=args.executor, time_budget=args.time_budget)
    print(json.dumps(document, indent=2, sort_keys=True))
    if not args.json:
        print()
        print(markdown_table(document))
        print()
        print("Components:", COMPONENTS_NOTE)
    if args.profile:
        profile_size = args.profile_size if args.profile_size is not None else sizes[0]
        result = profile_run(profile_size, turns=args.turns, seed=args.seed,
                             affordance_mode=args.affordance_mode,
                             snapshot_mode=args.snapshot_mode,
                             rule_batching=args.rule_batching,
                             executor=args.executor, limit=args.profile_limit)
        print()
        print(f"cProfile top {result['functions']} by cumulative time "
              f"(size={result['size']}, turns={result['turns_completed']}):")
        print(result["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
