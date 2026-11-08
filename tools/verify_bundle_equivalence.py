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

DR05 adds three optional integration scopes:

``--journal PATH``
    Run the partitioned side with ``bundle_log_path``, then read, replay and
    verify the durable journal after every turn and compare the replayed tick
    log/checksums with ``game.last_bundle_log``.  With several seeds the path
    gets a ``.<seed>`` component (``dr05.305000.jsonl``) because one journal
    file has a single writer; with one seed the path is used exactly.  An
    existing file at that path is replaced at the start of the run.

``--deltas``
    For every partitioned result assert the effects are present on a turn that
    mutated the graph, rebuild the delta with ``GraphDelta.from_effects``,
    JSON round-trip it and check its base/end envelope against the bundle,
    result and committed ack.

``--process``
    Dispatch a couple of serialized bundles through a real
    ``ProcessBundleTransport`` with the synthetic ``delta`` executor, check
    stable checksums and idempotence, and close the workers.  If process
    workers cannot start in this environment the check is reported as skipped
    rather than failed.

Usage:

    python3 tools/verify_bundle_equivalence.py
    python3 tools/verify_bundle_equivalence.py --seeds 305000,305002 --turns 8
    python3 tools/verify_bundle_equivalence.py --seeds 305002 --affordance-mode lazy
    python3 tools/verify_bundle_equivalence.py --json
    python3 tools/verify_bundle_equivalence.py --journal /tmp/dr05.jsonl \
        --deltas --process

Exit code 0 means every requested scope matched.  A divergence names the first
turn and the checksum/revision scope that differed.
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
from bigville.process_transport import ProcessBundleTransport, delta_executor
from bigville.runtime import GraphDelta
from bigville.tick_trace import semantic_world_state


DEFAULT_SEEDS = (305000, 305002)
DEFAULT_TURNS = 8
DEFAULT_SCENARIO = "town100"


def build_game(*, scenario: str, seed: int, executor: str,
               affordance_mode: str, bundle_log_path: str | None = None):
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
        bundle_log_path=bundle_log_path,
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


def _process_transport_check(wire_bundles: list[dict[str, Any]],
                             *, limit: int = 2) -> dict[str, Any]:
    """Round-trip a couple of bundles through a real process worker.

    The executor is the synthetic ``delta`` worker: it applies the bundle's
    operations to a plain JSON state and never imports the live game.  Process
    startup is the only part treated as skippable; once a worker is up, a
    checksum/idempotence divergence is a real failure.
    """
    import multiprocessing

    selected = wire_bundles[:limit]
    if not selected:
        return {"skipped": True, "reason": "no bundles to dispatch"}
    start_method = ("fork" if "fork" in multiprocessing.get_all_start_methods()
                    else None)
    try:
        transport = ProcessBundleTransport(executor="delta", workers=1,
                                           timeout=5.0, retries=0,
                                           start_method=start_method)
    except Exception as exc:  # environment has no usable process workers
        return {
            "skipped": True,
            "reason": f"{type(exc).__name__}: {exc}",
            "start_method": start_method,
        }

    unique: set[str] = set()
    try:
        for wire in selected:
            bundle = Bundle.from_dict(wire)
            result = transport.dispatch(bundle)
            duplicate = transport.dispatch(
                Bundle.from_dict(_wire_bundle(bundle)))
            if duplicate is not result:
                raise AssertionError(
                    f"process duplicate dispatch of {bundle.bundle_id!r} "
                    f"was not cached")
            expected = delta_executor(bundle)
            if result.output_sha != expected.output_sha:
                raise AssertionError(
                    f"process output checksum is not stable for "
                    f"{bundle.bundle_id!r}")
            if result.execution_sha != expected.execution_sha:
                raise AssertionError(
                    f"process execution checksum is not stable for "
                    f"{bundle.bundle_id!r}")
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
                    f"process replay lost {bundle.bundle_id!r}")
            if transport.acknowledgement(bundle.bundle_id) != ack:
                raise AssertionError(
                    f"process ack was not recorded for {bundle.bundle_id!r}")
            unique.add(bundle.bundle_id)
        if transport.executions != len(unique):
            raise AssertionError(
                f"process transport executed {transport.executions} bundles "
                f"for {len(unique)} unique ids")
        report = {
            "skipped": False,
            "start_method": start_method,
            "bundles": len(unique),
            "unique_ids": len(unique),
            "dispatch_order": list(transport.dispatch_order),
            "executions": transport.executions,
            "round_trip": True,
            "duplicate_dispatch_idempotent": True,
            "checksums_stable": True,
            "acks": len(unique),
        }
    finally:
        transport.close()
    return report


def _audit_deltas(log: Any, *, turn: int, pre_revision: int,
                  post_revision: int) -> dict[str, Any]:
    """Check per-result effects and the delta revision envelope.

    The result carries its base but not its end revision (DR03), so the
    committed ack's observed version is used as the end bound.  It must be at
    least the delta base and no newer than the post-turn graph revision.  A
    turn that advanced the graph revision must have at least one bundle with
    effects; otherwise the recorded delta is incomplete.
    """
    mutated = post_revision > pre_revision
    bundles_with_effects = 0
    effects_total = 0
    records: dict[str, dict[str, Any]] = {}
    for bundle_id in log.dispatched:
        bundle = log.dispatched[bundle_id]
        result = log.results[bundle_id]
        ack = log.acks[bundle_id]
        effects = tuple(result.effects)
        if not effects:
            records[bundle_id] = {
                "effects": 0,
                "base_version": result.base_version,
                "committed_version": ack.committed_version,
            }
            continue
        bundles_with_effects += 1
        effects_total += len(effects)
        if result.base_version != bundle.base_version:
            raise AssertionError(
                f"turn {turn}: result/delta base differs from the bundle for "
                f"{bundle_id!r}")
        delta = GraphDelta.from_effects(
            effects, base_revision=result.base_version)
        if delta.base_revision != result.base_version:
            raise AssertionError(
                f"turn {turn}: delta base {delta.base_revision} != result base "
                f"{result.base_version} for {bundle_id!r}")
        wire = json.loads(json.dumps(delta.to_dict(), sort_keys=True,
                                     allow_nan=False))
        rebuilt = GraphDelta.from_dict(wire)
        if rebuilt.to_dict() != delta.to_dict():
            raise AssertionError(
                f"turn {turn}: delta JSON round trip changed {bundle_id!r}")
        if rebuilt.to_effects() != effects:
            raise AssertionError(
                f"turn {turn}: delta effects round trip changed {bundle_id!r}")
        committed = ack.committed_version
        end = result.base_version if committed is None else int(committed)
        if end < delta.base_revision:
            raise AssertionError(
                f"turn {turn}: committed version {end} is older than delta "
                f"base {delta.base_revision} for {bundle_id!r}")
        if end > post_revision:
            raise AssertionError(
                f"turn {turn}: committed version {end} is newer than the "
                f"post-turn revision {post_revision} for {bundle_id!r}")
        enveloped = GraphDelta.from_effects(
            effects, base_revision=result.base_version, end_revision=end)
        rebuilt_envelope = GraphDelta.from_dict(json.loads(json.dumps(
            enveloped.to_dict(), sort_keys=True, allow_nan=False)))
        if rebuilt_envelope.to_dict() != enveloped.to_dict():
            raise AssertionError(
                f"turn {turn}: delta revision envelope round trip changed "
                f"{bundle_id!r}")
        records[bundle_id] = {
            "effects": len(effects),
            "base_version": result.base_version,
            "committed_version": committed,
            "end_revision": end,
            "json_round_trip": True,
        }

    if mutated and bundles_with_effects == 0:
        raise AssertionError(
            f"turn {turn}: graph revision advanced {pre_revision} -> "
            f"{post_revision} but no bundle recorded effects")
    return {
        "mutated": mutated,
        "pre_revision": pre_revision,
        "post_revision": post_revision,
        "bundles_with_effects": bundles_with_effects,
        "bundles_without_effects": len(log.dispatched) - bundles_with_effects,
        "effects_total": effects_total,
        "bundles": records,
        "ok": True,
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
              affordance_mode: str, journal_path: Path | None = None,
              deltas: bool = False, process: bool = False) -> dict[str, Any]:
    """Run the serial/partitioned/replay matrix for one seed."""
    if journal_path is not None:
        # A verification run starts from a fresh audit file.  The journal has a
        # single-writer rule; replacing a stale file keeps repeated runs
        # comparable and avoids appending to another run's tick blocks.
        journal_path = Path(journal_path)
        journal_path.unlink(missing_ok=True)

    serial = build_game(scenario=scenario, seed=seed, executor="serial",
                        affordance_mode=affordance_mode)
    partitioned = build_game(scenario=scenario, seed=seed,
                             executor="partitioned",
                             affordance_mode=affordance_mode,
                             bundle_log_path=(None if journal_path is None
                                              else str(journal_path)))
    replay = build_game(scenario=scenario, seed=seed, executor="partitioned",
                        affordance_mode=affordance_mode)

    journal = partitioned.bundle_journal
    tick_records: list[dict[str, Any]] = []
    partitioned_execution: list[str] = []
    replay_execution: list[str] = []
    wire_bundles: list[dict[str, Any]] = []
    first_payload_divergence = None
    first_execution_divergence = None
    first_revision_divergence = None
    journal_divergence = None
    delta_divergence = None
    revision_history: list[int] = []
    total_bundles = 0
    bundles_with_effects = 0
    effects_total = 0
    mutated_turns = 0

    try:
        for turn in range(1, turns + 1):
            pre_revisions = [game.world.revision
                             for game in (serial, partitioned, replay)]
            results = [game.step() for game in (serial, partitioned, replay)]
            for name, result in zip(("serial", "partitioned", "replay"),
                                    results):
                if result.get("status") != "advanced":
                    raise AssertionError(
                        f"turn {turn}: {name} returned "
                        f"{result.get('status')!r}")

            serial_revision = serial.world.revision
            partitioned_revision = partitioned.world.revision
            replay_revision = replay.world.revision
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

            revision_equal = (
                serial_revision == partitioned_revision == replay_revision)
            if not revision_equal and first_revision_divergence is None:
                first_revision_divergence = {
                    "turn": turn,
                    "scope": "graph_revision",
                    "serial": serial_revision,
                    "partitioned": partitioned_revision,
                    "replay": replay_revision,
                }
            if revision_history and partitioned_revision < revision_history[-1]:
                raise AssertionError(
                    f"turn {turn}: partitioned revision went backwards "
                    f"{revision_history[-1]} -> {partitioned_revision}")
            revision_history.append(partitioned_revision)

            partitioned_execution.append(log["execution_sha"])
            replay_execution.append(replay_log["execution_sha"])
            wire_bundles.extend(
                _wire_bundle(partitioned.last_bundle_log.dispatched[bundle_id])
                for bundle_id in log["bundle_ids"])

            record: dict[str, Any] = {
                "turn": turn,
                "serial_payload_sha": serial_payload,
                "partitioned_payload_sha": partitioned_payload,
                "replay_payload_sha": replay_payload,
                "payload_equal": payload_equal,
                "execution_sha": log["execution_sha"],
                "replay_execution_sha": replay_log["execution_sha"],
                "execution_stable": execution_equal,
                "serial_revision": serial_revision,
                "partitioned_revision": partitioned_revision,
                "replay_revision": replay_revision,
                "revision_equal": revision_equal,
                "bundles": log["bundles"],
                "bundle_ids": log["bundle_ids"],
                "results": log["results"],
                "acks": log["acks"],
                "committed_order": log["committed_order"],
                "order_matches_dispatch": log["order_matches_dispatch"],
            }

            if journal is not None:
                verification = journal.verify()
                replayed_logs = journal.replay()
                if not replayed_logs:
                    raise AssertionError(
                        f"turn {turn}: journal replayed no ticks")
                replayed = replayed_logs[-1]
                live = partitioned.last_bundle_log
                replay_equal = replayed.to_dict() == live.to_dict()
                if not replay_equal and journal_divergence is None:
                    journal_divergence = {
                        "turn": turn,
                        "scope": "journal_tick_log",
                    }
                if not replay_equal:
                    raise AssertionError(
                        f"turn {turn}: journal replay tick log differs from "
                        f"last_bundle_log")
                if replayed.execution_sha != log["execution_sha"]:
                    raise AssertionError(
                        f"turn {turn}: journal execution checksum differs")
                if replayed.payload_sha() != partitioned_payload:
                    raise AssertionError(
                        f"turn {turn}: journal payload checksum differs")
                if verification.ticks != turn:
                    raise AssertionError(
                        f"turn {turn}: journal has {verification.ticks} ticks")
                if verification.aborted_ticks:
                    raise AssertionError(
                        f"turn {turn}: journal has aborted ticks")
                journal_record = {
                    "path": str(journal.path),
                    "ticks": verification.ticks,
                    "records": verification.records,
                    "bundles": verification.bundles,
                    "bytes": verification.byte_size,
                    "replay_equal": replay_equal,
                    "execution_equal": True,
                    "payload_equal": True,
                    "aborted_ticks": verification.aborted_ticks,
                    "truncated_tail": verification.truncated_tail,
                }
                record["journal_replay_equal"] = replay_equal
                record["journal"] = journal_record

            if deltas:
                delta_record = _audit_deltas(
                    partitioned.last_bundle_log, turn=turn,
                    pre_revision=pre_revisions[1],
                    post_revision=partitioned_revision)
                bundles_with_effects += delta_record["bundles_with_effects"]
                effects_total += delta_record["effects_total"]
                mutated_turns += int(delta_record["mutated"])
                record["delta_presence"] = (
                    delta_record["bundles_with_effects"] > 0)
                record["deltas"] = delta_record

            tick_records.append(record)
    finally:
        if journal is not None:
            journal.close()

    fake = _fake_transport_check(wire_bundles)
    process_result = None
    if process:
        process_result = _process_transport_check(wire_bundles)
    partitioned_run_sha = run_execution_sha(partitioned_execution)
    replay_run_sha = run_execution_sha(replay_execution)
    payload_equal = first_payload_divergence is None
    execution_stable = (first_execution_divergence is None
                        and partitioned_run_sha == replay_run_sha)
    revision_equal = first_revision_divergence is None
    result: dict[str, Any] = {
        "seed": seed,
        "payload_equal": payload_equal,
        "execution_stable": execution_stable,
        "revision_equal": revision_equal,
        "revision_history": revision_history,
        "bundle_count": total_bundles,
        "bundles_per_turn": [record["bundles"] for record in tick_records],
        "first_divergence": first_payload_divergence,
        "first_execution_divergence": first_execution_divergence,
        "first_revision_divergence": first_revision_divergence,
        "partitioned_run_execution_sha": partitioned_run_sha,
        "replay_run_execution_sha": replay_run_sha,
        "fake_transport": fake,
        "ticks": tick_records,
    }
    if journal is not None:
        result["journal"] = {
            "path": str(journal.path),
            "bytes": journal.path.stat().st_size,
            "ticks": len(tick_records),
            "bundles": sum(record["bundles"] for record in tick_records),
            "replay_equal": journal_divergence is None,
            "verified": journal_divergence is None,
        }
    if deltas:
        result["deltas"] = {
            "ok": delta_divergence is None,
            "mutated_turns": mutated_turns,
            "bundles_with_effects": bundles_with_effects,
            "effects_total": effects_total,
        }
    if process_result is not None:
        result["process"] = process_result
    return result


def _journal_path_for(base: Path, seed: int, *, single: bool) -> Path:
    """Per-seed journal path; one file cannot be opened by two writers."""
    if single:
        return Path(base)
    suffix = base.suffix or ".jsonl"
    stem = base.name[:-len(base.suffix)] if base.suffix else base.name
    return base.with_name(f"{stem}.{seed}{suffix}")


def build_report(*, seeds: list[int], turns: int, scenario: str,
                 affordance_mode: str, journal: str | None = None,
                 deltas: bool = False,
                 process: bool = False) -> dict[str, Any]:
    """Build the verification report without printing or exiting."""
    report: dict[str, Any] = {
        "tool": "verify_bundle_equivalence",
        "scenario": scenario,
        "turns": turns,
        "affordance_mode": affordance_mode,
        "journal_enabled": journal is not None,
        "deltas_enabled": bool(deltas),
        "process_enabled": bool(process),
        "seeds": {},
        "ok": True,
    }
    for seed in seeds:
        seed_journal = (None if journal is None else
                        _journal_path_for(Path(journal), seed,
                                          single=len(seeds) == 1))
        try:
            result = _run_seed(
                scenario=scenario, seed=seed, turns=turns,
                affordance_mode=affordance_mode,
                journal_path=seed_journal, deltas=deltas, process=process)
        except Exception as exc:  # keep a report for the other seeds
            result = {
                "seed": seed,
                "payload_equal": False,
                "execution_stable": False,
                "revision_equal": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
            if seed_journal is not None:
                result["journal"] = {"path": str(seed_journal),
                                     "replay_equal": False}
        report["seeds"][str(seed)] = result
        report["ok"] = report["ok"] and _seed_ok(result)
    return report


def _seed_ok(result: dict[str, Any]) -> bool:
    ok = bool(
        result.get("payload_equal")
        and result.get("execution_stable")
        and result.get("revision_equal", True)
        and not result.get("error")
        and (result.get("fake_transport") or {}).get("round_trip")
        and (result.get("fake_transport") or {}).get(
            "duplicate_dispatch_idempotent")
    )
    if "journal" in result:
        ok = ok and bool(result["journal"].get("replay_equal"))
    if "deltas" in result:
        ok = ok and bool(result["deltas"].get("ok"))
    process = result.get("process")
    if process is not None and not process.get("skipped"):
        ok = ok and bool(process.get("round_trip")
                         and process.get("duplicate_dispatch_idempotent")
                         and process.get("checksums_stable"))
    return ok


def _print_summary(report: dict[str, Any]) -> None:
    print(f"scenario={report['scenario']} turns={report['turns']} "
          f"affordance={report['affordance_mode']}")
    for seed, result in report["seeds"].items():
        if result.get("error"):
            print(f"seed {seed}: ERROR {result['error']}")
            continue
        line = (f"seed {seed}: payload_equal={result['payload_equal']} "
                f"execution_stable={result['execution_stable']} "
                f"revision_equal={result.get('revision_equal')} "
                f"bundles={result['bundle_count']}")
        if "journal" in result:
            line += f" journal={result['journal'].get('replay_equal')}"
        if "deltas" in result:
            line += f" deltas={result['deltas'].get('ok')}"
        if "process" in result:
            process = result["process"]
            line += (" process=skipped" if process.get("skipped")
                     else f" process={process.get('round_trip')}")
        print(line)
    print("OK" if report["ok"] else "FAILED")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default=",".join(map(str, DEFAULT_SEEDS)),
                        help="comma-separated seeds (default 305000,305002)")
    parser.add_argument("--turns", type=int, default=DEFAULT_TURNS)
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO)
    parser.add_argument("--affordance-mode", choices=("menu", "lazy"),
                        default="menu")
    parser.add_argument("--journal", metavar="PATH", default=None,
                        help="run the partitioned side with a durable journal "
                             "(per-seed path when several seeds are named)")
    parser.add_argument("--deltas", action="store_true",
                        help="verify result effects and GraphDelta envelopes")
    parser.add_argument("--process", action="store_true",
                        help="round-trip bundles through a real process worker")
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
                          affordance_mode=args.affordance_mode,
                          journal=args.journal, deltas=args.deltas,
                          process=args.process)
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
