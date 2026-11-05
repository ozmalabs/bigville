# Phase 023: Timed jobs occupy the worker

## Summary

A worker with a timed job in progress cannot start another recipe. Starting or doing a recipe while busy is
refused with the new reason code `busy`. A timed job now advances, completes and spends stamina only on
ticks when its worker stands on the cell where the job started. Walking away pauses it. It resumes on return,
with its inputs and remaining ticks untouched. The paused state is published on the actor (`job_paused`) and
on the affordances, and the world offers a legal move back to the start cell. Eating while busy still works.

## Changes

Files changed or created:

- `worlds/bigville_world.py` (my hunks only, by function):
  - `_resolve_jobs`: after the `complete` check, a job whose worker is off its start cell is skipped
    (no decrement, no completion, no stamina). The actor's `job_paused` attribute is set to match.
    Completion clears `job_paused` next to `busy`.
  - `_open_job`: the Job node stores `start_cell` (the worker's cell as `[x, y]`) when the worker has a position.
  - `_move_actor_to`: one line re-syncs `job_paused` after any move, so the attribute is current without
    waiting for the next `_run`.
  - `_recipe_refusal`: returns `busy` when `busy(actor)` is true, checked after `not_known` and before `unskilled`.
    `start`, `do`, and `major_action` ("work", "make", "start") all pass through it.
  - `_actor_options`: while the job is paused, every option carries `job_paused: True`, and a `move` option to
    the start cell carries `resumes_job: True` (added only when that cell is reachable). Inserted before the
    destination loop, so the resume move gets the usual `destination` and terrain fields.
  - New methods after `busy`: `_job_of`, `_job_away`, `_set_job_paused`, `job_paused(actor)`,
    `job_start_cell(actor)`.
- `packs/bigville/world/refusal_reasons.json` and `packs/test_hamlet/world/refusal_reasons.json`: new code `busy`
  with a description, after `slot_used`. Both files match `tools/export_pack.py` output byte for byte.
- `bigville/backends/cheap.py`: a module constant `RESUME_JOB_BONUS = 40.0`, added to the score of options with
  `resumes_job`. This is the only backend change. See Deviations.
- `tests/test_phase023_job_occupancy.py` (new, 9 tests).
- `docs/phases/phase023/`: this report and the logs.

No existing test was changed. No entity table or self-test check was added (the brief names no new table).

## Design and final choices

- **Pause rule (the brief's default, kept).** A job advances, completes and spends stamina only while its
  worker stands on its start cell. The check runs in every `_run`, not only on armed ticks. A job waiting at
  zero remaining for inputs also waits when its worker is away, so the worker must return before it completes.
- **Start cell.** Recorded at job open. A job opened with no position is never paused.
- **Stamina.** The pause gate sits before the stamina spend, so a paused job spends nothing. Its declared
  stamina is spent over the ticks it actually runs.
- **Busy.** `busy` is the existing actor flag. It stays set until the job completes, including while a job
  waits for inputs or a tool. A busy worker is refused new recipes, which matches the affordance filter that
  already hid recipe options while busy.
- **Read-offs.** `job_paused` (1.0 or 0.0) on the actor node. `job_paused(actor)` and `job_start_cell(actor)`
  on the world. Affordances carry `job_paused` and `resumes_job`.
- **Resume.** The world offers the walk back. The backend chooses it. The cheap backend adds 40 to its score.
  The value is a valuation, not a rule, and sits in `RESUME_JOB_BONUS`. It is not sourced. It is set so that a
  routine move (score 10) loses to the resume.

## Data and sources

No new distribution, rate, or real-world figure. `RESUME_JOB_BONUS = 40.0` is a backend valuation, not a
figure from a source. The `busy` description is written for the resident, as the Phase 021 codes are.

## Validation

Commands and results (run in this checkout, which also holds the other session's uncommitted work):

- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0), issues (0). Log: `selftest.log`.
- `python3 -m domains.check --pack test_hamlet`: exit 0. Log: `check_hamlet.log`.
- `python3 tools/generate_seeds.py --check`: exit 0, 31 files match the pack. Log: `seeds_check.log`.
- `python3 tools/export_pack.py` (bigville and `--pack test_hamlet`, written to a temp directory): output
  identical to `packs/` for both packs, so the hand-edited JSON is in the exporter's layout.
- `python3 -m pytest tests/test_phase023_job_occupancy.py`: 9 passed.
- Full suite, the other session's seven files ignored (`--ignore` on `test_bigville_game_persistence.py`,
  `test_bigville_graph_persistence.py`, `test_bigville_ocelot_communication.py`,
  `test_bigville_ocelot_fresh_process.py`, `test_bigville_world_persistence.py`,
  `test_mixed_ocelot_checkpoint_parity.py`, `test_mixed_ocelot_village.py`): **849 passed, 1 skipped**, exit 0.
  Phase 022 reported 840 passed, 1 skipped with the same ignores. The difference is the 9 new tests.
  Log: `final_pytest_excl_other_session.log`.
- Full suite with every file: 866 passed, 2 skipped, 3 failed, exit 1. Log: `final_pytest.log`. The three
  failures are in the other session's files and are the known `ModuleNotFoundError: worlds.bigville_ocelot_adapter`
  (`test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
  `test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
  `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`).
  This run started before the last test in my file was added, so it includes 8 of my 9 tests.
- I did not re-establish a clean-HEAD baseline. An attempt to run one overlapped with my edits and was discarded.
  The Phase 022 figure above is the comparison.

Tests added in `tests/test_phase023_job_occupancy.py`:

- `test_busy_is_a_refusal_reason_in_the_pack`
- `test_a_second_start_while_busy_is_refused`: a second `start` and a `do` are both refused.
- `test_a_refused_start_while_busy_publishes_the_busy_reason_and_uses_no_slot`: the outcome is `busy`, and the
  refused attempt does not claim the turn slot.
- `test_a_worker_who_is_busy_can_still_eat`
- `test_walking_away_pauses_the_job_and_it_completes_after_return`: no advance, no cancel, inputs and reserve
  unchanged while away; finished after return.
- `test_the_declared_stamina_is_spent_once_however_long_the_job_pauses`
- `test_a_paused_job_shows_on_the_affordances_with_a_way_back`
- `test_a_job_short_of_its_tool_still_completes_when_the_tool_arrives` (existing Package 7 behaviour)
- `test_the_simple_backend_walks_back_to_a_paused_job`

## Limits

- The 100-resident village was not run. This phase changes its behaviour in two ways. A busy resident is refused
  new recipes (previously a second job could open). A job whose worker walks away now pauses. The effect on
  output is unmeasured.
- A job that waits for an input that never arrives now keeps its worker busy indefinitely. Before, the same
  worker could open a second job. The worker can still eat and move.
- The tests move the worker with `_move_actor_to`, a teleport. They do not walk the worker step by step with
  `move`. The pause check is per run, so a step-by-step walk is covered by the same code path, but no test
  shows it.
- `RESUME_JOB_BONUS` is untuned. Nothing measures how often a paused resident resumes in a run.

## Deviations

- **Pack edits outside the brief's write scope.** The brief's scope does not include `packs/`. The `busy` code
  was added to both packs because the supervising instruction asked for it.
- **Backend edit beyond "read the read-off".** The brief limits `cheap.py` to reading the paused read-off. The
  cheap backend reads `resumes_job` and adds a score bonus, so a paused resident walks back. Without it, the
  published read-off changes nothing in that backend. The bonus can be removed if the supervisor prefers a
  backend that only reads.
- **Two world hunks outside the job functions.** `_move_actor_to` (one line, to keep `job_paused` current) and
  `_actor_options` (the resume option and the paused flags) are not in the job code.
- **Other session's hunks** in `worlds/bigville_world.py` (the `food` flag in `_actor_options`, and
  `resident_plan_from_context`) and in `bigville/game.py` were not touched.

## Recipe audit: candidates for unattended work (data only, not implemented)

Every recipe in `packs/bigville/world/recipes.json` was read for whether a worker must stay with it until it
finishes. Times are the pack's `time_minutes`. No real-world duration was checked, so none is cited here.
This list is a judgement by process type and needs review before a phase uses it.

Strong candidates (a process that runs once set up):
- Fermentation and brewing: `brew_ale` 480, `brew_beer` 480, `brew_cider` 360, `brew_mead` 360, `make_vinegar` 120.
- Malting and steeping: `malt_barley` 240.
- Pit tanning: `tan_hide` 240.
- Charcoal clamp: `burn_charcoal` 60.
- Cheese, curds, yogurt: `make_cheese` 240, `make_cream_curd` 180, `make_yogurt` 180.
- Pickling, curing and salting: `make_pickles` 120, `make_sauerkraut` 120, `pickle_beets` 90, `cure_ham` 90, `salt_fish` 75, `salt_pork` 60, `dry_fruit` 180.
- Compost heap: `make_compost` 60 (an open recipe).
- Paper vat: `make_paper` 240.

Possible candidates (partly attended, for example turning, feeding a fire, or stirring):
- Ovens and firings: `bake_bread` 120 (the pack's oven-load example, which the brief names as out of scope),
  and the other `oven` bakes (`bake_*`, `make_pie`, `make_*_pie`).
- Smelting: `smelt_iron` 90. Dye vats: `dye_cloth` 120.
- Smoking and spit roasting: `smoke_fish` 150, `roast_meat` 120, `roast_poultry` 135, `roast_fish` 90.
- Long simmering in a pot: the stews and soups (for example `make_stew` 150, `make_pottage` 90, `make_pea_soup` 100).
- Pressing: `press_linseed_oil` 60, `make_cheese` (press).

## Open questions

1. Should a job that waits for an input or tool release its worker's busy flag, or keep it? The current choice
   keeps it (Package 7). That blocks the worker's other recipes until the input arrives.
2. Is 40 the right resume bonus, or should resuming be a rule the cheap policy reads from a pack constant?
3. Should `RESUME_JOB_BONUS` move to a pack table in a later phase? The standing rule says tunables go in the pack.
   The brief kept the write scope to the world and cheap.py, so I did not add a table.

## Follow-ups

- Phase 024 (sleep and collapse) pauses jobs for asleep and collapsed actors. The pause check in `_job_away`
  is the place to add those conditions, and `job_paused` is already the read-off.
- The recipe candidates above could become a `unattended` flag in `RECIPES` in a later phase, with a decision
  on whether a finished unattended batch needs its worker present to collect it.
