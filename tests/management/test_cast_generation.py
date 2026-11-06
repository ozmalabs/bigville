import copy
import json

import pytest

from bigville.backends import DeterministicBackend, LLMBackend
from bigville.management.catalog import build_capability_catalog
from bigville.management.drafts import preview_draft, resolve_draft
from bigville.management.http import create_server
from bigville.management.profiles import BackendAdapterRegistry


@pytest.fixture
def cast_scenario(tmp_path, monkeypatch):
    from bigville import scenarios

    root = tmp_path / "scenarios"
    root.mkdir()
    data = {
        "id": "cast_fixture", "name": "Cast Fixture",
        "map": {"grid": [["wall"] * 8] + [["wall"] + ["floor"] * 6 + ["wall"] for _ in range(6)] + [["wall"] * 8],
                "layout": {"w": 8, "h": 8, "homes": [[2, 2], [3, 2], [4, 2], [5, 2],
                                                            [2, 3], [3, 3], [4, 3], [5, 3],
                                                            [2, 4], [3, 4], [4, 4], [5, 4]]}},
        "actors": [{"name": "Ada", "role": "resident", "backend": "simple",
                    "home_cell": [1, 1], "identity": {"occupation": "founder"},
                    "personality": {"patience": 0.7}}],
        "management_cast_generation": {"schema_version": 1, "max_generated": 10,
                                       "roles": ["resident", "artisan", "farmer"]},
    }
    scenario_file = root / "cast_fixture.json"
    scenario_file.write_text(json.dumps(data))
    monkeypatch.setattr(scenarios, "SCENARIO_ROOT", root)
    return data, scenario_file


def base_draft(**changes):
    value = {"scenario_id": "cast_fixture", "name": "Cast test", "seed": 101,
             "autonomous": True, "default_backend": "simple", "ticks_per_period": "world",
             "turn_limit": 2}
    value.update(changes)
    return value


def cast_spec(*groups):
    return {"schema_version": 1, "groups": list(groups)}


def group(group_id="workers", count=3, **changes):
    value = {"id": group_id, "count": count, "role": "artisan",
             "backend_profile_id": "simple.default",
             "traits": {"age": {"min": 18, "max": 60},
                        "skill": {"min": 0.1, "max": 0.9}}}
    value.update(changes)
    return value


def test_generation_is_deterministic_seeded_and_catalog_declared(cast_scenario):
    spec = cast_spec(group())
    first, first_resolution = preview_draft(base_draft(cast_generation=spec))
    again, again_resolution = preview_draft(base_draft(cast_generation=spec))
    changed, changed_resolution = preview_draft(base_draft(seed=102, cast_generation=spec))
    assert first_resolution["valid"] and again_resolution["valid"] and changed_resolution["valid"]
    assert first["cast"]["actors"] == again["cast"]["actors"]
    assert first["canonical_config"]["generated_cast"] != changed["canonical_config"]["generated_cast"]
    assert first["configuration_hash"] == again["configuration_hash"]
    assert first["canonical_config"]["cast_generation_version"] == 1
    assert first["canonical_config"]["cast_generation_hash"]
    generated = [actor for actor in first["cast"]["actors"] if actor["name"].startswith("workers-")]
    assert len({tuple(actor["position"]) for actor in generated}) == len(generated)
    assert len(generated) == 3
    catalog = build_capability_catalog()
    feature = next(item["cast_generation"] for item in catalog["scenarios"]
                   if item["id"] == "cast_fixture")
    assert feature == {"schema_version": 1, "max_generated": 10,
                       "roles": ["resident", "artisan", "farmer"]}


def test_opted_in_scenario_resolves_eighty_generated_actors(cast_scenario):
    data, scenario_file = cast_scenario
    large = copy.deepcopy(data)
    grid = [["wall"] * 12] + [["wall"] + ["floor"] * 10 + ["wall"] for _ in range(10)] + [["wall"] * 12]
    homes = [[x, y] for y in range(1, 11) for x in range(1, 11)][:100]
    large["map"] = {"grid": grid, "layout": {"w": 12, "h": 12, "homes": homes}}
    large["management_cast_generation"]["max_generated"] = 100
    large["actors"][0]["home_cell"] = [1, 1]
    scenario_file.write_text(json.dumps(large))
    resolution = resolve_draft(base_draft(cast_generation=cast_spec(group(count=80))))
    assert resolution["valid"], resolution["errors"]
    assert len(resolution["canonical_config"]["generated_cast"]) == 80
    assert len({tuple(actor["home_cell"]) for actor in resolution["canonical_config"]["generated_cast"]}) == 80


@pytest.mark.parametrize("spec,field", [
    (cast_spec(group(count=11)), "cast_generation.groups.0.count"),
    (cast_spec(group(count=True)), "cast_generation.groups.0.count"),
    (cast_spec(group(), group()), "cast_generation.groups.1.id"),
    (cast_spec(group(role="king")), "cast_generation.groups.0.role"),
    (cast_spec(group(traits={"age": {"min": 70, "max": 20}})), "cast_generation.groups.0.traits.age"),
    (cast_spec(group(traits={"income": {"min": 1, "max": 10}})), "cast_generation.groups.0.traits"),
    ({"schema_version": 2, "groups": [group()]}, "cast_generation.schema_version"),
])
def test_invalid_groups_and_capacity_return_field_errors(cast_scenario, spec, field):
    resolution = resolve_draft(base_draft(cast_generation=spec))
    assert not resolution["valid"]
    assert field in resolution["errors"]


def test_town100_and_non_opt_in_scenarios_reject_generation(cast_scenario):
    town = resolve_draft(base_draft(scenario_id="town100", cast_generation=cast_spec(group())))
    data, scenario_file = cast_scenario
    ordinary_data = copy.deepcopy(data)
    ordinary_data.pop("management_cast_generation")
    scenario_file.write_text(json.dumps(ordinary_data))
    ordinary = resolve_draft(base_draft(cast_generation=cast_spec(group())))
    assert "cast_generation" in town["errors"]
    assert "cast_generation" in ordinary["errors"]
    old_town = resolve_draft(base_draft(scenario_id="town100"))
    assert old_town["valid"]
    assert "generated_cast" not in old_town["canonical_config"]
    from bigville.api import create_world
    town_preview, _ = preview_draft(base_draft(scenario_id="town100"))
    direct_world = create_world(scenario="town100", seed=101)
    assert town_preview["cast"]["count"] == len(direct_world._actors) == 100
    assert [item["name"] for item in town_preview["cast"]["actors"]] == sorted(direct_world._actors)
    assert all(item["position"] == list(direct_world.actor_position(item["name"]))
               for item in town_preview["cast"]["actors"])


def test_generated_capacity_uses_only_free_walkable_cells_and_rejects_bad_terrain(cast_scenario):
    data, scenario_file = cast_scenario
    malformed = copy.deepcopy(data)
    malformed["map"]["layout"]["homes"] = [[2, 2], [3, 2]]
    scenario_file.write_text(json.dumps(malformed))
    too_many = resolve_draft(base_draft(cast_generation=cast_spec(group(count=3))))
    assert "cast_generation.groups" in too_many["errors"]
    assert "walkable home cells" in too_many["errors"]["cast_generation.groups"]

    malformed["map"]["layout"]["homes"] = [[5, 5]]
    malformed["map"]["grid"][5][5] = "lava"
    scenario_file.write_text(json.dumps(malformed))
    unknown_terrain = resolve_draft(base_draft(cast_generation=cast_spec(group())))
    assert "cast_generation" in unknown_terrain["errors"]
    assert "Unknown scenario terrain" in unknown_terrain["errors"]["cast_generation"]


def test_invalid_authored_names_and_home_cells_are_field_errors(cast_scenario):
    data, scenario_file = cast_scenario
    malformed = copy.deepcopy(data)
    malformed["actors"][0]["name"] = ["Ada"]
    scenario_file.write_text(json.dumps(malformed))
    bad_name = resolve_draft(base_draft(cast_generation=cast_spec(group())))
    assert "cast_generation.authored_actors.0.name" in bad_name["errors"]

    malformed["actors"][0]["name"] = "Ada"
    malformed["actors"][0]["home_cell"] = [999, 999]
    scenario_file.write_text(json.dumps(malformed))
    bad_home = resolve_draft(base_draft(cast_generation=cast_spec(group())))
    assert "cast_generation.authored_actors.0.home_cell" in bad_home["errors"]

    malformed["actors"][0]["home_cell"] = [1, 1]
    malformed["actors"][0]["name"] = "workers-001"
    scenario_file.write_text(json.dumps(malformed))
    duplicate = resolve_draft(base_draft(cast_generation=cast_spec(group("workers", 1))))
    assert "cast_generation.groups.workers.id" in duplicate["errors"]


def test_authored_actor_is_preserved_and_generated_cast_launches_exactly(tmp_path, cast_scenario):
    from bigville.management.catalog import _scenario_entry
    data, _ = cast_scenario
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    profile_path = data_dir / "backend_profiles.json"
    profile_path.write_text(json.dumps({"schema_version": 1, "profiles": [{
        "id": "llm.fixture", "name": "Fixture LLM", "kind": "llm",
        "revision": "r1", "adapter": "adapter.fixture"}]}))

    class FakeProvider:
        def complete(self, payload):
            return "{}"

    adapters = BackendAdapterRegistry()
    factory_calls = []
    adapters.register("adapter.fixture", lambda world, character, profile: (
        factory_calls.append(character.character_id) or
        LLMBackend(character, FakeProvider(), autopilot=False)))
    server = create_server(port=0, data_dir=data_dir, profile_adapters=adapters)
    try:
        groups = cast_spec(
            group("builders", 2, role="farmer"),
            group("scribes", 1, role="artisan", backend_profile_id="llm.fixture"))
        draft = base_draft(cast_generation=groups)
        preview, resolution = preview_draft(draft, profile_registry=server.profile_registry)
        assert resolution["valid"], resolution["errors"]
        expected = {actor["name"]: actor for actor in preview["cast"]["actors"]}
        stored, _ = server.run_registry.create_run({"draft": draft, "idempotency_key": "cast-launch",
            "expected_config_hash": resolution["configuration_hash"],
            "expected_capability_revision": resolution["capability_revision"]})
        runtime = server.run_registry._runtime[stored["id"]]
        game = server.run_registry._ensure_game(runtime, stored)
        actual = {name: {"name": name, "role": game.world.eng.node(game.world._actors[name])["attrs"]["role"],
                         "position": list(game.world.actor_position(name)),
                         "backend": game.backends[name].kind}
                  for name in game.characters}
        assert set(actual) == set(expected)
        for name in expected:
            assert actual[name]["name"] == expected[name]["name"]
            assert actual[name]["role"] == expected[name]["role"]
            assert actual[name]["position"] == expected[name]["position"]
            actual_backend = "simple" if actual[name]["backend"] == "cheap" else actual[name]["backend"]
            assert actual_backend == expected[name]["backend"]
        assert type(game.backends["builders-001"]) is DeterministicBackend
        assert type(game.backends["scribes-001"]) is LLMBackend
        assert set(factory_calls) == {"scribes-001"}
        assert game.characters["Ada"].identity["occupation"] == "founder"
        assert game.characters["Ada"].personality["patience"] == 0.7
        assert data["actors"][0]["name"] == "Ada"  # authored fixture was not mutated
    finally:
        server.server_close()
