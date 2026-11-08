# NB02 — Bundle, tick and run checksums

Status: complete, 8 November 2026. Phase NB02 of
[`docs/design/DISTRIBUTED_BUNDLES.md`](../../design/DISTRIBUTED_BUNDLES.md).

- Base commit: `6581ab6781d5da28b55463c637d88bbea95fce04`
  (branch `distributed-bundles`, the NB01 commit before NB02 changes).
- Scope: a pure checksum layer and an in-memory tick audit log. No game,
  executor, checkpoint, default-path or world behaviour changed.
- Files added: `bigville/bundle_checks.py`, `tests/test_bundle_checks.py`.

## Design

`bigville/bundle_checks.py` imports only `bigville.bundles` (and lazily
`bigville.tick_trace` for the payload projection). It does not import
`bigville.game` or `worlds.bigville_world` at module import time. All
serialization uses `canonical_value`/`canonical_json` from `bigville.bundles`;
there is no second JSON encoder.

### Hash definitions

All hashes are lowercase SHA-256 over compact canonical JSON with sorted keys.

1. **`bundle_input_sha(bundle)`**
   `H(bundle.input_dict())`: namespace (run, executor, shard, tick,
   bundle_seq, attempt), base version, operations ordered by
   `BundleOperation.sort_key()` (tiebreak, actor, op id), sorted reads and
   sorted writes. Operation read/write sets are sorted too. `bundle_id` is
   deliberately absent, matching the NB01/design formula: the same work under
   the same namespace is the same input even if the coordinator labels the
   bundle differently.

2. **`bundle_output_sha(result)`**
   `H(bundle_id, namespace, base_version, status, effects, created_ids, result,
   reason)`. Effects, created ids and actor-result rows are canonicalised and
   sorted, so construction/completion order inside a result does not matter.
   `reason` is included because it is deterministic result content.

3. **`bundle_execution_sha(bundle, result)`**
   `H(input_sha, output_sha, namespace, attempt)`. The namespace already
   contains the executor name, so there is no separate executor field. The
   function rejects a result whose `bundle_id`, namespace or `base_version`
   does not match the bundle rather than hashing a misleading path.

4. **`tick_execution_sha(log)`**
   `H(sorted entries, committed_order)`, where each dispatched bundle
   contributes `(bundle_id, ack outcome, ack execution_sha)`. An
   unacknowledged bundle contributes `outcome=None` and `execution_sha=None`,
   so a missing ack changes the digest explicitly. The ack entries are sorted
   by bundle id, so result/ack arrival order is irrelevant. `committed_order`
   is a separate ordered list and is order-sensitive.

5. **`tick_payload_sha(state)`**
   A world-like object (any object with a callable `export_state`) is passed
   through `bigville.tick_trace.semantic_world_state`, then canonicalised and
   hashed. A mapping is treated as an already-normalised semantic payload and
   canonicalised as-is. The function never invents or mutates a world payload.

6. **`run_execution_sha(tick_hashes)`**
   `H([tick_execution_sha, ...])` in run order. A bare string is rejected so
   characters cannot be hashed as ticks; an empty run has a stable empty-list
   digest.

### Execution vs payload scope

| Included in execution hashes | Included in payload hash |
|---|---|
| run id, executor, shard, tick | world export facts after the tick |
| bundle seq and attempt | semantic log content |
| base version | turn/counter facts |
| operation params, read/write sets, tiebreaks | observer-visible entries |
| result status, effects, created ids, rows, reason | |
| ack outcome/execution hash and commit order | |

Excluded from execution output hashing: `BundleResult.output_sha` and
`BundleResult.execution_sha`. `execution_sha` would be a self-reference and
`output_sha` is exactly what the function returns, so hashing either would let
a stale checksum field change its own digest.

Excluded from the payload hash by `semantic_world_state`: utterance node ids,
allocation-order `id` fields on event/article/edition/handover/proposal/case
entries, and the insertion order of the log-like export lists. The payload
projection deliberately does not include execution namespace, bundle id,
attempt or commit order.

## `TickBundleLog`

`TickBundleLog(run_id, tick)` stores:

- `dispatched: dict[bundle_id, Bundle]`
- `results: dict[bundle_id, BundleResult]`
- `acks: dict[bundle_id, BundleAck]`
- `committed_order: tuple[bundle_id, ...]`
- an optional stored payload hash

Methods are `dispatch`, `result`, `acknowledge`, `commit`, `to_dict`,
`execution_sha` (property) and `payload_sha` (getter, or setter when given a
mapping/world). `set_payload` is an explicit setter alias.

Validation rules:

- a dispatch must belong to the log's `run_id` and `tick`;
- dispatching the same `bundle_id` twice is idempotent only for an identical
  bundle; a conflicting bundle is rejected;
- a result must name a dispatched bundle and match its namespace and base
  version; repeating an identical result is idempotent, a conflicting result
  is rejected;
- an ack must name a dispatched bundle and match its base version; if the
  result is already present, its `execution_sha` must match too; identical
  repeat acks are idempotent and conflicting acks are rejected;
- an ack for an undispatched bundle is rejected, so a tick cannot accumulate
  “extra” acks;
- a commit must name a dispatched bundle and may appear once, so duplicate
  commits are rejected;
- a recorded payload hash cannot be silently replaced by a different one.

The log is in-memory only, is not checkpointed, and has no durability or
process-transport semantics. `to_dict()` emits sorted bundle/result/ack maps,
the real commit order, both hashes and the stored payload hash; it contains no
live protocol objects and survives `json.dumps`.

## Tests

`tests/test_bundle_checks.py` has 24 tests covering:

- identical bundles/namespaces producing identical input, output and execution
  hashes;
- operation and resource construction order not changing the input hash;
- base version, namespace/executor and attempt changing the appropriate hash;
- output hash ignoring the two self-referential checksum fields, sorting
  effects, and reacting to status/effect/reason changes;
- mismatched result rejection for bundle id, namespace and base version;
- mapping payload hashes ignoring insertion order and reacting to a changed
  semantic fact;
- a tiny duck-typed world proving allocation ids and log order are ignored by
  the payload projection while a changed fact still changes the hash;
- tick hashes independent of result/ack arrival order;
- missing ack changing the tick hash;
- committed order changing the tick hash;
- undispatched, duplicate and conflicting ack rejection;
- dispatch/result/commit duplicate and mismatch validation;
- payload hash storage, idempotence and conflicting-payload rejection;
- deterministic JSON-safe `to_dict`;
- run hash stability, order sensitivity, empty-run stability and bare-string
  rejection.

Command and result:

```bash
python3 -m pytest -q tests/test_bundle_checks.py tests/test_bundles.py \
  -p no:cacheprovider
# 97 passed
```

Runtime is about 0.3 s, well below the 30 s budget.

## Limitations and caveats

- The mapping branch of `tick_payload_sha` assumes the caller supplied an
  already-semantic payload. Allocation-id stripping and log sorting live in
  `semantic_world_state`, which is only invoked for world-like objects. This
  keeps one definition rather than reimplementing the projection.
- `semantic_world_state` does not yet strip namespace/origin metadata because
  the current `export_state` does not contain any. NB03 must extend that one
  projection (not the mapping branch) when it adds node origins.
- `bundle_output_sha` intentionally excludes `output_sha`/`execution_sha`; call
  it on a result whose other fields are final.
- `TickBundleLog` assumes a single coordinating writer and has no lock. It is
  an audit record, not shared mutable state.
- An ack may be recorded before its result; in that case base version is
  checked against the bundle and execution hash is cross-checked later only if
  a result exists. NB04 should ack after receiving the result.
- The log does not enforce that an ack outcome matches the result status, nor
  monotonic `committed_version` beyond the `BundleAck` constructor rules; that
  remains coordinator policy.
- `commit` records committed order but does not require a committed ack.
- The payload mapping branch uses the stricter `bundles` encoder, which
  requires string keys and plain JSON-safe values; exotic world objects should
  be passed through their `export_state` path instead.

## Handoff

- **NB03 (provenance):** keep `NodeRef` an int. When node origins are added to
  `export_state`, extend `semantic_world_state` in `tick_trace.py` so payload
  hashes drop namespace/origin metadata. Do not add origins to the execution
  payload or accept a second payload definition.
- **NB04 (executor wiring):** create one `TickBundleLog` per tick, dispatch
  bundles, record results, ack only after the coordinator commits, and commit
  in the bundle plan's deterministic order. After applying the tick, call
  `log.payload_sha(game.world)` for the cross-executor hash and use
  `log.execution_sha` plus `run_execution_sha` for the executor path. Do not
  checkpoint the log yet.
