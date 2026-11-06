# Management M11 report

## Baseline and scope

Base commit `657f520` in an isolated worktree. Added opt-in, versioned generated cast groups for authored scenarios; the existing `town100` and authored casts remain unchanged without a generation request. The management-specific example scenario declares its available roles and capacity.

## Changes

The resolver validates bounded groups, profile availability, trait distributions, distinct names and available walkable home cells. Generation uses deterministic independent streams, records the resolved cast and generator identity, and shares materialization between preview and launch. The UI exposes group sizes, roles, profiles and supported distributions when a scenario opts in. The generator supports at least 80 generated actors when the scenario provides enough eligible cells; the example scenario deliberately has a smaller capacity. Unsupported scenarios and malformed terrain are rejected.

An independent review traced the same actor records and profile precedence through preview and launch. The generator hash describes cast content; the overall configuration hash also includes profile assignments and revisions.

## Verification

`python3 -m pytest -q tests/management/test_cast_generation.py tests/management/test_cast_browser.py tests/management/test_drafts.py tests/management/test_runs.py tests/management/test_backends.py tests/management/test_backends_browser.py tests/management/test_templates.py tests/management/test_templates_browser.py tests/management/test_new_run_browser.py tests/test_bigville_reporting.py` — 80 passed in 46.29s.

`git diff --check` — passed. Full suite and entity self-test are supervisor integration gates.

## Limits

The generator does not infer shared households; generated actors require distinct free homes. Existing `town100` does not yet support custom generation settings. Scenario capacities and allowed roles are explicit. The Luna executor hit a usage limit after implementation; the supervisor reran the recorded regression set and wrote this report.
