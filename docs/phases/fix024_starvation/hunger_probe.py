"""Town100, simple backends: hunger and stamina at a few turns, and the starve limit."""
import statistics
import sys

from bigville.api import create_game
from bigville import village_eval as ve
from domains import bigville_entities as E

game = create_game(scenario="town100", seed=305017, default_backend="simple", autonomous=True,
                   ticks_per_period=ve.TICKS_PER_PERIOD)
w = game.world
print("starve_limit", E.CARE.get("starve_limit"))
for t in range(96):
    game.step()
    if t in (0, 10, 30, 60, 90, 94):
        hs = [float(w.eng.node(n)["attrs"].get("hunger", 0.0)) for n in w._actors.values()]
        res = [w.stamina_reserve(a) for a in w._actors]
        asleep = sum(1 for a in w._actors if w.eng.node(w._actors[a])["attrs"].get("asleep"))
        coll = sum(1 for a in w._actors if w.eng.node(w._actors[a])["attrs"].get("collapsed"))
        print(t, "hunger mean %.3f max %.3f" % (statistics.mean(hs), max(hs)),
              "reserve mean %.3f min %.3f" % (statistics.mean(res), min(res)), "asleep", asleep, "collapsed", coll,
              "eats", sum(1 for a, r in game.last_responses.items() if r.major_action and r.major_action.action == "eat"))
