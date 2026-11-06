# Phase 050: the resolution core, one rule for every attempt

## Summary

An `attempt` action now resolves any verb the pack lists in `VERBS`, against a container, with an optional held
tool and an intensity. One pure function (`worlds/resolution.py`) turns capability against demand into progress,
stamina cost, strain, tool wear and noise. Two verbs have their primitive implemented: `damage` (smash, hit, cut,
chop, saw) and `open` (pry, force). A locked container opens when its accumulated progress reaches 1. A container
that reaches 0 structure is broken. Strain past the safe intensity becomes an `accident` harm. Noise is an event
heard by awake residents within the hearing radius.

Not done from the brief: the `displace` primitive (push, pull, lift, carry, throw, dig are declared and refused as
`unsupported`), quality and yield curves, recipe pace (intensity on `transform`), the `set_intensity` free action,
blows and throws, spilling the contents of a broken container, and any wiring of `escalate` into the simple backend's
choices. See Limits.

Self-test: 0 errors, 0 warnings (bigville and test_hamlet). Full suite: 1222 passed, 2 skipped, 3 failed at baseline;
the 3 failures are the known Ocelot adapter tests. See Validation for the final run.

No existing test was edited, and no committed test number changed. The committed recipe, movement and exhaustion
numbers are unchanged (golden table below).

## Changes

### Files created

- `worlds/resolution.py`: the pure resolution core. Functions `capability`, `technique_term`, `rho`,
  `progress_rate`, `cost_ratio`, `intensity_applied`, `overexertion`, `strain`, `tool_wear`, `noise_radius` and
  `resolve_step`. No world state, no randomness.
- `packs/bigville/world/resolution.json`: tables `VERBS`, `MATERIALS`, `RESOLUTION`.
- `packs/test_hamlet/world/resolution.json`: the same three tables. `VERBS` holds only the verbs the hamlet
  lexicon names (smash, hit, force, carry), because the hamlet has only the `fighting` and `baking` skills. Its
  `carry` uses no skill (`skill: null`).
- `tests/test_resolution_pure.py` (16 tests), `tests/test_phase050_resolution.py` (27 tests).
- `docs/phases/phase050/`: this report, `golden_before.py` and its logs, and the validation logs.

### Files edited (my hunks only)

- `packs/bigville/world/health.json`, `packs/test_hamlet/world/health.json`: `accident` added to `HEALTH.causes`.
- `packs/bigville/world/containers.json`: `lock_strength` on the lockable kinds: chest 1.0, safe 4.0, granary 2.0
  (APPROX). The `_doc` explains the unit.
- `packs/bigville/world/major_actions.json`, `packs/test_hamlet/world/major_actions.json`: action `attempt` with a
  description.
- `packs/bigville/world/refusal_reasons.json`, `packs/test_hamlet/world/refusal_reasons.json`: code `destroyed`.
- `packs/bigville/world/locks.json`, `packs/test_hamlet/world/locks.json`: `lock_strength` 1.0 on `STORE_LOCK`.
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`: manifest entries `VERBS`, `MATERIALS`, `RESOLUTION`
  (all from `world/resolution.json`, as ITEMS and FOOD_GRADING share `items.json`).
- `domains/world_affordances.py`: binds `VERBS`, `MATERIALS`, `RESOLUTION` (3 lines plus a comment).
- `domains/bigville_entities.py`: `_check_resolution` (new function, inserted before `_check_contest`), and one
  call after `_check_contest(...)` in `check_consistency`.
- `worlds/bigville_world.py` (my hunks, 7 of 9 in the file's diff):
  - `_wire_container`: structure 1.0, destroyed 0, `lock_strength` from `CONTAINERS`, lock condition 1.0, lock
    progress 0.
  - `_container_accessible`: a destroyed container is not accessible.
  - `_major_action_attempt`: `attempt` branch, before `complete_request`.
  - `_enact_plan`: `attempt` branch, before the final "no action" fallback. A native verb (walk, eat, drink, sleep,
    rest, sow, harvest) routes to its own action. A verb with no route (cook, mend) is refused as `unsupported`.
  - `_open_job`: the Job node stores `strength_needed` (the recipe's strength demand).
  - `_spend_job_stamina`: the declared share is multiplied by `cost_ratio(strength_needed, strength_now, 1, effort_cap)`.
  - New block before `_job_of`: `_attempt_verb`, `_run_attempt`, `_spend_attempt_stamina`, `_publish_noise`,
    `_record_attempt`, `attempt_counts`, `last_attempt`.
- `bigville/backends/cheap.py`: `SimplePolicy` gains `escalate_after_ticks` (0, off) and `escalate_step` (0.5), and a
  method `escalated_intensity`. No other part of the file changed.
- `bigville/backends/prompts.py`: one line in `build_system_text`, the list of attempt verbs.
- `bigville/backends/protocol.py`: a comment describing the `attempt` params (no code change).
- `bigville/reporting.py`: `SimulationReporter.attempts_by_verb()`.

Not touched: `bigville/game.py`, the other session's `record_action_outcome` block, and the other session's
hunks in `worlds/bigville_world.py` (see Shared files below).

### Design

Capability C = force x technique x fit x team x conditions. Demand D is the target's toughness x its structure
(damage) or its lock strength x lock condition (open). rho = C / D.

- Force = effective strength x body size x life-stage force (CONTEST table) x exhaustion speed factor (Phase 024).
  Intensity multiplies force, so it is part of C for progress.
- Technique = 0.5 + 0.5 x effective skill in the verb's skill (0.5 floor, APPROX). A verb with `skill: null` has
  technique 1.
- Fit = the tool's verb closeness in the verb's `tool_verbs` (0 when the tool's verb is not listed). With no tool,
  hands give 1.0 (neutral). Phase 048 will replace these.
- Team and conditions = 1.0 (neutral; Phases 047 and the conditions terms).
- Progress = min(attempt_cap_rate 2.0, rho). Structure or lock condition falls by 0.1 x progress x (0.5 + fragility).
  A lock opens when accumulated progress reaches 1. A lock condition of 0 breaks the lock.
- Stamina = base_cost 0.1 x clamp(D / C0, 0, 3) x intensity^1.5, where C0 is C without intensity. This is charged
  through an Effort node and `_run()`, as `rest` does. The Phase 022 hunger scaling and reserve floor apply.
- Strain += cost share x (1 - min(1, rho)) + max(0, i - 1.5)^2. At 1.0 the actor takes an `accident` harm of 0.1
  and the strain resets.
- Tool wear = 0.05 x intensity x (1 + 4 x (1 - fit)) x (1 + 0.5 x max(0, target hardness - tool hardness)). The
  tool breaks at condition 0 (`broken` = 1, which `_held_tool` already respects).
- Noise radius = 4 x intensity x material noise, in cells. It is published through `speech_radius`, so the
  `loudness` switch applies. Awake living residents within Chebyshev distance observe a `noise` event.
- Intensity ceiling = max_intensity 3.0 x speed factor x health. A request above it is clamped, and `last_attempt`
  reports the applied value and `clamped`.
- Refusals before the slot is claimed: `unsupported` (verb not in VERBS or with no primitive implemented),
  `malformed`, `unknown_target`, `not_in_reach`, `destroyed`, `no_lock`, `already_unlocked`, `no_tool` (a tool named
  but not held or broken). An attempt that makes no progress is still enacted and charged.
- What the actor observes (`last_attempt`): verb, target, tool kind, requested and applied intensity, clamped,
  progress, damage, outcome. Never C, D, rho or fit.
- `attempt_counts()` counts attempts per verb and outcome (`broke`, `damaged`, `progress`, `opened`, `broke_lock`,
  `no_progress`). `SimulationReporter.attempts_by_verb()` reads it.

### Data and sources

Every value below is APPROX unless stated. None was measured.

- Hardness scale. The Mohs scale (Mohs, 1822) places iron near 4.5 and granite at 6 to 7. The pack's 0 to 1 values
  keep that order (metal 0.6, stone 0.9) without converting it. Wood, cloth, leather and wax are not on Mohs.
- Life-stage force and the cost constants come from the Phase 029 CONTEST table, unchanged.
- `technique_floor` 0.5, `attempt_cap_rate` 2.0, `base_cost` 0.1, `effort_cap` 3.0, `k` 1.5, `i_safe` 1.5, `m` 2.0,
  `max_intensity` 3.0, `tool_wear` 0.05, `mismatch_wear` 4.0, `hardness_wear` 0.5, `damage_per_attempt` 0.1,
  `noise_base` 4.0, `strain_limit` 1.0, `accident_harm` 0.1. All are model choices. The sources are for order of
  magnitude only, and the values are tuned so that the tests' scenarios come out as described.
- Lock strengths (chest 1.0, safe 4.0, granary 2.0, store 1.0): design choices. No source was consulted.

## Changed numbers and behaviour

Committed numbers: none changed. Golden values from `docs/phases/phase050/golden_before.py`, run before and after
the edits (`golden_before.log` and `golden_after.log` are identical):

| Case | Before | After |
|---|---|---|
| forge_plough job spend, hunger 0 | 0.4 (hunger 0.025 after) | 0.4 (same) |
| forge_plough job spend, hunger 2 | 0.6 (hunger 2.0375 after) | 0.6 (same) |
| forge_knife timed spend, hunger 0 | 0.15 | 0.15 |
| forge_knife instant spend, hunger 0 / 2 | 0.15 / 0.225 | 0.15 / 0.225 |
| walk moves in 60 turns at reserve 0.9 / 0.5 / 0.2 | 60 / 40 / 20 | 60 / 40 / 20 |

Exhaustion (Phase 024 wake and sleep ticks) is covered by the existing `tests/test_phase024_exhaustion.py`, which
passes unchanged.

Behaviour that changes, not measured in a village run:
- A recipe worker whose strength falls during a job (for example when health falls) pays
  `cost_ratio(strength_needed, strength_now, floor 1, cap 3)` times the declared share. At the strength gate the
  ratio is 1, so nothing changes unless strength falls mid-job. Measured: the smith's health drops to 0.8 after the
  first tick, with stamina capacity raised so only strength changes (strength 1.04 against the plough's demand 1.2,
  ratio 1.154). The plough then spends 0.453 against the declared 0.400. The per-tick spend is not exactly constant
  (0.0283 to 0.0288), and I did not trace why. Without the capacity change the same drop spends 0.597, because the
  lower health also clamps the reserve to the lower stamina capacity (Phase 032). That clamp is existing behaviour,
  not the new term. The test is `test_a_worker_whose_strength_falls_mid_job_pays_more_than_the_declared_cost`.
- `accident` is an accepted health cause. It is recorded only by attempts that build strain. The cheap backend
  never proposes an attempt, so the village sees none.
- The major-action list now contains `attempt`. The LLM and Ocelot prompts list it, and the system prompt gains an
  "attempt verbs" line. Any prompt hash over the pack changes.
- A broken container refuses access (`_container_accessible`). No container breaks in a village run, because no
  backend proposes an attempt.

Existing tests changed: none. Existing tests that exercise the changed code paths pass unmodified:
`test_phase022_recipe_stamina.py`, `test_phase023_job_occupancy.py`, `test_phase024_exhaustion.py`,
`test_phase029_contest.py`, `test_phase037_health_routes.py`, `test_phase013a_packs.py` (see the persona note under
Validation), and `test_phase051_lexicon.py`.

## Validation

Run from `/home/matt/ozmadev/bigville`. Logs are in `docs/phases/phase050/`.

| Command | Before | After |
|---|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS 0; WARNINGS 0 (`baseline_selftest.log`) | exit 0; ERRORS 0; WARNINGS 0 (`selftest_final.log`). Balance and people issues: none reported. The RESOLUTION line: 23 verbs, 11 materials |
| `python3 -m domains.check --pack test_hamlet` | not run | exit 0; ERRORS 0; WARNINGS 0 (`check_hamlet.log`) |
| `python3 -m domains.check` | not run | exit 0 (`check_bigville.log`) |
| `python3 tools/generate_seeds.py --check` | not run | exit 0; "match pack 'bigville' (31 files)" (`seeds_check.log`) |
| `python3 tools/export_pack.py` and `--pack test_hamlet` | not run | normalised 206 tables each. Only my two `resolution.json` files changed bytes (one re-export after a doc edit). `lexicon.json` was not touched (checked by md5) |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (baseline) | 1222 passed, 2 skipped, 3 failed (`baseline_pytest.log`) | see the final run below |
| Final full run (`final_pytest.log`), with 43 new tests | | 1263 passed, 2 skipped, 5 failed. The 3 Ocelot failures (as baseline) and 2 `test_phase013a_packs.py` failures caused by the untracked persona file (see below) |
| Earlier full run, before `persona.json` appeared | | 1264 passed, 2 skipped, 3 failed (the Ocelot three only); that run included all 42 tests then present |
| `pytest tests/test_resolution_pure.py` | | 16 passed |
| `pytest tests/test_phase050_resolution.py` | | 27 passed (re-run after the last edit: 43 passed with the pure file) |

The 3 failures in both runs are `test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
`test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`
and `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`,
each `ModuleNotFoundError: worlds.bigville_ocelot_adapter`.

Persona note. Another session created `packs/bigville/world/persona.json` and `packs/test_hamlet/world/persona.json`
(untracked) during this phase, and its manifest entries (`PERSONA_*`, `ROUTINE*`, `PLACE_WORDS`) appear in both
`pack.json` files. The earlier full run passed `test_phase013a_packs.py`. The final run fails two tests in it:
`test_export_rerun_is_byte_identical` (`FileNotFoundError: .../bigville/world/persona.json` in the export copy) and
`test_exported_files_compile_back_to_the_same_tables` (the copy's tables differ on the persona `temperament` entry).
Phase 050 does not touch those files or entries. I did not edit or remove them. A copy of the tree without the
persona files could not load the packs (the manifest names them), so I could not isolate the failure further. The
owner must make the exporter and manifest agree on the persona tables before those two tests pass.

Git status. Start: 35 entries (the other session's work, recorded in the first `git status --short`). End:
`docs/phases/phase050/git_status_end.txt`.

## Limits

Brief items not implemented:
- **Displace primitive.** `push`, `pull`, `lift`, `carry`, `throw` and `dig` are in VERBS with `primitive: displace`.
  `attempt` refuses them as `unsupported`, so the cart and the movement-by-surplus acceptance cannot be tested.
  The self-test does not warn about this.
- **Spill.** A broken container is marked destroyed and refuses access. Its contents stay in it, unreachable. They do
  not spill onto the cell. This loses access to the contents, not the goods.
- **Quality, yield and ruin curves.** Not in RESOLUTION. Recipe outputs are unchanged.
- **Recipe pace.** No intensity on `transform` (haste_cap, care_cap, haste_penalty are not in the table). The
  pit-saw acceptance (1.5 faster and lower quality, 0.5 slower and better) is not met.
- **set_intensity.** Not implemented. A running timed job cannot change level.
- **Blows and throws.** No person targets. "A blow at low intensity barely harms" is not tested.
- **Trivial and slot rules.** `trivial_below` and `slot_above` are not implemented. Every attempt costs stamina and
  uses the action slot.
- **Escalation.** `escalated_intensity` and its two fields exist and are tested. Nothing calls them, because the
  cheap backend proposes no attempts, and I did not edit its choice method (Tract B owns it).
- **Strain decay.** Strain accumulates until it reaches the limit. Rest does not reduce it.
- **Training.** An attempt's Effort has `uses_strength` 0, so attempts do not train strength.
- **Movement and carry.** Phase 050 does not route walking or the carry model through the core.
- **Hunger from attempts.** Charged through the Effort path, so hunger rises by the spend as for recipes. Not measured.
- **Team and conditions.** Neutral at 1.0 (Phases 047 and 049).
- **Fit.** The closeness table is a stopgap for Phase 048. Hands are neutral (1.0).
- **Intensity ceiling.** Lowered by speed factor and health. The reserve works through the speed band.
- **MATERIALS** covers every material an item names. The per-class defaults the brief mentions are not added, and
  `edge` is not added.
- **Noise.** Chebyshev distance, no occlusion. No lamps or weather.
- **Hamlet.** Its VERBS table keeps only the verbs the hamlet lexicon names, and `carry` uses no skill there.
- **Not run.** The 100-resident town (`from_town100`, `run_village`). No village claim is made.

## Shared files

Hunks in `worlds/bigville_world.py` that are mine (for `git add -p`): the `_wire_container` attributes, the
`_container_accessible` check, the `attempt` branch in `_enact_plan`, the `attempt` branch in
`_major_action_attempt`, the `strength_needed` line in `_open_job`, the `cost_ratio` lines in `_spend_job_stamina`,
and the resolution block before `_job_of`. Not mine, to leave out: the `"food"` line in the container fetch option,
and `resident_plan_from_context`. Both are the other session's.

`domains/bigville_entities.py`: my hunks are `_check_resolution` and its call. The Phase 051 lexicon call is already
committed.

`bigville/backends/cheap.py`, `prompts.py`, `protocol.py`, `reporting.py` and `domains/world_affordances.py` had no
uncommitted hunks of another session when I began. Each diff is mine.

`packs/*/pack.json`: the other session's manifest hunks were committed in Phase 051. The current diff is mine only.

## Open questions

1. **Displace.** Should the next phase implement push and carry (the cart acceptance) or leave movement to Phase 040?
2. **Spill.** Should a broken chest spill its goods onto its cell (as stock on a cell) or stay sealed? Spilling needs a
   cell-stock model that the world does not have yet.
3. **Escalation.** Who calls `escalated_intensity`? If Tract B wants the cheap backend to propose attempts, that is a
   choice-method change for Tract B (Phases 058 and 059).
4. **Strain decay.** Should strain recover with sleep, as health does? I left it accumulating.
5. **Persona.** Two `test_phase013a_packs.py` tests fail on the other session's untracked `persona.json` files and
   their manifest entries. The owner should make the exporter write them, or defer them, before commit.
6. **Lock strengths and tuning.** All APPROX. The pure tests fix only the relative order, so a retune changes the
   world test numbers (for example the frail spoon and the 3-attempt strong opening).

## Follow-ups

- Phase 048 (fit): replace the closeness table with the tool-fitness table and drop the neutral hands value.
- Phase 047 (team) and Phase 049 (conditions): give `team` and `conditions` real terms.
- Recipe pace and set_intensity: the `transform` half of the intensity rule, and the free action.
- Displace and spill: the next primitives, each in its own change.
