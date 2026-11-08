# Phase 045: infants, dependants and coming of age

## Summary

Dependants are built behind a pack switch, `DEPENDANTS.enabled` (`packs/*/world/dependants.json`, off). With the switch
on:

- An infant is refused every major action with reason `infant`.
- An infant, child or youth (the life stages listed in `DEPENDANTS.stages`) acts at its life stage's `work_fraction`.
  Strength and stamina read the factor, so recipes with a strength demand progress more slowly for a child.
- Strength and stamina bases grow linearly from 0.3 and 0.4 of the adult default at birth to the whole at age 18.
  This is NEW DESIGN and APPROX.
- A dependant's care need is met on a day when a household member, awake and on the same cell, stands with it.
  An unattended dependant takes `neglect` harm (a new HEALTH cause) after its stage's span. Harm goes through `harm()`.
- A caregiver on a hungry dependant's cell can feed it one unit of its own unprepared food (the `care` action with
  `care_kind` `feed`). A caregiver away from an unattended dependant is offered the walk to it.
- A dependant that reaches the adult age gets the `adult` flag and one public `coming_of_age` event. Only residents who
  were dependants are announced.
- The simple backend's caregiver policy (`bigville/backends/dependants_policy.py`) feeds or walks to its dependant.
- A newborn keeps its `DependentBackend` while it is an infant. Once it is past infancy, the game gives it the simple
  backend, which acts.
- Read-offs `dependant` and `care_received` are in `body_state` (empty with the switch off).

Also changed, only with the switch on: the life stage from age. HEAD's whole-year bands leave gaps (3 to 4, 12 to 13,
17 to 18, 64 to 65), and an age in a gap reads as `elder`. A child of 3.5 was an elder, with the elder's age decline and
no dependant status. Births were off in HEAD, so no HEAD run met this. With the dependants switch on, a gap age belongs to
the band below.

Not built: the Mind-side rearing priors (`bl_come_of_age`, the backend's), carrying an infant, schooling, and the elder
`work_fraction` (0.35, which HEAD never read and which this phase does not apply).

Self-test: 0 errors, 0 warnings. Focused tests: 17 new, all passing (`tests/test_phase045_dependants.py`). The 60-turn
simple-backend run with every switch off is identical to HEAD. The full suite on the clean tree: 2259 passed, 5 skipped, and one failure that is the known Phase 055 speed flake (it passes alone). See Validation.

## Changes

### New files

| File | Purpose |
|---|---|
| `packs/bigville/world/dependants.json` | Table `DEPENDANTS`: `enabled` (false), `stages`, `reach_cells` (0), `neglect_after_days` by stage, `neglect_harm`, `caregiver_max_hunger`, `growth`. `_doc` cites the seeds and marks every figure APPROX or NEW DESIGN. Exporter-canonical (`tools/export_pack.py`). |
| `packs/test_hamlet/world/dependants.json` | Byte-identical copy of the bigville table. |
| `domains/dependants.py` | Pure arithmetic: `growth_fraction`, `neglect_harm`. |
| `worlds/dependants.py` | `DependantsMixin`, mixed into `BigvilleWorld`: `_age_stage`, refusal, work factor, growth, care and neglect, caregivers in reach, feeding (`feed_dependant`), dependant options, read-offs, coming of age. Every method returns a neutral value when the switch is off. |
| `bigville/backends/dependants_policy.py` | `dependant_choice(context)`: a caregiver feeds a hungry dependant on its cell, or walks to an unattended one. Reads only published affordances. |
| `bigville/resident_dependants.py` | `promote_grown_dependants(game)`: replaces a `DependentBackend` once the resident is no longer an infant. |
| `tests/test_phase045_dependants.py` | 17 tests (listed under Validation). |
| `docs/phases/phase045/PHASE045_REPORT.md` | This report. |
| `docs/phases/phase045/build_clean_tree.py` | Builds 9074cc3 + 044 + 045 in a scratch directory (exports the base, calls the 044 builder's copy and hunk functions, then applies `hunks.json`; asserts each anchor occurs once). |
| `docs/phases/phase045/hunks.json` | The 24 anchored hunks applied to shared files, with a note on each. |
| `docs/phases/phase045/files/` | Copies of the seven new files above, for the build script. |
| `docs/phases/phase045/measure/` | The 60-turn behaviour JSON and logs for HEAD and the clean phase tree. |
| `docs/phases/phase045/selftest_bigville_live.log`, `selftest_bigville_clean.log` | Self-test output on the shared checkout and on the clean tree. |
| `docs/phases/phase045/check_bigville.log`, `check_test_hamlet.log` | `python3 -m domains.check` for both packs on the clean tree. |
| `docs/phases/phase045/pytest_full_clean_head_044_045.log` | Full suite on the clean tree, final run (see Validation). |

### Shared-file hunks (24, each anchor occurs once in 9074cc3 + 044)

`worlds/bigville_world.py` (9):
1. Import `DependantsMixin` after the Phase 044 `BirthsMixin` import.
2. Class base `class BigvilleWorld(BirthsMixin):` gains `DependantsMixin`. In the shared checkout the line also has
   Phase 069's `BodyMixin`, so it reads `BirthsMixin, DependantsMixin, BodyMixin`. The clean build has no `BodyMixin`.
3. `_daily_life_tick`: `self._dependants_day()` after `self._births_day()`.
4. `_effective_body_stat`: the result also multiplies by `self._dependant_work_factor(actor)` (1.0 when off).
5. `_daily_life_tick`, life stage from age: `self._age_stage(age)` replaces the whole-year `next(...)` expression.
   With the switch off `_age_stage` is that expression unchanged.
6. `_attempt`: `sleep_code = (self._sleep_code(actor) or self._dependant_refusal(actor)) if gated else None`.
7. `_major_action_attempt`, care branch: `care_kind == "feed"` goes to `feed_dependant` before the medical acts.
8. `actor_affordances`: `+ self._dependant_options(actor)`.
9. `body_state`: `**self._dependant_readoffs(actor)` after `**self._birth_readoffs(actor)`.

`domains/world_affordances.py` (1): `DEPENDANTS = _PACK["DEPENDANTS"]` after `BIRTHS = _PACK["BIRTHS"]`.

`domains/bigville_entities.py` (2): `_check_dependants` inserted before `def _check_contest`; the call after
`_check_births(...)`.

`bigville/game.py` (2): `step()` calls `self._promote_grown_dependants()` after `_attach_newborns()`; the method
`_promote_grown_dependants` follows `_attach_newborns`.

`bigville/backends/cheap.py` (2): import `dependant_choice`; `decide()` returns a dependant act before the lamplighter
check (none when the switch is off).

`packs/bigville/pack.json`, `packs/test_hamlet/pack.json` (2): a `DEPENDANTS` entry after the `BIRTHS` entry (the last
entry in HEAD + 044).

`packs/bigville/world/health.json`, `packs/test_hamlet/world/health.json` (2): `"neglect"` added to `HEALTH.causes`.

`packs/bigville/world/marks.json`, `packs/test_hamlet/world/marks.json` (2): `"neglect": {}` row in `MARK_HARM` (the
self-test needs one row per cause, as for `childbirth` in Phase 044).

`packs/bigville/world/refusal_reasons.json`, `packs/test_hamlet/world/refusal_reasons.json` (2): the `infant` refusal code, with a description, before `destroyed`. `test_hamlet` has its own refusal table, and its self-test needs `infant` there too.

No existing test was changed. No assertion was removed or weakened.

### Shared checkout

The shared checkout carries the same hunks. Their text differs only where other sessions' work sits beside them: the
class base (`BodyMixin`), and the manifest entries and the refusal table style. These differences are cosmetic. The
clean build is the reference for the anchors.

Two files also carry another session's uncommitted rows: `packs/test_hamlet/world/refusal_reasons.json` has a Phase 069
`attending` row, and `packs/bigville/pack.json` and the health and marks tables carry other sessions' one-line
entries. Stage this phase's hunks with `git add -p`, or as a prepared snapshot, so those rows are not committed
with it. Nothing was staged or committed by this phase.

### Persistence and hooks

- The world checkpoint is generic. New Agent attributes (`dependant_days`, `care_days`, `neglect_days`, `adult`) are saved
  with the rest. Not tested by a checkpoint round trip (not in the brief's acceptance).
- `bigville/game_persistence.py` (Ocelot-owned, untracked) was not edited. An infant's `DependentBackend` still cannot be
  saved: `save_game_checkpoint` raises `TypeError: unsupported backend DependentBackend` (checked on the clean tree). A
  promoted child saves. The hook still needed is the Phase 044 one: in `_backend_checkpoint`, return
  `{"kind": "dependent"}` for `DependentBackend`, and in `_build_backend`, rebuild `DependentBackend(character)` for that
  kind.

## Validation

Base: `9074cc3`, the HEAD the brief names and Phase 044 was built on. The clean tree `/tmp/p045` is built by
`docs/phases/phase045/build_clean_tree.py --dest /tmp/p045`: 9074cc3, then the 20 Phase 044 hunks and 7 Phase 044 new
files, then this phase's 24 hunks and 7 new files.

HEAD moved while this phase ran: `51c650c` (Phase 069, committed by another session) now sits on 9074cc3. Its
`worlds/bigville_world.py` reads `class BigvilleWorld(BodyMixin):`, so the Phase 044 hunk anchored on
`class BigvilleWorld:` does not apply to it. Phase 044 (and so this phase) needs re-anchoring before it can be built on
the new HEAD. The clean build here uses 9074cc3, as the brief states.

Commands run from the shared checkout unless marked clean.

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` (shared checkout) | exit 0; ERRORS (0); WARNINGS (0). Log: `selftest_bigville_live.log`. |
| `python3 domains/bigville_entities.py` (clean) | exit 0; ERRORS (0); WARNINGS (0). Log: `selftest_bigville_clean.log`. |
| `python3 -m domains.check` (clean, bigville) | exit 0; ERRORS (0); WARNINGS (0). Log: `check_bigville.log`. |
| `python3 -m domains.check --pack test_hamlet` (clean) | exit 0; ERRORS (0); WARNINGS (0). Log: `check_test_hamlet.log`. |
| `python3 tools/export_pack.py --pack bigville --out DIR` and `--pack test_hamlet --out DIR`, every file compared with the shared checkout | exit 0 both; every file identical. |
| `python3 -m pytest -q -p no:cacheprovider tests/test_phase045_dependants.py` (shared checkout) | 17 passed. |
| `python3 -m pytest -q -p no:cacheprovider tests/test_phase045_dependants.py tests/test_phase044_births.py tests/test_phase043_care.py` (clean) | 59 passed (19 s). |
| `tests/test_phase004_located_gathering.py tests/test_phase009_kinship.py tests/test_phase011_fiscal.py tests/test_phase013a_packs.py tests/test_phase013b_data_pack.py tests/test_phase014_parameters.py tests/test_phase016a_founding_town.py` with the 045 files and the 044 and 043 tests and `tests/test_phase057_tui.py` (clean, after the fixes below) | 211 passed (145 s). |
| 60-turn behaviour, `git archive 9074cc3`: `PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label head60 --turns 60` | `measure/behaviour_head60.json`, `measure/head60.log`. |
| 60-turn behaviour, clean tree, same command | `measure/behaviour_p045_60.json`, `measure/p045_60.log`. |
| Comparison of the two JSON files, excluding `elapsed_seconds` and `label` | identical. Actions: eat 5, move 3526, none 1065, rest 1334, sleep 55, work 15; 0 deaths; 100 alive at turn 60; 845 relationships; 285 utterances. |
| Byte check: the seven new files in `docs/phases/phase045/files/` against the clean tree | identical. |
| Sanity run on the clean tree, births and dependants on (`/tmp/sanity045.py`, not in the repo): a forced conception, the birth, then 4 and 18 years of daily ticks | Birth, household and genealogy as in 044. The child was attended every day (`care_days` equals `dependant_days`), health 1.000 at 4 years, and the adult flag at 18. Six `coming_of_age` events in the run (other births also happened). 69 s. |
| Game checkpoint, clean tree (`/tmp/persist045.py`): a save with an infant, then with the same resident grown to a child | The infant's save fails (`unsupported backend DependentBackend`, the Phase 044 hook). The grown child's save succeeds. |
| Full suite, clean tree: `python3 -m pytest -q -p no:cacheprovider` (`timeout 5400`) | **1 failed, 2259 passed, 5 skipped** in 3740 s (62 min). The failure is `tests/test_phase055_concurrency.py::test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical` (ratio 0.82 under load, the known flake). Run alone it passes (`6 passed`, 45 s). The total is 2260, which is the 2243 of HEAD + 044 in the 044 report plus the 17 new tests. Log: `pytest_full_clean_head_044_045.log`. |

Full suite, first run (before the fixes below; the terminal output, since the log was overwritten by the second run):
**10 failed, 2250 passed, 5 skipped** in 4626 s.
- Seven `test_hamlet` tests failed: `test_phase004_located_gathering`, `test_phase009_kinship`, `test_phase011_fiscal`,
  `test_phase013a_packs` (export rerun), `test_phase013b_data_pack`, `test_phase014_parameters` and
  `test_phase016a_founding_town`. I read the tracebacks of phase004, phase009 and phase013a only. Those show
  `DEPENDANTS: 'infant' is not a REFUSAL_REASONS code` (the test_hamlet pack has its own refusal table) and the
  exporter's byte differences in `world/dependants.json`. Fixed by the `infant` row in the test_hamlet refusal table and
  by writing `dependants.json` as the exporter writes it.
- `test_phase055_concurrency.py` speed test: the known flake.
- Two `test_phase057_tui.py` HTTP tests (`test_over_http_*`): both pass alone on 9074cc3 and on the clean tree, so the
  failure is load-related. They pass in the set run above.

Tests added: 17 in `tests/test_phase045_dependants.py`:
- Table and self-test: the switch is off by default and both packs carry the table; the self-test has 0 errors and
  0 warnings, reports the growth curve and the gap bands, and rejects a bad neglect span.
- Arithmetic: growth is linear and holds at adult age; neglect harm waits out its span and scales with the care need.
- Switch off: an infant acts, nothing grows, no dependant option or read-off appears.
- Infants and children: an infant is refused with reason `infant` (both `major_action` and `enact_plan`); a child
  moves, and its strength is 0.25 of the same resident with the switch off; growth runs from the infant value to the
  adult default.
- Care and neglect: an attended infant is not harmed; an unattended one takes harm only after its span, with cause
  `neglect`; a caregiver feeds on the cell and is refused from afar (`not_in_reach`); the walk is offered only when no
  one attends.
- Coming of age: a youth crosses the adult age, gets the flag and one `coming_of_age` event, and the event does not repeat.
- The gap rule: an age in a gap is elder with the switch off and the band below with it on, including at the dawn tick.
- Backends: the simple caregiver feeds its infant through `BigvilleGame.step()`; a newborn keeps a `DependentBackend`
  until it is a child, then acts with the simple backend, and a newborn who is still an infant keeps its dependent backend.

Test changes: none. No existing test was edited, and no assertion was removed or weakened.

## Limits

- **Only physical facts and caregiver rules.** The world publishes the acts and checks them. The simple backend's
  policy (feed, then walk) is its own. The Mind-side priors from `bl_come_of_age` are not built (the brief leaves them
  to the backend). No seed rule is executed here. `bigville_infant_care` is Phase 043's well-baby care, which this phase
  reads but does not change.
- **Growth is NEW DESIGN.** The start fractions (0.3 strength, 0.4 stamina) and the linear rise are APPROX. Every newborn
  rises to the same adult default, because `add_actor` draws no individual body. No trait is inherited.
- **Job rate.** A child's job rate follows its strength only for recipes with a strength demand (Phase 049's
  `min(1, strength / demand)`). Recipes without a demand are not slowed. The speed term (exhaustion) is not scaled.
- **Contest double count.** `CONTEST.life_stage_force` (Phase 029) already gives a child 0.8 of an adult's force in a
  contest. The dependants factor now multiplies in too, so a child's contest force is 0.2 of an adult's. This is not
  corrected here (a contest-rule change belongs to the contest phase).
- **Feeding.** A caregiver feeds only from its own unprepared food. A prepared meal (which needs serving equipment) is not
  used for an infant. Nothing feeds an orphan except a caregiver with food in reach; an orphan with no food starves
  through the existing starvation route.
- **Caregivers.** Any household member who is an adult (not a dependant) and awake, on the same cell, counts as a
  caregiver. Presence is the care. Carrying an infant is not built, so an infant does not follow its mother.
- **Coming of age is announced, not learned.** The `coming_of_age` event is public, as `create_event` defaults. Nothing
  tells the residents, and no belief changes.
- **Life-stage gap rule.** With the switch on, a founder aged 64 to 65 is an adult until 65, not an elder for the year
  before. The switch-off path is HEAD's rule.
- **Elder work_fraction** (0.35, LIFE_STAGES) is not applied. The brief names children. Elders are unchanged.
- **Agent view and LLM.** With the switch on, the world publishes `care` options with `care_kind` `feed` and `move`
  options with `dependant`. Their handling in the agent view, the prompt packet and the reply schema (Phases 052 to 054)
  is not checked here. The switch is off in the shipped pack, so no default view shows them.
- **Infant checkpoint** fails until the Ocelot hook is in (see Persistence and hooks).
- **Founding cast.** All founders are adults, so the switch changes nothing for them except the gap rule above.
  Births are still off, so no infant exists in the shipped pack.

## Deviations

1. **The switch is a pack table value, `DEPENDANTS.enabled`, not a `physical_subsystems` key.** The brief asks for its own
   switch or the births switch, default off. The pack-table form matches Phases 042, 064 and 065. A physical-subsystem
   key would change the exact-dict expectations in `tests/test_simple_life.py` and `tests/test_scenario_runner.py`, which
   Phase 044 already edited.
2. **`DependentBackend` itself does not act.** Phase 044's file is not edited. The game replaces a grown child's
   `DependentBackend` with the simple backend (`resident_dependants.py`). The end state is the one the brief asks for: the
   dependent backend acts once the child is past infancy.
3. **A HEAD bug in the life-stage rule is fixed, behind the switch.** See the gap rule above. This is an existing
   defect, not a Phase 045 feature, and it is gated so the switch-off path is HEAD's.
4. **Body growth is a function of age, not a stored draw.** Each dawn sets `str_base` and `sta_base` from the age; nothing
   is stored beyond the existing base attributes.
5. **Shared-checkout line.** The class-base hunk sits beside Phase 069's `BodyMixin` in the shared checkout. The clean
   build has no `BodyMixin`, so its anchor differs. The effect is the same.

## Open questions

1. **Job rate for non-demanding recipes.** Should the work factor also scale the speed term, so a child's non-strength
   jobs also slow down? That changes exhaustion and is a Tract A decision.
2. **Contest double count.** Keep `CONTEST.life_stage_force` for children, or drop it now that the work factor applies?
3. **Feeding.** Should a caregiver be able to feed from a shared household larder, not only from its own food? Should a
   prepared meal be allowed for a dependant?
4. **Announcement.** Should `coming_of_age` be public, or known only to the household?
5. **Priors.** Who writes the Mind-side rule that shapes adult priors from `care_received` (the backend's `bl_come_of_age`)?
6. **Figures.** Confirm or replace the APPROX values in `packs/bigville/world/dependants.json`: the growth start fractions,
   the neglect spans and harm, and the caregiver hunger limit.

## Follow-ups

- Ocelot stream: the two `game_persistence.py` changes in Persistence and hooks.
- The Phase 044 open questions still apply (births default off; publicity; unions).
- A 100-resident village run with births and dependants on, before any default change. The run was not done here.
