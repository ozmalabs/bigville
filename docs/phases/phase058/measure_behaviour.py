"""Phase 058 behaviour measurement: a pinned, simple-backend town100 run.

    PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label before --turns 200
    PYTHONHASHSEED=0 python3 docs/phases/phase058/measure_behaviour.py --label after_seed_off --seeding off

Builds the 100-resident town (seed 305000) with the simple ("cheap") backend for every resident, runs
`game.step()` for the given number of turns, and writes one JSON file next to this script. The file holds
the action counts, the number of utterances, the handovers, deaths, the mean hunger at the end, the
per-resident action digests, and the full action sequence of five named residents (the first five of the
cast). `--seeding off` replaces the founding relationship seeding with a no-op, so the arm equals the
world with no relationship records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SEED = 305000
SAMPLE = 5


def _install_seeding_switch(mode):
    """`off` makes the founding relationship seeding a no-op. `on` forces it on (enabled=True), whatever the
    pack's default is. `default` leaves the pack's switch alone."""
    if mode == "default":
        return
    try:
        import domains.relationship_seeding as rs
    except ImportError:          # before Phase 058 there is no seeding to switch
        return
    if mode == "off":
        rs.seed_founding_relationships = lambda world, seed, **kw: 0
    else:
        real = rs.seed_founding_relationships
        rs.seed_founding_relationships = lambda world, seed, **kw: real(world, seed, **dict(kw, enabled=True))


def run(turns, seeding):
    _install_seeding_switch(seeding)
    from bigville.api import create_game
    game = create_game(scenario="town100", seed=SEED, default_backend="simple",
                       autonomous=True, ticks_per_period="world")
    world = game.world
    names = sorted(game.backends)
    sample = [r["name"] for r in world._cast100["residents"][:SAMPLE]]
    actions = Counter()
    per_actor = {name: [] for name in names}
    utterances = handovers = 0
    hunger_trace = []
    started = time.perf_counter()
    step = 0
    while step < turns:
        result = game.step()
        if result.get("status") == "waiting":
            continue
        step += 1
        for actor, response in game.last_responses.items():
            action = response.major_action.action if response.major_action else "none"
            per_actor.setdefault(actor, []).append(action)
            actions[action] += 1
            utterances += len(response.utterances)
            if action in {"give", "hand_over", "handover"}:
                handovers += 1
        alive = [n for n in names if world.is_alive(n)]
        hunger_trace.append(round(sum(float(world.eng.node(world._actors[n])["attrs"].get("hunger", 0.0))
                                      for n in alive) / max(1, len(alive)), 4))
    elapsed = time.perf_counter() - started
    alive = [n for n in names if world.is_alive(n)]
    hungers = [float(world.eng.node(world._actors[n])["attrs"].get("hunger", 0.0)) for n in alive]
    digests = {n: hashlib.sha256(",".join(seq).encode()).hexdigest()[:16] for n, seq in per_actor.items()}
    return {
        "seeding": seeding, "turns": step, "seed": SEED, "residents": len(names),
        "elapsed_seconds": round(elapsed, 1),
        "action_counts": dict(sorted(actions.items())),
        "utterances": utterances, "handovers": handovers,
        "deaths": len(names) - len(alive), "alive_at_end": len(alive),
        "hunger_mean_end": round(sum(hungers) / max(1, len(hungers)), 4),
        "hunger_mean_by_turn": hunger_trace,
        "relationships_on_record": len(getattr(world, "_relationships", {})),
        "per_actor_digest": digests,
        "sample_sequences": {n: per_actor.get(n, []) for n in sample},
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--turns", type=int, default=200)
    parser.add_argument("--seeding", choices=("on", "off", "default"), default="default")
    parser.add_argument("--out", default=None, help="the JSON file to write (default: behaviour_<label>.json here)")
    args = parser.parse_args(argv)
    data = run(args.turns, args.seeding)
    data["label"] = args.label
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), f"behaviour_{args.label}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    summary = {k: data[k] for k in ("label", "turns", "elapsed_seconds", "utterances", "handovers",
                                    "deaths", "alive_at_end", "hunger_mean_end", "relationships_on_record")}
    print(json.dumps(summary, sort_keys=True))
    print(json.dumps(data["action_counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
