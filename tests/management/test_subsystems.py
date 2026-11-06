import json

import pytest

from bigville.api import create_world
from bigville.management.drafts import preview_draft, resolve_draft
from bigville.management.runs import RunRegistry
from bigville.management.templates import TemplateRegistry


@pytest.fixture
def subsystem_scenario(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    value = {
        "id": "subsystem_fixture", "name": "Subsystem Fixture",
        "physical_subsystems": {"training": True, "metabolism": False},
        "map": {"grid": [["wall"] * 6] + [["wall"] + ["floor"] * 4 + ["wall"] for _ in range(4)] + [["wall"] * 6],
                "layout": {"w": 6, "h": 6, "homes": [[2, 2]]}},
        "actors": [{"name": "Ada", "role": "hand", "backend": "simple", "home_cell": [2, 2]}],
    }
    (root / "subsystem_fixture.json").write_text(json.dumps(value))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    return value


def draft(**changes):
    value = {"scenario_id": "subsystem_fixture", "name": "Switch test", "seed": 29,
             "autonomous": True, "default_backend": "simple", "ticks_per_period": "world",
             "turn_limit": 2}
    value.update(changes)
    return value


@pytest.mark.parametrize("overrides,expected,source", [
    ({}, {"training": True, "metabolism": False}, {"training": "scenario_override", "metabolism": "scenario_override"}),
    ({"training": False}, {"training": False, "metabolism": False}, {"training": "user_override", "metabolism": "scenario_override"}),
    ({"metabolism": True}, {"training": True, "metabolism": True}, {"training": "scenario_override", "metabolism": "user_override"}),
])
def test_preview_and_launch_share_effective_switches(subsystem_scenario, tmp_path, overrides, expected, source):
    request_draft = draft(physical_subsystems=overrides) if overrides else draft()
    preview, resolution = preview_draft(request_draft)
    assert resolution["valid"], resolution["errors"]
    config = resolution["canonical_config"]
    assert config["physical_subsystem_defaults"]["training"] is True
    assert {key: config["physical_subsystems"][key] for key in expected} == expected
    assert {key: config["physical_subsystem_sources"][key] for key in source} == source
    assert preview["canonical_config"]["physical_subsystem_overrides"] == overrides

    registry = RunRegistry(tmp_path / "registry")
    record, _ = registry.create_run({
        "draft": request_draft, "idempotency_key": "subsystem-launch",
        "expected_config_hash": resolution["configuration_hash"],
        "expected_capability_revision": resolution["capability_revision"],
    })
    game = registry._ensure_game(registry._runtime[record["id"]], record)
    assert game.world.physical_subsystems == config["physical_subsystems"]
    assert list(game.world.actor_position("Ada")) == preview["cast"]["actors"][0]["position"]


@pytest.mark.parametrize("value,field", [
    ({"unsupported": True}, "physical_subsystems.unsupported"),
    ({"training": "false"}, "physical_subsystems.training"),
    (["training"], "physical_subsystems"),
])
def test_invalid_subsystem_overrides_have_field_errors(subsystem_scenario, value, field):
    result = resolve_draft(draft(physical_subsystems=value))
    assert not result["valid"]
    assert field in result["errors"]


def test_direct_world_api_partial_override_inherits_other_scenario_switches(subsystem_scenario):
    world = create_world(scenario="subsystem_fixture", seed=29,
                         physical_subsystems={"training": False})
    assert world.physical_subsystems["training"] is False
    assert world.physical_subsystems["metabolism"] is False


def test_town100_switches_reach_constructor_and_launch_unchanged(tmp_path):
    request_draft = draft(scenario_id="town100", physical_subsystems={"illness": True, "training": False})
    preview, resolution = preview_draft(request_draft)
    assert resolution["valid"], resolution["errors"]
    direct = create_world(scenario="town100", seed=29,
                          physical_subsystems=resolution["canonical_config"]["physical_subsystem_overrides"])
    assert preview["canonical_config"]["physical_subsystems"] == direct.physical_subsystems
    assert direct.physical_subsystems["illness"] is True
    assert direct.physical_subsystems["training"] is False
    registry = RunRegistry(tmp_path / "registry")
    record, _ = registry.create_run({
        "draft": request_draft, "idempotency_key": "town-subsystem-launch",
        "expected_config_hash": resolution["configuration_hash"],
        "expected_capability_revision": resolution["capability_revision"],
    })
    game = registry._ensure_game(registry._runtime[record["id"]], record)
    assert game.world.physical_subsystems == preview["canonical_config"]["physical_subsystems"]


def test_template_round_trip_preserves_explicit_subsystem_override(subsystem_scenario, tmp_path):
    value = draft(physical_subsystems={"training": False})
    registry = TemplateRegistry(tmp_path / "templates.json")
    saved = registry.save(name="Training off", draft=value)
    loaded = TemplateRegistry(tmp_path / "templates.json").load(saved["id"], saved["version"])
    assert loaded["draft"]["physical_subsystems"] == {"training": False}
    assert resolve_draft(loaded["draft"])["canonical_config"]["physical_subsystems"]["training"] is False


def test_training_override_changes_real_body_behavior():
    world = create_world(scenario="town100", seed=29,
                         physical_subsystems={"training": False})
    world.add_tradesperson("Switch Smith", "smith")
    world.set_stock("iron", 2000)
    world.set_stock("charcoal", 2000)
    x, y, _width, _height = world._building_sites["forge"]
    world._move_actor_to("Switch Smith", (x, y))
    for _ in range(3):
        for item in list(world.eng.nodes("ToolItem")):
            if world.eng.node(item)["attrs"].get("kind") == "hammer":
                world.eng.set_attr(item, "condition", 1.0)
                world.eng.set_attr(item, "broken", 0.0)
        world.eng.set_attr(world._bodies["Switch Smith"], "stamina_reserve", 1.0)
        world.eng.set_attr(world._actors["Switch Smith"], "hunger", 0.0)
        assert world.do("Switch Smith", "forge_knife")
    body = world.eng.node(world._bodies["Switch Smith"])["attrs"]
    assert body["str_train"] == body["sta_train"] == 0.0
