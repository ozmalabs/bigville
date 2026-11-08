# Distributed runtime — final report

Status: complete (DR01-DR04 committed; DR05 uncommitted at time of writing),
8 November 2026.  Program plan:
[`docs/design/DISTRIBUTED_RUNTIME.md`](../../design/DISTRIBUTED_RUNTIME.md).
Predecessor program:
[`docs/phases/distributed-bundles/FINAL_REPORT.md`](../distributed-bundles/FINAL_REPORT.md).

This program took the in-process bundle protocol from `DISTRIBUTED_BUNDLES`
and added the runtime seam a worker boundary needs: monotonic graph revisions,
a durable replayable journal, replayable effect deltas, a real local process
transport, and one verification pass that exercises all four together.

Distribution is still **opt-in and local**.  The default executor, world
physics and checkpoint schema are unchanged.

## Phases delivered

| Phase | Commit | Delivered |
|---|---|---|
| DR01 | `1ddf95b` | `BigvilleGraph.revision` / `BigvilleWorld.revision`, revision in checkpoints with legacy migration, bundle `base_version` and committed ack versions, stale-result rejection. |
| DR02 | `f10dd86` | `BundleJournal`: append-only canonical JSONL with `tick_start`/`dispatch`/`result`/`ack`/`commit`/`tick_end`, fsync per record, `read`/`replay`/`verify`, truncation/corruption reporting, optional `bundle_log_path`. |
| DR03 | `bf267a8` | `GraphDelta` recording (`record_changes`), JSON-safe `to_dict`/`from_dict`, validated `apply_to`, `to_effects`/`from_effects`, real effect population in partitioned bundle results. |
| DR04 | `ef1baf9` | `ProcessBundleTransport`: JSON pipe to `multiprocessing` workers, synthetic `delta` executor, idempotence cache, validation, timeout/retry, crash/restart, clean shutdown. |
| DR05 | uncommitted | `verify_bundle_equivalence.py` journal/delta/process integration, `tests/test_distributed_runtime.py`, overhead and seed matrix, this report and README/plan status. |

Each phase has a report in `docs/phases/distributed-runtime/DRxx_REPORT.md`.

## Capabilities now available

### Protocol and revisions

- `Bundle -> BundleResult -> BundleAck` with a canonical namespace/idempotence
  key and the same rules in-process, across a JSON round trip and across a real
  process.
- Every bundle names the graph revision it read (`base_version`).  A result
  with a stale base, wrong namespace or wrong bundle id is rejected, never
  merged.
- Acks report a monotonic committed version; commit order is the deterministic
  plan order, not worker completion order.
- Graph revisions advance per successful mutation call and round-trip through
  checkpoints.  Serial, threaded and partitioned turns produce the same
  revision count for identical seed/turn inputs.

### Durable journal

- Optional `bundle_log_path` on `create_game` / `BigvilleGame`; serial and
  threaded turns write nothing.
- Append-only JSONL, one canonical record per line, `fsync` before append
  returns, single-writer rule documented and enforced process-locally.
- `read`, `replay` and `verify` rebuild tick logs, check bundle/result/ack/commit
  coverage, recompute checksums, check commit monotonicity and revisions, and
  distinguish a truncated tail from corruption.
- The DR05 tool proves the replayed tick log and both checksums equal the live
  `game.last_bundle_log` after every turn.

### Effect deltas

- `with graph.record_changes() as delta` captures nodes, edges and attr
  old/new values in exact mutation order, context-local per thread/context.
- `GraphDelta` is a validated, deterministic, JSON-safe value; `apply_to`
  validates against a shadow and enforces the base revision before mutating.
- Partitioned bundle results carry the recorded delta as
  `BundleResult.effects`; a no-op bundle has empty effects.
- `GraphDelta.from_effects` reconstructs the replayable delta (with a caller
  supplied revision envelope), and the journal stores the effects without a
  new record kind.

### Local process transport

- `ProcessBundleTransport` sends only JSON wire bundles over a
  `multiprocessing` pipe; workers never import the live game.
- One execution per `bundle_id`, including concurrent duplicates; per-attempt
  timeout, retry for timeout/crash, worker replacement, executor-error
  reporting, graceful idempotent close, no orphan processes.
- Results pass the same `PartitionedExecutor.validate_result` identity/staleness
  checks as the in-process transport.
- The transport is a seam, not a default: `PartitionedExecutor(transport=...)`
  already accepts it, but `create_game` still uses the in-process path unless
  the executor is `"partitioned"`.

### Verification tool

`tools/verify_bundle_equivalence.py` keeps its original serial / partitioned /
replay checksum matrix and adds:

- `--journal PATH` — partitioned journal, replay/verify every turn, compare
  with the live log and checksums;
- `--deltas` — effect presence on mutating turns, delta JSON round trip and
  base/end consistency with the bundle, result and ack;
- `--process` — serialized-bundle dispatch, duplicate-dispatch idempotence,
  stable checksums, ack/replay and clean close through a real worker.

Exit code is non-zero on any requested-scope failure; JSON output is preserved.

## Verification evidence

DR05 seed matrix (menu, `town100`, 8 turns, journal + deltas + process):

| Seed | Bundles | Payload | Execution | Revision | Journal replay | Journal bytes | Effects |
|---|---:|---|---|---|---|---:|---:|
| 305000 | 8 | equal | stable | equal | equal | 2,381,817 | 16,397 |
| 305002 | 8 | equal | stable | equal | equal | 2,392,640 | 16,527 |
| 305004 | 8 | equal | stable | equal | equal | 2,375,126 | 16,634 |
| 305006 | 8 | equal | stable | equal | equal | 2,361,397 | 16,405 |

Lazy seed `305002`, 8 turns: 13 bundles, all comparisons equal, journal
replayed, 16,416 effects, process smoke passed; exit 0.

Overhead on short partitioned `town100` runs was about 685 ms/turn partitioned
versus 364 ms/turn serial, 746 ms/turn with the journal and 788 ms/turn with
journal plus per-turn delta verification, on a contended host (load 5.4-6.2).
The journal was 1.25 MB for 4 turns / 24 records, about 311 KB/turn.  Full
numbers and caveats are in [`DR05_REPORT.md`](DR05_REPORT.md).

Exact gates run on this worktree:

```text
python3 -m pytest -q tests/test_distributed_runtime.py \
  tests/test_bundle_log.py tests/test_graph_deltas.py \
  tests/test_graph_revisions.py tests/test_process_transport.py \
  tests/test_bundle_transport.py tests/test_bundle_dispatch.py \
  -p no:cacheprovider
91 passed in 27.48s

python3 -m pytest -q tests/test_tick_sharding.py tests/test_tick_graph.py \
  tests/test_tick_graph_executor.py tests/test_engine_defaults.py \
  tests/test_lazy_*.py -p no:cacheprovider
175 passed, 1 skipped in 101.29s

python3 domains/bigville_entities.py
exit 0; ERRORS (0); WARNINGS (0); 481 nodes, 864 edges, 284 components

python3 tools/verify_bundle_equivalence.py \
  --seeds 305000,305002,305004,305006 --turns 8 \
  --journal /tmp/opencode/dr05_bundle.jsonl --deltas --json
exit 0; all four seeds payload/execution/revision/journal/delta equal
```

A full-suite run was **not** completed in this phase and no full-suite pass is
claimed.  The worktree was under the targeted-test instruction while the host
was contended; the exact targeted gates above passed.

## What remains for true remote distribution

1. **Network transport.** Replace or wrap the `multiprocessing` pipe with a
   framed socket/broker transport that keeps the same JSON envelope and
   `dispatch`/`acknowledge`/`replay` contract.
2. **Authentication and authorisation.** Identify coordinator and workers,
   sign/verify bundle and result payloads, and reject an unauthorised commit.
3. **Backpressure and flow control.** Bound in-flight bundles, queue depth and
   result/effect sizes; the current `max_message_bytes` is a single-message
   guard, not a scheduler.
4. **Snapshot shipping and restore.** Ship a versioned world snapshot (or a
   content-addressed handle) with the dispatch, restore it in the worker at
   `bundle.base_version`, and prove the restored graph revision matches.
5. **Live-world worker executor.** Implement the DR04 extension point: a
   worker restores the snapshot, executes the bundle, returns effects plus an
   authoritative end revision.  Today only the synthetic `delta` executor runs
   in a worker.
6. **Cross-host worker supervision.** Heartbeats, leases, worker registration,
   drain/replace across hosts, and a policy for timeout/retry ownership.
7. **Durable commit recovery.** Use the journal to resume or roll forward after
   a coordinator crash: prove which bundles committed, re-run missing effects,
   and reconcile the world revision.  The journal currently audits and replays;
   it does not recover a live coordinator.
8. **Delta merge ordering at scale.** Resolve parallel shard delta envelopes
   and apply them in commit order onto one canonical world; the primitive
   (`GraphDelta.apply_to`) exists, the coordinator merge/snapshot staging does
   not.
9. **Journal operations.** Rotation/retention/compression and a group-commit or
   WAL policy, since per-record `fsync` and full-file verification are audit
   costs today.

## Non-goals retained

- No Ocelot dependency.
- No change to serial defaults or world physics.
- No claim that the in-process partitioned executor is process or network
  distribution.
