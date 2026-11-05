# Phase 022: Recipe stamina is spent

## Summary

A recipe's declared stamina cost (`RECIPE_EXERTION`) now leaves the worker's `stamina_reserve`. It is
charged through the same `Effort` mechanism movement uses: spread evenly over the ticks of a timed job,
or charged at completion for an instant `do`. The reserve never goes below 0. Exertion, from recipes and
from movement, raises hunger by `HUNGER_PER_STAMINA` per unit spent. A hungrier resident spends more per
unit of work: the declared cost is multiplied by `1 + hunger / starve_limit`. The `fatigue` accumulator
is retired and `fatigue()` reads off stamina spent. The balance model has a stamina line for the founding
town. It does not flag the 100-resident town (0.020 spent against 9.4 affordable per resident per period).

## Changes

Files changed or created by this phase:

- `worlds/bigville_world.py` (my hunks only):
  - `_resolve_jobs`: each armed tick calls `_spend_job_stamina(job)`. Completion calls
    `_spend_job_stamina(job, final=True)` before the job's materials are consumed. The per-tick
    `fatigue` accumulator is removed.
  - `_open_job`: the Job node stores `stamina_total`, `stamina_left` and `stamina_ticks` (the job's
    tick count at open).
  - New method `_spend_job_stamina(job, final=False)`: mints an `Effort` node with `stamina_cost` and
    attaches it to the actor by an `exerted` edge. Movement uses the same edge.
  - `_resolve_actor_events`, `exerted` branch (the port of `bd_exert_cost`): the cost is scaled by
    `1 + hunger / starve_limit`, the actual spend is clamped at the reserve, and hunger rises by the
    actual spend times `HUNGER_PER_STAMINA`. Movement and recipes both pass through this branch.
  - `_resolve_actor_events`, `rested` branch: the 0.1 literal became `E.REST_RECOVERY_PER_UNIT`
    (same value).
  - `fatigue(actor)` returns `self.exertion(actor)` (stamina spent, `stamina - reserve`).
  - Actor init no longer sets the `fatigue` attribute.
  - Lines 6744 and 7047 of the file (at diff time) hold the other session's uncommitted hunks
    (`resident_plan_from_context` and the `food` flag). I did not touch them.
- `domains/world_affordances.py`:
  - New constant `REST_RECOVERY_PER_UNIT = 0.1` with an APPROX note.
  - `_balance_flows` adds `flows["stamina (per resident)"]` and a `stamina:` note.
- `tests/test_bigville_world_migrated.py`: one assertion changed (see below).
- `tests/test_phase022_recipe_stamina.py`: new, 7 tests.
- `docs/phases/phase022/PHASE022_REPORT.md` and logs (`baseline_*`, `final_*`, `other_session_tests.log`,
  `check_hamlet.log`, `seeds_check.log`).

No pack file, `bigville_entities.py`, or seed was changed.

### Design

- **Spend.** Per-tick share = `stamina_total / ticks`. Each `_run` after a tick arms, the share is
  spent, so a timed job spends its whole cost by its last tick. Instant `do` spends everything at
  completion. A job waiting for inputs at zero remaining is not charged again.
- **Hunger scaling.** `starve_limit` is read from the actor (CARE default, 4.0). The multiplier is
  `1 + hunger / starve_limit`: at starvation, the cost doubles. Read at spend time, so a long job whose
  hunger rises mid-way spends slightly more than the declared cost. The acceptance tests hold hunger at 0.
- **Hunger rise.** `HUNGER_PER_STAMINA` stays 1.0 (rationale below).
- **Fatigue.** Retired as an accumulator. Stamina spent (`exertion`) is the read-off, on a 0 to 1 scale.
  The former accumulator added `difficulty * 2` per tick and was not read by any rule.
- **Balance line.** `stamina (per resident)` = (supply, demand). Demand is the declared cost of the staple
  chain's recipe batches, plus the firewood split and the compost batches, divided by residents. Supply
  is the ticks of a day that labour does not take, times `REST_RECOVERY_PER_UNIT`. A ratio below 1 is
  reported as DEFICIT by the existing issue logic.

## Data and sources

- `HUNGER_PER_STAMINA = 1.0` (pack, unchanged). The seed `bigville_body.json` rule `bd_exert_cost`
  multiplies the stamina cost by the literal 1.0, so 1.0 is the seed's value. The pack's constant note
  says a heavy recipe (0.4) adds 0.4 "against a meal that relieves ~5". That is not this port: the port's
  hunger is a count of missed meals (+1.0 per period, `_resolve_period_effects`), and `eat` resets it to 0.
  In the port's units one stamina unit is one missed meal's worth, so 1.0 is kept and justified here.
  The pack note itself is stale and was not edited (outside this phase's write scope).
- `starve_limit` = 4.0 (`packs/bigville/world/care.json`, APPROX per the file's own note). It is the
  normalisation for the hunger multiplier.
- `REST_RECOVERY_PER_UNIT = 0.1`: the port's existing rest rate, moved from a literal into
  `world_affordances.py`. APPROX: the seed `bd_rest_recover` gives no rate. One rest action spans one
  tick (`TIME.minutes_per_tick` = 15, `ticks_per_period` = 96, from `packs/bigville/world/time.json`).
- `RECIPE_EXERTION` values for `forge_plough` (1.2, 0.4) and `split_firewood`, `make_compost` are read from
  the pack, unchanged.

## Changed numbers

Existing tests:

- `tests/test_bigville_world_migrated.py::test_a_recipe_takes_its_time_and_is_hard_work`:
  `w.fatigue("Wayland") > 10.0` became `> 0.0`. The old accumulator added `difficulty * 2` per tick. The
  new read-off is the stamina spent by a forge_knife job (about 0.152 with hunger near 0). The intent
  (the work tires him) is kept; the number now belongs to the new scale.

Behaviour that reaches the 100-resident village (not run; see Limits):

- Every resident's recipe runs and every move now spend stamina from the declared cost, at a higher rate
  when hungry, and exertion raises hunger by the amount spent. The effects on hunger, starvation, and rest
  choices in the village are unmeasured.
- Ahead of any run: `forge_plough` spends 0.4, `forge_knife` 0.15, `split_firewood` 0.2, `make_compost` 0.15,
  `dig_ore` 0.25 and `bake_bread` 0 of reserve per batch (all at zero hunger).

## Validation

Commands and results (run in this checkout; other session's uncommitted work present):

- `python3 domains/bigville_entities.py`: exit 0; ERRORS (0), WARNINGS (0), INFO (70).
  Balance report line: `stamina (per resident)  supply 9.4  demand 0.0  ratio 478.73`. The demand prints as
  0.0 because of the report's one-decimal format. The unrounded value is 0.020 (the note line gives it).
  `issues (0)`.
- `python3 -m domains.check --pack test_hamlet`: exit 0.
- `python3 tools/generate_seeds.py --check`: exit 0 (31 files match the pack).
- Baseline before edits, same command set: `python3 -m pytest -q -p no:cacheprovider` with the seven
  other-session test files ignored: 833 passed, 1 skipped (the brief's 828 is from a clean checkout).
- Final: same command with the seven files ignored: **840 passed, 1 skipped** (833 + 7 new tests; 0 failures).
- Other session's seven files (`test_bigville_game_persistence.py`, `test_bigville_graph_persistence.py`,
  `test_bigville_ocelot_communication.py`, `test_bigville_ocelot_fresh_process.py`,
  `test_bigville_world_persistence.py`, `test_mixed_ocelot_checkpoint_parity.py`,
  `test_mixed_ocelot_village.py`): 18 passed, 1 skipped, 3 failed. The three failures are the known
  `ModuleNotFoundError: worlds.bigville_ocelot_adapter` (`OcelotUnavailableError`), the same failures as
  at baseline. Log: `docs/phases/phase022/other_session_tests.log`.
- New tests (`tests/test_phase022_recipe_stamina.py`, 7):
  - `test_forging_a_plough_spends_its_declared_stamina_evenly_over_the_job`: 16 ticks, each 0.4/16, total 0.4.
  - `test_an_instant_craft_charges_its_stamina_at_completion_and_raises_hunger`: total 0.4, hunger +0.4,
    fatigue 0.4.
  - `test_a_light_recipe_leaves_the_reserve_unchanged`: `bake_bread` (cost 0) leaves the reserve and hunger.
  - `test_the_reserve_never_goes_below_zero`: timed and instant, from 0.1 against 0.4; never negative.
  - `test_a_hungry_worker_spends_more_stamina_for_the_same_work`: hunger 2 of 4 gives x1.5 (0.6).
  - `test_movement_is_scaled_by_hunger_and_raises_hunger_too`: the same step at hunger 2 costs x1.5 and
    raises hunger by the spend.
  - `test_the_balance_model_has_a_stamina_line_and_flags_a_town_that_overworks_its_rest`: the founding
    town passes; with 300 food units per resident per period (labour fills the day, so supply is 0) it is flagged.

## Limits

- The 100-resident village was not run. It takes about five minutes per period, and the brief did not
  ask for it. The stamina line for the 100-resident town is the balance model's figure, not a simulation.
- The spend is a lower bound. It counts only the staple chain, the firewood split, and composting.
  Field work, husbandry, felling, fertilising and walking have no recipe cost in `RECIPE_EXERTION` and are
  not in the balance demand. Walking is in the world (via the Effort event), not in the balance model.
- The affordable figure is an upper bound. It assumes every non-labour tick is a rest action at 0.1, and
  reserves no time for sleep. Because of this, the line cannot flag the town at realistic labour: the
  affordable figure is 9.4 per resident per period, about 470 times the spend. The line flags only when
  labour fills the day, which in the scenario needs between 200 and 300 food units per resident per period
  (at 200 supply is 2.1 against demand 1.0; at 300 supply is 0). Phase 024 adds sleep and
  collapse; sleep time would tighten this bound once it has a sourced allowance.
- The stamina line is in `flows`, not in `work`. Putting it in `work` would fail the JOBS duties coverage
  check (`check_consistency`), because every work stream must be covered by job duties.
- The hunger multiplier is evaluated at spend time, so a long job spends more than its declared cost when
  the worker is hungry during the job. The tests hold hunger at 0 for the declared-cost checks.
- A timed job keeps spending each tick while it runs, including ticks when its tool is broken and the job
  is waiting. Only the armed decrement spends; a job at zero remaining is not charged again.

## Open questions

1. **Pack location of two new numbers.** `REST_RECOVERY_PER_UNIT` (0.1) lives in `domains/world_affordances.py`
   because the brief's write scope excludes `packs/`. The standing rule says tunables go in the pack. Should
   I move it to `packs/bigville/world/constants.json` in a follow-up?
2. **Stale note in the pack.** `HUNGER_PER_STAMINA`'s `_doc` in `packs/bigville/world/constants.json` says a
   meal relieves about 5. The port's `eat` resets hunger to 0. Should that note be rewritten?
3. **Rest budget.** At 0.1 per tick the reserve refills in about 2.5 hours of rest, so stamina does not bind
   in the balance model. Is that the intended rest rate, or should the balance use a sourced sleep allowance
   (Phase 024)?
4. **Hunger scaling in the spend.** Read at spend time, or fixed when the job starts? Fixing it would make a
   job's total exactly its declared cost at its starting hunger. I kept spend-time reading (the seed's
   behaviour).

## Follow-ups

- Phase 024 (sleep and collapse) should set the rest budget and use `REST_RECOVERY_PER_UNIT` or its pack
  successor.
- Phase 006 household-work scoring (`household_work` in the pack) can now read the reserve and exertion
  read-off. It has not been changed here.
- Movement is not in the balance demand. A walking line would need trip counts, which the balance model
  does not have.
