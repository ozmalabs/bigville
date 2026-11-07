# LA07 — Lazy work prefilter and re-evaluation

Status: complete. Phase LA07 (follow-up from LA06) of the lazy-affordances
plan.
Base commit: `e2d28b2` (`Lazy affordances: add LA07 work-prefilter follow-up`,
branch `lazy-affordances`).
No commit or stage was performed by this phase.

## What changed

- **`worlds/bigville_world.py`**
  - New `_recipe_start_block(actor, recipe)` holds the structural checks that
    `_recipe_refusal` already applied on the enactment path: recipe existence,
    sleep/collapse, gathering site, `at_building`, burial readiness.
    `_recipe_refusal` now delegates to it, so the enactment refusal order is
    byte-for-byte the same and the two paths cannot drift.
  - New `recipe_preview(actor, recipe) -> {"ok": bool, "reason": str}`. It is
    read-only: it opens no job, consumes no stock, claims no action slot and
    writes no world state. It mirrors the menu work publish filter in the same
    order:
    1. recipe exists in `_actions`/`_recipe_specs` else `not_known`;
    2. `busy(actor)` else `not_possible` (the menu suppresses new work while a
       job is open);
    3. sleep/collapse code (`asleep`, `collapsed`, ...);
    4. `_capable`: `_skilled_enough` and `_recipe_in_season` else `unskilled`;
       strength below `RECIPE_EXERTION` else `unskilled`; a missing held tool
       for an open recipe else `out_of_stock`;
    5. `_recipe_start_block` (site/building `not_at_site`, burial `not_ready`);
    6. `_recipe_inputs_available` else `out_of_stock`.
    It deliberately adds no tool-fitness or bare-hands judgement: those are
    enactment consequences, not menu filters.
  - `observe(actor)` now publishes `busy` and a bounded (16), deterministic,
    name-sorted `work_candidates` list with `recipe`, `out` and `time_minutes`.
    A busy actor gets an empty list because the menu publishes no new work then.
    The list is built from the actor's known recipes plus the current job
    recipe, prefilters `at_building` against the local cell, then uses
    `recipe_preview`. To keep the observation cheap, one safe
    over-approximation runs first: a recipe is skipped only when a bulk input's
    total available quantity (own inventory, reachable containers, open town
    store) is already below the need. Item/type inputs are left to the full
    preview, so the prefilter can never reject a recipe that the full preview
    would accept. Observation never calls `_actor_options`/`actor_affordances`.
- **`bigville/backends/cheap.py`** — the lazy candidate generator no longer
  imports the recipe pack or guesses at local buildings/common recipes. It adds
  `work` only for entries in `entities["work_candidates"]` and only when
  `entities["busy"]` is false. The refusal fallback and every other candidate
  rule are unchanged; a refused work proposal is still ordinary feedback.
- **`tests/test_lazy_work.py`** (new, 16 tests) — preview read-only contract,
  reason matrix, menu agreement, observation enrichment, lazy candidate use,
  and the required runs.
- This report and the LA07 status row in `docs/design/LAZY_AFFORDANCES.md`.
  `tools/evaluate_affordance_modes.py` already published every field needed, so
  it was not changed.

## Preview / filter agreement

For three sampled `town100` actors, including a busy-capable one, the set of
recipes published by `actor_affordances()` as `work` is exactly the set whose
`recipe_preview` is ok at the same state. The test asserts equality, not a
subset, so a future menu change that the preview misses fails the suite. At
`turn == 0` the preview matches the menu; the one residual improvisation below
comes from the *enactment* turn boundary, not from a filter mismatch.

## Tests

Command shape and exact results on the contended host:

```bash
python3 -m pytest -q tests/test_lazy_work.py tests/test_lazy_cheap.py \
  tests/test_lazy_observation.py -p no:cacheprovider
# 35 passed in 78.24s (0:01:18)

python3 -m pytest -q tests/test_lazy_*.py -p no:cacheprovider
# 99 passed in 123.72s (0:02:03)

python3 domains/bigville_entities.py
# exit 0: 0 errors, 0 warnings, 95 info entries
```

The 16 LA07 tests cover: read-only preview (full `export_state`, turn state,
stock, inventory, outcome, tool tally and job unchanged); unknown, unskilled,
out-of-season, missing-input, wrong-site, wrong-building and busy reasons;
menu/preview agreement; `busy` and bounded sorted `work_candidates`; work only
from the published list; no work while busy; no work when no preview is ok; a
full 8-turn `town100` lazy run; the recorded menu action counts; and the 12-turn
small lazy run.

## Re-evaluation

Commands (all completed, no timeouts):

```bash
python3 tools/evaluate_affordance_modes.py --scenario town100 --seed 305000 \
  --turns 8 --modes menu,lazy --json-only
python3 tools/evaluate_affordance_modes.py --scenario town100 --seed 305001 \
  --turns 8 --modes menu,lazy --json-only
python3 tools/evaluate_affordance_modes.py --scenario small --seed 305000 \
  --turns 12 --modes menu,lazy --json-only
```

Every run completed the requested turns with status `advanced`; `town100` had
0 sanity errors and 1 warning (fastest-spoiling edible stock) in both modes.

### town100, seed 305000, 8 turns

| mode | applied | refused | refusal rate | alive | hunger | energy | health | health min | work | improvised | accidents | context s | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| menu | 800 | 0 | 0.0 | 100 | 0.115953 | 42.0239 | 1.0 | 1.0 | 15 | 0 | 0 | 2.741867 | 25.197457 |
| lazy | 800 | 0 | 0.0 | 100 | 0.106612 | 46.6911 | 1.0 | 1.0 | 100 | 1 | 0 | 1.090836 | 23.293430 |

Applied actions: menu `{move: 785, work: 15}`; lazy `{move: 700, work: 100}`.
Tool tally: menu `{improvised_jobs: 0, accidents: 0, broken_tools: 0}`;
lazy `{improvised_jobs: 1, accidents: 0, broken_tools: 0}`.

### town100, seed 305001, 8 turns

| mode | applied | refused | refusal rate | alive | hunger | energy | health | health min | work | improvised | accidents | context s | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| menu | 800 | 0 | 0.0 | 100 | 0.116095 | 41.9499 | 1.0 | 1.0 | 11 | 0 | 0 | 2.569375 | 23.568347 |
| lazy | 800 | 0 | 0.0 | 100 | 0.107278 | 46.3610 | 1.0 | 1.0 | 100 | 0 | 0 | 1.093315 | 23.400472 |

Applied actions: menu `{move: 789, work: 11}`; lazy `{move: 700, work: 100}`.
Tool tally: both modes `{improvised_jobs: 0, accidents: 0, broken_tools: 0}`.

### small (three-resident TG01-style room), seed 305000, 12 turns

| mode | applied | refused | refusal rate | alive | hunger | energy | health | health min | work | improvised | accidents | context s | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| menu | 0 | 0 | 0.0 | 3 | 0.0 | 100.0 | 1.0 | 1.0 | 0 | 0 | 0 | 0.444072 | 1.189864 |
| lazy | 35 | 1 | 0.027778 | 3 | 0.196233 | 8.546667 | 1.0 | 1.0 | 0 | 0 | 0 | 0.043225 | 0.639370 |

Applied actions: menu none; lazy `{move: 32, rest: 2, sleep: 1}`. The single
lazy refusal is `exhausted` (a move at the end of the run). Both modes report
the scenario's pre-existing sanity error “residents have unreachable or missing
workplaces”, which is a property of the bare room and is not caused by LA07.

### Reading the outcomes

- **Health regression removed.** LA06 had lazy health 0.951/0.957 (min 0.7/0.8)
  with 94/84 improvised jobs and 49/43 accidents on `town100`. LA07 has health
  1.0/min 1.0 in both seeds, 0 accidents, and only one improvised job on one
  seed. The small room went from 36 work actions, 6 improvised jobs and 4
  accidents with health 0.867 to 0 work actions and health 1.0.
- **Applied actions and survival match.** 100 applied/turn and all 100 alive on
  `town100` in both modes and seeds. Refusals remain 0 there.
- **Hunger and energy are no longer worse on `town100`.** Lazy hunger 0.107 vs
  0.116 and energy 46.7/46.4 vs 42.0/41.9, because residents work in place
  instead of walking.
- **Context is still about 2.4x cheaper than the menu**, despite the added work
  prefilter: 1.09 s vs 2.57-2.74 s over 8 turns. Whole-turn wall time is close
  (23.3 s vs 23.6-25.2 s) because commit and physical work dominate.
- **The small room is still a degenerate comparison.** Menu publishes no
  affordances there and stands still. Lazy now correctly proposes no work, but
  it still travels every turn, exhausting energy to 8.55 and raising hunger to
  0.196. That is a travel/valued-goal issue, not work validation: no accidents,
  no improvised jobs, health 1.0.

## Remaining causes

1. **One improvised job, `town100` seed 305000:** `press_linseed_oil` by
   Keturah Marsh, opened at world turn 1. Evidence from an instrumented run:
   `open_recipe=False`, `at_workplace=False` at open time. The recipe's press
   stands at the actor's workplace; `_at_workplace` deliberately skips the
   location check on the setup turn (`self._turn == 0`), so the context and
   preview built before the tick advances see the press, while the job opens
   after `_turn` becomes 1 and correctly finds it out of reach. The job runs
   bare-handed and causes no accident (health stays 1.0). This is a pre-existing
   setup-turn/enactment boundary asymmetry in `_at_workplace`, not an
   unvalidated recipe; changing it was outside LA07's scope. The 8-turn test
   records and asserts this exact shape rather than asserting an unexplained
   zero.
2. **Small-room travel.** With work suppressed, the lazy fallback walks every
   turn in a room with no goals, so energy falls and hunger rises while menu
   mode idles. The next hypothesis is to suppress oscillating idle travel or
   let rest/sleep outrank a move that makes no progress toward a named place.

## Default recommendation

**The LA06 blocking criterion is resolved, so the evidence now supports making
lazy the default for autonomous simple runs.** Lazy matches menu on survival,
health and applied actions on both `town100` seeds, is no worse on hunger and
energy there, and keeps a ~2.4x cheaper context. It is not worse on health in
the small room either.

Per the phase instruction the `menu` default is **not changed here**; the
recommendation is left to the supervisor. The caution is the small-room
travel/energy difference above: it is a behaviour-quality issue, not the health
regression that blocked LA06, and it should be either accepted (the room is an
artificial, goal-free scenario where menu does nothing) or fixed before a
default switch.

## Limitations

- `town100` had 0 refusals in both modes, so the refusal-by-reason table and
  the fallback path are exercised only by the small room's single `exhausted`
  refusal and by the unit tests.
- Only two `town100` seeds and one small seed were run; the evidence is
  reproducible but not a wide sweep.
- No trade occurred (`handovers_count` 0 in every run), so trade parity is not
  tested by this evaluation.
- The small comparison is degenerate: menu publishes nothing there, and the
  scenario has a pre-existing sanity error.
- `work_candidates` is bounded at 16 and built from the actor's known recipes
  plus the current job recipe. The menu publishes every skilled recipe that
  passes the physical gate; the lazy list is a subset, matching the cheap
  backend's pre-existing known-recipe filter. The preview agreement test
  samples three actors, and the full preview itself agrees with the menu for
  every recipe.
- Context/wall times are same-host relative measurements under contention, not
  absolute throughput claims.
