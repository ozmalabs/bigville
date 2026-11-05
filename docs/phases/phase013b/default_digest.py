"""A digest of default-world behaviour, run on HEAD (an export) and on the working tree (Phase 013b).

Prints one JSON object. Run it with PYTHONHASHSEED=0 from the repository root (or from an export of
HEAD with the same layout). Two runs with equal output mean the default world, its town map, and
the 100-resident town did the same things. It covers: a bare world's boot state, a baker's recipes
and three periods, the 100-resident town's map, deposits, residents, and three periods.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.getcwd()
sys.path.insert(0, ROOT)

from worlds.bigville_world import BigvilleWorld          # noqa: E402
from worlds.bigville_town100_world import (              # noqa: E402
    BigvilleTown100World, build_town_100)


def _stock(w):
    return {k: round(float(w.qty(k)), 6) for k in sorted(w._stock)}


def _grid_hash(grid):
    return hashlib.sha256(json.dumps(grid).encode()).hexdigest()[:16]


def main():
    out = {}
    w = BigvilleWorld()
    out["boot_items"] = len(w._item_specs)
    out["boot_recipes"] = len(w._recipe_specs)
    out["boot_affordances"] = sorted(w._affordances)
    out["boot_buildings"] = sorted(w._building_sites)
    w.add_actor("Ann", role="baker", skill=0.9)
    w.set_stock("grain", 6)
    w.set_stock("water", 6)
    out["mill"] = w.do("Ann", "mill_flour")
    out["bake"] = w.do("Ann", "bake_bread")
    w.pass_period(3)
    out["after_three_periods_stock"] = _stock(w)

    # The 100-resident town (its boot and three periods).
    t = BigvilleWorld.from_town100()
    out["town_residents"] = len(t._actors)
    out["town_actors_sample"] = sorted(t._actors)[:5]
    t.pass_period(3)
    out["town_stock_after_three_periods"] = _stock(t)

    # The 100-resident map builder and its town class.
    grid, aff, layout = build_town_100(305000)
    out["map_grid_hash"] = _grid_hash(grid)
    out["map_deposits"] = layout["deposits"]
    out["map_affordances"] = [(a["name"], a["x"], a["y"]) for a in aff]
    b = BigvilleTown100World(seed=305000)
    out["t100_residents"] = len(b.residents)
    out["t100_deposits"] = sorted(b.resident_records()[0].keys())
    print(json.dumps(out, sort_keys=True, default=str, indent=1))


if __name__ == "__main__":
    main()
