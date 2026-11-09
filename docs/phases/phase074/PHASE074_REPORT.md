# Phase 074: energy and access (waiting-tick charge, walking cost, balance tool)

## Summary

- **Waiting ticks no longer cost energy.** `BigvilleWorld.move_actor` built the walking Effort before it checked
  `carry_move_cooldown`. A walker in a slow band paid a full step on each tick it did not move. The Effort is now
  minted only on a stepping tick. Step timing is unchanged. On HEAD a waiting tick drops energy from 100 to 90;
  the new test confirms it now costs nothing.
- **The 0.1 walking factor is pack data.** `CARRYING.stamina_per_move_unit` replaces the literal in `move_actor`
  (both packs). The bigville value is now **0.01** (1 energy point per flat cell, was about 10). test_hamlet keeps 0.1.
- **Value chosen by a sweep** (table below). The acceptance criteria are mixed (see Limits): the commute criterion is
  met at 0.01 and the walking-share criterion is not, and the "walking attempts that move above 85 %" target is not met
  at any value.
- **`tools/balance_run.py`** is the reusable per-day instrument, with a per-resident block added after the steer (below).
- **Effect on the default town, 3 seeds, 7 days** (before = HEAD 28be3e7; the same numbers come from 0246afc): person-days
  426 to 545, first death day 3/4/4 to 5/4/5, extinction day 5/6/5 to 6/6/6. Production rises from 0 to 72 food units and
  23 finished jobs. **The town still does not survive.** Every one of the 300 residents starves by day 5 to 7.
- **Full suite**: 3103 passed, 13 skipped, 5 failed. All 5 failures are on the pre-existing list (section Validation).

## Changes

Shared files were edited in the working tree and are built into the scratch tree from HEAD by
`docs/phases/phase074/build_clean_tree.py` using anchored hunks in `docs/phases/phase074/hunks.json` (7 hunks).

| file | change |
|---|---|
| `worlds/bigville_world.py` | `move_actor`: the cooldown check (return on a waiting tick, decrement the cooldown) now comes before the walking Effort. The Effort's cost is `effort * CARRYING["stamina_per_move_unit"]` instead of `effort * 0.1` (the same value in `intensity`). Hunks: (1) cooldown check inserted before the Effort block; (2) `stamina_cost` line added at the top of the Effort block; (3) the Effort's `intensity` and `stamina_cost` read `stamina_cost`; (4) the old cooldown block removed from below the Effort. Nothing else changed. |
| `domains/bigville_entities.py` | `_check_carrying` (new): `stamina_per_move_unit` must be a fraction in (0, 1]; it reports the flat-step cost. Called from the self-test. |
| `packs/bigville/world/carrying.json` | new key `stamina_per_move_unit: 0.01`; `_doc` explains the value, the sweep and the criterion (APPROX). Exporter output checked byte-identical. |
| `packs/test_hamlet/world/carrying.json` | new key `stamina_per_move_unit: 0.1` (its pre-074 behaviour; `_doc` says so). Exporter output checked byte-identical. |
| `tools/balance_run.py` (new) | Per-day metrics for the default town (keys in its module docstring), `--seed`/`--seeds`, `--days`, `--ticks`, `--out`, `--label`, `--set TABLE.KEY=VALUE` (in-place override of an existing key in the default pack; unknown keys stop the run). Each run also lists every resident (see below). |
| `tests/test_phase074_walking.py` (new) | Waiting tick costs no energy; stepping tick does; flat step cost equals `100 * factor * terrain multiplier`; the factor is read from the pack table (monkeypatched to 0.2). |
| `tests/test_phase074_balance_run.py` (new) | 20-tick smoke run: one partial-day row with all documented keys; unknown `--set` key is refused. |
| `tests/test_phase024_exhaustion.py` | **Expectation changed**, see "Tests whose expectation changed". |
| `docs/phases/phase074/` | this report, `build_clean_tree.py`, `hunks.json`, `runs/` (JSON and log of every run), `full_suite.log`. |

## Validation

Scratch tree: `git archive HEAD` (28be3e7) plus the build. Real tree checks:

- Entity self-test (`python3 domains/bigville_entities.py`): **ERRORS 0, WARNINGS 0** (scratch and real tree). The new
  info line: "CARRYING: stamina_per_move_unit 0.01: a flat-ground step costs 1.00 energy points of the 100-point reserve".
- `python3 -m domains.check --pack bigville` and `--pack test_hamlet`: exit 0 both.
- Exporter: `tools/export_pack.py` output for both packs, diffed with the committed files: identical.
- Focused: `tests/test_phase074_walking.py` + `tests/test_phase074_balance_run.py`: 5 passed. On HEAD the waiting-tick test fails
  (`assert 90.0 == 100.0`), so it does test the bug.
- Full suite, bare, in the scratch tree (`timeout 5400 python3 -m pytest -q -p no:cacheprovider`, 34 min):
  **3103 passed, 13 skipped, 5 failed** (`docs/phases/phase074/full_suite.log`).

Failures, with the same test on the HEAD archive (28be3e7):

| test | HEAD | this phase | note |
|---|---|---|---|
| `tests/test_phase058_persona.py::test_the_simple_backend_takes_the_same_actions_as_before_for_50_turns` | fails: hunger float at index 7 (0.116 vs 0.1159) | fails **differently**: the first mismatch is action 14 (`move` where the reference says `rest`) | Reference not re-baselined. The walking change moves the action sequence; the reference was already failing on HEAD. Not fixed here. |
| `tests/test_fix_llm_checkpoint.py::test_a_game_saved_and_loaded_continues_to_the_same_run_digest[0]` | fails | fails, different digests | Compares a resumed run with a fresh control run. No pinned constant, so nothing to re-baseline. |
| `tests/test_package15_resource_social_stress.py::test_policy_pair_has_same_setup_and_predeclared_shock_across_seeds` | fails (`0 == 1`) | fails, same message | pre-existing |
| `tests/test_phase060_speech_in.py::test_a_short_village_run_with_the_switch_on_places_and_counts_what_it_hears` | fails (`heard` 0) | fails, same message | pre-existing |
| `tests/management/test_cast_browser.py::test_cast_groups_preview_and_launch_match_actual_world` | flaky | failed in the full run; passes alone on HEAD and on this tree | flaky, as the brief says |

Tests that were expected to move in the brief but **did not** change at 0.01:
- `tests/test_bigville_world_migrated.py::test_overweight_acceptance_is_possible_but_slows_and_costs_energy` passes.
- `tests/test_lazy_work.py::test_town100_menu_run_is_unchanged` passes (counts `move` 785, `work` 15 unchanged).
- `tests/test_phase013a_packs.py::test_export_rerun_is_byte_identical` passes.
- `tests/test_phase058_persona.py` hunger reference: see the table above.
- Scenario runner digests: the full suite did not fail any digest except the checkpoint one above.

## Measurements

Sweep and before/after: `runs/*.json`, `runs/*.log`. Seeds 305000, 305001, 305002, 7 days each, default
`create_game` settings in the brief. "Flat step" is `100 * factor` points on grass (terrain multiplier 1.0). Walked tiles
have multipliers of 0.65 to 0.9, so the step cost is a little less.

Sweep (all with the wait-tick fix; the first row is HEAD without the fix):

| label | factor | flat step (points) | person-days (3 seeds) | first death day | extinct day | walk attempts that moved | energy per cell moved (points) | cells per resident per day, d0-3 | share below 35 at end of day, d0-3 | energy at 17:00 d0-2 mean / share below 35 | food produced (units, 7 d) | jobs completed | store at end of day 0,1,2,3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HEAD 28be3e7 (no wait fix, 0.1) | 0.1 | 10 | 426 [420, 425, 434] | 3, 4, 4 | 5, 6, 5 | 47.2 % | 16.3 | 14.0 | 0.487 | 42.1 / 0.49 | 0 | 0 | 760, 547, 48, 0 |
| wait fix only | 0.1 | 10 | 482 [489, 479, 477] | 4, 4, 4 | 6, 6, 6 | 46.0 % | 7.4 | 21.3 | 0.334 | 42.6 / 0.52 | 0 | 3 | 742, 471, 185, 0 |
| sweep | 0.06 | 6 | 534 [533, 536, 533] | 4, 4, 4 | 6, 6, 6 | 45.3 % | 4.4 | 27.6 | 0.393 | 37.6 / 0.59 | 6 | 6 | 712, 484, 214, 0 |
| sweep | 0.04 | 4 | 540 [540, 540, 540] | 4, 4, 4 | 6, 6, 6 | 46.2 % | 2.9 | 32.2 | 0.385 | 33.9 / 0.65 | 30 | 12 | 698, 520, 235, 0 |
| sweep | 0.03 | 3 | 539 [543, 535, 539] | 4, 4, 4 | 6, 6, 6 | 47.1 % | 2.2 | 35.2 | 0.393 | 37.5 / 0.62 | 27 | 13 | 695, 507, 242, 0 |
| sweep | 0.02 | 2 | 540 [538, 540, 543] | 4, 4, 4 | 6, 6, 6 | 48.6 % | 1.4 | 39.7 | 0.534 | 42.7 / 0.32 | 18 | 11 | 682, 500, 229, 0 |
| **chosen** | **0.01** | **1** | **545 [552, 543, 541]** | **5, 4, 5** | **6, 6, 6** | **50.8 %** | **0.7** | **46.2** | **0.343** | **47.2 / 0.37** | **72** | **23** | **645, 500, 244, 0** |

Walking share of effort (mean over day rows): 0.9999 (HEAD), 0.9996, 0.9995, 0.9994, 0.9993, 0.9986, **0.9977** (chosen).
The person-day differences from 0.02 to 0.06 are inside the seed spread (about 10), so the survival numbers do not pick
the value. The choice rests on the commute criterion, the reserve margin and production.

Choice (APPROX; the reasoning is also in the pack `_doc`). Walked tiles average about 0.8 of the flat cost (terrain
0.65 to 0.9). A rested resident (100 points) pays about 24 points for the 29-cell store trip and about 42 points for the
51-cell farm trip at 0.01. Both arrive above the 35-point rest line. At 0.02 the same trips cost about 48 and 85, so a farmer
arrives near 15 and walks in the slowest band. 0.01 also gives the most production. The criterion "walking is not 99.9 % of
effort energy" is **not met** at any value (0.9977 at the chosen value).

Before and after, same seeds, 7 days (before = HEAD 28be3e7; the 0246afc numbers are identical):

| metric | before | after (0.01) |
|---|---|---|
| survival: alive at end of day 6 | 0, 0, 0 | 0, 0, 0 |
| person-days (7 days) | 426 [420, 425, 434] | 545 [552, 543, 541] |
| first death day | 3, 4, 4 | 5, 4, 5 |
| extinct day | 5, 6, 5 | 6, 6, 6 |
| walk attempts that moved | 47.2 % | 50.8 % |
| energy per cell moved (step cost) | 16.3 points | 0.7 points |
| cells walked per resident per day, d0-3 | 14.0 | 46.2 |
| share below 35 at end of day, d0-3 | 0.487 | 0.343 |
| energy at 17:00, d0-2 mean | 42.1 | 47.2 |
| store at end of day 0, 1, 2, 3 | 760, 547, 48, 0 | 645, 500, 244, 0 |
| work starts / completions (7 days) | 39 / 0 | 57 / 23 |
| food produced (units, 7 days) | 0 | 72 |
| meals eaten (7 days, all seeds) | 2326 | 2256 |

Acceptance check:
- Walking attempts that move rise to over 85 %: **not met** (47 % to 51 %). The moved share is set by the speed bands and
  terrain interval, not by energy (my reading of the data, not a separate test). Lowering the cost changes the band a walker is in only slowly. The study found most walkers sit in the x3 band (reserve 15 to 40)
  or the x1.5 band (40 to 70). Phase 075 (rest hysteresis) is the phase that moves walkers out of those bands.
- Study criteria met: waiting tick costs no energy (test); commute and store trip reachable from a rested body (the
  arithmetic above, not a measured trip).
- Not met: walking share below 99.9 %, survival.

### Per-resident inspection (steer)

The user asked, mid-phase, to run every resident for a few days and inspect each one, to check that they work. The
inspection uses the 0.01 run (seeds 305000 to 305002, 7 days, 300 residents). Each run's JSON lists every resident:
`residents` in `runs/after_*.json` (role, alive, death cause and day, cells walked, meals, fetches, work starts and
completions, walk attempts and moves, whether the resident reached its work cell, minimum and end energy).

| role (3 seeds) | n | alive at end | reached work cell | work starts | work completions | min energy (median) | cause of death |
|---|---|---|---|---|---|---|---|
| labourer (no duty; work cell is the store) | 177 | 0 | 177 | 6 | 0 | 15.0 | starvation |
| farmer | 18 | 0 | 4 | 20 | 7 | 14.4 | starvation |
| farm_labourer | 6 | 0 | 3 | 1 | 1 | 14.7 | starvation |
| butcher | 3 | 0 | 3 | 0 | 0 | 14.2 | starvation |
| baker | 3 | 0 | 0 | 9 | 8 | 15.3 | starvation |
| miller | 3 | 0 | 0 | 3 | 2 | 15.6 | starvation |
| forester | 3 | 0 | 0 | 4 | 1 | 15.3 | starvation |
| fisher | 6 | 0 | 0 | 2 | 1 | 14.2 | starvation |
| fishmonger | 3 | 0 | 0 | 1 | 1 | 11.9 | starvation |
| dairymaid, animal_keeper | 6 | 0 | 0 | 0 | 0 | 15 to 17 | starvation |
| innkeeper | 6 | 0 | 0 | 6 | 0 | 14.9 | starvation |
| other roles (clerk, smith, mason, teacher, and so on) | 66 | 0 | 24 | 5 | 2 | 13 to 16 | starvation |

Reading: all 300 residents die of starvation. The food-producing roles (51 residents) reached their own workplace cell
in 10 cases. The other 41 did not, so they never worked there. The labourers reach the store and do not start work; the
study found the policy drops work offers for recipes the resident does not know. Work completions total 23 over three
seeds and seven days, 15 of them from farmers and bakers. The residents act (moves, meals, fetches), but the production
chain does not run. This confirms the study's picture: Phase 074 lets residents move further, and the policy and the
starting economy (Phases 075 and 076) still stop the work.

## Limits

- The town does not survive: with the chosen value, every resident starves by day 5 to 7 on all three seeds.
- The moved-share target (above 85 %) is not met, and neither is the walking-share target (99.9 %).
- The value 0.01 is APPROX and game-scale. It is not a physiological figure. The sweep varied only the walking factor;
  every row includes the wait-tick fix except the HEAD row.
- Sweep has three seeds and 7 days. Differences between 0.02 and 0.06 in person-days are within the seed spread.
- The "energy per cell moved" column is the step cost minted (the Effort's declared cost), not measured reserve drops.
  Those two agree at the step level, but the tool does not track reserve drops.
- Work completions in `tools/balance_run.py` are counted at the day's last tick (a day boundary), and food produced
  is measured with the stock-delta hook used by the study (it fails loudly if the world's internals are renamed).
- The per-resident block reports status at the end of a run. Dead residents have no end distance or energy.
- The sweep and HEAD (0246afc) runs were made before the per-resident block existed, so their JSON has no `residents` key.
  The 28be3e7 HEAD runs and the 0.01 "after" runs have it.
- Scratch tree timing: I rebuilt the scratch tree once while the "after" runs were in progress. Those runs had already
  imported all code and pack data, and the rebuilt files were identical, so the runs stand. The later test-only edit
  (below) did not touch any file those runs read.

## Open questions

1. Walking share and the moved share are set by the slow bands (reserve below 70, 40, 15) and by terrain
   `move_time`, not by the cost. Should Phase 075 move the rest threshold (the study: 70), or should the band edges
   change? The study says the rest threshold is the lever, but I did not measure it here.
2. The labourers (177 of 300) reach the store but hold no duty, so they never work. Is the job draw (Phase 077 scope)
   or the policy (Phase 075) responsible?
3. Should `tests/test_phase058_persona.py` have its reference re-baselined after Phase 075 instead of now? The reference
   already failed on HEAD, so I left it alone.
4. HEAD moved from 0246afc to 28be3e7 while this phase ran (another session's engine speedups; the strength check in
   `worlds/bigville_world.py` that appeared in the working tree for a short time was not in the commit and is not in my
   hunks). The before numbers were re-run on 28be3e7 and match 0246afc exactly.

## Tests whose expectation changed

| test | old | new | reason |
|---|---|---|---|
| `tests/test_phase024_exhaustion.py::test_a_resident_who_keeps_working_after_a_collapse_falls_again` | loop bound `range(40)` (40 ticks) | `range(200)` | A step now costs 1 point, not 10 on flat ground. Walking from the collapse cap (0.25) down to `e_collapse` (0.05) takes about 20 steps, and below `e_low` (0.15) a walker moves one cell in six ticks. The same assertion (the walker collapses) then fails inside 40 ticks. The assertion itself is unchanged. |

No other existing test expectation changed.
