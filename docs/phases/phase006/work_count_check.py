"""Phase 006 diagnostic: which work recipes the simple residents enact in the first periods.

Usage: python3 work_count_check.py <repo_root> <periods>

Runs the same BigvilleGame loop as game_check.py and counts, per recipe, the work plans the world
enacted (the world's `_enact_plan` is wrapped; the count is of plans offered and applied, by recipe name).
Also counts how many open-recipe work plans were chosen while the resident stood at the store.
"""
import collections
import json
import os
import sys

root, periods = sys.argv[1], int(sys.argv[2])
sys.path.insert(0, root)
os.chdir(root)

from bigville.game import BigvilleGame  # noqa: E402
from worlds.bigville_world import BigvilleWorld  # noqa: E402

world = BigvilleWorld.from_town100(autonomous_actors=False)
ticks = int(world.E.TIME["ticks_per_period"])
game = BigvilleGame(world, autonomous=True, ticks_per_period=ticks)
counts = collections.Counter()
open_counts = collections.Counter()
store_cell = world.map_position_node(world._store)
original = world._enact_plan


def counting_enact(actor, plan):
    result = original(actor, plan)
    if plan.get("action") == "work":
        recipe = plan.get("recipe") or plan.get("params", {}).get("recipe") or "?"
        counts[(recipe, bool(result))] += 1
        spec = world._recipe_specs.get(recipe, {})
        if spec.get("open"):
            open_counts[recipe] += 1
    return result


world._enact_plan = counting_enact
for _ in range(periods * ticks):
    game.step()
print(json.dumps({"periods": periods, "work_plans_by_recipe_and_applied": {f"{k[0]}|applied={k[1]}": v
                                                                      for k, v in sorted(counts.items())},
                  "open_recipe_plans": dict(open_counts),
                  "store_cell": list(store_cell) if store_cell else None,
                  "night_soil_store": round(world.qty("night_soil"), 2),
                  "fuel_store": round(sum(world.qty(k) for k, _ in world.E.type_members(world.E.HEATING["fuel_type"])), 2)},
                 sort_keys=True))
