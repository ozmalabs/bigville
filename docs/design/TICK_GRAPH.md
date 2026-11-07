# Tick graph: equivalence-first concurrency and sharding

Status: active plan, 7 November 2026. This is an implementation plan for
converting Bigville's turn pipeline from "batch decisions, serial enactment"
into a declared tick graph that can commit independent effects concurrently and
later run sharded. The default behaviour must stay byte-for-byte equivalent to
the current engine.

## Why

Bigville already separates two ideas that are easy to conflate:

- **Decisions** are made against one world snapshot. Backends marked
  `concurrent` already decide in a thread pool (`bigville/concurrency.py`).
- **Enactment** is strictly ordered by `BigvilleGame.turn_order()`, a
  deterministic per-turn permutation (`bigville/game.py`).

The next step is to state, per effect, what it reads and writes, build a graph of
the turn, then commit non-conflicting effects concurrently while preserving the
existing order as a deterministic tie-break. That makes the pipeline shardable:
agents, world-rule passes and resource pools can live on different workers as
long as the same graph is rebuilt and reconciled per tick.

## Non-negotiable invariants

1. **Sequential equivalence.** With `turn_semantics="sequential"` (the default),
   the proposal, result, error, turn order and canonical world graph after every
   turn must match the pre-change engine.
2. **Deterministic reconciliation.** Every conflict is linearised by the existing
   `turn_order` permutation, extended by actor id. No scheduler timing may affect
   the result.
3. **Simultaneity is not blocked.** The operation model carries a read set, a
   write set and a conflict policy. A later phase can select
   `turn_semantics="simultaneous"` without rewriting the executor.
4. **No hidden global mutable state on an attempt.** `world._outcome_open`,
   `world._refusal_code` and `world._major_dispatch` must become per-attempt or
   per-actor before any parallel commit.
5. **No behaviour change outside a phase's stated scope.** Existing tests may not
   be weakened. Any changed numeric assertion is reported with its reason.

## Equivalence oracle

Each phase must compare against the same oracle:

- turn number and `turn_order`;
- every actor's proposed action and params, utterances, results and errors;
- continuation state;
- a SHA-256 of the canonical graph checkpoint (`eng.to_checkpoint_dict()`),
  reduced with sorted keys and a fixed encoder.

The oracle is built in TG01 and reused by every later phase. Test scenarios:
`town100` seed 305000, `resource_social_stress`, and a small deterministic
scenario. At least 8 turns per comparison, plus one 32-turn run before the final
integration commit.

## Phases

Phases run in order in this worktree. Each executor writes only its listed
files, adds tests, runs the targeted gates, and writes
`docs/phases/tick-graph/TGxx_REPORT.md`. The supervisor reviews, runs the full
gates, and commits; executors never commit.

### TG01 — Equivalence oracle and provenance trace

**Scope:** Add a pure trace/digest layer. No engine behaviour change.

**Files:** `bigville/tick_trace.py` (new), `tests/test_tick_trace.py` (new),
`docs/phases/tick-graph/TG01_REPORT.md`.

**Deliverables:**
- `step_trace(game)` records the turn, `last_order`, sorted proposals, results,
  errors, continuation requests and a canonical world checkpoint digest.
- `TurnTrace` appends records; `hexdigest()` hashes the sequence.
- `first_divergence(a, b)` returns the first turn and field that differ.
- Tests: two identical runs have the same digest; changing one proposal or one
  world fact changes it; divergence reports the right turn.

**Gate:** targeted tests pass; the trace can wrap `game.step()` without changing
any existing test.

### TG02 — Occupancy index (remove the O(N²) scan)

**Scope:** Maintain a cell → residents index alongside `_actor_positions` and
use it for nearby-resident, witness and distance filtering. Fall back safely if
the index is absent (old checkpoints).

**Files:** `worlds/bigville_world.py`, `bigville/game.py`,
`tests/test_tick_occupancy.py`, report.

**Deliverables:**
- Index updated at the single movement site (`_move_actor_to`) and for
  add/remove/death paths.
- `actors_near(position, radius)` helper returning sorted names.
- `BigvilleGame._context`, `_nearby_resident_ids`, `_apply_turn` witness scans
  and `_record_physical_changes` use the helper.
- Tests: index agrees with a brute-force scan across moves, deaths and spawns;
  8-turn trace digest unchanged on the standard scenarios.
- A micro-benchmark test or script records context-build time for 200 residents.

**Gate:** equivalence oracle unchanged; no linear scan over all actors remains in
the changed paths.

### TG03 — Frozen decision snapshot and parallel context construction

**Scope:** Build every deciding actor's context from one frozen snapshot, then
allow context construction itself to run in a pool in registration order. World
state must not be mutated between decision and enactment.

**Files:** `bigville/game.py`, `bigville/tick_trace.py` (snapshot support),
`tests/test_tick_snapshot.py`, report.

**Deliverables:**
- A `_DecisionSnapshot` captures turn, positions, attrs, calendar, affordances
  and index state for the decision phase.
- `_context(actor, snapshot=None)` reads the snapshot; `_published_practice`
  updates become a pre-pass over actors, not a side effect inside `_context`.
- `step()` builds contexts for all deciding actors before any `decide()` call;
  a pool may build them, but the result is consumed in registration order.
- A debug assertion (or explicit check) that the world graph is unchanged
  between the first and last context build.
- Tests: serial vs pooled context build produce identical `ActorContext` values
  and trace digests; practice records are unchanged.

**Gate:** equivalence oracle unchanged for all three scenarios.

### TG04 — Effect intents and the tick graph

**Scope:** Make enactment explicit. Define a pure `worlds/tick_graph.py` with
operations and conflict edges. The engine still applies effects in the old
serial order, but builds and validates the graph first.

**Files:** `worlds/tick_graph.py` (new), `bigville/game.py`,
`tests/test_tick_graph.py`, report.

**Deliverables:**
- `Resource`, `Operation` (op id, actor, kind, reads, writes, tiebreak),
  `TickGraph` with conflict detection and deterministic topological order.
- An action metadata table declaring the resources each verb touches (actor,
  cell, object, stock, container, building, utterance log, relationship, job).
- Contests, strikes, restraints, throws and joint acts are compound operations
  owning all participants and their shared resource.
- `build_tick_graph(order, responses, world)` for the current turn.
- Validation test: the graph's deterministic linearisation restricted to
  operations equals (or is compatible with) the existing `turn_order`, for
  several scenarios and seeds. Applying operations in graph order reproduces
  `last_results` exactly.
- The engine may keep calling `_apply_response` serially; the graph is built but
  not yet the executor.

**Gate:** equivalence oracle unchanged; graph-building can be disabled with a
constructor flag and adds no observable output.

### TG05 — Parallel commit of independent effects

**Scope:** Execute the TG04 graph with a ready-set scheduler. Default remains
serial; an opt-in `executor="threaded"` path may commit independent effects
concurrently. Conflicts, contests, joint acts and same-cell moves stay
serialised by the deterministic tie-break.

**Files:** `worlds/tick_graph.py`, `bigville/game.py`, `bigville/concurrency.py`,
`tests/test_tick_graph_executor.py`, report.

**Deliverables:**
- Per-attempt state (`_outcome_open`, `_refusal_code`, `_major_dispatch`) moved
  off the world instance or guarded by an attempt token.
- `TickExecutor` protocol: `serial` and `threaded` implementations returning
  results in deterministic graph order.
- Shard locks keyed by resource; independent operations run in a bounded pool.
- Equivalence tests: `serial` and `threaded` produce the same trace digest over
  the standard scenarios and seeds. A test forces a slow operation to prove
  actual overlap without changing results.
- A conflict test proves two moves into one cell and a take/strike pair are
  serialised, not raced.

**Gate:** equivalence oracle unchanged; threaded path is observationally
identical; single-thread default unchanged.

### TG06 — Simultaneous turn semantics (opt-in)

**Scope:** Add `turn_semantics="simultaneous"` as an explicit, non-default
option. All effects are validated and applied against the frozen snapshot, and
conflicts are resolved by the operation's conflict policy rather than by the old
application order.

**Files:** `bigville/game.py`, `bigville/api.py`, `worlds/tick_graph.py`,
`bigville/scenarios.py`, `tests/test_tick_simultaneous.py`, report.

**Deliverables:**
- Constructor/API option validated like `ticks_per_period`; unknown values fail.
- Simultaneous policy: independent writes commit together; conflicting writes
  use the documented tie-break (turn order, then actor id) or the existing
  contest resolution for take/strike/restrain/throw. Moves into one cell use the
  existing occupancy rule, never two winners.
- The sequential mode routes through the same graph but keeps today's order.
- Tests: simultaneous mode is deterministic across repeated runs and thread
  counts; sequential mode still matches the pre-change digest; a documented
  divergence test shows the two modes differ only where ordering was observable.
- Docs: semantics, guarantees and limits stated in this file and module docs.

**Gate:** full equivalence for sequential; deterministic simultaneity; no
existing test weakened.

### TG07 — Shardable executor, benchmark and integration report

**Scope:** Add the distribution seam without requiring a network deployment:
a `PartitionedExecutor` that assigns operations to in-process shards by
resource ownership, plus a benchmark and integration note.

**Files:** `bigville/sharding.py` (new), `worlds/tick_graph.py`,
`tools/benchmark_tick_graph.py` (new), `tests/test_tick_sharding.py`, report,
this plan's status table.

**Deliverables:**
- `ShardMap` maps cells, actors and resource pools to shard ids; cross-shard
  effects become coordinator operations at the barrier.
- `PartitionedExecutor` reproduces the sequential trace digest for the standard
  scenarios.
- Benchmark reports decisions, context build, world rules and commit times for
  50/100/200 residents and records the scaling curve.
- Integration report states what is ready for process/worker distribution and
  what still needs message transport, versioned shard snapshots and a durable
  tick log.

**Gate:** full suite and self-test pass; benchmark results recorded; no claim of
production distribution beyond what the tests prove.

## Status

| Phase | Status | Commit |
|---|---|---|
| TG01 | ready | — |
| TG02 | blocked on TG01 | — |
| TG03 | blocked on TG02 | — |
| TG04 | blocked on TG03 | — |
| TG05 | blocked on TG04 | — |
| TG06 | ready | — |
| TG07 | blocked on TG06 | — |

## Integration gates

Run after every phase:

```bash
python3 -m pytest -q tests/test_tick_*.py -p no:cacheprovider
python3 -m pytest -q tests/test_phase055_concurrency.py tests/test_phase047_joint_actions.py \
  tests/test_phase038_strikes.py tests/test_phase029_contest.py -p no:cacheprovider
```

Run before each supervisor commit:

```bash
python3 domains/bigville_entities.py
timeout 1500 python3 -m pytest -q -p no:cacheprovider
```
