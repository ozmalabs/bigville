"""Fix simple village: refusals by reason and by source, simple backend, town100.

    PYTHONHASHSEED=0 python3 docs/phases/fix_simple_village/probe_refusals.py --label before --turns 60

For every turn, each resident's refusal counter (the engine attribute `refusal_counts`, keyed by action and
reason) is read before and after game.step(). Each new refusal is attributed to the source of the response
that caused it:
  continuation  the response was a replayed continuation (backend_state.continued), not a backend decision
  backend       the backend decided the proposal this turn
Writes probe_<label>.json next to this script.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SEED = 305000


def _snapshot(world):
    out = {}
    for name in world._actors:
        counts = world.eng.node(world._actor(name))["attrs"].get("refusal_counts", {})
        out[name] = {(a, r): int(c) for a, reasons in counts.items() for r, c in reasons.items()}
    return out


def run(turns):
    from bigville.api import create_game
    game = create_game(scenario="town100", seed=SEED, default_backend="simple",
                       autonomous=True, ticks_per_period="world")
    world = game.world
    names = sorted(game.backends)
    actions = Counter()
    by_reason, by_source, by_action_reason = Counter(), Counter(), Counter()
    collapsed_per_turn, down_per_turn, collapsed_down_per_turn = [], [], []
    step = 0
    started = time.perf_counter()
    while step < turns:
        before = _snapshot(world)
        result = game.step()
        if result.get("status") == "waiting":
            continue
        step += 1
        after = _snapshot(world)
        for actor, response in game.last_responses.items():
            action = response.major_action.action if response.major_action else "none"
            actions[action] += 1
        turn_collapsed = 0
        for name in names:
            response = game.last_responses.get(name)
            for key, count in after.get(name, {}).items():
                delta = count - before.get(name, {}).get(key, 0)
                if delta <= 0:
                    continue
                action, reason = key
                source = "backend"
                if response is not None and response.backend_state.get("continued"):
                    source = "continuation"
                by_reason[reason] += delta
                by_source[(source, reason)] += delta
                by_action_reason[f"{action}/{reason}"] += delta
                if reason == "collapsed":
                    turn_collapsed += delta
        collapsed_per_turn.append(turn_collapsed)
        down = [n for n in names if world.is_alive(n) and world._sleep_code(n) is not None]
        down_per_turn.append(len(down))
        collapsed_down_per_turn.append(sum(1 for n in down if world._sleep_code(n) == "collapsed"))
    elapsed = time.perf_counter() - started
    alive = [n for n in names if world.is_alive(n)]
    return {
        "turns": step, "seed": SEED, "elapsed_seconds": round(elapsed, 1),
        "alive_at_end": len(alive), "action_counts": dict(sorted(actions.items())),
        "refusals_by_reason": dict(sorted(by_reason.items())),
        "refusals_by_source_reason": {f"{s}/{r}": c for (s, r), c in sorted(by_source.items())},
        "refusals_by_action_reason": dict(sorted(by_action_reason.items())),
        "refusals_total": sum(by_reason.values()),
        "collapsed_per_turn": collapsed_per_turn,
        "down_residents_per_turn": down_per_turn,
        "collapsed_residents_per_turn": collapsed_down_per_turn,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--turns", type=int, default=60)
    args = parser.parse_args(argv)
    data = run(args.turns)
    data["label"] = args.label
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"probe_{args.label}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    print(json.dumps({k: data[k] for k in ("label", "turns", "elapsed_seconds", "alive_at_end",
                                           "refusals_total", "refusals_by_reason")}, sort_keys=True))
    print(json.dumps(data["refusals_by_source_reason"], sort_keys=True))
    print(json.dumps(data["action_counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
