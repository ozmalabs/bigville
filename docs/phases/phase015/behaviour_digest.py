"""Phase 015 behaviour digest, run on HEAD (an export) and on the working tree.

Prints one JSON object. Run with PYTHONHASHSEED=0 from the repository root (or from an export of
HEAD with the same layout). Equal output means the 100-resident town built the same households,
parcel owners, residents, and crop beds, and that three village work ticks (`_village_work_tick`,
which `run_village` calls once per period) moved the same stock and set the same busy residents.
It does not run `run_village` itself, which takes about five minutes per period.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.getcwd()
sys.path.insert(0, ROOT)

from worlds.bigville_world import BigvilleWorld  # noqa: E402


def main():
    t = BigvilleWorld.from_town100()
    out = {}
    out["households"] = {name: [t.eng.node(h)["attrs"]["kind"], sorted(t.household_members(name))]
                         for name, h in sorted(t._households.items())}
    out["residents"] = {name: [t.eng.node(n)["attrs"].get("role"), t.eng.node(n)["attrs"].get("household"),
                               t.eng.node(n)["attrs"].get("trades")]
                        for name, n in sorted(t._actors.items())}
    out["land_owner"] = {name: t.land_owner(name) for name in sorted(t._land)}
    out["living_crops_after_seeding"] = len(t._living_crops())
    for period in range(3):
        t._village_work_tick(period)
        t.pass_period(1)
    out["stock_after_work"] = {k: round(float(t.qty(k)), 6) for k in sorted(t._stock)}
    out["busy_after_work"] = sorted(n for n in t._actors if t.busy(n))
    out["living_crops_after_work"] = len(t._living_crops())
    print(json.dumps(out, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
