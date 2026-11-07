# LA06 — Evaluation, default decision and benchmark

Status: complete. Phase LA06 of the lazy-affordances plan.
Base commit: `ab6d8e7` (LA05, branch `lazy-affordances`).
No commit or stage was performed by this phase.

## What changed

- **New `tools/evaluate_affordance_modes.py`.** Import-safe builder/main split,
  `--scenario town100|resource_social_stress|small`, `--seed`, `--turns`,
  `--modes menu,lazy`, `--timeout`, `--json-only`.  It builds the same
  scenario and seed once per mode with simple autonomous backends, runs the
  requested turns, and records per-turn status, proposals, applied/refused,
  refusals by reason, actions by kind, survival and body state, and final
  world report/tool tallies.  It prints JSON plus a markdown table and a
  lazy-minus-menu comparison.  No network, model or external service is used.
- **Extended `tools/benchmark_affordances.py`.** It now times the real lazy
  `_context` path alongside menu and the old observation-only seam, and times
  whole `step()` calls for fresh menu and lazy games (`--turns`).  The old
  `measure_size`/`benchmark`/`main` interface is preserved.
- **New `tests/test_lazy_evaluation.py`.** Covers the tool's import safety,
  scenario/mode validation, a two-turn two-mode run, JSON-safe evidence,
  timeout recording, the extended benchmark keys, and the declined default
  switch (`"menu"` default, `"lazy"` opt-in, `"auto"` rejected).
- **No behaviour change to the default.** `BigvilleGame` still constructs in
  `"menu"` and `create_game` still defaults to `"menu"`.  Only comments and the
  `create_game` docstring were updated to point at this evidence; `"auto"` was
  considered and declined.
- This report, `FINAL_REPORT.md`, the plan status/Results section, and a short
  README paragraph on the option.

## Evaluation

Command shape (all runs used `--timeout 180`; none timed out):

```bash
python3 tools/evaluate_affordance_modes.py --scenario town100 --seed 305000 \
  --turns 8 --modes menu,lazy --json-only
python3 tools/evaluate_affordance_modes.py --scenario town100 --seed 305001 \
  --turns 8 --modes menu,lazy --json-only
python3 tools/evaluate_affordance_modes.py --scenario small --seed 305000 \
  --turns 12 --modes menu,lazy --json-only
```

Every run completed all requested turns with status `advanced`; there were no
unhandled errors and the world sanity report had 0 errors and 1 warning (the
fastest-spoiling edible stock warning) in both `town100` modes.  Refusals were
**0** in every mode and scenario, so this evidence does not exercise refusal
variety.

### town100, seed 305000, 8 turns

| mode | status | turns | proposed | applied | refused | refusal rate | applied/turn | alive | hunger | energy | health | health min | work | handovers | accidents | context s | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| menu | completed | 8 | 800 | 800 | 0 | 0.0 | 100.0 | 100 | 0.115953 | 42.0239 | 1.0 | 1.0 | 15 | 0 | 0 | 2.816007 | 25.117343 |
| lazy | completed | 8 | 800 | 800 | 0 | 0.0 | 100.0 | 100 | 0.0 | 95.1 | 0.951 | 0.7 | 800 | 0 | 49 | 1.568496 | 23.953142 |

Applied actions: menu `{move: 785, work: 15}`; lazy `{work: 800}`.
Tool tally: menu `{improvised_jobs: 0, accidents: 0, broken_tools: 0}`;
lazy `{improvised_jobs: 94, accidents: 49, broken_tools: 0}`.
Step time: menu 24.116 s (3.015 s/turn), lazy 22.880 s (2.860 s/turn).

### town100, seed 305001, 8 turns

| mode | status | turns | proposed | applied | refused | refusal rate | applied/turn | alive | hunger | energy | health | health min | work | handovers | accidents | context s | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| menu | completed | 8 | 800 | 800 | 0 | 0.0 | 100.0 | 100 | 0.116095 | 41.9499 | 1.0 | 1.0 | 11 | 0 | 0 | 3.062799 | 25.084758 |
| lazy | completed | 8 | 800 | 800 | 0 | 0.0 | 100.0 | 100 | 0.0 | 95.7 | 0.957 | 0.8 | 800 | 0 | 43 | 1.375675 | 24.925902 |

Applied actions: menu `{move: 789, work: 11}`; lazy `{work: 800}`.
Tool tally: menu `{improvised_jobs: 0, accidents: 0, broken_tools: 0}`;
lazy `{improvised_jobs: 84, accidents: 43, broken_tools: 0}`.
Step time: menu 24.048 s (3.006 s/turn), lazy 23.834 s (2.979 s/turn).

### small (three-resident TG01-style room), seed 305000, 12 turns

| mode | status | turns | proposed | applied | refused | refusal rate | applied/turn | alive | hunger | energy | health | health min | work | handovers | accidents | context s | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| menu | completed | 12 | 0 | 0 | 0 | 0.0 | 0.0 | 3 | 0.0 | 100.0 | 1.0 | 1.0 | 0 | 0 | 0 | 0.352348 | 1.014580 |
| lazy | completed | 12 | 36 | 36 | 0 | 0.0 | 3.0 | 3 | 0.0 | 86.666667 | 0.866667 | 0.8 | 36 | 0 | 4 | 0.018739 | 0.647580 |

The small scenario has no buildings, work sites or other goal anchors, and the
menu published **zero** affordances there; menu mode therefore stood still
while lazy proposed common recipes and worked every turn.  Lazy again produced
improvised jobs (6) and accidents (4) and lost health.  This comparison is
degenerate for action quality (the menu did nothing), but it reproduces the
lazy candidate problem in isolation.

### Reading the outcomes

- **Applied actions:** not worse. Lazy applied 100 actions/turn on `town100`,
  the same as menu, with no refusals. On the small room menu applied nothing
  and lazy applied 36 actions.
- **Survival:** equal; all residents alive in every run.
- **Hunger/energy:** lazy was better (hunger 0.0 vs ~0.116; energy ~95 vs ~42
  on `town100`), because its residents worked in place instead of walking.
- **Health:** lazy was materially worse. The lazy cheap backend proposes
  common work recipes without validating the site, tool or ingredients, so the
  world accepts many improvised jobs and records accidents. Mean health fell to
  0.951/0.957 (minimum 0.7/0.8) on `town100` and 0.867 (minimum 0.8) on the
  small room, against 1.0 for menu.
- **Work/trade:** `world.report()` exposes handovers, and both modes had 0 (no
  trade was exercised). Work counts are taken from applied actions and the
  world's existing `attempt_counts`/`tool_tally`, not invented report fields.

## Default decision

**`affordance_mode="menu"` remains the default.  No `"auto"` mode was added.**

The plan requires declining the switch if lazy is materially worse on
survival, health or applied actions.  Lazy is equal on survival and applied
actions, but materially worse on health because of unvalidated work.  The
hunger/energy improvements and the context-time saving do not compensate for a
health regression that would compound over longer runs.

Lazy remains explicitly selectable with `create_game(..., affordance_mode="lazy")`
or `game.affordance_mode = "lazy"`.  Menu remains selectable for UI action
pickers, Ocelot's `replace_options` adapter, debugging and equivalence tests.

**Next hypothesis.** Make the lazy work proposal validate its site, tool and
ingredients before offering it (or drop unvalidated common recipes entirely),
so no improvised work is proposed by the cheap backend.  Re-run this same
evaluation; if lazy then matches menu on health, revisit the switch.  A second,
smaller step would teach the lazy fallback to prefer rest/eat over repeating a
work recipe that just failed.

## Benchmark

Exact commands:

```bash
python3 tools/benchmark_affordances.py --sizes 50,100 --repeats 1
python3 tools/benchmark_affordances.py --sizes 200 --repeats 1
```

Both used the default `--turns 1`, seed 305000, synthetic TG07 grid scenarios,
simple autonomous backends and construction excluded from the timed region.

| size | actors | menu ctx ms | lazy ctx ms | observe ms | menu/lazy ctx | menu turn ms | lazy turn ms | menu/lazy turn |
|---|---|---|---|---|---|---|---|---|
| 50 | 50 | 552.388 | 39.960 | 23.569 | 13.824x | 678.617 | 289.446 | 2.345x |
| 100 | 100 | 1106.828 | 125.123 | 71.292 | 8.846x | 1326.353 | 949.765 | 1.397x |
| 200 | 200 | 2840.002 | 303.707 | 237.243 | 9.351x | 3125.128 | 2443.968 | 1.279x |

`observe_only` is the LA01 `skip_affordances=True` seam and remains a lower
bound, not the lazy play path.  The real lazy context is 8.8-13.8x cheaper than
menu construction, but whole-turn time improves only 1.28-2.35x because commit
and physical work dominate.  The host was contended (load average roughly
10-20 on 16 CPUs with another pytest suite running), so these are same-host
relative measurements, not absolute throughput claims.

## Tests

```bash
python3 -m pytest -q tests/test_lazy_evaluation.py tests/test_lazy_llm.py \
  tests/test_lazy_cheap.py tests/test_lazy_observation.py \
  tests/test_lazy_target_resolution.py tests/test_lazy_affordances.py \
  -p no:cacheprovider
# 83 passed in 67.08s

python3 -m pytest -q tests/test_bigville_game_api.py tests/test_simple_life.py \
  tests/test_phase055_concurrency.py -p no:cacheprovider
# 48 passed, 1 failed in 76.46s

python3 domains/bigville_entities.py
# exit 0: 0 errors, 0 warnings, 95 info entries

python3 -m pytest -q tests/test_lazy_evaluation.py -p no:cacheprovider
# 8 passed in 0.81s (before the final report edits)
```

The single failure is the known environment-sensitive timing assertion in
`tests/test_phase055_concurrency.py::test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical`:

```text
SPEEDUP sequential=13.61s concurrent=11.77s ratio=0.86 calls=13
assert concurrent_seconds < 0.75 * sequential_seconds
```

The two semantic assertions before it passed (identical digests and identical
provider calls).  The host was heavily contended; this is a throughput
measurement under load, not a semantic failure and not caused by LA06.

## Full suite

The full suite was **not run to completion**.  Another pytest suite was active
in the worktree during this phase (for example
`tests/test_phase062_perceiver.py tests/test_phase052_agent_view.py ...`) and
the load average was about 20 on 16 CPUs.  Targeted suites above are the
evidence for this phase.  A full-suite pass is therefore **not claimed**; it
remains the final gate for an idle host.

## Limitations

- All evaluation runs had **0 refusals**, so refusal-rate behaviour, the
  refusal-by-reason table and the fallback path were not exercised by these
  scenarios.  The tests still cover refusal handling separately.
- No trade occurred in either mode (`handovers_count` 0), so trade parity is
  untested by this evaluation.  The report tool records the real field rather
  than inventing a trade count.
- The small room has no goals, buildings or work sites; menu mode offered zero
  affordances there.  Its comparison is useful for isolating the lazy work
  defect, not for judging action quality.
- The lazy health loss is specifically tied to unvalidated work recipes
  (`improvised_jobs`/`accidents`).  Other lazy candidates (eat, rest, move,
  fetch/put, tend, care) are exercised by tests but were not the dominant
  actions over these seeds.
- Wall-clock numbers are same-host relative measurements under contention, not
  absolute performance claims.
- `resource_social_stress` is supported by the tool but was not part of the
  required LA06 run matrix; `town100` and `small` are the recorded evidence.
