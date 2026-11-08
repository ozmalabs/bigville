# Phase 071d: replies are accepted unless malformed; free actions without a turn; notes and requests by handle; free outcomes survive a checkpoint

## Summary

The five decisions in the brief are implemented.

1. **A reply is accepted unless it is malformed.** The reply check rejects only type and shape errors. An unknown major or free action, a nonexistent target, an unknown region, an unknown intensity or amount word and a missing required target reach the world. The world refuses each with a REFUSAL_REASONS code shown in `last`. The repair call now runs only for malformed replies.
2. **Free actions without a turn, over HTTP too.** `POST /api/free` applies a reply that carries only `free_actions`, with no step, and returns the view. `HttpClient.apply_free` posts to it. An LLM resident whose reply carries free actions and no major action is asked again in the same turn, up to `PROMPT_REPLY.free_rounds_max` = 2 (APPROX).
3. **The LLM can name notes and requests.** The agent view (`self.giveable_notes`, `self.requests`) and the packet (`private.giveable_notes`, `private.requests`) list the handles. `give_note`, `accept` and `decline` name them.
4. **Free outcomes survive a checkpoint.** `game.free_outcomes` is saved and restored by `bigville/game_persistence.py`. A restored game shows the same `last`.
5. **Hand-offs from 071c.** `world.free_action` reads its defaults with `args[0] if args else None`, so keyword calls work. `Body.probe(handle)` replaces `body._derive()` in `free_replies`.

The packet's `private` section gains two keys, so the prompt schema changes. On the briefed base `709fde9` it rises to `bigville/prompt/6`. HEAD moved to `6fefedb` during this session (Phase 054b committed `bigville/prompt/6` and the handle tokens; Phase 042c also landed). On that HEAD the schema is `bigville/prompt/7`. See "Base moved during the session".

Results are in Validation below.

## Changes

Source: `bigville/backends/llm.py`, `reply_schema.py`, `prompt_packet.py`, `bigville/free_replies.py`, `bigville/game.py`, `bigville/game_persistence.py`, `bigville/server.py`, `bigville/tui/client.py`, `domains/agent_view.py`, `worlds/bigville_world.py`, `worlds/body.py`.

Pack data (both packs): `packs/{bigville,test_hamlet}/world/{prompt_packet,agent_view,refusal_reasons}.json`.

Tests: new `tests/test_phase071d_reply_checks.py` and `tests/test_phase071d_free_rounds_notes.py`. Changed: `tests/test_phase021_refusals.py`, `test_phase054_llm_prompt.py`, `test_phase054b_handles.py` (HEAD only), `test_bigville_backends.py`, `test_phase057_tui.py`, `test_phase067_tui_modes.py`, `test_phase071c_free_actions.py`, `test_phase071c_terminal.py`.

Patches: `PHASE071D_on_709fde9.patch` and `PHASE071D_on_6fefedb.patch` (the current HEAD). Not committed.

## Base moved during the session

HEAD moved from `709fde9` to `6fefedb` (Phase 054b `299a942`, Phase 042c `6fefedb`) while this phase ran. Two things followed.

1. **Patches.** `docs/phases/phase071d/PHASE071D_on_709fde9.patch` applies to the briefed base. `PHASE071D_on_6fefedb.patch` applies to the current HEAD. Both include the two new test files. The HEAD patch was made from a worktree at `6fefedb` with the conflicts resolved (below).
2. **Conflicts on 6fefedb.** Four files conflicted, all in lines that 054b also changed:
   - `bigville/backends/prompt_packet.py`: `PACKET_SCHEMA` is `prompt/7` on this HEAD (054b already took `/6`).
   - `tests/test_bigville_backends.py`: 054b already expects `/6`; the phase's expectation is `/7` on this HEAD.
   - `tests/test_phase054_llm_prompt.py`: the same schema pin, now `/7`.
   - `tests/test_phase071c_free_actions.py`: the glance test uses 054b's tokens (`_shown_token`). The `script.calls` assertion is the phase's change, applied to the token version.
3. **Handle tokens.** On 6fefedb the LLM sees opaque tokens for handles (`bigville/backends/handle_map.py`). That module already masks the phase's `self.giveable_notes` and `self.requests` (its `SELF_HANDLE_LISTS`). `tests/test_phase071d_free_rounds_notes.py` therefore reads the handle the model sees through `_shown(...)`, which returns the masked token when the backend has a handle map and the raw handle otherwise. The test installs the LLM backend first, because the map is created with the backend. `test_a_note_the_resident_does_not_hold_is_refused_as_not_held` calls `free_replies.apply_all` directly, since the model cannot name a note it does not hold.

The snapshot fixture on 6fefedb is 054b's. This phase's packet changes differ from it again, so the supervisor regenerates it on the new HEAD.

## Decision 1: replies are accepted unless malformed

### Design

- `reply_schema.check` and `llm.validate_response` now return errors only for shape and type. A word the lexicon does not know, in `intensity` or `params.amount` (major or free), folds to 1.0 in `to_wire`. 1.0 is the value the world already uses when the field is left out. I chose the fold over a pass-through because the world's pace and amount code would otherwise receive a string.
- An empty or unknown major or free action name is passed to the world. `_enact_plan` ends with `_refuse("unsupported")` for any name not in MAJOR_ACTIONS. Before, it refused `malformed`.
- A free action whose `requires_target` is set and has no target (and no `target_or_param`) is refused by `free_replies.apply_one` with the new code `no_target`.
- `REFUSAL_REASONS` gains `no_target`: "The action needs a target, and the reply named none." (both packs).

### Reply check table

Each check in `validate_response` (llm.py), `reply_schema.check` and the continuation check, and what happens to it now.

| Check | Where | Now |
|---|---|---|
| unknown top-level field | validate_response | kept (malformed) |
| major_action is not an object or null | validate_response | kept |
| major_action.action is not text | validate_response | kept (was: not non-empty text) |
| major_action.action is empty or unknown | (was validate_response, reply_schema) | moved: world refuses `unsupported` |
| major_action.params is not an object | validate_response | kept |
| major_action.reason is not text | validate_response | kept |
| unknown field in major_action | reply_schema | kept |
| major_action.target or with is not text or null | reply_schema | kept |
| intensity is not a number or text | reply_schema | kept |
| intensity is an unknown word | reply_schema (was) | moved: folds to 1.0 |
| params.verb is not text | reply_schema | kept (an unknown verb was already passed through) |
| params.amount is not a number or text | reply_schema | kept |
| params.amount is an unknown word | reply_schema (was) | moved: folds to 1.0 |
| free_actions is not a list of objects | validate_response | kept |
| free_actions.action is not text | validate_response | kept (was: not non-empty text) |
| free action name empty or unknown | (was reply_schema) | moved: world refuses `unsupported` |
| unknown field in a free action | reply_schema | kept |
| free action target is not text or null | reply_schema | kept |
| free action params is not an object | reply_schema | kept |
| free action text param (text, note, item, giver) is not text | reply_schema | kept |
| free action intensity is not a number or text | reply_schema | kept |
| free action intensity is an unknown word | reply_schema (was) | moved: folds to 1.0 |
| free action with a required target and none given | reply_schema (was) | moved: world refuses `no_target` |
| utterances is not a list of objects | validate_response | kept |
| utterances.text or target is the wrong type | validate_response | kept |
| utterance unknown field | reply_schema | kept |
| utterance `to` is not text | reply_schema | kept |
| utterance text missing or empty | reply_schema | kept (see Open questions) |
| memory_updates is not a list of objects | validate_response | kept |
| memory kind outside the pack's memory_kinds | reply_schema | kept (see Open questions) |
| memory text missing or empty | reply_schema | kept |
| more lessons than the packet's lessons_max | reply_schema | kept, as a well-formed reply refused (see Open questions) |
| waiting: true | validate_response | kept (see Open questions) |
| waiting is not true or false | validate_response | kept |
| continuation is not an object or null | validate_response | kept |
| continuation.task is not an object, or its action is empty | validate_response | kept (empty action is still malformed) |
| continuation.task.params is not an object | validate_response | kept |
| continuation.interrupt_on is not a list of text | validate_response | kept |
| continuation thresholds are not numbers | validate_response | kept |
| continuation.poll_each_turn is not a boolean | validate_response | kept |

### Test results for the decision

- `tests/test_phase071d_reply_checks.py` (8 tests): an unknown major action, an unknown free action, a nonexistent target (`strike` at "Nobody Known"), an unknown region (`press`), and a missing required target (`reply` with no target) are each accepted, refused by the world with a recorded reason, and make one provider call. A malformed reply (`major_action.action` = 5) makes a repair call, and the repaired reply is accepted (`outcome` "repaired"). Unknown intensity and amount words fold to 1.0.
- Note on `wait`: a `major_action` of `wait` is stored as no major action (`ActorResponse` has no major action for it). A `wait` with free actions therefore takes part in decision 2's free rounds. The tests use `rest` for their major action, to keep a single call.

## Decision 2: free actions without a turn

- **Over HTTP.** `POST /api/free` (new route; `GameService.free` in `bigville/server.py`). Its body is `{"free_actions": [...]}` and nothing else. A body with another key (a major action or utterances) gets 400 and a message that names `/api/turn`. The actions are checked by `reply_schema.check` and folded by `to_wire`, then applied by `free_replies.apply_all` with no step. The response is `{"status": "free", "view": ...}`. Its turn is unchanged. `HttpClient.apply_free` posts to this route. It no longer raises `UnsupportedOverHttp` (that class is still used elsewhere).
- **Free rounds in the game.** `Game._free_round_responses` (bigville/game.py) runs after each concurrent `decide_pooled` batch, in the main thread. While a reply has free actions, no major action, and rounds remain, it applies that reply with `_apply_response` (free actions, utterances and memory updates) and asks the same backend again with `_context(actor)`, which is the rebuilt view. The loop runs at most `PROMPT_REPLY.free_rounds_max` (2) times. The last reply stands as the turn. Simple backends never produce free actions, so the loop never runs for them. Both concurrent decision loops (`step` and `_step_deferred`) call it.
- The round runs sequentially, not in the pool, because a free action changes the world (for example `give_note`).

### Test results

- `tests/test_phase071d_free_rounds_notes.py`: an LLM glances, then acts in a second round; both are applied (`free_outcomes` holds the glance, and `last_responses` holds the rest). The round cap holds at `1 + free_rounds_max` calls when every reply is free-only. The turn advances by one. A simple resident sends no free action in three turns. `GameService.free` returns the view and leaves the turn unchanged, and refuses a major action.
- `tests/test_phase071c_terminal.py::test_over_http_a_glance_on_its_own_runs_with_no_turn` (see Changed tests) runs a real local HTTP server and checks the same over HTTP.

## Decision 3: notes and requests by handle

- **Notes.** `domains/agent_view.py::_giveable_notes` lists the Note nodes the resident holds, as `{handle, what}`. The handle is the world's note id (`note:N`). `what` is the note's text.
- **Requests.** `_open_requests` lists the requests addressed to the resident with status 0 (open), as `{handle, who, what}`. The handle is the request's `name` (`request:N`), `who` is the sender, and `what` is the task text.
- Both keys are whitelisted in `AGENT_VIEW_WHITELIST.self` (agent_view.json, both packs). The packet copies them into `private.giveable_notes` and `private.requests`, under the caps `giveable_notes` and `requests` (500 characters each, APPROX: a design choice), and cuts `what` to `note_chars`.
- The interface line in `prompt_packet.json` names the handles: `note` for give_note is "a handle from private.giveable_notes", and accept and decline name a request by its handle from private.requests, as target.
- **Refusal.** `world.give_note` moves whatever note it is named, and it did not check that the sender holds it. This phase found that gap in a test. `free_replies.apply_one` now refuses a `give_note` whose note the actor does not hold with `not_held` (an existing code). The check is `_holds_note`, in free_replies.

### Test results

- `test_the_view_lists_the_handles_of_held_notes_and_open_requests`: the handles, the `what` text, and `who` appear in the view. A note held by someone else does not.
- `test_an_llm_gives_a_note_it_holds_and_accepts_and_declines_by_their_handles`: the LLM gives `note:9` to the other resident, accepts `request:1` (status 1) and declines `request:2` (status -1).
- `test_a_note_the_resident_does_not_hold_is_refused_as_not_held`: gives `note:11`, which another resident holds. Refused with `not_held`; the holder keeps it.

## Decision 4: free outcomes survive a checkpoint

- `bigville/game_persistence.py`: `save_game_checkpoint` writes `free_outcomes` (a dict of plain dicts, one per resident). `load_game_checkpoint` restores it, with `.get("free_outcomes", {})` so older checkpoints still load.
- `tests/test_phase071d_free_rounds_notes.py::test_free_outcomes_survive_a_checkpoint`: a glance, a save, a load. The restored `free_outcomes` and the agent view's `last` equal the saved ones.

## Decision 5: hand-offs from 071c

- `worlds/bigville_world.py::free_action`: the defaults for reply, give_note, accept and decline use `args[0] if args else None`. `test_free_action_takes_keyword_arguments` calls each with keywords.
- `worlds/body.py::Body.probe(handle)`: returns `{sound, place}` for a felt signal, or None when the handle names no felt signal. It reads only. `free_replies._glance_probe` calls it. `test_body_probe_gives_the_sound_and_place_of_a_felt_signal` covers it.

## Shared-file hunks

Each hunk is separate from the other session's hunks in the same file. Both trees were checked.

- `bigville/game.py`: new method `_free_round_responses` (before `_apply_response_contained`). In `step` and `_step_deferred`, the `decide_pooled` loop line now wraps its call in `self._free_round_responses(...)`.
- `bigville/server.py`: new method `GameService.free` (after `GameService.turn`), and a route `/api/free` in `BigvilleHandler.do_POST` (after `/api/turn`).
- `domains/agent_view.py`: new functions `_giveable_notes` and `_open_requests` (after `_lessons`); two keys in the `_self` dict (`giveable_notes`, `requests`).
- `worlds/bigville_world.py`: `_enact_plan`, an `unsupported` branch before the final `malformed` return; `free_action`, four `args[0]` defaults.
- `domains/bigville_entities.py`: no change.

Files that were clean at the start (my hunks are the whole diff): `bigville/backends/llm.py`, `reply_schema.py`, `prompt_packet.py`, `bigville/free_replies.py`, `bigville/game_persistence.py`, `bigville/tui/client.py`, `worlds/body.py`. `bigville/backends/llm.py` (`validate_response`, the free-action and major-action name checks), `reply_schema.py` (`_check_major_action`, `_check_free_action`, `_fold_free`, `_fold_action`, `to_wire`, and the helpers `_is_number_or_word` and `_weight`; `_words_list` removed as unused), `prompt_packet.py` (`PACKET_SCHEMA`, and `private`'s two keys).

Pack data (both packs, written in the exporter's layout; no table added):
- `world/prompt_packet.json`: `PROMPT_REPLY.free_rounds_max` = 2 (APPROX), `PROMPT_PACKET.caps.giveable_notes` = 500 and `requests` = 500 (APPROX), and the free-action interface line.
- `world/agent_view.json`: `AGENT_VIEW_WHITELIST.self` gains `giveable_notes` and `requests`.
- `world/refusal_reasons.json`: `no_target`.

## Changed tests (old -> new)

- `tests/test_phase054_llm_prompt.py::test_a_reply_outside_the_schema_is_named_in_words`, two rows: `intensity: "very very hard"` -> `intensity: ["very very hard"]` (message now "intensity must be a number or a word"); `params.amount: "loads"` -> `["loads"]` (message "params.amount must be a number or a word"). Why: an unknown word is a world refusal now; the list keeps the malformed case.
- `tests/test_phase054_llm_prompt.py::test_an_invalid_reply_is_repaired_once...` and `::test_a_repaired_reply_in_words_is_accepted`: the same `very very hard` -> list change. Why: as above. A repair is still exercised.
- `tests/test_phase054_llm_prompt.py::test_the_packet_uses_the_packet_schema_and_the_pack_hash`: `bigville/prompt/5` -> `bigville/prompt/6` on 709fde9 (`/6` -> `/7` on 6fefedb). Why: the packet's `private` gains two keys.
- `tests/test_bigville_backends.py` (two lines): `bigville/prompt/5` -> `bigville/prompt/6` on 709fde9; on 6fefedb `/6` -> `/7`, the same lines. Why: as above.
- `tests/test_phase054b_handles.py::test_the_packet_schema_is_prompt_6` -> `test_the_packet_schema_is_prompt_7`: `PACKET_SCHEMA == "bigville/prompt/6"` -> `"bigville/prompt/7"` (on 6fefedb only). Why: this phase bumps the packet schema.
- `tests/test_phase021_refusals.py::test_a_malformed_plan_is_logged_once_not_once_per_nested_attempt`: the `dance` call moves first and asserts `reason == "unsupported"`; the `fetch` call (malformed) follows and keeps the original `malformed` check. Why: an unknown action is now `unsupported`. The malformed assertion is kept.
- `tests/test_phase071c_free_actions.py::test_a_free_action_reply_is_checked_against_the_free_action_table`: `glance` with no target `errors == ["free action glance needs a target"]` -> `== []`. Why: a missing target is the world's refusal now. The `set_intensity` value `"sideways"` -> `["sideways"]` (malformed case; the word is folded now).
- `tests/test_phase071c_free_actions.py::test_an_llm_glance_reply_is_enacted...`: `script.calls == 1` -> `== 1 + load_pack(PACK)["PROMPT_REPLY"]["free_rounds_max"]` (3). Why: a free-only reply is asked again (decision 2).
- `tests/test_phase071c_terminal.py::test_over_http_a_glance_on_its_own_is_refused_with_a_message` -> `test_over_http_a_glance_on_its_own_runs_with_no_turn`: was "`HttpClient.apply_free` raises `UnsupportedOverHttp`"; now a real local server, asserting `status` "free", a `view`, an unchanged `_turn`, and a recorded glance. Why: decision 2.

- `tests/test_phase057_tui.py::test_the_server_refuses_a_bad_reply_and_a_reaction_nobody_is_waiting_for`: the posted reply `intensity: "very very hard"` (expected 400) -> `intensity: ["very very hard"]` (still 400, "intensity must be"). Why: an unknown word is accepted now. This test failed in the full clean run and was fixed before the final run.
- `tests/test_phase067_tui_modes.py::test_the_text_mode_shows_only_what_the_packet_and_the_view_carry`: the allowed set of `private` keys gains `giveable_notes` and `requests`. Why: the packet lists the handles (decision 3).

No assertion was weakened or deleted. No fixture was edited. Two tests of the other session's file (tests/test_phase031_llm_backend.py) now fail. They are not edited here; see Open questions.

## Validation

Commands. The live tree is the shared checkout; the clean tree is `/tmp/t071d` (git worktree at HEAD 709fde9, with this phase's hunks applied). The base for the digests is `/tmp/b071d` (HEAD).

**Clean tree** (`/tmp/t071d`, HEAD 709fde9 plus this phase's hunks; the new test files are copied in):

- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)` (bigville).
- `python3 -m domains.check --pack test_hamlet`: exit 0, `ERRORS (0)`, `WARNINGS (0)`.
- `python3 tools/generate_seeds.py --check`: `match pack 'bigville' (31 files)`. No seed file changed, so no regeneration.
- New tests: `python3 -m pytest -q -p no:cacheprovider tests/test_phase071d_reply_checks.py tests/test_phase071d_free_rounds_notes.py`: 18 passed.
- Affected existing files (`test_phase071c_free_actions`, `test_phase071c_terminal`, `test_phase054_llm_prompt`, `test_phase021_refusals`, `test_phase031_llm_backend`, `test_phase057_tui`, `test_phase067_tui_modes`, `test_bigville_backends`): 206 passed, 3 failed (the snapshot, and two in `test_phase031_llm_backend`).
- Full suite: `timeout 3600 python3 -m pytest -q -p no:cacheprovider -rf tests` in the clean tree, log `docs/phases/phase071d/full_suite_clean_final.log`: **8 failed, 3024 passed, 6 skipped** (2039 s). Failures:
  - `management/test_cast_browser::test_cast_groups_preview_and_launch_match_actual_world`: also fails at HEAD (checked in `/tmp/b071d`).
  - `test_fix_llm_checkpoint[0]`, `test_package15_resource_social_stress`, `test_phase058_persona`, `test_phase060_speech_in`: the four the brief lists as failing at HEAD. I did not re-run them at HEAD in this session.
  - `test_phase054_llm_prompt::test_the_packet_matches_the_snapshot_for_a_fixed_view`: expected. The fixture is not edited (see Snapshot).
  - `test_phase031_llm_backend::test_callable_provider_is_accepted` and `::test_each_structural_rule_reports_a_fixed_message[bad0...]`: the other session's file (see Open questions 6).
  - An earlier full run (before the test edits in `test_phase057` and `test_phase067`, and before removing an unused helper) gave 10 failed, 3022 passed. Those two tests were the difference. Their current result is 206 passed in the targeted rerun, and the final run above.
- Snapshot: `tests/fixtures/phase054_packet_snapshot.json` is **not edited**; it changes. Differences (from a candidate generated to a temp file): `private.giveable_notes` and `private.requests` (empty lists for the fixed view), the free-action interface sentence, `sizes.total` 1817 -> 1821 and `sizes.system` 7741 -> 7861, and `schema` `bigville/prompt/5` -> `bigville/prompt/6`. The supervisor should regenerate it.
- Schema version: rises to `bigville/prompt/6` (the packet shape changed). `PACKET_SCHEMA` is in `bigville/backends/prompt_packet.py`.
- Digests (`docs/phases/phase070/compare_digest.py`, town100, seed 305017, simple backend; base = HEAD in `/tmp/b071d`):
  - 60 turns: base and new `3a8c1d8cc7b9e84acef84c4c1adb504038f914b6598acc234f6495ae311c695d`, deaths 0.
  - 200 turns: base and new `8d5d176fe20169ba83edcb8b6433d9085034facc228073c86d3c8f545bb3bc97`, deaths 0, 100 residents with `mark_wetness` 50.0.
  - Files: `digest_60_*.json`, `digest_200_*.json`. Both match the 071c figures. No simple-village number changed. The digests ran on the tree before the test-only edits and the removal of the unused `_words_list` helper. Neither can change simple-village behaviour.

**Current HEAD tree** (`/tmp/h071d`, worktree at `6fefedb` with this phase's changes applied as in `PHASE071D_on_6fefedb.patch`):

- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, `ERRORS (0)`, `WARNINGS (0)`.
- `python3 tools/generate_seeds.py --check`: `match pack 'bigville' (31 files)`.
- Full suite, `timeout 3600 python3 -m pytest -q -p no:cacheprovider -rf tests` (log `docs/phases/phase071d/full_suite_head_6fefedb.log`): **9 failed, 3062 passed, 6 skipped** (1977 s). The run was before one test edit (below). The failures:
  - `management/test_cast_browser`: also fails at HEAD 709fde9, as checked in this session.
  - `test_fix_llm_checkpoint[0]`, `test_package15_resource_social_stress`, `test_phase058_persona`, `test_phase060_speech_in`: the four the brief lists as failing at HEAD. Their failures are unchanged in this run. I did not re-run them at HEAD here.
  - `test_phase054_llm_prompt::test_the_packet_matches_the_snapshot_for_a_fixed_view`: expected (see Snapshot).
  - `test_phase031_llm_backend` (two): the other session's file (see Open questions).
  - `test_phase054b_handles::test_the_packet_schema_is_prompt_6`: caused by this phase's bump to `/7`. Fixed by one edit (see Changed tests). It passes now, with the 054b file, the new tests and the 071c tests (42 passed in `test_phase054b_handles.py`, 18 in the 071d files).
- Expected after that edit: 8 failed, 3063 passed. The final full run on HEAD was not repeated after the edit.

**Live tree** (`/home/matt/ozmadev/bigville`, shared checkout): **not runnable.** The other session's untracked `bigville/backends/duty.py` imports `DUTIES` from `domains/world_affordances.py`, and the live file has no such name (`ImportError: cannot import name 'DUTIES'`). Consequences:

- `python3 domains/bigville_entities.py`: exit 1 with that ImportError. The self-test has no ERRORS/WARNINGS count.
- `python3 -m pytest tests`: 179 collection errors; the run is interrupted (`docs/phases/phase071d/full_suite_live.log`). No live test result.
- `python3 tools/generate_seeds.py --check` (live, before the break): `match pack 'bigville' (31 files)`.
- Live `domains.check --pack test_hamlet`: the same ImportError.

The clean-tree results above are the evidence for this phase.

## Limits

- The live tree does not run. `bigville/backends/duty.py` (the other session's untracked file) imports `DUTIES` from `domains/world_affordances.py`, which the live file does not define. `import bigville.api` and `import bigville.game_persistence` fail on that import. Live results are therefore not available for any test that imports the game. The live self-test exits 1 with the same ImportError.
- A free-round reply that carries utterances or memory updates applies them in the round. A reply that is free-only at the cap stands as the turn, and its free actions are applied by `_apply_response` as before.
- The packet's `what` cuts each note and request to `note_chars` (240). The caps are APPROX, not measured.
- No village run with a live LLM resident was made. The LLM paths are covered by fake providers.
- The digests are simple-backend runs only. They show no change in the simple village; they do not test the LLM path.

## Open questions

1. **`waiting: true` is still a malformed reply.** It has a well-formed boolean. The world has no meaning for it except "wait". Should it map to `wait`, or be a world refusal?
2. **Lesson cap.** A reply with more lessons than `lessons_max` is refused by the reply check. It is well-formed. Should the merge (`_merge_lessons`) take it instead?
3. **Empty speech text and an unknown memory kind** are still malformed. Should an empty utterance go to the world (speak "" is a refusal)? Should an unknown memory kind be kept as text?
4. **Empty continuation action** (`continuation.task.action` = "") is still malformed.
5. **`wait` with free actions** counts as no major action and gets a free round. Is that the intent, or should a `wait` end the turn?
6. **`tests/test_phase031_llm_backend.py`** (the other session's file, not edited) has two failing tests. Line 127 pins `bigville/prompt/5` (now `/6`). `test_each_structural_rule_reports_a_fixed_message[bad0...]` expects `major_action: {"action": ""}` to fail with "must be a non-empty string". Decision 1 makes an empty action the world's refusal, so that row is obsolete. Its owner should update both.
8. **Snapshot.** `tests/fixtures/phase054_packet_snapshot.json` is not edited. The supervisor regenerates it. The only differences are: `private.giveable_notes` and `private.requests` (empty lists in the fixed view), the free-action interface sentence, `sizes` (`total` 1817 -> 1821, `system` 7741 -> 7861), and the `schema`.

## Follow-ups

- The live tree needs the `duty.py` / `world_affordances.py` import fixed before the live suite can run.
- Decide Open questions 1 to 5.
