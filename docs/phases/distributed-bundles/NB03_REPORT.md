# NB03 — Per-node provenance and qualified ids

Status: implemented, targeted gates green.

Base commit: `3e9d72dfa50733fe8c74507437e4063ed0da2f27` (`NB02: bundle, tick, run and payload checksums`)

## Scope

- `bigville/runtime.py` — origin context, `_Node.origin`, provenance API,
  checkpoint `origins` plus legacy migration.
- `tests/test_node_origins.py` — new coverage for NB03.
- `bigville/world_persistence.py` — intentionally unchanged. A graph origin is
  per-node checkpoint data, not a new world attribute, so `_EXTERNAL_FIELDS`
  needed no entry.

`NodeRef` remains an `int` subclass. No public id became a string or tuple.

## Origin context design

`bigville/runtime.py` adds:

```python
DEFAULT_ORIGIN = "unqualified"
_CURRENT_ORIGIN = contextvars.ContextVar(
    "bigville_graph_origin", default=None)
```

- The context variable holds the canonical execution namespace string. A
  `ContextVar` was chosen over thread-local state because it isolates both
  threads and concurrent async/context workers, and token reset makes nested
  entry safe. Threads that do not copy a context start with no binding.
- `BigvilleGraph.default_origin` is the class-level fallback
  (`"unqualified"`) used when no context is bound. Being a class attribute, it
  is not serialized into a world checkpoint and old checkpoints keep loading.
- `BigvilleGraph.current_origin` reports the effective origin (context binding
  or `default_origin`).
- `BigvilleGraph.execution_namespace(namespace)` is a re-entrant context
  manager. It accepts either an `ExecutionNamespace` (using its canonical
  `.name`) or a non-empty string, sets the context token, and restores the
  previous token in `finally`, including on exception.
- `add_node` stamps `_Node.origin` from `current_origin`. Its signature is
  unchanged.
- The context variable is module-wide, so a nested graph (a resident mind's
  private graph, or a voice graph) observes the same binding while a bundle
  namespace is active. This is deliberate: provenance follows the executing
  bundle, whichever graph receives the node.

## Node origin API

- `_Node` gained `origin: str = DEFAULT_ORIGIN`.
- `node_origin(node) -> str` reads the stored origin under the graph's read-lock
  policy.
- `qualified_id(node) -> QualifiedId` builds
  `QualifiedId(namespace=origin, local_id=int(node))`. `QualifiedId` is
  imported locally from `bigville.bundles`, so no import cycle or import-time
  coupling was introduced.
- `nodes_by_origin(origin) -> tuple[NodeRef, ...]` filters the graph and returns
  strictly ascending node ids.
- `node()` still returns exactly `{"type": ..., "attrs": ...}`; origins are not
  leaked into the public projection. `graph_to_dict()` is unchanged too, so its
  display/persistence consumers (for example `worlds/bigville_sim_world.py`)
  keep their existing shape.

## Checkpoint schema and migration

The schema string remains `"bigville/graph/1"`; the change is additive, so a
version bump was not required.

`to_checkpoint_dict()` now emits, in ascending node-id order:

```json
"origins": [[1, "unqualified"], [2, "rrun/t3/local/s0/b1/a1"]]
```

`from_checkpoint_dict()` behavior:

- Missing `origins` key: every node migrates to `"unqualified"`, the documented
  legacy namespace. New saves immediately round trip with explicit origins.
- Present `origins`: must be a list of `[int, str]` pairs. The loader rejects
  malformed entries, non-integer/non-positive node ids, duplicate ids,
  non-string or empty origin names, origins that reference a missing node, and
  origins that fail to cover every node (missing origin).
- Round trip preserves origins exactly; restored ids remain `NodeRef`/`int`.
- `world_persistence` continues to call the same encode/decode methods, so
  world and resident-graph checkpoints carry origins without any world-field
  change.

## Tests

New file `tests/test_node_origins.py` (19 tests) covers:

- unqualified default and `QualifiedId` construction;
- explicit namespace stamping and public `node()` shape;
- nested and re-entrant namespace context restore, including exception-free
  exit ordering;
- interleaved nodes under two namespaces, `nodes_by_origin` ordering;
- two-thread isolation with a barrier and no main-thread leak;
- checkpoint round trip, deterministic `origins` order, and `NodeRef`/`int`
  identity;
- legacy checkpoint without `origins` migrating to `"unqualified"`;
- rejection of duplicate ids, unknown ids, missing coverage, non-string/empty
  origins, non-list `origins` and malformed pairs;
- invalid context-manager arguments;
- a full `save_world_checkpoint`/`load_world_checkpoint` round trip preserving a
  namespace-stamped world node.

Commands and results:

```text
python3 -m pytest -q tests/test_node_origins.py \
  tests/test_bigville_graph_persistence.py tests/test_engine_reads.py \
  -p no:cacheprovider
35 passed in 1.30s

python3 -m pytest -q tests/test_bigville_world_persistence.py \
  tests/test_bigville_game_persistence.py -p no:cacheprovider
9 passed, 1 skipped in 1.64s
```

The skipped persistence test is the existing
`pytest.importorskip("worlds.bigville_ocelot_adapter")` provider test.

Additional assurance: `tests/test_tick_graph.py` passed. In
`tests/test_tick_trace.py`, 20 tests passed and
`test_changing_one_proposal_changes_the_digest_and_is_reported` failed. That
failure reproduces unchanged at the NB03 base commit `3e9d72d`; it is a
pre-existing simple-backend expectation, not an NB03 regression.

## Limitations

- Provenance is per node creation only. `set_attr`, edge addition and node
  mutation do not record a last-writer namespace; NB03 asked for creation
  origin.
- Origins are unvalidated free-form strings when set through
  `execution_namespace`; callers are expected to pass an `ExecutionNamespace`
  or its canonical `.name`. The checkpoint loader validates that an origin is
  a non-empty string, but does not require the canonical namespace grammar
  because `"unqualified"` and legacy labels are intentionally outside it.
- The origin context is process-local. A future out-of-process worker must set
  the same context in the worker process (NB04/NB05).
- `to_checkpoint_dict()` now feeds checksum/digest consumers
  (`tick_trace.world_sha256`, decision-snapshot digests). Two otherwise equal
  worlds whose nodes were created under different namespaces will now have
  different strict graph digests. That is the intended provenance signal; the
  semantic `export_state` projection is unchanged.

## Handoff

- **NB04:** when dispatching a component as a bundle, enter
  `world.eng.execution_namespace(bundle.namespace)` (or the target graph's
  manager) around worker execution so created ids receive the bundle namespace.
  Use `QualifiedId = graph.qualified_id(ref)` for `created_ids` in
  `BundleResult`. The context variable is shared by nested resident graphs, so
  no per-graph plumbing is needed. Keep the default serial path outside any
  namespace so existing worlds stay `"unqualified"`.
- **NB05:** the transport-neutral worker test should carry origins through a
  JSON round trip and use qualified ids in payload comparison while stripping
  them from `tick_payload_sha`. An out-of-process worker must establish its own
  `execution_namespace` context; the checkpoint `origins` list is the durable
  provenance record to compare.
