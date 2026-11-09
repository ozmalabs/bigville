# Phase 071e: a reply is accepted unless it is malformed

## Summary

The five cases from Phase 071d's open questions are accepted. Each accepted reply makes one provider call, and its outcome is recorded. Each malformed variant still makes the repair call. Only shape and type decide malformed now.

The packet, the reply shape and the prompt schema (`bigville/prompt/7`) are unchanged, so the packet snapshot fixture still matches and was not edited.

Base: HEAD `1cf9864` (Phase 071d). Work was done in a clean worktree (`/tmp/t071e`). HEAD did not move during the phase. The patch is `docs/phases/phase071e/PHASE071E.patch` (against `1cf9864`, includes the new test file). Nothing is committed.

## Changes

### Case 1: `waiting: true` is accepted

`waiting: true` is read as a wait: no major action this turn. The backend turns it into the explicit `wait` action (`reply_schema.to_wire`), so the game takes the same path as `major_action: wait`. If the reply also has a major action, the wait wins and the reply notes `major_action_ignored`. A `waiting` that is not a boolean is still malformed.

### Case 2: blank speech is accepted, and nothing is said

An utterance whose text is empty or only whitespace is dropped before the world sees it. `to_wire` records a refusal `{action: "speak", reason: "nothing_said"}`. The game's `_apply_response` writes it to the resident's free outcome through `free_replies.refuse`, so the agent view shows the reason in `last`. An utterance whose text is not a string, or that has no text field, is still malformed.

### Case 3: an unknown memory kind is kept as a note; blank memory is dropped

A memory update whose kind the pack does not list is stored as a `note`. The kind it named is kept in the record's content: `content = {"text": ..., "named_kind": "gossip"}`. A memory update with blank text is dropped and counted (`memory_dropped`). A kind that is not text, or a text that is not text, is still malformed.

### Case 4: an empty continuation action starts nothing

A continuation whose `task.action` is `""` is accepted. `to_wire` sets the continuation to `None`, so no continuation starts. It records a refusal `{action: "continuation", reason: "no_task"}`, which the game writes to the free outcome as in case 2. A task with no action field, or an action that is not text, is still malformed.

### Case 5: lessons over the cap are accepted; the newest are kept

A reply with more lesson updates than `lessons_max` (12) is accepted with one call. `to_wire` keeps the last 12 lesson updates in the reply's order (the later ones are newest) and drops the earlier ones. The count goes to the backend state as `reply_notes.lessons_dropped`. The merge then replaces the held lessons with the kept ones, as before. The lesson-count check and the `lesson_limit` argument are gone.

### New pack codes

`REFUSAL_REASONS` gains `nothing_said` ("Your reply had no words in it, so nothing was said.") and `no_task` ("Your continuation named no task, so nothing was started."). Both packs.

## Reply check table (updated)

| Check | Where | Now |
|---|---|---|
| unknown top-level field | validate_response | malformed |
| major_action not an object or null | validate_response | malformed |
| major_action.action not text | validate_response | malformed |
| major_action.action empty or unknown | world | refused `unsupported` (071d) |
| major_action.params not an object | validate_response | malformed |
| major_action.reason not text | validate_response | malformed |
| unknown field in major_action | reply_schema | malformed |
| major_action.target or with not text or null | reply_schema | malformed |
| intensity not number or text | reply_schema | malformed |
| intensity unknown word | to_wire | folds to 1.0 (071d) |
| params.verb not text | reply_schema | malformed |
| params.amount not number or text | reply_schema | malformed |
| params.amount unknown word | to_wire | folds to 1.0 (071d) |
| free_actions not a list of objects | validate_response | malformed |
| free action name not text | validate_response | malformed |
| free action name empty or unknown | world | refused `unsupported` (071d) |
| unknown field in a free action | reply_schema | malformed |
| free action target not text or null | reply_schema | malformed |
| free action params not an object | reply_schema | malformed |
| free action text param not text | reply_schema | malformed |
| free action intensity not number or text | reply_schema | malformed |
| free action intensity unknown word | to_wire | folds to 1.0 (071d) |
| free action needs a target, none given | world | refused `no_target` (071d) |
| utterances not a list of objects | validate_response | malformed |
| utterances.text or target wrong type | validate_response | malformed |
| utterance unknown field | reply_schema | malformed |
| utterance `to` not text | reply_schema | malformed |
| utterance text not text, or missing | reply_schema | malformed |
| utterance text empty or blank | to_wire | **accepted; nothing said; `nothing_said` recorded (071e case 2)** |
| memory_updates not a list of objects | validate_response | malformed |
| memory kind not text | reply_schema | malformed |
| memory kind outside memory_kinds | to_wire | **accepted as `note`, kind kept in content (071e case 3)** |
| memory text not text, or missing | reply_schema | malformed |
| memory text empty or blank | to_wire | **accepted and dropped; `memory_dropped` recorded (071e case 3)** |
| more lessons than lessons_max | to_wire | **accepted; newest kept; `lessons_dropped` recorded (071e case 5)** |
| waiting: true | to_wire | **accepted; read as wait (071e case 1)** |
| waiting not true or false | validate_response | malformed |
| continuation not an object or null | validate_response | malformed |
| continuation.task not an object, or action not text | validate_response | malformed |
| continuation.task action empty | to_wire | **accepted; no continuation; `no_task` recorded (071e case 4)** |
| continuation.task.params not an object | validate_response | malformed |
| continuation.interrupt_on not a list of text | validate_response | malformed |
| continuation thresholds not numbers | validate_response | malformed |
| continuation.poll_each_turn not a boolean | validate_response | malformed |

## Changed tests (old -> new)

- `tests/test_phase054_llm_prompt.py::test_a_reply_outside_the_schema_is_named_in_words`, two rows:
  - `memory_updates` kind `"gossip"` -> kind `5`, message `memory_updates kind must be text`. Why: an unknown kind is accepted now; a kind that is not text is still malformed.
  - `utterances` text `""` -> text `5`, message `utterances need a text`. Why: blank speech is accepted now.
- `tests/test_phase054_llm_prompt.py::test_a_merge_reply_naming_more_lessons_than_the_cap_is_repaired` -> `test_a_merge_reply_naming_more_lessons_than_the_cap_is_accepted_and_the_newest_are_kept`. Old: two calls and a repair message about the cap. New: one call; the merge keeps the last 12 lessons (`x1`..`x12`); `reply_notes == {"lessons_dropped": 1}`. Why: case 5.
- `tests/test_phase059_autopilot.py::test_waiting_true_is_never_accepted_and_the_repair_says_why` -> `test_waiting_true_is_accepted_in_one_call_and_read_as_a_wait`. Old: `waiting: true` is repaired, then the autopilot falls back. New: one call; the response has no major action; `turn_kind == "wait"`. The validator still rejects `waiting: "no"`. Why: case 1.
- `tests/test_phase067_tui_modes.py::_llm_reply` helper: `_check_reply(parsed, fields, PACK_NAME, None)` -> `_check_reply(parsed, fields, PACK_NAME)`. Why: the `lesson_limit` argument was removed.

No assertion was weakened or deleted. No fixture was edited.

## Tests added

`tests/test_phase071e_accept.py` (16 tests). Each case has an accepted test (one provider call, no repair, the outcome checked in the free outcome, the backend notes or the memory) and a malformed test (a repair call follows). The last test checks `reply_schema.check` on each accepted case.

## Files and hunks

Clean-tree files (the whole diff is this phase's):
- `bigville/backends/reply_schema.py`: `check` (lesson limit removed; blank text no longer an error; kind must be text), new `_count`, `_memory`; `to_wire` (waiting, blank speech, memory kinds, lesson cap, empty continuation; writes `reply_notes`). Module docstring corrected.
- `bigville/backends/llm.py`: module docstring (waiting line); `_continuation_errors` (empty action allowed); `_check_reply` (no `lesson_limit`); `validate_response` (`waiting: true` allowed; its docstring); `_check` (no `_lesson_limit`); `_lesson_limit` removed; `_accept` (reads and pops `reply_notes`, records refusals in `response.backend_state["reply_refusals"]`, writes `reply_notes` to `last_backend_state`).
- `bigville/free_replies.py`: new `refuse(game, actor, action, code)`, at the end.
- `packs/bigville/world/refusal_reasons.json`, `packs/test_hamlet/world/refusal_reasons.json`: `nothing_said`, `no_task` (after `unsupported`).
- `tests/test_phase054_llm_prompt.py`, `tests/test_phase059_autopilot.py`, `tests/test_phase067_tui_modes.py`: the changed tests above.
- `tests/test_phase071e_accept.py`: new.

Shared file, not copied to the live tree:
- `bigville/game.py`, `_apply_response`, a new block after the memory-update loop (before `return ok`). It reads `response.backend_state["reply_refusals"]` and calls `free_replies.refuse`. The live `game.py` differs from HEAD (another session's uncommitted hunks), so this block is not in the live file. The supervisor needs to apply it, from the patch, when that session's edits are committed.

Copied into the live tree (the live file equalled HEAD when copied): `bigville/backends/llm.py`, `bigville/backends/reply_schema.py`, `bigville/free_replies.py`, both `refusal_reasons.json`, `tests/test_phase054_llm_prompt.py`, `tests/test_phase059_autopilot.py`, `tests/test_phase067_tui_modes.py`, and the new `tests/test_phase071e_accept.py`. Not committed.

## Validation

Clean worktree `/tmp/t071e` at HEAD `1cf9864` plus this phase.

- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, `ERRORS (0)`, `WARNINGS (0)`.
- `python3 tools/generate_seeds.py --check`: `match pack 'bigville' (31 files)`. No seed changed.
- Affected tests (`test_phase071e_accept`, `test_phase054_llm_prompt`, `test_phase059_autopilot`, `test_phase067_tui_modes`, `test_phase031_llm_backend`, `test_phase071d_reply_checks`, `test_phase071d_free_rounds_notes`, `test_phase021_refusals`): **170 passed**, after the final edits.
- Full suite, `timeout 3600 python3 -m pytest -q -p no:cacheprovider -rf tests` (log `full_suite_clean_tree.log`): **5 failed, 3082 passed, 6 skipped**. The failures:
  - `test_fix_llm_checkpoint[0]`, `test_package15_resource_social_stress`, `test_phase058_persona`, `test_phase060_speech_in`: the four the brief lists as failing at HEAD. I did not re-run them at HEAD in this phase.
  - `management/test_cast_browser::test_cast_groups_preview_and_launch_match_actual_world`: the browser flake. It passed in the first full run of this tree and passes alone in the clean tree (1 passed) and at HEAD (1 passed).
- An earlier full run (before the phase 059 test change) had one more failure, `test_phase059_autopilot::test_waiting_true_is_never_accepted_and_the_repair_says_why`. The test was rewritten (above). The full suite was then re-run, giving the result above.
- After that run I made three comment and whitespace edits (a blank line, a trailing blank line, two long comments in `llm.py`, `free_replies.py` and `game.py`). They change no code. The affected tests were run again afterwards (170 passed). The full suite was not run again after the whitespace edits.
- Patch: `git apply --check` against `/tmp/b071e` (HEAD `1cf9864`) passes.
- Digests (`docs/phases/phase070/compare_digest.py`, town100, seed 305017, simple backend). HEAD and new give the same digest. Files `digest_60_*.json`, `digest_200_*.json`.
  - 60 turns: `3a8c1d8cc7b9e84acef84c4c1adb504038f914b6598acc234f6495ae311c695d`, 0 deaths, base = new.
  - 200 turns: `8d5d176fe20169ba83edcb8b6433d9085034facc228073c86d3c8f545bb3bc97`, 0 deaths, 100 residents with `mark_wetness` 50.0, base = new.
  - The simple backend never produces these replies, so no simple-village number could change.
- Live tree: the self-test and tests were not run there. Only the clean tree results are reported.

## Limits

- No LLM run with a real model. Every LLM path is covered by fake providers.
- Blank speech is recorded as the resident's free outcome, which replaces a glance or other free outcome that the same reply produced earlier. The agent view shows only the latest one.
- Lessons: "newest" means the last lesson updates in the reply's order. The reply does not carry timestamps.
- The digests are simple-backend runs only.

## Open questions

1. **`waiting: true` with a major action.** The wait wins and the major action is dropped (noted as `major_action_ignored`). Should the major action win instead?
2. **Consult text still says "Do not set waiting."** (`packs/bigville/world/prompt_packet.json`, `consult_rules`). I did not change the packet text, so the snapshot and schema stay the same. The model is still told not to use `waiting`. Should that instruction change? If so, the snapshot is regenerated.
3. **Missing text fields stay malformed.** An utterance or memory update with no `text` key is malformed, and only an empty or blank value is accepted. Should a missing text count as blank?
4. **Blank speech shows in `last` only.** The speech log does not record it. Should it also appear in the speech log?
5. **The game.py hunk.** It must be applied in the live tree once the other session commits its `game.py` changes.

## Follow-ups

- Apply the `game.py` hunk (see Files and hunks) when the live tree allows.
- Phase 071d's open questions: 1 (waiting), 2 (lesson cap), 3 (empty speech and unknown memory kind) and 4 (empty continuation) are answered by this phase. Question 5 (a wait with free actions) is unchanged.
- The two `test_phase031_llm_backend` failures that the 071d report recorded no longer occur in this tree (the affected run passed).
