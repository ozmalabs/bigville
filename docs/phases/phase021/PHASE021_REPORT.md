# Phase 021: refusal records and result feedback

## Summary

A refused major action now names a physical reason from a pack table (`REFUSAL_REASONS`, 21 codes).
The world logs each refusal for the acting resident (newest 20 kept, counted in total) and counts
refusals by action and reason. `last_outcome` (turn, action, applied, reason) sits on the actor's own
node and reaches that actor's observations and prompt. `BigvilleGame.last_rejections` lists this
turn's refusals, one per resident. `reporting.py` adds a `refusals` block to the report.

Refusal records checkpoint with the world, so `game_persistence.py` needed no change. The brief
assumed the world already had a typed-graph refusal log. It did not, so I created one (see Deviations).

Result: self-test 0 errors, 0 warnings. Full suite 851 passed, 2 skipped, 3 failed. The 3 failures
are the Ocelot adapter tests that fail at baseline with `ModuleNotFoundError: No module named
'worlds.bigville_ocelot_adapter'`. Phase 020 tests still pass (200). New `tests/test_phase021_refusals.py`: 20 passed.

## Changes

`domains/world_affordances.py`: binds `REFUSAL_REASONS` and `REFUSAL_LOG_LIMIT` from the pack.

`packs/bigville/world/refusal_reasons.json` (new): `REFUSAL_REASONS` (code -> description written for the
resident, quoted in the prompt) and `REFUSAL_LOG_LIMIT` = 20. `packs/bigville/pack.json`: two table entries.

`packs/test_hamlet/world/refusal_reasons.json` (new, a copy of the bigville table): the world needs the
codes for any pack. `packs/test_hamlet/pack.json`: two table entries.

`domains/bigville_entities.py`: new `_check_refusal_reasons` (snake_case codes, a description per code,
a `not_possible` catch-all, a whole-number log limit of at least 1), called from `check_consistency`.

`worlds/bigville_world.py`, by function (the other session's hunks are the `"food"` line in `_actor_options`
(around line 6650) and `resident_plan_from_context` (now at line 7049, through about line 7099); none of my
edits is within 4 lines of them):
- `__init__`: `_refusal_code`, `_outcome_open`.
- New block before `_claimed_attempt`: `_refuse` (sets and returns False; raises for codes not in the
  table), `_recipe_refusal` (the first failing check for a recipe, in `_capable`/`_can_attempt`/
  `_recipe_tools_usable` order), `_attempt` (outermost attempt publishes; nested attempts do not), `_publish_outcome`
  (writes `last_outcome`; for a refusal, adds a `Refusal` node linked by a `refused` edge, updates
  `refusal_counts`, drops the oldest entries past the limit), `last_outcome`, `refusals`, `refusal_counts`.
- `_claimed_attempt`: a claim that fails returns `slot_used`.
- `major_action`: now a wrapper over `_major_action_attempt`, which holds the old branches. Each branch
  returns `self._refuse(code)` for its checks. `take` returns `unsupported`.
- `do`, `start`: the recipe check is `_recipe_refusal`. Slot claims return `slot_used`.
- `enact_plan`: wrapped in `_attempt`. `_enact_plan`: unknown actor `unknown_target`, non-dict plan
  `malformed`, a `rest` when stamina is at least 0.8 `not_needed`, an unmatched plan `malformed`.
- Primitives, each refusal return given a code: `move_physical_object_as_actor`, `_physical_transfer_precheck`
  (rewritten as `if ...: return self._refuse(...)` with the same result), `give`, `_move_inventory_to_inventory`,
  `_give_discrete_item`, `_accept_discrete_item`, `pick_up`, `drop_item`, `eat`, `put`, `fetch`,
  `_move_stock_to_inventory`, `sow`, `water_crop`, `harvest_crop`, `fertilise`, `maintain_infrastructure`,
  `advance_building`, `_husbandry_yield`, `pay_obligation`, `collect`, `deliver_collected`, `care_for`,
  `complete_request`.

`bigville/game.py` (my hunks only): `_context` adds `observations["last_outcome"]`; new property
`last_rejections` before `step`. The other session's `_apply_response` hunk is untouched.

`bigville/backends/prompts.py`: `PromptBuilder.build` adds a top-level `public["last_outcome"]` when
the actor has an outcome, with `meaning` taken from the pack description of its reason.

`bigville/reporting.py`: `SimulationReporter.refusals()`, and `report["refusals"]`.

`tests/test_phase021_refusals.py` (new, 20 tests): refused fetch at an empty store records
`out_of_stock`; it appears in the actor's next context and not a neighbour's; a successful rest records
nothing; the prompt carries the reason and meaning; the report counts it; `last_rejections` shows the
turn's refusals after `step()` and empties after a tick; a game checkpoint round trip (`save_game_checkpoint`
/ `load_game_checkpoint`, unchanged) keeps the log, counts, last outcome and `last_rejections`; the log
keeps 20 entries and counts all; reasons for 7 parametrised cases; slot reuse; nested plans logged
once; `rest` when not tired; every code the world source uses is in the table.

No existing test was edited. No test number changed.

## Validation

Run from `/home/matt/ozmadev/bigville`. Working tree included the other session's uncommitted files.

- `git status --short` at start: the other session's modified files (README.md, bigville/backends/ocelot.py,
  bigville/game.py, bigville/runtime.py, bigville/seeds/bigville_actor_decision.json, docs/AGENT_BACKENDS_PLAN.md,
  tests/test_bigville_game_api.py, tests/test_bigville_scenarios.py, worlds/bigville_world.py) and their untracked
  files. Mine: `packs/` (pack.json x2, refusal_reasons.json x2), `domains/bigville_entities.py`,
  `domains/world_affordances.py`, `bigville/backends/prompts.py`, `bigville/reporting.py`,
  `tests/test_phase021_refusals.py`, `docs/phases/phase021/`.
- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)` (before and after my edits).
- `python3 -m domains.check --pack test_hamlet`: exit 0, ERRORS (0).
- `python3 tools/export_pack.py` and `--pack test_hamlet`: normalise rewrote the pack files; no other file
  changed.
- `python3 tools/generate_seeds.py --check`: exit 0, "match pack 'bigville' (31 files)".
- `timeout 900 python3 -m pytest -q -p no:cacheprovider tests/test_phase021_refusals.py`: 20 passed.
- `timeout 900 python3 -m pytest -q -p no:cacheprovider tests/test_phase020_validation.py`: 200 passed.
- `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (final): 851 passed, 2 skipped, 3 failed
  (log: `docs/phases/phase021/full_suite.log`). Failures: `test_bigville_ocelot_communication.py::
  test_real_ocelot_advertises_only_wired_communication_capabilities`, `test_mixed_ocelot_checkpoint_parity.py::
  test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`, `test_mixed_ocelot_village.py::
  test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`. Each raises
  `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'` (baseline, same three). Before my
  edits the same run gave 831 passed, 2 skipped, 3 failed.

## Limits

- Reasons come from reading the refusal sites, and the tests cover only some of them. Sites not tested
  directly: `treat` (a medicine shortfall inside `care_for` gets `not_possible`), `_inventory_can_receive`
  (not on the major-action path), and the `give` fallback when `_move_inventory_to_inventory` refuses (it
  inherits that function's code).
- `not_possible` is the fallback in `_attempt` when a refused attempt names no reason. No tested path
  produced it.
- Only major actions publish an outcome and log refusals. Free actions (speech, notes, accept, decline)
  are not covered.
- `enact_plan` still calls `dict(plan)` first, so a non-mapping plan raises `TypeError` before any refusal
  is logged (Phase 020 open question; left alone).
- A short payer's `pay_obligation` is logged as `out_of_stock` and keeps its slot, because arrears are recorded.
- Refused `rest` proposals from healthy residents now log `not_needed`. The 100-resident village was not
  run. Refusal logging adds graph nodes, which changes node ids. Whether village results change was not measured.
- Not checked: whether the Ocelot backend or the other session's mixed-run code reads `observations` in a way
  the new `last_outcome` key affects (their tests fail at baseline on the missing adapter).

## Changed numbers

None in existing tests. Behaviour changes that the village may show (not measured):
- Every refused major action is written to the graph (`Refusal` nodes, actor attributes `last_outcome` and
  `refusal_counts`). Node ids of later nodes shift.
- Prompts for a resident with an outcome carry a `last_outcome` key. The pack now has two more tables, so
  `pack_hash` changes for every prompt.
- `report()` has a `refusals` key.
- A refused `rest` from a healthy resident logs `not_needed`, once per proposal.

## Open questions

1. Should `not_needed` refusals (an unneeded `rest` or a healthy `care`) reach the LLM prompt? They show
   up in the next turn's `last_outcome` now, and a backend that keeps proposing `rest` will see "not needed"
   every turn. Options: keep, drop the logging for `not_needed`, or exempt idle proposals.
2. Should `last_rejections` also be written into `game_persistence.py`? It is derived from the world now,
   so it is not needed for a round trip. Only explicit persistence would require an edit there.
3. Should a non-mapping `enact_plan` plan be refused (Phase 020 open question)?

## Follow-ups

- Phase 031 (retry policy) can read `refusals` and `last_outcome`.
- Name the remaining `not_possible` paths when a village run shows which ones occur.
