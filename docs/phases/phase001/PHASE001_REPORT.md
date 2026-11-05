# Phase 001 -- Workshop tool kits

## Summary

Trade recipes now use physical `ToolItem`s kept at the worker's workplace building,
instead of the town-wide phantom `Tool` nodes. A trade recipe is usable only when an
unbroken tool of each required kind is at the worker's workplace (and the worker is
inside it once the clock runs) or held by the worker. Using a tool wears that item.

The implementation is complete and the self-test is clean. The full suite has
**5 failures**, all in two existing test files outside this phase's write scope. Those
tests read `world._tools` (removed by this phase) or depend on the smith standing at
their default map position. A scratch copy with those five setup lines changed passes
all 323 tests (315 existing plus 8 new). The repo copies were not changed. Decision
needed from the supervisor; see Open questions.

## Changes

`worlds/bigville_world.py`

- Removed `self._tools`, `self._tool_kinds`, the phantom `Tool` node creation in
  `__init__` and `add_recipe`, and `_instrument_usable`.
- Founding kit: after the buildings are installed, `_equip_workshop` places one
  unbroken `ToolItem` per kind on each building's `has_tool_item` edge from the
  `Place` node. Kinds come from `_workshop_kit(kind)`: the `TRADES[...]["tools"]` of
  every trade that works in the building (`_building_trades`: trades it `provides`,
  trades named in its `staff_role`, and trades whose `TRADES[...]["building"]` is it),
  plus the tools named by that trade's non-open recipes.
  Resulting kits: forge = hammer; woodshop = knife, saw; dairy = churn, press;
  townhall = quill; cooperage = adze; bakery = oven, barrel; kitchen = pot, barrel,
  and so on.
- Recipe-only tools get a home this way. For example `press` sits at the dairy because
  `make_cheese` names it. Tools named only by recipes of a trade with a building are
  covered the same way.
- Workplace: `_workplace(actor)` is the installed building of `TRADES[role]["building"]`,
  or none. `_at_workplace` returns it when the worker can use it now. Before the clock
  runs (`_turn == 0`) no location is checked. Once it runs, a worker who has a map
  position must stand inside that building's footprint (`_building_sites`).
- `_worker_tool(actor, kind)` returns an unbroken tool at the workplace first, then a
  held tool. Job completion wears the tool returned by this function.
- `_recipe_tools_usable(actor, recipe)` now uses `_worker_tool` for trade recipes and
  `_held_tool` for open recipes (unchanged rule).
- `_recipe_inputs_available(recipe, actor)` takes the actor and ends with
  `_recipe_tools_usable`. Its two callers (`_village_start` and the affordance loop in
  `actor_affordances`) pass the actor, so published affordances and `do`/`start` apply the
  same rule.
- `_resolve_jobs`: the start-time and completion-time tool checks use `_worker_tool`
  (trade) or `_held_tool` (open).
- New public methods: `workshop_tool(kind, building=None)` (an unbroken tool at a
  building, else the first found, else None), and `stow_tool(actor, item)` (puts a held
  tool on the workplace shelf; a major action once the clock runs). `_new_tool_item`
  is shared by `give_tool` and the kit, with `wear` taken from the item's `wear_rate`.
- `instrument_condition(kind)` reads `workshop_tool`; it returns 0.0 when no tool stands.

`tests/test_phase001_workshop_tools.py` (new, 8 tests): forging at the forge with the
forge's hammer; wear per use; refusal after break with nothing consumed; a new hammer
held or stowed at the forge restores forging; a worker outside the footprint is refused
once the clock runs; open recipes still need a held axe and ignore a shelf axe; founding
kits; a trade with no building needs a held tool; a runtime recipe gets its tool at the
trade's building.

`docs/phases/phase001/`: this report, `selftest.log`, `full_tests.log`.

No test numbers were changed.

## Validation

- `python3 domains/bigville_entities.py` -> exit 0. ERRORS (0), WARNINGS (0). Balance
  issues (0). JOBS: sustainable start True for N=100, 30 and 8. Log: `selftest.log`.
- `python3 -m pytest -q -p no:cacheprovider tests/test_phase001_workshop_tools.py` ->
  8 passed.
- `timeout 1500 python3 -m pytest -q -p no:cacheprovider` -> **5 failed, 318 passed**
  (54.9 s). Log: `full_tests.log`.
- Scratch copy (`tar` of the repo to `/tmp`, not the repo), with the five setup edits
  listed under Open questions applied: `python3 -m pytest -q -p no:cacheprovider` ->
  323 passed.
- Not run: the 100-resident town and village runs (not requested by the brief).

Failures in the repo run, verbatim:

- `tests/test_bigville_world_migrated.py::test_a_recipe_takes_its_time_and_is_hard_work`:
  `AssertionError: after the full 6 ticks the knife exists`, `assert (not True)`. The
  smith is at its default position outside the forge, and the clock runs.
- `tests/test_simple_tools_materials_job.py::test_timed_smithing_conserves_inputs_and_has_material_and_tool_controls`,
  `::test_job_trace_is_reproducible_for_fixed_seed`,
  `::test_missing_tool_rejects_start_without_consuming_inputs`,
  `::test_tool_lost_during_timed_job_blocks_completion_without_consuming_inputs`:
  `AttributeError: 'BigvilleWorld' object has no attribute '_tools'` (lines 23, 95, 109).

## Limits

- Buildings completed later through `BUILDING_PROJECTS`, and non-founding buildings
  (charcoal hearth, papermill, inkhouse), get no tool kit. Their trades need a held tool.
  Papermaking (`make_paper`, needs a press) therefore needs a carried press.
- Trades with no building (mason, quarrier, forester, farmer, chandler) now need a held
  tool. Their recipes change: `dress_stone` and `build_oven` (mason hammer), `dig_ore`
  (quarrier pick), and `make_candles` (chandler pot). The forester and farmer recipes
  that name tools are open recipes, which already used the worker's held tool. Their
  site-based tools have no shelf in this phase.
- Forged replacements (`forge_hammer` and the other tool recipes) still land as a town
  `ToolItem`. A resident must `pick_up` the item (existing rule) and then `stow_tool`
  it at the workplace.
- Tool choice between a shelf tool and a held tool is fixed: shelf first. Moving tools
  between buildings by resident choice is out of scope, as the brief states.
- The workplace footprint is the building's `_building_sites` rectangle. No
  pathing is involved; an actor inside the rectangle counts as at the building.

## Open questions

1. **Scope conflict (blocking).** Five existing tests fail on the phase's own changes.
   Their fix is setup only, and it sits in two files outside the write scope:
   - `tests/test_bigville_world_migrated.py::test_a_recipe_takes_its_time_and_is_hard_work`:
     after `w = World(); w.add_actor("Wayland", role="smith", ...)`, add
     `x, y, fw, fh = w._building_sites["forge"]; w._move_actor_to("Wayland", (x, y))`.
   - `tests/test_simple_tools_materials_job.py`: replace `world._tools["hammer"]` with
     `world.workshop_tool("hammer", building="forge")` (three places, lines 23, 95, 109). In the two
     `remove_edge_unchecked`/`add_edge_unchecked` tests, use
     `world._places["forge"]` and `"has_tool_item"` in place of `world._town` and
     `"has_tool"`. In `test_tool_lost_during_timed_job...`, move the smith into the
     forge footprint before `start`.
   Should the supervisor widen the scope to these two files, the scratch run shows these
   edits make the suite pass (323).
2. A worker with no map position is not location-gated, even after the clock runs.
   The brief read literally would refuse that worker. The existing test above needed
   that exemption as well as the setup change. Confirm this exemption.
3. Should a building completed later from `BUILDING_PROJECTS` receive its trade kit,
   or should residents stock it? The brief covers founding buildings only.
4. Should buildingless trades (mason, quarrier, etc.) get site-based tool storage, or
   stay as "carry your own"?
