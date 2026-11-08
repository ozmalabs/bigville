# DR01 — Graph revisions and stale-bundle validation

Status: complete (uncommitted), 8 November 2026. Phase DR01 of
[`docs/design/DISTRIBUTED_RUNTIME.md`](../../design/DISTRIBUTED_RUNTIME.md).

- Base commit: `3da2903` on branch `distributed-runtime`.
- Scope: `bigville/runtime.py`, `bigville/sharding.py`,
  `worlds/bigville_world.py` (the world revision property; `BigvilleWorld`
  lives there, not in `bigville/game.py`), `tests/test_graph_revisions.py`
  (new), one expected-value update in `tests/test_bundle_dispatch.py`, this
  report and the plan status row.
- No default executor, world physics or checkpoint schema version changed.

## Revision semantics

`BigvilleGraph.revision` is an in-memory, monotonically increasing integer
starting at 0. One successful public mutation call advances it exactly once:

| Call | Increment |
|---|---|
| `add_node` | +1 |
| `add_edge` / `add_edge_unchecked` | +1 (the public form delegates, so not +2) |
| `remove_edge_unchecked` | +1 |
| `remove_node` | +1, regardless of how many incident edges it cleans up |
| `set_attr` | +1 |
| reads, origin stamps, `execution_namespace`, `settle`, `force_all_dirty` | 0 |
| `load_seed_manifest` | through the `add_node` / `add_edge_unchecked` calls it makes (a new seed is +1; a new seed held by an existing agent is +2) |

A failed mutation that raises (missing node/endpoint) or a `remove_node` of an
absent node does not advance the revision. Increments happen under the existing
process-wide `_GRAPH_LOCK`, so a concurrent reader sees a whole increment.

There is no `set_type` in the graph runtime, so no type-change increment was
added. This is a call counter, not an equality check on graph state: repeating
an already-present `add_edge_unchecked`, for example, still counts as one
mutation call. That is deterministic and identical on serial, threaded and
partitioned paths.

`BigvilleWorld.revision` returns `int(self.eng.revision)`. It is a property,
not a stored field, so world checkpoints preserve the value through the graph
checkpoint and legacy world checkpoints (with a legacy graph) report 0.

## Checkpoint migration

`to_checkpoint_dict()` now includes `"revision"`. `from_checkpoint_dict()`:

- accepts a missing key as legacy and loads revision 0;
- rejects an explicit `null`, `bool`, non-int or negative value with
  `ValueError("Bigville graph checkpoint has invalid revision")`;
- applies the saved revision after restoring edges (restore itself calls
  `add_edge_unchecked`, which would otherwise leave the counter at the number
  of restored edges);
- round trips exactly: `from_checkpoint_dict(json.loads(json.dumps(data)))`
  returns the same `to_checkpoint_dict()`.

## Base and committed versions

- `PartitionedExecutor._base_version(world)` uses `world.revision`, then
  `world.eng.revision` (test doubles), and only then the historical
  `world._turn` fallback. A world with neither uses 0.
- `plan_bundles` captures the base once and stamps every bundle of the turn
  with that same `base_version` (namespace tick and bundle tick included).
- `validate_result(bundle, result)` still rejects any result whose
  `bundle_id`, namespace or `base_version` differs from the dispatch. The
  optional keyword `committed_version` additionally rejects a value below the
  bundle base.
- `ack_for(bundle, result, committed_version=...)` reports the post-apply
  graph revision for committed outcomes. The coordinator observes the world
  revision while committing in plan order; the in-process transport has
  already applied the shard effects, so the observed value may include other
  shards' effects. It is clamped to a walking maximum, giving a documented
  monotonic rule, and is never below the bundle base. Calling `ack_for`
  without the keyword keeps the historical base value for pure callers.
- Non-committed outcomes (`retry`, `error`, `rejected`) still report
  `committed_version=None`.
- `TickBundleLog` was not changed: it already keeps the dispatched `Bundle`
  (base/tick) and the acknowledged `BundleAck` (base/committed) in `.to_dict()`.

## Tests

New `tests/test_graph_revisions.py` covers: every mutation type increments
once; `remove_node` with several incident edges is one increment; reads,
provenance and execution namespaces do not increment; failed mutations do not
increment; seed manifests increment through their node/edge calls; checkpoint
round trip; legacy checkpoint loads as 0; invalid revision values are rejected;
`BigvilleWorld.revision` / `_base_version`; serial and partitioned revisions are
equal after four identical turns on the small scenario; bundle plans use the
current world revision; committed acks are monotonic and `>= base`; a
`base_version + 1` synthetic result is rejected by `validate_result`.

`tests/test_bundle_dispatch.py` was updated only where revision values changed:
the old "base version equals world turn" assertion became "all bundles share
one base captured from the revision, `log.tick == base`, and base is not newer
than the post-turn revision"; the old `committed_version == base` assertion
became `committed_version >= base` plus non-decreasing commit order.

Command results on this worktree:

```text
python3 -m pytest -q tests/test_graph_revisions.py tests/test_bundles.py \
  tests/test_bundle_checks.py tests/test_bundle_dispatch.py \
  tests/test_bigville_graph_persistence.py -p no:cacheprovider
129 passed in 21.45s

python3 -m pytest -q tests/test_tick_sharding.py tests/test_tick_graph.py \
  tests/test_tick_graph_executor.py -p no:cacheprovider
44 passed in 45.15s

python3 -m pytest -q tests/test_bigville_world_persistence.py \
  tests/test_bigville_game_persistence.py -p no:cacheprovider
9 passed, 1 skipped in 1.17s

python3 -m pytest -q tests/test_bundle_transport.py tests/test_node_origins.py \
  tests/test_engine_reads.py -p no:cacheprovider
35 passed in 0.79s
```

`python3 domains/bigville_entities.py` completed with `ERRORS (0)` and
`WARNINGS (0)` (95 informational lines; production graph 481 nodes / 864 edges
in 284 components).

Each runtime block finished well under 60 seconds.

## Limitations

- The revision counts mutation **calls**, not distinct state transitions (a
  duplicate edge add or an absent-edge remove still increments).
- World code that writes an attrs mapping obtained from `node_attrs()` directly
  bypasses `set_attr` and is therefore invisible to the counter. The current
  world mostly mutates through the graph API; DR03's change recording should
  eliminate this ambiguity for the mutations it must replay.
- The committed version is observed by the coordinator after dispatch, so it
  may be greater than the individual bundle's own contribution when several
  shards completed first. It is monotonic and `>= base`, but it is not a
  per-shard isolated commit counter.
- The revision remains in-memory; durable replay of revision history is DR02's
  journal work, not part of this phase.
- No network or worker-boundary execution was added; distribution remains the
  opt-in in-process partitioned path.

## Handoff

- **DR02:** record dispatch/base/committed revisions and tick checksums in the
  append-only journal. The log already carries base on the dispatched bundle
  and committed on the ack; the journal can serialize those directly. Consider
  writing the post-turn revision on `tick_end`.
- **DR03:** record mutations as deltas. The revision increment points are the
  natural recording boundaries; a recorded delta should declare the base
  revision it was produced from and be rejected by the same stale-base rule
  used here.
