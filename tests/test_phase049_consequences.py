"""Phase 049: consequences instead of gates.

Each converted gate is accepted, and its consequence is visible in the world's state (never announced). The
refusals for acts that cannot happen (no stock, out of reach, locked, asleep, unknown recipe) still refuse, and the
retired reason codes are gone from the pack's table.
"""
from __future__ import annotations

import pytest

from domains import bigville_entities as E
from worlds import resolution as R
from worlds.bigville_world import BigvilleWorld as World

TOL = 1e-6
WOODLOT_CELL = (29, 3)          # as in tests/test_phase004_located_gathering.py


def _smith(strength=1.3):
    w = World(exhaustion_slow_on=False)
    w.add_tradesperson("Smith", "smith")
    w.eng.set_attr(w._bodies["Smith"], "str_base", strength)
    w.set_stock("iron", 10)
    w.set_stock("charcoal", 10)
    x, y, _fw, _fh = w._building_sites["forge"]
    w._move_actor_to("Smith", (x, y))
    return w


def _job(w, name):
    return w.eng.neighbours(w._actor(name), "on_job")[0]


def _finish(w, name, cap=2000):
    """Tick until the worker's jobs end. The worker is kept rested and whole, so only the job's own rules act."""
    for _ in range(cap):
        if not w.busy(name):
            return
        w.eng.set_attr(w._bodies[name], "stamina_reserve", 1.0)
        w.eng.set_attr(w._actors[name], "health_value", 1.0)
        w.tick(1)
    raise AssertionError("the job did not finish")


# ------------------------------------------------------------------ the reason table

def test_the_retired_codes_are_gone_and_the_codes_for_impossible_acts_stay():
    for code in ("busy", "too_tired", "no_capacity", "no_tool", "out_of_season", "on_cooldown"):
        assert code not in E.REFUSAL_REASONS, code
    for code in ("not_held", "out_of_stock", "not_in_reach", "container_locked", "asleep", "collapsed",
                 "unsupported", "malformed", "not_known", "unknown_target", "not_ready"):
        assert code in E.REFUSAL_REASONS, code


# ------------------------------------------------------------------ 1. skill floor

def test_below_the_skill_floor_the_work_is_attempted_and_a_far_short_batch_is_spoiled():
    w = _smith()
    floor = float(E.min_skill("forge_plough"))
    w.set_skill_level("Smith", "smithing", floor * 0.2)            # far below the floor: a share of 0.2
    assert w._skill_share_of_floor("Smith", "forge_plough") == pytest.approx(0.2, abs=0.01)
    iron = w.qty("iron")
    assert w.start("Smith", "forge_plough"), "attempting below the skill floor is allowed"
    _finish(w, "Smith")
    assert w.qty("iron") < iron, "the spoiled batch used its inputs"
    assert w.newest_tool() is None, "and yielded nothing"


def test_a_batch_just_below_the_floor_is_made_and_its_share_is_lower():
    w = _smith()
    floor = float(E.min_skill("forge_plough"))
    w.set_skill_level("Smith", "smithing", floor * 0.7)            # share 0.7: above the ruin line (0.5)
    assert w._skill_share_of_floor("Smith", "forge_plough") == pytest.approx(0.7, abs=0.01)
    assert w.start("Smith", "forge_plough")
    _finish(w, "Smith")
    assert w.newest_tool() is not None, "a batch above the ruin line is made"


# ------------------------------------------------------------------ 2. season

def test_gathering_out_of_season_yields_the_season_share_for_the_time_spent():
    w = World()
    w.add_actor("Gatherer", role="labourer", skill=0.9)
    w.add_gathering_site("woodlot", WOODLOT_CELL)
    w._move_actor_to("Gatherer", WOODLOT_CELL)
    w.set_season("summer")                                          # mushrooms are gathered in autumn only
    assert w.start("Gatherer", "gather_mushrooms"), "gathering out of season is allowed"
    w.tick(10)
    assert w.qty("mushroom") == pytest.approx(3.0 * float(E.RESOLUTION["off_season_yield"]), abs=TOL)


def test_sowing_out_of_season_uses_the_seed_and_the_crop_fails_at_the_next_period():
    w = World()
    w.set_stock("carrot_seed", 1)
    w.set_season("autumn")                                          # carrots are a spring crop
    crop = w.sow("Hob", "carrot")
    assert crop is not None and w.qty("carrot_seed") == 0.0
    assert w.crop_alive(crop), "the loss is not yet seen"
    w.pass_period()
    assert not w.crop_alive(crop), "the crop fails to the season's weather"


# ------------------------------------------------------------------ 3. strength

def test_a_weak_worker_progresses_slower_and_strains_a_heavy_trade():
    strong, weak = _smith(strength=1.3), _smith(strength=1.0)      # the plough needs 1.2
    for w in (strong, weak):
        assert w.start("Smith", "forge_plough")
    before_s = float(strong.eng.node(_job(strong, "Smith"))["attrs"]["remaining"])
    before_w = float(weak.eng.node(_job(weak, "Smith"))["attrs"]["remaining"])
    strong.tick(1)
    weak.tick(1)
    gain_s = before_s - float(strong.eng.node(_job(strong, "Smith"))["attrs"]["remaining"])
    gain_w = before_w - float(weak.eng.node(_job(weak, "Smith"))["attrs"]["remaining"])
    assert gain_s == pytest.approx(1.0, abs=TOL), "at or above the demand the committed rate holds"
    assert gain_w == pytest.approx(1.0 / 1.2 * 1.0, abs=0.01), "below the demand it progresses at strength / demand"
    assert float(weak.eng.node(weak._actors["Smith"])["attrs"].get("strain", 0.0)) > 0.0, "and it strains"
    assert float(strong.eng.node(strong._actors["Smith"])["attrs"].get("strain", 0.0)) == 0.0


# ------------------------------------------------------------------ 4. busy

def test_a_second_job_is_accepted_and_stop_ends_either_job():
    w = _smith()
    assert w.start("Smith", "forge_plough")
    assert w.start("Smith", "forge_knife"), "a second job is accepted"
    assert len(w.eng.neighbours(w._actor("Smith"), "on_job")) == 2
    assert w.stop_job("Smith") and w.busy("Smith"), "stop ends one job; the other goes on"
    assert w.stop_job("Smith") and not w.busy("Smith")


# ------------------------------------------------------------------ 5. serving equipment

def test_a_meal_eaten_without_its_bowl_is_partly_wasted():
    w = World()
    w.add_actor("Tom", role="hand", home_cell=(1, 1))
    w.add_actor("Cook", role="cook", home_cell=(1, 1))
    w.set_stock("gruel", 1)
    w.add_shop("kitchen", (1, 1), input_kind="grain", output_kind="gruel", price=1)
    assert w.stock_person("Cook", "gruel", 1, price=1)
    assert w.purchase_utterance("Tom", "Cook", "gruel", 1)
    assert w.give("Cook", "Tom", "gruel", 1, payment_kind="coin", payment_amount=1)
    assert w.eat("Tom", "gruel"), "a meal without its bowl and ladle is eaten"
    attrs = w.eng.node(w._actor("Tom"))["attrs"]
    full = E.meal_value("gruel", float(attrs["last_meal_freshness"]))
    waste = float(E.RESOLUTION["unserved_waste"])
    assert float(attrs["last_meal_value"]) == pytest.approx(full * (1.0 - waste), abs=TOL)


# ------------------------------------------------------------------ 6. watertight containers

def test_a_fluid_put_in_a_leaky_vessel_leaks_each_period():
    w = World()
    w.add_actor("Tom", role="hand")
    w.add_container("sack1", kind="sack", holds=["ale"])
    w.set_stock("ale", 1)
    w.fetch("Tom", "ale", 1)
    assert w.put("Tom", "sack1", "ale", 1), "a fluid goes into a vessel that is not watertight"
    assert w.contents("sack1", "ale") == pytest.approx(1.0, abs=TOL)
    w.pass_period()
    assert w.contents("sack1", "ale") == pytest.approx(1.0 - float(E.RESOLUTION["leak_per_period"]), abs=1e-3)


# ------------------------------------------------------------------ 7. over-capacity

def test_a_carrier_over_capacity_takes_what_fits_and_the_rest_drops_at_their_feet():
    w = World()
    w.add_actor("Carrier", role="hand")
    w.set_stock("grain", 1000)
    vol = float(w.item_volume("grain"))
    cap = float(w.capacity(w._actor_inventories["Carrier"]))
    amount = cap / vol + 3.0
    assert w.fetch("Carrier", "grain", amount), "fetching more than the carrier can hold is allowed"
    assert w.inventory_qty("Carrier", "grain") == pytest.approx(cap / vol, abs=1e-3)
    assert w.qty("grain") == pytest.approx(1000.0 - amount, abs=1e-3), "the store gave the whole amount"
    assert w._dropped_stocks, "the excess lies on the carrier's cell"


def test_a_recipient_over_capacity_takes_what_fits_and_the_rest_drops():
    w = World()
    w.add_actor("Giver", role="hand")
    w.add_actor("Ada", role="hand")
    w.set_stock("grain", 1000)
    vol = float(w.item_volume("grain"))
    cap = float(w.capacity(w._actor_inventories["Ada"]))
    assert w.fetch("Ada", "grain", cap / vol)                       # Ada is full
    assert w.fetch("Giver", "grain", 2.0)
    assert w.give("Giver", "Ada", "grain", 2.0), "a full recipient is no refusal"
    assert w.inventory_qty("Giver", "grain") == pytest.approx(0.0, abs=TOL)
    assert w.inventory_qty("Ada", "grain") == pytest.approx(cap / vol, abs=1e-3)
    assert w._dropped_stocks, "the part that did not fit drops at the recipient's feet"


# ------------------------------------------------------------------ 8. pointless acts

def test_a_rest_or_sleep_at_a_high_reserve_is_allowed_and_uses_the_slot():
    w = World()
    w.add_actor("Ada", role="hand")
    w.eng.set_attr(w._bodies["Ada"], "stamina_reserve", 0.9)
    assert w.major_action("Ada", "rest", amount=1.0), "a rest at 0.9 is allowed"
    w.eng.set_attr(w._bodies["Ada"], "stamina_reserve", 1.0)
    w.eng.set_attr(w._actors["Ada"], "major_action_used", 0.0)
    assert w.major_action("Ada", "sleep"), "a sleep at a full reserve is allowed"


def test_watering_an_unthirsty_crop_is_refused_as_not_needed_and_spends_nothing():
    # Phase 049 (supervisor decision): this gate is kept. The village trace depends on it.
    w = World()
    w.add_actor("Hob", role="farmer")
    w.set_stock("carrot_seed", 1)
    w.set_stock("water", 10.0)
    crop = w.sow("Hob", "carrot")
    assert crop is not None
    water = w.qty("water")
    assert float(w.eng.node(crop)["attrs"]["thirst"]) == 0.0
    assert w.water_crop("Hob", crop) is False and w._refusal_code == "not_needed"
    assert w.qty("water") == water, "the water is not spent"


# ------------------------------------------------------------------ 9. walking below e_low

def test_a_resident_below_e_low_walks_at_the_slowest_rate_until_the_collapse():
    w = World()
    w.add_actor("Ada", role="hand")
    band = w._exhaustion_band("Ada")
    assert band["step"] == 0 and not band["below_e_low"]
    w.eng.set_attr(w._bodies["Ada"], "stamina_reserve", 0.1)
    band = w._exhaustion_band("Ada")
    assert band["below_e_low"] and band["speed"] == pytest.approx(0.5 / 3, abs=1e-3)
    assert not band["stopped"], "below e_low is slow, not stopped"


# ------------------------------------------------------------------ 10. harvest and tending

def test_harvesting_an_unripe_crop_yields_its_maturity_share_and_the_crop_is_gone():
    w = World()
    w.set_stock("carrot_seed", 1)
    crop = w.sow("Hob", "carrot")
    grow = float(w.eng.node(crop)["attrs"]["grow_periods"])
    w.eng.set_attr(crop, "age", grow / 2.0)
    full = float(w.eng.node(crop)["attrs"]["yield"]) * w.crop_nitrogen_factor(crop)
    got = w.harvest_crop(crop)
    assert got == pytest.approx(full * 0.5, rel=1e-3), "half-grown, it yields half the full yield"
    assert not w.crop_alive(crop), "the crop is gone either way"


def test_tending_an_animal_again_too_soon_yields_nothing_and_leaves_it_fussed():
    w = World()
    w.add_actor("Farmer", role="farmer")
    w.add_animal("Daisy", "cow")
    assert w.milk("Farmer", "Daisy") > 0.0
    assert w.milk("Farmer", "Daisy") == 0.0, "no yield again in the same period"
    assert float(w.eng.node(w._animals["Daisy"])["attrs"].get("fussed", 0.0)) == 1.0


# ------------------------------------------------------------------ impossible acts still refuse

def test_the_acts_that_cannot_happen_still_refuse_with_their_codes():
    w = _smith()
    assert not w.start("Smith", "no_such_recipe") and w._refusal_code == "not_known"
    w.set_stock("iron", 0.0)
    assert not w.fetch("Smith", "iron", 5.0) and w._refusal_code == "out_of_stock"
    w2 = World()
    w2.add_actor("Ada", role="hand", home_cell=(10, 10))
    w2.add_actor("Bob", role="hand", home_cell=(20, 20))
    w2.set_stock("bread", 1)
    assert not w2.major_action("Ada", "give", recipient="Bob", kind="bread", amount=1.0)
    assert w2.last_outcome("Ada")["reason"] == "not_in_reach"
    w2.eng.set_attr(w2._bodies["Ada"], "stamina_reserve", 0.0)
    w2.eng.set_attr(w2._actors["Ada"], "asleep", 1.0)
    assert not w2.major_action("Ada", "move", destination=(11, 10))
    assert w2.last_outcome("Ada")["reason"] == "asleep"
