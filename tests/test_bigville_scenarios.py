from bigville.api import create_game, create_world
from bigville.backends import ActorResponse
from bigville.scenarios import load_scenario


def test_scenario_ocelot_selection_fails_closed(monkeypatch):
    import pytest
    import bigville.backends.ocelot as adapter
    def unavailable(_name):
        raise ModuleNotFoundError("ocelot unavailable")
    monkeypatch.setattr(adapter, "import_module", unavailable)
    with pytest.raises(adapter.OcelotUnavailableError):
        create_game(scenario="restaurant", player="Nell")


def test_compact_scenarios_share_the_world_boundary_without_village_defaults():
    world = create_world(scenario="house_argument", autonomous_actors=False)
    assert len(world._map_cells) < 30
    assert set(world._actors) == {"Mara", "Jon"}
    assert set(world._places) == {"blue_house"}
    assert world.export_state()["scenario"]["id"] == "house_argument"
    scenario = load_scenario("house_argument").to_dict()
    scenario["actors"] = [dict(a, backend="simple") for a in scenario["actors"]]
    game = create_game(scenario=scenario, player="Mara")
    assert game.characters["Mara"].personality["directness"] == 0.9
    assert game.characters["Mara"].held_frames[0].seed == "conversation"


def test_scenario_actor_backend_selection_and_turn_flow():
    scenario = load_scenario("restaurant").to_dict()
    scenario["actors"] = [dict(a, backend="simple") if a["name"] == "Ruth" else a for a in scenario["actors"]]
    game = create_game(scenario=scenario, player="Nell")
    assert game.backends["Ruth"].kind == "cheap"
    assert game.backends["Ivo"].kind == "cheap"
    assert game.backends["Nell"].kind == "human"

    game.submit_player_response(ActorResponse(utterances=[{
        "target": "Ruth",
        "text": "Could I see the menu, please?",
        "raw": {"act": "request", "object": "menu"},
    }]))
    result = game.step()
    assert result["status"] == "advanced"
    assert result["snapshot"]["world"]["scenario"]["id"] == "restaurant"


def test_inline_scenario_definition_is_supported():
    world = create_world(scenario={
        "id": "argument_in_kitchen",
        "name": "Argument in the Kitchen",
        "map": {"grid": [["wall", "wall", "wall"],
                            ["wall", "floor", "wall"],
                            ["wall", "wall", "wall"]]},
        "actors": [],
        "buildings": [],
        "laws": [], "policies": [], "charters": [],
    }, autonomous_actors=False)
    assert len(world._map_cells) == 1
    assert world.export_state()["scenario"]["name"] == "Argument in the Kitchen"


def test_external_cognition_factory_is_used_without_importing_substrate():
    created = []

    class ExternalMind:
        def __init__(self, name):
            self.name = name
            created.append(name)

    world = create_world(scenario="house_argument", autonomous_actors=False,
                         cognition_factory=ExternalMind)
    assert created == ["Mara", "Jon"]
    assert world.actor_mind("Mara").name == "Mara"
