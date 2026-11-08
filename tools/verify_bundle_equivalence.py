#!/usr/bin/env python3
"""Verify distributed-bundle equivalence, acknowledgements and checksums.

This is the NB05 replay tool.  For every requested seed it builds three games
from the same scenario/seed/affordance mode:

1. one serial game (the semantic baseline);
2. one partitioned game (bundles dispatched through the local transport);
3. a second partitioned game (same-executor replay).

After every turn it compares the semantic world state and the payload checksum
(``tick_payload_sha``) between serial and partitioned, and the execution
checksum (``tick_execution_sha``) and commit order between the two partitioned
runs.  It also audits every ``TickBundleLog``: exactly one result and one
committed ack per dispatched bundle, no duplicate bundle ids or commits, and a
complete deterministic commit order.

Finally it JSON round-trips every partitioned bundle and dispatches it through
a fresh ``LocalBundleTransport`` whose synthetic executor uses only plain
bundle data.  No game or world object is passed to that transport; this is the
transport-neutrality self-test inside the verification tool.

Usage:

    python3 tools/verify_bundle_equivalence.py
    python3 tools/verify_bundle_equivalence.py --seeds 305000,305002 --turns 8
    python3 tools/verify_bundle_equivalence.py --seeds 305002 --affordance-mode lazy
    python3 tools/verify_bundle_equivalence.py --json

Exit code 0 means every seed matched.  A divergence names the first turn and
the checksum scope that differed.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import replace
from pathlib import Path
from typing import Any

# Allow ``python3 tools/verify_bundle_equivalence.py`` from the repository root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bigville.api import create_game
from bigville.bundle_checks import (
    bundle_execution_sha,
    bundle_output_sha,
    run_execution_sha,
    tick_payload_sha,
)
from bigville.bundles import (
    Bundle,
    BundleAck,
    BundleResult,
    LocalBundleTransport,
    QualifiedId,
)
from bigville.tick_trace import semantic_world_state


DEFAULT_SEEDS = (305000, 305002)
DEFAULT_TURNS = 8
DEFAULT_SCENARIO = "town100"


def build_game(*, scenario: str, seed: int, executor: str,
               affordance_mode: str):
    """Build one deterministic game for a verification run."""
    return create_game(
        scenario=scenario,
        seed=seed,
        default_backend="simple",
        autonomous=True,
        llm_log=False,
        executor=executor,
        turn_semantics="sequential",
        affordance_mode=affordance_mode,
        snapshot_mode="on_demand",
    )


def _wire_bundle(bundle: Bundle) -> dict[str, Any]:
    """A bundle exactly as a JSON transport would put it on the wire."""
    return json.loads(json.dumps(bundle.to_dict(), sort_keys=True,
                                 allow_nan=False))


def _synthetic_result(bundle: Bundle) -> BundleResult:
    """Execute a serialized bundle from plain data; never touches a world."""
    effects = []
    rows = []
    for operation in bundle.ordered_operations():
        params = dict(operation.params)
        value = params.get("amount", params.get("price", 0))
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            value = 0
        effects.append({
            "kind": "set_attr",
            "op_id": operation.op_id,
            "actor": operation.actor,
            "value": value,
        })
        rows.append((operation.actor, True, None))
    created_ids = ((QualifiedId(bundle.namespace.name, 1),)
                   if bundle.operations else ())
    provisional = BundleResult(
        bundle_id=bundle.bundle_id,
        namespace=bundle.namespace,
        base_version=bundle.base_version,
        status="ok",
        effects=tuple(effects),
        created_ids=created_ids,
        result=tuple(rows),
        output_sha="pending",
        execution_sha="pending",
    )
    provisional = replace(provisional,
                          output_sha=bundle_output_sha(provisional))
    return replace(provisional,
                   execution_sha=bundle_execution_sha(bundle, provisional))


def _fake_transport_check(wire_bundles: list[dict[str, Any]]) -> dict[str, Any]:
    """Drive every wire bundle through a transport with no live game.

    This is intentionally a second, independent pass: the partitioned run has
    already executed the bundle against the world.  Here the same serialized
    payload is re-dispatched with a synthetic executor, acknowledged, replayed
    and duplicated.  It proves the protocol (not the in-process callback) is
    what carries the work.
    """
    transport = LocalBundleTransport(_synthetic_result)
    dispatches = 0
    unique: set[str] = set()
    for wire in wire_bundles:
        bundle = Bundle.from_dict(wire)
        if bundle.canonical_json() != Bundle.from_dict(
                _wire_bundle(bundle)).canonical_json():
            raise AssertionError(
                f"bundle {bundle.bundle_id!r} changed across a JSON round trip")
        result = transport.dispatch(bundle)
        duplicate = transport.dispatch(Bundle.from_dict(_wire_bundle(bundle)))
        if duplicate is not result:
            raise AssertionError(
                f"duplicate dispatch of {bundle.bundle_id!r} was not cached")
        if result.execution_sha != _synthetic_result(bundle).execution_sha:
            raise AssertionError(
                f"synthetic checksum is not stable for {bundle.bundle_id!r}")
        ack = BundleAck(
            bundle_id=bundle.bundle_id,
            base_version=bundle.base_version,
            outcome="committed",
            committed_version=bundle.base_version,
            execution_sha=result.execution_sha,
        )
        transport.acknowledge(ack)
        if transport.replay(bundle.bundle_id) is not result:
            raise AssertionError(
                f"replay lost {bundle.bundle_id!r}")
        if transport.acknowledgement(bundle.bundle_id) != ack:
            raise AssertionError(
                f"ack was not recorded for {bundle.bundle_id!r}")
        dispatches += 1
        unique.add(bundle.bundle_id)
    return {
        "bundles": dispatches,
        "unique_ids": len(unique),
        "dispatch_order": list(transport.dispatch_order),
        "round_trip": True,
        "duplicate_dispatch_idempotent": True,
        "replay_ok": True,
        "acks": len(unique),
    }


def _audit_log(log: Any, turn: int) -> dict[str, Any]:
    """Check one turn's dispatch/result/ack/commit log is complete."""
    if log is None:
        raise AssertionError(f"turn {turn}: partitioned turn produced no bundle log")
    ids = tuple(log.dispatched)
    if len(ids) != len(set(ids)):
        raise AssertionError(f"turn {turn}: duplicate dispatched bundle id")
    if set(log.results) != set(ids):
        raise AssertionError(
            f"turn {turn}: results do not exactly cover dispatched bundles")
    if set(log.acks) != set(ids):
        raise AssertionError(
            f"turn {turn}: acks do not exactly cover dispatched bundles")
    if len(log.committed_order) != len(set(log.committed_order)):
        raise AssertionError(f"turn {turn}: duplicate committed bundle id")
    if set(log.committed_order) != set(ids):
        raise AssertionError(
            f"turn {turn}: committed order does not cover dispatched bundles")
    for bundle_id in ids:
        bundle = log.dispatched[bundle_id]
        result = log.results[bundle_id]
        ack = log.acks[bundle_id]
        if result.bundle_id != bundle_id or result.namespace != bundle.namespace:
            raise AssertionError(
                f"turn {turn}: result does not belong to {bundle_id!r}")
        if result.base_version != bundle.base_version:
            raise AssertionError(
                f"turn {turn}: stale result for {bundle_id!r}")
        if ack.outcome != "committed":
            raise AssertionError(
                f"turn {turn}: bundle {bundle_id!r} ack is {ack.outcome!r}")
        if ack.base_version != bundle.base_version:
            raise AssertionError(
                f"turn {turn}: ack base_version mismatch for {bundle_id!r}")
        if ack.execution_sha != result.execution_sha:
            raise AssertionError(
                f"turn {turn}: ack execution_sha mismatch for {bundle_id!r}")
    return {
        "bundles": len(ids),
        "bundle_ids": list(ids),
        "results": {
            bundle_id: {
                "status": log.results[bundle_id].status,
                "base_version": log.results[bundle_id].base_version,
                "execution_sha": log.results[bundle_id].execution_sha,
            }
            for bundle_id in ids
        },
        "acks": {
            bundle_id: {
                "outcome": log.acks[bundle_id].outcome,
                "base_version": log.acks[bundle_id].base_version,
                "committed_version": log.acks[bundle_id].committed_version,
                "execution_sha": log.acks[bundle_id].execution_sha,
            }
            for bundle_id in ids
        },
        "committed_order": list(log.committed_order),
        "order_matches_dispatch": log.committed_order == ids,
        "execution_sha": str(log.execution_sha),
        "payload_sha": log.payload_sha(),
        "payload_recorded": log.payload_sha() is not None,
    }


def _run_seed(*, scenario: str, seed: int, turns: int,
              affordance_mode: str) -> dict[str, Any]:
    """Run the serial/partitioned/replay matrix for one seed."""
    serial = build_game(scenario=scenario, seed=seed, executor="serial",
                        affordance_mode=affordance_mode)
    partitioned = build_game(scenario=scenario, seed=seed,
                             executor="partitioned",
                             affordance_mode=affordance_mode)
    replay = build_game(scenario=scenario, seed=seed, executor="partitioned",
                        affordance_mode=affordance_mode)

    tick_records: list[dict[str, Any]] = []
    partitioned_execution: list[str] = []
    replay_execution: list[str] = []
    wire_bundles: list[dict[str, Any]] = []
    first_payload_divergence = None
    first_execution_divergence = None
    total_bundles = 0

    for turn in range(1, turns + 1):
        results = [game.step() for game in (serial, partitioned, replay)]
        for name, result in zip(("serial", "partitioned", "replay"), results):
            if result.get("status") != "advanced":
                raise AssertionError(
                    f"turn {turn}: {name} returned {result.get('status')!r}")

        serial_payload = tick_payload_sha(serial.world)
        partitioned_payload = tick_payload_sha(partitioned.world)
        replay_payload = tick_payload_sha(replay.world)
        serial_state = semantic_world_state(serial.world)
        partitioned_state = semantic_world_state(partitioned.world)

        log = _audit_log(partitioned.last_bundle_log, turn)
        replay_log = _audit_log(replay.last_bundle_log, turn)
        total_bundles += log["bundles"]

        if log["payload_sha"] != partitioned_payload:
            raise AssertionError(
                f"turn {turn}: logged payload hash != post-turn world hash")
        if log["payload_sha"] != replay_log["payload_sha"]:
            raise AssertionError(
                f"turn {turn}: partitioned replay payload hash differs")

        payload_equal = (serial_state == partitioned_state
                         and serial_payload == partitioned_payload)
        if not payload_equal and first_payload_divergence is None:
            first_payload_divergence = {
                "turn": turn,
                "scope": "tick_payload_sha",
                "serial": serial_payload,
                "partitioned": partitioned_payload,
                "semantic_world_equal": serial_state == partitioned_state,
            }

        execution_equal = (
            log["execution_sha"] == replay_log["execution_sha"]
            and log["committed_order"] == replay_log["committed_order"])
        if not execution_equal and first_execution_divergence is None:
            first_execution_divergence = {
                "turn": turn,
                "scope": "tick_execution_sha",
                "partitioned": log["execution_sha"],
                "replay": replay_log["execution_sha"],
                "committed_order": log["committed_order"],
                "replay_committed_order": replay_log["committed_order"],
            }

        partitioned_execution.append(log["execution_sha"])
        replay_execution.append(replay_log["execution_sha"])
        wire_bundles.extend(
            _wire_bundle(partitioned.last_bundle_log.dispatched[bundle_id])
            for bundle_id in log["bundle_ids"])

        tick_records.append({
            "turn": turn,
            "serial_payload_sha": serial_payload,
            "partitioned_payload_sha": partitioned_payload,
            "replay_payload_sha": replay_payload,
            "payload_equal": payload_equal,
            "execution_sha": log["execution_sha"],
            "replay_execution_sha": replay_log["execution_sha"],
            "execution_stable": execution_equal,
            "bundles": log["bundles"],
            "bundle_ids": log["bundle_ids"],
            "results": log["results"],
            "acks": log["acks"],
            "committed_order": log["committed_order"],
            "order_matches_dispatch": log["order_matches_dispatch"],
        })

    fake = _fake_transport_check(wire_bundles)
    partitioned_run_sha = run_execution_sha(partitioned_execution)
    replay_run_sha = run_execution_sha(replay_execution)
    payload_equal = first_payload_divergence is None
    execution_stable = (first_execution_divergence is None
                        and partitioned_run_sha == replay_run_sha)
    return {
        "seed": seed,
        "payload_equal": payload_equal,
        "execution_stable": execution_stable,
        "bundle_count": total_bundles,
        "bundles_per_turn": [record["bundles"] for record in tick_records],
        "first_divergence": first_payload_divergence,
        "first_execution_divergence": first_execution_divergence,
        "partitioned_run_execution_sha": partitioned_run_sha,
        "replay_run_execution_sha": replay_run_sha,
        "fake_transport": fake,
        "ticks": tick_records,
    }


def build_report(*, seeds: list[int], turns: int, scenario: str,
                 affordance_mode: str) -> dict[str, Any]:
    """Build the verification report without printing or exiting."""
    report: dict[str, Any] = {
        "tool": "verify_bundle_equivalence",
        "scenario": scenario,
        "turns": turns,
        "affordance_mode": affordance_mode,
        "seeds": {},
        "ok": True,
    }
    for seed in seeds:
        try:
            result = _run_seed(scenario=scenario, seed=seed, turns=turns,
                               affordance_mode=affordance_mode)
        except Exception as exc:  # keep a report for the other seeds
            result = {
                "seed": seed,
                "payload_equal": False,
                "execution_stable": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        report["seeds"][str(seed)] = result
        report["ok"] = report["ok"] and _seed_ok(result)
    return report


def _seed_ok(result: dict[str, Any]) -> bool:
    return bool(
        result.get("payload_equal")
        and result.get("execution_stable")
        and not result.get("error")
        and (result.get("fake_transport") or {}).get("round_trip")
        and (result.get("fake_transport") or {}).get(
            "duplicate_dispatch_idempotent")
    )


def _print_summary(report: dict[str, Any]) -> None:
    print(f"scenario={report['scenario']} turns={report['turns']} "
          f"affordance={report['affordance_mode']}")
    for seed, result in report["seeds"].items():
        if result.get("error"):
            print(f"seed {seed}: ERROR {result['error']}")
            continue
        print(f"seed {seed}: payload_equal={result['payload_equal']} "
              f"execution_stable={result['execution_stable']} "
              f"bundles={result['bundle_count']}")
    print("OK" if report["ok"] else "FAILED")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default=",".join(map(str, DEFAULT_SEEDS)),
                        help="comma-separated seeds (default 305000,305002)")
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS)
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO)
    parser.add_argument("--affordance-mode", choices=("menu", "lazy"),
                        default="menu")
    parser.add_argument("--json", action="store_true",
                        help="emit compact JSON (default: indented JSON)")
    args = parser.parse_args(argv)

    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    if not seeds:
        parser.error("--seeds must name at least one seed")
    if args.turns < 1:
        parser.error("--turns must be at least 1")

    report = build_report(seeds=seeds, turns=args.turns,
                          scenario=args.scenario,
                          affordance_mode=args.affordance_mode)
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
