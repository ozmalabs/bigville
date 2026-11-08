# DR04 — Local process transport and worker lifecycle

Status: complete (uncommitted), 8 November 2026. Phase DR04 of
[`docs/design/DISTRIBUTED_RUNTIME.md`](../../design/DISTRIBUTED_RUNTIME.md).

- Base commit: `bf267a8` on branch `distributed-runtime` (DR03).
- New files: `bigville/process_transport.py`,
  `tests/test_process_transport.py`, this report.
- Changed files: `docs/design/DISTRIBUTED_RUNTIME.md` (DR04 status row only).
- `bigville/sharding.py` needed no change. The existing
  `PartitionedExecutor(transport=...)` seam already accepts any object with
  `dispatch`/`acknowledge`; one test demonstrates that compatibility with the
  synthetic protocol executor. The process transport is **not** the default and
  is not wired into `create_game` or the partitioned turn path.
- No game/world physics, checkpoint shape, serial default executor or bundle
  protocol object changed.

## Process protocol

`ProcessBundleTransport` starts `workers` child processes eagerly in its
constructor and keeps a pool under one condition variable. Each worker is a
module-level `_worker_main(conn, executor_spec, max_message_bytes)` target; the
same function is picklable under `spawn`.

```text
parent                                      worker
------                                      ------
Bundle.to_dict()
  -> json.dumps(message) -> size check
  -> Pipe.send_bytes  ---------------------> recv_bytes
                                              Bundle.from_dict
                                              executor(bundle)
                                              BundleResult
  <- Pipe.recv_bytes  <---------------------  result.to_dict()
BundleResult.from_dict
PartitionedExecutor.validate_result
  -> cache keyed by bundle_id
```

Messages are JSON objects, never pickled live objects:

| direction | kind | payload |
|---|---|---|
| parent → worker | `execute` | `request_id`, `bundle` wire dict |
| parent → worker | `shutdown` | — |
| worker → parent | `ready` | pid, executor name, modules imported during startup |
| worker → parent | `result` | `request_id`, `bundle_id`, `BundleResult` wire dict |
| worker → parent | `error` | `request_id`, exception type/message |
| worker → parent | `protocol_error` | malformed request/reply diagnostics |

`max_message_bytes` (default 1,000,000) is checked on the parent's send, on the
worker's receive, on the worker's reply and on the parent's receive. An
over-sized bundle is rejected before a worker is contacted
(`BundleMessageError`), and does not increment `executions` or the cache.

### Start method

`start_method=None` uses the platform `multiprocessing` default, which is
`fork` on this Linux host. `start_method="spawn"` is supported for:

- the built-in executor names (`delta`, `echo`, `test`);
- a `"package.module:function"` executor spec (the child imports it);
- a registered executor only if the child's import path registers it again.

A bare callable spec requires `fork` (or must itself be importable) because
`spawn` pickles the process arguments. The tests force `fork` when available to
avoid re-entering pytest's `__main__` under spawn; the worker function itself is
module level and spawn-safe.

## Executors

- `delta` (default): a pure synthetic executor. It applies `add_node`,
  `remove_node`, `add_edge`, `remove_edge` and `set_attr` operations to a plain
  JSON state (nodes, edges, attrs), records one result row per operation and
  appends a deterministic `state_sha` effect. It imports only
  `bigville.bundles`/`bigville.bundle_checks`/stdlib; it does not import
  `bigville.game` or `worlds.bigville_world`. State is rebuilt from the bundle
  alone, so a retry in a new worker is deterministic. `DeltaWorkerExecutor` is
  a picklable callable wrapper for callers that prefer an executor object.
- `echo`: a minimal deterministic executor for wire tests.
- `test`: a test-only hook selected by the first operation's `params`: `delta`,
  `delay`, `sleep`, `crash`, `raise`, `sleep_once`, `crash_once`, `stale`,
  `namespace_mismatch`. The one-shot modes use a caller-supplied marker path so
  a *restarted* worker can observe that the killed attempt already happened;
  this exercises real timeout/crash retries without any in-parent attempt
  counter.
- `register_executor(name, callable)` adds a named executor; a
  `"module:function"` string is the documented import-path form. Built-in names
  win over registry entries.

## Lifecycle, timeout, retry and crash handling

- **Idempotence.** The parent cache is authoritative: a completed `bundle_id`
  returns the exact cached `BundleResult` without contacting a worker. A
  duplicate that arrives while the leader is running waits on a per-id event and
  returns the leader's result. The worker also has a process-local cache. In the
  tests, `transport.executions` stays at 1 for a duplicate (including six
  concurrent duplicates) and the result object is identical.
- **Validation.** Before caching, every result goes through
  `PartitionedExecutor.validate_result` (lazy import): bundle id, namespace and
  exact base version. A stale or namespace-mismatched result raises
  `BundleResultError`, is not cached, and is removed from `dispatch_order`.
- **Timeout.** `timeout` bounds both the wait for an idle worker and the wait
  for that worker's reply. On expiry the worker is terminated, joined and
  replaced, then `BundleTimeoutError` is raised with the bundle id, timeout and
  attempt. A retry sends the identical bundle (same id/namespace).
- **Retry.** `retries` is the number of *additional* attempts after the first
  and applies only to `BundleTimeoutError` and `BundleWorkerError`. If all
  attempts fail the last error is raised. An executor exception is a
  `BundleExecutorError` and is not retried; the worker is healthy and stays in
  the pool.
- **Crash.** A worker that calls `os._exit`, dies from a signal or closes the
  pipe is detected through EOF/`is_alive`/exit code. It is terminated, joined,
  replaced in the pool and the dispatch follows the retry policy. A later
  dispatch on the same transport uses the replacement worker.
- **Shutdown.** `close()` is idempotent: it marks the transport closed, notifies
  waiters, sends `shutdown` to live workers, joins each with `join_timeout`,
  force-terminates/joins any straggler and closes the pipes. The context manager
  calls it. Workers are daemon processes as a final orphan guard. A dispatch
  after `close()` raises `ProcessTransportClosedError`.
- **Threading.** Independent dispatches may use different workers concurrently;
  a worker is `busy` until its reply is consumed. No worker handles two
  requests at once. `close()` is documented as not racing an in-flight turn.

## Tests

New `tests/test_process_transport.py` (18 tests) covers:

- dispatch/result/ack/replay across a real process, deterministic
  output/execution checksums, audit `to_dict` and duplicate dispatch from a
  fresh JSON round trip;
- bundle and result JSON wire round trips and checksum stability;
- a bare callable executor spec (`DeltaWorkerExecutor`) under `fork`;
- six concurrent dispatches of one bundle id executing once;
- two workers, seven concurrent bundles, per-bundle-id results with no
  cross-talk;
- ack validation (unknown, stale base, wrong checksum, conflicting ack);
- timeout with `retries=1`: two attempts, worker replaced, clear error, no
  cache, transport still usable;
- a one-shot sleep timeout whose retry succeeds deterministically under the
  original bundle id/namespace;
- a hard worker crash (`os._exit`) detected and restarted, then a subsequent
  dispatch succeeds;
- a one-shot crash whose retry succeeds deterministically;
- executor exception reported, not cached, worker survives and the same id
  executes again;
- stale and namespace-mismatched results rejected and not cached;
- over-sized dispatch rejected before any worker contact;
- `close()` joins two workers, is idempotent, and blocks later dispatch;
- context manager shutdown;
- worker startup imported no `bigville.game`, `bigville.api` or
  `worlds.bigville_world`;
- `PartitionedExecutor(transport=...)` accepting the transport and
  dispatching/acking a synthetic protocol bundle.

Commands on this worktree:

```text
python3 -m pytest -q tests/test_process_transport.py \
  tests/test_bundles.py tests/test_bundle_checks.py \
  tests/test_bundle_dispatch.py -p no:cacheprovider
127 passed in 22.94s

python3 -m pytest -q tests/test_graph_deltas.py \
  tests/test_graph_revisions.py tests/test_tick_sharding.py \
  -p no:cacheprovider
44 passed in 29.08s

python3 -m pytest -q tests/test_process_transport.py -p no:cacheprovider
18 passed in 0.92s

python3 domains/bigville_entities.py
exit 0, ERRORS (0), WARNINGS (0)
```

No full-suite run was made; only the targeted gates above. A separate
standalone script (not part of pytest) also dispatched the same synthetic
bundle with `start_method="spawn"` and matched the expected checksum, proving
the module-level worker is spawn-safe outside pytest's `__main__` handling.

## Limitations

- **No live world in a worker.** The `delta` executor is synthetic. A worker
  cannot yet read or mutate a `BigvilleWorld`; the extension point below is not
  implemented.
- **No snapshot shipping.** A versioned snapshot envelope, restore, delta
  application and end-revision metadata are DR05/later work. DR03's effects are
  accepted as opaque JSON mappings; the worker does not decode `$type` attrs.
- **No network.** This is a local `multiprocessing` pipe, not a socket, broker,
  authentication layer or cross-host supervisor. A remote transport would need
  framing/backpressure beyond the single-message size bound.
- **No durable transport state.** The parent cache is in memory. A transport
  restart loses cached results/acks; replay comes from the DR02 journal, not
  from this module.
- **Timeout covers the reply, not a write blocked in the OS pipe.** A dispatch
  is bounded before send; an unexpectedly full pipe could still block inside
  `send_bytes`. Messages are small in the tested path.
- **Worker cache is unbounded.** One result per distinct `bundle_id` lives in
  each worker for its lifetime. Long runs need eviction or a per-turn worker.
- **No retry backoff/jitter.** A retry is immediate; the policy is deliberately
  minimal and deterministic for tests.
- **`close()` is not safe concurrently with an in-flight dispatch.** It is
  intended for the end of a turn.
- **Executor exceptions are not retried.** That is a policy choice: a bundle
  callback error is treated as a unit/executor failure, not infrastructure.
- **Fork is the tested start method.** Spawn support is implemented and
  documented but not exercised by the pytest suite (pytest's `__main__`
  re-entry makes an in-suite spawn test fragile).

## Live-world extension point

A future worker executor, selected by name or import path, would:

1. receive a dispatch envelope containing a versioned snapshot handle (or the
   snapshot bytes) in addition to `bundle.to_dict()`;
2. restore a private world/graph at `bundle.base_version`;
3. execute the bundle's operations against that private graph;
4. return `BundleResult.effects` in the DR03 delta format plus an authoritative
   end revision alongside the result;
5. let the coordinator validate the base, reject stale deltas, order/merge the
   effects and acknowledge the commit.

Snapshot shipping, delta merge ordering and the live-world executor are the
DR05+ boundary. The process plumbing (worker lifecycle, JSON envelope, cache,
validation, retries) is already shaped for that payload.

## Handoff to DR05

- Integrate the process transport into the equivalence/verification tool for a
  synthetic bundle round trip (it is intentionally not the default executor).
- Extend the journal/replay checks to the process result/ack traffic.
- Measure process start/dispatch/retry overhead and record it.
- Carry an end-revision field (or a dedicated result envelope) with a
  worker-returned delta so revision replay, not just graph-state replay, can be
  proven.
- Decide whether a process worker should own a versioned snapshot and whether
  `retries`/`timeout` defaults belong on `PartitionedExecutor` or a supervisor.
- Keep the final report honest about the remaining remote-distribution gaps:
  network transport, auth, backpressure, snapshot shipping/restore, cross-host
  worker supervision, durable commit recovery and the live-world executor.
