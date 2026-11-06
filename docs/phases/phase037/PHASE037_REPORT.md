# Phase 037: one health, several routes to death

## Summary

Health is one variable, the actor's `health_value` (0 to 1). Every acute route down goes through `harm(actor, amount, cause)`, which applies the life stage's fragility, tags the cause and records a death when health reaches 0. Routes: injury, illness (daily disease loss and spoiled or raw meals), starvation (each period past `starve_limit`), exhaustion (a repeated collapse), and age (a daily decline for elders). Violence and intoxication are accepted causes with no caller yet (Phases 038 and 034). Recovery by care, treatment and ordinary sleep goes through `_heal`, capped at `max_health`. Every death records its cause in the death record and the death event. `SimulationReporter.deaths_by_cause()` counts them.

Starvation timelines are unchanged: `starve_harm` is 1.0, so a healthy resident dies in the first period past the limit, as before. The existing starvation tests pass without edits.

Self-test: 0 errors, 0 warnings. Phase 037 tests: 17 new, all pass. Full suite with the other session's eight untracked test files ignored: 1025 passed, 1 skipped, 0 failed. Those eight files: 197 passed, 1 skipped, 3 failed, all three the known `worlds.bigville_ocelot_adapter` import failures.

## Changes

### Pack data

- `packs/bigville/world/health.json` (new): table `HEALTH`. Keys `max_health`, `causes`, `age_rate` (per life stage, per year), `fragility` (per life stage), `starve_harm`, `illness_harm`, `rest_health_gain`, `exhaustion_harm`, `exhaustion_free_collapses`, `exhaustion_window_periods`. The `_doc` gives every figure's status and source.
- `packs/test_hamlet/world/health.json` (new): copy of the same table, with a `_doc` that points to the bigville citations.
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`: one `HEALTH` entry each.
- `packs/bigville/world/actor_defaults.json`, `packs/test_hamlet/world/actor_defaults.json`: `body.health` removed. The starting health is `health_value`, the only copy.

### `domains/world_affordances.py`

- Binds `HEALTH = _PACK["HEALTH"]`. (2 lines.)

### `domains/bigville_entities.py`

- New `_check_health`, called from `check_consistency` after `_check_exhaustion`. It checks: `max_health` in (0, 1]; the seven causes are present, unique and non-empty; `age_rate` and `fragility` cover exactly the `LIFE_STAGES` keys; the rates and multipliers are valid; `starve_harm` is positive; `illness_harm` is in [0, 1]; the harms are non-negative; the two whole-number windows are integers. It also writes two INFO lines: the years an elder takes to decline to 0 (20.0), and the periods past the limit that starvation takes to kill a healthy adult (1).

### `worlds/bigville_world.py` (my hunks only; 23 hunks)

- `health(actor)`: the one health variable.
- `harm(actor, amount, cause)`: acute harm, times fragility; a `ValueError` for a cause not in `HEALTH.causes`; death through `record_death` at health 0.
- `_drop_health`, `_heal` (caps at `max_health`), `_stable_draw` (see Design), `_exhaustion_collapse`.
- `injure`: the health drop is now `harm(..., "injury")`. The event text, the `injury` attribute and the `"injured"` label are unchanged.
- `treat` and `care_for`: their health gains go through `_heal`.
- `_daily_life_tick`: the age decline (`age_rate` per year, divided by `days_per_year`) for the actor's life stage. The disease loss is `harm(..., "illness")`. A dead resident is skipped for the rest of the dawn tick. The injury recovery uses `_heal`.
- `pass_period` (starvation branch in the metabolism loop): `hunger > starve_limit` is `harm(..., "starvation")` instead of setting `alive` to 0.
- `_record_death_event`: sets the actor's `death_cause` attribute.
- `_record_meal`: rolls the meal's `illness_risk` with `_stable_draw`; a hit is `harm(..., "illness")`. Adds a `meal_count` attribute.
- `_resolve_sleep`: a collapse calls `_exhaustion_collapse` first, and lies down only if the resident lives. A sleeper wakes at `min(rest_cap or collapse_cap, effective_stamina)` (see Deviations). An ordinary sleep tick calls `_heal(rest_health_gain)`. A full rest (not a collapse) sets `collapse_run` to 0.
- `_effective_body_stat`: reads `health(actor)`, not the body's copy. `body_state["health"]` reads the same variable.
- `add_actor`: the body node no longer holds `health`. Actor nodes gain `collapse_run` and `last_collapse_period`.

### `bigville/reporting.py` (one additive method)

- `SimulationReporter.deaths_by_cause()`: counts the world's `_deaths` by cause. Placed before `economy`. No other part of the file changed.

### Tests

- New `tests/test_phase037_health_routes.py` (17 tests, below).
- `tests/test_phase032_training.py`: the two health tests set the health variable on the actor, not on the body. Setup only, no assertion changed. Old -> new, each of four lines: `w.eng.set_attr(body, "health", 0.5)` -> `w.eng.set_attr(w._actors["Ada"], "health_value", 0.5)` (and the same for `1.0`); `w.eng.set_attr(w._bodies["Smith"], "health", 0.5)` -> `w.eng.set_attr(w._actors["Smith"], "health_value", 0.5)` (and `1.0`). Reason: the body's copy of health is removed (one health variable).

### Existing tests checked

Starvation tests, all unchanged and passing:
- `tests/test_bigville_world_migrated.py::test_residents_get_hungry_eat_food_and_starve_without_it` (5 periods, no food, dead)
- `tests/test_simple_life.py::test_without_food_resident_starves_as_periods_pass`
- `tests/test_simple_body_food.py::test_food_absent_control_starves_after_configured_period_horizon`
- `tests/test_phase014_parameters.py` (death-cause fallback `starvation` and `unknown`, and `starve_limit` overrides)
- `tests/test_phase022_recipe_stamina.py` (uses `starve_limit` for hunger scaling)

Animal starvation (`tests/test_phase008_animal_lifecycle.py`) does not use the resident path and passes unchanged.

## Design

- **One variable.** `health_value` on the actor is the only health number. The body's `health` and `ACTOR_DEFAULTS.body.health` are gone. Effective strength and stamina (Phase 032) read `health_value`. The string `health` attribute stays as a label (`healthy`, `injured`, `malnourished`, a disease name, `dead`), set by the existing care and disease rules.
- **Causes.** Every death records one cause, the route that took health to 0. Chronic age decline tags `age`. Each acute harm tags its own cause. `record_death(cause=...)` stores the cause in `death_cause`, the death record and the event detail.
- **Fragility.** Acute harm (injury, illness, starvation, exhaustion) is multiplied by the life stage's fragility. The age decline is not, since the brief names only acute harm.
- **Starvation.** `starve_harm` is 1.0 (the full health of a healthy resident). A resident past the limit takes 1.0 per period, so dies in the first such period. Smaller values soften starvation into several periods (tested with 0.5).
- **Spoiled and raw food.** The Phase 027 `illness_risk` is the chance per meal. `_record_meal` rolls it with `_stable_draw`, a draw from a local `random.Random` seeded by a string made of the world's `_burial_seed`, the eater, the town period, the food kind and the meal count. Nothing is stored on the world (the pattern `_burial_roll` uses). A hit is `harm(eater, illness_harm, "illness")`. Same world, same meals, same hits (tested).
- **Exhaustion.** A collapse counts toward a run of collapses. A collapse within `exhaustion_window_periods` (3 days) of the previous one extends the run. The first collapse of a run is free. Each later one harms `exhaustion_harm` (0.1) under cause `exhaustion`. A full rest (sleep to the cap) ends the run. This is the APPROX rule for "repeated collapse without recovery within a window".
- **Recovery.** Care (`care_for`, treatment) and the daily injury recovery heal through `_heal`. Ordinary sleep heals `rest_health_gain` (0.002) per clock tick, capped at `max_health` (1.0).
- **Age.** Elders decline by `age_rate` (0.05 a year) spread over days, so a healthy elder dies in about 20 years (about 7200 days in the 360-day year). No other stage declines.

## Data and sources

Every figure is APPROX unless stated. The seed `seeds/bigville_life_health.json` (v1.0.0) gives the rules and no values. Infant fragility is named in the infant-care seed (`infant_fragility`), but it has no value there either.

| Figure | Value | Status and source |
|---|---|---|
| `max_health` | 1.0 | The top of the existing 0 to 1 `health_value` scale (CARE). Not a sourced figure. |
| `age_rate` elder | 0.05 a year | APPROX. The mortality hazard rises roughly exponentially with age after early adulthood, doubling about every 8 years (Gompertz law; Gavrilov and Gavrilova, 2001, *The Biology of Life Span*). A linear decline is a simplification of that curve. |
| `fragility` infant | 2.0 | APPROX, no value in the seed. Infant deaths were roughly 15 to 20 per cent of births in the first year in pre-modern England (Wrigley and Schofield, 1981, *The Population History of England 1541-1871*). That supports an infant being much more fragile. The multiplier is a design choice, not derived from those figures. |
| `fragility` others | 1.0 | Design choice. |
| `starve_harm` | 1.0 | Chosen so the existing timelines hold (see Design). |
| `illness_harm` | 0.1 | APPROX, the seed's `illness_amount` has no value. |
| `rest_health_gain` | 0.002 per tick | APPROX, about 0.06 over an 8-hour sleep. |
| `exhaustion_harm` | 0.1 | APPROX. |
| `exhaustion_free_collapses` | 1 | Design choice. |
| `exhaustion_window_periods` | 3 | APPROX (days). |

## Changed numbers and behaviour

Changes that reach a running village, none of them measured:
- Infants take twice the acute harm from injury, illness and starvation, and a daily disease loss. An infant with a fever loses 0.1 a day, not 0.05. An infant injured for 0.6 dies, where an adult survives it.
- A disease death now records cause `illness`. It used to record the disease's name, for example `fever`.
- A spoiled meal can make its eater ill (0.1 health), at the Phase 027 risk. Most meals are not spoiled, so this is rare in practice.
- A sleeper with health below 1 wakes at its stamina capacity (health times stamina), not at 1.0. A healthy sleeper is unchanged.
- Each collapse is a harm event if the resident has collapsed before in the window.
- Founding residents are all under 65 (checked: the 100-resident cast has no one aged 65 or over, and every founder starts at health 1.0). The age decline therefore first reaches a resident when they turn 65.

## Validation

Run from `/home/matt/ozmadev/bigville`. Logs are in `docs/phases/phase037/`.

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` (`selftest_bigville.log`) | exit 0; ERRORS (0); WARNINGS (0). INFO lines: "a healthy elder declines to 0 in 20.0 years of elder age", "starvation kills a healthy adult 1 period(s) past starve_limit" |
| `python3 -m domains.check --pack test_hamlet` (`check_test_hamlet.log`) | exit 0 |
| `python3 tools/generate_seeds.py --check` (`generate_seeds_check.log`) | exit 0; "match pack 'bigville' (31 files)" |
| `python3 tools/export_pack.py` and `--pack test_hamlet` | normalised 203 tables each; see the Limits note on untracked files |
| `pytest tests/test_phase037_health_routes.py` | 17 passed |
| `pytest tests/test_phase024_exhaustion.py tests/test_phase032_training.py tests/test_phase014_parameters.py` | Not run as a group after the last fix. Phase 037 changes were covered by the full run below, which includes all three files and passes. |
| Full suite with the other session's eight untracked test files ignored (`pytest_other_session_ignored.log`) | 1025 passed, 1 skipped, 0 failed (364.9 s) |
| The eight ignored files (`pytest_other_session_files.log`) | 197 passed, 1 skipped, 3 failed. The three are `test_real_ocelot_advertises_only_wired_communication_capabilities`, `test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control` and `test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`, each `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'` |

I did not take a pre-change full-suite baseline, so I have no before-and-after count. The 17 new tests are the only additions to the counts.

The 100-resident village was not run, and no village figures are claimed.

## Tests added (test_phase037_health_routes.py)

- The table names the seven causes, and health has one home (no body copy). `harm` refuses an unknown cause.
- A large injury kills and records `injury`. A small one does not kill an adult.
- An infant takes double acute harm and dies of an injury an adult survives.
- An elder declines and dies of age at about 20 years (within two days). An adult of 30 to 50 does not decline.
- Starvation kills at the limit plus one period (existing timeline). A softer `starve_harm` (0.5, child pack) takes two periods.
- Disease drains health daily and its death is `illness`.
- Care heals and recovery stops at `max_health`. An ordinary sleep heals a tick at a time and wakes at the body's capacity (4 ticks, reserve 0.6).
- A second collapse within the window harms with `exhaustion`. A full rest ends the run. A collapse outside the window is free. Repeated collapse can kill with `exhaustion`.
- Spoiled meals make the eater ill at risk 0.3 (about 90 of 300 meals, within 25) and the draw is deterministic. Fresh meals never do.
- Every death has a cause from the table, and `deaths_by_cause()` counts `{"injury": 1, "starvation": 1}`.

## Limits

- The 100-resident village was not run. Its effect is inferred, not measured.
- Violence and intoxication have no caller yet, so their causes are accepted but never recorded in a run.
- Illness from food is an acute drop of 0.1 with no lasting disease. Nothing diagnoses it or treats it through the disease rules.
- Age decline is linear, not Gompertz (see Data and sources).
- `harm` on an injury applies fragility to the health drop, but the `injury` attribute (which care heals) is the unscaled severity. An infant's injury heals at the same rate per point as an adult's, though it costs twice the health.
- Sleep wakes at health-scaled capacity. `rest` clamps to effective stamina as before (Phase 032), so a body's stamina cannot exceed its capacity except through training.
- `_stable_draw` is keyed on the town period in days. Two meals by one resident on one day are told apart by the meal count, so the draws do not repeat.

## Deviations

1. **Body `health` removed (brief: one variable).** The body node and `ACTOR_DEFAULTS.body.health` are gone from both packs. Effective stats read the actor's `health_value`. Three tests that set the body's copy now set `health_value` (four lines, listed under Changes).
2. **Sleep wake rule (not in the brief).** Phase 032 clamps the reserve to effective stamina, which depends on health. An injured sleeper at health 0.6 could never reach `rest_cap` 1.0, so the wake check never fired. The sleeper now wakes at the lower of the cap and the effective capacity. This changes nothing for a body with capacity at least 1.0, which covers every founder with no injury. It was found by a test and fixed in this phase.
3. **Disease death cause.** A disease's daily loss now records `illness`, not the disease name. The brief lists `illness` among the causes.
4. **Reporting.** The brief asked for the report to count deaths by cause. I added a reporter method, not a new key in `population()`'s output, to keep that output's shape unchanged for other readers.

## Open questions

1. **Figures.** Confirm the APPROX values, especially `age_rate` (linear 0.05 from 65), `fragility` infant 2.0, `illness_harm` 0.1, and the three exhaustion values. None comes from the seed, and the sources cited support order of magnitude only.
2. **Starvation softness.** Keep `starve_harm` at 1.0 (the timelines hold) or soften it? Any value below 1.0 changes the existing starvation timelines, and the three tests that count periods would need new numbers.
3. **Wake rule.** Should a sleeper wake at effective stamina (as implemented) or keep waking at 1.0? The second reads more naturally as rest but leaves injured sleepers stuck.
4. **Food illness.** Should a spoiled meal's illness be a lasting disease (through `diagnose`) rather than a one-off drop?

## Follow-ups

- Phase 038 (strikes) and Phase 034 (intoxication) call `harm` with `violence` and `intoxication`.
- Phase 043 (screening and treatment) can use `_heal` and the causes.
- Phase 044 and 045 (births and dependants) must set `life_stage` through the existing age rule, so an infant gets the fragility.

## Shared files and git

- Shared-file hunks I added: `worlds/bigville_world.py` (23 hunks, listed under Changes), `domains/bigville_entities.py` (`_check_health` and its call), `domains/world_affordances.py` (`HEALTH` binding), `bigville/reporting.py` (`deaths_by_cause`), `packs/*/pack.json` (one entry each), and `packs/*/world/actor_defaults.json` (one line each).
- The other session's hunks were left alone. In `worlds/bigville_world.py` they are the `"food"` flag on the container fetch option (`bigville_world.py` near line 7297), and `resident_plan_from_context` (near line 7638). `git add -p` is needed to stage only my hunks in that file.
- **Untracked files of the other session were rewritten.** `tools/export_pack.py` normalised all tables, and that run rewrote `packs/bigville/world/lexicon.json` and `packs/test_hamlet/world/lexicon.json` (both untracked, owned by the other session) at 15:15. I did not keep a copy of their bytes, so I cannot say whether the content changed. Those two files should be checked against the other session's copy before commit.
- A first full-suite attempt in this phase failed one assertion in `tests/test_phase014_parameters.py::test_a_child_pack_changes_actor_defaults_and_the_tick_length_changes_timed_work` (line 119, `LEXICON_QUANTITIES[duration]... no band starts at 7.5`). It did not reproduce: the same test passed in isolation and in the full run with the other session's eight files ignored. The likely cause is the other session's lexicon files, which change during this run. Not investigated further.
- Git status start: the other session's modified and untracked files (listed in the standing rules), plus `packs/*/pack.json`, `packs/*/world/actor_defaults.json` and `worlds/bigville_world.py` as shown in the first `git status`. End status: `git_status_end.txt`. My new files: `packs/bigville/world/health.json`, `packs/test_hamlet/world/health.json`, `tests/test_phase037_health_routes.py`, `docs/phases/phase037/`.

## Supervisor review

- Accepted: one health variable (`health_value`), `harm(actor, amount, cause)`, starvation at `starve_harm` 1.0 per period past the limit (existing timelines unchanged), and the sleep wake rule at min(cap, effective stamina).
- Note for Tract B: during this phase `tools/export_pack.py` rewrote Tract B's then-untracked `packs/{bigville,test_hamlet}/world/lexicon.json` into the exporter's layout (15:15). The prior bytes were not kept; please check those two files before committing Phase 051.
- The Phase 051 `check_lexicon` call in `domains/bigville_entities.py` was left out of this commit (it is Tract B's hunk).
