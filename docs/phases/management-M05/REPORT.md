# Management M05 report

## Baseline

- Base commit: `b0817c9debaffb8c24d876f29fd27a7ca2702b1a`.
- Initial worktree was clean.
- Runtime/tool versions: Python 3.13.5, pytest 9.0.2, Playwright 1.58.0, NumPy 2.4.4. No dependencies were added.
- `tests/management/test_new_run_browser.py` did not exist at baseline; the M04 `test_runs.py` suite was already present.

## Scope and behaviour

Enabled the Runs navigation and added a run list with current status, scenario, seed, turn, and state-appropriate Start/Stop actions. Added a responsive new-run form for name, catalog scenario, explicit world seed, the supported simple backend, autonomous mode, ticks per period and optional turn limit. Human mode, other backends, templates and per-actor edits are not offered as functional choices.

The user can validate and preview through M03 before creating a run. The review displays the resolved config, real cast/backend assignments, physical subsystem values, bounded map preview, seed and config hash. Any form edit clears the review and disables launch. Validation captures a draft revision and ignores delayed validation/preview responses and errors after the user edits. During create/start, form controls are locked and the request uses a cloned review snapshot, so the submitted configuration cannot change underneath an in-flight request. Random writes one concrete integer to the seed field; that value remains the preview and launch seed. Creation sends the preview config hash, capability revision and an idempotency key to M04, then issues the real start command. Field-addressed errors read the shared nested `error.fields` envelope; stale identity errors invalidate review while preserving the draft. Duplicate submission is disabled synchronously.

The existing Worlds & casts and Backends catalog views remain available, with the link to the existing game preserved.

## Files

- `bigville/management/static/index.html`
- `bigville/management/static/management.css`
- `bigville/management/static/management.js`
- `tests/management/test_new_run_browser.py`
- `docs/phases/management-M05/REPORT.md`

## Commands and results

- `python3 -m pytest -q tests/management/test_new_run_browser.py tests/management/test_runs.py` — **15 passed**.
- `git diff --check` — clean.

The browser tests use a real local service and a deterministic authored fixture. They cover validate → preview → create → start, preview hash and seed provenance, resolved actor/backend output, form edits invalidating review, server rejection of an injected unsupported backend, stale hash errors in the shared envelope, double-click idempotence, keyboard/random-seed interaction at 390px without page overflow, and delayed validate/preview responses plus stale validation errors after draft edits.

## Limitations and handoff

The page exposes run status and basic start/stop actions; live overview, pause/resume, resident views and reports belong to later phases. A run with no turn limit continues until stopped. The UI keeps a draft after validation/create errors and requires another validation after edits or stale capability responses. No full integration suite or entity self-test was run. No commit was made.
