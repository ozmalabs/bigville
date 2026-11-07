"""Run the town100 simple village for N turns from a given tree; print a digest of the state without marks,
the number of mark attributes, and the marks summed over residents.  Usage: compare60.py <tree> <turns>"""
import hashlib
import json
import os
import sys

tree, turns = sys.argv[1], int(sys.argv[2])
sys.path.insert(0, tree)
os.chdir(tree)

from bigville.api import create_game  # noqa: E402
from bigville import village_eval as ve  # noqa: E402

game = create_game(scenario="town100", seed=305017, default_backend="simple", autonomous=True,
                   ticks_per_period=ve.TICKS_PER_PERIOD)
w = game.world
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
summary = {"turns": turns, "digest_without_marks": hashlib.sha256(no_marks.encode()).hexdigest(),
           "residents_with_marks": len(mark_attrs),
           "mark_totals": {}, "deaths": len(w._deaths)}
for marks in mark_attrs.values():
    for k, v in marks.items():
        summary["mark_totals"][k] = round(summary["mark_totals"].get(k, 0.0) + float(v), 4)
summary["mark_totals"] = dict(sorted(summary["mark_totals"].items()))
print(json.dumps(summary, sort_keys=True))
