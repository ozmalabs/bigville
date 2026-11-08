"""Phase 042c: the lamplighter over game days, with DAYNIGHT on (town100, simple backend). Adapted from
docs/phases/phase042b/three_day_run.py, with a seed and an optional role_identity for the lamplighter.

    PYTHONHASHSEED=0 python3 docs/phases/phase042c/duty_run.py --root TREE --days 7 --seed 305000 --out DIR
    PYTHONHASHSEED=0 python3 docs/phases/phase042c/duty_run.py --root TREE --days 7 --seed 305000 --role 0.1 --out DIR

--root is the tree to run (the clean scratch tree, or the HEAD archive for the 042b comparison). --role, when given,
sets the lamplighter's personality role_identity (the trait the duty is scaled by) before the first tick; without it
the lamplighter keeps the drawn value.

For each game day it reports, from the tick log:
* the dusk lighting: the hours after that day's sunset until all four lamps are lit (or None);
* the dawn douse: the hours after that day's sunrise until all four lamps are dark (or None);
* the lamplighter's light and douse actions applied in that day, and the refusals by reason;
* his eat, sleep and rest actions, his lowest energy and highest hunger, and whether he is alive;
* the ticks on which his choice was a duty (the duty drive held), and the duty trace of the last tick;
* the residents alive at the day's end (the whole town, every backend).
It writes DIR/duty_ticks.jsonl (one line per tick) and DIR/duty_summary.json. About 0.5 s a tick, so run it in the
background for several days.
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
    parser.add_argument("--role", type=float, default=None, help="the lamplighter's role_identity (0 to 1)")
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
    if args.role is not None:
        game.backends[lp].character.personality["role_identity"] = float(args.role)
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
    tick_path = os.path.join(args.out, "duty_ticks.jsonl")
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
                   "duty": choice.get("duty"),
                   "lamps_lit": sum(1 for n in w._dn_lamps.values() if float(w.eng.node(n)["attrs"]["lit"]) == 1.0),
                   "oil": round(float(w.qty("oil")), 3),
                   "town_alive": sum(1 for n in game.backends if w.is_alive(n))}
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
        choices = Counter(r["choice"] for r in day_rows)
        days.append({
            "day": day, "sunrise_hour": round(sunrise, 2), "sunset_hour": round(sunset, 2),
            "dusk_all_lit_hours_after_sunset": (round((all_lit["clock"] - sunset_clock) / (tpd / 24.0), 2)
                                                if all_lit and all_lit["clock"] >= sunset_clock else None),
            "dawn_all_dark_hours_after_sunrise": (round((all_dark["clock"] - sunrise_clock) / (tpd / 24.0), 2)
                                                  if all_dark else None),
            "lamp_lights_applied": ev["light"], "lamp_douses_applied": ev["douse"],
            "lamplighter_min_energy": min((r["energy"] for r in day_rows), default=None),
            "lamplighter_max_hunger": max((r["hunger"] for r in day_rows), default=None),
            "lamplighter_eat_ticks": choices.get("eat", 0), "lamplighter_sleep_ticks": choices.get("sleep", 0),
            "lamplighter_rest_ticks": choices.get("rest", 0),
            "lamplighter_duty_ticks": sum(1 for r in day_rows if r["reason"] == "duty"),
            "lamplighter_alive_at_day_end": bool(day_rows and day_rows[-1]["alive"]),
            "town_alive_at_day_end": day_rows[-1]["town_alive"] if day_rows else None,
        })
    summary = {"root": root, "seed": args.seed, "days": args.days, "role_override": args.role,
               "role_identity": game.backends[lp].character.personality.get("role_identity"),
               "ticks": len(ticks), "lamplighter": lp, "days_detail": days,
               "lamplighter_actions": dict(sorted(lp_actions.items())),
               "lamplighter_alive_end": bool(w.is_alive(lp)), "lamplighter_hunger_end": ticks[-1]["hunger"],
               "residents_alive_end": len(alive), "residents": len(game.backends),
               "oil_end": round(float(w.qty("oil")), 3), "lamps_lit_end": ticks[-1]["lamps_lit"]}
    with open(os.path.join(args.out, "duty_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True)
    print(json.dumps(summary, sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
