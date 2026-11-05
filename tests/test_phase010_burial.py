"""Phase 010: death, burial, and the graveyard.

A dead resident leaves a corpse on the cell where they died. A labourer with their own spade digs a grave
inside the graveyard. A corpse on the graveyard ground, with an open grave, is buried there. A corpse left
unburied for BURIAL.risk_after_periods periods puts its household at BURIAL.onset_chance a dawn of the
burial condition, through the ordinary disease mechanism. The world records these facts and checks the
physical preconditions. It never chooses who carries or buries a corpse.
"""
from __future__ import annotations

import collections
import hashlib
import json

import pytest

from domains import bigville_entities as E
from domains.world_affordances import BURIAL
from worlds.bigville_town100_world import SEED_DEFAULT, build_town_100
from worlds.bigville_world import BigvilleWorld

# The Phase 004 layout digest (tests/test_phase004_located_gathering.py) before the graveyard was added.
PHASE004_LAYOUT_DIGEST = "e302d08cf52d0e521f008714847b7c81e6e792af2754177fc91c40d4bfcf87ee"
WOODSHOP_FOOTPRINT = (34, 8, 3, 3)      # the woodshop as installed at founding (its origin and size)


@pytest.fixture
def town():
    return BigvilleWorld.from_town100(SEED_DEFAULT)


def _households(w):
    groups = collections.defaultdict(list)
    for name in w._actors:
        groups[w.eng.node(w._actors[name])["attrs"].get("household")].append(name)
    return groups


def _household_with_members(w, count=2):
    """A household whose members are all alive, at least `count` of them."""
    for household, members in sorted(_households(w).items(), key=lambda kv: str(kv[0])):
        alive = [m for m in members if float(w.eng.node(w._actors[m])["attrs"].get("alive", 1.0)) == 1.0]
        if household and len(alive) >= count:
            return household, alive
    raise AssertionError("no household with enough living members")


def _labourer(w, exclude=()):
    return next(n for n in w._actors if w.eng.node(w._actors[n])["attrs"].get("role") == "labourer"
                and n not in exclude and float(w.eng.node(w._actors[n])["attrs"].get("alive", 1.0)) == 1.0)


def _inside_graveyard(w):
    x, y, _w, _h = w._building_sites["graveyard"]
    return (x, y)


def _open_cell_outside(w):
    """A walkable cell that is not inside the graveyard footprint."""
    for cell in sorted(w._map_cells):
        if not w._in_graveyard(cell):
            return cell
    raise AssertionError("no walkable cell outside the graveyard")


def _corpse_items(w):
    return [n for n in w.eng.nodes("ToolItem") if w.eng.node(n)["attrs"].get("kind") == "corpse"]


# ----------------------------------------------------------------- data and the founding map
def test_the_graveyard_is_a_founding_building_with_a_knowledge_spec_and_a_fixed_site():
    assert "graveyard" in E.founding_buildings()
    assert "graveyard" in E.FOUNDING_BUILDING_SITES
    assert E.BUILDINGS["graveyard"]["knowledge"]["topics"]
    assert BURIAL["place"] == "graveyard"


def test_the_graveyard_takes_a_free_walkable_cell_clear_of_every_placement(town):
    grid, _affordances, layout = build_town_100(SEED_DEFAULT)
    x, y, w_, h_ = town._building_sites["graveyard"]
    footprint = {(i, j) for i in range(x, x + w_) for j in range(y, y + h_)}
    placed = [tuple(c) for c in layout["homes"] + layout["farms"] + list(layout["deposits"].values())
              + list(layout["work"].values()) + list(layout["sites"].values())]
    assert not footprint & set(placed), "the graveyard covers an existing placement"
    for cell in footprint:
        assert grid[cell[1]][cell[0]] == 0, f"graveyard cell {cell} is not grass"
        assert cell in town._map_cells, f"graveyard cell {cell} is not walkable"
    for kind, (ox, oy, ow, oh) in town._building_sites.items():
        if kind == "graveyard":
            continue
        assert not (x < ox + ow and ox < x + w_ and y < oy + oh and oy < y + h_), f"overlaps {kind}"


def test_the_layout_without_the_graveyard_is_still_the_phase004_layout():
    _grid, _affordances, layout = build_town_100(SEED_DEFAULT)
    body = {k: v for k, v in layout.items() if k != "sites"}
    body["building_sites"] = {k: v for k, v in body["building_sites"].items() if k != "graveyard"}
    assert hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() == PHASE004_LAYOUT_DIGEST


def test_the_woodshop_and_the_church_do_not_move(town):
    """Footprints as HEAD placed them (docs/phases/phase010/before_placements.json). The church's authored
    origin is (25, 12), but HEAD's allocator already moved it to the nearest clear cell (25, 15)."""
    assert town._building_sites["woodshop"] == WOODSHOP_FOOTPRINT
    assert town._building_sites["church"] == (25, 15, 4, 4)


# ----------------------------------------------------------------- a death leaves a corpse
def test_a_death_leaves_a_corpse_where_the_resident_died(town):
    victim = next(iter(town._actors))
    cell = town.actor_position(victim)
    assert town.corpse_of(victim) is None
    assert town.record_death(victim, cause="test")
    corpse = town.corpse_of(victim)
    assert corpse is not None
    attrs = town.eng.node(corpse)["attrs"]
    assert town.eng.node(corpse)["type"] == "ToolItem"
    assert attrs["kind"] == "corpse"
    assert attrs["weight"] == float(BURIAL["body_weight"])
    assert attrs["resident"] == victim
    assert attrs["buried"] == 0.0
    assert town.corpse_cell(victim) == cell
    assert corpse in _corpse_items(town)


def test_only_the_dead_leave_a_corpse(town):
    victim, bystander = list(town._actors)[:2]
    town.record_death(victim, cause="test")
    assert town.corpse_of(victim) is not None
    assert town.corpse_of(bystander) is None
    assert len(_corpse_items(town)) == 1


def test_a_corpse_is_not_buried_or_moved_by_the_world_on_its_own(town):
    victim = next(iter(town._actors))
    town.record_death(victim, cause="test")
    cell = town.corpse_cell(victim)
    town.pass_period(3)
    assert town.corpse_cell(victim) == cell
    assert town.eng.node(town.corpse_of(victim))["attrs"]["buried"] == 0.0


# ----------------------------------------------------------------- digging
def test_digging_needs_a_spade_and_the_graveyard(town):
    lab = _labourer(town)
    graveyard = _inside_graveyard(town)
    assert town._open_graves() == 0
    town._move_actor_to(lab, graveyard)
    assert not town.do(lab, "dig_grave"), "refused without a spade"
    assert town._open_graves() == 0
    town.give_tool(lab, "spade")
    town._move_actor_to(lab, _open_cell_outside(town))
    assert not town.do(lab, "dig_grave"), "refused outside the graveyard, spade or not"
    assert town._open_graves() == 0
    town._move_actor_to(lab, graveyard)
    spoil = town.qty("grave_spoil")
    assert town.do(lab, "dig_grave")
    assert town._open_graves() == 1
    assert town.qty("grave_spoil") == spoil + 1.0


def test_digging_uses_the_workers_own_spade_and_no_one_elses(town):
    lab = _labourer(town)
    other = _labourer(town, exclude=(lab,))
    town.give_tool(other, "spade")
    town._move_actor_to(lab, _inside_graveyard(town))
    assert not town.do(lab, "dig_grave"), "a spade in someone else's hands does not count"


# ----------------------------------------------------------------- burying
def test_burying_needs_a_corpse_on_the_graveyard_ground_and_an_open_grave(town):
    victim = next(iter(town._actors))
    town.record_death(victim, cause="test")
    lab = _labourer(town, exclude=(victim,))
    town.give_tool(lab, "spade")
    graveyard = _inside_graveyard(town)
    town._move_actor_to(lab, graveyard)
    assert not town.do(lab, "bury"), "refused with no open grave"
    assert town.do(lab, "dig_grave")
    assert not town.do(lab, "bury"), "refused while the corpse lies outside the graveyard"
    town._move_actor_to(lab, town.corpse_cell(victim))
    assert town.pick_up(lab, town.corpse_of(victim)), "a corpse is picked up with the ordinary action"
    assert town.corpse_cell(victim) == town.actor_position(lab)
    assert not town.do(lab, "bury"), "refused while the carrier stands outside the graveyard"
    town._move_actor_to(lab, graveyard)
    assert town.do(lab, "bury")
    corpse = town.corpse_of(victim)
    assert town.eng.node(corpse)["attrs"]["buried"] == 1.0
    assert town.corpse_cell(victim) is None
    assert town._open_graves() == 0
    assert town.corpse_of(victim) == corpse, "the record of the corpse is kept"
    assert not town.do(lab, "bury"), "a second burial needs a second open grave and a second corpse"


def test_bury_completes_only_when_the_grave_and_corpse_are_still_there(town):
    victim = next(iter(town._actors))
    town.record_death(victim, cause="test")
    lab = _labourer(town, exclude=(victim,))
    town.give_tool(lab, "spade")
    town._move_actor_to(lab, _inside_graveyard(town))
    assert town.do(lab, "dig_grave")
    town._move_actor_to(lab, town.corpse_cell(victim))
    assert town.pick_up(lab, town.corpse_of(victim))
    town._move_actor_to(lab, _inside_graveyard(town))
    assert town.do(lab, "bury")
    assert town.eng.node(town.corpse_of(victim))["attrs"]["buried"] == 1.0


# ----------------------------------------------------------------- the coffin
def test_the_coffin_recipe_works_at_the_woodshop(town):
    woodworker = "Wendel Plane"
    town.add_tradesperson(woodworker, "woodworker")
    town._move_actor_to(woodworker, (WOODSHOP_FOOTPRINT[0], WOODSHOP_FOOTPRINT[1]))
    town.set_stock("timber", 10.0)
    before = town.qty("timber")
    assert town.do(woodworker, "make_coffin")
    assert town.qty("timber") == before - 3.0
    coffins = [n for n in town.eng.nodes("ToolItem") if town.eng.node(n)["attrs"].get("kind") == "coffin"]
    assert len(coffins) == 1


def test_the_coffin_needs_the_woodworkers_timber_and_saw(town):
    woodworker = "Wendel Plane"
    town.add_tradesperson(woodworker, "woodworker")
    town._move_actor_to(woodworker, (WOODSHOP_FOOTPRINT[0], WOODSHOP_FOOTPRINT[1]))
    town.set_stock("timber", 2.0)
    assert not town._recipe_inputs_available("make_coffin", woodworker), "two timber is not enough for a coffin"
    town.do(woodworker, "make_coffin")         # the job waits, armed, for its third timber
    assert town.qty("timber") == 2.0
    assert not [n for n in town.eng.nodes("ToolItem") if town.eng.node(n)["attrs"].get("kind") == "coffin"]


def test_the_coffin_is_optional_for_burial(town):
    """A coffin does not change the burial's preconditions or its inputs (no mechanical effect is modelled)."""
    recipe = next(r for r in E.RECIPES if r["name"] == "bury")
    assert all(kind != "coffin" for kind, _ in recipe["in"])


# ----------------------------------------------------------------- the household risk
def test_an_unburied_corpse_raises_the_household_risk_after_n_periods_and_not_before(town):
    household, members = _household_with_members(town)
    victim = members[0]
    n = int(BURIAL["risk_after_periods"])
    town.record_death(victim, cause="test")
    assert town.burial_risk(household) == 0.0
    for _ in range(n - 1):
        town.pass_period(1)
        assert town.burial_risk(household) == 0.0, "no risk before the risk period"
    town.pass_period(1)
    assert town.burial_risk(household) == float(BURIAL["onset_chance"])


def test_a_household_without_a_corpse_has_no_risk(town):
    household, members = _household_with_members(town)
    victim = members[0]
    town.record_death(victim, cause="test")
    town.pass_period(int(BURIAL["risk_after_periods"]) + 2)
    others = [h for h in _households(town) if h not in (household, None, "")]
    assert others and all(town.burial_risk(h) == 0.0 for h in others)


def test_burying_removes_the_household_risk(town):
    household, members = _household_with_members(town)
    victim = members[0]
    town.record_death(victim, cause="test")
    town.pass_period(int(BURIAL["risk_after_periods"]))
    assert town.burial_risk(household) > 0.0
    lab = _labourer(town, exclude=(victim,))
    town.give_tool(lab, "spade")
    town._move_actor_to(lab, _inside_graveyard(town))
    assert town.do(lab, "dig_grave")
    town._move_actor_to(lab, town.corpse_cell(victim))
    assert town.pick_up(lab, town.corpse_of(victim))
    town._move_actor_to(lab, _inside_graveyard(town))
    assert town.do(lab, "bury")
    assert town.burial_risk(household) == 0.0


def test_an_unburied_corpse_makes_a_household_member_ill_through_the_disease_mechanism(town, monkeypatch):
    household, members = _household_with_members(town)
    victim, sick = members[0], members[1]
    n = int(BURIAL["risk_after_periods"])
    town.record_death(victim, cause="test")
    town.pass_period(n - 1)
    monkeypatch.setattr(town, "_burial_roll", lambda name: 0.0)     # every draw falls under the chance
    town._daily_life_tick()
    assert not town.eng.node(town._actors[sick])["attrs"].get("disease"), "no onset before the risk period"
    town.pass_period(1)
    town._daily_life_tick()
    attrs = town.eng.node(town._actors[sick])["attrs"]
    assert attrs.get("disease") == BURIAL["condition"]
    assert any(town.eng.node(i)["attrs"].get("patient") == sick
               for i in town.eng.nodes("Illness")), "the onset is a recorded illness"
    before = float(attrs.get("health_value", 1.0))
    town._daily_life_tick()
    assert float(town.eng.node(town._actors[sick])["attrs"]["health_value"]) < before, \
        "the disease drains health through the existing mechanism"


def test_a_draw_above_the_onset_chance_does_not_make_anyone_ill(town, monkeypatch):
    household, members = _household_with_members(town)
    victim, sick = members[0], members[1]
    town.record_death(victim, cause="test")
    town.pass_period(int(BURIAL["risk_after_periods"]))
    monkeypatch.setattr(town, "_burial_roll", lambda name: 0.999)
    town._daily_life_tick()
    assert not town.eng.node(town._actors[sick])["attrs"].get("disease")


def test_the_burial_draw_is_stateless_and_reproducible(town):
    first = town._burial_roll("Ada")
    assert town._burial_roll("Ada") == first
    assert 0.0 <= first < 1.0


# ----------------------------------------------------------------- the self-test and the pack
def test_the_self_test_is_clean_and_covers_the_burial_tables():
    report = E.check_consistency()
    assert report["errors"] == []
    assert report["warnings"] == []
    assert any("BURIAL" in line for line in report["info"])


def test_a_bad_burial_table_fails_the_self_test(monkeypatch):
    bad = dict(BURIAL, condition="healthy")
    monkeypatch.setattr(E, "BURIAL", bad)
    report = E.check_consistency()
    assert any(e.startswith("BURIAL.condition") for e in report["errors"])


def test_a_burial_recipe_that_names_no_graveyard_fails_the_self_test(monkeypatch):
    rows = [dict(r) for r in E.RECIPES]
    for r in rows:
        if r["name"] == "dig_grave":
            r["at_building"] = "church"
    monkeypatch.setattr(E, "RECIPES", rows)
    report = E.check_consistency()
    assert any("dig_grave" in e and "at_building" in e for e in report["errors"])


def test_the_coffin_and_the_spoil_are_items_that_something_uses_or_makes():
    assert "coffin" in E.ITEMS and "grave_spoil" in E.ITEMS
    assert E.ITEMS["coffin"]["verb"] == "bury"
    assert any(r["name"] == "make_coffin" and r["requires"] == "woodworker" for r in E.RECIPES)
    assert any(r["name"] == "dig_grave" and r["out"][0] == "grave_spoil" for r in E.RECIPES)


def test_the_test_hamlet_pack_has_an_empty_burial_table():
    from domains import pack as P
    hamlet = P.load_pack("test_hamlet")
    assert hamlet["BURIAL"] == {}
