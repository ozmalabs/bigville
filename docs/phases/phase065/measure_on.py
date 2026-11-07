"""Phase 065 check: the Phase 058 behaviour run with PERCEPTION and IMPAIRMENT forced on, for a tree.

    PYTHONHASHSEED=0 python3 docs/phases/phase065/measure_on.py --tree /tmp/t065 --label t065_on60 --turns 60 \
        --out /tmp/beh_t065_on60.json

The simple backend reads its own context and never the agent view, so this run is expected to equal HEAD's run. The
switches are set on the cached pack tables before the run, and the tree's own measure_behaviour.py does the work.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--turns", type=int, default=60)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    tree = os.path.abspath(args.tree)
    sys.path.insert(0, tree)
    from domains.pack import load_pack
    for name in ("PERCEPTION", "IMPAIRMENT"):
        load_pack("bigville")[name]["enabled"] = True
    path = os.path.join(tree, "docs", "phases", "phase058", "measure_behaviour.py")
    spec = importlib.util.spec_from_file_location("measure058", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main(["--label", args.label, "--turns", str(args.turns), "--out", args.out])


if __name__ == "__main__":
    sys.exit(main())
