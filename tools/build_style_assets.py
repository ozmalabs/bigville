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
ART_TILE = 32  # displayed terrain cell; authored at facade resolution rather than enlarged from 16px
BUILDING = 96
CHARACTER = 32
HELD_ITEM = 16

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


def material_texture(frames: list[Image.Image], choices: list[int], blocks: int = 8,
                     seed: int = 17, block_size: int = TILE) -> Image.Image:
    """Make a larger, varied material field from small pixel-art samples.

    The simulation still addresses terrain one logical cell at a time, but a
    material is rendered as a field rather than as one visibly repeated square
    per cell.  Mirrored samples keep the pixel language intact while breaking
    the obvious checkerboard rhythm at normal zoom.
    """
    size = block_size * blocks
    out = Image.new("RGB", (size, size))
    for row in range(blocks):
        for col in range(blocks):
            index = (col * 13 + row * 29 + seed) % len(choices)
            frame = frames[choices[index]].convert("RGB")
            transform = (col * 3 + row * 5 + seed) % 4
            if transform == 1:
                frame = ImageOps.mirror(frame)
            elif transform == 2:
                frame = ImageOps.flip(frame)
            elif transform == 3:
                frame = frame.transpose(Image.Transpose.ROTATE_180)
            out.paste(frame, (col * block_size, row * block_size))
    return out


def material_field(kind: str, size: int = ART_TILE * 8) -> Image.Image:
    """Paint a larger pixel-art material without logical-cell borders.

    Some source tiles intentionally contain a little scene dressing (lilypads,
    paving seams, or crop rows).  Repeating those tiles as a field would just
    move the square problem to a larger scale, so the broad materials get a
    sparse, deterministic pixel treatment in the same palette instead.
    """
    palettes = {
        "path": [(224, 160, 64), (235, 172, 78), (204, 137, 48), (171, 108, 31)],
        "water": [(16, 96, 112), (24, 106, 124), (36, 121, 139), (65, 145, 155)],
        "soil": [(96, 48, 16), (111, 57, 18), (132, 70, 22), (77, 42, 17)],
        "stone": [(160, 128, 96), (178, 145, 108), (139, 108, 80), (196, 165, 123)],
    }
    colors = palettes[kind]
    out = Image.new("RGB", (size, size), colors[0])
    draw = ImageDraw.Draw(out)

    def number(x: int, y: int, salt: int = 0) -> int:
        value = (x * 374761393 + y * 668265263 + salt * 1442695041) & 0xffffffff
        value = ((value ^ (value >> 13)) * 1274126177) & 0xffffffff
        return (value ^ (value >> 16)) & 0x7fffffff

    for y in range(size):
        for x in range(size):
            value = number(x, y, len(kind)) % 100
            if value < 12:
                out.putpixel((x, y), colors[1])
            elif value < 18:
                out.putpixel((x, y), colors[2])
            elif value < 21:
                out.putpixel((x, y), colors[3])

    if kind == "water":
        for y in range(4, size, 9):
            for x in range((y * 3) % 13 - 8, size, 25):
                if number(x, y, 5) % 3:
                    draw.line((x, y, x + 5, y - 1), fill=colors[3], width=1)
                    draw.point((x + 6, y), fill=colors[1])
    elif kind == "soil":
        for y in range(5, size, 7):
            for x in range((y * 5) % 11 - 5, size, 23):
                draw.line((x, y, x + 8, y), fill=colors[3], width=1)
    elif kind == "path":
        for i in range(36):
            x = number(i, 7, 3) % size
            y = number(i, 19, 7) % size
            draw.point((x, y), fill=colors[3])
            if number(i, 29, 11) % 2:
                draw.point((min(size - 1, x + 1), y), fill=colors[2])
    elif kind == "stone":
        # Irregular paving stones are deliberately larger and offset from the
        # simulation grid, so a paved square is still readable as a surface,
        # not as a set of map cells.
        for i in range(32):
            x = number(i, 2, 13) % size
            y = number(i, 31, 17) % size
            w = 7 + number(i, 41, 19) % 11
            h = 5 + number(i, 53, 23) % 8
            shade = colors[1 + number(i, 67, 29) % 3]
            points = [(x, y + 1), (x + 2, y), (x + w - 2, y),
                      (x + w, y + 2), (x + w - 1, y + h),
                      (x + 2, y + h - 1), (x, y + h - 2)]
            draw.polygon(points, fill=shade)
            draw.line((x + 1, y + h, x + w - 2, y + h), fill=colors[2], width=1)
    return out


def build_material_edges(surfaces: dict[str, Image.Image], tile_size: int = ART_TILE) -> dict[str, dict[str, list[int]]]:
    """Build irregular pixel-art interfaces for every broad material.

    The map still decides where each material cell is.  These transparent
    overlays soften the rendered boundary on both sides, so a grass field
    meeting stone, soil, or water is not a mathematically straight seam.
    """
    names = ["grass", "stone", "soil", "water"]
    directions = ["n", "e", "s", "w"]
    variants = 3
    sheet = Image.new("RGBA", (tile_size * len(names) * len(directions) * variants, tile_size),
                      (0, 0, 0, 0))
    mapping: dict[str, dict[str, list[int]]] = {}

    def number(x: int, y: int, salt: int = 0) -> int:
        value = (x * 374761393 + y * 668265263 + salt * 1442695041) & 0xffffffff
        value = ((value ^ (value >> 13)) * 1274126177) & 0xffffffff
        return (value ^ (value >> 16)) & 0x7fffffff

    frame_index = 0
    grass_edge = Image.new("RGB", (tile_size, tile_size), (82, 102, 34))
    grass_pixels = grass_edge.load()
    for y in range(tile_size):
        for x in range(tile_size):
            value = number(x, y, 71) % 10
            if value < 2:
                grass_pixels[x, y] = (112, 128, 42)
            elif value < 4:
                grass_pixels[x, y] = (65, 88, 31)
    surfaces = {**surfaces, "grass": grass_edge}
    for target_index, target in enumerate(names):
        mapping[target] = {}
        for direction_index, direction in enumerate(directions):
            mapping[target][direction] = []
            for variant in range(variants):
                edge = Image.new("L", (tile_size, tile_size), 0)
                for y in range(tile_size):
                    for x in range(tile_size):
                        across = {"n": y, "e": tile_size - 1 - x,
                                  "s": tile_size - 1 - y, "w": x}[direction]
                        along = x if direction in ("n", "s") else y
                        boundary = 2 + ((along * 7 + variant * 5 + target_index * 3) % 3)
                        if across <= boundary:
                            if target == "grass" and number(x, y, variant + target_index * 11) % 3:
                                continue
                            # A few missing pixels break up the contour while
                            # preserving a connected one-pixel lip at the seam.
                            if across > 0 and number(x, y, variant + target_index * 11) % 7 == 0:
                                continue
                            edge.putpixel((x, y), 255)
                frame = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
                frame.paste(surfaces[target].convert("RGBA"), (0, 0), edge)
                sheet.paste(frame, (frame_index * tile_size, 0), frame)
                mapping[target][direction].append(frame_index)
                frame_index += 1
    sheet.save(ASSETS / "style_material_edges.png")
    return mapping


def path_transition(path: Image.Image, mask: int, variant: int = 0,
                    tile_size: int = TILE) -> Image.Image:
    """Draw a dirt interface whose shape follows N/E/S/W connectivity.

    Grass is deliberately absent from this frame.  The map's grass field is
    underneath it; this overlay only paints the dirt footprint, allowing every
    disconnected edge to remain an organic grass-to-path boundary.
    """
    # Paths are overlays now.  The larger grass/path material fields underneath
    # provide the continuous ground, so each transition must not stamp a
    # second square of grass over its neighbours.
    out = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    shape = Image.new("L", (tile_size, tile_size), 0)
    draw = ImageDraw.Draw(shape)
    scale = tile_size / TILE
    def sx(value):
        return round(value * scale)
    def rect(box, fill=255):
        x0, y0, x1, y1 = box
        draw.rectangle((sx(x0), sx(y0), min(tile_size - 1, sx(x1 + 1) - 1),
                        min(tile_size - 1, sx(y1 + 1) - 1)), fill=fill)
    def polygon(points, fill=255):
        draw.polygon([(sx(x), sx(y)) for x, y in points], fill=fill)
    # The centreline moves by a couple of logical pixels between variants;
    # adjacent cells still connect at their shared edge, but long runs no
    # longer read as a ruler-straight grid road.
    lateral = (-1, 1, 0)[variant % 3]
    has_horizontal = bool(mask & (2 | 8))
    has_vertical = bool(mask & (1 | 4))
    dx = lateral if has_vertical and not has_horizontal else 0
    dy = lateral if has_horizontal and not has_vertical else 0
    if has_horizontal and has_vertical and mask in (3, 6, 9, 12):
        dx = lateral if mask in (3, 12) else 0
        dy = lateral if mask in (6, 9) else 0
    # Keep a generous grass shoulder inside each map cell. The old footprint
    # occupied nearly the whole cell, so a one-cell trail read as a road;
    # this is a six-pixel logical footpath at the normal 2x display scale.
    left, right = max(4, 5 + dx), min(11, 10 + dx)
    top, bottom = max(4, 5 + dy), min(11, 10 + dy)
    rect((left, top, right, bottom))
    # Keep each connected edge centred so the narrow trail remains visibly
    # continuous at the shared boundary; the lateral variant already gives
    # the route enough organic movement.
    offset = 0
    if mask & 1:
        polygon(((left + 1 + offset, 0), (right - 1 + offset, 0),
                 (right, top), (left, top)))
    if mask & 2:
        polygon(((right, top), (15, top + 1 + offset),
                 (15, bottom - 1 + offset), (right, bottom)))
    if mask & 4:
        polygon(((left, bottom), (right, bottom),
                 (right - 1 + offset, 15), (left + 1 + offset, 15)))
    if mask & 8:
        polygon(((0, top + 1 + offset), (left, top),
                 (left, bottom), (0, bottom - 1 + offset)))
    out.paste(path.convert("RGBA"), (0, 0), shape)
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
        return Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
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
    out = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    out.paste(shoreline.convert("RGBA"), (0, 0), shape)
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
    ground_base = [frame.resize((ART_TILE, ART_TILE), Image.Resampling.NEAREST)
                   for frame in base]
    material_files = {
        "ground": material_texture(ground_base, [0, 1], seed=11, block_size=ART_TILE),
        "path_ground": material_field("path"),
        "water_ground": material_field("water"),
        "soil_ground": material_field("soil"),
        "stone_ground": material_field("stone"),
    }
    for name, texture in material_files.items():
        texture.save(ASSETS / f"style_{name}.png")
    path_surface = material_field("path", size=TILE)
    material_edges = build_material_edges({
        "grass": material_texture(ground_base, [0, 1], blocks=1, seed=61, block_size=ART_TILE),
        "stone": material_field("stone", size=ART_TILE),
        "soil": material_field("soil", size=ART_TILE),
        "water": material_field("water", size=ART_TILE),
    })
    path_surface_hi = material_field("path", size=ART_TILE)
    path_tiles: dict[str, list[int]] = {
        str(mask): [mask * 3, mask * 3 + 1, mask * 3 + 2]
        for mask in range(16)
    }
    path_sheet = Image.new("RGBA", (ART_TILE * 16 * 3, ART_TILE), (0, 0, 0, 0))
    for mask in range(16):
        for variant in range(3):
            frame = path_transition(orient_path(path_surface_hi, mask, variant), mask, variant,
                                    tile_size=ART_TILE)
            path_sheet.paste(frame, (path_tiles[str(mask)][variant] * ART_TILE, 0))
    path_sheet.save(ASSETS / "style_path_tiles.png")
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
            frame = path_transition(path_surface, int(name[-2:]))
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
                orient_path(path_surface, mask, variant), mask, variant)
            index = path_variants[str(mask)][variant]
            sheet.paste(frame.convert("RGBA"), (index * TILE, 0))
    sheet.save(ASSETS / "style_tiles.png")
    return path_variants, path_tiles, material_edges


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


HELD_ITEM_NAMES = [
    "wooden_mug", "wooden_bowl", "wooden_ladle", "wooden_serving_spoon",
    "wooden_dipper", "pick", "axe", "hoe", "bread", "basket", "book",
    "hammer", "milk_pail", "shears", "fishing_rod", "parcel",
]


SQUARE_FIXTURE = 32
SQUARE_FIXTURE_NAMES = [
    "market_stall_bread", "market_stall_fish", "market_stall_cloth",
    "noticeboard", "well", "bench",
]


def build_square_fixtures() -> dict[str, int]:
    """Build correctly scaled, transparent pixel-art objects for the town square.

    These are world fixtures rather than 16px interior parts. Every frame is one displayed map
    cell (32px after the renderer's 2x terrain scale), with its feet on the cell baseline.
    """
    sheet = Image.new("RGBA", (SQUARE_FIXTURE * len(SQUARE_FIXTURE_NAMES), SQUARE_FIXTURE), (0, 0, 0, 0))
    sprites: dict[str, int] = {}
    dark = (67, 48, 43, 255)
    wood = (126, 77, 46, 255)
    wood_light = (181, 118, 62, 255)
    cream = (242, 202, 128, 255)

    def stall(colour: tuple[int, int, int, int], goods: tuple[int, int, int, int]):
        image = Image.new("RGBA", (SQUARE_FIXTURE, SQUARE_FIXTURE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        # canopy with scalloped lower edge
        draw.rectangle((3, 4, 28, 7), fill=dark)
        draw.rectangle((4, 7, 27, 12), fill=colour)
        for x in (4, 10, 16, 22):
            draw.rectangle((x, 7, min(27, x + 2), 12), fill=cream)
            draw.polygon(((x, 12), (min(27, x + 4), 12),
                          (min(27, x + 2), 15), (x + 1, 14)), fill=colour)
        # posts, counter, and two visible baskets/crates
        draw.rectangle((6, 12, 8, 25), fill=dark)
        draw.rectangle((24, 12, 26, 25), fill=dark)
        draw.rectangle((5, 20, 27, 25), fill=dark)
        draw.rectangle((7, 19, 25, 22), fill=wood_light)
        draw.rectangle((8, 23, 12, 27), fill=goods)
        draw.rectangle((20, 23, 24, 27), fill=goods)
        draw.line((8, 23, 12, 27), fill=wood)
        draw.line((12, 23, 8, 27), fill=wood)
        draw.line((20, 23, 24, 27), fill=wood)
        draw.line((24, 23, 20, 27), fill=wood)
        return image

    def noticeboard():
        image = Image.new("RGBA", (SQUARE_FIXTURE, SQUARE_FIXTURE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((14, 16, 17, 29), fill=dark)
        draw.rectangle((5, 5, 26, 19), fill=dark)
        draw.rectangle((7, 7, 24, 17), fill=wood_light)
        draw.rectangle((9, 9, 14, 14), fill=(246, 225, 168, 255))
        draw.rectangle((16, 10, 22, 15), fill=(224, 191, 126, 255))
        draw.point((10, 10), fill=(177, 69, 56, 255))
        return image

    def well():
        image = Image.new("RGBA", (SQUARE_FIXTURE, SQUARE_FIXTURE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((3, 15, 28, 29), fill=dark)
        draw.ellipse((5, 13, 26, 25), fill=(118, 133, 126, 255))
        draw.ellipse((9, 16, 22, 22), fill=(48, 91, 101, 255))
        draw.rectangle((7, 13, 24, 16), fill=(174, 171, 139, 255))
        draw.rectangle((8, 8, 10, 16), fill=wood)
        draw.rectangle((22, 8, 24, 16), fill=wood)
        draw.rectangle((8, 6, 24, 9), fill=dark)
        draw.line((15, 9, 15, 16), fill=wood_light, width=2)
        return image

    def bench():
        image = Image.new("RGBA", (SQUARE_FIXTURE, SQUARE_FIXTURE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((4, 13, 27, 17), fill=dark)
        draw.rectangle((5, 12, 26, 14), fill=wood_light)
        draw.rectangle((6, 20, 25, 23), fill=wood)
        draw.rectangle((8, 17, 10, 24), fill=dark)
        draw.rectangle((22, 17, 24, 24), fill=dark)
        return image

    images = [stall((181, 77, 65, 255), (202, 150, 71, 255)),
              stall((76, 123, 148, 255), (189, 149, 80, 255)),
              stall((169, 89, 124, 255), (103, 137, 80, 255)),
              noticeboard(), well(), bench()]
    for index, (name, image) in enumerate(zip(SQUARE_FIXTURE_NAMES, images)):
        sheet.alpha_composite(image, (index * SQUARE_FIXTURE, 0))
        sprites[name] = index
    sheet.save(ASSETS / "style_square_fixtures.png")
    return sprites


def build_held_items(manifest: dict, item_sheet: Image.Image) -> dict[str, int]:
    """Build recognizable small hand-held art for common carried objects."""
    cells = [grid_cell(item_sheet, 4, 4, i) for i in range(16)]
    sheet = Image.new("RGBA", (HELD_ITEM * len(HELD_ITEM_NAMES), HELD_ITEM), (0, 0, 0, 0))
    sprites = {}
    for index, name in enumerate(HELD_ITEM_NAMES):
        frame = fit_sprite(cells[index], (HELD_ITEM, HELD_ITEM), pad=0, bottom=False)
        sheet.alpha_composite(frame, (index * HELD_ITEM, 0))
        sprites[name] = index
    sheet.save(ASSETS / "style_held_items.png")
    return sprites


def main() -> None:
    manifest = json.loads((ASSETS / "manifest.json").read_text())
    terrain = Image.open(ASSETS / "style_terrain_atlas_source.png")
    buildings = Image.open(ASSETS / "style_building_atlas_source.png")
    cutaways = Image.open(ASSETS / "style_cutaway_atlas_source.png")
    characters = Image.open(ASSETS / "style_character_walk_atlas_source.png")
    held_items = Image.open(ASSETS / "style_held_items_atlas_source.png")
    old_tiles = Image.open(ASSETS / "tileset.png")
    reference = Image.open(ASSETS / "style_source_village.png").convert("RGB")
    path_variants, path_tiles, material_edges = build_tiles(manifest, terrain, reference, old_tiles)
    prop_sprites = build_props(terrain)
    sprites = build_buildings(manifest, buildings)
    cutaway_sprites = build_cutaways(manifest, cutaways)
    build_characters(manifest, characters)
    held_item_sprites = build_held_items(manifest, held_items)
    square_fixture_sprites = build_square_fixtures()
    out_manifest = {
        "source": "style_source_village.png",
        "terrain_source": "style_terrain_atlas_source.png",
        "building_source": "style_building_atlas_source.png",
        "cutaway_source": "style_cutaway_atlas_source.png",
        "character_source": "style_character_walk_atlas_source.png",
        "held_item_source": "style_held_items_atlas_source.png",
        "tiles": {"file": "style_tiles.png", "frame": TILE,
                  "tiles": manifest["tileset"]["tiles"]},
        "materials": {
            "logical_tile": TILE,
            "texture_scale": 1,
            "fields": {
                "ground": "style_ground.png",
                "path": "style_path_ground.png",
                "water": "style_water_ground.png",
                "soil": "style_soil_ground.png",
                "stone": "style_stone_ground.png",
            },
        },
        "material_edges": {"file": "style_material_edges.png", "frame": ART_TILE,
                           "targets": material_edges},
        "path_variants": path_variants,
        "path_tiles": {"file": "style_path_tiles.png", "frame": ART_TILE,
                        "variants": path_tiles},
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
        "held_items": {"file": "style_held_items.png", "frame": HELD_ITEM,
                       "sprites": held_item_sprites},
        "square_fixtures": {"file": "style_square_fixtures.png", "frame": SQUARE_FIXTURE,
                             "sprites": square_fixture_sprites},
    }
    (ASSETS / "style_manifest.json").write_text(json.dumps(out_manifest, indent=2) + "\n")
    print("wrote style_tiles.png style_ground.png style_path_ground.png style_water_ground.png "
        "style_soil_ground.png style_stone_ground.png style_material_edges.png "
          "style_path_tiles.png style_props.png style_large_props.png style_buildings.png "
          "style_square_fixtures.png "
          "style_manifest.json")


if __name__ == "__main__":
    main()
