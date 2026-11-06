# Bigville management frontend: execution phases

Status: proposed, 6 November 2026. This is an implementation plan, not a claim that the management service exists. Product requirements and screen descriptions are in [MANAGEMENT_FRONTEND.md](MANAGEMENT_FRONTEND.md); the visual reference is [new-run-prototype.html](new-run-prototype.html). The phases below are deliberately small enough to assign one at a time to a Luna agent.

## Instructions for the supervisor and each executor

- Use the latest agreed integration commit as the baseline. This checkout contains unrelated work, including persistence and agent-view changes: **do not reset, overwrite, stage or commit someone else's changes**. The supervisor first integrates or explicitly carries the required persistence and agent-view changes into a clean integration branch. Each phase runs in its own worktree/branch from that branch. A phase is not ready merely because its dependency's files happen to exist uncommitted in another tree.
- One phase per agent and one phase per branch. The executor reads this plan, the design, affected code and repository instructions, implements only the brief, and returns a report; the supervisor reviews, runs the gates, integrates and commits each phase. Do not launch dependent phases until their dependencies are integrated. Use separate filenames for new modules where possible; serialize changes to shared files. Existing project policy in `docs/FEATURE_PHASES.md` calls for supervisor commits and full-suite/self-test checks; follow it unless the user directs otherwise.
- Before editing, record the base commit, `git status --short`, dependency versions and the test baseline. If baseline checks fail, report the exact failures; do not modify unrelated code to hide them. Write `docs/phases/management-MNN/REPORT.md` with base, scope, behaviour, commands/results, files, known limitations, and handoff. Do not change this plan's status until the supervisor accepts the phase.
- Each phase lists **targeted tests to create** under `tests/management/`. They must exercise observable behaviour, not merely assert that implementation functions exist. Use temp directories, ephemeral ports, deterministic small scenarios and fake providers; never call live model APIs. Run `python3 -m pytest -q tests/management` after phase M01, plus existing affected tests. Browser tests use local fixtures and Playwright; if unavailable, record a blocker for the UI phase rather than claiming visual verification. The supervisor additionally runs `python3 domains/bigville_entities.py` and `timeout 1500 python3 -m pytest -q -p no:cacheprovider` at integration, as prescribed by `docs/FEATURE_PHASES.md`; record pre-existing failures separately.
- On unknown or unsupported functionality, surface a specific error or disabled state. Never invent successful run results, silently drop configuration, leak credentials, assume model availability, change world mechanics to fit the UI, or weaken existing tests. Preserve the existing game server and its API. Accessibility, responsive design and resident/referee separation are requirements, not later polish.

## Shared contracts and boundaries

The implementation is local-first and single-user for these phases. Bind the management server to loopback by default, store data under a configurable local data directory outside source control, and document that remote/multi-user deployment and authentication are out of scope. Referee endpoints are sensitive: the service must enforce perspective, and agent-facing responses must never contain referee data. Do not claim this is a secure multi-tenant service.

- All management API paths begin `/api/management/v1/`. Keep them distinct from the existing game's `/api/*`. JSON errors have `{ "error": { "code": string, "message": string, "fields": object? } }` and a suitable HTTP status. Unknown fields, unsupported choices and illegal transitions fail explicitly. Paths below are relative to that prefix.
- Persist draft/run/template documents with an explicit schema version. Generate opaque IDs server-side. Canonical JSON sorted by keys and an identified hash algorithm supply immutable configuration hashes. Keep generated numeric seeds, scenario identity and content hash, pack/build identity when available, resolved cast/backend assignments, effective switches, mode and cadence. Never include secrets or claim a seed alone guarantees reproducibility. Use atomic write/replace and reject malformed or incompatible stored versions without silently overwriting them.
- State machine: `draft` is client-side until creation; managed runs use `created`, `starting`, `running`, `paused`, `waiting`, `completed`, `failed`, `stopped`. Start is accepted only from `created`; pause from `running`; resume from `paused`; step from `created` or `paused`; stop from `created`, `running`, `paused` or `waiting`. `waiting` means actual human input is needed, not completion. Later phases may implement input handling; until then reject resume/input with a clear error. Commands are serialized per run; stop/pause become effective at the next quiescent turn boundary. Return `409` for invalid transitions.
- In phase M04 the real supported creation subset is: scenario ID including `town100`, name, explicit integer seed, `autonomous: true`, default `simple` backend, `ticks_per_period` (`world`, positive integer, or `null`) and optional positive turn limit. Reject all other inputs until later phases explicitly implement them. In particular, do not let a `town100` UI pretend it can set separate map/cast seeds, total population, distributions or actor-level backend overrides. A random seed is generated once in the browser, displayed, and submitted as an integer; server-side validation remains authoritative.
- UI uses plain HTML/CSS/JS in a new `bigville/management/` directory unless the supervisor approves a dependency. The management server serves these files and the existing game assets safely; keep a clear route to the old game. The prototype is visual guidance, not a data source. Use a small responsive shell, native controls and accessible labels/status messages. Actions with no service contract are not interactive.
- A phase's tests and API descriptions are part of its handoff. Any necessary interface change updates this section and all downstream briefs in the same reviewed change; never quietly change an earlier phase's semantics.

## Dependency order and scheduling

`M01 → M02 → M03 → M04 → M05 → M06 → M07 → M08 → M09 → M10 → M11 → M12`.

This conservative sequence avoids simultaneous edits to the server and UI. The supervisor may parallelize read-only research or non-overlapping test design after freezing contracts, but must integrate in this order. M08 depends on committed game checkpoint/restore and agent-view work; if unavailable, mark it blocked and continue only work explicitly independent of M08. M10–M12 are separate increments and do not block a usable M01–M09 product.

| Phase | Status | Deliverable |
|---|---|---|
| M01 | ready after clean baseline | capability catalog and management server skeleton |
| M02 | blocked by M01 | local frontend shell and catalog |
| M03 | blocked by M02 | draft validation and reproducible preview |
| M04 | blocked by M03 | durable run registry and lifecycle |
| M05 | blocked by M04 | new-run and runs pages |
| M06 | blocked by M05 | live overview, controls and resident perspectives |
| M07 | blocked by M06 | reports, events and trace artifacts |
| M08 | blocked by M07 and checkpoint integration | checkpoints and fork |
| M09 | blocked by M08 | templates and versioned reuse |
| M10 | blocked by M09 | backend profiles and actor assignments |
| M11 | blocked by M10 | configurable cast generation and backend splits |
| M12 | blocked by M11 | comparison and end-to-end release audit |

## M01 — Capability catalog and server skeleton

**Scope:** Add a separately launched, loopback-only management HTTP service. `GET /capabilities` returns a versioned catalog of `town100` and discoverable scenario IDs, scenario source/type, supported subsystem names/defaults from the engine, and backend kinds with truthful availability. A backend requiring a configured provider or missing Ocelot dependency must be unavailable with a reason; do not instantiate or contact providers. `GET /health` reports service readiness. Reject unknown paths with the shared error envelope. Record the engine build identity when known; represent unknown values as unknown. Supply a CLI and startup documentation. No run creation yet.

**Tests:** Create `test_capabilities.py` and `test_http.py`: exercise actual HTTP health/catalog, built-in plus a temporary authored scenario, missing integration, JSON errors, loopback default, and no mutation/provider call. Run `python3 -m pytest -q tests/management/test_capabilities.py tests/management/test_http.py tests/test_bigville_server.py`.

**Done:** Existing game server behaviour remains unchanged; catalog values are derived from the checked-out implementation and report unsupported options honestly.

## M02 — Responsive shell and catalog

**Scope:** Serve a management shell at `/` from the new service with Runs, Worlds & casts and Backends navigation; only catalog-backed sections are enabled. Display scenario details and backend readiness from M01, loading/empty/error states and link to the existing game without claiming multi-run support. Follow the prototype's visual direction; use real data, semantic landmarks, keyboard-accessible controls and layouts at 390px and desktop widths. No hard-coded installed model names.

**Tests:** Create `test_shell.py` for HTTP/static-path traversal and catalog rendering with a fake response; create `test_shell_browser.py` to navigate with keyboard, check mobile horizontal overflow, an unavailable backend and failed catalog request. Run `python3 -m pytest -q tests/management/test_shell.py tests/management/test_shell_browser.py`.

**Done:** The shell can be opened locally using the documented command and all visible navigation leads to real views or is clearly disabled.

## M03 — Validate and preview a draft

**Scope:** Implement `POST /run-drafts/validate` and `/run-drafts/preview` for the shared M04 subset. A draft accepts only known keys and an explicit seed; validation returns field-addressed errors, warnings, capability revision and normalized effective settings. Preview builds a disposable, deterministic world from the same resolved inputs, returns a bounded map/cast summary and canonical config hash, and does not create a run or write persistent simulation state. Avoid starting an autonomous worker or invoking external providers. Handle both `town100` and authored scenarios; explain authored per-actor backend overrides and reject scenarios requiring unsupported backends for this increment. Set reasonable server-side bounds for preview request/response sizes.

**Tests:** `test_drafts.py`: invalid fields, unavailable choices and cadence; same seed/config produces the same preview/hash; different seed on `town100` changes generated data; authored scenario overrides are reflected; preview creates no run and makes no provider calls. Use a small scenario for most tests and one real `town100` reproducibility test. Run `python3 -m pytest -q tests/management/test_drafts.py`.

**Done:** Preview and validation share a single resolver. The response contains no credentials, fake map, or independent seed setting.

## M04 — Durable runs and serialized lifecycle

**Scope:** Add a local persistent run registry and one managed worker per active run. `POST /runs` validates through M03, accepts an idempotency key and expected config hash/capability revision, atomically persists the immutable resolved configuration and creates a `created` record. Same key+same request returns the original ID; same key+different request is a conflict. `GET /runs` and `/runs/{id}` expose records. `POST /runs/{id}/commands` implements the shared state transitions with serialized commands and real autonomous game steps, a finite turn limit when provided, and truthful errors. Pause and stop occur only at step boundaries. On restart, unfinished in-memory execution must be marked interrupted/failed with a reason, not silently resumed or represented as live; persisted metadata remains readable. Do not call reset as an implicit stop.

**Tests:** `test_runs.py`, `test_lifecycle.py`: create/list/reload, invalid drafts and stale hashes, idempotency/reuse conflict, real small-scenario stepping and limit, pause/resume/stop/illegal transitions, simultaneous commands, worker exception and restart recovery. Verify distinct runs cannot mutate each other. Run `python3 -m pytest -q tests/management/test_runs.py tests/management/test_lifecycle.py`.

**Done:** No command reports completion before the step finishes; every status is durable and observable. Document limits of restart and turn-boundary cancellation.

## M05 — New run and run list

**Scope:** Implement Runs list and new-run form using M01–M04. Collect name, scenario, concrete world seed, supported backend, autonomous mode, cadence and turn limit; validate and preview, display resolved actor/backend and subsystem summary, and start only after successful server validation. Make Random materialize once and retain it through preview, review and submission. Revalidate after edits; prevent duplicate launch and preserve input on errors. Show run status and actionable errors. Omit template, human mode and per-actor editing until supported.

**Tests:** `test_new_run_browser.py`: complete create/preview/start using a small deterministic fixture; verify preview hash and launched seed agree, edits invalidate review, unsupported backend and stale hash show field errors, double click creates one run, and mobile/keyboard interaction works. Run `python3 -m pytest -q tests/management/test_new_run_browser.py tests/management/test_runs.py`.

**Done:** A user can start and find a real run without using the terminal; the UI never offers an unsupported control as functional.

## M06 — Live run, world and perspectives

**Scope:** Add run overview and state-appropriate lifecycle controls backed by M04. Poll a run-scoped read-only snapshot endpoint, display actual turn/status/errors, and reuse the existing renderer for a referee world view without changing the existing game route. Add a population table and actor details. Implement separate run-scoped referee and agent-view endpoints; agent view calls the engine's existing agent view and does not return full state, raw traces or referee snapshots. Provide an explicit perspective choice and never claim client-side filtering is access control. This local single-user increment is not a multi-user authorization system. Handle waiting, failed, unavailable snapshots, mapless scenarios and stale data.

**Tests:** `test_run_views.py`, `test_run_views_browser.py`: real status progression, disabled illegal commands, resident list, mapless fallback, selected resident perspective and a sentinel secret present in referee data but absent from agent responses. Verify no `/state` request is made in agent view after switching, and no cross-run data. Run `python3 -m pytest -q tests/management/test_run_views.py tests/management/test_run_views_browser.py tests/test_bigville_server.py`.

**Done:** The run can be observed and controlled while preserving the existing game's rendering and the documented perspective boundary.

## M07 — Reports, events and traces

**Scope:** Add run-scoped latest report and recorded events endpoints and a Reports / Events page. Use existing `game_report` and actual world events, marking live snapshot versus recorded history and census versus sampled measures. Add a trace option only if collection can use the actual executed turns without taking extra turns or modifying affordance state; otherwise leave trace disabled with a documented reason. Persist explicitly recorded artifacts, paginate event/trace results, and offer JSON download. Never present current state as historical data or missing metrics as zero.

**Tests:** `test_reports.py`, `test_reports_browser.py`: a small real run produces matching report values, event filtering/pagination, missing trace state, JSON export, and no simulation advancement when reading. If trace enabled, assert one trace record per real step and no mutation due to observation. Run `python3 -m pytest -q tests/management/test_reports.py tests/management/test_reports_browser.py`.

**Done:** Every displayed number has source/units or a clear unavailable label, and read operations do not advance the world.

## M08 — Checkpoints, restore and fork

**Prerequisite:** Committed `save_game_checkpoint` / `load_game_checkpoint`, their dependencies and tests, including the required agent-view work, are present in the integration branch. Record the commit and verify supported adapters; do not substitute a world-only checkpoint for a game checkpoint.

**Scope:** Add checkpoint eligibility and creation at a quiescent turn boundary, immutable checkpoint metadata/artifact listing, and fork-from-checkpoint to a distinct run ID. Keep the original unchanged and record parent run/checkpoint, config hash and turn. Explicitly report unsupported backend, active dispatch, invalid/corrupt checkpoint and restoration failure. Protect artifact paths from traversal. Add the corresponding run page and controls. On process restart, an interrupted run may be forked only from a verified checkpoint; do not silently resume.

**Tests:** `test_checkpoints.py`, `test_checkpoints_browser.py`: real small-world checkpoint/fork parity on supported backend, independent parent/child after further steps, unsupported backend, corrupt artifact, concurrent step/checkpoint boundary and traversal denial. Run `python3 -m pytest -q tests/management/test_checkpoints.py tests/management/test_checkpoints_browser.py tests/test_bigville_game_persistence.py`.

**Done:** The UI reports checkpoint eligibility and errors, and a successful fork retains physical and supported cognition state with provenance.

## M09 — Templates

**Scope:** Add local versioned template CRUD sufficient to save a run's non-secret configuration and load a specific immutable version into a draft. Store template ID/version and resolved config hash with runs. Applying to a modified draft asks before replacement; invalid or unavailable capabilities are reported and the draft is not silently normalized. Never save credentials. Provide list, save, inspect and load UI; deletion of referenced versions is not supported in this phase.

**Tests:** `test_templates.py`, `test_templates_browser.py`: version immutability, save/load round trip, stale capability failure, changed-draft confirmation, no secret persistence, and old run's provenance after a newer template version. Run `python3 -m pytest -q tests/management/test_templates.py tests/management/test_templates_browser.py`.

**Done:** A template recreates a configuration, while a checkpoint restores state; the UI explains this distinction.

## M10 — Backend profiles and authored actor assignments

**Scope:** Add server-configured profile catalog for simple and genuinely available Ocelot/LLM integrations, with a testable provider adapter registry and no browser-supplied secrets. A profile includes stable ID/revision and readiness; optional local secret references stay server-side and never appear in responses or exports. Permit default profiles and per-actor overrides for authored scenarios by materializing a scenario copy; preserve documented precedence and validate actor names. Do not claim built-in `town100` supports per-actor override unless the engine path is implemented and tested. Add backend profile and actor-assignment UI. Model names in the user's example remain examples until configured by the operator.

**Tests:** `test_backends.py`, `test_backends_browser.py`: authored actors resolve default and explicit overrides, unsupported town100 override rejected, unavailable provider and invalid profile rejected, no secret returned/stored in template, fake LLM provider actually called for assigned actor, and no network provider calls in tests. Run `python3 -m pytest -q tests/management/test_backends.py tests/management/test_backends_browser.py`.

**Done:** Previewed assignments are exactly those passed to the engine; an unavailable integration is never reported as ready.

## M11 — Cast generation and backend splits

**Scope:** Introduce an explicit, versioned population-generation contract for scenarios that declare support. Define cast bundles, generated population size, distribution inputs and group/backend assignment, then implement a concrete supported generator rather than editing scenario output cosmetically. Validate group sizes and distribution bounds, stable actor IDs, duplicate names, capacity and deterministic seed streams. Preserve existing `town100` behaviour unless its adapter explicitly supports these options. UI shows cast groups, count allocation and expandable actor assignments only for capable scenarios. No independent map/cast seed or global speech selector unless separately implemented as a validated engine contract.

**Tests:** `test_cast_generation.py`, `test_cast_browser.py`: same seed/config yields identical cast and backend assignments; changed seed affects generated traits; group totals/invalid distributions/duplicates rejected; preview matches the launched effective cast; old `town100` output remains unchanged when no new options are used. Run `python3 -m pytest -q tests/management/test_cast_generation.py tests/management/test_cast_browser.py` plus affected existing town100 tests.

**Done:** User-specified populations influence the real simulation and invalid or unsupported options cannot be submitted.

## M12 — Comparison and release audit

**Scope:** Add a run comparison view for two or more recorded reports with explicit scenario/config/seed/build/provenance and comparable metrics only. Missing data is labelled and incompatible units or report schema are not compared. Add downloadable reproducibility metadata without provider secrets. Complete the end-to-end documentation: local launch, supported configurations, worker/restart semantics, checkpoint restrictions, perspective boundary and troubleshooting. Perform a screen-by-screen accessibility and responsive audit; do not add a multi-user deployment claim.

**Tests:** `test_compare.py`, `test_compare_browser.py`: compatible/incompatible report schemas, missing series, real multi-run comparison, provenance export and secret redaction. End-to-end browser test: configure → preview → run → pause → report → checkpoint → fork → template → compare, with a deterministic small scenario and failure paths. Run `python3 -m pytest -q tests/management` and the full integration gates above.

**Done:** All promised pages work against real service data; every unimplemented feature remains visibly unavailable and documented. The supervisor records final test results and remaining limitations.

## Suggested phase dispatch

> Execute MNN in `docs/design/MANAGEMENT_EXECUTION_PHASES.md` against integration commit `<sha>`. Read the product design and applicable repository instructions; work only in your isolated worktree. Implement its scope and behavioural tests, run the named checks and report baseline, changes, commands/results and limitations in `docs/phases/management-MNN/REPORT.md`. Do not commit, modify other phases, or touch unrelated work. Escalate a missing dependency or conflicting contract with evidence rather than simulating support.
