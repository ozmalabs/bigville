# Simple village: remaining boundary violations

Audit of the current working tree on 2026-11-05 against
[`SIMPLE_VILLAGE_TEST_PLAN.md`](SIMPLE_VILLAGE_TEST_PLAN.md) and
[`SIMPLE_BOUNDARY_AUDIT.md`](SIMPLE_BOUNDARY_AUDIT.md). Source inspection plus
existing focused-test evidence. Line references below are current-tree
references.

## Prioritized findings

### 1. Animal grazing is not yet represented as a physical feeding source — medium

Animal metabolism now advances hunger and starvation only. Stock-feed consumption
requires the animal backend to select `eat`; the world offers and executes that
action only when a store pile has enough feed and is within one map step. Tests
cover nearby feed, inaccessible feed, absent feed, and quantity conservation.
Grazing is not offered as an action until the world has a situated grass resource
that grazing can physically consume. This avoids treating a behavior label as
food or letting a distant town stock pile feed an animal.

Focused regression:

```sh
PYTHONPATH=. pytest -q tests/test_simple_animals.py
```

### 2. Ordinary world ticks no longer choose resident policies — addressed

`BigvilleWorld.tick()` now advances physical time and does not invoke the
world-owned Ocelot/compatibility resident-plan loop. World constructors default
to `autonomous_actors=False`; the legacy argument remains accepted for
compatibility but does not make world time a cognition scheduler. Unattended
resident decisions run through `BigvilleGame(..., autonomous=True)` and its
configured backend(s), including the simple backend. `run_village()` remains an
explicit founding-policy evaluation helper, separate from ordinary world ticks.

### 3. Reading a civic document directly installs understanding — addressed

`read_document` now records only physical exposure. `read_newspaper` records
the articles read and returns their text. Backend-produced memory updates store
interpretations in each resident's private `CharacterDefinition`; the world has
no comprehension API and reading creates no semantic knowledge. Regression
coverage in `tests/test_bigville_game_api.py` and
`tests/test_bigville_world_migrated.py` checks that distinction and privacy.

### 4. Weekly report and newspaper are minted by the world without a reporter action — addressed

`run_village` advances time and records read-only snapshots; it no longer
selects a reporter, surveys village-wide totals, mints a `weekly_village_report`,
or prints copies on a calendar boundary. Writing requires an event explicitly
observed by the reporter, and publication remains an explicit caller action.
Regression coverage in `tests/test_bigville_world_migrated.py` crosses a weekly
boundary and verifies that time alone creates no report, edition, or copies; a
separate case verifies that an unobserved event cannot be written while an
explicitly observed event can be written and published.

### 5. Shop sale and labor settlement — migrated

`sell_to_shop`, `sell_labor`, and `pay_wage` now return false without side
effects. The simple backend no longer receives a fixed-wage labor affordance.
Separate transfers remain available when selected by cognition; these
compatibility methods do not infer acceptance, choose terms, create
transactions, or discharge wage-due state. Regression coverage is in
`tests/test_bigville_topic_style_migrated.py`.

## Reconciliation with the older audit

The purchase section in `SIMPLE_BOUNDARY_AUDIT.md` is stale in this checkout:
there is no `_person_purchase` definition, `buy()` now always returns false
(`worlds/bigville_world.py:3247-3255`), and the normal `_actor_options` path
publishes physical transfers rather than sale willingness/prices
(`5371-5418`). The purchase utterance remains a proposal only. Do not prioritize
removing the retired purchase resolver as live behavior. The mediated shop
labor path above, and the direct compatibility `sell_to_shop` helper
(`3308-3329`), are the remaining economic settlement paths worth migrating.

Completed bulk job output remains in town stock at the production location.
The town100-specific automatic maker allocation has been removed; a maker's
inventory changes only through an explicit physical transfer. Regression
coverage in `tests/test_bigville_world_migrated.py` checks that canonical bread
production consumes its inputs, adds output to town stock, and leaves the
maker's inventory unchanged.

No general world-side law enactment or authoritative case outcome was found in
the reviewed current paths: council voting/meeting and case/dispute resolution
are records/statements per the updated audit. Document reading and periodic
newspaper generation (findings 3 and 4) now preserve that recording boundary.
