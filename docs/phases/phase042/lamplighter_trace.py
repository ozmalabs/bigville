import sys, json
sys.path.insert(0, sys.argv[1]); import os; os.chdir(sys.argv[1])
from bigville.api import create_game
from worlds import daynight as dn
g = create_game(scenario="town100", seed=305000, default_backend="simple", autonomous=True, ticks_per_period="world")
w = g.world
dn.switch_on(w)
lp = dn.lamplighters(w)[0]
rows = []
for i in range(int(sys.argv[2])):
    g.step()
    if i % 6 == 5:
        c = w.calendar()
        lamps = [int(w.eng.node(n)["attrs"]["lit"]) for n in w._dn_lamps.values()]
        bs = w.body_state(lp)
        rows.append([c["clock"], round(c["hour"],1), int(dn.is_night(w)), lamps, round(w.qty("oil"),2), w.actor_position(lp), round(dn._jobs and 0 or w.stamina_reserve(lp),3)])
        print(rows[-1], flush=True)
