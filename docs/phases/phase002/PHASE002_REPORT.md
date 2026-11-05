# Phase 002: Recipe inputs from the worker's own stock

## Summary

A recipe's bulk inputs (and each member of a typed slot such as `fuel`) are now drawn in this
order: the worker's own inventory, then containers standing on the worker's current cell that the
worker may access, then the town store. Each job records on its Need node where every unit came
from (`drawn_from`). `_recipe_inputs_available` runs the same planner the job runs, so the published
affordance agrees with the completion. The self-test is clean (0 errors, 0 warnings), and the full
suite passes except two Ocelot tests in another session's files, which fail on a missing adapter
module that was already missing at baseline.

## Changes

- `worlds/bigville_world.py` (only the phase's code paths):
  - `type_available(type_name, actor=None)`: with no actor it still counts the store only (existing
    callers unchanged). With an actor it counts own stock, accessible co-located containers, and the
    store.
  - `_recipe_inputs_available(recipe, actor)`: now calls `_plan_inputs`, so it uses the same plan as
    the job, then checks tools as before.
  - New helpers: `_input_need`, `_bulk_sources`, `_source_qty`, `_source_label`, `_bulk_available`,
    `_draw_units`, `_claim`, `_plan_input`, `_plan_inputs`, `_take_draws`, `_record_drawn_from`.
  - `_resolve_jobs`: input handling rewritten to plan all inputs, then take and record. The tool
    check and the consumption order are unchanged.
  - `_open_job`: each Need node starts with `drawn_from = ""`.
- `tests/test_phase002_own_stock_inputs.py` (new): 9 tests.
- `docs/phases/phase002/PHASE002_REPORT.md` (this file).

No existing test file was edited. No data pack or entity table changed, so the self-test cross
references are unaffected.

### Draw order

For each bulk need, `_bulk_sources(actor, kind)` lists sources in this order:

1. `("own", carrier)`: the actor's inventory carrier (`_actor_inventories`).
2. `("box", name)`: each container whose mapped cell equals the actor's cell and whose
   `_container_accessible(actor, name)` is true. Inventory carriers are excluded. Containers with no
   mapped cell never qualify, and neither does an actor with no position.
3. `("store", None)`: the town store (`qty(kind)`).

A typed slot first asks `E.type_plan` which member items to use, cheapest per unit first, using the
combined availability across sources. Each chosen member is then drawn in the same source order.
Burnt byproducts (ash, soot) still go to the store, as before.

Item inputs (discrete components such as `pick_head`, `wheel`) keep the existing item search
(`_job_input`). Their presence is now checked by the affordance too.

### Reservation

The timed-job guarantee is unchanged in mechanism. Inputs are checked and consumed at completion,
not at start. Each job plans and then takes its units inside one sequential pass in `_resolve_jobs`.
A unit taken by an earlier job is gone before a later job plans, so two jobs cannot both count the
same units. Within one job, `claimed` tracks units already promised to earlier needs of that job,
keyed by (source, kind). The plan is applied only when every need of the job fits. A job that finds
its inputs short stays busy, as before, and completes once stock arrives.

`start` and `do` still do not check inputs when they open a job. The village policy checks the
affordance first (`_village_start`). This was already the case.

### drawn_from

The Need node's `drawn_from` is a string like `flour:own=40.0;water:store=20.0`, using the source
labels `own`, `box:<container name>`, and `store`. A typed slot's Need also keeps `filled_with`
(member:units), as before.

## Validation

- `python3 domains/bigville_entities.py`: exit 0, `ERRORS (0)`, `WARNINGS (0)`.
- `python3 -m domains.check --pack test_hamlet`: exit 0.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase002_own_stock_inputs.py`: 9 passed.
- Full suite in the shared checkout (`timeout 1500 python3 -m pytest -q -p no:cacheprovider`):
  391 passed, 2 skipped, 2 failed. The failures are
  `tests/test_bigville_ocelot_communication.py::test_real_ocelot_advertises_only_wired_communication_capabilities`
  and `tests/test_mixed_ocelot_village.py::test_mixed_real_ocelot_village_runs_multiple_turns_and_rejects_invalid_action`.
  Both raise verbatim:
  `OcelotUnavailableError: Ocelot backend requires Ocelot's worlds.bigville_ocelot_adapter ... Adapter import failed (ModuleNotFoundError: No module named 'worlds.bigville_ocelot_adapter')`.
  Those files belong to the other session. The same two tests fail on the pre-change working tree
  (380 passed, 1 skipped, 2 failed).
- Full suite with the two Ocelot files ignored (`--ignore=tests/test_bigville_ocelot_communication.py --ignore=tests/test_mixed_ocelot_village.py`):
  393 passed, 2 skipped. The skips are `tests/test_bigville_game_api.py:180` and
  `tests/test_bigville_game_persistence.py:56`, both for the missing Ocelot adapter.
- Clean comparison: `git archive HEAD` into a temp directory, then the full suite:
  364 passed (the baseline). The same directory with this phase's `worlds/bigville_world.py` and
  the new test file: 373 passed, which is 364 plus the 9 new tests. The copied world file also
  includes the other session's uncommitted `resident_plan_from_context` method. That method is
  unused by this phase, and the run did not depend on it. The temp directory was removed.

The 100-resident town was not run.

### Test counts changed

None. No existing assertion or number changed.

## Limits

- The new tests cover one baker, one cook, two co-located bakers, and one shared bin. They do not
  exercise a village run with many residents.
- The village policy (`_village_work_tick`) was not run. Its effect on bakers who now carry their
  own flour is not measured.
- Containers with no mapped cell never supply a worker. Setup containers without a cell are
  therefore never drawn on by recipes.
- The `drawn_from` string records draws only for bulk and typed needs. Item needs record nothing.

## Deviations

- Affordance for item inputs (`pick_head`, `wheel`, and similar). The brief said the affordance
  should match the run. The old check counted store stock of the item kind, but the run can only
  use a discrete item found by `_job_input`. The new affordance uses the same item search, so a
  recipe with a store-only item stock is no longer published as affordable. Nothing in the test
  suite depended on the old behaviour.

## Open questions and follow-ups

1. Pre-existing item-input defects, not changed here:
   - An item need with quantity 2 consumes one item. Verified: a resident holding two wheels runs
     `make_cart` once and keeps one wheel.
   - `_job_input` searches the town's `has_tool_item` edges and held items. It does not search
     building shelves. A wheel placed on the woodshop shelf is not an input.
2. The village policy in `_village_work_tick` still gates `make_gruel` and `grind_flour` on store
   quantities before calling `_village_start`. Those gates are stricter than the affordance, so a
   resident with their own grain is not started. Relaxing them would change the 100-resident town and
   is left for a later phase.
3. `fertilise` still draws its nitrogen from the store only (`type_available` without an actor).
   Only recipe inputs follow the new order.
4. Should a timed job re-plan its inputs at start, or reserve them then, so a backend can see that
   stock is committed? Today it plans only at completion, which the brief's acceptance does not
   require.

## Git status

At start (before any edit):

```
 M bigville/backends/ocelot.py
 M bigville/game.py
 M bigville/runtime.py
 M docs/AGENT_BACKENDS_PLAN.md
 M tests/test_bigville_game_api.py
 M tests/test_bigville_scenarios.py
 M worlds/bigville_world.py
?? bigville/mixed_ocelot_scenario.py
?? bigville/world_persistence.py
?? docs/MIXED_OCELOT_VILLAGE_RUN_20261105.md
?? docs/ocelot-integration-baseline.md
?? docs/runs/
?? tests/test_bigville_graph_persistence.py
?? tests/test_bigville_ocelot_communication.py
?? tests/test_bigville_ocelot_fresh_process.py
?? tests/test_bigville_world_persistence.py
?? tests/test_mixed_ocelot_village.py
?? tools/run_mixed_ocelot_village.py
```

At end, the other session had also added or changed `bigville/game_persistence.py`,
`bigville/seeds/bigville_actor_decision.json`, `tests/test_bigville_game_persistence.py`, and
`tests/test_mixed_ocelot_checkpoint_parity.py`. Those changes are the other session's. This phase
edited only `worlds/bigville_world.py` and added `tests/test_phase002_own_stock_inputs.py` and this
report. Nothing was committed.
