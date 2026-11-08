#!/usr/bin/env python3
"""Build HEAD plus Phase 044 in a clean directory.

    python3 docs/phases/phase044/build_clean_tree.py --dest /tmp/p044 [--base HEAD] [--repo /path/to/bigville]

1. Exports `git archive <base>` (default HEAD, resolved to a commit hash and printed) into --dest. The destination
   must not exist or must be empty.
2. Copies the new files from docs/phases/phase044/files/ into their paths. A path that already exists in the base
   stops the build.
3. Applies the anchored hunks in docs/phases/phase044/hunks.json to the base text of each shared file. Every hunk's
   `old` text must occur exactly once in the file as it stands at that point, or the build stops.

The result is <base> plus Phase 044 and nothing else. Other sessions' uncommitted work is not used.
hunks.json is anchored on f49a2f8; hunks_9074cc3.json is the earlier version, kept for history only.

The functions `export_commit`, `copy_new_files` and `apply_hunks` are reused by the Phase 045 builder.
"""
from __future__ import annotations

import argparse
import io
import json
import pathlib
import subprocess
import sys
import tarfile


HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
HUNKS = HERE / "hunks.json"
FILES = HERE / "files"


def resolve_commit(repo: pathlib.Path, base: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", f"{base}^{{commit}}"],
                         check=True, capture_output=True, text=True)
    return out.stdout.strip()


def export_commit(repo: pathlib.Path, commit: str, dest: pathlib.Path) -> None:
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"destination {dest} exists and is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    data = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", commit],
                          check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:
            tar.extractall(dest)


def copy_new_files(dest: pathlib.Path, files_root: pathlib.Path = FILES) -> list[str]:
    copied = []
    for source in sorted(files_root.rglob("*")):
        if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
            continue
        rel = source.relative_to(files_root)
        target = dest / rel
        if target.exists():
            raise SystemExit(f"new file {rel.as_posix()} already exists in the base; the anchor set is stale")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        copied.append(rel.as_posix())
    return copied


def apply_hunks(dest: pathlib.Path, hunks_path: pathlib.Path = HUNKS) -> int:
    hunks = json.loads(hunks_path.read_text(encoding="utf-8"))
    texts: dict[str, str] = {}
    for hunk in hunks:
        rel = hunk["file"]
        if rel not in texts:
            texts[rel] = (dest / rel).read_text(encoding="utf-8")
        count = texts[rel].count(hunk["old"])
        if count != 1:
            raise SystemExit(f"anchor for {hunk['note']!r} in {rel} occurs {count} times; expected 1")
        texts[rel] = texts[rel].replace(hunk["old"], hunk["new"], 1)
    for rel, text in texts.items():
        (dest / rel).write_text(text, encoding="utf-8")
    return len(hunks)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", required=True, type=pathlib.Path)
    parser.add_argument("--base", default="HEAD", help="the commit to export (default HEAD)")
    parser.add_argument("--repo", type=pathlib.Path, default=REPO)
    args = parser.parse_args(argv)
    commit = resolve_commit(args.repo, args.base)
    export_commit(args.repo, commit, args.dest)
    copied = copy_new_files(args.dest)
    applied = apply_hunks(args.dest)
    print(f"built {args.dest}: base {args.base} = {commit}; 044 new files {len(copied)}; 044 hunks {applied}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
