"""DR04: the bundle protocol across a real local process boundary.

These tests build no ``BigvilleGame`` and no live world.  Every bundle is
created from plain protocol objects, dispatched to a ``ProcessBundleTransport``
worker, and compared with the deterministic synthetic executor.  The process
transport is a protocol proof; the in-process transport remains the default.
"""
from __future__ import annotations

import json
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

mp = pytest.importorskip("multiprocessing")

from bigville.bundles import (
    Bundle,
    BundleAck,
    BundleOperation,
    BundleResult,
    ExecutionNamespace,
)
from bigville.process_transport import (
    BundleExecutorError,
    BundleMessageError,
    BundleTimeoutError,
    BundleWorkerError,
    DeltaWorkerExecutor,
    ProcessBundleTransport,
    ProcessTransportClosedError,
    delta_executor,
)
from bigville.sharding import BundleResultError, PartitionedExecutor
from worlds.tick_graph import Resource


_START_METHOD = ("fork" if "fork" in mp.get_all_start_methods() else None)
ACTOR = Resource("actor", "Ada")
CELL = Resource("cell", (1, 1))


# --------------------------------------------------------------------------- helpers


def make_bundle(seq: int, *, mode: str | None = None, seconds: float | None = None,
                marker=None, big: str | None = None) -> Bundle:
    """A self-contained bundle whose first operation carries the test hook."""
    ns = ExecutionNamespace(
        run_id="dr04", executor="process", shard=0, tick=1, bundle_seq=seq)
    params = {"node": seq, "type": "Agent", "attrs": {"seq": seq}}
    if mode is not None:
        params["mode"] = mode
    if seconds is not None:
        params["seconds"] = seconds
    if marker is not None:
        params["marker"] = str(marker)
    operations = [
        BundleOperation(
            op_id=f"add-{seq}",
            actor="Ada",
            kind="add_node",
            params=params,
            reads=(),
            writes=(ACTOR,),
            tiebreak=(0, "Ada", f"add-{seq}"),
        ),
        BundleOperation(
            op_id=f"attr-{seq}",
            actor="Ada",
            kind="set_attr",
            params={"node": seq, "key": "mood", "value": seq},
            reads=(),
            writes=(ACTOR,),
            tiebreak=(1, "Ada", f"attr-{seq}"),
        ),
    ]
    if big is not None:
        operations.append(BundleOperation(
            op_id=f"big-{seq}",
            actor="Ada",
            kind="generic",
            params={"blob": big},
            reads=(),
            writes=(ACTOR,),
            tiebreak=(2, "Ada", f"big-{seq}"),
        ))
    return Bundle(
        bundle_id=ns.name,
        namespace=ns,
        run_id=ns.run_id,
        tick=ns.tick,
        shard=ns.shard,
        base_version=0,
        operations=tuple(operations),
        reads=(),
        writes=(ACTOR,),
        tiebreak=(0, "Ada"),
    )


def wire_round_trip(value):
    return json.loads(json.dumps(value.to_dict(), sort_keys=True,
                                 allow_nan=False))


def ack_for(bundle: Bundle, result: BundleResult) -> BundleAck:
    return BundleAck(
        bundle_id=bundle.bundle_id,
        base_version=bundle.base_version,
        outcome="committed",
        committed_version=bundle.base_version,
        execution_sha=result.execution_sha,
    )


@pytest.fixture
def make_transport():
    created: list[ProcessBundleTransport] = []

    def factory(**kwargs) -> ProcessBundleTransport:
        kwargs.setdefault("start_method", _START_METHOD)
        try:
            transport = ProcessBundleTransport(**kwargs)
        except (OSError, PermissionError, BundleWorkerError) as exc:
            pytest.skip(f"child processes are not available: {exc}")
        created.append(transport)
        return transport

    yield factory
    for transport in created:
        transport.close()


# --------------------------------------------------------------------------- protocol


def test_dispatch_result_ack_and_replay_across_a_real_process(make_transport):
    transport = make_transport()
    bundle = make_bundle(1)
    expected = delta_executor(bundle)

    result = transport.dispatch(bundle)

    assert result.status == "ok"
    assert result.bundle_id == bundle.bundle_id
    assert result.namespace == bundle.namespace
    assert result.base_version == bundle.base_version
    assert result.output_sha == expected.output_sha
    assert result.execution_sha == expected.execution_sha
    assert transport.replay(bundle.bundle_id) is result
    assert transport.dispatch_order == (bundle.bundle_id,)
    assert transport.executions == 1
    assert len(transport.worker_pids) == 1

    ack = ack_for(bundle, result)
    transport.acknowledge(ack)
    assert transport.acknowledgement(bundle.bundle_id) == ack

    # A duplicate dispatch, even from a fresh wire round trip, is a cache hit.
    duplicate = transport.dispatch(
        Bundle.from_dict(wire_round_trip(bundle)))
    assert duplicate is result
    assert transport.executions == 1
    assert transport.dispatch_order == (bundle.bundle_id,)

    audit = transport.to_dict()
    assert audit["dispatch_order"] == [bundle.bundle_id]
    assert json.loads(json.dumps(audit))["results"][bundle.bundle_id]["status"] == "ok"


def test_bundle_and_result_are_json_wire_safe(make_transport):
    transport = make_transport()
    bundle = make_bundle(2)
    result = transport.dispatch(bundle)

    wire_bundle = wire_round_trip(bundle)
    wire_result = wire_round_trip(result)
    restored_bundle = Bundle.from_dict(wire_bundle)
    restored_result = BundleResult.from_dict(wire_result)

    assert restored_bundle == bundle
    assert restored_result == result
    assert restored_bundle.canonical_json() == bundle.canonical_json()
    assert restored_result.execution_sha == result.execution_sha
    # The cache accepts the same bundle restored from the wire.
    assert transport.dispatch(restored_bundle) is result
    assert transport.executions == 1


def test_callable_executor_spec_is_accepted(make_transport):
    if _START_METHOD != "fork":
        pytest.skip("a bare callable executor spec requires fork")
    transport = make_transport(executor=DeltaWorkerExecutor())
    bundle = make_bundle(5)

    result = transport.dispatch(bundle)

    assert result.execution_sha == delta_executor(bundle).execution_sha


def test_concurrent_duplicate_dispatch_executes_once(make_transport):
    transport = make_transport(executor="test")
    bundle = make_bundle(3, mode="delay", seconds=0.1)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(
            lambda _index: transport.dispatch(bundle), range(6)))

    assert all(result is results[0] for result in results)
    assert transport.executions == 1
    assert transport.dispatch_order == (bundle.bundle_id,)


def test_multiple_workers_have_no_cross_talk(make_transport):
    transport = make_transport(executor="test", workers=2, timeout=10.0)
    bundles = [make_bundle(seq, mode="delay", seconds=0.05)
               for seq in range(10, 17)]

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(transport.dispatch, bundle)
                   for bundle in bundles]
        results = [future.result() for future in futures]

    assert len(transport.worker_pids) == 2
    assert transport.executions == len(bundles)
    by_id = {result.bundle_id: result for result in results}
    assert set(by_id) == {bundle.bundle_id for bundle in bundles}
    for bundle in bundles:
        result = by_id[bundle.bundle_id]
        assert result.namespace == bundle.namespace
        assert result.base_version == bundle.base_version
        assert result.execution_sha == delta_executor(bundle).execution_sha
        assert transport.replay(bundle.bundle_id) is result
    assert set(transport.dispatch_order) == set(by_id)


def test_acknowledge_rejects_unknown_stale_and_conflicting_acks(make_transport):
    transport = make_transport()
    bundle = make_bundle(4)
    result = transport.dispatch(bundle)
    ack = ack_for(bundle, result)

    with pytest.raises(ValueError, match="unknown bundle"):
        transport.acknowledge(replace(
            ack, bundle_id="not-dispatched"))
    with pytest.raises(ValueError, match="base_version"):
        transport.acknowledge(replace(
            ack, base_version=bundle.base_version + 1))
    with pytest.raises(ValueError, match="execution_sha"):
        transport.acknowledge(replace(ack, execution_sha="wrong"))

    transport.acknowledge(ack)
    with pytest.raises(ValueError, match="conflicting"):
        transport.acknowledge(replace(
            ack,
            outcome="retry",
            committed_version=None,
            reason="later",
        ))


# --------------------------------------------------------------------------- failure policy


def test_timeout_terminates_worker_and_a_failed_retry_raises(make_transport):
    transport = make_transport(executor="test", timeout=0.1, retries=1)
    bundle = make_bundle(20, mode="sleep", seconds=5)
    stale_pid = transport.worker_pids[0]

    with pytest.raises(BundleTimeoutError) as raised:
        transport.dispatch(bundle)

    assert bundle.bundle_id in str(raised.value)
    assert raised.value.timeout == 0.1
    assert raised.value.attempt == 2
    assert transport.executions == 2
    assert transport.replay(bundle.bundle_id) is None
    assert transport.dispatch_order == ()
    assert stale_pid not in transport.worker_pids
    assert all(process.is_alive()
               for process in transport.worker_processes)

    # The transport is still usable with a replacement worker.
    good = make_bundle(21)
    result = transport.dispatch(good)
    assert result.execution_sha == delta_executor(good).execution_sha


def test_retry_after_timeout_once_succeeds_deterministically(
        make_transport, tmp_path):
    marker = tmp_path / "timeout-once.marker"
    transport = make_transport(executor="test", timeout=0.1, retries=1)
    bundle = make_bundle(30, mode="sleep_once", seconds=5, marker=marker)

    result = transport.dispatch(bundle)

    assert marker.exists()
    assert transport.executions == 2
    assert result.status == "ok"
    assert result.execution_sha == delta_executor(bundle).execution_sha
    assert transport.replay(bundle.bundle_id) is result
    # The successful retry is cached under the original bundle id.
    assert transport.dispatch(bundle) is result
    assert transport.executions == 2


def test_worker_crash_is_detected_restarted_and_next_dispatch_succeeds(
        make_transport):
    transport = make_transport(executor="test", retries=0)
    crash = make_bundle(40, mode="crash")
    old_pid = transport.worker_pids[0]

    with pytest.raises(BundleWorkerError) as raised:
        transport.dispatch(crash)

    assert crash.bundle_id in str(raised.value)
    assert transport.replay(crash.bundle_id) is None
    assert transport.dispatch_order == ()
    new_pids = transport.worker_pids
    assert old_pid not in new_pids
    assert len(new_pids) == 1
    assert transport.worker_processes[0].is_alive()

    good = make_bundle(41)
    result = transport.dispatch(good)
    assert result.execution_sha == delta_executor(good).execution_sha


def test_retry_after_crash_once_succeeds_deterministically(
        make_transport, tmp_path):
    marker = tmp_path / "crash-once.marker"
    transport = make_transport(executor="test", retries=1)
    bundle = make_bundle(50, mode="crash_once", marker=marker)

    result = transport.dispatch(bundle)

    assert marker.exists()
    assert transport.executions == 2
    assert result.execution_sha == delta_executor(bundle).execution_sha
    assert transport.replay(bundle.bundle_id) is result


def test_executor_exception_is_reported_and_not_cached(make_transport):
    transport = make_transport(executor="test")
    bundle = make_bundle(60, mode="raise")
    pid = transport.worker_pids[0]

    with pytest.raises(BundleExecutorError, match="RuntimeError"):
        transport.dispatch(bundle)
    assert transport.replay(bundle.bundle_id) is None
    assert transport.dispatch_order == ()
    assert transport.worker_pids == (pid,)
    assert transport.worker_processes[0].is_alive()

    # The same id executes again (nothing cached), and a later bundle works.
    with pytest.raises(BundleExecutorError):
        transport.dispatch(bundle)
    assert transport.executions == 2

    good = make_bundle(61)
    result = transport.dispatch(good)
    assert result.execution_sha == delta_executor(good).execution_sha


@pytest.mark.parametrize("mode, message", [
    ("stale", "base_version"),
    ("namespace_mismatch", "namespace"),
])
def test_stale_or_mismatched_results_are_rejected_and_not_cached(
        make_transport, mode, message):
    transport = make_transport(executor="test")
    bundle = make_bundle(70, mode=mode)

    with pytest.raises(BundleResultError, match=message):
        transport.dispatch(bundle)

    assert transport.replay(bundle.bundle_id) is None
    assert transport.dispatch_order == ()
    assert transport.executions == 1

    good = make_bundle(71)
    result = transport.dispatch(good)
    assert result.execution_sha == delta_executor(good).execution_sha


def test_oversized_dispatch_is_rejected_before_contacting_a_worker(
        make_transport):
    transport = make_transport(max_message_bytes=2000)
    bundle = make_bundle(80, big="x" * 10_000)

    with pytest.raises(BundleMessageError, match="limit"):
        transport.dispatch(bundle)

    assert transport.executions == 0
    assert transport.replay(bundle.bundle_id) is None
    assert transport.dispatch_order == ()

    good = make_bundle(81)
    assert transport.dispatch(good).status == "ok"
    assert transport.executions == 1


# --------------------------------------------------------------------------- lifecycle


def test_close_joins_every_worker_and_is_idempotent(make_transport):
    transport = make_transport(workers=2)
    processes = transport.worker_processes
    assert len(processes) == 2
    assert all(process.is_alive() for process in processes)

    transport.close()

    assert transport.worker_pids == ()
    assert all(not process.is_alive() for process in processes)
    transport.close()  # idempotent

    with pytest.raises(ProcessTransportClosedError):
        transport.dispatch(make_bundle(90))


def test_context_manager_closes_workers(make_transport):
    transport = make_transport()
    with transport as entered:
        assert entered is transport
        process = transport.worker_processes[0]
        assert transport.dispatch(make_bundle(91)).status == "ok"
        assert process.is_alive()

    assert not process.is_alive()
    assert transport.worker_pids == ()


def test_worker_imports_no_live_game_or_world(make_transport):
    transport = make_transport()
    info = transport.worker_info()

    assert len(info) == 1
    assert info[0]["alive"] is True
    assert info[0]["pid"] == transport.worker_pids[0]
    forbidden_prefixes = (
        "bigville.game",
        "bigville.api",
        "worlds.bigville_world",
    )
    assert not [name for name in info[0]["imported"]
                if name.startswith(forbidden_prefixes)]


# --------------------------------------------------------------------------- seam


def test_partitioned_executor_transport_seam_accepts_the_process_transport(
        make_transport):
    transport = make_transport()
    executor = PartitionedExecutor(transport=transport)
    bundle = make_bundle(100)

    results = executor.dispatch_bundles([bundle], transport)

    assert len(results) == 1
    result = results[0]
    assert result.bundle_id == bundle.bundle_id
    assert result.execution_sha == delta_executor(bundle).execution_sha

    ack = PartitionedExecutor.ack_for(
        bundle, result, committed_version=bundle.base_version)
    transport.acknowledge(ack)
    assert transport.acknowledgement(bundle.bundle_id) == ack
