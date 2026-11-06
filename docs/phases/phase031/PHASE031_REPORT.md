# Phase 031: Register and harden the LLM backend (stage 1)

## Summary

The `"llm"` kind can be built by `create_game`, with a provider supplied by the caller. Core imports no vendor SDK and makes no network call. Provider output is validated against the pack's `PROMPT_RESPONSE_FIELDS`. A parse or validation failure gets one repair call that carries only fixed error messages. After a second failure, or after a provider exception, the resident takes an idle turn and the failure is counted. `decide` does not raise for provider, parse or validation errors. Counts reach the game-level report beside the Phase 021 refusals.

Tests use a fake provider only. Self-test: 0 errors, 0 warnings. Full suite: 994 passed, 3 failed, 2 skipped. The 3 failures are the Ocelot adapter tests, which fail the same way with the Phase 031 files reverted (see Validation).

## Changes

- `bigville/backends/llm.py` (rewritten, same public class and provider protocol):
  - `LLMBackend.decide` runs one provider call, then up to `MAX_REPAIRS = 1` repair call. The repair request is the original prompt dict plus `"repair": {"errors": [...]}`. The errors are fixed strings, such as `major_action.params must be an object`. No model output is echoed.
  - `validate_response(parsed, fields)` checks unknown keys against `PROMPT_RESPONSE_FIELDS`, and the types of `major_action`, `continuation`, `utterances`, `memory_updates` and `waiting`. It does not check whether an action is legal; the world does that.
  - `_fail` returns `ActorResponse(major_action=None, waiting=False)`, which is an idle turn, and counts the failure.
  - Provider exceptions are caught, counted as `provider_errors`, and not repaired. An unexpected exception in the prompt or decision path is caught by an outer guard and counted with reason `internal_error`.
  - `safe_error(text)` collapses whitespace, truncates to 160 characters, and replaces the text with a `[redacted ...]` marker when it matches a credential pattern (`authorization`, `bearer`, `api_key`, `secret`, `token`, `sk-`, `key=`, or a run of 28 or more letters and digits).
  - Cumulative counts in `last_backend_state` and in `dump_held_state().backend_state`: `calls` (provider calls, repairs included), `repairs_used`, `repaired_successes`, `successes`, `failures` (idle fallbacks), `provider_errors`, `invalid_outputs`, `latency_ms_total`, `last_error`. Per decision: `outcome` (`ok`, `repaired`, or `idle_fallback`), `attempts`, and `reason` on failure. The existing keys (`prompt_schema`, `prompt_hash`, `response_hash`, `latency_ms`) are kept and unchanged for a first-call success.
  - `llm_counts` property returns a copy of the cumulative counts.
- `bigville/api.py`:
  - `create_game(..., llm_provider=None)`. The provider is used for every resident whose kind is `"llm"`, whether from `default_backend="llm"` or from a scenario actor's `backend`.
  - `llm_backend_factory(provider)` returns a `backend_factories` entry, so `create_game(default_backend="llm", backend_factories={"llm": llm_backend_factory(p)})` also works.
  - Passing both `llm_provider` and `backend_factories["llm"]` raises `ValueError`. An `"llm"` kind with neither raises `ValueError`.
  - `LLMBackend` is imported from `bigville.backends`.
- `bigville/reporting.py`: appended `llm_report(backends)` (per-resident counts, decisions, mean latency per decision, last error, and totals) and `game_report(game)`. `game_report` returns `game.world.report()` plus a top-level `"llm"` key beside the existing `"refusals"` key. `SimulationReporter` is unchanged.
- `bigville/server.py` (one line): `GameService.report` returns `game_report(self.game)` instead of `self.game.world.report()`, so `GET /api/report` includes the `"llm"` key. This is the only change outside the write scope named in the brief, and it is additive.
- `tests/test_phase031_llm_backend.py` (new): 26 tests.

## Provider passing: choice

I chose a keyword argument, `create_game(..., llm_provider=p)`, because it is the shortest way to give one provider to every LLM resident. The helper `llm_backend_factory(p)` covers callers who already use `backend_factories`. The provider is either an object with `complete(prompt)` or a callable taking the prompt dict.

## How the counts reach the report

`BigvilleGame` holds the backends and `BigvilleWorld` does not, so `world.report()` cannot see the LLM counts. `game_report(game)` joins the two. The world report, and any code that calls it directly, does not contain the `"llm"` key. Refusal counts remain in `report["refusals"]`, and the LLM counts sit beside them as `report["llm"]`. `BigvilleGame` and `game.py` are unchanged.

## Tests added

All 26 tests in `tests/test_phase031_llm_backend.py` pass.

- Registration: `create_game(default_backend="llm", llm_provider=...)` and `create_game(default_backend="llm", backend_factories={"llm": llm_backend_factory(...)})` build an `LLMBackend` for every non-player resident (town100). A scenario actor with `backend: "llm"` gets an `LLMBackend` (norms_property_sharing with Ben switched to llm). The missing-provider and both-provided cases raise `ValueError`. A callable provider is accepted.
- Good output: a first-call reply produces the same prompt hash and response hash as before, with `attempts=1`, `outcome="ok"`, and counts `(1, 0, 1, 0)`.
- Repair: invalid JSON, then valid JSON, succeeds on the repair. The second request has `repair == {"errors": ["output is not a JSON object"]}`. A schema violation is repaired the same way. The repair request contains no echo of the bad output.
- Validation: the structural rules each report a fixed message, and an unknown field is an error.
- Repeated invalid output: an idle `ActorResponse` (no major action, not waiting), two calls, one failure, one invalid output.
- Game turn: an idle fallback in `BigvilleGame.step()` returns `"advanced"` and the world turn increases by one.
- Provider exception: one call, no repair, `provider_errors=1`. An `Authorization: Bearer sk-...` message is redacted and the key does not appear in backend state or in the held state.
- `TimeoutError` text is stored as `TimeoutError: read timed out`.
- `safe_error` truncates, collapses whitespace, and redacts.
- A bug in the prompt builder is counted as `internal_error`, not raised.
- Reports: `game_report` contains `refusals` and `llm`, with per-resident and total counts after one turn in which one resident succeeded and one failed. `llm_report` on a game with no LLM residents returns zero totals.

## Validation

- `python3 -m pytest -q -p no:cacheprovider tests/test_phase031_llm_backend.py`: 26 passed.
- `python3 domains/bigville_entities.py`: exit 0, ERRORS (0), WARNINGS (0).
- `python3 -m domains.check`: exit 0.
- `timeout 1500 python3 -m pytest -q -p no:cacheprovider` (full suite, final run): 3 failed, 994 passed, 2 skipped in 357.7 s. Failures:
  - `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`
  - `tests/test_mixed_ocelot_checkpoint_parity.py::test_phase6_mixed_village_midpoint_checkpoint_matches_uninterrupted_control`
  - `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`
  All three raise `OcelotUnavailableError ... ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter'`. I checked them against a copy of the tree in `/tmp`, with the Ocelot checkout symlinked as `../ocelot` and the four Phase 031 files reverted to HEAD. They fail there in the same way. The other session's uncommitted edits were present in that copy too, so this is evidence the failure does not come from Phase 031, not a clean-HEAD run.
- No existing test was changed. No existing assertion was weakened or removed.
- No `.env` was read, no network call was made, no provider other than a fake was used, and the 100-resident village run was not run.

## Limits

- No live provider. Behaviour against a real model (latency, repair rate, JSON quality) is not measured.
- `latency_ms` covers only the time spent in `decide`, which includes any repair call. It is not a measured per-turn cost.
- `validate_response` checks structure only. It does not check that an action name is in the pack or legal for the actor. The world does that.
- The credential filter is a heuristic. It drops any error text with a 28-character or longer run of letters and digits, so some harmless text is redacted too.
- `world.report()` has no LLM section. Only `game_report` (and `GET /api/report`, which uses it) has one.

## Open questions

1. A model may return `waiting: true`. The current validator accepts that field. In `BigvilleGame.step()` a waiting response stops the turn for every resident. Should an LLM backend be allowed to wait at all? I left it as before.
2. Provider exceptions are not repaired or retried. A timeout costs one idle turn. Should transient provider errors get a retry, and is that a call the brief wants counted as a repair?
3. Should `backend_state` in a model reply be accepted? It is not in `PROMPT_RESPONSE_FIELDS`, so the validator rejects it.
4. Idle fallback is used in place of the plan's `waiting`, as the brief asks. The divergence is recorded in the `LLMBackend` module docstring and here.

## Git status

Before (at start of this phase):

```
 M README.md
 M bigville/backends/ocelot.py
 M bigville/game.py
 M bigville/runtime.py
 M bigville/seeds/bigville_actor_decision.json
 M docs/AGENT_BACKENDS_PLAN.md
 M docs/FEATURE_PHASES.md
 M tests/test_bigville_game_api.py
 M tests/test_bigville_scenarios.py
 M worlds/bigville_world.py
?? bigville/game_persistence.py
?? bigville/mixed_ocelot_scenario.py
?? bigville/world_persistence.py
?? docs/MIXED_OCELOT_VILLAGE_RUN_20261105.md
?? docs/ocelot-integration-baseline.md
?? docs/runs/
?? tests/test_bigville_game_persistence.py
?? tests/test_bigville_graph_persistence.py
?? tests/test_bigville_ocelot_communication.py
?? tests/test_bigville_ocelot_fresh_process.py
?? tests/test_bigville_world_persistence.py
?? tests/test_mixed_ocelot_checkpoint_parity.py
?? tests/test_mixed_ocelot_village.py
?? tests/test_phase031_llm_backend.py  (not yet present at start; created by this phase)
?? tools/run_mixed_ocelot_scale.py
?? tools/run_mixed_ocelot_village.py
```

After (at end of this phase). Other sessions changed more files while this phase ran: `domains/bigville_entities.py`, `domains/world_affordances.py`, `bigville/backends/cheap.py`, `tests/test_bigville_world_migrated.py`, the `packs/` files, `docs/phases/phase030/`, and several new `locks.json` and `test_phase030` files. None of those are from this phase. This phase's files are `bigville/api.py`, `bigville/backends/llm.py`, `bigville/reporting.py`, `bigville/server.py` (modified), `tests/test_phase031_llm_backend.py` (new), and `docs/phases/phase031/PHASE031_REPORT.md` (new).
