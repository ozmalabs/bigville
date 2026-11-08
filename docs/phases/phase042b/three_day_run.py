"""Phase 042b: the lamplighter over game days, with DAYNIGHT on (town100, seed 305000, simple backend).

    PYTHONHASHSEED=0 python3 docs/phases/phase042b/three_day_run.py --root TREE --days 3 --out DIR

Runs `game.step()` for days x 96 ticks (one tick is 15 minutes, TIME.ticks_per_day 96), with worlds.daynight
switched on right after the game is created. For each day it reports, from the tick log:
* the dusk lighting: the hours after that day's sunset until all four lamps are lit (or None);
* the dawn douse: the hours after that day's sunrise until all four lamps are dark (or None);
* the lamplighter's light and douse actions applied in that day, and his refusals by reason;
* his eat, sleep and rest actions, his lowest energy and highest hunger, and whether he is alive;
* the deaths in the town at the end, and the oil in the store.
It writes DIR/three_day_ticks.jsonl (one line per tick) and DIR/three_day_summary.json. The run is slow
(about 0.5 s a tick), so run it in the background if the days are many.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--seed", type=int, default=305000)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    sys.path.insert(0, root)
    os.chdir(root)
    os.makedirs(args.out, exist_ok=True)
    from bigville.api import create_game
    from worlds import daynight as dn
    from domains import daynight as D
    from domains import bigville_entities as E

    game = create_game(scenario="town100", seed=args.seed, default_backend="simple", autonomous=True,
                       ticks_per_period="world", affordance_mode="menu")
    w = game.world
    dn.switch_on(w)
    lp = dn.lamplighters(w)[0]
    tpd = int(E.TIME["ticks_per_day"])
    orig = w.major_action
    lp_actions = Counter()
    lp_events = []   # (clock, action) for each applied light or douse

    def spy(actor, action, *a, **k):
        res = orig(actor, action, *a, **k)
        if actor == lp:
            code = None if res else w.eng.node(w._actor(lp))["attrs"].get("last_outcome", {}).get("reason")
            lp_actions[action if res else f"{action}:{code}"] += 1
            if res and action in ("light", "douse"):
                lp_events.append((float(w.calendar()["clock"]), action))
        return res

    w.major_action = spy
    ticks = []
    turns = args.days * tpd
    step = 0
    tick_path = os.path.join(args.out, "three_day_ticks.jsonl")
    with open(tick_path, "w", encoding="utf-8") as log:
        while step < turns:
            result = game.step()
            if result.get("status") == "waiting":
                continue
            step += 1
            c = w.calendar()
            be = game.backends.get(lp)
            choice = be.last_choice or {} if be is not None else {}
            body = w.body_state(lp)
            row = {"tick": step, "clock": float(c["clock"]), "hour": round(float(c["hour"]), 3),
                   "night": int(dn.is_night(w)), "pos": list(w.actor_position(lp) or ()),
                   "energy": round(float(body["stamina_reserve"]) * 100.0, 2),
                   "hunger": round(float(w.eng.node(w._actors[lp])["attrs"].get("hunger", 0.0)), 3),
                   "alive": bool(w.is_alive(lp)), "asleep": bool(body["asleep"]),
                   "choice": choice.get("action"), "reason": choice.get("reason"),
                   "lamps_lit": sum(1 for n in w._dn_lamps.values() if float(w.eng.node(n)["attrs"]["lit"]) == 1.0),
                   "oil": round(float(w.qty("oil")), 3)}
            ticks.append(row)
            log.write(json.dumps(row) + "\n")
    w.major_action = orig
    alive = [n for n in game.backends if w.is_alive(n)]
    days = []
    for day in range(args.days):
        sunrise, sunset, length = D.sunrise_sunset(day % int(E.TIME["days_per_year"]), E.DAYNIGHT)
        base = day * tpd
        sunrise_clock = base + (sunrise - float(E.TIME["start_hour"])) * tpd / 24.0
        sunset_clock = base + (sunset - float(E.TIME["start_hour"])) * tpd / 24.0
        day_rows = [r for r in ticks if base <= r["clock"] < base + tpd]
        after_sunset = [r for r in ticks if r["clock"] >= sunset_clock and r["clock"] < sunrise_clock + tpd]
        all_lit = next((r for r in after_sunset if r["lamps_lit"] == len(w._dn_lamps)), None)
        all_dark = next((r for r in ticks if r["clock"] >= sunrise_clock and r["lamps_lit"] == 0
                         and r["clock"] < sunset_clock), None)
        ev = defaultdict(int)
        for clock, action in lp_events:
            if base <= clock < base + tpd:
                ev[action] += 1
        days.append({
            "day": day, "sunrise_hour": round(sunrise, 2), "sunset_hour": round(sunset, 2),
            "dusk_all_lit_hours_after_sunset": (round((all_lit["clock"] - sunset_clock) / (tpd / 24.0), 2)
                                                if all_lit and all_lit["clock"] >= sunset_clock else None),
            "dawn_all_dark_hours_after_sunrise": (round((all_dark["clock"] - sunrise_clock) / (tpd / 24.0), 2)
                                                  if all_dark else None),
            "lamp_lights_applied": ev["light"], "lamp_douses_applied": ev["douse"],
            "lamplighter_min_energy": min((r["energy"] for r in day_rows), default=None),
            "lamplighter_max_hunger": max((r["hunger"] for r in day_rows), default=None),
            "lamplighter_alive_at_day_end": bool(day_rows and day_rows[-1]["alive"]),
        })
    summary = {"root": root, "seed": args.seed, "days": args.days, "ticks": len(ticks),
               "lamplighter": lp, "days_detail": days, "lamplighter_actions": dict(sorted(lp_actions.items())),
               "lamplighter_alive_end": bool(w.is_alive(lp)), "lamplighter_hunger_end": ticks[-1]["hunger"],
               "residents_alive_end": len(alive), "residents": len(game.backends),
               "oil_end": round(float(w.qty("oil")), 3), "lamps_lit_end": ticks[-1]["lamps_lit"]}
    with open(os.path.join(args.out, "three_day_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True)
    print(json.dumps(summary, sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
