# Phase 049: consequences instead of gates (Tract A)

Status: implemented, not committed. Three supervisor decisions are applied (see Summary). The default village is back
to 0 deaths in the 192-turn probe, and the 50-turn behaviour reference matches again.

## Summary

The brief's gates are converted, except where listed under Limits and where the supervisor restored a gate. A converted
gate now lets the act happen and writes its consequence to world state: quality and yield, spoiled batches, strain,
slower progress, shared progress between jobs, spilled or dropped stock, leaking vessels, a lower yield from an unripe
crop, a fussed animal. Refusals for acts that cannot happen stay (no stock, out of reach, locked, asleep, unknown
recipe, unknown target). Six reason codes are retired from both packs: `busy`, `too_tired`, `no_capacity`, `no_tool`,
`out_of_season`, `on_cooldown`. One code is added: `exhausted`.

Supervisor decisions, applied in this round:

1. **Walk below e_low (option b).** A backend plan's `move` (and a plan's walk to an animal) below e_low is refused in
   `_enact_plan` with `exhausted`, so a backend's continuation is interrupted as before the conversion. A direct world
   call (`major_action(actor, "move", ...)`) still walks at the slowest rate until the collapse.
2. **Watering an unthirsty crop.** The `not_needed` refusal is restored in `water_crop`. The water is not spent.
3. **Call-cap test.** The cause was the plan-path `rest` at a reserve of 0.8 or more. It was accepted after the
   conversion. At HEAD it was refused `not_needed`, which made the simple backend consult again on turn 1 (`task_failed`).
   Without that consult, no later consult reached the call cap. The plan-path refusal is restored. A direct
   `major_action` rest is still allowed.

Results after the three changes: the self-test has 0 errors and 0 warnings. The death probe has 0 deaths in 192 turns.
`tests/test_phase058_persona.py` (the 50-turn reference) passes. The three tests that failed because of this phase now
pass. The full suite gives 1670 passed, 7 failed, 3 skipped. The 7 failures are the non-phase failures the first round reported: 3 baseline
ocelot adapter tests and 4 TUI tests (see Validation).

## Changes

### Gate by gate

| # | Gate | Now | Terms and numbers |
|---|---|---|---|
| 1 | Skill floor (`_skilled_enough`) | Accepted. A batch's yield is scaled by min(1, skill / min_skill). A batch with skill below `skill_ruin_ratio` of the floor is spoiled: inputs used, nothing made. A heavy trade (strength demand > 0) strains its worker by the skill shortfall, through Phase 050's strain term. | `skill_ruin_ratio` 0.5 (APPROX). Quality already equalled the skill level. |
| 2 | Season: gather | Accepted. The batch's yield is scaled by `off_season_yield`, fixed when the job opens. | 0.25 (APPROX). Woodlot and orchard gathering only: the nine seasonal recipes. |
| 2 | Season: sow | Accepted. The seed is used. The crop gets `season_fail` and dies at the next period. | No new number. |
| 3 | Strength | Accepted. Progress per tick is multiplied by min(1, strength / demand). Effort already scaled by demand / strength (Phase 050 cost ratio). Shortfall strains the worker. | Committed rate kept at or above the demand. |
| 4 | Busy | Accepted. Each open job of a worker advances at speed / (number of open jobs), and the stamina spent follows the progress. `stop_job(actor, job)` ends a named job. | None. |
| 5 | Serving equipment in `eat` | Accepted. Without the vessel or utensil, or from a vessel too small, the meal's value is scaled by 1 - `unserved_waste`. | 0.25 (APPROX). |
| 6 | Watertight vessel in `put` | Accepted. A non-watertight vessel keeps its fluid, and loses `leak_per_period` of each fluid every period. | 0.1 per period (APPROX). |
| 7 | Over capacity: `give`, `transfer`, `fetch`, `put`, `eat` | Accepted. The receiver or carrier takes what fits by volume, and the excess drops as a `DroppedStock` at its feet (`put` drops it at the actor's cell). Source loses the full amount. Load overflow keeps the existing `_accept_stock` drop. Slowing under load already existed (`carry_state`). | None. |
| 8 | Pointless acts | Accepted: `sleep` at a full reserve, `care` on someone not in need. **Kept as refusals (supervisor):** `rest` at reserve >= 0.8 on the plan path (`not_needed`; a direct `major_action` rest is allowed), and `water` on an unthirsty crop (`not_needed`). | None. |
| 9 | Too tired to walk | Accepted in the world. Below e_low a direct walk moves at 0.5 of 3 moves per tick (speed 1/6, interval 6). It stops at the collapse. **Backend plans:** a `move` below e_low is refused `exhausted` (in `_enact_plan`, also for a plan's walk to an animal). Offers still hide moves below e_low. | `EXHAUSTION.moves_per_tick[3]` 0 -> 0.5 (APPROX). Self-test requires a positive last count. |
| 10 | Unripe harvest | Accepted. Yield = yield x maturity (age / grow_periods, capped at 1) x nitrogen factor. The crop is gone. Seed return scales by maturity too. Mature crops are unchanged. Burial `not_ready` stays. | None. |
| 11 | Animal tended too soon | Accepted. Yields nothing, uses the slot, and sets the animal's `fussed` count. | None. |
| 12 | Reason codes | `busy`, `too_tired`, `no_capacity`, `no_tool`, `out_of_season`, `on_cooldown` removed from both `refusal_reasons.json` files. `exhausted` added to both (the plan-path walk refusal). The `not_needed` description is back to its HEAD wording, because its restored gates are live again. See Open questions (3) for the codes kept. | None. |

Named tool the worker does not hold (`no_tool` in recipes, attempts and displacement) is no longer refused. The work
goes on with bare hands (`hands_fit`). The brief retires the code, and Phase 048 had already set this rule for
recipes. This is a decision; it is listed in Open questions.

### Files changed

- `worlds/bigville_world.py` (shared). My hunks, by function: `_recipe_refusal`; `_tool_choice`; `_attempt_verb`;
  `_displace_verb`; `_resolve_jobs` (job progress with `_jobs_sharing` and `_job_strength_rate`, the completion skill
  and season terms, and the busy flag at completion); `_open_job` (`season_yield`); new `_skill_share_of_floor`,
  `_job_strength_rate`, `_jobs_sharing`; `stop_job` (optional job); `_resolve_period_effects` (season-failed crops);
  `_move_stock_to_inventory`; `_move_inventory_to_inventory` (returns the amount taken); `give` (uses the amount
  taken); `_physical_transfer_precheck`; `eat`; `_husbandry_yield`; new `_tend_outcome`; `harvest_crop`; `sow`;
  `care_for`; `water_crop` (the `not_needed` gate restored in this round); new `_leak_containers` and its call in
  `pass_period`; `put`; `_major_action_attempt` (move, sleep); `_enact_plan` (the `move` and `tend_animals` walk
  branches refuse `exhausted` below e_low; the `rest` branch restores `not_needed` at reserve >= 0.8);
  `_exhaustion_band` (new key `below_e_low`); `actor_affordances`' move filter (now `below_e_low`). Tract B's hunks
  (`_actor_options` food flag, `resident_plan_from_context`) are untouched.
- `domains/bigville_entities.py` (shared). Self-test: `too_tired` and `no_tool` no longer required codes; moves check
  allows a positive last count; four new RESOLUTION keys checked to lie in [0, 1]. Tract B's hunk at about line 1884
  is untouched.
- `packs/bigville/world/refusal_reasons.json`, `packs/test_hamlet/world/refusal_reasons.json`: six codes removed; new
  `exhausted` code; three descriptions reworded (`not_ready`, `not_needed`, `unskilled`). The `not_needed` text is now
  the HEAD wording again, because its rest and crop cases are live again.
- `packs/bigville/world/resolution.json`, `packs/test_hamlet/world/resolution.json`: keys `skill_ruin_ratio`,
  `off_season_yield`, `unserved_waste`, `leak_per_period`; doc paragraph "PHASE 049 KEYS".
- `packs/bigville/world/exhaustion.json`, `packs/test_hamlet/world/exhaustion.json`: `moves_per_tick` last count 0.5.
- `tests/test_phase049_consequences.py` (new, 17 tests). The watering test is changed in this round (see below).
- Existing tests edited (each listed below).

Not touched: `bigville/backends/cheap.py`, `psi_can.py`, `bigville/game.py`, `packs/*/pack.json`,
`packs/*/world/prompt_packet.json`, the seeds, `docs/FEATURE_PHASES.md`, the snapshot fixture
`tests/fixtures/phase054_packet_snapshot.json`. No MAJOR_ACTION or FREE_ACTION was added, so no snapshot change is
needed.

### Existing tests changed (old -> new, and why)

Each change replaces an assertion of the refusal the brief converts. None removes a test. In this round, the two
edits to `test_phase020_validation.py` and `test_phase021_refusals.py` were reverted to HEAD, because the plan-path
rest refusal is restored. Those files now match HEAD.

- `test_phase023_job_occupancy.py`: `test_busy_is_a_refusal_reason_in_the_pack` -> `..._no_longer_a_refusal_reason...`
  (busy absent); `test_a_second_start_while_busy_is_refused` -> `..._is_accepted_and_shares_the_progress` (two jobs,
  each advances 0.5 per tick); `test_a_refused_start_while_busy_publishes_...` -> `test_stop_ends_one_of_a_workers_two_jobs`.
- `test_phase024_exhaustion.py`: `too_tired` removed from the required codes; `moves_per_tick` [3,2,1,0] -> [3,2,1,0.5];
  `test_a_resident_below_e_low_cannot_start_a_walk` -> `..._still_walks_until_the_collapse` (direct walk accepted, speed
  1/6, stops at the collapse); `test_sleep_is_refused_when_rested_...` -> `test_a_sleep_at_a_full_reserve_is_allowed_...`;
  `test_a_worker_too_exhausted_to_walk_does_not_advance_the_job` -> `..._below_e_low_advances_a_timed_job_at_the_slowest_rate`
  (advance 1/6 per tick; was 0).
- `test_phase032_training.py`: `..._can_attempt_a_recipe_that_was_above_them_...` (start accepted, job stopped before
  the training loop; the offer still withholds it); `test_a_low_health_smith_cannot_forge_a_knife...` ->
  `..._forges_a_knife_at_a_cost_until_healthy`.
- `test_phase034_intoxication.py`: the drunk smith below the floor starts the plough (the batch is poorer), then
  sober starts it too.
- `test_phase050_resolution.py`: `..._not_hold_is_refused_as_no_tool` -> `..._is_used_with_bare_hands`;
  `test_a_frail_resident_with_a_spoon...` checks the spoon's first attempt (progress 0, as before; later attempts
  now run on bare hands once the spoon breaks); `test_a_spent_reserve_lowers_the_ceiling_to_nothing` ->
  `..._to_the_slowest_rate` (ceiling = max_intensity / 6 = 0.5, was 0).
- `test_phase048_tool_fitness.py`: the saw the smith does not hold is a bare-hand job (fit = `hands_fit`), not `no_tool`.
- `test_bigville_world_migrated.py`: `test_crops_are_sown_only_in_their_season` ->
  `test_crops_are_sown_in_their_season_and_an_out_of_season_sowing_fails` (turnip seed used; crop dies after a period);
  the soup test (a meal eaten bare-handed is accepted; a second meal is then served with bowl and ladle); the tailoring
  test `test_fine_tailoring...` (poorer batch, no refusal) and `test_you_cannot_read_your_way...` (Nan's batch is
  spoiled: silk used, no gown).
- `test_simple_crop_water.py`: `sow` out of season returns a crop and uses the seed; the crop dies after a period. The
  test's name and its affordance check are unchanged.
- `test_simple_tools_materials_job.py`: the bare-hand loop keeps the worker rested and whole (see Limits: a bare-hand
  job drains its worker). The test's assertions are unchanged.
- `test_phase021_refusals.py` and `test_phase020_validation.py`: edited in the first round, reverted to HEAD in this
  round (see above). Net change: none.

Changed in this round, in my own new file `tests/test_phase049_consequences.py`:
- `test_watering_an_unthirsty_crop_spends_the_water_and_does_nothing_else` -> `test_watering_an_unthirsty_crop_is_refused_as_not_needed_and_spends_nothing`.
  It now asserts `water_crop` returns False, the code is `not_needed`, and the water is not spent. Reason: the
  supervisor restored the gate.

### Test counts

New: 17 tests in `tests/test_phase049_consequences.py`. Edited: about 22 existing test functions in 9 files, listed
above. Test-file changes that were reverted in this round: `test_phase020_validation.py`, `test_phase021_refusals.py`
(net zero).

## Validation

Commands run from the repo root, after the three changes of this round. Logs are in this directory.

| Check | Result |
|---|---|
| `python3 domains/bigville_entities.py` (`selftest_fix_round.log`) | exit 0; ERRORS (0), WARNINGS (0). The balance, jobs and people sections print with no errors. |
| `python3 -m domains.check --pack test_hamlet` (`check_hamlet_fix_round.log`) | exit 0 |
| `python3 tools/generate_seeds.py --check` (`seeds_check_fix_round.log`) | exit 0 |
| `PYTHONPATH=. python3 /tmp/death_probe.py 192` (`death_probe_fix_round.log`) | 0 deaths in 192 turns (ticks_per_period 96, seed 305017, simple backends) |
| `python3 -m pytest -q -p no:cacheprovider tests/test_phase058_persona.py` (the 50-turn reference, against `docs/phases/fix024_starvation/behaviour_after_fix024.json`) | passes (part of the 323-test targeted run below) |
| `tests/test_simple_work_food_exchange.py` | passes, unchanged |
| `tests/test_phase055_concurrency.py` | 6 of 6 pass in the isolated run and in the targeted run. In the first targeted run of this round, `test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical` failed its timing assertion once. It passed in every later run, and I did not establish whether it is flaky at HEAD. |
| Targeted run: `test_phase058_persona`, `test_simple_work_food_exchange`, `test_phase055_concurrency`, `test_phase049_consequences`, `test_phase020_validation`, `test_phase021_refusals`, `test_phase024_exhaustion`, `test_phase013a_packs` | 323 passed (about 4 min) |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (`pytest_full_fix_round.log`) | 7 failed, 1670 passed, 3 skipped (1171 s). An earlier run in this round gave the same counts; its log was overwritten by the second run. |

Scratch measurements (in `/tmp`, not in the repo):

- Bisect of the call-cap test: at HEAD, the resident's plan `rest` is refused `not_needed` on turn 1, which logs
  `task_failed` and a consult. In the working tree before this round, that rest was accepted, so the only consults were
  `check_in` on turn 0. Restoring the plan-path rest refusal alone made the six tests in `test_phase055_concurrency.py`
  pass. The same run at HEAD also passes all six. I did not bisect the walk, watering or harvest conversions one by one,
  because the rest refusal alone fixed the test.

The 7 failures in the full suite:

- Baseline, unchanged (3): `test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
  `test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
  `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`.
  The adapter module `worlds.bigville_ocelot_adapter` is missing.
- Pre-existing in this checkout, not from this phase (4): `test_phase057_tui.py` (4 `test_over_http_*` and
  `test_the_server_refuses_...`). Evidence from the earlier round: a `git archive HEAD` export passes 48 of 48. An overlay
  of the working tree's `bigville/`, `domains/` and tests, with HEAD's world and packs, still fails the same 4. So the
  cause sits in Tract B's uncommitted code. This round's failure message is `assert (200 == 400)` on an out-of-range
  `intensity` over HTTP.

Caused by this phase: none of the 7. The three phase-caused failures from the previous round are fixed.

## Limits

- Kept as refusals, not converted (supervisor decision): `rest` at reserve >= 0.8 on the plan path (`not_needed`), and
  `water` on an unthirsty crop (`not_needed`, in `water_crop`, so direct calls are refused too). The brief listed both
  as conversions (item 8). A direct `major_action("rest")` at a high reserve is still allowed.
- Backend walks below e_low are refused (`exhausted`). A backend cannot walk until its reserve recovers above e_low.
  The brief's "slower until you fall down" applies to direct world calls only.
- Not converted, kept as refusals: the medical acts' `unskilled` (checkup, treat, well-baby need the medical skill) and
  their `not_needed` (treating a healthy patient); `maintain`'s `not_needed` (works already sound). The brief's skill
  floor, season, strength and need gates are recipe and care gates; these were not listed. `unskilled` and `not_needed`
  therefore stay in `REFUSAL_REASONS`.
- `fill` (the setup primitive that moves store stock into a container) still refuses fluids in a non-watertight vessel.
  Only `put` leaks, as the brief says.
- Skill ruin is a deterministic threshold (`skill_ruin_ratio`), not a probability. The resolution core draws no random
  numbers.
- Offers are unchanged. `_capable`, `_recipe_inputs_available`, `_container_can_receive` and the season filter on
  `sow` still withhold below-floor recipes, out-of-season work, and over-capacity transfers from the menu. The menu is
  shared by every backend, so the LLM backend does not see these options either.
- `job_paused`, `job_start_cell` and `_job_of` read the worker's first job only. The `stop` free action routes through
  `game.py`, which passes no job, so `stop` ends the first job. Tract B owns the routing.
- An exhausted worker's job stops advancing and the worker stays busy until they recover.
- A bare-hand nail job drains its worker's stamina to 0 (measured in the first round, not re-measured). Its progress
  then depends on strength; strain from the low fit causes accidents, which lower health and strength, which slow the
  job further. The job can stall for the whole run.
- The 100-resident village was not run in full. Only the 192-turn death probe (simple backends) and the 50-turn persona
  test were run.
- Phase 050's `RESOLUTION` and `EXHAUSTION` numbers are unchanged except the four keys and the 0.5 slowest rate. All
  new numbers are APPROX; none has a source.

## Open questions

1. **Walk and rest on the plan path (decided in this round).** Option (b) is implemented: a backend walk below e_low is
   refused `exhausted`. The plan-path rest gate and the world's watering gate are restored, as in Limits. The simple village
   returns to the reference, so the 50-turn persona test passes. The walk conversion is kept for direct calls.
   The supervisor should confirm that the brief's "walk until the collapse" is reachable only by direct world calls.
2. **Watering (decided in this round).** The `not_needed` gate is restored. The village trace depends on it.
3. **Medical codes.** Should medical `unskilled` and `not_needed` be converted too? I kept them.
4. **Bare hands for a named tool.** The brief retires `no_tool`. I made a named tool the worker does not hold a bare-hand
   job. Would the supervisor prefer `not_held`?
5. **Concurrency (decided in this round).** The call-cap test moved because of the plan-path rest gate (see Validation).
   The restored gate is the cause. Tract B's `cheap.py` may need the same rule if it changes its rest policy.

## Follow-ups

- Tract B: `cheap.py`'s continuation interrupts (the walk refusal `exhausted` now interrupts a plan's walk below
  e_low); the `stop` routing and the job read-offs. The `exhausted` code needs a description check in any lexicon or
  prompt that quotes `REFUSAL_REASONS`.
- A prompt or lexicon check that quotes `REFUSAL_REASONS` if any reads the retired codes (none found by grep).
- A check of the 100-resident village (`docs/phases/phase058/measure_behaviour.py` and a 100-resident run) is still
  open. It was not run in this round.
