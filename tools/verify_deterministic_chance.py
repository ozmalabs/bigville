#!/usr/bin/env python3
"""Verify the deterministic-chance rule under every executor and a restore.

For every requested seed the tool builds the same scenario and compares:

1. **serial vs partitioned.**  Both games step the same turns.  After each
   turn it compares the semantic world state (``semantic_world_state``), the
   semantic payload checksum (``tick_payload_sha``) and the graph revision.
2. **partitioned replay.**  A second partitioned game must produce the same
   per-turn execution checksum (``TickBundleLog.execution_sha``), the same
   committed order, the same payload checksum and the same revision.  The two
   per-turn execution checksums are folded into a ``run_execution_sha``.
3. **reordered draws.**  The same controlled set of weather, infrastructure,
   birth, illness, meal and strike draws is evaluated once in ascending actor
   order and once in descending actor order.  The reordering is a fixed,
   documented reversal (never a random shuffle); every outcome must match per
   key.  This is the order-independence rule at draw level.
4. **checkpoint / restore.**  A fresh game is checkpointed after turn N and
   restored; the restored game continues with the same settings.  Every
   remaining turn's semantic payload checksum and revision must equal the
   uninterrupted baseline.
5. **shared-RNG / source audit.**  No game world has an ``_rng`` attribute, and
   the DS03 production source audit (the matcher in
   ``tests/test_random_audit.py``) reports no findings.

A chance-heavy setup is applied identically to every game: births and illness
are enabled in the world's physical subsystem switches, the clock starts one
tick before dawn so weather and the daily draws fire, a well with failure risk
1.0 is added, and a gestating dam is added so the animal-birth sex draw fires.
``_stable_draw`` calls are counted by purpose and reported; that is evidence the
run exercised the chance streams rather than only comparing untouched state.

Usage::

    python3 tools/verify_deterministic_chance.py
    python3 tools/verify_deterministic_chance.py --seeds 305000,305002 --turns 8
    python3 tools/verify_deterministic_chance.py --scenario small --json
    python3 tools/verify_deterministic_chance.py --executor partitioned
    python3 tools/verify_deterministic_chance.py --no-chance-heavy

Exit code 0 means every requested comparison matched.  A divergence names the
first turn and the scope that differed.  The module is import-safe: building a
report constructs worlds, but importing it does not.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

# Allow ``python3 tools/verify_deterministic_chance.py`` from the repository root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bigville.api import create_game
from bigville.bundle_checks import run_execution_sha, tick_payload_sha
from bigville.tick_trace import semantic_world_state


DEFAULT_SEEDS = (305000, 305002, 305004, 305006)
DEFAULT_TURNS = 8
DEFAULT_SCENARIO = "town100"
DEFAULT_AFFORDANCE_MODE = "menu"
DEFAULT_EXECUTOR = "both"

SMALL_SCENARIO = {
    "id": "ds04_chance_room",
    "name": "DS04 chance room",
    "map": {"grid": [["floor"] * 6 for _ in range(6)]},
    "actors": [
        {"name": "Ada", "role": "resident", "backend": "simple", "home_cell": [1, 1]},
        {"name": "Ben", "role": "resident", "backend": "simple", "home_cell": [2, 2]},
        {"name": "Cy", "role": "farmer", "backend": "simple", "home_cell": [3, 3]},
    ],
    "initial": {"hour": 6.0, "weather": "clear", "temperature": 18.0},
    "physical_subsystems": {
        "metabolism": True, "illness": True, "births": True,
        "ecology": False, "decay": False, "practice": False, "training": False,
    },
    "buildings": [], "laws": [], "policies": [], "charters": [],
}


def scenario_for(name: str):
    """The scenario object for a CLI name."""
    return SMALL_SCENARIO if name == "small" else name


def build_game(*, scenario: str = DEFAULT_SCENARIO, seed: int,
               executor: str, affordance_mode: str = DEFAULT_AFFORDANCE_MODE):
    """Build one deterministic game for a verification run."""
    return create_game(
        scenario=scenario_for(scenario),
        seed=seed,
        default_backend="simple",
        autonomous=True,
        llm_log=False,
        executor=executor,
        turn_semantics="sequential",
        affordance_mode=affordance_mode,
        snapshot_mode="on_demand",
    )


# --------------------------------------------------------------------- chance setup


def prime_chance(world) -> dict[str, Any]:
    """Make the chance streams reachable; identical for every game.

    * births and illness switches on (town100 defaults them off);
    * clock one tick before the dawn boundary, so the first step runs the daily
      weather and illness/birth draws;
    * one well with failure risk 1.0, so the infrastructure draw fires;
    * one gestating cow, so the animal-birth sex draw fires in the first period.
    """
    world.physical_subsystems["births"] = True
    world.physical_subsystems["illness"] = True
    world.eng.set_attr(world._town, "clock", 95.0)
    world.add_infrastructure("ds04_well", kind="well")
    world.eng.set_attr(world._infrastructure["ds04_well"], "failure_risk", 1.0)
    cell = next(iter(world._map_cells))
    world.add_animal("Ds04Dam", "cow", cell=cell, sex="female")
    world.eng.set_attr(world._animals["Ds04Dam"], "gestating_days", 1.0)
    world.eng.set_attr(world._animals["Ds04Dam"], "sire", "Ds04Sire")
    # One explicit period pass fires the infrastructure and animal-birth draws
    # without waiting 96 turns.  It is applied identically to every game.
    world.pass_period(1)
    return {
        "births": True,
        "illness": True,
        "daily_weather": True,
        "infrastructure": "ds04_well",
        "animal_birth": "Ds04Dam",
    }


def _count_stable_draws(world, counts: Counter | None = None) -> Counter:
    """Count ``world._stable_draw`` purposes by wrapping the bound method."""
    counts = Counter() if counts is None else counts
    original = getattr(world, "_stable_draw", None)
    if original is None:
        return counts

    def counted(purpose, *parts, actors=()):
        counts[str(purpose)] += 1
        return original(purpose, *parts, actors=actors)

    world._stable_draw = counted
    return counts


def chance_evidence(world) -> dict[str, Any]:
    """Readable evidence that the chance-heavy streams actually ran."""
    weather = world.calendar().get("weather")
    conditions = {
        name: world.infrastructure_condition(name)
        for name in sorted(world._infrastructure)
        if name == "ds04_well"
    }
    animal_births = {
        name: float(world.eng.node(node)["attrs"].get("births", 0.0))
        for name, node in sorted(world._animals.items())
        if name == "Ds04Dam"
    }
    return {
        "weather": weather,
        "infrastructure_conditions": conditions,
        "animal_births": animal_births,
        "infrastructure_failed": any(value < 1.0 for value in conditions.values()),
        "animal_birth_drawn": any(value > 0.0 for value in animal_births.values()),
    }


# ------------------------------------------------------------------- turn records


def turn_record(game) -> dict[str, Any]:
    """The semantic state, checksum and revision after one completed turn."""
    state = semantic_world_state(game.world)
    return {
        "revision": int(game.world.revision),
        "payload_sha": tick_payload_sha(state),
        "state": state,
    }


def _compact(record: dict[str, Any]) -> dict[str, Any]:
    return {"revision": record["revision"], "payload_sha": record["payload_sha"]}


def _same_state(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return (first["revision"] == second["revision"]
            and first["payload_sha"] == second["payload_sha"]
            and first["state"] == second["state"])


# ----------------------------------------------------------------------- reordering


def _draw_events(world, order: list[str], *,
                 reverse: bool = False) -> dict[str, Any]:
    """Evaluate the controlled chance draws in a caller-chosen order.

    The same values are keyed by event, so the returned mapping is directly
    comparable between the ascending and descending passes.  These are the
    exact helper calls the world/body make; no state is mutated.  ``reverse``
    reverses the weather-day and infrastructure-name sequences too, so every
    stream participates in the reordering rather than only the actor loops.
    """
    from domains import determinism

    events: dict[str, Any] = {}
    world_seed = determinism.world_seed(world)
    season = str(world.season())
    options = tuple(option for option in
                    world.E.SEASONS.get(season, {}).get("weather", ("clear",))
                    if option in world.E.WEATHER) or ("clear",)

    # Weather draws, forward/reverse by day.
    days = [100, 101, 102]
    for day in (list(reversed(days)) if reverse else days):
        events[f"weather:{day}"] = determinism.choice(
            options, world_seed, "weather", day, season, options)

    # Infrastructure draws, forward/reverse by name.  Two synthetic identities
    # keep the sequence comparable without mutating a real node.
    infrastructure = [("ds04_well", "well"), ("ds04_granary", "granary")]
    names = list(reversed(infrastructure)) if reverse else infrastructure
    for name, kind in names:
        events[f"infrastructure:{name}"] = determinism.uniform(
            world_seed, "infrastructure", name, kind, 0.0, 1.0, 1.0)

    # Per-actor draws, forward/reverse by actor name.  The actor's day and
    # target are fixed from the sorted name set, so reversing the evaluation
    # order cannot change *which* draw an actor gets.
    canonical = sorted(order)
    for actor in order:
        index = canonical.index(actor)
        target = canonical[(index + 1) % len(canonical)]
        day = 100 + index
        period = float(world._town_period())
        events[f"birth:{actor}"] = world._stable_draw(
            "births", "conceive", actor, day, actors=(actor,))
        events[f"illness:{actor}"] = world._stable_draw(
            "illness", actor, "fever", day)
        events[f"meal:{actor}"] = world._stable_draw(
            "meal_illness", actor, period, "bread", 1)
        events[f"strike:{actor}"] = world._strike_locus(
            {"region": "head", "attacker": actor, "target": target,
             "attacker_side": {"skill": 0.5}}, None)
    return events


def reorder_check(world) -> dict[str, Any]:
    """Compare every controlled draw under ascending and descending order."""
    names = sorted(world._actors)
    forward = _draw_events(world, names)
    reverse = _draw_events(world, list(reversed(names)), reverse=True)
    mismatches = {
        key: {"ascending": forward.get(key), "descending": reverse.get(key)}
        for key in sorted(set(forward) | set(reverse))
        if forward.get(key) != reverse.get(key)
    }
    return {
        "ok": not mismatches,
        "events": len(forward),
        "mismatches": mismatches,
        "actors": len(names),
        "order": "sorted ascending vs fixed descending",
    }


# ----------------------------------------------------------------------- audit


def _load_audit_module():
    """Load ``tests/test_random_audit.py`` without importing the tests package."""
    path = _ROOT / "tests" / "test_random_audit.py"
    spec = importlib.util.spec_from_file_location("ds04_random_audit", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load audit matcher from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_audit() -> dict[str, Any]:
    """Run the DS03 production source audit in the tool."""
    audit = _load_audit_module()
    findings: list[dict[str, Any]] = []
    for relative, path in audit.production_files():
        findings.extend(audit.scan_source(path.read_text(encoding="utf-8"),
                                          relative))
    return {"ok": not findings, "findings": findings,
            "files": len(audit.production_files())}


# ------------------------------------------------------------------ comparisons


def _first_divergence(turn: int, scope: str, left, right) -> dict[str, Any]:
    return {"turn": turn, "scope": scope, "left": left, "right": right}


def _run_serial_partitioned(seed: int, turns: int, scenario: str,
                            affordance_mode: str, *, run_serial: bool,
                            run_partitioned: bool,
                            chance_heavy: bool) -> dict[str, Any]:
    """Step the requested executors and compare every turn."""
    serial = (build_game(scenario=scenario, seed=seed, executor="serial",
                         affordance_mode=affordance_mode) if run_serial else None)
    partitioned = (build_game(scenario=scenario, seed=seed,
                              executor="partitioned",
                              affordance_mode=affordance_mode)
                   if run_partitioned else None)
    replay = (build_game(scenario=scenario, seed=seed,
                         executor="partitioned",
                         affordance_mode=affordance_mode)
              if run_partitioned else None)

    games = [game for game in (serial, partitioned, replay) if game is not None]
    counts = Counter()
    evidence = {}
    for game in games:
        if chance_heavy:
            evidence.update(prime_chance(game.world))
            _count_stable_draws(game.world, counts)

    baseline = serial if serial is not None else partitioned
    trajectory: list[dict[str, Any]] = []
    partitioned_execution: list[str] = []
    replay_execution: list[str] = []
    first_state = None
    first_payload = None
    first_execution = None
    first_revision = None

    for turn in range(1, turns + 1):
        results = {}
        for name, game in (("serial", serial), ("partitioned", partitioned),
                           ("replay", replay)):
            if game is None:
                continue
            result = game.step()
            if result.get("status") != "advanced":
                raise AssertionError(
                    f"turn {turn}: {name} returned {result.get('status')!r}")
            results[name] = turn_record(game)

        trajectory.append(_compact(results["serial" if serial is not None
                                                else "partitioned"]))

        if serial is not None and partitioned is not None:
            left, right = results["serial"], results["partitioned"]
            if not _same_state(left, right) and first_state is None:
                first_state = _first_divergence(turn, "semantic_world_state",
                                                _compact(left), _compact(right))
            if left["payload_sha"] != right["payload_sha"] and first_payload is None:
                first_payload = _first_divergence(
                    turn, "tick_payload_sha", left["payload_sha"],
                    right["payload_sha"])
            if left["revision"] != right["revision"] and first_revision is None:
                first_revision = _first_divergence(
                    turn, "graph_revision", left["revision"], right["revision"])

        if partitioned is not None and replay is not None:
            log = partitioned.last_bundle_log
            replay_log = replay.last_bundle_log
            if log is None or replay_log is None:
                raise AssertionError(
                    f"turn {turn}: partitioned turn produced no bundle log")
            execution = log.execution_sha
            replay_execution_sha = replay_log.execution_sha
            partitioned_execution.append(execution)
            replay_execution.append(replay_execution_sha)
            left, right = results["partitioned"], results["replay"]
            if execution != replay_execution_sha and first_execution is None:
                first_execution = _first_divergence(
                    turn, "tick_execution_sha", execution, replay_execution_sha)
            if left["payload_sha"] != right["payload_sha"] and first_payload is None:
                first_payload = _first_divergence(
                    turn, "partitioned_replay_payload_sha",
                    left["payload_sha"], right["payload_sha"])
            if left["revision"] != right["revision"] and first_revision is None:
                first_revision = _first_divergence(
                    turn, "partitioned_replay_revision", left["revision"],
                    right["revision"])
            if (tuple(log.committed_order) != tuple(replay_log.committed_order)
                    and first_execution is None):
                first_execution = _first_divergence(
                    turn, "committed_order", list(log.committed_order),
                    list(replay_log.committed_order))

    evidence.update(chance_evidence(baseline.world))
    execution_stable = first_execution is None
    if partitioned_execution or replay_execution:
        execution_stable = (
            execution_stable
            and run_execution_sha(partitioned_execution)
            == run_execution_sha(replay_execution))
    state_equal = first_state is None
    payload_equal = first_payload is None
    revision_equal = first_revision is None
    return {
        "serial_enabled": serial is not None,
        "partitioned_enabled": partitioned is not None,
        "semantic_state_equal": state_equal,
        "payload_equal": payload_equal,
        "revision_equal": revision_equal,
        "execution_stable": execution_stable,
        "first_state_divergence": first_state,
        "first_payload_divergence": first_payload,
        "first_execution_divergence": first_execution,
        "first_revision_divergence": first_revision,
        "partitioned_run_execution_sha": (
            run_execution_sha(partitioned_execution)
            if partitioned_execution else None),
        "replay_run_execution_sha": (
            run_execution_sha(replay_execution)
            if replay_execution else None),
        "turns": turns,
        "draw_counts": dict(sorted(counts.items())),
        "chance_heavy": evidence,
        "trajectory": trajectory,
        "revisions": [record["revision"] for record in trajectory],
        "payload_shas": [record["payload_sha"] for record in trajectory],
    }


def _run_checkpoint(seed: int, turns: int, scenario: str,
                    affordance_mode: str, checkpoint_turn: int,
                    baseline_trajectory: list[dict[str, Any]], *,
                    chance_heavy: bool) -> dict[str, Any]:
    """Run to ``checkpoint_turn``, save, restore and compare the rest."""
    from bigville.game_persistence import (load_game_checkpoint,
                                           save_game_checkpoint)

    game = build_game(scenario=scenario, seed=seed, executor="serial",
                      affordance_mode=affordance_mode)
    if chance_heavy:
        prime_chance(game.world)
    prefix: list[dict[str, Any]] = []
    for turn in range(1, checkpoint_turn + 1):
        result = game.step()
        if result.get("status") != "advanced":
            raise AssertionError(
                f"checkpoint run turn {turn}: {result.get('status')!r}")
        prefix.append(_compact(turn_record(game)))

    with tempfile.TemporaryDirectory(prefix="ds04-checkpoint-") as folder:
        save_game_checkpoint(game, Path(folder) / "game")
        restored = load_game_checkpoint(Path(folder) / "game", llm_log=False)

    # Session options are not stored in the game checkpoint; restore the same
    # deterministic settings before continuing.
    restored.executor = "serial"
    restored.affordance_mode = affordance_mode
    restored.snapshot_mode = "on_demand"
    restored.rule_batching = "turn"

    continued: list[dict[str, Any]] = []
    for turn in range(checkpoint_turn + 1, turns + 1):
        result = restored.step()
        if result.get("status") != "advanced":
            raise AssertionError(
                f"restored run turn {turn}: {result.get('status')!r}")
        continued.append(_compact(turn_record(restored)))

    expected_prefix = baseline_trajectory[:checkpoint_turn]
    expected_rest = baseline_trajectory[checkpoint_turn:turns]
    prefix_mismatch = next(
        (index + 1 for index, (left, right)
         in enumerate(zip(prefix, expected_prefix)) if left != right), None)
    restore_mismatch = next(
        (checkpoint_turn + index + 1 for index, (left, right)
         in enumerate(zip(continued, expected_rest)) if left != right), None)
    first = None
    if prefix_mismatch is not None:
        first = {"turn": prefix_mismatch, "scope": "checkpoint_prefix"}
    elif len(prefix) != len(expected_prefix) or len(continued) != len(expected_rest):
        first = {"turn": checkpoint_turn, "scope": "checkpoint_length"}
    elif restore_mismatch is not None:
        first = {"turn": restore_mismatch, "scope": "restored_continuation"}
    return {
        "ok": first is None,
        "checkpoint_turn": checkpoint_turn,
        "continued_turns": turns - checkpoint_turn,
        "prefix_equal": prefix_mismatch is None,
        "restored_equal": restore_mismatch is None,
        "first_divergence": first,
        "prefix": prefix,
        "continued": continued,
    }


def _run_seed(*, seed: int, turns: int, scenario: str,
              affordance_mode: str, executor: str,
              chance_heavy: bool) -> dict[str, Any]:
    """Run the full verification matrix for one seed."""
    started = time.perf_counter()
    run_serial = executor in ("both", "serial")
    run_partitioned = executor in ("both", "partitioned")
    matrix = _run_serial_partitioned(
        seed, turns, scenario, affordance_mode,
        run_serial=run_serial, run_partitioned=run_partitioned,
        chance_heavy=chance_heavy)

    probe = build_game(scenario=scenario, seed=seed, executor="serial",
                       affordance_mode=affordance_mode)
    if chance_heavy:
        prime_chance(probe.world)
    reorder = reorder_check(probe.world)
    rng_absent = not hasattr(probe.world, "_rng")

    checkpoint_turn = max(1, turns // 2)
    checkpoint = _run_checkpoint(
        seed, turns, scenario, affordance_mode, checkpoint_turn,
        matrix["trajectory"], chance_heavy=chance_heavy)

    ok = bool(
        matrix["semantic_state_equal"]
        and matrix["payload_equal"]
        and matrix["revision_equal"]
        and matrix["execution_stable"]
        and reorder["ok"]
        and checkpoint["ok"]
        and rng_absent)
    if chance_heavy:
        ok = ok and (matrix["chance_heavy"]["infrastructure_failed"]
                     or matrix["chance_heavy"]["animal_birth_drawn"])
    return {
        "seed": seed,
        "ok": ok,
        "matrix": matrix,
        "reorder": reorder,
        "checkpoint": checkpoint,
        "rng_absent": rng_absent,
        "seconds": round(time.perf_counter() - started, 3),
    }


# --------------------------------------------------------------------- report


def build_report(*, seeds: list[int], turns: int, scenario: str,
                 affordance_mode: str = DEFAULT_AFFORDANCE_MODE,
                 executor: str = DEFAULT_EXECUTOR,
                 chance_heavy: bool = True,
                 audit: bool = True) -> dict[str, Any]:
    """Build the verification report without printing or exiting."""
    report: dict[str, Any] = {
        "tool": "verify_deterministic_chance",
        "scenario": scenario,
        "turns": turns,
        "affordance_mode": affordance_mode,
        "executor": executor,
        "chance_heavy": chance_heavy,
        "seeds": {},
        "ok": True,
    }
    if audit:
        audit_result = source_audit()
        report["source_audit"] = audit_result
        report["ok"] = report["ok"] and audit_result["ok"]
    for seed in seeds:
        try:
            result = _run_seed(seed=seed, turns=turns, scenario=scenario,
                               affordance_mode=affordance_mode,
                               executor=executor, chance_heavy=chance_heavy)
        except Exception as exc:  # keep a report for the other seeds
            result = {
                "seed": seed,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        report["seeds"][str(seed)] = result
        report["ok"] = report["ok"] and bool(result.get("ok"))
    return report


def _print_summary(report: dict[str, Any]) -> None:
    print(f"scenario={report['scenario']} turns={report['turns']} "
          f"executor={report['executor']}")
    if "source_audit" in report:
        audit = report["source_audit"]
        print(f"source audit: {'OK' if audit['ok'] else 'FAILED'} "
              f"({len(audit['findings'])} findings, {audit['files']} files)")
    for seed, result in report["seeds"].items():
        if result.get("error"):
            print(f"seed {seed}: ERROR {result['error']}")
            continue
        matrix = result["matrix"]
        checkpoint = result["checkpoint"]
        print(
            f"seed {seed}: semantic={matrix['semantic_state_equal']} "
            f"payload={matrix['payload_equal']} "
            f"revision={matrix['revision_equal']} "
            f"execution={matrix['execution_stable']} "
            f"reorder={result['reorder']['ok']} "
            f"checkpoint={checkpoint['ok']} "
            f"rng_absent={result['rng_absent']} "
            f"{result['seconds']}s")
    print("OK" if report["ok"] else "FAILED")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default=",".join(map(str, DEFAULT_SEEDS)),
                        help="comma-separated seeds (default 305000,305002,305004,305006)")
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS)
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO,
                        help="town100, small, or a scenario file name")
    parser.add_argument("--affordance-mode", choices=("menu", "lazy"),
                        default=DEFAULT_AFFORDANCE_MODE)
    parser.add_argument("--executor", choices=("both", "serial", "partitioned"),
                        default=DEFAULT_EXECUTOR,
                        help="which execution matrix to run (default both)")
    parser.add_argument("--no-chance-heavy", action="store_true",
                        help="do not enable births/illness or inject draw triggers")
    parser.add_argument("--no-audit", action="store_true",
                        help="skip the production source audit")
    parser.add_argument("--json", action="store_true",
                        help="emit compact JSON (default: indented JSON)")
    args = parser.parse_args(argv)

    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    if not seeds:
        parser.error("--seeds must name at least one seed")
    if args.turns < 2:
        parser.error("--turns must be at least 2 (checkpoint needs a prefix and a continuation)")

    report = build_report(
        seeds=seeds, turns=args.turns, scenario=args.scenario,
        affordance_mode=args.affordance_mode, executor=args.executor,
        chance_heavy=not args.no_chance_heavy, audit=not args.no_audit)
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        _print_summary(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
