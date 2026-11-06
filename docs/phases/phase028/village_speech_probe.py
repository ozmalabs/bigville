"""Phase 028 probe: speech deliveries in the 100-resident village, with the loudness switch on and off.

Runs the default cheap backends through BigvilleGame for a fixed number of turns and counts what the
hearing rules delivered. Not a balance study: it reports counts for one seed and a short run.

    python3 docs/phases/phase028/village_speech_probe.py TURNS SWITCH(on|off) SEED
"""
import sys
import time

sys.path.insert(0, "/home/matt/ozmadev/bigville")

from bigville.game import BigvilleGame  # noqa: E402
from worlds.bigville_world import BigvilleWorld  # noqa: E402


def main(turns, loudness_on, seed):
    world = BigvilleWorld.from_town100(seed=seed)
    world.physical_subsystems["loudness"] = loudness_on
    game = BigvilleGame(world, autonomous=True, ticks_per_period=None)
    start = time.time()
    for _ in range(turns):
        game.step()
    elapsed = time.time() - start
    utterances = list(world._utterances.values())
    attrs = [world.eng.node(node)["attrs"] for node in utterances]
    broadcasts = sum(1 for a in attrs if not a.get("target"))
    heard_counts = [sum(1 for d in (a.get("deliveries") or {}).values() if d.get("heard")) for a in attrs]
    seen_counts = [sum(1 for d in (a.get("deliveries") or {}).values() if d.get("seen")) for a in attrs]
    targeted_heard = sum(
        1 for a in attrs if a.get("target") and float(
            ((a.get("deliveries") or {}).get(a.get("target"), {}) or {}).get("heard", 0.0)))
    targeted = len(attrs) - broadcasts
    print(f"seed={seed} turns={turns} loudness={'on' if loudness_on else 'off'} "
          f"seconds={elapsed:.1f} residents={len(world._actors)}")
    print(f"utterances={len(attrs)} targeted={targeted} broadcast={broadcasts}")
    print(f"targeted content delivered={targeted_heard} ({(targeted_heard / targeted if targeted else 0):.2f})")
    print(f"utterances with at least one listener hearing={sum(1 for h in heard_counts if h)}")
    print(f"mean hearers per utterance={sum(heard_counts) / len(heard_counts) if heard_counts else 0:.2f}")
    print(f"mean witnesses per utterance={sum(seen_counts) / len(seen_counts) if seen_counts else 0:.2f}")
    print(f"speech status={world.speech_occlusion_status()}")


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2] == "on", int(sys.argv[3]))
