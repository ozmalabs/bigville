"""Phase 030 digest check: the 100-resident town run for a short span, printed as JSON.

Run before and after the phase's edits and compare the output:
    python3 docs/phases/phase030/digest_check.py > docs/phases/phase030/digest_<label>.log
Both village_eval arms, seed 305017, 24 turns (the same span phase 026 used). Nothing is written to the
world; the script only reads the run's measurements.
"""
import json

from bigville import village_eval as ve

out = {}
for arm in ("baseline", "sharing"):
    r = ve.run_evaluation(seeds=(305017,), arms=(arm,), turns=24, replay=False, max_run_seconds=900)
    run = r["runs"][0]
    out[arm] = {"digest": run["measurements_digest"], "final": run["final"], "actions": run["actions"],
                "invariants": run["invariants"]}
print(json.dumps(out, sort_keys=True, default=str))
