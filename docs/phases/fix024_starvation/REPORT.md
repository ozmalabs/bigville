# fix024: starvation in the town100 simple-backend game

## Summary

The regression is fixed for the measured runs. The town100 game with simple backends (seed 305017,
`ticks_per_period=96`) lost 95 of 100 residents to starvation by turn 95 before this change. After it, the
probe reports 0 deaths at 192 turns and 0 deaths at 384 turns. Two changes did the work:

1. `HUNGER_PER_STAMINA` 1.0 -> 0.2 (both packs). Phase 027 made a meal relieve one loaf (1.0 hunger), but this
   constant stayed on the old scale where a meal relieved about 5. Exertion therefore added five times too much hunger.
2. In the simple backend's `decide`, a resident at hunger >= `HUNGER_BEFORE_SLEEP` (1.0) with a food fetch or move
   in reach counts as fed first, so it does not sleep before going for food. Unlike the brief's wording, the
   awake rest is not held back by food in reach (see Deviations).

Repeated-collapse deaths (Phase 037) were 3 of 6 deaths in the intermediate run (variant A: the constant change plus
the food gate on the awake rest too). Letting the awake rest win over food in reach removed them.

## Changes

Files I changed or created (other uncommitted work in this checkout is not mine and is not listed):

- `packs/bigville/world/constants.json`: `HUNGER_PER_STAMINA` 1.0 -> 0.2; its `_doc` entry rewritten (the
  old text said a meal relieves about 5, and that is no longer true).
- `packs/test_hamlet/world/constants.json`: `HUNGER_PER_STAMINA` 1.0 -> 0.2. Its `_doc` names the table entries
  without values, so I did not change it.
- `bigville/backends/cheap.py` (my hunks only; the Phase 034 hunks in this file are not mine):
  - module constant `HUNGER_BEFORE_SLEEP = 1.0` after `RESUME_JOB_BONUS`, with a comment.
  - in `decide`, after the `fed_first` line: `food_in_reach` (hunger >= HUNGER_BEFORE_SLEEP and an option with
    action fetch or move carrying `food`, `fetch_kind`, or `physical_source == "container"`); `held_meal_first`
    keeps the old value of `fed_first`; `fed_first` is extended by `food_in_reach`. The sleep gate uses `fed_first`
    as before.
  - the awake rest gate uses `held_meal_first` instead of `fed_first`.
- `tests/test_phase050_resolution.py`: one assertion changed (see Changed numbers and tests).
- `tests/test_phase058_persona.py`: the reference file changed (see below).
- `tests/test_fix024_starvation.py` (new): regression test, 97 turns, no starvation deaths.
- `docs/phases/fix024_starvation/`: this report, probe output, and the recorded behaviour file (`behaviour_after_fix024.json`).
  The probe scripts are copied here: `death_probe.py`, `hunger_probe.py`, and `fix024_decide_log.py`, my decision log.

Phase 059's autopilot lives in `bigville/backends/autopilot.py`, `domains/autopilot.py`, and the LLM backend, not
in `cheap.py`'s `decide`. The `fed_first` gate in `decide` is still the equivalent place, so I did not touch
autopilot code.

## Design

- Hunger scale: hunger rises 1.0 per period and starvation harm applies above `starve_limit` (4.0). A loaf meal
  relieves 1.0 (`feeds`: 1.0 for bread-type items). `HUNGER_PER_STAMINA` 0.2 is 1.0 of the old design divided by the
  old meal of 5. A heavy recipe (stamina_cost ~0.4) now adds about 0.08 of a loaf-meal per use. APPROX: derived from
  the old design's own figures; no real-world source.
- `HUNGER_BEFORE_SLEEP` (1.0, one unmet loaf-meal): a valuation in `cheap.py`, not a pack value. It is the level at
  which the simple resident prefers food to sleep or rest.
- The collapse guard (sleep when energy < 20 on a safe spot) stays behind the food gate. I tested the alternative:
  see Validation, variant B.

## Validation

Probe: `PYTHONPATH=. python3 /tmp/death_probe.py N` (copied to this directory). Simple backends, seed 305017.

| Run | Turns | Deaths | Causes | First death |
|---|---|---|---|---|
| Before (HEAD + other uncommitted work, my hunks reverted) | 192 | 95 | starvation 95 | turn 95 |
| Before (same tree) | 384 | 95 | starvation 95 | turn 95 |
| Intermediate: constant only plus food gate on rest too (variant A) | 384 | 6 | exhaustion 3, starvation 3 | turn 243 |
| Variant B: collapse guard overrides food in reach (on top of A) | 384 | 7 | starvation 7 | turn 287 |
| Variant C: food gate on sleep only, rest unblocked (**final**) | 192 | 0 | none | none |
| Variant C (**final**) | 384 | 0 | none | none |

Variant A's 192-turn run: 0 deaths (`probe_v1_192.txt`). Variants A and B were run in scratch copies; the final
tree is variant C. Output: `probe_before_384.txt`, `probe_v1_384.txt`, `probe_final_192.txt`, `probe_final_384.txt`.

Hunger probe (`hunger_probe.py`, 96 turns, town100 simple): hunger at turn 94, mean / max / residents collapsed:
before 3.45 / 4.77 / 18; final 0.63 / 0.91 / 0 (`hunger_probe_before.txt`, `hunger_probe_final.txt`).

Diagnosis of the 384-turn residue (A): the starvation victims slept at hunger 3.7 with no food option visible,
because asleep residents get no affordances and the store's fetch appears only near the store (`decide_log_v1_starve.txt`).
The exhaustion victims had food in reach at energy 25-35, so the food gate blocked their rest; they walked to
food, drained stamina, and collapsed again (`diag_v1_384.txt`). Phase 037's rule then charged 0.1 health for each
collapse past the first in a run.

Commands and results:

- `python3 domains/bigville_entities.py`: ERRORS (0), WARNINGS (0). Balance, jobs, and people sections print no
  issue lines (`selftest.txt`).
- `python3 -m domains.check --pack test_hamlet`: ERRORS (0), WARNINGS (0) (`check_hamlet.txt`); the same for
  `--pack bigville` (`check_bigville.txt`).
- `python3 tools/generate_seeds.py --check`: matches (`seeds_check.txt`).
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase013a_packs.py`: 8 passed (pack bytes unchanged in the exporter layout).
- Golden script `docs/phases/phase050/golden_before.py`: output recorded in `golden_after_hpst.txt`. Changed lines
  (old log -> now): `plough spend hunger0 (0.4, 0.025)` -> `(0.4, 0.005)`; `plough spend hunger2 (0.6, 2.0375)` ->
  `(0.6, 2.0075)`; `knife spend hunger0 (0.15, 0.025)` -> `(0.15, 0.005)`. The `.py` has no literal numbers and is
  unchanged. `golden_before.log` is history and is unchanged.
- Regression test `tests/test_fix024_starvation.py`: passes on the fixed tree. On a copy with my hunks reverted it
  fails (`regression_on_baseline.txt`, 1 failed). Runtime: 193 s for the 110-turn version with the hunger probe
  running alongside; 177 s for the 97-turn version on the baseline copy under load. I did not time the 97-turn
  version alone.
- Full suite: `python3 -m pytest -q -p no:cacheprovider` (log: `full_pytest.log`): **7 failed, 1608 passed, 3 skipped**
  in 1100 s. Another session's pytest also ran in this checkout during that time.
  - 3 failures, the known baseline: `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
    `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
    `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`.
    All fail with `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`.
  - 4 failures in `tests/test_phase057_tui.py` (`test_over_http_a_menu_row_is_bound_by_the_server_and_the_world_enacts_it`,
    `test_over_http_walking_to_a_known_place_sends_the_rows_destination`, `test_over_http_a_reaction_is_delivered_to_the_holder`,
    `test_the_server_refuses_a_bad_reply_and_a_reaction_nobody_is_waiting_for`). They also fail on the baseline copy with
    my hunks reverted (4 failed, 44 passed), so this change does not cause them. They touch the untracked TUI and
    server work in progress from another session.
  - The phase 058 persona pin passes with the re-recorded reference (see below). An earlier full run before the
    re-record had 4 failures: those 3 ocelot tests and that pin.

## Changed numbers and tests

- `HUNGER_PER_STAMINA`: 1.0 -> 0.2 in `packs/bigville/world/constants.json` and `packs/test_hamlet/world/constants.json`.
- `tests/test_phase022_recipe_stamina.py`: no change. Its hunger assertions use `E.HUNGER_PER_STAMINA` by name, and they pass.
- `tests/test_phase024_exhaustion.py`: no change; passes.
- `tests/test_phase050_resolution.py::test_smashing_a_wooden_chest_damages_it_each_attempt_until_it_breaks_and_then_it_is_refused`:
  `assert any(d == 0.0 for d in falls), "a worn hammer makes no progress (Phase 048)"` -> `assert falls[-1] < falls[0], "a worn hammer does less per attempt (Phase 048)"`.
  Why: the zero-progress attempts came from exertion hunger draining Ada's reserve (the attempt clamps to the
  reserve). With 0.2 the reserve lasts the 9 attempts and no zero appears. With hunger held at 0 the zero never
  appears at either constant, so it was never a hammer effect. Hammer wear still shows: progress falls from 0.121
  to 0.066. Flagged for review: this replaces an assertion, not only a number.
- `tests/test_phase058_persona.py::test_the_simple_backend_takes_the_same_actions_as_before_for_50_turns`: the reference
  file changed from `docs/phases/phase058/behaviour_before.json` to `docs/phases/fix024_starvation/behaviour_after_fix024.json`,
  recorded with `measure_behaviour.py --label after_fix024 --turns 50 --seeding off`. Why: the five sampled residents'
  action sequences change (for example Alby Marsh diverges at index 13). The action counts over 50 turns are the same as
  the first recording's (eat 4, move 3118, none 667, rest 1153, sleep 43, work 15), and mean hunger is lower
  (0.013 vs 0.066 at turn 1). The Phase 058 file is unchanged. Flagged for review: a re-pin, not an unchanged pin.
- New test: `tests/test_fix024_starvation.py`, 97 turns.

Behaviour changes that affect the 100-resident village: the town100 simple-backend run changes (the 384-turn probe, the 50-turn
pin). I did not run `run_village`, so no village numbers beyond these are measured.

## Limits

- Probes run one seed (305017) to 384 turns. Longer runs, other seeds, and LLM or Ocelot backends are not tested.
- The hunger figure of 0.2 and the 1.0 meal are APPROX (see Design). Balance was not re-derived.
- No tracing of the final (variant C) run: its zero deaths are measured, its hunger path is not, past the hunger
  probe's 96 turns.
- `HUNGER_BEFORE_SLEEP` and the rest exception are valuations picked from the trace above, tested on one seed.
- The sleep-blindness finding (a sleeping resident cannot see food, so a hungry resident who sleeps may wake next to no food)
  is not fixed. On this seed the final tree had no starvation deaths; I did not trace whether the sleep-while-hungry
  pattern still occurs in it.

## Deviations from the brief

- The brief's food-first gate applies to sleep and rest. I left the awake rest out of the food gate. Variant A (gate
  on rest too) had exhaustion deaths; the trace showed exhausted residents walking to food and collapsing. Variant C has
  0 deaths at 384 turns.
- I tested the brief's question on the collapse guard: letting the guard win over food in reach (variant B) gave 7
  starvation deaths, so the guard stays behind the food gate.
- The Phase 058 pin is re-recorded rather than left failing, and one Phase 050 assertion is replaced. Both are listed
  above for review.
- The regression test runs 97 turns. That is the shortest run that still shows the bug (first death at step 96), and
  it takes about two to three minutes, a little over the ~2 minute target.
- `packs/test_hamlet` `_doc` names the entries without values, so it was not edited.

## Open questions

1. Should the simple resident see food beyond the world's store affordance (the world does not publish food while
   the resident sleeps, and the store appears only nearby)? That is a world publication decision, not a backend one.
2. Phase 037's repeated-collapse rule (`exhaustion_harm` 0.1, `exhaustion_window_periods` 3) was not changed. Should it
   stay as it is with the rest exception in place?
3. Is 0.2 right for `HUNGER_PER_STAMINA`, or should it be re-derived from the balance model's food needs?
4. The two test changes (Phase 050 assertion, Phase 058 reference) need your review.

## Follow-ups

- Trace a 384-turn run with the final tree to confirm hunger stays low for the whole run, not only day 1.
- Run the 100-resident village (`run_village`) in the background to see the effect on the long run.
