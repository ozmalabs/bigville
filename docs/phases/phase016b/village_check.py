"""Short village check for Phase 016b: build the founding town and run a few periods of the world.

Usage: python3 village_check.py <repo_root> <periods> [ticks_per_period]

Residents do not decide here (autonomous_actors=False), so the run shows what the physical world does
with the cast: who is alive, grain and bread stock, and deaths. It is not a behaviour test.
"""
import json
import os
import sys
import time

root, periods = sys.argv[1], int(sys.argv[2])
ticks = int(sys.argv[3]) if len(sys.argv) > 3 else None
sys.path.insert(0, root)
os.chdir(root)

from worlds.bigville_world import BigvilleWorld  # noqa: E402

world = BigvilleWorld.from_town100(autonomous_actors=False)


def snapshot(label):
    alive = sum(1 for node in world._actors.values() if float(world.eng.node(node)["attrs"].get("alive", 1.0)) == 1.0)
    return {"label": label, "alive": alive, "deaths": len(world._deaths),
            "grain": round(world.qty("grain"), 2), "bread": round(world.qty("bread"), 2),
            "flour": round(world.qty("flour"), 2), "clock": world.calendar()["day"]}


out = {"root": root, "periods": periods, "ticks_per_period": ticks, "start": snapshot("start"), "by_period": []}
start = time.time()
for p in range(periods):
    t0 = time.time()
    if ticks:
        report = world.run_village(periods=1, ticks_per_period=ticks)
    else:
        report = world.run_village(periods=1)
    snap = snapshot(f"period {p + 1}")
    snap["seconds"] = round(time.time() - t0, 1)
    snap["sanity_alive"] = report.get("alive") if isinstance(report, dict) else None
    snap["sanity_errors"] = report.get("errors") if isinstance(report, dict) else None
    out["by_period"].append(snap)
    print(json.dumps(snap, default=str), flush=True)
out["seconds_total"] = round(time.time() - start, 1)
print("FINAL " + json.dumps(out, default=str))
