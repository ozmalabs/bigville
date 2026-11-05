"""Phase 014: the world's mechanics parameters are read from the data pack.

The moved constants (clock, town and resident starting state, care and starvation, default prices,
document literacy gates, engine and resident seed lists, relationship kinds) come from the pack.
A child pack that extends bigville and overrides one of them changes the world's behaviour with no
code change. The default values are the ones the code had before the move.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "runners", "dsl", "python"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from domains import bigville_entities as DEFAULT          # noqa: E402
from domains.data_view import entities                     # noqa: E402
from worlds.bigville_world import BigvilleOcelotActor, BigvilleWorld   # noqa: E402

MOVED = ("TIME", "TOWN_INITIAL", "ACTOR_DEFAULTS", "CARE", "PRICE_DEFAULTS", "DOCUMENT_LITERACY",
         "ENGINE_SEEDS", "RESIDENT_SEEDS", "RESIDENT_CONCEPT_SEEDS", "RELATIONSHIP_KINDS",
         "RELATIONSHIP_DEFAULT")


def _child(tmp_path, tables):
    """A child pack that extends bigville. `tables` maps a table name to (value, merge): a merged dict
    updates the parent's dict key by key, and anything else replaces the parent's table."""
    root = tmp_path / "child_pack"
    (root / "world").mkdir(parents=True)
    (root / "frames").mkdir()
    entries = []
    for name, (value, merge) in tables.items():
        rel = f"world/{name.lower()}.json"
        (root / rel).write_text(json.dumps({"_doc": "phase 014 test override", "_types": {},
                                            "tables": {name: value}}), encoding="utf-8")
        entry = {"name": name, "file": rel}
        if merge:
            entry["merge"] = True
        entries.append(entry)
    (root / "pack.json").write_text(json.dumps({
        "format": 1, "name": "child_pack", "version": 1, "description": "phase 014 test child of bigville",
        "extends": "bigville", "tables": entries}), encoding="utf-8")
    return str(root)


def _forge_ticks(world):
    """Start a 90-minute forge_knife at the forge and count the ticks until the smith is free."""
    world.set_stock("iron", 5)
    world.set_stock("charcoal", 5)
    x, y, _fw, _fh = world._building_sites["forge"]
    world._move_actor_to("Wayland", (x, y))
    assert world.start("Wayland", "forge_knife")
    ticks = 0
    while world.busy("Wayland"):
        world.tick(1)
        ticks += 1
        assert ticks < 100, "the forge job never finished"
    return ticks


def test_the_default_values_are_the_ones_the_code_had_before_the_move():
    assert DEFAULT.TIME["minutes_per_tick"] == 15.0
    assert DEFAULT.TIME["ticks_per_day"] == 96 and DEFAULT.TIME["ticks_per_period"] == 96
    assert DEFAULT.TIME["days_per_year"] == 360 and DEFAULT.TIME["days_per_week"] == 7
    assert DEFAULT.TOWN_INITIAL["hour"] == 6.0 and DEFAULT.TOWN_INITIAL["season"] == "spring"
    assert DEFAULT.TOWN_INITIAL["weather"] == "clear" and DEFAULT.TOWN_INITIAL["temperature"] == 15.0
    assert DEFAULT.TOWN_INITIAL["firewood_demand"] == 1.0 and DEFAULT.TOWN_INITIAL["year"] == 1.0
    actor = DEFAULT.ACTOR_DEFAULTS
    assert (actor["skill"], actor["station"], actor["coin"], actor["reputation"], actor["age"]) == \
        (0.7, "educated", 10.0, 0.5, 30.0)
    assert actor["inventory_max_load"] == 50.0 and actor["inventory_capacity"] == 50.0
    assert DEFAULT.CARE["injury_severity"] == 0.25 and DEFAULT.CARE["treat_health_gain"] == 0.25
    assert DEFAULT.CARE["care_injury_relief"] == 0.2 and DEFAULT.CARE["care_health_gain"] == 0.1
    assert DEFAULT.CARE["care_hunger_need"] == 2.0 and DEFAULT.CARE["starve_limit"] == 4.0
    assert DEFAULT.PRICE_DEFAULTS == {"shop_price": 2.0, "shop_is_open": 1, "stock_price": 1.0,
                                      "labour_wage": 2.0}
    assert DEFAULT.DOCUMENT_LITERACY == {"policy": "functional", "law": "educated", "charter": "educated"}
    assert DEFAULT.ENGINE_SEEDS == ["bigville_action_general", "bigville_action_container",
                                    "bigville_action_animal", "bigville_action_merchant",
                                    "bigville_action_life", "bigville_action_decay",
                                    "bigville_action_clothing", "bigville_action_skill",
                                    "bigville_terrain_movement", "bigville_body"]
    assert DEFAULT.RESIDENT_SEEDS == ["bigville_actor_decision", "bigville_speech_decide",
                                      "bigville_loud_comm"]
    assert DEFAULT.RESIDENT_CONCEPT_SEEDS == ["conversation"]
    assert DEFAULT.RELATIONSHIP_KINDS["rival_of"] == {"kind": "feud", "strength": -0.8}
    assert DEFAULT.RELATIONSHIP_DEFAULT == {"kind": "acquaintance", "strength": 0.5}


def test_the_default_world_reads_the_default_pack_and_its_defaults():
    w = BigvilleWorld(autonomous_actors=False)
    assert w.E is DEFAULT
    w.add_actor("Ada", role="hand", home_cell=(1, 1))
    a = w.eng.node(w._actors["Ada"])["attrs"]
    assert a["coin"] == 10.0 and a["reputation"] == 0.5 and a["age"] == 30.0 and a["skill"] == 0.7
    assert a["starve_limit"] == 4.0 and a["health_value"] == 1.0 and a["injury"] == 0.0
    assert a["literacy"] == pytest.approx(DEFAULT.STATION_EDUCATION["educated"]["literacy"])
    assert w.capacity(w._actor_inventories["Ada"]) == 50.0 and w.max_load(w._actor_inventories["Ada"]) == 50.0


def test_the_hamlet_pack_carries_the_same_mechanics_tables():
    hamlet = entities("test_hamlet")
    for name in MOVED:
        assert getattr(hamlet, name) == getattr(DEFAULT, name), name
    assert hamlet.check_consistency()["errors"] == []


def test_a_child_pack_changes_actor_defaults_and_the_tick_length_changes_timed_work(tmp_path):
    child = _child(tmp_path, {"ACTOR_DEFAULTS": ({"coin": 25.0}, True),
                              "TIME": ({"minutes_per_tick": 7.5}, True)})
    kid = entities(child)
    assert kid.ACTOR_DEFAULTS["coin"] == 25.0 and kid.ACTOR_DEFAULTS["skill"] == 0.7, "merged, not replaced"
    assert len(kid.ITEMS) == len(DEFAULT.ITEMS), "tables the child does not list are inherited"
    assert kid.check_consistency()["errors"] == []

    world = BigvilleWorld(data_pack=child, autonomous_actors=False)
    base = BigvilleWorld(autonomous_actors=False)
    for w in (world, base):
        w.add_actor("Wayland", role="smith")
    assert world.eng.node(world._actors["Wayland"])["attrs"]["coin"] == 25.0
    assert base.eng.node(base._actors["Wayland"])["attrs"]["coin"] == 10.0

    # A 90-minute job is 6 ticks at 15 minutes and 12 ticks at 7.5 minutes.
    assert _forge_ticks(base) == 6
    assert _forge_ticks(world) == 12


def test_a_child_pack_changes_the_calendar_day_length(tmp_path):
    child = _child(tmp_path, {"TIME": ({"ticks_per_day": 48}, True)})
    world = BigvilleWorld(data_pack=child, autonomous_actors=False)
    base = BigvilleWorld(autonomous_actors=False)
    world.tick(100)
    base.tick(100)
    assert world.calendar()["day"] == 2.0 and world.calendar()["hour"] == 8.0, "48 ticks a day, 0.5 h a tick"
    assert base.calendar()["day"] == 1.0 and base.calendar()["hour"] == 7.0, "96 ticks a day, 0.25 h a tick"


def test_a_child_pack_changes_care_town_prices_and_the_document_literacy_gate(tmp_path):
    child = _child(tmp_path, {
        "CARE": ({"starve_limit": 2.0}, True),
        "TOWN_INITIAL": ({"firewood_demand": 2.0}, True),
        "PRICE_DEFAULTS": ({"shop_price": 3.5}, True),
        "DOCUMENT_LITERACY": ({"law": "functional"}, True),
    })
    world = BigvilleWorld(data_pack=child, autonomous_actors=False)
    base = BigvilleWorld(autonomous_actors=False)
    for w in (world, base):
        w.add_actor("Ada", role="hand", home_cell=(1, 1))
        w.eng.set_attr(w._actors["Ada"], "hunger", 2.0)
    assert world.eng.node(world._actors["Ada"])["attrs"]["starve_limit"] == 2.0
    assert world._death_cause(world.eng.node(world._actors["Ada"])["attrs"]) == "starvation"
    assert base._death_cause(base.eng.node(base._actors["Ada"])["attrs"]) == "unknown", "4 is the default limit"

    assert world.eng.node(world._town)["attrs"]["firewood_demand"] == 2.0
    assert base.eng.node(base._town)["attrs"]["firewood_demand"] == 1.0

    cell = sorted(world._map_cells)[0]
    world.add_shop("phase014_trade", cell, input_kind="grain", output_kind="flour")
    base.add_shop("phase014_trade", cell, input_kind="grain", output_kind="flour")
    assert world.eng.node(world._shops["phase014_trade"])["attrs"]["price"] == 3.5
    assert base.eng.node(base._shops["phase014_trade"])["attrs"]["price"] == 2.0

    for w in (world, base):
        w.add_actor("Ben", role="hand", literacy=0.5, capability=0.2)
    law = next(iter(base._law_specs))
    policy = next(iter(base._policy_specs))
    assert world.write_document("Ben", law, kind="law") is not None, "the child lets a functional reader write a law"
    assert base.write_document("Ben", law, kind="law") is None, "the default law gate needs education"
    assert world.write_document("Ben", policy, kind="policy") is not None
    assert base.write_document("Ben", policy, kind="policy") is not None, "a policy needs functional literacy"


def test_a_child_pack_changes_injury_and_care_amounts(tmp_path):
    child = _child(tmp_path, {"CARE": ({"injury_severity": 0.5, "care_injury_relief": 0.4,
                                        "care_health_gain": 0.3}, True)})
    world = BigvilleWorld(data_pack=child, autonomous_actors=False)
    base = BigvilleWorld(autonomous_actors=False)
    for w in (world, base):
        w.add_actor("Ada", role="hand")

    world.injure("Ada")
    base.injure("Ada")
    attrs = lambda w: w.eng.node(w._actors["Ada"])["attrs"]     # noqa: E731
    assert attrs(world)["injury"] == pytest.approx(0.5) and attrs(world)["health_value"] == pytest.approx(0.5)
    assert attrs(base)["injury"] == pytest.approx(0.25) and attrs(base)["health_value"] == pytest.approx(0.75)

    assert world.care_for("Ada", "Ada") and base.care_for("Ada", "Ada")
    assert attrs(world)["injury"] == pytest.approx(0.1) and attrs(world)["health_value"] == pytest.approx(0.8)
    assert attrs(base)["injury"] == pytest.approx(0.05) and attrs(base)["health_value"] == pytest.approx(0.85)


def test_a_child_pack_changes_the_engine_and_resident_seed_lists(tmp_path):
    child = _child(tmp_path, {"ENGINE_SEEDS": (["bigville_action_general"], False),
                              "RESIDENT_SEEDS": (["bigville_actor_decision"], False)})
    world = BigvilleWorld(data_pack=child, autonomous_actors=False)
    base = BigvilleWorld(autonomous_actors=False)
    assert "bigville_action_general" in world.eng.seed_manifests
    assert "bigville_body" not in world.eng.seed_manifests, "the child's engine list replaces the parent's"
    assert "bigville_body" in base.eng.seed_manifests

    mind = BigvilleOcelotActor("Ada", data_pack=child)
    assert "bigville_actor_decision" in mind.inner.seed_manifests
    assert "bigville_loud_comm" not in mind.inner.seed_manifests
    assert "bigville_loud_comm" in BigvilleOcelotActor("Ada").inner.seed_manifests, "no pack: the default list"


def test_a_scenario_initial_value_still_overrides_the_pack_town_defaults():
    w = BigvilleWorld(scenario={"id": "phase014", "name": "Phase014", "initial": {"firewood_demand": 3.0}},
                      autonomous_actors=False)
    attrs = w.eng.node(w._town)["attrs"]
    assert attrs["firewood_demand"] == 3.0, "the scenario's initial value wins"
    assert attrs["season"] == "spring" and attrs["hour"] == 6.0, "the rest come from TOWN_INITIAL"


def test_a_child_pack_with_bad_cross_references_fails_the_self_test(tmp_path):
    child = _child(tmp_path, {"ACTOR_DEFAULTS": ({"station": "nobody"}, True),
                              "ENGINE_SEEDS": (["no_such_seed"], False)})
    errors = entities(child).check_consistency()["errors"]
    assert any("station 'nobody'" in e for e in errors)
    assert any("no_such_seed" in e for e in errors)


def test_the_townspeople_relationship_map_is_read_from_the_pack():
    w = BigvilleWorld.from_townspeople_50(seed=305000)
    assert len(w._actors) == 50
    kinds = {w.eng.node(node)["attrs"]["kind"] for node in w._relationships.values()}
    assert {"feud", "friend"} <= kinds
