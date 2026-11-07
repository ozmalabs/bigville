# LA08 — Default rollout: `"auto"` affordance mode

Status: complete, uncommitted.  Phase LA08 of the lazy-affordances plan.
Base commit: `516ecaf` (`Lazy affordances: LA07 results and LA08 default-rollout
plan`, branch `lazy-affordances`).
No commit or stage was performed by this phase.

## What changed

- **`bigville/game.py`**
  - `_AFFORDANCE_MODES` is now `{"menu", "lazy", "auto"}`.
  - `BigvilleGame` stores `affordance_mode_requested` (the caller's value) and
    reports the resolved `affordance_mode` (`"menu"` or `"lazy"`).  The direct
    constructor still defaults to `"menu"`; `"auto"` is accepted explicitly.
  - New `resolve_affordance_mode()` resolves the request against the current
    session.  Explicit `"menu"`/`"lazy"` always win.  `"auto"` selects lazy only
    when all of these hold:
    1. the session is autonomous (`self.player is None`);
    2. every registered resident backend is built-in deterministic simplicity
       (`kind` in `{"cheap", "simple"}`, or an instance of `CheapBackend`);
    3. no LLM, Ocelot or human backend is registered.
    Anything else resolves to menu.  The method is deterministic and
    idempotent.
  - The constructor resolves at the end, after the player and every backend are
    known.  `set_backend()` re-resolves an `"auto"` session, so injecting an
    LLM, Ocelot or human backend after construction cannot leave a stale lazy
    resolution.
  - Ocelot's per-actor menu exception in `_context` is unchanged.
- **`bigville/api.py`** — `create_game(..., affordance_mode="auto")` is the new
  default.  It passes the request through, assigns all backends as before, then
  calls `game.resolve_affordance_mode()`.  Explicit `"menu"`/`"lazy"` still win.
- **`tests/test_lazy_default.py`** (new, 16 tests) — the resolution matrix,
  property exposure, play-path spies, and direct-constructor behaviour.
- **Menu-specific tests** — games that assert the menu's exact trace, option
  list, down-state proposals or measurement seam now pass
  `affordance_mode="menu"` explicitly.  No behavioural assertion or expected
  value was weakened or changed.
- This report, `FINAL_REPORT.md`, `README.md`, and the LA08 status row in
  `docs/design/LAZY_AFFORDANCES.md`.

## Resolution rule

| Request | Session | Resolved |
|---|---|---|
| `"menu"` | anything | `menu` |
| `"lazy"` | anything (Ocelot actors still get the per-actor menu context) | `lazy` |
| `"auto"` | autonomous, only cheap/simple backends, no player/LLM/Ocelot/human | `lazy` |
| `"auto"` | any player, LLM, Ocelot or other backend | `menu` |
| `"auto"` | direct `BigvilleGame` after later `set_backend()` changes | recomputed |

`game.affordance_mode_requested` always reports the request
(`"auto"`/`"menu"`/`"lazy"`); `game.affordance_mode` reports the resolved mode.

## Tests

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
# The failure is the environment-sensitive timing assertion
# test_a_slow_provider_is_faster_when_decided_concurrently_and_the_results_are_identical
# (sequential=14.29s, concurrent=11.71s, ratio 0.82; required < 0.75).
# Its semantic assertions (identical digests and identical provider calls)
# passed.  Run alone immediately afterwards it passed (1 passed in 26.27s).
# build_llm_town resolves to "menu" here (auto + LLM backend), so the test is
# not on the lazy path.

python3 -m pytest -q tests/test_lazy_*.py -p no:cacheprovider
# 114 passed, 1 skipped in 126.00s (after pinning the two menu digest tests
# and the skip_affordances seam to explicit menu mode; see below)

python3 domains/bigville_entities.py
# exit 0: 0 errors, 0 warnings, 95 info entries
```

### The new default is genuinely lazy

The spy test runs two turns of an autonomous simple `town100` game with
`mock.patch.object` on `BigvilleWorld.actor_affordances` and
`BigvilleWorld._actor_options`, and asserts the call list is empty.  A second
test runs an explicit menu game and asserts the menu is called.  The resolution
matrix covers lazy for autonomous `simple` and `cheap`, menu for LLM, player and
Ocelot (the Ocelot scenario skips cleanly when Ocelot is unavailable, while a
parametrized injection test asserts the same rule with a foreign backend).

### Test adaptations

Only games whose assertions are about the menu were pinned to
`affordance_mode="menu"`:

- `tests/test_lazy_cheap.py::test_menu_mode_trace_digest_is_unchanged`
- `tests/test_fix_simple_village.py` `_game()` (down-state proposals and the
  60-turn no-body-refusal assertion are menu-behaviour tests)
- `tests/test_lazy_affordances.py` `_town()` (the LA01 `skip_affordances`
  measurement seam is menu-only) and the old default test, rewritten to the new
  auto/lazy default
- `tests/test_lazy_evaluation.py` default/auto tests, rewritten to the new
  default
- `tests/test_lazy_observation.py` and `tests/test_lazy_target_resolution.py`
  menu trace-digest tests
- the menu-era simple-backend acceptance tests, which inspect
  `context.affordances` or assert exact action sequences:
  `test_simple_body_food.py`, `test_simple_crop_water.py`,
  `test_simple_norms_enforcement.py`, `test_simple_room_policy.py`,
  `test_simple_storage_decay_construction.py`,
  `test_simple_transfer_intent.py`, `test_simple_work_food_exchange.py`,
  `test_role_affordance_cognition.py`
- `tests/test_tick_sharding.py` (its strict serial-versus-partitioned trace is
  a menu-era equivalence oracle; see the limitation below)
- `docs/phases/phase058/measure_behaviour.py` (the historical 50-turn simple
  backend recording)

`tests/test_lazy_llm.py` and `build_llm_town` needed no edit: `set_backend()`
re-resolves `"auto"` when the LLM backend is added, so those sessions are menu.

Additional affected suites run after those adaptations:

```bash
python3 -m pytest -q tests/test_simple_animals.py tests/test_simple_body_food.py \
  tests/test_simple_crop_water.py tests/test_simple_norms_enforcement.py \
  tests/test_simple_room_policy.py tests/test_simple_storage_decay_construction.py \
  tests/test_simple_tools_materials_job.py tests/test_simple_transfer_intent.py \
  tests/test_simple_work_food_exchange.py tests/test_role_affordance_cognition.py \
  tests/test_phase021_refusals.py tests/test_phase042_daynight.py \
  -p no:cacheprovider
# 91 passed in 34.03s

python3 -m pytest -q tests/test_phase018_llm_instructions.py \
  tests/test_tick_snapshot.py -p no:cacheprovider
# 25 passed in 54.58s

python3 -m pytest -q tests/test_tick_graph.py tests/test_tick_graph_executor.py \
  tests/test_tick_occupancy.py tests/test_tick_sharding.py \
  tests/test_fix024_starvation.py tests/test_phase053_fog.py \
  tests/test_phase058_persona.py -p no:cacheprovider
# after the menu pins: tick_sharding 15 passed; the 50-turn persona recording
# 1 passed.  The rest of that batch passed except the two menu-era tests above.

python3 -m pytest -q tests/test_phase054_actionable.py \
  tests/test_phase012_cognitive_learning.py -p no:cacheprovider
# 24 passed in 33.26s
```

## Evaluation

Commands:

```bash
python3 tools/evaluate_affordance_modes.py --scenario town100 --seed 305000 \
  --turns 8 --modes menu,lazy --json-only
python3 tools/evaluate_affordance_modes.py --scenario town100 --seed 305001 \
  --turns 8 --modes menu,lazy --json-only
python3 tools/evaluate_affordance_modes.py --scenario small --seed 305000 \
  --turns 12 --modes menu,lazy --json-only
```

### town100, seed 305000, 8 turns

| mode | applied | refused | alive | hunger | energy | health | health min | work | improvised | accidents | context s | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| menu | 800 | 0 | 100 | 0.115953 | 42.0239 | 1.0 | 1.0 | 15 | 0 | 0 | 3.051325 | 24.700264 |
| lazy | 800 | 0 | 100 | 0.106612 | 46.6911 | 1.0 | 1.0 | 100 | 1 | 0 | 0.940908 | 19.611421 |

Applied: menu `{move: 785, work: 15}`; lazy `{move: 700, work: 100}`.

### town100, seed 305001, 8 turns

| mode | applied | refused | alive | hunger | energy | health | health min | work | improvised | accidents | context s | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| menu | 800 | 0 | 100 | 0.116095 | 41.9499 | 1.0 | 1.0 | 11 | 0 | 0 | 2.678966 | 21.087594 |
| lazy | 800 | 0 | 100 | 0.107278 | 46.3610 | 1.0 | 1.0 | 100 | 0 | 0 | 0.880073 | 20.205989 |

Applied: menu `{move: 789, work: 11}`; lazy `{move: 700, work: 100}`.

### small room, seed 305000, 12 turns

| mode | applied | refused | alive | hunger | energy | health | health min | work | improvised | accidents | context s | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| menu | 0 | 0 | 3 | 0.0 | 100.0 | 1.0 | 1.0 | 0 | 0 | 0 | 0.323274 | 1.038273 |
| lazy | 35 | 1 | 3 | 0.196233 | 8.546667 | 1.0 | 1.0 | 0 | 0 | 0 | 0.036355 | 0.490999 |

Applied: menu none; lazy `{move: 32, rest: 2, sleep: 1}`.  The single refusal is
`exhausted`.  Both modes report the scenario's pre-existing sanity error
“residents have unreachable or missing workplaces”.

### Default-mode run

An 8-turn `town100` run with `create_game(..., default_backend="simple",
autonomous=True)` and no mode argument reported:

```
requested_mode: "auto"
resolved_mode:  "lazy"
applied: 800, refused: 0, alive: 100
applied actions: {move: 700, work: 100}
hunger 0.106612, energy 46.6911, health mean/min 1.0/1.0
tool tally: {improvised_jobs: 1, accidents: 0, broken_tools: 0}
context 0 errors / 1 warning, wall 20.83s
```

These are the same numbers as the explicit lazy run, so the default genuinely
takes the lazy path.

## Decision

**`create_game` defaults to `"auto"`.**  Autonomous simple/cheap sessions resolve
to lazy; player, LLM and Ocelot sessions resolve to menu.  A direct
`BigvilleGame` keeps menu as its default.  Explicit `"menu"`/`"lazy"` remain
available and always win.

LA07 removed the health blocker: lazy and menu both stay at health 1.0, and
lazy is no worse on survival, hunger or energy on `town100`.  Context
construction remains roughly 2.9-3.0x cheaper on these runs (0.88-0.94s vs
2.68-3.05s over 8 turns).

## Known limitation: lazy mode with the partitioned executor

Default `town100` is serial, so this does not affect the default play path.
While running the affected executor suites this phase found a real
lazy-specific divergence:

- With `affordance_mode="menu"`, serial and partitioned `town100` runs produce
  identical four-turn semantic traces (verified).
- With `affordance_mode="lazy"` at the same seed, the serial run is
  deterministic but the partitioned run first diverges at turn 2 in
  `world_sha256`.  Responses, results, order, errors and continuations are
  identical; the difference is three residents' tiny energy/hunger/exertion and
  terrain-speed values (`~1e-3`), i.e. an enactment order effect for actors
  moving through the same cells.
- `tests/test_tick_sharding.py` is pinned to `affordance_mode="menu"` because
  its strict serial-versus-partitioned digest is a menu-era oracle.  That pin
  preserves the historical pass but **does not fix the lazy+partitioned
  divergence**.

This is reported rather than hidden.  It is a tick-graph/partitioned-executor
follow-up, outside LA08's mode-rollout scope; the serial default and every
required LA08 gate are unaffected.  The next hypothesis is to make lazy direct
params produce the same resource/claim decomposition as menu target keys so
partition scheduling cannot reorder same-cell movement effects.

## Caveat: small-room energy

The goal-free three-resident room still shows a behaviour-quality difference:
menu publishes no affordances and idles (energy 100, hunger 0), while lazy
proposes `move` every turn and exhausts energy to 8.55 with hunger 0.196.  There
are no accidents, no improvised jobs and health is 1.0.  This is the known idle
travel issue from LA07, not a validation or health regression.  It is recorded
here and in `FINAL_REPORT.md` as the next behaviour-quality hypothesis:
suppress oscillating idle travel, or let rest/sleep outrank a move that makes no
progress toward a named place.

## Limitations

- Only two `town100` seeds and one small seed were evaluated, as in LA06/LA07.
- No trade and no refusals occurred on `town100`, so refusal variety and trade
  parity are not exercised by the evaluation.
- The small comparison is degenerate: menu does nothing there.
- The concurrency timing assertion remains host-load sensitive and is not a
  semantic failure.
- Wall-clock numbers are same-host relative measurements.
