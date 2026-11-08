"""NB01: pure bundle/dispatch/ack protocol and in-process transport.

These tests exercise the wire shapes, their validation, deterministic
canonicalisation, and the idempotence/ack contract of
``LocalBundleTransport``.  No game, world or executor is built.
"""
from __future__ import annotations

import json
import threading

import pytest

from bigville.bundles import (
    Bundle,
    BundleAck,
    BundleOperation,
    BundleResult,
    BundleTransport,
    BundleValueError,
    ExecutionNamespace,
    LocalBundleTransport,
    QualifiedId,
    canonical_json,
)
from bigville.runtime import NodeRef
from worlds.tick_graph import Resource


NS = ExecutionNamespace(
    run_id="17", executor="partitioned", shard=3, tick=42, bundle_seq=7)
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
        "output_sha": f"output-{bundle.bundle_id}",
        "execution_sha": f"execution-{bundle.bundle_id}",
        "reason": "",
    }
    values.update(overrides)
    return BundleResult(**values)


# --------------------------------------------------------------------------- namespace


def test_namespace_name_grammar_and_round_trip():
    assert NS.name == "r17/t42/partitioned/s3/b7/a1"
    assert ExecutionNamespace.parse(NS.name) == NS
    assert ExecutionNamespace.is_valid_name(NS.name)

    restored = ExecutionNamespace.from_dict(NS.to_dict())
    assert restored == NS
    assert restored.name == NS.name


def test_namespace_attempt_and_defaults():
    assert ExecutionNamespace("1", "serial", 0, 0, 0).name == \
        "r1/t0/serial/s0/b0/a1"
    retry = ExecutionNamespace("1", "serial", 0, 0, 0, attempt=2)
    assert retry.name.endswith("/a2")
    assert retry != ExecutionNamespace("1", "serial", 0, 0, 0)


@pytest.mark.parametrize("kwargs", [
    {"run_id": "", "executor": "e", "shard": 0, "tick": 0, "bundle_seq": 0},
    {"run_id": "run", "executor": "", "shard": 0, "tick": 0,
     "bundle_seq": 0},
    {"run_id": "a/b", "executor": "e", "shard": 0, "tick": 0,
     "bundle_seq": 0},
    {"run_id": "run", "executor": "e/x", "shard": 0, "tick": 0,
     "bundle_seq": 0},
    {"run_id": "a#b", "executor": "e", "shard": 0, "tick": 0,
     "bundle_seq": 0},
    {"run_id": "run", "executor": "e#x", "shard": 0, "tick": 0,
     "bundle_seq": 0},
    {"run_id": "run", "executor": "e", "shard": -1, "tick": 0,
     "bundle_seq": 0},
    {"run_id": "run", "executor": "e", "shard": 0, "tick": -1,
     "bundle_seq": 0},
    {"run_id": "run", "executor": "e", "shard": 0, "tick": 0,
     "bundle_seq": -1},
    {"run_id": "run", "executor": "e", "shard": 0, "tick": 0,
     "bundle_seq": 0, "attempt": 0},
    {"run_id": "run", "executor": "e", "shard": True, "tick": 0,
     "bundle_seq": 0},
    {"run_id": 17, "executor": "e", "shard": 0, "tick": 0,
     "bundle_seq": 0},
])
def test_namespace_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        ExecutionNamespace(**kwargs)


@pytest.mark.parametrize("text", [
    "",
    "17/t42/partitioned/s3/b7/a1",
    "r17/t042/partitioned/s3/b7/a1",
    "r17/t42/partitioned/s3/b7/a0",
    "r17/t42/partitioned/s3/b7/a1/",
    "r17/t42/partitioned/s3/b7",
    "r17/t42/partitioned/x3/b7/a1",
    "r/t42/partitioned/s3/b7/a1",
    "r17/t42//s3/b7/a1",
    "r17#x/t42/partitioned/s3/b7/a1",
])
def test_namespace_parse_rejects_non_canonical_names(text):
    with pytest.raises(ValueError):
        ExecutionNamespace.parse(text)
    assert not ExecutionNamespace.is_valid_name(text)


def test_namespace_from_dict_rejects_missing_and_extra_keys():
    data = NS.to_dict()
    with pytest.raises(ValueError):
        ExecutionNamespace.from_dict({key: data[key] for key in data
                                      if key != "tick"})
    with pytest.raises(ValueError):
        ExecutionNamespace.from_dict({**data, "extra": 1})


# --------------------------------------------------------------------------- qualified id


def test_qualified_id_string_and_round_trip():
    qualified = QualifiedId(NS.name, 42)
    assert str(qualified) == f"{NS.name}#42"
    assert QualifiedId.parse(str(qualified)) == qualified
    assert QualifiedId.from_dict(qualified.to_dict()) == qualified
    assert json.loads(json.dumps(qualified.to_dict())) == qualified.to_dict()


@pytest.mark.parametrize("kwargs", [
    {"namespace": "", "local_id": 0},
    {"namespace": "a#b", "local_id": 0},
    {"namespace": NS.name, "local_id": -1},
    {"namespace": NS.name, "local_id": True},
])
def test_qualified_id_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        QualifiedId(**kwargs)


@pytest.mark.parametrize("text", ["", "no-separator", "#1", "ns#", "ns#x"])
def test_qualified_id_parse_rejects_invalid_text(text):
    with pytest.raises(ValueError):
        QualifiedId.parse(text)


# --------------------------------------------------------------------------- operations


def test_operation_is_frozen_and_params_are_read_only():
    operation = make_operation(params={"speed": 1, "path": (1, 2)})
    assert isinstance(operation.reads, tuple)
    assert isinstance(operation.writes, tuple)
    assert operation.tiebreak == (0, "Ada", "op1")
    # Tuples normalise to deterministic JSON lists exactly once.
    assert operation.params["path"] == [1, 2]
    with pytest.raises(TypeError):
        operation.params["speed"] = 2  # type: ignore[index]
    with pytest.raises(AttributeError):
        operation.op_id = "other"  # type: ignore[misc]


def test_operation_round_trip_and_canonical_form():
    operation = make_operation(
        params={"z": 1, "a": {"nested": [True, None]}}, tiebreak=(0, "Ada"))
    restored = BundleOperation.from_dict(operation.to_dict())
    assert restored == operation
    assert restored.to_dict() == operation.to_dict()
    assert restored.canonical_dict() == operation.canonical_dict()
    json.dumps(operation.to_dict(), allow_nan=False)


def test_operation_rejects_non_json_values():
    with pytest.raises(BundleValueError):
        make_operation(params={"bad": {1, 2}})
    with pytest.raises(BundleValueError):
        make_operation(params={1: "non-string key"})
    with pytest.raises(BundleValueError):
        make_operation(params={"nan": float("nan")})
    with pytest.raises(ValueError, match="tiebreak"):
        make_operation(tiebreak="not-a-sequence")


# --------------------------------------------------------------------------- bundle


def test_bundle_round_trip_and_dedupe_key():
    bundle = make_bundle(operations=(
        make_operation("op1", tiebreak=(0, "Ada")),
        make_operation("op2", kind="speak", reads=(ACTOR,), writes=(WITNESS,),
                       tiebreak=(1, "Ada")),
    ))
    restored = Bundle.from_dict(bundle.to_dict())
    assert restored == bundle
    assert restored.to_dict() == bundle.to_dict()
    assert restored.dedupe_key == "bundle-1"
    assert restored.canonical_json() == bundle.canonical_json()
    json.dumps(bundle.to_dict(), allow_nan=False)


def test_bundle_canonical_form_ignores_operation_and_resource_order():
    first = make_operation("op1", tiebreak=(1, "Ben"))
    second = make_operation("op2", tiebreak=(0, "Ada"))
    left = make_bundle(operations=(first, second))
    right = Bundle.from_dict({
        **make_bundle(operations=(second, first)).to_dict(),
        # The bundle sets are carried in a different order too.
        "reads": [CELL.to_dict(), ACTOR.to_dict()],
        "writes": [WITNESS.to_dict(), CELL.to_dict()],
    })
    assert left.to_dict() != right.to_dict()
    assert left.input_dict() == right.input_dict()
    assert left.canonical_dict() == right.canonical_dict()
    assert left.canonical_json() == right.canonical_json()
    assert [op.op_id for op in left.ordered_operations()] == ["op2", "op1"]


def test_bundle_rejects_duplicate_operation_ids():
    with pytest.raises(ValueError, match="duplicate operation id"):
        make_bundle(operations=(make_operation("same"), make_operation("same")))


@pytest.mark.parametrize("field,value,match", [
    ("run_id", "18", "run_id"),
    ("tick", 43, "tick"),
    ("shard", 4, "shard"),
])
def test_bundle_rejects_namespace_mismatch(field, value, match):
    arguments = {
        "bundle_id": "bundle-1",
        "namespace": NS,
        "run_id": NS.run_id,
        "tick": NS.tick,
        "shard": NS.shard,
        "base_version": 0,
        "operations": (make_operation(),),
        "reads": BUNDLE_READS,
        "writes": BUNDLE_WRITES,
        "tiebreak": (0, "Ada"),
    }
    arguments[field] = value
    with pytest.raises(ValueError, match=match):
        Bundle(**arguments)


def test_bundle_rejects_operation_outside_bundle_resource_sets():
    with pytest.raises(ValueError, match="reads outside"):
        make_bundle(operations=(make_operation(
            reads=(Resource("actor", "Ben"),)),))
    with pytest.raises(ValueError, match="writes outside"):
        make_bundle(operations=(make_operation(
            writes=(Resource("cell", (9, 9)),)),))


def test_bundle_rejects_bad_base_version_and_empty_id():
    with pytest.raises(ValueError):
        make_bundle(base_version=-1)
    with pytest.raises(ValueError):
        make_bundle(bundle_id="")


# --------------------------------------------------------------------------- result


def test_result_round_trip_and_json_safety():
    bundle = make_bundle()
    result = make_result(bundle)
    restored = BundleResult.from_dict(result.to_dict())
    assert restored == result
    assert restored.to_dict() == result.to_dict()
    assert restored.succeeded
    json.dumps(result.to_dict(), allow_nan=False)

    # NodeRef is an int subclass; it must become a plain int on the wire.
    leaking = make_result(bundle, effects=(
        {"node": NodeRef(7), "pair": (1, 2)},))
    data = leaking.to_dict()
    assert type(data["effects"][0]["node"]) is int
    assert data["effects"][0]["node"] == 7
    assert data["effects"][0]["pair"] == [1, 2]
    assert type(data["effects"][0]["pair"]) is list
    json.dumps(data, allow_nan=False)
    assert BundleResult.from_dict(data).to_dict() == data


def test_result_canonical_form_is_order_insensitive():
    bundle = make_bundle()
    first = make_result(bundle, effects=({"b": 2}, {"a": 1}),
                        created_ids=(QualifiedId(NS.name, 2),
                                     QualifiedId(NS.name, 1)),
                        result=(("Ben", True, None), ("Ada", True, None)))
    second = make_result(bundle, effects=({"a": 1}, {"b": 2}),
                         created_ids=(QualifiedId(NS.name, 1),
                                      QualifiedId(NS.name, 2)),
                         result=(("Ada", True, None), ("Ben", True, None)))
    assert first.to_dict() != second.to_dict()
    assert first.canonical_dict() == second.canonical_dict()


@pytest.mark.parametrize("overrides,match", [
    ({"status": "done"}, "status"),
    ({"created_ids": (QualifiedId("r99/t0/other/s0/b0/a1", 1),)},
     "namespace"),
    ({"output_sha": ""}, "output_sha"),
    ({"execution_sha": ""}, "execution_sha"),
    ({"result": (("Ada", "yes", None),)}, "applied"),
    ({"result": (("Ada", True),)}, "row"),
    ({"effects": ({"bad": {1, 2}},)}, "effects"),
])
def test_result_rejects_invalid_values(overrides, match):
    with pytest.raises((ValueError, BundleValueError), match=match):
        make_result(make_bundle(), **overrides)


# --------------------------------------------------------------------------- ack


def test_ack_round_trip():
    ack = BundleAck(
        bundle_id="bundle-1", base_version=3, outcome="committed",
        committed_version=4, execution_sha="execution-bundle-1",
        reason="merged")
    assert BundleAck.from_dict(ack.to_dict()) == ack
    assert BundleAck.from_dict(ack.to_dict()).to_dict() == ack.to_dict()
    json.dumps(ack.to_dict(), allow_nan=False)

    retry = BundleAck(bundle_id="bundle-1", base_version=3, outcome="retry",
                      committed_version=None, execution_sha="execution-bundle-1")
    assert BundleAck.from_dict(retry.to_dict()) == retry
    rejected = BundleAck(bundle_id="bundle-1", base_version=3,
                         outcome="rejected", committed_version=None,
                         execution_sha="execution-bundle-1", reason="stale")
    assert BundleAck.from_dict(rejected.to_dict()) == rejected


@pytest.mark.parametrize("kwargs", [
    {"outcome": "maybe", "committed_version": None},
    {"outcome": "committed", "committed_version": None},
    {"outcome": "committed", "committed_version": 2},
    {"outcome": "retry", "committed_version": 4},
    {"outcome": "rejected", "committed_version": 4},
    {"outcome": "retry", "committed_version": None, "execution_sha": ""},
])
def test_ack_rejects_invalid_values(kwargs):
    values = {
        "bundle_id": "bundle-1",
        "base_version": 3,
        "outcome": "committed",
        "committed_version": 4,
        "execution_sha": "execution-bundle-1",
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        BundleAck(**values)


# --------------------------------------------------------------------------- transport


def test_local_transport_dispatch_is_idempotent_and_replayable():
    bundle = make_bundle()
    calls: list[str] = []

    def executor(received: Bundle) -> BundleResult:
        calls.append(received.bundle_id)
        return make_result(received)

    transport = LocalBundleTransport(executor)
    first = transport.dispatch(bundle)
    second = transport.dispatch(bundle)

    assert calls == ["bundle-1"]
    assert second is first
    assert transport.replay("bundle-1") is first
    assert transport.replay("missing") is None
    assert transport.dispatch_order == ("bundle-1",)
    assert isinstance(transport, BundleTransport)


def test_local_transport_ack_must_match_cached_result():
    bundle = make_bundle()
    transport = LocalBundleTransport(lambda received: make_result(received))
    result = transport.dispatch(bundle)
    ack = BundleAck(
        bundle_id=bundle.bundle_id, base_version=bundle.base_version,
        outcome="committed", committed_version=bundle.base_version + 1,
        execution_sha=result.execution_sha)

    transport.acknowledge(ack)
    assert transport.acknowledgement(bundle.bundle_id) == ack
    # Repeating the identical confirmation is idempotent.
    transport.acknowledge(ack)

    audit = transport.to_dict()
    assert audit["dispatch_order"] == ["bundle-1"]
    assert list(audit["results"]) == ["bundle-1"]
    assert audit["acks"]["bundle-1"] == ack.to_dict()
    json.dumps(audit, allow_nan=False)


@pytest.mark.parametrize("ack_kwargs,match", [
    ({"bundle_id": "unknown"}, "unknown bundle"),
    ({"base_version": 99}, "base_version"),
    ({"execution_sha": "wrong"}, "execution_sha"),
])
def test_local_transport_rejects_unknown_or_mismatched_ack(ack_kwargs, match):
    bundle = make_bundle()
    transport = LocalBundleTransport(lambda received: make_result(received))
    result = transport.dispatch(bundle)
    values = {
        "bundle_id": bundle.bundle_id,
        "base_version": bundle.base_version,
        "outcome": "committed",
        "committed_version": bundle.base_version + 1,
        "execution_sha": result.execution_sha,
    }
    values.update(ack_kwargs)
    with pytest.raises(ValueError, match=match):
        transport.acknowledge(BundleAck(**values))


def test_local_transport_rejects_conflicting_duplicate_ack():
    bundle = make_bundle()
    transport = LocalBundleTransport(lambda received: make_result(received))
    result = transport.dispatch(bundle)
    first = BundleAck(
        bundle_id=bundle.bundle_id, base_version=bundle.base_version,
        outcome="committed", committed_version=4,
        execution_sha=result.execution_sha, reason="first")
    second = BundleAck(
        bundle_id=bundle.bundle_id, base_version=bundle.base_version,
        outcome="committed", committed_version=4,
        execution_sha=result.execution_sha, reason="second")
    transport.acknowledge(first)
    with pytest.raises(ValueError, match="conflicting ack"):
        transport.acknowledge(second)
    assert transport.acknowledgement(bundle.bundle_id) == first


def test_local_transport_concurrent_duplicate_dispatch_executes_once():
    bundle = make_bundle()
    calls: list[str] = []
    barrier = threading.Barrier(2)

    def executor(received: Bundle) -> BundleResult:
        calls.append(received.bundle_id)
        return make_result(received)

    transport = LocalBundleTransport(executor)
    results: list[BundleResult] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            barrier.wait(timeout=5)
            results.append(transport.dispatch(bundle))
        except BaseException as exc:  # pragma: no cover - failure diagnostic
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert len(results) == 2
    assert results[0] is results[1]
    assert calls == ["bundle-1"]


def test_local_transport_executor_failure_is_not_cached():
    bundle = make_bundle()
    calls = {"count": 0, "fail": True}

    def executor(received: Bundle) -> BundleResult:
        calls["count"] += 1
        if calls["fail"]:
            raise RuntimeError("worker unavailable")
        return make_result(received)

    transport = LocalBundleTransport(executor)
    with pytest.raises(RuntimeError, match="worker unavailable"):
        transport.dispatch(bundle)
    assert transport.replay(bundle.bundle_id) is None
    assert transport.dispatch_order == ()

    calls["fail"] = False
    result = transport.dispatch(bundle)
    assert result.bundle_id == bundle.bundle_id
    assert calls["count"] == 2
    assert transport.replay(bundle.bundle_id) is result


def test_local_transport_rejects_and_does_not_cache_mismatched_result():
    bundle = make_bundle()
    calls = {"count": 0, "bad": True}

    def executor(received: Bundle) -> BundleResult:
        calls["count"] += 1
        bundle_id = "other" if calls["bad"] else received.bundle_id
        return make_result(received, bundle_id=bundle_id)

    transport = LocalBundleTransport(executor)
    with pytest.raises(ValueError, match="bundle_id"):
        transport.dispatch(bundle)
    assert transport.replay(bundle.bundle_id) is None

    calls["bad"] = False
    result = transport.dispatch(bundle)
    assert calls["count"] == 2
    assert transport.replay(bundle.bundle_id) is result


def test_local_transport_preloaded_results_replay_without_executor():
    bundle = make_bundle()
    preloaded = make_result(bundle)
    calls: list[str] = []

    def executor(received: Bundle) -> BundleResult:
        calls.append(received.bundle_id)
        return make_result(received)

    transport = LocalBundleTransport(
        executor, results={bundle.bundle_id: preloaded})
    assert transport.dispatch(bundle) is preloaded
    assert transport.replay(bundle.bundle_id) is preloaded
    assert calls == []
    assert transport.dispatch_order == ()


def test_canonical_json_rejects_unsupported_container_types():
    with pytest.raises(BundleValueError):
        canonical_json({"bad": {1, 2}})
    with pytest.raises(BundleValueError):
        canonical_json({"bad": object()})
