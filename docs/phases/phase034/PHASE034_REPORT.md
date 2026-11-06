# Phase 034: intoxication (Tract A)

## Summary

Alcohol is now a physical fact in the body. A drink adds its grams of alcohol to a Body-node
`intoxication` level (0 sober to 1 at full scale), scaled by body size. The level falls linearly each clock
tick. A working skill loses coordination (physical skills) or focus (cognitive skills) in proportion to the
level, through `effective_skill`, so recipe gates, the contest and attempts see it without new code. Above
0.35 movement slows by a factor of 0.5, multiplied with the Phase 024 speed factor. At 0.8 the resident passes
out into the asleep state with reason `passed_out`, and wakes unaided below 0.35.

The world publishes the level and its band. The simple backend reads the level as policy (a bonus toward
social options and a penalty on effortful ones, at drunk or above). The prompt builder gives the band as felt
state. Nothing in the world changes a resident's choices.

- Self-test: 0 errors, 0 warnings.
- Hamlet check: exit 0.
- `generate_seeds.py --check`: exit 0.
- Phase tests: 21 new, all pass.
- Full suite: 1507 passed, 2 skipped, 4 failed. Three failures are the baseline Ocelot import errors
  (`worlds.bigville_ocelot_adapter`). The fourth is an LLM speech reply-validation failure in another tract's
  in-flight work (see Limits). Both are recorded verbatim in `full_suite.log`.
- No existing test was changed.
- The 100-resident village was not run.

## Changes

### Files created

- `packs/bigville/world/intoxication.json`: table `INTOXICATION` with sources in its `_doc`.
- `packs/test_hamlet/world/intoxication.json`: the same table, so the standalone pack loads.
- `tests/test_phase034_intoxication.py`: 21 tests.
- `docs/phases/phase034/`: this report, `full_suite.log`, `selftest.log`, `hamlet_check.log`,
  `generate_seeds_check.log`, `phase034_tests.log`, `git_status_end.txt`.

### Files edited (pack data)

- `packs/bigville/world/items.json`: `alcohol` (grams of ethanol per serving) on `ale` 18.0, `cider` 20.0,
  `mead` 45.0, `beer` 22.0.
- `packs/bigville/world/refusal_reasons.json` and `packs/test_hamlet/world/refusal_reasons.json`: new code
  `passed_out`.
- `packs/bigville/world/lexicon.json`: the `intoxication` quantity is now `published: true`, its edges are the
  table's bands (0, 0.1, 0.35, 0.6; was 0, 0.2, 0.5, 0.8), and `_doc` says the read-off is published. Added
  `LEXICON_PAYLOAD` entry `intoxication -> intoxication`. This file is in Tract B's lexicon area, and the
  edit was needed for `test_phase051_lexicon` to pass once the observation exists.
- `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`: manifest entry `INTOXICATION`, after `HEALTH`.

### Shared-file hunks (for review, each separate from other sessions' edits)

- `domains/world_affordances.py`: after `HEALTH = _PACK["HEALTH"]`, bindings `INTOXICATION` and
  `INTOXICATION_BANDS`. After `feeds()`, new functions `alcohol`, `sober_per_tick`, `intoxication_gain`,
  `intoxication_band`.
- `domains/shared_frames.py`: after `SKILL_LIMITATIONS`, binding `INTOXICATION`. In `effective_skill`, one line
  `delta += _intoxication_effect(person, skill)`. New `_intoxication_effect` before `_limitation_effects`.
- `domains/bigville_entities.py`: new `_check_intoxication` before `_check_illness`. One call added in
  `check_consistency` after `_check_health`.
- `bigville/backends/cheap.py`: an import of `INTOXICATION` after the `simple_band` import. In `__init__`, one
  line `self.intoxication_trace` after `self.model = CANWeightModel()`. `_hook_bonus` now adds
  `_intoxication_bonus`, a new method that follows it. Not touched: `decide`, `_update_goals`, `_time_band`,
  `_choice_key`, `_goal_bonus`, and the policy class.
- `bigville/game.py`: two observation keys, `intoxication` and `intoxication_band`, after `"energy"` in the
  observations builder.
- `bigville/backends/prompts.py`: `_DRINK_FEEL` after `_STANDING_KINDS`. In `PromptBuilder.build`, a
  `public["felt_body"]` line when the band is tipsy or above.
- `bigville/reporting.py`: method `intoxication()` after `improvised_work`. A new key `"intoxication"` in
  `report()`.

### Edits to `worlds/bigville_world.py` (separate from the Phase 048 changes it builds on)

- Body node creation: `intoxication` 0.0.
- `__init__`, after `_tool_tally`: `_intox_ticks` (resident-ticks per band) and `_intox_drunk_grams`.
- `eat`: `self._drink_alcohol(actor, kind)` after `_record_meal`.
- `effective_skill`: passes `intoxication` in the person dict to `E.effective_skill`.
- `_sleep_code`: returns `passed_out` when `asleep` is set with `sleep_kind` 3.
- `_resolve_sleep`: the regain branch skips `passed_out`, so a drink sleep restores no stamina.
- `_run`: calls `_resolve_intoxication()` after `_resolve_sleep()`.
- New section before `sleep_facts`: `intoxication`, `intoxication_band`, `stagger_speed`, `_drink_alcohol`,
  `_pass_out`, `_resolve_intoxication`, `intoxication_tally`.
- `move_actor`: the interval is divided by `stagger_speed`.
- `_actor_options`: a move option's `speed_factor` is multiplied by `stagger_speed`.
- `body_state`: `intoxication` and `intoxication_band`.

### Design

- **Gain.** Widmark: blood alcohol (g/100 ml) = grams / (r x kg x 10), with kg = 70 x body size, r = 0.68.
  Intoxication = blood alcohol / 0.4. One mug of ale (18 g) gives 0.0945 in a size-1 body and 0.135 in a
  size-0.7 body. One mug of mead (45 g) gives 0.236.
- **Sobering.** `sober_per_hour` = 0.015 / 0.4 = 0.0375. `sober_per_tick` is derived in code as
  `sober_per_hour x TIME.minutes_per_tick / 60` = 0.009375 at 15-minute ticks. A mug of ale takes about 10
  ticks (2.5 hours) to clear.
- **Skill.** A physical skill loses 0.3 per unit of intoxication (`coordination_rate`), a cognitive skill 0.25
  (`focus_rate`). A smith at effective 0.75 drops to 0.60 at level 0.5, below the 0.7 floor of
  `forge_plough`.
- **Contest.** Reaction scores fall because the reaction score uses effective fighting skill. In a test, a
  holder at strength 1.0 with fighting at the baseline keeps goods sober against a taker at 0.9. At level 0.3
  he loses them.
- **Movement.** Above `stagger_above` (0.35), `stagger_speed` 0.5 multiplies the speed factor. The walk
  interval in `move_actor` is divided by it. The test walk takes about twice as many turns.
- **Pass-out.** At 0.8 or above, the resident is asleep with `sleep_kind` 3 and reason `passed_out`. Wake comes
  at level below 0.35, after about 48 ticks (12 hours) from 0.8. A drunk sleep restores no stamina.
- **Backend policy.** At 0.35 or above, `_intoxication_bonus` adds +20 to an option that is a social action
  (`transfer`, or any option with a `recipient` key) and subtracts 20 from effortful actions (`work`, `build`,
  `maintain`, `harvest`, `sow`, `water`, `fertilise`, `tend_animals`, `fetch`, `care`). Each bonus is kept in
  `intoxication_trace`, which holds the last 20.
- **Report.** `SimulationReporter.intoxication()`: residents now in each band (plus `passed_out`), resident-ticks
  per band so far, and grams of alcohol drunk so far.

### Changed numbers

None in existing tests. Nothing in the 100-resident village was run, so no village numbers changed. Behaviour
changes in a run would start only when a resident eats a drink.

## Validation

Commands and results:

- `python3 domains/bigville_entities.py`: exit 0. ERRORS (0), WARNINGS (0). Log: `selftest.log`.
- `python3 -m domains.check --pack test_hamlet`: exit 0. Log: `hamlet_check.log`.
- `python3 tools/generate_seeds.py --check`: exit 0, "match pack 'bigville' (31 files)". Log:
  `generate_seeds_check.log`.
- Pack bytes: `python3 tools/export_pack.py --pack bigville --out /tmp/out_bigville` and the same for
  `test_hamlet`, written to temp directories. Diffed against the live files: `intoxication.json`,
  `items.json`, `refusal_reasons.json`, `lexicon.json` and `pack.json` match, and so do the hamlet files. The
  live packs were not exported into.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase034_intoxication.py`: 21 passed.
- `timeout 1500 python3 -m pytest -q -p no:cacheprovider`: 1507 passed, 2 skipped, 4 failed in 539 s. Failures:
  - `test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
    `test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
    `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`:
    `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`. The baseline failures.
  - `test_bigville_game_api.py::test_llm_backend_speech_is_not_rewritten_for_a_legacy_npc_recipient`: the LLM
    reply is rejected with `utterances has no field 'raw'`. Reproduced in a copy of the tree with my two
    `game.py` observation lines removed, so it is not caused by this phase. It sits in another tract's
    uncommitted reply-schema work.

Other notes from the same tree: while the other tract was mid-edit, a full run showed 36 failures in
`test_phase059_autopilot.py`, `test_phase031_llm_backend.py`, `test_bigville_backends.py` and
`test_bigville_game_api.py`, and the self-test showed one AGENT VIEW error from `domains/agent_view.py`. Those
went away when that work settled. The final run is the one above.

## Limits

- **Village.** Not run. Static state of `from_town100()`: 0 ale, 0 cider, 0 mead and 0 beer in stock; 2
  innkeepers (the only `brewer` trade in the cast, JOBS `innkeeper`). All 100 residents hold a wooden mug and
  dipper in their tableware, which I checked by the tableware dict only, not by a serve test. So residents do
  not drink at founding. Drink appears only if a brewer makes it: the recipes `brew_ale`, `brew_cider`,
  `brew_mead` and `brew_beer` need the `brewer` trade (the cast's innkeepers hold it, JOBS `innkeeper`), plus
  their inputs (ale: grain; cider: apple; mead: honey; beer: malt, hops and yeast; each with water and fuel).
  Whether a run brews any was not checked. Once ale is held, a cheap resident eats it only when hungry,
  and only when no better held food scores higher (ale feeds 0.3, bread 1.0, and the meal bonus is 10 x
  `meal_value`).
- **Social options.** The default `SimplePolicy` has `allow_transfers` False, so a transfer is never offered
  unless a scenario enables it. The social bonus therefore reaches only `move` options that carry a recipient,
  which the world publishes only when the resident carries goods that recipient can take. Drunk residents
  will rarely see a social option. The test enables transfers.
- **Reason trace.** The bonus is recorded in `intoxication_trace`. It is not written into `last_choice["reason"]`,
  because that would need an edit to `decide`, which was out of bounds.
- **Practice learning.** `practice_gain` reads raw skill levels, not `effective_skill`. Intoxication does not
  slow practice learning. The brief asked for this, and it is not done. It is an open question below.
- **Mood and focus.** The seed R41 `nu_psych` rule (mood up, focus down) is not implemented. The world does
  not publish mood from alcohol. Focus is covered only through the skill loss.
- **Persistence.** `_intox_ticks` and `_intox_drunk_grams` are plain values, but the untracked
  `bigville/world_persistence.py` does not list them. Checkpoint restore resets the counts. The same gap
  already exists for Phase 048's `_tool_tally`.
- **Sight.** Passing out records no sight event. Residents on the same cell do not see it. The collapse path
  records one, through `_record_sight`.
- **Ocelot and psi_can.** `psi_can.py` and the Ocelot read-off were not changed. `CANWeightModel` does not read
  observations. Ocelot is in another session's untracked work.
- **Sourcing.** The ethanol density (0.789 g/ml), the NHS unit definition (8 g), Widmark's distribution ratio
  (0.68, Watson et al. 1981), and the elimination rate (0.015 g/100 ml/h, Jones 2010) are cited in the table's
  `_doc`. The mug volume, the strengths of cider and mead, the 70 kg reference body, the 0.4 full scale, every
  band edge, the coordination and focus rates, the stagger speed, the pass-out and wake levels, and the policy
  bonuses are APPROX. The NHS and Jones figures are from memory and were not re-fetched in this session.
  Verify them before relying on them.
- **Assets.** `items.json` gained a key, `alcohol`. The asset generators do not read it, and
  `generate_assets.py` was not run. The asset manifest test passes.

## Open questions

1. **Beer is not a drink in the food service.** `beer` has `food_group: drink` and `alcohol`, but
   `FOOD_SERVICE.drink` covers only `ale`, `cider` and `mead` (`DRINK_FOODS`). A resident can eat beer
   bare-handed, with no mug. That gap predates this phase. Should `beer` join `DRINK_FOODS`?
2. **Practice learning under intoxication.** Should `practice_gain` use the intoxicated level, so a drunk
   resident learns less, or is that out of scope? The brief asked for it.
3. **Social options.** Should the simple policy allow transfers by default? Without that, the policy almost never
   fires.
4. **Mood.** Should `nu_psych` (mood up, focus down) be added as a cognition-side read-off, or left out?

## Follow-ups

- Run the village after Tract B's LLM reply work lands, to see whether innkeepers brew and whether cheap
  residents drink.
- Persist `_intox_ticks` and `_intox_drunk_grams` in the persistence layer (or add them to Phase 048's tally
  gap).
