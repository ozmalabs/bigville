"""Phase 006: household work choice in the backends.

Open (household) recipes are published with physical read-offs: the fuel the worker holds, the fuel
in the town store while the worker stands at the store, the household's felt heating shortfall, and
night soil held or in the store. The backend (psi_can.open_work_need, used by cheap and psi_can alike)
turns those read-offs into points with the pack's HOUSEHOLD_WORK weights. An open recipe is offered
only when it has points above zero.
"""
from __future__ import annotations

import pytest

from bigville.backends.cheap import DeterministicBackend
from bigville.backends.protocol import ActorContext
from bigville.backends.psi_can import CANWeightModel, open_work_governed, open_work_need
from bigville.character import CharacterDefinition, MemoryRecord
from domains import bigville_entities as E
from domains import data_view
from worlds.bigville_world import BigvilleWorld

FUEL_KINDS = tuple(kind for kind, _units in E.type_members(E.HEATING["fuel_type"]))
NIGHT_SOIL = E.HOUSEHOLD_WORK["night_soil_kind"]
LOW = E.HOUSEHOLD_WORK["fuel_low_units"]
HIGH = E.HOUSEHOLD_WORK["night_soil_high_units"]


def _memory(recipe):
    return MemoryRecord(f"mem_{recipe}", {"recipe": recipe}, kind="recipe_knowledge")


def _character(name, role, *recipes):
    return CharacterDefinition(name, name, identity={"role": role},
                               memories=[_memory(r) for r in recipes])


def _work(world, name, recipe):
    return next((o for o in world.actor_affordances(name)
                 if o.get("action") == "work" and o.get("recipe") == recipe), None)


def _decide(world, name, character):
    """One cheap-backend decision over the world's published affordances, at a working hour."""
    ctx = ActorContext(character, 0, {"hunger": 0.0, "energy": 100.0, "calendar": {"hour": 10.0},
                                      "nearby_residents": []},
                       world.actor_affordances(name))
    return DeterministicBackend(character).decide(ctx).major_action


def _wood_in_hand(world, name, units):
    """Put `units` of wood into the actor's own inventory, drawn from the store."""
    world.set_stock("wood", units)
    assert world._move_stock_to_inventory(name, "wood", units)


@pytest.fixture
def world():
    w = BigvilleWorld()
    w.add_actor("Ash", role="forester", skill=0.8)
    w.give_tool("Ash", "axe")
    w.set_stock("lumber", 5)
    w.set_stock("wood", 0)
    return w


def _away_from_store(world, name):
    store = world.map_position_node(world._store)
    if world.actor_position(name) == store:
        world._move_actor_to(name, (0, 8))
    assert world.actor_position(name) != store


# ------------------------------------------------------------------ read-offs
def test_fuel_read_offs_are_published_only_on_the_fuel_recipe(world):
    _wood_in_hand(world, "Ash", 2.0)
    split = _work(world, "Ash", "split_firewood")
    assert split["open_recipe"] is True
    assert split["fuel_held"] == pytest.approx(2.0)
    assert "night_soil_held" not in split and "night_soil_store" not in split

    # A non-open trade recipe carries no household read-offs at all.
    saw = _work(world, "Ash", "saw_planks")
    assert saw is not None
    assert not {"open_recipe", "fuel_held", "fuel_store", "household_fuel_short"} & set(saw)


def test_night_soil_read_offs_are_published_only_on_the_compost_recipe():
    w = BigvilleWorld()
    w.add_actor("Bee", role="farmer", skill=0.8)
    w.give_tool("Bee", "spade")
    w.set_stock("ash", 4.0)
    w.set_stock(NIGHT_SOIL, 3.0)
    w.set_stock("wood", 2.0)
    compost = _work(w, "Bee", "make_compost")
    assert compost is not None
    assert compost["open_recipe"] is True
    assert compost["night_soil_held"] == 0.0
    assert "fuel_held" not in compost and "fuel_store" not in compost


def test_the_store_read_off_is_present_only_while_the_worker_stands_at_the_store(world):
    world.set_stock("wood", 3.0)
    store = world.map_position_node(world._store)
    _away_from_store(world, "Ash")
    away = _work(world, "Ash", "split_firewood")
    assert "fuel_store" not in away

    world._move_actor_to("Ash", store)
    there = _work(world, "Ash", "split_firewood")
    assert there["fuel_store"] == pytest.approx(3.0)


def test_household_shortfall_is_a_read_off_for_members_only(world):
    world.add_household("Hearth")
    world.assign_household("Ash", "Hearth")
    world.eng.set_attr(world._households["Hearth"], "fuel_short", 0.5)
    split = _work(world, "Ash", "split_firewood")
    assert split["household_fuel_short"] == pytest.approx(0.5)

    world.add_actor("Cole", role="forester", skill=0.8)
    world.give_tool("Cole", "axe")
    world.set_stock("lumber", 5)
    loner = _work(world, "Cole", "split_firewood")
    assert "household_fuel_short" not in loner


def test_a_resident_without_an_axe_is_not_offered_split_firewood():
    w = BigvilleWorld()
    w.add_actor("Dee", role="forester", skill=0.8)
    w.set_stock("lumber", 5)
    w.set_stock("wood", 0.0)
    assert _work(w, "Dee", "split_firewood") is None


# ------------------------------------------------------------------ the cheap backend chooses
def test_axe_holder_chooses_split_firewood_when_fuel_is_low(world):
    character = _character("Ash", "forester", "split_firewood")
    action = _decide(world, "Ash", character)
    assert action.action == "work"
    assert action.params["recipe"] == "split_firewood"


def test_axe_holder_does_not_choose_split_firewood_when_fuel_is_high(world):
    _wood_in_hand(world, "Ash", LOW + 4.0)
    character = _character("Ash", "forester", "split_firewood")
    split = _work(world, "Ash", "split_firewood")
    assert split["fuel_held"] >= LOW
    assert open_work_need(split) == 0.0
    action = _decide(world, "Ash", character)
    assert action is None or action.params.get("recipe") != "split_firewood"


def test_a_cold_household_with_fuel_in_hand_still_chooses_split_firewood(world):
    _wood_in_hand(world, "Ash", LOW + 4.0)
    world.add_household("Hearth")
    world.assign_household("Ash", "Hearth")
    world.eng.set_attr(world._households["Hearth"], "fuel_short", 1.0)
    action = _decide(world, "Ash", _character("Ash", "forester", "split_firewood"))
    assert action.params["recipe"] == "split_firewood"


def test_spade_holder_chooses_make_compost_when_night_soil_is_high():
    w = BigvilleWorld()
    w.add_actor("Bee", role="farmer", skill=0.8)
    w.give_tool("Bee", "spade")
    w.set_stock("ash", 4.0)
    w.set_stock("wood", 2.0)
    w.set_stock(NIGHT_SOIL, HIGH + 2.0)
    assert w._move_stock_to_inventory("Bee", NIGHT_SOIL, HIGH)
    action = _decide(w, "Bee", _character("Bee", "farmer", "make_compost"))
    assert action.params["recipe"] == "make_compost"


def test_spade_holder_does_not_choose_make_compost_when_night_soil_is_low():
    w = BigvilleWorld()
    w.add_actor("Bee", role="farmer", skill=0.8)
    w.give_tool("Bee", "spade")
    w.set_stock("ash", 4.0)
    w.set_stock("wood", 2.0)
    w.set_stock(NIGHT_SOIL, 2.0)   # one batch: offered, but below night_soil_high_units
    compost = _work(w, "Bee", "make_compost")
    assert compost is not None, "the recipe is offered (its inputs are on hand)"
    assert compost["night_soil_held"] < HIGH
    assert open_work_need(compost) == 0.0
    action = _decide(w, "Bee", _character("Bee", "farmer", "make_compost"))
    assert action is None or action.params.get("recipe") != "make_compost"


def test_night_soil_in_the_store_is_not_perceived_away_from_the_store():
    w = BigvilleWorld()
    w.add_actor("Bee", role="farmer", skill=0.8)
    w.give_tool("Bee", "spade")
    w.set_stock("ash", 4.0)
    w.set_stock("wood", 2.0)
    w.set_stock(NIGHT_SOIL, HIGH * 3)
    _away_from_store(w, "Bee")
    compost = _work(w, "Bee", "make_compost")
    assert "night_soil_store" not in compost
    assert open_work_need(compost) == 0.0
    w._move_actor_to("Bee", w.map_position_node(w._store))
    assert open_work_need(_work(w, "Bee", "make_compost")) > 0.0


# ------------------------------------------------------------------ psi_can behaves the same
def test_psi_can_model_chooses_split_firewood_only_when_fuel_is_low(world):
    character = _character("Ash", "forester", "split_firewood")
    ctx = ActorContext(character, 0, {"hunger": 0.0, "energy": 100.0, "calendar": {"hour": 10.0}},
                       world.actor_affordances("Ash"))
    chosen = CANWeightModel().choose(ctx, [_work(world, "Ash", "split_firewood")])
    assert chosen is not None and chosen["recipe"] == "split_firewood"

    _wood_in_hand(world, "Ash", LOW + 4.0)
    ctx = ActorContext(character, 0, {"hunger": 0.0, "energy": 100.0, "calendar": {"hour": 10.0}},
                       world.actor_affordances("Ash"))
    assert CANWeightModel().choose(ctx, [_work(world, "Ash", "split_firewood")]) is None


def test_open_work_need_applies_the_pack_weights_it_is_given():
    option = {"action": "work", "recipe": "split_firewood", "open_recipe": True,
              "fuel_held": 0.0, "household_fuel_short": 0.0}
    table = {"fuel_low_units": LOW, "night_soil_high_units": HIGH, "night_soil_kind": NIGHT_SOIL,
             "weights": {"fuel_cold": 0.0, "fuel_low": 12.5, "night_soil_high": 0.0}}
    assert open_work_need(option, table) == pytest.approx(12.5)
    assert open_work_need(option, dict(table, weights=dict(table["weights"], fuel_low=0.0))) == 0.0


def test_a_non_open_option_earns_no_open_work_points():
    assert open_work_need({"action": "work", "recipe": "saw_planks", "fuel_held": 0.0}) == 0.0


def test_other_open_recipes_keep_their_prior_offer_without_a_need():
    # Baking bread at home has no fuel or night-soil read-off, so the need does not gate it: a resident who
    # can attempt it is still offered it, as before Phase 006.
    bake = {"action": "work", "recipe": "bake_bread_at_home", "kind": "bread", "open_recipe": True, "score": 0.0}
    assert not open_work_governed(bake)
    ctx = ActorContext(_character("Ash", "forester"), 0,
                       {"hunger": 0.0, "energy": 100.0, "calendar": {"hour": 10.0}}, [bake])
    chosen = CANWeightModel().choose(ctx, [bake])
    assert chosen is not None and chosen["recipe"] == "bake_bread_at_home"


# ------------------------------------------------------------------ the pack and the self-test
def test_the_bigville_table_is_bound_and_the_hamlet_carries_a_value():
    assert E.HOUSEHOLD_WORK["weights"].keys() == {"fuel_cold", "fuel_low", "night_soil_high"}
    hamlet = data_view.entities("test_hamlet")
    assert hamlet.HOUSEHOLD_WORK["weights"].keys() == {"fuel_cold", "fuel_low", "night_soil_high"}


def test_the_self_test_rejects_a_negative_weight(monkeypatch):
    bad = {**E.HOUSEHOLD_WORK, "weights": {**E.HOUSEHOLD_WORK["weights"], "fuel_low": -1.0}}
    monkeypatch.setattr(E, "HOUSEHOLD_WORK", bad)
    report = E.check_consistency()
    assert any("HOUSEHOLD_WORK: weight 'fuel_low' must not be negative" in e for e in report["errors"])
