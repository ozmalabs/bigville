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
                         "assets/building_badges.png", "assets/props.png",
                         "assets/large_props.png", "assets/terrain_art_direction.png",
                         "assets/stardew_like_art_direction.png",
                         "assets/style_source_village.png",
                         "assets/style_terrain_atlas_source.png",
                         "assets/style_building_atlas_source.png",
                         "assets/style_tiles.png", "assets/style_props.png",
                         "assets/style_ground.png", "assets/style_path_ground.png",
                         "assets/style_water_ground.png", "assets/style_soil_ground.png",
                         "assets/style_stone_ground.png", "assets/style_material_edges.png",
                         "assets/style_large_props.png", "assets/style_buildings.png",
                         "assets/style_cutaway_atlas_source.png", "assets/style_cutaways.png",
                         "assets/style_character_walk_atlas_source.png", "assets/style_characters.png",
                         "assets/style_held_items_atlas_source.png", "assets/style_held_items.png",
                         "assets/style_manifest.json"):
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
    assert manifest["rendering"]["projection"] == "square_cells_3q_top_down"
    assert manifest["rendering"]["display_scale"] == 2
    assert manifest["style_reference"] == "stardew_like_art_direction.png"
    assert manifest["style_assets"]["source_reference"] == "style_source_village.png"
    assert manifest["style_assets"]["cutaway_source"] == "style_cutaway_atlas_source.png"
    assert manifest["style_assets"]["character_source"] == "style_character_walk_atlas_source.png"
    assert manifest["style_assets"]["held_item_source"] == "style_held_items_atlas_source.png"
    style = json.loads((GAME_ROOT / "assets/style_manifest.json").read_text())
    from PIL import Image
    assert style["tiles"]["file"] == "style_tiles.png"
    assert style["materials"]["texture_scale"] == 2
    assert set(style["materials"]["fields"]) == {"ground", "path", "water", "soil", "stone"}
    assert all((GAME_ROOT / "assets" / filename).is_file()
               for filename in style["materials"]["fields"].values())
    assert style["material_edges"]["file"] == "style_material_edges.png"
    assert set(style["material_edges"]["targets"]) == {"grass", "stone", "soil", "water"}
    assert all(set(directions) == {"n", "e", "s", "w"}
               for directions in style["material_edges"]["targets"].values())
    edge_sheet = Image.open(GAME_ROOT / "assets/style_material_edges.png").convert("RGBA")
    assert all(len(frames) == 3 and all(edge_sheet.crop((frame * 16, 0, frame * 16 + 16, 16)).getbbox()
                                         for frame in frames)
               for directions in style["material_edges"]["targets"].values()
               for frames in directions.values())
    assert len(style["path_variants"]) == 16
    assert all(len(frames) == 3 for frames in style["path_variants"].values())
    tiles = Image.open(GAME_ROOT / "assets/style_tiles.png").convert("RGBA")
    assert all(tiles.crop((frame * 16, 0, frame * 16 + 16, 16)).getbbox()
               for frames in style["path_variants"].values() for frame in frames)
    # Path frames are interfaces, not opaque replacement tiles: each cardinal
    # edge reaches the neighbour only when that bit is connected.
    for mask, frames in style["path_variants"].items():
        frame = tiles.crop((frames[0] * 16, 0, frames[0] * 16 + 16, 16))
        edge_points = {1: (8, 0), 2: (15, 8), 4: (8, 15), 8: (0, 8)}
        for bit, point in edge_points.items():
            assert bool(frame.getpixel(point)[3]) == bool(int(mask) & bit)
    assert {"tree", "bush"} <= set(style["large_props"]["sprites"])
    assert style["buildings"]["file"] == "style_buildings.png"
    assert style["cutaways"]["file"] == "style_cutaways.png"
    assert set(entities.BUILDINGS) <= set(style["cutaways"]["sprites"])
    assert style["characters"]["file"] == "style_characters.png"
    assert style["characters"]["frame"] == 32
    assert style["held_items"]["file"] == "style_held_items.png"
    assert {"wooden_mug", "pick", "bread"} <= set(style["held_items"]["sprites"])
    assert len(manifest["terrain"]["transition_masks"]["path"]) == 16
    assert len(manifest["terrain"]["transition_masks"]["water"]) == 16
    assert {"tree", "flower_clump", "bush", "reed", "bench"} <= set(manifest["terrain"]["props"])
    assert {"tree", "bush"} <= set(manifest["terrain"]["large_props"])
