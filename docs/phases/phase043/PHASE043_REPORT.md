# Phase 043: screening, treatment, well-baby care and illness

## Summary

An illness switch (`physical_subsystems.illness`, off by default) adds three things to the world:

- **Illness onset.** Each dawn, a resident who is not ill may catch fever. The draw is stateless and seeded (`_stable_draw`), keyed on the world seed, the resident, the disease and the day. The world's own state is not used. The onset uses `diagnose()`, as the burial condition does.
- **An illness course.** Each day while ill, the resident loses the disease's severity, plus progression while unscreened, less treat relief while treated, plus an infant penalty for an unvisited infant. The loss goes through `harm(..., "illness")` with fragility off. Untreated residents regain `natural_care` a day, treated residents `treated_heal`. The course ends after `course_days`.
- **Three care acts** (checkup, treat, well-baby visit). Each is the existing `care` action with a `care_kind`. Each needs a resident with the skill, standing with the patient. Each sets a flag on the body for a table-set number of days. Treatment consumes medicine from the town store through Phase 030's store guard.

With the switch off, no illness starts, and no new care option is offered. The village's numbers are unchanged by construction. The 100-resident village was not run, so no village figures are claimed.

Self-test: 0 errors, 0 warnings. Phase 043 tests: 24 new, all pass. Full suite: 1375 passed, 2 skipped, 3 failed. The three failures are the known `worlds.bigville_ocelot_adapter` import errors.

## Changes

### New pack data

- `packs/bigville/world/disease.json`: table `DISEASE`, one entry `fever` (onset per day by season, stage multiplier by life stage, `severity`, `progression`, `treat_relief`, `course_days`). All figures APPROX.
- `packs/bigville/world/medical_care.json`: table `MEDICAL_CARE` (`screen_days` 60, `treated_days` 14, `well_baby_days` 30, `natural_care` 0.01, `treated_heal` 0.04, `infant_fragility` 0.05, `medicine_per_treatment` 1.0, `skills` per act). All APPROX. Written in the exporter's layout, checked by `test_phase013a_packs`.
- `packs/test_hamlet/world/disease.json`, `packs/test_hamlet/world/medical_care.json`: both tables empty. The test pack has no medicine or midwifery skill, so it has no illness rules. With the switch on, a world on this pack finds no onsets, but a medical act raises `KeyError` on the empty `MEDICAL_CARE` table. The switch is not meant for this pack, and no test turns it on there.

### Shared files (my hunks only)

- `packs/bigville/pack.json`: two entries (`DISEASE`, `MEDICAL_CARE`) after the `HEALTH` entry, at about line 224. Tract B's persona entries are at the end of the list, far away.
- `packs/test_hamlet/pack.json`: the same two entries after `HEALTH`.
- `domains/world_affordances.py`: after `HEALTH = _PACK["HEALTH"]`, a comment and two bindings (`DISEASE`, `MEDICAL_CARE`).
- `domains/bigville_entities.py`: new function `_check_illness` (after `_check_health`), and one call after the `_check_health(...)` call. Tract B's two lines in `check_consistency` (`check_persona`) are separate and were left alone.
- `worlds/bigville_world.py`, by function:
  - `PHYSICAL_SUBSYSTEM_DEFAULTS`: `"illness": False`, with a comment.
  - `harm`: a keyword `fragility=True`. With `False`, the amount is applied as given.
  - `body_state`: read-offs `illness`, `screened`, `treated`, `well_baby` added to the returned dict.
  - `_daily_life_tick`: the lapse of care flags, the table-driven course in place of the flat daily loss (when the switch is on and the disease is in `DISEASE`), and the onset call after the burial diagnosis.
  - A new block before `birth`: `_illness_on`, `_care_flag_value`, `_set_care_flag`, `_lapse_care_flags`, `_illness_onset`, `_illness_day`, `_holds_care_skill`, `_care_act_refusal`, `checkup`, `treat_patient`, `well_baby_visit`.
  - `_actor_options`: one block before the "Ordinary object movement" comment. It offers medical care options (`action: "care"`, `care_kind`) only when the switch is on.
  - `_enact_plan`, the `care` branch: passes `care_kind=plan.get("care_kind")` to `major_action`.
  - `major_action`, the `care` branch: when `care_kind` is set, routes to `checkup`, `treat_patient` or `well_baby_visit` inside the usual claimed attempt. Unknown kinds are refused as `malformed`.
- `tests/test_simple_life.py`, `tests/test_scenario_runner.py`: one line each (see Validation).

Not touched: `bigville/backends/cheap.py` (none of its functions), `bigville/game.py`, `bigville/reporting.py`, `bigville/backends/protocol.py`, the `MAJOR_ACTIONS` table.

### New tests

- `tests/test_phase043_care.py`: 24 tests (listed below).

## Design

- **Medical acts ride the `care` action.** `MAJOR_ACTIONS` already lists `care` (kind `care`), so no new major action key was added. A `care_kind` of `checkup`, `treat` or `well_baby` selects the act. The shared plan path `_enact_plan` passes `care_kind` through, so backends that propose plans reach the same acts.
- **The effective drop** is `severity + (0 if screened else progression) - (treat_relief if treated) + (infant_fragility if infant and not well_baby)`, floored at 0. This follows the seed's formula in `seeds/bigville_doctor_care.json` and `seeds/bigville_infant_care.json`. The seeds' fees and affordability are not implemented (Phase 041 and the residents' institutions).
- **Fragility.** Phase 037 multiplies acute harm by the life stage's fragility (infant 2.0). The illness course does not use that multiplier. It uses the additive infant penalty from the seed instead, so an infant is not penalised twice.
- **Illness onset** uses `_stable_draw("illness", name, disease, day)`. The same seed, residents and days give the same onsets (tested). Onsets are not drawn from the world RNG.
- **Flags** are attributes on the body node, each with an `*_until` calendar day. The dawn tick clears a flag once its day has passed.
- **Treatment** sets `treated` and consumes medicine. It does not cure. The illness clears after `course_days`, or the resident dies first. A treated resident recovers faster (see Limits).
- **Existing paths are unchanged.** `treat()` and `care_for()` keep their Phase 030 behaviour, including the instant cure through `treat()`. The legacy flat daily disease loss still applies with the switch off, and to any disease not in `DISEASE`.

## Data and sources

Every figure is APPROX. No source was consulted for the seasonal onset rates, the stage multipliers, the drops, the durations or the recovery rates. The disease `_doc` cites Wrigley and Schofield (1981) for the shape of the pre-modern mortality pattern only. I did not check that citation against the book in this session. It is the same source the Phase 037 `HEALTH` table cites.

The durations (screen 60 days, treated 14, well-baby 30) are design choices for a village with a doctor's visit about once a season.

## Changed numbers and behaviour

Nothing changes with the switch off, except these visible shapes:

- `body_state` has four new keys. Any reader that compares the whole dict sees them.
- Two existing tests asserted the exact default `physical_subsystems` dict. They now include `"illness": False` (see Validation).
- `_lapse_care_flags` runs for every living resident each day. It changes nothing when no flag is set.

No village number is measured. With the switch on, the expected onset rate for fever is about 0.49 per adult resident-year (self-test INFO line, from the summed seasonal rates, APPROX). A seeded 360-day summer run of 50 adults gave 35 and 37 onsets for two seeds, against about 36 expected at the summer rate.

## Validation

Run from `/home/matt/ozmadev/bigville`. Logs in `docs/phases/phase043/`.

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` (before: `selftest_before.log`; after: `selftest_final.log`) | exit 0; ERRORS (0); WARNINGS (0), both before and after. INFO: fever about 0.49 onsets per adult resident-year. |
| `python3 -m domains.check --pack test_hamlet` (`check_test_hamlet.log`) | exit 0 |
| `python3 tools/generate_seeds.py --check` (`generate_seeds_check.log`) | exit 0; "match pack 'bigville' (31 files)" |
| Exporter layout: `python3 tools/export_pack.py --pack bigville --out /tmp/exp43/bigville` (and `test_hamlet`), run on a temp output only | Exit 0. `medical_care.json` was rewritten to the exporter's layout (copied back from the temp output). `disease.json` and the test_hamlet files already matched. The live packs were not exported into. |
| `pytest tests/test_phase043_care.py` | 24 passed |
| `pytest tests/test_phase013a_packs.py tests/test_scenario_runner.py tests/test_simple_life.py tests/test_phase037_health_routes.py tests/test_phase030_store_lock.py tests/test_phase014_parameters.py` | 105 passed (run after the two test edits) |
| Full suite, first run (`pytest_full_all.log`) | 6 failed, 1372 passed, 2 skipped. Three were the Ocelot import errors. Two were the exact-dict tests, fixed below. One was the export layout of `medical_care.json`, fixed above. |
| Full suite, final (`pytest_full_final.log`) | 3 failed, 1375 passed, 2 skipped, 477 s. The three failures: `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`, `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`, `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`. Each is `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`, the known baseline failure. |

### Test edits (old -> new, each a new switch key)

1. `tests/test_simple_life.py::test_physical_subsystems_default_on_and_reject_invalid_configuration`: the expected default dict gains `"illness": False`. Reason: the new switch is a physical subsystem, default off. The other keys and their values are unchanged.
2. `tests/test_scenario_runner.py::test_runner_replays_identically_and_records_seed_and_causal_trace`: the expected `physical_subsystems` dict gains `"illness": False`. Same reason.

### Tests added (`tests/test_phase043_care.py`, 24)

- The switch is off by default, and the test pack has empty tables.
- The self-test rejects a bad course length, a negative severity and an unknown skill.
- Switch off: no illness arrives in a year for an adult, a child and an infant.
- Onset is deterministic for a seed, happens, and differs for another seed. The chance follows the season and the life stage.
- An unscreened patient loses more health than a screened one (exact figures).
- A treated patient recovers while an untreated one declines (exact figures).
- An unvisited infant pays exactly `infant_fragility` more than a seen one, and an adult pays no infant penalty.
- The illness clears after `course_days`. An untreated, low-health resident dies with cause `illness`.
- Treatment consumes medicine and is refused for a distant doctor (`not_in_reach`), a locked store (`store_locked`), a patient with no illness (`not_needed`) and no medicine (`out_of_stock`).
- Only a skilled resident can checkup or treat (`unskilled`). A midwife can visit an infant. A seen infant is not seen twice.
- Acts are refused while the switch is off (`unsupported`).
- Flags lapse on their day. Read-offs appear in `body_state`.
- Medical options are offered to the skilled, only when there is something to do, and not while the switch is off.
- `major_action("care", care_kind=...)` routes correctly, and an unknown kind is refused. The plan path passes `care_kind` through. A plain `care` still uses `care_for`.

## Limits

- **No village run.** The 100-resident village was not run, with or without the switch. Its onset and death counts are unknown. A 24-turn digest would take a long time, and the brief did not ask for one.
- **The simple backend is not exercised.** `cheap.py` is untouched. A doctor's `care` options carry the existing +24 role preference for `care`, so the simple doctor is likely to choose a medical act, but nothing tests this. Its choices could be too frequent: it may checkup every unscreened resident it stands with. Not measured.
- **Fever is the only disease.** The table takes more entries, but none are added.
- **Untreated illness ends on its own** after `course_days` (14). This is a design choice not in the brief. A low-health resident can die of it first.
- **Treated residents are not cured at once.** Treatment lowers the daily cost and speeds recovery, and the course still runs its length. The legacy `treat()` still cures at once, and `care_for` still uses it.
- **No fees.** Phase 041 is not done, and the fee and affordability rules are the residents'.
- **No spread.** Illness does not pass between residents.
- **Days are calendar days.** The flags and the illness course count the dawn tick, not the `pass_period` count.
- **Read-offs.** `body_state` now carries four more keys.

## Deviations

1. **cheap.py was not edited.** The brief lists it in the write scope ("a doctor or midwife offers care when asked"). The existing doctor and midwife role preference for `care` already covers the new options, because the medical options are `care` options. Editing the choice method was ruled out by the supervisor. This is the reason for the no-edit decision.
2. **The brief's acts are `care_kind` values, not new major actions.** `checkup`, `treat` and `well_baby` are reached through `care`. The world method for treatment is `treat_patient`, since `treat` already names the legacy method.
3. **The illness course uses an additive infant penalty and no fragility multiplier.** This follows the seed's formula. It differs from Phase 037's multiplicative fragility for all other acute harm. `harm` gained the keyword `fragility=False` for it.
4. **Treatment needs an illness.** The brief does not say this. I added it so medicine is not spent on healthy patients.
5. **Seeds not loaded.** The brief's `seeds/bigville_doctor_care.json` and `seeds/bigville_infant_care.json` are not loaded. Their rules are reproduced in the world, as the brief's Goal describes.
6. **Git status moved during the run.** At the end, `bigville/backends/cheap.py`, `packs/*/world/lexicon.json` and `tests/test_phase051_lexicon.py` no longer show as modified, and `domains/persona.py` and related files are no longer untracked. Another session committed or changed them. I did not touch those files. The start and end statuses are in `git_status_start.txt` and `git_status_end.txt`.

## Open questions

1. **Figures.** Confirm the APPROX values, especially the onset rates, the stage multipliers and the drop sizes. None comes from a checked source.
2. **Untreated course.** Should untreated fever resolve after 14 days, or run until the resident recovers or dies?
3. **Simple doctor.** Should the simple backend choose checkups and treatments at all? If yes, it needs a policy in `cheap.py`, which is Tract B's file. If no, the simple doctor keeps only `care_for`.
4. **Treatment cure.** Should a treatment cure the illness at once, as the legacy `treat()` does, or only speed it?

## Follow-ups

- Phase 044 (births) can use `_holds_care_skill` and the infant penalty. Phase 045 can read the `well_baby` read-off.
- A village run with the switch on, once someone decides the figures.
- Phase 041 (physical coin) adds fees to `checkup` and `treat_patient` when it lands.
