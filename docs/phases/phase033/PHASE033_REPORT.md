# Phase 033: Restraint (Tract A)

## Summary

Restraint is in: `restrain` (hold a resident standing on your cell), `release`, and `struggle`.
It reuses the Phase 029 contest and the Phase 038 contest plumbing. A held resident cannot walk,
and a holder cannot walk until it releases. Both sides pay stamina each tick of the hold by the
take's effort rule. A struggle that wins frees the held resident. Observers on the cell see the
grab. The world attaches no custody, arrest or crime to any of it.

This report completes work begun by a cancelled run. The world logic, pack tables, self-test checks
and the test file from that run were sound and are kept. This run added the affordances for a held
or holding resident, a struggle policy in the cheap backend, and two tests.

Self-test 0 errors, 0 warnings. Full suite: 1800 passed, 8 failed, 3 skipped. Seven of the eight
failures are not caused by this phase: three Ocelot adapter import errors, and four TUI over-HTTP
tests that still fail with this phase's hunks reverted. The eighth, the packet snapshot, is caused by
this phase's three new MAJOR_ACTIONS. See Validation.

## Changes

Files marked (new) did not exist at HEAD. Shared files are listed by hunk, with the function where
each hunk sits. Hunks that belong to other sessions are not listed.

**`worlds/bigville_world.py`** (ten hunks, all restraint):
1. `move_actor`: a held resident or a holder returns its current cell (no step taken).
2. `_actor_options`: publishes `struggle` to a held resident and `release` to a holder. While either
   holds, `move` options are removed, so every published option is legal. Placed after the paused-job loop.
3. `enact_plan`: `restrain`, `release` and `struggle` need no target map rebuild.
4. `_enact_plan`: dispatches the three actions.
5. `major_action` (`move` branch): refuses `restrained` (held) or `holding` (holder).
6. `major_action`: dispatches `restrain` (no reaction), `release` and `struggle`.
7. `tick`: calls `_holds_tick()` after `_terrain_recovery_tick()`.
8. `take_resolve`: routes a pending `restrain` to `restrain_resolve`.
9. `contest_begin`: routes `restrain` to `restrain_begin`.
10. New section "restraint (Phase 033)", after the strike section: `holder_of`, `holding_of`,
    `_set_hold`, `_clear_hold`, `restrain_begin`, `restrain_resolve`, `_release_held`, `struggle`,
    `_holds_tick`. The hold is two string attributes on the actor nodes (`held_by`, `holding`).

**`bigville/game.py`** (one hunk): `_is_contest` also accepts `restrain`, so the step loop asks the
target for a reaction (`_contest_choice`). Other hunks in this file (route_plan, learn_all,
record_action_outcome) are not mine.

**`bigville/backends/cheap.py`** (new hunks; the file had no other uncommitted changes):
- `DeterministicBackend.decide`: a held resident proposes `struggle` before any other choice.
- The options filter also excludes `release`, so the cheap policy never chooses it.
- `react` is unchanged. The Phase 038 reaction (resist, then brace, then yield) already answers
  restraint offers.

**`domains/bigville_entities.py`** (one hunk in `_check_contest`): checks that `restrain`, `release`
and `struggle` have descriptions, and that the eight restraint refusal codes exist. The `fog_check`
hunk further down is not mine.

**`packs/bigville/world/major_actions.json`** and **`packs/test_hamlet/world/major_actions.json`**:
three entries (`restrain`, `release`, `struggle`, kind `contest`, each with a description).

**`packs/bigville/world/refusal_reasons.json`** and **`packs/test_hamlet/world/refusal_reasons.json`**:
eight codes (`restrained`, `holding`, `already_holding`, `already_restrained`, `not_holding`,
`not_restrained`, `slipped`, `pinned`), each with a description.

**`packs/bigville/world/contest.json`**: the `_doc` text gains a RESTRAINT paragraph. No table row
changed. Restraint uses the take's numbers (`base_cost`, `grip`, `technique_weight`,
`decisive_margin`, `trivial_below`, `slot_above`, `practice_minutes`), so no new figure is introduced.

**`tests/test_phase033_restraint.py`** (new): 22 tests. Covered: the acceptance list (a stronger
holder restrains a weaker target; the holder tires and the hold fails on collapse; the target frees
itself by winning a struggle; release lets the target leave; restraining out of reach is refused),
plus: a holder cannot walk and the held cannot walk; an equal grab against a resisting target slips;
a child holding a smith pays the full share and a smith holding a child pays nothing; `evade` voids
the grab; witnesses in sight see it and others do not; a restraint through `enact_plan` takes one
slot; a human target waits and then resumes; a target with no `react` method is logged
`no_react_method`; replay is deterministic; held and holding residents see `struggle` or `release`
and no `move`; the cheap backend struggles free when strong enough; a held resident can still
speak.

**`docs/phases/phase033/`**: this report and logs (see Validation). The earlier logs in this
directory (`check_hamlet.log`, `selftest_bigville.log`, `seeds_check.log`, `death_probe_before.log`,
`death_probe_after.log`, `full_pytest.log`) are from the cancelled run and are kept as history.

### Changed numbers and existing tests

No existing test assertion was edited by this phase. The snapshot fixture
`tests/fixtures/phase054_packet_snapshot.json` was not edited (see Validation). No physical-subsystem
switch was added, so `tests/test_simple_life.py` and `tests/test_scenario_runner.py` are unchanged.
The 100-resident village was not run.

### Design notes

- Reach is the same cell, as for a take and a strike.
- Restraint is not published as an option. Nothing in the default policy restrains anyone, so the
  simple village stays unchanged. A backend that wants to restrain proposes `restrain` directly.
- `struggle` and `release` appear only while a hold stands.
- Stamina per tick: the holder pays for the held resident's grip by the effort rule. The held resident
  pays for the holder's grip, unless it is asleep.
- The hold ends on release, when the holder dies, sleeps or collapses, when either resident dies, when
  the two no longer share a cell, or when the held resident wins a struggle.

## Validation

Commands are run from `/home/matt/ozmadev/bigville`.

| Command | Result |
|---|---|
| `python3 domains/bigville_entities.py` (`docs/phases/phase033/selftest_bigville_033.log`) | exit 0; ERRORS (0), WARNINGS (0) |
| `python3 -m domains.check --pack test_hamlet` (`check_hamlet_033.log`) | exit 0; ERRORS (0), WARNINGS (0) |
| `python3 tools/generate_seeds.py --check` (`seeds_check_033.log`) | exit 0; seeds match pack `bigville` (31 files) |
| `PYTHONPATH=. python3 /tmp/death_probe.py 192` (`death_probe_after_033.log`, run after all world and backend edits) | 192 turns, 0 deaths |
| `python3 -m pytest -q -p no:cacheprovider tests/test_phase033_restraint.py` (`restraint_tests_033.log`) | 22 passed |
| `timeout 1800 python3 -m pytest -q -p no:cacheprovider -rfE` (`full_pytest_033.log`) | 8 failed, 1800 passed, 3 skipped, 1640 s |

The full-suite run started before the last test (`test_a_held_resident_can_still_speak_to_the_holder`)
was added. That test passed when run alone with the restraint file. The full suite was not run again.
The run took 27 minutes, longer than the 1500 s budget in the brief. It shares the machine with
another session's suite, so the timeout is not a result.

The eight failures:

1. `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`
2. `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`
3. `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`

   All three fail with `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`. This is
   the baseline failure the supervisor described. These are another session's test files.

4. `tests/test_phase054_llm_prompt.py::test_the_packet_matches_the_snapshot_for_a_fixed_view`
   This phase's cause. The `system` section of the packet grows from 4930 to 5673 characters. In a
   copy of the tree I restored HEAD's `major_actions.json` and the test passed. With this phase's
   `major_actions.json` and HEAD's `refusal_reasons.json` it failed. So the three new MAJOR_ACTIONS
   entries cause it, and the eight refusal codes do not. The fixture is not edited, as the brief requires.
   The fixture needs regenerating by its owner.

5. to 8. `tests/test_phase057_tui.py::test_over_http_a_menu_row_is_bound_by_the_server_and_the_world_enacts_it`,
   `::test_over_http_walking_to_a_known_place_sends_the_rows_destination`,
   `::test_over_http_a_reaction_is_delivered_to_the_holder`, and
   `::test_the_server_refuses_a_bad_reply_and_a_reaction_nobody_is_waiting_for`.
   These are not from this phase. In a copy of the tree with every hunk of mine reverted (the
   restraint hunks in `worlds/bigville_world.py`, `bigville/game.py`, `domains/bigville_entities.py` and
   `cheap.py`, and the restraint pack entries), the same four tests still fail. The failures are in the
   server and agent-view work (intensity validation, menu rows) that the other session has not committed.

Also seen once: `tests/test_phase013a_packs.py::test_exported_files_compile_back_to_the_same_tables`
failed on `VIEW_WORDS` in an early run and passed in the full run. The lexicon was changing under the
other session at that time. It is not from this phase's files.

## Limits

- Group restraint (several residents holding one) is out of scope (Phase 047).
- Doors and confinement (Phase 039) are out of scope. Nothing here blocks a path.
- The cheap backend never restrains. It struggles when held, but it never releases a hold it made.
  A cheap holder keeps the hold until the hold breaks by collapse, sleep, or the holder and target
  parting. A release policy is a backend choice and belongs to a later phase.
- The restraint's physical event for observers is recorded with the action label `contest`
  (`game._record_contest_witnesses` labels only `strike` and `contest`). Changing it is a small
  follow-up.
- The Ocelot and LLM backends have no restraint policy and no reaction adapter. They can still use the
  `restrain`, `release` and `struggle` actions.

## Open questions

- Should the packet snapshot be regenerated for the three new MAJOR_ACTIONS? The owner of
  `phase054_packet_snapshot.json` must decide. The change is the 743-character growth of the
  `system` section.
- Should the cheap backend get a release policy? Without one, a restrained cheap resident can only
  be held or freed by the physics, not by its own choice.
- Should the speech and witness labels for restraint be separate from `contest`?

## Sources

No new distribution, rate, or real-world figure is introduced. Every number used is in `CONTEST`
(APPROX, from Phase 029 and 038).
