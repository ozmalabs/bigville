"""Benchmark affordance-menu construction against an observation-only context (LA01).

The lazy-affordances plan replaces the exhaustive per-turn legal-action menu
with observation/proposal/validation.  This benchmark measures the first half
of the cost question: how long does ``_context`` take when it builds the full
menu, versus the same context with the menu omitted?

Two paths are timed for every resident, with ``time.perf_counter`` and with
game construction excluded:

- ``menu``: ``game._context(actor)``, which calls ``actor_affordances()``;
- ``observe_only``: ``game._context(actor, skip_affordances=True)``, the LA01
  measurement seam.  This is not the lazy game path yet; LA01 only adds the
  seam and records the baseline.

The scenario builder is import-safe: ``build_scenario(size)`` comes from
``tools/benchmark_tick_graph.py`` and returns a scenario dictionary without
constructing a world.  ``main()`` prints a JSON document and a markdown table.
Physical subsystems are off in the scenario for speed.  This is an in-process
local measurement; it does not include backend decisions or enactment.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

# Allow ``python3 tools/benchmark_affordances.py`` from the repository root and
# let tests import this module without side effects.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools.benchmark_tick_graph import (  # noqa: E402  (path setup first)
    DEFAULT_SEED,
    DISABLED_SUBSYSTEMS,
    build_scenario,
)

DEFAULT_SIZES = (50, 100, 200)
DEFAULT_REPEATS = 1


def build_game(size: int, *, seed: int = DEFAULT_SEED):
    """Build one benchmark game with simple autonomous backends.

    The scenario already disables the physical subsystems, so the measured
    contexts are dominated by affordance construction rather than metabolism
    or ecology work.
    """
    from bigville.api import create_game

    return create_game(scenario=build_scenario(size, seed=seed), seed=seed,
                       default_backend="simple", autonomous=True, llm_log=False)


def _actors(game: Any) -> list[str]:
    return [name for name in game.backends if game.world.is_alive(name)]


def _time_pass(game: Any, actors: list[str], *, skip_affordances: bool) -> float:
    """Time one context build for every actor; no turn is advanced."""
    started = time.perf_counter()
    for actor in actors:
        game._context(actor, skip_affordances=skip_affordances)
    return time.perf_counter() - started


def measure_size(size: int, *, seed: int = DEFAULT_SEED,
                 repeats: int = DEFAULT_REPEATS) -> dict[str, Any]:
    """Measure menu and observation-only context builds for one size."""
    game = build_game(size, seed=seed)
    actors = _actors(game)
    menu_seconds = []
    observe_seconds = []
    for _ in range(max(1, repeats)):
        # Context construction publishes the practice window as a side effect.
        # Clear it before each pass so both paths see the same window.
        game._published_practice.clear()
        observe_seconds.append(_time_pass(game, actors, skip_affordances=True))
        game._published_practice.clear()
        menu_seconds.append(_time_pass(game, actors, skip_affordances=False))
    count = max(1, len(actors))
    menu_total = sum(menu_seconds) / len(menu_seconds)
    observe_total = sum(observe_seconds) / len(observe_seconds)
    return {
        "size": size,
        "actors": len(actors),
        "repeats": max(1, repeats),
        "menu_seconds": round(menu_total, 6),
        "menu_ms_per_actor": round(1000.0 * menu_total / count, 6),
        "observe_only_seconds": round(observe_total, 6),
        "observe_only_ms_per_actor": round(1000.0 * observe_total / count, 6),
        "ratio_menu_over_observe": (round(menu_total / observe_total, 3)
                                    if observe_total > 0 else None),
    }


def benchmark(sizes: Iterable[int], *, seed: int = DEFAULT_SEED,
              repeats: int = DEFAULT_REPEATS) -> dict[str, Any]:
    """Run every size and return a JSON-friendly document."""
    return {
        "seed": seed,
        "repeats": max(1, repeats),
        "physical_subsystems": dict(DISABLED_SUBSYSTEMS),
        "note": ("observe_only uses _context(..., skip_affordances=True); "
                 "it is a measurement seam in LA01, not the lazy play path"),
        "results": [measure_size(size, seed=seed, repeats=repeats)
                    for size in sizes],
    }


def markdown_table(document: dict[str, Any]) -> str:
    """A compact table for the phase report."""
    lines = [
        "| size | actors | menu total ms | menu ms/actor | "
        "observe total ms | observe ms/actor | ratio |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in document["results"]:
        lines.append(
            "| {size} | {actors} | {menu_ms} | {menu_per} | {obs_ms} | "
            "{obs_per} | {ratio}x |".format(
                size=row["size"], actors=row["actors"],
                menu_ms=round(1000.0 * row["menu_seconds"], 3),
                menu_per=round(row["menu_ms_per_actor"], 3),
                obs_ms=round(1000.0 * row["observe_only_seconds"], 3),
                obs_per=round(row["observe_only_ms_per_actor"], 3),
                ratio=row["ratio_menu_over_observe"]))
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
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS,
                        help="timed passes per path and size (default 1)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--json-only", action="store_true",
                        help="print the JSON document only")
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be positive")

    document = benchmark(args.sizes, seed=args.seed, repeats=args.repeats)
    print(json.dumps(document, indent=2, sort_keys=True))
    if not args.json_only:
        print()
        print(markdown_table(document))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
