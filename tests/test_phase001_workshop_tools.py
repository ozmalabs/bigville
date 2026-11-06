"""Phase 001: trade recipes use physical tools kept at the worker's workplace building.

A trade recipe needs an unbroken tool of each required kind at the worker's workplace
(inside its footprint once the clock runs) or held by the worker. Open (household) recipes
still need the worker's own held tool.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from worlds.bigville_world import BigvilleWorld as World      # noqa: E402


def _footprint(w, key):
    x, y, fw, fh = w._building_sites[key]
    return x, y, fw, fh


def _inside(w, key):
    """A walkable cell inside the building's footprint."""
    x, y, fw, fh = _footprint(w, key)
    return next((x + dx, y + dy) for dy in range(fh) for dx in range(fw) if (x + dx, y + dy) in w._map_cells)


def _outside(w, key):
    """A walkable cell outside the building's footprint."""
    x, y, fw, fh = _footprint(w, key)
    return next(c for c in sorted(w._map_cells)
                if not (x <= c[0] < x + fw and y <= c[1] < y + fh))


def _smith_at_forge():
    w = World()
    w.add_actor("Smith", role="smith", skill=0.9)
    w.set_stock("iron", 20)
    w.set_stock("charcoal", 20)
    w._move_actor_to("Smith", _inside(w, "forge"))
    return w


def test_smith_at_forge_forges_with_the_forges_hammer_and_it_wears():
    w = _smith_at_forge()
    hammer = w.workshop_tool("hammer", building="forge")
    assert hammer is not None and w.tool_condition(hammer) == 1.0
    assert w.do("Smith", "forge_nails")
    assert w.qty("nails") == 5.0 and w.qty("iron") == 19.0
    first_wear = w.tool_condition(hammer)
    assert first_wear < 1.0, "the forge's hammer wears with use"
    assert w.do("Smith", "forge_nails")
    assert w.tool_condition(hammer) < first_wear, "each use wears the same hammer further"



def test_a_broken_forge_hammer_forging_goes_on_with_bare_hands_and_wastes_the_batch():
    # Phase 048: a missing or broken tool is not a refusal. The smith forges with bare hands (fitness 0.05), which
    # uses the iron and yields nothing; a hammer in the smith's hands makes the nails.
    w = _smith_at_forge()
    hammer = w.workshop_tool("hammer", building="forge")
    w.eng.set_attr(hammer, "condition", 0.02)
    assert w.do("Smith", "forge_nails"), "the last use wears the hammer to zero"
    assert w.tool_broken(hammer) and w.instrument_condition("hammer") == 0.0

    iron, nails = w.qty("iron"), w.qty("nails")
    assert not w._recipe_inputs_available("forge_nails", "Smith"), "the offer still wants a usable tool"
    assert w.do("Smith", "forge_nails"), "with no hammer the smith works bare-handed"
    assert w.qty("iron") == iron - 1.0, "the bare-hand batch uses its inputs"
    assert w.qty("nails") == nails, "a bare-hand batch is wasted: it yields nothing"
    assert not w.busy("Smith")

    # Two bare-hand batches cost the smith three times the stamina each, so rest before the batch with the hammer.
    w.eng.set_attr(w._bodies["Smith"], "stamina_reserve", 1.0)
    w.eng.set_attr(w._actors["Smith"], "collapsed", 0.0)
    w.eng.set_attr(w._actors["Smith"], "asleep", 0.0)
    spare = w.give_tool("Smith", "hammer")
    assert w.do("Smith", "forge_nails"), "a hammer in the smith's hands is usable"
    assert w.tool_condition(spare) < 1.0 and w.qty("nails") == nails + 5.0



def test_a_new_hammer_placed_at_the_forge_restores_forging():
    w = _smith_at_forge()
    w.eng.set_attr(w.workshop_tool("hammer", building="forge"), "condition", 0.0)
    w.eng.set_attr(w.workshop_tool("hammer", building="forge"), "broken", 1.0)
    nails = w.qty("nails")
    assert w.do("Smith", "forge_nails"), "without a hammer the smith works bare-handed (Phase 048)"
    assert w.qty("nails") == nails, "and the batch is wasted"

    new = w.give_tool("Smith", "hammer")
    assert w.stow_tool("Smith", new), "the smith places the new hammer on the forge's shelf"
    assert w.workshop_tool("hammer", building="forge") == new
    assert w.do("Smith", "forge_nails") and w.tool_condition(new) < 1.0 and w.qty("nails") == nails + 5.0



def test_a_worker_away_from_the_forge_cannot_use_its_tools_once_the_clock_runs():
    # Phase 048: outside the forge the forge's hammer is out of reach, so the smith works bare-handed. The
    # hammer is not worn, and the batch is wasted.
    w = _smith_at_forge()
    w.tick(1)
    assert w.do("Smith", "forge_nails"), "inside the forge, the smith forges"
    hammer = w.workshop_tool("hammer", building="forge")
    worn = w.tool_condition(hammer)
    w.actor_tick()                                   # a new turn frees the major-action slot
    w._move_actor_to("Smith", _outside(w, "forge"))
    iron, nails = w.qty("iron"), w.qty("nails")
    assert w.do("Smith", "forge_nails"), "outside the forge the smith works with bare hands (Phase 048)"
    assert w.tool_condition(hammer) == worn, "the forge's hammer is out of reach, so it is not used"
    assert w.qty("iron") == iron - 1.0 and w.qty("nails") == nails



def test_open_recipes_use_the_workers_own_held_tool_and_not_a_shelf_tool():
    w = World()
    w.add_actor("Ash", role="forester", skill=0.8)
    w.set_stock("wood", 5)
    w.set_stock("lumber", 2)
    # A tool on a building shelf does not serve a household recipe (Phase 048: the worker goes bare-handed).
    shelf_axe = w._new_tool_item("axe")
    w.eng.add_edge_unchecked(w._places["forge"], "has_tool_item", shelf_axe)
    assert w.do("Ash", "split_firewood")
    assert w.tool_condition(shelf_axe) == 1.0, "the shelf's axe is not used"
    own = w.give_tool("Ash", "axe")
    assert w.do("Ash", "split_firewood") and w.tool_condition(own) < 1.0


def test_founding_buildings_hold_their_trades_kits_and_recipe_only_tools():
    w = World()
    assert [w.tool_kind(t) for t in w.eng.neighbours(w._places["forge"], "has_tool_item")] == ["hammer"]
    # `knife` is named by the woodworker's own carving recipes, so it is part of the shop's kit too.
    assert sorted(w.tool_kind(t) for t in w.eng.neighbours(w._places["woodshop"], "has_tool_item")) == ["knife", "saw"]
    # `press` is named by the dairy's own recipes but is in no TRADES kit.
    assert sorted(w.tool_kind(t) for t in w.eng.neighbours(w._places["dairy"], "has_tool_item")) == ["churn", "press"]
    assert [w.tool_kind(t) for t in w.eng.neighbours(w._places["townhall"], "has_tool_item")] == ["quill"]


def test_a_trade_with_no_building_must_carry_its_tool():
    w = World()
    w.add_actor("Quarry", role="quarrier", skill=0.8)
    assert not w._recipe_tools_usable("Quarry", "dig_ore")
    w.give_tool("Quarry", "pick")
    assert w._recipe_tools_usable("Quarry", "dig_ore")


def test_a_recipe_added_at_runtime_gets_its_tool_at_the_trades_building():
    w = World()
    w.add_recipe({"name": "saw_planks_test", "requires": "smith", "in": [["iron", 1]],
                  "out": ["nails", 1], "tools": ["saw"], "time_minutes": 0})
    assert sorted(w.tool_kind(t) for t in w.eng.neighbours(w._places["forge"], "has_tool_item")) == ["hammer", "saw"]
