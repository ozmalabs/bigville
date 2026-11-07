# Lazy affordances: observations, proposals and validation

Status: complete, LA06 uncommitted, 8 November 2026. This plan replaces the
per-turn, per-resident exhaustive list of legal actions with an observation/
proposal/validation model. It builds on the tick-graph work but is an
independent program. LA06 kept `menu` as the default on health evidence; the
lazy path is implemented and opt-in.

## Principle

The world owns three separate things, and they must not be conflated:

1. **What exists:** residents, objects, containers, buildings, land, animals,
   stocks, positions and their observable properties.
2. **What is legal:** whether a proposed action is admissible *now*.
3. **What is worth doing:** a cognition backend's choice.

Today `BigvilleWorld._actor_options()` constructs (1) + (2) for every resident
on every turn. The result is a combinatorial menu: every visible object
against every possible destination, every carried kind against every recipient,
every held kind against every container, and so on. It dominates the turn
(87-94% of measured step time at 50-200 residents). It is also the wrong
interface: the legal space is not the interesting space.

The lazy model:

- observation publishes **entities and capabilities**;
- cognition **proposes** an action using stable ids, names or cells;
- the world **validates** it and either applies it or refuses with an existing
  refusal code;
- a refusal is normal feedback. The backend may fail, retry, or choose a
  fallback next turn.

The world must never silently rewrite an invalid proposal into a valid one.

## Invariants

1. **World authority.** Every applied major action still passes through
   `major_action()` / `_enact_plan()` and its physical checks. No proposal path
   bypasses validation.
2. **No exhaustive menu on the play path.** In lazy mode, `_context()` must not
   call `actor_affordances()` / `_actor_options()`.
3. **Stable identities.** Proposals refer to actors, objects, containers,
   buildings and cells by stable names/ids or cells. Ephemeral `target:N` keys
   are a compatibility format, not the primary interface.
4. **Failure is ordinary.** Unknown, unreachable, unavailable or malformed
   proposals return `False` and an existing refusal reason. They must not raise
   into the turn or abort other residents.
5. **Menu mode is preserved.** `affordance_mode="menu"` keeps the current
   behaviour for equivalence tests, Ocelot's current adapter, UI action pickers
   and debugging. Lazy mode is opt-in until its evaluation passes.
6. **Executor independence.** Serial, threaded and partitioned tick-graph
   execution and the TG06 simultaneous claim policy continue to work
   unchanged.
7. **No Rust dependency.** Native acceleration is considered only after the
   lazy path is measured; it is not part of this plan.

## Phases

Each phase is executed by one agent, reviewed by the supervisor, and committed
with a report in `docs/phases/lazy-affordances/LAxx_REPORT.md`. Agents do not
commit or stage. Phases run in order.

### LA01 — Mode flag, measurement and baseline

**Scope:** Add `affordance_mode` (`"menu"` default, `"lazy"` opt-in) to
`BigvilleGame` and `create_game`; add a benchmark that measures the cost of
menu construction versus observation-only context.

**Files:** `bigville/game.py`, `bigville/api.py`,
`tools/benchmark_affordances.py` (new), `tests/test_lazy_affordances.py` (new),
`docs/phases/lazy-affordances/LA01_REPORT.md`.

**Deliverables:**
- Validated `affordance_mode in {"menu", "lazy"}`. Any other value raises
  `ValueError` at construction. Default stays `"menu"`.
- The mode is exposed on the game and passed through `create_game`.
- In LA01, lazy mode may still call the menu internally (a placeholder), but
  the mode and the report must state that clearly.
- Benchmark builds synthetic 50/100/200-resident scenarios (reuse the TG07
  scenario builder), measures context build with a menu path and an
  observation-only path, and prints JSON plus a table. Observation-only is a
  local measurement helper, not yet the lazy game path.
- Tests: option validation; default `menu` trace unchanged; benchmark builder
  imports without running.

**Gate:** targeted tests; no behaviour change in menu mode.

### LA02 — Action-specific target resolution

**Scope:** Remove the hidden full-menu rebuild from enactment. Add
`world.resolve_targets(actor, action, params)` and use it in `_enact_plan()`.
This is the prerequisite for any lazy proposal path.

**Files:** `worlds/bigville_world.py`, `tests/test_lazy_target_resolution.py`
(new), report.

**Deliverables:**
- `resolve_targets(actor, action, params)` returns whatever `_enact_plan` needs
  for that action and no more: recipients for give/transfer, containers for
  put/fetch, objects/destinations for move_object, destinations for move,
  food kinds for eat, recipes/sites/tools for work, targets for contests, etc.
  It must populate `_actor_targets[actor]` only with that action's candidates,
  preserving compatibility with existing `target:N` proposals.
- `_enact_plan()` no longer calls `_actor_options()` wholesale for target
  resolution. It accepts direct actor/object/container names and cells in
  addition to legacy target keys.
- A caller may still request the full menu; that is not on the enactment path.
- Tests:
  - every option from `actor_affordances()` still enacts on a tournament of
    scenarios (reuse `test_phase020_validation.py` style);
  - direct-name/direct-cell proposals enact or refuse with the same result as
    the target-key form;
  - `_enact_plan` for each verb does not invoke `_actor_options` (instrument and
    assert);
  - menu-mode traces unchanged on the standard scenarios.

**Gate:** targeted tests plus `tests/test_phase020_validation.py`; no behaviour
change.

### LA03 — Observation model and indices

**Scope:** Publish entities and capabilities instead of a legal menu, and make
the observation itself cheap.

**Files:** `worlds/bigville_world.py`, `bigville/game.py`,
`tests/test_lazy_observation.py` (new), report.

**Deliverables:**
- `world.observe(actor)` (name to be agreed in implementation) returns a
  JSON-safe observation with:
  - self state: position, terrain, body needs, inventory, held/worn, job,
    continuation, turn state;
  - nearby actors: stable id, name, distance, role/group, relationship signal;
  - visible objects: stable id, kind, location, and capability tags
    (`grabbable`, `container`, `open`, `edible`, `tool`, `reachable`);
  - containers/objects in reach with open/locked/contents-summary;
  - current cell features: building, land, gathering site, fixtures, exits;
  - known recipes, relevant skill/tool facts, `last_outcome`.
- Add derived indices to make it cheap:
  - object location -> objects;
  - recipient -> utterances (for `heard_utterances`);
  - keep the TG02 occupancy index for nearby actors.
- Lazy `_context()` uses `observe(actor)` and does **not** call
  `actor_affordances()`. The menu-mode context is unchanged.
- Tests: observation equals a brute-force/local reference; no world mutation;
  repeated observations are deterministic; a 100/200-resident micro-benchmark
  records context time for menu vs lazy (lazy can still be a stub in this
  phase, but the observation call must be measured).

**Gate:** targeted tests; menu-mode traces unchanged.

### LA04 — Lazy cognition for the simple backend

**Scope:** Make `DeterministicBackend` (cheap/simple) work without the menu.
It generates candidates from needs and observations; the world validates.

**Files:** `bigville/backends/cheap.py`, `bigville/backends/protocol.py` if a
context field is needed, `tests/test_lazy_cheap.py` (new), report.

**Deliverables:**
- Candidate generation from:
  - needs: eat a carried food, rest, sleep;
  - current cell/job/continuation: continue work, water/harvest/tend/fertilise
    when the cell exposes it;
  - goals: move toward home/work/market/site, speak to nearby actors;
  - local entities: give/transfer to nearby actors, put/fetch at containers in
    reach, pick up/move visible objects.
- The candidate list is bounded by local entities (nearby actors, objects in
  reach, current cell features), not the whole world.
- Existing scoring is reused where practical. If a proposal is refused, the
  backend reads `last_outcome`/`last_rejections` and takes a fallback: a safer
  candidate (rest/eat/move) or a fresh decision next turn.
- Menu mode remains the default in this phase; lazy mode is opt-in.
- Tests: eat/move/work/give/pick-up paths on small scenarios; an invalid
  proposal is refused with the expected code and does not abort the turn; the
  fallback acts; menu-mode traces unchanged; refusal rate is reported (not
  asserted to a fixed number).

**Gate:** targeted tests; a short 8-turn lazy run on the small scenario and
town100 completes with no unhandled errors.

### LA05 — LLM prompt, agent view, Ocelot and UI on-demand

**Scope:** Adapt the text/prompt-facing surfaces to entities/capabilities and
keep the full menu as an explicit query.

**Files:** `bigville/backends/prompts.py`, `bigville/backends/llm.py`,
`bigville/backends/prompt_packet.py`, `domains/agent_view.py`,
`bigville/server.py`, `bigville/tui/client.py`, report.

**Deliverables:**
- Lazy prompt packet: a bounded list of visible entities with stable ids and
  capability tags, current cell features, known recipes, and the proposal
  schema. No exhaustive legal-action list.
- The LLM adapter parses proposals using stable ids; an invalid proposal
  reaches the world, is refused, and is returned to the provider as feedback
  on the next turn (or falls back to autopilot if configured).
- `agent_view` exposes the lazy observation by default in lazy mode; the full
  menu remains available through the existing explicit affordance query.
- Server/TUI action pickers call `actor_affordances()` only when the UI asks,
  never as part of a turn's context.
- Ocelot's `replace_options` path remains available in menu mode. Lazy mode
  documents that Ocelot must either request a menu or consume the observation
  adapter; no silent fallback that breaks its contract.
- Tests: fake-provider prompt contains entities and not the full option list;
  a refused proposal is visible in the next prompt; UI on-demand endpoints still
  list options; menu-mode tests unchanged.

**Gate:** targeted LLM/agent-view/server tests; no network calls.

### LA06 — Evaluation, default decision, benchmark and final report

**Scope:** Decide the default from evidence, remove the per-turn menu from the
default play path if the evaluation supports it, and document the result.

**Files:** `bigville/game.py`, `bigville/api.py`, scenario/management docs,
`tools/benchmark_affordances.py`, `docs/phases/lazy-affordances/LA06_REPORT.md`,
this plan's status table.

**Deliverables:**
- A reproducible evaluation comparing `menu` and `lazy` over the standard
  scenarios and seeds: turns completed, refusals by reason, actions applied,
  hunger/energy/health outcomes, work and trade counts, and wall-clock time.
- If lazy is not worse on the agreed primary outcomes, make it the default for
  autonomous simple runs and keep `menu` selectable. If it is worse, leave
  `menu` as the default and record the evidence and the next hypothesis. Do not
  hide a regression.
- Benchmark 50/100/200 residents: context time, total turn time, refusals and
  options built (menu mode only), with the exact command.
- Notes for management/scenario configuration: how to select the mode, what the
  UI does, and which callers still require a full menu.
- Final report states what was removed from the play path, what remains
  on-demand, and what would justify Rust next.

**Gate:** targeted suite, `python3 domains/bigville_entities.py`, and the full
suite when the host is not contended; if the full suite cannot finish, record
the exact command, duration and failure/timeout rather than claiming a pass.

### LA07 — Lazy work prefilter and re-evaluation (follow-up)

**Scope:** Remove the LA06 health regression without rebuilding the menu: give
the lazy work candidate the same cheap site/tool/ingredient prefilter the menu
uses, then re-run the LA06 evaluation.

**Files:** `worlds/bigville_world.py`, `bigville/backends/cheap.py`,
`tools/evaluate_affordance_modes.py` only if the evidence needs another field,
`tests/test_lazy_work.py` (new), report.

**Deliverables:**
- `world.recipe_preview(actor, recipe)` is read-only and returns
  `{ok, reason}` using the same conditions the menu's work loop uses:
  not busy, `_can_attempt`, and `_recipe_inputs_available`. It must not open a
  job, consume stock, or claim the action slot.
- `world.observe(actor)` publishes `busy` (or the equivalent the candidate
  generator needs).
- The lazy cheap backend only proposes `work` for recipes whose preview is ok,
  and does not propose work while busy. A refused work proposal that still
  slips through is handled by the existing refusal fallback.
- Tests: preview agrees with the menu's work filter over a matrix of known /
  unskilled / out-of-season / missing-input / missing-site cases; lazy
  candidates contain no work when the preview is false; an 8-turn `town100`
  lazy run has no improvised jobs or accidents, or the remaining causes are
  identified.
- Re-run the LA06 comparison (town100 seed 305000/305001, 8 turns; small, 12
  turns). If lazy now matches menu on health and applied actions, revisit the
  default decision; if not, keep `menu` and record the next cause. Do not add
  `"auto"` or change the default without the evidence.

**Gate:** targeted lazy tests, the work-filter matrix, and the re-evaluation.

### LA08 — Default rollout

**Scope:** Add an `"auto"` mode and make it the `create_game` default after the
LA07 evidence. `auto` resolves to `lazy` only for an autonomous session with no
player, a built-in simple/cheap default backend, and no LLM or Ocelot actor.
Everything else resolves to `menu`. A direct `BigvilleGame` constructor keeps
`menu` as its default; callers may pass `"auto"` explicitly.

**Files:** `bigville/game.py`, `bigville/api.py`,
`tests/test_lazy_default.py` (new), `tools/evaluate_affordance_modes.py` only
if the evidence needs another mode label, `docs/phases/lazy-affordances/LA08_REPORT.md`,
`FINAL_REPORT.md`, `README.md`, this plan's status table.

**Deliverables:**
- `"auto"` is a validated request value; the game exposes the resolved mode
  (`affordance_mode`) and the requested value.
- `create_game` defaults to `"auto"`; explicit `"menu"`/`"lazy"` still win.
- Resolution is deterministic and documented. It never silently downgrades an
  unsupported combination; it selects menu for player/LLM/Ocelot.
- Tests: resolution matrix (autonomous simple -> lazy; player -> menu;
  LLM/Ocelot -> menu; explicit modes unchanged); menu remains available for
  UI/Ocelot/debug.
- Run the affected existing tests. If the new default breaks tests that
  specifically assert menu behaviour, pass `affordance_mode="menu"` in those
  tests only where they are menu tests; do not weaken behavioural assertions.
  If failures cannot be resolved without hiding a regression, revert the
  default and report it.
- Re-run the LA06/LA07 evaluation on the resolved defaults and record the
  final numbers. Update `FINAL_REPORT.md` and the README to say what is now
  the default and what remains menu-only.

**Gate:** targeted suites plus the evaluation; full suite remains the final
gate on an idle host.

## Status

| Phase | Status | Commit |
|---|---|---|
| LA01 | complete | `9725e10` |
| LA02 | complete | `6e54bb4` |
| LA03 | complete | `9d54a86` |
| LA04 | complete | `e1a8829` |
| LA05 | complete | `ab6d8e7` |
| LA06 | complete | `e687661` |
| LA07 | complete (uncommitted) | — |
| LA08 | complete (uncommitted) | — |

## Results

LA06 evaluated the two modes on the same scenarios and seeds with simple
autonomous backends: `town100` seed 305000 and 305001 for 8 turns, and the
small TG01-style room for 12 turns.  The full table is in
`docs/phases/lazy-affordances/LA06_REPORT.md`.

- **Applied actions and survival were not worse.** Both modes applied 100
  actions per turn on `town100`, refused none, and kept all 100 residents
  alive over 8 turns.  Lazy had lower hunger (0.0 vs 0.116) and higher energy
  (95.1/95.7 vs 42.0/41.9).
- **Health was materially worse in lazy mode.** The lazy work candidates
  include common recipes without validating the site, tool or ingredients.
  Over 8 `town100` turns that produced 84-94 improvised jobs and 43-49
  accidents, lowering mean health to 0.951/0.957 (minimum 0.7/0.8) against
  1.0 in menu mode.  The small run reproduced it: 36 applied `work` actions,
  6 improvised jobs, 4 accidents, mean health 0.867 against 1.0.
- **Context construction is much cheaper, but total turn time less so.** On the
  synthetic benchmark, menu context was 13.8x lazy at 50 residents, 8.8x at
  100 and 9.4x at 200; whole-turn time was 2.35x, 1.40x and 1.28x.  Commit and
  physical work still dominate as resident count rises.

**Decision:** `affordance_mode="menu"` remains the default.  No `"auto"` mode
was added.  Lazy stays explicitly selectable and on-demand surfaces keep using
the menu.  The next hypothesis is to make the lazy work proposal validate
site, tool and ingredients (or simply stop proposing unvalidated common
recipes) before re-running this evaluation; the speed result alone does not
justify the health regression.

## Integration gates

After every phase:

```bash
python3 -m pytest -q tests/test_lazy_*.py -p no:cacheprovider
python3 -m pytest -q tests/test_phase020_validation.py tests/test_phase035_nutrition.py \
  tests/test_phase048_tool_fitness.py tests/test_bigville_world_migrated.py \
  -p no:cacheprovider
```

Before the supervisor commit:

```bash
python3 domains/bigville_entities.py
```

The full suite is the final gate, not a per-phase gate.

## Relationship to the tick graph

The tick graph stays: observation -> proposal -> validation -> effect intent ->
tick graph -> deterministic commit. Removing the menu changes where proposals
come from, not how validated effects are ordered or committed. `menu` mode
continues to exercise the same executor paths, so the TG01-TG07 equivalence
harness remains valid.
