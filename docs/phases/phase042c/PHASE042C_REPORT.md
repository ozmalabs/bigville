# Phase 042c report: the lamplighter acts from a sense of duty

Base: HEAD `709fde9` (Phase 071c). The shared checkout had uncommitted work from other sessions (`domains/world_affordances.py`, `domains/bigville_entities.py`, `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`, `worlds/bigville_world.py`, and others). I did not edit those files in the working tree. All building and verification ran in a clean tree from `docs/phases/phase042c/build_clean_tree.py` (`git archive HEAD`, the copies in `hunks.json`, the `delete`, and five anchored hunks).

**The working tree is not runnable until the anchored hunks are applied.** `bigville/backends/duty.py` imports `DUTIES` from `domains/world_affordances.py`, and cheap.py imports duty.py. Without the hunks the backend fails to import. The commit must include the hunks listed under Changes.

## Summary

The hard-coded lamplighter round (Phase 042b's `lamplighter.py`, with its STARVE_GUARD, HUNGER_FIRST, ROUND_REST_ENERGY, WALK_ENERGY and DUSK_READY_ENERGY) is gone. The lamp work is now a job duty, a drive on one urgency scale:

- The world publishes physical facts on the lamplighter's offers: how many lamps are unlit (light) or lit (douse), and the hours until each change is due, from the sky (`worlds/daynight.py` `lamp_facts`).
- `bigville/backends/duty.py` turns them into a due level (0 to 1). The urgency is the resident's `role_identity` times the due level.
- The duty holds (it is the whole choice) when its urgency is above the larger of two need urgencies: hunger / starve_limit (1.0 at starvation) and tiredness (1.0 at collapse). A dutiful resident forgoes a meal or a sleep. A lax one does not. Starvation and collapse end any duty.
- When the duty does not hold, its offers get a bonus in the existing CAN weighting, so they compete with other options as before.
- Valuations (lead, floor, ramp, in-place bonus) are in the pack table `DUTIES` (`packs/bigville/world/duty.json`), APPROX.

**Result: the lamps are lit later than under 042b.** Over 7 game days on seed 305000 (lamplighter role_identity 0.888), all four lamps were lit a median of 9.1 hours after sunset. Phase 042b's median on the same seed was 5.1 hours (042b's range was 1.1 to 5.5). The lamplighter was asleep for 13 to 16 of the 16 ticks in the four hours after sunset on all five nights. The cause is energy: he spends the afternoon walking and tiring himself. The duty's dusk urgency is `role_identity` x 0.5 at sunset, rising to `role_identity` three hours after sunset, and it loses to his tiredness, so he sleeps before he lights. The dawn douse is similar to 042b (1 to 9 hours after sunrise, median about 6, against 1 to 7 before).

- The duty works as a trait: the lamp work over days 0 to 4 rises with role_identity (8, 32 and 44 lamp actions for 0.1, 0.5 and 0.888/0.9), and so does the hungry work (0, 16 and 43 hungry ticks spent on duty).
- Hunger does not rise with role_identity in the mean (1.07, 1.18, 1.16 over days 0 to 4). The brief expected a high-duty lamplighter to suffer more hunger. The data does not show it at the mean. It shows more hungry ticks on duty.
- Town survival (100 of 100) holds through day 2 on both seeds. The town then starves on days 4 to 6 with the lamplighter, and HEAD (042b) does the same on the same seed. This is the simple backend's food supply, not a duty effect. Seven-day "100 of 100" was not achieved with HEAD or with this phase.
- `DAYNIGHT.enabled` stays off. See the recommendation under Limits.

## Changes

### Files created

| File | What |
|---|---|
| `bigville/backends/duty.py` | The duty drive: `due_level`, `need_urgencies`, `duty_drive` (None unless an offer carries `duty` for a job in DUTIES), `DutyDrive` (holds, bonus, scored, trace), `duty_action`. |
| `domains/duty_check.py` | Self-test checks for DUTIES: job in JOBS, task in LABOUR_TASKS, acts in MAJOR_ACTIONS, valuations in range, the lamplighter's duty present, and its `lead_hours` equal to `DAYNIGHT.lamplighter_dusk_lead_hours`. |
| `packs/bigville/world/duty.json` | Table `DUTIES`: `lamplighter` (task lamplighting, acts light and douse, lead_hours 6.0, due_floor 0.5, ramp_hours 3.0, in_place_bonus 2.0, score_weight 6.0). Exporter-canonical. |
| `packs/test_hamlet/world/duty.json` | Table `DUTIES` empty (the test pack has no lamplighter; its `lamplighter_job` is empty). Every bound table name must resolve. |
| `tests/test_phase042c_duty.py` | 25 tests: due level, urgencies, holding rule, backend choice, lamp facts, pack tables. |
| `docs/phases/phase042c/` | This report, `build_clean_tree.py`, `hunks.json`, `duty_run.py` (the day run, adapted from 042b's `three_day_run.py` with `--seed` and `--role`), `summarise_runs.py`, `runs/` (7-day runs and the sensitivity run), `logs/`. |

### Files changed in the working tree

| File | Change |
|---|---|
| `worlds/daynight.py` | `lamp_facts` (new); `lamp_options` publishes `duty` on the light, douse and station walk offers; adds a pre-dawn walk (`near_dawn`) and a standby rest at the station before a due time, when no lamp is to be lit or doused from there; removes 042b's `dusk_ready` and `post` rests; module doc. |
| `bigville/backends/cheap.py` | Imports `duty`; the lamp round block is replaced by a duty block (a holding duty is the choice, `reason` "duty"); the weighted score adds `duty.bonus(candidate)`. Three hunks, nothing else. |
| `bigville/backends/lamplighter.py` | **Deleted.** |
| `domains/daynight_check.py` | A comment only. |
| `packs/bigville/world/daynight.json` | `_doc` only (the round's file is gone; the lead is now also the duty's). Data unchanged. Exporter output identical. |
| `tests/test_phase042b_lamplighter.py` | Section 1 removed (10 tests, below). Section 2 and 3 unchanged. |
| `tests/test_phase042_daynight.py` | One test replaced, and its import (below). |

### Shared-file hunks (anchored; the working-tree copies are not written)

| File | Anchor (HEAD text, asserted once) | Change |
|---|---|---|
| `domains/world_affordances.py` | the `DAYNIGHT_LAMPS = _PACK["DAYNIGHT_LAMPS"]` binding | adds `DUTIES = _PACK["DUTIES"]` |
| `domains/bigville_entities.py` | the `from domains import daynight_check as _daynight_check` import | adds `from domains import duty_check as _duty_check` |
| `domains/bigville_entities.py` | the `founding_map=FOUNDING_MAP, time=TIME)   # Phase 042` end of the daynight check call | adds the `_duty_check.check(...)` call |
| `packs/bigville/pack.json` | the last table entry (`BODY_AGE`) and the closing brackets | adds `{"name": "DUTIES", "file": "world/duty.json"}` |
| `packs/test_hamlet/pack.json` | the same | the same entry, for test_hamlet |

The builder applies several anchors to one file in turn (a fix made during this phase; each anchor is asserted once in HEAD).

### Deleted round, and the offers it used

The round's order and constants are removed. The world's offers changed as follows, because the duty needs facts the old offers did not carry:

1. Every light, douse and station-walk offer carries `duty`: `{job, light_pending, light_hours, douse_pending, douse_hours}`. These are facts, not choices.
2. `light_pending` is zero while the store has no oil (a light would be refused `out_of_stock`).
3. The station walk also appears before dawn in the dark (`near_dawn`, the same 6 h lead as dusk), so the lamplighter walks back before the douse.
4. At the station, with nothing to light or douse from there and a due time within the lead, the world offers a `rest` (purpose `standby`) with the facts. Without it nothing holds the lamplighter at the station after the lamps are lit.
5. The `dusk_ready` and `post` rests are removed. A rest is now a need or a duty act.

No world rule changed, and Phase 049's `exhausted` refusals are unchanged.

### Tests changed

| Test | Change | Reason |
|---|---|---|
| `test_phase042b_lamplighter.py`: `test_the_round_is_empty_for_a_resident_who_is_not_the_lamplighter` | removed | tested `lamplighter_choice`, which is deleted. Intent (non-lamplighters get no choice) is in `test_with_no_duty_due_there_is_no_drive` and `test_a_resident_with_no_duty_offer_takes_the_ordinary_choice`. |
| same file: `test_lamp_work_is_done_at_once_when_it_is_offered` | removed | round constant behaviour. Lamp work due and dutiful: `test_a_dutiful_lamplighter_lights_the_lamp_before_he_eats`. |
| same file: `test_a_held_meal_comes_first_when_hungry` | removed | the round's hunger threshold. Replaced by the holding rule: `test_a_dutiful_lamplighter_holds_his_duty_over_a_meal` and `test_a_lax_lamplighter_does_not_hold_his_duty_over_a_meal`. |
| same file: `test_lamp_work_comes_before_food_when_hungry_and_no_meal_is_held` | removed | same as above; `test_a_dutiful_lamplighter_lights_the_lamp_before_he_eats`. |
| same file: `test_the_starvation_guard_yields_to_the_ordinary_policy_whatever_is_offered` | removed | STARVE_GUARD is gone. `test_starvation_ends_a_duty_whatever_the_role`. |
| same file: `test_by_day_a_tired_lamplighter_rests_before_any_walk` | removed | ROUND_REST_ENERGY is gone. `test_a_dutiful_lamplighter_keeps_lamp_work_at_low_energy_above_collapse`, `test_collapse_ends_a_duty_whatever_the_role`. |
| same file: `test_at_night_a_tired_lamplighter_yields_to_the_ordinary_sleep` | removed | the round's yield. The sleep decision is the ordinary policy's (unchanged); the duty holding is in the 042c tests. |
| same file: `test_a_walk_to_the_station_starts_only_with_energy_to_spare` | removed | WALK_ENERGY is gone. **No test now covers walks at low energy.** The world's Phase 049 refusals still apply. |
| same file: `test_a_hungry_lamplighter_walks_to_the_station_only_when_lamp_work_is_due` | removed | the round's due rule. The world's `due` flag is still tested by `test_the_station_walk_is_offered_away_from_the_station_and_is_marked_due_at_night`. |
| same file: `test_at_the_station_the_lamplighter_rests_until_he_is_ready_for_dusk` | removed | DUSK_READY_ENERGY and the dusk rest are gone. The standby rest is tested in `test_at_the_station_before_dawn_with_the_lamps_lit_a_standby_rest_carries_the_douse_facts`. |
| `test_phase042_daynight.py`: `test_the_backend_chooses_the_lamp_round_and_the_world_does_not` | replaced by `test_the_world_offers_lamp_work_with_its_facts_and_the_backend_chooses_it` | the old one asserted the round's functions. The new one asserts that the world offers the light with facts and no rest, and that a dutiful lamplighter's duty picks the light. The intent (the world offers, the backend chooses) is kept. |
| `test_phase042_daynight.py` import | `lamplighter_choice` replaced by `duty_action, duty_drive` | the module is deleted. |

No other existing assertion changed. `test_a_lamp_round_is_not_offered_to_a_resident_who_is_too_exhausted_to_walk` keeps its assertion (no `move` offered while exhausted); only its name mentions the round.

## Validation

All commands were run in the clean tree `/tmp/p42c/final` (built by `build_clean_tree.py` at HEAD `709fde9`), unless noted. The 7-day runs used `/tmp/p42c/clean3`, which differs from `final` only in comments and `_doc` text (checked: the 60-turn behaviour is identical in both; the code is the same).

| Check | Command | Result |
|---|---|---|
| Build | `python3 docs/phases/phase042c/build_clean_tree.py --out /tmp/p42c/final` | HEAD archived; 11 copies, 1 delete, 5 anchored hunks (`logs/build_clean_tree_final.log`) |
| Entity self-test | `python3 domains/bigville_entities.py` | exit 0; **ERRORS 0; WARNINGS 0** (`logs/selftest_bigville_final.log`) |
| Pack check, bigville | `python3 -m domains.check --pack bigville` | exit 0; ERRORS 0; WARNINGS 0 |
| Pack check, test_hamlet | `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS 0; WARNINGS 0 |
| Pack canonical | `python3 tools/export_pack.py --pack bigville --out DIR` (and test_hamlet) | `world/duty.json`, `world/daynight.json` and both `pack.json` files byte-identical to the exporter output |
| Focused tests | `python3 -m pytest -q -p no:cacheprovider tests/test_phase042b_lamplighter.py tests/test_phase042_daynight.py tests/test_phase042c_duty.py tests/test_phase049_consequences.py` | **77 passed** (`logs/pytest_focused_final.log`) |
| 60 turns, DAYNIGHT off | `PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label h60 --turns 60` (HEAD archive, and final) | JSON identical to HEAD except `elapsed_seconds` (`logs/behaviour_60_head.json`, `logs/behaviour_60_final.json`); 100 per-resident digests equal |
| Full suite | `python3 -m pytest -q -p no:cacheprovider`, background | 4 failed (all pre-existing), 3025 passed, 6 skipped |

**Full suite** (bare `python3 -m pytest -q -p no:cacheprovider` in `/tmp/p42c/final`, background, 2271 s; `logs/full_suite.log`): **4 failed, 3025 passed, 6 skipped.** The four failures are the pre-existing ones the brief names, with the same assertions: `tests/test_fix_llm_checkpoint.py` (`digest[0]`), `tests/test_package15_resource_social_stress.py` (policy pair), `tests/test_phase058_persona.py` (50-turn hunger reference), and `tests/test_phase060_speech_in.py` (`heard > 0`, got 0). `tests/management/test_cast_browser.py` passed in this run.

### Seven-day runs (DAYNIGHT on, town100, simple backend)

`docs/phases/phase042c/duty_run.py`, 672 ticks (7 game days) per run. Each run's per-day table, with the lamplighter's lows and the town count, is in `logs/summary_tables.md`. Per-tick data: `runs/<name>/duty_ticks.jsonl`. The run names are the letters in the first column: A and B are 042c on seeds 305000 and 305001; C and D are HEAD (042b) on the same seeds; E, F and G are 042c on 305000 with role_identity 0.1, 0.5 and 0.9; `sens_due_floor_0.9_G3` is the sensitivity run (3 days).

Hours after sunset until all four lamps are lit (dusk), and hours after sunrise until all four are dark (dawn). A dash means the event did not happen that day. "Town" is residents alive at the day's end.

| Run | Seed | role_identity | Dusk lit, days 0 to 4 (h after sunset) | Dawn dark, days 0 to 4 (h after sunrise) | Town alive, days 0 to 4 | Lamplighter alive at day 4 |
|---|---|---|---|---|---|---|
| 042b, HEAD (C) | 305000 | 0.888 | 5.45, 1.42, 1.14, 5.11, 5.58 | –, 2.08, 6.86, 1.14, 6.42 | 100 on days 0 to 3, 98 on day 4 | yes |
| **042c (A)** | 305000 | 0.888 | **8.95, 9.92, 8.14, 9.11, 9.08** | 1.05, 6.58, 5.11, 7.64, 8.67 | 100 on days 0 to 3, 98 on day 4 | yes |
| 042b, HEAD (D) | 305001 | 0.835 | 5.45, 5.17, 3.39, 3.36, 4.33 | –, 5.33, 1.11, 1.89, 5.42 | 100 on days 0 to 4 | yes |
| **042c (B)** | 305001 | 0.835 | 3.45, 2.67, 8.89, 1.11, – | 1.05, 1.08, 1.11, –, 6.67 | 100 on days 0 to 4 | yes |
| 042c role 0.1 (E) | 305000 | 0.1 | –, –, –, –, – (4 lamp actions on day 0 only) | 1.05, 0.08, 0.11, 0.14, 0.17 | 100 on days 0 to 3, 98 on day 4 | yes |
| 042c role 0.5 (F) | 305000 | 0.5 | 8.95, 9.92, 0.14, 7.61, 0.08 | 1.05, 6.58, –, 6.39, – | 100 on days 0 to 3, 98 on day 4 | yes |
| 042c role 0.9 (G) | 305000 | 0.9 | 8.95, 9.92, 8.14, 9.11, 9.08 | as A | as A | yes |
| 042c, due floor 0.9 (sensitivity, not adopted) | 305000 | 0.9 | 8.95, 1.17, 1.14 (3 days) | 1.05, 6.58, 5.36 | 100 on days 0 to 2 | yes |

Notes on the table:

- Days 5 and 6 are not in the table. The town starves from day 5 in HEAD (18 of 100 alive at the end of day 5, 1 at the end of day 6, seed 305000) and in 042c (20 and 0). The lamplighter starves with the town in every 042c run.
- Role 0.888 (A) and 0.9 (G) give tick-identical runs (0 differing ticks). The role grid is therefore coarse above 0.9.
- The dawn value reads near 0 when no lamp was lit before dawn (the lamps were already dark). Role 0.1 lit no lamp after day 0.
- The day-0 dusk of about 9 hours occurs in every 042c run on seed 305000. The lamplighter starts that day at 06:00 in the dark, lights the lamps before dawn, and walks away (ordinary policy) with energy falling to about 14 by 16:00. He sleeps from about 16:15 and is not awake until about 23:30.
- The sensitivity run changes only `due_floor` (0.5 to 0.9) in a copy of the tree. It is not part of the phase's configuration. It shows what the due floor does to the lead: nights 1 and 2 lit within 1.2 hours. Day 0 is unchanged.

### Role-identity variation (lamp work, days 0 to 4, seed 305000)

| role_identity | Lamp actions (lights + douses) | Hungry ticks worked on duty (hunger at least 1.0) | Mean hunger, days 0 to 4 |
|---|---|---|---|
| 0.1 (E) | 8 | 0 of 239 hungry ticks | 1.07 |
| 0.5 (F) | 32 | 16 of 305 | 1.18 |
| 0.888 (A) | 44 | 43 of 310 | 1.16 |
| 0.9 (G) | 44 | 43 of 310 | 1.16 |

Lamp actions rise monotonically with role_identity. Hungry duty ticks rise too. The mean hunger does not rise monotonically (1.07, 1.18, 1.16).

## Limits

- **Dusk timing is worse than 042b.** The lamplighter sleeps through dusk when his energy is low at sunset. At sunset the duty's urgency is role x 0.5 (0.44 at role 0.888). Tiredness is above 0.44 once energy falls below about 58, so the duty loses there. Phase 042b avoided this with a rule (rest at the station to 70 before dusk). 042c has no such rule, by design (the brief asked for no special ordering), and I did not add one.
- **Valuations decide the dusk timing.** `due_floor` 0.5 and `ramp_hours` 3 are APPROX choices, not sourced. The sensitivity run shows a higher floor fixes nights 1 and 2. I did not tune the pack to the target. The choice of floor is an open question.
- **The lamplighter is appointed, not chosen.** `appoint_lamplighters` gives the job to the first adult in founding order. Role_identity is not considered. The founding draw's mean for the lamplighter job is 0.3 (`FOUNDING_JOBS`, APPROX), so most appointees are likely to be low-duty. Seeds 305000 and 305001 drew 0.888 and 0.835.
- **Town survival.** The simple backend's food supply runs out on days 4 to 6 on both seeds (HEAD included). A 7-day "100 of 100" is not reachable without a food fix.
- **Lazy mode.** The duty reads menu offers. Lazy-mode contexts carry no lamp offers (as in 042b).
- **Energy drain.** A walk at low energy costs about 10 energy in a tick (seen at energy 16 to 6). A dutiful lamplighter walks at energy 16 and reaches about 6 (collapse is 5). The duty holds until his urgency is below his tiredness, so the drain is not guarded by a rule.
- **The walk and the rest are shared with the ordinary policy.** The ordinary policy's food-first rule (`held_meal_first`) stops the rest gate when a meal is held, so a tired lamplighter with a meal held walks instead of resting. This is the simple policy's behaviour, untouched.
- **The 060 `heard` and 058 hunger tests** are pre-existing failures (see the full suite).

**Recommendation: keep `DAYNIGHT.enabled` off for the bigville pack.** The duty works as a trait, and the offers and the pack are in place. But the lamps are lit about 4 hours later than 042b's median on the default seed, the lamplighter sleeps through dusk on most nights, and the town starves on days 4 to 6 with or without the switch. Before the switch goes on, I would want: a lamp-timing target the duty meets (a higher due floor or a foresight term, decided by the supervisor), a lamplighter chosen by role_identity, and a food fix for the simple backend.

## Open questions

1. **Due floor and foresight.** The dusk timing depends on how the due level compares with tiredness. Options: a higher `due_floor` (the sensitivity run: 0.9 lights nights 1 and 2 within 1.2 hours), or a rest-before-due term, which is a need-like rule. Which should the supervisor accept?
2. **Who is the lamplighter.** Appoint by role_identity (the duty's trait), or keep founding order and set the job's drawn mean higher?
3. **Apply the hunks.** The five anchored hunks must be applied to the commit (see Changes). Until then the working tree does not import.
4. **Walk at low energy.** 042b's WALK_ENERGY rule is gone and nothing replaces it. Is the Phase 049 refusal enough, or should a walk start only with energy to spare, as a need?
5. **Oil.** Still no oil production (042b open question 4).
