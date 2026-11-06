# Phase 050b: the rest of the resolution core

## Summary

Phase 050b adds the remaining items of Phase 050 that stage 1 left open:

1. `displace` for push, pull and drag. A physical object on the ground moves by the surplus force. Lift, carry, throw and dig stay refused as `unsupported`.
2. Spill: a container broken by an attempt drops its contents on its cell as dropped stock.
3. Recipe pace (intensity on a timed `start`): haste and care caps, a stamina term, quality and yield curves, and spoilage below `ruin_below`.
4. `set_intensity` free action: changes a running job's pace and keeps its progress.
5. Trivial and slot rules (Phase 029's thresholds, applied to attempts), and strain recovery during sleep.

The self-test reports 0 errors and 0 warnings on both packs. The full suite gives 1349 passed, 2 skipped, 3 failed. The 3 failures are the known Ocelot adapter tests (`worlds.bigville_ocelot_adapter` not found). The golden numbers are unchanged.

One incident needs the supervisor's attention. My pack export rewrote an untracked file that belongs to Tract B. See Changes, "Incident".

The 100-resident village was not run.

## Changes

### New code

- `worlds/resolution.py`, appended: `pace_clamp`, `pace_defect`, `pace_quality`, `pace_yield`, `ruined`, `push_cells`, `friction_demand`. Pure, no state, no randomness. At pace 1.0, `pace_quality` returns its input unchanged (the same float).
- `domains/bigville_entities.py`, `_check_resolution`: checks that each displace verb says `implemented` (true or false) and that no other verb does; range checks on the new `RESOLUTION` keys; `trivial_below <= slot_above`; pace quality and yield are non-increasing over pace 0.1 to 3.0; `FREE_ACTIONS` has `set_intensity`.

### Pack data (both packs unless stated)

- `packs/bigville/world/resolution.json`, `packs/test_hamlet/world/resolution.json`:
  - `RESOLUTION` gains `haste_cap`, `care_cap`, `haste_penalty`, `haste_yield_loss`, `ruin_below`, `trivial_below`, `slot_above`, `strain_sleep_recovery`, `push_mass_unit`, `push_cells_per_surplus`, `push_max_cells`.
  - `VERBS`: `push`, `pull` and `drag` are `implemented: true` (`drag` is new in the bigville pack). `lift`, `carry`, `throw` and `dig` are `implemented: false`. The hamlet keeps `carry` as `implemented: false`.
  - The `_doc` explains each new key and marks it APPROX.
- `packs/bigville/world/free_actions.json`, `packs/test_hamlet/world/free_actions.json`: `set_intensity`, with kind, `requires_target: false` and a description.
- `packs/bigville/world/major_actions.json`, `packs/test_hamlet/world/major_actions.json`: the `attempt` description names push, pull and drag.
- `pack.json` is not touched by this phase.

### World (`worlds/bigville_world.py`)

Hunks, by function. None touches the other session's hunks (the `seed_founding_relationships` call, the `"food"` fetch option, and `resident_plan_from_context`).

- `_resolve_jobs`: a timed job advances `speed x pace` per tick. The quality goes through `pace_quality`, the output through `pace_yield`, and a spoiled batch yields nothing (its inputs are still used). The byproducts are skipped too when spoiled. A `batch_spoiled` event is created.
- `_spend_job_stamina`: the effort is scaled by `pace ** k`.
- `_open_job`: takes `pace` and stores it on the Job node.
- `start`: takes `intensity` (the pace), clamped by `_pace_value`.
- `_major_action_attempt`, the `start` branch: validates `intensity` and passes it to `start`.
- `_enact_plan`, the `work` line: passes an optional `intensity` from the plan.
- `free_action`: routes `set_intensity` to the new `set_job_pace`.
- `_resolve_sleep` and the new `_recover_strain`: a sleeping resident sheds `strain_sleep_recovery` per clock tick.
- The attempt block (from `_attempt_verb` to `_run_displace`, which replaces the stage-1 `_attempt_verb` and `_run_attempt`):
  - `_enact_attempt` applies the slot rule.
  - `_capability_terms`, `_resolve_terms`, `_container_plan` and `_finish_attempt` split the stage-1 code into shared parts. The damage and open results are unchanged (golden and tests agree).
  - `_spill_contents` runs when a container breaks.
  - `_displace_verb`, `_displace_plan`, `_run_displace` and `_sign` implement displacement.
- `_record_attempt`: takes `moved` and records `cells_moved`.

### Prompt (`bigville/backends/prompts.py`)

One hunk: the attempt-verb line lists only verbs the world runs (no `implemented: false`).

### Tests

- `tests/test_phase050_resolution.py`:
  - One existing test edited. `test_a_physical_verb_without_an_implemented_primitive_is_unsupported` used `push` as its unimplemented example. Push is now implemented, so the verb became `lift` (still unimplemented). The assertion (`False`, reason `unsupported`) is unchanged.
  - Added `import pytest`.
  - Appended 17 tests (displace, the slot and trivial rules, spill, pace, set_intensity, strain).
- `tests/test_resolution_pure.py`: appended 6 tests for the pure pace, yield, ruin, push and friction functions.

### Incident: a file of another session was rewritten

I ran `python3 tools/export_pack.py` and `python3 tools/export_pack.py --pack test_hamlet` to normalise my edits. The exporter rewrote `packs/test_hamlet/world/persona.json`. That file is untracked and belongs to Tract B (Phase 058).

- Before: md5 `df6a9d3e81be1b00091b58424901ba44`. After: md5 `a3f1969d147cfe78d410453548c8064a`.
- I could not restore the original bytes. I searched `/tmp`, `/home/matt` and the pytest temporary directories for the hamlet persona text and found no copy.
- The exporter's own round-trip check passed, which should mean the tables are unchanged. I did not verify the bytes.
- The bigville persona file and every other pack file had identical checksums before and after the export run. Only this file changed.
- Side observation: the two `test_phase013a_packs.py` failures that Phase 050 recorded now pass (the pack tests give 49 passed with the persona tests). I did not confirm the cause. The hamlet file's layout is one candidate, but I cannot prove it now that the file has been rewritten.

Tract B should check `packs/test_hamlet/world/persona.json` against its own copy.

## Validation

Run from `/home/matt/ozmadev/bigville`. Logs are in `docs/phases/phase050/` with the `050b_` prefix. Earlier Phase 050 logs are untouched.

| Command | Result | Log |
|---|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS 0; WARNINGS 0 | `050b_selftest.log` |
| `python3 -m domains.check --pack test_hamlet` | exit 0; ERRORS 0; WARNINGS 0 | `050b_check_hamlet.log` |
| `python3 -m domains.check` | exit 0 | `050b_check_bigville.log` |
| `python3 tools/generate_seeds.py --check` | exit 0; "match pack 'bigville' (31 files)" | `050b_seeds_check.log` |
| `timeout 1500 python3 -m pytest -q -p no:cacheprovider` | 1349 passed, 2 skipped, 3 failed (the three Ocelot tests, `ModuleNotFoundError: worlds.bigville_ocelot_adapter`) | `050b_full_pytest.log` |
| `pytest tests/test_phase050_resolution.py tests/test_resolution_pure.py` | 66 passed (44 and 22 test functions) | run output |
| `pytest tests/test_phase013a_packs.py tests/test_phase058_persona.py` | 49 passed | run output |
| `python3 docs/phases/phase050/golden_before.py` | identical to `golden_before.log` | `050b_golden_after.log` |

Pace probes, from the world run on the `make_table` recipe (woodworker, 150 minutes, which is 10 ticks at 15 minutes per tick):

| Pace | Ticks | Item quality | Stamina spent |
|---|---|---|---|
| 0.5 | 20 | 0.85 | 0.071 |
| 1.0 | 10 | 0.70 | 0.205 |
| 1.5 | 7 | 0.625 | 0.382 |

The 1.0 row matches the committed reference: quality equals the worker's skill (0.70).

Push probe (a 100-unit cart, adjacent, on grass; the force is strength x technique 0.5 x intensity):

- Strength 2.0 at intensity 3.0: the cart moves 2 cells.
- Strength 2.0 at intensity 1.0 or 1.5: no movement.
- Strength 0.5 at intensity 3.0: no movement.

Pinned by the tests.

## Limits

- **Displace.** Implemented for push, pull and drag only. Demand is `mass / push_mass_unit x move_time of the cell`. Surplus is capability minus demand, and the cells moved are `floor(surplus x 2)`, capped at 3. Push reaches 1 cell and pull or drag reaches 2. A pull stops short of the resident's own cell. There is no occupancy check: a cart can slide onto another resident or object. Displacement makes no noise and does not wear the cart. Lift, carry, throw and dig are refused as `unsupported`. Throw belongs to Phase 038. The CARRYING table is not used: it drives walking and carrying, not pushing.
- **Cart.** No cart in the town can be targeted, because a cart is a tool item with no cell. The acceptance cart is a `PhysicalObject` created in the test (`mass` 100, `cell` set). Item weights are unitless pack numbers, so `mass` is an authored attribute in the same weight units. An object without `mass` falls back to `item_weight(kind)` when its kind is in ITEMS, and is otherwise refused.
- **Pit-saw acceptance.** The pack has no pit-saw recipe. `saw_planks` at the sawpit takes 20 minutes, which is two ticks. At 1.5 it still finishes in two ticks, so "finishes sooner" cannot show in whole ticks. Its yield does change (1.75 against 2.0 at pace 1.5). The timing and quality claims are tested on `make_table` instead.
- **Quality and yield curves.** They are functions of pace only. I did not make them functions of capability against recipe difficulty. The `rho` in the brief is the pace ratio here, not the worker's capability.
- **Spoilage.** A batch spoils only when the pace takes its quality below `ruin_below` (0.1). A batch that was already below the line at pace 1 is not spoiled by the pace. This keeps committed batches unchanged. A spoiled batch yields nothing.
- **Spill.** Spilled goods become dropped-stock piles on the cell. No existing path lets a resident pick up a dropped-stock pile, so the spilled goods cannot be recovered in the world. A container held by a resident spills at that resident's feet.
- **set_intensity.** The world method and the free action work. `game.py` calls `free_action` only for `speak`, and backends cannot send free actions other than speech. So no resident can run `set_intensity` through the game yet. `FREE_ACTIONS` still lists it, and the LLM prompt therefore lists it too.
- **Trivial and slot.** Applied to attempts, using the stamina share with intensity (the stamina share times intensity to the power k). The thresholds are the Phase 029 values (0.25 and 0.5), kept in `RESOLUTION` as copies. `CONTEST` keeps its own copies, which Phase 029's code reads. Moving them is left for later.
- **Strain recovery.** 0.1 per clock tick of sleep (APPROX, not sourced; a clock tick is 15 minutes, so a full strain of 1.0 clears in 10 ticks, about 2.5 hours). Strain does not recover while awake.
- **Attempts and stamina.** Low-share attempts (below 0.25) now spend no stamina. Stage 1's tests pass with this change, and no committed number moved.
- **Blows and throws.** Not started, as the brief asked (Phase 038).
- **Village.** The 100-resident town was not run. The changed code runs in every village (the job loop, sleep recovery and the attempt path). Its numbers at pace 1.0 are identical in the golden checks and the suite, but no village result is claimed.

## Shared files

Hunks that are mine (for `git add -p`). Tract B's hunks in these files are left out.

- `worlds/bigville_world.py`: the hunks at `_resolve_jobs` (timed-job progress, the quality block, the byproducts line), `_spend_job_stamina`, `_open_job`, `start` and `_pace_value`, `_major_action_attempt` (`start` branch), `_enact_plan` (the `work` line), `free_action` and `set_job_pace`, `_resolve_sleep` and `_recover_strain`, and the attempt block from `_attempt_verb` to `_run_displace`, with `_record_attempt`. Tract B's hunks are at the founding-relationships call, the `"food"` line in the fetch option, and `resident_plan_from_context`.
- `domains/bigville_entities.py`: two hunks in `_check_resolution`: the displace `implemented` check in the VERBS loop, and the Phase 050b block before `info.append(RESOLUTION ...)`. The `check_consistency` hunk is Tract B's.
- `bigville/backends/prompts.py`: one hunk, the attempt-verb line.
- `worlds/resolution.py`, `tests/test_phase050_resolution.py`, `tests/test_resolution_pure.py`: the whole diff is mine.
- `packs/*/world/resolution.json`, `free_actions.json`, `major_actions.json`: mine only. `pack.json` is not changed this phase.

## Open questions

1. **Routing `set_intensity`.** Should `game.py` route free actions from backend responses (Tract B's file), or should `set_intensity` be left out of the prompt until it is routed?
2. **Pick-up of spilled piles.** Dropped stock has no pick-up action. Should spilled goods be recoverable?
3. **Curves.** Should quality and yield depend on capability against recipe difficulty as well as on pace?
4. **Thresholds.** Should `CONTEST` drop its copies of `trivial_below` and `slot_above` and read them from `RESOLUTION`? That changes Phase 029's code.
5. **Persona file.** Tract B should check `packs/test_hamlet/world/persona.json` after the export incident above.

## Follow-ups

- Lift and carry: a held physical object, which needs a hands model.
- Occupancy for displacement, and noise for a loud drag.
- Escalation: nothing calls `escalated_intensity` (unchanged from stage 1).
