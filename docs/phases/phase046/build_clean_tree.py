#!/usr/bin/env python3
"""Build a clean scratch tree for Phase 046: a git commit plus this phase's files and anchored hunks.

    python3 docs/phases/phase046/build_clean_tree.py --dest /tmp/p046
    python3 docs/phases/phase046/build_clean_tree.py --dest /tmp/p046_head --head-only

The base is `git archive` of --base (default HEAD, resolved to a commit and printed), so other sessions' uncommitted
work in the shared checkout is never read. The phase's new files come from files/ (the same relative paths in the
tree). The shared-file edits are the entries of hunks.json, applied in order. Each `old` text must occur EXACTLY ONCE
in its file at its point in the chain; otherwise the build stops and nothing is written past the failing hunk.
--head-only builds the base alone (the baseline for the 60-turn comparison).
"""
from __future__ import annotations

import argparse
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
FILES = HERE / "files"
HUNKS = HERE / "hunks.json"


def resolve_commit(repo: pathlib.Path, rev: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", f"{rev}^{{commit}}"],
                         check=True, capture_output=True, text=True)
    return out.stdout.strip()


def export_commit(repo: pathlib.Path, commit: str, dest: pathlib.Path) -> None:
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"destination {dest} exists and is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "-C", str(repo), "archive", commit], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        tar.extractall(dest, filter="data")


def copy_files(dest: pathlib.Path) -> list[str]:
    copied = []
    for source in sorted(p for p in FILES.rglob("*") if p.is_file()):
        rel = source.relative_to(FILES)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied.append(rel.as_posix())
    return copied


def apply_hunks(dest: pathlib.Path) -> list[str]:
    applied = []
    for index, hunk in enumerate(json.loads(HUNKS.read_text(encoding="utf-8"))):
        target = dest / hunk["file"]
        text = target.read_text(encoding="utf-8")
        found = text.count(hunk["old"])
        if found != 1:
            raise SystemExit(f"hunk {index} ({hunk['file']}: {hunk['note']}): anchor occurs {found} times, expected 1")
        target.write_text(text.replace(hunk["old"], hunk["new"], 1), encoding="utf-8")
        applied.append(f"{index}:{hunk['file']}")
    return applied


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", required=True, type=pathlib.Path)
    parser.add_argument("--base", default="HEAD", help="the commit to export (default HEAD)")
    parser.add_argument("--repo", type=pathlib.Path, default=REPO)
    parser.add_argument("--head-only", action="store_true", help="export the base only, with no phase files or hunks")
    args = parser.parse_args(argv)

    commit = resolve_commit(args.repo, args.base)
    export_commit(args.repo, commit, args.dest)
    if args.head_only:
        print(f"built {args.dest}: base {args.base} = {commit} (head only)")
        return 0
    copied = copy_files(args.dest)
    applied = apply_hunks(args.dest)
    print(f"built {args.dest}: base {args.base} = {commit}; new files {len(copied)}; hunks {len(applied)}")
    for rel in copied:
        print(f"  new  {rel}")
    for item in applied:
        print(f"  hunk {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
