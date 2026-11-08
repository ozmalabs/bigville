"""Local process transport for the bundle protocol (DR04).

This module proves that the NB01/NB05 bundle protocol survives a real
``multiprocessing`` boundary.  It is deliberately **not** wired into
``create_game`` and is not the default executor: the in-process
``LocalBundleTransport`` remains the reference path.  A process worker here
executes a bundle from plain JSON data and returns a checksummed
``BundleResult``; it never imports the live game or a live world.

Transport shape
---------------

```text
Bundle.to_dict() -> JSON bytes -> Pipe -> worker executor
                                             |
BundleResult <- JSON bytes <- Pipe <---------+
```

The parent validates every result with the same identity checks as
``PartitionedExecutor.validate_result`` (bundle id, namespace, base version) and
only then puts it in the idempotence cache.  A stale or mismatched result is
rejected and never cached.

Lifecycle
---------

* ``workers`` child processes are started eagerly by the constructor and kept
  in a small pool.  ``start_method`` selects the ``multiprocessing`` context;
  ``None`` means the platform default (``fork`` on Linux, documented below).
  ``spawn`` works for the module-level built-in executors and for a
  ``module:function`` executor spec; a bare callable requires ``fork`` unless
  it is picklable/importable.
* A duplicate dispatch of an already completed ``bundle_id`` returns the
  parent's cached result and does not contact a worker.  A duplicate that
  arrives while the first is running waits for the leader.
* ``timeout`` is the per-attempt wait for an idle worker and for the worker's
  reply.  A late worker is terminated and replaced before
  ``BundleTimeoutError`` is raised.
* ``retries`` is the number of *additional* attempts after the first, for
  timeout and worker-crash failures only.  A retry sends the identical bundle
  (same id/namespace), so the built-in ``delta`` executor is deterministic
  across workers.  An executor exception is reported immediately as
  ``BundleExecutorError`` and is not retried.
* A worker that exits without a reply is detected from EOF/process death,
  terminated/joined, replaced, and the dispatch is retried per policy.
  ``close()`` (and the context manager) shuts every worker down and joins it.

Message bounds
--------------

Every message is JSON encoded before sending and checked against
``max_message_bytes``.  The same bound is applied on receive.  No live world
object is ever pickled or sent; only the bundle's wire dictionary crosses the
boundary.  A caller that needs a larger bundle must raise the bound explicitly.

Live-world extension point
--------------------------

DR03 defines the replayable ``GraphDelta`` effect format.  A future worker can:

1. receive a versioned world snapshot reference (or shipped snapshot) in the
   dispatch envelope;
2. restore a private world at ``bundle.base_version``;
3. execute the bundle against that private world;
4. return ``BundleResult.effects`` (the delta) and the authoritative end
   revision in the result envelope;
5. let the coordinator validate the base, order/merge the deltas and apply them
   to the canonical world.

Snapshot shipping and the live-world worker executor are explicitly out of
scope for DR04.  The worker process here is a protocol/serialisation proof, not
a world runner.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import multiprocessing
import os
import sys
import threading
import time
from dataclasses import dataclass, replace
from multiprocessing.connection import Connection
from typing import Any, Callable, Mapping

from .bundle_checks import bundle_execution_sha, bundle_output_sha
from .bundles import (
    Bundle,
    BundleAck,
    BundleResult,
    ExecutionNamespace,
    QualifiedId,
    canonical_json,
)


__all__ = [
    "BundleExecutorError",
    "BundleMessageError",
    "BundleTimeoutError",
    "BundleWorkerError",
    "ProcessBundleTransport",
    "ProcessTransportError",
    "ProcessTransportClosedError",
    "DeltaWorkerExecutor",
    "delta_executor",
    "echo_executor",
    "register_executor",
    "resolve_executor",
    "test_executor",
]


DEFAULT_MAX_MESSAGE_BYTES = 1_000_000
_READY_TIMEOUT = 5.0
_JOIN_TIMEOUT = 5.0
_POLL_SLICE = 0.05


# --------------------------------------------------------------------------- errors


class ProcessTransportError(RuntimeError):
    """Base class for local process transport failures."""


class BundleTimeoutError(ProcessTransportError):
    """A worker did not answer within the configured timeout.

    ``bundle_id``, ``timeout`` and ``attempt`` are exposed for a coordinator
    that wants to log or decide a policy; the worker that timed out has already
    been terminated and replaced before this is raised.
    """

    def __init__(self, bundle_id: str, timeout: float, attempt: int = 1,
                 detail: str = "") -> None:
        self.bundle_id = bundle_id
        self.timeout = timeout
        self.attempt = attempt
        message = (f"bundle {bundle_id!r} timed out after {timeout:g}s "
                   f"(attempt {attempt})")
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)


class BundleWorkerError(ProcessTransportError):
    """A worker died, closed its pipe or sent a malformed reply."""

    def __init__(self, bundle_id: str, detail: str,
                 attempt: int = 1) -> None:
        self.bundle_id = bundle_id
        self.attempt = attempt
        super().__init__(
            f"bundle {bundle_id!r} worker failure (attempt {attempt}): {detail}")


class BundleExecutorError(ProcessTransportError):
    """The worker's executor raised; the worker itself is still healthy.

    This is not retried automatically: a Python exception from the bundle
    callback is treated as a deterministic unit/executor failure, not an
    infrastructural timeout or crash.
    """

    def __init__(self, bundle_id: str, error_type: str, detail: str) -> None:
        self.bundle_id = bundle_id
        self.error_type = error_type
        super().__init__(
            f"bundle {bundle_id!r} executor raised {error_type}: {detail}")


class BundleMessageError(ProcessTransportError):
    """A dispatch or reply exceeded ``max_message_bytes``."""


class ProcessTransportClosedError(ProcessTransportError):
    """The transport was closed before this dispatch could complete."""


# --------------------------------------------------------------------------- executors


def _as_int(value: Any, default: int = 0) -> int:
    """A JSON-safe integer coercion for the synthetic executors."""
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return int(value)


def _as_text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _extra_params(bundle: Bundle) -> Mapping[str, Any]:
    """The first operation's parameters, used only by the ``test`` hook."""
    if not bundle.operations:
        return {}
    return dict(bundle.ordered_operations()[0].params)


def delta_executor(bundle: Bundle) -> BundleResult:
    """Apply a bundle's operations to a plain JSON state and checksum it.

    The state is built from this bundle alone, so execution is a pure function
    of the bundle: the same bundle dispatched to a new worker after a timeout
    or crash produces exactly the same result and checksums.  Supported
    operations are the DR03 effect operations (``add_node``, ``remove_node``,
    ``add_edge``, ``remove_edge`` and ``set_attr``); any other operation is
    recorded as a generic deterministic effect.

    Nothing here imports ``bigville.game`` or a live world.  The returned
    ``BundleResult`` carries the JSON effects plus a final ``state_sha`` effect
    that digests the synthetic state, which is what the tests compare across a
    retry.
    """
    nodes: dict[str, dict[str, Any]] = {}
    attrs: dict[str, dict[str, Any]] = {}
    edges: set[tuple[int, str, int]] = set()
    effects: list[dict[str, Any]] = []
    rows: list[tuple[Any, bool, Any]] = []
    created: list[QualifiedId] = []

    for operation in bundle.ordered_operations():
        params = dict(operation.params)
        if operation.kind == "add_node":
            node = _as_int(params.get("node", params.get("id", 0)))
            node_type = _as_text(params.get("type"), "Node")
            node_attrs = params.get("attrs", {})
            nodes[str(node)] = {"type": node_type, "attrs": node_attrs}
            effects.append({
                "op": "add_node",
                "node": node,
                "type": node_type,
                "attrs": node_attrs,
            })
            qualified = QualifiedId(bundle.namespace.name, node)
            if qualified not in created:
                created.append(qualified)
        elif operation.kind == "remove_node":
            node = _as_int(params.get("node", params.get("id", 0)))
            nodes.pop(str(node), None)
            attrs.pop(str(node), None)
            effects.append({"op": "remove_node", "node": node})
        elif operation.kind in ("add_edge", "remove_edge"):
            source = _as_int(params.get("source"))
            target = _as_int(params.get("target"))
            edge_kind = _as_text(params.get("edge"))
            if operation.kind == "add_edge":
                edges.add((source, edge_kind, target))
            else:
                edges.discard((source, edge_kind, target))
            effects.append({
                "op": operation.kind,
                "source": source,
                "kind": edge_kind,
                "target": target,
            })
        elif operation.kind == "set_attr":
            node = _as_int(params.get("node", params.get("id", 0)))
            key = _as_text(params.get("key"), "value")
            value = params.get("value")
            attrs.setdefault(str(node), {})[key] = value
            effects.append({
                "op": "set_attr",
                "node": node,
                "key": key,
                "value": value,
            })
        else:
            effects.append({
                "op": "execute",
                "op_id": operation.op_id,
                "kind": operation.kind,
                "actor": operation.actor,
                "params": params,
            })
        rows.append((operation.actor, True, None))

    state = {
        "nodes": nodes,
        "edges": [list(edge) for edge in sorted(edges)],
        "attrs": attrs,
    }
    state_sha = hashlib.sha256(
        canonical_json(state).encode("utf-8")).hexdigest()
    effects.append({"op": "state_sha", "sha256": state_sha})

    provisional = BundleResult(
        bundle_id=bundle.bundle_id,
        namespace=bundle.namespace,
        base_version=bundle.base_version,
        status="ok",
        effects=tuple(effects),
        created_ids=tuple(created),
        result=tuple(rows),
        output_sha="pending",
        execution_sha="pending",
    )
    provisional = replace(provisional,
                          output_sha=bundle_output_sha(provisional))
    return replace(provisional,
                   execution_sha=bundle_execution_sha(bundle, provisional))


class DeltaWorkerExecutor:
    """A picklable callable wrapper around :func:`delta_executor`.

    The transport accepts a bare callable as an executor spec (with ``fork``,
    or wherever the callable itself is importable).  This small class gives the
    synthetic executor a stable, module-level type name for that use.
    """

    def __call__(self, bundle: Bundle) -> BundleResult:
        return delta_executor(bundle)


def echo_executor(bundle: Bundle) -> BundleResult:
    """A minimal deterministic executor that echoes the bundle operations."""
    effects = []
    rows = []
    for operation in bundle.ordered_operations():
        effects.append({
            "op": "echo",
            "op_id": operation.op_id,
            "actor": operation.actor,
            "kind": operation.kind,
        })
        rows.append((operation.actor, True, None))
    provisional = BundleResult(
        bundle_id=bundle.bundle_id,
        namespace=bundle.namespace,
        base_version=bundle.base_version,
        status="ok",
        effects=tuple(effects),
        created_ids=(),
        result=tuple(rows),
        output_sha="pending",
        execution_sha="pending",
    )
    provisional = replace(provisional,
                          output_sha=bundle_output_sha(provisional))
    return replace(provisional,
                   execution_sha=bundle_execution_sha(bundle, provisional))


def _marker_was_created(marker: Any, *, atomic: bool) -> bool:
    """Claim a one-shot failure marker, returning True only for the first call.

    ``marker`` is a filesystem path supplied in a test bundle's parameters.
    Using the file itself (rather than worker memory) lets a *restarted* worker
    observe that the first, killed attempt already happened.  ``atomic`` uses
    ``open(..., "x")`` so concurrent callers cannot both win.
    """
    path = _as_text(marker)
    if not path:
        raise ValueError("test executor mode requires a 'marker' parameter")
    if atomic:
        try:
            with open(path, "x", encoding="utf-8"):
                pass
        except FileExistsError:
            return False
        return True
    if os.path.exists(path):
        return False
    with open(path, "w", encoding="utf-8"):
        pass
    return True


def test_executor(bundle: Bundle) -> BundleResult:
    """Test-only hook selected by the first operation's ``params``.

    ``mode`` is one of:

    ``delta`` (default)
        Run :func:`delta_executor`.
    ``sleep``
        Sleep ``seconds`` (default 5) then return the delta result.
    ``delay``
        Sleep ``seconds`` (default 0.05) then return the delta result.
    ``crash``
        Exit the worker process immediately with status 23.
    ``raise``
        Raise ``RuntimeError`` in the worker executor.
    ``sleep_once`` / ``crash_once``
        Use ``marker`` as a one-shot flag: the first worker sleeps/exits, a
        restarted worker returns the delta result.  This exercises a real
        timeout/crash retry without any in-parent attempt counter.
    ``stale`` / ``namespace_mismatch``
        Return a deliberately invalid result so the parent's validation is
        exercised.  A stale/mismatched result must never be cached.

    Every non-crashing mode ultimately returns the deterministic
    :func:`delta_executor` result, so tests can compare checksums exactly.
    """
    params = dict(_extra_params(bundle))
    mode = _as_text(params.get("mode"), "delta")
    seconds = params.get("seconds", 5)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        seconds = 5.0

    if mode == "delta":
        return delta_executor(bundle)
    if mode == "delay":
        time.sleep(float(params.get("seconds", 0.05)))
        return delta_executor(bundle)
    if mode == "sleep":
        time.sleep(float(seconds))
        return delta_executor(bundle)
    if mode == "crash":
        os._exit(23)
    if mode == "raise":
        raise RuntimeError("test executor raised on purpose")
    if mode == "sleep_once":
        if _marker_was_created(params.get("marker"), atomic=True):
            time.sleep(float(seconds))
        return delta_executor(bundle)
    if mode == "crash_once":
        if _marker_was_created(params.get("marker"), atomic=True):
            os._exit(24)
        return delta_executor(bundle)
    if mode == "stale":
        result = delta_executor(bundle)
        return replace(result, base_version=bundle.base_version + 1)
    if mode == "namespace_mismatch":
        result = delta_executor(bundle)
        other = ExecutionNamespace(
            run_id=bundle.namespace.run_id,
            executor=bundle.namespace.executor,
            shard=bundle.namespace.shard,
            tick=bundle.namespace.tick,
            bundle_seq=bundle.namespace.bundle_seq + 1,
        )
        return replace(result, namespace=other, created_ids=(),
                       output_sha="mismatch", execution_sha="mismatch")
    raise ValueError(f"unknown test executor mode: {mode!r}")


_EXECUTOR_REGISTRY: dict[str, Callable[[Bundle], BundleResult]] = {}
_BUILTIN_EXECUTORS: dict[str, Callable[[Bundle], BundleResult]] = {
    "delta": delta_executor,
    "echo": echo_executor,
    "test": test_executor,
}


def register_executor(name: str, executor: Callable[[Bundle], BundleResult], *,
                      overwrite: bool = False) -> None:
    """Register a named executor for :class:`ProcessBundleTransport`.

    The registry lives in this module.  With ``fork`` a child inherits it; with
    ``spawn`` a test must register again at import time in the child's import
    path or use the ``module:function`` spelling instead.  Built-in names win
    over a registry entry of the same name.
    """
    if not isinstance(name, str) or not name:
        raise ValueError("executor name must be a non-empty string")
    if not callable(executor):
        raise ValueError("executor must be callable")
    if name in _BUILTIN_EXECUTORS:
        raise ValueError(f"{name!r} is a built-in executor name")
    if name in _EXECUTOR_REGISTRY and not overwrite:
        raise ValueError(f"executor already registered: {name!r}")
    _EXECUTOR_REGISTRY[name] = executor


def resolve_executor(spec: Any) -> Callable[[Bundle], BundleResult]:
    """Resolve an executor spec to a callable.

    Supported forms are a callable, a built-in name (``delta``, ``echo``,
    ``test``), a registered name, or ``"package.module:function"``.  The
    import-path form is the one that works under ``spawn`` without a registry.
    """
    if callable(spec):
        return spec
    if not isinstance(spec, str) or not spec:
        raise TypeError(
            "executor must be a callable or a non-empty string spec")
    builtin = _BUILTIN_EXECUTORS.get(spec)
    if builtin is not None:
        return builtin
    registered = _EXECUTOR_REGISTRY.get(spec)
    if registered is not None:
        return registered
    if ":" in spec:
        module_name, _, attribute = spec.partition(":")
        if not module_name or not attribute:
            raise ValueError(f"invalid executor import path: {spec!r}")
        module = importlib.import_module(module_name)
        resolved = getattr(module, attribute, None)
        if not callable(resolved):
            raise ValueError(
                f"executor import path is not callable: {spec!r}")
        return resolved
    raise ValueError(
        f"unknown executor {spec!r}; use a built-in, a registered name or "
        "'module:function'")


# --------------------------------------------------------------------------- worker


def _worker_send(conn: Connection, message: Mapping[str, Any],
                 max_message_bytes: int) -> bool:
    """Send one JSON message; return False when the parent has gone away."""
    try:
        payload = json.dumps(
            message, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        payload = json.dumps({
            "kind": "protocol_error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(payload) > max_message_bytes:
        payload = json.dumps({
            "kind": "protocol_error",
            "error_type": "BundleMessageError",
            "error": f"worker reply exceeds {max_message_bytes} bytes",
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        conn.send_bytes(payload)
    except (BrokenPipeError, EOFError, OSError):
        return False
    return True


def _worker_main(conn: Connection, executor_spec: Any,
                 max_message_bytes: int) -> None:
    """The child process entry point (module level, picklable under spawn)."""
    modules_before = set(sys.modules)
    try:
        executor = resolve_executor(executor_spec)
    except BaseException as exc:  # noqa: BLE001 - report startup failure
        _worker_send(conn, {
            "kind": "ready",
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }, max_message_bytes)
        try:
            conn.close()
        finally:
            return

    imported = sorted(set(sys.modules) - modules_before)
    if not _worker_send(conn, {
        "kind": "ready",
        "ok": True,
        "pid": os.getpid(),
        "executor": (executor_spec if isinstance(executor_spec, str)
                     else getattr(executor_spec, "__qualname__", "<callable>")),
        "imported": imported,
    }, max_message_bytes):
        try:
            conn.close()
        finally:
            return

    cache: dict[str, BundleResult] = {}
    while True:
        try:
            payload = conn.recv_bytes(max_message_bytes)
        except EOFError:
            break
        except OSError:
            break
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            if not _worker_send(conn, {
                "kind": "protocol_error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }, max_message_bytes):
                break
            continue
        if not isinstance(message, dict):
            if not _worker_send(conn, {
                "kind": "protocol_error",
                "error_type": "ValueError",
                "error": "request must be a JSON object",
            }, max_message_bytes):
                break
            continue

        kind = message.get("kind")
        if kind == "shutdown":
            _worker_send(conn, {"kind": "bye", "pid": os.getpid()},
                         max_message_bytes)
            break
        if kind != "execute":
            if not _worker_send(conn, {
                "kind": "protocol_error",
                "request_id": message.get("request_id"),
                "error_type": "ValueError",
                "error": f"unknown request kind: {kind!r}",
            }, max_message_bytes):
                break
            continue

        request_id = message.get("request_id")
        try:
            bundle = Bundle.from_dict(message.get("bundle"))
        except (TypeError, ValueError) as exc:
            if not _worker_send(conn, {
                "kind": "error",
                "request_id": request_id,
                "bundle_id": None,
                "error_type": type(exc).__name__,
                "error": f"invalid bundle: {exc}",
            }, max_message_bytes):
                break
            continue

        cached = cache.get(bundle.bundle_id)
        if cached is not None:
            result = cached
        else:
            try:
                result = executor(bundle)
            except BaseException as exc:  # noqa: BLE001 - report, keep worker
                if not _worker_send(conn, {
                    "kind": "error",
                    "request_id": request_id,
                    "bundle_id": bundle.bundle_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }, max_message_bytes):
                    break
                continue
            if not isinstance(result, BundleResult):
                if not _worker_send(conn, {
                    "kind": "error",
                    "request_id": request_id,
                    "bundle_id": bundle.bundle_id,
                    "error_type": "ValueError",
                    "error": (f"executor returned "
                              f"{type(result).__name__}, not BundleResult"),
                }, max_message_bytes):
                    break
                continue
            cache[bundle.bundle_id] = result

        if not _worker_send(conn, {
            "kind": "result",
            "request_id": request_id,
            "bundle_id": bundle.bundle_id,
            "result": result.to_dict(),
        }, max_message_bytes):
            break

    try:
        conn.close()
    except OSError:
        pass


# --------------------------------------------------------------------------- transport


@dataclass
class _Worker:
    process: Any
    conn: Connection
    ready: dict[str, Any]
    busy: bool = False


class ProcessBundleTransport:
    """A local multi-process implementation of the bundle transport protocol.

    ``executor`` is a built-in name (``"delta"`` default), a registered name,
    a ``"module:function"`` import path, or a callable (``fork`` only unless it
    is importable).  Workers execute bundles from JSON data only.

    The transport is thread-safe: independent dispatches may use different
    workers concurrently, while a duplicate ``bundle_id`` waits for its leader
    and then returns the same cached result.  ``close()`` is not intended to
    race an in-flight dispatch; call it after the turn completes.
    """

    def __init__(self, executor: Any = "delta", workers: int = 1,
                 timeout: float = 5.0, retries: int = 0,
                 start_method: str | None = None, *,
                 max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
                 start_timeout: float = _READY_TIMEOUT,
                 join_timeout: float = _JOIN_TIMEOUT,
                 results: Mapping[str, BundleResult] | None = None) -> None:
        if not isinstance(workers, int) or isinstance(workers, bool) or workers < 1:
            raise ValueError("workers must be a positive integer")
        if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
                or timeout <= 0):
            raise ValueError("timeout must be a positive number")
        if (not isinstance(retries, int) or isinstance(retries, bool)
                or retries < 0):
            raise ValueError("retries must be a non-negative integer")
        if (not isinstance(max_message_bytes, int)
                or isinstance(max_message_bytes, bool)
                or max_message_bytes < 1):
            raise ValueError("max_message_bytes must be a positive integer")
        if (not isinstance(start_timeout, (int, float))
                or isinstance(start_timeout, bool) or start_timeout <= 0):
            raise ValueError("start_timeout must be a positive number")
        if (not isinstance(join_timeout, (int, float))
                or isinstance(join_timeout, bool) or join_timeout <= 0):
            raise ValueError("join_timeout must be a positive number")
        if not callable(executor) and not isinstance(executor, str):
            raise TypeError("executor must be callable or a string spec")

        self.executor = executor
        self.workers = workers
        self.timeout = float(timeout)
        self.retries = int(retries)
        self.start_method = start_method
        self.max_message_bytes = int(max_message_bytes)
        self.start_timeout = float(start_timeout)
        self.join_timeout = float(join_timeout)

        self._ctx = multiprocessing.get_context(start_method)
        self._condition = threading.Condition(threading.RLock())
        self._results: dict[str, BundleResult] = {}
        self._acks: dict[str, BundleAck] = {}
        self._dispatch_order: list[str] = []
        self._inflight: dict[str, tuple[threading.Event, int]] = {}
        self._closed = False
        self._request_seq = 0
        self._executions = 0
        self._worker_seq = 0

        for bundle_id, result in (results or {}).items():
            if not isinstance(bundle_id, str) or not bundle_id:
                raise ValueError("preloaded results need non-empty bundle ids")
            if not isinstance(result, BundleResult):
                raise ValueError("preloaded results must be BundleResult values")
            if result.bundle_id != bundle_id:
                raise ValueError(
                    "preloaded result key does not match result.bundle_id")
            self._results[bundle_id] = result

        self._workers: list[_Worker] = []
        try:
            for _ in range(self.workers):
                self._workers.append(self._spawn_worker())
        except BaseException:
            for worker in self._workers:
                self._terminate_worker(worker)
            self._workers.clear()
            raise

    # -- lifecycle -------------------------------------------------------

    def _spawn_worker(self) -> _Worker:
        parent_conn, child_conn = self._ctx.Pipe(duplex=True)
        self._worker_seq += 1
        process = self._ctx.Process(
            target=_worker_main,
            args=(child_conn, self.executor, self.max_message_bytes),
            name=f"bigville-bundle-{self._worker_seq}",
            daemon=True,
        )
        process.start()
        child_conn.close()
        try:
            ready = self._read_ready(process, parent_conn)
        except BaseException:
            self._terminate_process(process, parent_conn)
            raise
        if not ready.get("ok"):
            self._terminate_process(process, parent_conn)
            raise BundleWorkerError(
                "<worker-startup>",
                f"executor {self.executor!r} could not start: "
                f"{ready.get('error_type')}: {ready.get('error')}")
        return _Worker(process=process, conn=parent_conn, ready=ready)

    def _read_ready(self, process: Any, conn: Connection) -> dict[str, Any]:
        deadline = time.monotonic() + self.start_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BundleWorkerError(
                    "<worker-startup>",
                    f"worker did not become ready within "
                    f"{self.start_timeout:g}s")
            try:
                if conn.poll(min(remaining, _POLL_SLICE)):
                    payload = conn.recv_bytes(self.max_message_bytes)
                    message = json.loads(payload.decode("utf-8"))
                    if not isinstance(message, dict) or \
                            message.get("kind") != "ready":
                        raise BundleWorkerError(
                            "<worker-startup>",
                            "worker sent an invalid ready message")
                    return message
            except (EOFError, OSError) as exc:
                raise BundleWorkerError(
                    "<worker-startup>",
                    f"worker exited before ready: {type(exc).__name__}") from exc
            if not process.is_alive():
                raise BundleWorkerError(
                    "<worker-startup>",
                    f"worker exited before ready (exitcode "
                    f"{process.exitcode!r})")

    def _terminate_process(self, process: Any, conn: Connection) -> None:
        try:
            if process.is_alive():
                process.terminate()
        except (OSError, ValueError):
            pass
        try:
            process.join(self.join_timeout)
        except (OSError, ValueError):
            pass
        try:
            if process.is_alive():
                process.kill()
                process.join(self.join_timeout)
        except (OSError, ValueError, AttributeError):
            pass
        try:
            conn.close()
        except (OSError, ValueError):
            pass

    def _terminate_worker(self, worker: _Worker) -> None:
        worker.busy = False
        self._terminate_process(worker.process, worker.conn)

    def _shutdown_worker(self, worker: _Worker) -> None:
        """Ask a healthy worker to exit, then join/terminate it."""
        worker.busy = False
        if worker.process.is_alive():
            try:
                payload = json.dumps(
                    {"kind": "shutdown"}, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")
                worker.conn.send_bytes(payload)
            except (BrokenPipeError, EOFError, OSError, ValueError):
                pass
            try:
                worker.process.join(self.join_timeout)
            except (OSError, ValueError):
                pass
        if worker.process.is_alive():
            self._terminate_process(worker.process, worker.conn)
        else:
            try:
                worker.conn.close()
            except (OSError, ValueError):
                pass

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise ProcessTransportClosedError("process transport is closed")

    def close(self) -> None:
        """Terminate/join every worker.  Safe to call more than once."""
        with self._condition:
            if self._closed:
                return
            self._closed = True
            workers = list(self._workers)
            self._workers.clear()
            self._condition.notify_all()
        for worker in workers:
            self._shutdown_worker(worker)

    def __enter__(self) -> "ProcessBundleTransport":
        with self._condition:
            self._raise_if_closed()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    # -- worker pool -----------------------------------------------------

    def _replace_worker_locked(self, worker: _Worker) -> _Worker:
        """Terminate a dead/timed-out worker and start its replacement."""
        index = self._workers.index(worker)
        self._terminate_worker(worker)
        replacement = self._spawn_worker()
        self._workers[index] = replacement
        self._condition.notify_all()
        return replacement

    def _acquire_worker(self, bundle_id: str,
                        wait: float) -> _Worker:
        deadline = time.monotonic() + wait
        with self._condition:
            while True:
                self._raise_if_closed()
                for worker in self._workers:
                    if worker.busy:
                        continue
                    if not worker.process.is_alive():
                        worker = self._replace_worker_locked(worker)
                    worker.busy = True
                    return worker
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BundleTimeoutError(
                        bundle_id, self.timeout,
                        detail="no idle worker became available")
                self._condition.wait(remaining)

    def _release_worker(self, worker: _Worker) -> None:
        with self._condition:
            worker.busy = False
            self._condition.notify_all()

    def _discard_worker(self, worker: _Worker) -> None:
        with self._condition:
            if self._closed:
                if worker in self._workers:
                    self._workers.remove(worker)
                self._terminate_worker(worker)
                return
            if worker in self._workers:
                self._replace_worker_locked(worker)
            else:
                self._terminate_worker(worker)
            self._condition.notify_all()

    # -- protocol --------------------------------------------------------

    def dispatch(self, bundle: Bundle) -> BundleResult:
        """Execute ``bundle`` in a worker, at most once per ``bundle_id``."""
        if not isinstance(bundle, Bundle):
            raise TypeError("dispatch expects a Bundle")
        bundle_id = bundle.bundle_id
        with self._condition:
            self._raise_if_closed()
            cached = self._results.get(bundle_id)
            if cached is not None:
                self.validate_result(bundle, cached)
                return cached
            entry = self._inflight.get(bundle_id)
            leader = entry is None
            if leader:
                pending = threading.Event()
                self._inflight[bundle_id] = (
                    pending, threading.get_ident())
                self._dispatch_order.append(bundle_id)
            else:
                pending, owner = entry

        if not leader:
            if owner == threading.get_ident():
                raise RuntimeError(
                    "re-entrant dispatch of the same bundle id")
            pending.wait()
            with self._condition:
                cached = self._results.get(bundle_id)
            if cached is not None:
                self.validate_result(bundle, cached)
                return cached
            return self.dispatch(bundle)

        try:
            result = self._execute_with_retry(bundle)
            self.validate_result(bundle, result)
        except BaseException:
            with self._condition:
                self._inflight.pop(bundle_id, None)
                try:
                    self._dispatch_order.remove(bundle_id)
                except ValueError:
                    pass
                self._condition.notify_all()
            pending.set()
            raise

        with self._condition:
            self._results[bundle_id] = result
            self._inflight.pop(bundle_id, None)
            self._condition.notify_all()
        pending.set()
        return result

    def acknowledge(self, ack: BundleAck) -> None:
        if not isinstance(ack, BundleAck):
            raise TypeError("acknowledge expects a BundleAck")
        with self._condition:
            result = self._results.get(ack.bundle_id)
            if result is None:
                raise ValueError(
                    f"cannot acknowledge unknown bundle: {ack.bundle_id!r}")
            if ack.base_version != result.base_version:
                raise ValueError(
                    "ack base_version does not match the dispatched result")
            if ack.execution_sha != result.execution_sha:
                raise ValueError(
                    "ack execution_sha does not match the dispatched result")
            existing = self._acks.get(ack.bundle_id)
            if existing is not None and existing != ack:
                raise ValueError(
                    f"conflicting ack for bundle: {ack.bundle_id!r}")
            self._acks[ack.bundle_id] = ack

    def replay(self, bundle_id: str) -> BundleResult | None:
        with self._condition:
            return self._results.get(bundle_id)

    @staticmethod
    def validate_result(bundle: Bundle, result: BundleResult) -> None:
        """Apply the same identity/staleness rule as ``PartitionedExecutor``.

        Imported lazily so this module does not pull the sharding/game modules
        into a worker or a simple protocol consumer.
        """
        from .sharding import PartitionedExecutor
        PartitionedExecutor.validate_result(bundle, result)

    # -- execution -------------------------------------------------------

    def _execute_with_retry(self, bundle: Bundle) -> BundleResult:
        total = self.retries + 1
        for attempt in range(1, total + 1):
            try:
                return self._execute_once(bundle, attempt)
            except (BundleTimeoutError, BundleWorkerError) as exc:
                exc.attempt = attempt
                if attempt >= total:
                    raise
        raise AssertionError("retry loop exhausted without a result")

    def _execute_once(self, bundle: Bundle, attempt: int) -> BundleResult:
        self._preflight_bundle(bundle)
        worker = self._acquire_worker(bundle.bundle_id, self.timeout)
        discard = False
        try:
            with self._condition:
                self._raise_if_closed()
                self._request_seq += 1
                request_id = self._request_seq
                self._executions += 1
            try:
                result = self._send_request(
                    worker, bundle, request_id, attempt)
            except (BundleTimeoutError, BundleWorkerError):
                discard = True
                raise
            return result
        finally:
            if discard:
                self._discard_worker(worker)
            else:
                self._release_worker(worker)

    def _preflight_bundle(self, bundle: Bundle) -> None:
        """Reject an over-sized dispatch before a worker sees it."""
        try:
            payload = json.dumps(
                {"kind": "execute", "request_id": 0,
                 "bundle": bundle.to_dict()},
                sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise BundleMessageError(
                f"bundle {bundle.bundle_id!r} is not JSON encodable: {exc}"
            ) from exc
        if len(payload) > self.max_message_bytes:
            raise BundleMessageError(
                f"bundle {bundle.bundle_id!r} dispatch is "
                f"{len(payload)} bytes, limit is {self.max_message_bytes}")

    def _send_request(self, worker: _Worker, bundle: Bundle,
                      request_id: int, attempt: int) -> BundleResult:
        message = {
            "kind": "execute",
            "request_id": request_id,
            "bundle": bundle.to_dict(),
        }
        try:
            payload = json.dumps(
                message, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise BundleMessageError(
                f"bundle {bundle.bundle_id!r} is not JSON encodable: {exc}"
            ) from exc
        if len(payload) > self.max_message_bytes:
            raise BundleMessageError(
                f"bundle {bundle.bundle_id!r} dispatch is "
                f"{len(payload)} bytes, limit is {self.max_message_bytes}")
        if not worker.process.is_alive():
            raise BundleWorkerError(
                bundle.bundle_id, "worker was not alive before send", attempt)
        try:
            worker.conn.send_bytes(payload)
        except (BrokenPipeError, EOFError, OSError) as exc:
            raise BundleWorkerError(
                bundle.bundle_id, f"send failed: {type(exc).__name__}: {exc}",
                attempt) from exc

        response = self._wait_for_response(worker, bundle.bundle_id, attempt)
        return self._parse_response(bundle, response, request_id, attempt)

    def _wait_for_response(self, worker: _Worker, bundle_id: str,
                           attempt: int) -> bytes:
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BundleTimeoutError(bundle_id, self.timeout, attempt)
            try:
                ready = worker.conn.poll(min(remaining, _POLL_SLICE))
            except (EOFError, OSError) as exc:
                raise BundleWorkerError(
                    bundle_id,
                    f"poll failed: {type(exc).__name__}: {exc}",
                    attempt) from exc
            if ready:
                return self._recv_bytes(worker, bundle_id, attempt)
            if not worker.process.is_alive():
                # The reply may have landed just before the exit; drain once.
                try:
                    if worker.conn.poll(0):
                        return self._recv_bytes(worker, bundle_id, attempt)
                except (EOFError, OSError):
                    pass
                raise BundleWorkerError(
                    bundle_id,
                    f"worker process exited (exitcode "
                    f"{worker.process.exitcode!r}) without a reply",
                    attempt)

    def _recv_bytes(self, worker: _Worker, bundle_id: str,
                    attempt: int) -> bytes:
        try:
            return worker.conn.recv_bytes(self.max_message_bytes)
        except EOFError as exc:
            raise BundleWorkerError(
                bundle_id, "worker closed the pipe without a reply",
                attempt) from exc
        except OSError as exc:
            raise BundleWorkerError(
                bundle_id, f"receive failed: {type(exc).__name__}: {exc}",
                attempt) from exc

    def _parse_response(self, bundle: Bundle, payload: bytes,
                        request_id: int, attempt: int) -> BundleResult:
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise BundleWorkerError(
                bundle.bundle_id, f"worker reply is not JSON: {exc}",
                attempt) from exc
        if not isinstance(message, dict):
            raise BundleWorkerError(
                bundle.bundle_id, "worker reply is not a JSON object",
                attempt)
        if message.get("request_id") != request_id:
            raise BundleWorkerError(
                bundle.bundle_id,
                f"worker reply request_id {message.get('request_id')!r} "
                f"does not match {request_id}", attempt)
        kind = message.get("kind")
        if kind == "error":
            error_type = str(message.get("error_type", "Exception"))
            detail = str(message.get("error", ""))
            raise BundleExecutorError(bundle.bundle_id, error_type, detail)
        if kind != "result":
            raise BundleWorkerError(
                bundle.bundle_id,
                f"unexpected worker reply kind: {kind!r}", attempt)
        try:
            return BundleResult.from_dict(message.get("result"))
        except (KeyError, TypeError, ValueError) as exc:
            raise BundleWorkerError(
                bundle.bundle_id, f"invalid result payload: {exc}",
                attempt) from exc

    # -- inspection ------------------------------------------------------

    @property
    def dispatch_order(self) -> tuple[str, ...]:
        with self._condition:
            return tuple(self._dispatch_order)

    @property
    def executions(self) -> int:
        """How many requests were actually sent to a worker.

        A cached duplicate dispatch does not increment this, which is the
        observable proof of idempotence.
        """
        with self._condition:
            return self._executions

    @property
    def worker_processes(self) -> tuple[Any, ...]:
        with self._condition:
            return tuple(worker.process for worker in self._workers)

    @property
    def worker_pids(self) -> tuple[int, ...]:
        return tuple(process.pid for process in self.worker_processes)

    def worker_info(self) -> list[dict[str, Any]]:
        """Debug/inspection view of each worker (not part of the audit form)."""
        with self._condition:
            return [{
                "pid": worker.process.pid,
                "alive": worker.process.is_alive(),
                "busy": worker.busy,
                "executor": worker.ready.get("executor"),
                "imported": list(worker.ready.get("imported", ())),
            } for worker in self._workers]

    def acknowledgement(self, bundle_id: str) -> BundleAck | None:
        with self._condition:
            return self._acks.get(bundle_id)

    def to_dict(self) -> dict[str, Any]:
        """Deterministic audit form: dispatch order plus sorted maps."""
        with self._condition:
            return {
                "dispatch_order": list(self._dispatch_order),
                "results": {
                    bundle_id: self._results[bundle_id].to_dict()
                    for bundle_id in sorted(self._results)
                },
                "acks": {
                    bundle_id: self._acks[bundle_id].to_dict()
                    for bundle_id in sorted(self._acks)
                },
                "workers": self.workers,
                "timeout": self.timeout,
                "retries": self.retries,
            }
