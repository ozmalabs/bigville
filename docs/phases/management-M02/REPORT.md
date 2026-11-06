# Management M02 report

## Baseline

- Base commit: `4d596052098796970426bb54f2a96b6dab672511`.
- Initial worktree was clean.
- Runtime/tool versions: Python 3.13.5, pytest 9.0.2, Playwright 1.58.0, NumPy 2.4.4.
- The two M02 test files did not exist at baseline; the baseline named test command therefore had no tests to execute.
- No new Python or JavaScript dependency was added. Playwright was already installed in the environment and is used only for browser tests.

## Scope and behaviour

Added a responsive local management shell at `/`, with semantic landmarks and accessible status/error messaging. Worlds & casts and Backends are enabled catalog views; Runs is explicitly disabled because this service has no run registry yet. The shell requests live scenario/backend data from the M01 capabilities endpoint, displays source/type/hash/subsystem details and backend readiness reasons, and shows loading, empty, and failed-request states with retry. It links to the existing game at port 8765.

The HTTP service serves the HTML and static CSS/JS assets from package resources, rejects resolved paths outside the static root, and leaves M01 API routes intact. Static assets were added to `pyproject.toml` package data so the shell also works from an installed package; this changes packaging only and adds no dependency.

## Files

- `bigville/management/http.py`
- `bigville/management/static/index.html`
- `bigville/management/static/management.css`
- `bigville/management/static/management.js`
- `tests/management/test_shell.py`
- `tests/management/test_shell_browser.py`
- `pyproject.toml`
- `README.md`
- `docs/phases/management-M02/REPORT.md`

## Commands and results

- `python3 -m pytest -q tests/management/test_shell.py tests/management/test_shell_browser.py` — **7 passed**, including the installed Chromium browser checks at 390px and desktop width.
- `python3 -m bigville.management.http --help` — CLI loads and shows host/port options.
- `git diff --check` — clean.

The browser suite verifies keyboard navigation, unavailable backend messaging, catalog request failure feedback, and absence of horizontal page overflow at 390px. One initial failure-path test waited for `networkidle` and timed out; it now waits for DOM readiness and asserts that the error alert appears. The final named command passes.

## Limitations and handoff

The service remains read-only: Runs is disabled, and the shell does not offer draft, preview, creation, or control actions. The existing game link assumes the documented default game server address. No full-suite or entity self-test was run because the supervisor noted that integration gates are already running. No plan status or unrelated files were changed.
