"""Phase 009: kinship, households, and inheritance.

Genealogy is a world fact (bore/fathered and union_with edges with periods). Kin terms are held by each
resident and may disagree with the genealogy. On a death the genealogical heirs are published under the
default custom and no property moves. The founding draw is checked against its cited shares in the self-test.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                          # noqa: E402

from domains import bigville_entities as E                 # noqa: E402
from domains import population as POP                       # noqa: E402
from domains.data_view import entities                      # noqa: E402
from worlds.bigville_world import BigvilleWorld             # noqa: E402


def _attrs(world, node):
    return dict(world.eng.node(node)["attrs"])


def _parents(world, node):
    """Parent nodes read straight from the graph's bore and fathered edges (no E helper)."""
    out = []
    for edge in ("bore", "fathered"):
        out += [int(n) for n in world.eng.in_neighbours(node, edge)]
    return sorted(out)


def _children(world, node):
    return sorted({int(n) for edge in ("bore", "fathered") for n in world.eng.neighbours(node, edge)})


@pytest.fixture(scope="module")
def town():
    """A founding town for read-only checks. Tests that record a death build their own."""
    return BigvilleWorld.from_town100()


def _founder_with_heirs(world, custom=None):
    """A founder whose genealogical heirs include a living child, and the heirs under `custom`."""
    index = world._kin_index()
    now = world._kin_clock()
    for name, node in world._actors.items():
        heirs = E.genealogical_heirs(index, int(node), now, custom)
        if any(h["kind"] == "child" for h in heirs):
            return name, node
    raise AssertionError("no founder with a living child in this town")


def _property(world):
    """Everything a transfer of property would change: stock, carried goods, coin, land title, household."""
    return {
        "stock": dict(world._stock),
        "inventory": {n: copy.deepcopy(world.inventory(n)) for n in world._actors},
        "coin": {n: _attrs(world, node).get("coin") for n, node in world._actors.items()},
        "household": {n: _attrs(world, node).get("household") for n, node in world._actors.items()},
        "land": {land: copy.deepcopy(world.land_record(land)) for land in world._land},
    }


# ------------------------------------------------------------------ genealogy at founding

def test_genealogy_is_recorded_for_every_founder(town):
    for name, node in town._actors.items():
        attrs = _attrs(town, node)
        assert attrs["kin_dead"] == 0.0, name
        assert float(attrs["kin_birth"]) < 0.0, name
        assert _parents(town, node), f"{name} has no parent on record"
    unions = town.eng.nodes("Union")
    assert unions, "no unions were recorded"
    union = _attrs(town, unions[0])
    a, b = int(union["a"]), int(union["b"])
    assert town.eng.has_edge(a, "union_with", b) and town.eng.has_edge(b, "union_with", a)
    assert town.eng.has_edge(a, "in_union", unions[0])
    assert union["start"] < 0.0


def test_births_are_bore_or_fathered_by_the_parent_sex(town):
    for node in town.eng.nodes("Agent"):
        for child in town.eng.neighbours(node, "bore"):
            assert _attrs(town, node)["kin_sex"] == "female"
            assert _attrs(town, child)["kin_birth"] > _attrs(town, node)["kin_birth"]
        for child in town.eng.neighbours(node, "fathered"):
            assert _attrs(town, node)["kin_sex"] == "male"


def test_founding_genealogy_leaves_every_resident_and_the_stock_unchanged(monkeypatch):
    with_kin = BigvilleWorld.from_town100()
    monkeypatch.setattr(BigvilleWorld, "_found_kinship", lambda self, residents, seed: None)
    without = BigvilleWorld.from_town100()
    monkeypatch.undo()
    assert sorted(with_kin._actors) == sorted(without._actors)
    for name in with_kin._actors:
        mine = {k: v for k, v in _attrs(with_kin, with_kin._actors[name]).items() if not k.startswith("kin_")}
        assert mine == _attrs(without, without._actors[name]), name
    assert with_kin._stock == without._stock
    assert sorted(with_kin._households) == sorted(without._households)
    assert {k: with_kin.land_owner(k) for k in with_kin._land} == {k: without.land_owner(k) for k in without._land}


def test_the_founding_genealogy_is_the_same_for_the_same_seed():
    first = BigvilleWorld.from_town100()
    second = BigvilleWorld.from_town100()
    assert sorted(first._kin_index()["persons"]) == sorted(second._kin_index()["persons"])
    for name in first._actors:
        assert sorted(first.kin_terms_held(name), key=str) == sorted(second.kin_terms_held(name), key=str)


# ------------------------------------------------------------------ kin terms held

def test_an_aunt_is_identified_by_her_path(town):
    """An aunt is a parent's sister: the holder's parent P has a parent in common with the aunt."""
    found = 0
    for name, node in town._actors.items():
        for row in town.kin_terms_held(name):
            if row["term"] != "aunt" or row["attribution"] != "genealogy":
                continue
            aunt = int(row["target_node"])
            assert _attrs(town, aunt)["kin_sex"] == "female"
            assert any(aunt in _children(town, grand) and aunt != parent
                       for parent in _parents(town, node)
                       for grand in _parents(town, parent)), name
            found += 1
            if found >= 5:
                return
    assert found, "no aunt on record among the founders"


def test_a_fictive_uncle_is_held_by_a_resident_with_no_genealogical_path(town):
    holder = next(iter(town._actors))
    stranger = None
    for name, node in town._actors.items():
        if name != holder and town.genealogical_kin(holder, node) is None:
            stranger = (name, node)
            break
    assert stranger is not None
    row = town.hold_kin_term(holder, stranger[1], "uncle", attribution="honorific", source="test")
    assert row["term"] == "uncle" and row["attribution"] == "honorific"
    assert town.genealogical_kin(holder, stranger[1]) is None
    held = [r for r in town.kin_terms_held(holder) if r["target_node"] == int(stranger[1])]
    assert {r["term"] for r in held} == {"uncle"}
    # the reference is private: another resident holds nothing for this pair
    other = next(n for n in town._actors if n not in (holder, stranger[0]))
    assert not [r for r in town.kin_terms_held(other) if r["holder_node"] == int(town._actors[holder])
                and r["attribution"] == "honorific"]


def test_the_held_term_and_the_genealogy_may_disagree_without_error(town):
    for name, node in town._actors.items():
        cousins = [r for r in town.kin_terms_held(name) if r["term"] == "cousin"]
        if cousins:
            target = int(cousins[0]["target_node"])
            break
    else:
        pytest.fail("no cousin on record among the founders")
    town.hold_kin_term(name, target, "aunt", attribution="honorific")
    assert town.genealogical_kin(name, target)[0] == "cousin"
    terms = {r["term"] for r in town.kin_terms_held(name) if r["target_node"] == target}
    assert {"cousin", "aunt"} <= terms


def test_an_attribution_only_gives_the_terms_it_lists(town):
    holder = next(iter(town._actors))
    target = next(n for n in town._actors.values() if int(n) != int(town._actors[holder]))
    with pytest.raises(AssertionError):
        town.hold_kin_term(holder, target, "uncle", attribution="adoption")


# ------------------------------------------------------------------ inheritance

def test_a_death_publishes_genealogical_heirs_and_moves_no_property():
    world = BigvilleWorld.from_town100()
    deceased, node = _founder_with_heirs(world)
    expected = E.genealogical_heirs(world._kin_index(), int(node), world._kin_clock())
    before = _property(world)

    world.record_death(deceased, cause="test")

    assert _property(world) == before
    records = world.eng.nodes("HeirRecord")
    assert records
    record = _attrs(world, records[-1])
    assert record["predecessor"] == deceased
    assert record["custom"] == E.INHERITANCE_CUSTOM["default"] == "partible"
    assert record["deed_type"] == "inheritance"
    listed = [part.split("|") for part in record["heirs"].split(";")]
    assert len(listed) == len(expected)
    assert abs(sum(float(share) for _, _, share, _ in listed) - 1.0) < 1e-3
    events = [e for e in world.eng.nodes("Event") if _attrs(world, e)["kind"] == "heirs_published"]
    assert events and _attrs(world, events[-1])["public"] == 1.0
    assert _attrs(world, events[-1])["subject"] == deceased


def test_primogeniture_gives_the_eldest_child_the_whole_and_the_spouse_a_life_interest():
    world = BigvilleWorld.from_town100()
    deceased, node = _founder_with_heirs(world, custom="primogeniture")
    published = world.publish_heirs(deceased, custom="primogeniture")
    assert published["custom"] == "primogeniture"
    children = [h for h in published["heirs"] if h["kind"] == "child"]
    assert len(children) == 1 and children[0]["share"] == 1.0
    for spouse in (h for h in published["heirs"] if h["kind"] == "spouse"):
        assert spouse["share"] == 0.0 and spouse["life_interest"] is True


def test_publishing_heirs_for_a_resident_with_no_genealogy_is_a_no_op_on_the_record():
    world = BigvilleWorld()
    world.add_actor("Stranger", role="clerk")
    assert world._record_kin_death("Stranger") is None
    assert world.publish_heirs("Stranger") is None
    assert not world.eng.nodes("HeirRecord")


# ------------------------------------------------------------------ the pure draws

def test_relatives_by_path_distinguish_full_and_half_siblings():
    persons = {i: {"id": i, "sex": s, "birth": b, "death": d, "name": str(i), "founder": False, "in_village": False}
               for i, (s, b, d) in enumerate([("female", -30, None), ("female", -60, -20.0),
                                              ("male", -62, -25.0), ("male", -58, -22.0),
                                              ("female", -28, None), ("male", -27, None)])}
    births = [{"parent": 1, "child": 0, "period": -30}, {"parent": 2, "child": 0, "period": -30},
              {"parent": 1, "child": 4, "period": -28}, {"parent": 2, "child": 4, "period": -28},
              {"parent": 1, "child": 5, "period": -27}, {"parent": 3, "child": 5, "period": -27}]
    index = POP.index_kinship(persons, births, [])
    rel = POP.kin_relatives(index, 0)
    assert rel[4][0] == "sibling"
    assert rel[5][0] == "half_sibling"
    assert rel[1][0] == "parent" and rel[2][0] == "parent"


def test_generated_genealogy_is_consistent_with_its_own_ages():
    rng = np.random.default_rng(9009)
    kin = POP.draw_founding_kin([{"name": f"f{i}", "age": 30.0} for i in range(100)], rng)
    index = POP.index_kinship(kin["persons"], kin["births"], kin["unions"])
    for b in kin["births"]:
        parent, child = index["persons"][b["parent"]], index["persons"][b["child"]]
        assert child["birth"] >= parent["birth"] + 15
        if parent["death"] is not None:
            assert parent["death"] >= child["birth"]
    for u in kin["unions"]:
        if u["end"] is not None:
            assert u["end"] > u["start"]


def test_a_founder_has_a_grandparent_and_an_aunt_or_uncle_by_path():
    rng = np.random.default_rng(9009)
    kin = POP.draw_founding_kin([{"name": f"f{i}", "age": 30.0} for i in range(100)], rng)
    index = POP.index_kinship(kin["persons"], kin["births"], kin["unions"])
    terms = [POP.kin_relatives(index, f) for f in kin["founders"]]
    assert all(any(t == "grandparent" for t, _ in rel.values()) for rel in terms)
    assert all(any(t in ("aunt", "uncle") for t, _ in rel.values()) for rel in terms)


# ------------------------------------------------------------------ the self-test

def test_the_self_test_reports_household_and_extended_family_shares_against_their_sources():
    report = E.check_consistency()
    assert not report["errors"], report["errors"]
    assert not report["warnings"], report["warnings"]
    size = [m for m in report["info"] if m.startswith("HOUSEHOLDS: household size")]
    extended = [m for m in report["info"] if m.startswith("HOUSEHOLDS: extended-family share")]
    assert size and "Laslett 1972" in size[0] and "Wrigley and Schofield 1981" in size[0]
    assert extended and "Laslett 1972" in extended[0]
    draw = E.describe_household_distribution(20000, seed=3)
    target = E.HOUSEHOLD_TARGETS
    assert abs(draw["mean_size"] - float(target["mean_size"]["value"])) <= float(target["mean_size"]["tolerance"])
    assert abs(draw["extended_share"] - float(target["extended_share"]["value"])) <= \
        float(target["extended_share"]["tolerance"])


def test_the_test_hamlet_pack_keeps_the_kinship_tables_and_a_clean_self_test():
    view = entities("test_hamlet")
    report = view.check_consistency()
    assert not report["errors"] and not report["warnings"]
    assert view.KIN_TERMS == E.KIN_TERMS
    assert view.INHERITANCE_CUSTOM == E.INHERITANCE_CUSTOM
    assert view.HOUSEHOLD_SIZE == E.HOUSEHOLD_SIZE
