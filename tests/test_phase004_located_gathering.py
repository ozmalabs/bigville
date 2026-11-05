"""Phase 004: located gathering. A gathering recipe is admissible only for an actor standing on the site of
its kind, with a batch of the site's stock there. A batch draws that stock as its job opens, and the stock
regrows once per period (a day) up to the site's capacity.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from domains import bigville_entities as E
from domains.knowledge import derive_knowledge, person_from_attrs
from worlds.bigville_sim_world import SOLID, TILE_NAME, TREE
from worlds.bigville_town100_world import SEED_DEFAULT, build_town_100
from worlds.bigville_world import BigvilleWorld

GATHERING_KINDS = ("woodlot", "orchard", "kitchen_garden", "quarry")
WOODLOT_CELL = (29, 3)              # the woodlot anchor: beside the forest body
# sha256 of the founding layout without its `sites` key, exported from HEAD 4e9c97d before Phase 004 placed
# any site. Equal digests show that the new sites move no existing home, workplace, farm, or deposit.
# Phase 010 added the graveyard to building_sites, so this digest now covers that entry. Without it the
# layout hashes to the Phase 004 value (tests/test_phase010_burial.py checks that).
HEAD_LAYOUT_DIGEST = "92051d44d883e78239d86bfb2bb131292de1834fb0417840dd58b3b96a0c4f28"
WALL = next(code for code, name in TILE_NAME.items() if name == "wall")


def _bare_world(*, kind=None, cell=WOODLOT_CELL, **site):
    """A scenario world without the town: one labourer, and optionally one site (placed explicitly)."""
    w = BigvilleWorld()
    w.add_actor("Gatherer", role="labourer", skill=0.9)
    if kind is not None:
        w.add_gathering_site(kind, cell, **site)
    w._move_actor_to("Gatherer", cell)
    return w


def _neighbour_tiles(grid, cell):
    x, y = cell
    out = []
    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if 0 <= ny < len(grid) and 0 <= nx < len(grid[0]):
            out.append(grid[ny][nx])
    return out


@pytest.fixture
def town():
    return BigvilleWorld.from_town100(SEED_DEFAULT)


# ----------------------------------------------------------------- the founding map
def test_the_founding_map_places_one_site_per_gathered_from_kind():
    kinds = {r["gathered_from"] for r in E.RECIPES if r.get("gathered_from")}
    assert kinds == set(GATHERING_KINDS)
    _grid, _affordances, layout = build_town_100(SEED_DEFAULT)
    assert set(layout["sites"]) == kinds


def test_each_site_is_a_walkable_cell_distinct_from_every_other_placement():
    grid, _affordances, layout = build_town_100(SEED_DEFAULT)
    taken = [tuple(c) for c in layout["homes"] + layout["farms"]
             + list(layout["deposits"].values()) + list(layout["work"].values())]
    sites = [tuple(c) for c in layout["sites"].values()]
    assert len(set(sites)) == len(sites), "two sites share a cell"
    for kind, cell in layout["sites"].items():
        assert cell not in taken, f"{kind} sits on an existing placement"
        assert grid[cell[1]][cell[0]] not in SOLID, f"{kind} is not walkable"


def test_the_woodlot_stands_beside_the_forest_and_the_quarry_beside_the_rock_face():
    grid, _affordances, layout = build_town_100(SEED_DEFAULT)
    assert TREE in _neighbour_tiles(grid, layout["sites"]["woodlot"])
    assert WALL in _neighbour_tiles(grid, layout["sites"]["quarry"])


def test_the_new_sites_move_no_existing_home_workplace_farm_or_deposit():
    _grid, _affordances, layout = build_town_100(SEED_DEFAULT)
    body = {k: v for k, v in layout.items() if k != "sites"}
    assert hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() == HEAD_LAYOUT_DIGEST
    assert layout["deposits"] == {"fish": (1, 2), "lumber": (7, 30), "stone": (42, 8)}


# ----------------------------------------------------------------- the 100-resident town
def test_the_town_places_each_site_on_its_cell_with_the_pack_stock(town):
    _grid, _affordances, layout = build_town_100(SEED_DEFAULT)
    for kind, cell in layout["sites"].items():
        assert town.gathering_site_cell(kind) == tuple(cell)
        assert town.gathering_stock(kind) == float(E.GATHERING_SITES[kind]["stock"])


def test_a_resident_gathers_at_the_woodlot_and_not_from_home(town):
    name = next(n for n in town._actors if town.eng.node(town._actors[n])["attrs"].get("role") == "labourer")
    town.set_season("spring")
    home = town.actor_position(name)
    site = town.gathering_site_cell("woodlot")
    before = town.gathering_stock("woodlot")
    assert not town.do(name, "lift_saplings"), "refused away from the woodlot"
    assert town.gathering_stock("woodlot") == before
    town._move_actor_to(name, site)
    assert town.do(name, "lift_saplings")
    assert town.gathering_stock("woodlot") == before - 3.0
    town._move_actor_to(name, home)
    assert not town.do(name, "lift_saplings"), "the woodlot's work is refused again once the resident leaves"


def test_a_resident_is_offered_a_walk_to_the_site_and_the_work_only_on_it(town):
    name = next(n for n in town._actors if town.eng.node(town._actors[n])["attrs"].get("role") == "labourer")
    town.set_season("spring")
    site = town.gathering_site_cell("woodlot")
    away = _actor_options_for(town, name)
    assert any(o["action"] == "move" and o.get("destination") == site for o in away)
    assert not any(o["action"] == "work" and o.get("recipe") == "lift_saplings" for o in away)
    town._move_actor_to(name, site)
    here = _actor_options_for(town, name)
    assert any(o["action"] == "work" and o.get("recipe") == "lift_saplings" for o in here)
    assert not any(o["action"] == "move" and o.get("destination") == site for o in here)


def _actor_options_for(town, name):
    return list(town._actor_options(name))


def test_a_site_with_no_stock_left_is_not_offered_as_a_destination(town):
    name = next(n for n in town._actors if town.eng.node(town._actors[n])["attrs"].get("role") == "labourer")
    town.set_season("spring")
    town.eng.set_attr(town._gathering_sites["woodlot"]["node"], "stock", 0.0)
    away = _actor_options_for(town, name)
    assert not any(o["action"] == "move" and o.get("destination") == town.gathering_site_cell("woodlot")
                   for o in away)


# ----------------------------------------------------------------- admissibility and stock
def test_gathering_is_refused_away_from_a_site():
    w = _bare_world(kind="woodlot")
    w._move_actor_to("Gatherer", next(c for c in sorted(w._map_cells) if c != WOODLOT_CELL))
    w.set_season("summer")
    assert w.actor_position("Gatherer") != w.gathering_site_cell("woodlot")
    assert not w.do("Gatherer", "gather_berries")
    assert w.gathering_stock("woodlot") == 60.0 and w.qty("berry") == 0.0


def test_gathering_is_allowed_on_the_site_and_draws_its_stock_then_the_site_stays_below_one_batch():
    w = _bare_world(kind="woodlot")
    w.set_season("summer")
    assert w.do("Gatherer", "gather_berries")
    assert w.gathering_stock("woodlot") == 56.0
    assert w.qty("berry") == 4.0


def test_a_site_refuses_a_batch_larger_than_its_stock_and_draws_down_to_zero():
    w = _bare_world(kind="woodlot", stock=3.0)
    w.set_season("summer")
    assert not w.do("Gatherer", "gather_berries"), "a batch of 4 berries needs 4 units of stock"
    w.set_season("spring")
    assert w.do("Gatherer", "lift_saplings"), "a batch of 3 saplings takes the 3 left"
    assert w.gathering_stock("woodlot") == 0.0
    assert not w.do("Gatherer", "lift_saplings"), "an empty site supplies nothing"


def test_no_site_means_no_gathering_even_on_the_cell_of_a_would_be_site():
    w = _bare_world(kind=None)
    w.set_season("summer")
    assert w.gathering_site_cell("woodlot") is None
    assert not w.do("Gatherer", "gather_berries")


def test_a_timed_gathering_batch_takes_its_stock_as_it_opens_and_yields_when_done():
    w = _bare_world(kind="woodlot", cell=WOODLOT_CELL)
    w.set_season("autumn")
    assert w.start("Gatherer", "gather_mushrooms")
    assert w.gathering_stock("woodlot") == 57.0, "the batch is taken as the job opens"
    assert w.qty("mushroom") == 0.0, "the mushrooms arrive when the 90-minute job finishes"
    w.tick(10)
    assert w.qty("mushroom") == 3.0


# ----------------------------------------------------------------- regrowth
def test_a_site_regrows_once_per_period_and_no_further_than_its_capacity():
    w = _bare_world(kind="woodlot", stock=50.0, growback=6.0, capacity=60.0)
    w.set_season("spring")
    w.tick(95)
    assert w.gathering_stock("woodlot") == 50.0, "nothing regrows before the day ends"
    w.tick(1)
    assert w.gathering_stock("woodlot") == 56.0, "one period's growback"
    assert w.do("Gatherer", "lift_saplings")
    assert w.gathering_stock("woodlot") == 53.0
    w.tick(96)
    assert w.gathering_stock("woodlot") == 59.0
    w.tick(96)
    assert w.gathering_stock("woodlot") == 60.0, "capped at capacity"
    w.tick(96)
    assert w.gathering_stock("woodlot") == 60.0


# ----------------------------------------------------------------- packs
def test_a_pack_without_gathering_sites_builds_a_world_and_refuses_a_site():
    w = BigvilleWorld(data_pack="test_hamlet")
    assert w.gathering_site_cell("woodlot") is None
    with pytest.raises(ValueError, match="not a GATHERING_SITES kind"):
        w.add_gathering_site("woodlot", WOODLOT_CELL)


def test_the_self_test_is_clean_for_bigville_and_for_the_hamlet_pack():
    from domains.data_view import entities
    report = E.check_consistency()
    assert report["errors"] == [] and report["warnings"] == []
    hamlet = entities("test_hamlet").check_consistency()
    assert hamlet["errors"] == [] and hamlet["warnings"] == []


def test_the_self_test_reports_a_gathering_recipe_whose_site_is_missing(monkeypatch):
    monkeypatch.setattr(E, "GATHERING_SITES", {k: v for k, v in E.GATHERING_SITES.items() if k != "woodlot"})
    errors = E.check_consistency()["errors"]
    assert any("'woodlot' is not a GATHERING_SITES kind" in e for e in errors)


def test_the_self_test_reports_a_site_whose_stock_is_above_its_capacity(monkeypatch):
    sites = dict(E.GATHERING_SITES)
    sites["quarry"] = dict(sites["quarry"], stock=sites["quarry"]["capacity"] + 1.0)
    monkeypatch.setattr(E, "GATHERING_SITES", sites)
    errors = E.check_consistency()["errors"]
    assert any("GATHERING_SITES[quarry]: stock must be between 0 and capacity" in e for e in errors)


def test_every_site_has_a_place_row_in_the_derived_knowledge(town):
    name = next(iter(town._actors))
    attrs = dict(town.eng.node(town._actors[name])["attrs"])
    person = person_from_attrs(name, attrs, pack=E, history=attrs.get("history"),
                               kin_terms=[r["term"] for r in town.kin_terms_held(name)],
                               neighbours=[], home_cell=town.actor_position(name))
    derived = derive_knowledge(person, E)
    for kind in GATHERING_KINDS:
        assert derived[f"place:{kind}"]["type"] == "place"
