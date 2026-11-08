"""Phase 070b: the simple village digest (as docs/phases/phase070/compare_digest.py) plus three counts the phase needs:
residents with a located injury (ledger above zero at the end and at any turn), the hours a day residents sleep, and
how many residents would feel their sleep debt (the sleep_debt source above its awareness, on the referee read).

Usage: python3 village_check.py <tree> <turns>
The tree is the repository to import (the working tree). Prints one JSON line.
Sleep hours come from the body's own tick hook: one count per world tick (96 per day, TIME). Nothing is changed.
"""
import hashlib
import json
import os
import sys

tree, turns = sys.argv[1], int(sys.argv[2])
sys.path.insert(0, tree)
os.chdir(tree)

from bigville.api import create_game  # noqa: E402
from bigville import village_eval as ve  # noqa: E402
from domains import interoception as I  # noqa: E402
from domains import bigville_entities as E  # noqa: E402

game = create_game(scenario="town100", seed=305017, default_backend="simple", autonomous=True,
                   ticks_per_period=ve.TICKS_PER_PERIOD)
w = game.world

stats = {"ticks": 0, "asleep_ticks": {}, "injured_turns": {}, "ever_injured": set()}
original_tick = w._body_tick


def counting_tick():
    stats["ticks"] += 1
    for name in w._actors:
        if not w.is_alive(name) or name not in getattr(w, "embodiment", {}):
            continue
        body = w.body_of(name)
        if body.attention() == "asleep":
            stats["asleep_ticks"][name] = stats["asleep_ticks"].get(name, 0) + 1
        if body.state["ledger"]:
            stats["ever_injured"].add(name)
    return original_tick()


w._body_tick = counting_tick
for _ in range(turns):
    game.step()


def canon(obj):
    return json.dumps(obj, sort_keys=True, default=str)


state = w.export_state()
actor_attrs = {}
mark_attrs = {}
for name, node in w._actors.items():
    attrs = dict(w.eng.node(node)["attrs"])
    actor_attrs[name] = {k: v for k, v in attrs.items() if not k.startswith("mark_")}
    marks = {k: v for k, v in attrs.items() if k.startswith("mark_")}
    if marks:
        mark_attrs[name] = marks
no_marks = canon({"state": state, "actors": actor_attrs, "stock": {k: w.qty(k) for k in sorted(w._stock)},
                  "deaths": len(w._deaths)})
days = stats["ticks"] / float(E.TIME["ticks_per_day"]) if "ticks_per_day" in E.TIME else stats["ticks"] / 96.0
alive = [n for n in w._actors if w.is_alive(n) and n in getattr(w, "embodiment", {})]
hours = sorted(round(stats["asleep_ticks"].get(n, 0) * float(E.TIME["minutes_per_tick"]) / 60.0 / days, 2)
               for n in alive)
felt = 0
reads = []
for n in alive:
    body = w.body_of(n)
    row = next(r for r in body.referee()["sources"] if r["source"] == "sleep_debt")
    reads.append(round(row["raw_intensity"], 3))
    felt += bool(row["felt"])
summary = {"turns": turns, "ticks": stats["ticks"], "digest_without_marks":
           hashlib.sha256(no_marks.encode()).hexdigest(), "deaths": len(w._deaths),
           "residents_ever_injured": len(stats["ever_injured"]),
           "residents_injured_now": sum(1 for n in alive if w.body_of(n).state["ledger"]),
           "sleep_hours_per_day": {"min": hours[0] if hours else None, "median": hours[len(hours) // 2] if hours else None,
                                   "max": hours[-1] if hours else None, "n": len(hours)},
           "sleep_debt_felt_now": felt, "sleep_debt_raw_now": {"min": min(reads) if reads else None,
                                                             "max": max(reads) if reads else None}}
print(json.dumps(summary, sort_keys=True))
