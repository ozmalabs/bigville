# Distributed bundles — final report

Program: **Distributed bundles: namespace, dispatch, confirmation and
checksums**. Plan:
[`docs/design/DISTRIBUTED_BUNDLES.md`](../../design/DISTRIBUTED_BUNDLES.md).
Status: NB01–NB04 committed on `distributed-bundles`; NB05 implemented and
uncommitted at the time of writing.

| Phase | Commit | What it added |
|---|---|---|
| NB01 | `6581ab6` | Pure `Bundle`/`BundleResult`/`BundleAck` protocol, namespace/qualified ids, `LocalBundleTransport` |
| NB02 | `3e9d72d` | Bundle/tick/run checksums and the `TickBundleLog` audit record |
| NB03 | `7c9e3e8` | Per-node execution provenance, qualified ids, legacy-safe checkpoints |
| NB04 | `6ea732b` | Partitioned executor builds, dispatches, validates, acks and commits bundles |
| NB05 | uncommitted | Transport-neutral proof, reproducible equivalence tool, README/plan close-out |

## What changed

### NB01 — protocol and local transport

Added `bigville/bundles.py` with frozen, JSON-safe dataclasses:

- `ExecutionNamespace` — `r<run_id>/t<tick>/<executor>/s<shard>/b<bundle_seq>/a<attempt>`;
- `BundleOperation`, `Bundle`, `BundleResult`, `BundleAck`, `QualifiedId`;
- `BundleTransport` (`dispatch` / `acknowledge` / `replay`) and
  `LocalBundleTransport`.

The transport is caller-supplied-executor based, caches one result per
`bundle_id`, returns the cached object on duplicate dispatch, rejects a result
whose bundle id/namespace/base version does not match, and validates acks
against the stored result. `NodeRef` stays an int; qualified identity is only
the wire/provenance form.

### NB02 — checksums

Added `bigville/bundle_checks.py`:

- execution scope: `bundle_input_sha`, `bundle_output_sha`,
  `bundle_execution_sha`, `tick_execution_sha`, `run_execution_sha`;
- payload scope: `tick_payload_sha`, built on the existing
  `semantic_world_state` projection (allocation ids and log insertion order
  removed);
- `TickBundleLog`: in-memory dispatch/result/ack/commit-order record with a
  deterministic JSON audit form. It is not checkpointed.

### NB03 — provenance

- The graph gained a current execution-namespace context; `add_node` stamps
  the namespace that created each node.
- `node_origin`, `qualified_id` and `nodes_by_origin` expose provenance while
  `NodeRef` remains an int.
- Checkpoints still load old `bigville/graph/1` data; origins are optional and
  old nodes read as `unqualified`/legacy.
- New nodes created during a bundle execution carry that bundle namespace.

### NB04 — partitioned executor

- `PartitionedExecutor.plan_bundles` builds one bundle per deterministic
  coordinator/shard group from `game.last_tick_graph` operations, with declared
  read/write sets and turn-order tiebreaks.
- `commit` dispatches through an injected transport/executor or a fresh
  `LocalBundleTransport`, runs the coordinator barrier first and spatial shards
  in a bounded pool, validates every result, acknowledges/commits in plan
  order, and refuses stale/mismatched results.
- `BigvilleGame` gained a deterministic `run_id` (scenario + map seed) and
  `last_bundle_log`; partitioned turns record the post-turn payload hash.
- `base_version` is documented as `int(world._turn)` because this phase has no
  per-commit world revision.

### NB05 — transport seam and close-out

- `tests/test_bundle_transport.py` proves `Bundle -> JSON -> Bundle ->
  BundleResult -> JSON -> BundleAck` works through `LocalBundleTransport` with
  a synthetic executor and no live game/world.
- `tools/verify_bundle_equivalence.py` compares serial vs partitioned payloads,
  audits every bundle log, replays seeds through a second partitioned game, and
  re-dispatches wire bundles through a world-free transport.
- README explains the protocol, both checksum scopes, local-only status and the
  verification commands.
- The plan status table is updated; no production seam fix was needed.

## Protocol shape

```text
Bundle(
    bundle_id, namespace, run_id, tick, shard, base_version,
    operations, reads, writes, tiebreak,
)
BundleOperation = (op_id, actor, kind, params, reads, writes, tiebreak)

Bundle -> BundleResult(
    bundle_id, namespace, base_version, status,
    effects, created_ids, result, output_sha, execution_sha, reason,
) -> BundleAck(
    bundle_id, base_version, outcome,
    committed_version, execution_sha, reason,
)
```

Invariants now enforced in code:

1. the coordinator is the only committer; a result is invisible until ack;
2. `bundle_id` (the namespace name) is the idempotence key and is unique in a
   run;
3. duplicate dispatch returns the cached result and never executes twice;
4. a stale base version or mismatched namespace/bundle id is rejected, not
   merged;
5. commit order is the deterministic bundle-plan order, not worker completion
   order;
6. `NodeRef` stays an int and old checkpoints still load;
7. bundle dispatch is opt-in (`executor="partitioned"`); serial and threaded
   paths are unchanged.

## Checksum scopes

| Scope | Functions | Includes | Use |
|---|---|---|---|
| Execution | `bundle_input_sha`, `bundle_output_sha`, `bundle_execution_sha`, `tick_execution_sha`, `run_execution_sha` | namespace, executor, attempt, operations/resources, result rows/effects, commit order | Identifies a worker path; same-executor replay should match, different executors need not |
| Payload | `tick_payload_sha` | semantic world facts after a turn, with allocation ids and non-observable list order removed | Cross-executor equivalence: serial and partitioned must match |

A bundle result also carries `output_sha` and `execution_sha`; the tick log
records both tick hashes. `run_execution_sha` folds the ordered per-tick
execution hashes.

## Verification matrix

Required targeted gates:

```text
python3 -m pytest -q tests/test_bundle_transport.py tests/test_bundles.py \
  tests/test_bundle_checks.py tests/test_node_origins.py \
  tests/test_bundle_dispatch.py -p no:cacheprovider
134 passed in 23.60s

python3 -m pytest -q tests/test_tick_sharding.py tests/test_tick_graph.py \
  tests/test_tick_graph_executor.py tests/test_engine_defaults.py \
  tests/test_lazy_*.py -p no:cacheprovider
175 passed, 1 skipped in 103.51s

python3 domains/bigville_entities.py
ERRORS 0, WARNINGS 0, INFO 95
```

Bundle equivalence tool:

```text
python3 tools/verify_bundle_equivalence.py --seeds 305000,305002 --turns 8 --json
exit 0, 37.67 s
seed 305000: payload_equal=True execution_stable=True bundles=8
             run sha == replay sha =
             efdc3f93d6ede36d9ac05c1d3e66f0f345b659ea41bc07e95c4f15f6f05a554a
seed 305002: payload_equal=True execution_stable=True bundles=8
             run sha == replay sha =
             58d49103c5d4b5716b859db4ac1269ee06e90a4bfc0c48b2bab8d6ce21da0140
fake transport: 8/8 and 8/8 bundles round-tripped, duplicate dispatch
                idempotent, replay and acks recorded.

python3 tools/verify_bundle_equivalence.py --seeds 305002 --turns 8 \
  --affordance-mode lazy --json
exit 0, 15.60 s
seed 305002: payload_equal=True execution_stable=True bundles=13
             per-turn=[1,1,2,2,1,2,3,1]
             run sha == replay sha =
             e44c270fcc35d916b020c3b7cd3aa8591349409df5d09415251df2833a8113e3
fake transport: 13/13 bundles round-tripped.

python3 tools/verify_bundle_equivalence.py --seeds 305004,305006 --turns 8 --json
exit 0, 37.17 s
both seeds payload_equal=True execution_stable=True bundles=8;
run sha == replay sha for each seed.
```

In the menu-mode `town100` sample each turn formed one coordinator bundle; the
lazy run exercised 1–3 bundles per turn (multi-bundle dispatch and ordering).
The forced-shard NB04 tests remain the multi-spatial-shard coverage.

The full suite was **not** run during NB05; the host had an active suite and
the targeted gates above are the phase contract. No full-suite result is
claimed.

## Still local only

- **No network/socket/process transport.** `LocalBundleTransport` calls a
  Python callable in the same process. There is no message codec beyond the
  tested JSON forms, no worker lifecycle or supervision, and no
  authentication.
- **Shared-world execution.** The reference executor mutates the in-process
  world during dispatch. Acknowledgement makes a result logically visible but
  cannot roll back a partial mutation after an infrastructure failure.
  `BundleResult.effects` is present but empty in this reference form.
- **Turn version, not per-commit revision.** `base_version` and
  `committed_version` are `int(world._turn)`; bundles in one turn share them.
- **No durable log.** `TickBundleLog`, the transport replay cache and acks are
  in memory and not checkpointed. The default transport is recreated per
  commit; cross-call replay requires an injected/persisted transport.
- **No snapshot shipping.** Bundles carry operations and declared resources,
  not a world checkpoint. Remote restore is not implemented.
- **Graph-only created ids.** Provenance covers the world graph; nested
  resident graphs share the context but are not enumerated by
  `nodes_by_origin`.
- **No backpressure, quota or scheduler policy.** The coordinator dispatches
  the planned groups; there is no admission control beyond the worker pool.

## Next steps for real distribution

1. **Transport implementation.** A process/socket `BundleTransport` using the
   already-tested JSON forms, with connection handling, timeouts, retries and
   the same `dispatch`/`acknowledge`/`replay` contract.
2. **Worker lifecycle.** Process/worker startup, health, supervision,
   cancellation and bounded concurrency.
3. **Durable coordinator log.** Append/checkpoint dispatch, result, ack and
   commit records so a restarted coordinator can replay without re-executing
   committed work.
4. **Snapshot/delta shipping.** Send a base snapshot or ordered deltas to a
   remote worker; replace the shared-world callback with pure
   `BundleResult.effects` application at the coordinator.
5. **Versioning.** Replace the turn-number base version with a monotonic world
   (or per-resource) revision so stale bundles are rejected at commit time.
6. **Security and backpressure.** Authenticate workers, authorise bundles,
   bound queues and apply admission control/quotas.

The bundle identity, idempotence, acknowledgement, deterministic commit order
and two checksum scopes are complete and transport-neutral. The remaining work
is infrastructure around that contract, not a redesign of it.
