"""Benchmark menu construction against the real lazy context and whole turns.

The lazy-affordances plan replaces the exhaustive per-turn legal-action menu
with observation/proposal/validation.  This benchmark measures how long
``_context`` takes when it builds the full menu, when it takes the real lazy
path, and when the LA01 observation-only seam omits the menu.

Three context paths are timed for every resident, with ``time.perf_counter``
and with game construction excluded:

- ``menu``: ``game._context(actor)`` in a menu-mode game, which calls
  ``actor_affordances()``;
- ``lazy``: ``game._context(actor)`` in a lazy-mode game, the real LA03-LA06
  observation/proposal path;
- ``observe_only``: ``game._context(actor, skip_affordances=True)``, the LA01
  measurement seam.  It is kept as the original baseline, not as the lazy path.

``--turns`` additionally times whole ``game.step()`` calls for a fresh menu
game and a fresh lazy game at each size, so context and total turn cost are
reported together.  Construction is excluded from every measurement.

The scenario builder is import-safe: ``build_scenario(size)`` comes from
``tools/benchmark_tick_graph.py`` and returns a scenario dictionary without
constructing a world.  ``main()`` prints a JSON document and a markdown table.
Physical subsystems are off in the scenario for speed.  This is an in-process
local measurement: context passes exclude backend decisions and enactment,
while the optional ``--turns`` measurement includes them.
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
DEFAULT_TURNS = 1


def build_game(size: int, *, seed: int = DEFAULT_SEED, mode: str = "menu"):
    """Build one benchmark game with simple autonomous backends.

    The scenario already disables the physical subsystems, so the measured
    contexts are dominated by affordance construction rather than metabolism
    or ecology work.  ``mode`` is ``"menu"`` or ``"lazy"``.
    """
    from bigville.api import create_game

    return create_game(scenario=build_scenario(size, seed=seed), seed=seed,
                       default_backend="simple", autonomous=True, llm_log=False,
                       affordance_mode=mode)


def _actors(game: Any) -> list[str]:
    return [name for name in game.backends if game.world.is_alive(name)]


def _time_pass(game: Any, actors: list[str], *, skip_affordances: bool) -> float:
    """Time one context build for every actor; no turn is advanced."""
    started = time.perf_counter()
    for actor in actors:
        game._context(actor, skip_affordances=skip_affordances)
    return time.perf_counter() - started


def _time_turns(game: Any, turns: int) -> list[float]:
    """Time whole ``step()`` calls on one already-constructed game."""
    seconds = []
    for _ in range(max(0, int(turns))):
        started = time.perf_counter()
        result = game.step()
        seconds.append(time.perf_counter() - started)
        if result.get("status") != "advanced":
            break
    return seconds


def measure_size(size: int, *, seed: int = DEFAULT_SEED,
                 repeats: int = DEFAULT_REPEATS,
                 turns: int = DEFAULT_TURNS) -> dict[str, Any]:
    """Measure menu, lazy and observation-only contexts plus turn time."""
    menu_game = build_game(size, seed=seed, mode="menu")
    lazy_game = build_game(size, seed=seed, mode="lazy")
    actors = _actors(menu_game)
    menu_seconds = []
    lazy_seconds = []
    observe_seconds = []
    for _ in range(max(1, repeats)):
        # Context construction publishes the practice window as a side effect.
        # Clear it before each pass so every path sees the same window.
        menu_game._published_practice.clear()
        observe_seconds.append(_time_pass(menu_game, actors,
                                          skip_affordances=True))
        menu_game._published_practice.clear()
        menu_seconds.append(_time_pass(menu_game, actors,
                                       skip_affordances=False))
        lazy_game._published_practice.clear()
        lazy_seconds.append(_time_pass(lazy_game, actors,
                                       skip_affordances=False))
    count = max(1, len(actors))
    menu_total = sum(menu_seconds) / len(menu_seconds)
    lazy_total = sum(lazy_seconds) / len(lazy_seconds)
    observe_total = sum(observe_seconds) / len(observe_seconds)
    menu_turns = _time_turns(menu_game, turns)
    lazy_turns = _time_turns(lazy_game, turns)
    return {
        "size": size,
        "actors": len(actors),
        "repeats": max(1, repeats),
        "turns": max(0, int(turns)),
        "menu_seconds": round(menu_total, 6),
        "menu_ms_per_actor": round(1000.0 * menu_total / count, 6),
        "lazy_seconds": round(lazy_total, 6),
        "lazy_ms_per_actor": round(1000.0 * lazy_total / count, 6),
        "observe_only_seconds": round(observe_total, 6),
        "observe_only_ms_per_actor": round(1000.0 * observe_total / count, 6),
        "ratio_menu_over_observe": (round(menu_total / observe_total, 3)
                                    if observe_total > 0 else None),
        "ratio_menu_over_lazy": (round(menu_total / lazy_total, 3)
                                 if lazy_total > 0 else None),
        "menu_turn_seconds": round(sum(menu_turns), 6),
        "lazy_turn_seconds": round(sum(lazy_turns), 6),
        "ratio_menu_turn_over_lazy_turn": (
            round(sum(menu_turns) / sum(lazy_turns), 3)
            if sum(lazy_turns) > 0 else None),
    }


def benchmark(sizes: Iterable[int], *, seed: int = DEFAULT_SEED,
              repeats: int = DEFAULT_REPEATS,
              turns: int = DEFAULT_TURNS) -> dict[str, Any]:
    """Run every size and return a JSON-friendly document."""
    return {
        "seed": seed,
        "repeats": max(1, repeats),
        "turns": max(0, int(turns)),
        "physical_subsystems": dict(DISABLED_SUBSYSTEMS),
        "note": ("lazy is the real lazy _context path; observe_only is the "
                 "LA01 skip_affordances measurement seam, kept for baseline. "
                 "Turn time is step() only and excludes construction."),
        "results": [measure_size(size, seed=seed, repeats=repeats, turns=turns)
                    for size in sizes],
    }


def markdown_table(document: dict[str, Any]) -> str:
    """A compact table for the phase report."""
    lines = [
        "| size | actors | menu ctx ms | lazy ctx ms | observe ms | "
        "menu/lazy ctx | menu turn ms | lazy turn ms | menu/lazy turn |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in document["results"]:
        lines.append(
            "| {size} | {actors} | {menu_ms} | {lazy_ms} | {obs_ms} | "
            "{ctx_ratio}x | {menu_turn} | {lazy_turn} | {turn_ratio}x |".format(
                size=row["size"], actors=row["actors"],
                menu_ms=round(1000.0 * row["menu_seconds"], 3),
                lazy_ms=round(1000.0 * row["lazy_seconds"], 3),
                obs_ms=round(1000.0 * row["observe_only_seconds"], 3),
                ctx_ratio=row["ratio_menu_over_lazy"],
                menu_turn=round(1000.0 * row["menu_turn_seconds"], 3),
                lazy_turn=round(1000.0 * row["lazy_turn_seconds"], 3),
                turn_ratio=row["ratio_menu_turn_over_lazy_turn"]))
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
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS,
                        help="whole steps to time per mode and size (default 1)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--json-only", action="store_true",
                        help="print the JSON document only")
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if args.turns < 0:
        parser.error("--turns must not be negative")

    document = benchmark(args.sizes, seed=args.seed, repeats=args.repeats,
                         turns=args.turns)
    print(json.dumps(document, indent=2, sort_keys=True))
    if not args.json_only:
        print()
        print(markdown_table(document))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
