# Phase 016b: the founding cast from JOBS, with real ages, households, and a genealogy drawn from them

## Summary

The 100-resident founding cast is now seeded from `E.seed_jobs(100)`. Each resident's role is their first job.
Founders have ages drawn from a pack distribution (APPROX), and they are grouped into 46 households with one
home per household. The genealogy is drawn from those households, so co-resident spouses form a union, and
siblings in a household share parents. `populate_town100` sets capability from literacy through a pack table
(the HEAD values, 0.9 and 0.55), and skill from each job's trade base skill (TRADES) instead of a flat 0.7.

The self-test is 0 errors and 0 warnings, and the hamlet check is clean. The suite gives 432 passed, 2 skipped,
and 4 failed. Three failures are the other session's Ocelot tests, which were already failing before my edits.
The fourth is `tests/test_bigville_disposition_seed.py::test_homophily_same_role_overrepresented`. The new role
mix moves its ratio below the test's 1.5 threshold. I did not change the threshold, so that failure needs your
decision (see Open questions).

Over five simulated days with the simple backends, the new cast and the HEAD cast both keep 100 residents alive
with no deaths. Both run out of bread on day 4. Grain runs out sooner in the new cast (day 1, not day 2 to 3).

## Changes

Pack data (bigville pack unless noted):

- `population/founding_cast.json`: `FOUNDING_ROLES` (25 role rows) becomes `FOUNDING_JOBS`, keyed by JOBS key
  (27 rows: group, role identity mean and sd, workplace). New `FOUNDING_AGE` table. `FOUNDING_CLASS` gains
  `capability_by_literacy`. `FOUNDING_ANCHOR_NAMES` is keyed by job. Banker (Scrooge) is dropped.
- `frames/jobs.json`: two JOBS entries added, `fishmonger` (trade fisher, fixed 1.0) and `reporter` (trade
  reporter, fixed 1.0). See Deviations.
- `population/household_composition.json`: `KIN_MODEL.SIBLING_IN_VILLAGE` (0.25) is replaced by
  `SIBLING_MAX_GAP_YEARS` (15, APPROX). The old key only drove the generator I replaced.
- `pack.json` (bigville and test_hamlet): manifest entry renamed to `FOUNDING_JOBS`, `FOUNDING_AGE` added.
- `test_hamlet/population/founding_cast.json` and `test_hamlet/population/household_composition.json`: the same
  table shapes (empty founding tables; KIN_MODEL key changed as above). `test_hamlet/frames/jobs.json` is
  unchanged.

Code:

- `domains/population.py`: binds `FOUNDING_JOBS`, `FOUNDING_AGE`, and `LIFE_STAGES`. New functions
  `draw_founding_ages`, `draw_founding_households`, `plan_founding_town`. `draw_founding_kin` is rewritten (see
  Genealogy). `describe_founding_kin(founders, *, seed)` now draws its own ages and reports the household shape.
- `domains/bigville_entities.py`: the founding-town check reads `FOUNDING_JOBS`. Each JOBS key needs a row (error
  if not). Each row needs a valid group and workplace. Anchors must be job keys. `check_job_seed(BALANCE residents)`
  must be ok (error if not). `FOUNDING_AGE` must lie inside the adult life stage. `SIBLING_MAX_GAP_YEARS` is range
  checked. The founding-kin info line reports the default town's shape. The founding-kin info is skipped for a
  pack without founding tables (the hamlet).
- `worlds/bigville_town100_world.py`: `build_town_100` makes one home per household (`plan_founding_town`).
  `generate_cast100` takes roles from the staffing plan, workplace and group from `FOUNDING_JOBS`, the age,
  household, and genealogy from the plan, skill from TRADES, and capability from the pack table. Each cast record
  gains `age`, `jobs`, `trades`, `skill`, `capability`, `household`, and `household_role`. The cast also
  carries a `households` list. `write_cast_seed` is unchanged.
- `worlds/bigville_world.py` (my hunks only, in `populate_town100`, `from_town100`'s docstring, and the
  data-pack check): one household per founding household, with its kind from its head's role and group. Each
  resident is added with the cast's age, skill, capability, and trades. `_found_kinship(residents, seed)` keeps its
  signature (a Phase 009 test monkeypatches it) and now reads the same plan.

Generated:

- `seeds/bigville_cast100.json` and `bigville/seeds/bigville_cast100.json`: regenerated with `write_cast_seed`. The two
  files are byte-identical. Nothing loads them at runtime; `seeds/bigville_can_beliefs.json` names them in its
  description only.

Tests:

- `tests/test_phase016b_founding_cast.py` (new, 14 tests): counts equal `seed_jobs(100)` and `check_job_seed(100)`
  agrees with the cast built; every job has a workplace and a group, and each resident works there; the self-test is
  clean; ages are drawn, in range, and carried by the world; households partition the residents, and each has one
  home; a household's kind follows its head; co-resident spouses are unions; children and siblings have the expected
  parents; every founder has a parent on record; realised household shares match the reported ones; the plan is
  deterministic for one seed; capability and skill come from the pack; the committed cast seeds equal the generator's
  output.
- Edited existing tests (listed in Changed test numbers).

Not edited: `bigville/village_eval.py`, preregistered docs, `docs/FEATURE_PHASES.md`, and the other session's files.

### The job-to-workplace map

Every JOBS key has a row. The FTE and holder columns come from `E.check_job_seed(100)`.

| job | group | role identity mean / sd | workplace | FTE needed | holders seeded |
|---|---|---|---|---|---|
| farmer | middle | 0.6 / 0.08 | farm | 4.28 | 6 |
| farm_labourer | low | 0.2 / 0.06 | farm | 1.59 | 2 |
| animal_keeper | low | 0.25 / 0.06 | farm | 0.25 | 1 |
| miller | middle | 0.58 / 0.07 | mill | 0.31 | 1 |
| baker | high | 0.88 / 0.04 | bakery | 0.42 | 1 |
| forester | low | 0.28 / 0.06 | lumber | 0.00 | 0 |
| smith | middle | 0.62 / 0.07 | carpenter | 1.10 | 2 |
| carpenter | high | 0.9 / 0.04 | carpenter | 1.10 | 2 |
| cooper | middle | 0.55 / 0.07 | carpenter | 0.55 | 1 |
| mason | high | 0.9 / 0.04 | mason | 1.05 | 2 |
| leatherworker | low | 0.3 / 0.06 | market | 0.55 | 1 |
| weaver | low | 0.3 / 0.06 | market | 0.55 | 1 |
| tailor | middle | 0.5 / 0.07 | market | 0.55 | 1 |
| fisher | low | 0.28 / 0.06 | fish | 2.00 | 2 |
| butcher | middle | 0.55 / 0.07 | market | 0.55 | 1 |
| dairymaid | low | 0.2 / 0.06 | farm | 0.55 | 1 |
| innkeeper | high | 0.85 / 0.04 | inn | 1.10 | 2 |
| mayor | high | 0.92 / 0.03 | townhall | 1.00 | 1 |
| clerk | middle | 0.55 / 0.07 | townhall | 1.60 | 2 |
| constable | middle | 0.6 / 0.07 | watch | 1.00 | 1 |
| councillor | middle | 0.62 / 0.07 | townhall | 1.10 | 2 |
| teacher | middle | 0.65 / 0.07 | school | 1.60 | 2 |
| doctor | high | 0.84 / 0.05 | surgery | 1.00 | 1 |
| midwife | middle | 0.58 / 0.07 | surgery | 1.00 | 1 |
| pastor | high | 0.82 / 0.05 | church | 1.00 | 1 |
| fishmonger | high | 0.88 / 0.04 | fishmonger | 1.00 | 1 |
| reporter | middle | 0.6 / 0.07 | press | 1.00 | 1 |
| labourer | low | 0.22 / 0.06 | market | 0.00 | 60 (spare) |

The role identity values are authored design choices (APPROX). The 016a values are kept for jobs that existed
(farmer through pastor, fisher, and the reporter and fishmonger rows). The values for smith, cooper, tailor,
weaver, leatherworker, butcher, dairymaid, and animal_keeper are new and authored.

Workplaces that are shared or borrowed: smith and cooper use the carpenter anchor. Tailor, weaver, leatherworker,
butcher, and labourer use the market. Dairymaid and animal_keeper use the farm. Forester is at the lumber deposit
but has no FTE, so no one is seeded there. Workplace anchors with no job are bank, estate, manor, and store. The stone deposit has
no job.

### Ages

`FOUNDING_AGE`: mean 36, sd 12, bounds 18 to 64, on stream seed + 9016. The bounds are the LIFE_STAGES adult
stage. The mean and sd are APPROX (a working-age adult population of a pre-industrial village). They are not
sourced to a measured age structure. The realised ages of the default town: mean 34.99, sd 10.35, min 18, max 63.

### Household construction

Households are built in four steps (`draw_founding_households`):

1. A seeded order of the founders. The head is the first founder at least `AGE_AT_FIRST_UNION.male.mean` (27.5)
   years old, or the first founder left.
2. The head's size comes from `draw_household` (HOUSEHOLD_SIZE, EXTENDED_FAMILY, EXTENDED_KIN). A marriage draw
   (EVER_MARRIED). If married, the spouse lives in the household only if an opposite-sex free founder within 10
   years of age exists and a SPOUSE_IN_VILLAGE draw succeeds. Otherwise the spouse is outside the village.
3. Adult children: free founders at least 18 years younger than each parent, filled up to the drawn size.
4. An extended household whose drawn kin is a sibling takes one free adult founder within
   `SIBLING_MAX_GAP_YEARS` of the head. Grandparents and other kin are not founders, so they are not modelled.

Children under 18 are not modelled. Every founder is an adult of working age, so a household holds only the
founders who fit these rules. The drawn size caps a household but does not force it.

Households are then assigned one home each. The map builder places 46 homes, and no resident shares a home with
another household. Household kinds follow HOUSEHOLDS from the head's role and group: landless 32, craft 5, farm 6,
institutional 3. Farm plots (8) are owned by the households of the 6 farmers, as before (`land_roles`).

### Genealogy

`draw_founding_kin` now runs after the households:

- The head's parents are one couple. They bear the head and the head's siblings, so siblings in a household share
  parents. The couple's other children (aunts and uncles) are outside the village. The parents' parents are a
  couple already in the record with probability GRANDPARENT_REUSE, else a new couple.
- A co-resident spouse, or an outside spouse for a married head, forms a union. It starts after both are of age, no
  later than the founding year, and no later than the first child less one year. The couple's children are the
  household's adult children, plus outside children up to CHILDREN_PER_UNION.
- A founder who is not a head or spouse (an adult child or sibling) marries outside the village with probability
  EVER_MARRIED.
- A head with no spouse bears their adult children alone (a single parent on record). No outside partner is
  invented.
- Two founders can be in a union only if they are co-resident spouses (checked by test).

Shape for the default town (`describe_founding_kin(100, seed=305000)`):

| measure | value |
|---|---|
| founders with a parent on record | 100% |
| founders in a union (co-resident or outside spouse) | 75% |
| founders with an aunt or uncle | 100% |
| founders with a first cousin | 33% |
| households with a co-resident spouse | 5 of 46 (10.9%) |
| adult children in households with a co-resident spouse | 1.2 on average |
| households | 46 |
| mean founders per household (realised) | 2.17 |
| mean drawn household size | 4.50 |
| households with one founder only | 50% |
| extended households (realised, a sibling lives in it) | 2.2% (1 of 46) |
| extended households drawn | 13.0% (6 of 46) |

Phase 009 reported 69% of founders joined and 2.5 children for married founders at age 30. Those numbers came from
the old generator. The new figures are not comparable.

### Household shares against HOUSEHOLD_TARGETS

The self-test still checks the draw itself, on 20,000 sample households: mean size 4.66 against 4.75 (tolerance 0.30),
and extended share 0.098 against 0.10 (tolerance 0.03). Both pass.

The realised town does not match the targets, and the comparison is not like for like:

- Mean size: 2.17 founders per household against 4.75 full members. The target counts children; the town holds
  adult founders only.
- Extended share: 2.2% against 10%. The target includes grandparents and other kin, who are not founders, so
  they cannot be housed.

### Capability and skill

- `capability` stays 0.9 for literate residents and 0.55 for the others. The values are now
  `FOUNDING_CLASS.capability_by_literacy` in the pack. They are the HEAD values, carried over, and they are authored,
  not sourced (APPROX). The realised count is 78 at 0.9 and 22 at 0.55.
- `skill` is the base skill of the job's first trade in TRADES, falling back to ACTOR_DEFAULTS.skill (0.7) when the
  trade has none. This replaces the flat 0.7. It is a deliberate behaviour change. Labourers now have 0.5 (60
  residents). The realised mean is 0.570, against 0.70 at HEAD.

## Validation

| Check | Command | Result |
|---|---|---|
| Self-test, bigville (before) | `python3 domains/bigville_entities.py` (HEAD tree) | exit 0; ERRORS 0, WARNINGS 0. Output: `selftest_before.txt` |
| Self-test, bigville (after) | same, working tree | exit 0; ERRORS 0, WARNINGS 0. Output: `selftest_after.txt` |
| Hamlet check (before) | `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS 0, WARNINGS 0. `hamlet_before.txt` |
| Hamlet check (after) | same | exit 0; ERRORS 0, WARNINGS 0. `hamlet_after.txt` |
| Suite, before (working tree, other session's files present) | `timeout 1500 python3 -m pytest -q -p no:cacheprovider` | 3 failed, 419 passed, 2 skipped. The 3 are the Ocelot tests (see below). `pytest_before.txt` |
| Suite, after | same | 4 failed, 432 passed, 2 skipped. `pytest_after.txt` |
| Suite, after, other session's Ocelot files ignored | same, with `--ignore` for the 3 Ocelot test files | 1 failed, 432 passed, 2 skipped. The 1 is the homophily test. `pytest_after_ignoring_other_session_ocelot.txt` |
| New tests | `pytest tests/test_phase016b_founding_cast.py` | 14 passed |
| Phase 016a tests | `pytest tests/test_phase016a_founding_town.py` | 3 passed (after the edits below) |

The clean-checkout baseline in the brief (397) predates the other session's test files. The working tree
without those files had 419 passing tests before my edits.

The other session's failures, verbatim from `pytest_after.txt`:

- `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`:
  `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`
- `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`:
  `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`
- `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`:
  `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'` (raised as `OcelotUnavailableError`)

My failure, verbatim:

- `tests/test_bigville_disposition_seed.py::test_homophily_same_role_overrepresented`:
  `AssertionError: (0.521505376344086, 0.3624242424242424)`, `assert 0.521505376344086 > (0.3624242424242424 * 1.5)`.
  At HEAD the same measure was 0.2527 against a baseline of 0.1024 (ratio 2.47). The ratio is now 1.44. The
  baseline rises because 60 of 100 residents are labourers, so same-role pairs look less unusual. I did not lower
  the 1.5 threshold.

Village checks (short runs, `docs/phases/phase016b/`):

- `village_check.py` (world only, `autonomous_actors=False`, 30 periods): HEAD and the new cast both show 100 alive
  for periods 1 to 4, then 0 alive and 100 deaths at period 5. Grain and bread are gone by then. Logs:
  `village_head.log`, `village_after.log`. Nobody decides in this run, so it shows only the starting stock and
  consumption. It cannot tell the two casts apart.
- `game_check.py` (`BigvilleGame`, `autonomous=True`, simple backends, 5 periods of 96 ticks each; I stopped both
  runs after period 5, so there is no FINAL line):

| period (day) | HEAD alive / deaths | HEAD grain / bread | new alive / deaths | new grain / bread |
|---|---|---|---|---|
| start | 100 / 0 | 40 / 720 | 100 / 0 | 40 / 760 |
| 1 | 100 / 0 | 10 / 669 | 100 / 0 | 0 / 783 |
| 2 | 100 / 0 | 7 / 546 | 100 / 0 | 0 / 694 |
| 3 | 100 / 0 | 7 / 503 | 100 / 0 | 0 / 583 |
| 4 | 100 / 0 | 0 / 0 | 100 / 0 | 0 / 0 |
| 5 | 100 / 0 | 239 / 0 | 100 / 0 | 168 / 0 |

  The starting bread differs by 40 because the new cast has one baker, not two. Baker FTE is 0.42, and one holder
  takes 40 loaves from the store into their own inventory at the start. Flour is 20 at HEAD and 37 in the new run on
  day 5. The runs take about 250 s per period when run side by side, so I did not run more periods.

These checks are short and use one seed. They do not show the town is sustainable. Both casts run out of bread on
day 4 and have no harvest in the first five days.

## Limits

- Children under 18 are not modelled. Adult founders fill the households, so realised household sizes are adult
  counts and cannot match the target.
- Only founders are housed. Grandparents, other kin, and servants or lodgers are not, so the extended share is low.
- Half the households (23 of 46) have one founder. A head needs an adult child at least 18 years younger, so younger
  heads have no children to take in, and the household stays small.
- No cousins except through the head's aunts and uncles. The cousin share (33%) comes from the grandparent reuse
  path.
- Founders' outside spouses and parents are not in the village, and their children are Kin nodes with no household.
- Ages are a model choice (APPROX). The household rules (head age 27.5, child gap 18, sibling gap 15) are model
  choices, not measured facts.
- The village checks are five simulated days, one seed, and the simple backends. They say nothing about the cast's
  long-run balance. The homophily result is a single seed.
- Forester has zero FTE at 100 residents, so the lumber deposit has no staff. The balance model derives that FTE.
- The founding map is not changed except for the number of homes (46 instead of 100). No workshop anchors were added
  for smith, cooper, tailor, weaver, leatherworker, butcher, or dairymaid, so those jobs share the nearest existing
  anchor.

## Deviations

1. JOBS gained two entries, `fishmonger` and `reporter` (fixed 1.0 each). The brief did not ask for this. Without
   them, the market test (`test_canonical_market_health_calendar_and_export_are_live`, the fishmonger shop has no
   resident at its cell) and the newspaper tests (no reporter) fail. Both trades already exist. The hamlet's jobs
   table is unchanged.
2. Banker (Scrooge), landlord, shopkeeper, servant, and quarrier have no JOBS entry, so they are not in the cast.
   Scrooge's anchor name is dropped. "Anchor names stay" therefore holds for four of five anchors. The fishmonger
   anchor (Doreen Ferrety) keeps its name, now on the `fishmonger` job.
3. Skill changed from the flat 0.7 to the job's trade base skill. Capability values are unchanged in number.
4. The founding-kin info line in the self-test and `describe_founding_kin` report a different shape from Phase 009.
   Its key was renamed (`mean_children_with_spouse`) because the old label counted only the household's children.
5. The `village_check.py` run in its physical-only form was unable to discriminate. I added `game_check.py` for a
   decision-driven run. Both are in the report directory.

## Changed test numbers

Every changed test number or test mechanism, old and new, with the reason.

1. `tests/test_bigville_world_migrated.py::test_canonical_world_imports_the_map_cast_and_resource_sites`:
   `len(w._households) == 100` becomes `== 46`. Households are the founding households (46 at seed 305000), with
   one home each. The old figure was one household per resident.
2. `tests/test_phase016a_founding_town.py::test_the_founding_town_is_built_from_the_bigville_pack`:
   the expected role counts came from the `FOUNDING_ROLES` row counts. They now come from the primary job of
   `E.seed_jobs(100)`. The total stays 100, read from `BALANCE_SCENARIO.residents`.
3. `tests/test_phase016a_founding_town.py::test_a_child_pack_that_changes_the_names_and_a_role_count_builds_a_different_town`
   is renamed `..._and_the_jobs_builds_a_different_town`. The child pack no longer overrides `FOUNDING_ROLES`
   (labourer -1, carpenter +1). It overrides JOBS (carpenter `per_100` 1.0 to 2.0), because counts now come from
   JOBS. The expected counts are the child's `seed_jobs(100)`. The assertion that homes equal the parent's is changed
   to: homes equal the child's households, and deposits and farm plots equal the parent's. Reason: homes now
   follow the households, which follow the jobs. The names assertions are unchanged.
4. `tests/test_phase016a_founding_town.py::test_the_hamlet_has_no_founding_town_and_from_town100_refuses_it`:
   `E.FOUNDING_ROLES` becomes `E.FOUNDING_JOBS`. Only the table name changed.
5. Not changed, still failing: `tests/test_bigville_disposition_seed.py::test_homophily_same_role_overrepresented`.
   The threshold 1.5 is not lowered (lowering it would weaken the assertion). See Open questions.

## Open questions

1. Homophily threshold. The test's 1.5 factor fails at 1.44 with the new cast. Should the threshold be
   re-derived for this cast, or should the cast keep a less labour-heavy mix?
2. Should children under 18 and non-kin lodgers be modelled, so household sizes can match Laslett's 4.75? That
   would need a lodger rule and a household role for children.
3. Forester has zero FTE, so no one works the lumber deposit. Should the balance model staff firewood at 100
   residents?
4. Should banker, shopkeeper, landlord, servant, and quarrier become JOBS entries? Scrooge's anchor depends on it.
5. Should smith, cooper, tailor, weaver, leatherworker, butcher, and dairymaid get their own workshop anchors? That
   changes the founding map.
6. The new cast is 60% labourers, on the spare-residents rule. Is that the intended mix? The village check shows
   grain running out on day 1.

## Follow-ups

- Re-derive the homophily threshold, or restore a mix the test expects (Open question 1).
- Add workshop anchors for the crafts that share anchors, and staff the lumber deposit (Open questions 3 and 5).
- If children are to count, add them as households members with a child role and adjust the household target
  comparison.
- Decide the fate of the dropped roles (Open question 4).
- Longer village runs, with more seeds, for sustainability.

## Working tree

Start (`git status --short`): the other session's files only. Modified: README.md, bigville/backends/ocelot.py,
bigville/game.py, bigville/runtime.py, bigville/seeds/bigville_actor_decision.json, docs/AGENT_BACKENDS_PLAN.md,
docs/FEATURE_PHASES.md, tests/test_bigville_game_api.py, tests/test_bigville_scenarios.py, worlds/bigville_world.py.
Untracked: bigville/game_persistence.py, bigville/mixed_ocelot_scenario.py, bigville/world_persistence.py,
docs/MIXED_OCELOT_VILLAGE_RUN_20261105.md, docs/ocelot-integration-baseline.md, docs/runs/, the persistence and Ocelot
tests, tests/test_mixed_ocelot_*.py, tools/run_mixed_ocelot_*.py.

End: the same entries, plus these files of mine:

- Modified: `domains/population.py`, `domains/bigville_entities.py`, `worlds/bigville_town100_world.py`,
  `tests/test_phase016a_founding_town.py`, `tests/test_bigville_world_migrated.py`, `packs/bigville/frames/jobs.json`,
  `packs/bigville/pack.json`, `packs/bigville/population/founding_cast.json`,
  `packs/bigville/population/household_composition.json`, `packs/test_hamlet/pack.json`,
  `packs/test_hamlet/population/founding_cast.json`, `packs/test_hamlet/population/household_composition.json`,
  `seeds/bigville_cast100.json`, `bigville/seeds/bigville_cast100.json`.
- `worlds/bigville_world.py`: my hunks are in `populate_town100`, `from_town100`'s docstring, and the data-pack
  check. The file also holds the other session's hunks (the `food` flag and `resident_plan_from_context`). Stage the
  two sets separately.
- New: `tests/test_phase016b_founding_cast.py`, `docs/phases/phase016b/` (this report, logs, pytest and self-test
  output, `village_check.py`, `game_check.py`).

Nothing was committed, branched, stashed, or reverted.

## Supervisor review

- Homophily (open question 1): `tests/test_bigville_disposition_seed.py::test_homophily_same_role_overrepresented`
  now compares odds rather than rates, with the same 1.5 threshold. A rate ratio is capped at 1/baseline,
  so it falls as one role dominates the cast even if the bias is unchanged. The odds ratio is 2.96 for the
  HEAD cast and 1.92 for this cast. For a rare role the odds ratio is a slightly looser criterion than the
  rate ratio (it is always at least as large when the rate exceeds the baseline). The test still fails for
  a cast with no homophily.
- Cast mix (open question 6) is left for the user: 60 of 100 founders are spare labourers working at the
  market, because the cast is adults only and JOBS staffs only the balance model's work streams.
