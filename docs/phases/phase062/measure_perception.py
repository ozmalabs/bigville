"""Phase 062 measurement: the Phase 058 simple-backend run with PERCEPTION.enabled forced on or off.

    PYTHONHASHSEED=0 python3 docs/phases/phase062/measure_perception.py --root <tree> --switch on --turns 60 \
        --label t2_on60 --out <json>

`--root` is a repository tree (use build_clean_tree.py's output, so other sessions' edits are not measured). The
Phase 058 `measure_behaviour.run()` of that tree does the run, unchanged. This wrapper only sets the pack table's
switch before the run. The simple backend never reads the agent view, so the expected result is an identical run.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--switch", choices=("on", "off"), required=True)
    parser.add_argument("--turns", type=int, default=60)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    args.out = os.path.abspath(args.out)
    root = os.path.abspath(args.root)
    sys.path.insert(0, root)
    os.chdir(root)

    from domains.pack import load_pack
    load_pack("bigville")["PERCEPTION"]["enabled"] = args.switch == "on"
    path = os.path.join(root, "docs", "phases", "phase058", "measure_behaviour.py")
    spec = importlib.util.spec_from_file_location("measure_behaviour_058", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.run(args.turns, "default")
    result.update({"label": args.label, "perception_switch": args.switch})
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
    print(json.dumps({k: result[k] for k in ("label", "turns", "utterances", "deaths", "hunger_mean_end")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
