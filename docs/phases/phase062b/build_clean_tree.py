"""Build an isolated tree for Phase 062B: `git archive HEAD` plus this phase's files, and list the hunks.

    python3 docs/phases/phase062b/build_clean_tree.py --out /tmp/t062b
    python3 docs/phases/phase062b/build_clean_tree.py --list

The shared working tree holds other sessions' uncommitted edits, so measuring it would mix their work into this phase.
Every file this phase touches was clean in the working tree when the phase began (its `git status` was empty), so each
one is copied whole from the working tree over the HEAD archive. `--list` prints, for each file, the hunks that differ
from HEAD, each with its anchor (the nearest line of code above the change), so a reviewer can check the diff against
the report. Run `--list` on a tree whose HEAD still matches this phase's base (fa47c57 or later, see the report).
"""
from __future__ import annotations

import argparse
import difflib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

FILES = [
    "domains/perceiver.py",
    "domains/perception_check.py",
    "packs/bigville/world/perception.json",
    "packs/test_hamlet/world/perception.json",
    "tests/test_phase062b_perceiver_marks.py",
]


def _head_bytes(rel):
    """The HEAD bytes of a file, or None when HEAD does not have it."""
    proc = subprocess.run(["git", "-C", ROOT, "show", f"HEAD:{rel}"], capture_output=True)
    return proc.stdout if proc.returncode == 0 else None


def build(out):
    if os.path.exists(out):
        raise SystemExit(f"{out} exists; remove it first")
    os.makedirs(out)
    archive = subprocess.run(["git", "-C", ROOT, "archive", "HEAD"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", out], input=archive, check=True)
    for rel in FILES:
        dest = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, rel), dest)
    print(f"built {out} from HEAD with {len(FILES)} files copied from this phase")
    return 0


def list_hunks():
    for rel in FILES:
        head = _head_bytes(rel)
        mine = open(os.path.join(ROOT, rel), "rb").read()
        if head is None:
            print(f"{rel}: new file, {len(mine.splitlines())} lines")
            continue
        a = head.decode("utf-8").splitlines(keepends=True)
        b = mine.decode("utf-8").splitlines(keepends=True)
        matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        hunks = [op for op in matcher.get_opcodes() if op[0] != "equal"]
        print(f"{rel}: {len(hunks)} hunks")
        for tag, i1, i2, j1, j2 in hunks:
            anchor = next((a[k].rstrip() for k in range(i1 - 1, -1, -1) if a[k].strip()), "<start of file>")
            print(f"  {tag} HEAD lines {i1 + 1}-{i2} -> {j1 + 1}-{j2}; anchor after: {anchor[:100]!r}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--out", help="directory to build the clean tree in (must not exist)")
    group.add_argument("--list", action="store_true", help="list this phase's hunks by file and anchor")
    args = parser.parse_args(argv)
    if args.list:
        return list_hunks()
    return build(os.path.abspath(args.out))


if __name__ == "__main__":
    sys.exit(main())
