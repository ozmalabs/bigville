"""Phase 041: physical coin and safes.

A resident's own coin is their purse. Coin moves into a lockable container (a safe) or a fiscal purse with put, and
back with fetch. A container opens by its lock (Phase 030), so a closed safe refuses and a dual-key safe opens only
after two distinct keyholders have turned their keys. A purse opens only to its holder. Stored coin is not carried,
and a resident's own coin adds COIN_WEIGHT per coin to the carried weight. Coin is conserved across every move, and
the report's economy section counts where the coin is.
"""
from __future__ import annotations

from bigville.reporting import SimulationReporter
from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld as World

A, H, CLERK = "Ada", "Hal", "Cora"


def _town(*, tick=False):
    """Two residents on the store cell and a clerk. With `tick`, the turn clock runs and a major action is claimed
    for the turn. Without it, the turn-only position and slot checks are off."""
    w = World(autonomous_actors=False)
    cell = w.map_position_node(w._store)
    w.add_actor(A, role="hand", home_cell=cell)
    w.add_actor(H, role="hand", home_cell=cell)
    w.add_actor(CLERK, role="clerk", home_cell=cell)
    for name in (A, H, CLERK):
        w._move_actor_to(name, cell)
    if tick:
        w.tick()
        w.mark_turn_start()
    return w


def _reason(w, name):
    """The code of the last refused attempt. The turn clock is off in most tests, so the published outcome is not
    kept; the world's own refusal code is read instead, as the Phase 030 tests do."""
    return w._refusal_code


def _total_coin(w):
    """Every coin the town holds: residents' purses, stored in containers, in fiscal purses, and the store."""
    residents = sum(w.coin(name) for name in w._actors)
    containers = sum(w.contents(name, "coin") for name in w._containers)
    purses = sum(float(w.eng.node(node)["attrs"].get("coin", 0.0)) for node in w.eng.nodes("Purse"))
    return round(residents + containers + purses + w.qty("coin"), 4)


def test_coin_put_into_an_open_safe_leaves_the_resident_and_is_fetched_back_whole():
    w = _town()
    w.add_container("safe", kind="safe", holds="coin", lock_id=7.0, locked=False)
    w.set_coin(A, 10.0)
    assert w.put(A, "safe", "coin", 4.0) is True
    assert w.coin(A) == 6.0 and w.contents("safe", "coin") == 4.0, "the coin leaves the purse and is stored"
    assert w.fetch(A, "coin", 4.0, source="safe") is True
    assert w.coin(A) == 10.0 and w.contents("safe", "coin") == 0.0, "fetched back whole"


def test_a_closed_safe_refuses_put_and_fetch_and_a_keyholder_opens_it():
    w = _town()
    w.add_container("safe", kind="safe", holds="coin", lock_id=7.0, locked=True)
    w.give_key(H, opens=7.0)
    w.set_coin(A, 5.0)
    assert w.put(A, "safe", "coin", 5.0) is False and _reason(w, A) == "container_locked"
    assert w.coin(A) == 5.0 and w.contents("safe", "coin") == 0.0, "a refused put moves nothing"
    w.set_coin(H, 3.0)
    assert w.put(H, "safe", "coin", 3.0) is True, "the keyholder opens the safe and stores coin"
    assert w.fetch(A, "coin", 1.0, source="safe") is False and _reason(w, A) == "container_locked"
    assert w.contents("safe", "coin") == 3.0 and w.coin(A) == 5.0


def test_a_dual_key_safe_opens_only_after_two_distinct_keyholders_turn_their_keys():
    w = _town()
    w.add_container("vault", kind="safe", holds="coin", lock_id=9.0, locked=True, keys_required=2)
    w.give_key(H, opens=9.0)
    w.give_key(A, opens=9.0)
    w.set_coin(H, 5.0)
    assert w.unlock(H, "vault") is True and w.is_locked("vault"), "one key turned is not enough"
    assert w.put(H, "vault", "coin", 5.0) is False and _reason(w, H) == "container_locked"
    assert w.unlock(H, "vault") is False and w._refusal_code == "already_authorised", "one person, one turn"
    assert w.unlock(A, "vault") is True and not w.is_locked("vault"), "the second keyholder opens it"
    assert w.put(H, "vault", "coin", 5.0) is True and w.contents("vault", "coin") == 5.0


def test_coin_is_conserved_across_gives_safe_moves_and_purse_moves():
    w = _town()
    w.add_container("safe", kind="safe", holds="coin", lock_id=7.0, locked=False)
    assert w.found_purse("treasury", CLERK) is not None
    w.set_coin(A, 12.0); w.set_coin(H, 4.0); w.set_coin(CLERK, 4.0)
    start = _total_coin(w)
    assert start == 20.0
    assert w.give(A, H, "coin", 3.0) is True
    assert w.put(H, "safe", "coin", 5.0) is True
    assert w.put(CLERK, "treasury", "coin", 4.0) is True
    assert w.fetch(H, "coin", 2.0, source="safe") is True
    assert w.fetch(CLERK, "coin", 1.0, source="treasury") is True, "the holder takes coin from the purse"
    assert _total_coin(w) == start
    assert w.coin(A) == 9.0 and w.coin(H) == 4.0 and w.coin(CLERK) == 1.0
    assert w.contents("safe", "coin") == 3.0


def test_a_purse_refuses_anyone_but_its_holder_and_records_the_deposit():
    w = _town()
    purse = w.found_purse("treasury", CLERK)
    w.set_coin(A, 6.0)
    assert w.put(A, "treasury", "coin", 3.0) is False and _reason(w, A) == "container_locked"
    assert w.eng.node(purse)["attrs"]["coin"] == 0.0
    w.set_coin(CLERK, 2.0)
    assert w.put(CLERK, "treasury", "coin", 2.0) is True
    assert w.eng.node(purse)["attrs"]["coin"] == 2.0 and w.eng.node(purse)["attrs"]["recorded"] == 2.0
    assert w.fetch(CLERK, "coin", 1.0, source="treasury") is True and w.coin(CLERK) == 1.0


def test_stored_coin_is_not_carried_and_a_resident_purse_weighs_coin_weight_per_coin(monkeypatch):
    # A pile's weight is read when the container is wired (as for every kind), so the weight is set first.
    monkeypatch.setattr(E, "COIN_WEIGHT", 0.01)
    w = _town()
    w.add_container("safe", kind="safe", holds="coin", lock_id=7.0, locked=False)
    w.set_coin(A, 100.0)
    assert w.carried_weight(A) == 1.0, "a purse of 100 coin at 0.01 kg each"
    assert w.put(A, "safe", "coin", 60.0) is True
    assert w.carried_weight(A) == 0.4, "stored coin is not carried: only the 40 in the purse count"
    assert w.contents_weight("safe") == 0.6, "the stored coin is the container's load"


def test_with_the_founding_weight_a_purse_carries_nothing_extra():
    w = _town()
    w.add_container("safe", kind="safe", holds="coin", lock_id=7.0, locked=False)
    w.set_coin(A, 100.0)
    assert E.COIN_WEIGHT == 0.0, "APPROX founding value: coin adds no load"
    assert w.carried_weight(A) == 0.0


def test_a_full_container_refuses_coin_beyond_its_load(monkeypatch):
    monkeypatch.setattr(E, "COIN_WEIGHT", 1.0)
    w = _town()
    w.add_container("safe", kind="safe", holds="coin", lock_id=0.0, locked=False)
    node = w._containers["safe"][0]
    w.eng.set_attr(node, "max_load", 5.0)
    w.set_coin(A, 10.0)
    assert w.put(A, "safe", "coin", 6.0) is False and _reason(w, A) == "full"
    assert w.coin(A) == 10.0 and w.contents("safe", "coin") == 0.0
    assert w.put(A, "safe", "coin", 5.0) is True and w.contents("safe", "coin") == 5.0


def test_coin_put_and_fetch_are_major_actions_and_use_the_turn_slot():
    w = _town(tick=True)
    w.add_container("safe", kind="safe", holds="coin", lock_id=0.0, locked=False)
    w.set_coin(A, 8.0)
    assert w.major_action(A, "put", container="safe", kind="coin", amount=3.0) is True
    assert w.contents("safe", "coin") == 3.0 and w.coin(A) == 5.0
    assert w.major_action(A, "fetch", kind="coin", amount=1.0, source="safe") is False
    assert w.last_outcome(A)["reason"] == "slot_used", "a second major action in the turn is refused"


def test_the_report_counts_where_the_coin_is():
    w = _town()
    w.add_container("safe", kind="safe", holds="coin", lock_id=7.0, locked=False)
    w.found_purse("treasury", CLERK)
    w.set_coin(A, 7.0); w.set_coin(H, 2.0); w.set_coin(CLERK, 0.0)
    assert w.put(A, "safe", "coin", 3.0) is True
    coin = SimulationReporter(w).economy()["coin"]
    assert coin == {"resident_purses": 6.0, "stored_in_containers": 3.0, "in_purses": 0.0, "in_store": 0.0,
                    "total": 9.0}
    assert coin["total"] == _total_coin(w)
