#!/usr/bin/env python3
"""Build runtime atlases from the original Bigville art direction.

The source sheets are art references exported as grids.  This script makes
small, transparent runtime sprites from them; the original village scene is
never used as a map backdrop.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "bigville" / "game" / "assets"
TILE = 16
BUILDING = 96
CHARACTER = 32

MAGENTA = (255, 0, 255)


def grid_cell(sheet: Image.Image, columns: int, rows: int, index: int) -> Image.Image:
    """Return a grid cell, excluding the thin white gutters if present."""
    w, h = sheet.size
    col, row = index % columns, index // columns
    left = round(col * w / columns)
    right = round((col + 1) * w / columns)
    top = round(row * h / rows)
    bottom = round((row + 1) * h / rows)
    # Generated sheets have a small gutter.  Cropping it prevents separator
    # pixels from leaking into a tile when the sheet is downsampled.
    gutter_x = max(1, round((right - left) * 0.035))
    gutter_y = max(1, round((bottom - top) * 0.035))
    return sheet.crop((left + gutter_x, top + gutter_y,
                       right - gutter_x, bottom - gutter_y))


def remove_key(image: Image.Image, tolerance: int = 70) -> Image.Image:
    """Make hot-magenta sheet background transparent."""
    image = image.convert("RGBA")
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            if r > 180 and b > 140 and g < tolerance:
                pixels[x, y] = (r, g, b, 0)
    return image


def fit_sprite(image: Image.Image, size: tuple[int, int], pad: int = 1,
               bottom: bool = False) -> Image.Image:
    image = remove_key(image)
    bbox = image.getbbox()
    if bbox is None:
        return Image.new("RGBA", size, (0, 0, 0, 0))
    image = image.crop(bbox)
    max_w, max_h = size[0] - pad * 2, size[1] - pad * 2
    scale = min(max_w / image.width, max_h / image.height)
    resized = image.resize((max(1, round(image.width * scale)),
                            max(1, round(image.height * scale))),
                           Image.Resampling.NEAREST)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    x = (size[0] - resized.width) // 2
    y = size[1] - pad - resized.height if bottom else (size[1] - resized.height) // 2
    out.alpha_composite(resized, (x, y))
    return out


def opaque_tile(image: Image.Image) -> Image.Image:
    """Make a keyed atlas cell a fully opaque terrain tile.

    The generated sheet has magenta around each painted tile.  Transparent
    pixels are correct for props, but terrain must be filled or the key color
    would show between map cells.  The most common painted color is a stable
    material-colored fill for those few keyed pixels.
    """
    image = remove_key(image)
    colors = []
    for r, g, b, a in image.getdata():
        if a:
            colors.append((r, g, b))
    if colors:
        # Quantize so small pixel-art highlights do not win the frequency test.
        buckets: dict[tuple[int, int, int], int] = {}
        for r, g, b in colors:
            key = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
            buckets[key] = buckets.get(key, 0) + 1
        fill = max(buckets, key=buckets.get)
    else:
        fill = (80, 120, 55)
    out = Image.new("RGBA", image.size, (*fill, 255))
    out.alpha_composite(image)
    return out.convert("RGB")


def path_transition(grass: Image.Image, path: Image.Image, mask: int,
                    variant: int = 0) -> Image.Image:
    """Blend an organic path edge into grass using N/E/S/W connectivity."""
    out = grass.copy()
    shape = Image.new("L", (TILE, TILE), 0)
    draw = ImageDraw.Draw(shape)
    draw.rectangle((4, 4, 11, 11), fill=255)
    offset = ((mask * 3 + variant * 5) % 3) - 1
    if mask & 1:
        draw.polygon(((5 + offset, 0), (10 + offset, 0), (11, 8), (4, 8)), fill=255)
    if mask & 2:
        draw.polygon(((8, 4), (15, 5 + offset), (15, 10 + offset), (8, 11)), fill=255)
    if mask & 4:
        draw.polygon(((4, 8), (11, 8), (10 + offset, 15), (5 + offset, 15)), fill=255)
    if mask & 8:
        draw.polygon(((0, 5 + offset), (8, 4), (8, 11), (0, 10 + offset)), fill=255)
    out.paste(path, (0, 0), shape)
    return out


def orient_path(path: Image.Image, mask: int, variant: int) -> Image.Image:
    """Give a connected path the texture direction implied by its mask."""
    horizontal = mask in (2, 8, 10)
    if mask in (3, 12):
        horizontal = variant == 1
    elif mask in (6, 9):
        horizontal = variant == 0
    frame = path.transpose(Image.Transpose.ROTATE_90) if horizontal else path.copy()
    # Mirroring changes the placement of stones and highlights without
    # changing the road connection, keeping long runs from looking stamped.
    if variant == 1:
        frame = ImageOps.mirror(frame) if horizontal else ImageOps.flip(frame)
    elif variant == 2:
        frame = frame.transpose(Image.Transpose.ROTATE_180)
    return frame


def water_transition(water: Image.Image, shoreline: Image.Image, mask: int) -> Image.Image:
    """Keep open water open and add shoreline only at exposed edges."""
    if mask == 15:
        return water.copy()
    if mask == 0:
        return shoreline.copy()
    shape = Image.new("L", (TILE, TILE), 0)
    draw = ImageDraw.Draw(shape)
    draw.rectangle((4, 4, 11, 11), fill=255)
    # A missing cardinal neighbour is the exposed shore edge.
    if not mask & 1:
        draw.rectangle((0, 0, 15, 5), fill=255)
    if not mask & 2:
        draw.rectangle((10, 0, 15, 15), fill=255)
    if not mask & 4:
        draw.rectangle((0, 10, 15, 15), fill=255)
    if not mask & 8:
        draw.rectangle((0, 0, 5, 15), fill=255)
    out = water.copy()
    out.paste(shoreline, (0, 0), shape)
    return out


def build_tiles(manifest: dict, terrain: Image.Image, reference: Image.Image,
                old_tiles: Image.Image) -> dict[str, list[int]]:
    # The order is deliberately documented here: it is the semantic index of
    # the generated sheet, not a fragile crop coordinate in the old backdrop.
    # 0 grass, 1 alternate grass, 2 path, 3 path transition, 4 stone square,
    # 5 tilled soil, 6 water, 7 shoreline, 8 flowers, 9 berry bush, 10 tree,
    # 11 pine, 12 fence, 13 fence corner, 14 barrel/crate, 15 bridge.
    cells = [grid_cell(terrain, 4, 4, i) for i in range(16)]
    base = [opaque_tile(cell.resize((TILE, TILE), Image.Resampling.NEAREST))
            for cell in cells]
    # These two clean grass patches come from the original scene rather than
    # the prop-heavy terrain study.  Flowers and bushes are separate overlays,
    # so the assembled map has the original lush texture without a repeated
    # flower pattern in every cell.
    base[0] = reference.crop((20, 20, 52, 52)).resize(
        (TILE, TILE), Image.Resampling.NEAREST).convert("RGB")
    base[1] = reference.crop((340, 20, 372, 52)).resize(
        (TILE, TILE), Image.Resampling.NEAREST).convert("RGB")
    semantic = {
        "grass": base[0], "grass_alt": base[1], "path": base[2],
        "dirt": base[2], "square": base[4], "floor": base[4],
        "wall": base[4], "water": base[6], "sand": base[2],
        "tree": base[0], "bush": base[0], "flower": base[0],
        "rocks": base[0], "well": base[4], "crop": base[5],
        "mud": base[5], "tilled": base[5], "tilled_wet": base[5],
        "fence": base[0], "bridge": base[15], "roof": base[4],
        "snow": base[1], "grass_wet": base[1], "grass_autumn": base[1],
        "wheat_young": base[5], "wheat_mature": base[5],
        "barley_mature": base[5], "cabbage": base[5],
    }
    old = old_tiles.convert("RGBA")
    names = manifest["tileset"]["tiles"]
    path_variants: dict[str, list[int]] = {}
    first_extra = len(names)
    for mask in range(16):
        path_variants[str(mask)] = [first_extra + mask * 3,
                                    first_extra + mask * 3 + 1,
                                    first_extra + mask * 3 + 2]
    total_frames = first_extra + 16 * 3
    sheet = Image.new("RGBA", (TILE * total_frames, TILE), (0, 0, 0, 0))
    for i, name in enumerate(names):
        if name.startswith("path_transition_"):
            frame = path_transition(base[0], base[2], int(name[-2:]))
        elif name.startswith("water_transition_"):
            frame = water_transition(base[6], base[7], int(name[-2:]))
        else:
            frame = semantic.get(name)
            if frame is None:
                x = names[name] * TILE
                frame = old.crop((x, 0, x + TILE, TILE)).convert("RGB")
        sheet.paste(frame.convert("RGBA"), (i * TILE, 0))
    for mask in range(16):
        for variant in range(3):
            frame = path_transition(
                base[0], orient_path(base[2], mask, variant), mask, variant)
            index = path_variants[str(mask)][variant]
            sheet.paste(frame.convert("RGBA"), (index * TILE, 0))
    sheet.save(ASSETS / "style_tiles.png")
    return path_variants


def build_props(terrain: Image.Image) -> dict[str, int]:
    cells = [grid_cell(terrain, 4, 4, i) for i in range(16)]
    # props.png is a 16px sheet used for small dressing; make the art legible
    # at the renderer's 2x display scale.  Large trees/bushes get their own
    # 32px sheet below so the map can have a readable canopy layer.
    small = [8, 8, 9, 0, 12, 14, 0, 14, 14, 14, 12]
    props = Image.new("RGBA", (TILE * len(small), TILE), (0, 0, 0, 0))
    for i, source_index in enumerate(small):
        props.alpha_composite(fit_sprite(cells[source_index], (TILE, TILE), pad=0),
                              (i * TILE, 0))
    props.save(ASSETS / "style_props.png")
    large = Image.new("RGBA", (32 * 2, 32), (0, 0, 0, 0))
    large.alpha_composite(fit_sprite(cells[10], (32, 32), pad=0, bottom=True), (0, 0))
    large.alpha_composite(fit_sprite(cells[9], (32, 32), pad=0, bottom=True), (32, 0))
    large.save(ASSETS / "style_large_props.png")
    return {
        "tree": 0, "flower_clump": 1, "bush": 2, "grass_tuft": 3,
        "stone": 4, "mushroom": 5, "reed": 6, "log": 7,
        "barrel": 8, "bench": 9, "stump": 10,
    }


def build_buildings(manifest: dict, buildings_sheet: Image.Image) -> dict:
    cells = [grid_cell(buildings_sheet, 3, 2, i) for i in range(6)]
    names = list(manifest["buildings"]["sprites"])
    sheet = Image.new("RGBA", (BUILDING * len(names), BUILDING), (0, 0, 0, 0))
    sprites = {}
    # Families are intentionally repeated across institutions: the important
    # distinction is the building's semantic type and footprint, while the
    # village remains visually coherent rather than becoming a collage.
    for i, name in enumerate(names):
        frame = fit_sprite(cells[i % len(cells)], (BUILDING, BUILDING), pad=2, bottom=True)
        sheet.alpha_composite(frame, (i * BUILDING, 0))
        sprites[name] = i
    sheet.save(ASSETS / "style_buildings.png")
    return sprites


def build_cutaways(manifest: dict, cutaway_sheet: Image.Image) -> dict:
    """Build roof-off companions with the same footprint and facade scale."""
    cells = [grid_cell(cutaway_sheet, 3, 2, i) for i in range(6)]
    names = list(manifest["buildings"]["sprites"])
    sheet = Image.new("RGBA", (BUILDING * len(names), BUILDING), (0, 0, 0, 0))
    sprites = {}
    for i, name in enumerate(names):
        frame = fit_sprite(cells[i % len(cells)], (BUILDING, BUILDING), pad=2, bottom=True)
        sheet.alpha_composite(frame, (i * BUILDING, 0))
        sprites[name] = i
    sheet.save(ASSETS / "style_cutaways.png")
    return sprites


CHARACTER_COLORS = [
    (116, 145, 73), (205, 151, 55), (119, 101, 157), (104, 151, 75),
    (105, 113, 124), (183, 91, 70), (85, 119, 168), (61, 91, 145),
    (180, 139, 54), (47, 139, 131), (126, 149, 76), (120, 125, 139),
    (145, 111, 77), (177, 91, 69), (62, 121, 145), (137, 99, 152),
]


def tint_clothes(image: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """Recolour the vest area while leaving face, hair, hands and boots intact."""
    image = image.copy().convert("RGBA")
    pixels = image.load()
    for y in range(10, 24):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            if not a or not (g >= r * 0.82 and g >= b * 1.03):
                continue
            luminance = max(45, (r + g + b) // 3)
            scale = luminance / max(1, sum(color) // 3)
            target = tuple(max(0, min(255, round(channel * scale))) for channel in color)
            pixels[x, y] = tuple(round(original * 0.25 + replacement * 0.75)
                                 for original, replacement in zip((r, g, b), target)) + (a,)
    return image


def build_characters(manifest: dict, character_sheet: Image.Image) -> None:
    """Build readable 32px walk cycles for every existing role/age variant."""
    cells = [grid_cell(character_sheet, 3, 4, i) for i in range(12)]
    base_frames = [fit_sprite(cell, (CHARACTER, CHARACTER), pad=1, bottom=True)
                   for cell in cells]
    names = list(manifest["character_variants"]["variants"])
    sheet = Image.new("RGBA", (CHARACTER * 3,
                                CHARACTER * 4 * len(names)), (0, 0, 0, 0))
    for variant_index, _name in enumerate(names):
        for i, frame in enumerate(base_frames):
            frame = tint_clothes(frame, CHARACTER_COLORS[variant_index % len(CHARACTER_COLORS)])
            x = (i % 3) * CHARACTER
            y = (variant_index * 4 + i // 3) * CHARACTER
            sheet.alpha_composite(frame, (x, y))
    sheet.save(ASSETS / "style_characters.png")


def main() -> None:
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    terrain = Image.open(ASSETS / "style_terrain_atlas_source.png")
    buildings = Image.open(ASSETS / "style_building_atlas_source.png")
    cutaways = Image.open(ASSETS / "style_cutaway_atlas_source.png")
    characters = Image.open(ASSETS / "style_character_walk_atlas_source.png")
    old_tiles = Image.open(ASSETS / "tileset.png")
    reference = Image.open(ASSETS / "style_source_village.png").convert("RGB")
    path_variants = build_tiles(manifest, terrain, reference, old_tiles)
    prop_sprites = build_props(terrain)
    sprites = build_buildings(manifest, buildings)
    cutaway_sprites = build_cutaways(manifest, cutaways)
    build_characters(manifest, characters)
    out_manifest = {
        "source": "style_source_village.png",
        "terrain_source": "style_terrain_atlas_source.png",
        "building_source": "style_building_atlas_source.png",
        "cutaway_source": "style_cutaway_atlas_source.png",
        "character_source": "style_character_walk_atlas_source.png",
        "tiles": {"file": "style_tiles.png", "frame": TILE,
                  "tiles": manifest["tileset"]["tiles"]},
        "path_variants": path_variants,
        "props": {"file": "style_props.png", "frame": TILE, "sprites": prop_sprites},
        "large_props": {"file": "style_large_props.png", "frame": 32,
                        "sprites": {"tree": 0, "bush": 1}},
        "buildings": {"file": "style_buildings.png", "frame": BUILDING,
                      "sprites": sprites},
        "cutaways": {"file": "style_cutaways.png", "frame": BUILDING,
                     "sprites": cutaway_sprites},
        "characters": {"file": "style_characters.png", "frame": CHARACTER,
                       "cols": 3, "rows_per_variant": 4,
                       "variants": manifest["character_variants"]["variants"]},
    }
    (ASSETS / "style_manifest.json").write_text(json.dumps(out_manifest, indent=2) + "\n")
    print("wrote style_tiles.png style_props.png style_large_props.png style_buildings.png style_manifest.json")


if __name__ == "__main__":
    main()
