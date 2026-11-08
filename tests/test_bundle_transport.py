"""NB05: the bundle protocol is transport-neutral and wire-serialisable.

These tests deliberately build no ``BigvilleGame`` and never import the world or
executor modules.  A bundle is JSON round-tripped, then dispatched through
``LocalBundleTransport`` with a synthetic executor that computes its result
from the plain bundle data alone.  That is the same path a process/socket
transport would use: ``Bundle -> JSON -> Bundle -> BundleResult -> JSON ->
BundleAck``.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from bigville.bundle_checks import bundle_execution_sha, bundle_output_sha
from bigville.bundles import (
    Bundle,
    BundleAck,
    BundleOperation,
    BundleResult,
    ExecutionNamespace,
    LocalBundleTransport,
    QualifiedId,
)
from worlds.tick_graph import Resource


NS = ExecutionNamespace(
    run_id="transport-demo", executor="remote", shard=2, tick=5, bundle_seq=1)
OTHER_NS = ExecutionNamespace(
    run_id="transport-demo", executor="remote", shard=2, tick=5, bundle_seq=2)

ACTOR = Resource("actor", "Ada")
CELL = Resource("cell", (3, 4))
WITNESS = Resource("witness", (3, 4))


def make_bundle() -> Bundle:
    """A bundle with two operations and nested JSON-safe parameters."""
    move = BundleOperation(
        op_id="move-1",
        actor="Ada",
        kind="move",
        params={"destination": [3, 4], "price": 2.5, "meta": {"reason": "go"}},
        reads=(ACTOR,),
        writes=(CELL, WITNESS),
        tiebreak=(0, "Ada", "move-1"),
    )
    speak = BundleOperation(
        op_id="speak-1",
        actor="Ada",
        kind="speak",
        params={"text": "hello", "audience": ["Ben"]},
        reads=(ACTOR,),
        writes=(WITNESS,),
        tiebreak=(1, "Ada", "speak-1"),
    )
    return Bundle(
        bundle_id=NS.name,
        namespace=NS,
        run_id=NS.run_id,
        tick=NS.tick,
        shard=NS.shard,
        base_version=5,
        operations=(move, speak),
        reads=(ACTOR, CELL, WITNESS),
        writes=(CELL, WITNESS),
        tiebreak=(0, "Ada"),
    )


def wire_round_trip(value):
    """JSON encode/decode exactly like a transport boundary would."""
    return json.loads(json.dumps(value.to_dict(), sort_keys=True,
                                 allow_nan=False))


def synthetic_executor(bundle: Bundle) -> BundleResult:
    """Execute a bundle from plain data only; no game or world exists here."""
    effects = []
    rows = []
    for operation in bundle.ordered_operations():
        params = dict(operation.params)
        value = params.get("price", 0)
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


def ack_for(bundle: Bundle, result: BundleResult) -> BundleAck:
    return BundleAck(
        bundle_id=bundle.bundle_id,
        base_version=bundle.base_version,
        outcome="committed",
        committed_version=bundle.base_version,
        execution_sha=result.execution_sha,
    )


def test_serialized_bundle_dispatches_acknowledges_and_replays_without_a_game():
    bundle = make_bundle()
    restored = Bundle.from_dict(wire_round_trip(bundle))

    assert restored == bundle
    assert restored.to_dict() == bundle.to_dict()
    assert restored.canonical_json() == bundle.canonical_json()

    calls: list[str] = []

    def counting_executor(value: Bundle) -> BundleResult:
        calls.append(value.bundle_id)
        return synthetic_executor(value)

    transport = LocalBundleTransport(counting_executor)
    result = transport.dispatch(restored)

    assert result.bundle_id == restored.bundle_id
    assert result.namespace == restored.namespace
    assert result.base_version == restored.base_version
    assert result.status == "ok"
    assert result.execution_sha == synthetic_executor(restored).execution_sha

    ack = ack_for(restored, result)
    transport.acknowledge(ack)
    assert transport.acknowledgement(restored.bundle_id) == ack
    assert transport.replay(restored.bundle_id) is result
    assert transport.dispatch_order == (restored.bundle_id,)

    # A retry from the same serialized form is idempotent: one execution only.
    again = transport.dispatch(Bundle.from_dict(wire_round_trip(bundle)))
    assert again is result
    assert calls == [bundle.bundle_id]


def test_wire_result_and_ack_replay_through_a_fresh_transport():
    bundle = make_bundle()
    result = synthetic_executor(bundle)
    ack = ack_for(bundle, result)

    # Round-trip the result and ack as separate wire messages.
    wire_result = BundleResult.from_dict(wire_round_trip(result))
    wire_ack = BundleAck.from_dict(wire_round_trip(ack))
    assert wire_result == result
    assert wire_ack == ack

    def must_not_run(_bundle: Bundle) -> BundleResult:
        raise AssertionError("a preloaded replay must not execute")

    transport = LocalBundleTransport(
        must_not_run,
        results={result.bundle_id: wire_result})
    replayed = transport.dispatch(Bundle.from_dict(wire_round_trip(bundle)))
    assert replayed == result
    assert transport.replay(result.bundle_id) is wire_result
    transport.acknowledge(wire_ack)
    assert transport.acknowledgement(result.bundle_id) == wire_ack
    assert transport.dispatch_order == ()


def test_checksums_are_reproducible_from_the_wire_form():
    bundle = make_bundle()
    restored = Bundle.from_dict(wire_round_trip(bundle))
    result = synthetic_executor(restored)
    wire_result = BundleResult.from_dict(wire_round_trip(result))

    assert result == wire_result
    assert bundle_output_sha(result) == bundle_output_sha(wire_result)
    assert bundle_execution_sha(bundle, result) == \
        bundle_execution_sha(restored, wire_result)


@pytest.mark.parametrize("mutation, message", [
    ("stale", "base_version"),
    ("namespace", "namespace"),
])
def test_stale_or_mismatched_results_are_rejected_and_not_cached(mutation, message):
    bundle = Bundle.from_dict(wire_round_trip(make_bundle()))
    good = synthetic_executor(bundle)
    stale = (replace(good, base_version=bundle.base_version + 1)
             if mutation == "stale" else replace(
                 good, namespace=OTHER_NS, created_ids=()))

    transport = LocalBundleTransport(lambda _bundle: stale)
    with pytest.raises(ValueError, match=message):
        transport.dispatch(bundle)
    assert transport.replay(bundle.bundle_id) is None
    assert transport.dispatch_order == ()


def test_stale_or_mismatched_acks_are_rejected():
    bundle = make_bundle()
    transport = LocalBundleTransport(synthetic_executor)
    result = transport.dispatch(bundle)

    with pytest.raises(ValueError, match="base_version"):
        transport.acknowledge(replace(
            ack_for(bundle, result), base_version=bundle.base_version + 1))
    with pytest.raises(ValueError, match="execution_sha"):
        transport.acknowledge(replace(
            ack_for(bundle, result), execution_sha="not-the-result"))
    with pytest.raises(ValueError, match="unknown bundle"):
        transport.acknowledge(BundleAck(
            bundle_id="missing-bundle",
            base_version=bundle.base_version,
            outcome="committed",
            committed_version=bundle.base_version,
            execution_sha=result.execution_sha,
        ))
    assert transport.acknowledgement(bundle.bundle_id) is None
