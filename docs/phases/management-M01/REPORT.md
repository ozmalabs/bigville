# Management M01 report

## Baseline

- Base commit: `9be749e40d5f8e5d3cd74c3caa832ad79943936`.
- Initial `git status --short`: clean.
- Runtime: Python 3.13.5; pytest 9.0.2; project declares `numpy>=1.24` and no added dependencies.
- Baseline command `python3 -m pytest -q tests/management/test_capabilities.py tests/management/test_http.py tests/test_bigville_server.py` could not run: the two new management test files did not yet exist, so pytest exited with “file or directory not found” and ran no tests. No code or unrelated files were changed to mask this.

## Scope and behaviour

Added a separately launched HTTP discovery service at `bigville.management.http`. It binds to `127.0.0.1:8766` by default, accepts only loopback IP bind addresses, and exposes `GET /api/management/v1/health` and `GET /api/management/v1/capabilities`. Unknown paths and unsupported methods return the shared JSON error envelope.

The versioned catalog includes built-in `town100`, discoverable authored scenario IDs with source/type and effective physical subsystem values, engine subsystem defaults, a revision hash, and build identity when available. Scenario files are canonically hashed; `town100` reports `content_hash: null` with a reason because the engine does not expose a pack/content identity. Simple and human are available; Ocelot availability checks adapter importability without constructing it; LLM is unavailable until configured server-side. Catalog generation creates no world/game and invokes no provider.

README startup instructions document the local-only, single-user scope and current catalog-only behaviour.

## Files

- `bigville/management/__init__.py`
- `bigville/management/catalog.py`
- `bigville/management/http.py`
- `tests/management/test_capabilities.py`
- `tests/management/test_http.py`
- `README.md`
- `docs/phases/management-M01/REPORT.md`

## Commands and results

- `python3 -m pytest -q tests/management/test_capabilities.py tests/management/test_http.py tests/test_bigville_server.py` — **12 passed**.
- `python3 -m pytest -q tests/management` — **9 passed**.
- `python3 -m bigville.management.http --help` — CLI loads and shows host/port options.
- `git diff --check` — clean.

## Limitations and handoff

This phase does not create runs or serve a frontend. Provider-profile configuration and LLM readiness are not implemented, so LLM remains explicitly unavailable. Built-in `town100` pack identity is unknown and is not represented by a fabricated hash. The service remains a loopback, local single-user tool, not an authenticated multi-user deployment. No full suite or entity self-test was run; those remain integration gates for the supervisor.
