from bigville.server import GameService


def test_game_service_turn_is_canonical_and_json_safe():
    service = GameService(scenario="town100", player="Verity Peaseblossom")
    initial = service.state()
    assert initial["schema"] == "bigville/game/1"
    assert initial["player_context"]["actor"] == "Verity Peaseblossom"
    result = service.turn({"utterances": [{
        "target": "Ida Ditchwater", "content": "Good morning."
    }]})
    assert result["status"] == "advanced"
    assert result["state"]["world"]["clock"]["clock"] == 1.0
    assert result["state"]["world"]["residents"]


def test_game_assets_are_present():
    from bigville.server import GAME_ROOT

    for filename in ("index.html", "game.js", "game.css", "assets/tileset.png",
                     "assets/buildings.png", "assets/character_variants.png",
                     "assets/items.png", "assets/actions.png", "assets/manifest.json",
                     "assets/village_scene.png"):
        assert (GAME_ROOT / filename).is_file(), filename
