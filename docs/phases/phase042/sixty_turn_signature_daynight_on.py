"""Deterministic 60-turn simple-village signature. Usage: python3 sixty.py <tree_root> [turns]"""
import hashlib
import json
import os
import sys

root = os.path.abspath(sys.argv[1])
turns = int(sys.argv[2]) if len(sys.argv) > 2 else 60
sys.path.insert(0, root)
os.chdir(root)

from bigville.api import create_game  # noqa: E402

game = create_game(scenario="town100", seed=305000, default_backend="simple", autonomous=True,
                   ticks_per_period="world")
from worlds import daynight as _dn
_dn.switch_on(w0 := game.world)
statuses = {}
for _ in range(turns):
    result = game.step()
    st = str(result.get("status"))
    statuses[st] = statuses.get(st, 0) + 1
w = game.world
from domains import bigville_entities as E  # noqa: E402

stocks = {k: round(float(w.qty(k)), 4) for k in sorted(E.ITEMS)}
stocks = {k: v for k, v in stocks.items() if v}
actors = []
for name in sorted(w._actors):
    try:
        pos = w.actor_position(name)
    except Exception:
        pos = None
    alive = w.is_alive(name)
    actors.append([name, str(pos), bool(alive), round(float(w.health(name)), 4)])
sig = {
    "turns": turns,
    "statuses": statuses,
    "refusals": w.refusal_counts(),
    "stocks": stocks,
    "actors": actors,
    "alive": sum(1 for a in actors if a[2]),
    "clock": w.calendar().get("clock"),
    "lamps": [[int(w.eng.node(n)["attrs"]["lit"]), round(float(w.eng.node(n)["attrs"]["fuel"]),3)] for n in w._dn_lamps.values()],
    "lamplighters": _dn.lamplighters(w),
}
text = json.dumps(sig, sort_keys=True, default=str)
print(json.dumps({"sha256": hashlib.sha256(text.encode()).hexdigest(), "alive": sig["alive"],
                  "actors": len(actors), "clock": sig["clock"], "stocks_n": len(stocks),
                  "statuses": statuses}, sort_keys=True))
with open(os.environ.get("SIG_OUT", "/tmp/p42/sig.json"), "w") as fh:
    fh.write(text)
