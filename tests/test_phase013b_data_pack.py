"""Phase 013b: the world reads a named data pack.

A world takes its entity tables and rules from one pack (`BigvilleWorld(data_pack=...)`, or the
scenario's "data_pack"). These tests cover the standalone test pack `packs/test_hamlet`, the
`domains.check` self-test on it, the default-pack equivalence, and isolation between worlds.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import types

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from domains import bigville_entities as DEFAULT          # noqa: E402
from domains.data_view import entities                     # noqa: E402
from domains.pack import PackError, canonical, load_pack   # noqa: E402
from worlds.bigville_world import BigvilleWorld as World   # noqa: E402

HAMLET = "test_hamlet"


def _public_tables(module):
    """Every public, non-callable value of an entity module, as canonical text (type and order kept)."""
    out = {}
    for name in dir(module):
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if callable(value) or isinstance(value, types.ModuleType):
            continue
        try:
            out[name] = canonical(value)
        except PackError:   # e.g. the `annotations` feature object of `from __future__`
            continue
    return out


def test_hamlet_world_boots_and_its_baker_runs_the_hamlet_recipes():
    w = World(data_pack=HAMLET)
    assert w.data_pack == HAMLET
    assert [r["name"] for r in w.E.RECIPES] == ["mill_flour", "bake_bread"]
    w.add_actor("Ann", role="baker", skill=0.9)
    w.set_stock("grain", 2)
    w.set_stock("water", 2)
    assert w.do("Ann", "mill_flour")
    assert w.do("Ann", "bake_bread")
    assert w.qty("bread") == 2.0
    assert w.qty("flour") == 0.0
    assert w.qty("water") == 1.0


def test_domains_check_exits_zero_on_the_hamlet_and_prints_its_report():
    proc = subprocess.run([sys.executable, "-m", "domains.check", "--pack", HAMLET],
                          cwd=_ROOT, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr
    assert "ERRORS (0)" in proc.stdout
    assert "WARNINGS (0)" in proc.stdout


def test_domains_check_default_pack_matches_the_self_test_script():
    check = subprocess.run([sys.executable, "-m", "domains.check"], cwd=_ROOT,
                           capture_output=True, text=True, timeout=600)
    script = subprocess.run([sys.executable, os.path.join("domains", "bigville_entities.py")], cwd=_ROOT,
                            capture_output=True, text=True, timeout=600)
    assert check.returncode == script.returncode == 0
    assert check.stdout == script.stdout


def test_a_fresh_view_of_the_bigville_pack_equals_the_default_modules(tmp_path):
    """The view built from the pack (not the default modules) gives the same tables: a copy of
    bigville, made as a child pack that extends it with no change."""
    view = entities("bigville")
    assert view is DEFAULT, "the default pack is served by the real modules"
    child = _child_of_bigville_dir(tmp_path)
    fresh = entities(child)
    assert fresh is not DEFAULT
    assert _public_tables(fresh) == _public_tables(DEFAULT)
    assert fresh.check_consistency()["errors"] == DEFAULT.check_consistency()["errors"] == []


def test_a_world_on_a_fresh_bigville_view_behaves_like_the_default_world(tmp_path):
    default = World()
    fresh = World(data_pack=_child_of_bigville_dir(tmp_path))
    for w in (default, fresh):
        w.add_actor("Sam", role="sawyer", skill=0.9)
        w.set_stock("lumber", 4)
        assert w.do("Sam", "saw_planks")
    snapshot = lambda w: (w.qty("lumber"), w.qty("timber"), w.inventory("Sam"))  # noqa: E731
    assert snapshot(fresh) == snapshot(default)
    assert snapshot(default)[1] > 0.0


def test_two_worlds_with_different_packs_in_one_process_do_not_share_tables():
    default = World()
    hamlet = World(data_pack=HAMLET)
    assert hamlet.E is not default.E
    assert [r["name"] for r in hamlet.E.RECIPES] == ["mill_flour", "bake_bread"]
    assert len(default.E.RECIPES) == len(DEFAULT.RECIPES) > 100
    assert "saw_planks" not in {r["name"] for r in hamlet.E.RECIPES}
    assert "wood" in DEFAULT.ITEMS and "wood" not in hamlet.E.ITEMS
    assert hamlet.E.scarcity("bread") == pytest.approx(1.5)
    # The default modules and the default world are unchanged by building the hamlet world.
    assert len(DEFAULT.RECIPES) == len(default.E.RECIPES)
    assert "bake_bread" in {r["name"] for r in default.E.RECIPES}
    default.add_actor("Sam", role="sawyer", skill=0.9)
    default.set_stock("lumber", 2)
    assert default.do("Sam", "saw_planks")


def test_a_scenario_selects_the_pack_and_setting_it_twice_is_an_error():
    w = World(scenario={"id": "hamlet_scenario", "data_pack": HAMLET})
    assert w.data_pack == HAMLET
    with pytest.raises(ValueError):
        World(data_pack=HAMLET, scenario={"id": "conflict", "data_pack": HAMLET})


def test_an_unknown_pack_is_refused():
    with pytest.raises(PackError):
        World(data_pack="no_such_pack_anywhere")


def test_the_hamlet_pack_is_standalone_and_names_every_table_the_modules_bind():
    hamlet = load_pack(HAMLET)
    assert hamlet.extends is None
    assert set(load_pack("bigville").names()) <= set(hamlet.names())


def _child_of_bigville_dir(tmp_path):
    """A pack directory under the test's temp dir that extends bigville and changes nothing."""
    path = os.path.join(str(tmp_path), "bigville_copy")
    os.makedirs(path)
    with open(os.path.join(path, "pack.json"), "w", encoding="utf-8") as fh:
        json.dump({"format": 1, "name": "bigville_copy", "version": 1, "extends": "bigville",
                   "tables": []}, fh)
    return path
