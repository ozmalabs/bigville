# Engine speedups: batch rules, lazy snapshots, cheaper state reads

Status: active plan, 8 November 2026. This program targets the post-lazy
critical path: per-action world-rule sweeps, per-turn snapshot/report building,
and graph read overhead. It does **not** use Ocelot or any external engine.

## Why

The lazy-affordance default removed the exhaustive menu from the play path. A
profile of 50 residents, 2 turns now shows roughly:

- ~48% — `_apply_turn` → each action triggers a full `_run()` rule sweep;
- ~29% — `_finish_turn` → `snapshot()` / `export_state()` / `report()`;
- ~8% — lazy context/observation;
- ~17% — graph `node()` reads;
- ~11% — nearby/distance.

The menu is no longer the problem. The program must reduce repeated world-rule
work and stop computing data the caller does not read, without changing the
default simulation's meaning.

## Non-negotiable invariants

1. **One authoritative turn result.** A turn still advances exactly once, applies
   each actor's validated action, and produces the same `status`, `turn`,
   `results`, and refusal/error records.
2. **No hidden state divergence.** Optimised modes must either be equivalent to
   the legacy path or be explicit opt-in modes with their differences measured
   and documented. Never silently change default physics.
3. **Deterministic.** Scheduling, caches and batching must not depend on wall
   clock, thread completion order or dict insertion order.
4. **Checkpointable.** New derived caches and locks are excluded from
   checkpoints and rebuilt on restore. New world/game options are validated and
   recorded.
5. **No Ocelot dependency.** No generated graph, substrate, or external engine.
6. **Existing tests may not be weakened.** If a default changes, tests that
   specifically assert the old default are pinned explicitly; behavioural
   assertions stay intact.

## Phase plan

Each phase is implemented by one agent in this worktree, reviewed and committed
by the supervisor, with a report in `docs/phases/engine-speedups/ENxx_REPORT.md`.

### EN01 — Profiling harness and baseline

**Scope:** Make the current lazy default measurable in components, so later
phases can prove which change helped.

**Files:** `tools/profile_engine.py` (new), `tests/test_engine_speedups.py`
(new), report.

**Deliverables:**
- Import-safe builder plus CLI: `--size`, `--turns`, `--affordance-mode`,
  `--executor`, `--profile` (cProfile top functions).
- Per-turn breakdown: decision/context build, `world.tick`, action commit,
  `_finish_turn` (including snapshot/report), full `step`, and counts of
  `_run()` calls, `eng.node()` calls, `actors_near()` calls.
- Baseline table for 50/100 residents, 2-3 turns, lazy default and menu where
  useful; save a JSON/markdown artifact under `docs/phases/engine-speedups/`.
- Tests: builder import safety, component keys, `_run` count sanity.

**Gate:** targeted tests; baseline recorded.

### EN02 — Lazy snapshot and report

**Scope:** Stop building a full UI snapshot and report on every headless turn.
Keep the strict default available.

**Files:** `bigville/game.py`, `worlds/bigville_world.py`, `bigville/api.py`,
`tests/test_engine_snapshot.py` (new), report.

**Deliverables:**
- Add `snapshot_mode` (`"every_turn"` default, `"on_demand"` opt-in) and a
  `snapshot()`/`step(include_snapshot=...)` seam. In `on_demand`, `step()`
  returns `{"status", "turn", "results"}` (and any waiting fields) without a
  `"snapshot"` key; `game.snapshot()` builds one when asked.
- `world.export_state(include_report=False)` and `game.snapshot(include_report=...)`
  avoid `report()`/`report_history()` unless requested. The existing default
  `export_state()` keeps its current output.
- Add `snapshot_mode="auto"` if useful: on_demand for autonomous simple runs,
  every_turn otherwise. Decide from the evidence; do not change the default
  without recording it.
- Tests: on-demand step omits the snapshot and leaves no report work (spy);
  `game.snapshot()` still returns the full structure; default every_turn is
  unchanged; waiting/contest paths still carry their context; report on demand
  equals the old report.
- Measure before/after at 50/100 and record.

**Gate:** targeted tests; no default behaviour change unless `auto` is chosen
with evidence.

### EN03 — Turn-batched rule resolution

**Scope:** Stop running the full `_run()` sweep after every action. Batch the
world-rule passes once after the turn's actions, behind a validated
`rule_batching` option. Legacy action-level batching stays available.

**Files:** `worlds/bigville_world.py`, `bigville/game.py`, `bigville/api.py`,
`tests/test_engine_rule_batching.py` (new), report.

**Deliverables:**
- `rule_batching` in `{"action", "turn"}` (`"action"` default initially).
- A world re-entrant batch scope: while active, primitive `_run()` calls are
  deferred; the game enters it around the action commit loop and runs exactly
  one `world.resolve_actor_turn()`/`_run()` afterwards. Do not suppress the
  world tick's own rule passes.
- `world.tick()` and `_finish_turn()` must not double-run when the batch scope
  has already resolved.
- Audit the primitives that call `_run()` (movement, jobs, stock, tools,
  clothing, doors, etc.) and make the deferral explicit: a deferred call is not
  a silent no-op, it records that a full sweep is owed. Provide a debug
  assertion that the final sweep ran.
- Tests: `_run` call count per turn drops from O(actions) to a constant in turn
  mode; action/result/refusal records are still produced; the legacy mode is
  unchanged; a contest/joint turn, a job turn, a stock/decay turn and a
  body-stats turn are covered.
- **Equivalence/evaluation:** compare action mode vs turn mode on town100
  seeds 305000/305001 (8 turns) and the small scenario: applied actions,
  refusals, survival, health/hunger/energy, work/trade, and any divergence.
  Turn batching is allowed to be an opt-in semantics change if the divergence
  is measured; do not make it default in this phase.
- If turn batching proves too divergent, implement and record the narrower
  alternative: targeted per-actor rule passes (`_run_for(actor)`) for the
  primitives whose effects are actor-local. Do not leave the option half-applied.

**Gate:** targeted tests plus the comparison; evidence recorded.

### EN04 — Cheaper state reads

**Scope:** Reduce the graph and proximity overhead that remains after rule
batching. Default behaviour must be unchanged.

**Files:** `bigville/runtime.py`, `worlds/bigville_world.py`,
`bigville/game.py`, `tests/test_engine_reads.py` (new), report.

**Deliverables:**
- Fast read path on `BigvilleGraph`: avoid the global lock for reads in serial
  use, or make the lock no-op/fast when no concurrent writer exists; expose a
  direct attrs accessor for hot paths (`node_attrs`) without changing the public
  `node()` result.
- Reduce repeated `NodeRef(int(...))`/dict-wrapper work in the hottest rule and
  context paths measured by EN01.
- Cache per-turn derived reads where safe: `actors_near`/nearby residents,
  exhaustion band, effective stamina/body state, and similar values that are
  pure within a turn. Invalidate on mutation or bound the cache to a world
  revision/turn.
- Tests: serial/threaded graph safety still passes; cached reads equal
  uncached on mutation; menu/lazy traces unchanged; benchmark before/after.
- Do not add per-instance locks/objects that would fail checkpoint encoding;
  add any new derived field to `_EXTERNAL_FIELDS` or keep it module-level.

**Gate:** targeted tests including the tick-graph concurrency tests; measured
improvement recorded.

### EN05 — Evaluation, defaults and final report

**Scope:** Measure the combined result, choose defensible defaults for
autonomous simple runs, and close the program.

**Files:** `bigville/game.py`, `bigville/api.py`, `README.md`,
`docs/design/ENGINE_SPEEDUPS.md`, `docs/phases/engine-speedups/EN05_REPORT.md`,
`FINAL_REPORT.md`.

**Deliverables:**
- Combined benchmark 50/100/200 residents: baseline lazy, EN02 on_demand,
  EN03 turn batching, EN04 reads, and the combination. Report context, tick,
  commit, finish/snapshot, `_run` calls, node calls, wall time.
- Behaviour comparison for the same modes on town100 seeds 305000/305001 and
  the small scenario: applied/refused, survival, health/hunger/energy, work,
  trade, determinism (two runs equal).
- Choose defaults:
  - snapshot mode: on_demand is safe for headless autonomous simple runs if all
    in-tree consumers either request `game.snapshot()` explicitly or are
    already UI/API callers.
  - rule batching: turn mode becomes default only if the behaviour comparison
    is acceptable and the performance gain is clear; otherwise it stays opt-in
    and the next targeted-pass step is stated.
  - `create_game` may resolve `"auto"` modes by backend/session, mirroring the
    affordance-mode pattern; explicit values always win.
- Update README and final report. State what is default, what is opt-in, what
  remains, and the exact full-suite status.

**Gate:** targeted suites, self-test, and the full suite on an idle host; if the
full suite cannot finish, record the exact timeout/load rather than claiming a
pass.

## Status

| Phase | Status | Commit |
|---|---|---|
| EN01 | ready | — |
| EN02 | ready | — |
| EN03 | ready | — |
| EN04 | blocked on EN03 | — |
| EN05 | blocked on EN04 | — |

## Integration gates

After every phase:

```bash
python3 -m pytest -q tests/test_engine_*.py -p no:cacheprovider
python3 -m pytest -q tests/test_lazy_*.py tests/test_tick_snapshot.py \
  tests/test_tick_graph.py tests/test_phase055_concurrency.py -p no:cacheprovider
```

Before supervisor commits:

```bash
python3 domains/bigville_entities.py
```

Full suite is the final gate, not a per-phase gate.
