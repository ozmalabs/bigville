# Distributed bundles: namespace, dispatch, confirmation and checksums

Status: active plan, 8 November 2026. This program makes the executor namespace
a first-class **bundle identity** and turns the tick graph into a dispatchable,
acknowledged unit of work. It is transport-neutral: the first implementation
runs in-process, but the protocol is the one a process/socket worker will use.

No Ocelot dependency and no network transport in this program.

## Why

The tick graph already separates a turn into operations, resource claims and
deterministic commit components. The partitioned executor commits those
components in-process. A distributed system needs more than “call a function”:

- a unit of work that can be sent to a worker;
- a stable identity for that unit, including retries;
- a base snapshot version so a worker cannot apply stale effects;
- an idempotent result;
- a confirmation that the coordinator committed it;
- a checksum per bundle, per tick and per run;
- provenance so a node/event/effect can be attributed to the bundle that made it.

The namespace is that identity. It is not only a node-ID prefix: it is the
bundle, the dispatch envelope, the idempotence key, the provenance tag and the
checksum scope.

## Invariants

1. **One authoritative commit.** Workers execute; the coordinator validates,
   orders and commits. A bundle result is invisible until acked.
2. **Deterministic bundle execution.** Given `(base_version, operations,
   namespace)`, a worker produces the same effects, created ids and result
   checksum. Retries reuse the namespace; a new namespace is a new branch.
3. **Idempotence.** A `bundle_id` is unique within a run. A duplicate dispatch
   returns the same result or the stored ack; it never applies twice.
4. **Base-version validation.** A result whose `base_version` is not the
   bundle's dispatch base is rejected/retried, never merged.
5. **Deterministic merge.** Bundle results are committed in the bundle plan's
   deterministic order, not in worker completion order.
6. **Two checksum scopes.** Execution checksums include namespace/executor;
   payload checksums strip allocation provenance and compare world facts.
7. **No NodeRef API break.** `NodeRef` stays an int locally. Qualified identity
   is `(namespace, local_seq)` in provenance, serialization and the wire format.
8. **Backward-compatible checkpoints.** Existing checkpoints load; new origin
   metadata is optional/migrated, not required for old graphs.
9. **No hidden default change.** Bundle dispatch is opt-in until its parity and
   performance are established.

## Protocol

### Namespace

```text
ExecutionNamespace(
    run_id, executor, shard, tick, bundle_seq, attempt=1,
)
qualified name = "<run_id>/t<tick>/<executor>/s<shard>/b<bundle_seq>/a<attempt>"
```

A retry reuses the same namespace and attempt identity for deterministic node
allocation; an explicitly new attempt may use `a2` and is treated as a branch,
not a retry.

### Bundle

```text
Bundle(
    bundle_id, namespace, run_id, tick, shard,
    base_version,
    operations: tuple[BundleOperation],
    reads: tuple[Resource],
    writes: tuple[Resource],
    tiebreak: tuple,
)
BundleOperation = (op_id, actor, kind, params, reads, writes, tiebreak)
```

The bundle is built from one conflict component (or a shard group of
non-conflicting components) in the tick graph. It carries only what the worker
needs; it does not contain a whole world checkpoint unless the transport
requires one.

### Result

```text
BundleResult(
    bundle_id, namespace, base_version,
    status: "ok" | "refused" | "retry" | "error",
    effects: tuple[Effect],
    created_ids: tuple[QualifiedId],
    result: tuple[(actor, applied, error)],
    output_sha,
    execution_sha,
    reason,
)
```

`effects` are deltas (`set_attr`, `add_node`, `add_edge`, `remove_*`) or, for
the first in-process implementation, the existing actor-result tuples when the
worker already mutated the shared world. The distributed form must use deltas.

### Ack

```text
BundleAck(
    bundle_id, base_version,
    outcome: "committed" | "retry" | "rejected",
    committed_version,
    execution_sha,
    reason,
)
```

### Transport

```python
class BundleTransport(Protocol):
    def dispatch(self, bundle: Bundle) -> BundleResult: ...
    def acknowledge(self, ack: BundleAck) -> None: ...
    def replay(self, bundle_id: str) -> BundleResult | None: ...
```

`LocalBundleTransport` runs the bundle in-process and is the reference
implementation. A future process/socket transport implements the same methods;
nothing in the game should depend on the transport class.

## Checksums

1. **`bundle_input_sha`**
   `H(base_version, sorted operations, reads, writes, namespace)`
2. **`bundle_output_sha`**
   `H(bundle_id, base_version, status, effects, created_ids, result, executor)`
3. **`bundle_execution_sha`**
   `H(bundle_input_sha, bundle_output_sha, namespace, attempt)`
4. **`tick_execution_sha`**
   `H(sorted (bundle_id, ack outcome, execution_sha), commit_order)`
5. **`tick_payload_sha`**
   canonical world state after applying the tick, with namespaces/allocation
   ids removed; this is the cross-executor equivalence hash.
6. **`run_execution_sha`**
   `H(tick_execution_sha for every tick)`

The tick log records dispatch, result, ack and both tick hashes. A full run
checksum identifies the executor path; the payload hash compares the world.

## Phases

Each phase is implemented by one agent, reviewed and committed by the
supervisor, with a report in `docs/phases/distributed-bundles/NBxx_REPORT.md`.

### NB01 — Bundle protocol and local transport

**Scope:** Add the pure protocol objects and an in-process transport. No game
behaviour change.

**Files:** `bigville/bundles.py` (new), `tests/test_bundles.py` (new), report.

**Deliverables:**
- `ExecutionNamespace`, `BundleOperation`, `Bundle`, `BundleResult`,
  `BundleAck`, `QualifiedId`, `BundleTransport`, `LocalBundleTransport`.
- Deterministic JSON `to_dict`/`from_dict` round trips; validation of ids,
  versions and namespaces.
- `LocalBundleTransport` dispatches to a caller-supplied executor function
  (the game will wire it in NB04); records a replay cache by `bundle_id`;
  duplicate dispatch returns the cached result; `replay` works; `acknowledge`
  validates the result belongs to the bundle.
- No game imports required except the `Resource` type if needed; keep the
  module dependency-light and import-safe.
- Tests: namespace grammar; bundle round trip; duplicate dispatch idempotence;
  result/ack mismatch rejection; replay; deterministic created ids.

**Gate:** targeted tests; no engine behaviour change.

### NB02 — Bundle and tick checksums

**Scope:** Add the checksum layer and a tick log independent of transport.

**Files:** `bigville/tick_trace.py` or new `bigville/bundle_checks.py`,
`tests/test_bundle_checks.py` (new), report.

**Deliverables:**
- Pure functions for `bundle_input_sha`, `bundle_output_sha`,
  `bundle_execution_sha`, `tick_execution_sha`, `tick_payload_sha`,
  `run_execution_sha`.
- Canonical serialization helpers (sorted keys, typed containers, stable
  resource/operation ordering) that do not depend on node ids.
- `TickBundleLog` with `dispatch`, `result`, `ack`, `committed_order` and
  `to_dict`; optional in-memory storage on the game (not checkpointed yet).
- Tests: identical bundles/namespaces produce identical hashes; different
  namespaces differ in execution hash but not in canonical payload; a missing
  ack changes the tick checksum; replay is stable.

**Gate:** targeted tests; no default behaviour change.

### NB03 — Per-node provenance and qualified ids

**Scope:** Stamp graph nodes with the bundle namespace that created them and
carry that through checkpoints. Keep `NodeRef` an int.

**Files:** `bigville/runtime.py`, `bigville/world_persistence.py`,
`bigville/schemas` if present, tests, report.

**Deliverables:**
- `BigvilleGraph` has a current execution namespace (explicit context or
  module/thread-local context manager) and a per-node `origin` mapping
  `NodeRef -> namespace` or `_Node.origin`.
- `add_node` stamps the current namespace; `node_origin(node)`,
  `qualified_id(node) -> (namespace, int)` and `nodes_by_origin(namespace)`.
- Checkpoint schema accepts existing `bigville/graph/1`; new saves include
  origins and are backward-loadable (old nodes default to a documented
  `"legacy"`/`"unqualified"` namespace). Restore validates origins if present.
- Serializer/deserializer round trip preserves origins; `graph_to_dict` (the
  lossy projection) may include origins but must not break its consumers.
- Tests: origin stamping under nested namespaces; restore parity; legacy
  checkpoint migration; thread-local namespace safety; NodeRef stays int.

**Gate:** targeted checkpoint/runtime tests; full graph/persistence suites.

### NB04 — Wire bundles into the partitioned executor

**Scope:** Make the partitioned executor build bundles, dispatch through
`LocalBundleTransport`, collect results, ack and commit in deterministic order.
Keep the default executor and the existing partitioned result unchanged.

**Files:** `bigville/sharding.py`, `bigville/game.py`, tests, report.

**Deliverables:**
- Build a bundle per conflict component/shard group using `BundleOperation`s
  from the tick graph and the bundle's read/write sets.
- `base_version` comes from a graph/world version; add a monotonic version if
  needed, or use the turn plus commit sequence with a documented contract.
- `PartitionedExecutor` uses the transport for dispatch; it stores a
  `TickBundleLog` on the game (`last_bundle_log` or equivalent) with
  dispatch/result/ack/commit order.
- Deterministic commit order; duplicate dispatch/retry paths; mismatch or
  stale base version is rejected, not merged.
- The semantic state of serial vs partitioned must still match over the same
  seeds/turns, including the earlier same-cell/witness cases.
- Tests: bundle count/ids, ack completeness, replay, failed/stale result,
  deterministic commit, and a regression run for seeds 305000-305006.

**Gate:** tick/sharding/executor tests plus the semantic equivalence matrix.

### NB05 — Transport seam, checksum comparison and final docs

**Scope:** Prove the protocol is transport-neutral, compare checksums, and
close the program.

**Files:** `bigville/bundles.py` or `bigville/sharding.py`,
`tools/verify_bundle_equivalence.py` (new), `README.md`,
`docs/phases/distributed-bundles/FINAL_REPORT.md`, report.

**Deliverables:**
- A transport-neutral worker interface test: a fake out-of-process transport
  (JSON round trip, no shared world) drives the same `Bundle`/`BundleResult`
  for a small synthetic executor, proving the protocol does not require the
  live world object.
- Extend or add a verification tool:
  - serial vs partitioned bundle runs;
  - `tick_payload_sha` equal across executors;
  - `tick_execution_sha`/run execution hash identifies executor and is stable
    for same-executor replay;
  - bundle ids/acks complete and no duplicate commits.
- Run the seed/turn matrix (including the partitioned-fix seeds) and record
  results.
- README/docs explain the protocol, the two checksum scopes, what is local
  only, and what remains for real distribution (transport, process lifecycle,
  durable log, snapshot shipping, backpressure).
- Update `docs/design/DISTRIBUTED_BUNDLES.md` status table.

**Gate:** targeted suites, self-test; full suite is the final idle-host gate.

## Status

| Phase | Status | Commit |
|---|---|---|
| NB01 | complete | `6581ab6` |
| NB02 | complete | `3e9d72d` |
| NB03 | complete | `7c9e3e8` |
| NB04 | complete | `6ea732b` |
| NB05 | uncommitted | — |

## Integration gates

```bash
python3 -m pytest -q tests/test_bundles.py tests/test_bundle_checks.py \
  tests/test_tick_sharding.py tests/test_tick_graph.py \
  tests/test_tick_graph_executor.py -p no:cacheprovider
python3 -m pytest -q tests/test_engine_*.py tests/test_lazy_*.py \
  -p no:cacheprovider
python3 domains/bigville_entities.py
```

## Non-goals

- No network, socket, process pool, message broker or authentication.
- No live snapshot shipping or remote restore.
- No change to world physics, action validation or the default serial path.
- No Ocelot dependency.
