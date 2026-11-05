"""Snapshot the entity tables, type-faithfully, for the phase 013a equality check.

Run from the repository root:  python3 docs/phases/phase013a/snapshot_tables.py [out.json]

Captures every public, non-callable, upper-case attribute of `domains.bigville_entities` (E) and of
the three domain modules, plus the private tables that other code reads (_CEREAL, _PERISHABLE_RAW,
_SKILL_CLUSTER, _PSEUDO). Values are encoded so that JSON can hold their exact Python types:

  list                  -> JSON list
  tuple                 -> {"__tuple__": [...]}
  set / frozenset       -> {"__set__": [...]} / {"__frozenset__": [...]}  (members sorted by encoding)
  dict, all keys str    -> JSON object (key order kept)
  dict, other keys      -> {"__dict__": [[key, value], ...]}  (key order kept)
  str, int, float, bool, None -> JSON scalars (int and float stay distinct)

Tests compare `json.dumps(encode(live), ensure_ascii=False)` with the file's canonical dump, so a
change of type, value, or key order fails.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)


def encode(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, tuple):
        return {"__tuple__": [encode(v) for v in value]}
    if isinstance(value, (set, frozenset)):
        tag = "__frozenset__" if isinstance(value, frozenset) else "__set__"
        members = [encode(v) for v in value]
        return {tag: sorted(members, key=lambda m: json.dumps(m, ensure_ascii=False))}
    if isinstance(value, dict):
        if all(isinstance(k, str) for k in value):
            return {k: encode(v) for k, v in value.items()}
        return {"__dict__": [[encode(k), encode(v)] for k, v in value.items()]}
    raise TypeError(f"cannot snapshot {type(value).__name__}: {value!r}")


def public_tables(module):
    out = {}
    for name in dir(module):
        if name.startswith("_") or not name.isupper():
            continue
        value = getattr(module, name)
        if callable(value):
            continue
        out[name] = encode(value)
    return out


def snapshot():
    from domains import bigville_entities as E
    from domains import population, shared_frames, world_affordances

    private = {}
    for name in ("_CEREAL", "_PERISHABLE_RAW", "_SKILL_CLUSTER", "_PSEUDO"):
        for mod in (world_affordances, shared_frames, population, E):
            if hasattr(mod, name):
                private[name] = encode(getattr(mod, name))
                break
    return {
        "E": public_tables(E),
        "world_affordances": public_tables(world_affordances),
        "shared_frames": public_tables(shared_frames),
        "population": public_tables(population),
        "private": private,
    }


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "before_tables.json")
    data = snapshot()
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    counts = {k: len(v) for k, v in data.items()}
    print("wrote", out, counts)
