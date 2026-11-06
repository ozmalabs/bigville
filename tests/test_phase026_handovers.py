"""Phase 026: a completed physical handover of coin or goods is a Handover fact, and the Transaction record is gone.

The world records what moved, from whom, to whom, by which action and how much. It does not call a handover a
sale, so a bread-for-coin exchange appears as two handovers that share nothing but a turn.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from domains import bigville_entities as E
from worlds.bigville_world import BigvilleWorld

CELL = (0, 8)
ROOT = Path(__file__).resolve().parents[1]
HANDOVER_KEYS = {"turn", "kind", "good", "quantity", "from", "from_kind", "to", "to_kind"}


def _world(*names):
    """Each named resident stands on CELL with no coin and no stock."""
    w = BigvilleWorld()
    for name in names:
        w.add_actor(name, role="resident")
        w.set_coin(name, 0)
        w._move_actor_to(name, CELL)
    return w


def _handovers(world):
    return [dict(world.eng.node(node)["attrs"]) for node in world._handovers.values()]


def _summary(world):
    return [(h["kind"], h["good"], h["quantity"], h["from_kind"], h["from"], h["to_kind"], h["to"])
            for h in _handovers(world)]


def test_bread_for_coin_is_two_unrelated_handovers_with_no_trade_field():
    w = _world("Ann", "Ben")
    w.set_stock("bread", 5)
    w.stock_person("Ann", "bread", 1, price=2.0)
    w.set_coin("Ben", 5)
    before = len(_handovers(w))
    assert w.give("Ann", "Ben", "bread", 1) is True
    assert w.give("Ben", "Ann", "coin", 2) is True

    new = _handovers(w)[before:]
    assert [(h["kind"], h["good"], h["from"], h["to"]) for h in new] == [
        ("give", "bread", "Ann", "Ben"), ("give", "coin", "Ben", "Ann")]
    for handover in new:
        assert set(handover) == HANDOVER_KEYS, "a handover holds only its physical facts"
        assert handover["quantity"] > 0.0
    assert w.coin("Ann") == 2.0 and w.coin("Ben") == 3.0


def test_the_transfer_action_records_its_own_kind_and_a_give_records_give():
    w = _world("Ann", "Ben")
    w.set_stock("grain", 3)
    w.fetch("Ann", "grain", 2)
    assert w.major_action("Ann", "transfer", source="Ann", recipient="Ben", kind="grain", amount=1) is True
    assert w.give("Ann", "Ben", "grain", 1) is True
    kinds = [h["kind"] for h in _handovers(w)]
    assert kinds[-2:] == ["transfer", "give"]


def test_a_refused_handover_records_nothing():
    w = _world("Ann", "Ben")
    w.set_coin("Ann", 1)
    assert w.give("Ann", "Ben", "coin", 5) is False
    assert w.give("Ann", "Ben", "bread", 1) is False
    assert _handovers(w) == []
    assert w._handover_totals["count"] == 0


def test_stock_moves_between_store_container_and_resident_are_recorded_with_their_endpoints():
    w = _world("Ann")
    w.set_stock("grain", 5)
    w.add_container("barrel", holds=("grain",), cell=CELL)
    assert w.fetch("Ann", "grain", 2) is True
    assert w.put("Ann", "barrel", "grain", 1) is True
    assert w.fetch("Ann", "grain", 1, source="barrel") is True
    assert _summary(w) == [
        ("fetch", "grain", 2.0, "store", "store", "actor", "Ann"),
        ("put", "grain", 1.0, "actor", "Ann", "container", "barrel"),
        ("fetch", "grain", 1.0, "container", "barrel", "actor", "Ann"),
    ]


def test_fiscal_coin_moves_are_handovers_with_purse_and_actor_endpoints():
    w = _world("Ada", "Tam", "Lord", "Hal")
    w.add_actor("Ivy", role="clerk")
    w._move_actor_to("Ivy", CELL)
    assert w.found_purse("treasury", "Ivy") is not None

    tax = w.assess_obligation("council_tax", "Ada", "treasury", amount=155)
    w.set_coin("Ada", 200)
    assert w.pay_obligation("Ada", tax) is True
    salary = w.assess_obligation("treasury_salaries", "treasury", "Lord", amount=30)
    assert w.pay_obligation("Ivy", salary) is True, "the tax just paid into the treasury covers the salary"
    rent = w.assess_obligation("hired_collection", "Tam", "Lord", amount=25, collector="Hal")
    w.set_coin("Tam", 30)
    assert w.collect("Hal", rent) is True
    assert w.deliver_collected("Hal", rent, 8000) is True

    assert _summary(w) == [
        ("pay_obligation", "coin", 155.0, "actor", "Ada", "purse", "treasury"),
        ("pay_obligation", "coin", 30.0, "purse", "treasury", "actor", "Lord"),
        ("collect", "coin", 25.0, "actor", "Tam", "actor", "Hal"),
        ("deliver_collected", "coin", 20.0, "actor", "Hal", "actor", "Lord"),
    ]
    assert len(w._transactions) == 4, "the fiscal count covers every fiscal coin handover"


def test_a_purse_paying_out_is_a_purse_endpoint():
    w = _world("Ada")
    w.add_actor("Ivy", role="clerk")
    w._move_actor_to("Ivy", CELL)
    assert w.found_purse("treasury", "Ivy") is not None
    w.set_coin("Ada", 0)
    purse = w._purse_node("treasury")
    w.eng.set_attr(purse, "coin", 40.0)
    salary = w.assess_obligation("treasury_salaries", "treasury", "Ada", amount=30)
    assert w.pay_obligation("Ivy", salary) is True
    assert _summary(w)[-1] == ("pay_obligation", "coin", 30.0, "purse", "treasury", "actor", "Ada")


def test_the_report_counts_handovers_by_good_kind_and_endpoint_and_has_no_transactions_key():
    w = _world("Ann", "Ben")
    w.set_stock("bread", 5)
    w.stock_person("Ann", "bread", 1, price=2.0)
    w.give("Ann", "Ben", "bread", 1)
    w.set_coin("Ben", 5)
    w.give("Ben", "Ann", "coin", 2)
    economy = w.report(sample_size=2, seed=1)["economy"]

    assert "transactions" not in economy
    assert economy["handovers"]["count"] == 3
    assert economy["handovers"]["by_good"]["coin"] == {"count": 1, "quantity": 2.0}
    assert economy["handovers"]["by_good"]["bread"] == {"count": 2, "quantity": 2.0}
    assert economy["handovers"]["by_kind"]["give"] == {"count": 2, "quantity": 3.0}
    assert economy["handovers"]["by_endpoint"]["actor->actor"] == {"count": 2, "quantity": 3.0}
    assert economy["handovers"]["by_endpoint"]["store->actor"] == {"count": 1, "quantity": 1.0}


def test_the_series_reports_handover_count_and_coin_handed_over():
    w = _world("Ann", "Ben")
    w.set_coin("Ben", 5)
    w.give("Ben", "Ann", "coin", 2)
    current = w.report(sample_size=2, seed=1)["series"]["current"]
    assert current["handovers"] == 1.0
    assert current["coin_handed_over"] == 2.0
    assert "transactions" not in current and "transaction_value" not in current


def test_the_log_keeps_the_newest_handovers_while_the_counts_stay_cumulative(monkeypatch):
    w = _world("Ann", "Ben")
    monkeypatch.setattr(E, "HANDOVER_LOG_LIMIT", 3)
    w.set_coin("Ben", 10)
    for _ in range(5):
        assert w.give("Ben", "Ann", "coin", 1) is True
        assert w.give("Ann", "Ben", "coin", 1) is True
    assert len(w._handovers) == 3
    assert [h["quantity"] for h in _handovers(w)] == [1.0, 1.0, 1.0]
    assert w._handover_totals["count"] == 10
    assert len(w._handovers) == len(w.eng.neighbours(w._town, "has_handover"))
    assert w.report(sample_size=2, seed=1)["economy"]["handovers"]["count"] == 10


def test_the_transaction_count_never_shrinks_when_old_handovers_are_dropped(monkeypatch):
    w = _world("Ann", "Ben")
    monkeypatch.setattr(E, "HANDOVER_LOG_LIMIT", 1)
    w.add_actor("Ivy", role="clerk")
    w._move_actor_to("Ivy", CELL)
    assert w.found_purse("treasury", "Ivy") is not None
    w.set_coin("Ben", 10)
    tax = w.assess_obligation("council_tax", "Ben", "treasury", amount=2)
    assert w.pay_obligation("Ben", tax) is True
    assert len(w._transactions) == 1
    w.give("Ben", "Ann", "coin", 1)
    w.give("Ann", "Ben", "coin", 1)
    assert len(w._handovers) == 1
    assert len(w._transactions) == 1, "a count of fiscal handovers, not the retained log"


def test_an_unknown_handover_kind_is_a_programming_error():
    w = _world("Ann", "Ben")
    with pytest.raises(ValueError, match="unknown handover kind"):
        w._record_handover("barter", "bread", 1.0, ("actor", "Ann"), ("actor", "Ben"))


def test_every_handover_kind_the_world_source_names_is_in_the_pack_table():
    source = (ROOT / "worlds" / "bigville_world.py").read_text(encoding="utf-8")
    named = set(re.findall(r'_record_handover\(\s*"(\w+)"', source))
    named |= set(re.findall(r'handover_kind="(\w+)"', source))
    assert named, "the source names some handover kinds"
    assert named <= set(E.HANDOVER_KINDS), named - set(E.HANDOVER_KINDS)


def test_the_self_test_is_clean_for_the_handover_tables():
    report = E.check_consistency()
    assert report["errors"] == []
    assert not [w for w in report["warnings"] if "HANDOVER" in w]


def test_the_self_test_reports_a_handover_log_limit_below_one(monkeypatch):
    monkeypatch.setattr(E, "HANDOVER_LOG_LIMIT", 0)
    errors = E.check_consistency()["errors"]
    assert any("HANDOVER_LOG_LIMIT" in e for e in errors)


def test_the_self_test_reports_an_endpoint_kind_missing_from_the_table(monkeypatch):
    monkeypatch.setattr(E, "HANDOVER_ENDPOINTS",
                        {k: v for k, v in E.HANDOVER_ENDPOINTS.items() if k != "merchant"})
    errors = E.check_consistency()["errors"]
    assert any("needs the endpoint kind 'merchant'" in e for e in errors)
