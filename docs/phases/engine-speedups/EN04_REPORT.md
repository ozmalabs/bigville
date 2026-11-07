# EN04 — Cheaper state reads

Status: complete, 8 November 2026. Phase EN04 of
[`docs/design/ENGINE_SPEEDUPS.md`](../../design/ENGINE_SPEEDUPS.md).

- Base commit: `7f71fbf53faa43af890ef7fc7dc54f849f19b1be`
  (branch `engine-speedups`, EN03 applied; no EN04 changes).
- Host: contended Linux host, 16 CPUs, `uptime` load average `17.81 16.39
  16.63` during the paired measurements. A full suite was also active for part
  of the run. Absolute milliseconds are noisy; call counts, cProfile ratios and
  the direction of every component are the stable signals.
- Comparison scenario: `tools/profile_engine.py`,
  `tools.benchmark_tick_graph.build_scenario(size)`, 2 turns, seed 305000,
  `--affordance-mode lazy --rule-batching turn --snapshot-mode on_demand`,
  serial executor. The "before" column was produced from a pristine
  `git archive` copy of the base commit, alternating before/after runs on the
  same host (three pairs, medians below), not from pre-EN04 numbers recorded
  earlier.
- Default modes are unchanged: `rule_batching="action"`,
  `snapshot_mode="every_turn"`, and `affordance_mode` resolution are untouched.
  `BigvilleGame.executor="serial"` remains the default.

## What the post-EN03 profile showed

Fresh command:

```bash
python3 tools/profile_engine.py --size 50 --turns 2 --affordance-mode lazy \
  --rule-batching turn --snapshot-mode on_demand --profile --json
```

The first run on the untouched base gave 2,750,614 profiled calls and 1.482 s;
the paired run used for the table below gave 1.039 s. In both, observation —
not the rule sweep — was the dominant remaining cost:

| cumtime s | % of profiled | ncalls | function |
|---|---|---|---|
| 1.045 | 100% | 2 | `game.step` / `_step_deferred` |
| 0.505 | 49% | 2 | `_build_contexts` → `_context` → `_lazy_context` |
| 0.501 | 48% | 51 | `world.observe` |
| 0.334 | 32% | 51 | `_observe_work_candidates` |
| 0.180 | 17% | 2 | `_apply_turn` (commit) |
| 0.163 | 16% | 51 | `_observe_bulk_available` |
| 0.157 | 15% | 252 | `actors_near` |
| 0.111 | 11% | 561 | `recipe_preview` |
| 0.096 | 9% | 51 | `_observe_nearby_actors` |
| 0.084 | 8% | 53,284 | `BigvilleGraph.node` |

`_observe_work_candidates` was therefore the single largest self-contained
target: it called `_observe_bulk_available` for every actor (81 bulk kinds
times a full container/store scan) and `_known_recipe_names` twice per actor
(once in `observe`, once in the work list), and each preview repeated body and
skill read-offs. The graph used the process-wide RLock and allocated a fresh
`{"type", "attrs"}` wrapper on every one of 53k reads. `actors_near` was called
252 times per two turns, 50 of them only to count cell occupancy.

## Changes and safety bounds

### 1. Graph fast reads (`bigville/runtime.py`, `bigville/game.py`)

- `BigvilleGraph(lock_reads=True)` is the default and every constructor path,
  including `from_checkpoint_dict`, keeps it. Writes always take `_GRAPH_LOCK`.
- `node`, `node_attrs`, `has_node`, `nodes`, `has_edge`, `neighbours` and
  `in_neighbours` skip the lock only when `lock_reads` is false. They keep the
  historical `int()` coercion for non-int identifiers (the fast path works for
  ints and `NodeRef` directly because `NodeRef` equals and hashes as its int).
- `node_attrs(node)` returns the canonical attribute mapping without building
  the public wrapper; `node()` still returns `{"type", "attrs"}` with the same
  shape.
- `BigvilleGame.executor` sets the policy: `"serial"` disables read locking,
  `"threaded"` and `"partitioned"` keep it. **Invariant:** `lock_reads=False`
  is only valid when no thread may mutate the graph while readers run. Serial
  commits mutate on the caller's thread; the only other threads are context
  workers reading an asserted-frozen decision snapshot. A game changed to a
  concurrent executor re-enables the lock before its next commit. A direct
  caller may pass `lock_reads=False` only with the same guarantee.
- The flag is an instance attribute on the graph and is not part of the graph
  checkpoint, so a restored graph is always locked until a serial game applies
  its policy.

### 2. Proximity cache and occupancy (`worlds/bigville_world.py`)

- `BigvilleWorld.decision_reads()` is a re-entrant scope backed by a
  module-level `weakref.WeakKeyDictionary` (never checkpointed). While open,
  `actors_near` memoises the **unfiltered** row by
  `(position, radius, alive_only)`; `exclude` is applied to the returned copy.
- The game opens the scope for `_build_contexts` only. It closes before
  `world.tick()`, the action commit, witness/speech code and any after-state
  read. There is no movement counter to get wrong: a post-action proximity
  query is always computed from live positions. Nested scopes share the outer
  cache; the outermost exit discards it.
- `occupancy_at(cell)` reads the derived position bucket directly. It equals
  `len(actors_near(cell, 0, alive_only=False))` for a map cell, without the
  candidate scan, distance filter and sort, and returns 0 for a non-map cell
  exactly as the old proximity read did.
- `_ActorPositions.near` now scans occupied buckets when the Chebyshev square
  contains more cells than there are occupied buckets (the common radius-8
  case), and keeps the direct cell scan for small radii.

### 3. Observation/work-candidate caching (`worlds/bigville_world.py`, `bigville/game.py`)

Static pack-derived data is cached per world in a module-level weak map,
explicitly invalidated by `_install_item` / `_install_recipe` (and therefore
`add_recipe`):

- common recipe names and the small uncommon set (the base loop tested a
  `knows` edge for all 166 recipes; only 7 are uncommon in this pack);
- the set of bulk-input kinds used by `_observe_bulk_available`;
- the town store's lock node.

The frozen-snapshot scope additionally memoises, per actor (or actor+recipe /
actor+skill), with copies returned to callers:

- `_known_recipe_names`;
- `_observe_bulk_available` (sources are hoisted once instead of rescanning
  containers and the store lock per kind);
- `_observe_work_candidates` (busy is checked before the cache, so a post-action
  observation of a now-busy actor still returns `[]`);
- `recipe_preview`;
- `body_state`, `_exhaustion_band`, `effective_stamina`, `effective_skill`.

No cache is written outside the decision scope. Nothing can be stale after an
action because the scope has already closed; the only mutation inside it is a
programming error already guarded by `_assert_decision_snapshot_unchanged`.

## Tests

```bash
python3 -m pytest -q tests/test_engine_reads.py tests/test_engine_rule_batching.py \
  tests/test_engine_snapshot.py tests/test_engine_speedups.py -p no:cacheprovider
# 47 passed in 3.02s

python3 -m pytest -q tests/test_tick_graph.py tests/test_tick_graph_executor.py \
  tests/test_tick_occupancy.py tests/test_lazy_*.py -p no:cacheprovider
# 146 passed, 1 skipped in 194.46s

python3 -m pytest -q tests/test_phase055_concurrency.py tests/test_phase029_contest.py \
  tests/test_bigville_world_persistence.py -p no:cacheprovider
# 36 passed, 1 failed in 53.92s
# Failure is the pre-existing timing threshold in
# test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical
# (ratio 0.79, required < 0.75). It reproduces unchanged on a pristine
# git archive of base commit 7f71fbf (ratio 0.79, 1 failed in 24.64s), so it is
# host-load timing, not an EN04 regression.

python3 domains/bigville_entities.py
# ERRORS (0), WARNINGS (0), INFO (95)
```

`tests/test_engine_reads.py` (10 tests) covers:

- locked and fast graph reads give exactly the same `node`, `node_attrs`,
  `nodes`, `has_edge`, `neighbours` and `in_neighbours` results, including the
  historical `int()` coercion and the unchanged public shape;
- a 1,500-node writer runs concurrently with readers on a locked graph;
- a graph checkpoint round-trips and a restored graph is locked;
- a serial game has `lock_reads=False`, threaded/partitioned (via the executor
  setter) has `True`, and a threaded turn advances with no pending sweep;
- two context workers share the frozen read scope;
- cached `actors_near` equals a brute-force query and equals the uncached path
  after a move, a spawn and a death; the cache is gone outside the scope;
- `occupancy_at` equals `actors_near(..., 0, alive_only=False)`, including a
  dead resident;
- `observe` inside the scope equals an uncached reference, and two actors do
  not receive each other's nearby rows;
- an observation/body cache does not survive a hunger or stamina mutation;
- decision caches add no instance fields to the world, so they are not
  checkpoint state;
- cached `work_candidates` equal the menu's work filter (first 16 sorted) and
  every published recipe previews ok.

Behavioural equivalence was also checked externally against the base commit:
six-turn small-room and four-turn town100 runs, in both `action` and `turn`
rule-batching modes, produced identical `step_semantic_trace` digests for every
turn and identical final `export_state` digests.

## Measurements

Three alternating before/after pairs, 2 turns, per-turn medians. `node/turn`
is `BigvilleGraph.node()` as counted by the harness; the total graph reads
column adds `node_attrs()` (the harness does not wrap it, so it was counted by
a separate two-turn run).

| size | mode | step ms | context ms | commit ms | finish ms | world tick ms | other ms | `node`/turn | total graph reads/turn | `actors_near`/turn | `_run`/turn |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | before | 185.6 | 85.3 | 16.8 | 18.6 | 6.3 | 58.5 | 26,642 | 26,642 | 126 | 3 |
| 50 | after | 113.9 | 30.7 | 13.2 | 10.5 | 4.0 | 52.1 | 10,737 | 20,929 | 100.5 | 3 |
| 100 | before | 471.2 | 211.0 | 50.1 | 54.1 | 11.5 | 148.0 | 69,902 | 69,902 | 253 | 3 |
| 100 | after | 293.4 | 75.4 | 29.0 | 38.3 | 7.1 | 147.5 | 31,117 | 58,361 | 201.5 | 3 |

Delta (after vs before):

| size | step | context | commit | finish | world tick | `node` calls | total graph reads | `actors_near` calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | −38.6% | −64.0% | −21.4% | −43.6% | −36.3% | −59.7% | −21.4% | −20.2% |
| 100 | −37.7% | −64.3% | −42.2% | −29.2% | −38.5% | −55.5% | −16.5% | −20.4% |

`_run` stays at 3 per turn in turn mode and `applied` stays at 50/100, as it
must. The `commit`, `finish`, `world tick` and `other` reductions are smaller
and noisier than the context reduction; only the context and graph-read
reductions are large enough to quote confidently under load ~17. The commit and
finish drops are consistent with the graph fast path (both phases read state
heavily) but were not isolated in a separate run.

### What gave which delta

- **Static recipe/bulk data + hoisted bulk sources** — the largest single win.
  cProfile `_observe_bulk_available` fell 0.163 → 0.026 s and
  `_observe_work_candidates` 0.334 → 0.090 s on the same 2-turn profile.
  `_known_recipe_names` no longer performs ~166 `has_edge` reads per call.
- **`node_attrs` + serial read fast path** — `BigvilleGraph.node` cumtime fell
  0.084 → 0.016 s while `node_attrs` costs 0.010 s for 20,384 calls; total graph
  reads fell 21%/16.5% and `node()` calls fell 60%/55%. The 80,291 RLock
  `__exit__` calls in the base profile disappear from the top 100.
- **Observation/body/skill memoisation** — `recipe_preview` fell 0.111 → 0.042 s
  and `effective_skill` 561 calls now cost 0.008 s. The per-actor work and known
  lists are computed once per frozen snapshot.
- **Occupancy bucket + occupied-bucket proximity scan** — `actors_near` calls
  fell 20% (the per-`observe` occupancy query is gone) and its cProfile cumtime
  fell 0.157 → 0.103 s.
- **Proximity memoisation itself** produced no measurable win in this scenario,
  because each resident queries a distinct position inside the frozen snapshot.
  It is retained as the required safe reuse point for repeated identical
  queries and for future multi-consumer observation paths; the tests prove it
  equals the uncached result and cannot outlive the scope.

### cProfile top functions, same command

| rank | before (base `7f71fbf`) | after |
|---|---|---|
| 1 | `game.step` 1.045 s | `game.step` 0.777 s |
| 2 | `_build_contexts` 0.505 s | `cheap.decide` 0.306 s |
| 3 | `world.observe` 0.501 s | `_build_contexts` 0.198 s |
| 4 | `_observe_work_candidates` 0.334 s | `world.observe` 0.195 s |
| 5 | `cheap.decide` 0.272 s | `psi_can.choose` 0.197 s |
| 6 | `_apply_turn` 0.180 s | `_apply_turn` 0.150 s |
| 7 | `_observe_bulk_available` 0.163 s | `_observe_work_candidates` 0.090 s |
| 8 | `actors_near` 0.157 s | `actors_near` 0.094 s (201 calls) |
| 9 | `recipe_preview` 0.111 s | `_observe_nearby_actors` 0.068 s |
| 10 | `BigvilleGraph.node` 0.084 s (53,284) | `recipe_preview` 0.042 s |

Profiled calls fell from 1,532,474 to 1,130,402 over the same two turns.

## Limitations

- Measurements are single-host and in-process under load ~17 with a full suite
  active. Absolute milliseconds are indicative; call counts and cProfile
  cumtimes are the reliable comparison. Re-measure on an idle host in EN05.
- In this benchmark the second turn builds only one context because nearly every
  resident is on an uninterrupted continuation; `context_ms` in the table is a
  per-turn average over one expensive decision turn and one cheap turn. The
  cProfile numbers (51 contexts over two turns) are the cleaner measure of the
  observation path.
- The proximity/work/body caches are bound to the frozen decision scope, not
  to a movement counter. That is deliberate: it makes post-action witness and
  after-state reads trivially safe, but it also means the commit-phase
  `_activate_continuation` proximity query is always recomputed. A movement-
  revision cache could reuse more, at the cost of proving every mutation path
  invalidates it; that was not worth the risk in this phase.
- `_static_reads` is invalidated by recipe/item installation and keyed on the
  table sizes. Direct mutation of `_recipe_specs`/`_item_specs` behind the
  install methods would leave it stale; no in-tree caller does that.
- `node_attrs` returns the canonical mutable attribute mapping, exactly as
  `node()["attrs"]` already did. It is a read convenience, not a copy.
- The graph fast path is only as safe as its caller. The game enforces the
  serial/no-concurrent-writer rule through the executor setter, but a direct
  `BigvilleGraph(lock_reads=False)` user takes the same responsibility.
- Backend valuation (`psi_can.choose`, 0.197 s / 26% of the after profile),
  remaining proximity scans and movement routing are now the largest measured
  items and were out of EN04's read-cache scope.

## EN05 recommendation

1. Keep the serial graph fast path and `node_attrs`; they are mechanical,
   covered by the locked/fast equivalence test and the tick-graph concurrency
   suite, and cannot change results.
2. Keep the decision-scope caches; they are scoped to the frozen snapshot, so
   they do not constrain the snapshot/rule-batching default decisions.
3. Re-run the 50/100/200 table on an idle host before choosing defaults. On
   this load the combination of EN02 `on_demand` + EN03 `turn` + EN04 reads is
   about 39% faster per turn at 50 and 38% at 100 than EN03 alone in the same
   scenario.
4. For the next read phase, target backend valuation/scoring and the
   `_apply_turn` path (movement routing, preference scoring), not observation:
   observation fell from ~49% to ~25% of the profiled step and the remaining
   `observe` cost is mostly the nearby-proximity scan.
5. Do not make the proximity cache survive the decision scope without a
   movement/death revision counter and tests on every mutation path. The current
   scope boundary is the defensible safety bound.
