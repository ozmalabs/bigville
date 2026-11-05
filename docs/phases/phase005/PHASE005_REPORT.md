# Phase 005: Household heating and fuel use

## Summary

Each household now burns fuel for space heat once per period (one day). The burn is
`HEATING.base_burn` times the day's weather `firewood_demand`. The household draws its own fuel
first, then the town store, and leaves ash and soot in the store. A household that cannot burn its
full need is cold: each member's chill rises by the unmet share of need. The balance model's fuel
line now includes the heating demand.

The self-test is 0 errors and 0 warnings. The new `tests/test_phase005_heating.py` (14 tests) passes.
The full suite has 3 failures in the other session's Ocelot test files. They fail on the pre-change
tree too, because the Ocelot adapter module is not importable here.

The heating burn lowers the fuel margin from 3.6x to 1.24x. The balance model flags no issue. The
founding cast changed: 10 residents change role, and one forester is added at 100 residents. The
committed cast seeds were regenerated.

## Changes

Files changed or created by this phase:

- `packs/bigville/world/heating.json` (new): table `HEATING`: `fuel_type` "fuel", `base_burn` 0.4,
  `unheated_chill` 1.0, with the sources in its `_doc`.
- `packs/bigville/pack.json`: manifest entry for `HEATING`.
- `packs/bigville/population/balance_scenario.json`: new key `households: 46`, documented in `_doc`.
- `packs/test_hamlet/world/heating.json` (new) and `packs/test_hamlet/pack.json`: the hamlet binds
  every table name, so it gets a `HEATING` with `base_burn` 0 (the hamlet has no fuel slot).
- `domains/world_affordances.py`: binds `HEATING`; new `mean_firewood_demand()` and
  `heating_demand(sc)`; `_balance_flows` adds the heating demand to the `fuel (heat)` demand and writes
  a `heating:` note.
- `domains/population.py`: `scale_scenario` scales `households` with the town (`round(46 * n / 100)`).
- `domains/bigville_entities.py`: self-test checks. `HEATING.fuel_type` must be an INPUT_TYPE with
  members when `base_burn` is above 0; `base_burn` and `unheated_chill` must not be negative.
- `worlds/bigville_world.py` (Phase 005 hunks only):
  - `_household_fuel_sources(household)`: own-store sources (see below).
  - `_burn_household_heat(households=None)`: the burn, called from `_resolve_period_effects` once per
    period when metabolism is on. It returns at once when `base_burn` is 0.
  - `_household_unheated_share(household)`.
  - `_resolve_clothing_and_bodies`: chill gains the unheated term.
  - `add_household`: the Household node starts with `fuel_short` 0.0.
- `seeds/bigville_cast100.json` and `bigville/seeds/bigville_cast100.json`: regenerated with
  `write_cast_seed` (see Changed numbers). The two copies are byte-identical.
- `tests/test_phase005_heating.py` (new, 14 tests).
- `docs/phases/phase005/`: this report and the logs.

`worlds/bigville_world.py` also carries the other session's hunks in `_actor_options` (the "food"
fetch flag) and `resident_plan_from_context`. I did not touch them.

### Burn data and source

- `base_burn` = 0.4 fuel units per household per period at `firewood_demand` 1.0. **APPROX, not
  checked against a source.** The derivation is in the `_doc`: it is about twice the balance model's
  own cooking fuel per household (10 units per period over 46 households, about 0.22 each). That
  rests on a recalled finding that about two-thirds of pre-industrial English household wood went on
  space heating (P. Warde, *Energy Consumption in England and Wales 1560-2000*, 2007). I did not
  re-read that book.
- Units are the model's fuel units (1 wood = 1 fuel), not kilograms. Converting to kilograms would
  mean retuning the cooking figures, which I did not do.
- Weather: `firewood_demand` ranges from 0.6 (hot) to 1.7 (frost). The year's mean is 1.0375. It is
  the average of each season's mean, with seasons weighted equally (90 days each in TIME), and each
  weather option equally likely, which matches how the world draws daily weather.
- `unheated_chill` = 1.0. **APPROX.** It is scaled to the town's `cold` exposure, which is 0 or 1.

### Own-store rule

A household's own fuel is the fuel its members hold, plus the fuel in containers at its home cell.
Concretely, the sources are, in order:

1. Each member's own inventory. This is the Phase 002 `("own", carrier)` source from
   `_bulk_sources`, and it counts wherever the member is standing.
2. Each container at the household's home cell that at least one member may access
   (`_container_accessible`). Carriers are excluded, as in `_bulk_sources`.

Containers at other cells are not the household's. The town store comes last. Within each source
group the plan takes the cheapest fuel kind first (`type_plan`). Own sources are planned before the
store, so the store is drawn only for the rest of the need.

Two choices here are mine, not from the brief:

- The home cell stands in for the member's position. A member away from home still draws on their
  own inventory, but not on the home barrel unless they stand there, so no other cell counts.
- Ash and soot go to the town store, as `_consume_type` does for recipe fuel. The household does not
  keep its own ash.

### Chill rule

`chill = max(0, cold - warmth) + unheated_share * unheated_chill`

`unheated_share` is `fuel_short`, the unmet fraction of the household's need at the last burn. It is
0 when fully heated and 1 with no fuel. The term is read on the next body update, so chill lags the
burn by at most one update. Households with no fuel burn in hot weather are still chilled, because
the need (base x firewood_demand, 0.24 in the hottest case) is still positive. Non-household actors
get 0 from this term.

No backend reads `chill`. The `grep` for `chill` in `bigville/backends/` and `bigville/` found no
readers. So the chill has no effect on decisions or health yet.

### Balance change (fuel line, `_balance_flows`, BALANCE_SCENARIO)

| | before (HEAD 8f18d26) | after |
|---|---|---|
| fuel (heat) supply | 35.95 | 35.95 |
| fuel (heat) demand | 10.00 | 29.09 |
| ratio | 3.60 | 1.24 |
| heating note | none | `heating: 46 households burn 19.1 fuel/period on average (base 0.4 x mean firewood demand 1.04)` |
| labour demand (min/period) | 3285.8 | 3468.6 |
| work: firewood | 0.0 | 91.4 |
| work: felling | 0.0 | 91.4 |
| nitrogen note: ash | 2.0 | 5.8 |

Heating is 46 x 0.4 x 1.0375 = 19.09 per period. The fuel line raises no DEFICIT or TIGHT issue. The
margin falls to 24%, so the TIGHT threshold (under 15%) is not reached.

Break-even values for `base_burn`, holding the rest of the model fixed:

- Above about 0.45 the fuel line becomes TIGHT (margin under 15%).
- Above about 0.54 it becomes a DEFICIT.

### Changed numbers in existing tests

None. The full suite passed with every existing assertion unchanged. Two data-driven results moved
and were checked by the existing tests, and both still pass:

- `tests/test_phase016b_founding_cast.py::test_the_committed_cast_seeds_are_the_generator_output`
  and `tests/test_phase019_knowledge.py::test_the_committed_cast_seed_carries_the_history_the_generator_gives`
  failed until the committed cast seeds were regenerated. The tests were not edited.
- `tests/test_phase016a_founding_town.py` and `test_phase016b_founding_cast.py` still pass with the
  new cast.

### Founding cast and JOBS

The forester load is new. The cast changes as follows.

- JOBS staffing, N=100: forester FTE 0.00 -> 0.38 (1 holder); labourer 60 -> 59.
- N=30: forester 0.00 -> 0.12 (1 holder); labourer 4 -> 3.
- N=8: forester 0.00 -> 0.04 (1 holder); the "several jobs" example gains a miller.
- The cast reshuffles 10 residents' roles along one chain: a labourer becomes a farmer, a farmer
  becomes a mason, and so on, ending with one miller becoming a forester. Households are unchanged
  (46, same members).
- Trades report: butcher holders 3 -> 2, collier 1 -> 2, and a new forester trade line (INFO count
  66 -> 67). Charter awareness shifts too (one understanding figure 0.03 -> 0.04).

`tools/generate_seeds.py --check` passes. The JOBS and TRADES seeds are unchanged in content.

### Test file

`tests/test_phase005_heating.py`, 14 tests, all passing:

- Balance: the fuel demand grows by exactly `heating_demand`. The report's fuel line includes it.
  `scale_scenario` scales the household count. The mean firewood demand is the seasonal average.
- Weather scaling: a burn equals base x weather for hot, clear and frost. It runs through the period
  clock as well.
- Own store: a member's own fuel is burnt before the store. A home-cell container counts as the
  household's own fuel. A container at another cell does not count.
- Ash and soot: they go to the store at the pack's byproduct rates (0.2 and 0.05 per unit).
- Chill: no fuel gives chill 1.0. Half the need gives 0.5. Fuel restores 0. Frost with no fuel adds
  to the town's cold term.
- A pack with `base_burn` 0 burns nothing.

## Validation

Run from `/home/matt/ozmadev/bigville`.

- `python3 domains/bigville_entities.py` (saved to `selftest_bigville.txt`): exit 0. ERRORS (0),
  WARNINGS (0).
- `python3 -m domains.check --pack test_hamlet` (saved to `selftest_test_hamlet.txt`): exit 0.
  ERRORS (0), WARNINGS (0).
- `python3 tools/generate_seeds.py --check`: "generated seeds ... match pack 'bigville' (22 files)",
  exit 0.
- `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (`full_pytest_final.log`): **519 passed,
  2 skipped, 3 failed.** Failures:
  - `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`
  - `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`
  - `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`

  Each fails with `OcelotUnavailableError: Ocelot backend requires Ocelot's
  worlds.bigville_ocelot_adapter ... Adapter import failed (ModuleNotFoundError: No module named
  'worlds.bigville_ocelot_adapter')`. They are the other session's tests. The baseline log
  (`baseline_pytest.log`), taken before my edits, shows the same three failures: 505 passed, 2
  skipped, 3 failed.
- The same suite with those three files ignored (`pytest_ignoring_other_session_failures.log`):
  **519 passed, 2 skipped, 0 failed.**
- `git status --short`: recorded at start and end. The start list contained the other session's
  files and untracked persistence and Ocelot files. The end list adds `docs/phases/phase005/`,
  `packs/*/world/heating.json`, and `tests/test_phase005_heating.py`, and the modified files listed
  under Changes.

I did not run the 100-resident village (`run_village`). The brief did not ask for it. The figures
above come from the balance model and one-day world runs only.

## Limits

- `base_burn` and `unheated_chill` are APPROX. The 0.4 figure rests on a recalled secondary finding
  that I did not check. The unit is the model's fuel unit, not kilograms.
- Heating adds 19 units per day. The break-even values above show how far the figure can move before
  the fuel line tightens or fails.
- Ash goes to the store. The balance model counts it as compostable, but I did not check whether the
  world's compost recipe draws on the store's ash.
- Chill has no consumer yet. No backend or health rule reads it.
- The burn is one per period. It is not scaled to household size.
- The Household node's `fuel_need` and `fuel_short` are the only heating state. Nothing persists
  heating history.

## Open questions

- Is 0.4 fuel units per household per day right? A figure in kilograms, from a checked source,
  would settle the unit. Until then the burn's size is a guess.
- Should a household keep its own ash, or should ash stay a town byproduct as recipes leave it?
- Should chill affect a backend decision or health? Phase 006 may need a fuel read-off, and chill
  would be a second physical signal.
- The hamlet pack has no `HOUSEHOLDS` fallback kind, so `add_household` with no kind fails there. It
  predates this phase and is noted, not fixed.

## Deviations from the brief

- The write scope in the brief omitted `packs/`, `domains/population.py`, and the regenerated seeds.
  The supervising message named `packs/bigville` for new tables, and `scale_scenario` needed the
  household scaling. Those edits are the ones listed under Changes.
- The brief asked for a per-household base burn in `world_affordances.py`. The value lives in
  `packs/bigville/world/heating.json`, bound by `world_affordances.py`, which matches the pack
  convention the supervising message set.
- `test_hamlet` got its own `heating.json` with `base_burn` 0, because it has no fuel slot and
  `packs/test_hamlet` must bind every table name.
- `_burn_household_heat` takes an optional `households` argument, which the tests use to burn one
  household at a time. The period hook calls it with no arguments, so all households burn.
