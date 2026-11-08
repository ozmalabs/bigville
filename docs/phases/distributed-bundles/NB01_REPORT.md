# NB01 — Bundle protocol and local transport

Status: complete, 8 November 2026. Phase NB01 of
[`docs/design/DISTRIBUTED_BUNDLES.md`](../../design/DISTRIBUTED_BUNDLES.md).

- Base commit: `f63c63ede9984f329eb988bbbb4358cd3e1be079`
  (branch `distributed-bundles`, the plan commit before NB01 changes).
- Scope: pure protocol objects and an in-process transport only. No game,
  executor, checkpoint, default-path or world behaviour changed.
- File added: `bigville/bundles.py`; tests added: `tests/test_bundles.py`.

## Protocol shapes

All protocol objects are frozen dataclasses. Integer fields reject `bool`;
run/executor/op/kind/hash ids reject empty strings; all `from_dict` readers
reject missing and unknown keys so a field drift cannot be silently ignored.

### `ExecutionNamespace`

```text
ExecutionNamespace(run_id, executor, shard, tick, bundle_seq, attempt=1)
name = r<run_id>/t<tick>/<executor>/s<shard>/b<bundle_seq>/a<attempt>
```

Example: `r17/t42/partitioned/s3/b7/a1`. `run_id`, `executor`, `shard`,
`tick` and `bundle_seq` must be non-negative (`run_id`/`executor` non-empty
strings) and `attempt >= 1`. `/` and `#` are reserved delimiters and are
rejected inside the run id and executor.

`ExecutionNamespace.parse` validates the grammar and rejects non-canonical
spellings such as `t042`, `a0`, a trailing slash or missing segments.
`is_valid_name` is the non-raising form. `to_dict`/`from_dict` round trip
exactly. A retry is expected to reuse the same namespace; `attempt > 1` is an
explicit branch, not an implicit retry.

### `QualifiedId`

```text
QualifiedId(namespace, local_id)   # namespace is a namespace name
str() = "<namespace>#<local_id>"
```

`namespace` is non-empty and must not contain `#`; `local_id` is a
non-negative int. `parse`, `to_dict` and `from_dict` round trip. This is the
wire/provenance form only: `NodeRef` in the graph remains an int.

### `BundleOperation`

```text
BundleOperation(op_id, actor, kind, params, reads, writes, tiebreak)
```

- `op_id`/`kind` non-empty; `actor` is `None` or a non-empty string.
- `params` must be a mapping with string keys; values pass through
  `canonical_value` and the result is stored in a `MappingProxyType`
  (top-level read-only). Tuples become lists, `NodeRef` becomes a plain int.
  Sets, arbitrary objects, non-string keys and non-finite floats raise
  `BundleValueError`.
- `reads`/`writes` are coerced to tuples of `Resource`; `tiebreak` is a
  tuple/list coerced to a tuple through the same JSON-safe normaliser.
- `sort_key()` gives the documented deterministic intra-bundle order:
  tiebreak components (typed ranks), actor, then op id.
- `to_dict` preserves operation/resource order; `canonical_dict` sorts
  resources and is the order-insensitive checksum form.

### `Bundle`

```text
Bundle(bundle_id, namespace, run_id, tick, shard, base_version,
       operations, reads, writes, tiebreak)
```

`bundle_id` is non-empty and is also `dedupe_key`. `namespace` must be an
`ExecutionNamespace`, and `run_id`/`tick`/`shard` must match it exactly.
`base_version >= 0`; `operations` is a tuple of `BundleOperation` with unique
`op_id`s. Every operation's read set must be a subset of the bundle read set
and every write set a subset of the bundle write set. The bundle-level sets
may be a strict superset because a shard group carries the union of its
components; that is the documented consistency rule.

`to_dict` preserves the plan's operation order. `input_dict` is the checksum
input and contains exactly `namespace`, `base_version`, deterministically
ordered operations, sorted reads and sorted writes (no `bundle_id`, matching
the design formula). `canonical_dict` adds the bundle id, and
`canonical_json` is compact canonical JSON. `ordered_operations()` exposes the
deterministic order without mutating the stored tuple.

### `BundleResult`

```text
BundleResult(bundle_id, namespace, base_version, status,
             effects, created_ids, result, output_sha, execution_sha, reason)
```

- `status` is one of `ok`, `refused`, `retry`, `error`; `succeeded` is true
  only for `ok`.
- `effects` is a tuple of mappings normalised to JSON-safe values and stored
  read-only at the top level.
- `created_ids` is a tuple of `QualifiedId`; each id's namespace must equal
  `result.namespace.name`.
- `result` is a tuple of `(actor, applied, error)` rows: actor is `None` or a
  non-empty string, `applied` is a bool, error is `None` or a non-empty string.
- Both checksums must be non-empty strings; `reason` is optional text.
- `to_dict` preserves effect/created-id/row order; `canonical_dict` sorts each
  of those lists and is the order-insensitive output form.

### `BundleAck`

```text
BundleAck(bundle_id, base_version, outcome, committed_version,
          execution_sha, reason)
```

`outcome` is `committed`, `retry` or `rejected`; `base_version >= 0` and
`execution_sha` is non-empty. A committed ack requires
`committed_version >= base_version`; retry/rejected acks require
`committed_version is None`.

### Transport

```python
class BundleTransport(Protocol):
    def dispatch(self, bundle: Bundle) -> BundleResult: ...
    def acknowledge(self, ack: BundleAck) -> None: ...
    def replay(self, bundle_id: str) -> BundleResult | None: ...
```

`LocalBundleTransport(executor, *, results=None)` holds a caller-supplied
`(Bundle) -> BundleResult` callable. It keeps a replay cache keyed by
`bundle_id`, a per-bundle in-flight marker, an ack table and a dispatch-order
list. `results` preloads the cache for replay of a durable log; preloaded
entries never call the executor and are not counted in `dispatch_order`.

## Idempotence and ack behaviour

- First dispatch calls the executor once, validates the returned
  `BundleResult`, caches it and records the bundle id.
- Duplicate dispatch returns the **same cached object**; the executor is not
  called again. Concurrent dispatches of one id wait on the leader's event and
  return the leader's cached result. Distinct bundle ids may execute
  concurrently because the executor is not called under the shared lock.
- A re-entrant dispatch of the same `bundle_id` from inside its own executor
  raises `RuntimeError` rather than deadlocking.
- `dispatch` validates that the result's `bundle_id`, `namespace` and
  `base_version` match the dispatched bundle. A mismatch raises `ValueError`
  and caches nothing.
- If the executor raises, the exception reaches the caller and no result is
  cached; the in-flight marker is cleared and the id is removed from
  `dispatch_order`. A later dispatch retries the executor. This is deliberate:
  an infrastructural failure is not a deterministic `BundleResult`, so the
  coordinator, not the transport, decides whether to retry.
- `replay` returns the cached result or `None`; it never executes the
  executor.
- `acknowledge` requires a cached result for the bundle id and checks
  `base_version` and `execution_sha` against that result. Unknown bundles and
  mismatches raise `ValueError`. Repeating an identical ack is idempotent; a
  second, different ack for the same bundle raises `ValueError`.
- `to_dict` returns `dispatch_order`, a bundle-id-sorted result map and a
  bundle-id-sorted ack map, all JSON-safe and deterministic for auditing.

The transport does not enforce that the ack outcome corresponds to the result
status. That is coordinator policy (for example, `refused`/`error` normally
become `rejected`) and is intentionally left to NB04/NB05.

## Tests

`tests/test_bundles.py` covers:

- namespace name grammar, canonical parse, invalid values, non-canonical text,
  `to_dict`/`from_dict` round trip and missing/extra keys;
- `QualifiedId` string/parse/round trip and invalid forms;
- operation freezing, read-only params, tuple normalisation, round trip,
  canonical form and rejection of set/non-string-key/NaN values;
- bundle round trip, `dedupe_key`, operation/resource-order-independent
  canonical forms, duplicate op ids, run/tick/shard mismatch, operations
  outside the bundle resource sets and bad versions;
- result/ack round trips, invalid statuses/outcomes/versions/rows, created-id
  namespace mismatch and effect validation;
- JSON safety: `NodeRef` is emitted as a plain int, tuples as lists, and the
  serialized dictionaries survive `json.dumps`;
- transport idempotence, replay identity, concurrent duplicate dispatch
  executing once, audit `to_dict`, preloaded results, ack recording and
  idempotent repeat, unknown/mismatched/conflicting ack rejection, executor
  failure not cached, mismatched result not cached.

Command and result:

```bash
python3 -m pytest -q tests/test_bundles.py -p no:cacheprovider
# 73 passed
```

Runtime is about 0.2 s in this checkout, well below the 30 s budget.

## Limitations and caveats

- `effects` are opaque JSON-safe deltas. NB01 validates their shape and
  serializability, not the semantics of `set_attr`/`add_node`/`add_edge`.
- `output_sha` and `execution_sha` are required but not computed here; NB02
  supplies the checksum functions. The transport only compares the execution
  hash present on the result and ack.
- `base_version` is a protocol field, not a world version. The transport checks
  result-vs-dispatch base equality only; a stale base against the live world is
  a coordinator concern for NB04.
- The cache is in memory and per transport instance. There is no durability,
  process lifecycle, socket, authentication or snapshot shipping.
- `bundle_id` uniqueness is scoped to a run/coordinator. The transport trusts
  the caller for that uniqueness; it only guarantees per-id idempotence.
- `params` and effect mappings are read-only at the top level. Nested values
  are fresh copies produced by the normaliser and are JSON values, but they are
  not recursively frozen.
- Ack outcome/result-status consistency and committed-version monotonicity
  beyond `committed_version >= base_version` are left to the coordinator.

## Handoff

- **NB02 (checksums):** use `Bundle.input_dict()` /
  `Bundle.canonical_dict()` and `BundleResult.canonical_dict()` as the
  canonical inputs. `canonical_json` is the compact sorted-key encoder. Do not
  re-sort operation resources differently: the bundle already sorts resources
  and orders operations by `sort_key()`.
- **NB04 (game wiring):** build one `Bundle` per conflict component/shard
  group, with the union of component resources at bundle level and each
  operation's declared sets as subsets. Pass a monotonic `base_version`,
  dispatch through `LocalBundleTransport`, translate the result into the
  existing actor-result path, ack only after the coordinator commits, and
  commit bundles in the bundle plan's deterministic order, never in worker
  completion order. Use `dispatch_order`/`to_dict` for the tick audit log.
- **NB03 (provenance):** `QualifiedId.namespace` is already checked against the
  result namespace; node allocation remains the worker's job. Keep `NodeRef`
  an int and use `QualifiedId` only at the provenance/wire boundary.
