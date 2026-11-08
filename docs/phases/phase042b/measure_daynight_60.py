"""Phase 042b: the Phase 058 60-turn measurement with DAYNIGHT on or off, for the bigville pack.

    PYTHONHASHSEED=0 python3 docs/phases/phase042b/measure_daynight_60.py --root TREE --mode on|off --out FILE

It imports docs/phases/phase058/measure_behaviour.py from TREE and runs its `run(turns, seeding)` with the
default seeding. Mode `on` calls worlds.daynight.switch_on on each new world right after the game is created,
which is the same call the pack switch makes at construction (the pack default stays off). Mode `off` changes
nothing. The output holds the same fields as the Phase 058 file, plus the lamplighter's record when day and
night is on.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--mode", choices=("on", "off"), required=True)
    parser.add_argument("--turns", type=int, default=60)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    sys.path.insert(0, root)
    os.chdir(root)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "measure_behaviour", os.path.join(root, "docs", "phases", "phase058", "measure_behaviour.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    import bigville.api as api
    real_create = api.create_game
    worlds = []

    def create_and_switch(*a, **k):
        game = real_create(*a, **k)
        if args.mode == "on":
            from worlds import daynight as dn
            dn.switch_on(game.world)
        worlds.append(game.world)
        return game

    api.create_game = create_and_switch
    data = m.run(args.turns, "default")
    data["mode"] = args.mode
    data["root"] = root
    if args.mode == "on":
        from worlds import daynight as dn
        w = worlds[0]
        lp = dn.lamplighters(w)
        data["lamplighter"] = lp[0] if lp else None
        data["lamps_lit_at_end"] = sum(1 for n in w._dn_lamps.values() if float(w.eng.node(n)["attrs"]["lit"]) == 1.0)
        data["oil_at_end"] = round(float(w.qty("oil")), 3)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    keys = ("mode", "turns", "deaths", "alive_at_end", "hunger_mean_end", "utterances", "handovers",
            "action_counts", "lamplighter", "lamps_lit_at_end", "oil_at_end")
    print(json.dumps({k: data.get(k) for k in keys if k in data}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
