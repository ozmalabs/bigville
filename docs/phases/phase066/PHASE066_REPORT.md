# Phase 066: the LLM harness: continue the session, keep the memory, keep the whole log

## Summary

An LLM resident now continues one conversation with its model. Each resident has a thread: the system text once,
then per consult a user message (the full packet, or the changes since the last consult) and the reply's content.
The packet is still built from the agent view, so the Phase 054 words-only rule holds. A full packet is sent every
`full_every` consults, and when a thread passes its character budget a new thread starts with the full packet
(persona, usual day, lessons and notes) under a new session id.

The complete log is new. Every provider call attempt, and every budget refusal, is one line in a hash-chained JSONL
file (`bigville/llm_log.py`). The line keeps the messages as sent and the whole response, reasoning fields included,
untruncated. Only the API key is replaced. The provider layer no longer drops fields: `complete()` returns a
`ProviderResult`, a `str` of the reply content that carries the whole call on `.result`. Callers that expect text
work unchanged.

Thinking reaches the log only. It is not in a message, the packet, the response, the backend or held state, the
world report, or the replay key. A test with a loopback stub checks each of these.

Stop and resume: `LLMBackend.to_dict()` and `from_dict()` hold the thread, the counts, the consult gate, the autopilot's
goals and choices, and the call budget. A town stopped at turn 3 and resumed from JSON gives the same run digest and
the same messages to the model as an uninterrupted run (test). The character (memories, held frames) is not in that
state; the game checkpoint holds it, and that checkpoint currently refuses LLM residents (see Memory below).

Simple-backend behaviour is unchanged: the 60-turn town100 run matches a fresh `git archive e8ffe69` run on all 14
compared fields. Self-tests: 0 errors and 0 warnings for both packs.

## Changes

### Created

- `bigville/providers/result.py`: `CallResult` (a frozen record of one call: content, the reasoning fields, finish
  reason, model, response and request ids, usage, cost, headers, body, request, retry attempts, timings) and
  `ProviderResult` (a `str` subclass with `.result`).
- `bigville/llm_log.py`: `LLMLog` (append-only, hash chain, optional gzip per record, head file `<log>.head.json`),
  `verify_log`, `read_log`, `attach(backends, log)`, `LogCorrupt`, `scrub`, `digest`.
- `bigville/backends/thread.py`: `ConsultThread` (messages, consult counts, last state, session id, to_dict and
  from_dict), `state_changes` (the delta between two packet states), `message_text`, `canonical`, and the defaults
  `DEFAULT_THREAD_CHARS = 60000` and `DEFAULT_FULL_EVERY = 6` (both APPROX).
- `tests/test_phase066_session_log.py`: 17 tests (loopback stub and in-process fakes only).
- `docs/phases/phase066/`: this report, `phase066_probes.py` (sample log and checkpoint probes),
  `sample_llm_log.jsonl`, `behaviour_head.json`, `behaviour_mine.json`, their logs, the self-test outputs, and
  `full_suite_live.log`.

### Rewritten (own files, LLM tract)

- `bigville/providers/openai_compatible.py`: `complete(payload, meta)` returns a `ProviderResult`. `_parse` returns it
  and reads `reasoning_content`, `reasoning` and `reasoning_details` from the message or the choice, wherever they
  are. `_request` returns the response headers and records each try (status, latency, delay, redacted error) in
  `attempts`. `last_call` (per thread) holds the whole record of the last call, a failed one included. The session
  header is `run id + meta["session"]` (the thread's id), or the actor's name as before. A payload with a `messages`
  list is sent as those messages (`messages_of`). Other payloads are split as before.
- `bigville/backends/llm.py`: the consult path (thread, delta or full packet, compaction, repair as one user message),
  logging, `to_dict` and `from_dict`. Phase 031, 054 and 059 behaviour is kept (autopilot, caps, repair, fallbacks,
  reactions, lesson merge, counts).

### Edited

- `bigville/llm_transcript.py`: `prompt_hash` keys a payload with `messages` on its messages and repair errors
  (`thread_key`, `thread_hash`). A payload without messages keys as before. `ReplayProvider` names the first differing
  message when no recording matches: it compares against the recording with the longest matching prefix
  (`first_message_difference`).
- `bigville/providers/__init__.py`: exports `CallResult` and `ProviderResult`.
- `bigville/reporting.py`, `llm_report` region only (see hunks).
- `packs/bigville/world/prompt_packet.json` and `packs/test_hamlet/world/prompt_packet.json` (identical): a new key
  `PROMPT_PACKET.thread` with five texts (`first`, `start`, `full`, `delta`, `repair`). Both files equal the exporter's
  output (`tools/export_pack.py`, checked for both packs). The manifests are unchanged, because the table is in an
  existing file.

### Shared-file hunks

None. No file outside this phase's write scope was edited. For transparency, the `reporting.py` hunks, all inside the
LLM region, are these (anchors are unchanged lines of HEAD):

1. `llm_report`, per-resident row: `**_spend_row(counts),` now ends with a comma and `**_thread_row(counts)}` follows.
   Anchor: `"last_error": str(counts["last_error"]),`.
2. `llm_report`, totals: a loop over `THREAD_SUM_KEYS` and `thread_chars_max`, before the `return`. Anchor:
   `for day, bucket in sorted(per_day.items())}`.
3. New module-level `THREAD_SUM_KEYS` and `_thread_row(counts)`, between `llm_report` and `_spend_row`. Anchor: the
   `return {"residents_count": ...}` line of `llm_report`.

### Tests whose numbers or assertions changed

`tests/test_phase031_llm_backend.py`, two edits:

1. `test_repair_request_carries_the_original_prompt_and_only_the_error_messages`: the equality with the first request
   now ignores `messages` and `thread`, and checks that the repair request's messages are the first request's messages
   plus one more message. Reason: the repair is one extra message in the thread (Phase 066). The marker check (the
   failed output is not echoed) is unchanged.
2. `test_llm_report_ignores_backends_without_llm_counts`: the expected total gained `threads`, `compactions`,
   `full_consults`, `delta_consults` and `thread_chars_max`, all 0. Reason: the report shape grew.

No other existing test was edited. No assertion was removed or weakened.

## Validation

All commands run in `/home/matt/ozmadev/bigville` unless noted. The tree is shared, and its uncommitted work from
other sessions was present throughout.

- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0). Output: `docs/phases/phase066/selftest_bigville.txt`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, ERRORS (0), WARNINGS (0). Output: `selftest_test_hamlet.txt`.
- `python3 tools/export_pack.py --pack bigville --out <tmp>` and `--pack test_hamlet`: the written
  `world/prompt_packet.json` is byte-identical to the repository file in both packs.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase066_session_log.py`: 17 passed.
- Existing LLM tests (`test_phase031_llm_backend.py`, `test_phase054_llm_prompt.py`, `test_phase054_actionable.py`,
  `test_phase059_autopilot.py`, `test_bigville_backends.py`, `test_phase055_providers.py`,
  `test_phase055_transcript_replay.py`, `test_phase055_concurrency.py`, `test_phase055_core_imports.py`,
  `test_phase018_llm_instructions.py`): all pass except the snapshot test below.
- Full suite on the live tree, `timeout 2400 python3 -m pytest -q -p no:cacheprovider` (log `full_suite_live.log`,
  1240.7 s): **8 failed, 1644 passed, 3 skipped.** The failures and their attribution:
  - `test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
    `test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
    `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`.
    Error: `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`. Earlier phases report the same
    three. On a rebuilt clean copy (`git archive e8ffe69`, this phase's files applied, the Ocelot test files and the
    sibling checkout beside it) all three fail. Two report `No module named 'worlds.bigville_ocelot_adapter'` (the
    error above). The third also hits an `ImportError` (`_checkpoint_decode` missing from HEAD's `runtime.py`) from an
    untracked module I copied in for the test; that is an artefact of the copy, not of this phase.
  - `test_phase057_tui.py`: `test_over_http_a_menu_row_is_bound_by_the_server_and_the_world_enacts_it`,
    `test_over_http_walking_to_a_known_place_sends_the_rows_destination`,
    `test_over_http_a_reaction_is_delivered_to_the_holder`,
    `test_the_server_refuses_a_bad_reply_and_a_reaction_nobody_is_waiting_for`. Not in this phase's files. On the
    clean copy, `test_phase057_tui.py` passes (49 passed, with the snapshot test below). The live tree has other
    sessions' uncommitted edits to `server.py` and `game.js`.
  - `test_phase054_llm_prompt.py::test_the_packet_matches_the_snapshot_for_a_fixed_view`: the system text is 9
    characters longer on the live tree (4930, snapshot 4921). The difference is another session's uncommitted
    `strike` action in `packs/bigville/world/major_actions.json` (`git diff` shows four added lines). It is not in this
    phase's packet text, and the clean copy passes it.
  - The mixed-town run (`test_phase055_mixed_town.py`) passed in the full run.
- Simple-backend behaviour (`PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --turns 60`, town100
  seed 305000): a fresh `git archive e8ffe69` run (`behaviour_head.json`) and this phase's files applied to that
  archive (`behaviour_mine.json`) agree on all 14 compared fields (`action_counts`: eat 5, move 3526, none 1065,
  rest 1334, sleep 55, work 15; 285 utterances; hunger mean 0.4442; per-actor digests). The move count (3526) differs
  from the 3333 in the Phase 055 and 059 reports; those were for earlier commits. I did not trace the difference.
- Checkpoint probe (`python3 docs/phases/phase066/phase066_probes.py checkpoint`): a cheap-only town saves; a town with one
  LLM resident raises `TypeError: unsupported backend LLMBackend; supply an explicit backend checkpoint adapter`.
- Sample log probe (`python3 docs/phases/phase066/phase066_probes.py sample-log`): 2 records, chain ok, no problems,
  fake key absent from the file, `[redacted key]` present.
- Not run: any live provider, the 100-resident LLM town, and any real network call. No `.env` was read.

### Sample log record

From `docs/phases/phase066/sample_llm_log.jsonl`, written by the probe against the loopback stub. The fake key is
`sk-fake-probe-…`. Messages are cut to 160 characters, and the body and the thinking are shortened here. The file holds
them whole.

```json
{"seq": 1, "prev": "0000000000000000...", "hash": "9a45b9cfa64751c2...",
 "record": {"kind": "call", "run_id": "probe66", "resident": "Adelina Gorse", "turn": 0, "thread": "Adelina Gorse/t0",
  "thread_index": 0, "session": "Adelina Gorse", "consult_no": 1, "mode": "full", "compacted": false,
  "consult_reason": "check_in", "attempt": 0, "outcome": "accepted", "fallback_cause": null, "errors": [],
  "thread_hash": "cba005c50eec438edd3957a805ebbfdc915eba05085dfac1b47d450526bba023",
  "messages": [
    {"role": "system", "content": "You are one resident of Bigville. Bigville is a village ...[4930 chars]"},
    {"role": "user", "content": "This is the start of your session in Bigville. Here is your state in full. ...[8285 chars]"}],
  "response": {"ok": true, "content": "{\"major_action\": {\"action\": \"rest\", \"params\": {}}, \"utterances\": [{\"text\": \"key [redacted key]\"}]}",
    "reasoning_content": "The bread is nearly gone and the mill is closed, so I rest and think about the flour. The bread is ...[567 chars in total, stored whole]",
    "reasoning": null, "reasoning_details": null, "finish_reason": "stop", "model": "glm-5.3-flash",
    "response_id": "stub-1", "request_id": "probe-0",
    "usage": {"prompt_tokens": 120, "completion_tokens": 40, "completion_tokens_details": {"reasoning_tokens": 214},
              "opencode": {"allowance": 0.002, "list_cost": 0.002}},
    "cost": 0.002, "headers": {"x-request-id": "probe-0", "Content-Type": "application/json", "...": "..."},
    "body": "(the whole parsed response)",
    "request": {"model": "glm-5.3-flash", "session": "probe66-Adelina Gorse", "max_tokens": 4096, "response_format": true, "messages": 2},
    "attempts": [{"attempt": 0, "status": 200, "latency_ms": 11.717}], "json_mode": "accepted",
    "started_at": "2026-11-06T13:11:18.835+00:00", "latency_ms": 11.749},
  "retries": [{"attempt": 0, "status": 200, "latency_ms": 11.717}],
  "timings": {"latency_ms": 12.252, "provider_latency_ms": 11.749, "started_at": "2026-11-06T13:11:18.835+00:00"}}}
```

Thinking sample (the first 300 characters of the stored `reasoning_content`, from the same record):
"The bread is nearly gone and the mill is closed, so I rest and think about the flour. The bread is nearly gone and the
mill is closed, so I rest and think about the flour. ..." The last sentence of the stored text is `My key is [redacted key];
I must not write it down.`, with the key replaced and the rest untouched.

### Threads and thinking in the report

`llm_report` now carries, per resident and in total: `threads` (threads started, the first plus one per compaction),
`compactions`, `full_consults`, `delta_consults`, `thread_chars_max`, and per resident `thread_length` (consults in the
current thread) and `thread_chars`. `tokens_reasoning` (the provider's reasoning-token count) is in the report as
`thinking_tokens` per resident. The probe run with a 9000-character budget showed 3 threads and 1 compaction for two
residents over 3 turns.

## What survives a checkpoint and a restart

Checked in the other stream's files (read only):

- `game_persistence.save_game_checkpoint` calls `_backend_checkpoint`, which handles the simple, human and Ocelot
  backends and raises `TypeError` for any other type. An `LLMBackend` is refused, so a game with one LLM resident cannot
  be saved. The probe confirms this on the live tree.
- The character is saved with its memories (lessons, notes, place beliefs, plans) and held frames, by
  `_character_to_checkpoint`. That is the only LLM-relevant state a checkpoint would carry today, and it is saved only
  if the whole save succeeds, which it does not for an LLM resident.
- Not in any checkpoint: the thread (the model's conversation), the consult gate's state, the autopilot's goals and last
  choice (the simple branch saves these for the simple backend type only), the call budget's daily counts and spend (a
  restart would reset the daily call cap), the counts and report totals, and the log's position.
- The log is a file. It survives a restart, and `LLMLog` reopens it after verifying the chain.

Backend level (new, tested): `to_dict()` and `from_dict()` carry the thread, counts, gate, autopilot and budget. Stop and
resume at turn 3 of six reproduces the uninterrupted run exactly (`test_a_run_stopped_and_resumed_...`). A round trip
through JSON is equal to the original state (`test_the_backend_state_round_trips_...`).

To make a checkpoint keep an LLM resident, the other stream needs a `kind: "llm"` branch in `_backend_checkpoint` and
`_build_backend` that stores `backend.to_dict()` and restores with `LLMBackend.from_dict(data, character, provider)`. The
provider is not in the state and must be supplied again at load. I did not edit those files.

## Limits

- No live provider. The OpenCode Go response shape for reasoning fields is not verified. The provider reads
  `reasoning_content`, `reasoning` and `reasoning_details` from the message or the choice. Whatever the response carries
  is kept whole in `body`, so no field is dropped even if it is named differently.
- `DEFAULT_THREAD_CHARS` (60000) and `DEFAULT_FULL_EVERY` (6) are APPROX. Characters stand in for tokens. They are
  constructor arguments, not environment settings.
- The log writes the full messages of each call, so each record carries the thread so far. Log size grows with the
  square of the thread length. Gzip compresses it. This was not measured on a long run.
- The log is written only when a log is attached: `LLMLog` plus `attach(game.backends, log)`, or `backend.log = ...`.
  `create_game` and `build_llm_town` do not attach one (`bigville/api.py` is out of scope). A production run must attach
  it.
- The head file catches a log cut short at the end. A log and its head file both replaced are not detected: the chain
  has no signature.
- A budget refusal makes no call and is logged as `kind: "refused"`. A consult that a refusal stops logs no call record.
- `to_dict` does not hold the character. The shared `CallBudget` is restored by each backend that is resumed, so the
  last restore wins. The values are equal when all backends are dumped at the same point.
- `ReplayProvider` names the first differing message only when the recording kept its prompts (the default). Replay keys
  of LLM calls changed: a Phase 055 transcript of an LLM run recorded before this phase does not replay.
- Thinking is stored, not fed back. A model does not see its own earlier reasoning (by the brief's out-of-scope note).
- The 17 new tests use fakes and the loopback stub. The concurrency speed test and the mixed-town test passed in the
  full run, but their timings were not measured separately.

## Open questions

1. Attach a log by default in `create_game` or `build_llm_town`? That needs a log path argument and an edit to
   `bigville/api.py`, which is out of scope. The brief's "complete log" is only complete with an attached log.
2. Approve a `kind: "llm"` branch in the other stream's checkpoint (see Changes). Until then no game with an LLM
   resident can be checkpointed.
3. Should thinking ever be fed back to the model? The brief says no for now. The log holds it either way.
4. Are the APPROX budgets right (60000 characters, a full packet every 6 consults, 2000 reserved for the reply)?
5. The repair is one user message with the fixed errors, and the failed reply is not echoed. This keeps the Phase 031
   rule. The brief's "one extra message" is read this way.
6. The five `PROMPT_PACKET.thread` texts are not checked by `domains/prompt_packet_check.py`, which is not in this
   phase's scope. A presence check would be a small addition.
7. For long runs, should the log keep each thread's messages once and reference them by hash, instead of repeating
   them in every record?

## Steering (steer-8b63b5a4-7611-428e-a99a-b0e97d302634)

The harness parts of the steering message (continued session, memory, the complete log with thinking) are this phase.
The speech, perception and TUI parts are planning work. Programme E already has briefs for them (Phases 060 to 065
for speech and faculties, 067 for the TUI, 068 for graph memory, parked until 056 has data). Those plans are in
`docs/FEATURE_PHASES.md`, which is outside this phase's write scope, so I did not add or change any phase. Whether the
speech parser needs a small model call is an open design question for the supervisor, and the Programme E text already
states the cheapest-first order.
