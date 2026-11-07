# Lazy affordances — final report (LA01-LA06)

Status: program complete, LA06 uncommitted.  Branch `lazy-affordances`.
No commit or stage was performed by the phase agents.

## What changed across the program

| Phase | Commit | Change |
|---|---|---|
| LA01 | `9725e10` | Added the validated `affordance_mode` seam (`menu` default, `lazy` opt-in) to `BigvilleGame`/`create_game`, the menu-versus-observation benchmark, and the first tests. |
| LA02 | `6e54bb4` | Added `BigvilleWorld.resolve_targets(actor, action, params)` and removed the hidden full-menu rebuild from `_enact_plan` for direct stable names/ids/cells. Legacy `target:N` proposals still rebuild the menu. |
| LA03 | `9d54a86` | Added `world.observe(actor)`: a cheap, deterministic, read-only, JSON-safe observation of self, nearby actors, visible objects/containers, cell features, recipes and last outcome. Added object-location and utterance-recipient indices. Lazy `_context` no longer calls `actor_affordances`. |
| LA04 | `e1a8829` | Taught the deterministic simple backend to generate bounded lazy candidates from needs and observations, read refusals, and fall back. Enriched the observation with inventory details, places, cell animals/crops/projects/infrastructure/shops and world containers in reach. |
| LA05 | `ab6d8e7` | Added the lazy agent view and lazy prompt packet, direct-param reply handling, refusal feedback in the next prompt, and kept menu mode for UI pickers and Ocelot's `replace_options` path. |
| LA06 | `uncommitted` | Added the mode evaluation tool and tests, extended the benchmark to the real lazy path and whole-turn time, evaluated the modes, declined the default switch on health evidence, and wrote this report. |

Design plan: `docs/design/LAZY_AFFORDANCES.md`.  Per-phase evidence:
`docs/phases/lazy-affordances/LA0x_REPORT.md`.

## What was removed from the play path

In `affordance_mode="lazy"` only:

- `_context()` builds from `world.observe(actor)` and never calls
  `actor_affordances()` / `_actor_options()`;
- `_enact_plan()` resolves direct stable targets through `resolve_targets()`
  instead of rebuilding the exhaustive menu;
- the simple backend generates its own bounded candidate list from the
  observation instead of receiving the legal menu;
- the LLM prompt packet publishes entities/capabilities and a proposal schema,
  not an exhaustive legal-action list;
- the lazy agent view publishes entities, places and capabilities, not the
  menu.

`affordance_mode="menu"` is still the default, so the exhaustive menu is still
on the default play path.  The lazy path is complete and opt-in, not the
default.  This is deliberate: see the health evidence below.

## What remains on-demand

- **UI action pickers.**  Server `/api/view`, the TUI, `GameService.state()`
  and `EmbeddedClient.affordances()` still call `actor_affordances()` only when
  the UI asks.
- **Ocelot.**  An Ocelot actor, or any backend with
  `wants_affordance_menu = True`, stays on the menu path even in a lazy game.
  Ocelot's `replace_options` contract is unchanged.
- **Menu agent/referee view.**  `game.agent_view()` is the menu view; a referee
  view that needs the exhaustive list asks for it explicitly.
- **Debugging and equivalence.**  Menu mode remains the trace oracle and the
  published-option validation boundary; the Phase 020 tournament and the
  tick-trace digests still exercise it.
- **Benchmark seam.**  `_context(..., skip_affordances=True)` remains as the
  LA01 measurement helper, not as a play path.

## Evaluation and default decision

The LA06 evaluation compared menu and lazy on the same scenario and seed with
simple autonomous backends:

- `town100`, seeds 305000 and 305001, 8 turns;
- a three-resident TG01-style room, 12 turns;
- all runs completed with no refusals, no unhandled errors and all residents
  alive.

Lazy applied the same 100 actions/turn on `town100` and had lower hunger and
higher energy.  But its cheap backend proposed common work recipes without
validating site, tool or ingredients.  The world accepted them and recorded
improvised jobs and accidents:

| run | mode | health mean | health min | improvised jobs | accidents |
|---|---|---|---|---|---|
| town100 seed 305000 | menu | 1.0 | 1.0 | 0 | 0 |
| town100 seed 305000 | lazy | 0.951 | 0.7 | 94 | 49 |
| town100 seed 305001 | menu | 1.0 | 1.0 | 0 | 0 |
| town100 seed 305001 | lazy | 0.957 | 0.8 | 84 | 43 |
| small seed 305000 | menu | 1.0 | 1.0 | 0 | 0 |
| small seed 305000 | lazy | 0.867 | 0.8 | 6 | 4 |

**Decision: `affordance_mode="menu"` stays the default and no `"auto"` mode was
added.**  Lazy remains explicitly selectable.  The next hypothesis is to make
lazy work candidates validate site/tool/ingredients (or stop proposing
unvalidated common recipes), then re-run the same evaluation.  The speed result
alone does not justify a health regression.

Full LA06 tables, exact commands and benchmark numbers are in
`docs/phases/lazy-affordances/LA06_REPORT.md`.

## What the evidence says about Rust next

- Menu construction was the dominant context cost: on the synthetic benchmark,
  menu context was **13.8x** lazy at 50 residents, **8.8x** at 100 and
  **9.4x** at 200.
- Whole-turn time improved much less: **2.35x**, **1.40x** and **1.28x**.
  Commit and physical work dominate as resident count rises.
- Therefore a native rewrite of the affordance-menu builder is **not
  justified**: the lazy design already removes most of that work, and the
  remaining bottleneck is the validated turn/commit path.
- If native acceleration is considered later, the evidence points at commit
  and world-tick work, not at menu construction.  Nothing in this program adds
  or requires a Rust dependency.

## Tests and full-suite status

Executed in this worktree:

```bash
python3 -m pytest -q tests/test_lazy_evaluation.py tests/test_lazy_llm.py \
  tests/test_lazy_cheap.py tests/test_lazy_observation.py \
  tests/test_lazy_target_resolution.py tests/test_lazy_affordances.py \
  -p no:cacheprovider
# 83 passed in 67.08s

python3 -m pytest -q tests/test_bigville_game_api.py tests/test_simple_life.py \
  tests/test_phase055_concurrency.py -p no:cacheprovider
# 48 passed, 1 failed in 76.46s

python3 domains/bigville_entities.py
# exit 0: 0 errors, 0 warnings
```

The one failure is the environment-sensitive concurrency timing assertion,
`test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical`
(`sequential=13.61s`, `concurrent=11.77s`, ratio `0.86`).  Its semantic
assertions (identical digests and identical provider calls) passed.  The host
was heavily contended and another pytest suite was active.

The **full suite did not complete** and no full-suite pass is claimed.  It
remains the final gate for an idle host.

## Limitations carried forward

- Lazy mode had zero refusals in all evaluation runs; refusal variety and
  trade parity were not exercised by these scenarios.
- The small room published no menu affordances, so its comparison isolates the
  lazy work defect rather than judging action quality.
- The lazy health loss is tied to unvalidated work candidates.  Eat, rest,
  move, fetch/put, tend, care and refusal fallback are covered by tests but
  were not the dominant actions over these seeds.
- Mode selection is per game, not per actor, except for Ocelot's explicit
  per-actor menu exception.
- Wall-clock numbers are same-host relative measurements under contention.
