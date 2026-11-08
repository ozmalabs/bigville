"""DS01: deterministic canonical seeds, weather and infrastructure draws.

The helper is the single source of runtime chance.  These tests pin its
canonical form, its stability across draw order, actor-state inclusion, the
two migrated world draws, and the checkpoint schema migration.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from bigville.api import create_world
from bigville.runtime import NodeRef
from bigville.world_persistence import load_world_checkpoint, save_world_checkpoint
from domains import bigville_entities as E
from domains import determinism


def _scenario():
    return {
        "id": "determinism_fixture",
        "name": "Determinism fixture",
        "map": {"grid": [["floor"] * 4 for _ in range(4)]},
        "actors": [
            {"name": "Ada", "role": "farmer", "home_cell": [0, 0]},
            {"name": "Ben", "role": "farmer", "home_cell": [1, 0]},
        ],
        "buildings": [], "laws": [], "policies": [], "charters": [],
        "stocks": {"grain": 8},
    }


def _world(seed=305000, *, infrastructure=False):
    world = create_world(scenario=_scenario(), seed=seed)
    if infrastructure:
        world.add_infrastructure("village_well", kind="well")
    return world


def _infrastructure_condition(world, name="village_well"):
    return float(world.eng.node(world._infrastructure[name])["attrs"]["condition"])


def _set_failure_risk(world, risk, name="village_well"):
    world.eng.set_attr(world._infrastructure[name], "failure_risk", float(risk))


# ------------------------------------------------------------- canonicalisation
def test_dict_key_order_does_not_change_the_canonical_bytes():
    assert (determinism.canonical_bytes({"a": 1, "b": [2, 3]})
            == determinism.canonical_bytes({"b": [2, 3], "a": 1}))


def test_set_order_does_not_change_the_canonical_bytes():
    assert (determinism.canonical_bytes({"c", "a", "b"})
            == determinism.canonical_bytes({"b", "c", "a"}))


def test_node_ref_canonicalises_as_its_integer_value():
    assert determinism.canonical_bytes(NodeRef(7)) == determinism.canonical_bytes(7)


def test_tuple_and_list_share_one_sequence_form():
    assert determinism.canonical_bytes((1, 2)) == determinism.canonical_bytes([1, 2])


def test_canonical_bytes_are_pinned_values_not_python_hash_values():
    assert determinism.canonical_bytes({"a": 1, "b": [2, 3]}) == (
        b'{"$type":"sequence","items":[{"$type":"mapping","items":'
        b'[["a",1],["b",{"$type":"sequence","items":[2,3]}]]}]}')
    assert determinism.derive_seed(305000, "weather", 7, "summer") == (
        134642697992948289433037185386385931291)


def test_non_finite_floats_and_arbitrary_objects_are_rejected():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="non-finite"):
            determinism.canonical_bytes(bad)
    with pytest.raises(TypeError, match="unsupported canonical value"):
        determinism.canonical_bytes(object())


# --------------------------------------------------------------- seed and draw
def test_same_seed_and_parts_give_the_same_values():
    first = (determinism.derive_seed(305000, "illness", "Ada", 7),
             determinism.uniform(305000, "illness", "Ada", 7),
             determinism.choice(("a", "b", "c"), 305000, "illness", "Ada", 7),
             determinism.shuffle([1, 2, 3, 4], 305000, "illness", "Ada", 7),
             determinism.sample([1, 2, 3, 4], 2, 305000, "illness", "Ada", 7))
    second = (determinism.derive_seed(305000, "illness", "Ada", 7),
              determinism.uniform(305000, "illness", "Ada", 7),
              determinism.choice(("a", "b", "c"), 305000, "illness", "Ada", 7),
              determinism.shuffle([1, 2, 3, 4], 305000, "illness", "Ada", 7),
              determinism.sample([1, 2, 3, 4], 2, 305000, "illness", "Ada", 7))
    assert first == second


def test_different_seeds_or_purposes_give_different_values():
    assert determinism.derive_seed(305000, "a") != determinism.derive_seed(305000, "b")
    assert determinism.derive_seed(305000, "a") != determinism.derive_seed(305001, "a")
    assert determinism.uniform(305000, "a") != determinism.uniform(305000, "b")


def test_uniform_is_in_the_half_open_unit_interval():
    values = [determinism.uniform(305000, "range", index) for index in range(200)]
    assert all(0.0 <= value < 1.0 for value in values)
    assert len(set(values)) == len(values)


def test_shuffle_and_sample_do_not_mutate_the_input():
    sequence = [1, 2, 3, 4, 5]
    original = list(sequence)
    shuffled = determinism.shuffle(sequence, 305000, "order")
    sampled = determinism.sample(sequence, 3, 305000, "order")
    assert sequence == original
    assert shuffled is not sequence
    assert sorted(shuffled) == original
    assert len(sampled) == 3 and set(sampled) <= set(original)
    assert sequence == original


def test_choice_and_sample_are_stable_for_unordered_inputs():
    assert (determinism.choice({"a", "b", "c"}, 305000, "pick")
            == determinism.choice({"c", "b", "a"}, 305000, "pick"))
    assert (determinism.sample({"a", "b", "c"}, 2, 305000, "pick")
            == determinism.sample({"c", "b", "a"}, 2, 305000, "pick"))


# ---------------------------------------------------------------- actor state
def test_state_uniform_changes_when_the_actor_or_body_state_changes():
    world = _world()
    base = determinism.state_uniform(world, "illness", "Ada", 7)
    world.eng.set_attr(world._actors["Ada"], "health_value", 0.25)
    assert determinism.state_uniform(world, "illness", "Ada", 7) != base

    world = _world()
    base = determinism.state_uniform(world, "illness", "Ada", 7)
    world.eng.set_attr(world._bodies["Ada"], "mood", 99.0)
    assert determinism.state_uniform(world, "illness", "Ada", 7) != base


def test_state_uniform_includes_explicit_and_automatically_named_actors():
    world = _world()
    no_actor = determinism.state_uniform(world, "strike", 1)
    explicit = determinism.state_uniform(world, "strike", 1, actors=("Ada",))
    automatic = determinism.state_uniform(world, "strike", "Ada", 1)
    assert no_actor != explicit
    assert no_actor != automatic

    world.eng.set_attr(world._bodies["Ada"], "stamina", 0.1)
    assert determinism.state_uniform(world, "strike", "Ada", 1) != automatic
    assert determinism.state_uniform(world, "strike", 1, actors=("Ada",)) != explicit


def test_actor_state_for_a_missing_actor_is_graceful_and_stable():
    world = _world()
    assert determinism.actor_state(world, "Nobody") == {
        "name": "Nobody", "present": False}
    assert determinism.state_uniform(world, "strike", "Nobody", 1) == (
        determinism.state_uniform(world, "strike", "Nobody", 1))


def test_draw_order_a_then_b_matches_b_then_a_per_actor():
    first = _world()
    second = _world()
    a_then_b = {name: determinism.state_uniform(first, "illness", name, 7)
                for name in ("Ada", "Ben")}
    b_then_a = {name: determinism.state_uniform(second, "illness", name, 7)
                for name in ("Ben", "Ada")}
    assert a_then_b == b_then_a


# --------------------------------------------------------------------- weather
def test_weather_choice_is_identical_for_two_worlds_with_the_same_seed():
    first = _world(305000)
    second = _world(305000)
    first._set_daily_weather(7, "summer")
    second._set_daily_weather(7, "summer")
    assert first.calendar()["weather"] == second.calendar()["weather"]
    assert not hasattr(first, "_rng") and not hasattr(second, "_rng")


def test_weather_can_change_with_day_season_or_seed():
    world = _world(305000)
    days = set()
    for day in range(12):
        world._set_daily_weather(day, "spring")
        days.add(world.calendar()["weather"])
    assert len(days) > 1, "different days in one season can choose different weather"

    world._set_daily_weather(3, "spring")
    spring = world.calendar()["weather"]
    world._set_daily_weather(3, "summer")
    summer = world.calendar()["weather"]
    assert spring != summer, "the season's option set changes the choice"

    same_seed = _world(305000)
    same_seed._set_daily_weather(3, "spring")
    assert same_seed.calendar()["weather"] == spring
    elsewhere = [_world(seed) for seed in range(305001, 305009)]
    for other in elsewhere:
        other._set_daily_weather(3, "spring")
    assert any(other.calendar()["weather"] != spring for other in elsewhere)
    assert set(E.SEASONS["spring"]["weather"]) >= {spring}


# ------------------------------------------------------------- infrastructure
def test_infrastructure_failure_is_identical_for_the_same_state_and_period():
    first = _world(305000, infrastructure=True)
    second = _world(305000, infrastructure=True)
    for world in (first, second):
        _set_failure_risk(world, 0.5)
    for period in range(12):
        for world in (first, second):
            world.eng.set_attr(world._infrastructure["village_well"], "condition", 1.0)
            world.eng.set_attr(world._town, "period", float(period))
        first._advance_infrastructure()
        second._advance_infrastructure()
        assert _infrastructure_condition(first) == _infrastructure_condition(second)


def test_infrastructure_risk_and_condition_change_the_expected_decision():
    world = _world(305000, infrastructure=True)

    _set_failure_risk(world, 1.0)
    world._advance_infrastructure()
    assert _infrastructure_condition(world) == pytest.approx(0.75)

    world.eng.set_attr(world._infrastructure["village_well"], "condition", 1.0)
    _set_failure_risk(world, 0.0)
    world._advance_infrastructure()
    assert _infrastructure_condition(world) == pytest.approx(1.0)

    world.eng.set_attr(world._infrastructure["village_well"], "condition", 0.0)
    _set_failure_risk(world, 1.0)
    world._advance_infrastructure()
    assert _infrastructure_condition(world) == pytest.approx(0.0)

    seed = determinism.world_seed(world)
    healthy = determinism.uniform(
        seed, "infrastructure", "village_well", "well", 0.0, 1.0, 0.5)
    damaged = determinism.uniform(
        seed, "infrastructure", "village_well", "well", 0.0, 0.75, 0.5)
    riskier = determinism.uniform(
        seed, "infrastructure", "village_well", "well", 0.0, 1.0, 0.75)
    assert healthy != damaged, "condition is part of the infrastructure identity"
    assert healthy != riskier, "risk is part of the infrastructure identity"


# ------------------------------------------------------------------ checkpoints
def _manifest_and_world_json(checkpoint):
    manifest = json.loads((checkpoint / "manifest.json").read_text(encoding="utf-8"))
    world_json = checkpoint / manifest["generation"] / "world.json"
    return manifest, world_json


def test_new_checkpoint_writes_no_rng_state(tmp_path):
    world = _world(305000, infrastructure=True)
    checkpoint = tmp_path / "town"
    save_world_checkpoint(world, checkpoint)
    manifest, world_json = _manifest_and_world_json(checkpoint)
    attrs = json.loads(world_json.read_text(encoding="utf-8"))
    assert "_rng_state" not in attrs
    assert "_rng" not in attrs
    assert "world.json" in manifest["files"]


def test_legacy_checkpoint_with_rng_state_loads_and_continues_deterministically(tmp_path):
    control = _world(305000, infrastructure=True)
    saved = _world(305000, infrastructure=True)
    for world in (control, saved):
        _set_failure_risk(world, 0.5)
        world.eng.set_attr(world._town, "period", 4.0)

    checkpoint = tmp_path / "town"
    save_world_checkpoint(saved, checkpoint)

    # Turn the fresh checkpoint into a pre-DS01 one: add the retired field and
    # refresh the manifest checksum exactly as an old writer would have.
    manifest, world_json = _manifest_and_world_json(checkpoint)
    attrs = json.loads(world_json.read_text(encoding="utf-8"))
    attrs["_rng_state"] = {"$type": "tuple", "items": [3, 3, 3]}
    world_json.write_text(json.dumps(attrs, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False), encoding="utf-8")
    manifest["files"]["world.json"] = hashlib.sha256(world_json.read_bytes()).hexdigest()
    (checkpoint / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8")

    restored = load_world_checkpoint(checkpoint)
    assert not hasattr(restored, "_rng")

    restored._set_daily_weather(5, "winter")
    control._set_daily_weather(5, "winter")
    assert restored.calendar()["weather"] == control.calendar()["weather"]

    restored._advance_infrastructure()
    control._advance_infrastructure()
    assert _infrastructure_condition(restored) == _infrastructure_condition(control)
