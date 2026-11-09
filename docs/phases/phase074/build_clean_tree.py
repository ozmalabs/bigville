"""Build a clean scratch tree for Phase 074 from the CURRENT HEAD plus this phase's changes.

    python3 docs/phases/phase074/build_clean_tree.py [--out DIR]

1. `git archive HEAD` is extracted into DIR (default /tmp/phase074/tree).
2. Files this phase owns outright (new files, and the two pack JSON files) are copied from the working tree.
3. Each entry of hunks.json (file, old, new) is applied to the HEAD text of a shared file. `old` must occur
   exactly once in that HEAD text, or the build stops. Shared files are edited by other sessions, so the
   working-tree copy is never copied whole.
4. For each shared file the built text is compared with the working tree and the result is printed. A
   difference is expected only where another session has changed the same file.

The scratch tree never holds copies of tests under docs/ (that breaks bare pytest collection).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile

PHASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(PHASE_DIR, "..", "..", ".."))

# Files this phase owns outright. They are copied from the working tree (none of them is shared).
WHOLE_FILES = [
    "packs/bigville/world/carrying.json",
    "packs/test_hamlet/world/carrying.json",
    "tools/balance_run.py",
    "tests/test_phase074_walking.py",
    "tests/test_phase074_balance_run.py",
]


def _head_archive(out):
    archive = subprocess.run(["git", "-C", ROOT, "archive", "HEAD"], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(out)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _read(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/tmp/phase074/tree")
    args = parser.parse_args(argv)
    out = os.path.abspath(args.out)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    _head_archive(out)

    for rel in WHOLE_FILES:
        _write(os.path.join(out, rel), _read(os.path.join(ROOT, rel)))

    with open(os.path.join(PHASE_DIR, "hunks.json"), encoding="utf-8") as handle:
        hunks = json.load(handle)
    shared = sorted({hunk["file"] for hunk in hunks})
    for rel in shared:
        path = os.path.join(out, rel)
        text = _read(path)
        for hunk in (h for h in hunks if h["file"] == rel):
            count = text.count(hunk["old"])
            if count != 1:
                sys.exit(f"anchor for {rel} occurs {count} times in HEAD text: {hunk['old'][:80]!r}")
            text = text.replace(hunk["old"], hunk["new"], 1)
        _write(path, text)
        same = text == _read(os.path.join(ROOT, rel))
        print(f"{rel}: built from HEAD + hunks; identical to working tree: {same}")
    print(f"built {out}: {len(WHOLE_FILES)} owned files, {len(hunks)} hunks in {len(shared)} shared files")


if __name__ == "__main__":
    main()
