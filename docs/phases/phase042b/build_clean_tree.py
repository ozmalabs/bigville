"""build_clean_tree.py -- build a clean scratch tree for Phase 042b: `git archive HEAD` plus this phase's files.

    python3 docs/phases/phase042b/build_clean_tree.py --out /tmp/p42b/clean

Reads docs/phases/phase042b/hunks.json, the single source of truth:
* every 'copy' entry copies a file from its working-tree path over the HEAD archive;
* every 'anchored' entry replaces one exact block of HEAD text with its 'new' text. The block must occur exactly
  once in the HEAD file, which the builder asserts before it writes.

Nothing is written under the working tree. The output directory must not exist, or must be empty. Each copied
file's change against HEAD is printed (lines added and removed), so the supervisor can read what the tree receives.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
HUNKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hunks.json")


def head_text(path):
    """The file's text at HEAD (git show), or None when HEAD does not have it."""
    proc = subprocess.run(["git", "-C", REPO, "show", f"HEAD:{path}"], capture_output=True)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8")


def head_sha():
    return subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


def delta(old, new):
    added = removed = 0
    for line in difflib.unified_diff((old or "").splitlines(), new.splitlines(), lineterm="", n=0):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def build(out):
    if os.path.exists(out) and os.listdir(out):
        raise SystemExit(f"{out} exists and is not empty; choose a new directory")
    os.makedirs(out, exist_ok=True)
    archive = subprocess.run(["git", "-C", REPO, "archive", "HEAD"], capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", out], input=archive.stdout, check=True)
    with open(HUNKS, encoding="utf-8") as fh:
        spec = json.load(fh)
    print(f"HEAD {head_sha()} archived into {out}")
    for entry in spec["copy"]:
        path = entry["path"]
        source = os.path.join(REPO, path)
        if not os.path.isfile(source):
            raise SystemExit(f"copy source missing: {path}")
        base = head_text(path)
        if entry["status"] == "replace" and base is None:
            raise SystemExit(f"{path} is marked replace but HEAD does not have it")
        if entry["status"] == "new" and base is not None:
            raise SystemExit(f"{path} is marked new but HEAD already has it")
        with open(source, encoding="utf-8") as fh:
            text = fh.read()
        target = os.path.join(out, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(text)
        added, removed = delta(base, text)
        print(f"copy   {path:44s} {entry['status']:8s} +{added} -{removed} vs HEAD")
    for entry in spec["anchored"]:
        path = entry["path"]
        base = head_text(path)
        if base is None:
            raise SystemExit(f"anchored file missing at HEAD: {path}")
        count = base.count(entry["old"])
        if count != 1:
            raise SystemExit(f"anchor for {path} occurs {count} times at HEAD (expected once): {entry['anchor']}")
        text = base.replace(entry["old"], entry["new"], 1)
        target = os.path.join(out, path)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(text)
        added, removed = delta(base, text)
        print(f"hunk   {path:44s} anchored +{added} -{removed}: {entry['anchor']}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    return build(os.path.abspath(args.out))


if __name__ == "__main__":
    sys.exit(main())
