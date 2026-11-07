# EN01 — Profiling harness and baseline

Status: complete, 8 November 2026. Phase EN01 of
[`docs/design/ENGINE_SPEEDUPS.md`](../../design/ENGINE_SPEEDUPS.md).

- Base commit: `90c07675c989f86c537316a6f78b361ffe048e93`
  (branch `engine-speedups`, before EN01 changes).
- Host: contended Linux host; `/proc/loadavg` was `16.16 14.78 12.30` before the
  baseline run. Absolute milliseconds therefore carry load noise; ratios and
  call counts are the stable signal. Re-run on an idle host before quoting
  small (<5%) differences.
- Scenario: `tools.benchmark_tick_graph.build_scenario(size)` — deterministic
  grid town, one `simple`-backed resident per cell, physical subsystems off.
  Nobody is an LLM; no external model or network call is made.

## Harness design

`tools/profile_engine.py` is import-safe: importing it only defines the
scenario builder, timers, `run_one`, `profile_run`, `profile`, `markdown_table`
and `main`; no game is built and no benchmark runs. The repository root is
added to `sys.path` so `python3 tools/profile_engine.py` works from the root.

Measured components (all `time.perf_counter`, construction excluded):

| name | wrapped method | scope |
|---|---|---|
| `step` | measured around `game.step()` | whole turn |
| `context` | `game._build_contexts` | frozen decision snapshot + contexts |
| `world_tick` | `world.tick` | includes both internal `_run()` passes |
| `commit_total` | `game._apply_turn` | serial commit **including** `finish` |
| `commit` | derived `commit_total - finish` | action commit without finish |
| `finish` | `game._finish_turn` | bookkeeping, report and snapshot |
| `snapshot` | `game.snapshot` | **subset of `finish`**, not additive |
| `other` | derived `step - context - world_tick - commit_total` | decisions, ordering, tick graph, joint resolution, animal turn, timer overhead |

Accounting rule: one timer per distinct method, each wrapped with
`functools.wraps` and returning the original value. Nested timers are
cumulative, so `finish ⊆ commit_total ⊆ step` and `snapshot ⊆ finish`. The
harness reports `commit_excluding_finish` so the components add up:

```
step = context + world_tick + commit_excluding_finish + finish + other
```

`finish` includes `snapshot`; `snapshot` is shown separately and must never be
added to the total. `other` is a residual rather than an instrumented phase:
it contains backend `decide()` time, turn ordering, tick-graph construction,
joint resolution, `animal_turn`, and the small overhead of the wrappers
themselves.

Counts are per-turn deltas of calls made during the turn:

- `world._run` calls — full rule sweeps (the EN03 target);
- `eng.node` calls — graph reads through `BigvilleGraph.node` (the EN04 target);
- `world.actors_near` calls — proximity scans (also EN04);
- `proposed` / `applied` — responses carrying a major action, and truthy
  `game.last_results` entries.

`--profile` builds a **fresh** game for the same size/turns and runs cProfile on
`game.step()` only, so the profiled call counts are not polluted by the
component wrappers. It prints the top 35 functions by cumulative time (tunable
with `--profile-limit` and `--profile-size`).

CLI: `--size` (default 50), `--sizes` (comma list, overrides `--size`),
`--turns` (default 2), `--seed` (default 305000), `--affordance-mode`
(`lazy` default, `menu` allowed), `--executor` (`serial` default, `threaded`,
`partitioned`), `--profile`, `--json` (JSON only; the default prints JSON and
the markdown table), `--time-budget`.

## Baseline

Command actually run (load caveat above):

```bash
python3 tools/profile_engine.py --sizes 50,100 --turns 2 --affordance-mode lazy \
  > /tmp/en01_lazy.txt
python3 tools/profile_engine.py --sizes 50,100 --turns 2 --affordance-mode lazy \
  --json > docs/phases/engine-speedups/baseline.json
python3 tools/profile_engine.py --size 50 --turns 2 --affordance-mode lazy \
  --profile --json > /tmp/en01_profile.txt
```

The full per-turn JSON is in
[`baseline.json`](baseline.json). The measured run (second command) gave:

| size | mode | turns | step ms/turn | context ms | world tick ms | commit ms | finish ms | snapshot ms (subset) | other ms | _run/turn | node/turn | near/turn | applied/turn |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 50 | lazy | 2/2 | 320.317 | 67.451 | 5.593 | 129.773 | 60.438 | 47.065 | 57.062 | 53.0 | 94154.0 | 126.0 | 50.0 |
| 100 | lazy | 2/2 | 966.002 | 175.806 | 10.714 | 516.937 | 118.369 | 73.812 | 144.174 | 103.0 | 309188.5 | 253.0 | 100.0 |

Share of total `step` time in the same run:

| size | context | world tick | commit excl. finish | finish | snapshot (inside finish) | other |
|---|---|---|---|---|---|---|
| 50 | 21.1% | 1.7% | 40.5% | 18.9% | 14.7% | 17.8% |
| 100 | 18.2% | 1.1% | 53.5% | 12.3% | 7.6% | 14.9% |

Turn totals (2 turns per size, seconds): size 50 — step 0.641, context 0.135,
world tick 0.011, commit total 0.380 (commit excl. finish 0.260, finish 0.121,
snapshot 0.094), other 0.114, 106 `_run`, 188,308 `node`, 252 `actors_near`,
100 proposed/applied. Size 100 — step 1.932, context 0.352, world tick 0.021,
commit total 1.271 (commit excl. finish 1.034, finish 0.237, snapshot 0.148),
other 0.288, 206 `_run`, 618,377 `node`, 506 `actors_near`, 200 proposed/applied.

Per-turn `_run` count is `actions + 3` in this scenario: 50 actions + two
`world.tick` passes + one `world.resolve_actor_turn()` in `_finish_turn` for
size 50; 100 actions + 3 for size 100. That linear-in-actions scaling is the
EN03 target. `applied/turn` equals the resident count: every simple backend
proposed and had an action applied.

Run-to-run noise is visible: an earlier identical run gave 333.5 ms/turn for
size 50 and 975.5 ms/turn for size 100. Treat differences below roughly 10% at
this load as noise.

## Profile highlights

`python3 tools/profile_engine.py --size 50 --turns 2 --affordance-mode lazy
--profile --json`, 2 turns, 2,750,614 calls, 1.482 s profiled:

| cumtime s | % of profiled | ncalls | function |
|---|---|---|---|
| 1.487 | 100% | 2 | `game.py:1237(step)` / `_step_deferred` |
| 0.845 | 57% | 2 | `game.py:1474(_apply_turn)` |
| 0.552 | 37% | 100 | `game.py:1107(_apply_response_contained)` |
| 0.551 | 37% | 100 | `bigville_world.py:9095(enact_plan)` |
| 0.537 | 36% | 100 | `bigville_world.py:2431(move_actor)` |
| 0.503 | 34% | 106 | `bigville_world.py:1353(_run)` |
| 0.343 | 23% | 2 | `game.py:1192(_build_contexts)` |
| 0.341 | 23% | 51 | `bigville_world.py:8926(observe)` |
| 0.291 | 20% | 2 | `game.py:1823(_finish_turn)` |
| 0.220 | 15% | 2 | `game.py:1986(snapshot)` |
| 0.205 | 14% | 2 | `bigville_world.py:9460(export_state)` |
| 0.197 | 13% | 188,308 | `runtime.py:137(node)` |
| 0.126 | 8% | 2 | `worlds/bigville_world.py:2125(report)` |
| 0.115 | 8% | 252 | `bigville_world.py:2339(actors_near)` |
| 0.141 | 10% | 51 | `bigville/backends/psi_can.py:150(choose)` |
| 0.219 | 15% | 51 | `bigville/backends/cheap.py:176(decide)` |

What the profile says for the later phases:

- `_run()` is 34% of profiled time with only 106 calls; it is reached from
  action enactment (`_claimed_attempt` → `_walked_toward` → `move_actor` →
  `_run`) as well as from `world.tick`, so the action-level sweep is the
  dominant EN03 target.
- `snapshot`/`export_state`/`report` cost 0.205–0.220 s over 2 turns (about
  three quarters of `finish`), the EN02 target.
- `eng.node` is called 188,308 times (about 94k per turn, ~2.3 per resident
  action-plus-context) and 13% of profiled time; `actors_near` is 8%. These are
  the EN04 targets.
- Lazy context is 23% (`_build_contexts` → `observe`), mostly
  `_observe_work_candidates` (0.224 s); it is not the menu any more.

## Tests

```bash
python3 -m pytest -q tests/test_engine_speedups.py -p no:cacheprovider
```

Result: 5 passed in 0.41 s. Coverage:

- importing `tools.profile_engine` does not call `bigville.api.create_game`
  (monkeypatched to raise) and exposes the builder entry points;
- `build_scenario(5)` is a plain dictionary with five simple residents and
  physical subsystems off;
- a size-5 one-turn run returns every component key with non-negative values,
  `_run`/`node`/`actors_near` counts > 0, and only subset sanity
  (`step ≥ context`, `step ≥ commit_total`, `commit_total ≥ finish ≥ snapshot`)
  rather than a tight additive assertion;
- wrapping a real game advances exactly one world turn, and every timer records
  at least one call while `snapshot` remains exactly one;
- the markdown table names the components and the size.

## Limitations

- This is a local, in-process, single-host measurement. It excludes game
  construction but includes Python interpretation, GC and wrapper overhead.
- The timer wrappers add per-call overhead to `_build_contexts`, `world.tick`,
  `_apply_turn`, `_finish_turn`, `snapshot`, `_run`, `eng.node` and
  `actors_near`. The relative comparison across phases is valid because the
  same wrappers are reused, but absolute values are not directly comparable to
  `benchmark_tick_graph.py`.
- The residual `other` is not a measured phase; it absorbs backend decision
  time and any uninstrumented work.
- The scenario disables physical subsystems, has no buildings/laws/policies,
  and uses only simple backends. It measures engine mechanics, not LLM or
  menu-mode play. A menu run is supported by `--affordance-mode menu` but was
  not part of this baseline.
- Host load was high (load average ~16); absolute milliseconds vary run to run.
- Concurrency executors (`threaded`, `partitioned`) are accepted but were not
  baselined here; their `_apply_turn` path also calls `_finish_turn`, so the
  accounting still holds.

## Handoff

- **EN02 (lazy snapshot/report):** target `finish` and its `snapshot` subset.
  Baseline `finish` is 60–118 ms/turn and `snapshot` 47–74 ms/turn (13–19% of
  `step`). Re-run the same command with the new mode and compare `finish_ms`,
  `snapshot_ms`, `node/turn` and `_run/turn`; expect `finish` to fall while
  `commit`/context stay flat.
- **EN03 (turn-batched rules):** target `_run/turn`. Baseline is
  `actions + 3` (53 at size 50, 103 at size 100). The gate should show a
  constant per turn while `applied/turn` and the applied/refusal records stay
  equal. `world_tick` (5–11 ms/turn) is small here; do not optimize it away.
- **EN04 (cheaper reads):** target `node/turn` (94k–155k) and `near/turn`
  (126–253) without changing context or menu/lazy traces. `eng.node` is 13%
  of profiled time; `actors_near` 8%. Keep the serial/threaded graph tests
  green.
- **EN05:** use `per_turn.step_ms`, the component split and the three call
  counts from `baseline.json` as the like-for-like comparison. Re-run both
  sizes on an idle host for the final report and state the load.
