# DR05 — Integration, overhead and final gate

Status: complete (uncommitted), 8 November 2026. Final phase of
[`docs/design/DISTRIBUTED_RUNTIME.md`](../../design/DISTRIBUTED_RUNTIME.md).

- Base commit: `ef1baf9` on branch `distributed-runtime` (DR04).
- Changed files: `tools/verify_bundle_equivalence.py`, `README.md`,
  `docs/design/DISTRIBUTED_RUNTIME.md` (status table), this report and
  `FINAL_REPORT.md`.
- New file: `tests/test_distributed_runtime.py`.
- No production executor, world physics, checkpoint or default path changed.
  The only production-adjacent change is the verification tool.

## What was integrated

`tools/verify_bundle_equivalence.py` keeps its serial / partitioned / replay
matrix and adds three opt-in scopes.  With none of the new flags the default
seeds, turns, checksum comparison, JSON output and exit code are unchanged.

| Flag | What it proves |
|---|---|
| `--journal PATH` | The partitioned game runs with `bundle_log_path`; after every turn the tool reads, replays and verifies the journal and compares the replayed tick log, execution checksum and payload checksum with `game.last_bundle_log`. |
| `--deltas` | Every partitioned result's effects are rebuilt with `GraphDelta.from_effects`, JSON round-tripped through `to_dict`/`from_dict`, and checked against the bundle base, result base and committed ack. A turn whose graph revision advanced must have at least one bundle with effects. |
| `--process` | A couple of serialized bundles are dispatched through `ProcessBundleTransport` with the synthetic `delta` executor, duplicated from a fresh JSON round trip, acknowledged, replayed and closed. Stable output/execution checksums and one execution per bundle id are asserted. |

Journal path rule: one journal has one writer, so with several seeds the path
gets a `.<seed>` component (`dr05_bundle.305000.jsonl`); with one seed the given
path is used exactly.  A stale file at that path is replaced at the start of the
run.  Process-worker startup is the only skippable part: if no worker can start,
the seed reports `process.skipped` instead of failing.

Per seed/turn the report now records payload equality, execution stability,
serial/partitioned/replay revision equality, journal replay equality, delta
presence and bundle/result/ack/commit completeness.  A seed is `ok` only when
every requested scope passed.

## Seed matrix

Command (the `--process` smoke was included):

```bash
python3 tools/verify_bundle_equivalence.py \
  --seeds 305000,305002,305004,305006 --turns 8 \
  --journal /tmp/opencode/dr05_bundle.jsonl --deltas --process --json
```

Result: exit 0, `ok=true`, 2m19.5s.  Menu affordance, `town100`, one bundle per
turn, all serial/partitioned/replay comparisons equal.

| Seed | Turns | Bundles | Payload equal | Execution stable | Revision equal | Journal replay | Journal bytes | Delta effects | Process smoke |
|---|---:|---:|---|---|---|---|---:|---:|---|
| 305000 | 8 | 8 | yes | yes | yes | yes | 2,381,817 | 16,397 | pass (2 bundles, fork) |
| 305002 | 8 | 8 | yes | yes | yes | yes | 2,392,640 | 16,527 | pass (2 bundles, fork) |
| 305004 | 8 | 8 | yes | yes | yes | yes | 2,375,126 | 16,634 | pass (2 bundles, fork) |
| 305006 | 8 | 8 | yes | yes | yes | yes | 2,361,397 | 16,405 | pass (2 bundles, fork) |

The exact gate command without `--process` also exited 0 in 2m17.7s with all
four seeds reporting `payload_equal`, `execution_stable`,
`revision_equal`, `journal.replay_equal` and `deltas.ok` true.

Lazy seed (`--seeds 305002 --turns 8 --affordance-mode lazy --deltas
--process --journal /tmp/opencode/dr05_lazy.jsonl`) exited 0 in 30.0s: 13
bundles over 8 turns, payload/execution/revision equal, journal replayed to the
live log, 16,416 delta effects, 2,408,658 journal bytes, process smoke passed.

## Overhead

Setup: `town100`, seed `305000`, `executor_workers=4`, lazy affordances,
`snapshot_mode="on_demand"`, 4 turns, one bundle per turn.  Host was **not**
idle: 16 cores, load average 5.4-6.2, and an unrelated `python main.py
--virtual-only` process was using roughly 250% CPU during the run.  Treat the
absolute milliseconds as noisy and the relative shape as indicative.

| Variant | turn 1 | turn 2 | turn 3 | turn 4 | mean | Journal |
|---|---:|---:|---:|---:|---:|---:|
| Serial baseline | 507.5 ms | 739.1 ms | 125.0 ms | 83.0 ms | **363.6 ms** | — |
| Partitioned, no journal | 867.3 ms | 1090.5 ms | 475.0 ms | 307.3 ms | **685.0 ms** | — |
| Partitioned + journal | 907.2 ms | 1153.8 ms | 541.2 ms | 382.7 ms | **746.2 ms** | 1,245,816 B |
| Partitioned + journal + delta verify | 958.2 ms | 1263.8 ms | 533.7 ms | 394.7 ms | **787.6 ms** | 1,245,816 B |

- Journal writing adds about **61 ms/turn** over partitioned in this run
  (per-record `fsync`, as measured in DR02).
- Adding delta reconstruction/round-trip verification on top adds about
  **41 ms/turn**.
- The journal held 24 records (4 ticks, 4 bundles) in 1.25 MB, about
  **311 KB/turn**.  That is roughly 3x the DR02 size because results now carry
  the full effect delta.
- The separate journal verify/replay pass cost **852.9 ms/turn** (journal) and
  **889.7 ms/turn** (journal+delta), growing from 406 ms to 1.3 s as the file
  grew.  Verification re-reads and re-hashes the whole journal each turn; it is
  an audit cost, not a production per-turn cost.

## Tests

```text
python3 -m pytest -q tests/test_distributed_runtime.py -p no:cacheprovider
5 passed in 1.67s

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
```

`tests/test_distributed_runtime.py` covers:

- six-turn serial vs partitioned payload/semantic/revision equality, complete
  dispatch/result/ack/commit coverage, committed acks and monotonic revisions;
- a three-turn partitioned journal that verifies, replays every tick to the
  recorded live log and matches the final `last_bundle_log` and payload hash;
- serial turns leaving no journal file even when a path is configured;
- a node-creating bundle turn whose effects rebuild a JSON-round-tripped
  `GraphDelta` with a consistent base/end envelope;
- a real process worker dispatch with a one-shot timeout/retry, stable
  checksums, duplicate-dispatch idempotence, ack/replay, clean close and
  post-close rejection.

Runtime of the new file is under 2 seconds; the full targeted gates above are
under two minutes each.

## Full-suite status

**No full-suite run was completed in this phase, and no full-suite pass is
claimed.**  The gate instruction for this worktree was to use targeted tests
while another suite/workload may be active.  The host confirmed contention
(load average 5.38-6.23 on 16 cores; an unrelated `python main.py
--virtual-only` at ~250% CPU), so a full-suite result would not have been a
clean idle-host measurement.  The three targeted gates above, the verification
tool matrix and the domain self-test all completed successfully.

## Limitations

- The runtime is still **local-only**: no network/socket transport,
  authentication, broker, backpressure or cross-host supervision.
- Journal replay can audit and reconstruct tick logs, but there is no durable
  commit-recovery procedure that resumes a crashed coordinator into its world.
- `BundleResult` still carries only the bundle base.  The tool uses the
  committed ack as the end-revision bound for delta round trips; an authoritative
  per-result end revision is not shipped.
- Multi-bundle turns are checked per result; the tool does not merge every
  shard delta into one full-world replay (parallel shard deltas may interleave
  revision envelopes).  `GraphDelta.apply_to` remains the same-base replay
  primitive.
- The process smoke uses the synthetic `delta` worker and the first two
  serialized bundles of a seed, not the live world.  The live-world worker and
  snapshot shipping remain unimplemented.
- Journal verification is O(file) per call and was run every turn for the
  integration proof; production would verify at commit/close boundaries.
- The journal has a documented single writer; the tool therefore derives a
  per-seed file when several seeds are verified together.
- Timings include host contention and are not a benchmark.

## Handoff

The program closes with [`FINAL_REPORT.md`](FINAL_REPORT.md), which lists what
DR01-DR05 delivered and the exact remaining work for remote distribution.
