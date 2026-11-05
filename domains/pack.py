"""pack.py -- data packs: read a pack's JSON files, apply `extends`, restore types, and compile.

A pack is a directory with a `pack.json` manifest and one JSON file per table (or per group of
scalar constants):

    packs/bigville/
        pack.json                 manifest: name, version, description, extends, tables
        world/items.json          one table per file
        world/constants.json      scalars and small parameter groups, several names per file
        frames/...  population/...

Manifest `tables` lists every stored table: `{"name": "ITEMS", "file": "world/items.json"}`. A
child pack may list a table again with `"merge": true` to update its parent's dict by key; without
`merge` the child's table replaces the parent's. Tables the child does not list are inherited.

Each table file is a JSON object:

    {"_doc": "...explanatory comments carried from the source...",
     "_types": {"TABLE": {"/json/pointer": "tuple" | "set" | "frozenset" | "tuple_keys"}},
     "tables": {"TABLE": ...}}

Keys starting with `_` other than those named here are ignored by the loader. JSON cannot hold
tuples, sets, or tuple keys, so `_types` names the value (JSON pointer from the table's root) that
must be restored to that Python type. A `tuple_keys` dict is stored as a list of [key, value] pairs.

`compile_tables` adds the entries that used to be derived at import time (scrap items and their
prices, fuel slots and preparation methods on heated recipes, the seed-return default, the law and
policy origin defaults and their concatenations, and the skill-to-cluster index). It runs on the
base data, and each step is guarded so that compiling compiled data changes nothing.
"""
from __future__ import annotations

import copy
import json
import os

FORMAT_VERSION = 1
PACKS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packs"))

# Names the compiler creates. They are never stored in a pack file.
DERIVED_NAMES = ("POLICIES", "LAWS", "_SKILL_CLUSTER")

# Defaults the compiler fills into each LOCAL_POLICIES / LOCAL_LAWS bundle (setdefault).
BUNDLE_DEFAULTS = (("origin", "bigville"), ("immutable", False), ("enforcement", "bigville"))

# Seed return for a harvest that does not state one (setdefault on every CROPS entry).
DEFAULT_SEED_RETURN = 1.25


class PackError(Exception):
    """A pack is missing, malformed, or inconsistent."""


class Pack:
    """A loaded, compiled pack. `tables` holds every compiled name (stored and derived)."""

    def __init__(self, name, path, description, extends, tables, derived, base):
        self.name = name
        self.path = path
        self.description = description
        self.extends = extends
        self.tables = tables
        self.derived = frozenset(derived)
        self.base = base          # the uncompiled base data (after `extends`), for export

    def __getitem__(self, name):
        try:
            return self.tables[name]
        except KeyError:
            raise KeyError(f"pack '{self.name}' has no table '{name}'") from None

    def __contains__(self, name):
        return name in self.tables

    def names(self):
        return list(self.tables)

    def __repr__(self):
        return f"Pack({self.name!r}, {len(self.tables)} names)"


# ---------------------------------------------------------------- JSON pointers and types

def _escape(segment):
    return str(segment).replace("~", "~0").replace("/", "~1")


def _is_scalar(value):
    return value is None or isinstance(value, (bool, int, float, str))


def to_json(value, types, ptr=""):
    """Convert a Python value to JSON-ready data, recording the non-JSON types in `types`.

    `types` maps a JSON pointer (relative to the table root) to "tuple", "set", "frozenset", or
    "tuple_keys". Lists, dicts with str keys, and scalars pass through unchanged."""
    if _is_scalar(value):
        return value
    if isinstance(value, list):
        return [to_json(v, types, f"{ptr}/{i}") for i, v in enumerate(value)]
    if isinstance(value, tuple):
        types[ptr] = "tuple"
        return [to_json(v, types, f"{ptr}/{i}") for i, v in enumerate(value)]
    if isinstance(value, (set, frozenset)):
        types[ptr] = "frozenset" if isinstance(value, frozenset) else "set"
        for member in value:
            if not _is_scalar(member):
                raise PackError(f"set member at {ptr or '/'} is not a scalar: {member!r}")
        return sorted(value, key=lambda m: json.dumps(m, ensure_ascii=False))
    if isinstance(value, dict):
        if all(isinstance(k, str) for k in value):
            return {k: to_json(v, types, f"{ptr}/{_escape(k)}") for k, v in value.items()}
        if all(isinstance(k, tuple) and all(_is_scalar(x) for x in k) for k in value):
            types[ptr] = "tuple_keys"
            return [[list(k), to_json(v, types, f"{ptr}/{i}")] for i, (k, v) in enumerate(value.items())]
        raise PackError(f"dict at {ptr or '/'} has keys that are neither all str nor all tuples")
    raise PackError(f"cannot store {type(value).__name__} at {ptr or '/'}")


def from_json(value, types, ptr=""):
    """Inverse of to_json: restore tuples, sets, and tuple keys named in `types`."""
    kind = types.get(ptr)
    if kind == "tuple_keys":
        return {tuple(k): from_json(v, types, f"{ptr}/{i}") for i, (k, v) in enumerate(value)}
    if isinstance(value, list):
        items = [from_json(v, types, f"{ptr}/{i}") for i, v in enumerate(value)]
        if kind == "tuple":
            return tuple(items)
        if kind == "set":
            return set(items)
        if kind == "frozenset":
            return frozenset(items)
        return items
    if isinstance(value, dict):
        return {k: from_json(v, types, f"{ptr}/{_escape(k)}") for k, v in value.items()}
    return value


def canonical(value):
    """A type-tagged, order-preserving JSON string: equal strings mean equal values, types, and order."""
    return json.dumps(_tagged(value), ensure_ascii=False)


def _tagged(value):
    if _is_scalar(value):
        return value
    if isinstance(value, list):
        return [_tagged(v) for v in value]
    if isinstance(value, tuple):
        return {"__tuple__": [_tagged(v) for v in value]}
    if isinstance(value, (set, frozenset)):
        tag = "__frozenset__" if isinstance(value, frozenset) else "__set__"
        return {tag: sorted((_tagged(v) for v in value), key=lambda m: json.dumps(m, ensure_ascii=False))}
    if isinstance(value, dict):
        if all(isinstance(k, str) for k in value):
            return {k: _tagged(v) for k, v in value.items()}
        return {"__dict__": [[_tagged(k), _tagged(v)] for k, v in value.items()]}
    raise PackError(f"cannot tag {type(value).__name__}")


# ---------------------------------------------------------------- reading

def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise PackError(f"missing pack file: {path}") from None
    except json.JSONDecodeError as exc:
        raise PackError(f"bad JSON in {path}: {exc}") from None


def resolve_pack_dir(name_or_path, packs_root=None):
    """A bare name is looked up under the packs root. A path (absolute, or containing a separator
    or starting with '.') is used as given, so a name never resolves to an unrelated directory."""
    if os.path.isabs(name_or_path) or os.sep in name_or_path or name_or_path.startswith("."):
        return os.path.abspath(name_or_path)
    return os.path.join(packs_root or PACKS_ROOT, name_or_path)


def read_manifest(pack_dir):
    manifest = _read_json(os.path.join(pack_dir, "pack.json"))
    if manifest.get("format", FORMAT_VERSION) != FORMAT_VERSION:
        raise PackError(f"{pack_dir}: unsupported pack format {manifest.get('format')}")
    if "name" not in manifest or "tables" not in manifest:
        raise PackError(f"{pack_dir}: pack.json needs 'name' and 'tables'")
    return manifest


def read_table_file(pack_dir, rel):
    """Return (doc, {table name: value}) for one table file, with types restored."""
    data = _read_json(os.path.join(pack_dir, rel))
    tables = data.get("tables")
    if not isinstance(tables, dict):
        raise PackError(f"{rel}: expected a 'tables' object")
    types_all = data.get("_types", {})
    out = {}
    for name, value in tables.items():
        out[name] = from_json(value, types_all.get(name, {}))
    return data.get("_doc", ""), out


def read_base(name_or_path, packs_root=None, _seen=()):
    """The base data of a pack after `extends` is applied, uncompiled.

    Returns (manifest, pack_dir, base_tables, docs) where docs maps each table to its file's doc."""
    pack_dir = resolve_pack_dir(name_or_path, packs_root)
    if pack_dir in _seen:
        raise PackError(f"extends cycle through {pack_dir}")
    manifest = read_manifest(pack_dir)
    base, docs, own_names = {}, {}, set()
    parent_name = manifest.get("extends")
    if parent_name:
        _, _, base, docs = read_base(parent_name, packs_root, _seen + (pack_dir,))
        base = copy.deepcopy(base)
    files = {}
    for entry in manifest["tables"]:
        rel = entry["file"]
        if rel not in files:
            files[rel] = read_table_file(pack_dir, rel)
        doc, values = files[rel]
        name = entry["name"]
        if name not in values:
            raise PackError(f"{pack_dir}: '{name}' is listed in pack.json but not in {rel}")
        value = values[name]
        if entry.get("merge"):
            if name not in base or not isinstance(base[name], dict) or not isinstance(value, dict):
                raise PackError(f"{pack_dir}: merge of '{name}' needs a dict in the parent and in the child")
            base[name].update(value)
        else:
            base[name] = value
        docs[name] = doc
        own_names.add(name)
    return manifest, pack_dir, base, docs


# ---------------------------------------------------------------- compiling

def compile_tables(base):
    """Add the derived entries to base tables, in place, and return the dict.

    Each step reads only base tables and the constants in the same dict, and each one is skipped
    when its output is already present, so compiling compiled data changes nothing."""
    t = base
    _compile_scraps(t)
    _compile_scrap_prices(t)
    _compile_heated_recipes(t)
    _compile_seed_return(t)
    _compile_bundles(t)
    _compile_skill_clusters(t)
    return t


def _compile_scraps(t):
    """Eating a food with `leaves_scraps` leaves a "<food>_scraps" item (lighter, cheaper, spoils fast)."""
    items = t["ITEMS"]
    wf, decay = t["SCRAP_WEIGHT_FACTOR"], t["SCRAP_DECAY"]
    for kind, spec in list(items.items()):
        if spec.get("leaves_scraps") and f"{kind}_scraps" not in items:
            items[f"{kind}_scraps"] = {
                "class": "material", "bulk": True, "food": True, "scraps": True, "scraps_of": kind,
                "food_group": "scraps", "fare": "poor", "compostable": 1.0,
                "weight": round(float(spec.get("weight", 1.0)) * wf, 3),
                "volume": float(spec.get("volume", 1.0)), "decay": decay,
            }


def _compile_scrap_prices(t):
    """Scraps are priced as a cheap fraction of the food they were left from (setdefault)."""
    scarcity = t["SCARCITY"]
    factor = t["SCRAP_SCARCITY_FACTOR"]
    for kind, spec in t["ITEMS"].items():
        if spec.get("scraps_of"):
            scarcity.setdefault(kind, round(scarcity.get(spec["scraps_of"], 1.0) * factor, 4))


def _compile_heated_recipes(t):
    """A heated dish needs heat and containment (abstract), plus a fuel slot, and keeps its old
    appliance names as `method_tools` hints. The base `tools` list is moved to `method_tools`."""
    methods_all = t["PREPARATION_METHODS"]
    by_hint = t["PREPARATION_METHODS_BY_HINT"]
    requirements = t["PREPARATION_REQUIREMENTS"]
    fuel_per_batch = t["FUEL_PER_BATCH"]
    heated = t["HEATED_FOOD_RECIPES"]
    for recipe in t["RECIPES"]:
        if recipe["name"] not in heated or "preparation" in recipe:
            continue
        methods = []
        for hint in list(recipe.get("tools", [])):
            for method in by_hint.get(hint, methods_all):
                if method not in methods:
                    methods.append(method)
        recipe["preparation"] = {"requires": list(requirements), "methods": methods or list(methods_all)}
        if not any(kind == "fuel" for kind, _ in recipe["in"]):
            recipe["in"] = list(recipe["in"]) + [["fuel", fuel_per_batch.get(recipe["name"], 1)]]
        if "tools" in recipe:
            recipe["method_tools"] = recipe.pop("tools")


def _compile_seed_return(t):
    for spec in t["CROPS"].values():
        spec.setdefault("seed_return", DEFAULT_SEED_RETURN)


def _compile_bundles(t):
    """Law and policy bundles get origin defaults; POLICIES and LAWS are the Giantville floor
    followed by the local bundles, sharing the same entries."""
    for bundle in t["LOCAL_POLICIES"] + t["LOCAL_LAWS"]:
        for key, default in BUNDLE_DEFAULTS:
            bundle.setdefault(key, default)
    t["POLICIES"] = t["GIANTVILLE_POLICIES"] + t["LOCAL_POLICIES"]
    t["LAWS"] = t["GIANTVILLE_LAWS"] + t["LOCAL_LAWS"]


def _compile_skill_clusters(t):
    """skill -> cluster index, read by skill_cluster() and the closeness functions."""
    t["_SKILL_CLUSTER"] = {skill: cluster for cluster, spec in t["SKILL_CLUSTERS"].items()
                           for skill in spec["skills"]}


# ---------------------------------------------------------------- loading

_CACHE = {}


def load_pack(name_or_path, packs_root=None):
    """Load and compile a pack (cached per directory). `name_or_path` is a name under packs/ or a directory."""
    pack_dir = resolve_pack_dir(name_or_path, packs_root)
    if pack_dir in _CACHE:
        return _CACHE[pack_dir]
    manifest, _, base, _docs = read_base(name_or_path, packs_root)
    stored = set(base)
    compiled = compile_tables(copy.deepcopy(base))
    derived = [n for n in compiled if n not in stored]
    pack = Pack(manifest["name"], pack_dir, manifest.get("description", ""), manifest.get("extends"),
                compiled, derived, base)
    _CACHE[pack_dir] = pack
    return pack
