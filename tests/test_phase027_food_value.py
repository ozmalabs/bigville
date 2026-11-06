"""Phase 027: food value, freshness and graded eating.

A meal relieves hunger by the food's `feeds` (loaf-equivalents), times its freshness, times the raw penalty
when the food needs preparation and has none. Spoiled food stays in stock and is still eaten. Freshness
travels with the food when it moves and mixes with fresh food when they share a pile.
"""
import pytest

import domains.bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World


def _tom():
    w = World()
    w.add_actor("Tom", role="hand", home_cell=(1, 1))
    return w


def _set_hunger(w, value):
    w.eng.set_attr(w._actor("Tom"), "hunger", float(value))


def _hunger(w):
    return w.hunger("Tom")


def test_every_food_item_has_a_feeds_value_and_derived_scraps_relieve_nothing():
    foods = [k for k, spec in E.ITEMS.items() if spec.get("food") and not spec.get("scraps_of")]
    assert len(foods) > 50
    for kind in foods:
        value = E.ITEMS[kind].get("feeds")
        assert isinstance(value, (int, float)) and 0.0 < value <= 1.5, f"{kind} needs a feeds value"
    assert E.feeds("pork_scraps") == 0.0, "scraps are animal feed, not people food"


def test_the_grading_constants_are_fractions_and_the_self_test_stays_clean():
    assert 0.0 < E.FOOD_GRADING["raw_penalty"] <= 1.0
    assert 0.0 <= E.FOOD_GRADING["rot_illness"] <= 1.0
    assert 0.0 <= E.FOOD_GRADING["raw_illness"] <= 1.0
    report = E.check_consistency()
    assert report["errors"] == [] and report["warnings"] == []


def test_a_loaf_clears_a_periods_hunger():
    w = _tom()
    w.set_stock("bread", 5)
    w.fetch("Tom", "bread", 1)
    _set_hunger(w, 1.0)
    assert w.eat("Tom", "bread")
    assert _hunger(w) == 0.0, "one fresh loaf is one resident's meal for a period"


def test_a_single_apple_relieves_part_of_a_period_and_two_apples_a_loaf():
    one = _tom()
    one.set_stock("apple", 2)
    one.fetch("Tom", "apple", 2)
    _set_hunger(one, 1.0)
    assert one.eat("Tom", "apple")
    assert _hunger(one) == pytest.approx(0.5), "a fresh apple relieves half a period"

    two = _tom()
    two.set_stock("apple", 2)
    two.fetch("Tom", "apple", 2)
    _set_hunger(two, 1.0)
    assert two.eat("Tom", "apple") and two.eat("Tom", "apple")
    loaf = _tom()
    loaf.set_stock("bread", 1)
    loaf.fetch("Tom", "bread", 1)
    _set_hunger(loaf, 1.0)
    assert loaf.eat("Tom", "bread")
    assert _hunger(two) == _hunger(loaf) == 0.0, "two apples are as much as a loaf"


def test_stale_bread_relieves_less_than_fresh_and_carries_an_illness_risk():
    fresh = _tom()
    fresh.set_stock("bread", 2)
    fresh.fetch("Tom", "bread", 1)
    _set_hunger(fresh, 1.0)
    assert fresh.eat("Tom", "bread")
    assert fresh.last_meal("Tom")["illness_risk"] == 0.0

    stale = _tom()
    stale.set_stock("bread", 2)
    stale.pass_period(1)                     # bread goes stale after one period
    stale.fetch("Tom", "bread", 1)
    _set_hunger(stale, 1.0)
    assert stale.stock_adjective("bread") == "stale"
    assert stale.eat("Tom", "bread")
    meal = stale.last_meal("Tom")
    assert 0.0 < meal["freshness"] < 1.0
    assert _hunger(stale) == pytest.approx(1.0 - meal["freshness"]), "relief is the bread's freshness"
    assert _hunger(stale) > _hunger(fresh), "stale bread relieves less than fresh bread"
    assert meal["illness_risk"] == pytest.approx(E.FOOD_GRADING["rot_illness"] * (1.0 - meal["freshness"]))
    assert meal["illness_risk"] > 0.0, "stale bread carries an illness risk"


def test_raw_meat_relieves_little_and_cooked_meat_relieves_its_full_feeds():
    raw = _tom()
    raw.set_stock("mutton", 1)
    raw.fetch("Tom", "mutton", 1)
    _set_hunger(raw, 1.0)
    assert raw.eat("Tom", "mutton")
    assert _hunger(raw) == pytest.approx(1.0 - E.FOOD_GRADING["raw_penalty"])
    assert raw.last_meal("Tom")["illness_risk"] == pytest.approx(E.FOOD_GRADING["raw_illness"])

    cooked = _tom()
    cooked.set_stock("roast", 1)
    cooked.fetch("Tom", "roast", 1)
    _set_hunger(cooked, 1.0)
    assert cooked.eat("Tom", "roast")
    assert _hunger(cooked) == 0.0, "a prepared roast is edible at full value"


def test_a_spoiled_pile_is_kept_and_can_still_be_eaten():
    w = _tom()
    w.set_stock("bread", 3)
    for _ in range(12):
        if w.stock_condition("bread") <= 0.0:
            break
        w.pass_period(1)
    assert w.stock_condition("bread") == 0.0, "the bread has spoiled"
    assert w.qty("bread") == 3.0, "spoiled stock is not deleted"
    assert w.stock_adjective("bread") in ("rotten", "putrid")
    assert not w._relieves_hunger("bread"), "spoiled food is not a hunger source to walk to"

    w.fetch("Tom", "bread", 1)
    assert w.qty("bread") == 2.0 and w.inventory_qty("Tom", "bread") == 1.0
    _set_hunger(w, 1.0)
    assert w.eat("Tom", "bread"), "a desperate resident can still eat spoiled bread"
    assert _hunger(w) == 1.0, "spoiled bread relieves nothing"
    meal = w.last_meal("Tom")
    assert meal["value"] == 0.0 and meal["illness_risk"] == pytest.approx(E.FOOD_GRADING["rot_illness"])


def test_only_an_empty_stock_yields_nothing():
    w = _tom()
    _set_hunger(w, 1.0)
    assert not w.eat("Tom", "bread")
    assert _hunger(w) == 1.0


def test_freshness_travels_with_food_moved_to_a_carrier():
    w = _tom()
    w.set_stock("bread", 4)
    w.pass_period(1)
    before = w.stock_condition("bread")
    assert 0.0 < before < 1.0
    w.fetch("Tom", "bread", 2)
    inventory_node = w._inventory_stock("Tom", "bread")
    assert w.eng.node(inventory_node)["attrs"]["condition"] == pytest.approx(before)


def test_spoiled_food_stays_spoiled_when_it_is_filled_into_a_container():
    w = _tom()
    w.set_stock("bread", 4)
    for _ in range(12):
        if w.stock_condition("bread") <= 0.0:
            break
        w.pass_period(1)
    w.add_container("larder_x", kind="barrel", holds=["bread"], cell=(1, 1))
    w.fill("Tom", "larder_x", "bread", 2)
    assert w.contents("larder_x", "bread") == 2.0
    assert w.stored_condition("larder_x", "bread") == 0.0, "a fill keeps the spoiled condition"


def test_fresh_production_mixes_with_spoiled_stock_and_does_not_launder_it():
    w = _tom()
    w.set_stock("bread", 3)
    for _ in range(12):
        if w.stock_condition("bread") <= 0.0:
            break
        w.pass_period(1)
    w.set_stock("bread", 3.0 + 60.0)         # a bake of 60 into the same pile
    assert w.stock_condition("bread") == pytest.approx(60.0 / 63.0, abs=1e-3)
    assert w.stock_condition("bread") < 1.0


def test_a_cooked_meal_is_fresh_and_a_raw_one_is_not_the_same_food():
    assert E.meal_value("roast", 1.0) == E.ITEMS["roast"]["feeds"]
    assert E.meal_value("mutton", 1.0) == pytest.approx(E.ITEMS["mutton"]["feeds"] * E.FOOD_GRADING["raw_penalty"])
    assert E.meal_value("apple", 0.0) == 0.0
    assert E.meal_illness_risk("apple", 1.0) == 0.0
    assert E.meal_illness_risk("mutton", 1.0) == pytest.approx(E.FOOD_GRADING["raw_illness"])


def test_the_balance_food_line_is_in_loaves_per_period():
    flows, _notes, _work = E._balance_flows(E.BALANCE_SCENARIO)
    supply, demand = flows["food (loaves, upper bound)"]
    assert demand == pytest.approx(E.BALANCE_SCENARIO["residents"] * E.BALANCE_SCENARIO["food_per_resident"])
    assert supply > 0.0
    assert "food (upper bound)" not in flows
