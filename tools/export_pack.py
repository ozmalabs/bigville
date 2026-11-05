"""export_pack.py -- write a data pack's base files in the form an author writes them.

    python3 tools/export_pack.py [--pack bigville] [--out DIR]

Two modes, chosen by whether packs/<pack>/pack.json exists:

* Bootstrap (no manifest yet): take today's tables from the domain modules, write BASE data
  (every derived entry removed), and copy each table's explanatory comments into the file's
  `_doc`. This ran once, against the modules as they were before packs existed.
* Normalise (manifest exists): read the pack's base files, compile them with domains/pack.py,
  strip the derived entries again, check the result compiles back to the same tables, and rewrite
  the files. A rerun on unchanged files writes identical bytes.

Derived entries removed on export: `*_scraps` items and their SCARCITY prices, the fuel input and
`preparation` on heated recipes (their `method_tools` go back to `tools`), `seed_return` equal to
the default, the origin/immutable/enforcement defaults on local bundles, and POLICIES, LAWS, and
_SKILL_CLUSTER (never stored).
"""
from __future__ import annotations

import ast
import copy
import io
import json
import os
import shutil
import sys
import tokenize

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from domains import pack as P  # noqa: E402

MODULE_FILES = {
    "world_affordances": os.path.join(ROOT, "domains", "world_affordances.py"),
    "shared_frames": os.path.join(ROOT, "domains", "shared_frames.py"),
    "population": os.path.join(ROOT, "domains", "population.py"),
    "bigville_entities": os.path.join(ROOT, "domains", "bigville_entities.py"),
}
# Module whose top-level tables belong to each group. Only the listed names are moved out of
# bigville_entities; everything else there (the self-test, and the _PSEUDO helper) stays.
GROUP_OF_MODULE = {"world_affordances": "world", "shared_frames": "frames", "population": "population"}
MOVED_FROM_ENTITIES = {"ANIMAL_SERVICES": "world"}
# Tables whose names are derived by the compiler; they are never stored, and their comments
# attach to the table they are computed from.
DERIVED_SOURCE = {"POLICIES": "LOCAL_POLICIES", "LAWS": "LOCAL_LAWS", "_SKILL_CLUSTER": "SKILL_CLUSTERS"}
# Non-scalar parameter groups that live in the group's constants file with the scalars.
CONSTANT_TABLES = {"NITROGEN", "TRANSFER", "PRACTICE", "APTITUDE_PRACTICE"}
PACK_DESCRIPTION = ("Bigville founding world. Base data only: domains/pack.py adds the derived "
                    "entries (scrap items, fuel slots, default seed return, bundle origins, and the "
                    "POLICIES, LAWS, and _SKILL_CLUSTER indexes).")


# ---------------------------------------------------------------- source comments

def _derive_target(node):
    body = ast.unparse(node)
    if "SCARCITY" in body:
        return "SCARCITY"
    if "HEATED_FOOD_RECIPES" in body or "method_tools" in body:
        return "RECIPES"
    if "seed_return" in body:
        return "CROPS"
    if "leaves_scraps" in body:
        return "ITEMS"
    if "origin" in body:
        return "LOCAL_POLICIES"
    raise ValueError(f"unrecognised derivation at line {node.lineno}")


def source_chunks(path):
    """Top-level statements of a module, each with the comment lines that belong to it.

    A comment line belongs to the next top-level statement after it (so a comment block above a
    table describes that table). Kinds: assign, update (`X.update(...)`), derive (a for loop that
    builds a table), or other (imports, docstrings, defs, if-blocks)."""
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    comments = {}
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            text = tok.string[1:]
            comments[tok.start[0]] = (text[1:] if text.startswith(" ") else text).rstrip()
    chunks, prev_end = [], 0
    for node in tree.body:
        start, end = node.lineno, node.end_lineno
        gap = [ln for ln in range(prev_end + 1, start) if ln in comments]
        inner = sorted(ln for ln in comments if start <= ln <= end)
        kind, names = "other", []
        if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets):
            kind, names = "assign", [t.id for t in node.targets]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            kind, names = "assign", [node.target.id]
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "update"
              and isinstance(node.value.func.value, ast.Name)):
            kind, names = "update", [node.value.func.value.id]
        elif isinstance(node, ast.For):
            kind, names = "derive", [_derive_target(node)]
        chunks.append({"kind": kind, "names": names, "start": start, "end": end,
                       "gap": gap, "lines": gap + inner, "doc": [comments[ln] for ln in gap + inner]})
        prev_end = end
    return chunks


def _doc_text(lines):
    return "\n".join(lines).strip("\n")


# ---------------------------------------------------------------- legacy model (bootstrap)

def legacy_model():
    """Tables, grouping, and comments from the domain modules as they are in the working tree."""
    import importlib
    modules = {name: importlib.import_module(f"domains.{name}") for name in MODULE_FILES}
    tables, order, group_of, docs = {}, [], {}, {}
    for mod_name in ("world_affordances", "shared_frames", "population", "bigville_entities"):
        module = modules[mod_name]
        for ch in source_chunks(MODULE_FILES[mod_name]):
            if ch["kind"] == "assign":
                for name in ch["names"]:
                    if name in DERIVED_SOURCE:
                        docs.setdefault(DERIVED_SOURCE[name], []).extend(ch["doc"])
                        continue
                    if mod_name == "bigville_entities" and name not in MOVED_FROM_ENTITIES:
                        continue
                    group = MOVED_FROM_ENTITIES.get(name) or GROUP_OF_MODULE[mod_name]
                    tables[name] = getattr(module, name)
                    group_of[name] = group
                    order.append(name)
                    docs.setdefault(name, []).extend(ch["doc"])
            elif ch["kind"] in ("update", "derive"):
                if mod_name == "bigville_entities":
                    continue
                target = ch["names"][0]
                docs.setdefault(target, []).extend(ch["doc"])
    for name in list(DERIVED_SOURCE):
        tables[name] = getattr(modules[_module_of(name)], name)
    return tables, order, group_of, {k: _doc_text(v) for k, v in docs.items()}


def _module_of(name):
    return "bigville_entities" if name in MOVED_FROM_ENTITIES else "shared_frames" if name in (
        "POLICIES", "LAWS", "_SKILL_CLUSTER") else "world_affordances"


def _is_constant(name, value):
    return P._is_scalar(value) or name in CONSTANT_TABLES


# ---------------------------------------------------------------- uncompile and verify

def uncompile(tables):
    """Remove the compiler's derived entries from compiled tables. Returns base data (a new dict)."""
    base = copy.deepcopy({k: v for k, v in tables.items() if k not in P.DERIVED_NAMES})
    for kind in [k for k, s in base["ITEMS"].items() if "scraps_of" in s]:
        del base["ITEMS"][kind]
    factor = base["SCRAP_SCARCITY_FACTOR"]
    for kind, spec in tables["ITEMS"].items():
        src = spec.get("scraps_of")
        if src and kind in base["SCARCITY"]:
            if base["SCARCITY"][kind] == round(tables["SCARCITY"].get(src, 1.0) * factor, 4):
                del base["SCARCITY"][kind]
    heated = base["HEATED_FOOD_RECIPES"]
    for recipe in base["RECIPES"]:
        recipe.pop("preparation", None)
        if "method_tools" in recipe:
            recipe["tools"] = recipe.pop("method_tools")
        if recipe["name"] in heated and recipe["in"]:
            kind, qty = recipe["in"][-1]
            if kind == "fuel" and qty == base["FUEL_PER_BATCH"].get(recipe["name"], 1):
                recipe["in"] = recipe["in"][:-1]
    for spec in base["CROPS"].values():
        if spec.get("seed_return") == P.DEFAULT_SEED_RETURN:
            del spec["seed_return"]
    for bundle in base["LOCAL_POLICIES"] + base["LOCAL_LAWS"]:
        for key, default in P.BUNDLE_DEFAULTS:
            if key in bundle and bundle[key] == default and type(bundle[key]) is type(default):
                del bundle[key]
    return base


def verify_round_trip(base, tables):
    """compile(uncompile(T)) must equal T for every name, including types and order."""
    recompiled = P.compile_tables(copy.deepcopy(base))
    bad = [n for n in tables if n not in recompiled or P.canonical(recompiled[n]) != P.canonical(tables[n])]
    if bad:
        raise SystemExit(f"round trip differs for: {', '.join(sorted(bad))}")
    extra = [n for n in recompiled if n not in tables]
    if extra:
        raise SystemExit(f"round trip produces unexpected names: {', '.join(sorted(extra))}")


# ---------------------------------------------------------------- writing

def write_pack_files(out_dir, entries, base, file_docs):
    """Write one JSON file per manifest file. `entries` is [(name, rel)] in manifest order."""
    by_file = {}
    for name, rel in entries:
        by_file.setdefault(rel, []).append(name)
    for rel, names in by_file.items():
        tables_json, types = {}, {}
        for name in names:
            tt = {}
            tables_json[name] = P.to_json(base[name], tt)
            if tt:
                types[name] = tt
        data = {"_doc": file_docs.get(rel, ""), "_types": types, "tables": tables_json}
        path = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _write_manifest(out_dir, name, entries):
    manifest = {"format": P.FORMAT_VERSION, "name": name, "version": 1,
                "description": PACK_DESCRIPTION, "extends": None,
                "tables": [{"name": n, "file": rel} for n, rel in entries]}
    with open(os.path.join(out_dir, "pack.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def bootstrap(pack_name, out_dir):
    tables, order, group_of, docs = legacy_model()
    entries, file_docs, seen_files = [], {}, {}
    for name in order:
        value = tables[name]
        if _is_constant(name, value):
            rel = f"{group_of[name]}/constants.json"
            text = f"{name}: {docs[name]}" if docs.get(name) else name
            file_docs[rel] = "\n\n".join(filter(None, [file_docs.get(rel, ""), text]))
        else:
            rel = f"{group_of[name]}/{name.lower()}.json"
            file_docs[rel] = docs.get(name, "")
        entries.append((name, rel))
        seen_files[rel] = True
    base = uncompile(tables)
    verify_round_trip(base, tables)
    os.makedirs(out_dir, exist_ok=True)
    _write_manifest(out_dir, pack_name, entries)
    write_pack_files(out_dir, entries, base, file_docs)
    return len(entries), len(seen_files)


def normalise(pack_name, pack_dir, out_dir):
    manifest, _, raw, _ = P.read_base(pack_dir)
    if manifest.get("extends"):
        raise SystemExit("export_pack normalises base packs only; this pack extends another")
    tables = P.compile_tables(copy.deepcopy(raw))
    base = uncompile(tables)
    verify_round_trip(base, tables)
    entries = [(t["name"], t["file"]) for t in manifest["tables"]]
    file_docs = {}
    for _, rel in entries:
        if rel not in file_docs:
            with open(os.path.join(pack_dir, rel), encoding="utf-8") as fh:
                file_docs[rel] = json.load(fh).get("_doc", "")
    if os.path.abspath(out_dir) != os.path.abspath(pack_dir):
        os.makedirs(out_dir, exist_ok=True)
        shutil.copyfile(os.path.join(pack_dir, "pack.json"), os.path.join(out_dir, "pack.json"))
    write_pack_files(out_dir, entries, base, file_docs)
    return len(entries)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--pack", default="bigville")
    parser.add_argument("--out", default=None, help="output directory (default: packs/<pack>)")
    parser.add_argument("--bootstrap", action="store_true",
                        help="one-time: build a pack from legacy domain modules (needs their comments)")
    args = parser.parse_args(argv)
    pack_dir = P.resolve_pack_dir(args.pack)
    out_dir = args.out or pack_dir
    if os.path.exists(os.path.join(pack_dir, "pack.json")):
        count = normalise(args.pack, pack_dir, out_dir)
        print(f"normalised {count} tables into {out_dir}")
    elif not args.bootstrap:
        raise SystemExit(f"no pack.json in {pack_dir}; pass --bootstrap to build one from the legacy modules")
    else:
        count, files = bootstrap(args.pack, out_dir)
        print(f"bootstrapped {count} tables into {files} files under {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
