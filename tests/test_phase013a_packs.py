"""Phase 013a: the entity tables come from packs/bigville, compiled by domains/pack.py.

The migration's equality check against the pre-phase snapshot is a one-time record
(docs/phases/phase013a/: snapshot_tables.py, before_tables.json); it is not a permanent test,
because later phases change the data on purpose.
"""
import copy
import importlib.util
import json
import os

import pytest

from domains import bigville_entities as E
from domains import pack as P
from domains import population, shared_frames, world_affordances

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SNAPSHOT_DIR = os.path.join(ROOT, "docs", "phases", "phase013a")


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SNAPSHOT_DIR, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _export_module():
    spec = importlib.util.spec_from_file_location("export_pack", os.path.join(ROOT, "tools", "export_pack.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def before():
    with open(os.path.join(SNAPSHOT_DIR, "before_tables.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _dump(value):
    return json.dumps(value, ensure_ascii=False)


def test_modules_bind_the_pack_objects():
    pack = P.load_pack("bigville")
    assert E.ITEMS is pack["ITEMS"] is world_affordances.ITEMS
    assert shared_frames.POLICIES is pack["POLICIES"]
    assert shared_frames._SKILL_CLUSTER is pack["_SKILL_CLUSTER"]
    assert population.PREFERENCE_RESEARCH is pack["PREFERENCE_RESEARCH"]
    assert E.ANIMAL_SERVICES == frozenset({"labour", "herding", "ratting"})


def test_types_json_cannot_hold_are_restored():
    assert isinstance(E.SERVING_EQUIPMENT, tuple)
    assert isinstance(E.STARTING_CROPS, tuple)
    assert isinstance(E.HEATED_FOOD_RECIPES, frozenset)
    assert isinstance(E.SLAUGHTER_PRODUCTS, frozenset)
    assert isinstance(E.SOUP_FOODS, set)
    assert isinstance(E.BUILDINGS["townhall"]["footprint"], tuple)
    assert all(isinstance(k, tuple) and len(k) == 2 for k in E.SKILL_AFFINITY)


def test_base_files_hold_no_derived_entries():
    base_dir = os.path.join(P.PACKS_ROOT, "bigville")
    items = json.load(open(os.path.join(base_dir, "world", "items.json"), encoding="utf-8"))["tables"]["ITEMS"]
    assert not any("scraps_of" in spec for spec in items.values())
    recipes = json.load(open(os.path.join(base_dir, "world", "recipes.json"), encoding="utf-8"))["tables"]["RECIPES"]
    assert not any("preparation" in r or "method_tools" in r for r in recipes)
    crops = json.load(open(os.path.join(base_dir, "world", "crops.json"), encoding="utf-8"))["tables"]["CROPS"]
    assert all(spec.get("seed_return") != 1.25 for spec in crops.values())
    assert "pork_scraps" in E.ITEMS and "pork_scraps" not in items


def test_export_rerun_is_byte_identical(tmp_path):
    export = _export_module()
    out = tmp_path / "bigville"
    assert export.main(["--pack", "bigville", "--out", str(out)]) == 0
    source = os.path.join(P.PACKS_ROOT, "bigville")
    names = sorted(os.path.relpath(os.path.join(d, f), source)
                   for d, _, files in os.walk(source) for f in files)
    assert names
    for rel in names:
        with open(os.path.join(source, rel), "rb") as a, open(out / rel, "rb") as b:
            assert a.read() == b.read(), rel


def test_exported_files_compile_back_to_the_same_tables(tmp_path):
    export = _export_module()
    out = tmp_path / "copy"
    export.main(["--pack", "bigville", "--out", str(out)])
    copied = P.load_pack(str(out))
    original = P.load_pack("bigville")
    assert set(copied.tables) == set(original.tables)
    for name in original.tables:
        assert P.canonical(copied[name]) == P.canonical(original[name]), name


def test_compile_is_idempotent():
    _, _, base, _ = P.read_base("bigville")
    once = P.compile_tables(copy.deepcopy(base))
    twice = P.compile_tables(copy.deepcopy(once))
    assert set(once) == set(twice)
    for name in once:
        assert P.canonical(once[name]) == P.canonical(twice[name]), name


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def test_child_pack_extends_bigville_and_overrides_two_tables(tmp_path):
    parent = P.load_pack("bigville")
    child_dir = tmp_path / "child_town"
    fish_cake = {"class": "material", "bulk": True, "weight": 1.0, "volume": 1.0,
                 "food": True, "leaves_scraps": 0.2}
    new_law = {"name": "test_gleaning_law", "title": "Gleaning Ordinance", "kind": "law",
               "scope": "village", "seed_roles": ["mayor"],
               "concepts": [{"name": "gleaning_is_allowed", "abstraction": "principle",
                             "reference": {"subject": "gleaning", "predicate": "is", "object": "allowed"}}]}
    _write(child_dir / "pack.json", {
        "format": 1, "name": "child_town", "version": 1, "description": "test child",
        "extends": "bigville",
        "tables": [
            {"name": "ITEMS", "file": "world/items.json", "merge": True},
            {"name": "SCARCITY", "file": "world/scarcity.json", "merge": True},
            {"name": "LOCAL_LAWS", "file": "frames/local_laws.json"},
        ],
    })
    _write(child_dir / "world" / "items.json", {"_doc": "", "_types": {}, "tables": {
        "ITEMS": {"test_fish_cake": fish_cake}}})
    _write(child_dir / "world" / "scarcity.json", {"_doc": "", "_types": {}, "tables": {
        "SCARCITY": {"test_fish_cake": 1.0}}})
    laws = copy.deepcopy(parent["LOCAL_LAWS"]) + [new_law]
    _write(child_dir / "frames" / "local_laws.json", {"_doc": "", "_types": {}, "tables": {
        "LOCAL_LAWS": laws}})

    child = P.load_pack(str(child_dir))
    assert child.extends == "bigville"
    # the override is in, with the compiler's derived scrap entry
    assert child["ITEMS"]["test_fish_cake"] == fish_cake
    assert child["ITEMS"]["test_fish_cake_scraps"]["scraps_of"] == "test_fish_cake"
    assert child["SCARCITY"]["test_fish_cake_scraps"] == round(1.0 * 0.15, 4)
    assert len(child["ITEMS"]) == len(parent["ITEMS"]) + 2
    # the new law is added, and the compiler gives it the bundle defaults
    assert len(child["LOCAL_LAWS"]) == len(parent["LOCAL_LAWS"]) + 1
    law = child["LOCAL_LAWS"][-1]
    assert law["origin"] == "bigville" and law["immutable"] is False and law["enforcement"] == "bigville"
    assert child["LAWS"][-1] is law
    # everything else is inherited unchanged
    assert P.canonical(child["POLICIES"]) == P.canonical(parent["POLICIES"])
    assert P.canonical(child["GIANTVILLE_LAWS"]) == P.canonical(parent["GIANTVILLE_LAWS"])
    assert P.canonical(child["CROPS"]) == P.canonical(parent["CROPS"])
    assert P.canonical(child["RECIPES"]) == P.canonical(parent["RECIPES"])
    assert P.canonical(child["SCARCITY"]["barley"]) == P.canonical(parent["SCARCITY"]["barley"])
    # the parent pack is not changed by the child
    assert "test_fish_cake" not in parent["ITEMS"]
    assert "test_gleaning_law" not in [law["name"] for law in parent["LAWS"]]


def test_manifest_naming_a_missing_table_is_rejected(tmp_path):
    _write(tmp_path / "bad" / "pack.json", {"format": 1, "name": "bad", "tables": [
        {"name": "ITEMS", "file": "world/items.json"}]})
    _write(tmp_path / "bad" / "world" / "items.json", {"_doc": "", "_types": {}, "tables": {"RECIPES": []}})
    with pytest.raises(P.PackError, match="ITEMS"):
        P.load_pack(str(tmp_path / "bad"))
