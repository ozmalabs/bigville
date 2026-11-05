"""generate_seeds.py -- write the Ocelot seed files a data pack produces.

    python3 tools/generate_seeds.py                        # bigville -> bigville/seeds/
    python3 tools/generate_seeds.py --check                # exit 1 if those files are stale
    python3 tools/generate_seeds.py --pack test_hamlet --out /tmp/hamlet_seeds
    python3 tools/generate_seeds.py --pack packs/my_child --out /tmp/child_seeds

The output is deterministic: a rerun on an unchanged pack writes identical bytes. A pack other than
bigville needs --out, so a test or child pack never overwrites the canonical seeds. Hand-written seeds
in the output directory are never overwritten; a generated file the pack no longer makes is removed.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from domains import generated_seeds as G  # noqa: E402
from domains.data_view import DEFAULT_PACK  # noqa: E402
from domains.pack import PackError, load_pack  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 tools/generate_seeds.py", description=__doc__.split("\n")[0])
    parser.add_argument("--pack", default=DEFAULT_PACK, help="pack name under packs/, or a directory")
    parser.add_argument("--out", default=None,
                        help=f"output directory (default for {DEFAULT_PACK}: {G.CANONICAL_SEED_DIR})")
    parser.add_argument("--check", action="store_true", help="report stale, missing, or orphaned seeds; write nothing")
    args = parser.parse_args(argv)
    try:
        pack = load_pack(args.pack)
    except PackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out = args.out
    if out is None:
        if pack.name != G.CANONICAL_PACK:
            print(f"error: pack '{pack.name}' needs --out (only '{G.CANONICAL_PACK}' writes to the canonical "
                  "directory)", file=sys.stderr)
            return 2
        out = G.CANONICAL_SEED_DIR
    if args.check:
        problems = G.check_seeds(pack, out)
        for problem in problems:
            print(f"stale: {problem}")
        if problems:
            print(f"{len(problems)} problem(s) in {out}; run python3 tools/generate_seeds.py")
            return 1
        print(f"generated seeds in {out} match pack '{pack.name}' ({len(G.expected_files(pack))} files)")
        return 0
    try:
        written = G.write_seeds(pack, out)
    except PackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {len(written)} generated seed files for pack '{pack.name}' to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
