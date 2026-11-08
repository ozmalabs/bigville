# DR03 — Graph deltas and effect results

Status: complete (uncommitted), 8 November 2026. Phase DR03 of
[`docs/design/DISTRIBUTED_RUNTIME.md`](../../design/DISTRIBUTED_RUNTIME.md).

- Base commit: `f10dd86` on branch `distributed-runtime` (DR02).
- Changed files: `bigville/runtime.py`, `bigville/sharding.py`,
  `docs/design/DISTRIBUTED_RUNTIME.md` (DR03 status row), this report.
- New file: `tests/test_graph_deltas.py`.
- `bigville/bundles.py` needed no change: `BundleResult.effects` already
  normalises a sequence of JSON-safe mappings, and the effect shape below fits
  that contract.
- No public `node()`/checkpoint shape, world physics or default executor
  changed. Serial and threaded turns still record and write nothing.

## Delta format

`bigville.runtime.GraphDelta` is the replayable record of one execution scope's
successful graph mutations:

| field | shape |
|---|---|
| `base_revision`, `end_revision` | non-negative ints, `end >= base` |
| `nodes_added` | `(id, type, attrs, origin)` |
| `nodes_removed` | `id` |
| `edges_added`, `edges_removed` | `(source, kind, target)` |
| `attrs` | `(node, key, old_value, new_value)` in mutation order |
| `operations` | exact mutation order used for replay |

The categorised lists are the inspection/summary view. `operations` is the
authoritative order and is also serialized, so a remove-then-re-add of the same
edge or attribute replays correctly. A hand-built delta that only fills the
categorised lists is applied in the documented canonical phase order: added
nodes, added edges, attr writes, removed edges, removed nodes.

`to_dict()` is deterministic and JSON-safe:

```json
{
  "schema": "bigville/graph_delta/1",
  "base_revision": 12,
  "end_revision": 17,
  "nodes_added": [[13, "Utterance", {"$type": "dict", "items": []}, "r.../b0/a1"]],
  "nodes_removed": [],
  "edges_added": [[1, "spoke", 13]],
  "edges_removed": [],
  "attrs": [[1, "mood", 2.0, 3.0]],
  "operations": [
    {"op": "add_node", "node": 13, "type": "Utterance",
     "attrs": {"$type": "dict", "items": []}, "origin": "r.../b0/a1"},
    {"op": "add_edge", "source": 1, "kind": "spoke", "target": 13}
  ]
}
```

All non-primitive values (`attrs`, attr old/new) use the existing
`_checkpoint_encode`/`_checkpoint_decode` tags. This retains `NodeRef`, tuple,
set/frozenset and dict fidelity instead of silently flattening a tuple to a list
in the wire form. `from_dict()` validates the schema, revision envelope, every
id/kind/type/origin, and decodes every value.

## Recording semantics

`with graph.record_changes() as delta:` is `ContextVar`-backed, the same
isolation model as node origins:

- two worker threads/contexts get separate deltas; a thread that enters the
  scope after the context was created does not see another thread's delta;
- a nested scope on the *same* graph shares the outer delta and does not reset
  its base revision;
- a nested scope on a *different* graph gets its own delta and restores the
  outer one on exit;
- `base_revision` defaults to the graph revision at entry; `end_revision` is
  the graph revision observed on exit, including successful mutations before an
  exception unwinds the scope.

Only successful mutations are recorded. A missing-node `set_attr`, a missing
endpoint `add_edge_unchecked`, or a no-op `remove_node(absent)` raises or
returns without appending anything. `add_edge*`, `remove_edge*`, `set_attr`,
`add_node` and `remove_node` are all instrumented; there is no `set_type` in
the runtime to record.

`remove_node` records the node and each incident edge exactly once, sorted by
`(source, kind, target)`, before the graph removes them. A node removal still
counts as one revision increment; the incident edge entries are replay detail,
not extra logical revisions.

Attr recording captures the old value before assignment. An absent key is
recorded with `old = None`; the old value is audit information, while replay
always writes `new`.

## Applying a delta

`delta.apply_to(graph, validate_base=True)`:

1. rejects a graph whose `revision` differs from `base_revision` (unless the
   caller explicitly opts out);
2. validates all operations against a shadow of the graph — duplicate node
   adds, missing node/edge endpoints, operation shape, duplicate/removal rules;
3. only then applies under the process-wide graph lock and sets
   `graph.revision = end_revision`.

Validation is complete before the first real mutation, so a rejected delta
leaves the graph untouched. Application itself is not rolled back if an
internal invariant fails after validation; the coordinator is expected to be
the only writer during apply. Nodes are installed with their recorded ids via a
private replay helper (`BigvilleGraph._install_node`), preserving `next_id` and
the canonical checkpoint shape. Applying a delta inside an active
`record_changes()` scope suppresses recording, so replay cannot pollute the
surrounding delta.

## Effects integration

`PartitionedExecutor.make_bundle_executor` now wraps the reference
`game._run_component` call in `graph.record_changes()` and sets:

```python
BundleResult.effects = tuple(delta.to_effects())
```

The in-process world is still mutated directly. Effects are the
transport/replay form, not an alternative write path. Effect operations are:

| op | fields |
|---|---|
| `add_node` | `node`, `type`, `attrs` (encoded), `origin` |
| `remove_node` | `node` |
| `add_edge` / `remove_edge` | `source`, `kind`, `target` |
| `set_attr` | `node`, `key`, `old`, `new` (encoded) |

They are JSON-safe mappings accepted by the existing `BundleResult`
normaliser, so the DR02 journal now carries the real delta without a new record
kind. A bundle with no mutations gets `effects == ()`. For an `error` result,
any mutations made before the exception are still reported; they happened in
the in-process path.

`BundleResult.base_version` is the bundle's base. The delta's own
`base_revision` is the graph revision observed when the bundle actually began
executing; under parallel shards that can be later than the turn base because
another shard already committed. A single-bundle turn has
`delta.base_revision == result.base_version`.

`GraphDelta.from_effects(effects, base_revision=..., end_revision=...)` rebuilds
a delta from a result. The revision envelope is not duplicated in every effect;
callers supply the base from the result and, when exact revision replay is
needed, the end revision from the delta/ack. Without `end_revision` only graph
state is replayed.

## Tests

New `tests/test_graph_deltas.py` (12 tests) covers:

- recording and applying every mutation type, including attr old/new chains and
  an explicit remove-edge followed by a node removal;
- incident-edge recording exactly once in sorted order and replay equality;
- origin preservation through record, JSON and apply;
- failed mutations producing no records and empty effects;
- JSON round trips of `GraphDelta`, `to_dict`/`from_dict` and `to_effects`/
  `from_effects`, with canonical checkpoint and end-revision equality;
- wrong-base rejection and same-base clone acceptance;
- invalid endpoints and duplicate node adds rejected without partial
  application;
- nested recording sharing the outer delta and two threads receiving separate
  deltas;
- a real partitioned bundle turn whose `last_bundle_log` result effects replay
  exactly onto a snapshot at the bundle base (including revision and origins);
- an idle bundle turn with empty effects;
- serial vs partitioned semantic state and revision equality over three turns
  on the DR01 small scenario/seed 305000. Origin provenance intentionally
  differs (bundle namespaces in partitioned, `unqualified` in serial), so the
  comparison is `graph_to_dict()` plus revision, not the full checkpoint.

Commands on this worktree:

```text
python3 -m pytest -q tests/test_graph_deltas.py \
  tests/test_graph_revisions.py tests/test_bundles.py \
  tests/test_bundle_checks.py tests/test_bundle_dispatch.py \
  -p no:cacheprovider
135 passed in 23.64s

python3 -m pytest -q tests/test_tick_sharding.py \
  tests/test_tick_graph_executor.py tests/test_engine_reads.py \
  -p no:cacheprovider
39 passed in 39.57s

python3 -m pytest -q tests/test_bundle_log.py -p no:cacheprovider
24 passed in 1.23s
```

`python3 domains/bigville_entities.py` exited 0 with `ERRORS (0)` and
`WARNINGS (0)`; production graph 481 nodes / 864 edges / 284 components.

## Limitations

- Effects encode graph values with the checkpoint's `$type` tags. They are
  plain JSON-safe mappings, but a consumer that only wants ordinary JSON
  primitives must decode them first (`GraphDelta.from_effects`).
- `BundleResult` has no end-revision field (adding one would change every
  result constructor and checksum). Effects therefore carry operations only;
  the base is `result.base_version` and the authoritative end revision remains
  on the in-process `GraphDelta` / commit ack. A worker-returned delta should
  ship its envelope alongside the effects in DR04.
- A multi-bundle parallel turn cannot be replayed by applying one bundle's
  effects to the turn-base snapshot: each shard's delta is produced from the
  revision it actually observed and the shards may interleave node allocation.
  Exact full-world replay needs coordinator staging/ordering of per-bundle
  deltas (the DR04/DR05 merge path).
- Only the world graph (`game.world.eng`) is recorded by the reference bundle
  executor. Separate subsystem graphs (for example a speech/bond world's own
  `self.s`) are not part of this delta.
- Writing an attrs mapping obtained from `node_attrs()` directly still bypasses
  `set_attr` and therefore the delta, exactly as it bypasses revision counting.
- Recording snapshots attr values through the checkpoint encoder. A value the
  checkpoint cannot represent now raises at record time instead of later at
  checkpoint time; this only affects a scope that is actually recording.
- Effects are unbounded in size; no compression or per-turn size cap is added.
  The journal now stores the full effect list for every partitioned result.
- `apply_to` is process-local and assumes the coordinator serialises writes;
  concurrent cross-process application needs the DR04 worker/commit protocol.

## Handoff to DR04

A worker can now restore a versioned snapshot, execute a bundle, and return a
`GraphDelta` instead of mutating the canonical world. The coordinator should:

1. validate `result.base_version` against the dispatch using the existing stale
   rule;
2. validate the returned delta's base (`apply_to(..., validate_base=True)`) and
   reject rather than merge a stale or malformed delta;
3. apply deltas in plan/commit order, or stage them so parallel shards' revision
   envelopes are resolved before the next turn;
4. carry the authoritative `end_revision` with the worker payload (a dedicated
   delta field/result metadata) so replay can prove the revision count as well
   as the canonical graph state.

No live-world snapshot shipping is added here; the in-process reference
executor intentionally continues to mutate the live world and report what it
did.
