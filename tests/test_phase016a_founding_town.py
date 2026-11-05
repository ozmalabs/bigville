"""Phase 016a: the founding town is built from its data pack.

`BigvilleWorld.from_town100(data_pack=...)` builds the founding town of a pack (default: bigville).
The cast, the map, and the sites come from the pack's founding tables. A child pack that changes one
of them builds a different town with no code change. A pack with no founding town is refused.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from collections import Counter

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from domains.data_view import entities          # noqa: E402
from domains.pack import load_pack              # noqa: E402
from worlds.bigville_town100_world import BigvilleTown100World   # noqa: E402
from worlds.bigville_world import BigvilleWorld  # noqa: E402

BIG = "bigville"
HAMLET = "test_hamlet"


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _role_counts(world):
    return Counter(world.eng.node(node)["attrs"]["role"] for node in world._actors.values())


def test_the_founding_town_is_built_from_the_bigville_pack():
    world = BigvilleWorld.from_town100()
    assert world.data_pack == BIG
    E = world.E
    wanted = Counter()
    for row in E.FOUNDING_ROLES:
        wanted[row["role"]] += row["count"]
    assert _role_counts(world) == wanted
    assert len(world._actors) == sum(row["count"] for row in E.FOUNDING_ROLES) == 100
    assert set(world._map_layout["deposits"]) == set(E.FOUNDING_DEPOSITS)
    assert world.eng.node(world._actors["John"])["attrs"]["role"] == "mayor"
    # naming the pack explicitly gives the same town as the default
    explicit = BigvilleWorld.from_town100(data_pack=BIG)
    assert sorted(explicit._actors) == sorted(world._actors)


def test_a_child_pack_that_changes_the_names_and_a_role_count_builds_a_different_town(tmp_path):
    parent = load_pack(BIG)
    child_dir = tmp_path / "child_town"
    first = ["Zara", "Quill", "Mabel", "Osric", "Pell"]
    roles = copy.deepcopy(parent["FOUNDING_ROLES"])
    labourer = next(row for row in roles if row["role"] == "labourer")
    carpenter = next(row for row in roles if row["role"] == "carpenter")
    labourer["count"] -= 1          # one fewer labourer ...
    carpenter["count"] += 1         # ... and one more carpenter: still 100 residents and 100 homes
    _write(child_dir / "pack.json", {
        "format": 1, "name": "child_town", "version": 1, "description": "test child",
        "extends": BIG,
        "tables": [
            {"name": "FOUNDING_FIRST_NAMES", "file": "population/names.json"},
            {"name": "FOUNDING_ROLES", "file": "population/roles.json"},
        ],
    })
    _write(child_dir / "population" / "names.json", {"_doc": "", "_types": {}, "tables": {
        "FOUNDING_FIRST_NAMES": first}})
    _write(child_dir / "population" / "roles.json", {"_doc": "", "_types": {}, "tables": {
        "FOUNDING_ROLES": roles}})

    child = BigvilleWorld.from_town100(data_pack=str(child_dir))
    default = BigvilleWorld.from_town100()

    assert child.data_pack == str(child_dir)
    expected = Counter({row["role"]: row["count"] for row in parent["FOUNDING_ROLES"]})
    expected["labourer"] -= 1
    expected["carpenter"] += 1
    assert _role_counts(child) == expected
    assert len(child._actors) == 100
    # residents who are not anchored take a first name from the child's pool
    anchors = set(child.E.FOUNDING_ANCHOR_NAMES.values())
    drawn = [name for name in child._actors if name not in anchors]
    assert drawn and all(name.split()[0] in first for name in drawn)
    assert sorted(child._actors) != sorted(default._actors)
    # the map and its sites are inherited, so they are the same as the default town's
    assert child._map_layout["homes"] == default._map_layout["homes"]
    assert child._map_layout["deposits"] == default._map_layout["deposits"]
    # and the default town is unchanged by building the child
    assert all(name.split()[0] not in first for name in default._actors if name not in anchors)


def test_the_hamlet_has_no_founding_town_and_from_town100_refuses_it():
    E = entities(HAMLET)
    assert list(E.FOUNDING_ROLES) == [] and E.FOUNDING_MAP == {}
    report = E.check_consistency()
    assert report["errors"] == []
    assert any("FOUNDING TOWN: none" in str(line) for line in report["info"])
    with pytest.raises(ValueError, match="no founding town"):
        BigvilleWorld.from_town100(data_pack=HAMLET)
    with pytest.raises(ValueError, match="founding town"):
        BigvilleTown100World(data_pack=HAMLET)
