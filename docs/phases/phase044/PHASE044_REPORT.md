# Phase 044: pregnancy and birth

## Summary

Pregnancy and birth are in the world, behind a `births` switch (`physical_subsystems.births`). The switch is
off in the code, so the population is fixed unless a scenario turns it on. A fertile woman in a recorded union
conceives on a seeded daily draw. A pregnancy runs 270 days, costs food and late-term work capacity, and ends in
a stillbirth (recorded, no resident added) or a live birth. A live birth calls `birth()`, records the genealogy
(`bore`, `fathered` and the kin fields Phase 009 reads), takes the mother's household, and draws the risks of
maternal death and first-year death through `harm()`. A midwife in reach halves those risks. A newborn gets a
character and a dependent backend that proposes nothing.

The bigville pack keeps the switch off. The analytic birth flow of the founding cast is about twice the
pre-industrial English birth rate, and no village run was done (see Open questions and Limits).

Self-test: 0 errors, 0 warnings. New tests: 18 (`tests/test_phase044_births.py`), all passing. The 60-turn
simple-backend measurement is identical to HEAD on every field except wall-clock time and the label. The full suite on the
clean tree (HEAD plus all 20 hunks) gives 2243 passed, 5 skipped, 0 failed.

## Changes

### New files

| File | Purpose |
|---|---|
| `packs/bigville/world/births.json` | Table `BIRTHS`: conception rate by age band, gestation, postpartum block, pregnancy food and load, delivery risks, midwife factor, nursing hunger, fertile ages. Sources in `_doc`. |
| `packs/test_hamlet/world/births.json` | Byte-identical copy of the bigville table (the test pack has no fixed population to protect). |
| `worlds/births.py` | `BirthsMixin`, mixed into `BigvilleWorld`: conception, pregnancy, delivery, midwife, naming, genealogy, hunger rate, capacity factor, read-offs. Every method returns a neutral value with the switch off. |
| `domains/fertility_check.py` | Pure arithmetic for the self-test: `completed_family` (an exact monthly Markov chain over free, pregnant and postpartum states) and `births_per_union_year`. |
| `bigville/resident_births.py` | Game-level: `DependentBackend` (proposes nothing, has `dump_held_state`), `attach_resident`, `attach_newborns`. |
| `tests/test_phase044_births.py` | 18 tests (listed under Validation). |
| `docs/phases/phase044/PHASE044_REPORT.md` | This report. |
| `docs/phases/phase044/build_clean_tree.py` | Rebuilds HEAD plus this phase in a scratch directory (see Validation). |
| `docs/phases/phase044/hunks.json` | The 20 anchored hunks applied to shared files, with a note on each. |
| `docs/phases/phase044/files/` | Copies of the six new files above, for the build script. |
| `docs/phases/phase044/measure/` | The 60-turn measurement JSON and logs for HEAD and the phase tree. |
| `docs/phases/phase044/selftest_bigville.log`, `check_test_hamlet.log` | Self-test and pack-check output. |
| `docs/phases/phase044/pytest_full_run1_before_expectation_fix.log`, `pytest_full_run2_clean_head_plus_044.log` | Full suite on the clean tree: run 1 before the two test-expectation hunks, run 2 after them. |

### Shared-file hunks (20, all anchored, each anchor occurs once in HEAD)

`worlds/bigville_world.py` (7):
1. import `BirthsMixin` after `from worlds import daynight as _dn ...` (Phase 042 line).
2. class line `class BigvilleWorld:` becomes `class BigvilleWorld(BirthsMixin):`.
3. `PHYSICAL_SUBSYSTEM_DEFAULTS`: `"births": False` after `"object_force": False,`.
4. `pass_period`, actor loop: hunger added is `self._hunger_rate(actor)` (1.0 with the switch off).
5. `_effective_body_stat`: the result is multiplied by `self._capacity_factor(actor)` (1.0 with the switch off).
6. `_daily_life_tick`: `self._births_day()` after the resident loop (before `def add_waste`).
7. `body_state`: `**self._birth_readoffs(actor)` after `**self.aftereffects(actor)` (empty with the switch off).

`domains/world_affordances.py` (1): `BIRTHS = _PACK["BIRTHS"]` after `MEDICAL_CARE = _PACK["MEDICAL_CARE"]`.

`domains/bigville_entities.py` (2): `_check_births` inserted before `def _check_contest`; the call
`_check_births(...)` after `_check_illness(...)`.

`bigville/game.py` (2): `add_resident` and `_attach_newborns` before `_sync_animal_backends`; the first line of
`step()` is `self._attach_newborns()`.

`packs/bigville/pack.json`, `packs/test_hamlet/pack.json` (2): a `BIRTHS` entry after the last entry
(`IMPAIRMENT_NEIGHBOURS` in HEAD).

`packs/bigville/world/health.json`, `packs/test_hamlet/world/health.json` (2): `"childbirth"` added to `HEALTH.causes`.

`packs/bigville/world/marks.json`, `packs/test_hamlet/world/marks.json` (2): an empty `"childbirth": {}` row in
`MARK_HARM` (the Phase 063 self-test needs one row per cause).

`tests/test_simple_life.py`, `tests/test_scenario_runner.py` (2): test expectations only. Each asserts an exact
dictionary of the physical-subsystem defaults, and each gains `"births": False` (see Test changes below).

Note on the live tree: `packs/*/pack.json` in the shared checkout already carried Phase 067's TUI entries, which are
one-line entries. The `BIRTHS` line sits after `TUI_PROSE` there, in the same one-line style. The clean build uses
HEAD's multi-line style. `packs/*/world/tui_modes.json`, `bigville/tui/*` and `domains/tui_check.py` were not touched.

### Persistence

`bigville/world_persistence.py` (tracked) saves every world attribute and the graph generically. New state is kept
on resident nodes (`pregnant`, `conceived_day`, `due_day`, `partner`, `birth_block_until`, `kin_*`, `mother`), in
plain world lists (`_births`, `_stillbirth_log`) and as stateless draws. The checkpoint test passes for a
pregnancy and for a newborn. `bigville/game_persistence.py` was not edited (see the hook below).

## Design

- **Conception.** Each dawn, for each living woman with `kin_sex` female, an age in 15 to 49, a recorded union
  (`in_union` Union node with `ended` 0) and a living opposite-sex partner, the daily chance is
  `1 - exp(-rate / days_per_year)`. The rate is the band's `conception_per_year`. The draw is
  `_stable_draw("births", "conceive", name, day)`: stateless, keyed on the world seed, so the world's RNG stream
  is not consumed.
- **Pregnancy.** `due_day = conceived_day + 270`. While pregnant the resident's hunger rate is the life stage's
  `food` times `pregnancy_food` (1.2). Strength and stamina are multiplied by `1 - max_load x (term - from_term) /
  (1 - from_term)` over the last half of the term (max_load 0.3). A conception is blocked for 360 days after each
  birth.
- **Delivery.** A stillbirth draw (0.03) records `_stillbirth_log` and a non-public `stillbirth` event; no resident is
  added. Otherwise the child is created with `birth()` and given a sex draw (0.5), a name, and the genealogy
  (`bore` from the mother, `fathered` from a partner in or out of the village). Its first-year death draw
  (`infant_first_year_death` = 0.25) kills it at once with cause `illness`, and the mother's death draw
  (`maternal_death` = 0.01) kills her with cause `childbirth`. A midwife (`midwifery` skill above 0, on the mother's
  cell or within `midwife_reach` 1) multiplies both risks by `midwife_factor` 0.5.
- **Names.** A first name from `FOUNDING_FIRST_NAMES` at a seeded start, the next unused one if taken, and the
  mother's surname.
- **Feeding.** With the switch on, each resident's hunger rises by its life stage's `food` rate (the table already
  had it, unused until now). A nursed infant (mother alive, same cell or household) rises by `nursed_hunger` (0).
  With the switch off, every resident rises by 1.0 as before.
- **Work.** `effective_strength` and `effective_stamina` read `_effective_body_stat`, which now applies the
  pregnancy capacity factor. Nothing else reads `work_fraction`, which is still unused (Phase 045).
- **Self-test.** `_check_births` checks the table's ranges and cross-references: the bands cover every fertile
  age, `infant_first_year_death` equals `1 - INFANT_SURVIVAL`, `midwifery` is a skill when it is in the pack, and
  `childbirth` is a cause with a `MARK_HARM` row. It reports the completed family of a woman entering a union at
  the cited mean age (25.5): **4.27** children by 50, against the cited CHILDREN_PER_UNION mean of 4.8 (APPROX), and
  it is an error if more than 1.0 away (it is 0.53 away). It also reports births per union woman-year at 25, 30 and
  35 (0.261, 0.249, 0.221).

## Data and sources

Every figure in `BIRTHS` is APPROX unless noted in its `_doc`. The `_doc` cites Henry (1961), Coale and Trussell
(1974), Wrigley and Schofield (1981) and Hajnal (1965) for the shape and level of marital fertility, and a standard
obstetric reckoning for the 270-day gestation (266 from conception, 280 from the last period). **None of these
sources was checked against its text in this session.** The conception rates were chosen so that a woman who enters
a union at 25.5 has about the cited completed family (4.8, APPROX); they are a design fit, not a measured schedule.
The postpartum block (360 days), the stillbirth (0.03) and maternal death (0.01) rates, the pregnancy food and load
figures, the midwife factor and the nursing rate are design figures or order-of-magnitude values (APPROX).

`infant_first_year_death` takes 1 minus the existing `INFANT_SURVIVAL` (0.75, Phase 009, APPROX), and the self-test
checks that they agree.

The seed `bigville/seeds/bigville_fert_decide.json` describes a resident's desire for children (the quantity and
quality trade-off). It is a decision rule for residents and is not used here. Conception is a physical draw. The
seeds `bigville_life_inheritance`, `bigville_will` and `bigville_infant_care` were read for their interfaces only: the
inheritance and will rules already run on death through Phase 009, and the infant fragility is Phase 037's.

## Validation

All commands run from `/home/matt/ozmadev/bigville` on the shared checkout unless noted. The clean tree is
`/tmp/p044`, built by `docs/phases/phase044/build_clean_tree.py`.

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` (live tree) | exit 0; ERRORS (0); WARNINGS (0). `BIRTHS` INFO lines as above. Log: `selftest_bigville.log`. |
| same, clean tree `/tmp/p044` | exit 0; ERRORS (0); WARNINGS (0). |
| same, HEAD `git archive HEAD` | exit 0; ERRORS (0); WARNINGS (0). |
| `python3 -m domains.check --pack test_hamlet` (live and clean) | exit 0; ERRORS (0); WARNINGS (0). Log: `check_test_hamlet.log`. |
| `python3 -m domains.check` (bigville, live) | exit 0; ERRORS (0); WARNINGS (0). |
| `python3 tools/export_pack.py --pack bigville --out DIR` and `--pack test_hamlet` into a temp dir | exit 0. `births.json` was rewritten by the exporter (copied back, both packs). `health.json`, `marks.json` and `pack.json` in both packs match the exporter's bytes. |
| `python3 -m pytest -q -p no:cacheprovider tests/test_phase044_births.py` (live tree) | 18 passed (15.6 s). |
| 60-turn behaviour, HEAD: `PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label head60 --turns 60` in `git archive HEAD` | ran; `measure/behaviour_head60.json`, `measure/head60.log`. |
| 60-turn behaviour, phase tree (clean build), same command | ran; `measure/behaviour_p044_60.json`, `measure/p044_60.log`. |
| Comparison of the two JSON files, excluding `elapsed_seconds` and `label` | identical (`a == b`). Actions: eat 5, move 3526, none 1065, rest 1334, sleep 55, work 15; 0 deaths; 100 alive at turn 60; 845 relationships; 285 utterances. |
| Full suite, clean tree `/tmp/p044` (HEAD plus this phase): `python3 -m pytest -q -p no:cacheprovider` (run 2; run 1 used `timeout 5400`) | see the lines below. Logs: `pytest_full_run1_before_expectation_fix.log`, `pytest_full_run2_clean_head_plus_044.log`. |

Full suite, run 1 (`pytest_full_run1_before_expectation_fix.log`, 3598 s): **3 failed, 2240 passed, 5 skipped.**
- `tests/test_simple_life.py::test_physical_subsystems_default_on_and_reject_invalid_configuration` and
  `tests/test_scenario_runner.py::test_runner_replays_identically_and_records_seed_and_causal_trace` failed. Each asserts
  an exact dictionary of the physical-subsystem defaults, which now has `births`. Fixed by the expectation change under
  Test changes.
- `tests/test_phase055_concurrency.py::test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical`
  failed. This is the speed test you listed as a known flake.

After the expectation change, `tests/test_simple_life.py` (that test), `tests/test_scenario_runner.py` (that test) and
`tests/test_phase044_births.py` gave 20 passed (17.3 s) on the clean tree.

Full suite, run 2 (`pytest_full_run2_clean_head_plus_044.log`, the clean tree with all 20 hunks): **2243 passed, 5 skipped, 0 failed** (3918 s). The speed test that failed in run 1 passed in this run.

Tests added: 18 in `tests/test_phase044_births.py`:
- Table and switch: the switch is off by default and both packs have the table; the self-test has 0 errors and
  reports the births rows.
- Switch off: the population is fixed over 120 days with a forced rate of 1; the body read-offs are absent and the
  food and capacity factors are 1.
- Fertility: a monkeypatched rate of 1 a year gives first conceptions for 22 union women within three standard
  deviations of the expected count (one seed, 360 days). The seeded stream is repeatable and does not touch the
  world's RNG state. Only a fertile union woman with a living partner can conceive.
- Pregnancy: it runs to the due day, the newborn has genealogy, household and infant stage, the postpartum block is set.
  A newborn's name is unused and keeps the mother's surname. A stillbirth adds no resident. A maternal death records
  `childbirth`. A midwife in reach keeps a mother alive where the same draw kills her without one. Two worlds on one
  seed agree on the delivery.
- Costs: food rate 1.2 while pregnant; capacity factor 0.85 at three-quarters of the term; a nursed infant's hunger
  rate is 0, and an orphan's is its life-stage food rate.
- Persistence and game: the world checkpoint keeps a pregnancy, then a newborn, with its genealogy and mind; the game
  attaches a `DependentBackend` to a newborn and `step()` runs.
- Arithmetic: a zero rate gives no births; a faster rate gives more; `births_per_union_year` is below the renewal
  limit.

Existing tests edited: two, both exact-dictionary expectations (see Test changes). No assertion was removed or
weakened.

Test changes (numbers changed because the change deliberately alters the default set of physical subsystems):
- `tests/test_simple_life.py::test_physical_subsystems_default_on_and_reject_invalid_configuration`: the expected
  default dict gains `"births": False`. `births` is a new physical subsystem, default off, as `illness` was in Phase 043.
- `tests/test_scenario_runner.py::test_runner_replays_identically_and_records_seed_and_causal_trace`: the expected
  `physical_subsystems` dict gains `"births": False`, for the same reason.

## Limits

- **No growth check was run.** The brief asks the self-test to report the 100-resident town's growth against its
  source. The self-test cannot do that without a village run, which takes about five minutes a period (the brief
  says to run it only when asked). The self-test reports the completed family and the births per union woman-year
  instead.
- **The founding cast would grow too fast for the switch to default on.** Built from the cast with the switch on,
  39 of 100 residents are union women, and the analytic birth flow is **7.25 births a year, or 72.5 per 1000
  residents**. Wrigley and Schofield's pre-industrial English crude birth rate is about 30 to 35 per 1000 (APPROX,
  recalled, not checked). The likely cause is the cast's age structure: all 100 founders are adults (age 30 by
  default) and there are no children, so 39 per cent of residents are union women. The analytic figure is not a
  run, so it does not show what the town does. So the bigville pack keeps the switch off. The brief's condition for
  turning it on, a passing long-run growth check, was not met.
- **Only founding unions produce births.** No new unions form and no one remarries. The simulation does not set a
  union's `ended` flag when a partner dies; the conception check instead treats a dead partner as no partner. Births
  therefore fall as the founding couples age out of child-bearing, and the town cannot renew itself through new
  marriages. Courtship and union formation are Phase 009's and the residents' (not built here).
- **Newborns start with default body stats.** No trait, strength or skill is inherited (`add_actor` defaults).
- **First-year infant death is drawn once at birth.** It is not spread over the year through the illness and
  starvation routes, which would need Phase 045's care. The death is recorded as `illness`.
- **Feeding.** A nursed infant takes no food while its mother lives with it. An orphaned infant eats at its life-stage
  food rate (0.35 hunger a period) and passes the starvation limit (4) after about 12 periods unless someone feeds it.
  Nothing in this phase feeds it: Phase 045 gives dependants their care.
- **Pregnancies end at the mother's death.** A pregnant resident who dies of any cause before term does not deliver.
- **No village run, no simple-backend choice.** `cheap.py` is untouched. No backend chooses a union, a conception or
  a birth. The birth mechanics are physical and automatic when the switch is on.
- **Births are not announced.** The birth and stillbirth events are `public=False` with no observer. Who learns of a
  birth is open (see Open questions).
- **Stillbirths** go to `_stillbirth_log`; `_births` holds live births only.
- **`work_fraction` and `food_need`** are still unread, except as above: `food_need` is not read (the life-stage food
  rate is read directly), and `work_fraction` is still unused (Phase 045).

## Deviations

1. **The switch is a physical-subsystem key, not a pack-table value.** The brief says "behind a `births` switch (pack
   table), default OFF". The switch is `physical_subsystems.births`, default `False` in `PHYSICAL_SUBSYSTEM_DEFAULTS`,
   as `illness` is in Phase 043. The figures are in the `BIRTHS` pack table. The bigville pack does not turn the
   switch on.
2. **`childbirth` is a new HEALTH cause**, added to `health.json` (Phase 037's table) and to `MARK_HARM` in
   `marks.json` (Phase 063's table). The brief asks for maternal death through `harm()`, and the existing causes did
   not fit.
3. **Infant first-year deaths are drawn at birth**, not through the illness routes (see Limits).
4. **Hunger rule changed only with the switch on.** The brief does not say how a newborn is fed. The life-stage food
   rate applies only with the switch on, so the default run is unchanged.
5. **Game persistence needs a hook (not made).** `save_game_checkpoint` raises
   `TypeError: unsupported backend DependentBackend` once a newborn exists (checked: a game with one newborn fails to
   save). The tracked file `bigville/game_persistence.py` is owned by the Ocelot stream, so this phase did not edit it.
   The hook it needs: in `_backend_checkpoint`, `if type(backend) is DependentBackend: return {"kind": "dependent"}`
   (import from `bigville.resident_births`), and in `_build_backend`, `if kind == "dependent": return
   DependentBackend(character)`. Game saves are unaffected while the switch is off, because no newborn exists.
   The world checkpoint is unaffected: `world_persistence.py` is generic.

## Open questions

1. **Default.** Leave the births switch off for bigville, or make the switch a scenario choice until the cast's age
   structure has children? The 72.5 per 1000 figure says the current cast is not a town to switch on.
2. **Publicity.** Should a birth be a public event (every resident sees it) or known only to the household? It is
   non-public now.
3. **Unions.** Should the simulation form new unions (a courtship rule) so the town can renew itself? That is the
   residents' decision (Phase 009) and needs a seed or a backend change.
4. **Figures.** Confirm the APPROX values in `BIRTHS` against Wrigley and Schofield, Henry and Coale and Trussell.
   The conception rates are a fit to the cited completed family, not a measured schedule.
5. **Feeding of newborns.** Is nursing a sufficient model for the first years, or should Phase 045's caregivers be
   required before a newborn can be fed by anyone other than the mother?

## Follow-ups

- Hook for the Ocelot stream: the two `game_persistence.py` changes in Deviation 5.
- Phase 045: feeding and care for infants, `work_fraction` read by the work rules, and a dependent backend that acts
  when an infant becomes a child.
- A village run with the switch on and a growth band check, before any default change. It needs a cast with children,
  or a run long enough for them to grow up.

## Working tree

Start of phase (`git status --short`, 9074cc3 at HEAD): the shared checkout already held uncommitted work from other
sessions: the Phase 067 TUI modes (`bigville/tui/*`, `domains/tui_check.py`, `packs/*/world/tui_modes.json`), the
Ocelot stream (`bigville/game_persistence.py` and related), `worlds/bigville_world.py`, `bigville/game.py`,
`domains/bigville_entities.py`, and several docs and tests. None of it was staged or changed by this phase, except
that my hunks sit in the same files.

End of phase, files this phase touched in the shared checkout: the 20 hunks above in `worlds/bigville_world.py`,
`domains/world_affordances.py`, `domains/bigville_entities.py`, `bigville/game.py`, `packs/bigville/pack.json`,
`packs/test_hamlet/pack.json`, `packs/*/world/health.json`, `packs/*/world/marks.json`, `tests/test_simple_life.py`,
`tests/test_scenario_runner.py`; and the new files listed under Changes. Nothing was committed.
