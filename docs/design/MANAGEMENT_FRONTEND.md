# Bigville management frontend: assessment and design

Status: design proposal, 6 November 2026. The companion `new-run-prototype.html` is a local, illustrative prototype; it does not create or change runs. Existing behaviour can change as the code evolves.

## Purpose and scope

Give a researcher or operator one place to configure, start, observe, reproduce and compare simulations. Keep the existing village game as the spatial view inside a run. The primary workflow is **configure → validate → start → observe → checkpoint/export → compare**. A run is an immutable initial configuration plus an execution history; a template is a reusable configuration, not a saved world; a checkpoint is a point-in-time world and agent state, not a template.

## Assessment of the current system

| Capability | What exists | Implication for the UI |
|---|---|---|
| Worlds and scenarios | `create_game` accepts the built-in `town100` or a scenario ID, file, or inline definition. Scenarios contain map, actors, seeds, initial conditions, laws and policies. `list_scenarios()` lists JSON scenarios; `town100` is a special built-in. | Catalog both kinds and describe their capabilities. Do not assume all scenarios are villages. |
| Population | `town100` builds a founding town with generated residents, jobs, households and seeded traits from pack data. Other scenarios define actor records and can specify per-actor backends. | Show the actual resolved cast and source. A free population count, cast bundles, backend splits and editable distributions need a generator/configuration layer; “20 core + 80 generated” is an example, not a current contract. |
| Seeds and map | `town100` uses one seed for its generated town and cast, with internal streams. Other scenarios may have authored maps. | Show a single effective world seed initially, materialise random as an integer before launch, and keep it visible. A separate map seed requires backend support; don't pretend changing it is independent. A preview needs a preview endpoint. |
| Backends | Simple/cheap, human, Ocelot and provider-neutral LLM adapters exist. Scenario actor choices override the default. LLM needs a supplied provider; Ocelot needs its integration. | Show configured provider profiles and availability checks, not a fixed list of model claims. Per-actor editing requires scenario materialisation/orchestration, especially for `town100`. Keep credentials server-side. |
| Controls and time | `create_game` supports autonomous or human-controlled sessions and `ticks_per_period`; the scenario runner runs unattended turns and records traces. | Provide run mode, player selection when applicable, turn limit and cadence. Autonomous and human-player modes are mutually exclusive. Continuous operation, pause and scheduling require a worker/service. |
| World switches | World validates named physical subsystem booleans with defaults in `BigvilleWorld`; scenario data can set them. | Populate actual supported switches and effective defaults from a capability API. Metabolism, ecology, decay and illness are examples. Do not present purchases or bank accounting as independent switches without an implemented gate. |
| Speech | Backend speech interfaces and structured/opaque messages exist; capabilities vary by backend. | Display actual backend communication capabilities. The proposed enforced/structured/seeded selector requires a defined system contract and enforcement; don't imply it exists. |
| Inspect and report | World state, actor views, game report and runner trace expose population, economy, social and physical data. The current server exposes health, state, view, report, turn and reset for one in-memory session. | Reuse the renderer and reports, with explicit referee vs resident perspective. Multi-run history, timelines, comparisons, export and historical data require storage/service work. |
| Persistence | Game and world checkpoint modules save and restore at quiescent boundaries, with supported backend/adapter restrictions. | Show checkpoint eligibility and errors before save; do not promise every custom provider can restore. Checkpoint HTTP APIs and managed storage are needed. |

Source: `bigville/api.py`, `bigville/scenarios.py`, `worlds/bigville_town100_world.py`, `worlds/bigville_world.py`, `bigville/server.py`, `bigville/scenario_runner.py`, `bigville/reporting.py`, `bigville/game_persistence.py`, `bigville/backends/llm.py`, and `docs/SCENARIOS.md`. Treat the running server's capability response as authoritative, rather than hard-coding this assessment.

## Information architecture

Persistent sidebar: **Runs**, **Templates**, **Worlds & casts**, **Backends**. Settings and help sit at the bottom. Run-specific pages share a header containing run name, status, scenario, effective seed, and actions relevant to its state.

1. **Runs** — default landing page. Search/filter by status, scenario and creation date; rows show name, state, world, population, turn/time, last activity and backend summary. Primary action: New run. Resume, duplicate configuration, open results and archive are contextual. Empty state explains how to start. Statuses: draft, queued, starting, running, paused, waiting for input, completed, failed, stopped. Only show states the service actually supports.
2. **New run / edit draft** — progressive sections on one page: identity/template, world, population & backends, map, rules, execution, review. A sticky summary shows the effective configuration and validation; no irreversible action until Start. More detail below.
3. **Run overview** — current status, simulated date/turn, population, backend counts, current activity and errors, with Start/Pause/Resume/Stop as appropriate; links to the live world and reports. Explain waiting for human input. Stop does not silently delete results. Provide confirmation for stopping a running simulation.
4. **World** — existing map renderer and resident inspector; camera controls, time/turn controls and a selectable resident. The perspective switch explicitly separates referee state from resident knowledge, and resident view uses the server's agent view rather than filtering an omniscient snapshot in the browser. A run without a map has an appropriate table/text view. Do not imply the current player UI is already compatible with the agent-only endpoint.
5. **Population** — sortable residents, alive/dead status, role, location, backend and relevant health; filters and a resident detail drawer. Details separate physical state, backend-provided state and a resident's observations. In referee mode, link to an actor-specific perspective; don't expose private state in agent mode. Backend changes mid-run are disabled until lifecycle semantics exist.
6. **Events & traces** — chronological, filterable actions, outcomes, speech and world events, with turn and actor filters. Distinguish recorded trace data from event summaries and clearly show when tracing was not enabled; absence of a recorded event is not proof nothing happened. Detailed traces can be large and should paginate.
7. **Reports & compare** — population, economy, social and physical metrics with units, census/sample labels and time series where recorded; compare compatible runs side by side, retaining seed, scenario and configuration. Show missing or incomparable data rather than inventing zeros. Export report/trace when available.
8. **Checkpoints & artifacts** — checkpoint list, turn/time, backend compatibility, restore and fork actions, trace/report downloads and provenance. A fork creates a new run, preserves the parent and records the checkpoint; checkpoint operations wait for a quiescent boundary.
9. **Templates** — list, create from configuration, version and duplicate templates. Preview changes and show missing/obsolete capabilities before applying. Applying a template changes the draft, not a running session. Runs retain the resolved template version and configuration.
10. **Worlds & casts** — catalog scenario/pack metadata, map and actor definitions, and inspect what is authored versus generated. Cast editing and distribution presets are future authoring features, separate from the run's configuration. Avoid treating a scenario as a location or a pack as a scenario.
11. **Backends** — manage named local backend/provider profiles, connection readiness and configuration; never display or export secrets. Ocelot prerequisites and LLM provider adapters are checked by the service. Adding model profiles, credentials, budgets and spend limits requires explicit service support. Named models in the brief are example profile names, not installed providers.

## New-run interaction design

Desktop: 232px navigation rail, central form column (maximum 840px), 300px sticky review panel. Mobile: top bar, stacked sections and an expandable review drawer. Each section can collapse after validation. Inputs have labels, help, keyboard access and text errors; colour never carries status alone. No forced wizard: sections are navigable, with a clear final review.

**Identity.** Run name (required, not necessarily unique); optional description; template picker with version and explicit Load action. Loading a template into a changed draft shows a replace/keep decision. Display a server-generated immutable run ID and engine/pack version or hash once created; do not conflate that with the editable run name.

**World.** Searchable scenario picker, with description, type, source and version/hash. Show `town100` alongside authored scenarios, plus scenario-specific options supplied by capabilities. On world change, show which prior overrides will be discarded, then revalidate.

**Population & backends.** Display resolved population, composition and an actor table. Default backend applies only where there is no explicit actor assignment. Show the effective source (scenario override, group override if implemented, or default). Expand rows for per-actor choice where supported. Proposed cast groups, generated count, proportional backend splits and demographic/trait distributions are advanced configuration features, shown only after generator support exists; counts must add up and assignment rules must be deterministic. Display estimated provider availability and unknown cost without making up pricing.

**Map.** Show selected scenario's map type and whether authored or generated; provide preview after the server can construct a read-only preview from the exact draft. One run seed initially, with Random and explicit numeric input; resolve random once and retain the value for preview, launch and reproduction. Separate map/cast seeds remain unavailable until supported.

**Rules.** Searchable, grouped supported physical switches with on/off, default, description and effects. Show effective values inherited from the scenario. Display rules whose implementation cannot be turned off as information, not switches. Speech is described per backend; a global mode is a future option subject to a defined policy. Advanced settings should never expose raw internal flags as if they are validated product features.

**Execution.** Autonomous or human-controlled; select player only for human mode; ticks per period with “world default” and disabled option if supported; optional turn limit; tracing choice and storage implications. New runs have no preselected provider secret. Validate availability and checkpoint support based on the actual selected backend profiles.

**Review and start.** Show exact effective scenario/pack/build identity, seed, cast/backend assignment, subsystem switches, mode, turn limit and cadence. Validate client-side for immediate feedback, then server-side against a capability revision. Indicate warnings separately from blockers. Start creates a run once using an idempotency key; lock duplicate submission. Show creation/launch errors in context and keep the draft. A preview is not proof of backend/provider readiness.

## Service and data design

The current `GameService` is single-session and in-memory; adding a management UI requires a separate orchestrator rather than assuming its existing endpoints are multi-run. Proposed resources:

- `GET /api/capabilities` — versioned scenario/pack, backend, model-profile, map, switch and checkpoint support; availability and validation metadata.
- `GET/POST /api/templates`, `GET /api/templates/{id}/versions/{version}` — immutable versioned templates.
- `POST /api/run-drafts/validate` and `POST /api/run-drafts/preview` — resolve one draft using the same generator and seed as launch, return effective config, warnings/errors and a preview identifier/hash; do not start or mutate a run.
- `GET/POST /api/runs`, `GET /api/runs/{id}` — persistent metadata, immutable resolved configuration and idempotent creation; `POST /api/runs/{id}/commands` for state-checked start, pause, resume, step and stop. Operations return status and errors, not fabricated completion.
- Run-scoped `state`, `view`, `report`, `events`, `trace`, `checkpoints` and artifact endpoints, with pagination, authorization, separate referee/agent access and documented retention. `POST /api/runs/{id}/checkpoints` and a fork operation must validate quiescence and adapters.

A run record stores ID, name, timestamps, status, scenario and pack identity, source/configuration hashes, concrete seed, fully resolved actor/backend assignments, subsystem values, mode, cadence, trace policy, parent checkpoint and artifact references. Provider profiles are referenced by ID and revision, never embedded secrets. Store actual reproducibility metadata and explain that a seed alone cannot guarantee identical runs across builds, provider behaviour or external dependencies. Server validation is authoritative and rejects unsupported or stale settings; defaults and override precedence are visible in the review. Define actor action outcomes, access controls, scheduling, cancellation, concurrency and checkpoint support before exposing those controls.

## Delivery sequence

1. Capability catalog and read-only management shell, scenario/actor detail, report and existing session view. Keep current game functionality working.
2. Validated draft and launch for capabilities the engine actually accepts; materialise effective settings and add persistent run registry/worker, stateful execution controls and error handling.
3. Checkpoint/fork and artifact storage, with adapter compatibility; reports and recorded trace browsing.
4. Templates, comparison and provenance; then separately design and implement configurable population generation, cast groups, independent seeds and global speech controls as supported contracts emerge.

## Acceptance criteria

- A user can discover actual available scenarios and backends, identify unavailable integrations, and review effective actor backend precedence before launch.
- The preview and launched run use the same saved numeric seed and resolved inputs. Unsupported settings cannot silently appear to work.
- A running, waiting, completed or failed run shows its actual state; actions respect the state and a human-input wait is not presented as completion.
- Resident and referee views use the appropriate server boundary. Reports distinguish recorded history, samples and missing data.
- A checkpoint operation states compatibility and failure clearly; restoring or forking preserves provenance and never overwrites the parent silently.
- Desktop and narrow layouts are usable by keyboard, and errors are associated with their inputs. The visual prototype is labelled as illustrative and cannot start a run.
