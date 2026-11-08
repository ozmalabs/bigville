# Phase 063: visible condition (marks)

Tract A. Status: implemented and validated; not committed (the supervisor commits).

## Summary

Each resident now carries nine surface marks: dirt, coal dust (`soot`), flour dust, blood, mud, sweat,
wetness, soiled clothes, and visible injury. Work and events raise them, and time, rain, washing, and a
fresh garment lower them. The world publishes the marks and what an observer could see, and it draws no
conclusion. No code path in the simple village reads the marks, so the simple village's decisions and
state are unchanged. The state digest without mark attributes matches the pre-change tree over 192 turns.

## Changes

New files:
- `packs/bigville/world/marks.json`: tables `MARKS` (nine kinds), `MARK_RULES`, `MARK_HARM` (one row per
  HEALTH cause), `MARK_EVENTS` (butchery). All numbers APPROX, stated in the file's `_doc`.
- `packs/test_hamlet/world/marks.json`: the same tables for the standalone hamlet, with `MARKS` and
  `MARK_EVENTS` empty and `MARK_HARM` an empty row per cause. `MARK_RULES` has the bigville values.
- `tests/test_phase063_marks.py`: 18 tests (see Validation).
- `docs/phases/phase063/`: this report, self-test and suite logs, digests, `compare60.py`.

Changed data:
- `packs/bigville/world/recipes.json`: a `marks` row on 10 recipes (`burn_charcoal`, `smelt_iron`,
  `grind_flour`, `grind_rye`, `dig_ore`, `dig_grave`, `tan_hide`, `split_firewood`, `saw_planks`,
  `make_compost`). The file held no other hunks at the start of the phase.
- `packs/bigville/world/shocks.json`: a `marks` row on `drought`, `flood`, `fire`.
- `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`: four manifest rows (`MARKS`, `MARK_RULES`,
  `MARK_HARM`, `MARK_EVENTS`) after `DAYNIGHT_MAJOR_ACTIONS`. Both files also carry another session's
  uncommitted reformatting, so `git diff` on them is mostly not mine.
- `bigville/seeds/gen_recipes.json`: regenerated with `tools/generate_seeds.py` (the recipe rows changed).
  `--check` passes. `bigville/seeds/bigville_actor_decision.json` was not changed by me.

Code:
- `worlds/bigville_world.py`, my hunks:
  - new block before `harm()`: `mark_level`, `marks`, `observable_marks`, `_set_mark`, `_add_marks`,
    `_change_clothes_marks`, `_marks_period`, `wash`, and the class attribute `_WET_MARK`;
  - `_resolve_jobs`: a completed job adds its recipe's `marks` to the worker;
  - `_resolve_period_effects`: `_marks_period()` once per period, before the ecology block;
  - `wear`: `_change_clothes_marks` after the garment is attached;
  - `add_shock`: the shock's `marks` fall on every living resident at onset;
  - `_drop_health`: `MARK_HARM[cause]` times the health lost, before any death is recorded;
  - `butcher`: `MARK_EVENTS["butcher"]`.
- `domains/bigville_entities.py`: `_check_marks` (before `_check_intoxication`) and its call after
  `_check_health`.
- `domains/world_affordances.py`: four binding lines after `DAYNIGHT_LAMPS` (`MARKS`, `MARK_RULES`,
  `MARK_HARM`, `MARK_EVENTS`). This file is outside the listed write scope; the bindings are needed so that
  `E.MARKS` exists.

Design:
- A mark's level is the float attribute `mark_<kind>` on the actor node, from 0 to `max_level` (1.0). It is
  absent when zero, so a clean resident keeps no new attributes.
- Gains: a recipe's `marks` on completion; `MARK_HARM[cause]` per point of health lost (after life-stage
  fragility); `MARK_EVENTS` per occurrence; `SHOCKS[...].marks` at onset.
- Falls: `decay` per period for every mark; `rain_wash` per period times rain exposure for washable marks,
  where exposure is the town's `wet` less the resident's `rain_cover`; `clothes_change_drop` on putting on a
  garment; `wash` takes `wash_drop` of the level for washable marks.
- Rain adds `wet_gain` times exposure to `wetness`.
- Visibility: a mark is visible when the observer is within `see_range` cells, the light is at least
  `see_light`, and the level is at least `visible_level`. Each row carries `notice_skill` (only `injury`
  sets one: `medicine`). `observable_marks(actor, distance, light=1.0)` returns these rows.
- `wash(actor)`: needs store access (as `water` does) and `wash_water` units of store water. It takes the
  resident's turn, uses the same claim as other major actions, and returns False when refused.
- The self-test checks: each kind's fields and gates (`notice_skill` must be a SKILLS name); every HEALTH
  cause has a `MARK_HARM` row (`{}` when it leaves no mark); every kind named by a recipe, shock, or event
  is a `MARKS` kind; a kind with no source is a warning (wetness is exempt; rain raises it).

## Validation

Commands and results (all run in `/home/matt/ozmadev/bigville`):

- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0). Log: `selftest.log`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, ERRORS (0), WARNINGS (0). Log: `selftest_hamlet.log`.
- `python3 tools/generate_seeds.py --check`: "match pack 'bigville' (31 files)".
- Export layout: `tools/export_pack.py --pack bigville|test_hamlet --out /tmp/...` (a temp directory only).
  My files match byte for byte: `world/marks.json`, `world/recipes.json`, `world/shocks.json`, `pack.json`
  (both packs). `tests/test_phase013a_packs.py` also passes.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase063_marks.py`: 18 passed.
- Related tests (`test_phase058_persona`, `test_phase013a_packs`, `test_phase054_llm_prompt`,
  `test_phase037_health_routes`, `test_phase038_strikes`, `test_phase043_care`, `test_phase048_tool_fitness`):
  162 passed.
- Death probe `PYTHONPATH=. python3 /tmp/death_probe.py 192`: deaths 0, first death none
  (`death_probe_192.log`).
- Digest of the town100 simple village (`compare60.py`, seed 305017). The digest covers the export, actor
  attributes without `mark_*`, stock, and deaths. Pre-change copy: `/tmp/bigville_base`, a snapshot of the
  working tree before my first edit.
  - 60 turns: digests identical (`f334f71e...`). No resident has a mark: no marked recipe completed in
    60 turns.
  - 192 turns: digests identical (`e04f5787...`). 100 residents carry marks: dirt 2.08 in total, wetness 50.0
    (0.5 each, from one rain period), sweat 0.0 (decayed). The digest rules out any change to the simple run
    other than marks.
- Full suite, `timeout 3000 python3 -m pytest -q -p no:cacheprovider -n 4` (final code, log in
  `full_suite.log`): 7 failed, 2196 passed, 6 skipped in 693 s.
  - `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
    `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
    `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`:
    `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`, raised at import, before any
    world code runs. These are the other session's untracked files and the known baseline failure.
  - Four `tests/test_phase057_tui.py` HTTP tests (`test_over_http_a_menu_row_is_bound...`,
    `..._walking_to_a_known_place...`, `..._a_reaction_is_delivered...`,
    `test_the_server_refuses_a_bad_reply...`). They fail the same way on the pre-change copy
    (`/tmp/bigville_base`: 4 failed, 44 passed, 3 skipped for that file group). One example:
    `assert (200 == 400)` for an invalid intensity. Not related to marks.

## Changed numbers in existing tests

None. No existing assertion was edited.

## Limits

- The marks are not in `export_state()`, the agent view, or the prompt packet. They are reached through
  `marks()` and `observable_marks()`. Phase 062 is the consumer.
- No mechanic reads a mark. Marks do not change effort, health, fitness, or any decision.
- Washing is not a resident action yet (see Open questions).
- The 60-turn run changed by no marks at all. The 192-turn run exercised charcoal, digging, splitting,
  and one rain period. Other paths (violence, butchery, shocks, the `wash` act) are covered only by tests.
- All levels, rates, and ranges are APPROX design choices. They are not measured.
- Shocks mark every living resident at onset, indoors or out. The rule has no indoor or outdoor test.
- The lexicon words for marks are the `label` fields in `MARKS`. I did not add rows to `lexicon.json`
  (Tract B's file).
- `falling` is covered by `injure()`, which harms through `injury`. No separate fall event exists.

## Open questions

1. **Should residents be able to wash?** Registering `wash` in `packs/bigville/world/major_actions.json` makes it
   reachable, but the Phase 054 packet prints every major action, so
   `tests/fixtures/phase054_packet_snapshot.json` would change. That fixture is Tract B's. I did not edit it.
   I left `wash` as a world method with no action name.
2. Should the shock marks apply only to residents outdoors?
3. Is `soiled_clothes` the right name for the clothes mark, and should torn clothes be a separate mark?

## Follow-ups

- Phase 062 reads `observable_marks()` as the evidence for its upper tiers, with the wording from the
  lexicon.
- Phase 069 writes `observable()` as the same ledger; these marks are its visible side.
