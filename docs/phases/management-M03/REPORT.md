# Management M03 report

## Baseline

- Base commit: `0bc79cf7b2a6003a22dd9d7ec60d8f826b51f1f7`.
- Initial worktree was clean.
- Runtime: Python 3.13.5; pytest 9.0.2; NumPy 2.4.4. No dependencies were added.
- `tests/management/test_drafts.py` was absent at baseline. The integration full-suite baseline remains pending with the supervisor.

## Scope and behaviour

Added `POST /api/management/v1/run-drafts/validate` and `/run-drafts/preview`. Both use the same `resolve_draft` contract. Inputs are limited to scenario ID, name, explicit seed, autonomous mode, default backend, `ticks_per_period`, and optional turn limit; unknown keys and unsupported values receive field-addressed errors. Scenario IDs must be discoverable IDs or `town100`, preventing local paths from being loaded through this API.

Normalization accepts `simple` and its `cheap` alias, then records canonical `simple`. It only accepts autonomous mode, `world`, null, or a positive integer cadence, and a bounded positive integer turn limit. Boolean values are rejected where Python would otherwise treat them as integers. Seeds must be nonnegative and no greater than `2^53-1`; town100 uses NumPy seed handling and engine seed metadata is stored as floats, so negative or imprecisely representable values are refused before world creation. An authored actor override is reflected in the normalized configuration and preview; unsupported human, LLM, Ocelot, or other actor backends are rejected with the actor named in the scenario error.

Validation returns capability revision, warnings, normalized settings, engine identity and a canonical sorted-JSON SHA-256 configuration hash. Preview constructs a disposable world through `create_world` only, with autonomous actor execution disabled. It returns actual bounded map grid/tile counts and cast/backend/position data. Preview limits are a 64 KiB request body, 40×40 returned map grid, 200 listed actors, and 1 MB JSON response. Invalid drafts return 422 with field errors; scenario construction errors are also field-addressed 422 responses. Preview does not create a game, run record, persistent state, worker, or provider call.

## Files

- `bigville/management/drafts.py`
- `bigville/management/http.py`
- `tests/management/test_drafts.py`
- `docs/phases/management-M03/REPORT.md`

## Commands and results

- `python3 -m pytest -q tests/management/test_drafts.py` — **25 passed**.
- `git diff --check` — clean.

Tests cover unknown/invalid fields, cadence edge cases including bool, unsupported backend choices, path/unknown scenario rejection, negative seed rejection, unsupported authored subsystem configuration, authored override precedence, deterministic preview/hash, changed town100 seed output, no game/provider construction, HTTP validation/preview and body size limits, and field-addressed scenario construction errors.

## Limitations and handoff

This phase validates and previews only; run creation/lifecycle is M04. The seed range cap preserves exact engine metadata representation. Preview map output is capped, but world construction still loads the selected authored scenario before producing the bounded response. Full-suite and entity self-test gates were not run because the supervisor reported the integration baseline as pending. No unrelated files or plan status were changed; no commit was made.
