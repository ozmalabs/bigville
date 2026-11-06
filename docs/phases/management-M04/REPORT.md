# Management M04 report

## Baseline

- Base commit: `b08b6c7955a25676deac6f1a27980991710ee144`.
- Initial worktree was clean.
- Runtime/tool versions: Python 3.13.5, pytest 9.0.2, NumPy 2.4.4. No dependencies were added.
- The named M04 tests did not exist at baseline. The supervisor reported the full integration gate for previous phases as pending.

## Scope and behaviour

Added a local durable run registry, defaulting to `~/.local/share/bigville-management`, configurable through `BIGVILLE_MANAGEMENT_DATA_DIR` or `--data-dir`. Registry JSON is schema-versioned and atomically replaced after each mutation. Malformed or incompatible registry data is rejected without overwriting it. Opaque server-generated run IDs and hashed idempotency keys are used. `POST /api/management/v1/runs` accepts `{draft, idempotency_key, expected_config_hash, expected_capability_revision}`; it resolves through M03, checks both expected identities, materializes a disposable preview to retain resolved actor/backend assignments, and persists a `created` run. Repeated key+configuration returns the existing ID; key reuse with a different resolved configuration conflicts. `GET /runs` and `GET /runs/{id}` expose persisted records.

`POST /runs/{id}/commands` implements start, pause, resume, step and stop. One per-run lock serializes commands with actual game steps; pause and stop acquire the lock at a turn boundary. Start/resume run a daemon worker using `create_game` and the saved scenario, seed, backend and cadence. A finite turn limit completes only after the successful turn has been recorded. Waiting is stored distinctly from completion and cannot resume without input support. Worker initialization/step exceptions are persisted as failed. The service never calls reset as a stop operation. HTTP validation, preview and run-creation errors use the shared `{ "error": { "code", "message", "fields"? } }` envelope. Run-creation preview failures are converted to JSON errors with a scenario field message; persistence errors also return a server error response instead of dropping the connection.

After restart, records in starting/running/paused/waiting, and created records that already stepped, are marked failed with an interruption reason because in-memory world state is not persisted. Untouched created records and terminal metadata remain readable. Before a created run starts or takes its first step, the server resolves it again and compares config hash and capability revision. The build identity now includes a deterministic source/pack digest, and capability revision includes that identity, so scenario, data-pack, engine-source, or capability drift is refused. Run records retain the original M03 configuration hash plus resolved actor/backend assignments.

README startup documentation now describes registry location, configuration, supported autonomous simple runs, restart semantics and local single-user limits. An M02 shell test that previously asserted `/runs` returned 404 now verifies the implemented list endpoint and keeps a separate unknown-route assertion.

## Files

- `bigville/management/runs.py`
- `bigville/management/http.py`
- `bigville/management/catalog.py`
- `tests/management/test_runs.py`
- `tests/management/test_lifecycle.py`
- `tests/management/test_shell.py` (updated expected `/runs` behavior)
- `README.md`
- `docs/phases/management-M04/REPORT.md`

## Commands and results

- `python3 -m pytest -q tests/management/test_runs.py tests/management/test_lifecycle.py` — **17 passed**.
- `python3 -m pytest -q tests/management` — **58 passed** across M01–M04, including Playwright browser coverage.
- `git diff --check` — clean.

Coverage includes create/list/reload, immutable config and actor assignments, invalid drafts, stale config/capability identities, idempotency, malformed registry protection, HTTP routes and commands, real small-scenario stepping and worker completion limits, pause/step/resume/stop and illegal transitions, concurrent pause/stop at a gated turn boundary, worker errors, waiting state, restart recovery, distinct-run isolation, refusing launch after authored scenario or engine build drift, shared nested field-error envelopes, and JSON handling of run-creation preview failures.

## Limitations and handoff

The registry persists run metadata but not live game state; restart fails unfinished execution rather than resuming. Per-run workers are in-process daemon threads, so the service remains a local single-user tool, not a multi-user scheduler or authenticated deployment. M04 only launches autonomous simple-backend runs. The supervisor’s full integration gate and entity self-test were not run in this worktree. No commit was made.
