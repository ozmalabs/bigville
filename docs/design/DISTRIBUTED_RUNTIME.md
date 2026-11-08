# Distributed runtime: revisions, durable logs, deltas and workers

Status: active plan, 8 November 2026. This program continues
`DISTRIBUTED_BUNDLES.md` from an in-process bundle protocol to a runtime seam
that can survive retries, crashes and a worker boundary.

It still does not require a network service. The transport is local process /
synthetic by default; the contract is the one a socket or remote worker would
use.

## Starting point

`NB01-NB05` delivered:

- `Bundle -> BundleResult -> BundleAck` with an idempotent
  `LocalBundleTransport`;
- bundle/execution/payload checksums and a `TickBundleLog`;
- per-node provenance and legacy-safe checkpoints;
- partitioned ticks dispatched and acknowledged as bundles;
- transport-neutral wire round trips and a verification tool.

The remaining gap is that bundles still execute against one live world, the
log is in memory, and there is no per-commit revision, effect delta or worker
process.

## Invariants

1. **The coordinator commits.** A worker never mutates the canonical world. It
   returns effects/deltas; the coordinator validates, orders and applies them.
2. **Versioned base.** Every bundle names the world/graph revision it read.
   A result whose base is stale is rejected/retried, never merged.
3. **Durable audit.** Dispatch, result and ack can be written to an append-only
   durable log and replayed to verify the same checksums.
4. **Idempotence.** A `bundle_id` is unique per run; retries reuse its
   namespace and produce the same result/effects.
5. **No silent default change.** Distribution remains opt-in; serial stays the
   default executor and world physics is unchanged.
6. **No NodeRef break.** Node ids stay ints; provenance is origin/qualified id.
7. **Transport-neutral.** The same protocol works in-process, across a local
   process, and later over a socket.

## Phases

Each phase is implemented by one agent, reviewed and committed by the
supervisor, with a report in `docs/phases/distributed-runtime/DRxx_REPORT.md`.

### DR01 — Graph revisions and stale-bundle validation

**Scope:** Give the canonical graph/world a monotonic revision, use it as the
bundle `base_version`, and validate committed results against it.

**Files:** `bigville/runtime.py`, `bigville/sharding.py`,
`bigville/game.py` if needed, `tests/test_graph_revisions.py` (new), report.

**Deliverables:**
- `BigvilleGraph.revision` increments on every mutation (`add_node`,
  `add_edge*`, `remove_*`, `set_attr`, type changes if any). It is deterministic
  and independent of timing.
- `BigvilleWorld.revision` exposes the graph revision.
- Checkpoint `to_checkpoint_dict`/`from_checkpoint_dict` carries the revision
  (with legacy migration to a documented default); restoring a graph preserves
  it. Origin metadata does not change the revision count.
- `PartitionedExecutor.plan_bundles` uses `world.revision` as `base_version`;
  `BundleAck.committed_version` is the revision after the bundle's effects are
  applied. `validate_result` rejects a result whose base does not match.
- `TickBundleLog` records dispatch/base/committed revisions and exposes them.
- Tests: monotonicity across each mutation type; restore parity; legacy
  checkpoint; stale result rejection; serial/partitioned equivalence; revision
  counts equal for identical serial/partitioned turns.
- No default behaviour change.

**Gate:** graph/persistence/tick-sharding/bundle tests.

### DR02 — Durable bundle/tick log

**Scope:** An append-only, replayable journal of bundle dispatch, result, ack,
commit order and tick checksums. In-memory remains the default.

**Files:** `bigville/bundle_log.py` (new), `bigville/sharding.py`,
`bigville/game.py`, `tests/test_bundle_log.py` (new), report.

**Deliverables:**
- `BundleJournal(path)` with append-only records:
  - `{"kind":"tick_start",...}`, `dispatch`, `result`, `ack`, `commit`,
    `tick_end` with `tick_execution_sha`/`tick_payload_sha`/revision;
  - JSONL, canonical JSON, fsync/atomic-enough append, file locking or a
    documented single-writer rule;
  - `read()`, `replay()` rebuilding a `TickBundleLog`; `verify()` checking
    bundle/result/ack coverage, checksums and commit order.
- Optional `bundle_log_path`/journal on `BigvilleGame` or the partitioned
  executor; default off. Serial/threaded turns write nothing.
- Corruption/truncation handling: a partial last line is reported or safely
  ignored with an explicit result; no silent acceptance.
- Tests: write/read/replay/verify; duplicate/unknown/missing records;
  truncated tail; checksum mismatch; idempotent re-append; no file for serial;
  path validation/temp dirs.
- Measure the overhead on a short partitioned run and record it.

**Gate:** targeted tests; partitioned semantic equivalence unchanged.

### DR03 — Graph deltas and effect results

**Scope:** Make a bundle result able to carry the mutations it would apply,
so a worker can execute off-world and the coordinator can merge/apply deltas.

**Files:** `bigville/runtime.py`, `bigville/bundles.py`,
`bigville/sharding.py`, `tests/test_graph_deltas.py` (new), report.

**Deliverables:**
- `BigvilleGraph` mutation recording context:
  - `with graph.record_changes() as delta:` records added/removed nodes,
    added/removed edges, and attr changes (old/new) in deterministic order;
  - `GraphDelta` JSON-safe `to_dict`/`from_dict`/`apply_to(graph)` with
    validation (node/edge existence, duplicate ops, attrs JSON-safe).
- `BundleResult.effects` is populated from the recorded delta in the
  reference bundle executor. The in-process path still mutates the world
  directly; the result effects are the replayable delta. Document whether the
  executor applies or returns them.
- `apply_delta` is idempotent/validating enough for a replay test: apply the
  delta to a cloned/restored graph and compare canonical state.
- Tests: record/apply round trip; all mutation types; attr old/new; remove
  node/edge; JSON round trip; applying to the wrong base version is rejected;
  the bundle result effects cover the actual changed state; serial/partitioned
  state unchanged.
- Keep `NodeRef` ints; delta node ids are local ints plus origin namespace if
  available.

**Gate:** runtime/checkpoint/bundle/partitioned tests.

### DR04 — Local process transport and worker lifecycle

**Scope:** Prove the bundle protocol survives a real process boundary and a
worker lifecycle. The live-world snapshot path may remain an explicit
extension point.

**Files:** `bigville/process_transport.py` (new),
`tests/test_process_transport.py` (new), report.

**Deliverables:**
- `ProcessBundleTransport` using `multiprocessing` (spawn/fork documented) or a
  subprocess JSON/pipe worker:
  - dispatch a `Bundle` (JSON/pickle-safe) to a worker;
  - worker executes a registered executor (module-level callable or a
    synthetic delta executor) and returns `BundleResult`;
  - timeout, retry policy, crash detection, restart, graceful shutdown; no
    hung process;
  - idempotence by `bundle_id`; duplicate dispatch does not execute twice;
  - results validated by the same `PartitionedExecutor.validate_result`.
- Provide a small `DeltaWorkerExecutor` for tests that applies a bundle's
  operations to a plain JSON state and returns a delta result; it must not
  import the live game.
- Document the live-world extension point: a future worker restores a
  versioned world snapshot, executes the bundle, and returns effects; snapshot
  shipping itself is not required in this phase.
- Tests: dispatch/result/ack across process, duplicate dispatch, timeout and
  retry, worker crash/restart, clean shutdown, no orphan process, JSON round
  trip, deterministic checksums.
- Keep tests bounded (<60s) and skip cleanly if multiprocessing/spawn is not
  available in the environment.

**Gate:** targeted tests; no default executor change.

### DR05 — Integration, overhead and final gate

**Scope:** Combine revisions, journal, deltas and the process transport where
the current architecture allows, measure overhead, run the verification matrix
and close the program.

**Files:** `tools/verify_bundle_equivalence.py` (extend for revision/journal),
`tests/test_distributed_runtime.py` (new),
`docs/phases/distributed-runtime/FINAL_REPORT.md`, README, plan status.

**Deliverables:**
- Verification: serial vs partitioned bundle payload equality, execution
  stability, revision monotonicity, journal replay equality, delta replay
  equality, process transport round trip on a synthetic bundle.
- Seed matrix: 305000, 305002, 305004, 305006 at 8-16 turns (menu and one lazy
  run) as time permits.
- Measure overhead with the journal off/on and delta recording off/on; record
  per-turn milliseconds and log sizes.
- Update README and docs with what is now possible, what is still local-only,
  and the exact full-suite status (do not claim a pass that did not complete).
- Final report lists remaining work for true remote distribution: network
  transport, auth, backpressure, snapshot shipping/restore, worker supervision
  across hosts, durable commit recovery, and the live-world worker executor.

**Gate:** targeted suites, self-test, and the full suite on an idle host; record
the exact timeout/load if it cannot finish.

## Status

| Phase | Status | Commit |
|---|---|---|
| DR01 | complete (uncommitted) | — |
| DR02 | blocked on DR01 | — |
| DR03 | blocked on DR02 | — |
| DR04 | blocked on DR03 | — |
| DR05 | blocked on DR04 | — |

## Integration gates

```bash
python3 -m pytest -q tests/test_graph_revisions.py tests/test_bundle_log.py \
  tests/test_graph_deltas.py tests/test_process_transport.py \
  tests/test_bundles.py tests/test_bundle_checks.py tests/test_bundle_dispatch.py \
  -p no:cacheprovider
python3 -m pytest -q tests/test_tick_sharding.py tests/test_tick_graph.py \
  tests/test_tick_graph_executor.py tests/test_engine_defaults.py \
  tests/test_lazy_*.py -p no:cacheprovider
python3 domains/bigville_entities.py
```

## Non-goals

- No network/socket/broker or authentication.
- No live-world remote restore (the extension point is documented; snapshot
  shipping is a later program).
- No change to the default serial executor or world physics.
- No Ocelot dependency.
