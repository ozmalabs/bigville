import sys, collections, time, traceback
sys.path.insert(0, "/home/matt/ozmadev/bigville")
from worlds.bigville_world import BigvilleWorld

def fresh(ticks):
    w = BigvilleWorld.from_town100(autonomous_actors=False)
    for _ in range(ticks):
        w.tick()
    return w

t0 = time.time()
results = collections.Counter()
failures = []
for ticks in (1, 3):
    base = fresh(ticks)
    print("base", ticks, round(time.time() - t0, 1), "s", flush=True)
    for actor in sorted(base._actors):
        base.actor_tick(actor)
        try:
            options = base.actor_affordances(actor)
        except Exception as exc:
            print("AFFORDANCE RAISE", ticks, actor, type(exc).__name__, exc, flush=True)
            traceback.print_exc()
            continue
        for opt in options:
            plan = dict(opt)
            fw = fresh(ticks)
            fw.actor_tick(actor)
            try:
                ok = fw.enact_plan(actor, plan)
            except Exception as exc:
                ok = f"RAISE {type(exc).__name__}: {exc}"
            key = (plan.get("action"), "ok" if ok is True else ("false" if ok is False else str(ok)[:60]))
            results[key] += 1
            if ok is not True:
                failures.append((ticks, actor, plan, ok))
        print("actor", ticks, actor, len(options), round(time.time() - t0, 1), flush=True)
    print("ticks", ticks, "done", round(time.time() - t0, 1), flush=True)
print("options by action/result:")
for k, v in sorted(results.items(), key=lambda kv: str(kv[0])):
    print(" ", k, v)
print("n failures", len(failures))
seen = set()
for ticks, actor, plan, ok in failures:
    key = (plan.get("action"), str(ok)[:80])
    if key in seen:
        continue
    seen.add(key)
    print(ticks, actor, plan, ok)
