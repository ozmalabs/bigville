import json, sys
from worlds.bigville_world import BigvilleWorld
from bigville import village_eval as ve
mode = sys.argv[1]
if mode == "no_records":
    BigvilleWorld._record_handover = lambda self, *a, **k: None
out = {}
for arm in ("baseline", "sharing"):
    r = ve.run_evaluation(seeds=(305017,), arms=(arm,), turns=24, replay=False, max_run_seconds=800)
    run = r["runs"][0]
    out[arm] = {"digest": run["measurements_digest"], "final": run["final"], "actions": run["actions"],
                "invariants": run["invariants"]}
print(json.dumps(out, sort_keys=True, default=str))
