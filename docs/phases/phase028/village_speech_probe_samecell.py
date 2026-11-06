"""Phase 028 probe: how many village utterances a same-cell rule would have delivered.

The pre-028 world delivered a targeted utterance only when speaker and target stood on the same cell. This probe
runs the same village as village_speech_probe.py (loudness on) and counts, at the moment of each speak, how many
targeted utterances had the target on the speaker's cell. The utterance schedule of the cheap backends depends on
turn, time and who is nearby, not on what was heard, so the count is taken from the same schedule the new rule
delivered on.

    python3 docs/phases/phase028/village_speech_probe_samecell.py TURNS SEED
"""
import sys
import time

sys.path.insert(0, "/home/matt/ozmadev/bigville")

from bigville.game import BigvilleGame  # noqa: E402
from worlds.bigville_world import BigvilleWorld  # noqa: E402


def main(turns, seed):
    world = BigvilleWorld.from_town100(seed=seed)
    counts = {"targeted": 0, "same_cell": 0, "adjacent": 0, "beyond_one": 0, "unplaced": 0}
    original = world.speak

    def counting_speak(speaker, target=None, content="", **kwargs):
        if target is not None:
            counts["targeted"] += 1
            a, b = world.actor_position(speaker), world.actor_position(target)
            if a is None or b is None:
                counts["unplaced"] += 1
            else:
                d = max(abs(a[0] - b[0]), abs(a[1] - b[1]))
                if d == 0:
                    counts["same_cell"] += 1
                elif d == 1:
                    counts["adjacent"] += 1
                else:
                    counts["beyond_one"] += 1
        return original(speaker, target, content, **kwargs)

    world.speak = counting_speak
    game = BigvilleGame(world, autonomous=True, ticks_per_period=None)
    start = time.time()
    for _ in range(turns):
        game.step()
    attrs = [world.eng.node(node)["attrs"] for node in world._utterances.values()]
    heard = sum(1 for a in attrs if a.get("target") and float(
        ((a.get("deliveries") or {}).get(a.get("target"), {}) or {}).get("heard", 0.0)))
    print(f"seed={seed} turns={turns} seconds={time.time() - start:.1f}")
    print(f"speak calls with a target at speech time: {counts}")
    print(f"new rule: targeted content delivered={heard} of {len(attrs)} utterances")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]))
