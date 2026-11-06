"""Phase 030: the town store has a lock and key.

A key is a discrete item (a ToolItem of kind KEY_KIND) held like a tool, so it can be given, dropped, picked up and
taken. Lock and unlock are major actions on a named container or on the town store ("store"), from the cell the lock
stands on, with a key the actor holds. A lock with keys_required above 1 opens once that many distinct keyholders have
each turned a key. Every resident-initiated path that reads or writes the town stock asks `_store_open` first.
"""
from __future__ import annotations

import json
import os

from bigville.game import BigvilleGame
from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A, H = "Ada", "Hal"
LOCK_ID = E.STORE_LOCK["lock_id"]
PACK_CODES = ("no_lock", "no_key", "already_locked", "already_unlocked", "already_authorised", "store_locked")


def _town(*, tick=True):
    """Two residents on the store cell, ten bread in the store. With `tick`, the turn clock runs (a major action
    is then claimed for the turn). Without it, position and slot checks that apply only in a running turn are off."""
    w = World(autonomous_actors=False)
    cell = w.map_position_node(w._store)
    w.add_actor(A, role="hand", home_cell=cell)
    w.add_actor(H, role="hand", home_cell=cell)
    w._move_actor_to(A, cell)
    w._move_actor_to(H, cell)
    w.set_stock("bread", 10)
    if tick:
        w.tick()
        w.mark_turn_start()
    return w, cell


def _neighbour(w, cell):
    return next(c for c in sorted(w._map_cells)
                if max(abs(c[0] - cell[0]), abs(c[1] - cell[1])) == 1)


def _set_store_lock(w, *, locked=None, keys_required=None):
    node = w._store_lock_node()
    if locked is not None:
        w.eng.set_attr(node, "locked", 1.0 if locked else 0.0)
    if keys_required is not None:
        w.eng.set_attr(node, "keys_required", float(keys_required))


def _locked(w):
    return float(w.eng.node(w._store_lock_node())["attrs"]["locked"]) == 1.0


def _reason(w, name):
    return w.last_outcome(name)["reason"]


def _plain(value):
    """True when a value is plain data (no objects, no random generators)."""
    if isinstance(value, dict):
        return all(isinstance(k, str) and _plain(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return all(_plain(v) for v in value)
    return value is None or isinstance(value, (str, int, float, bool))


# ------------------------------------------------------------------ data and wiring

def test_the_lock_data_and_refusal_codes_are_in_both_packs():
    assert E.KEY_KIND == "key" and E.KEY_KIND not in E.ITEMS, "a key is not a bulk good"
    assert E.KEY_WEIGHT > 0
    assert E.STORE_LOCK["locked"] is False and E.STORE_LOCK["keys_required"] == 1, "the default town is unlocked"
    for pack in ("bigville", "test_hamlet"):
        reasons = json.load(open(os.path.join(ROOT, "packs", pack, "world", "refusal_reasons.json")))["tables"]
        actions = json.load(open(os.path.join(ROOT, "packs", pack, "world", "major_actions.json")))["tables"]
        for code in PACK_CODES:
            assert reasons["REFUSAL_REASONS"][code]["description"].strip(), (pack, code)
        for action in ("lock", "unlock"):
            assert actions["MAJOR_ACTIONS"][action]["description"].strip(), (pack, action)


def test_the_store_lock_is_its_own_node_and_the_store_keeps_no_lock_attributes():
    w, _cell = _town()
    assert w.store_attrs() == {"name": "store"}, "the store carries no commodity or lock floats"
    lock = w._store_lock_node()
    assert w.eng.node(lock)["type"] == "Lock"
    attrs = w.eng.node(lock)["attrs"]
    assert attrs == {"lock_id": float(LOCK_ID), "locked": 0.0, "keys_required": 1.0}, "founded unlocked"


# ------------------------------------------------------------------ keys are items

def test_a_key_is_a_discrete_item_held_like_a_tool():
    w, _cell = _town()
    key = w.give_key(H, opens=LOCK_ID)
    assert w.eng.node(key)["type"] == "ToolItem" and w.eng.node(key)["attrs"]["kind"] == E.KEY_KIND
    assert [item["kind"] for item in w.held_items(H)] == ["key"]
    assert list(w.eng.neighbours(w._actor(H), "holds_key")) == [], "no holds_key edge: the key is an item"
    assert _plain(w.eng.node(key)["attrs"]), "a key is plain data, so checkpoints can hold it"


def test_a_key_passed_to_another_resident_opens_the_store_for_them():
    w, _cell = _town(tick=False)
    _set_store_lock(w, locked=True)
    key = w.give_key(H, opens=LOCK_ID)
    assert w.fetch(A, "bread", 1.0) is False and w._refusal_code == "store_locked"
    assert w.give(H, A, key) is True
    assert [item["kind"] for item in w.held_items(A)] == ["key"] and w.held_items(H) == []
    assert w.fetch(A, "bread", 1.0) is True, "the new keyholder opens the store"
    assert w.fetch(H, "bread", 1.0) is False and w._refusal_code == "store_locked", "the giver has no key any more"


def test_a_key_dropped_opens_nothing_until_someone_picks_it_up():
    w, _cell = _town(tick=False)
    _set_store_lock(w, locked=True)
    key = w.give_key(H, opens=LOCK_ID)
    assert w.drop_item(H, key) is True
    assert w.unlock(A, "store") is False and w._refusal_code == "no_key"
    assert w.pick_up(A, key) is True
    assert w.unlock(A, "store") is True and not _locked(w)


def test_a_held_key_can_be_taken_through_the_contest():
    w, _cell = _town()
    key = w.give_key(H, opens=LOCK_ID)
    w.eng.set_attr(w._bodies[A], "str_base", 1.3)
    w.eng.set_attr(w._bodies[H], "str_base", 0.7)
    pending, reason = w.take_begin(A, {"source": H, "kind": key, "amount": 1.0})
    assert pending is not None, reason
    applied, code = w.take_resolve(pending, "resist")
    assert applied is True and code is None
    assert w._item_owner_edge(A, key) is not None and w._item_owner_edge(H, key) is None
    assert w.eng.node(list(w._handovers.values())[-1])["attrs"]["kind"] == "take"


# ------------------------------------------------------------------ lock and unlock

def test_a_key_holder_locks_and_unlocks_the_store_from_its_cell():
    w, _cell = _town()
    w.give_key(H, opens=LOCK_ID)
    assert w.major_action(H, "lock", container="store") is True and _locked(w)
    w2, _cell2 = _town()
    w2.give_key(H, opens=LOCK_ID)
    _set_store_lock(w2, locked=True)
    assert w2.major_action(H, "unlock", container="store") is True and not _locked(w2)


def test_lock_refusals_name_their_reason():
    w, cell = _town()
    assert w.major_action(A, "lock", container="store") is False and _reason(w, A) == "no_key"
    w.give_key(H, opens=LOCK_ID)
    _set_store_lock(w, locked=True)
    assert w.major_action(H, "lock", container="store") is False and _reason(w, H) == "already_locked"
    _set_store_lock(w, locked=False)
    assert w.major_action(H, "unlock", container="store") is False and _reason(w, H) == "already_unlocked"
    w._move_actor_to(H, _neighbour(w, cell))
    _set_store_lock(w, locked=True)
    assert w.major_action(H, "unlock", container="store") is False and _reason(w, H) == "not_in_reach"
    assert w.major_action(H, "unlock", container="nowhere") is False and _reason(w, H) == "unknown_target"
    w.add_container("pantry", kind="pantry", holds=("bread",), cell=_neighbour(w, cell))
    assert w.major_action(H, "unlock", container="pantry") is False and _reason(w, H) == "no_lock"


def test_a_container_locks_and_unlocks_by_name_and_only_its_keyholder_can_do_it():
    w, _cell = _town()
    w.add_container("safe", kind="safe", holds="coin", lock_id=7.0, locked=True)
    w.give_key(H, opens=7.0)
    assert w.lock(A, "safe") is False and w.is_locked("safe"), "no key, no lock"
    assert w.unlock(H, "safe") is True and not w.is_locked("safe")
    assert w.lock(H, "safe") is True and w.is_locked("safe")


def test_a_lock_that_needs_two_keyholders_opens_after_two_distinct_turns_of_a_key():
    w, _cell = _town()
    _set_store_lock(w, locked=True, keys_required=2)
    w.give_key(H, opens=LOCK_ID)
    w.give_key(A, opens=LOCK_ID)
    assert w.major_action(H, "fetch", kind="bread", amount=1.0) is False and _reason(w, H) == "store_locked"
    assert w.major_action(H, "unlock", container="store") is True and _locked(w), "one turn of a key is not enough"
    assert w.major_action(H, "unlock", container="store") is False and _reason(w, H) == "slot_used"
    assert w.unlock(H, "store") is False and w._refusal_code == "already_authorised", "one person, one turn"
    assert w.unlock(A, "store") is True and not _locked(w), "the second keyholder opens it"
    assert list(w.eng.neighbours(w._store_lock_node(), "authorised_by")) == []
    assert w.fetch(H, "bread", 1.0) is True, "open now (a direct fetch: H's major action is already spent)"


def test_a_dual_key_container_stays_shut_to_one_keyholder_and_a_single_key_one_opens_to_its_holder():
    w, _cell = _town(tick=False)
    w.add_container("vault", kind="safe", holds="coin", lock_id=9.0, locked=True, keys_required=2)
    w.give_key(H, opens=9.0)
    assert w._container_accessible(H, "vault") is False
    w.add_container("chest", kind="chest", holds="coin", lock_id=10.0, locked=True)
    w.give_key(H, opens=10.0)
    assert w._container_accessible(H, "chest") is True


# ------------------------------------------------------------------ the store paths

def test_fetch_from_a_locked_store_needs_the_key_and_an_unlocked_store_is_unchanged():
    w, _cell = _town()
    assert w.major_action(H, "fetch", kind="bread", amount=1.0) is True, "the founding store is unlocked"
    _set_store_lock(w, locked=True)
    assert w.major_action(A, "fetch", kind="bread", amount=1.0) is False and _reason(w, A) == "store_locked"
    assert w.inventory_qty(A, "bread") == 0.0 and w.qty("bread") == 9.0
    w.give_key(A, opens=LOCK_ID)
    assert w.major_action(A, "fetch", kind="bread", amount=1.0) is True


def test_recipe_inputs_draw_from_the_store_only_for_a_resident_with_access():
    w, _cell = _town(tick=False)
    _set_store_lock(w, locked=True)
    assert all(label != "store" for label, _ in w._bulk_sources(A, "bread"))
    assert w._bulk_available(A, "bread") == 0.0
    assert w._bulk_available(None, "bread") == 10.0, "a call with no resident still sees the store"
    w.give_key(A, opens=LOCK_ID)
    assert w._bulk_available(A, "bread") == 10.0


def test_a_job_short_of_store_access_stays_pending_until_a_key_arrives():
    w = World(exhaustion_slow_on=False)
    w.add_tradesperson("Smith", "smith")
    w.set_stock("iron", 10)
    w.set_stock("charcoal", 10)
    x, y, _fw, _fh = w._building_sites["forge"]
    w._move_actor_to("Smith", (x, y))
    _set_store_lock(w, locked=True)
    assert w.start("Smith", "forge_plough")
    for _ in range(40):
        w.tick(1)
    assert w.busy("Smith") and w.qty("iron") == 10.0, "the job waits; its inputs stay in the store"
    w.give_key("Smith", opens=LOCK_ID)
    for _ in range(300):
        if not w.busy("Smith"):
            break
        w.tick(1)
    assert not w.busy("Smith") and w.qty("iron") < 10.0, "with the key the store opens and the job completes"


def test_sow_water_fertilise_and_harvest_refuse_a_locked_store_and_work_with_a_key():
    w, cell = _town(tick=False)
    plot = _neighbour(w, cell)
    w.add_land("plot", cell=plot)
    w.add_land("ripe_plot", cell=_neighbour(w, plot))
    crop = next(c for c, spec in E.CROPS.items() if spec["season"] == w.season())
    spec = E.CROPS[crop]
    w.set_stock(spec["seed"], 3.0)
    manure = E.type_members(E.NITROGEN["fertiliser_type"])[0][0]
    w.set_stock(manure, 5.0)
    w.set_stock("water", 50.0)
    _set_store_lock(w, locked=True)
    assert w.major_action(H, "sow", target=(crop, "plot")) is False and _reason(w, H) == "store_locked"
    w.give_key(H, opens=LOCK_ID)
    assert w.major_action(H, "sow", target=(crop, "plot")) is True, "a keyholder sows from the store seed"
    grown = w._crops[len(w._crops) - 1]
    w.eng.set_attr(grown, "thirst", 1.0)
    assert w.major_action(A, "water", target=grown) is False and _reason(w, A) == "store_locked"
    assert w.qty("water") == 50.0
    assert w.major_action(A, "fertilise", target="ripe_plot") is False and _reason(w, A) == "store_locked"
    assert w.qty(manure) == 5.0
    w.eng.set_attr(grown, "age", float(spec["grow_periods"]))
    harvest_kind = spec["harvest"]
    before = w.qty(harvest_kind)
    assert w.major_action(A, "harvest", target=grown) is False and _reason(w, A) == "store_locked"
    assert w.qty(harvest_kind) == before
    w.give_key(A, opens=LOCK_ID)
    assert w.major_action(A, "harvest", target=grown) is True and w.qty(harvest_kind) > before


def test_medicine_comes_from_the_store_and_a_caregiver_without_access_gives_ordinary_care():
    w, _cell = _town(tick=False)
    w.set_stock("medicine", 2.0)
    w.eng.set_attr(w._actors[H], "health", "ill")
    w.eng.set_attr(w._actors[H], "disease", "fever")
    _set_store_lock(w, locked=True)
    assert w.treat(A, H, medicine=1.0) is False and w._refusal_code == "store_locked"
    assert w.qty("medicine") == 2.0
    assert w.care_for(A, H) is True and w.qty("medicine") == 2.0, "ordinary care, no medicine drawn"
    w.give_key(A, opens=LOCK_ID)
    w.eng.set_attr(w._actors[H], "health", "ill")       # the ordinary care above already marked H healthy
    assert w.care_for(A, H) is True and w.qty("medicine") == 1.0, "with the key the medicine is used"


def test_fill_and_empty_of_a_container_with_the_store_need_access():
    w, cell = _town(tick=False)
    w.add_container("pantry", kind="pantry", holds=("bread",), cell=cell)
    _set_store_lock(w, locked=True)
    assert w.fill(H, "pantry", "bread", 2.0) is False and w._refusal_code == "store_locked"
    assert w.qty("bread") == 10.0 and w.contents("pantry", "bread") == 0.0
    w.give_key(H, opens=LOCK_ID)
    assert w.fill(H, "pantry", "bread", 2.0) is True
    assert w.contents("pantry", "bread") == 2.0 and w.qty("bread") == 8.0
    assert w.empty(A, "pantry", "bread", 1.0) is False and w._refusal_code == "store_locked"
    assert w.contents("pantry", "bread") == 2.0
    w.give_key(A, opens=LOCK_ID)
    assert w.empty(A, "pantry", "bread", 1.0) is True and w.contents("pantry", "bread") == 1.0


def test_newspapers_stock_and_waste_refuse_without_access():
    w, _cell = _town(tick=False)
    w.set_stock("newspaper", 2.0)
    edition = w.eng.add_node("NewspaperEdition", {})
    _set_store_lock(w, locked=True)
    assert w.give_newspaper(H, edition) is None and w.qty("newspaper") == 2.0
    assert w.stock_person(H, "bread", 1.0) is False and w.qty("bread") == 10.0
    before = w.qty("compost")
    assert w.process_waste(H, "kitchen_scraps", 1.0) is False and w.qty("compost") == before
    w.give_key(H, opens=LOCK_ID)
    assert w.give_newspaper(H, edition) is not None and w.qty("newspaper") == 1.0
    assert w.stock_person(H, "bread", 1.0) is True and w.qty("bread") == 9.0
    assert w.process_waste(H, "kitchen_scraps", 1.0) == E.WASTE_CYCLES["kitchen_scraps"]["output"]


def test_the_founding_policy_and_non_residents_are_not_guarded_by_the_lock():
    w, _cell = _town(tick=False)
    _set_store_lock(w, locked=True)
    assert w._store_open(None) is True and w._store_open("nobody") is True
    w._store_bypass = True
    try:
        assert w.fetch(H, "bread", 1.0) is True, "inside the founding policy the store is not guarded"
    finally:
        w._store_bypass = False
    w._village_work_tick(0)
    assert w._store_bypass is False, "the policy restores the guard when its step ends"


# ------------------------------------------------------------------ publication and the cheap resident

def test_lock_and_unlock_are_published_only_with_a_fitting_key_at_the_cell():
    w, cell = _town()

    def actions(who):
        return [o["action"] for o in w._actor_options(who)]

    assert "lock" not in actions(H) and "unlock" not in actions(H)
    w.give_key(H, opens=LOCK_ID)
    assert "lock" in actions(H), "a keyholder at the store can lock it"
    assert "lock" not in actions(A) and "unlock" not in actions(A), "no key, no option"
    _set_store_lock(w, locked=True)
    assert "unlock" in actions(H)
    assert not any(o["action"] == "fetch" and o.get("stock_source") == "town" for o in w._actor_options(A)), \
        "a resident with no access is not offered the store's stock"
    w._move_actor_to(H, _neighbour(w, cell))
    assert "lock" not in actions(H) and "unlock" not in actions(H), "away from the lock, no option"


def test_the_cheap_resident_unlocks_the_store_it_holds_the_key_to():
    w, _cell = _town(tick=False)
    _set_store_lock(w, locked=True)
    w.give_key(H, opens=LOCK_ID)
    game = BigvilleGame(w, autonomous=True)
    game.step()
    assert game.backends[H].last_choice.get("reason") == "unlock_with_key"
    assert not _locked(w)


def test_an_unlocked_store_keeps_its_stock_for_everyone():
    w, _cell = _town()
    assert any(o["action"] == "fetch" and o.get("stock_source") == "town" for o in w._actor_options(A))
    assert w.major_action(A, "fetch", kind="bread", amount=1.0) is True
    assert w.inventory_qty(A, "bread") == 1.0 and w.qty("bread") == 9.0
    assert not _locked(w)
