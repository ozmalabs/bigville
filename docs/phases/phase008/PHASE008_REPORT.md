# Phase 008: animal life cycle

## Summary

Animals now age each period, conceive when a mature, fed female and a mature, fed male of one species
share an enclosure, give birth after a species' gestation, and die at their lifespan. Births add
animals that the game gives the species' NPC setup. Bees do not breed. The founding herd of the
100-resident town is unchanged (one animal per species, all female), so it has no mate and no births.
Self-test: 0 errors, 0 warnings. The 26 new tests pass. The full suite has 3 failures, all in the other
session's ocelot tests, caused by a missing module (see Validation).

## Changes

- `packs/bigville/world/animals.json`: `_doc` now explains the life-cycle fields and units. Each species
  gets `founding_sex`. Breeding species get `breeds`, `gestation_days`, `litter`,
  `breeding_interval_days`, `birth_male_share`, and `approx`. Bees get `breeds: false`. The file was
  rewritten in the exporter's canonical form (`tools/export_pack.py`), so `test_phase013a_packs.py`
  still passes. The only removed line is the old `_doc` text.
- `domains/bigville_entities.py`: new checks in the animal loop of `check_consistency()`. They cover
  `founding_sex`, `breeds`, lifespan longer than maturity, the four life-cycle fields for breeders
  (present, positive gestation, whole-number litter, interval at least gestation, male share in
  0 to 1), `approx` naming only life-cycle fields, and no life-cycle fields on a non-breeder.
- `worlds/bigville_world.py` (my hunks only):
  - `__init__`: `self._animal_life_seed = int(map_seed)`, placed after `self._rng`.
  - `_resolve_period_effects`, metabolism block: capture `fed` before hunger advances; starvation now
    calls `_record_animal_death(node, "starvation")`; call `_advance_animal_life(fed)` after the
    night-soil and heat steps.
  - `add_animal`: new keyword arguments `sex` and `age_days`; new attributes `sex`, `age_days`,
    `gestating_days`, `sire`, `dam`, `births`, `conceived_age`, `born_period`, `death_cause`,
    `death_period`.
  - New methods, placed before `animal_affordances`: `_town_period`, `_animal_month_days`,
    `_is_mature`, `_record_animal_death`, `_advance_animal_life`, `_give_birth`.
- `tests/test_phase008_animal_lifecycle.py`: new, 26 tests.
- `docs/phases/phase008/`: this report, `full_pytest.log`, `pytest_ignoring_other_session.log`,
  `selftest_default.txt`, `check_test_hamlet.txt`.

Not changed: `game.py` (the game already syncs backends for every animal in `world._animals`, so
newborns get backends with no edit), `BALANCE_SCENARIO`, the cast seeds (`generate_seeds --check`
still matches), `test_hamlet` (its `ANIMALS` table is empty, so it has nothing to check), and any
existing test.

In `worlds/bigville_world.py`, the other session's hunks are also present, and I did not touch them:
the `food` flag in the fetch options (about line 6326) and `resident_plan_from_context` (about line
6630). Committing this file will include those hunks unless the supervisor splits them out.

## Species data and sources

Per-species life-cycle values. All figures are APPROX (see Limits), so each species lists them in
`approx`:

| species | breeds | gestation_days | litter | breeding_interval_days | founding_sex |
|---|---|---|---|---|---|
| pig | yes | 114 | 10 | 150 | female |
| cow | yes | 283 | 1 | 365 | female |
| chicken | yes | 21 (incubation; hatch is the birth) | 8 | 90 | female |
| horse | yes | 340 | 1 | 365 | female |
| dog | yes | 63 | 6 | 180 | female |
| cat | yes | 65 | 4 | 120 | female |
| sheep | yes | 147 | 1 | 365 | female |
| bee | no | - | - | - | female (unused) |

`birth_male_share` is 0.5 for every breeder (a 1:1 birth sex ratio, APPROX).

Sources, named in the `_doc` of `animals.json`: Hafez & Hafez, *Reproduction in Farm Animals*
(7th ed., 2000), for livestock gestation and litter figures; the Merck Veterinary Manual for dog, cat,
and poultry; standard dairy and sheep husbandry practice for the calving and lambing intervals. No web
or document access was available in this session, so I could not open these texts. The figures are
recalled from those references and have not been checked against them. The supervisor should verify
them before relying on them.

Units. One period is one day (`TIME.ticks_per_period` = 96 ticks, which the TIME doc calls one day).
The existing `matures` and `lifespan` fields are in months, as their `_doc` says. One month is
`TIME.days_per_year / 12` = 30 days, the sim's calendar split (seasons.json has twelve months in a
360-day year). Gestation and the breeding interval are in days. Age is kept in days (`age_days`).

## Mechanics

Each period (one day), inside the metabolism block:

1. `fed` records which living animals had hunger zero before this period's metabolism. Hunger
   zero means the animal ate since the last period. Eating (the `eat` action at the store) resets
   hunger to zero.
2. Starvation runs as before. It now records `death_cause = "starvation"` and `death_period`.
3. Ageing: each living animal gains one day. At `age >= lifespan * 30` the animal dies with
   `death_cause = "old_age"`.
4. Gestation: each carrying dam loses one day. At zero she gives birth to `litter` young.
5. Conception: a dam breeds when she is alive, female, of a breeding species, mature, fed, not
   carrying, past `breeding_interval_days` since her last conception, and in an enclosure. The sire is
   the first living, mature, fed male of her species in the same enclosure, by name. Dams are processed
   in name order. A dam conceives in one period, and the sire is recorded in `sire`.

Births: each young is a new `Animal` at the dam's cell, enclosure, household, and grazing land, with
age zero. Its `dam` and `sire` are recorded. It is named `<species>_b<period>_<n>`. Its NPC setup is
applied the next time `BigvilleGame.animal_turn()` syncs backends. `game.py` already does this for every
animal in the world, so no game code was needed.

Deaths are recorded in the same node attributes: `alive = 0`, `death_cause`, `death_period`. No
observation is written, and `_births` and `_deaths` (which count residents) are not used.

## Randomness

Only one random draw exists: the sex of each young. It is `random.Random(f"{seed}:{dam}:{litter_no}:{index}")`
with the map seed, the dam's name, her litter count (the `births` attribute), and the index in the
litter. The young is male when the draw is below `birth_male_share`. The draw keeps no state, and it
never touches `self._rng`. A test checks that `_rng` is unchanged by births. The first version kept a
`random.Random` object on the world. That broke the other session's checkpoint tests, because
`world_persistence.py` excludes `_rng` by name and rejects other RNG objects. The stateless draw
avoids that and gives the same sexes after a checkpoint restore.

No existing draw changes. Births are the only new consumer of randomness, and existing tests produce no
births.

## Founding sex-ratio choice

The founding herd keeps one animal per species, so `BALANCE_SCENARIO` (one of each species) is unchanged.
I did not add pairs. Each founder is female (`founding_sex: female` for every species). With one animal
per species there is no mate, so no founder can breed. The 100-town therefore gets no births. A new test
checks this for three pass-period steps. The choice of female is arbitrary for pig, horse, dog, and cat.
It matches the herd's produce (milk, eggs, wool) for the other species. Founders start adult
(`age_days = matures * 30`).

## Changed numbers

No existing test was changed. No existing assertion was modified or removed. The only behaviour change
that existing data-driven code can see is the new `death_cause` attribute on starvation deaths. The
Phase 007 balance test and the 7-animal founding test still pass unchanged.

## Validation

Commands, run after all edits:

- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)`. Output in
  `docs/phases/phase008/selftest_default.txt`. Also 0/0 before the edits.
- `python3 -m domains.check --pack test_hamlet`: exit 0, 0 errors, 0 warnings. Before the edits, also
  exit 0.
- `python3 tools/generate_seeds.py --check`: `generated seeds ... match pack 'bigville' (22 files)`,
  exit 0. The generated seeds did not change.
- `timeout 1500 python3 -m pytest -q -p no:cacheprovider`: **3 failed, 568 passed, 2 skipped**
  (`docs/phases/phase008/full_pytest.log`). The 3 failures are the other session's, verbatim:
  - `FAILED tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`
  - `FAILED tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`
  - `FAILED tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`

  Each fails with `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`. That module
  is in neither HEAD nor the working tree, so the failure predates this phase.
- With those three files ignored: **568 passed, 2 skipped, 0 failed**
  (`docs/phases/phase008/pytest_ignoring_other_session.log`).
- `tests/test_phase008_animal_lifecycle.py`: 26 passed (run alone and inside the suite).
- The persistence files (`test_bigville_game_persistence.py`, `test_bigville_world_persistence.py`)
  failed on my first version (`unsupported graph value at world._animal_life_rng: Random`). They pass
  now. I ran them with the new test file: 35 passed, 1 skipped.
- Export check: `tools/export_pack.py --pack bigville` into a temp directory, then `diff -rq`. Only
  `world/animals.json` differed, so I copied the exported version. `test_phase013a_packs.py` passes.
- A 280-period run of `from_town100()` with `pass_period()` and hunger reset to zero each period (not a
  village run): `pig_2` died at period 270 with `death_cause = old_age` and `age_days = 450`. The other
  founders were alive at period 280. I did not run the 100-resident village.

Git status at start (before any edit) listed the other session's files: README.md, bigville/backends/
ocelot.py, bigville/game.py, bigville/runtime.py, bigville/seeds/bigville_actor_decision.json,
docs/AGENT_BACKENDS_PLAN.md, docs/FEATURE_PHASES.md, tests/test_bigville_game_api.py,
tests/test_bigville_scenarios.py, worlds/bigville_world.py, and untracked persistence, ocelot, and
mixed-ocelot files. At the end, my files are also modified or added: `domains/bigville_entities.py`,
`packs/bigville/world/animals.json`, `tests/test_phase008_animal_lifecycle.py`, `docs/phases/phase008/`,
and my hunks in `worlds/bigville_world.py`. I did not stage or commit anything.

A pre-edit full-suite baseline was not obtained cleanly. A background run overlapped my first edits,
so I deleted its log. The pre-edit baselines that were clean are the self-test, the test_hamlet check,
and the seed check, all listed above.

## Limits

- Founders cannot breed in the 100-resident town, so breeding does not run there unless a supervisor
  adds pairs.
- The life-cycle figures are APPROX. I could not check them against their references in this session.
- The chicken model treats the 21-day incubation as gestation and each brood of 8 as a birth. This adds
  8 Animal nodes per brood, so a long-running flock grows the graph.
- Sheep litter is 1. The integer litter understates lambing (roughly 150%, APPROX).
- Bees: a bee colony is one animal in the model, and it dies at its lifespan. Colony growth and
  swarming are not modelled.
- Not modelled: breeding seasons, lactation or postpartum effects beyond the interval, newborn
  mortality beyond starvation (a newborn starves like any animal), and litter-size variation.
- Ageing, old-age death, and breeding run only when the `metabolism` subsystem is on, because they sit
  inside that block.
- A dead animal keeps its node. Its `death_cause` and `death_period` are the only record.
- Founders are adult (`age_days = matures * 30`). A calf's age starts at zero.

## Open questions

1. **Pig lifespan.** `lifespan: 15` is in months (1.25 years), while the other species' values look
   like realistic lifespans in months (cow 240, horse 360). A fed founding pig dies of old age at period
   270. The data is unchanged here. The supervisor should decide whether 15 is a typo for 15 years (180
   months) or a deliberate slaughter-age value.
2. **Founding pairs.** Breeding needs a second animal per species. Adding pairs means changing
   `BALANCE_SCENARIO` (the balance flows and staffing would change), regenerating the cast seeds with
   `write_cast_seed`, and checking that JOBS staffing still works. The brief allowed this, but I did not
   do it.
3. **Verification of the APPROX figures**, against the cited references.
4. **Commit hygiene.** `worlds/bigville_world.py` also holds the other session's uncommitted hunks.

## Supervisor review

- Pig lifespan (open question 1): corrected from 15 to 180 months (15 years, APPROX) in
  `packs/bigville/world/animals.json`, with a note in its `_doc`. The other species' lifespans are
  natural lifespans in months (cow 240, horse 360), and a slaughter age belongs to people's choices, not
  to the animal's lifespan. No other code read the pig lifespan, and no test depended on it.
- Founding pairs (open question 2) are not added: the founding herd stays one female per species, so
  the founding town has no births. Adding pairs changes BALANCE_SCENARIO and the staffing, which is a
  decision for later.
- The life-cycle figures stay APPROX (not checked against the cited references).
