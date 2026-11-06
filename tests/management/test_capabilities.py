import json

from bigville.management import catalog
from worlds.bigville_world import BigvilleWorld


def test_catalog_lists_builtin_authored_scenarios_and_engine_defaults(tmp_path, monkeypatch):
    authored = {
        "id": "temporary_authored", "name": "Temporary", "type": "village",
        "actors": [{"name": "Ada"}], "physical_subsystems": {"illness": True},
    }
    (tmp_path / "temporary_authored.json").write_text(json.dumps(authored))
    monkeypatch.setattr(catalog, "SCENARIO_ROOT", tmp_path)
    monkeypatch.setattr(catalog, "list_scenarios", lambda: ["temporary_authored"])
    monkeypatch.setattr("bigville.scenarios.SCENARIO_ROOT", tmp_path)

    response = catalog.build_capability_catalog()

    by_id = {entry["id"]: entry for entry in response["scenarios"]}
    assert by_id["town100"]["source"] == "built_in"
    assert by_id["town100"]["type"] == "village"
    assert by_id["temporary_authored"]["source"] == "authored"
    assert by_id["temporary_authored"]["type"] == "village"
    assert by_id["temporary_authored"]["physical_subsystems"]["illness"] is True
    assert by_id["temporary_authored"]["physical_subsystems"]["metabolism"] is True
    assert {item["name"]: item["default"] for item in response["physical_subsystems"]} == \
        BigvilleWorld.PHYSICAL_SUBSYSTEM_DEFAULTS
    assert response["schema_version"] == 1
    assert response["engine_build"]


def test_backend_availability_is_truthful_without_provider_construction(monkeypatch):
    def missing_ocelot():
        raise RuntimeError("adapter missing")

    monkeypatch.setattr("bigville.backends.ocelot.ocelot_resident_class", missing_ocelot)
    backends = {entry["kind"]: entry for entry in catalog._backend_catalog()}
    assert backends["simple"] == {"kind": "simple", "available": True, "reason": None}
    assert backends["ocelot"]["available"] is False
    assert "adapter missing" in backends["ocelot"]["reason"]
    assert backends["llm"]["available"] is False
    assert "configured" in backends["llm"]["reason"]


def test_catalog_discovery_does_not_construct_a_game_or_call_provider(monkeypatch):
    import bigville.api

    def forbidden(*args, **kwargs):
        raise AssertionError("game/provider construction must not occur during discovery")

    monkeypatch.setattr(bigville.api, "create_game", forbidden)
    response = catalog.build_capability_catalog()
    assert response["scenarios"]
    assert response["backends"]
