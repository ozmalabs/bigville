"""Short decision-driven village check for Phase 016b.

Usage: python3 game_check.py <repo_root> <periods>

Builds the founding town and drives its residents with BigvilleGame (autonomous=True, the simple
backends), one game step at a time. Prints one JSON line per period: residents alive, deaths, grain,
bread, and flour. A period is the pack's TIME ticks_per_period game ticks.
"""
import json
import os
import sys
import time

root, periods = sys.argv[1], int(sys.argv[2])
sys.path.insert(0, root)
os.chdir(root)

from bigville.game import BigvilleGame  # noqa: E402
from worlds.bigville_world import BigvilleWorld  # noqa: E402

world = BigvilleWorld.from_town100(autonomous_actors=False)
ticks = int(world.E.TIME["ticks_per_period"])
steps = periods * ticks
game = BigvilleGame(world, autonomous=True, ticks_per_period=ticks)


def snapshot(step):
    alive = sum(1 for node in world._actors.values() if float(world.eng.node(node)["attrs"].get("alive", 1.0)) == 1.0)
    return {"step": step, "alive": alive, "deaths": len(world._deaths), "grain": round(world.qty("grain"), 2),
            "bread": round(world.qty("bread"), 2), "flour": round(world.qty("flour"), 2),
            "day": world.calendar()["day"], "seconds": round(time.time() - start, 1)}


start = time.time()
print(json.dumps(snapshot(0)), flush=True)
for step in range(1, steps + 1):
    game.step()
    if step % ticks == 0:
        print(json.dumps(snapshot(step)), flush=True)
print("FINAL " + json.dumps(snapshot(steps)), flush=True)
