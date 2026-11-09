# Phase 071f: one way to wait

## Summary

The LLM reply contract has one way to wait: `major_action: {"action": "wait"}`. The top-level `waiting` field is gone from
the pack, the packet and the validator. A reply that still carries `waiting` is accepted. The key is dropped, counted in
`reply_notes` as `waiting_ignored`, and the reply's major action stands. The prompt schema is `bigville/prompt/8`.

A wait is a no-op at the game. The LLM path and the TUI pass send no major action, so nothing reaches the world. A
`wait` proposal from any other backend also skips the world (no refusal). `last` does not change on a wait. It keeps
showing the previous major outcome. See Open questions.

Base: HEAD `99c29b5`. The clean worktree `/tmp/t071f` is at that commit with this phase applied. The patch is
`docs/phases/phase071f/PHASE071F.patch` (against `99c29b5`, includes the new test file). Nothing is committed.

## The contract before and after

| Item | Before (071e) | After (071f) |
|---|---|---|
| `PROMPT_RESPONSE_FIELDS` (both packs) | ends with `"waiting"` | no `waiting` |
| Packet consult rule | "... wait. Do not set waiting." | "... whose action is wait." (the sentence about `waiting` is removed) |
| Packet interface line | "To do nothing on purpose, set action to wait." | unchanged |
| Top-level `waiting: true` | read as a wait; a major action in the same reply is dropped (`major_action_ignored`) | ignored, noted `waiting_ignored`; the major action stands |
| Top-level `waiting: false` / other value | `false` ok, non-boolean malformed | ignored, noted `waiting_ignored`; not an error |
| `major_action: {"action": "wait"}` | no-op, `turn_kind` `wait`, `waits` counter | unchanged |
| `major_action: null` | carry on as usual | unchanged |
| Packet schema | `bigville/prompt/7` | `bigville/prompt/8` |

### The stray-`waiting` rule

A top-level `waiting` key is not a shape error, whatever its value. `validate_response` skips it when it checks for unknown
fields. `to_wire` removes it from the wire form and adds `waiting_ignored` to `reply_notes`. The major action, if any, is
left as written. No repair call runs. The key cannot set `ActorResponse.waiting`, because the wire form no longer holds it.

The rule is one rule: the key is ignored and noted. It does not override or get overridden by the major action.

## What `wait` does, by path

- **LLM reply, `major_action: {"action": "wait"}`:** `reply_schema.to_wire` keeps the action. `LLMBackend._accept` turns it
  into a response with no major action. The backend records `turn_kind: "wait"` and counts `waits`. The game then does
  nothing for the action. No outcome is published and no refusal is recorded.
- **TUI pass (`wait`, `.`, `stop`, `z` at the prompt), or an empty reply:** `ActorResponse.from_dict({})` gives no major
  action. The game does nothing for the action, as above.
- **TUI typed reply with `major_action` wait:** `client.send_reply` runs `to_wire`, then `from_dict`. The result is a
  `wait` proposal, which the game handles in the guard below.
- **Any other backend proposing `wait`:** before this phase the game passed it to `world.enact_plan`, and the world refused
  it as `unsupported`. Probe at HEAD: `_apply_response` returned `False` and `last_outcome` was
  `{'action': 'wait', 'applied': False, 'reason': 'unsupported'}`. Now `bigville/game.py::_apply_response` skips any
  `wait` proposal. It returns `True` and writes nothing to the world.

### What `last` shows after a wait

`last` comes from the world's last published major outcome (`World.last_outcome`). A wait publishes none, so `last` keeps
the previous one. Probe, after a refused `levitate` (run in the worktree):

```
after refused levitate, last: {'action': 'levitate', 'outcome': 'it did not happen', 'reason': 'The world has no physical way to do this action yet.'}
LLM wait turn_kind: wait | last after wait: {'action': 'levitate', 'outcome': 'it did not happen', ...}
pass {} applied, last: {'action': 'levitate', 'outcome': 'it did not happen', ...}
typed wait via to_wire applied, last: {'action': 'levitate', 'outcome': 'it did not happen', ...} | refusals: [{'actor': 'Ben', 'action': 'levitate', 'reason': 'unsupported', 'turn': 0}]
```

So a resident who waited still sees its previous refusal as `last`. This is the state the code gives today. The brief asks
for a wait "recorded as the turn's action". Recording it as one would change the turn structure (a wait would become a
major action in every LLM and TUI turn) and the `last` view of every wait. I did not make that change. See Open questions.

## Readers and writers of `ActorResponse.waiting` (internal, unchanged)

Meaning: the backend is waiting for a human (the human backend has no answer yet). It is not a contract field.

- **Writers:** `bigville/backends/human.py` `HumanBackend.react` and `HumanBackend.decide` (`ActorResponse(waiting=True)`
  when no answer is queued). `ActorResponse.from_dict` (`bigville/backends/protocol.py`) reads `waiting` from any wire dict.
  The TUI's raw `client.submit(wire)` uses this path. The LLM backend writes nothing: `_accept` builds fresh responses without
  the flag, and the fallback and reaction paths do not set it.
- **Readers:** `bigville/game.py` (the `response.waiting` checks in the turn loops, around lines 1522, 1533, 1606, 1623, and
  `_contest_choice` at 2274). `bigville/tick_trace.py` (line 144, the trace field). `bigville/game_persistence.py` (lines 91 and 112,
  the checkpoint field; the file is tracked at HEAD).
- **Not changed:** `ActorResponse.from_dict` still reads `waiting`. The self-test's `_RESPONSE_FIELDS` set in
  `domains/bigville_entities.py` still lists `waiting`. It checks that each pack field is one the backend reads, so it
  stays.

## Changes

Source (all in `99c29b5` files, all copied to the live tree):

- `bigville/backends/reply_schema.py`: `STRAY_WAITING` constant. `to_wire` drops the stray key and notes `waiting_ignored`.
  The old `waiting: true` branch and `major_action_ignored` are removed. Docstring updated.
- `bigville/backends/llm.py`: `validate_response` skips the stray key in the unknown-field check. The boolean check on
  `waiting` is removed. Docstrings updated (module, `validate_response`). Imports `STRAY_WAITING`.
- `bigville/backends/prompt_packet.py`: `PACKET_SCHEMA = "bigville/prompt/8"`.
- `bigville/game.py`: `_apply_response` skips a `wait` major action (the no-op guard).

Packs (both `bigville` and `test_hamlet`, same edit in each):

- `world/llm_instructions.json`: `waiting` removed from `PROMPT_RESPONSE_FIELDS`.
- `world/prompt_packet.json`: "Do not set waiting." removed from `consult_rules`.

Tests, new:

- `tests/test_phase071f_wait.py` (12 tests): the packet and pack names only `wait`; a wait reply waits in one call with no
  outcome and no refusal; a `wait` proposal from another backend is a no-op; a null major action carries on; the stray key is
  accepted, noted, and the major action stands; the wire form drops the key and `from_dict` gives `waiting` False; the stray
  key is not a shape error for any value, but an unknown field is still one; the human backend still returns `waiting`
  until it is answered.

Tests, changed (old -> new):

- `tests/test_phase071e_accept.py`:
  - `test_waiting_true_is_accepted_and_read_as_a_wait` -> `test_a_stray_waiting_key_is_ignored_and_noted_and_the_turn_carries_on`.
    Old: `waiting: true` with no major action waits. New: the key is ignored; the turn carries on; `reply_notes == {"waiting_ignored": 1}`.
  - `test_waiting_true_with_a_major_action_waits_and_says_the_action_was_ignored` ->
    `test_a_stray_waiting_key_with_a_major_action_leaves_the_major_action_standing`. Old: the rest is dropped.
    New: `rest` stands; `reply_notes == {"waiting_ignored": 1}`.
  - `test_waiting_that_is_not_a_boolean_is_still_malformed` -> `test_a_stray_waiting_key_is_accepted_whatever_its_value`.
    Old: a repair call. New: one call. Reason: the key is no longer a field.
- `tests/test_phase059_autopilot.py`: `test_waiting_true_is_accepted_in_one_call_and_read_as_a_wait` ->
  `test_a_stray_waiting_key_is_accepted_in_one_call_and_the_major_action_stands`. Old: `turn_kind` `wait`, major action None.
  New: `turn_kind` `act`, `rest` stands, `reply_notes == {"waiting_ignored": 1}`. The validator assertions now pass `("major_action",)`
  as the fields, and both `True` and `"no"` are accepted.
  - `test_the_validator_still_accepts_waiting_false` is unchanged. It still passes.
- `tests/test_phase031_llm_backend.py`:
  - `VALID` lost `"waiting": false`.
  - The three `fields` tuples and `good` dict lost `"waiting"`.
  - Row `({"waiting": "no"}, "waiting must be true or false")` removed. Replaced by
    `test_a_stray_waiting_key_is_not_a_shape_error`. Old: a non-boolean `waiting` is a shape error. New: not an error.
  - `seen == ["bigville/prompt/7"]` -> `["bigville/prompt/8"]` (schema).
- `tests/test_phase054_llm_prompt.py`:
  - `record.schema == ... "bigville/prompt/7"` -> `"bigville/prompt/8"`.
  - `test_a_hostile_reply_still_has_to_pass_the_schema_whatever_the_speech_said`: the reply `_reply(None, waiting=True)` now
    also carries `bogus=1`, so the schema check still bites (a repair call runs). Old: the stray key alone. Reason: the stray key no longer fails.
- `tests/test_phase054b_handles.py`: `PACKET_SCHEMA == "bigville/prompt/7"` -> `"bigville/prompt/8"`.
- `tests/test_bigville_backends.py`: the reply text lost `"waiting":false`; the schema assertions `prompt/7` -> `prompt/8`
  (two places).

Not edited: `tests/fixtures/phase054_packet_snapshot.json` (the supervisor regenerates it). The snapshot test fails until then.

Docs: none edited. `docs/AGENT_BACKENDS_PLAN.md` line 24 shows `"waiting": false` in an example reply, and
`docs/FEATURE_PHASES.md` is not mine to edit. Both are for the supervisor.

## Packet snapshot change (for the supervisor)

Regenerated text against `tests/fixtures/phase054_packet_snapshot.json`, with the fixture not written:

```
-    "rules": "... A reply with no major_action carries on as usual. To d...    (fixture: "... Do not set waiting.")
+    "rules": "... (regenerated: the sentence "Do not set waiting." is gone)
-   "consult": 332,      +   "consult": 312,
-   "total": 1821        +   "total": 1801
-   "schema": "bigville/prompt/7",   +   "schema": "bigville/prompt/8",
```

The diff has no other lines.

## Validation

Clean worktree `/tmp/t071f` at `99c29b5` plus this phase. The live tree was checked after copying (see below).

- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)`. (Clean worktree and live tree.)
- `python3 -m domains.check --pack test_hamlet`: exit 0, `ERRORS (0)`, `WARNINGS (0)`.
- `python3 tools/generate_seeds.py --check`: exit 0, `match pack 'bigville' (31 files)`.
- Pack bytes: `python3 tools/export_pack.py --pack <p> --out /tmp/exp71f/<p>` for `bigville` and `test_hamlet`, run on the
  worktree and written to a temp dir (the live packs were not touched). `world/llm_instructions.json`,
  `world/prompt_packet.json` and `pack.json` are byte-identical to the edited files for both packs.
- Targeted tests (14 files, 256 tests, clean worktree): 255 passed, 1 failed. The failure is the packet snapshot,
  expected as above.
- Live tree after copy: `tests/test_phase071f_wait.py`, `tests/test_phase071e_accept.py`, `tests/test_phase059_autopilot.py`:
  62 passed.
- Full suite, clean worktree: `timeout 3600 python3 -m pytest -q -p no:cacheprovider -rf tests`: **6 failed, 3097 passed,
  13 skipped, 27 warnings** in 2236.75 s. Log: `docs/phases/phase071f/full_suite_clean_tree.log`. The failures:
  - `tests/test_phase054_llm_prompt.py::test_the_packet_matches_the_snapshot_for_a_fixed_view`: expected, see above.
  - `test_fix_llm_checkpoint[0]`, `test_package15_resource_social_stress`, `test_phase058_persona`,
    `test_phase060_speech_in`: the four failures the brief lists at HEAD. Run again at HEAD (`git archive` of `99c29b5`):
    `4 failed in 43.79s`, the same four.
  - `tests/management/test_cast_browser.py::test_cast_groups_preview_and_launch_match_actual_world`: the browser flake.
    It failed at HEAD in one run and passed in the clean tree in another (`1 passed`).
  - The skipped count is 13 here, against 6 in phase 071e's run. I did not find the cause.
- Digests (`docs/phases/phase070/compare_digest.py`, town100, seed 305017, simple backend, run on HEAD and on the phase tree):
  - 60 turns: `3a8c1d8cc7b9e84acef84c4c1adb504038f914b6598acc234f6495ae311c695d` on both trees, 0 deaths.
  - 200 turns: `8d5d176fe20169ba83edcb8b6433d9085034facc228073c86d3c8f545bb3bc97` on both trees, 0 deaths,
    `mark_wetness` 50.0 across 100 residents.
  - The JSON files are in this directory (`digest_60_head.json` and so on). The simple backend never sends a `wait` or a
    `waiting` reply, so no digest number could change.

## Changed numbers

- The packet schema is `prompt/8`. The packet's consult text and total size change: `consult` 332 -> 312 and total
  1821 -> 1801 for the fixed view in the snapshot test. No simple-village number changes.
- The LLM village (100 residents) is not run. Its behaviour changes only in the reply shape: a stray `waiting` key is no
  longer read as a wait. A model that still sends `waiting: true` with no major action now carries on as usual.

## Limits

- No real model was run. The LLM paths were exercised with a scripted provider only.
- The TUI pass and the typed-wait path were checked by reading the code and by the probe above. They were not run through
  the terminal.
- The digests cover the simple backend only.
- `last` after a wait is unchanged and stale (see above).

## Open questions

1. **`last` after a wait.** Should a wait publish its own outcome (`wait`, applied) so `last` reads "wait: done"? That
   changes the turn record for every LLM and TUI wait, so it needs a decision. If yes, the wait must reach the game as a
   major `wait` action (the LLM path currently drops it before the game) and the TUI pass must send one too.
2. **Stray key rule.** This phase ignores the key whatever its value. An alternative is to accept only a boolean and
   keep rejecting other types. I chose "ignored" because the contract has no such field.
3. **Phase 071e's open question 2 is answered.** The consult rule no longer says "Do not set waiting."
4. **Live tree state.** The brief's list of other sessions' uncommitted files is out of date. At the start of this phase
   `git status --short` showed only `?? .opencode/` and `?? docs/phases/phase052/full_suite_live_tree_midedit.log`. The
   listed files are now part of `99c29b5`. This phase's copy into the live tree was clean at HEAD for every file it changed,
   including `bigville/game.py`.
5. **Worktree.** `/tmp/t071f` (the phase's clean worktree) is still registered with the repository. Remove it with
   `git worktree remove /tmp/t071f` when it is no longer needed. `/tmp/t071f_base` is a `git archive` copy of HEAD and is not a worktree.

## Supervisor follow-up: `wait` is recorded as the turn's major action

The user's decision ("the major action is wait") answers open question 1. The supervisor made the change on top of the
executor's patch:

- `bigville/backends/llm.py` (`_accept`): a `wait` reply keeps `major_action = wait` in the response, instead of an
  empty response.
- `bigville/game.py` (`_apply_response`): a `wait` from any backend enacts nothing and publishes the outcome
  `{action: "wait", applied: true, reason: ""}` through `world._publish_outcome`, so `last` shows the wait, not an older
  outcome. No refusal is logged.
- `bigville/tui/app.py`: the TUI's pass words (`wait`, `.`, `stop`, `z`) send `major_action: wait` instead of an empty
  turn. The narration still says "Time passes."; `last` reads "wait: done".
- `major_action: null` (carry on as usual) is unchanged.

Changed tests (old -> new):
- `tests/test_phase059_autopilot.py::test_a_reply_with_no_action_carries_on_as_usual_and_wait_idles`: a wait's
  `major_action is None` -> `major_action.action == "wait"`.
- `tests/test_phase071f_wait.py`: the wait reply's `major_action is None` -> `"wait"`; `last_outcome is None` after a
  wait -> the wait recorded as done with no refusal (two tests, renamed to say so).

Affected test files: 265 passed. The simple village does not propose `wait`, so the digests are unchanged (checked by
the supervisor's verify run).
