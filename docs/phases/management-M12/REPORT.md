# Management M12 report

## Baseline

- Worktree: `/home/matt/ozmadev/bigville-management-m12`
- Base commit: `bc4d4cc`
- No dependency or `pyproject.toml` changes.
- The M12 baseline had live-only report reads from M07. The live endpoint remains explicit; comparison now uses persisted captures.

## Changes

- Added immutable report snapshot capture/listing, stored in the durable run registry with report schema, run turn/status, normalized configuration hash, capability revision, seed, scenario content identity, and the exact engine build identity already captured in run configuration.
- Added comparison for two to ten distinct runs using the latest saved snapshot per run. Only the known `bigville/report/1` report schema is comparable. Missing snapshots, unsupported schemas, missing/non-numeric/non-finite metrics, and incompatible economic identities are shown as unavailable with a reason. Economic quantities require matching known scenario source/content hash and engine source hash (which includes pack source files); no values are synthesized.
- Added safe reproducibility metadata export. Secret-bearing keys and references are recursively omitted. Corrupt stored snapshot data fails closed through the shared JSON error envelope for snapshot listing, comparison, and metadata export.
- The registry validates persisted report snapshots on load and validates snapshot structure/provenance against the owning run before returning public list/detail records. Corrupt persisted registry data is refused at startup; corrupt in-memory records produce the shared JSON error.
- Added capture, export, and multi-run comparison controls. The results use semantic table headers, native labelled controls, live status messages, and a locally scrollable wide table.
- Added the complete local-operation documentation to `README.md`: run launch, supported profile/config boundaries, restart/worker behavior, checkpoint and perspective boundaries, report comparisons, and troubleshooting.
- Added test-only synchronization fixes to two existing browser tests after the full suite exposed cancelled Playwright response-body reads in asynchronous event callbacks. Existing assertions remain intact. Three separate fixture corrections supplied on the integration branch (`test_cast_browser.py`, `test_checkpoints_browser.py`, `test_drafts.py`) were retained as baseline changes.

## Accessibility and responsive audit

- Workspace/run navigation, forms, backend pages, run views, reports/events, templates, checkpoints, and human input retain visible labels and heading structure. Controls use native buttons/selects; status and action errors use live/status or alert regions.
- New comparison controls have an associated multi-select label/help text; result tables have row/column header scopes. The 375 px browser case confirms there is no page-level horizontal overflow; wide table content stays within its own scroll container.
- Keyboard operation relies on native browser controls and existing visible focus styles. No automated screen-reader/axe audit was available, so semantic markup was reviewed and the browser suite exercises the primary controls.

## Verification

- `python3 -m pytest -q tests/management/test_compare.py tests/management/test_reports.py tests/management/test_compare_browser.py tests/management/test_management_journey_browser.py` — **21 passed**.
- `python3 -m pytest -q tests/management` — **160 passed** in 137.73s.
- Final follow-up tightened snapshot schema-version typing and turn bounds; `python3 -m pytest -q tests/management/test_compare.py tests/management/test_reports.py` — **21 passed** after those changes. The full suite was not rerun after this narrow validation-only follow-up.
- The browser journey covers configure → preview → run → pause → report capture → checkpoint → fork → template save → compare, including the invalid one-run comparison path.

## Limits

- Management remains a local, single-user service. It has no remote/multi-user deployment claim.
- Run worlds and workers are not persisted. Captured report snapshots do survive restart; interrupted runs are still marked failed rather than resumed.
- Comparison currently supports only six allowlisted metrics. Economic comparisons are conservatively unavailable when scenario or engine/pack identity is unknown or different. Built-in `town100` does not expose a canonical scenario content hash, so its economic values are not compared.
- `GET /runs/{id}/report` remains a live readout; operators must record snapshots before those runs can be compared.
