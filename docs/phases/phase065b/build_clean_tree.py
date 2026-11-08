"""Build an isolated tree for Phase 065b from `git archive HEAD`, the current commit.

    python3 docs/phases/phase065b/build_clean_tree.py --out /tmp/t065b            # HEAD + 065b
    python3 docs/phases/phase065b/build_clean_tree.py --out /tmp/h065b --stage head   # HEAD, untouched

The working tree is shared, so its other edits are not used. Whole files this phase owns are copied from their working-tree
paths (NEW_FILES). Shared files are changed only by the anchored (old, new) hunks in hunks.json, applied to the HEAD text.
Each hunk's `old` lines must occur exactly once in the HEAD file, or the build stops. Nothing is written into the working
tree, and nothing is written under docs/ except the report.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
HERE = os.path.dirname(os.path.abspath(__file__))

# Whole files this phase owns (copied from the working tree).
NEW_FILES = [
    "domains/impairment.py",
    "domains/impairment_check.py",
    "packs/bigville/world/impairment.json",
    "packs/test_hamlet/world/impairment.json",
    "tests/test_phase065b_impairment.py",
]


def _head_file(rel):
    return subprocess.run(["git", "-C", ROOT, "show", f"HEAD:{rel}"], check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout


def _patch(text, old, new, rel, why):
    found = text.count(old)
    if found != 1:
        raise SystemExit(f"{rel}: anchor found {found} times, expected 1 ({why}):\n{old[:300]!r}")
    return text.replace(old, new)


def _lines(items):
    return "".join(line + "\n" for line in items)


def load_hunks():
    with open(os.path.join(HERE, "hunks.json"), encoding="utf-8") as handle:
        return json.load(handle)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--stage", choices=("head", "065b"), default="065b")
    args = parser.parse_args(argv)
    out = os.path.abspath(args.out)
    if os.path.exists(out):
        raise SystemExit(f"{out} exists; remove it first")
    os.makedirs(out)
    archive = subprocess.run(["git", "-C", ROOT, "archive", "HEAD"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", out], input=archive, check=True)
    if args.stage == "head":
        print(f"built {out}: HEAD, untouched")
        return 0

    for rel in NEW_FILES:
        src = os.path.join(ROOT, rel)
        if not os.path.exists(src):
            raise SystemExit(f"file missing in the working tree: {rel}")
        dest = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)

    texts = {}
    hunks = load_hunks()
    for hunk in hunks:
        rel = hunk["file"]
        if rel not in texts:
            texts[rel] = _head_file(rel)
        texts[rel] = _patch(texts[rel], _lines(hunk["old"]), _lines(hunk["new"]), rel, hunk["why"])
    for rel, text in texts.items():
        dest = os.path.join(out, rel)
        with open(dest, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"built {out}: HEAD plus 065b ({len(NEW_FILES)} whole files, {len(hunks)} hunks in {len(texts)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
