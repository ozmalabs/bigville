"""Fix simple village: founding tie counts by kind, per resident, and the workplace ring's overlap.

    python3 docs/phases/fix_simple_village/tie_counts.py   -> tie_counts.json (next to this script)

Builds the bare town100 (seed 305000) with the pack's default seeding switch, counts the directed ties on
record by kind, the household flag, and per holder (total and close kinds). Then it calls
seed_workplace_relationships on a second build and reports how many of its ties overwrite a founding bond.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from domains.pack import load_pack  # noqa: E402
from worlds.bigville_world import BigvilleWorld  # noqa: E402

SEED = 305000


def main():
    world = BigvilleWorld.from_town100(seed=SEED, autonomous_actors=False)
    cfg = load_pack("bigville")["RELATIONSHIP_SEEDING"]
    close = set(cfg["close_kinds"])
    attrs = {key: world.eng.node(bond)["attrs"] for key, bond in world._relationships.items()}
    kinds = Counter(a["kind"] for a in attrs.values())
    household_flag = sum(1 for a in attrs.values() if a.get("household") == 1.0)
    reciprocated = sum(1 for (a, b) in attrs if (b, a) in attrs)
    total_per, close_per = Counter(), Counter()
    for (holder, _target), a in attrs.items():
        total_per[holder] += 1
        if a["kind"] in close:
            close_per[holder] += 1
    residents = list(world._actors)
    totals = [total_per.get(name, 0) for name in residents]
    closes = [close_per.get(name, 0) for name in residents]
    out = {
        "seed": SEED, "switch_enabled": bool(cfg["enabled"]), "directed_records": len(attrs),
        "by_kind": dict(sorted(kinds.items())), "household_flag": household_flag,
        "reciprocated_records": reciprocated,
        "per_resident_total": {"min": min(totals), "median": statistics.median(totals), "max": max(totals),
                               "with_zero": sum(1 for t in totals if t == 0)},
        "per_resident_close": {"min": min(closes), "median": statistics.median(closes), "max": max(closes)},
    }

    fresh = BigvilleWorld.from_town100(seed=SEED, autonomous_actors=False)
    founding = {key: bond for key, bond in fresh._relationships.items()}
    minted = fresh.seed_workplace_relationships()
    overwritten = sum(1 for key, bond in founding.items() if fresh._relationships[key] is not bond)
    ring_new = sum(1 for key in fresh._relationships if key not in founding)
    out["workplace_ring"] = {"minted_pairs": minted, "new_directed_keys": ring_new,
                             "founding_bonds_overwritten": overwritten}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tie_counts.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
