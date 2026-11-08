"""NB02: checksums and the per-tick bundle audit log.

No game, world or executor is built except for one tiny duck-typed world used
to prove the payload hash reuses ``semantic_world_state``.  Everything here is
pure protocol data.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from bigville.bundle_checks import (
    TickBundleLog,
    bundle_execution_sha,
    bundle_input_sha,
    bundle_output_sha,
    run_execution_sha,
    tick_execution_sha,
    tick_payload_sha,
)
from bigville.bundles import (
    Bundle,
    BundleAck,
    BundleOperation,
    BundleResult,
    ExecutionNamespace,
    QualifiedId,
)
from worlds.tick_graph import Resource


NS = ExecutionNamespace(
    run_id="17", executor="partitioned", shard=3, tick=42, bundle_seq=7)
ALT_NS = ExecutionNamespace(
    run_id="17", executor="serial", shard=3, tick=42, bundle_seq=7)

ACTOR = Resource("actor", "Ada")
CELL = Resource("cell", (1, 2))
WITNESS = Resource("witness", (1, 2))
BUNDLE_READS = (ACTOR, CELL)
BUNDLE_WRITES = (CELL, WITNESS)


def make_operation(op_id: str = "op1", *, actor: str | None = "Ada",
                   kind: str = "move", params=None,
                   reads=(ACTOR,), writes=(CELL,),
                   tiebreak=None) -> BundleOperation:
    return BundleOperation(
        op_id=op_id,
        actor=actor,
        kind=kind,
        params={} if params is None else params,
        reads=reads,
        writes=writes,
        tiebreak=(0, "Ada", op_id) if tiebreak is None else tiebreak,
    )


def make_bundle(bundle_id: str = "bundle-1", *,
                operations=None, reads=BUNDLE_READS, writes=BUNDLE_WRITES,
                namespace: ExecutionNamespace = NS,
                base_version: int = 3) -> Bundle:
    if operations is None:
        operations = (make_operation(),)
    return Bundle(
        bundle_id=bundle_id,
        namespace=namespace,
        run_id=namespace.run_id,
        tick=namespace.tick,
        shard=namespace.shard,
        base_version=base_version,
        operations=tuple(operations),
        reads=tuple(reads),
        writes=tuple(writes),
        tiebreak=(0, "Ada"),
    )


def make_result(bundle: Bundle, **overrides) -> BundleResult:
    values = {
        "bundle_id": bundle.bundle_id,
        "namespace": bundle.namespace,
        "base_version": bundle.base_version,
        "status": "ok",
        "effects": ({"op": "set_attr", "attr": "moved", "value": [2, 2]},),
        "created_ids": (QualifiedId(bundle.namespace.name, 101),),
        "result": (("Ada", True, None),),
        "output_sha": "pending",
        "execution_sha": "pending",
        "reason": "",
    }
    values.update(overrides)
    draft = BundleResult(**values)
    output_sha = bundle_output_sha(draft)
    draft = replace(draft, output_sha=output_sha)
    execution_sha = bundle_execution_sha(bundle, draft)
    return replace(draft, execution_sha=execution_sha)


def make_ack(bundle: Bundle, result: BundleResult | None = None, *,
             outcome: str = "committed",
             committed_version: int | None = None,
             execution_sha: str | None = None,
             reason: str = "") -> BundleAck:
    if execution_sha is None:
        if result is None:
            raise ValueError("an ack needs a result or an execution_sha")
        execution_sha = result.execution_sha
    if outcome == "committed" and committed_version is None:
        committed_version = bundle.base_version + 1
    if outcome != "committed":
        committed_version = None
    return BundleAck(
        bundle_id=bundle.bundle_id,
        base_version=bundle.base_version,
        outcome=outcome,
        committed_version=committed_version,
        execution_sha=execution_sha,
        reason=reason,
    )


def build_log(order, *, run_id: str = "17", tick: int = 42,
              acked=("a", "b"), committed=("a", "b")) -> TickBundleLog:
    """Build a two-bundle log with configurable arrival/commit order."""
    bundles = {bundle_id: make_bundle(f"bundle-{bundle_id}")
               for bundle_id in ("a", "b")}
    results = {bundle_id: make_result(bundle)
               for bundle_id, bundle in bundles.items()}
    acks = {bundle_id: make_ack(bundles[bundle_id], results[bundle_id])
            for bundle_id in acked}
    log = TickBundleLog(run_id, tick)
    for bundle_id in order:
        log.dispatch(bundles[bundle_id])
    for bundle_id in order:
        log.result(results[bundle_id])
    for bundle_id in reversed(order):
        if bundle_id in acks:
            log.acknowledge(acks[bundle_id])
    for bundle_id in committed:
        log.commit(f"bundle-{bundle_id}")
    return log


# --------------------------------------------------------------------------- bundle hashes


def test_identical_bundle_and_namespace_have_identical_hashes():
    bundle = make_bundle()
    result = make_result(bundle)

    assert bundle_input_sha(bundle) == bundle_input_sha(make_bundle())
    assert bundle_output_sha(result) == bundle_output_sha(make_result(bundle))
    assert bundle_execution_sha(bundle, result) == \
        bundle_execution_sha(make_bundle(), make_result(bundle))
    assert len(bundle_input_sha(bundle)) == 64


def test_input_hash_ignores_operation_and_resource_construction_order():
    first = make_operation(op_id="first", tiebreak=(1, "Ada", "first"),
                           reads=(ACTOR, CELL), writes=(CELL, WITNESS))
    second = make_operation(op_id="second", tiebreak=(2, "Bob", "second"),
                            reads=(ACTOR,), writes=(WITNESS,))
    left = make_bundle(
        operations=(first, second),
        reads=(ACTOR, CELL, WITNESS), writes=(CELL, WITNESS))
    right = make_bundle(
        operations=(second, first),
        reads=(WITNESS, CELL, ACTOR), writes=(WITNESS, CELL))

    assert left.operations != right.operations
    assert bundle_input_sha(left) == bundle_input_sha(right)
    assert bundle_input_sha(left) == bundle_input_sha(
        make_bundle(operations=(second, first),
                    reads=(CELL, ACTOR, WITNESS),
                    writes=(CELL, WITNESS)))


def test_input_hash_changes_with_base_version_and_namespace():
    bundle = make_bundle()
    assert bundle_input_sha(bundle) != bundle_input_sha(
        make_bundle(base_version=4))
    assert bundle_input_sha(bundle) != bundle_input_sha(
        make_bundle(namespace=ALT_NS))


def test_output_hash_ignores_self_referential_checksum_fields():
    bundle = make_bundle()
    result = make_result(bundle)
    edited = replace(result, output_sha="different", execution_sha="different")
    assert bundle_output_sha(edited) == bundle_output_sha(result)


def test_output_hash_is_order_insensitive_but_fact_sensitive():
    bundle = make_bundle()
    left = make_result(bundle, effects=(
        {"op": "set_attr", "attr": "a", "value": 1},
        {"op": "set_attr", "attr": "b", "value": 2},
    ))
    right = make_result(bundle, effects=(
        {"op": "set_attr", "attr": "b", "value": 2},
        {"op": "set_attr", "attr": "a", "value": 1},
    ))
    changed = make_result(bundle, effects=(
        {"op": "set_attr", "attr": "b", "value": 3},
        {"op": "set_attr", "attr": "a", "value": 1},
    ))

    assert bundle_output_sha(left) == bundle_output_sha(right)
    assert bundle_output_sha(left) != bundle_output_sha(changed)
    assert bundle_output_sha(left) != bundle_output_sha(
        make_result(bundle, status="refused"))
    assert bundle_output_sha(left) != bundle_output_sha(
        make_result(bundle, reason="because"))


def test_execution_hash_includes_namespace_and_attempt():
    bundle = make_bundle()
    result = make_result(bundle)
    alt_result = make_result(make_bundle(namespace=ALT_NS))
    retry_ns = ExecutionNamespace(
        run_id=NS.run_id, executor=NS.executor, shard=NS.shard,
        tick=NS.tick, bundle_seq=NS.bundle_seq, attempt=2)
    retry_bundle = make_bundle(namespace=retry_ns)
    retry_result = make_result(retry_bundle)

    serial = bundle_execution_sha(bundle, result)
    assert serial != bundle_execution_sha(
        make_bundle(namespace=ALT_NS), alt_result)
    assert serial != bundle_execution_sha(retry_bundle, retry_result)
    # The input hash already differs, but the execution hash must as well.
    assert bundle_execution_sha(bundle, result) == bundle_execution_sha(
        make_bundle(), make_result(make_bundle()))


@pytest.mark.parametrize("field,value", [
    ("bundle_id", "other-bundle"),
    ("base_version", 4),
])
def test_execution_hash_rejects_mismatched_result(field, value):
    bundle = make_bundle()
    result = make_result(bundle)
    bad = replace(result, **{field: value})
    with pytest.raises(ValueError):
        bundle_execution_sha(bundle, bad)


def test_execution_hash_rejects_mismatched_namespace_result():
    bundle = make_bundle()
    other = make_result(make_bundle(namespace=ALT_NS))
    with pytest.raises(ValueError):
        bundle_execution_sha(bundle, other)


def test_hash_functions_reject_wrong_types():
    with pytest.raises(TypeError):
        bundle_input_sha({"not": "a bundle"})
    with pytest.raises(TypeError):
        bundle_output_sha({"not": "a result"})
    with pytest.raises(TypeError):
        bundle_execution_sha(make_bundle(), {"not": "a result"})


# --------------------------------------------------------------------------- payload hash


def test_payload_hash_of_mapping_ignores_insertion_order():
    left = {"turn": 5, "actors": [{"name": "Ada", "cell": [1, 2]}],
            "stock": {"wood": 2}}
    right = {"stock": {"wood": 2},
             "actors": [{"name": "Ada", "cell": [1, 2]}], "turn": 5}

    assert tick_payload_sha(left) == tick_payload_sha(right)
    assert tick_payload_sha(left) != tick_payload_sha(
        {"turn": 6, "actors": [{"name": "Ada", "cell": [1, 2]}],
         "stock": {"wood": 2}})


class TinyWorld:
    """Minimal ``export_state`` duck type for the semantic projection."""

    def __init__(self, events, utterances):
        self.events = events
        self.utterances = utterances

    def export_state(self, event_tail=None):
        return {
            "turn": 5,
            "events": [dict(event) for event in self.events],
            "utterances": [dict(entry) for entry in self.utterances],
        }


def test_payload_hash_ignores_allocation_ids_and_log_order():
    first = TinyWorld(
        events=[{"id": 1, "kind": "birth", "who": "Ada"},
                {"id": 2, "kind": "build", "who": "Bob"}],
        utterances=[{"id": 101, "actor": "Ada", "text": "hello"}],
    )
    second = TinyWorld(
        events=[{"id": 9, "kind": "build", "who": "Bob"},
                {"id": 8, "kind": "birth", "who": "Ada"}],
        utterances=[{"id": 777, "actor": "Ada", "text": "hello"}],
    )

    assert tick_payload_sha(first) == tick_payload_sha(second)
    second.events[0]["who"] = "Cara"
    assert tick_payload_sha(first) != tick_payload_sha(second)


def test_payload_hash_rejects_non_mapping_without_export_state():
    with pytest.raises(TypeError):
        tick_payload_sha(["not", "a", "payload"])


# --------------------------------------------------------------------------- tick log


def test_tick_hash_is_independent_of_result_and_ack_arrival_order():
    left = build_log(("a", "b"))
    right = build_log(("b", "a"))

    assert left.results.keys() == right.results.keys()
    assert left.execution_sha == right.execution_sha == tick_execution_sha(left)
    # Both the property and no-argument method spellings are supported.
    assert left.execution_sha() == left.execution_sha


def test_missing_ack_changes_tick_hash():
    log = TickBundleLog("17", 42)
    bundle = make_bundle("bundle-a")
    result = make_result(bundle)
    ack = make_ack(bundle, result)
    log.dispatch(bundle)
    log.result(result)

    before = log.execution_sha
    log.acknowledge(ack)
    after = log.execution_sha
    assert before != after
    assert after == tick_execution_sha(log)


def test_committed_order_is_honoured():
    left = build_log(("a", "b"), committed=("a", "b"))
    right = build_log(("a", "b"), committed=("b", "a"))

    assert left.execution_sha != right.execution_sha
    assert left.committed_order == ("bundle-a", "bundle-b")
    assert right.committed_order == ("bundle-b", "bundle-a")


def test_ack_for_undispatched_bundle_is_rejected():
    log = TickBundleLog("17", 42)
    bundle = make_bundle("bundle-a")
    ack = make_ack(bundle, execution_sha="abc")
    with pytest.raises(ValueError):
        log.acknowledge(ack)


def test_extra_and_duplicate_acks():
    log = TickBundleLog("17", 42)
    bundle = make_bundle("bundle-a")
    result = make_result(bundle)
    ack = make_ack(bundle, result)
    log.dispatch(bundle)
    log.result(result)

    log.acknowledge(ack)
    digest = log.execution_sha
    # An identical repeat is idempotent and cannot inflate the audit.
    assert log.acknowledge(ack) is ack
    assert log.execution_sha == digest

    conflicting = make_ack(bundle, result, outcome="retry",
                           reason="coordinator changed its mind")
    with pytest.raises(ValueError):
        log.acknowledge(conflicting)

    ghost = make_ack(make_bundle("bundle-ghost"), execution_sha="abc")
    with pytest.raises(ValueError):
        log.acknowledge(ghost)


def test_dispatch_result_commit_validation():
    log = TickBundleLog("17", 42)
    bundle = make_bundle("bundle-a")
    result = make_result(bundle)

    with pytest.raises(ValueError):
        log.result(result)
    with pytest.raises(ValueError):
        log.commit(bundle.bundle_id)

    log.dispatch(bundle)
    assert log.dispatch(bundle) is bundle
    with pytest.raises(ValueError):
        log.dispatch(make_bundle("bundle-a", base_version=99))
    other_tick = ExecutionNamespace(
        run_id=NS.run_id, executor=NS.executor, shard=NS.shard,
        tick=NS.tick + 1, bundle_seq=0)
    with pytest.raises(ValueError):
        log.dispatch(make_bundle("bundle-other", namespace=other_tick))

    log.result(result)
    assert log.result(result) is result
    with pytest.raises(ValueError):
        log.result(make_result(bundle, status="refused"))

    log.commit(bundle.bundle_id)
    with pytest.raises(ValueError):
        log.commit(bundle.bundle_id)


def test_result_must_match_stored_bundle():
    log = TickBundleLog("17", 42)
    bundle = make_bundle("bundle-a")
    other = make_bundle("bundle-a", namespace=ALT_NS)
    log.dispatch(bundle)

    with pytest.raises(ValueError):
        log.result(make_result(other))
    with pytest.raises(ValueError):
        log.result(make_result(bundle, base_version=4))


def test_payload_hash_is_stored_not_faked():
    log = TickBundleLog("17", 42)
    payload = {"turn": 1, "actors": {"Ada": {"cell": [1, 2]}}}

    assert log.payload_sha() is None
    digest = log.payload_sha(payload)
    assert digest == tick_payload_sha(payload)
    assert log.payload_sha() == digest
    assert log.set_payload(payload) == digest

    with pytest.raises(ValueError):
        log.payload_sha({"turn": 2, "actors": {}})


def test_tick_log_to_dict_is_json_safe_and_deterministic():
    log = build_log(("a", "b"))
    log.payload_sha({"turn": 42, "actors": {"Ada": {"cell": [1, 2]}}})

    first = log.to_dict()
    second = log.to_dict()
    assert first == second
    assert first["committed_order"] == ["bundle-a", "bundle-b"]
    assert first["execution_sha"] == log.execution_sha
    assert first["payload_sha"] == log.payload_sha()
    assert list(first["dispatched"]) == ["bundle-a", "bundle-b"]
    assert list(first["results"]) == ["bundle-a", "bundle-b"]
    assert list(first["acks"]) == ["bundle-a", "bundle-b"]
    # The audit log is a plain JSON value: no live protocol objects leak.
    assert json.loads(json.dumps(first)) == first


# --------------------------------------------------------------------------- run hash


def test_run_hash_is_stable_over_tick_hashes():
    ticks = [tick_execution_sha(build_log(("a", "b"), committed=("a", "b"))),
             tick_execution_sha(build_log(("a", "b"), committed=("b", "a")))]

    assert run_execution_sha(ticks) == run_execution_sha(list(ticks))
    assert run_execution_sha(ticks) != run_execution_sha(list(reversed(ticks)))
    assert run_execution_sha(ticks) != run_execution_sha(ticks + ["extra"])
    assert run_execution_sha([]) == run_execution_sha([])


def test_run_hash_rejects_a_bare_string():
    with pytest.raises(TypeError):
        run_execution_sha("abcdef")
    with pytest.raises(ValueError):
        run_execution_sha([""])
