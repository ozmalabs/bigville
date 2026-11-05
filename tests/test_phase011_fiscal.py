"""Phase 011: fiscal institutions as data, and the physical purse and obligation actions.

The eight seed files stay as they are. These tests check that every rule in them is mapped to a data entry
or to the backend, that the world's whole-coin rounding matches the seeds' own formula, and that the world
moves coin only when the parties are present and the coin is there. A missed payment is recorded and
nothing else happens.
"""
from __future__ import annotations

import json
import math
import os
from collections import Counter

import pytest

from domains import bigville_entities as E
from domains import shared_frames
from domains.world_affordances import round_bp
from worlds.bigville_world import BigvilleWorld

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_DIR = os.path.join(ROOT, "bigville", "seeds")
EIGHT_SEEDS = ("bigville_fisc_state", "bigville_clerk_treasurer", "bigville_coll_collect", "bigville_fin_tenure",
               "bigville_fisc_church", "bigville_labour", "bigville_econloop", "bigville_school_fund")


def _seed_rules():
    """Rule name -> the seed file it is written in, for the eight seeds."""
    found = {}
    for seed in EIGHT_SEEDS:
        with open(os.path.join(SEED_DIR, seed + ".json"), encoding="utf-8") as fh:
            for rule in json.load(fh)["rules"]:
                found.setdefault(rule["name"], []).append(seed)
    return found


# ------------------------------------------------------------------ rule mapping
def test_every_seed_rule_is_mapped_exactly_once_to_an_institution_or_the_backend():
    seed_rules = _seed_rules()
    assert len(seed_rules) == 44 and all(len(files) == 1 for files in seed_rules.values())
    mapped = Counter()
    for spec in shared_frames.FISCAL_INSTITUTIONS.values():
        mapped.update(spec["seed_rules"])
    mapped.update(row["rule"] for row in shared_frames.FISCAL_BACKEND_OWNED)
    assert {rule: n for rule, n in mapped.items() if n != 1} == {}
    assert set(mapped) - set(seed_rules) == set(), "mapped rules that no seed file contains"
    assert set(seed_rules) - set(mapped) == set(), "seed rules mapped to nothing"


def test_each_mapped_rule_is_listed_under_a_seed_file_its_entry_names():
    seed_rules = _seed_rules()
    for name, spec in shared_frames.FISCAL_INSTITUTIONS.items():
        assert set(spec["seeds"]) <= set(EIGHT_SEEDS), name
        for rule in spec["seed_rules"]:
            assert set(seed_rules[rule]) <= set(spec["seeds"]), f"{name} maps {rule} to the wrong seed"
    for row in shared_frames.FISCAL_BACKEND_OWNED:
        assert seed_rules[row["rule"]] == [row["seed"]], row["rule"]
        assert row["owner"] == "backend" and row["reason"].strip()


def test_the_test_hamlet_pack_has_no_fiscal_rules_to_map():
    from domains.data_view import entities
    hamlet = entities("test_hamlet")
    assert hamlet.FISCAL_INSTITUTIONS == {} and hamlet.FISCAL_BACKEND_OWNED == []
    assert hamlet.FISCAL_PURSES == {} and hamlet.FISCAL_ACTIONS == {}
    report = hamlet.check_consistency()
    assert report["errors"] == [] and report["warnings"] == []


# ------------------------------------------------------------------ rounding
def _find_term(term, kind):
    """The first sub-term of type `kind` under `term` (depth first)."""
    if isinstance(term, dict):
        if term.get("type") == kind:
            return term
        for value in term.values():
            found = _find_term(value, kind)
            if found is not None:
                return found
    elif isinstance(term, list):
        for value in term:
            found = _find_term(value, kind)
            if found is not None:
                return found
    return None


def _seed_idiv(rule_name, effect_key):
    """The IDiv term the seed writes into `effect_key` (a set_attr effect of the named rule)."""
    with open(os.path.join(SEED_DIR, _seed_file_of(rule_name) + ".json"), encoding="utf-8") as fh:
        rule = next(r for r in json.load(fh)["rules"] if r["name"] == rule_name)
    for effect in rule["effects"]:
        if effect[0] == "set_attr" and effect[2] == effect_key:
            found = _find_term(effect[3], "IDiv")
            if found is not None:
                return found
    raise AssertionError(f"{rule_name} has no IDiv in its {effect_key} effect")


def _seed_file_of(rule_name):
    return _seed_rules()[rule_name][0]


def _eval_seed_term(term, env):
    """Evaluate the seed DSL arithmetic used by these rules: Lit, Attr, Plus, Times, Minus, IDiv."""
    if isinstance(term, dict) and "__term__" in term:
        term = term["__term__"]
    kind = term["type"]
    if kind == "Lit":
        return int(term["value"])
    if kind == "Attr":
        return int(env[term["key"]])
    if kind == "Plus":
        return sum(_eval_seed_term(item, env) for item in term["items"])
    if kind == "Times":
        product = 1
        for item in term["items"]:
            product *= _eval_seed_term(item, env)
        return product
    if kind == "Minus":
        return _eval_seed_term(term["a"], env) - _eval_seed_term(term["b"], env)
    if kind == "IDiv":
        return _eval_seed_term(term["a"], env) // _eval_seed_term(term["b"], env)
    raise AssertionError(f"unexpected seed term {kind}")


ROUND_CASES = [(0, 0), (1, 5000), (3, 5000), (5, 1000), (2, 2500), (15, 333), (20, 5000), (7, 10000),
               (999, 1), (1234, 1550), (25, 8000), (1000, 1550), (10**6, 3333)]


@pytest.mark.parametrize("amount,bp", ROUND_CASES)
def test_round_bp_matches_the_seeds_integer_formula(amount, bp):
    tax = _eval_seed_term(_seed_idiv("fs_collect", "funds"), {"taxable": amount, "tax_rate_bp": bp})
    delivery = _eval_seed_term(_seed_idiv("bc_deliver", "coin"), {"collected": amount, "deliver_bp": bp})
    assert round_bp(amount, bp) == tax == delivery == (amount * bp + 5000) // 10000


def test_round_bp_rounds_halves_up_and_below_half_down():
    assert round_bp(1, 5000) == 1        # 0.5 -> 1
    assert round_bp(3, 5000) == 2        # 1.5 -> 2
    assert round_bp(5, 1000) == 1        # 0.5 -> 1
    assert round_bp(15, 333) == 0        # 0.4995 -> 0
    assert round_bp(1000, 1550) == 155   # exact


@pytest.mark.parametrize("amount,bp", [(1.5, 100), (-1, 100), (10, 10001), (10, -1), (True, 100)])
def test_round_bp_refuses_fractions_negative_amounts_and_bad_rates(amount, bp):
    with pytest.raises(ValueError):
        round_bp(amount, bp)


# ------------------------------------------------------------------ the physical actions
CELL = (0, 8)
NEXT_CELL = (0, 9)


def _world():
    """Ada and Tam are residents, Lord the landlord, Hal a hired collector, and Ivy the clerk who holds the
    treasury. All stand on one cell with no coin unless a test gives some."""
    w = BigvilleWorld()
    w.add_actor("Ada", role="resident")
    w.add_actor("Tam", role="resident")
    w.add_actor("Lord", role="resident")
    w.add_actor("Hal", role="resident")
    w.add_actor("Ivy", role="clerk")
    for name in ("Ada", "Tam", "Lord", "Hal", "Ivy"):
        w.set_coin(name, 0)
        w._move_actor_to(name, CELL)
    assert w.found_purse("treasury", "Ivy") is not None
    return w


def _attrs(world, node):
    return world.eng.node(node)["attrs"]


def _total_coin(world):
    people = sum(world.coin(name) for name in ("Ada", "Tam", "Lord", "Hal", "Ivy"))
    return people + _attrs(world, world._purse_node("treasury"))["coin"]


def test_a_tax_is_paid_by_a_co_located_payer_into_the_treasury():
    w = _world()
    tax = w.assess_obligation("council_tax", "Ada", "treasury", base=1000, rate_bp=1550)
    assert _attrs(w, tax)["amount"] == 155.0
    w.set_coin("Ada", 200)
    total = _total_coin(w)
    assert w.pay_obligation("Ada", tax) is True
    assert w.coin("Ada") == 45.0
    purse = _attrs(w, w._purse_node("treasury"))
    assert purse["coin"] == 155.0 and purse["recorded"] == 155.0
    assert _attrs(w, tax)["paid"] == 155.0 and _attrs(w, tax)["periods_paid"] == 1.0
    assert _attrs(w, tax)["arrears"] == 0.0
    assert _total_coin(w) == total, "coin is conserved across the payment"


def test_a_tax_payment_is_refused_without_coin_and_the_shortfall_is_recorded_as_arrears():
    w = _world()
    tax = w.assess_obligation("council_tax", "Ada", "treasury", amount=155)
    w.set_coin("Ada", 10)
    assert w.pay_obligation("Ada", tax) is False
    assert w.coin("Ada") == 10.0
    assert _attrs(w, w._purse_node("treasury"))["coin"] == 0.0
    assert _attrs(w, tax)["arrears"] == 1.0 and _attrs(w, tax)["paid"] == 0.0


def test_a_tax_payment_is_refused_away_from_the_clerk_and_records_nothing():
    w = _world()
    tax = w.assess_obligation("council_tax", "Ada", "treasury", amount=155)
    w.set_coin("Ada", 200)
    w._move_actor_to("Ada", NEXT_CELL)
    before = dict(_attrs(w, tax))
    assert w.pay_obligation("Ada", tax) is False
    assert w.coin("Ada") == 200.0
    assert _attrs(w, w._purse_node("treasury"))["coin"] == 0.0
    assert dict(_attrs(w, tax)) == before, "a payer who is not reached leaves no record"


def test_only_the_debtor_or_the_purse_holder_can_make_a_payment():
    w = _world()
    tax = w.assess_obligation("council_tax", "Ada", "treasury", amount=50)
    w.set_coin("Ada", 100)
    assert w.pay_obligation("Tam", tax) is False, "a bystander cannot pay Ada's tax"
    assert w.coin("Ada") == 100.0


def test_a_missed_rent_becomes_arrears_with_no_eviction_and_no_other_change():
    w = _world()
    rent = w.assess_obligation("rent_and_tenancy", "Tam", "Lord", amount=40)
    w.set_coin("Tam", 10)
    before = {node: dict(w.eng.node(node)["attrs"]) for node in w.eng.nodes()}
    assert w.collect("Lord", rent) is False
    after = {node: dict(w.eng.node(node)["attrs"]) for node in w.eng.nodes()}
    assert set(after) == set(before), "no node was added or removed"
    changed = {node for node in before if before[node] != after[node]}
    assert changed == {rent}, "only the obligation changed"
    assert after[rent]["arrears"] == 1.0 and after[rent]["paid"] == 0.0
    assert w.coin("Tam") == 10.0 and w.coin("Lord") == 0.0
    assert w.actor_position("Tam") == CELL and "Tam" in w._actors
    assert "evicted" not in after[rent] and "foreclosed" not in after[rent]

    w.set_coin("Tam", 50)
    assert w.collect("Lord", rent) is True
    assert _attrs(w, rent)["paid"] == 40.0 and _attrs(w, rent)["arrears"] == 1.0


def test_a_collector_reaches_only_a_debtor_on_its_own_cell():
    w = _world()
    rent = w.assess_obligation("rent_and_tenancy", "Tam", "Lord", amount=40)
    w.set_coin("Tam", 100)
    w._move_actor_to("Tam", NEXT_CELL)
    assert w.collect("Lord", rent) is False
    assert _attrs(w, rent)["arrears"] == 0.0 and w.coin("Tam") == 100.0


def test_a_hired_collector_holds_coin_and_delivers_a_share_keeping_the_skim():
    w = _world()
    rent = w.assess_obligation("hired_collection", "Tam", "Lord", amount=25, collector="Hal")
    w.set_coin("Tam", 30)
    total = _total_coin(w)
    assert w.collect("Hal", rent) is True
    assert w.coin("Tam") == 5.0 and w.coin("Hal") == 25.0
    assert _attrs(w, rent)["held"] == 25.0
    assert w.deliver_collected("Ada", rent, 8000) is False, "only the named collector can deliver"
    assert w.deliver_collected("Hal", rent, 8000) is True
    assert w.coin("Lord") == 20.0 and w.coin("Hal") == 5.0
    attrs = _attrs(w, rent)
    assert attrs["held"] == 0.0 and attrs["delivered"] == 20.0 and attrs["skimmed"] == 5.0
    assert _total_coin(w) == total, "coin is conserved across collection and delivery"


def test_a_hired_collector_cannot_deliver_away_from_the_landlord():
    w = _world()
    rent = w.assess_obligation("hired_collection", "Tam", "Lord", amount=25, collector="Hal")
    w.set_coin("Tam", 30)
    assert w.collect("Hal", rent) is True
    w._move_actor_to("Hal", NEXT_CELL)
    assert w.deliver_collected("Hal", rent, 8000) is False
    assert _attrs(w, rent)["held"] == 25.0 and w.coin("Lord") == 0.0


def test_a_purse_pays_out_to_a_co_located_resident():
    w = _world()
    w.set_coin("Ivy", 0)
    treasury = w._purse_node("treasury")
    w.eng.set_attr(treasury, "coin", 60.0)
    w.eng.set_attr(treasury, "recorded", 60.0)
    salary = w.assess_obligation("treasury_salaries", "treasury", "Ada", amount=30)
    assert w.pay_obligation("Ivy", salary) is True
    assert _attrs(w, treasury)["coin"] == 30.0 and _attrs(w, treasury)["recorded"] == 30.0
    assert w.coin("Ada") == 30.0
    w.eng.set_attr(treasury, "coin", 5.0)
    assert w.pay_obligation("Ivy", salary) is False
    assert _attrs(w, salary)["arrears"] == 1.0, "a short treasury leaves the salary unpaid and recorded"


def test_purses_open_only_for_their_holder_role_and_once():
    w = _world()
    assert w.found_purse("church_funds", "Ada") is None, "a resident who is not a pastor"
    assert w.found_purse("parish_box", "Ivy") is None, "a purse the pack does not name"
    assert w.found_purse("treasury", "Ivy") is None, "a purse already open"


def test_an_obligation_is_refused_when_its_parties_are_unknown_or_the_figures_are_not_whole_coins():
    w = _world()
    assert w.assess_obligation("not_an_institution", "Ada", "treasury", amount=1) is None
    assert w.assess_obligation("council_tax", "Ada", "nobody", amount=1) is None
    assert w.assess_obligation("council_tax", "treasury", "treasury", amount=1) is None
    assert w.assess_obligation("council_tax", "Ada", "Ada", amount=1) is None
    assert w.assess_obligation("council_tax", "Ada", "treasury", amount=1.5) is None
    assert w.assess_obligation("council_tax", "Ada", "treasury", base=1000, rate_bp=10001) is None
    assert w.assess_obligation("council_tax", "Ada", "treasury") is None, "neither an amount nor a base and rate"
    assert w.assess_obligation("hired_collection", "Tam", "Lord", amount=5, collector="treasury") is None
    assert w.assess_obligation("hired_collection", "Tam", "Lord", amount=5, collector="Tam") is None


def test_a_major_action_spends_the_turn_slot_once():
    w = _world()
    tax = w.assess_obligation("council_tax", "Ada", "treasury", amount=10)
    w.set_coin("Ada", 100)
    assert w.major_action("Ada", "pay_obligation", obligation=tax) is True
    assert w.major_action("Ada", "pay_obligation", obligation=tax) is False, "the slot is already used"
    assert w.coin("Ada") == 90.0


# ------------------------------------------------------------------ the self-test covers the new tables
def test_the_self_test_is_clean_and_names_the_fiscal_tables():
    report = E.check_consistency()
    assert report["errors"] == [] and report["warnings"] == []
    assert any(line.startswith("FISCAL: 9 institutions, 44 seed rules mapped (20 backend-owned), 2 purses")
               for line in report["info"])


def test_the_self_test_reports_a_rule_mapped_twice(monkeypatch):
    monkeypatch.setattr(E, "FISCAL_BACKEND_OWNED",
                        list(E.FISCAL_BACKEND_OWNED) + [{"rule": "fs_graft", "seed": "bigville_fisc_state",
                                                         "owner": "backend", "reason": "duplicate"}])
    errors = E.check_consistency()["errors"]
    assert any("'fs_graft' is mapped more than once" in e for e in errors)


def test_the_self_test_reports_a_seed_rule_that_nothing_maps(monkeypatch):
    monkeypatch.setattr(E, "FISCAL_BACKEND_OWNED",
                        [row for row in E.FISCAL_BACKEND_OWNED if row["rule"] != "lm_switch"])
    errors = E.check_consistency()["errors"]
    assert any("seed bigville_labour: rule 'lm_switch' is not mapped" in e for e in errors)


def test_every_fiscal_action_is_a_world_method_with_a_description():
    for name, spec in E.FISCAL_ACTIONS.items():
        assert callable(getattr(BigvilleWorld, name, None)), f"{name} is not a BigvilleWorld method"
        assert spec["description"].strip()
    for name in E.FISCAL_PURSES:
        assert E.FISCAL_PURSES[name]["holder_role"] in (set(E.GOVERNANCE_OFFICES) | set(E.JOBS))
