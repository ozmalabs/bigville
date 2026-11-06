# Management M10 report: backend profiles and actor assignments

## Result

Implemented server-configured backend profiles, authored-scenario per-actor assignments, and the management UI for selecting those profiles. Profile records expose readiness and stable revisions without returning adapter details or secret references. The server can accept a `BackendAdapterRegistry` through `create_server(profile_adapters=...)`; registered LLM adapters are called for the actor assigned to their profile. The browser cannot supply factories or secrets.

Assignment precedence is explicit actor assignment, then scenario-authored backend, then the selected default profile. Explicit assignments therefore take effect before authored-backend availability is checked. Per-actor assignments for `town100` remain rejected because its engine path does not implement them. Custom simple and Ocelot profile variants are rejected rather than accepted with settings the runtime would ignore. The CLI has no built-in third-party LLM adapter, so LLM profiles remain unavailable there until an embedding application registers one. This limitation and the registration hook are documented in `README.md`.

Provider initialization and request failures are surfaced with generic sanitized messages. Tests verify that secret references and provider exception text do not appear in profile catalogs, run configs, templates, reports, or snapshots, and that two different profile assignments invoke their corresponding fake adapters.

M09 template versions retain their immutable stored data. A persisted pre-M10 template whose capability/profile/scenario identity is stale can still be inspected, but loading returns an explicit incompatibility error; it is not silently rewritten or dropped. The migration behavior is covered by a persisted-template regression test.

## Verification

The named M10 tests and affected M03–M09 regressions passed:

```text
python3 -m pytest -q tests/management/test_backends.py tests/management/test_backends_browser.py tests/management/test_capabilities.py tests/management/test_drafts.py tests/management/test_runs.py tests/management/test_new_run_browser.py tests/management/test_templates.py tests/management/test_templates_browser.py
64 passed in 23.20s
```

The browser test uses local fake adapters and verifies actor selection in the UI, preview assignments, run creation, and actual adapter calls. `git diff --check` passed. No live provider calls were made. The full repository integration gate was not run as part of this phase.
