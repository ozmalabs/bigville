# Phase 048: tools by fitness, and the wrong tool in a pinch (Tract A)

## Summary

A tool now has a fitness for each verb. Fitness is the work's closeness to the tool's verb, times the tool's hardness,
edge and weight against the work, times its quality and condition. The right tool at full quality and condition has
fitness 1.0, so the committed recipe numbers do not move (golden table below). Any other tool, or bare hands
(fitness 0.05), still works, slower and at a cost. A recipe no longer refuses for want of its tool. The job runs on
bare hands, and a batch that falls below the waste line yields nothing.

Progress, stamina, quality, yield, tool wear, strain and accidents all follow the fitness. Attempts (Phase 050) use
the same fitness in place of the stopgap closeness table. `stop` is a new free action that abandons a timed job.
The `tool` key is accepted on a work proposal.

Not done, or done in part (see Limits): the simple backend's `improvise` is a flag and a helper that the choice method
does not call. `stop` and `set_intensity` cannot be sent by a backend, because `game.py` routes only `speak` as a
free action. The 100-resident village was not run, and its numbers will change (see Changed numbers).

Self-test: 0 errors, 0 warnings. Hamlet check: 0 errors, 0 warnings. Full suite: 1417 passed, 2 skipped, 3 failed.
The 3 failures are the Ocelot adapter tests recorded in Phases 050 and 050b (`worlds.bigville_ocelot_adapter` not found).

## Changes

### Files created

- `tests/test_phase048_tool_fitness.py` (16 tests).
- `docs/phases/phase048/`: this report, the golden logs, self-test and check logs, the full-suite log, `git_status_start.txt`
  and `git_status_end.txt`.

### Files edited

- `worlds/resolution.py` (appended, Phase 048 section): `closeness_table`, `closeness`, `hardness_term`, `edge_term`,
  `weight_term`, `fitness`, `effort_multiplier`, `fit_quality`, `fit_wasted`, `fit_yield`, `tool_wear_excess`. Pure,
  no state, no random numbers.
- `packs/bigville/world/resolution.json` and `packs/test_hamlet/world/resolution.json`:
  - `VERBS`: `tool_verbs` removed from every verb. Each verb with a primitive gets `work`, the physical work class it
    needs (smash, hit, force: strike; cut: cut; chop: chop; saw: saw; open, pry: pierce; dig, push, pull, drag, lift,
    carry, throw: their own names). The `drag` entry moved to the end of the table's key order.
  - New table `TOOL_FIT`: `verbs` (the vocabulary, 38 names in bigville, including every tool verb in ITEMS, and
    `store` for barrels used as recipe tools), `same_verb` 1.0, `pairs` (23 symmetric closeness pairs), `edge_verbs`,
    `edged_kinds` (knife, cleaver, axe, saw, awl, adze), `no_edge` 0.2, `weight_verbs`, `min_weight` 0.5,
    `hardness_zero_gap` 0.3, `rows` (knife: cut 1.0 effort 1.0, strike 0.3 effort 2.0).
  - `RESOLUTION`: `hands_fit` 1.0 becomes 0.05. New `fit_quality_loss` 0.5 and `waste_below` 0.25.
  - `_doc` explains the new keys. Every new figure is APPROX, and the source note says so.
- `packs/bigville/world/free_actions.json`, `packs/test_hamlet/world/free_actions.json`: `stop` (kind `abandon`).
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`: manifest entry `TOOL_FIT` (file `world/resolution.json`).
- `worlds/bigville_world.py`, `domains/bigville_entities.py`, `domains/world_affordances.py`, `bigville/backends/cheap.py`,
  `bigville/backends/protocol.py`, `bigville/reporting.py`: see Shared files.
- Tests changed (listed under Changed numbers): `tests/test_phase001_workshop_tools.py`, `tests/test_phase010_burial.py`,
  `tests/test_phase023_job_occupancy.py`, `tests/test_phase050_resolution.py`, `tests/test_simple_tools_materials_job.py`,
  `tests/test_bigville_world_migrated.py`.

### Design (what the code does)

- **Fitness** (`_tool_fit`, world). Bare hands: `hands_fit` 0.05 for any verb. An authored row in `TOOL_FIT.rows` for
  the verb: its `mult` times quality and condition, with its `effort`. The right tool for a recipe slot (same kind as the
  slot): 1.0 times quality and condition. Any other tool: closeness x hardness x edge x weight, times quality and
  condition. For a recipe slot the work material is the slot kind's own material (recipes name no work material). For an
  attempt it is the target's material. `base_mult` is not used, because some items exceed 1 (axe 2.2).
- **Choice** (`_job_tool_item`, `_tool_choice`). A job's tool is by mode. `default`: the right kind the worker holds, or
  is at the workplace shelf for trade work, else hands. `item`: the held tool named in the proposal (`tool: <kind>`), while
  the worker holds it. `hands`: `tool: "none"` or null. A named kind the worker does not hold is refused as `no_tool`.
  A non-string is `malformed`.
- **Timed jobs** (`_resolve_jobs`, `_refresh_job_fit`). Each tick removes `speed x pace x fit` from the remaining time, so
  a job takes 1/fit as long. Stamina spent per tick is the declared share times the progress made, times
  `clamp(1/fit, 1, effort_cap)` times the row's effort (so bare hands pay 3). Tool wear per tick is the extra wear of a
  poor fit: `wear x intensity x mismatch_wear x (1 - fit) x (1 + hardness_wear x gap)`. It is zero for a fitting tool. A
  tool at 0 condition is broken, and the job then falls back to hands. Strain per tick is `(speed x pace / ticks) x (1 - fit)`,
  added through `_accrue_strain` (the Phase 050 code, moved out unchanged). A full strain is an `accident` harm.
- **Completion** (`_resolve_jobs`). Quality becomes `quality x (1 - 0.5 x (1 - fit_low))`, where `fit_low` is the lowest
  fitness over the job. Output is multiplied by `fit_low` and is zero when `fit_low < waste_below` (the batch is
  wasted: inputs used, no output, no byproducts, and event `batch_wasted`). A burial job with a wasted batch leaves no
  grave. The completion wear is unchanged (the job's `wear` attribute, on the tool the job used).
- **Attempts** (Phase 050 path). `_capability_terms` takes its fit from `_tool_fit` for the verb's `work` on the target's
  material. A row's `effort` multiplies the stamina of an attempt. Wear and strain use the same helpers as before.
- **Refusals.** `_recipe_refusal` no longer refuses `no_tool`. `_recipe_inputs_available` and `_capable` are unchanged,
  so the options a backend is offered are unchanged (a recipe is still offered only with its right tool).
- **Stop** (`stop_job`, free action `stop`). Marks the job complete and stopped, clears busy, removes the on-job edge.
  Inputs are taken at completion, so only the progress is lost. Stamina already spent stays spent.
- **Tally** (`tool_tally`, `SimulationReporter.improvised_work`). Plain counts over the town: `improvised_jobs`
  (a job opened without the right tool it names), `accidents`, `broken_tools`.
- **Simple backend** (`cheap.py`, `SimplePolicy`). Field `improvise` (default False) and a method `improvised_tool`
  that picks the held tool with the best visible score (its condition, a third of it if its verb differs). Not called by
  the choice method, which Tract B owns for Phase 059.
- **Protocol** (`protocol.py`). A comment describes the `tool` key on `work`. No code change in that file.

### Shared files, my hunks (for `git add -p`)

- `worlds/bigville_world.py`, by function:
  - `_DEFAULT_TOOL` sentinel (after the imports); `__init__` (`_tool_tally`).
  - `_resolve_jobs`: the missing-tool block removed; the tick branch (`_refresh_job_fit`, progress and stamina by `fit`);
    the refresh before the completion path; the quality, yield and waste lines and the `batch_wasted` event; the byproduct
    guard; the completion wear through `_job_tool_item` and `_wear_tool`; the burial guard.
  - `_spend_job_stamina`: `effort_mult` on the declared share.
  - `_open_job`: signature, job attributes, the tool edge, the improvised tally, and the first refresh.
  - `do`, `start`: the `tool` argument and its resolution.
  - `_recipe_refusal`: the two `no_tool` checks removed.
  - `_major_action_attempt` (work, make, start): the tool is checked before the slot is claimed.
  - `_enact_plan` (the `work` line): passes `tool` when the plan has it.
  - `free_action`: the `stop` branch.
  - New block before `_held_tool`: `_tool_choice`, `_holds_item`, `_job_tool_item`, `_tool_fit`, `_wear_tool`,
    `_accrue_strain`, `_refresh_job_fit`, `stop_job`, `tool_tally`.
  - `_capability_terms` (new `target_material` argument; fit from `_tool_fit`), `_container_plan` (terms after the
    target material), `_displace_plan` (the new argument), `_finish_attempt` (`_wear_tool`, `effort`, `_accrue_strain`).
  - Not mine, left out: the `"food"` line in the container fetch option, and `resident_plan_from_context` (Tract B).
- `domains/bigville_entities.py`: in `_check_resolution`, the VERBS loop (the `tool_verbs` check replaced by a `work`
  check), the call to `_check_tool_fit` at the end, and the new function `_check_tool_fit`. Not mine: the Phase 052
  `check_agent_view` hunk and the persona hunk in `check_consistency`.
- `domains/world_affordances.py`: `TOOL_FIT = _PACK["TOOL_FIT"]` with a comment (2 lines).
- `packs/bigville/pack.json`, `packs/test_hamlet/pack.json`: the `TOOL_FIT` entry after `RESOLUTION` (4 lines each).
  Not mine: the persona entries that show as deleted in the working copy.
- `bigville/backends/cheap.py`: `improvise` and `improvised_tool` after `escalated_intensity` (18 lines). No change to
  `_update_goals`, `_time_band` or the choice method.
- `bigville/backends/protocol.py`: 4 comment lines after the Phase 050 attempt comment.
- `bigville/reporting.py`: `improvised_work` after `attempts_by_verb`.

### Data and sources

No figure is measured. Every figure is APPROX, a model choice made to keep the tests' scenarios in the order described.
The hardness scale is the one described in the Phase 050 MATERIALS notes (Mohs 1822, for order only). `hardness_zero_gap`,
`no_edge`, `min_weight`, `fit_quality_loss`, `waste_below`, the pair values and the knife rows are APPROX.

## Changed numbers

Committed golden numbers (`docs/phases/phase050/golden_before.py`, run before and after, `golden_pre.log` and
`golden_post.log` identical): the plough and knife stamina at hunger 0 and 2, the instant knife spend, and walking at three
reserves. All unchanged.

Behaviour that changes, not measured in a village run:
- A tool that has been used is at condition below 1, so its fitness is below 1. Its job takes longer, its output is
  smaller and its batch is lower in quality, in proportion to the wear. A hammer at 0.98 makes output at 98% of the
  expected yield. Tools wear 0.02 (hammer) to 0.15 (axe, pick) per use (ITEMS `wear_rate`), so every shelf tool in a village changes over time.
- Bare hands fit at 0.05 where Phase 050 had 1.0 (the stopgap `hands_fit`). Every attempt without a tool progresses
  20 times slower, and strains more.
- The stopgap closeness pairs are replaced by `TOOL_FIT.pairs`. Most pairs keep their value. Some change: smash with a
  cleaver 0.6 to 0.5 (strike and cleave), smash with an awl (pierce) 0.2 to 0.4 (strike and pierce), open with an
  awl 0.6 to 1.0 (the work is now pierce itself), open with a cut tool 0.2 to 0.5 (cut and pierce).

Existing tests changed. Each keeps its intent. Each change is a consequence listed here.

| File | Test | Change | Why |
|---|---|---|---|
| test_phase001_workshop_tools.py | `test_a_broken_forge_hammer_refuses_forging_...` | renamed `..._forging_goes_on_with_bare_hands_and_wastes_the_batch`. The refusal of forging becomes the bare-hand batch: iron used, no nails. The batch with the spare hammer rests the smith first (its bare-hand batches cost 3 times the stamina and collapse it). | A missing tool is not a refusal (brief). |
| test_phase001_workshop_tools.py | `test_a_new_hammer_placed_at_the_forge_restores_forging` | First assertion: `not do` becomes `do`, with no nails (a wasted batch). | As above. |
| test_phase001_workshop_tools.py | `test_a_worker_away_from_the_forge_...` | `not do` becomes `do`; the forge's hammer is not worn; the batch is wasted. | Out of reach means bare hands. |
| test_phase001_workshop_tools.py | `test_open_recipes_still_need_the_workers_own_held_tool` | renamed `..._use_the_workers_own_held_tool_and_not_a_shelf_tool`. Lumber 2 added. Bare hands do the work; the shelf axe is not used; the own axe is. | The open recipe no longer refuses; the own-tool rule is kept as the fitness choice. |
| test_phase010_burial.py | `test_digging_needs_a_spade_and_the_graveyard` | Refusal without a spade becomes a bare-hand dig with no grave and no spoil. | As above; a wasted burial dig leaves no grave. |
| test_phase010_burial.py | `test_digging_uses_the_workers_own_spade_and_no_one_elses` | `not do` becomes `do`, with no grave, and the other's spade is unworn. | As above. |
| test_phase023_job_occupancy.py | `test_a_job_short_of_its_tool_still_completes_when_the_tool_arrives` | renamed `test_a_job_whose_tool_breaks_midway_goes_on_with_bare_hands`. The job waits no more: it advances by about 0.05 of a tick. | The job no longer stalls for want of a tool. |
| test_simple_tools_materials_job.py | `test_missing_tool_rejects_start_without_consuming_inputs` | renamed `test_missing_tool_starts_on_bare_hands_and_the_batch_is_wasted`. Start succeeds; inputs are taken at completion; nails 0. | As above. |
| test_simple_tools_materials_job.py | `test_tool_lost_during_timed_job_blocks_completion_...` | renamed `..._goes_on_at_bare_hand_speed_and_recovers_with_the_tool`. | As above. |
| test_phase050_resolution.py | `_ground_world` | new optional `tool` argument (default None; existing callers unchanged). | Bare hands cannot shift a cart (0.05). |
| test_phase050_resolution.py | `test_a_strong_resident_pushes_a_cart_by_the_surplus_force` | strength 2.0 becomes 4.0; a wagon held and named (`with_kind="wagon"`); cells moved 2 becomes 3; cart at cell+3 becomes cell+4. | A wagon's haul fits push at 0.6. With strength 4 the surplus is 1.6, so 3 cells. |
| test_phase050_resolution.py | `test_a_weak_resident_does_not_move_the_cart_even_at_full_force` | wagon held and named; the comment's capability 0.75 becomes 0.45. Outcome unchanged (stuck). | As above. |
| test_phase050_resolution.py | `test_a_pull_draws_the_cart_...` | strength 2.0 becomes 4.0; wagon held and named. Outcome unchanged (stops one cell short). | As above. |
| test_phase050_resolution.py | `test_smashing_a_wooden_chest_...` | "each attempt damages it" becomes "the first attempts damage it, and a worn hammer makes no progress". The post-break check rests the actor first. | A hammer's fitness is its condition, so a worn hammer stops damaging the chest before it breaks. A worn hammer costs more stamina, so the actor collapsed before the check. |
| test_bigville_world_migrated.py | `test_a_forged_tool_is_a_discrete_item_...` | fitness 0.48 becomes `approx(0.4752)`. | The master's use wore the forge's hammer to 0.96, and the novice's knife is made at its condition. |
| test_bigville_world_migrated.py | `test_a_composite_tool_...` | quality 0.6 becomes `approx(0.594)`; fitness 1.2 becomes `approx(1.188)`. | The hammer was worn by the head's forging before assembly. |
| test_bigville_world_migrated.py | `test_the_new_trades_run_their_production_chains` | cooper: two rives make 5.91 staves, short of the barrel's six, so three rives (8.73 staves) are made. The weaver: two weaves make 1.95 cloth, short of the coat's two, so three weaves (2.85) are made. | Each rive or weave wears the adze or the loom, and a worn tool yields less. |
| test_bigville_world_migrated.py | `test_a_made_barrel_is_a_usable_container` | three rives, not two (as above). Barrel quality 0.7 becomes `approx(0.6685)` in two places (0.7 scaled by the adze's 0.91). | As above. |

Tests added to an existing file: `import pytest` in `test_bigville_world_migrated.py`.

## Validation

Run from `/home/matt/ozmadev/bigville`. Logs are in `docs/phases/phase048/`.

| Command | Result | Log |
|---|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS 0; WARNINGS 0. Its INFO lines: `TOOL_FIT: 38 verbs, 23 pairs, 1 authored tools (APPROX)`; `RESOLUTION: 24 verbs, 11 materials` | `selftest_final.log` |
| `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS 0; WARNINGS 0 | `check_hamlet.log` |
| `python3 -m domains.check` | exit 0 | `check_bigville.log` |
| `python3 tools/generate_seeds.py --check` | exit 0; "match pack 'bigville' (31 files)" | `seeds_check.log` |
| `pytest tests/test_phase013a_packs.py tests/test_phase058_persona.py tests/test_phase017_generated_seeds.py` | 63 passed (pack bytes and generated seeds) | run output |
| `python3 docs/phases/phase050/golden_before.py` | identical to `golden_pre.log` | `golden_post.log` |
| `pytest tests/test_phase048_tool_fitness.py` | 16 passed | run output |
| `pytest` on the tool, resolution and migrated files, before the final run | 178 passed | run output |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (final) | 1417 passed, 2 skipped, 3 failed. The 3 are `test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`, `test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control` and `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`, each `ModuleNotFoundError: worlds.bigville_ocelot_adapter` | `pytest_final.log` |

The earlier full run (`pytest_post.log`, before the migrated-test edits) gave 1413 passed and 7 failed: those 3 Ocelot
failures and 4 in `test_bigville_world_migrated.py` (the stave, quality and fitness values above).

`pytest_pre.log` is not a valid baseline. I started it before my edits, but it was still running when I changed
`worlds/bigville_world.py`, and it shows a `NameError` from one of those edits. I did not rerun the baseline on a clean
tree. The reference is the Phase 050b report (1349 passed, 3 failed, the same Ocelot tests).

Git status: start `git_status_start.txt`, end `git_status_end.txt`. My files are the ones listed in Files edited, plus
the untracked `tests/test_phase048_tool_fitness.py` and `docs/phases/phase048/`. Nothing was committed, staged, or
reformatted.

## Limits

- **Village not run.** The 100-resident town was not run. The numbers that change in a village are the worn-tool
  yields and times, the hands strain, and any tool breakage. Those numbers are unmeasured.
- **`stop` and `set_intensity` are not reachable from a backend.** `game.py` calls `free_action` only for `speak`. The
  two free actions work through the world's method (tests call `free_action`), but no resident can send them yet.
- **`tool` in a proposal.** `game.py` passes plans through `_enact_plan`, so the `tool` key reaches the world without a
  change there. Only `work` (and `start`/`make` through the same branch) reads it. I did not check how an LLM or Ocelot
  response is validated before enactment.
- **Offers.** The options a backend is offered still need the right tool (`_recipe_inputs_available`, `_capable`).
  Bare-hand or any-held-tool work is accepted when proposed, but no backend is offered it. The simple backend's
  default is therefore unchanged, and so is its improvisation (below).
- **`improvise` is not wired.** `SimplePolicy.improvise` (default False) and `improvised_tool` exist. A test checks only the
  default (False); `improvised_tool` has no test. The choice method does not call them. Phase 059 owns that change.
- **Per-tick observation.** A resident sees its batch's waste, its broken tool and its accidents as events and harm. It
  does not see its per-tick progress. The job's `fit`, `fit_low` and `effort_mult` are stored on the Job node for the
  engine. Phase 052's leak list must name them.
- **Instant recipes take no time.** `do` completes in the same call, so the 1/fit time does not apply to it. Its
  stamina (times 1/fit, capped) and its waste do apply.
- **The spoon.** The pack has no wooden spoon. The test uses a `board` (wood, verb knead) on a locked iron chest.
- **Pushing by hand.** Bare hands fit a push at 0.05, so a resident with no tool moves no cart (brief rule). The tests
  hold a wagon for that reason.
- **Strain of bare-handed jobs.** Summed over a job, strain from bare hands is about `(1 - f) / f`, which is about 19
  units at f = 0.05. With strain limit 1.0 and accident harm 0.1 (both APPROX), that is about 19 accidents of 0.1 health
  each, before the life-stage fragility factor. This follows from the formula. I did not measure it in a run, and it may
  kill a worker who stays on bare hands.
- **Edge and weight are per kind, not per material.** An item's edge is a kind list (`edged_kinds`), because a material
  does not decide whether a tool has an edge. Weight is the item's weight (default 1.0), so most tools pass the weight term.
- **Authored rows are in `TOOL_FIT.rows`.** The brief asked for them on items. I did not change `ITEMS`, so no asset
  regeneration was needed.
- **Brief items not done.** Phase 040's strike and throw reuse (040 is not committed). Learning which tool suits, and
  the skill, season and strength gates (Phase 049). Place-bound equipment.

## Shared file notes

The `packs/*/pack.json` diffs show other sessions' changes (the persona manifest entries, as deletions in the working
copy). Only the `TOOL_FIT` entry is mine. `bigville/backends/protocol.py` and `domains/bigville_entities.py` also contain
other sessions' hunks, listed above.

## Open questions

1. **Bare-hand pushing.** Should push, pull and drag have a per-verb bare-hand row (for example 1.0 for a body moving a
   load at normal intensity) instead of the seed's 0.05? The brief's rule makes the cart unmovable without a tool.
2. **Bare-hand strain.** About 19 strain units per full bare-handed job (see Limits). Should `accident_harm`, `strain_limit`
   or the strain share be tuned before any village run?
3. **Yield curve.** Yield is linear in fit, so a 2% worn tool costs 2% of output. A milder curve, such as a threshold
   below 0.9, is an option. The brief says only that yield falls with fit.
4. **Offers.** Should the option list offer bare-hand or any-held-tool work to LLM and Ocelot backends? Doing so would
   also change what the simple backend sees, unless its improvisation is off by default in its own filter.
5. **Routing.** Should `game.py` route `stop` and `set_intensity` from backend responses? That is Tract B's file.
6. **Village.** Should the 100-resident village run before this phase is committed? The numbers will change, and the
   changes are listed above but not measured.

## Follow-ups

- Phase 040: the strike and throw rows use the `TOOL_FIT` table and the bare-hand floor, as the brief says.
- Phase 052: add the hidden names this phase creates (`fit`, `fit_low`, `effort_mult` on jobs, and `tool_tally`).
- Phase 056: count improvised work and accidents from `tool_tally` (and `SimulationReporter.improvised_work`).
- Phase 059: call `SimplePolicy.improvised_tool` from the choice method, if the simple backend should improvise.
