# Phase 059: autopilot and momentum

## Summary

An LLM resident now owns a `DeterministicBackend` (the simple backend) for the same character. The
autopilot decides every turn the resident is not on a model plan. The model is consulted only when a
consult trigger fires: an interrupt, a routine boundary, a check-in after `max_quiet_ticks`, an
autopilot with nothing to do, a reaction, or an event the pack names. A consult that cannot finish (a
provider error, an invalid reply after one repair, a call or spend cap) falls back to the autopilot's
action and is counted by cause. `waiting: true` from a model is rejected. A reply with no
`major_action` carries on as usual. The action `wait` is the explicit idle.

Fake provider only. No network, no `.env`, no commits. Self-test 0 errors, 0 warnings for both packs.
Full suite: 1451 passed, 2 skipped, 3 failed. The 3 failures are the Ocelot adapter tests and fail
the same way on a clean HEAD (see Validation). The simple backend alone is unchanged: a 60-turn
town100 run matches a clean HEAD run on every field.

## Changes

### Created

- `bigville/backends/autopilot.py`: `ConsultGate` (the trigger rules and per-resident state) and
  `CallBudget` (caps on calls per resident per day, and on spend from a provider's `last_cost`).
- `domains/autopilot.py`: pack-driven numbers and pure rules. `routine_strength`, `max_quiet_ticks`,
  `boundary_consult_chance`, `habit_roll`, `usual_block`, `usual_words`, and the trigger names `TRIGGERS`.
- `domains/autopilot_check.py`: `check_autopilot`, the self-test check.
- `packs/bigville/world/autopilot.json` and `packs/test_hamlet/world/autopilot.json`: table `AUTOPILOT`
  (routine strength terms, quiet ticks, boundary share, consult triggers, thresholds, refusal repeats,
  calls per day). Both files were written by hand and then replaced with the exporter's output
  (`tools/export_pack.py --out` into a scratch directory; only `world/autopilot.json` was copied back).
- `tests/test_phase059_autopilot.py`: 34 tests, fake provider, one group per acceptance item.
- `docs/phases/phase059/`: this report, `behaviour_head.json`, `behaviour_mine.json`, the measurement
  logs, `log_full_suite.txt`.

### Rewritten (Phase 031 file, owned by this tract)

- `bigville/backends/llm.py`. Phase 031's provider call, validation and single repair are kept. Added:
  the autopilot, the consult path, the fallbacks by cause, carry-on and wait, the `waiting: true`
  rejection, `react` consults, `note_turn` for plan turns, and the counts. `autopilot=False` gives the
  Phase 031 behaviour (consult every turn, idle on failure).

### Edited tests (Phase 031 file, this tract)

`tests/test_phase031_llm_backend.py`. Every change is listed here.

1. `test_repeated_invalid_output_returns_an_idle_response_and_counts_a_failure`: the backend is built with
   `autopilot=False`. Reason: its assertions are the Phase 031 idle turn. With the autopilot on, the
   response is the autopilot's action (the context affords a move).
2. `test_idle_fallback_in_a_game_turn_advances_the_world_and_never_raises`: `autopilot=False`, same reason.
3. `test_provider_exception_is_not_repaired_counted_and_does_not_reach_the_world`: `autopilot=False`, same reason.
4. `test_provider_error_text_that_looks_like_a_credential_is_dropped`: `autopilot=False`, same reason.
5. `test_a_bug_in_the_prompt_path_is_counted_not_raised`: `autopilot=False`, same reason.
6. `test_llm_report_ignores_backends_without_llm_counts`: the expected total dict gained the keys the
   report now carries (`autopilot_turns`, `carry_ons`, `waits`, `deviations`, `turns`,
   `fallbacks_by_cause`, `consults_by_reason`, `share_consulted`, `share_autopilot`), all zero, empty or
   `None`. Reason: the report shape grew. The assertion is still an exact equality.

No assertion was weakened or removed. Phase 031's `waiting` validator test still passes (`waiting: false`
is accepted; `waiting: "no"` is still an error).

### Shared-file hunks (additive; anchors are HEAD lines)

Built against HEAD (commit 387f46b). The supervisor can rebuild each hunk from its anchor.

1. `bigville/game.py`, `BigvilleGame.step()`, two hunks.
   - Hunk A. Anchor: the unchanged line `            if active is not None and reason is None:`. Insert
     after it, before `                response = self._continuation_response(active)`:
     ```
                 # Phase 059: a model plan holds this turn; an LLM resident's autopilot still sees it.
                 note_turn = getattr(backend, "note_turn", None)
                 if callable(note_turn):
                     note_turn(self._context(actor))
     ```
   - Hunk B. Anchor: the unchanged line `                context = self._context(actor)` (HEAD line 816,
     the only such line in `game.py`). Insert after it, before `                response = backend.decide(context)`:
     ```
                 if reason is not None:
                     # Phase 059: the interrupt reason, so a backend can tell why it is asked again.
                     context.backend_state["continuation_interrupted"] = reason
     ```
2. `bigville/reporting.py`, two hunks.
   - Hunk A. Anchor: the unchanged blank line before `LLM_TOTAL_KEYS = (`. Replace the second line of that
     tuple, `                  "provider_errors", "invalid_outputs")`, with
     `                  "provider_errors", "invalid_outputs", "autopilot_turns", "carry_ons", "waits", "deviations")`.
   - Hunk B. Anchor: the unchanged blank lines before `def llm_report(`. Replace the whole `llm_report`
     function, up to the blank lines before `def game_report(`, with the function in the working tree
     (`def llm_report` to `def game_report` in `bigville/reporting.py`). It adds the autopilot totals,
     `turns`, `fallbacks_by_cause`, `consults_by_reason` and the two shares. `game_report` is unchanged.
3. `domains/bigville_entities.py`, two lines. Anchor: the unchanged line
   `    check_persona(_WORLD_PACK.path, errors, warnings, info)`. Insert after it:
   ```
       from domains.autopilot_check import check_autopilot  # Phase 059: the autopilot's consult rules
       check_autopilot(_WORLD_PACK.path, errors, warnings, info)
   ```
4. `packs/bigville/pack.json` and `packs/test_hamlet/pack.json`, the same four-line entry in each. Anchor:
   the HEAD entry `      "file": "world/persona.json"` belongs to the object `"name": "RELATIONSHIP_SEEDING"`,
   which closes with `    },`. Insert after that closing `    },`, before the object whose name is
   `AGENT_VIEW_WHITELIST`:
   ```
       {
         "name": "AUTOPILOT",
         "file": "world/autopilot.json"
       },
   ```
   Note on the working tree: another session's uncommitted change rewrote both manifests as one-line
   objects. In the working tree I inserted the entry as one line
   (`    {"name": "AUTOPILOT", "file": "world/autopilot.json"},`) after the one-line RELATIONSHIP_SEEDING
   entry. Both forms are valid JSON, and the export test passes on both. It does not check the manifest's
   layout.

Not edited, although the brief's write scope named some of them: `bigville/backends/cheap.py` (the
would-be choice is the autopilot's `decide` output, and the routine comes from `domains/persona.py`),
`bigville/backends/protocol.py` (the "as usual" and wait semantics live in `llm.py`), `bigville/api.py`,
`prompts.py`, `worlds/bigville_world.py`, `bigville/backends/ocelot.py`.

## Validation

Every command ran in `/home/matt/ozmadev/bigville` unless noted.

- `python3 domains/bigville_entities.py`: exit 0. `ERRORS (0)`, `WARNINGS (0)`. Info line:
  `AUTOPILOT (bigville): all autopilot checks pass (11 consult triggers, quiet ticks 24 to 192)`.
- `python3 -m domains.check --pack test_hamlet`: exit 0. `ERRORS (0)`, `WARNINGS (0)`. Info line:
  `AUTOPILOT (test_hamlet): all autopilot checks pass (11 consult triggers, quiet ticks 12 to 48)`.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase059_autopilot.py tests/test_phase031_llm_backend.py tests/test_phase013a_packs.py tests/test_phase013b_data_pack.py`: **77 passed**
  (34 from Phase 059, 26 from Phase 031, and 17 from the two pack test files, which include the export test).
  Two runs on the live tree gave 77 passed each. The live tree is shared, and in one window of about two minutes
  (around 19:12 to 19:13) four runs of these files failed 1 to 16 tests, all with
  `AttributeError: 'BigvilleWorld' object has no attribute 'intoxication'`. That is Tract A's uncommitted Phase 034 work
  in `worlds/bigville_world.py`, which was being edited at the time. Later live runs passed, and six fixed hash seeds
  passed on `test_phase013b_data_pack.py`. The same four files passed 77 of 77 in four runs with hash seeds 1 to 4 in
  the clean "mine" tree (HEAD plus this phase's hunks).
- Full suite, `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (log `log_full_suite.txt`):
  **1451 passed, 2 skipped, 3 failed** in 520.6 s. The failures:
  - `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`
  - `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`
  - `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`

  All three raise `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`. Attribution:
  the sibling checkout `/home/matt/ozmadev/ocelot` exists in the live parent directory, so the tests
  take the import path. In a clean copy of HEAD (`git archive HEAD`) with the untracked support modules
  and a symlink to that checkout placed beside it, the same three tests fail with the same error. The
  same happens in the copy with my hunks added. The failure is therefore not caused by this phase.
  The Phase 031 and Phase 058 reports record the same three failures.
- Behaviour, simple backend (`PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label ... --turns 60 --out ...`,
  town100, seed 305000, `--seeding default`, 60 turns). Two trees were compared:
  - `head`: a clean `git archive HEAD` copy.
  - `mine`: that copy with only this phase's hunks and new files applied (the anchors above).

  Every field is identical: action counts (`eat` 5, `move` 3333, `none` 1050, `rest` 1549, `sleep` 48,
  `work` 15), 300 utterances, 0 handovers, 0 deaths, the hunger trace for all 60 turns, and the digests of
  all 100 residents. Files: `behaviour_head.json`, `behaviour_mine.json`, `log_measure_head.txt`,
  `log_measure_mine.txt`. The 200-turn run of Phase 058 was not repeated.
- Fake-provider runs (in the tests, not a town run):
  - One LLM resident in `norms_property_sharing` (autonomous), 200 ticks, a provider that always carries on:
    19 calls. Reasons: `spoken_to` 18, `nothing_to_do` 1. 181 autopilot turns.
  - One resident, `routine_strength` 0.0 (quiet span 24 ticks), 200 ticks: 15 calls (`check_in` 3,
    `routine_boundary` 12). One with `routine_strength` 1.0 (quiet span 192 ticks): 2 calls.
- Not run: the 100-resident LLM town, and any live provider. The brief did not ask for either.

## Behaviour

- **Autopilot every turn.** `decide` runs the autopilot first on every turn the game asks. The
  counterfactual is therefore the autopilot's `decide` output, on every turn, not only on consulted ones.
  A consult records `would_be` and whether the accepted reply `departs` from it.
- **Triggers.** A consult fires for: a hunger or energy crossing (the threshold values from the pack, watched
  by the backend itself, and the game's own interrupt reasons); a tie in view (a nearby resident whose
  `tie_strength` or `band_code` is positive); speech addressed to the resident; a failed attempt (`task_failed`),
  or the same failure reason twice (`refusal_repeats`); a physical event whose target is the resident
  (`world_event`); a routine boundary, when a fixed hash of (resident, day, block) falls below
  `1 - routine_strength`; the first turn and every quiet span (`check_in`); an idle autopilot, once per quiet span
  (`nothing_to_do`); a reaction to a contested take (`react`).
- **Plans.** A model plan (a continuation) is held by the game. On those turns `note_turn` updates the
  autopilot's goals and the gate's last values, with no provider call. A plan ends at its destination
  (`destination_reached`, which prompts nothing) or at an interrupt (which consults).
- **Fallback.** Causes: `provider_error`, `invalid_output` (after one repair), `call_cap`, `spend_cap`,
  `internal_error`, and `invalid_reaction`. Each returns the autopilot's action, with `llm_fallback` set in
  the response's `backend_state`.
- **Replies.** `waiting: true` is an invalid output and goes to the repair. A reply with no `major_action`
  keeps the autopilot's action and continuation, and uses the reply's utterances and memory updates
  (`carry_ons`). `major_action.action == "wait"` gives an idle response with no continuation (`waits`).
  Any other action is the model's, with its continuation (`successes`, `turn_kind` `act`).
- **Prompt.** The payload carries an `autopilot` section beside the Phase 018 record: `why_consulted`,
  `usual_now` (the block's sentence from `domains/persona.py`, in words, for example `Usually now: ... (at work).`),
  and the rules text. The record's prompt hash does not include it, so the Phase 031 hash test still holds.
- **Counts.** `llm_counts` and `llm_report` carry: `calls`, `repairs_used`, `repaired_successes`,
  `successes` (accepted replies), `failures` (fallbacks, all causes), `fallbacks_by_cause`, `provider_errors`,
  `invalid_outputs`, `autopilot_turns`, `carry_ons`, `waits`, `deviations`, `consults_by_reason`, `turns`,
  `share_consulted` and `share_autopilot`. `decisions` is `successes + failures` (consults attempted,
  including ones a cap refused).

## Limits

- No live provider. Latency, repair rate and reply quality with a real model are not measured.
- Plan turns: `decide` does not run on them, so the autopilot takes in those turns through
  `_update_goals` and the gate's last values only. Its counterfactual is not computed for them.
- Calls per day, quiet ticks (24 to 192), the trait weights of `routine_strength`, the thresholds and
  the boundary share are APPROX model choices (see the `_doc` in `world/autopilot.json`). None is measured.
  `routine_strength` uses role identity, arousal (inverted) and outlook. None of the personality numbers
  is a conscientiousness scale, and the brief's wording did not name one.
- `routine_strength` skips a trait whose number is missing rather than defaulting it. A resident with only
  `role_identity` is judged on that alone.
- Deviation compares the action name and its `target` parameter only. A move to another destination with
  the same target does not count as a departure.
- The gate's rules use the routine only for jobs or life stages that have a ROUTINE row (no routine: no
  routine-boundary trigger).
- LLM residents use the default simple profile for the autopilot. `create_game` does not pass a scenario's
  `simple_profile` to them, because the change would be in `bigville/api.py`, which is not in this phase's
  write scope.
- A `poll_each_turn` continuation from a model makes the game ask every turn. The gate has no trigger for it,
  so the autopilot acts and replaces the plan. Not tested.
- The autopilot's speech (its `_speech`) can update its own last-speech turn on a consulted turn, even when
  the model's reply is used. This does not change the world.
- Human unattended autopilot (brief item 8): deferred. The human backend still waits, as before.
- `llm_report`'s `decisions` now counts attempted consults (including those a cap refused), not only
  idle turns as in Phase 031.
- The first turn of every LLM resident is a consult (`check_in`), so a town of N LLM residents makes at
  least N calls at the start.

## Open questions

1. Should a model's `continuation` survive a carry-on reply? Now a carry-on keeps the autopilot's
   continuation, and a `wait` drops both. Choose one rule.
2. Should the scenario's `simple_profile` reach the autopilot of an LLM resident? It needs a small change in
   `bigville/api.py` (`llm_backend_factory` passing `simple_policy_for(profile)`). Approve that edit, or leave it.
3. Should `poll_each_turn` be honoured, or ignored and logged? Honouring it asks the model every turn.
4. Are the APPROX numbers right: quiet ticks 24 to 192, 12 calls per resident per day, boundary share 1.0,
   the `routine_strength` weights? They are in `world/autopilot.json` and easy to change.
5. Should Phase 054 move the `autopilot` section into `PromptBuilder` (its prompt packet owner) rather than
   the payload that `llm.py` adds? The brief for 054 says the private part leads with the persona card and
   "what you would usually do now". This phase adds the second part in `llm.py`.
6. Should the human unattended autopilot be built now, or kept for later?
7. Phase 031's open question on `waiting: true` is now answered: a model's `waiting: true` is an invalid output.
   Confirm that reading.

## Working tree at start of this phase (`git status --short`, recorded before any edit)

Other sessions' uncommitted work, unchanged by this phase except where listed under Changes:

```
 M README.md
 M bigville/backends/cheap.py
 M bigville/backends/ocelot.py
 M bigville/backends/protocol.py
 M bigville/game.py
 M bigville/game/game.js
 M bigville/reporting.py
 M bigville/runtime.py
 M bigville/seeds/bigville_actor_decision.json
 M bigville/server.py
 M docs/AGENT_BACKENDS_PLAN.md
 M domains/bigville_entities.py
 M domains/world_affordances.py
 M packs/bigville/pack.json
 M packs/bigville/world/free_actions.json
 M packs/bigville/world/resolution.json
 M packs/test_hamlet/pack.json
 M packs/test_hamlet/world/free_actions.json
 M packs/test_hamlet/world/resolution.json
 M tests/test_bigville_game_api.py
 M tests/test_bigville_scenarios.py
 M tests/test_bigville_server.py
 M tests/test_bigville_world_migrated.py
 M tests/test_phase001_workshop_tools.py
 M tests/test_phase010_burial.py
 M tests/test_phase023_job_occupancy.py
 M tests/test_phase050_resolution.py
 M tests/test_simple_tools_materials_job.py
 M worlds/bigville_world.py
 M worlds/resolution.py
?? bigville/game_persistence.py
?? bigville/mixed_ocelot_scenario.py
?? bigville/world_persistence.py
?? docs/MIXED_OCELOT_VILLAGE_RUN_20261105.md
?? docs/ocelot-integration-baseline.md
?? docs/phases/phase048/
?? docs/phases/phase052/full_suite_live_tree_midedit.log
?? docs/runs/
?? tests/test_bigville_game_persistence.py
?? tests/test_bigville_graph_persistence.py
?? tests/test_bigville_ocelot_communication.py
?? tests/test_bigville_ocelot_fresh_process.py
?? tests/test_bigville_world_persistence.py
?? tests/test_mixed_ocelot_checkpoint_parity.py
?? tests/test_mixed_ocelot_village.py
?? tests/test_phase048_tool_fitness.py
?? tools/run_mixed_ocelot_scale.py
?? tools/run_mixed_ocelot_village.py
```

Files this phase touched (in addition to the list above, which other sessions own): `bigville/backends/llm.py`,
`bigville/game.py` (two hunks), `bigville/reporting.py` (two hunks), `domains/bigville_entities.py` (two lines),
`packs/bigville/pack.json` and `packs/test_hamlet/pack.json` (one entry each), `tests/test_phase031_llm_backend.py`,
and the new files listed under Changes.
