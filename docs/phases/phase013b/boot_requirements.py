"""Which hamlet tables must have content for a world to boot (Phase 013b, the "minimum pack" contract).

Every bound table name must be present in a pack (the loader refuses a pack without it). This script
asks the narrower question: for each table that holds content in packs/test_hamlet, does a world still
boot if that table is emptied (an empty list or dict of the same JSON shape, types kept)?

For each variant it copies the hamlet into a temporary pack, empties one table, and runs
BigvilleWorld(data_pack=...) followed by one baker's recipe. Scalars cannot be emptied and are listed
as such. Run from the repository root: `python3 docs/phases/phase013b/boot_requirements.py`.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import traceback

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

HAMLET = os.path.join(ROOT, "packs", "test_hamlet")


def _table_locations(pack_dir):
    manifest = json.load(open(os.path.join(pack_dir, "pack.json"), encoding="utf-8"))
    return [(t["name"], t["file"]) for t in manifest["tables"]]


def _boot_with_empty(name, file_rel):
    """Copy the hamlet, empty `name`, boot a world on it, and run one baker recipe."""
    from worlds.bigville_world import BigvilleWorld
    tmp = tempfile.mkdtemp(prefix="hamlet_minus_")
    try:
        dst = os.path.join(tmp, "pack")
        shutil.copytree(HAMLET, dst)
        path = os.path.join(dst, file_rel)
        body = json.load(open(path, encoding="utf-8"))
        value = body["tables"][name]
        if not value and not isinstance(value, (int, float, str, bool)):
            return "already empty"
        if isinstance(value, dict):
            body["tables"][name] = {}
        elif isinstance(value, list):
            body["tables"][name] = []
        else:
            return "scalar (not emptied)"
        json.dump(body, open(path, "w", encoding="utf-8"), indent=2)
        try:
            w = BigvilleWorld(data_pack=dst)
            w.add_actor("Ann", role="baker", skill=0.9)
            w.set_stock("grain", 2)
            w.set_stock("water", 2)
            ok = w.do("Ann", "mill_flour")
            return "boots; mill_flour ran" if ok else "boots; mill_flour refused"
        except Exception as exc:   # report, do not stop the sweep
            last = traceback.format_exc().strip().splitlines()[-1]
            return f"FAILS: {type(exc).__name__}: {last[:140]}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    rows = []
    for name, rel in _table_locations(HAMLET):
        result = _boot_with_empty(name, rel)
        rows.append((name, rel, result))
    for name, rel, result in rows:
        print(f"{name:<28} {rel:<34} {result}")
    failing = [name for name, _, r in rows if r.startswith("FAILS")]
    print()
    print(f"tables checked: {len(rows)}; boot needs content in: {len(failing)}")
    print("  " + ", ".join(failing) if failing else "  none")


if __name__ == "__main__":
    main()
