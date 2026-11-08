"""Phase 060 measurement: the Phase 058 behaviour run, with SPEECH_UNDERSTANDING forced on or off.

    python3 measure_speech.py --root <tree> --switch off --turns 60 --label off60 --out <json>

`--root` is a repository tree (a snapshot is safest while others are editing the working tree). The Phase 058
`measure_behaviour.run()` of that tree does the run, unchanged. This wrapper only forces the listener's switch
(bigville.backends.speech_in.switched) and captures the game, so the listener's counts (heard, placed by source,
and effects) can be added to the JSON. Seeding is left at the pack's default, as in Phase 058's default arm.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys


def _load(root):
    path = os.path.join(root, "docs", "phases", "phase058", "measure_behaviour.py")
    spec = importlib.util.spec_from_file_location("measure_behaviour_058", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--switch", choices=("on", "off"), required=True)
    parser.add_argument("--turns", type=int, default=60)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    args.out = os.path.abspath(args.out)     # before the chdir into the tree below
    root = os.path.abspath(args.root)
    sys.path.insert(0, root)
    os.chdir(root)

    import bigville.api as api
    try:
        from bigville.backends import speech_in
    except ImportError:          # the baseline tree (phase changes stripped) has no listener module
        speech_in = None
    captured = []
    real_create = api.create_game

    def capture(*a, **kw):
        game = real_create(*a, **kw)
        captured.append(game)
        return game

    api.create_game = capture
    mb = _load(root)
    if speech_in is None:
        if args.switch == "on":
            raise SystemExit("this tree has no speech_in module, so the switch cannot be on")
        data = mb.run(args.turns, "default")
    else:
        with speech_in.switched(args.switch == "on"):
            data = mb.run(args.turns, "default")
    totals, per_resident = {}, {}
    for name, backend in (captured[0].backends.items() if captured else []):
        counts = speech_in.stats(backend) if speech_in is not None else {}
        if counts:
            per_resident[name] = counts
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value
    data.update({"label": args.label, "switch": args.switch, "tree": root,
                 "speech_in_totals": dict(sorted(totals.items())),
                 "speech_in_residents_with_counts": len(per_resident)})
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    print(json.dumps({k: data[k] for k in ("label", "switch", "turns", "elapsed_seconds", "utterances",
                                           "handovers", "deaths", "hunger_mean_end")}, sort_keys=True))
    print(json.dumps(data["speech_in_totals"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
