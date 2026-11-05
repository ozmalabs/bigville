# Phase 006: Household work choice in the backends

## Summary

Open (household) recipes now carry physical read-offs: fuel the worker holds, fuel in the town store
when the worker stands there, the household's last heating shortfall, and night soil held or in the
store. The backend turns these into points with weights from a new pack table, `HOUSEHOLD_WORK`. An
open recipe that depends on fuel or night soil is offered only when it has points above zero. The
rule sits in `bigville/backends/psi_can.py` and applies to cheap and psi_can alike, since cheap
chooses through `CANWeightModel.choose`.

A resident with an axe, low fuel, and the recipe in memory chooses `split_firewood`. With fuel held
at or above the threshold and a warm household, the same resident does not. The spade-and-night-soil
case works the same way for `make_compost`.

In the founding town, nothing changes over three simulated days: the village run matches HEAD on
every recorded value. The reason is that no founding resident holds an axe or a spade, and the
open-recipe tool rule requires the worker's own held tool. The read-offs cannot steer anyone until a
resident holds one.

Self-test 0 errors, 0 warnings. `tests/test_phase006_household_work.py` has 17 tests, all passing.

## Changes

- `packs/bigville/world/household_work.json` (new): table `HOUSEHOLD_WORK`: `night_soil_kind`
  "night_soil", `fuel_low_units` 1.0, `night_soil_high_units` 4.0, `weights` {`fuel_cold` 30,
  `fuel_low` 30, `night_soil_high` 30}. Every value is APPROX (a design choice; `_doc` gives the
  reasoning).
- `packs/bigville/pack.json`: manifest entry for `HOUSEHOLD_WORK`.
- `packs/test_hamlet/world/household_work.json` (new) and `packs/test_hamlet/pack.json`: the same
  values. The hamlet has no night soil and no open recipes, so these values never affect it.
- `domains/world_affordances.py`: binds `HOUSEHOLD_WORK`. `domains/bigville_entities.py` re-exports
  it through the existing star import.
- `domains/bigville_entities.py` (self-test): `HOUSEHOLD_WORK` thresholds and weights must be above
  zero (or non-negative for weights), the weight keys must be exactly the three named, and
  `night_soil_kind` must be an ITEM when an open recipe consumes it.
- `worlds/bigville_world.py` (my hunks only):
  - new `_open_work_read_offs(actor, recipe)`, placed before `_recipe_in_season`.
  - in `_actor_options`, one line after the open-recipe `work` option append:
    `options[-1].update(self._open_work_read_offs(actor, recipe))`.
  - The other session's hunks (the `"food"` fetch flag near line 6146 and `resident_plan_from_context`
    near line 6447) are untouched.
- `bigville/backends/psi_can.py`: new `open_work_governed(option)` and `open_work_need(option,
  table=None)`. `CANWeightModel.score` adds the need to the weighted score. `CANWeightModel.choose`
  drops governed open-recipe options with need 0. `cheap.py` is not edited: it chooses through
  `CANWeightModel.choose`.
- `tests/test_phase006_household_work.py` (new, 17 tests).
- `docs/phases/phase006/`: this report, the game check and diagnostic scripts, and their logs.

## Read-offs and why each is perceivable

Read-offs are added only to open recipes, and only the ones they concern. `open_recipe` marks every
open recipe.

| Key | On which options | Value | Why the worker can perceive it |
|---|---|---|---|
| `open_recipe` | every open recipe | true | A fact of the recipe, from RECIPES `open`. |
| `fuel_held` | a recipe whose output is the HEATING fuel slot (`split_firewood`) | fuel units in the worker's own inventory (1 wood = 1; straw 0.3, dung 0.6, peat 1.5, charcoal 3.0 by ITEMS tag) | The worker holds it. |
| `fuel_store` | the same, only while the worker stands on the store cell | fuel units in the town store | Seen on the spot. Store stock is not otherwise published (checked: `_context` observations hold no store totals). |
| `household_fuel_short` | the same, only for a resident in a household | the household's last unmet heating share, 0 to 1 | Members feel this as cold. It is the same figure that drives the chill term. It lags one period. |
| `night_soil_held` | a recipe that consumes `night_soil` (`make_compost`) | night soil in the worker's own inventory | The worker holds it. |
| `night_soil_store` | the same, only while the worker stands on the store cell | night soil in the town store | Night soil accumulates in the store (`_collect_night_soil` writes the store stock; no other place holds it). |

Read-offs are not published to other residents, and no recommendation or need label is published.
Fuel and night-soil read-offs are absent from non-open recipes and from the other open recipes
(`bake_bread_at_home`, `spin_thread`). A key is absent when the worker cannot perceive that quantity.

## Scoring rule and pack weights

For an option with `fuel_held` (fuel recipe):

- `fuel_cold` (30) x `household_fuel_short` (0 to 1, clamped), and
- `fuel_low` (30), once, when `fuel_held + fuel_store` is below `fuel_low_units` (1.0).

For an option with `night_soil_held` (compost recipe):

- `night_soil_high` (30), once, when `night_soil_held + night_soil_store` is at least
  `night_soil_high_units` (4.0, two compost batches).

The points are added to the option's weighted score. A governed option (one with `fuel_held` or
`night_soil_held`) is offered only when its points are above zero. Other open recipes keep their
previous behaviour.

Threshold basis: `fuel_low_units` 1.0 is about 2.4 days of mean household heating (HEATING base 0.4
x mean firewood demand 1.04). `night_soil_high_units` 4.0 is two batches (`make_compost` takes 2
night soil). The weights are the same size as the cheap backend's work-goal bonus (30) and
role bonus (24). None of these are sourced figures; `packs/bigville/world/household_work.json` marks
them APPROX.

## Validation

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` | exit 0, ERRORS (0), WARNINGS (0). Log: `selftest_bigville.txt` |
| `python3 -m domains.check --pack test_hamlet` | exit 0, ERRORS (0), WARNINGS (0). Log: `selftest_test_hamlet.txt` |
| `python3 tools/generate_seeds.py --check` | exit 0. Seeds match pack `bigville` (22 files). Log: `generate_seeds_check.txt` |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` | 3 failed, 536 passed, 2 skipped. Log: `pytest_full.log` |
| same, ignoring the other session's files (`tests/test_mixed_ocelot_*.py`, `tests/test_bigville_ocelot_*.py`, `tests/test_bigville_*persistence*.py`, `tests/test_bigville_game_api.py`, `tests/test_bigville_scenarios.py`) | 482 passed. Log: `pytest_ignoring_other_session.log` |
| `pytest tests/test_phase006_household_work.py` | 17 passed |

The three failures are the other session's, and they are not caused by this phase. Verbatim:

- `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`
- `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`
- `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`

Each fails with `OcelotUnavailableError: ... Adapter import failed (ModuleNotFoundError: No module
named 'worlds.bigville_ocelot_adapter')`. The adapter module is not on this checkout's path.

### Tests in `tests/test_phase006_household_work.py`

- Read-offs are on the fuel recipe only (`fuel_held`) and the compost recipe only (`night_soil_held`).
  `saw_planks` and `make_compost` carry no fuel keys. `split_firewood` carries no night-soil keys.
- `fuel_store` is present only while standing at the store cell.
- `household_fuel_short` is present for household members only.
- A resident without an axe is not offered `split_firewood`.
- Axe holder with low fuel chooses `split_firewood` (cheap backend). With fuel at the threshold, it
  does not. A cold household still chooses it with fuel in hand.
- Spade holder with night soil at the threshold chooses `make_compost`. With one batch (below the
  threshold) it does not. Night soil in the store is not perceived away from the store.
- `CANWeightModel.choose` (psi_can) matches the cheap backend on the split-firewood cases.
- The weights come from the table passed in. Setting `fuel_low` to 0 removes the points.
- Other open recipes (`bake_bread_at_home`) are not gated by the need.
- The bigville table is bound; the hamlet table is bound.
- The self-test rejects a negative weight (monkeypatched table).

## Village comparison

Command: `docs/phases/phase006/game_check.py <root> 3`, 3 periods (288 ticks), 100 residents,
`BigvilleGame(autonomous=True)` with the simple backends. "Before" is HEAD (`git archive`, a clean
export). "After" is HEAD plus only this phase's hunks. The export was built from HEAD and patched
with this phase's hunks only, so the other session's uncommitted changes are not in either run.

| Day | Tree | Alive | Bread | Fuel in store | Night soil in store | Households short | Mean fuel_short |
|---|---|---|---|---|---|---|---|
| 1 | HEAD | 100 | 779 | 0.0 | 20 | 36 | 0.13 |
| 1 | after | 100 | 779 | 0.0 | 20 | 36 | 0.13 |
| 2 | HEAD | 100 | 700 | 0.0 | 40 | 46 | 1.00 |
| 2 | after | 100 | 700 | 0.0 | 40 | 46 | 1.00 |
| 3 | HEAD | 100 | 602 | 0.0 | 60 | 46 | 1.00 |
| 3 | after | 100 | 602 | 0.0 | 60 | 46 | 1.00 |

Logs: `game_head_before.log`, `game_after.log`. Both runs took about 14 minutes.

A one-period work diagnostic (`work_count_check.py`) counts applied work plans by recipe:

| Recipe | HEAD | after |
|---|---|---|
| `bake_bread_at_home` | 11 | 11 |
| `spin_thread` | 2 | 2 |
| `split_firewood` | 0 | 0 |
| `make_compost` | 0 | 0 |

Logs: `work_count_head.log`, `work_count_after.log`. The founding cast has one resident who knows
`split_firewood` (Lavinia Grubb, a forester). Eight residents know `make_compost`. No founding
resident holds an axe or a spade (checked with `_held_tool`).

The first version of the offer filter dropped every open recipe without a need. The diagnostic
showed `bake_bread_at_home` (11) and `spin_thread` (2) disappearing. The filter now applies only to
fuel and night-soil recipes, and the runs above use the fixed version. The intermediate run is
discarded.

## Limits

- Three periods, one seed, simple backends only. No Ocelot run. The 100-resident run takes about
  five minutes per period.
- The read-offs cannot change a founding resident's choice, because no founding resident holds an
  axe or spade. I found no action that takes a tool from a shelf to hand (`stow_tool` goes the other
  way). The generic `move_object` is disabled in the default simple policy, and I did not check
  whether it can carry a tool.
- Night soil is visible only at the store. Compost is therefore chosen only by a spade holder who
  stands at the store. On day 1 no compost plan was applied (work count), and the three-day run left
  the store's night soil identical to HEAD.
- The LLM and Ocelot backends see the read-offs in their affordance lists, but no scoring is
  applied for them. The Ocelot adapter is unavailable on this checkout.
- Thresholds and weights are APPROX design choices, not measured or sourced rates.
- Stamina is not read: see Follow-ups.

## Deviations from the brief

- The scoring rule is in `psi_can.py`, not `cheap.py`. Cheap chooses through `CANWeightModel.choose`,
  so both backends apply the same rule. `cheap.py` is unchanged.
- The offer filter applies to fuel and night-soil recipes only. Filtering every open recipe changed
  bread and spinning behaviour (see Village comparison), so it was narrowed.
- `HOUSEHOLD_WORK` is bound in `world_affordances.py`, beside `HEATING`.
- Test edits: none. No existing test was changed, and the existing suite passed with the new code.

## Open questions

- Should a resident be able to fetch an axe or spade from a workplace shelf to hand? Without that,
  these read-offs cannot act in the founding town.
- Should night soil be published at the latrine (a cell) so residents can see it without visiting
  the store? The current model keeps it in the store.

## Follow-ups

- Phase 022/024 stamina. The brief for 006 says the open-recipe choice should read the stamina
  reserve and exhaustion state once 022 and 024 land. Split firewood (40 minutes) and compost (60
  minutes) are strenuous work, and the read-off is not yet in place. The `strength` gate on open
  recipes is unchanged.
- A tool-to-hand action, or a rule that residents begin with their trade tools in hand. Either is a
  world change outside this phase.
