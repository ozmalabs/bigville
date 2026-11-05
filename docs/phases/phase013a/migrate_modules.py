"""One-time migration: domain modules read their tables from packs/bigville instead of defining them.

Run once, from the repository root, after tools/export_pack.py has bootstrapped packs/bigville from
the committed modules:  python3 docs/phases/phase013a/migrate_modules.py

For each module it deletes every top-level data statement (assignments, `X.update(...)`, and the
for-loops that derived entries) together with the comment lines that belong to them, then inserts
a `_PACK = _load_pack("bigville")` block with one binding per table in the module's group. Every
deleted comment line must already appear in a pack file's `_doc`; the script stops otherwise.
Functions and other code are left as they are.
"""
from __future__ import annotations

import ast
import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from tools.export_pack import MODULE_FILES, source_chunks, MOVED_FROM_ENTITIES  # noqa: E402
from domains.pack import DERIVED_NAMES  # noqa: E402

PACK_DIR = os.path.join(ROOT, "packs", "bigville")
GROUP_OF = {"world_affordances": "world", "shared_frames": "frames", "population": "population"}
KEEP_IN_ENTITIES = {"_PSEUDO"}          # self-test helper; not part of the pack


def pack_names_by_group():
    with open(os.path.join(PACK_DIR, "pack.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    groups = {}
    for entry in manifest["tables"]:
        groups.setdefault(entry["file"].split("/")[0], []).append(entry["name"])
    return groups


def pack_doc_text():
    parts = []
    for path in glob.glob(os.path.join(PACK_DIR, "*", "*.json")):
        with open(path, encoding="utf-8") as fh:
            parts.append(json.load(fh).get("_doc", ""))
    return "\n".join(parts)


def _norm(text):
    return re.sub(r"\s+", " ", text).strip()


def migrate(module):
    path = MODULE_FILES[module]
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if "_load_pack" in text or "from domains.pack" in text:
        raise SystemExit(f"{module} already migrated; refusing to run twice")
    lines = text.split("\n")
    chunks = source_chunks(path)
    delete, removed_comments = set(), []
    for ch in chunks:
        if ch["kind"] not in ("assign", "update", "derive"):
            continue
        if module == "bigville_entities":
            if ch["kind"] != "assign" or ch["names"][0] in KEEP_IN_ENTITIES:
                continue
            if ch["names"][0] not in MOVED_FROM_ENTITIES:
                continue
        delete.update(ch["gap"])
        delete.update(range(ch["start"], ch["end"] + 1))
        removed_comments.extend(ch["doc"])
    # the comments must survive in the pack
    docs = _norm(pack_doc_text())
    missing = [c for c in removed_comments if c.strip() and _norm(c) not in docs]
    if missing:
        raise SystemExit(f"{module}: comments not found in pack docs, e.g. {missing[:3]!r}")

    bindings = []
    if module != "bigville_entities":
        group = GROUP_OF[module]
        names = list(pack_names_by_group().get(group, []))
        if module == "shared_frames":
            names += list(DERIVED_NAMES)
        bindings = ["from domains.pack import load_pack as _load_pack", "",
                    '# Tables and constants below are read from the "bigville" data pack (packs/bigville/).',
                    "# Their explanatory comments are in the pack files as \"_doc\"; domains/pack.py",
                    "# compiles the derived entries. Functions in this module read these names unchanged.",
                    '_PACK = _load_pack("bigville")']
        bindings += [f'{n} = _PACK["{n}"]' for n in names]
        bindings.append("")

    tree = ast.parse(text)
    last_import = max((n.end_lineno for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))), default=0)
    out = []
    for i, line in enumerate(lines, start=1):
        if i not in delete:
            out.append(line)
        if bindings and i == last_import:
            out.append("")
            out.extend(bindings)
    new = "\n".join(out)
    new = re.sub(r"\n{4,}", "\n\n\n", new)
    compile(new, path, "exec")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new)
    # every top-level assignment left must be a helper that stays in the module
    left = []
    for n in ast.parse(new).body:
        if not isinstance(n, (ast.Assign, ast.AnnAssign)):
            continue
        value = n.value
        if isinstance(value, ast.Subscript) and ast.unparse(value.value) == "_PACK":
            continue                                   # a binding from the pack
        if ast.unparse(value).startswith("_load_pack("):
            continue
        for t in ([n.target] if isinstance(n, ast.AnnAssign) else n.targets):
            if isinstance(t, ast.Name):
                left.append(t.id)
    stray = [n for n in left if not (module == "bigville_entities" and n in KEEP_IN_ENTITIES)]
    if stray:
        raise SystemExit(f"{module}: data left in the module: {stray}")
    return len(removed_comments), len(bindings)


if __name__ == "__main__":
    for mod in ("world_affordances", "shared_frames", "population", "bigville_entities"):
        comments, bound = migrate(mod)
        print(f"{mod}: removed {comments} comment blocks; inserted {bound} binding lines")
