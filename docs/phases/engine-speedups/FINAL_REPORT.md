# Engine speedups — final report

Status: program complete in the worktree, 8 November 2026. Plan:
[`docs/design/ENGINE_SPEEDUPS.md`](../../design/ENGINE_SPEEDUPS.md). Phase
reports: [EN01](EN01_REPORT.md), [EN02](EN02_REPORT.md), [EN03](EN03_REPORT.md),
[EN04](EN04_REPORT.md), [EN05](EN05_REPORT.md).

## What changed

| phase | commit | change | measured effect |
|---|---|---|---|
| EN01 | `85d89a1` | import-safe engine profiling harness, component split and call counts | baseline recorded; per-turn `_run` was actions+3, node reads 94k/155k at 50/100 |
| EN02 | `44f3fb1` | `snapshot_mode` (`every_turn`/`on_demand`/`auto`), `snapshot(include_report=...)`, report-free headless turns | snapshot cost 0 in on_demand; `finish` −47% to −84%; node reads −2% to −7% |
| EN03 | `7f71fbf` | `rule_batching` (`action`/`turn`), one authoritative finish sweep, re-entrant world batch scope | `_run`/turn actions+3 → 3; commit excluding finish −89% to −93%; step −35% to −58% |
| EN04 | `a724d65` | serial graph fast reads, `node_attrs`, decision-scope proximity/observation/body caches, occupancy buckets | step −32% to −40%; context −57% to −62%; node calls −55% to −60%; `actors_near` −20% |
| EN05 | uncommitted | combined evaluation; `create_game` auto defaults for snapshot and rule batching; rule-batching auto resolution; docs and final report | new vs legacy: step −55%/−55%/−66%, wall −55%/−40%/−55% at 50/100/200 |

## Measured speedups

Same host, same scenario (`tools/profile_engine.py`, synthetic simple town,
2 turns, seed 305000, serial executor, physical subsystems off). Legacy is
`affordance_mode="lazy"`, `snapshot_mode="every_turn"`,
`rule_batching="action"`; new is lazy/on_demand/turn.

| size | step ms legacy | step ms new | step delta | wall s legacy | wall s new | wall delta | `_run`/turn | node/turn |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 221.819 | 100.359 | −54.8% | 0.784 | 0.357 | −54.5% | 53 → 3 | 49,499 → 10,737 |
| 100 | 609.915 | 273.546 | −55.2% | 1.633 | 0.979 | −40.0% | 103 → 3 | 177,904 → 31,117 |
| 200 | 2,093.626 | 703.920 | −66.4% | 5.024 | 2.279 | −54.6% | 203 → 3 | 655,313 → 82,476 |

The EN04 read delta was isolated against a pristine `git archive` of the EN03
base `7f71fbf` under the same combined modes: step −39.7%/−32.1%/−39.1%,
context −56.9%/−61.6%/−60.2%, node reads −59.7%/−55.5%/−59.1% and
`actors_near` −20.2%/−20.4%/−20.2% at 50/100/200.

Indicative cumulative comparison against the EN01 baseline (lazy/every_turn/
action; recorded under similar heavy external load, 50/100 only): per-turn step
fell from 320.317 to 100.359 ms at 50 (3.2×) and from 966.002 to 273.546 ms at
100 (3.5×). Host load and load-dependent context/commit noise make this
indicative rather than a controlled end-to-end benchmark; the same-host
legacy-vs-new rows above are the defensible comparison.

All measurements were taken under external load (load average roughly 14–16)
with unrelated full suites running on the host. Absolute milliseconds are
noisy; call counts and the direction of every component are stable, and the
behaviour comparison is exact.

## New defaults

`create_game` now resolves all three session options by backend:

| session | affordance | snapshot | rule batching |
|---|---|---|---|
| autonomous simple/cheap | lazy | on_demand | turn |
| player | menu | every_turn | action |
| LLM | menu | every_turn | action |
| Ocelot/human/other | menu | every_turn | action |
| explicit value | explicit | explicit | explicit |
| direct `BigvilleGame(world)` | menu | every_turn | action |

- `affordance_mode="auto"` was already the `create_game` default from LA08.
- `snapshot_mode="auto"` is now the `create_game` default; it resolves to
  on_demand for the headless simple/cheap session and every_turn otherwise.
- `rule_batching="auto"` is new; it resolves to turn for the same session and
  action otherwise. A direct `BigvilleGame` still defaults to action.
- Each mode exposes `<mode>_requested` and its resolved property, and
  `set_backend()` re-resolves all three auto modes.
- On demand callers that need UI state call `game.snapshot()`;
  `bigville/server.py` and `bigville/management/runs.py` already do.

Behaviour was compared on `town100` seeds 305000/305001 (8 turns) and the
12-turn small room, new defaults versus explicit legacy: applied/refused,
survival, health/hunger/energy, work, handovers/trade, improvised jobs and
accidents were identical per turn, and two new-default runs produced identical
step records and final state digests. No material divergence was observed, so
the defaults were adopted.

## Still opt-in

- `rule_batching="action"` for simple/cheap sessions that depend on intra-turn
  read-offs. Turn batching is an ordering change by construction; the evaluated
  move/work/rest scenarios did not exercise every recipe, container, clothing,
  tool or combat permutation.
- `snapshot_mode="every_turn"` for callers that read `step()["snapshot"]`
  directly instead of calling `game.snapshot()`.
- `affordance_mode="menu"` for action pickers, Ocelot's adapter, debugging and
  equivalence oracles.
- The historical modes remain the direct-constructor defaults, so code that
  builds `BigvilleGame` directly is unchanged.
- Concurrent executors remain non-default (`serial` is the default). The
  partitioned-executor divergence recorded by the lazy-affordances program is
  independent of these defaults and still open.

## What did not change

- World physics, the one-authoritative-turn rule, action validation/refusals,
  scheduling order, continuations, contests, joint actions, animals, persistence
  and checkpoint shape.
- The serial executor remains the default; `threaded`/`partitioned` keep the
  locked graph read path.
- Player, LLM and Ocelot sessions keep menu/every_turn/action and the full
  per-turn snapshot.
- The world snapshot and report are still available on demand, with the same
  shape and values as before.
- Checkpoints reject an open rule batch; batch/pending flags remain ephemeral
  and are not persisted.

## Tests and gate status

EN05 targeted results:

- `tests/test_engine_*.py tests/test_lazy_*.py` — 178 passed, 1 skipped.
- `tests/test_tick_graph.py tests/test_tick_graph_executor.py
  tests/test_tick_occupancy.py tests/test_tick_snapshot.py` — 40 passed.
- `tests/test_bigville_game_api.py tests/test_simple_life.py
  tests/test_fix_simple_village.py tests/test_bigville_scenarios.py
  tests/test_scenario_runner.py` — 63 passed.
- `tests/test_phase055_concurrency.py tests/test_phase029_contest.py
  tests/test_phase047_joint_actions.py tests/test_bigville_world_persistence.py`
  — 68 passed, 1 known host-load timing failure (concurrency speedup ratio 0.81
  vs the required <0.75). The same failure reproduces on pristine base commits
  in the EN03/EN04 reports.
- `tests/management` (extra, because management runs exercise the new
  snapshot/rule defaults) — 164 passed, 1 browser start-up race that passed when
  rerun in isolation.
- `python3 domains/bigville_entities.py` — 0 errors, 0 warnings, 95 info.
- New `tests/test_engine_defaults.py` — 17 passed; covers the full resolution
  matrix, re-resolution, idempotence, validation, the two-turn headless/batched
  run, and the explicit legacy path.

The full suite did not complete in this worktree and **no full-suite pass is
claimed**. Unrelated full suites were active on the host during the work
(`/tmp/p045` and an xdist run), so the full suite remains the supervisor's final
gate on an idle host.

## Next steps

1. Run the full suite on an idle host and record the exact result.
2. Target backend valuation/scoring (`psi_can.choose`) and the remaining
   proximity/movement routing, which are now the largest measured items.
3. Resolve the partitioned-executor divergence (first observed in the semantic
   world hash with identical proposals/results); it is a tick-graph scheduling
   follow-up, not an ENGINE_SPEEDUPS default.
4. If turn batching is later proposed for player/LLM sessions, audit intra-turn
   read-off consumers first (instant `do` sharing inputs, containers, tool
   wear, clothing/exposure, contest stamina).
