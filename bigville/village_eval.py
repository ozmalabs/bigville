"""Bounded package 17-18 town100 evaluation harness.

The protocol runs the actual town100 game through the simple backend. It has
no test-only decision loop. See ``docs/PACKAGE17_18_VILLAGE_EVAL_PREREG.md`` for
the registered arms, measurements, acceptance thresholds, and claim status.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
from pathlib import Path
from typing import Any

from .api import create_game
from .backends import DeterministicBackend, SimplePolicy


SCHEMA = "bigville/package17-18-village-eval/1"
SEEDS = (305017, 305018, 305019)
ARMS = ("baseline", "food_shock", "sharing", "food_shock_sharing")
TICKS_PER_PERIOD = 96
PERIODS = 5
MAX_TURNS = TICKS_PER_PERIOD * PERIODS
MAX_RUN_SECONDS = 900.0
MAX_TOTAL_SECONDS = 15000.0
MAX_REPORT_BYTES = 4_000_000
FOOD_SHOCK_FRACTION = 0.20
SHARING_TRANSFER_BONUS = 8.0

_FOOD_ACTIONS = {
    "eat", "fetch", "buy", "sell", "serve", "transfer", "harvest", "milk",
    "sow", "water", "grind_flour", "bake_bread", "make_pottage",
}
_WORK_ACTIONS = {
    "work", "harvest", "sow", "water", "tend_animals", "milk", "shear",
    "craft", "grind_flour", "bake_bread", "make_pottage", "repair", "build",
}
_CONSERVATIVE_TRANSFER_ACTIONS = {"fetch", "transfer", "store", "withdraw"}
_PROVENANCE_PATHS = ("bigville", "worlds", "domains", "scenarios", "seeds",
                     "pyproject.toml")


def _hash_file_manifest(root: Path, relative_paths) -> dict[str, str]:
    """Hash the registered source/config files below ``root`` deterministically."""
    files = set()
    for relative in relative_paths:
        path = root / relative
        if path.is_dir():
            files.update(candidate for candidate in path.rglob("*")
                         if candidate.is_file()
                         and "__pycache__" not in candidate.parts
                         and candidate.suffix != ".pyc")
        elif path.is_file():
            files.add(path)
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(files)
    }


def _provenance() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    source_config_hashes = _hash_file_manifest(root, _PROVENANCE_PATHS)
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "source_config_hashes": source_config_hashes,
        "source_config_manifest_sha256": _canonical_digest(source_config_hashes),
    }


def _round(value: Any) -> float:
    return round(float(value), 6)


def _numeric_or_label(value: Any) -> float | str:
    try:
        return _round(value)
    except (TypeError, ValueError):
        return str(value)


def _resource_snapshot(world) -> dict[str, float]:
    """Read item quantities in town/resident/container/deposit locations.

    This is a diagnostic inventory. Recipe conversion, decay, metabolism,
    extraction, and ecology are legitimate sources or sinks, so only the
    transfer-like action invariant below is used as a conservation check.
    """
    amounts: dict[str, float] = {}

    def add(kind, quantity):
        if kind and kind != "none":
            amounts[str(kind)] = amounts.get(str(kind), 0.0) + float(quantity)

    for kind in world._stock:
        if kind != "none":
            add(kind, world.qty(kind))
    for actor in world._actors:
        for kind, quantity in world.inventory(actor).items():
            add(kind, quantity)
    actor_carriers = set(world._actor_inventories.values())
    for _name, (_node, inners) in world._containers.items():
        if _name in actor_carriers:
            # Resident inventories were already included through inventory();
            # their physical carrier node is the same stock, not another pile.
            continue
        for kind, node in inners.items():
            attrs = world.eng.node(node)["attrs"]
            add(kind, attrs.get("qty", 0.0))
    for kind, node in world._resource_deposits.items():
        # Deposits are a location, not a distinct item type. Keep them under
        # the same item key as town stock and inventories so moving an item
        # out of a deposit remains visible as a conserved transfer.
        add(kind, world.eng.node(node)["attrs"].get("stock", 0.0))
    for name, node in world._dropped_stocks.items():
        attrs = world.eng.node(node)["attrs"]
        add(attrs.get("kind", name), attrs.get("qty", 0.0))
    return {kind: _round(quantity) for kind, quantity in sorted(amounts.items())}


def _resident_snapshot(world) -> list[dict[str, Any]]:
    residents = []
    for name in sorted(world._actors):
        attrs = world.eng.node(world._actors[name])["attrs"]
        starve_limit = max(1.0, float(attrs.get("starve_limit", 4.0)))
        residents.append({
            "id": name,
            "alive": bool(float(attrs.get("alive", 1.0))),
            "hunger": _round(float(attrs.get("hunger", 0.0)) / starve_limit),
            "health": _numeric_or_label(attrs.get("health", "unknown")),
            "inventory": {key: _round(value)
                          for key, value in sorted(world.inventory(name).items())},
        })
    return residents


def _measure(world) -> dict[str, Any]:
    return {
        "turn": int(world._turn),
        "period": _round(world.eng.node(world._town)["attrs"].get("period", 0.0)),
        "residents": _resident_snapshot(world),
        "resources": _resource_snapshot(world),
        "utterances": len(world._utterances),
        "transactions": len(world._transactions),
        "deaths": len(world._deaths),
    }


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resource_deltas(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    return {kind: _round(after.get(kind, 0.0) - before.get(kind, 0.0))
            for kind in sorted(set(before) | set(after))
            if abs(after.get(kind, 0.0) - before.get(kind, 0.0)) > 1e-8}


def _install_arm(game, arm: str) -> None:
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {ARMS}")
    if arm not in {"sharing", "food_shock_sharing"}:
        return
    policy = SimplePolicy(allow_transfers=True,
                          action_bonuses={"transfer": SHARING_TRANSFER_BONUS})
    for name, character in game.characters.items():
        game.set_backend(name, DeterministicBackend(character, policy=policy))


def _apply_food_shock(world) -> dict[str, Any]:
    food_stocks = {
        kind: world.qty(kind)
        for kind in sorted(world._stock)
        if kind != "none" and world._item_specs.get(kind, {}).get("food")
        and world.qty(kind) > 0
    }
    if not food_stocks:
        return {"fraction": FOOD_SHOCK_FRACTION, "before": {}, "removed": {},
                "after": {}, "applied": False}
    removed = {}
    after = {}
    for kind, before in food_stocks.items():
        loss = before * FOOD_SHOCK_FRACTION
        node = world._stock[kind]
        world.eng.set_attr(node, "qty", before - loss)
        removed[kind] = _round(loss)
        after[kind] = _round(before - loss)
    return {"fraction": FOOD_SHOCK_FRACTION,
            "before": {key: _round(value) for key, value in food_stocks.items()},
            "removed": removed, "after": after, "applied": True}


def _domain(action: str, *, speech=0, transactions=0, resource_delta=None):
    domains = []
    if action in _FOOD_ACTIONS or (resource_delta and action not in _WORK_ACTIONS):
        domains.append("food")
    if action in _WORK_ACTIONS or (resource_delta and action not in _FOOD_ACTIONS):
        domains.append("work")
    if action == "transfer" or speech or transactions:
        domains.append("social")
    return domains or ["other"]


def _add_counts(target: dict, key: str, value: int):
    target[key] = target.get(key, 0) + int(value)


def _period_causal_trace(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold per-turn causal measurements into a compact, five-period trace."""
    groups: dict[int, list[dict[str, Any]]] = {}
    for row in steps:
        groups.setdefault((row["turn"] - 1) // TICKS_PER_PERIOD, []).append(row)
    result = []
    for period_index, rows in sorted(groups.items()):
        domains = {}
        hunger_deltas = []
        invariant_turns = {"negative_stocks": 0,
                           "negative_resources": 0,
                           "invalid_action_results": 0,
                           "sanity_error_turns": 0}
        for row in rows:
            hunger_deltas.extend(row["hunger_delta_by_actor"].values())
            invariant_turns["negative_stocks"] += not row["invariants"]["stock_nonnegative"]
            invariant_turns["negative_resources"] += not row["invariants"]["resource_quantities_nonnegative"]
            invariant_turns["invalid_action_results"] += not row["invariants"]["action_results_boolean"]
            invariant_turns["sanity_error_turns"] += row["invariants"]["sanity_errors"] > 0
            for domain, data in row["chains"].items():
                target = domains.setdefault(domain, {"actions": {}, "resource_delta": {},
                    "inventory_delta": {}, "utterances": 0, "transactions": 0})
                for action, counts in data["actions"].items():
                    total = target["actions"].setdefault(action, {
                        "count": 0, "succeeded": 0, "failed": 0})
                    for key in total:
                        total[key] += counts[key]
                for field in ("resource_delta", "inventory_delta"):
                    for item, amount in data[field].items():
                        target[field][item] = _round(target[field].get(item, 0.0) + amount)
                target["utterances"] += data["utterances"]
                target["transactions"] += data["transactions"]
        hunger_sorted = sorted(hunger_deltas)
        result.append({
            "period_index": period_index,
            "turn_start": rows[0]["turn"], "turn_end": rows[-1]["turn"],
            "chains": domains,
            "hunger_delta": {
                "resident_turns": len(hunger_deltas),
                "mean": _round(sum(hunger_deltas) / len(hunger_deltas)) if hunger_deltas else None,
                "p95": _round(hunger_sorted[min(len(hunger_sorted) - 1,
                    math.ceil(len(hunger_sorted) * .95) - 1)]) if hunger_sorted else None,
                "increased": sum(value > 0 for value in hunger_deltas),
                "decreased": sum(value < 0 for value in hunger_deltas),
            },
            "invariant_turns": invariant_turns,
        })
    return result


def run_arm(seed: int, arm: str, *, turns: int = MAX_TURNS,
            ticks_per_period: int = TICKS_PER_PERIOD,
            max_run_seconds: float = MAX_RUN_SECONDS) -> dict[str, Any]:
    if seed not in SEEDS:
        raise ValueError(f"seed must be in the preregistered set {SEEDS}")
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {ARMS}")
    if isinstance(turns, bool) or not isinstance(turns, int) or not 1 <= turns <= MAX_TURNS:
        raise ValueError(f"turns must be an integer in [1, {MAX_TURNS}]")
    if ticks_per_period != TICKS_PER_PERIOD:
        raise ValueError(f"ticks_per_period is preregistered at {TICKS_PER_PERIOD}")
    if not math.isfinite(max_run_seconds) or not 1 <= max_run_seconds <= MAX_RUN_SECONDS:
        raise ValueError(f"max_run_seconds must be in [1, {MAX_RUN_SECONDS:g}]")

    started = time.perf_counter()
    game = create_game(scenario="town100", seed=seed, default_backend="simple",
                       autonomous=True, ticks_per_period=ticks_per_period)
    _install_arm(game, arm)
    world = game.world
    shock = ({"applied": False} if "food_shock" not in arm else _apply_food_shock(world))
    initial = _measure(world)
    attempted = succeeded = failed = invalid_action_results = 0
    action_counts: dict[str, dict[str, int]] = {}
    chain_counts: dict[str, dict[str, Any]] = {}
    transfer_invariant_checks = transfer_invariant_failures = 0
    step_trace = []

    for _ in range(turns):
        if time.perf_counter() - started >= max_run_seconds:
            raise TimeoutError(f"seed {seed} arm {arm} exceeded {max_run_seconds:g}s runtime budget")
        before_turn = _measure(world)
        causal_events = []
        original_apply = game._apply_response

        def observed_apply(actor, response):
            nonlocal transfer_invariant_checks, transfer_invariant_failures
            before_resources = _resource_snapshot(world)
            before_inventory = dict(world.inventory(actor))
            before_utterances = len(world._utterances)
            before_transactions = len(world._transactions)
            proposal = response.major_action
            action = str(proposal.action) if proposal is not None else "observe"
            result = original_apply(actor, response)
            after_resources = _resource_snapshot(world)
            after_inventory = dict(world.inventory(actor))
            resource_delta = _resource_deltas(before_resources, after_resources)
            inventory_delta = _resource_deltas(
                {str(k): float(v) for k, v in before_inventory.items()},
                {str(k): float(v) for k, v in after_inventory.items()})
            emitted_speech = len(world._utterances) - before_utterances
            made_transactions = len(world._transactions) - before_transactions
            if action in _CONSERVATIVE_TRANSFER_ACTIONS:
                transfer_invariant_checks += 1
                if any(abs(value) > 1e-6 for value in resource_delta.values()):
                    transfer_invariant_failures += 1
            causal_events.append({
                "action": action, "result": result,
                "domains": _domain(action, speech=emitted_speech,
                                    transactions=made_transactions,
                                    resource_delta=resource_delta),
                "inventory_delta": inventory_delta,
                "resource_delta": resource_delta,
                "utterances": emitted_speech,
                "transactions": made_transactions,
            })
            return result

        game._apply_response = observed_apply
        try:
            result = game.step()
        finally:
            game._apply_response = original_apply
        if result.get("status") != "advanced":
            raise RuntimeError(f"unattended game did not advance: {result}")
        per_action = {}
        per_domain = {name: {"actions": {}, "resource_delta": {},
                             "inventory_delta": {}, "utterances": 0,
                             "transactions": 0}
                      for name in ("work", "food", "social", "other")}
        for index, (actor, response) in enumerate(game.last_responses.items()):
            proposal = response.major_action
            action = str(proposal.action) if proposal is not None else "observe"
            outcome = game.last_results.get(actor)
            event = causal_events[index]
            if proposal is not None:
                attempted += 1
                row = action_counts.setdefault(action, {"attempted": 0,
                                                        "succeeded": 0, "failed": 0})
                row["attempted"] += 1
                if outcome is True:
                    succeeded += 1
                    row["succeeded"] += 1
                elif outcome is False:
                    failed += 1
                    row["failed"] += 1
                else:
                    invalid_action_results += 1
            for domain in event["domains"]:
                bucket = per_domain[domain]
                action_row = bucket["actions"].setdefault(action, {"count": 0,
                    "succeeded": 0, "failed": 0})
                action_row["count"] += 1
                if outcome is True:
                    action_row["succeeded"] += 1
                elif outcome is False:
                    action_row["failed"] += 1
                for key, value in event["resource_delta"].items():
                    bucket["resource_delta"][key] = _round(
                        bucket["resource_delta"].get(key, 0.0) + value)
                for key, value in event["inventory_delta"].items():
                    bucket["inventory_delta"][key] = _round(
                        bucket["inventory_delta"].get(key, 0.0) + value)
                bucket["utterances"] += event["utterances"]
                bucket["transactions"] += event["transactions"]
            if proposal is not None or event["utterances"] or event["transactions"]:
                key = action
                summary = per_action.setdefault(key, {"attempted": 0,
                    "succeeded": 0, "failed": 0, "resource_delta": {},
                    "inventory_delta": {}, "utterances": 0, "transactions": 0})
                if proposal is not None:
                    summary["attempted"] += 1
                    if outcome is True:
                        summary["succeeded"] += 1
                    elif outcome is False:
                        summary["failed"] += 1
                for field in ("resource_delta", "inventory_delta"):
                    for item, quantity in event[field].items():
                        summary[field][item] = _round(summary[field].get(item, 0.0) + quantity)
                summary["utterances"] += event["utterances"]
                summary["transactions"] += event["transactions"]

        after_turn = _measure(world)
        for domain, data in per_domain.items():
            for action, counts in data["actions"].items():
                totals = chain_counts.setdefault(domain, {}).setdefault(action, {
                    "count": 0, "succeeded": 0, "failed": 0,
                    "resource_delta": {}, "inventory_delta": {},
                    "utterances": 0, "transactions": 0})
                for key in ("count", "succeeded", "failed", "utterances", "transactions"):
                    if key in counts:
                        totals[key] += counts[key]
            for field in ("resource_delta", "inventory_delta"):
                total = chain_counts.setdefault(domain, {}).setdefault("_all", {
                    "resource_delta": {}, "inventory_delta": {},
                    "utterances": 0, "transactions": 0})
                for item, quantity in data[field].items():
                    total[field][item] = _round(total[field].get(item, 0.0) + quantity)
            total = chain_counts.setdefault(domain, {}).setdefault("_all", {
                "resource_delta": {}, "inventory_delta": {},
                "utterances": 0, "transactions": 0})
            total["utterances"] += data["utterances"]
            total["transactions"] += data["transactions"]

        sanity = world.sanity_report()
        stock_values = {kind: world.qty(kind) for kind in world._stock if kind != "none"}
        negative_visible_resources = sorted(kind for kind, value in after_turn["resources"].items()
                                            if value < -1e-6)
        action_results_valid = all(game.last_results.get(actor) in (True, False)
                                   for actor, response in game.last_responses.items()
                                   if response.major_action is not None)
        step_trace.append({
            "turn": after_turn["turn"], "period": after_turn["period"],
            "chains": per_domain,
            "actions": per_action,
            "hunger_delta_by_actor": {
                before["id"]: _round(next((row["hunger"] for row in after_turn["residents"]
                                           if row["id"] == before["id"]), before["hunger"])
                                     - before["hunger"])
                for before in before_turn["residents"]},
            "invariants": {
                "stock_nonnegative": all(value >= -1e-6 for value in stock_values.values()),
                "resource_quantities_nonnegative": not negative_visible_resources,
                "action_results_boolean": action_results_valid,
                "sanity_errors": len(sanity.get("errors", [])),
                "negative_stocks": list(sanity.get("negative_stocks", [])),
            },
        })

    elapsed = time.perf_counter() - started
    if elapsed > max_run_seconds:
        raise TimeoutError(f"seed {seed} arm {arm} exceeded {max_run_seconds:g}s runtime budget")
    final = _measure(world)
    final_sanity = world.sanity_report()
    alive = [row for row in final["residents"] if row["alive"]]
    hunger = [row["hunger"] for row in alive]
    hunger_sorted = sorted(hunger)
    severe_hunger = sum(value >= 0.95 for value in hunger)
    invariant_failures = {
        "transfer_like_resource_conservation": transfer_invariant_failures,
        "negative_stock_turns": sum(not row["invariants"]["stock_nonnegative"]
                                     for row in step_trace),
        "negative_visible_resource_turns": sum(
            not row["invariants"]["resource_quantities_nonnegative"] for row in step_trace),
        "invalid_action_result_turns": sum(
            not row["invariants"]["action_results_boolean"] for row in step_trace),
        "sanity_error_turns": sum(row["invariants"]["sanity_errors"] > 0
                                   for row in step_trace),
    }
    successful_social = chain_counts.get("social", {}).get("_all", {})
    return {
        "seed": seed, "arm": arm,
        "scenario": "town100", "backend": "simple",
        "turns": turns, "periods": final["period"] - initial["period"],
        "ticks_per_period": ticks_per_period,
        "initial": {"population": len(initial["residents"]),
                    "alive": sum(row["alive"] for row in initial["residents"]),
                    "resources": initial["resources"],
                    "residents": initial["residents"]},
        "food_shock": shock,
        "final": {"population": len(final["residents"]),
                  "alive": len(alive), "deaths": final["deaths"],
                  "hunger_mean": _round(sum(hunger) / len(hunger)) if hunger else None,
                  "hunger_p95": _round(hunger_sorted[min(len(hunger) - 1,
                      math.ceil(len(hunger) * .95) - 1)]) if hunger else None,
                  "hunger_ge_0_75": sum(value >= .75 for value in hunger),
                  "hunger_ge_0_95": severe_hunger,
                  "resources": final["resources"],
                  "utterances_total": final["utterances"],
                  "transactions_total": final["transactions"],
                  "sanity_errors": list(final_sanity.get("errors", [])),
                  "negative_stocks": list(final_sanity.get("negative_stocks", []))},
        "resource_control": {
            "initial_by_kind": initial["resources"], "final_by_kind": final["resources"],
            "delta_by_kind": _resource_deltas(initial["resources"], final["resources"]),
            "interpretation": "diagnostic; work, metabolism, ecology, decay, and recipes affect mass",
        },
        "actions": {"attempted": attempted, "succeeded": succeeded, "failed": failed,
                    "invalid_results": invalid_action_results,
                    "failure_rate": _round(failed / attempted) if attempted else 0.0,
                    "by_action": dict(sorted(action_counts.items()))},
        "causal_chains": {
            "by_domain_and_action": chain_counts,
            "period_trace": _period_causal_trace(step_trace),
            "social_utterances": int(successful_social.get("utterances", 0)),
            "social_transactions": int(successful_social.get("transactions", 0)),
        },
        "invariants": {"transfer_like_action_checks": transfer_invariant_checks,
                       "failures": invariant_failures,
                       "final_sanity_errors": list(final_sanity.get("errors", [])),
                       "final_negative_stocks": list(final_sanity.get("negative_stocks", []))},
        "runtime_seconds": _round(elapsed),
        "measurements_digest": _canonical_digest(step_trace),
    }


def _initial_conditions_match(runs: list[dict[str, Any]]) -> bool:
    by_key = {(row["seed"], row["arm"]): row for row in runs}
    for seed in {row["seed"] for row in runs}:
        for left, right in (("baseline", "sharing"),
                            ("food_shock", "food_shock_sharing")):
            if (seed, left) in by_key and (seed, right) in by_key:
                a, b = by_key[(seed, left)]["initial"], by_key[(seed, right)]["initial"]
                if a != b:
                    return False
        if (seed, "baseline") in by_key and (seed, "food_shock") in by_key:
            baseline, shocked = by_key[(seed, "baseline")], by_key[(seed, "food_shock")]
            if baseline["initial"]["residents"] != shocked["initial"]["residents"]:
                return False
            expected = baseline["initial"]["resources"]
            actual = shocked["initial"]["resources"]
            removal = shocked["food_shock"].get("removed", {})
            for kind, quantity in expected.items():
                expected_after = _round(quantity - removal.get(kind, 0.0))
                if abs(actual.get(kind, 0.0) - expected_after) > 1e-5:
                    return False
    return True


def run_evaluation(*, seeds=SEEDS, arms=ARMS, turns=MAX_TURNS, replay=True,
                   max_run_seconds=MAX_RUN_SECONDS) -> dict[str, Any]:
    seeds, arms = tuple(seeds), tuple(arms)
    if not seeds or len(seeds) > len(SEEDS) or len(set(seeds)) != len(seeds):
        raise ValueError(f"choose 1 to {len(SEEDS)} unique preregistered seeds")
    if any(seed not in SEEDS for seed in seeds):
        raise ValueError(f"seeds must be selected from the preregistered set {SEEDS}")
    if not arms or len(set(arms)) != len(arms) or any(arm not in ARMS for arm in arms):
        raise ValueError(f"arms must be unique members of {ARMS}")
    started = time.perf_counter()
    runs = []
    replay_rows = []
    for seed in seeds:
        for arm in arms:
            first = run_arm(seed, arm, turns=turns, max_run_seconds=max_run_seconds)
            runs.append(first)
            # The full condition set is duplicated at one predeclared seed.
            if replay and seed == SEEDS[0]:
                second = run_arm(seed, arm, turns=turns,
                                 max_run_seconds=max_run_seconds)
                replay_rows.append({"seed": seed, "arm": arm,
                    "measurements_match": first["measurements_digest"] == second["measurements_digest"],
                    "first_digest": first["measurements_digest"],
                    "replay_digest": second["measurements_digest"],
                    "runtime_seconds": second["runtime_seconds"]})
    total_runtime = _round(time.perf_counter() - started)

    per_run_checks = all(
        row["final"]["alive"] >= math.ceil(row["initial"]["population"] * .90)
        and row["final"]["hunger_ge_0_95"] <= math.floor(row["final"]["alive"] * .20)
        and row["actions"]["failure_rate"] <= .05
        and row["actions"]["invalid_results"] == 0
        and not row["invariants"]["failures"]["transfer_like_resource_conservation"]
        and not row["invariants"]["failures"]["negative_stock_turns"]
        and not row["invariants"]["failures"]["negative_visible_resource_turns"]
        and not row["invariants"]["failures"]["invalid_action_result_turns"]
        and not row["invariants"]["failures"]["sanity_error_turns"]
        and not row["invariants"]["final_sanity_errors"]
        and not row["invariants"]["final_negative_stocks"]
        and row["runtime_seconds"] <= max_run_seconds
        for row in runs)
    full_protocol = (seeds == SEEDS and arms == ARMS and turns == MAX_TURNS and replay
                     and max_run_seconds == MAX_RUN_SECONDS
                     and len(replay_rows) == len(ARMS))
    replay_ok = bool(replay_rows) and all(row["measurements_match"] for row in replay_rows)
    protocol = {"seeds": list(seeds), "arms": list(arms), "turns": turns,
                "periods": turns // TICKS_PER_PERIOD,
                "ticks_per_period": TICKS_PER_PERIOD,
                "replay_seed": SEEDS[0] if replay and SEEDS[0] in seeds else None,
                "replay_arms": [row["arm"] for row in replay_rows],
                "max_run_seconds": max_run_seconds,
                "max_total_seconds": MAX_TOTAL_SECONDS,
                "scenario": "town100", "backend": "simple",
                "food_shock_fraction": FOOD_SHOCK_FRACTION,
                "sharing_transfer_bonus": SHARING_TRANSFER_BONUS}
    acceptance = {
        "all_requested_cells_completed": len(runs) == len(seeds) * len(arms),
        "matched_initial_conditions": _initial_conditions_match(runs),
        "all_food_shock_cells_applied_registered_shock": all(
            row["food_shock"].get("applied", False) for row in runs
            if "food_shock" in row["arm"]),
        "per_run_survival_hunger_action_and_invariant_criteria": per_run_checks,
        "replay_matches": replay_ok,
        "runtime_within_total_budget": total_runtime <= MAX_TOTAL_SECONDS,
        "preregistered_protocol_complete": full_protocol,
    }
    acceptance["evaluation_passed"] = (
        full_protocol and all(acceptance[key] for key in (
            "all_requested_cells_completed", "matched_initial_conditions",
            "all_food_shock_cells_applied_registered_shock",
            "per_run_survival_hunger_action_and_invariant_criteria",
            "replay_matches", "runtime_within_total_budget")))
    # This evaluator cannot attest the separately owned package-14/full-suite
    # and major-action-boundary prerequisites; never present its own result as
    # permission to make the package claim.
    acceptance["external_prerequisites_recorded"] = False
    acceptance["claim_gate_ready"] = False
    return {
        "schema": SCHEMA, "protocol": protocol, "runs": runs,
        "replays": replay_rows,
        "provenance": _provenance(),
        "total_runtime_seconds": total_runtime,
        "acceptance": acceptance,
        "claims_status": "evaluation only; claim gate requires full protocol and separately recorded package 14 and major-action prerequisites",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded town100 package 17-18 evaluator")
    parser.add_argument("--seed", type=int, action="append", choices=SEEDS,
                        help="preregistered seed (repeat up to three times; default all)")
    parser.add_argument("--arm", choices=ARMS, action="append",
                        help="registered condition (repeat; default all conditions)")
    parser.add_argument("--turns", type=int, default=MAX_TURNS,
                        help=f"turn budget (1..{MAX_TURNS}; full gate uses {MAX_TURNS})")
    parser.add_argument("--max-run-seconds", type=float, default=MAX_RUN_SECONDS,
                        help=f"per-cell ceiling (1..{MAX_RUN_SECONDS:g}; default {MAX_RUN_SECONDS:g})")
    parser.add_argument("--no-replay", action="store_true",
                        help="omit first-seed condition replays (not a complete claim gate)")
    parser.add_argument("--output", type=Path, help="write compact JSON report to path")
    args = parser.parse_args(argv)
    report = run_evaluation(seeds=args.seed or SEEDS, arms=args.arm or ARMS,
                            turns=args.turns, replay=not args.no_replay,
                            max_run_seconds=args.max_run_seconds)
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_REPORT_BYTES:
        parser.error("report exceeds 4 MB output bound")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    # A smoke/partial run may satisfy its local outcome checks, but it is not
    # the registered protocol and must not look like a successful evaluation
    # to shell callers. The report carries the same protocol-level decision.
    return 0 if report["acceptance"]["evaluation_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
