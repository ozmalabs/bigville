# EN05 — Evaluation, defaults and final report

Status: implemented, uncommitted, 8 November 2026. Phase EN05 of
[`docs/design/ENGINE_SPEEDUPS.md`](../../design/ENGINE_SPEEDUPS.md).

- Base commit: `a724d65` (branch `engine-speedups`, EN01–EN04 applied).
- Host: contended Linux host, 16 CPUs. `/proc/loadavg` was
  `13.74 16.10 16.31` before the combined benchmark and `14.79 16.16 16.33`
  after it. Unrelated pytest suites were active on the host throughout; no full
  suite in this worktree was run (see “Full-suite status”). Absolute
  milliseconds are noisy; call counts, the component direction and the
  same-host legacy-vs-new comparison are the stable signals.
- Scenario for every performance number:
  `tools/profile_engine.py` / `tools.benchmark_tick_graph.build_scenario(size)`,
  2 turns, seed 305000, autonomous `simple` residents, serial executor,
  physical subsystems off.

## What changed

### `rule_batching="auto"`

`rule_batching` now accepts `"action"`, `"turn"` and `"auto"`.

- A direct `BigvilleGame` constructor still defaults to `"action"`.
- `create_game` defaults to `"auto"`.
- `"auto"` resolves to `"turn"` for an autonomous session with no player whose
  backends are all built-in cheap/simple, and to `"action"` for a player, LLM,
  Ocelot, human or any other backend.
- The resolution reuses the existing LA08 `_auto_resolves_lazy()` predicate
  that already drives affordance and snapshot auto modes. It is deterministic
  and idempotent.
- `set_backend()` re-resolves an auto rule-batching request, and
  `create_game()` resolves again after assigning the scenario's real backends.
- `game.rule_batching_requested` keeps the caller's value;
  `game.rule_batching` reports `"action"` or `"turn"`.

### Snapshot default

- `BigvilleGame` still defaults to `"every_turn"`.
- `create_game` now defaults to `"auto"` (it already supported it). Auto
  resolves to `"on_demand"` for the same autonomous simple/cheap session and
  `"every_turn"` otherwise. The post-backend resolution in `create_game` was
  already present and is still called.

### Resolution matrix

| session | affordance_mode | snapshot_mode | rule_batching |
|---|---|---|---|
| direct `BigvilleGame(world)` | menu | every_turn | action |
| `create_game`, autonomous simple/cheap | lazy | on_demand | turn |
| `create_game`, player | menu | every_turn | action |
| `create_game`, LLM | menu | every_turn | action |
| `create_game`, Ocelot/other/human backend | menu | every_turn | action |
| explicit `"menu"` / `"every_turn"` / `"action"` | explicit wins | explicit wins | explicit wins |
| explicit `"lazy"` / `"on_demand"` / `"turn"` | explicit wins | explicit wins | explicit wins |

Every auto mode is re-resolved by `set_backend()`; injecting an LLM/Ocelot/human
backend moves all three back to the historical path, and injecting a simple
backend moves them back to the headless path.

## Combined benchmark

Equivalent commands (the table was produced by a local script calling
`tools.profile_engine.run_one(...)` for each configuration):

```bash
python3 tools/profile_engine.py --sizes 50,100,200 --turns 2 \
  --affordance-mode lazy --snapshot-mode every_turn --rule-batching action
python3 tools/profile_engine.py --sizes 50,100,200 --turns 2 \
  --affordance-mode lazy --snapshot-mode on_demand --rule-batching action
python3 tools/profile_engine.py --sizes 50,100,200 --turns 2 \
  --affordance-mode lazy --snapshot-mode every_turn --rule-batching turn
python3 tools/profile_engine.py --sizes 50,100,200 --turns 2 \
  --affordance-mode lazy --snapshot-mode on_demand --rule-batching turn
```

Per-turn values, one sample per row. `snapshot key` says whether `step()`
carried the full snapshot; `snapshot ms` is a subset of `finish`, not additive.
`wall s` is the two-turn step loop, construction excluded.

| size | config | step ms | context ms | world tick ms | commit ms | finish ms | snapshot ms | other ms | `_run`/turn | node/turn | near/turn | applied/turn | snapshot key | wall s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| 50 | legacy (`every_turn`/`action`) | 221.819 | 27.646 | 3.280 | 89.199 | 58.063 | 47.633 | 43.629 | 53.0 | 49,498.5 | 100.5 | 50.0 | yes | 0.784 |
| 50 | EN02 (`on_demand`/`action`) | 181.837 | 26.209 | 3.862 | 90.273 | 9.394 | 0.000 | 52.100 | 53.0 | 45,861.5 | 100.5 | 50.0 | no | 0.557 |
| 50 | EN03 (`every_turn`/`turn`) | 145.021 | 29.073 | 3.135 | 10.124 | 59.886 | 48.326 | 42.802 | 3.0 | 14,373.5 | 100.5 | 50.0 | yes | 0.464 |
| 50 | **combined / new default** (`on_demand`/`turn`) | 100.359 | 31.521 | 3.648 | 10.216 | 11.844 | 0.000 | 43.130 | 3.0 | 10,736.5 | 100.5 | 50.0 | no | 0.357 |
| 100 | legacy (`every_turn`/`action`) | 609.915 | 72.957 | 6.931 | 299.243 | 102.599 | 71.053 | 128.184 | 103.0 | 177,903.5 | 201.5 | 100.0 | yes | 1.633 |
| 100 | EN02 (`on_demand`/`action`) | 569.673 | 74.217 | 6.346 | 322.074 | 34.555 | 0.000 | 132.482 | 103.0 | 171,366.5 | 201.5 | 100.0 | no | 1.583 |
| 100 | EN03 (`every_turn`/`turn`) | 372.935 | 73.727 | 9.085 | 23.312 | 108.153 | 68.994 | 158.659 | 3.0 | 37,653.5 | 201.5 | 100.0 | yes | 1.172 |
| 100 | **combined / new default** (`on_demand`/`turn`) | 273.546 | 67.179 | 6.502 | 26.235 | 34.875 | 0.000 | 138.754 | 3.0 | 31,116.5 | 201.5 | 100.0 | no | 0.979 |
| 200 | legacy (`every_turn`/`action`) | 2,093.626 | 217.655 | 16.151 | 1,338.585 | 190.959 | 97.524 | 330.276 | 203.0 | 655,312.5 | 401.5 | 200.0 | yes | 5.024 |
| 200 | EN02 (`on_demand`/`action`) | 1,977.269 | 169.719 | 11.883 | 1,400.828 | 100.734 | 0.000 | 294.106 | 203.0 | 642,975.5 | 401.5 | 200.0 | no | 4.773 |
| 200 | EN03 (`every_turn`/`turn`) | 871.580 | 225.933 | 15.937 | 88.267 | 202.436 | 104.058 | 339.007 | 3.0 | 94,812.5 | 401.5 | 200.0 | yes | 2.579 |
| 200 | **combined / new default** (`on_demand`/`turn`) | 703.920 | 211.772 | 12.413 | 85.758 | 96.225 | 0.000 | 297.752 | 3.0 | 82,475.5 | 401.5 | 200.0 | no | 2.279 |

### Individual phase deltas

Percentages are relative to the same-host legacy row.

| phase | size | step | commit | finish | snapshot | `_run`/turn | node/turn |
|---|---|---:|---:|---:|---:|---|---:|
| EN02 (`on_demand`) | 50 | −18.0% | +1.2% | −83.8% | 47.6 ms → 0 | 53 → 53 | −7.3% |
| EN02 (`on_demand`) | 100 | −6.6% | +7.6% | −66.3% | 71.1 ms → 0 | 103 → 103 | −3.7% |
| EN02 (`on_demand`) | 200 | −5.6% | +4.6% | −47.2% | 97.5 ms → 0 | 203 → 203 | −1.9% |
| EN03 (`turn`) | 50 | −34.6% | −88.7% | +3.1% | unchanged | 53 → 3 | −71.0% |
| EN03 (`turn`) | 100 | −38.9% | −92.2% | +5.4% | unchanged | 103 → 3 | −78.8% |
| EN03 (`turn`) | 200 | −58.4% | −93.4% | +6.0% | unchanged | 203 → 3 | −85.5% |
| combined vs legacy | 50 | −54.8% | −88.5% | −79.6% | 47.6 ms → 0 | 53 → 3 | −78.3% |
| combined vs legacy | 100 | −55.2% | −91.2% | −66.0% | 71.1 ms → 0 | 103 → 3 | −82.5% |
| combined vs legacy | 200 | −66.4% | −93.6% | −49.6% | 97.5 ms → 0 | 203 → 3 | −87.4% |

EN03's `finish` rises slightly because the deferred action effects move from
`commit` into the finish sweep; `commit` here excludes `finish`, so the total
is what matters. The wall-clock two-turn loop fell from 0.784/1.633/5.024 s to
0.357/0.979/2.279 s at 50/100/200 (−54.5%/−40.0%/−54.6%).

### EN04 isolated delta

EN04 is a code-level read optimisation present in every current row, so it
cannot be toggled off in this worktree. To isolate it, the combined configuration
(`lazy`/`on_demand`/`turn`) was also run from a pristine `git archive` of the
EN03 base commit `7f71fbf` on the same host immediately after the current
matrix:

| size | source | step ms | context ms | commit ms | finish ms | node/turn | near/turn |
|---|---|---:|---:|---:|---:|---:|---:|
| 50 | EN03 base | 166.343 | 73.088 | 21.539 | 15.322 | 26,642.0 | 126.0 |
| 50 | current | 100.359 | 31.521 | 10.216 | 11.844 | 10,736.5 | 100.5 |
| 100 | EN03 base | 403.015 | 175.129 | 42.255 | 42.664 | 69,901.5 | 253.0 |
| 100 | current | 273.546 | 67.179 | 26.235 | 34.875 | 31,116.5 | 201.5 |
| 200 | EN03 base | 1,156.503 | 532.284 | 159.392 | 120.319 | 201,779.0 | 503.0 |
| 200 | current | 703.920 | 211.772 | 85.758 | 96.225 | 82,475.5 | 401.5 |

EN04 deltas at 50/100/200: step −39.7%/−32.1%/−39.1%, context
−56.9%/−61.6%/−60.2%, commit −52.6%/−37.9%/−46.2%, finish
−22.7%/−18.3%/−20.0%, node calls −59.7%/−55.5%/−59.1%, `actors_near`
−20.2%/−20.4%/−20.2%. This is consistent with the EN04 report's 50/100
measurement and extends it to 200 residents. The base archive run was taken
immediately after, not strictly alternating with, each current run, so treat the
large context/node reductions as the signal and the smaller commit/finish
changes as noisy.

## Behaviour and determinism

Scenarios: `town100` seeds 305000 and 305001 for 8 turns, and the LA06
12-turn small room (three simple residents, metabolism on). “Legacy” is
`affordance_mode="lazy"`, `snapshot_mode="every_turn"`,
`rule_batching="action"`. “New” leaves all three at their `create_game`
defaults, which resolve to lazy/on_demand/turn. Wall time excludes construction.

| scenario / seed | turns | mode | proposed | applied | refused | alive | hunger mean | energy mean | health mean | work | handovers | improvised jobs | accidents | wall s |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| town100 / 305000 | 8 | legacy | 800 | 800 | 0 | 100 | 0.106612 | 46.6911 | 1.0 | 100 | 0 | 1 | 0 | 15.452 |
| town100 / 305000 | 8 | new | 800 | 800 | 0 | 100 | 0.106612 | 46.6911 | 1.0 | 100 | 0 | 1 | 0 | 2.324 |
| town100 / 305000 | 8 | new repeat | 800 | 800 | 0 | 100 | 0.106612 | 46.6911 | 1.0 | 100 | 0 | 1 | 0 | 2.459 |
| town100 / 305001 | 8 | legacy | 800 | 800 | 0 | 100 | 0.107278 | 46.3610 | 1.0 | 100 | 0 | 0 | 0 | 16.503 |
| town100 / 305001 | 8 | new | 800 | 800 | 0 | 100 | 0.107278 | 46.3610 | 1.0 | 100 | 0 | 0 | 0 | 2.268 |
| town100 / 305001 | 8 | new repeat | 800 | 800 | 0 | 100 | 0.107278 | 46.3610 | 1.0 | 100 | 0 | 0 | 0 | 2.206 |
| small / 305000 | 12 | legacy | 36 | 35 | 1 (`exhausted`) | 3 | 0.196233 | 8.546667 | 1.0 | 0 | 0 | 0 | 0 | 0.431 |
| small / 305000 | 12 | new | 36 | 35 | 1 (`exhausted`) | 3 | 0.196233 | 8.546667 | 1.0 | 0 | 0 | 0 | 0 | 0.041 |
| small / 305000 | 12 | new repeat | 36 | 35 | 1 (`exhausted`) | 3 | 0.196233 | 8.546667 | 1.0 | 0 | 0 | 0 | 0 | 0.036 |

Every per-turn record (status, proposals by action, applied/refused, refusal
reasons, alive, hunger/energy/health) was identical between legacy and new, and
between the two new-default runs. The final
`world.export_state(include_report=False)` SHA-256 digest was also identical in
all three comparisons. No material divergence was observed.

Trade/handovers were zero in these autonomous scenarios. That matches the prior
EN03 evaluation and means trade parity was not exercised by this evidence set;
the evaluated work path is the 100-work-per-town run, with one improvised job on
seed 305000 and none on 305001, and no accidents.

## Defaults and rationale

**Adopted as default:** `create_game` resolves affordance → lazy, snapshot →
on_demand and rule batching → turn for an autonomous simple/cheap session.

Why:

1. The combined speedup is large and in the same direction at every size:
   −55%/−55%/−66% step time and −55%/−40%/−55% two-turn wall time versus the
   same-host legacy modes.
2. `_run` sweeps fall from actions+3 to exactly 3 per turn, and node reads fall
   78–87%, without changing applied actions or final state in the evaluated
   scenarios.
3. The headless path is already what in-tree autonomous consumers read:
   `bigville/management/runs.py` and `bigville/server.py` call `game.snapshot()`
   explicitly when they need a UI state; `scenario_runner`, the evaluation tools
   and the profiling harness read world state or use explicit modes. Player and
   LLM sessions resolve to every_turn anyway.
4. The new defaults are restricted to the session class the program targeted.
   A player, LLM, Ocelot, human or unknown backend keeps the historical
   menu/every_turn/action path, so a menu-era or cognition consumer is not
   silently moved.

**Still explicit/opt-in:**

- `rule_batching="action"` for any simple/cheap run that depends on intra-turn
  read-offs (instant recipes sharing an input, container transfers, tool wear,
  clothing/exposure or contest stamina read earlier in the same turn). Turn
  batching is an ordering change by construction even though no divergence was
  observed here.
- `snapshot_mode="every_turn"` for a caller that reads `step()["snapshot"]`
  directly; `on_demand` callers must call `game.snapshot()`.
- `affordance_mode="menu"` for action pickers, Ocelot's adapter and equivalence
  oracles.
- A direct `BigvilleGame` constructor keeps menu/every_turn/action.

## Tests

```bash
python3 -m pytest -q tests/test_engine_defaults.py -p no:cacheprovider
# 17 passed in 0.85 s

python3 -m pytest -q tests/test_engine_*.py tests/test_lazy_*.py -p no:cacheprovider
# 178 passed, 1 skipped in 92.56 s

python3 -m pytest -q tests/test_tick_graph.py tests/test_tick_graph_executor.py \
  tests/test_tick_occupancy.py tests/test_tick_snapshot.py -p no:cacheprovider
# 40 passed in 75.86 s

python3 -m pytest -q tests/test_bigville_game_api.py tests/test_simple_life.py \
  tests/test_fix_simple_village.py tests/test_bigville_scenarios.py \
  tests/test_scenario_runner.py -p no:cacheprovider
# 63 passed in 67.82 s

python3 -m pytest -q tests/test_phase055_concurrency.py tests/test_phase029_contest.py \
  tests/test_phase047_joint_actions.py tests/test_bigville_world_persistence.py \
  -p no:cacheprovider
# 68 passed, 1 failed in 69.45 s
# The failure is the pre-existing timing threshold in
# test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical
# (concurrent/sequential ratio 0.81, required < 0.75). It reproduces unchanged
# on pristine base commits in the EN03 and EN04 reports and is host-load timing,
# not an EN05 regression. The other 68 tests pass.

python3 -m pytest -q tests/management -p no:cacheprovider
# 164 passed, 1 failed in 93.03 s
# The failure was test_cast_browser's start-up race: it read a generated
# resident after the run had already advanced a turn. Rerun in isolation:
# 1 passed in 2.00 s. This is a browser timing flake, not a default or state
# regression.

python3 domains/bigville_entities.py
# ERRORS (0), WARNINGS (0), INFO (95)
```

`tests/test_engine_defaults.py` (new, 17 tests) covers:

- the resolution matrix: autonomous simple and cheap → lazy/on_demand/turn;
  player, LLM and an injected LLM/Ocelot/human/other/unknown backend →
  menu/every_turn/action; explicit values win in both directions;
- a direct `BigvilleGame` defaults to menu/every_turn/action, and explicit
  `"auto"` on the direct constructor resolves lazy/on_demand/turn;
- `set_backend()` re-resolves all three modes in both directions and resolution
  is idempotent;
- `rule_batching` rejects invalid values in the setter and `create_game`;
- a two-turn autonomous simple run under the new defaults calls neither
  `actor_affordances`/`_actor_options` nor `snapshot`/`report`/`report_history`,
  returns no `"snapshot"` key, and runs exactly 3 `_run` sweeps per turn;
- an explicit menu/every_turn/action game still builds the menu, includes the
  snapshot, calls report/report_history, and runs the historical per-action
  sweep.

Old-default tests were pinned, not weakened:

- `tests/test_engine_snapshot.py` now requests `snapshot_mode="every_turn"`
  explicitly in the test that asserts the full snapshot shape;
- `tests/test_engine_rule_batching.py` now asserts the direct-constructor
  `"action"` default instead of the old `create_game` default, and still
  validates invalid values.

No behavioural assertion was removed. `tests/test_bigville_scenarios.py` still
asserts the player snapshot because a player session resolves to every_turn.

## Full-suite status

**The full suite was not run to completion in this session and no full-suite
pass is claimed.** The worktree instruction was to use targeted tests only
while a full suite was active. At measurement time an unrelated pytest full
suite was running in `/tmp/p045` and an xdist suite was also active; load
average stayed around 14–16. Running the full suite now would not be a clean
gate. It remains the supervisor's final gate on an idle host.

## Limitations

- One sample per benchmark row, single host, in-process, under external load.
  The context/`other` split is especially noisy; call counts and the
  legacy-vs-new direction are reliable.
- Only the synthetic simple/cheap scenario was benchmarked. Menu, LLM and
  Ocelot sessions were covered by resolution tests, not timed.
- Turn batching remains an ordering change. The evaluated town/small scenarios
  are the common move/work/rest pattern; they do not prove equivalence for every
  recipe, container, clothing, tool or combat permutation. The explicit
  `rule_batching="action"` escape hatch is documented, and auto only selects
  turn for simple/cheap sessions.
- Trade parity was not exercised: handovers/trade were zero in all behaviour
  runs.
- A consumer that creates a `BigvilleGame` directly, or a simple/cheap caller
  that reads `step()["snapshot"]`, does not get the new defaults automatically.
- The partitioned-executor divergence recorded by the lazy-affordances program
  is independent of these defaults. `executor="serial"` remains the default.

## Handoff

- Full suite on an idle host; record the exact result before the supervisor
  commits EN05.
- Next engine targets from the post-EN04 profile: backend valuation/scoring
  (`psi_can.choose`), remaining proximity scans and movement routing.
- Keep the partitioned-executor divergence as its own follow-up: it is not
  caused by, and is not fixed by, the EN05 defaults.
