# Phase 070c: injury by what the action uses, and a preschooler life stage

## Summary

Two user decisions, both implemented in the pack, the physics and the self-test.

1. **Injury by action.** A located injury now lowers only the capacities of the actions that use its region.
   `ACTION_BODY_USE` (pack) maps each action to the regions and capacities it uses. The whole-body read, with no action,
   is unchanged in meaning. With an empty ledger every factor is exactly 1.0.
2. **Preschooler.** `preschooler` (3 to 5 years) inherits from `child` through `LIFE_STAGES.inherits`. It overlays only
   the sleep need (10 h). Inheritance is resolved once, in `domains/pack.py`. Comparisons by name read the stage's chain.

The self-test is at 0 errors and 0 warnings on `bigville` and on `test_hamlet`. `generate_seeds --check` passes (31 files).
The founding cast is unchanged (ages 18 to 63), so 0 residents changed stage. The 60- and 200-turn simple village digests
equal the base, with 0 deaths. The full suite ends with 21 failures, 2980 passed and 7 skipped. Three are the known Ocelot
baseline, eight also fail on the pre-edit snapshot, nine are in the other session's in-progress work, and one passes
when rerun alone. Two lamplighter failures are not attributed by a run (see the attribution section).

Two consequences need a decision (see Open questions). Moving the infant band to 0 to 2 moves 3-year-olds from infant to
preschooler, which changes their care, work, food and acuity. The age-word bands now say "a young child" for 3 to 5.

## Changes

Files (this phase only; other sessions' uncommitted hunks in the shared files were left in place).

- New: `domains/life_stage_check.py`, `tests/test_phase070c_body.py` (9 tests), `tests/test_phase070c_stages.py` (14 tests), `docs/phases/phase070c/`.
- Changed, mine only: `worlds/body.py` (`pack_tables`, `action_row`, `recipe_action`, `_body_capacity_factor`, `_speed_of`,
  `_recipe_body_use`), `worlds/dependants.py` (`_stage_chain`, `_life_stage_is`, `_is_dependant`, `_dependant_refusal`,
  `_dependant_work_factor`), `worlds/births.py` (the nursed-hunger check), `bigville/resident_dependants.py` (the infant
  promotion check), `domains/pack.py` (`_compile_life_stages`, `fill_life_stage_inheritance`, `stage_dicts`, `load_pack`),
  `domains/interoception_check.py` (`_check_phase070c`), `packs/{bigville,test_hamlet}/world/{interoception,life_stages,lexicon}.json`,
  `tests/test_phase045_dependants.py` (see Changed numbers).
- Changed, shared (my hunks only): `worlds/bigville_world.py` (by function: `move_actor`, the stamina consumption in the
  exerted branch, `_job_strength_rate` and `_job_recipe_name`, `_spend_job_stamina`, `_crew_spend`, `_recipe_preview_compute`,
  `_capable`, `_capability_terms`, `_container_plan`, `_displace_plan`, `_finish_attempt`, `_spend_attempt_stamina`, `_queue_effort`,
  `_enact_carry`, `_contest_spend`, `_contest_side`, `_member_force`, `strike_begin`, `restrain_begin`, `throw_begin`, `throw_resolve`,
  `_weapon_for_strike`, `_throw_range`, `struggle`, `_holds_tick`, `effective_strength`, `speed_factor`, `strength`, the walking
  exertion effort, `_illness_day` (infant fragility), `well_baby_visit` (infant check), `_actor_options` (the well-baby option));
  `domains/world_affordances.py` (one line: `LIFE_STAGE_CHAIN` after `LIFE_STAGES`); `domains/bigville_entities.py`
  (`_check_dependants`: inherited dependant spans, and the call to `check_life_stages`); `packs/{bigville,test_hamlet}/pack.json`
  (manifest lines for ACTION_BODY_USE, RECIPE_BODY_USE and STAGE_KEYED, after INJURY_EFFECTS and LIFE_STAGES).
- Data: `packs/*/world/interoception.json` (`ACTION_BODY_USE`, `RECIPE_BODY_USE`, leg strength weight, `BODY_RATES.sleep_need_hours.preschooler`),
  `packs/*/world/life_stages.json` (bands, `preschooler`, `STAGE_KEYED`), `packs/*/world/lexicon.json` (the preschooler phrase, and the age band).

The stage-keyed tables themselves (`health.json`, `contest.json`, `disease.json`, `impairment.json`, `persona.json`,
`perception.json`, `dependants.json`) were not edited. Their preschooler entries come from the loader.

### Decision 1: injury by action

**Data** (`packs/bigville/world/interoception.json`, and the same in `packs/test_hamlet`):

- `INJURY_EFFECTS.weights.leg.strength` is new, 0.5 (APPROX). Pushing, pulling, carrying, lifting and restraining use the leg.
- `ACTION_BODY_USE` (new table): action to region to capacities.
- `RECIPE_BODY_USE` (new table): `dig_ore` and `dig_grave` use `dig`. Other recipes use `work`.
- Manifest lines for both tables in `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`.

Action to region table (capacities in brackets; `s` strength, `t` stamina, `v` speed):

| Action | Regions and capacities | Source of the row |
|---|---|---|
| walk (move) | leg [v] | walking intervals; brief: leg for speed |
| carry, lift (joint carry) | arm [s], back [s, t], leg [s] | brief: back, arm, leg for strength; back stamina from INJURY_EFFECTS |
| work (recipe default) | arm [s] | brief: arm by default |
| dig (dig recipes) | arm [s], back [s, t] | brief: digging uses back |
| throw | arm [s] | brief: strikes and throws use arm |
| strike, hit, smash, cut, chop, saw, open, pry, force | arm [s] | brief: hit, smash, chop, saw use arm |
| push, pull, drag | back [s, t], leg [s] | brief: push, pull, drag use back and leg |
| restrain, struggle | arm [s], back [s, t], leg [s] | brief: restrain, struggle use arm, back, leg |
| contest (take, defence, the holder's grip) | arm [s], back [s, t], leg [s, v] | brief: contests use arm, back, leg |
| speak, sleep, rest, eat, drink | none | brief: speech, sleep, rest, eat use nothing |
| default (any other verb) | arm [s] | a verb with no row |

Not in the table: **kick** (no such action exists in `VERBS` or the major actions), **climb** (no such action), and
**ploughing** (no field action; the only plough recipe is `forge_plough`, which is forging and uses the arm). The chest and
head weights are in INJURY_EFFECTS, but no action row names them, so they lower only the whole-body read.

**Rule.** `factor(action, capacity) = max(floor, 1 - sum over the regions the action names for that capacity of
weight x ledger)`. With no action, every region counts (the general read). Factor 1.0 exactly with an empty ledger.

**Code.**

- `worlds/body.py`: `pack_tables` loads both tables; `action_row()` and `recipe_action()` look them up. `_body_capacity_factor(actor, capacity, action=None)`
  takes the action. `_speed_of(actor, action)` is the exhaustion speed times the speed factor. `_recipe_body_use(recipe)`.
- `worlds/bigville_world.py`: `effective_strength(actor, action=None)`, `speed_factor(actor, action=None)` and
  `strength(actor, action=None)` take the action. `_job_recipe_name(job)` is new.

**Call sites.** Each is listed with the action key it reads. Entries marked general read the whole-body factor (no action).

| Function | Read | Action key |
|---|---|---|
| `move_actor` (walking interval) | speed factor | `walk` |
| `_capability_terms` (attempts: push, pull, hit, smash, chop, saw, cut, open, pry, force) | speed, strength | the verb (`action` argument from `_container_plan` and `_displace_plan`) |
| `_member_force` (joint carry, `_carry_options`, `_enact_carry`) | strength, speed | `carry` |
| `_contest_side` (default) | strength, speed | `contest` (take, both sides of a take) |
| `_contest_side` in `strike_begin` (attacker) | strength, speed | `strike` (defender stays `contest`) |
| `_contest_side` in `throw_begin` (attacker) | strength, speed | `throw` |
| `_contest_side` in `restrain_begin` (attacker) | strength, speed | `restrain` (target `struggle`) |
| `struggle` (actor, holder) | strength, speed | `struggle`, holder `restrain` |
| `_holds_tick` (holder, target) | strength, speed | holder `restrain`, target `struggle` |
| `_weapon_for_strike` (object as weapon) | strength | `strike` |
| `throw_begin` (ceiling) | speed | `throw` |
| `_throw_range` | strength | `throw` |
| `throw_resolve` (actor step, target evade step) | speed | `throw`; target `contest` |
| `_recipe_preview_compute`, `_capable` (recipe gate) | strength | the recipe's key (`dig` or `work`) |
| `_job_strength_rate` (job progress rate) | strength | the job's recipe key |
| `_spend_job_stamina` (job cost ratio) | strength | the job's recipe key |
| `_resolve_body_stats`, `capacities()`, `body_state`, `exhaustion band` caps and collapse, `_resolve_body_stats`, `game.py` claim priority | strength, stamina | general (no action) |

**Stamina costs.** Each Effort node carries `body_use`, the action it is spent on. The exerted branch (`worlds/bigville_world.py`,
the stamina consumption) divides the cost by `_body_capacity_factor(actor, "stamina", body_use)`. Efforts tagged:
walking (`walk`), job work (recipe key), crew helpers (recipe key), joint carry (`carry`), attempts (the verb),
contests (`contest`; a restraint and a struggle also default to `contest`, not their own row). `effective_stamina` has
no action argument; the reserve cap and the exhaustion band read the general stamina.

**Tests.** `tests/test_phase070c_body.py` (9 tests): empty ledger gives 1.0 for every row; a leg injury slows walking and
lowers a push but not a chop; an arm injury lowers a chop and a strike but not walking; a back injury lowers carrying and
not walking; the whole-body read counts every region while an action counts its own; an unknown verb uses the arm row;
speech, sleep, rest, eat and drink use nothing; the walking speed is the exhaustion speed times the leg factor; a push's
stamina cost rises with a back injury and a chop's does not.

**Phase 070b tests.** Unchanged. `test_an_arm_injury_lowers_effective_strength_by_its_weight` reads the general
(whole-body) strength, so it still holds. The leg strength weight is new, so the general strength of a leg-injured
resident is lower than in 070b. No 070b assertion covers that case.

### Decision 2: preschooler life stage

**Bands** (`packs/*/world/life_stages.json`, whole years):

| Stage | 070b | 070c | Source |
|---|---|---|---|
| infant | 0 to 3 | 0 to 2 | the preschool band starts at 3 |
| preschooler | none | 3 to 5, `inherits: child` | NSF preschool years, Hirshkowitz et al. 2015 (sleep range 10 to 13 h) |
| child | 4 to 12 | 6 to 12 | |

Work fraction, care and food come from child (0.25, 0.5, 0.6).

**Inheritance, one resolver.** `domains/pack.py`: `_compile_life_stages` runs in `compile_tables`. It checks that each `inherits` names a
stage and has no cycle (both raise `ValueError`), and builds the derived table `LIFE_STAGE_CHAIN` (stage, then ancestors,
nearest first). `fill_life_stage_inheritance` runs once in `load_pack`, after compiling. It fills each LIFE_STAGES field the
stage does not give (except age_min and age_max), and each per-stage entry of the tables listed in `STAGE_KEYED.paths`
(`packs/*/world/life_stages.json`, registered in both manifests). `stage_dicts()` walks a dotted path, with `*` for every row.
The fill runs after compiling, not inside it, because the exporter (`tools/export_pack.py`) compiles the stored files and
writes the result back. An in-place fill would write `preschooler` into `contest.json` and the other stage tables, and
`test_phase013a_packs::test_export_rerun_is_byte_identical` failed on that (fixed by this order).

STAGE_KEYED paths: `CONTEST.life_stage_force`, `DEPENDANTS.neglect_after_days`, `DISEASE.*.stage_risk`, `HEALTH.age_rate`,
`HEALTH.fragility`, `IMPAIRMENT_NEIGHBOURS`, `INTEROCEPTION.acuity.life_stage`, `BODY_RATES.sleep_need_hours`,
`LEXICON_QUANTITIES.life_stage.self`, `LEXICON_QUANTITIES.life_stage.other`, `PERCEPTION.stage_nouns`, `ROUTINE_STAGE`.

Values the preschooler takes from child: every entry above, except:

- `BODY_RATES.sleep_need_hours.preschooler = 10` (own value; child stays 9). This is the one overlay.
- `LEXICON_QUANTITIES.life_stage.self/other.preschooler = "a young child"` (own phrase).

Consequences of the inheritance, all taken from child: impairment neighbours (`IMPAIRMENT_NEIGHBOURS.preschooler` = infant,
youth; a copy, child's row is not edited), the perception stage noun ("child"), the routine row `_child`, the acuity factor 0.9,
the contest force 0.8, the fragility and age_rate (0.0 and 0.0), the disease stage risk (1.5 for fever), and the neglect span (3 days).

**Comparisons by name.** Each one now asks the stage's chain (`LIFE_STAGE_CHAIN`) with `_life_stage_is(stage, name)`:

| Location | Was | Now |
|---|---|---|
| `worlds/dependants.py` `_is_dependant` | `stage in DEPENDANTS.stages` | any chain entry in `DEPENDANTS.stages` |
| `worlds/dependants.py` `_dependant_refusal` | `stage == "infant"` | `"infant"` in the chain (refusal `infant`) |
| `worlds/dependants.py` `_dependant_work_factor` | `stage not in DEPENDANTS.stages` | `_is_dependant(actor)`; the value is read from LIFE_STAGES |
| `worlds/bigville_world.py` `_illness_day` (infant fragility) | `stage == "infant"` | chain |
| `worlds/bigville_world.py` `well_baby_visit` | `life_stage != "infant"` | not in chain |
| `worlds/bigville_world.py` `_actor_options` (well-baby option) | `life_stage == "infant"` | chain |
| `worlds/births.py` nursed hunger | `stage == "infant"` | chain |
| `bigville/resident_dependants.py` promotion to a resident backend | `life_stage == "infant"` | chain |

Not changed: `role == "child"` (household role, not a life stage: `worlds/daynight.py`, `domains/population.py`);
`KIN_TERMS.child` and `BIOGRAPHY_TEMPLATES.household.child` (kinship roles); `REFUSAL_REASONS.infant` (a refusal code).

**Age to stage.** The switch-on rule is unchanged (each band runs from its age_min to the next band's age_min).
The switch-off whole-year rule is unchanged (a gap age reads as elder).

**Words.** `LEXICON_QUANTITIES.life_stage` gets `preschooler` ("a young child"). `LEXICON_QUANTITIES.age` (the self and
other age words) gets a band at 3 ("preschooler", "a young child"), and child moves from 4 to 6. Every edge must be an
age_min (the lexicon check). The test_hamlet pack has no age words table, so its age words are unchanged.

**Self-test.** `domains/life_stage_check.py` (new): unknown or cyclic `inherits`; each age a number with age_min at or below
age_max; bands contiguous from 0; every STAGE_KEYED path resolves to a table (a missing table is informational, a
mistyped fixed path is an error); an inheriting stage covers every table its ancestor covers; the lexicon names every
stage. `domains/bigville_entities.py` `_check_dependants` now requires one neglect span for each dependant stage,
counting inherited dependants, and calls the new check. `domains/interoception_check.py` `_check_phase070c` checks
ACTION_BODY_USE (regions are ANATOMY nodes, capacities are named, each named capacity has an INJURY_EFFECTS weight, the
default row exists), RECIPE_BODY_USE values are action keys, and the preschooler has its own sleep value.

**Tests.** `tests/test_phase070c_stages.py` (14 tests): inherited values equal child's (except the sleep need and the words);
child-band values; the sleep need of 10 h, and a resident body reads 10 and 9; the chain; membership and refusal; contiguous
bands; a cycle and an unknown parent are refused by the loader and by the self-test helper; the age stage with the
switch on and off; the lexicon phrase and the age-band edges; the acuity factor; the self-test has no life-stage errors.

## Changed numbers and tests

Changed numbers (behaviour or data):

- `LIFE_STAGES.infant.age_max` 3 to 2. `LIFE_STAGES.child.age_min` 4 to 6. New `LIFE_STAGES.preschooler` 3 to 5.
- `BODY_RATES.sleep_need_hours.preschooler` 10 (new key).
- `INJURY_EFFECTS.weights.leg.strength` 0.5 (new, APPROX). This also changes the general strength of a resident with a leg injury.
- `LEXICON_QUANTITIES.age` new band 3 ("a young child"), child band 4 to 6.

Changed test assertions (`tests/test_phase045_dependants.py`):

- `test_an_age_in_the_gap_between_two_bands_is_the_band_below_only_with_the_switch_on`: with the switch off, `_age_stage(3.5) == "elder"`
  became `_age_stage(2.5) == "elder"` (3.5 is no longer a gap). With the switch on, `_age_stage(3.5) == "infant"` became
  `"preschooler"`, `_age_stage(3.0) == "infant"` became `"preschooler"`, and a new `_age_stage(2.5) == "infant"`. Reason: the band change.
- `test_a_child_aged_three_and_a_half_is_not_treated_as_an_elder_at_the_dawn_tick`: `life_stage == "infant"` became
  `"preschooler"`, and `_is_dependant` still holds. Reason: the band change. The intent (not an elder) is unchanged.

No 070b or 070 test assertion changed.

## Validation

Commands and results (run on the live tree, with the other session's uncommitted changes present):

- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0). Saved to `selftest_bigville.txt`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, ERRORS (0), WARNINGS (0). Saved to `check_test_hamlet.txt`.
- `python3 tools/generate_seeds.py --check`: exit 0, "match pack 'bigville' (31 files)". Saved to `generate_seeds_check.txt`.
- The cast seed: `write_cast_seed` to a temporary file gives bytes identical to `seeds/bigville_cast100.json` and
  `bigville/seeds/bigville_cast100.json`. No cast file was written.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase070c_body.py tests/test_phase070c_stages.py tests/test_phase045_dependants.py`: 40 passed (9 + 14 + 17).
- Related physics suites, run after the action edits and before the stage work: `test_phase070b_body`, `test_phase070_locus`,
  `test_phase050_resolution`, `test_phase038_strikes`, `test_phase040_objects_as_arms`, `test_phase024_exhaustion`,
  `test_phase029_contest`, `test_phase032_training`, `test_phase047_joint_actions`, `test_phase048_tool_fitness`,
  `test_state_draws`, `test_phase049_consequences`, `test_phase022_recipe_stamina`, `test_phase023_job_occupancy`,
  `test_phase039_doors`, `test_phase045_dependants` (only the 070c-changed test is different now): 325 pass, 1 fail. The
  failure was the self-test check, which at that moment reported the other session's in-progress impairment table
  (`MISHEARING`). It passes now, with the self-test at 0 errors.
- Digests: `docs/phases/phase070/compare_digest.py`, town100, seed 305000, simple backend.
  - Base: the working tree at the start of this phase (copied before any edit).
  - New: the base plus only this phase's files (the other session changed TUI, LLM, impairment and Phase 071c files after the copy, so the live tree could not be used).
  - 60 turns: base and new `digest_without_marks` both `3a8c1d8c...`, deaths 0. Saved as `digest_60_base.json` and `digest_60_new.json`.
  - 200 turns: base and new both `8d5d176f...`, deaths 0, 100 residents with mark totals (`mark_wetness` 50.0 in both). Saved as `digest_200_base.json` and `digest_200_new.json`.
- Full suite (`timeout 7200 python3 -m pytest -q -p no:cacheprovider tests -rf`, live tree, `full_suite.log`): 21 failed, 2980 passed, 7 skipped, in 2017 s.
  The earlier `pytest` with no path also collects `docs/phases/phase044` and `045` copies of the other session's tests, so the run uses `tests/`.
- Digests were rerun after the fill moved into `load_pack` (`digest_60_new.json`, `digest_200_new.json`): unchanged.

## Limits

- Injury weights and the 0.5 floor are APPROX. No village run injures a resident, so the action factors are exercised only by unit tests.
- The stamina factor applies to the cost of an Effort, not to `effective_stamina`. The stamina of restraint and struggle uses the `contest` row.
- Chest and head injuries lower the whole-body read only; no action row uses them.
- The 60 and 200 turn digests do not exercise births, dependants or preschoolers (no resident is under 18 in the cast).
- Under the switch-off whole-year rule, an age in a gap reads as elder. With the new bands the gaps are 2 to 3 and 5 to 6.
  This matters only when births run without the dependants switch. Births are off by default, and no shipped scenario turns them on.
- The age words for 3 to 5 year olds now say "a young child" (they said "a baby" at 3 and "a child" at 4 and 5).

## Open questions

1. **Infant band 0 to 2 changes 3-year-olds.** Under the dependants switch, a 3-year-old is now a preschooler, not an infant:
   it is no longer refused major actions, its care need drops from 1.0 to 0.5, its work fraction rises from 0.0 to 0.25,
   its food need from 0.35 to 0.6, and its acuity from 0.6 to 0.9. The brief limits the change to 4- and 5-year-olds, so
   this is a change outside that limit. Options: keep 3 years with infant (the preschooler then starts at 4, which
   departs from the 3 to 5 band), or accept the change. Decision needed.
2. **Switch-off gap ages.** Should the switch-off whole-year rule read gap ages with the band below (as the switch-on rule does)?
   That would fix 2.x, 5.x and the existing gaps (3.x as infant, 12.x as child, 17.x as youth, 64.x as adult) for all runs. It
   changes 64.x residents from elder to adult in long runs, which the brief does not ask for. Decision needed.
3. **Age words for 3 to 5 year-olds.** Accept "a young child" for the age words, or keep "a child" for 4 and 5 and use no preschool age band
   (the lexicon check requires an age word edge at each stage's age_min)?
4. **Stamina of restraint and struggle.** Give them their own efforts' body_use (the rows exist) rather than `contest`.

## Deviations from the brief

- The brief's "stamina costs" are implemented on Effort nodes (see Decision 1), not on `effective_stamina`.
- No kick, climb or ploughing action exists, so no rows were written for them.
- The brief's "children are not preschoolers in the cast" was tested, not assumed: the cast seed is byte-identical.
- The brief's "no behaviour may change for a 4- or 5-year-old except the sleep need" holds for the digests. It does not hold for the age words, and the
  3-year-old change in open question 1 is outside the brief's stated limit.
- Tests were run in the live tree. Some of the suite's results depend on the other session's in-progress work (see the suite section).

## Full suite: attribution of the 21 failures

Run: `tests/` on the live tree, 2017 s. The other session's uncommitted work was present during the run.

| Group | Tests | Evidence |
|---|---|---|
| Ocelot adapter missing (brief's known baseline) | `test_bigville_ocelot_communication`, `test_mixed_ocelot_checkpoint_parity`, `test_mixed_ocelot_village` (3) | `ModuleNotFoundError: worlds.bigville_ocelot_adapter`, as the brief says |
| Fail on the pre-edit snapshot too | `test_fix_llm_checkpoint[0]`, `test_package15_resource_social_stress`, `test_phase057_tui` (4 over HTTP), `test_phase058_persona` (simple backend, 50 turns), `test_phase060_speech_in` (8) | The same tests fail in `/tmp/base070c` (the tree before this phase's edits), with the same messages (for example `assert 200 == 400`) |
| The other session's in-progress work (prompt schema, impairment, lamplighter) | `test_phase031_llm_backend::test_callable_provider_is_accepted` (`bigville/prompt/5` where the test expects `/4`), `test_phase054_llm_prompt` (prompt packet snapshot, `"system"` length), `test_phase065b_impairment` (5, `percept() got an unexpected keyword 'shift'`, no `mishear_checked`), `test_phase042b_lamplighter` (2) (9) | The prompt schema and the impairment test files are the other session's. The lamplighter test does not collect on the snapshot (it imports names that are absent there); its assertions concern lighting a lamp, which this phase does not touch. Not attributed further. |
| Transient | `test_phase013a_packs::test_exported_files_compile_back_to_the_same_tables` (1) | Failed once with `SPEECH_PARSER` differing between the export and the load, while the other session was editing the packs. Rerun alone: 8 of 8 pass. |

Phase 070b and 070 tests: all pass. `tests/test_phase070c_body.py` (9 tests) and `tests/test_phase070c_stages.py` (14 tests) pass.
`tests/test_phase045_dependants.py` (17 tests; 2 tests with changed assertions, see above) passes.
