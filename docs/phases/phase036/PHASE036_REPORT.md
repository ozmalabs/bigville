# Phase 036: alcohol's longer effects (Tract A)

## Summary

The longer effects of drink are in place behind `physical_subsystems.alcohol_aftereffects`, which is off by default.
With the switch on:

- **Tolerance.** Each drink adds `tolerance_per_drink` (0.1) to a body `tolerance` (capped at 1.0). A tolerant body
  takes `1 - tolerance_relief x tolerance` of the dose. Sober ticks (intoxication below the tipsy band) fade it.
- **Dependence, craving, withdrawal.** A body that reaches `dependence_tolerance` (0.5) becomes dependent, and the flag
  stays. A dependent body's craving rises on sober ticks and falls by `craving_relief_per_drink` on each drink. At
  craving 0.3 or more, withdrawal lowers working skill (by `withdrawal_skill` x craving) and stamina capacity (by
  `withdrawal_stamina` x craving).
- **Hangover.** A drinking episode whose peak reaches `hangover_above` (0.6) leaves a hangover when the level falls below
  the tipsy band. It lasts `hangover_ticks` (96 clock ticks). It lowers working skill by 10 per cent and halves the stamina
  a sleeper regains.
- **Poisoning.** Above `poison_above` (0.7), each clock tick does acute harm with cause `intoxication`, scaled from 0 at
  0.7 to `poison_harm` (0.1) at full scale. Pass-out is applied first within the same tick.
- **Speech clarity.** An utterance carries `clarity` = 1 - the speaker's intoxication. Each listener's copy also loses up to
  `clarity_distance_loss` (0.5) at the edge of the hearing radius. The text is not changed.
- **Coping policy.** `SimplePolicy.coping_drink` (default False) gives a drink option `coping_bonus` (20) when mood is
  below `distress_below` (0.35) or craving is at the withdrawal line. It reads the new observation `aftereffects`.

With the switch off, the world, the observations, the body state, the speech records and the reporter output are as before.
Phase 034 (dose, sobering, pass-out, stagger, skill loss) is unchanged.

All new figures are APPROX. No source was consulted for them.

## Changes

### Pack data

- `packs/bigville/world/intoxication.json`: 19 keys added to the `INTOXICATION` table (the aftereffect figures), and
  `_doc` extended with a paragraph that gives each key's meaning and status. No manifest entry was needed, so
  `packs/bigville/pack.json` is untouched.
- `packs/test_hamlet/world/intoxication.json`: the same table (the hamlet copies the bigville table, as in Phase 034).

### `domains/bigville_entities.py` (new hunks only; file was clean at start)

- New `_check_aftereffects` after `_check_intoxication`: all 19 keys present; rates and shares in [0, 1];
  `0 < dependence_tolerance <= tolerance_max <= 1`; `tipsy < hangover_above <= 1`; `stupefied <= poison_above <= 1`;
  `hangover_ticks` a whole number. INFO line: the hangover in hours and the dependence threshold.
- One call added in `check_consistency`, after `_check_intoxication`.

### `worlds/bigville_world.py` (17 hunks are this phase's; two uncommitted hunks belong to another session, the `"food"`
flag in `_actor_options` (~line 7688) and `resident_plan_from_context` (~line 8061), and were not touched)

- `PHYSICAL_SUBSYSTEM_DEFAULTS`: `alcohol_aftereffects: False`.
- Body node creation: `tolerance`, `craving`, `dependent`, `hangover_ticks`, `episode_peak` (all 0.0).
- `speak`: when on, a per-listener `clarity` in `deliveries` and an utterance `clarity`.
- New `speech_clarity` (after `speech_radius`).
- `heard_utterances`: adds `clarity` to a record only when the delivery carries one.
- `effective_skill`: multiplied by `_aftereffect_skill_factor` (1.0 when off).
- `effective_stamina`: multiplied by `_withdrawal_stamina_factor` (1.0 when off).
- `_resolve_sleep`: the regain is multiplied by `_hangover_recovery_factor` (1.0 when off).
- `_drink_alcohol`: when on, dose scaling, tolerance gain, dependence flag and craving relief.
- `_resolve_intoxication`: calls `_alcohol_tick` when on; poisoning after the pass-out check, on clock ticks only.
- New section "alcohol aftereffects (Phase 036)": `_aftereffects_on`, `_alcohol_tick`, `_withdrawing`,
  `_withdrawal_share`, `_hangover_on`, `aftereffects` (read-offs), `_aftereffect_skill_factor`,
  `_withdrawal_stamina_factor`, `_hangover_recovery_factor`.
- `body_state`: `**self.aftereffects(actor)` at the end. Empty dict when off, so the keys are unchanged.

State is held in Body node attributes (plain floats) and in the speech delivery records. No Python attributes were added to
the world, so the supervisor's persistence rule (plain values or graph nodes only) holds. The untracked `world_persistence.py`
was not read or changed, so whether it saves the new Body attributes is not checked here.

### `bigville/backends/cheap.py` (file was clean at start; all hunks are this phase)

- Import `alcohol` from `domains.world_affordances` as `_alcohol_grams`.
- `SimplePolicy.coping_drink: bool = False`, with a comment, after `improvise`.
- `_hook_bonus` adds `self._coping_bonus(context, option)` to the existing `_intoxication_bonus` term. One line changed.
- New method `_coping_bonus` after `_hook_bonus`.
- `decide`, `_update_goals`, `_time_band`, `_choice_key`, `_goal_bonus` and the policy class's other fields are not touched.

### `bigville/game.py` (my hunk only, around line 560)

- Observations: `aftereffects` (the world's dict) when non-empty, i.e. with the switch on. Tract B's hunk
  (`record_action_outcome`, around line 727) is separate and not touched.

### `bigville/reporting.py` (file was clean at start)

- `SimulationReporter.aftereffects()`: residents alive with the switch on, dependent, withdrawing, hungover, and mean
  tolerance and craving. All zero or empty when off.

### Tests

- New `tests/test_phase036_alcohol_aftereffects.py`: 21 tests (switch and defaults, tolerance, dependence and withdrawal,
  hangover, poisoning and pass-out order, clarity, the coping policy, the reporter). All pass.
- `tests/test_simple_life.py` (`test_physical_subsystems_default_on_and_reject_invalid_configuration`): the expected dict
  gains `"alcohol_aftereffects": False`. Reason: a new physical-subsystem switch (the brief's rule).
- `tests/test_scenario_runner.py` (the `physical_subsystems` assertion of the first scenario): the same key added. Same reason.
- No existing assertion was changed or removed.

### Not changed

- `domains/world_affordances.py`: no code change. The table is read through the existing `INTOXICATION` binding.
- `bigville/backends/prompts.py`: not changed. `PromptBuilder` does not note low clarity (the brief said "may").
- `tools/export_pack.py`: run only into `/tmp/out036`, never on the live packs. The exported `intoxication.json` files
  match the live files byte for byte, for both packs.
- No MAJOR_ACTION or FREE_ACTION was added, so `tests/fixtures/phase054_packet_snapshot.json` is unchanged.
- The `cheap.py` goal and choice methods are not restructured.

## Validation

Run in `/home/matt/ozmadev/bigville` with the shared tree in its state at the start of this phase plus my edits.

| Command | Result | Log |
|---|---|---|
| `python3 domains/bigville_entities.py` | exit 0; ERRORS (0); WARNINGS (0) | `selftest.log` |
| `python3 -m domains.check --pack test_hamlet` | exit 0 | `hamlet_check.log` |
| `python3 tools/generate_seeds.py --check` | exit 0; "match pack 'bigville' (31 files)" | `generate_seeds_check.log` |
| `python3 tools/export_pack.py --pack bigville --out /tmp/out036/bigville` and `--pack test_hamlet` | exit 0; both `intoxication.json` identical to the live files | (not logged) |
| `python3 -m pytest -q -p no:cacheprovider tests/test_phase036_alcohol_aftereffects.py` | 21 passed | `phase036_tests.log` |
| Nearby set: `test_phase034_intoxication.py`, `test_phase037_health_routes.py`, `test_phase036_alcohol_aftereffects.py`, `test_simple_life.py`, `test_scenario_runner.py`, `test_phase013a_packs.py`, `test_phase058_persona.py`, `test_phase051_lexicon.py` | 332 passed | `near_tests.log` |
| `PYTHONPATH=. python3 /tmp/death_probe.py 192`, before the change (in a copy of the pre-change tree) | 192 turns, 0 deaths | `death_probe_192_before.log` |
| Same probe, after the change | 192 turns, 0 deaths | `death_probe_192_after.log` |
| `timeout 3600 python3 -m pytest -q -p no:cacheprovider -rfE` (full suite, changed tree) | 8 failed, 1750 passed, 3 skipped (1621 s) | `full_suite.log` |

The 8 failures:

- 3 are the known baseline failures (`worlds.bigville_ocelot_adapter` not found):
  `test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
  `test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
  `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`.
- 4 are `tests/test_phase057_tui.py` over-HTTP tests (`test_over_http_a_menu_row_is_bound_by_the_server_and_the_world_enacts_it`,
  `test_over_http_walking_to_a_known_place_sends_the_rows_destination`, `test_over_http_a_reaction_is_delivered_to_the_holder`,
  `test_the_server_refuses_a_bad_reply_and_a_reaction_nobody_is_waiting_for`). The same 4 fail on the pre-change copy
  (`/tmp/base036`, which has the other tract's uncommitted server work). The first is an assertion `200 == 400` on an
  intensity reply. Not caused by this phase.
- 1 is `tests/test_phase055_concurrency.py::test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical`.
  It passes when run alone on the changed tree. It is a timing test and failed under load from other sessions' suites
  running at the same time. Not rerun on the pre-change copy.

I attempted a full pre-change baseline run, but my own `timeout 1500` stopped it at about 91 per cent, with no summary. The
numbers above are therefore not compared against a complete baseline count. The new tests add 21 to the count.

The 100-resident village was not run. The 192-period probe was run, both before and after, and gave 0 deaths each time.
With the switch off (the default) and no drink in the founding village, the village is unchanged by construction.

## Limits

- **The switch is off, so nothing here runs in the default village.** Whether a village run with the switch on, and drink
  brewed, shows the intended pattern was not checked. Phase 034 found no drink at founding (0 ale, cider, mead or beer in
  stock in the 100-resident cast).
- **Figures are APPROX.** Tolerance, craving, withdrawal, hangover, poisoning, clarity and the coping numbers are model
  choices. No source was consulted. The Phase 034 figures (Widmark, sobering rate) keep their existing citations.
- **The lethal dose is a test result, not a calibration.** Five mugs of mead (45 g each) kill a 70 kg adult at health 1.0 in
  the test. An ordinary dose (one ale) does no poison harm.
- **Craving never falls without a drink.** The brief says craving rises while sober, so a dependent resident who abstains
  stays in withdrawal until they drink. No abstinence fade was added.
- **Dependence never clears.** Once tolerance reaches `dependence_tolerance`, the flag stays set.
- **Speech clarity is not used by any listener.** Cognition may read `clarity` from `heard_utterances`. The prompt builder
  does not note it. Phase 054's packet is unchanged.
- **Practice learning is still unaffected by intoxication**, as in Phase 034.
- **Coping policy is untested in a village run.** It is covered only by unit tests on `_coping_bonus`. It reads mood and craving
  from the `aftereffects` observation, which exists only with the switch on. Mood is not an observation otherwise.
- **Persistence not checked** (see Changes).

## Open questions

1. Should craving fall over time without drink (abstinence), or stay as the brief describes?
2. Should dependence ever clear, or should it stay permanent as built?
3. Are the poison and hangover figures acceptable for a village with brewing turned on? They have not been run.
4. Should `PromptBuilder` note low clarity, as the brief allowed, and should a listener's cognition treat low clarity
   differently? Both are cognition-side and not done here.
5. Should the coping policy be on in any scenario, or stay off?

## Follow-ups

- Run a village with the switch on and brewing enabled to see whether dependence, hangover and poisoning appear.
- Check `bigville/world_persistence.py` (untracked, another session's) for the new Body attributes.
- Pre-existing failures to take up with their owners: the three Ocelot import failures, the four TUI over-HTTP failures
  (Tract B's in-flight server work), and the load-sensitive concurrency timing test.
