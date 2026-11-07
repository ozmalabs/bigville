#!/usr/bin/env python3
"""Evaluate ``affordance_mode="menu"`` against ``affordance_mode="lazy"`` (LA06).

The tool builds the same scenario and seed twice, uses the built-in simple
(cheap) autonomous backend in both runs, and executes the same number of
turns.  It records, per turn and in total:

- step status, proposals, applied and refused actions;
- refusals by reason (the delta of the world's cumulative refusal counter);
- actions by kind (proposals and applied actions separately);
- survivors, mean hunger, mean energy and mean health;
- work/trade evidence that the world actually reports;
- wall-clock step and context-build time.

No external service, model or network call is used.  ``main`` is import-safe:
the builder functions can be imported and called without running a scenario.

Usage::

    python3 tools/evaluate_affordance_modes.py --scenario town100 \
        --seed 305000 --turns 8 --modes menu,lazy
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

# Run from the repository root and import from tools/tests without executing.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEFAULT_SCENARIO = "town100"
DEFAULT_SEED = 305000
DEFAULT_TURNS = 8
DEFAULT_MODES = ("menu", "lazy")
DEFAULT_RULE_BATCHING = "action"
DEFAULT_TIMEOUT = 180.0
SCENARIOS = ("town100", "resource_social_stress", "small")

# The small TG01/TG03-style room used by the tick-graph and lazy tests.  It is
# deliberately local to this tool so the evaluation does not depend on a test
# module.  Three simple residents, no external services, metabolism on.
SMALL_SCENARIO = {
    "id": "la06_small_room",
    "name": "LA06 small room",
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


def scenario_definition(scenario: str) -> Any:
    """Resolve a CLI scenario name to ``create_game``'s scenario argument."""
    if scenario == "small":
        return dict(SMALL_SCENARIO)
    if scenario in {"town100", "resource_social_stress"}:
        return scenario
    raise ValueError(f"unknown scenario {scenario!r}; choose from {list(SCENARIOS)}")


def build_game(scenario: str, mode: str, *, seed: int = DEFAULT_SEED,
               rule_batching: str = DEFAULT_RULE_BATCHING):
    """Build one autonomous simple-backed game in the requested mode."""
    from bigville.api import create_game

    return create_game(
        scenario=scenario_definition(scenario), seed=seed,
        default_backend="simple", autonomous=True, llm_log=False,
        affordance_mode=mode, rule_batching=rule_batching)


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


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _mean(values: Iterable[float]) -> float | None:
    values = [float(value) for value in values]
    return round(sum(values) / len(values), 6) if values else None


def _alive_actors(game: Any) -> list[str]:
    return [name for name in game.backends if game.world.is_alive(name)]


def _action_of(response: Any) -> str:
    action = getattr(response, "major_action", None)
    return str(getattr(action, "action", "")) if action is not None else ""


def _turn_metrics(game: Any) -> dict[str, Any]:
    alive = _alive_actors(game)
    health_states: Counter[str] = Counter()
    for name in alive:
        attrs = game.world.eng.node(game.world._actors[name])["attrs"]
        health_states[str(attrs.get("health", "unknown"))] += 1
    health_values = [game.world.health(name) for name in alive]
    return {
        "alive": len(alive),
        "hunger_mean": _mean(game.world.hunger(name) for name in alive),
        "energy_mean": _mean(game.world.energy(name) for name in alive),
        "health_mean": _mean(health_values),
        "health_min": round(min(health_values), 6) if health_values else None,
        "health_states": dict(sorted(health_states.items())),
    }


def _report_subset(game: Any) -> dict[str, Any]:
    """Only the fields the reporter actually publishes; never invented."""
    try:
        report = game.world.report(sample_size=10, seed=None)
    except Exception as exc:  # a report failure is recorded, not hidden
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    economy = report.get("economy", {})
    population = report.get("population", {})
    handovers = economy.get("handovers", {})
    return {
        "available": True,
        "alive": population.get("alive"),
        "population": len(population.get("residents", []) or []),
        "food_quantity": economy.get("food_quantity"),
        "food_quantity_in_stock": economy.get("food_quantity_in_stock"),
        "food_quantity_held": economy.get("food_quantity_held"),
        "handovers_count": handovers.get("count"),
        "handovers_by_good": handovers.get("by_good"),
        "shops": sorted((economy.get("shops") or {}).keys()),
        "refusals": report.get("refusals", {}),
        "utterances": (report.get("social", {}).get("conversation", {})
                       .get("utterances")),
    }


def _attempt_subset(game: Any) -> dict[str, Any]:
    """Work outcome counts that exist on the world (``attempt_counts``)."""
    try:
        counts = game.world.attempt_counts()
        tool_tally = game.world.tool_tally()
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    work = counts.get("work", {})
    return {
        "available": True,
        "work": dict(sorted(work.items())) if work else {},
        "verbs": sorted(counts),
        "tool_tally": {str(key): int(value)
                       for key, value in sorted(tool_tally.items())},
    }


def _sanity_subset(game: Any) -> dict[str, Any]:
    try:
        sanity = game.world.sanity_report()
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "available": True,
        "errors": len(sanity.get("errors", [])),
        "warnings": len(sanity.get("warnings", [])),
        "error_messages": list(sanity.get("errors", []))[:5],
        "warning_messages": list(sanity.get("warnings", []))[:5],
    }


def _refusal_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    reasons: dict[str, int] = {}
    for reason, count in (after.get("by_reason") or {}).items():
        delta = int(count) - int((before.get("by_reason") or {}).get(reason, 0))
        if delta:
            reasons[str(reason)] = delta
    return dict(sorted(reasons.items()))


def run_mode(scenario: str, mode: str, *, seed: int = DEFAULT_SEED,
             turns: int = DEFAULT_TURNS,
             timeout: float = DEFAULT_TIMEOUT,
             rule_batching: str = DEFAULT_RULE_BATCHING) -> dict[str, Any]:
    """Run one mode and return its per-turn and final evidence."""
    started = time.perf_counter()
    game = build_game(scenario, mode, seed=seed, rule_batching=rule_batching)
    context_timer = _Timer()
    if hasattr(game, "_build_contexts"):
        context_timer.wrap(game, "_build_contexts")

    total_applied = 0
    total_refused = 0
    total_proposed = 0
    total_no_action = 0
    proposed_by_action: Counter[str] = Counter()
    applied_by_action: Counter[str] = Counter()
    refusals_by_reason: Counter[str] = Counter()
    steps: list[dict[str, Any]] = []
    status = "completed"
    error: str | None = None
    completed = 0
    context_seen = 0.0

    before_counts = game.world.refusal_counts()
    for index in range(max(0, int(turns))):
        if time.perf_counter() - started > timeout:
            status = "timeout"
            break
        step_started = time.perf_counter()
        try:
            result = game.step()
        except Exception as exc:  # record rather than fabricate a completed run
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            break
        step_seconds = time.perf_counter() - step_started
        context_step_seconds = context_timer.seconds - context_seen
        context_seen = context_timer.seconds
        after_counts = game.world.refusal_counts()
        delta = _refusal_delta(before_counts, after_counts)
        before_counts = after_counts
        step_status = str(result.get("status", "unknown"))

        responses = dict(getattr(game, "last_responses", {}) or {})
        results = dict(getattr(game, "last_results", {}) or {})
        proposed_now: Counter[str] = Counter()
        applied_now: Counter[str] = Counter()
        applied = refused = no_action = 0
        for actor, response in responses.items():
            action = _action_of(response)
            if not action:
                no_action += 1
                continue
            proposed_now[action] += 1
            if results.get(actor) is True:
                applied += 1
                applied_now[action] += 1
            elif results.get(actor) is False:
                refused += 1
            else:
                # No result means the actor's proposal was not enacted in this
                # turn (for example a waiting human); count it as not applied.
                no_action += 1

        total_applied += applied
        total_refused += refused
        total_proposed += sum(proposed_now.values())
        total_no_action += no_action
        proposed_by_action.update(proposed_now)
        applied_by_action.update(applied_now)
        refusals_by_reason.update(delta)
        completed += 1
        steps.append({
            "turn": index + 1,
            "world_turn": int(getattr(game.world, "_turn", 0)),
            "status": step_status,
            "proposed": sum(proposed_now.values()),
            "applied": applied,
            "refused": refused,
            "no_action": no_action,
            "proposed_by_action": dict(sorted(proposed_now.items())),
            "applied_by_action": dict(sorted(applied_now.items())),
            "refusals_by_reason": delta,
            "step_seconds": round(step_seconds, 6),
            "context_seconds": round(context_step_seconds, 6),
            **_turn_metrics(game),
        })
        if step_status != "advanced":
            status = step_status
            break

    wall = time.perf_counter() - started
    final_metrics = _turn_metrics(game)
    denominator = max(1, total_proposed)
    return {
        "mode": mode,
        "rule_batching": rule_batching,
        "scenario": scenario,
        "seed": seed,
        "requested_turns": int(turns),
        "turns_completed": completed,
        "status": status,
        "error": error,
        "steps": steps,
        "totals": {
            "proposed": total_proposed,
            "applied": total_applied,
            "refused": total_refused,
            "no_action": total_no_action,
            "refusal_rate": round(total_refused / denominator, 6),
            "applied_per_turn": round(total_applied / max(1, completed), 6),
            "proposed_by_action": dict(sorted(proposed_by_action.items())),
            "applied_by_action": dict(sorted(applied_by_action.items())),
            "refusals_by_reason": dict(sorted(refusals_by_reason.items())),
        },
        "final": {
            **final_metrics,
            "actions_applied": dict(sorted(applied_by_action.items())),
            "work_applied": int(applied_by_action.get("work", 0)),
            "attempts": _attempt_subset(game),
            "report": _report_subset(game),
            "sanity": _sanity_subset(game),
        },
        "timings": {
            "wall_seconds": round(wall, 6),
            "step_seconds": round(sum(step["step_seconds"] for step in steps), 6),
            "context_seconds": round(context_timer.seconds, 6),
            "context_calls": context_timer.calls,
        },
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode = {row["mode"]: row for row in results}
    menu, lazy = by_mode.get("menu"), by_mode.get("lazy")
    if menu is None or lazy is None:
        return {}
    return {
        "turns": {"menu": menu["turns_completed"], "lazy": lazy["turns_completed"]},
        "applied_per_turn": {
            "menu": menu["totals"]["applied_per_turn"],
            "lazy": lazy["totals"]["applied_per_turn"],
            "delta": round(lazy["totals"]["applied_per_turn"]
                           - menu["totals"]["applied_per_turn"], 6),
        },
        "refusal_rate": {
            "menu": menu["totals"]["refusal_rate"],
            "lazy": lazy["totals"]["refusal_rate"],
            "delta": round(lazy["totals"]["refusal_rate"]
                           - menu["totals"]["refusal_rate"], 6),
        },
        "alive": {
            "menu": menu["final"]["alive"], "lazy": lazy["final"]["alive"],
            "delta": lazy["final"]["alive"] - menu["final"]["alive"],
        },
        "hunger_mean": {
            "menu": menu["final"]["hunger_mean"],
            "lazy": lazy["final"]["hunger_mean"],
            "delta": (None if menu["final"]["hunger_mean"] is None
                      or lazy["final"]["hunger_mean"] is None else
                      round(lazy["final"]["hunger_mean"]
                            - menu["final"]["hunger_mean"], 6)),
        },
        "energy_mean": {
            "menu": menu["final"]["energy_mean"],
            "lazy": lazy["final"]["energy_mean"],
            "delta": (None if menu["final"]["energy_mean"] is None
                      or lazy["final"]["energy_mean"] is None else
                      round(lazy["final"]["energy_mean"]
                            - menu["final"]["energy_mean"], 6)),
        },
        "health_mean": {
            "menu": menu["final"]["health_mean"],
            "lazy": lazy["final"]["health_mean"],
            "delta": (None if menu["final"]["health_mean"] is None
                      or lazy["final"]["health_mean"] is None else
                      round(lazy["final"]["health_mean"]
                            - menu["final"]["health_mean"], 6)),
        },
        "health_min": {
            "menu": menu["final"]["health_min"],
            "lazy": lazy["final"]["health_min"],
        },
        "tool_tally": {
            "menu": menu["final"]["attempts"].get("tool_tally"),
            "lazy": lazy["final"]["attempts"].get("tool_tally"),
        },
        "work_applied": {
            "menu": menu["final"]["work_applied"],
            "lazy": lazy["final"]["work_applied"],
            "delta": lazy["final"]["work_applied"] - menu["final"]["work_applied"],
        },
        "handovers": {
            "menu": menu["final"]["report"].get("handovers_count"),
            "lazy": lazy["final"]["report"].get("handovers_count"),
        },
        "context_seconds": {
            "menu": menu["timings"]["context_seconds"],
            "lazy": lazy["timings"]["context_seconds"],
        },
        "wall_seconds": {
            "menu": menu["timings"]["wall_seconds"],
            "lazy": lazy["timings"]["wall_seconds"],
        },
    }


def evaluate(scenario: str = DEFAULT_SCENARIO, *, seed: int = DEFAULT_SEED,
             turns: int = DEFAULT_TURNS,
             modes: Iterable[str] = DEFAULT_MODES,
             timeout: float = DEFAULT_TIMEOUT,
             rule_batching: str = DEFAULT_RULE_BATCHING) -> dict[str, Any]:
    """Run every requested mode on the same scenario/seed and compare them."""
    chosen = [str(mode) for mode in modes]
    unknown = [mode for mode in chosen if mode not in {"menu", "lazy"}]
    if unknown:
        raise ValueError(f"unknown modes {unknown}; choose from ['menu', 'lazy']")
    if rule_batching not in {"action", "turn"}:
        raise ValueError(
            f"unknown rule_batching {rule_batching!r}; choose from ['action', 'turn']")
    results = [run_mode(scenario, mode, seed=seed, turns=turns, timeout=timeout,
                        rule_batching=rule_batching)
               for mode in chosen]
    return {
        "scenario": scenario,
        "seed": seed,
        "turns": int(turns),
        "modes": chosen,
        "rule_batching": rule_batching,
        "timeout_seconds": timeout,
        "results": results,
        "comparison": _summary(results),
    }


def markdown_table(document: dict[str, Any]) -> str:
    """A compact table for the LA06 report."""
    lines = [
        "| mode | batching | status | turns | proposed | applied | refused | refusal rate | "
        "applied/turn | alive | hunger | energy | health | health min | work | "
        "handovers | accidents | context s | wall s |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in document["results"]:
        final = row["final"]
        totals = row["totals"]
        report = final.get("report", {})
        tally = final.get("attempts", {}).get("tool_tally", {}) or {}
        lines.append(
            "| {mode} | {batching} | {status} | {turns} | {proposed} | {applied} | {refused} | "
            "{rate} | {per_turn} | {alive} | {hunger} | {energy} | {health} | "
            "{health_min} | {work} | {handovers} | {accidents} | {context} | "
            "{wall} |".format(
                mode=row["mode"],
                batching=row.get("rule_batching", DEFAULT_RULE_BATCHING),
                status=row["status"],
                turns=row["turns_completed"], proposed=totals["proposed"],
                applied=totals["applied"], refused=totals["refused"],
                rate=totals["refusal_rate"],
                per_turn=totals["applied_per_turn"],
                alive=final.get("alive"), hunger=final.get("hunger_mean"),
                energy=final.get("energy_mean"), health=final.get("health_mean"),
                health_min=final.get("health_min"),
                work=final.get("work_applied"),
                handovers=report.get("handovers_count"),
                accidents=tally.get("accidents"),
                context=row["timings"]["context_seconds"],
                wall=row["timings"]["wall_seconds"]))
    return "\n".join(lines)


def _parse_modes(text: str) -> list[str]:
    modes = [part.strip() for part in text.split(",") if part.strip()]
    if not modes:
        raise argparse.ArgumentTypeError("modes must not be empty")
    return modes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO,
                        choices=list(SCENARIOS))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS)
    parser.add_argument("--modes", type=_parse_modes,
                        default=list(DEFAULT_MODES),
                        help="comma-separated: menu,lazy")
    parser.add_argument("--rule-batching", default=DEFAULT_RULE_BATCHING,
                        choices=["action", "turn"],
                        help="world-rule batching (default action)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="wall-clock budget per mode in seconds")
    parser.add_argument("--json-only", action="store_true",
                        help="print the JSON document only")
    args = parser.parse_args(argv)
    if args.turns < 0:
        parser.error("--turns must not be negative")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    document = evaluate(args.scenario, seed=args.seed, turns=args.turns,
                        modes=args.modes, timeout=args.timeout,
                        rule_batching=args.rule_batching)
    print(json.dumps(_jsonable(document), indent=2, sort_keys=True))
    if not args.json_only:
        print()
        print(markdown_table(document))
        if document["comparison"]:
            print()
            print("Comparison (lazy - menu):")
            print(json.dumps(document["comparison"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
