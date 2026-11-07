# M11A report — Physical subsystem configuration

## Base and environment

- Base commit: `0c46ed28c795241064c2c26ed6a60a15e7bb89c6`
- Python: 3.13.5
- pytest: 9.0.2
- Worktree was clean before implementation. No commit was created.

## Delivered

- Drafts accept `physical_subsystems` only as a map of engine-supported names to booleans. Unknown names, non-boolean values, and non-object inputs return field errors.
- Resolution records engine defaults, explicit user overrides, effective switch values, and each value's source. All of these values participate in the canonical configuration hash. Templates round-trip explicit overrides.
- Capability data lists supported switches, defaults, and short engine-derived descriptions. The new-run form lets users inherit the scenario/default value or set On/Off; review displays effective values and their source.
- Changing scenarios resets prior subsystem overrides and refreshes inherited values and source labels for the newly selected scenario.
- Preview and launch pass the same resolved switches to world constructors before initialization for authored scenarios and built-in `town100`. Authored values are retained for unselected switches; explicit user values take precedence. The existing direct `BigvilleWorld` constructor rule against specifying scenario and constructor switches simultaneously remains intact.
- Run identity revalidation converts the stored normalized overrides back to the public draft field, preventing valid configured runs from failing at startup.
- Added behavioral coverage proving that the `training` switch disables skill gain from real forge work.

## Verification

Ran the phase tests and affected scenario, run, template, cast, subsystem, and persistence regressions:

```text
python3 -m pytest -q tests/management/test_subsystems.py tests/management/test_subsystems_browser.py tests/management/test_drafts.py tests/management/test_runs.py tests/management/test_templates.py tests/management/test_cast_generation.py tests/test_simple_life.py tests/test_phase032_training.py tests/test_bigville_world_persistence.py
99 passed in 29.53s
```

`git diff --check` passed. The full repository suite was not run.

## Files

- `worlds/bigville_world.py`, `bigville/api.py`: constructor propagation and authored scenario materialization.
- `bigville/management/drafts.py`, `runs.py`, `catalog.py`: validation, provenance, immutable identity, construction, and switch descriptions.
- `bigville/management/static/index.html`, `management.js`: subsystem controls and review.
- `tests/management/test_subsystems.py`, `test_subsystems_browser.py`: API, lifecycle, template, behavioral, and browser coverage.

## Handoff

All implemented switches map directly to `BigvilleWorld.PHYSICAL_SUBSYSTEM_DEFAULTS`. The selector does not expose purchases, banking, or global speech controls. No provider or network calls are involved.
