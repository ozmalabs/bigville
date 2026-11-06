# Phase 055: the LLM backend, stage 3: operations

## Summary

A town of LLM residents can now run concurrently, record and replay its calls, and call OpenCode Go through a
stdlib HTTP provider. The call cap already yielded the autopilot's action (Phase 059); this phase makes the cap
check thread-safe and extends the counts with cost, tokens and per-day figures.

- Concurrency: backends marked `concurrent` decide in a bounded thread pool (default 4 workers). The game builds
  every such context first and applies results in registration order. A slow fake provider runs faster
  concurrently, with identical results.
- Transcripts and replay: an append-only JSONL file per run. A replay provider serves recordings by turn, actor and
  prompt hash. A changed prompt raises `ReplayMismatch`, which the backend counts as a provider error and falls back
  on.
- Providers: stdlib `urllib` OpenAI-compatible client, OpenCode Go settings from the environment, a stdlib `.env`
  reader that fills unset variables only. Contributor models are refused by name. Keys are redacted from errors,
  logs and transcripts.
- Mixed town: `bigville/llm_scenario.py` builds a town with N LLM residents among simple ones. The test runs 3 LLM and
  97 simple residents for 100 turns on a recording fake provider: 38 calls.
- Reports: `llm_report` gains cost, tokens, provider call time and per-day figures, per resident and in total.
- The core imports with no network and no third-party module (subprocess test).

Self-tests: `bigville` ERRORS (0), WARNINGS (0); `test_hamlet` ERRORS (0), WARNINGS (0).
Full suite: 1609 passed, 3 skipped, 7 failed. The 3 Ocelot adapter failures are the known ones. The 4 Phase 057 TUI
failures appear only on the live tree, and they also fail with this phase's `game.py` hunks removed (see Validation).

Simple-backend behaviour is identical. A 60-turn town100 run with HEAD plus this phase's `game.py` hunks matches a
clean HEAD run and `docs/phases/phase054/behaviour_head.json` on all 14 compared fields.

## Changes

### Created

- `bigville/concurrency.py`: `decide_pooled({actor: (backend, context)})` runs `decide` in a `ThreadPoolExecutor` and
  returns results in dict order. `pool_workers` takes the largest `concurrency` attribute (default `DEFAULT_WORKERS = 4`).
- `bigville/llm_transcript.py`: `prompt_hash` (SHA-256 of the canonical JSON of the payload), `call_provider` (the
  Phase 031 call forms, plus `complete(payload, meta=...)` for providers with `wants_meta`), `Transcript` (JSONL
  append under a lock, passed through a `redact` function), `RecordingProvider`, `ReplayProvider` (keyed by turn,
  actor and prompt hash; repeated identical calls replay in order), `ReplayMismatch`, `RecordedError`,
  `read_transcript`.
- `bigville/providers/__init__.py`: exports.
- `bigville/providers/dotenv.py`: `parse_dotenv`, `load_dotenv(path, environ)` (fills unset variables only; a missing
  file is not an error).
- `bigville/providers/openai_compatible.py`: `OpenAICompatibleProvider` (urllib; `User-Agent: bigville/0.55.0`,
  `x-opencode-session: <run id>-<resident>`, bearer key; JSON mode tried first and recorded per model in
  `json_mode_status`; retries with backoff and `Retry-After` for 429, 5xx and network errors; no retry for other 4xx;
  `RateLimiter`; `last_cost`, `last_usage`, `last_model` per thread; `redact`; `capabilities()`). `allowance_cost`.
- `bigville/providers/opencode_go.py`: `OpenCodeGoSettings` (the key is `repr=False`), `from_environment`,
  `validate_model` (refuses names containing "contributor"), `validate_base_url` (https, or http to loopback only),
  `build_provider`, `build_budget` (the pack's per-day call cap plus `BIGVILLE_LLM_BUDGET`), `build_transport`.
- `bigville/llm_scenario.py`: `build_llm_town(provider, llm_residents=3, ..., settings=None)`, `choose_llm_residents`
  (the first N names in sorted order), `step_record`, `RunDigest` (SHA-256 over per-turn proposals and results).
- `tests/llm_stub.py`: `StubServer` (loopback 127.0.0.1, port 0, scriptable responses, records requests), `completion`,
  `FakeProvider` (thread-safe, optional delay, cost, error, `wants_meta`), `varied_reply`.
- `tests/test_phase055_providers.py` (23 tests), `tests/test_phase055_transcript_replay.py` (5),
  `tests/test_phase055_concurrency.py` (6), `tests/test_phase055_mixed_town.py` (1, about 3 minutes),
  `tests/test_phase055_core_imports.py` (2).
- `tests/live/test_live_opencode.py` (1 test, skipped unless `BIGVILLE_LIVE_LLM=1` and a key is present; not run).
- `docs/phases/phase055/`: this report, `measure_phase055.py`, `concurrency.json`, `sample_transcript.jsonl`, the
  behaviour JSON and logs, the self-test outputs, `full_suite.log`, and `log_measure_phase055.txt`.

### Changed

- `bigville/backends/llm.py` (LLM tract file, not shared): class attributes `concurrent = True` and
  `concurrency = DEFAULT_WORKERS`. `_call(payload, meta)` passes the turn, actor, attempt and period. `_ask` uses
  `budget.reserve(...)` (check and record in one step). `_record_cost(day, started)` books spend, tokens and call time
  per resident and per day. `decide` and `react` set the day bucket. `llm_counts` adds `cost`, `tokens_in`,
  `tokens_out`, `tokens_reasoning`, `call_latency_ms_total` and `by_day`.
- `bigville/backends/autopilot.py` (LLM tract file, not shared): `CallBudget` takes a lock. It gains `reserve(resident,
  day)`, which checks and records a call atomically. `refusal`, `record_call` and `record_cost` keep their behaviour and
  now lock. The docstring explains the shared-budget guarantee.

### Shared-file hunks (anchors are unchanged lines in the working tree)

`bigville/game.py` (four hunks; the file also carries other sessions' uncommitted work):

1. Import. Anchor: `from .backends.protocol import communication_capabilities`. Insert after it:
   `from .concurrency import decide_pooled`.
2. `BigvilleGame.step()`. Anchor: `        responses = {}` followed by `        for actor, backend in self.backends.items():`. Insert
   between them: `        deferred = {}  # Phase 055: ...` (one line).
3. In the same loop, before `                response = backend.decide(context)`, which follows the Phase 059
   `context.backend_state["continuation_interrupted"] = reason` block. Insert:
   `if getattr(backend, "concurrent", False):` with `deferred[actor] = (backend, context)` and `continue`.
4. Before `        # This opens the turn and advances the physical environment, but does`. Insert the pooled block: call
   `decide_pooled(deferred)`, copy `continuation_interrupted` onto each response, append to `responses`, and return
   `waiting` for a waiting response (as the loop does).

With no concurrent backend, `deferred` is empty and `decide_pooled({})` returns `{}`. The non-concurrent path is
unchanged.

`bigville/reporting.py` (one replaced function, plus one new helper):

5. `llm_report`: the docstring gains a Phase 055 paragraph. Per resident, the row gains `**_spend_row(counts)`
   (`call_latency_ms_total`, `cost`, `tokens_in`, `tokens_out`, `tokens_reasoning`, `per_day`). The total gains the
   same sums and a merged `per_day`. Anchor: `    total.update({"decisions": decisions, "turns": turns, ...` is
   unchanged; the new loop sits after it. The new `_spend_row` helper is inserted between `llm_report` and `def game_report`.

No change to `domains/`, `packs/`, `bigville_entities.py` or `pack.json`. The tunables (key, URL, model, timeouts,
retries, rate, concurrency, budget) are operational, so they live in the environment and in
`bigville/providers/opencode_go.py`, not in world data.

### Test whose numbers changed

- `tests/test_phase031_llm_backend.py::test_llm_report_ignores_backends_without_llm_counts`: the expected dict gained the
  new keys (`call_latency_ms_total`, `cost`, `tokens_in`, `tokens_out`, `tokens_reasoning`, `per_day`), all zero or empty.
  Reason: the report shape grew (item 5). No assertion was weakened.

No other existing test was edited.

## Validation

All commands ran in `/home/matt/ozmadev/bigville`.

- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0). Output: `selftest_bigville.txt`.
- `python3 -m domains.check --pack test_hamlet`: exit 0, ERRORS (0), WARNINGS (0). Output: `selftest_test_hamlet.txt`.
- Phase 055 tests, `python3 -m pytest -q -p no:cacheprovider tests/test_phase055_*.py`: all pass (38 tests).
  The live test skips. `pytest --collect-only tests/live` collects it, and it skips without `BIGVILLE_LIVE_LLM=1`.
- Existing LLM tests, `tests/test_phase031_llm_backend.py tests/test_phase059_autopilot.py tests/test_phase054_*.py
  tests/test_bigville_backends.py tests/test_bigville_reporting.py tests/test_bigville_game_api.py`: 153 passed, 1 skipped,
  1 failed. The failure was the Phase 031 report-shape test (see Changes). After the fix, the report tests in
  `tests/test_phase031_llm_backend.py` passed, and the full suite below passed all of the LLM tests.
- Full suite, `timeout 1800 python3 -m pytest -q -p no:cacheprovider` (log `full_suite.log`, 1084 s):
  **1609 passed, 3 skipped, 7 failed.**
  - Ocelot adapter, 3 failures, the known ones:
    `test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`,
    `test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`,
    `test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`.
    All fail with `ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`.
  - Phase 057 TUI, 4 failures, `test_phase057_tui.py`: `test_over_http_a_menu_row_is_bound_by_the_server_and_the_world_enacts_it`,
    `test_over_http_walking_to_a_known_place_sends_the_rows_destination`,
    `test_over_http_a_reaction_is_delivered_to_the_holder`,
    `test_the_server_refuses_a_bad_reply_and_a_reaction_nobody_is_waiting_for`.
    Attribution: the file alone gives 4 failed, 44 passed on the live tree. Those tests also fail on a copy of the live
    tree with this phase's `game.py` hunks removed (4 failed, 44 passed). They pass on a clean `git archive HEAD` copy
    (48 passed) and on HEAD with this phase's `game.py` hunks applied (48 passed). The cause is uncommitted work in
    the shared tree (the server and game code), not this phase.
- Simple-backend behaviour (`PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label ... --turns 60`,
  town100 seed 305000):

  | tree | move | utterances | hunger_mean_end | vs `phase054/behaviour_head.json` |
  |---|---|---|---|---|
  | clean HEAD (`git archive HEAD`) | 3333 | 300 | 2.4309 | identical, 14 of 14 fields |
  | HEAD + this phase's `game.py` hunks | 3333 | 300 | 2.4309 | identical, 14 of 14 fields |
  | live tree without this phase's `game.py` hunks | 3526 | 285 | 0.4442 | differs (other sessions' work) |
  | live tree with this phase's hunks | 3526 | 285 | 0.4442 | differs (other sessions' work) |

  The last two rows are identical to each other, so the hunks change nothing on the live tree. Files:
  `behaviour_clean_head.json`, `behaviour_head_plus_055_hunks.json`, `behaviour_live_tree_*.json`, and their logs.
- Mixed town, 3 LLM and 97 simple residents, 100 turns (test and `measure_phase055.py`): **38 provider calls**
  (12, 12 and 14 per LLM resident). Consults by reason: `spoken_to` 61, `task_failed` 21, `check_in` 3,
  `routine_boundary` 3. Fallbacks: `call_cap` 50, none by provider error. The LLM totals: 88 decisions (38 accepted,
  50 fallbacks), 79 autopilot turns, 16 carry-ons, 10 waits. About 133 of the 300 LLM resident-turns were on a held
  plan and never reached `decide` (inferred: 300 - 167). Wall time 179 s in the measurement run.
- Concurrency, `docs/phases/phase055/concurrency.json`, with a 0.3 s delay per decision:

  | case | seconds |
  |---|---|
  | pool only, 8 decisions, 1 worker | 2.401 |
  | pool only, 2 workers | 1.202 |
  | pool only, 4 workers (default) | 0.601 |
  | pool only, 8 workers | 0.301 |
  | whole town, 8 LLM residents, 2 turns, sequential | 8.307 |
  | whole town, 4 workers | 5.651 |
  | whole town, 8 workers | 5.321 |

  The whole-town digests are equal (12 calls each). The world step takes about 1.6 s per turn on the 100-resident
  town (measured: 16.2 s for 10 simple-only steps), so the whole-turn gain is smaller than the pool gain. The speed
  test in the suite asserts a ratio below 0.75; the run recorded 0.69.
- Transcript and replay: a recorded run replays with the same `RunDigest` and no mismatch. A changed prompt is reported
  as `replay mismatch at turn ...`, counted as `provider_error`, and the game still advances.
- Key redaction: the full stub run (HTTP 500 that echoes the key, a reply that echoes the key) leaves no key in the
  transcript, the captured logs or stdout and stderr. The transcript holds `[redacted key]`.
- Core imports: a subprocess with socket connections blocked imports the core with no third-party module, and
  `bigville.providers` is not loaded.

### Sample transcript line

From `docs/phases/phase055/sample_transcript.jsonl` (fake key `sk-fake-phase055-…`; the prompt is shortened here):

```json
{"actor": "Adelina Gorse", "attempt": 0, "cost": 0.0021, "latency_ms": 7.839, "model": "glm-5.3-flash",
 "prompt": "<13187 characters, omitted here>",
 "prompt_hash": "a94aaa24867f15c3cff9835b4861a0d4d954316b297d9bc8c8d2e2e1fcfbbe83",
 "reply": "{\"major_action\": {\"action\": \"rest\", \"params\": {}}, \"utterances\": []}",
 "run_id": "sample55", "schema": "bigville/llm-transcript/1",
 "tokens": {"input": 120, "output": 40, "reasoning": 3}, "turn": 0}
```

A reply that echoes the key is stored redacted:
`"reply": "{... \"text\": \"my key is [redacted key]\"}"`. The request's session header is not in the transcript. The
log line for the same call reads `llm call model=glm-5.3-flash session=sample55-Adelina Gorse status=200 attempt=0 latency_ms=...`.

## Limits

- No real OpenCode Go call was made, and no live test was run. The stub follows the chat-completions shape the plan
  records, and the `usage.opencode.allowance` shape is unverified (see open questions).
- These are APPROX values, not sourced from the plan: request timeout 60 s, 3 retries with 1 s doubling backoff, 0.25 s
  minimum interval between requests, `max_tokens` 4096, concurrency 4. The Contributor refusal follows the plan's
  note. The loopback-only plain-http rule is this phase's own choice, so keys cannot go over clear text to other hosts.
- The `json_mode` status becomes `accepted` when a 200 comes back with the parameter. It does not prove the model
  produced JSON in that mode. The backend's fenced-JSON parser still runs on every reply.
- The spend cap is checked before each call and recorded after it. With N concurrent calls, up to N - 1 extra calls can
  start after the cap is reached. The test checks this bound.
- With no `BIGVILLE_LLM_BUDGET`, there is no spend cap, only the pack's per-resident daily call cap (12).
- `call_cap` and `spend_cap` refusals count in `failures` and `fallbacks_by_cause`, as Phase 059 specified. They are
  not provider failures, and the report does not separate them.
- "Per period" in the report means the calendar day, the period the call budget uses. The game's `ticks_per_period`
  periods are not separately counted.
- Replay matches the recorded call's cost and usage. It cannot check that a live provider's metadata is stable.
- The concurrency speed test is timing-based. The bound (0.75) leaves room, but a loaded machine can still change the
  ratio.
- The mixed-town test takes about 3 minutes. The full suite took 1084 s on this run, with other sessions active.
- The mixed-town run used the default simple profile for every resident's autopilot.
- `packet_system` in `prompts.py` is set lazily. Two threads may compute it, and both get the same string. This phase
  did not change that file.

## Open questions

1. What is the shape of `usage.opencode.allowance` in a real response (a cost per call, a remaining balance, or a
   dict)? The provider reads a number or a dict with `cost`, `used` or `spent`, and counts anything else as unreported.
   A live check of one call would settle it.
2. Should a live run require `BIGVILLE_LLM_BUDGET`? Right now no spend cap is set unless the variable is given.
3. Should `call_cap` and `spend_cap` refusals move out of `failures` in the report?
4. Are the APPROX defaults right: 60 s timeout, 3 retries, 0.25 s interval, `max_tokens` 4096, concurrency 4?
5. Should "per period" mean the game's period (`ticks_per_period`) rather than the calendar day?
6. Commit: `bigville/game.py` and `bigville/reporting.py` also carry other sessions' uncommitted changes. The commit
   should take only this phase's hunks listed above.
7. The whole-town gain is limited by the world step (about 1.6 s per turn at 100 residents). Parallel world work is
   out of scope; say if it is wanted.
