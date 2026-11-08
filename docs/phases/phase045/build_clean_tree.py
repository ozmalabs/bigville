#!/usr/bin/env python3
"""Build HEAD plus Phase 044 (and optionally plus Phase 045) in a clean directory.

    python3 docs/phases/phase045/build_clean_tree.py --dest /tmp/p044 --stage 044
    python3 docs/phases/phase045/build_clean_tree.py --dest /tmp/p045 --stage 045 [--base HEAD] [--repo PATH]

--stage 044  base + the Phase 044 files and hunks (docs/phases/phase044/).
--stage 045  base + Phase 044 + Phase 045 files and hunks (docs/phases/phase045/). This is the default.

The base defaults to HEAD, resolved to a commit hash and printed. The Phase 044 steps reuse the Phase 044 builder's
functions (export, copy, anchored hunks). Each anchor must occur exactly once in the text at its point in the chain,
or the build stops. Other sessions' uncommitted work is not used.
hunks.json is anchored on f49a2f8 + 044; hunks_9074cc3.json is the earlier version, kept for history only.
"""
from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys


HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
HUNKS = HERE / "hunks.json"
FILES = HERE / "files"
PHASE044 = HERE.parent / "phase044" / "build_clean_tree.py"


def load_phase044():
    spec = importlib.util.spec_from_file_location("phase044_build", PHASE044)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", required=True, type=pathlib.Path)
    parser.add_argument("--stage", choices=["044", "045"], default="045")
    parser.add_argument("--base", default="HEAD", help="the commit to export (default HEAD)")
    parser.add_argument("--repo", type=pathlib.Path, default=REPO)
    args = parser.parse_args(argv)

    p44 = load_phase044()
    commit = p44.resolve_commit(args.repo, args.base)
    p44.export_commit(args.repo, commit, args.dest)
    copied44 = p44.copy_new_files(args.dest)
    applied44 = p44.apply_hunks(args.dest)
    line = f"built {args.dest}: base {args.base} = {commit}; 044 new files {len(copied44)}; 044 hunks {applied44}"
    if args.stage == "045":
        copied = p44.copy_new_files(args.dest, FILES)
        applied = p44.apply_hunks(args.dest, HUNKS)
        line += f"; 045 new files {len(copied)}; 045 hunks {applied}"
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
