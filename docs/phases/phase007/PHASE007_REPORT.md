# Phase 007: balance scenario from the world

## Summary

`BigvilleWorld.balance_scenario()` reports the BALANCE_SCENARIO shape from a built town. For the
100-resident town, every fact key agrees with the world exactly except the grain beds, and the three
parameters are checked against their pack source. The one disagreement is the grain beds: the world builds 61 (wheat 21,
barley 20, oats 20) where the scenario says 80 (27/27/26). I did not change the world or the pack for
this. It is recorded as a strict xfail in the new test, and it needs a decision (see Open questions).
No pack value was corrected, so the founding cast did not change and no seeds were regenerated.

## Changes

- `worlds/bigville_world.py`: new method `BigvilleWorld.balance_scenario()`, inserted before
  `seed_residents`. One hunk, +42 lines. The other hunks in this file (the `resident_plan_from_context`
  and "food" fetch-option changes, from the other session) are untouched and not mine to commit.
- `tests/test_phase007_balance_scenario.py` (new): 5 passing tests and 1 strict xfail.
- `docs/phases/phase007/PHASE007_REPORT.md` (new): this report.
- Not changed: `domains/population.py`, `packs/bigville/population/balance_scenario.json`, seeds,
  `domains/bigville_entities.py`.

## Key-by-key comparison (100-resident town, `from_town100()`)

| Key | Pack value | Built value | Kind | Result |
|---|---|---|---|---|
| residents | 100 | 100 (actors) | fact | agrees |
| households | 46 | 46 (Household nodes) | fact | agrees |
| beds wheat | 27 | 21 | fact | **disagrees** (xfail) |
| beds barley | 27 | 20 | fact | **disagrees** (xfail) |
| beds oats | 26 | 20 | fact | **disagrees** (xfail) |
| beds, garden (cabbage, potato, carrot, onion, bean) | not in table | 1 each | fact | built, not modelled; asserted |
| plots | 8 | 8 (arable land) | fact | agrees |
| plot_area | 1.0 | 1.0 | fact | agrees |
| soil | loam | loam | fact | agrees |
| animals | cow, chicken, pig, sheep, horse, bee, dog: 1 each | same | fact | agrees |
| pasture_area | 4.0 | 4.0 (pasture land) | fact | agrees |
| water_sources | well, spring, spring, stream | same kinds, same order | fact | agrees |
| woodland | absent; model default 1.0 | 1 (lumber deposits) | optional fact | agrees with default |
| food_per_resident | 1.0 | not a world fact | parameter | checked: recipes doc "a loaf is one resident's bread for a period"; bake_bread makes 60 loaves per batch |
| staple | bake_bread | recipe present in built world, outputs bread | parameter | checked |
| work_minutes_per_resident | 480 | not a world fact | parameter | no pack source (APPROX); checked only that 0 < 480 <= one period (1440 min) |

Test coverage: `test_counts_and_fixed_values_agree_exactly_for_the_100_town` asserts all fact keys
except beds. `test_the_built_beds_outside_the_scenario_are_one_garden_bed_per_starting_crop` pins the
garden beds. `test_parameters_are_checked_against_their_pack_source` covers the three parameters.
`test_a_drifting_scenario_is_reported` shows that a changed residents, animals, water source, or plot
count is reported by the comparison.

## Values corrected

None. The pack values match what the world builds for every key except the grain beds, and I judged
the world to be the side that is wrong there (below).

## Grain beds: the world misbuilds the intended 80

The pack (27/27/26) and the docstring of `_seed_village_crops` ("Eighty beds") both describe 80 grain
beds. The world builds 61. Two causes, both in `_seed_village_crops` (not changed):

1. The loop `while len(self._living_crops()) < target` breaks on the first crop whose seed is exhausted.
   Grain seed is 40 wheat, 20 barley, 20 oats (STARTING_STOCK), 80 in all. Barley and oats run out
   first, the loop stops, and 19 wheat seed stays unused in the store after the build (checked).
2. `target=80` counts every living crop, including the 5 garden crops. Even with unlimited seed, the
   loop would stop at 75 grain beds plus 5 garden beds.

Both causes can be fixed in one place, and the 80 grain seeds then supply exactly 80 grain beds. That
changes founding crop counts, the balance numbers, and possibly tests that depend on them, so it is
left to the supervisor. I did not correct the pack to 61/20/20 because the pack and the docstring
describe 80 as the intent.

## Validation

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS (0), WARNINGS (0) |
| `python3 -m domains.check --pack test_hamlet` | exit 0 |
| `python3 tools/generate_seeds.py --check` | exit 0; seeds match pack 'bigville' (22 files) |
| `python3 -m pytest -q -p no:cacheprovider tests/test_phase007_balance_scenario.py -rxX` | 5 passed, 1 xfailed in 0.31s |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (full suite) | 541 passed, 3 failed, 2 skipped, 1 xfailed in 116.35s |
| Full suite with the other session's files ignored | 487 passed, 1 xfailed, 0 failed in 112.27s |

Three failures, all in the other session's files, reported verbatim:

- `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`
- `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`
- `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`

Each fails with `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`
(`OcelotUnavailableError: Ocelot backend requires Ocelot's worlds.bigville_ocelot_adapter ...`). The
adapter comes from the Ocelot repo and is not on PYTHONPATH here. They are not caused by this phase.

The ignored-files run used these patterns: `tests/test_bigville_ocelot_*.py`, `tests/test_mixed_ocelot_*.py`,
`tests/test_bigville_*persistence*.py`, `tests/test_bigville_game_api.py`, `tests/test_bigville_scenarios.py`.

Pre-run baseline: self-test 0/0 and 514 tests passing on a clean checkout (from the brief). The
other session's uncommitted work is present, so the counts above are not comparable to that baseline.

Git status at start (other session's files included): README.md, bigville/backends/ocelot.py,
bigville/game.py, bigville/runtime.py, bigville/seeds/bigville_actor_decision.json,
docs/AGENT_BACKENDS_PLAN.md, docs/FEATURE_PHASES.md, tests/test_bigville_game_api.py,
tests/test_bigville_scenarios.py, worlds/bigville_world.py, and untracked files for the other session's
persistence, ocelot, and mixed-run work. Git status at end: the same, plus `tests/test_phase007_balance_scenario.py`
and `docs/phases/phase007/` added.

## Limits

- The comparison covers only the 100-resident town. The method and the comparison work on any built
  pack town, but I checked only that one.
- `work_minutes_per_resident` (480) has no source in the pack. It is marked APPROX. Nothing in the
  built world measures a working day.
- `food_per_resident` is checked against a comment in the recipes doc, not against measured food need.
- Woodland is taken as the count of lumber deposits, one woodlot each. The table has no woodland key;
  the model's default of 1.0 is what is compared.
- The self-test does not check the drift. It has no built world, so the guard is in the test file.

## Open questions

1. Grain beds: should the world build 80 grain beds (fix both causes above, a behaviour change in
   founding crop yields), or should the scenario describe 61? I recommend the first, since the pack and
   docstring say 80. Then remove the xfail marker; strict xfail fails once the bug is fixed, which forces that edit.
2. Should `woodland` be added to the pack table explicitly, so the model does not depend on its default?
3. Is 480 working minutes per period sourced anywhere? If not, record it as APPROX in the pack.

## Supervisor review: grain beds fixed

Decision: the world should build the 80 grain beds the scenario and the docstring describe.

- `_seed_village_crops` now sows each crop up to its BALANCE_SCENARIO bed count, round-robin, skipping a
  crop once it has its count or its seed runs out. The founding beds count toward the totals, and the
  garden beds are not counted against the grain target. `populate_town100` calls it with no target.
- `packs/bigville/world/starting_stock.json`: barley_seed 20 -> 27 and oats_seed 20 -> 26, so the seed
  covers the scenario's beds (wheat 27, barley 27, oats 26). wheat_seed stays 40 and 13 remain in reserve.
- The built town's beds: wheat 21 -> 27, barley 20 -> 27, oats 20 -> 26 (61 -> 80 grain beds). The
  garden beds are unchanged (one each).
- `tests/test_phase007_balance_scenario.py`: the strict xfail is removed and the comparison now expects
  full agreement.
- No existing test changed. The suite (other session's three Ocelot files ignored) gives 542 passed,
  2 skipped.
