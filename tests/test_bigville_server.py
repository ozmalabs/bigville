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
                         "assets/building_interiors.png", "assets/building_parts.png",
                         "assets/building_badges.png"):
            assert (GAME_ROOT / filename).is_file(), filename


def test_asset_manifest_covers_entity_items_and_modular_buildings():
    import json
    from domains import bigville_entities as entities
    from bigville.server import GAME_ROOT

    manifest = json.loads((GAME_ROOT / "assets/manifest.json").read_text())
    assert set(entities.ITEMS) <= set(manifest["items"]["icons"])
    assert set(entities.BUILDINGS) <= set(manifest["buildings"]["sprites"])
    assert {"floor", "wall", "roof", "door"} <= set(manifest["buildings"]["parts"])
    assert manifest["design"]["logical_tile"] == 16
