# Phase 024: exhaustion, collapse and sleep

## Summary

The reserve now sets a movement band, from the seeded `mv_energy_budget`. At or above 0.70 a resident
walks at full speed. Between 0.40 and 0.70 the movement interval is x1.5, between 0.15 and 0.40 it is x3,
and below 0.15 walking is refused (`too_tired`). A resident whose reserve falls below `e_collapse` (0.05,
APPROX) collapses where they stand. A collapsed resident is refused other major actions (`collapsed`),
wakes at `collapse_cap` (0.25, APPROX), and falls again if they keep working. A new major action, `sleep`,
restores the reserve to `rest_cap` (1.0). A sleeping resident is refused other major actions (`asleep`).
Timed jobs pause while their worker sleeps or has collapsed, through the Phase 023 pause. A tired worker's
job advances at the movement speed. The world publishes `lateness` and `safe` for the sleep decision. The
simple backend decides when to sleep. `REST_RECOVERY_PER_UNIT` moved into the new `EXHAUSTION` pack table.

Self-test: 0 errors, 0 warnings. Full suite: 895 passed, 2 skipped, 3 failed. The 3 failures are the
Ocelot adapter tests that also fail at the start of this phase (`ModuleNotFoundError: worlds.bigville_ocelot_adapter`).

## Changes

Pack data (new table, and codes in both packs):
- `packs/bigville/world/exhaustion.json` (new): table `EXHAUSTION`. Keys: `slow_on`, `e_high`, `e_mid`,
  `e_low`, `moves_per_tick`, `e_collapse`, `rest_gain`, `rest_cap`, `collapse_gain`, `collapse_cap`,
  `night_start_hour`, `night_end_hour`, `rest_recovery_per_unit`. The `_doc` gives each value's source or APPROX.
- `packs/test_hamlet/world/exhaustion.json` (new): copy of the same table.
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`: one `EXHAUSTION` entry each.
- `packs/bigville/world/refusal_reasons.json`, `packs/test_hamlet/world/refusal_reasons.json`: codes
  `asleep`, `collapsed`, `too_tired` (the last is a new code, see Deviations).
- `packs/bigville/world/major_actions.json`, `packs/test_hamlet/world/major_actions.json`: action `sleep`
  with a description.
- All six edited pack files are in the exporter's layout (`tools/export_pack.py` rewrote nothing else).

`domains/world_affordances.py`: binds `EXHAUSTION`. `REST_RECOVERY_PER_UNIT` now reads
`EXHAUSTION["rest_recovery_per_unit"]` (0.1, unchanged value).

`domains/bigville_entities.py`: `_check_exhaustion` (fractions in [0, 1], e_high > e_mid > e_low > 0,
e_low > e_collapse, e_collapse < collapse_cap < rest_cap <= 1, collapse_gain <= rest_gain, moves_per_tick
falling to 0, a boolean `slow_on`, night hours in [0, 24)). `_check_refusal_reasons` requires the three new
codes. Both are called from `check_consistency`. I checked that the new checks report bad values.

`worlds/bigville_world.py` (my hunks only; the other session's hunks are `resident_plan_from_context` and the
`"food"` line in the fetch options, and I did not touch them):
- `__init__`: keyword `exhaustion_slow_on=None`. Order: constructor value, then scenario `exhaustion.slow_on`,
  then the pack default. Sets `self.exhaustion_slow_on`.
- `_run`: calls `_resolve_sleep()` after `_resolve_actor_events()`.
- `_resolve_jobs`: an armed tick advances a job by the worker's speed (`_job_speed`). A speed of 0 skips the
  tick (no progress, no stamina). `_spend_job_stamina(job, share=speed)`.
- `_spend_job_stamina`: new `share` argument (default 1.0, so unslowed jobs are unchanged).
- `_job_away`: a sleeping or collapsed worker counts as away, so the Phase 023 pause applies.
- `move_actor`: band read before the walker's own effort is spent. Stopped: returns with no effort.
  Otherwise the waiting-tick cooldown is a float (`cooldown + interval - 1`). With whole-number intervals this
  matches the old integer cooldown.
- `add_actor`: node attributes `asleep`, `collapsed`, `sleep_kind`, `slow_on`, `exhaustion_step`, `speed_factor`.
- New block after `job_start_cell`: `_sleep_code`, `asleep`, `collapsed`, `_exhaustion_band`,
  `_refresh_exhaustion`, `exhaustion_step`, `speed_factor`, `_job_speed`, `_witnesses`, `_record_sight`,
  `_lie_down`, `_wake`, `_resolve_sleep`, `sleep_facts`.
- `body_state`: adds `exhaustion_step`, `speed_factor`, `asleep`, `collapsed`.
- `_actor_options`: no options while asleep or collapsed. A `sleep` option (with `lateness` and `safe`) when
  reserve is below `rest_cap`. No move options when stopped. Move options carry `speed_factor` and
  `exhaustion_step`.
- `_major_action_attempt`: `move` refused `too_tired` when stopped. New `sleep` branch (`not_needed` at full
  reserve). `_lie_down_as_major` (new, after `_rested`).
- `_attempt`: refuses any major action while the actor is asleep or collapsed, before the attempt runs.
- `_recipe_refusal`: first check returns `collapsed` or `asleep`.
- `_enact_plan`: a `sleep` plan calls `major_action(actor, "sleep")`.

`bigville/backends/cheap.py`: `SimplePolicy` gains `sleep_energy_threshold` (40.0) and `collapse_guard_energy`
(20.0). `sleep` is excluded from the general option pool. The sleep rule runs before the rest rule. It picks
sleep when energy is below 40, the spot is safe, and either it is night (`lateness` >= 1) or energy is below
20. `last_choice["reason"]` is `sleep_at_night` or `sleep_before_collapse`. The rest rule is unchanged.

`bigville/backends/psi_can.py`: `ACTION_CONCEPTS["sleep"]` added (one line).

Tests:
- `tests/test_phase024_exhaustion.py` (new, 28 tests).
- `tests/test_phase022_recipe_stamina.py`: see Changed numbers and tests.
- `tests/test_phase023_job_occupancy.py`: `_smith()` setup only.

### Design

- **Bands.** Step 0 at or above `e_high`, 1 at or above `e_mid`, 2 at or above `e_low`, 3 below. Speed is
  `moves_per_tick[step] / moves_per_tick[0]` (1, 2/3, 1/3, 0). The interval is its inverse (1, 1.5, 3). The
  interval multiplies the carry and terrain interval already in `move_actor`.
- **Thresholds.** Fractions of the body's stamina capacity (body `stamina`).
- **Collapse.** Checked in every `_run`, for awake living residents.
- **Sleep and wake.** Regain happens only on armed (clock tick) runs. A sleeper regains `rest_gain` per tick up
  to `rest_cap`. A collapsed one regains `collapse_gain` up to `collapse_cap`. Each wakes at its cap.
- **Witnesses.** Awake, living residents on the same cell. Each collapse and sleep creates one `Event`
  node (kind `collapse` or `sleep`) with an `observed_event` edge to each witness. No witness, no event.
- **Facts.** `lateness` = hours past 21:00, or past midnight until 05:00, from the town clock, 0 otherwise.
  `safe` = the actor stands on their `home_at` cell or inside a sheltered building's footprint.

## Data and sources

Seed values (from `seeds/bigville_move_energy.json` v1.1.0 and `seeds/bigville_time_sleep.json` v1.0.0):
- `e_high` 70, `e_mid` 40, `e_low` 15 on the seed's 0 to 100 scale, as fractions 0.70, 0.40, 0.15.
- `moves_per_tick` [3, 2, 1, 0], giving speeds 1, 2/3, 1/3, 0.
- `slow_on` is the seed's falsifier. `energy_cost` is not changed here. It is already the Phase 022 cost.
- The seed's `rest_gain`, `rest_cap`, `collapse_gain`, `collapse_cap`, `e_collapse` and `sleep_threshold` have no
  values in the seed or elsewhere in the repository. The values below are APPROX.

New values (APPROX, not sourced, marked in the pack `_doc`):
- `e_collapse` 0.05.
- `rest_gain` 0.03 per tick. Over 32 ticks (8 hours at 15 minutes per tick) that is 0.96.
- `rest_cap` 1.0.
- `collapse_gain` 0.02 per tick. `collapse_cap` 0.25.
- `night_start_hour` 21, `night_end_hour` 5. The real sunset is Phase 042.
- `rest_recovery_per_unit` 0.1, moved unchanged from `world_affordances.py`.
- Backend valuations in `cheap.py`: `sleep_energy_threshold` 40, `collapse_guard_energy` 20.

## Changed numbers

Existing test changes (the brief's behaviour change requires them):
1. `tests/test_phase022_recipe_stamina.py::_smith` and `tests/test_phase023_job_occupancy.py::_smith`:
   `World()` became `World(exhaustion_slow_on=False)`. These tests assert full-speed job timing. A plough
   that drains the reserve from 1.0 to 0.6 is slowed by design, so the timing assertions would fail. No
   assertion was changed by this. The slowdown is tested in `test_phase024_exhaustion.py`.
2. `tests/test_phase022_recipe_stamina.py::test_the_reserve_never_goes_below_zero`: the last assertion
   `reserve == 0.0 and not busy` became `collapsed_during_job`. A timed job at reserve 0.1 now drops the
   worker to a collapse (below 0.05) before the reserve reaches zero. The floor at zero is still checked on
   every tick. The instant `do` half of the test is unchanged.

No other existing assertion was changed or removed.

Behaviour changes that reach the 100-resident village (not run):
- Walks slow down below 0.70 of reserve. Walkers collapse below 0.05.
- Sleep options appear in every awake resident's affordances below reserve 1.0.
- The simple backend sleeps at night, or by day below energy 20, when on a safe spot.
- Timed jobs pace with the worker's speed, and jobs spend stamina per unit of progress.
- `body_state` has four new keys. Actor nodes have six new attributes. Each collapse or sleep creates an event
  node when a witness is present.

## Validation

Run from `/home/matt/ozmadev/bigville`. Working tree included the other session's uncommitted work.

- `git status --short` at start: the other session's modified and untracked files listed in the brief's
  preamble, plus `bigville/backends/cheap.py` and `psi_can.py` only after my edits.
- Baseline before edits, `timeout 1500 python3 -m pytest -q -p no:cacheprovider`: 867 passed, 2 skipped, 3 failed
  (log `baseline_full.log`). The 3 failures are the known Ocelot adapter tests.
- Baseline self-test: ERRORS (0), WARNINGS (0) (`baseline_selftest.log`).
- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0), issues (0) (`selftest.log`).
  The stamina balance line is unchanged. It still reads "no sleep reserved".
- `python3 -m domains.check --pack test_hamlet`: exit 0 (`check_hamlet.log`).
- `python3 tools/generate_seeds.py --check`: exit 0, "match pack 'bigville' (31 files)" (`seeds_check.log`).
- `python3 tools/export_pack.py` and `--pack test_hamlet`: no further changes after my edits.
- `pytest tests/test_phase024_exhaustion.py`: 28 passed.
- `pytest tests/test_phase022_recipe_stamina.py tests/test_phase023_job_occupancy.py`: passed after the
  changes listed above.
- Full suite, final (`final_full.log`): 895 passed, 2 skipped, 3 failed, exit 1. Failures:
  `test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
  `test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
  `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`.
  Each raises `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`, as at baseline.

Tests in `tests/test_phase024_exhaustion.py` (28):
- Codes and table: refusal codes and `sleep` present; `REST_RECOVERY_PER_UNIT` read from the table; seeded fractions and hop budget.
- Walks at reserves 0.9, 0.5 and 0.2 take 60, 40 and 20 moves in 60 turns (x1, x1.5, x3).
- Reserve 0.1: walk refused `too_tired`, no move options.
- Body state and move options publish `exhaustion_step` and `speed_factor`.
- `exhaustion_slow_on=False` and scenario `exhaustion.slow_on: false`: no slowdown.
- Collapse below `e_collapse`; refusal `collapsed`; wake at `collapse_cap` after exactly
  `ceil(gap / collapse_gain)` = 11 ticks; falling again while walking.
- Witnessed collapse: the co-located resident gets one `collapse` event; the actor does not.
- Sleep restores to `rest_cap` in `ceil(0.5 / rest_gain)` = 17 ticks and wakes. `not_needed` at full reserve.
  `asleep` refusals for move, rest and sleep. No major affordances while asleep.
- `sleep_facts`: lateness from the hour (12:00 gives 0, 23:30 gives 2.5, 02:00 gives 5, 05:00 gives 0); safe at
  home; not safe far away. The sleep option carries the facts below rest_cap only.
- Jobs: a sleeping worker's job pauses and resumes after waking; a collapsed worker's job pauses; a worker at
  reserve 0.5 advances 2/3 of a tick; a worker at 0.1 does not advance.
- Simple backend: sleeps at night when safe; sleeps by day below energy 20 when safe; rests when unsafe at
  energy 30; moves when energy is 60.

## Limits

- **Witnesses.** Sight has no range model, so a witness is a resident on the same cell. Sight does not shorten at night.
- **Concern not formed.** `bt_concern` is not ported. The world records the witnessed event (kind `collapse` or
  `sleep`, `observed_event` edge). No backend changes affect and no resident's affect changes. Phase 029 or a later
  backend phase can read the event.
- **Thresholds do not vary yet.** Thresholds are fractions of body stamina capacity. Every founding resident has
  capacity 1.0 (`sta_base` defaults to 1.0, and `draw_physique` in `population.py` is never called). So the
  per-character variation the brief asks for is in place but has no effect in the founding town.
- **Stamina on waiting turns.** `move_actor` charges the walker's effort on every call, including turns spent
  waiting on the cooldown (existing behaviour). At x3 a walker therefore spends about three times the stamina per
  cell. Not measured in a village run.
- **Collapse mid-walk.** The step is taken, then the collapse is checked. A walker who collapses on their last step
  arrives asleep.
- **Options while down.** An asleep or collapsed resident gets an empty option list. The `asleep` and `collapsed`
  flags are in `body_state`, not on each option. Those flags are not in the observations the game context sends.
- **Balance model.** The stamina balance line (Phase 022) still reports "no sleep reserved". It was not updated.
- **Household work (Phase 006).** Not changed.
- **Scenario switch.** `exhaustion.slow_on` in a scenario is read from the scenario dict. A scenario loaded from
  file keeps unknown keys, so it works, but I tested only an inline scenario dict.
- **Not run.** The 100-resident village (`from_town100`, `run_village`) was not run. No behaviour or balance
  claim is made beyond the tests above.

## Open questions

1. **Jobs below e_low.** The brief's extension says jobs advance at the movement factor. At reserve below 0.15,
   the factor is 0, so a worker stops. The job stays busy and waits for a rest. Alternative: a floor at the slowest
   band (1/3). Which do you want?
2. **Too-tired code.** I added `too_tired` for walking below e_low. The brief named only `asleep` and `collapsed`.
   Keep it, or use another existing code?
3. **Per-resident thresholds.** Real variation needs body capacities that differ. Should `draw_physique` feed
   `sta_base` (the population table is not in this phase's scope)?
4. **Concern.** Should the witness's affect (arousal, valence, `Concern` node) be ported now, or with Phase 029?
5. **Sight range.** Same-cell witnessing is a placeholder. Is there a sight rule (distance, lamps) to use?

## Follow-ups

- Phase 029 can read `asleep` and `collapsed` on the actor node and in `body_state`, and the `Event` nodes with
  `observed_event` edges.
- Phase 042 supplies the real sunset for `night_start_hour`, `night_end_hour` and `lateness`.
- Phase 037 can read the `collapsed` flag.
- Balance model: put the sleep allowance in the stamina line (the seed's `bt_decide_sleep` cost is not sourced).
