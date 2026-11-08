# Lazy affordances — final report (LA01–LA08)

Status: program complete, LA07/LA08 uncommitted.  Branch `lazy-affordances`.
No commit or stage was performed by the phase agents.

## What changed across the program

| Phase | Commit | Change |
|---|---|---|
| LA01 | `9725e10` | Added the validated `affordance_mode` seam (`menu` default, `lazy` opt-in) to `BigvilleGame`/`create_game`, the menu-versus-observation benchmark, and the first tests. |
| LA02 | `6e54bb4` | Added `BigvilleWorld.resolve_targets(actor, action, params)` and removed the hidden full-menu rebuild from `_enact_plan` for direct stable names/ids/cells. Legacy `target:N` proposals still rebuild the menu. |
| LA03 | `9d54a86` | Added `world.observe(actor)`: a cheap, deterministic, read-only, JSON-safe observation of self, nearby actors, visible objects/containers, cell features, recipes and last outcome. Added object-location and utterance-recipient indices. Lazy `_context` no longer calls `actor_affordances`. |
| LA04 | `e1a8829` | Taught the deterministic simple backend to generate bounded lazy candidates from needs and observations, read refusals, and fall back. Enriched the observation with inventory details, places, cell animals/crops/projects/infrastructure/shops and world containers in reach. |
| LA05 | `ab6d8e7` | Added the lazy agent view and lazy prompt packet, direct-param reply handling, refusal feedback in the next prompt, and kept menu mode for UI pickers and Ocelot's `replace_options` path. |
| LA06 | `e687661` | Added the mode evaluation tool and tests, extended the benchmark to the real lazy path and whole-turn time, evaluated the modes, and declined the default switch on a lazy health regression. |
| LA07 | uncommitted | Added `world.recipe_preview(actor, recipe)` and the observation's bounded `work_candidates`, so the lazy cheap backend only proposes work whose site, tool and ingredients the menu would also publish. Re-evaluated: the health regression is gone. |
| LA08 | `689b499` | Added `affordance_mode="auto"`, made it the `create_game` default, kept the direct constructor on `menu`, resolved lazy only for autonomous simple/cheap sessions, re-resolved on backend changes, and rolled out the evaluation/docs. |

Design plan: `docs/design/LAZY_AFFORDANCES.md`.  Per-phase evidence:
`docs/phases/lazy-affordances/LA0x_REPORT.md`.

## What is removed from the default play path

`create_game` now defaults to `affordance_mode="auto"`.  For an autonomous
session whose resident backends are all built-in simple/cheap — the common
headless simulation and test setup — the default resolves to lazy:

- `_context()` builds from `world.observe(actor)` and never calls
  `actor_affordances()` / `_actor_options()`;
- `_enact_plan()` resolves direct stable targets through `resolve_targets()`
  instead of rebuilding the exhaustive menu;
- the simple backend generates its own bounded candidate list from the
  observation instead of receiving the legal menu;
- the LLM prompt packet and lazy agent view publish entities/capabilities and a
  proposal schema, not an exhaustive legal-action list.

The exhaustive menu is still built for, and only for, sessions that need it:
a player, an LLM, an Ocelot actor, another backend, or an explicit
`affordance_mode="menu"`.

## What remains on-demand or menu-only

- **UI action pickers.**  Server `/api/view`, the TUI, `GameService.state()`
  and `EmbeddedClient.affordances()` still call `actor_affordances()` only when
  the UI asks.
- **Ocelot.**  An Ocelot actor, or any backend with
  `wants_affordance_menu = True`, stays on the menu context even in a lazy game.
  Ocelot's `replace_options` contract is unchanged.
- **Player and LLM sessions.**  `"auto"` selects menu for them; explicit
  `"lazy"` remains available to a caller that wants the LA05 lazy LLM path.
- **Menu agent/referee view.**  `game.agent_view()` is the menu view; a referee
  view that needs the exhaustive list asks for it explicitly.
- **Debugging and equivalence.**  Menu mode remains the trace oracle and the
  published-option validation boundary; the Phase 020 tournament and the
  tick-trace digests still exercise it.
- **Benchmark seam.**  `_context(..., skip_affordances=True)` remains as the
  LA01 measurement helper, not as a play path.

## Evaluation and default decision

LA06 compared menu and lazy with simple autonomous backends on `town100` seeds
305000 and 305001 for 8 turns and a three-resident TG01-style room for 12 turns.
Lazy applied the same actions and survived, but its cheap backend proposed work
without validating site, tool or ingredients.  The world accepted those
proposals and recorded 84–94 improvised jobs and 43–49 accidents, lowering mean
health to 0.951/0.957 (minimum 0.7/0.8) against 1.0 in menu mode.  LA06
therefore kept `menu` as the default.

LA07 fixed the cause without rebuilding the menu.  The lazy backend now only
proposes recipes whose `recipe_preview` passes the same structural checks the
menu uses, and proposes no work while busy.  The re-evaluation removed the
regression:

| run | mode | health mean | health min | improvised jobs | accidents |
|---|---|---|---|---|---|
| town100 seed 305000 | menu | 1.0 | 1.0 | 0 | 0 |
| town100 seed 305000 | lazy | 1.0 | 1.0 | 1 | 0 |
| town100 seed 305001 | menu | 1.0 | 1.0 | 0 | 0 |
| town100 seed 305001 | lazy | 1.0 | 1.0 | 0 | 0 |
| small seed 305000 | menu | 1.0 | 1.0 | 0 | 0 |
| small seed 305000 | lazy | 1.0 | 1.0 | 0 | 0 |

On `town100`, both modes applied 800 actions over 8 turns, refused none, and
kept all 100 residents alive.  Lazy had lower hunger (0.107 vs 0.116) and higher
energy (46.7/46.4 vs 42.0/41.9).  Context construction was 2.7–3.2x cheaper
(0.88–0.94s vs 2.68–3.05s), and whole-turn wall time was slightly lower in
LA08's runs (19.6–20.2s vs 21.1–24.7s).

**Final default: `create_game(..., affordance_mode="auto")`.**  It resolves to
lazy for an autonomous session with only built-in simple/cheap backends and to
menu for a player, LLM, Ocelot or any other backend.  A direct
`BigvilleGame(world)` still defaults to `"menu"`; explicit `"menu"`/`"lazy"`
always win.  `game.affordance_mode_requested` reports the request and
`game.affordance_mode` reports the resolved mode.  `set_backend()` re-resolves
an `"auto"` session, so injecting an LLM after construction correctly switches
it to menu.

An 8-turn default-mode `town100` run with `default_backend="simple",
autonomous=True` reported `requested_mode="auto"`, `resolved_mode="lazy"`, 800
applied, 0 refused, all 100 alive, health 1.0, and the same actions and metrics
as the explicit lazy run.  The default is genuinely lazy.

Full LA06/LA07/LA08 tables, exact commands and benchmark numbers are in
`docs/phases/lazy-affordances/LA06_REPORT.md`,
`LA07_REPORT.md` and `LA08_REPORT.md`.

### Small-room energy caveat

The goal-free three-resident room is still a degenerate comparison.  Menu
publishes no affordances and idles (energy 100, hunger 0).  Lazy proposes no
work, but walks every turn and exhausts energy to 8.55 with hunger 0.196.  It
has no accidents, no improvised jobs and health 1.0.  This is the LA07 idle
travel issue, not the LA06 health regression: the next behaviour-quality
hypothesis is to suppress oscillating idle travel, or let rest/sleep outrank a
move that makes no progress toward a named place.

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
python3 -m pytest -q tests/test_lazy_default.py tests/test_lazy_work.py \
  tests/test_lazy_cheap.py tests/test_lazy_llm.py -p no:cacheprovider
# 52 passed, 1 skipped in 68.39s

python3 -m pytest -q tests/test_bigville_game_api.py tests/test_simple_life.py \
  tests/test_fix_simple_village.py tests/test_bigville_scenarios.py \
  tests/test_scenario_runner.py -p no:cacheprovider
# 63 passed in 248.06s

python3 -m pytest -q tests/test_phase055_concurrency.py \
  tests/test_phase059_autopilot.py -p no:cacheprovider
# 39 passed, 1 failed in 74.01s

python3 -m pytest -q tests/test_lazy_*.py -p no:cacheprovider
# 114 passed, 1 skipped in 126.00s

python3 -m pytest -q tests/test_simple_animals.py tests/test_simple_body_food.py \
  tests/test_simple_crop_water.py tests/test_simple_norms_enforcement.py \
  tests/test_simple_room_policy.py tests/test_simple_storage_decay_construction.py \
  tests/test_simple_tools_materials_job.py tests/test_simple_transfer_intent.py \
  tests/test_simple_work_food_exchange.py tests/test_role_affordance_cognition.py \
  tests/test_phase021_refusals.py tests/test_phase042_daynight.py \
  -p no:cacheprovider
# 91 passed in 34.03s (after pinning those menu-era simple-backend tests to menu)

python3 -m pytest -q tests/test_tick_graph.py tests/test_tick_graph_executor.py \
  tests/test_tick_occupancy.py tests/test_tick_sharding.py \
  tests/test_fix024_starvation.py tests/test_phase053_fog.py \
  tests/test_phase058_persona.py -p no:cacheprovider
# tick_sharding 15 passed, the 50-turn persona recording 1 passed after the
# menu pins; the remaining modules passed.

python3 domains/bigville_entities.py
# exit 0: 0 errors, 0 warnings, 95 info entries
```

The one failure is the environment-sensitive concurrency timing assertion
`test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical`
(sequential=14.29s, concurrent=11.71s, ratio 0.82; required < 0.75).  Its
semantic assertions (identical digests and identical provider calls) passed, and
the same test passed alone immediately afterwards (1 passed in 26.27s) and in
the LA06 run before this phase.  `build_llm_town` resolves to menu under LA08
(auto + LLM backend), so the test does not exercise the lazy path.

The **full suite did not complete** and no full-suite pass is claimed.  It
remains the final gate for an idle host.

## Limitations carried forward

- Lazy mode had zero refusals on `town100` in all evaluation runs; refusal
  variety and trade parity were not exercised by these scenarios.
- The small room published no menu affordances, so its comparison isolates the
  lazy travel behaviour rather than judging action quality.
- Only two `town100` seeds and one small seed were run; the evidence is
  reproducible but not a wide sweep.
- Mode selection is per game, not per actor, except for Ocelot's explicit
  per-actor menu exception.
- **A supervisor 8-turn replay found a partitioned-executor divergence in menu
  mode too.**  It was diagnosed and fixed in
  `docs/phases/tick-graph/PARTITIONED_FIX_REPORT.md`: turn-order within shards,
  conflict-aware component merging, move step-cell declarations, co-location
  witness resources, and allocation-id normalisation. Serial and partitioned
  semantic states now match over the tested seed/turn matrix; partitioned remains
  opt-in and the default executor is serial.
- **Lazy + partitioned executor** was the same tick-graph scheduling issue; it is
  fixed by the follow-up above and covered by the lazy 24-turn serial-vs-partitioned
  checks. The partitioned executor remains opt-in; serial is the default.
- Wall-clock numbers are same-host relative measurements under contention.
