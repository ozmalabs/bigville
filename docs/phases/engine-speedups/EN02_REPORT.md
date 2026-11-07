# EN02 — Lazy snapshot and report

Status: complete, 8 November 2026. Phase EN02 of
[`docs/design/ENGINE_SPEEDUPS.md`](../../design/ENGINE_SPEEDUPS.md).

- Base commit: `85d89a1ca748d84ec5d3120e835cbfa5c98ab781`
  (branch `engine-speedups`, EN01 applied; no EN02 changes).
- Host: contended Linux host; `/proc/loadavg` was `30.12 19.00 14.50` before the
  first measurement and `30.79–32.19` during the repeat. A full suite was also
  active. Absolute milliseconds are therefore noisy; the stable signal is that
  `snapshot()` is not called at all in `on_demand`, so its cost disappears from
  `finish`.
- Scenario for every number: `tools/profile_engine.py`,
  `tools.benchmark_tick_graph.build_scenario(size)`, 2 turns, seed 305000,
  `--affordance-mode lazy`, serial executor, physical subsystems off.

## Mode and split design

### `snapshot_mode`

`BigvilleGame` and `create_game` now accept `snapshot_mode`:

| requested value | resolved `snapshot_mode` | `step()` result |
|---|---|---|
| `"every_turn"` (default) | `every_turn` | includes `"snapshot"`, exactly as before |
| `"on_demand"` | `on_demand` | no `"snapshot"` key; caller asks `game.snapshot()` |
| `"auto"` | `on_demand` for an autonomous session whose backends are all built-in cheap/simple; `every_turn` for a player, LLM, Ocelot or other backend | follows the resolved value |

- `snapshot_mode_requested` keeps the caller's value; `snapshot_mode` reports
  the resolved value. `resolve_snapshot_mode()` is idempotent and uses the same
  backend rule as the LA08 affordance auto mode (`_auto_resolves_lazy`).
- `set_backend()` re-resolves an `"auto"` snapshot mode, exactly as it already
  re-resolves an `"auto"` affordance mode, so injecting a foreign backend after
  construction moves the session back to `every_turn`.
- `create_game` defaults to `"every_turn"`. The default is deliberately **not**
  changed in this phase; `"auto"` is available but opt-in.
- Invalid values raise `ValueError` in the setter/constructor.
- `step(include_snapshot=None)` is a one-call override: `True` always builds the
  snapshot, `False` never does, `None` follows the resolved mode. The override
  is threaded through the inline/deferred decision paths, the serial/threaded/
  partitioned commit paths and `_resume_suspended`, so a resumed contest uses
  the current call's choice.

### `_finish_turn`

The only changed finish work is the final result construction:

```python
result = {"status": "advanced", "turn": ..., "results": ...}
if include_snapshot:
    result["snapshot"] = self.snapshot()
return result
```

Rule resolution, map-memory learning, event expiry, period changes, continuation
activation and all waiting/contest paths are unchanged. In `on_demand` a normal
turn returns exactly `{"status", "turn", "results"}`; a waiting turn still
returns its existing `context`/`affordances` (and `reaction` for a contest) and
never built a snapshot in the first place.

### `snapshot()` / `export_state()` split

- `BigvilleGame.snapshot(include_report=True)` keeps the historical output by
  default. `snapshot(include_report=False)` calls
  `world.export_state(event_tail=100, include_report=False)` and still returns
  `schema`, `player`, `world`, `characters`, `held_state` and `continuations`.
- `BigvilleWorld.export_state(include_report=True)` keeps the no-argument
  output and values exactly (`report` and `report_history` are still present and
  equal `world.report()` / `world.report_history()`).
  `include_report=False` omits those two derived keys; the canonical world data
  (`residents`, `map`, `stocks`, `events`, `sanity`, …) is unchanged. A caller
  that wants only the report can call `world.report()` directly.
- An `on_demand` turn is cheaper than `snapshot(include_report=False)` because it
  builds no snapshot at all; the explicit partial snapshot is still available
  to UI/debug callers.

### Harness

`tools/profile_engine.py` gained `--snapshot-mode {every_turn,on_demand,auto}`
(default `every_turn`), threaded through `build_game`, `run_one`, `profile_run`,
`profile` and the JSON output; the markdown table shows the snapshot mode.
Existing harness tests and defaults are unchanged.

## Tests

```bash
python3 -m pytest -q tests/test_engine_snapshot.py tests/test_engine_speedups.py -p no:cacheprovider
# 22 passed in 2.08 s

python3 -m pytest -q tests/test_lazy_default.py tests/test_bigville_game_api.py tests/test_simple_life.py -p no:cacheprovider
# 58 passed, 1 skipped in 28.39 s

python3 -m pytest -q tests/test_bigville_reporting.py tests/test_bigville_scenarios.py tests/test_tick_snapshot.py -p no:cacheprovider
# 18 passed in 87.70 s (extra regression check for export/snapshot consumers)

python3 domains/bigville_entities.py
# ERRORS (0), WARNINGS (0)
```

`tests/test_engine_snapshot.py` (17 tests) covers:

- `every_turn` default: `step()` includes a snapshot with
  `schema`/`world`/`characters`/`held_state`/`continuations`, and it equals
  `game.snapshot()`;
- `on_demand`: `step()` has no `"snapshot"` and returns only
  `status`/`turn`/`results`; spies prove `world.report` and
  `world.report_history` are not called; `game.snapshot()` still produces the
  full snapshot;
- a spy on `game.snapshot` proves the on-demand turn does not even call the
  snapshot method;
- `step(include_snapshot=True)` on an `on_demand` game includes a snapshot and
  `step(include_snapshot=False)` on an `every_turn` game omits it;
- `snapshot(include_report=False)` and `export_state(include_report=False)`
  skip report work and keep the core structure, while the no-argument
  `export_state()` keeps the old shape and report values;
- a human waiting result and a contested-reaction waiting result both return
  `context`/`affordances` (and `reaction`) with no snapshot and no report work,
  and the resumed contest is also snapshot-free in `on_demand`;
- the `auto` matrix: autonomous simple → `on_demand`; player / LLM /
  Ocelot-like backend → `every_turn`; explicit values win; invalid values raise.

## Measurements

Command (repeated for each mode and then once more for a second sample):

```bash
python3 tools/profile_engine.py --sizes 50,100 --turns 2 \
  --affordance-mode lazy --snapshot-mode every_turn
python3 tools/profile_engine.py --sizes 50,100 --turns 2 \
  --affordance-mode lazy --snapshot-mode on_demand
```

Per-turn values from the first pair (load average 30.12 before the run):

| size | mode | step ms | context ms | world tick ms | commit ms | finish ms | snapshot ms | other ms | `_run`/turn | node/turn |
|---|---|---|---|---|---|---|---|---|---|---|
| 50 | every_turn | 631.159 | 138.254 | 10.188 | 288.466 | 101.680 | 80.865 | 92.570 | 53.0 | 94,154.0 |
| 50 | on_demand | 491.231 | 128.364 | 10.060 | 245.865 | 27.149 | 0.000 | 79.792 | 53.0 | 88,467.0 |
| 100 | every_turn | 1,618.023 | 290.846 | 15.374 | 912.191 | 192.189 | 110.318 | 207.423 | 103.0 | 309,188.5 |
| 100 | on_demand | 1,543.070 | 306.990 | 16.540 | 899.527 | 69.488 | 0.000 | 250.525 | 103.0 | 298,551.5 |

Repeat pair (load average 30.79–32.19, different order):

| size | mode | step ms | context ms | commit ms | finish ms | snapshot ms |
|---|---|---|---|---|---|---|
| 50 | every_turn | 535.089 | 114.847 | 244.370 | 95.550 | 73.877 |
| 50 | on_demand | 480.207 | 126.055 | 245.838 | 24.465 | 0.000 |
| 100 | every_turn | 1,638.746 | 332.539 | 875.155 | 191.400 | 117.645 |
| 100 | on_demand | 1,474.578 | 326.678 | 847.935 | 82.165 | 0.000 |

What is stable across the two samples:

- `snapshot()` is not called in `on_demand`, so per-turn snapshot cost falls to
  exactly 0 and `finish` falls from 95.6–101.7 ms to 24.5–27.1 ms at size 50
  (about 73–74%) and from 191.4–192.2 ms to 69.5–82.2 ms at size 100 (about
  57–64%). The remaining `finish` is the rule resolution, map-memory, event
  expiry, period and continuation bookkeeping, not snapshot/report.
- Node reads fall by roughly 6% at 50 and 3–4% at 100 because `export_state`
  no longer walks residents, stocks, events and objects for the report.
- `_run`/turn is unchanged at `actions + 3` (53 / 103), as expected: EN03 owns
  rule batching.
- Total `step` time falls in both samples, but by an amount that is hard to
  separate from the very noisy context/commit components at load ~30. The
  repeat pair (10% lower `step` at both sizes) is the more credible total.

## Limitations

- No default behaviour changed: `every_turn` is still the default, so the
  speedup is opt-in until EN05 decides whether headless autonomous simple runs
  should use `"on_demand"` or `"auto"` by default.
- An in-tree consumer that reads `step()["snapshot"]` keeps working under the
  default. A consumer that explicitly selects `on_demand` or `auto` must call
  `game.snapshot()` (or `world.report()`) when it needs the snapshot/report.
- `snapshot(include_report=False)` and `export_state(include_report=False)`
  omit the `report`/`report_history` keys rather than returning `None`; this is
  documented on both methods and the default no-argument forms are unchanged.
- The measurements are in-process, single-host and were taken under heavy
  external load with a full suite active. Absolute values are not a clean
  benchmark; ratios should be re-measured on an idle host for EN05.
- Only the micro-scenario harness was measured (`simple` backends, physical
  subsystems off). Player, LLM and menu-mode snapshot consumers were covered by
  tests but not benchmarked.

## Handoff to EN03

- Benchmark headless turns with `--snapshot-mode on_demand` from now on: `finish`
  is then bookkeeping-only (24–82 ms at these sizes), so EN03's `_run` changes
  are not hidden behind snapshot/report noise.
- Target `_run`/turn, which is unchanged at `actions + 3` (53 at size 50, 103 at
  size 100). Keep `applied/turn` at 50/100 and the applied/refusal records equal
  when batching.
- Keep `every_turn` as the default until EN05; use the `auto` matrix here as the
  existing precedent for resolving a new mode by session/backend.
- `tools/profile_engine.py` now records `snapshot_mode` in its JSON and table;
  carry that field into the EN05 combined benchmark so the comparison states
  which snapshot mode each row used.
