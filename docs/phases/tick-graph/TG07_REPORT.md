# TG07 — Shardable executor, benchmark and integration note

Base commit: `a82a52e` (TG06: opt-in simultaneous item-claim reconciliation)

No file was staged or committed. The pre-existing untracked `.opencode/`
directory was not touched.

## Scope and files

TG07 adds an in-process sharding seam. It does **not** add process, worker
process, socket or durable-log distribution. Every shard runs as a thread
inside one Python process and shares one live `BigvilleWorld`.

Files changed:

- `bigville/sharding.py` (new) — `ShardMap`, `ShardPlan`, `partition_units`,
  `PartitionedExecutor`.
- `bigville/game.py` — `"partitioned"` executor routing and
  `_apply_turn_partitioned`; serial and threaded paths unchanged.
- `tools/benchmark_tick_graph.py` (new) — synthetic grid benchmark and JSON /
  markdown output.
- `tests/test_tick_sharding.py` (new) — 15 tests.
- `docs/phases/tick-graph/TG07_REPORT.md` (this report).
- `docs/design/TICK_GRAPH.md` — status rows TG01–TG07.

## Shard design

### `ShardMap(cell_size=8, coordinator=0)`

- `cell_shard(cell)` uses `floor(x / cell_size)` and
  `floor(y / cell_size)`, mixes the two block indices with fixed integer
  constants (not salted `hash()`), and returns `1 + (mixed & 0x7FFFFFFF)`.
  The `1 +` keeps the coordinator id `0` free. Negative coordinates use
  `math.floor`, so `(-1, -1)` and `(-8, -8)` share the correct block.
- `actor_shard(actor, world)` reads `world.actor_position(actor)`; an absent or
  unknown actor is the coordinator.
- `resource_shard(resource, world)` maps `actor` resources through
  `actor_shard`, `cell` resources through `cell_shard`, and **every other
  resource kind** (`stock`, `container`, `item`, `building`, `job`,
  `relationship`, `utterance`, `memory`, `world`, `witness`, ...) to the
  coordinator. This is deliberately conservative: an undeclared or
  non-spatial effect is serialised rather than raced.
- `unit_shards` and `is_cross_shard` expose the set view used by planning.

### `partition_units(units, world, shard_map=None)`

`units` is `{actor: resources}`. The plan:

- emits every actor exactly once, grouped by shard;
- sorts actors lexicographically inside a shard, so a plain dictionary's
  insertion order cannot change the plan;
- places a unit at the coordinator when its resources span more than one shard
  (`cross_shard`), when it owns a coordinator resource, or when it declares no
  resource at all;
- reports `cross_shard` (only units that actually span shards) separately from
  `coordinator_units` (the full coordinator-barrier set);
- `to_dict()` gives a stable JSON-friendly view for a future wire protocol.

### `PartitionedExecutor(shard_map=None, workers=None)`

- `plan(units, world)` is the pure assignment step.
- `commit(game, order, responses, suppressed=None, plan=None)`:
  1. derives actor units with `game._unit_resources`, widening empty units and
     global writers to `Resource("world", "global")`;
  2. runs cross-shard/coordinator units first, serially, in turn order;
  3. turns every remaining shard into one component of `order` indices and
     calls the TG05 seam `game._run_component(order, responses, component,
     suppressed)` — one worker per shard, bounded by `workers` or the shard
     count;
  4. returns `{actor: (actor, result, error)}` rebuilt in turn order.
- The executor owns no result/error dictionaries. `_apply_turn_partitioned`
  writes `last_results` / `last_errors` exactly like
  `_apply_turn_threaded`, and calls `_finish_turn` once.

### `BigvilleGame` routing

`_EXECUTORS` now contains `serial`, `threaded` and `partitioned`; `serial`
remains the default. `_threaded_eligible` and `_partitioned_eligible` share
`_concurrent_commit_eligible`, which keeps the TG05 restrictions:

- `start == 0` (a resumed turn stays serial);
- `last_tick_graph is not None`;
- no `take`/`strike`/`restrain`/`throw` contest in the turn.

If any restriction fails, the historical serial loop runs. Joint members are
skipped at commit, as in TG05. TG06 suppression passes through unchanged.
`last_shard_plan` is an observational attribute set only on a partitioned turn;
it is not checkpointed.

## What is ready for process/worker distribution

- A deterministic, world-independent ownership function (`ShardMap`) with a
  plain `to_dict()`.
- A deterministic plan (`ShardPlan`) with `by_shard`, `cross_shard` and
  `coordinator_units`, and a conservative cross-shard barrier.
- Unit resource sets are `Resource` values (hashable, `to_dict()`-serialisable),
  so a future scheduler can ship them to workers.
- The commit seam is already a plain `(game, order, responses, component,
  suppressed)` call returning plain `(actor, result, error)` tuples.
- Semantic equivalence is guarded by `step_semantic_trace`, and the shard
  planner is covered by pure unit tests plus an actual-overlap test.

## What still needs work before real distribution

1. **Message transport.** There is no IPC. Shards share one live world object;
   a process split needs request/response messages for units, suppression,
   contest actions and results, plus a timeout/retry policy.
2. **Versioned shard snapshots.** A worker cannot read the coordinator's live
   world safely. Each shard needs an immutable, versioned read snapshot (the
   TG03 `_DecisionSnapshot` is a starting point) and a declared base version
   for every write.
3. **Durable tick log.** There is no write-ahead or commit log, no replay and no
   crash recovery. A distributed commit needs a durable, ordered record of
   applied effects and of every coordinator decision.
4. **Claim resolution at the barrier.** TG06 item claims are resolved in the
   coordinator before either commit path; a real scheduler must keep that step
   at the barrier and broadcast winners/losers to shard workers.
5. **Failure and lifecycle handling.** A worker exception is contained per
   actor today; there is no shard failure detection, cancellation or
   reassignment.
6. **Consistent global side effects.** Speech delivery, witness records and
   world-rule sweeps read global state. TG05's conservative global override
   keeps them ordered; a distributed design must make those reads explicit
   resources or route them to the coordinator.

## Benchmark

Command (from the repository root):

```bash
python3 tools/benchmark_tick_graph.py --sizes 50,100,200 --turns 2 --progress
```

Scenario: `build_scenario(n)` places `n` simple-backed residents one per cell
on the smallest square grid, seed `305000`, physical subsystems off. Each
`(size, executor)` cell builds a fresh game (construction excluded) and runs two
turns. Timing wrappers:

- `context_ms` — `BigvilleGame._build_contexts`;
- `world_tick_ms` — `BigvilleWorld.tick`;
- `commit_ms` — `BigvilleGame._apply_turn`;
- `ms/turn` — the whole `BigvilleGame.step()`.

All values below are the actual JSON output of one uninterrupted run; the
`context`, `world tick` and `commit` columns are totals over the two turns.

| size | executor | turns | ms/turn | context ms | world tick ms | commit ms | shards | coordinator | cross-shard | note |
|---|---|---|---|---|---|---|---|---|---|---|
| 50 | serial | 2/2 | 480.158 | 867.547 | 6.235 | 80.376 | — | — | — | |
| 50 | threaded | 2/2 | 463.157 | 833.646 | 6.341 | 80.356 | — | — | — | |
| 50 | partitioned | 2/2 | 464.002 | 832.430 | 6.295 | 82.557 | 2 | 4 | 4 | |
| 100 | serial | 2/2 | 992.839 | 1829.676 | 11.707 | 125.067 | — | — | — | |
| 100 | threaded | 2/2 | 1000.931 | 1848.230 | 14.903 | 116.775 | — | — | — | |
| 100 | partitioned | 2/2 | 1008.199 | 1870.300 | 11.605 | 115.907 | 5 | 9 | 9 | |
| 200 | serial | 2/2 | 2351.174 | 4401.748 | 24.621 | 214.717 | — | — | — | |
| 200 | threaded | 2/2 | 2368.081 | 4441.210 | 28.346 | 195.624 | — | — | — | |
| 200 | partitioned | 2/2 | 2406.045 | 4514.552 | 29.240 | 194.916 | 5 | 18 | 18 | |

`shards` includes the coordinator shard. For example at 200 residents:
5 shards total, 182 actors in four spatial shards and 18 coordinator units
(cross-shard movers plus global/speech units).

### Reading the numbers honestly

- **Context construction dominates**: 87–94% of step time. Sharding the commit
  cannot move the total much.
- **Partitioned is not faster in this grid benchmark.** The commit total is
  within roughly ±5% of serial at every size, and `ms/turn` is 0–2% slower at
  100/200. Graph planning and the extra coordinator pass cost about as much as
  any overlap saves.
- **The default `cell_size=8` makes ordinary movement cross-shard.** A `move`
  unit declares its actor, source cell and destination cell. In a synthetic
  town where every resident moves each turn, a step from one 8×8 block into
  another spans two shards and is forced to the coordinator. At 200 residents
  only 18 units were coordinator-bound in the measured turns, so the map is not
  degenerate, but the remaining shards are not CPU-bound enough for threading
  to help: GIL-bound pure-Python world work does not overlap well.
- Larger `cell_size` would reduce cross-shard moves; that is a tuning knob, not
  a correctness change. The benchmark always uses the default map.

These are measurements of a local, single-process scaffold. They are not a
scaling claim.

## Tests

`tests/test_tick_sharding.py` — 15 tests:

1. `ShardMap` cell shards deterministic for positive, negative and edge cells;
   adjacent blocks differ, the coordinator id stays free.
2. actor mapping uses position; absent actors go to the coordinator.
3. resource kind mapping (`actor`, `cell` spatial; all other kinds coordinator).
4. `unit_shards` / `is_cross_shard`.
5. `partition_units` puts every actor exactly once and forces non-spatial units
   to the coordinator.
6. far-apart actors land in different shards.
7. a non-spatial resource forces the coordinator barrier.
8. the plan is independent of dict insertion order.
9. `ShardPlan` stable view and `to_dict`.
10. serial vs partitioned semantic trace over 4 turns on `town100` seed 305000
    and the TG01 small room; two serial and two partitioned runs, with digest,
    semantic state, order, results and errors compared.
11. a contest turn falls back to the serial loop under
    `executor="partitioned"`, recording no shard plan.
12. a forced cross-shard unit (Ada's unit gains a cell in another block) still
    produces serial-identical results and is listed at the coordinator.
13. `PartitionedExecutor.commit` returns only the completed actor map.
14. a sleep-wrapped `_apply_response_contained` proves far-apart resting units
    actually overlap in shard workers (serial max 1, partitioned max > 1).
15. `tools/benchmark_tick_graph.build_scenario` is importable and side-effect
    free.

## Commands and results

```bash
python3 -m py_compile bigville/sharding.py bigville/game.py \
  tools/benchmark_tick_graph.py tests/test_tick_sharding.py
# OK

python3 -m pytest -q tests/test_tick_sharding.py -p no:cacheprovider
# 15 passed in 42.02s

python3 -m pytest -q tests/test_tick_sharding.py tests/test_tick_simultaneous.py \
  tests/test_tick_graph_executor.py tests/test_tick_graph.py -p no:cacheprovider
# 56 passed in 98.98s (0:01:38)

python3 -m pytest -q tests/test_phase055_concurrency.py tests/test_phase029_contest.py \
  tests/test_phase038_strikes.py tests/test_phase047_joint_actions.py -p no:cacheprovider
# 81 passed in 54.50s

python3 domains/bigville_entities.py
# consistency report: ERRORS (0), WARNINGS (0); production graph acyclic after
# condensing loops: True

python3 tools/benchmark_tick_graph.py --sizes 50,100,200 --turns 2 --progress
# exit 0; results in the table above
```

## Known limitations

- **In-process only.** Every shard shares one `BigvilleGame` and one
  `BigvilleWorld`. There is no isolation, no serialisation of world state, no
  process boundary and no network. The name "partitioned" describes the
  scheduling seam, not a deployment.
- **Conservative coordinator fallback.** All non-`actor`/`cell` resource kinds,
  empty units and global writers go to the coordinator. A stock-, item- or
  container-heavy turn is therefore serial even when the actors are far apart.
- **Cell-block granularity.** A move whose source and destination fall in
  different 8-cell blocks is cross-shard. Long moves and every actor that walks
  across a block boundary run at the barrier.
- **No measured speed-up.** The benchmark shows commit times within noise of
  serial, and total step time slightly worse for partitioned at 100/200. The
  phase delivers a correct seam and a harness, not a performance win.
- **No rollback.** If a shard worker fails after a partial world write, the
  per-actor exception containment records a failure but does not undo effects.
- **Inherited TG05 scheduling limits.** The scheduler trusts the TG04 resource
  table; speech and witness effects are conservative global units; per-observer
  event ordering is protected but not proven identical when independent units
  witness the same observer. Partitioned turns use the same assumptions.
- **Semantic, not byte identity.** As in TG05, node ids and some log insertion
  orders may differ from serial. Equivalence is asserted on
  `step_semantic_trace`, never on raw graph node ids.
- **Two-turn benchmark.** The design document asks for one 32-turn run before
  the final integration commit. This phase ran 4-turn equivalence tests and a
  2-turn benchmark; the 32-turn run remains a supervisor/final-gate step.
- **No API change needed.** `create_game(executor=...)` already passes the
  string through; `"partitioned"` is accepted by the same validator. The option
  is not separately surfaced in the TUI or server command line.

## Supervisor follow-up (8-turn replay)

`tools/verify_tick_equivalence.py --turns 8 --scenario town100 --affordance-mode menu`
matched serial and threaded but found the first partitioned divergence at turn 6 in
`world_sha256` (proposals, results, order, errors and continuations still identical).
The four-turn equivalence test did not reach it. Partitioned scheduling is therefore a
known limitation rather than a proven-equivalent executor; the default executor remains
serial. The next hypothesis is an under-declared same-cell/terrain movement resource (or
the coordinator-first ordering) in the partitioned path.
