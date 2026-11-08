# NB04 — Wire bundles into the partitioned executor

Status: implemented, targeted gates green (three pre-existing lazy-digest
failures are unchanged from the base commit).

Base commit: `7c9e3e8c41ac2bcdb6605a34d11a6c7dcdd3dc0d`
(`NB03: per-node execution provenance and legacy-safe checkpoints`, branch
`distributed-bundles`).

## Scope

- `bigville/sharding.py` — bundle plan, local dispatch, validation, ack and
  deterministic commit; optional transport/executor seam.
- `bigville/game.py` — deterministic `run_id`, `last_bundle_log`, partitioned
  turn wiring and post-turn payload hash.
- `tests/test_bundle_dispatch.py` — new NB04 coverage.
- `bigville/api.py` — intentionally unchanged. `run_id` is derivable from the
  world, so `create_game` needed no new option. `BigvilleGame` accepts an
  optional `run_id=` argument for callers/tests that need to state one.

No default executor, world rule, checkpoint or contest/joint path changed.
Serial and threaded turns still create no bundle log.

## Bundle construction

`PartitionedExecutor.plan_bundles(game, order, responses, plan)` builds one
bundle per deterministic commit group:

1. the coordinator barrier group, in turn order (all `coordinator_units`);
2. then each spatial shard in ascending numeric shard id, its actors in turn
   order (the EN04 same-cell ordering fix is preserved).

`ShardPlan` is unchanged and remains available as `game.last_shard_plan`.
`component_groups()` is the single source of that order, so planning and commit
cannot drift.

For each group:

- `BundleOperation`s are copied from `game.last_tick_graph` for every operation
  owned by the group's actors: the actor-facing major action, plus its speech
  and memory operations when present. An actor with no major action has the
  graph's `kind="idle"` operation, so it is represented explicitly, with empty
  writes and the graph's payload/reason. Joint operations are excluded: joint
  acts were already resolved before commit and joint members are not units.
- `op_id`, `actor`, `kind`, `params` (from the tick-graph operation payload),
  `reads`, `writes` and `tiebreak` are copied directly.
- The bundle read/write sets are the union of its operations' declared
  resources, in graph order. `Bundle` still validates every operation set as a
  subset.
- Every non-joint actor in `order` appears in exactly one bundle.
- `bundle_id` is the canonical namespace name
  `r<run_id>/t<tick>/partitioned/s<shard>/b<seq>/a1`.
- `bundle_seq` is 0 for the coordinator group, then ascending through the
  sorted spatial shards. The bundle `tiebreak` is the group's turn indices.

## Run id and base version

`BigvilleGame` now has `run_id`:

- optional constructor argument (`BigvilleGame(..., run_id=...)`);
- otherwise derived deterministically from the world's scenario id/name and the
  map seed stored on the world's `Map` node, for example
  `bigville-305000` or `nb04_bundle_room-305000`;
- never derived from `id(self)`, process state or wall time;
- sanitised to the namespace grammar (`/`, `#` and spaces become `_`).

The world has no general revision counter in this phase, so the documented
`base_version` contract is `int(world._turn)`. `BigvilleGame` advances the turn
before it builds the tick graph, so the plan, bundles, namespace `tick`, ack and
`TickBundleLog` all share that version. A world without `_turn` falls back to 0.
This is documented in `_base_version()` and avoids inventing a wall-clock value.

## Dispatch, validation, ack and commit

`PartitionedExecutor.commit` now:

1. builds the same plan as before (unless one is supplied);
2. dispatches every bundle into a `TickBundleLog` in plan order;
3. uses the injected transport, else an injected bundle executor wrapped in
   `LocalBundleTransport`, else a fresh `LocalBundleTransport` around the
   reference callback. The transport/executor seam is available both in the
   constructor and as `commit(..., transport=..., bundle_executor=...)`.
4. runs the coordinator bundle first and serially; spatial shard bundles then
   run in a bounded `ThreadPoolExecutor`, exactly the previous barrier/pool
   semantics. Results are collected in plan order, never completion order.
5. validates each result (`bundle_id`, namespace, `base_version`) before it is
   recorded or acked. A stale/mismatched result raises `BundleResultError`,
   receives a `rejected` ack when a real result object is available, and is
   never stored as a result or merged into the turn.
6. records, acks and commits each valid group in plan order:
   - `ok` and `refused` → `committed`, `committed_version = base_version`;
   - `retry` → `retry`, no commit, clear error;
   - `error` → `rejected`, no commit, clear error.
   Per-actor contained errors remain `(actor, applied, error)` rows and still
   commit, matching serial semantics: one resident's failed unit does not stop
   the turn.

`committed_version` is the turn's plan version because this phase writes no
per-bundle world revision. It is always `>= base_version`, as `BundleAck`
requires.

The reference callback wraps `game._run_component(order, responses, component,
suppressed)` in `world.eng.execution_namespace(bundle.namespace)`, then returns a
`BundleResult` with the actor result triples, `created_ids`, and
`bundle_output_sha`/`bundle_execution_sha`. `effects` is empty while the world is
shared in-process (the protocol explicitly allows this reference form until a
delta transport exists).

Idempotence is the transport's replay cache: a second dispatch of the same
`bundle_id` returns the cached result and does not call the executor. The
`transport=`/`bundle_executor=` arguments are the test seam; the new test
asserts the callback runs once per bundle across two dispatches.

`game.last_bundle_log` is a `TickBundleLog` with dispatched bundles, results,
acks, committed order and the post-turn payload hash
(`semantic_world_state`). It is reset at the start of every turn and remains
`None` on serial/threaded turns.

## Node origins

Every node created while a bundle's callback runs is stamped with that bundle's
namespace by the NB03 context (`world.eng.execution_namespace`). The callback
differs `nodes_by_origin(namespace)` before/after execution to fill
`BundleResult.created_ids` as `QualifiedId(namespace, local_id)`. Nodes created
outside the commit window (world tick, `_finish_turn`) remain `unqualified` or
belong to their own namespace, as before. `NodeRef` stays an int.

## Tests

New `tests/test_bundle_dispatch.py` (12 tests) covers:

- one bundle per coordinator/shard group, exactly non-joint actor coverage,
  unique ids/namespaces, shared base version/tick/run id and bundle seq;
- idle actors represented by a graph `idle` operation;
- complete dispatch/result/ack log, deterministic committed order across two
  identical runs, `committed_version` and execution hashes;
- duplicate dispatch idempotence through `LocalBundleTransport`;
- stale `base_version` rejection and rejected ack without commit;
- namespace mismatch rejection;
- `error` and `retry` results producing non-committed acks, no commit and no
  world change with a synthetic transport;
- node provenance of bundle-created nodes (`MajorAction`/`Effort`/`Event`/
  `Refusal` families);
- serial-vs-partitioned semantic state and trace digest for seeds 305000 and
  305002 over 8 turns in menu mode, plus no duplicate bundle ids/commits;
- serial and threaded turns have no bundle log.

Commands and exact results:

```text
python3 -m pytest -q tests/test_bundle_dispatch.py tests/test_bundles.py \
  tests/test_bundle_checks.py tests/test_node_origins.py -p no:cacheprovider
128 passed in 22.11s

python3 -m pytest -q tests/test_tick_sharding.py \
  tests/test_tick_graph_executor.py tests/test_engine_rule_batching.py \
  -p no:cacheprovider
44 passed in 42.99s

python3 -m pytest -q tests/test_engine_defaults.py tests/test_lazy_*.py \
  -p no:cacheprovider
128 passed, 1 skipped, 3 failed in 63.40s

python3 domains/bigville_entities.py
ERRORS 0, WARNINGS 0, INFO 95
```

The three failures are the `MENU_DIGEST_AT_LA01` assertions in
`test_lazy_cheap.py`, `test_lazy_observation.py` and
`test_lazy_target_resolution.py`. They were reproduced unchanged from a clean
`git archive HEAD` tree at the base commit (`3 failed in 0.55s`), so they are
pre-existing and unrelated to NB04.

Semantic comparison for the NB04 regression tests:

```text
seed 305000, 8 turns, menu: first_divergence = None
  trace digest equal; semantic_world_state equal;
  last_order/last_results/last_errors equal
seed 305002, 8 turns, menu: first_divergence = None
  trace digest equal; semantic_world_state equal;
  last_order/last_results/last_errors equal
partitioned bundle log: no duplicate dispatched ids or committed ids
```

## Limitations

- The local callback mutates the shared world during dispatch; the result is
  logically invisible until ack, but a transport-level error after partial
  mutation cannot be rolled back. This is the documented reference
  implementation, not a distributed transaction.
- `base_version` is the world turn, not a per-commit world revision. Two
  commits inside one turn share it; `committed_version` does the same.
- `created_ids` covers the world graph. Nested resident graphs observe the same
  namespace context but are not part of `world.eng.nodes_by_origin`.
- A fresh default transport is created per commit. Cross-call replay is
  guaranteed only when the caller injects/persists one transport; a transport
  must be scoped to one run because bundle ids include the deterministic run
  id and tick.
- No network, process, socket, durable log or snapshot shipping is added.

## Handoff to NB05

NB05 can drive the same `Bundle`/`BundleResult` through a fake out-of-process
transport using the `transport=`/`bundle_executor=` seam. The audit inputs are
already recorded: `TickBundleLog.execution_sha` (execution path, executor and
commit order) and `payload_sha()` (semantic world after the turn). NB05 should
compare payload hashes between serial and partitioned runs, record the run-level
execution hash, and document what remains for real transport, lifecycle,
durability, snapshot shipping and backpressure.
