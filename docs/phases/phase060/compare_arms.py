"""Phase 060: compare the behaviour JSON files of the measurement arms (written by measure_speech.py).

    python3 docs/phases/phase060/compare_arms.py A.json B.json

Prints the differences between two arms: the scalar fields, the action counts, the number of residents whose
action digest differs (and which), and the sample sequences that differ. Fields that are not behaviour (label,
tree, elapsed time) are skipped.
"""
from __future__ import annotations

import json
import sys
from collections import Counter

SKIP = {"label", "tree", "elapsed_seconds", "switch"}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def compare(a, b):
    lines = []
    keys = sorted(set(a) | set(b))
    for key in keys:
        if key in SKIP or key in ("per_actor_digest", "sample_sequences", "action_counts", "hunger_mean_by_turn"):
            continue
        if a.get(key) != b.get(key):
            lines.append(f"{key}: {a.get(key)} -> {b.get(key)}")
    ca, cb = Counter(a.get("action_counts", {})), Counter(b.get("action_counts", {}))
    for action in sorted(set(ca) | set(cb)):
        if ca[action] != cb[action]:
            lines.append(f"action {action}: {ca[action]} -> {cb[action]} ({cb[action] - ca[action]:+d})")
    da, db = a.get("per_actor_digest", {}), b.get("per_actor_digest", {})
    differing = sorted(n for n in set(da) | set(db) if da.get(n) != db.get(n))
    lines.append(f"residents with a different action sequence: {len(differing)} of {len(set(da) | set(db))}")
    for name in differing[:10]:
        lines.append(f"  {name}")
    sa, sb = a.get("sample_sequences", {}), b.get("sample_sequences", {})
    for name in sorted(set(sa) | set(sb)):
        if sa.get(name) != sb.get(name):
            first = next((i for i, (x, y) in enumerate(zip(sa.get(name, []), sb.get(name, [])))
                          if x != y), min(len(sa.get(name, [])), len(sb.get(name, []))))
            lines.append(f"sample {name}: first difference at turn {first + 1}")
    return lines


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    a, b = load(argv[0]), load(argv[1])
    lines = compare(a, b)
    print(f"{a.get('label')} -> {b.get('label')}")
    print("\n".join(lines) if lines else "identical behaviour (every field, digest and sample sequence)")
    if b.get("speech_in_totals"):
        print("speech_in totals:", json.dumps(b["speech_in_totals"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
