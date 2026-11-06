# Phase 027: Food value, freshness and graded eating

## Summary

Each food item has a `feeds` value in loaf-equivalents. One loaf (`bread`, 1.0) is one resident's meal,
the unit of `food_per_resident` in the balance scenario. `eat` lowers hunger by
`feeds x freshness`, times `raw_penalty` when the food needs preparation and has none, and clamps at 0.
Spoiled food is still eaten and relieves nothing. Its meal publishes `illness_risk`, which Phase 037 will
route as illness. Spoiled stock stays in the pile instead of being deleted. Freshness travels with food
moved between piles and mixes with fresh food that joins the same pile. The balance model's food line is
in loaves.

Self-test: 0 errors, 0 warnings. `test_hamlet` check: exit 0. Full suite with the other session's seven
untracked test files ignored: 912 passed, 1 skipped, 0 failed.

## Changes

### Pack data (`packs/bigville`, `packs/test_hamlet`)

- `world/items.json` (bigville): `feeds` on all 70 food items. `needs_prep: true` on the raw animal foods
  `mutton`, `pork`, `beef`, `poultry`, `fish`. New table `FOOD_GRADING` in the same file:
  `raw_penalty` 0.3, `rot_illness` 0.3, `raw_illness` 0.05 (all APPROX, see Data and sources). The file
  `_doc` gains a "food grading" section.
- `pack.json` (bigville and test_hamlet): one `FOOD_GRADING` entry each, bound to `world/items.json`.
- `world/items.json` (test_hamlet): `bread` feeds 1.0 (the only food there), and the `FOOD_GRADING` table.
- Both packs normalised with `tools/export_pack.py` (bigville: 191 tables; test_hamlet: 191 tables).

Feeds values, by group (full list in the file):

| Group | feeds |
|---|---|
| Bread and bake-based meals (`bread`, `buttered_bread`, `flatbread`, `porridge`, `noodles`, ...) | 0.5 to 1.0 |
| Whole-meal dishes (`stew`, `roast`, `pie`, `meat_pie`, `shepherds_pie`, `sausage_stew`) | 1.0 |
| Cured and joint meats (`ham`, `pork`, `beef`, `mutton`) | 0.8 to 1.0 |
| Fruit (`apple`, `pear` 0.5; `plum` 0.4; `berry` 0.25) | 0.25 to 0.5 |
| Dairy and fat (`butter`, `honey` 0.5; `cheese` 0.6; `milk` 0.4) | 0.3 to 0.6 |
| Preserves and condiments (`pickles`, `sauerkraut` 0.2; `mustard` 0.1) | 0.1 to 0.4 |
| Drink (`ale` 0.3; `beer`, `cider`, `mead` 0.2) | 0.2 to 0.3 |

### `domains/world_affordances.py`

- Binds `FOOD_GRADING`.
- New functions: `feeds(kind)` (0 for derived scraps), `meal_value(kind, freshness)`,
  `meal_illness_risk(kind, freshness)`.
- `_tag_yield(kind, "food")` uses `feeds` instead of 1.0 per food item.
- `_balance_flows`: the food line is named `food (loaves, upper bound)`. Its note reads "loaves/period".

### `domains/bigville_entities.py`

- New `_check_food_grading`, called from `check_consistency` after `_check_exhaustion`. It requires a
  numeric `feeds` in (0, 1.5] on every food item except derived scraps, a boolean `needs_prep` on foods
  only, and the `FOOD_GRADING` constants as fractions.

### `worlds/bigville_world.py` (my hunks only; the other session's hunks are untouched)

- `eat`: hunger falls by `meal_value(kind, pile freshness)`, floored at 0. The meal is recorded by the new
  `_record_meal`. The empty-stock refusal (`not_held`) and the serving-equipment checks are unchanged.
- New methods, placed after `eat`: `_record_meal`, `last_meal(actor)` (value, freshness, pleasantness,
  illness_risk), `meal_value(actor, kind)`, `_relieves_hunger(kind)`, `_pile_condition(node)`,
  `_mix_freshness(node, added, added_condition)`.
- `set_stock(kind, qty, *, condition=None)`: a pile that gains units mixes their freshness in (new
  production arrives at 1.0). A transfer passes the arriving food's condition.
- `_run`: the store-level "fresh harvest" reset at the end of a run is removed, and so is the `before`
  snapshot it used. Mixing in `set_stock` and the transfers replaces it. The spoil rule no longer sets
  `qty` to 0 at condition 0.
- Transfers that carry a pile's freshness: `_move_stock_to_inventory` (store to carrier), `fetch` (from a
  container), `put`, `_move_inventory_to_stock`, `_move_inventory_to_inventory` (`give`), and the armed
  `fill` and `empty` in `_resolve_actor_events`.
- `_actor_options`: the eat option carries `meal_value`. The store fetch, the market move and the
  tradesperson's output option set `food` only when the food relieves some hunger at the pile's freshness.
  The "food" flag on container fetches (other session's hunk) is untouched.
- `_audit`: `food_qty` counts loaf-equivalents weighted by freshness. `food_shelf_life` ignores spoiled piles.

### `bigville/backends/cheap.py`

- Among eat options, `score` gains `10 x meal_value`. Eating is still chosen by the existing goal bonus.
  The value only orders eat options against each other.

### Tests

- New `tests/test_phase027_food_value.py` (13 tests): feeds on every food item; grading constants; self-test
  clean; a loaf clears a period; one apple relieves half and two apples equal a loaf; stale bread relieves
  less and carries an illness risk; raw mutton relieves `raw_penalty` and cooked roast its full feeds; a
  spoiled pile is kept and can be eaten; only an empty stock yields nothing; freshness moves with fetch and
  fill; fresh production mixes with spoiled stock; meal value and risk functions; balance food line in loaves.
- Existing assertions changed (old -> new, and why):
  1. `tests/test_bigville_world_migrated.py::test_residents_get_hungry_eat_food_and_starve_without_it`:
     `hunger == 0.0` -> `== 1.5`. The bread has aged two periods (freshness 0.5), so one loaf relieves 0.5
     of hunger 2.0.
  2. `tests/test_bigville_world_migrated.py::test_perishable_food_rots_through_its_stages_and_spoils`:
     `qty("bread") == 0.0` -> `== 20.0`, plus `stock_condition == 0.0`. This is the fs_rot change: spoiled
     stock stays.
  3. `tests/test_simple_body_food.py::test_simple_resident_observes_hunger_fetches_eats_and_conserves_food`:
     pantry apples `== 8` -> `== 7`; final hunger `== 0` -> `== 0.5`. Decay is off in this scenario, so
     three fresh apples (0.5 each) are eaten and leave 0.5.
  4. `tests/test_simple_life.py::test_simple_resident_fetches_and_eats_physical_food_across_periods`:
     final hunger `== 0` -> `== 0.75`; pantry apples `== 8` -> `== 6`. Here the apples age (perishable
     decay of 0.25 a period), so four apples are eaten at freshness 0.75, which relieves 0.375 each.
  5. `tests/test_phase023_job_occupancy.py::test_a_worker_who_is_busy_can_still_eat`:
     hunger `== 0.0` -> `== 1.0`. One fresh loaf relieves 1.0 of hunger 2.0.

  No assertion was weakened or deleted; the eating and rot tests keep their intent.

## Data and sources

- `feeds`: APPROX. Judged from each food's energy against bread, with bread = 1.0 by definition (one loaf is
  one meal). No table in this repo fixes these values. The brief fixes apple at 0.5 (two apples = a loaf).
  By energy, an apple at the pack's 0.3 kg is about 0.12 of a 0.5 kg loaf, using typical energy densities
  I recall (not sourced here). The apple value follows the brief; see Open questions.
- `raw_penalty` 0.3: APPROX. The seed `bigville_foodstuff.json` names a raw penalty but gives no value.
- `rot_illness` 0.3 and `raw_illness` 0.05: APPROX. The seed names both terms but gives no value. Illness
  risk is a per-meal probability; Phase 037 decides how it becomes harm.
- The seed's "a meal relieves about 5" is not used. The world's hunger scale is +1.0 per period
  (`_resolve_period_effects`), and `food_per_resident` is 1.0 loaf per period, so one loaf is the
  reconciled unit.
- Pleasantness is the freshness (`meal_pleasantness`). Taste belongs to Phase 035.

## Validation

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS (0), WARNINGS (0), issues (0). Output: `docs/phases/phase027/selftest.log`; the pre-change output is `selftest_before.log` |
| `python3 -m domains.check --pack test_hamlet` | exit 0 |
| `python3 tools/generate_seeds.py --check` | exit 0; 31 files match the pack |
| `python3 tools/export_pack.py` and `--pack test_hamlet` | normalised; a rerun leaves the files unchanged |
| `python3 -m pytest -q -p no:cacheprovider tests/test_phase027_food_value.py` | 13 passed |
| Full suite, other session's 7 untracked files ignored (`--ignore` list in the standing rules) | 912 passed, 1 skipped, 0 failed. Log: `tests_full_other_session_ignored.log` |
| Clean export of HEAD (`git archive HEAD` to a temp dir, full suite) | 894 passed, 1 skipped. Log: `head_clean_export_tests.log` |
| Other session's 7 files (for reference) | 18 passed, 1 skipped, 3 failed. The three are `test_real_ocelot_advertises_only_wired_communication_capabilities`, `test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control` and `test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`, each with `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`. Log: `other_session_files.log` |
| Founding cast | Regenerated `seeds/bigville_cast100.json` and `bigville/seeds/bigville_cast100.json` to a temp path with `write_cast_seed`. Both are byte-identical to the committed files, so the cast is unchanged. Nothing was written to the repo. |

A first baseline run started before my pack edits overlapped them. Three tests (`test_phase013a`,
`test_phase013b`, `test_phase015`) failed in that run. They pass on re-run (22 passed), so the failures came
from the overlap and are not part of this phase's result.

## Balance (per period, BALANCE_SCENARIO)

| Line | Before | After |
|---|---|---|
| food (upper bound), supply | 812.0 food units | `food (loaves, upper bound)` 358.0 loaves |
| food demand | 100.0 | 100.0 (unchanged: 100 residents x 1.0 loaf) |
| food ratio | 8.12 | 3.58 |
| food note, from grain | 540.0 | 194.4 |

Every other line printed the same value before and after (diff of the self-test output). The supply fell
because each food item now counts as its feeds, not as one unit. A porridge is 0.8 loaves, not 1.0. The
recipe chains did not change.

## Behaviour changes that reach the 100-resident village (not run)

I did not run the 100-resident village, and the brief does not ask for it. These effects are expected from
the code and are not measured:

- Eating a non-loaf food relieves less than a loaf. Residents eat more often when they live on apples,
  fruit or raw meat.
- Raw animal meat relieves 0.3 of a meal, so a resident who eats it raw gets much less from it.
- Spoiled food stays in the store and in carriers. Residents who hold it can eat it (value 0, illness risk
  0.3). The store fetch and market move no longer advertise spoiled piles as food, so a resident does not walk
  to a store for them.
- Fresh production that joins a non-empty pile now mixes with its condition. It used to reset the pile to
  fresh. A bake into a half-stale pile now starts below 1.0.
- Scraps relieve nothing. Before, eating any food reset hunger to 0, scraps included.
- `reporting.py` still counts food in units (`food_qty`), not loaves. The report was out of scope.

## Limits

- The 100-resident village was not run. Its outcomes (food, starvation, illness risk) are unmeasured.
- Dropped bulk stock (`_drop_stock`, the carry overflow pile) has no freshness and does not decay. It is not
  a `Stock` node, so the freshness path does not reach it.
- `illness_risk` is published only. Nothing harms the body yet (Phase 037).
- Balance food supply is an upper bound (best recipe path, cooked foods at feeds). Raw meat is counted at
  full feeds in this bound.
- The `food` flag on the other session's container fetch option is not changed. It still reads
  `bool(food)` and does not check freshness.

## Open questions

1. **Raw wheat is not food in this pack.** The brief's acceptance names raw wheat. Grains are not
   food-flagged. Flagging them as food would reclassify them: `adjectival()` makes food perishable, so wheat
   would decay (0.25 a period unless overridden), and it would change `eat` options and the balance. I
   tested the raw penalty on raw mutton instead. Do you want grains as food, with a decay override and a
   check of the balance?
2. **Apple feeds 0.5 is the brief's value, not an energy value.** Energy per unit is about 0.12 of a loaf at
   the pack's weights (see Data and sources). If feeds should track energy, the acceptance "two apples =
   a loaf" must change, and the apple's value changes with it.
3. **Discard is needed; I did not add one.** The brief expects spoiled food to leave by "the existing waste
   and compost path". That path does not take food: `make_compost` accepts only `compostable` items (straw,
   ash, scraps, meat leavings). A bulk pile has no drop or destroy action. A `discard` major action (a
   bulk-stock `drop` that removes the qty) would close it. I recommend adding it in a later phase.
4. **Simple backend and zero-value food.** The cheap backend still eats held food with value 0 (spoiled piles
   and scraps) when it is hungry, because a held eat option carries the usual goal bonus. Whether a resident
   should refuse worthless food is a cognition choice, so I left it.
5. **APPROX constants.** `raw_penalty`, `rot_illness` and `raw_illness` need a source or a Phase 037 review.

## Follow-ups

- Phase 037: route `illness_risk` (the `illness_risk` attribute on the eating resident; `last_meal(actor)`)
  through the health routes, as a cause `illness`.
- Phase 035: `meal_pleasantness` is the freshness until taste exists.
- A `discard` action (open question 3).
- `reporting.py` food counters in loaves.

## Other session's hunks

My edits sit in separate hunks. The other session's hunks in `worlds/bigville_world.py` (the `food` flag on
the container fetch option, `resident_plan_from_context`, and the other edits listed in the standing
rules) are untouched. `bigville/game.py`, `bigville/runtime.py`, and the other session's test and untracked
files are untouched.

## Git status

Start: `git_status_start.txt`. End: `git_status_end.txt`, captured before this report file was written.
My changed files:

- `bigville/backends/cheap.py`
- `domains/bigville_entities.py`
- `domains/world_affordances.py`
- `packs/bigville/pack.json`, `packs/bigville/world/items.json`
- `packs/test_hamlet/pack.json`, `packs/test_hamlet/world/items.json`
- `worlds/bigville_world.py` (my hunks only)
- `tests/test_bigville_world_migrated.py`, `tests/test_phase023_job_occupancy.py`,
  `tests/test_simple_body_food.py`, `tests/test_simple_life.py`
- `tests/test_phase027_food_value.py` (new)
- `docs/phases/phase027/` (new)

## Supervisor review

- Open question 4 resolved in `bigville/backends/cheap.py`: an `eat` option whose published
  `meal_value` is 0 (a spoiled pile) is dropped from the cheap resident's options and does not
  count as carried food, so a hungry resident holding only spoiled food goes to fetch fresh food
  instead of eating the pile turn after turn. Options without a `meal_value` key are unaffected.
- Open questions 1 (grains as food), 2 (apple value by energy) and 3 (a `discard` action) are left
  for the user.
