"""Phase 042b reproduction: the lamplighter's tick-by-tick round on town100 (seed 305000, simple backend).

    PYTHONHASHSEED=0 python3 docs/phases/phase042b/reproduce_trace.py --root TREE --ticks 140 [--off]

Prints one JSON line per tick: the clock hour and night flag, the lamplighter's position, energy (stamina
reserve x 100), hunger, sleep state, the backend's last choice and reason, the outcome the world published for
him, and the lamps lit. With --off the switch is left off and the lamplighter is the first founding resident
(Verity Peaseblossom), for comparison.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--ticks", type=int, default=140)
    parser.add_argument("--off", action="store_true")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    sys.path.insert(0, root)
    os.chdir(root)
    from bigville.api import create_game
    from worlds import daynight as dn

    game = create_game(scenario="town100", seed=305000, default_backend="simple", autonomous=True,
                       ticks_per_period="world", affordance_mode="menu")
    w = game.world
    if not args.off:
        dn.switch_on(w)
    lp = dn.lamplighters(w)[0] if dn.on(w) else "Verity Peaseblossom"
    step = 0
    while step < args.ticks:
        result = game.step()
        if result.get("status") == "waiting":
            continue
        step += 1
        c = w.calendar()
        backend = game.backends.get(lp)
        choice = (backend.last_choice or {}) if backend is not None else {}
        body = w.body_state(lp)
        outcome = w.eng.node(w._actor(lp))["attrs"].get("last_outcome")
        lamps = [int(w.eng.node(n)["attrs"]["lit"]) for n in getattr(w, "_dn_lamps", {}).values()]
        print(json.dumps({
            "tick": step, "hour": round(float(c["hour"]), 2), "night": int(dn.is_night(w)) if dn.on(w) else None,
            "pos": list(w.actor_position(lp) or ()), "energy": round(float(body["stamina_reserve"]) * 100, 1),
            "hunger": round(float(w.eng.node(w._actors[lp])["attrs"].get("hunger", 0.0)), 3),
            "asleep": bool(body["asleep"]), "choice": choice.get("action"), "reason": choice.get("reason"),
            "outcome": outcome, "lamps": lamps}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
