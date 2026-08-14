#!/usr/bin/env python3
"""Reproducible pixel-art asset generator for TownView.

Draws a cohesive, Stardew-esque asset set from a tight warm palette and writes:

    tileset.png      - 16x16 terrain/prop tiles (horizontal strip)
    characters.png   - a 16x16 humanoid, 3 walk frames x 4 directions (recolourable
                       at runtime by MULTIPLY-tinting the light body)
    buildings.png    - 48x48 institution sprites (horizontal strip)
    manifest.json    - names every asset + its frame geometry (the reusable list)

Zero third-party dependencies: a minimal stdlib PNG encoder (zlib + struct) so the
assets regenerate anywhere Python runs. Deterministic -> byte-stable output.

Run:  python3 web/townview/assets/generate_assets.py
"""
from __future__ import annotations
import json
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
try:
    from domains import bigville_entities as E
except Exception:  # keep the art generator usable as a standalone utility
    E = None

# ----------------------------------------------------------------------------
# minimal RGBA image + stdlib PNG writer
# ----------------------------------------------------------------------------


class Img:
    __slots__ = ("w", "h", "px")

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 4)  # RGBA, transparent

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 4
            self.px[i:i + 4] = bytes(c)

    def rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set(xx, yy, c)

    def blit(self, src, dx, dy):
        for yy in range(src.h):
            for xx in range(src.w):
                i = (yy * src.w + xx) * 4
                if src.px[i + 3]:
                    self.set(dx + xx, dy + yy, src.px[i:i + 4])


def write_png(img: Img, path: str):
    raw = bytearray()
    for y in range(img.h):
        raw.append(0)  # filter type 0
        raw += img.px[y * img.w * 4:(y + 1) * img.w * 4]

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))

    ihdr = struct.pack(">IIBBBBB", img.w, img.h, 8, 6, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))


def rgba(h, a=255):
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def _mix(a, b, amount):
    return tuple(round(a[i] * (1.0 - amount) + b[i] * amount) for i in range(4))


def _name_color(name, palette):
    value = 0
    for char in name:
        value = (value * 33 + ord(char)) & 0x7fffffff
    return palette[value % len(palette)]


# ----------------------------------------------------------------------------
# palette (warm, cohesive)
# ----------------------------------------------------------------------------
PAL = {
    "grass_a": rgba("7cb35a"), "grass_b": rgba("6fa74e"), "grass_c": rgba("8cc169"),
    "dirt_a": rgba("b98a54"), "dirt_b": rgba("a97a46"),
    "path_a": rgba("c9b98f"), "path_b": rgba("bdab7e"),
    "square_a": rgba("d3c49a"), "square_b": rgba("c2b184"), "square_edge": rgba("a9976c"),
    "water_a": rgba("4f97c9"), "water_b": rgba("6fb1dd"), "water_c": rgba("3f82b4"),
    "floor_a": rgba("caa877"), "floor_b": rgba("b8965f"),
    "wall_a": rgba("806c58"), "wall_b": rgba("6d5a48"),
    "trunk": rgba("6b4a2f"), "leaf_a": rgba("3f7d3a"), "leaf_b": rgba("4e9145"),
    "flower_r": rgba("d1584e"), "flower_y": rgba("e5b93b"), "petal": rgba("f0e7d2"),
    "stone_a": rgba("9a8f7e"), "stone_b": rgba("857a68"),
    "sand": rgba("d8c79a"),
    # character
    "skin": rgba("e6b892"), "skin_sh": rgba("cf9e78"),
    "hair": rgba("4a3524"), "body": rgba("dcdcd2"), "body_sh": rgba("bfbfb4"),
    "boot": rgba("5a4632"), "eye": rgba("2a2620"),
    # buildings
    "roof_red": rgba("b1543e"), "roof_blue": rgba("46708f"), "roof_green": rgba("4f8355"),
    "roof_gold": rgba("cf9a3a"), "roof_gray": rgba("7d7266"), "roof_purple": rgba("6d5a86"),
    "roof_teal": rgba("357f7c"), "roof_brown": rgba("8a6a44"),
    "brick_a": rgba("d8c7a6"), "brick_b": rgba("c8b592"),
    "door": rgba("6b4a2f"), "win": rgba("bfe1ef"), "trim": rgba("efe6d2"),
    "shadow": rgba("00000030"),
}

T = 16  # tile size

# ----------------------------------------------------------------------------
# terrain tiles
# ----------------------------------------------------------------------------


def _speckle(img, base, spA, spB, seed):
    img.rect(0, 0, T, T, PAL[base])
    r = seed
    for y in range(T):
        for x in range(T):
            r = (r * 1103515245 + 12345) & 0x7fffffff
            v = r % 100
            if v < 8:
                img.set(x, y, PAL[spA])
            elif v < 14:
                img.set(x, y, PAL[spB])
    # A few little clustered blades make a meadow tile feel hand-placed rather
    # than dithered. The fixed seed keeps every generated map reproducible.
    for i in range(4):
        x = (seed * 5 + i * 7) % (T - 2) + 1
        y = (seed * 3 + i * 5) % (T - 3) + 2
        img.set(x, y, PAL[spA])
        img.set(x + 1, y - 1, PAL[spA])


def tile_grass(v=0):
    im = Img(T, T)
    _speckle(im, "grass_a", "grass_b", "grass_c", 7 + v)
    return im


def tile_path():
    im = Img(T, T)
    _speckle(im, "path_a", "path_b", "dirt_a", 31)
    for x, y in ((2, 3), (12, 6), (6, 12), (14, 13)):
        im.set(x, y, PAL["dirt_b"])
    return im


def tile_dirt():
    im = Img(T, T)
    _speckle(im, "dirt_a", "dirt_b", "path_b", 53)
    return im


def tile_square():
    im = Img(T, T)
    im.rect(0, 0, T, T, PAL["square_a"])
    for y in range(T):
        for x in range(T):
            if (x % 8 == 0) or (y % 8 == 0):
                im.set(x, y, PAL["square_edge"])
            elif ((x // 8) + (y // 8)) % 2 == 0 and (x % 8 in (1, 2)):
                im.set(x, y, PAL["square_b"])
    return im


def tile_floor():
    im = Img(T, T)
    im.rect(0, 0, T, T, PAL["floor_a"])
    for y in range(0, T, 4):
        im.rect(0, y, T, 1, PAL["floor_b"])
    return im


def tile_wall():
    im = Img(T, T)
    im.rect(0, 0, T, T, PAL["wall_a"])
    for y in range(0, T, 4):
        im.rect(0, y, T, 1, PAL["wall_b"])
    for x in range(0, T, 8):
        im.rect(x, 0, 1, T, PAL["wall_b"])
    return im


def tile_water():
    im = Img(T, T)
    _speckle(im, "water_a", "water_b", "water_c", 91)
    for x in range(2, T, 6):
        im.set(x, 4, PAL["water_b"])
        im.set(x + 1, 4, PAL["water_b"])
        im.set(x + 3, 10, PAL["water_b"])
    return im


def tile_sand():
    im = Img(T, T)
    _speckle(im, "sand", "path_a", "dirt_a", 17)
    return im


def tile_tree():
    im = tile_grass(1)
    im.rect(7, 10, 2, 5, PAL["trunk"])
    for (cx, cy, rr) in ((8, 6, 5), (5, 8, 3), (11, 8, 3)):
        for y in range(cy - rr, cy + rr):
            for x in range(cx - rr, cx + rr):
                if (x - cx) ** 2 + (y - cy) ** 2 <= rr * rr:
                    im.set(x, y, PAL["leaf_a"] if (x + y) % 3 else PAL["leaf_b"])
    return im


def tile_bush():
    im = tile_grass(2)
    for (cx, cy, rr) in ((6, 10, 3), (10, 10, 3), (8, 8, 3)):
        for y in range(cy - rr, cy + rr):
            for x in range(cx - rr, cx + rr):
                if (x - cx) ** 2 + (y - cy) ** 2 <= rr * rr:
                    im.set(x, y, PAL["leaf_b"] if (x + y) % 2 else PAL["leaf_a"])
    return im


def tile_flower():
    im = tile_grass(3)
    for (cx, cy, col) in ((5, 6, "flower_r"), (11, 9, "flower_y"), (8, 11, "flower_r")):
        im.set(cx, cy, PAL["petal"])
        im.set(cx - 1, cy, PAL[col])
        im.set(cx + 1, cy, PAL[col])
        im.set(cx, cy - 1, PAL[col])
        im.set(cx, cy + 1, PAL[col])
    return im


def tile_rocks():
    im = tile_grass(4)
    for (cx, cy, rr) in ((6, 9, 3), (10, 10, 2), (9, 6, 2)):
        for y in range(cy - rr, cy + rr):
            for x in range(cx - rr, cx + rr):
                if (x - cx) ** 2 + (y - cy) ** 2 <= rr * rr:
                    im.set(x, y, PAL["stone_a"] if (x + y) % 2 else PAL["stone_b"])
    return im


def tile_well():
    im = tile_grass(5)
    im.rect(4, 4, 8, 8, PAL["stone_b"])
    im.rect(5, 5, 6, 6, PAL["water_a"])
    im.rect(4, 4, 8, 1, PAL["stone_a"])
    return im


def tile_crop():
    im = tile_dirt()
    for x in range(2, T, 4):
        im.rect(x, 2, 1, T - 4, PAL["leaf_a"])
        im.set(x, 3, PAL["flower_y"])
    return im


TILES = [
    ("grass", tile_grass(0)), ("grass_alt", tile_grass(2)), ("path", tile_path()),
    ("dirt", tile_dirt()), ("square", tile_square()), ("floor", tile_floor()),
    ("wall", tile_wall()), ("water", tile_water()), ("sand", tile_sand()),
    ("tree", tile_tree()), ("bush", tile_bush()), ("flower", tile_flower()),
    ("rocks", tile_rocks()), ("well", tile_well()), ("crop", tile_crop()),
]


def tile_variant(base, accent, seed):
    im = base()
    for y in range(1, T - 1):
        x = (seed * 7 + y * 3) % (T - 2) + 1
        im.set(x, y, PAL[accent])
        if y % 4 == 0:
            im.set((x + 1) % T, y, PAL[accent])
    return im


def tile_tilled():
    im = tile_dirt()
    for y in range(3, T, 4):
        im.rect(0, y, T, 1, PAL["dirt_b"])
    return im


def tile_wet_tilled():
    im = tile_tilled()
    for x in range(2, T, 5):
        im.rect(x, 2, 1, 10, PAL["water_c"])
    return im


def tile_fence():
    im = tile_grass(6)
    im.rect(1, 6, 14, 2, PAL["trunk"]); im.rect(1, 11, 14, 2, PAL["trunk"])
    for x in (2, 7, 12):
        im.rect(x, 4, 2, 11, PAL["trunk"])
    return im


def tile_bridge():
    im = Img(T, T); im.rect(0, 0, T, T, PAL["water_a"])
    for x in range(0, T, 4):
        im.rect(x, 0, 3, T, PAL["floor_a"])
        im.rect(x, 0, 1, T, PAL["floor_b"])
    return im


def tile_roof():
    im = Img(T, T); im.rect(0, 0, T, T, PAL["roof_red"])
    for y in range(0, T, 4):
        im.rect(0, y, T, 1, PAL["roof_brown"])
    for x in range(2, T, 5):
        im.rect(x, 0, 1, T, PAL["roof_brown"])
    return im


def tile_snow():
    im = Img(T, T); im.rect(0, 0, T, T, rgba("d8e2e6"))
    for x, y in ((2, 4), (11, 7), (6, 13), (14, 2)):
        im.set(x, y, rgba("b8ccd3"))
    return im


def tile_mud():
    return tile_variant(tile_dirt, "dirt_b", 11)


EXTRA_TILES = [
    ("mud", tile_mud()), ("tilled", tile_tilled()), ("tilled_wet", tile_wet_tilled()),
    ("fence", tile_fence()), ("bridge", tile_bridge()), ("roof", tile_roof()),
    ("snow", tile_snow()), ("grass_wet", tile_variant(lambda: tile_grass(4), "water_b", 5)),
    ("grass_autumn", tile_variant(lambda: tile_grass(1), "flower_y", 8)),
    ("wheat_young", tile_variant(tile_crop, "grass_c", 2)),
    ("wheat_mature", tile_variant(tile_crop, "flower_y", 9)),
    ("barley_mature", tile_variant(tile_crop, "roof_gold", 13)),
    ("cabbage", tile_variant(tile_crop, "leaf_b", 17)),
]
TILES.extend(EXTRA_TILES)


def _path_transition(mask):
    """A path tile with organic grass edges selected by cardinal neighbours."""
    im = tile_grass(mask % 3)
    im.rect(5, 5, 6, 6, PAL["path_a"])
    if mask & 1: im.rect(5, 0, 6, 7, PAL["path_a"])
    if mask & 2: im.rect(9, 5, 7, 6, PAL["path_a"])
    if mask & 4: im.rect(5, 9, 6, 7, PAL["path_a"])
    if mask & 8: im.rect(0, 5, 7, 6, PAL["path_a"])
    # Soft, irregular verge pixels break the geometric edge while retaining a
    # clear walkable centre and a readable corner/branch silhouette.
    for i in range(7):
        x = (mask * 5 + i * 3) % 16
        y = (mask * 7 + i * 5) % 16
        if im.px[(y * T + x) * 4 + 1] > 100:
            im.set(x, y, PAL["dirt_b"])
            if x + 1 < T and y % 2 == 0:
                im.set(x + 1, y, PAL["path_b"])
    return im


def _water_transition(mask):
    """A water cell whose shoreline follows the surrounding water cells."""
    im = tile_grass((mask + 1) % 3)
    im.rect(5, 5, 6, 6, PAL["water_a"])
    if mask & 1: im.rect(5, 0, 6, 7, PAL["water_a"])
    if mask & 2: im.rect(9, 5, 7, 6, PAL["water_a"])
    if mask & 4: im.rect(5, 9, 6, 7, PAL["water_a"])
    if mask & 8: im.rect(0, 5, 7, 6, PAL["water_a"])
    # A pale shoreline highlight makes the water/grass boundary legible at
    # overview scale and gives reeds a natural edge to sit against.
    for x in range(2, 15, 6):
        im.set(x, 5 + (mask % 3), PAL["water_b"])
    return im


for _mask in range(16):
    TILES.append((f"path_transition_{_mask:02d}", _path_transition(_mask)))
for _mask in range(16):
    TILES.append((f"water_transition_{_mask:02d}", _water_transition(_mask)))


PROP_NAMES = ["tree", "flower_clump", "bush", "grass_tuft", "stone", "mushroom", "reed", "log", "barrel", "bench", "stump"]


def large_prop_sprite(name):
    """32px foliage silhouettes for the close 2x village view."""
    size = 32
    im = Img(size, size)
    if name == "tree":
        im.rect(14, 18, 5, 14, PAL["trunk"])
        for cx, cy, rr, col in ((13, 12, 10, "leaf_a"), (21, 13, 9, "leaf_b"), (8, 18, 7, "leaf_b"), (18, 8, 7, "leaf_a")):
            for yy in range(cy - rr, cy + rr + 1):
                for xx in range(cx - rr, cx + rr + 1):
                    if (xx - cx) ** 2 + (yy - cy) ** 2 <= rr * rr:
                        im.set(xx, yy, PAL[col])
        for x, y in ((9, 7), (17, 5), (22, 10), (5, 17)):
            im.rect(x, y, 3, 2, PAL["grass_c"])
    elif name == "bush":
        for cx, cy, rr, col in ((9, 19, 8, "leaf_a"), (17, 15, 10, "leaf_b"), (25, 20, 8, "leaf_a")):
            for yy in range(cy - rr, cy + rr + 1):
                for xx in range(cx - rr, cx + rr + 1):
                    if (xx - cx) ** 2 + (yy - cy) ** 2 <= rr * rr:
                        im.set(xx, yy, PAL[col])
        im.rect(5, 25, 23, 5, PAL["leaf_a"])
    return im


def prop_sprite(name):
    im = Img(T, T)
    if name == "tree":
        im.rect(7, 10, 3, 6, PAL["trunk"])
        for cx, cy, rr, col in ((7, 6, 5, "leaf_a"), (11, 7, 4, "leaf_b"), (4, 9, 3, "leaf_b")):
            for yy in range(cy - rr, cy + rr + 1):
                for xx in range(cx - rr, cx + rr + 1):
                    if (xx - cx) ** 2 + (yy - cy) ** 2 <= rr * rr:
                        im.set(xx, yy, PAL[col])
        im.set(6, 4, PAL["grass_c"]); im.set(10, 5, PAL["grass_c"])
    elif name == "flower_clump":
        for x, y, col in ((4, 7, "flower_y"), (8, 4, "flower_r"), (12, 7, "petal")):
            im.rect(x, y + 2, 2, 7, PAL["leaf_a"])
            im.set(x, y, PAL[col]); im.rect(x - 1, y + 1, 4, 2, PAL[col])
            im.set(x + 1, y + 2, PAL["petal"])
    elif name == "bush":
        for cx, cy, rr, col in ((5, 9, 4, "leaf_a"), (10, 8, 5, "leaf_b"), (13, 10, 3, "leaf_a")):
            for yy in range(cy - rr, cy + rr + 1):
                for xx in range(cx - rr, cx + rr + 1):
                    if (xx - cx) ** 2 + (yy - cy) ** 2 <= rr * rr:
                        im.set(xx, yy, PAL[col])
        im.rect(4, 12, 10, 2, PAL["leaf_a"])
    elif name == "grass_tuft":
        for x in (4, 7, 10, 13):
            im.rect(x, 7 - (x % 3), 1, 8, PAL["leaf_a"]); im.set(x + 1, 6, PAL["leaf_b"])
    elif name == "stone":
        im.rect(2, 10, 12, 4, PAL["stone_b"]); im.rect(4, 7, 8, 4, PAL["stone_a"])
        im.rect(6, 7, 4, 1, PAL["trim"])
    elif name == "mushroom":
        im.rect(7, 8, 2, 6, PAL["trim"]); im.rect(4, 6, 8, 3, PAL["flower_r"]); im.set(6, 6, PAL["petal"]); im.set(10, 7, PAL["petal"])
    elif name == "reed":
        for x in (4, 7, 10, 13):
            im.rect(x, 3 + x % 3, 1, 12, PAL["leaf_a"]); im.set(x + 1, 3 + x % 3, PAL["leaf_b"])
    elif name == "log":
        im.rect(2, 9, 12, 4, PAL["trunk"]); im.rect(3, 8, 10, 1, PAL["floor_b"]); im.set(3, 10, PAL["trim"])
    elif name == "barrel":
        im.rect(5, 4, 7, 10, PAL["floor_b"]); im.rect(4, 5, 9, 2, PAL["trunk"]); im.rect(4, 11, 9, 2, PAL["trunk"])
    elif name == "bench":
        im.rect(2, 7, 12, 3, PAL["floor_b"]); im.rect(3, 10, 2, 5, PAL["trunk"]); im.rect(11, 10, 2, 5, PAL["trunk"])
    elif name == "stump":
        im.rect(5, 7, 7, 8, PAL["trunk"]); im.rect(4, 5, 9, 4, PAL["floor_b"]); im.rect(7, 6, 3, 1, PAL["door"])
    return im


# ---------------------------------------------------------------------------
# item icons -- every item in bigville_entities.ITEMS gets a stable 16x16 icon.
# The icons are deliberately small and silhouette-led so the sheet remains
# usable at 1x, 2x, and 3x without interpolation.

ICON_PALETTE = [PAL["roof_red"], PAL["roof_gold"], PAL["roof_green"], PAL["roof_blue"],
                PAL["roof_purple"], PAL["floor_a"], PAL["water_a"], PAL["flower_y"]]


def item_icon(kind, spec):
    im = Img(T, T)
    ink = PAL["eye"]
    accent = _name_color(kind, ICON_PALETTE)
    light = _mix(accent, PAL["trim"], 0.45)
    material = str(spec.get("material", ""))
    food = bool(spec.get("food"))
    seed = bool(spec.get("seed")) or kind.endswith("_seed")
    tool = spec.get("class") == "tool"
    garment = bool(spec.get("garment"))
    container = bool(spec.get("container"))
    if seed:
        im.rect(4, 2, 8, 12, accent); im.rect(5, 3, 6, 10, light)
        im.rect(7, 5, 2, 2, PAL["leaf_a"]); im.rect(9, 8, 2, 2, PAL["leaf_a"])
    elif tool and kind == "pick":
        # A pick must read as a pick at 1x, not as the generic tool silhouette.
        for i in range(9):
            im.rect(6 + i // 3, 7 + i, 2, 2, PAL["trunk"])
        im.rect(2, 4, 11, 2, PAL["stone_a"]); im.rect(3, 3, 2, 4, PAL["stone_b"])
        im.rect(11, 3, 2, 4, PAL["stone_b"])
    elif tool and kind == "axe":
        for i in range(9): im.rect(4 + i, 5 + i, 2, 2, PAL["trunk"])
        im.rect(9, 2, 5, 6, PAL["stone_a"]); im.rect(11, 3, 3, 4, PAL["stone_b"])
    elif tool and kind == "spade":
        im.rect(7, 2, 2, 10, PAL["trunk"]); im.rect(5, 11, 6, 3, PAL["stone_a"])
        im.rect(6, 13, 4, 2, PAL["stone_b"])
    elif tool and kind == "rake":
        im.rect(7, 3, 2, 11, PAL["trunk"]); im.rect(3, 3, 10, 2, PAL["stone_a"])
        for x in (3, 6, 9, 12): im.rect(x, 4, 1, 4, PAL["stone_b"])
    elif tool and kind == "scythe":
        for i in range(9): im.rect(4 + i, 12 - i // 2, 2, 2, PAL["trunk"])
        im.rect(9, 2, 2, 8, PAL["stone_a"]); im.rect(10, 2, 4, 2, PAL["stone_b"])
    elif tool:
        im.rect(2, 10, 11, 2, PAL["trunk"]); im.rect(10, 3, 4, 6, PAL["stone_a"])
        im.rect(11, 3, 2, 2, PAL["stone_b"]); im.set(3, 10, ink)
    elif garment:
        im.rect(4, 3, 8, 2, accent); im.rect(2, 5, 12, 7, accent)
        im.rect(4, 12, 3, 2, accent); im.rect(9, 12, 3, 2, accent)
        im.rect(7, 5, 2, 8, light)
    elif container:
        im.rect(3, 5, 10, 8, accent); im.rect(4, 4, 8, 2, light)
        im.rect(5, 6, 6, 5, PAL["floor_b"] if material == "wood" else PAL["stone_b"])
        if "mug" in kind:
            im.rect(12, 7, 2, 4, accent)
    elif food:
        if any(word in kind for word in ("soup", "stew", "porridge", "pottage", "gruel", "pudding")):
            im.rect(2, 7, 12, 5, accent); im.rect(4, 5, 8, 3, light)
            im.rect(5, 3, 1, 3, PAL["steam"] if "steam" in PAL else PAL["trim"])
        elif any(word in kind for word in ("bread", "cake", "pie", "loaf", "cracker", "flatbread", "dumpling")):
            im.rect(2, 6, 12, 7, accent); im.rect(4, 4, 8, 3, light)
            im.rect(5, 6, 1, 4, PAL["roof_brown"]); im.rect(9, 6, 1, 4, PAL["roof_brown"])
        else:
            im.rect(3, 6, 10, 6, accent); im.rect(5, 4, 6, 3, light)
            im.set(7, 7, PAL["flower_y"]); im.set(9, 9, PAL["leaf_a"])
    elif kind in {"coin", "nails", "hinge", "weld", "ore", "iron", "charcoal"}:
        im.rect(3, 5, 10, 7, PAL["stone_a"]); im.rect(5, 3, 6, 3, light)
        im.set(8, 7, accent)
    elif any(word in kind for word in ("cloth", "linen", "silk", "wool", "thread", "rag", "leather")):
        im.rect(3, 4, 10, 9, accent); im.rect(5, 2, 6, 3, light)
        for y in (6, 9): im.rect(4, y, 8, 1, PAL["trim"])
    else:
        im.rect(3, 5, 10, 8, accent); im.rect(5, 3, 6, 3, light)
        im.rect(5, 7, 6, 1, PAL["trim"]); im.set(8, 10, PAL["leaf_a"])
    # A one-pixel dark silhouette edge makes the generated icon set readable.
    for x, y in ((2, 6), (13, 6), (3, 13), (12, 13)):
        im.set(x, y, ink)
    return im


def build_item_sheet():
    kinds = sorted(E.ITEMS) if E is not None else []
    cols = 16
    rows = max(1, (len(kinds) + cols - 1) // cols)
    sheet = Img(cols * T, rows * T)
    index = {}
    for i, kind in enumerate(kinds):
        x, y = i % cols, i // cols
        sheet.blit(item_icon(kind, E.ITEMS[kind]), x * T, y * T)
        index[kind] = {"x": x, "y": y, "frame": i}
    return sheet, index, cols, rows

# ----------------------------------------------------------------------------
# character: 3 frames x 4 directions, 16x16. Body drawn LIGHT so a runtime
# MULTIPLY tint recolours the outfit per resident while keeping shading + outline.
# directions: 0=down 1=up 2=left 3=right ; frames: 0=idle 1=stepA 2=stepB
# ----------------------------------------------------------------------------
DIRS = ["down", "up", "left", "right"]


def char_frame(direction, frame):
    im = Img(T, T)
    legoff = {0: 0, 1: 1, 2: -1}[frame]  # walk bob per leg
    # legs / boots
    im.rect(6, 13 + (legoff if legoff > 0 else 0), 2, 2, PAL["boot"])
    im.rect(9, 13 + (0 if legoff > 0 else -legoff), 2, 2, PAL["boot"])
    # body (tintable)
    im.rect(5, 8, 6, 5, PAL["body"])
    im.rect(5, 8, 1, 5, PAL["body_sh"])
    im.rect(10, 8, 1, 5, PAL["body_sh"])
    # arms
    im.rect(4, 8, 1, 4, PAL["body_sh"])
    im.rect(11, 8, 1, 4, PAL["body_sh"])
    # head
    im.rect(5, 3, 6, 5, PAL["skin"])
    im.rect(5, 7, 6, 1, PAL["skin_sh"])
    # hair + face by direction
    if direction == "up":
        im.rect(4, 2, 8, 4, PAL["hair"])
        im.rect(5, 5, 6, 1, PAL["hair"])
    elif direction == "down":
        im.rect(4, 2, 8, 3, PAL["hair"])
        im.rect(4, 4, 1, 2, PAL["hair"])
        im.rect(11, 4, 1, 2, PAL["hair"])
        im.set(6, 5, PAL["eye"]); im.set(9, 5, PAL["eye"])
        im.rect(7, 6, 2, 1, PAL["skin_sh"])
    else:  # left / right profile
        im.rect(4, 2, 8, 3, PAL["hair"])
        if direction == "left":
            im.rect(4, 3, 1, 3, PAL["hair"])
            im.set(6, 5, PAL["eye"])
        else:
            im.rect(11, 3, 1, 3, PAL["hair"])
            im.set(9, 5, PAL["eye"])
    return im


CHAR_VARIANTS = [
    "adult", "child", "elder", "farmer", "smith", "cook", "clerk",
    "constable", "councillor", "merchant", "teacher", "doctor", "shepherd",
    "builder", "fisher", "craftsperson",
]
VARIANT_COLORS = {
    "adult": "body", "child": "roof_gold", "elder": "roof_purple",
    "farmer": "roof_green", "smith": "roof_gray", "cook": "roof_red",
    "clerk": "roof_blue", "constable": "roof_blue", "councillor": "roof_gold",
    "merchant": "roof_teal", "teacher": "roof_green", "doctor": "roof_gray",
    "shepherd": "roof_brown", "builder": "roof_red", "fisher": "water_a",
    "craftsperson": "roof_purple",
}


def char_variant_frame(variant, direction, frame):
    im = char_frame(direction, frame)
    accent = PAL[VARIANT_COLORS[variant]]
    # Role/age cues stay simple because the base body is still recolourable at
    # runtime by the town renderer.
    if variant == "child":
        im.rect(6, 7, 4, 1, accent)
        im.rect(7, 12, 1, 2, PAL["boot"]); im.rect(9, 12, 1, 2, PAL["boot"])
    elif variant == "elder":
        im.rect(5, 6, 6, 1, PAL["trim"])
    elif variant in {"farmer", "shepherd"}:
        im.rect(4, 4, 8, 1, accent); im.rect(5, 3, 6, 1, accent)
        im.rect(12, 8, 1, 5, PAL["trunk"])
    elif variant == "smith":
        im.rect(3, 9, 2, 3, PAL["stone_a"]); im.rect(12, 9, 2, 3, PAL["stone_a"])
    elif variant == "cook":
        im.rect(4, 2, 8, 2, PAL["trim"]); im.rect(6, 1, 4, 1, PAL["trim"])
    elif variant in {"clerk", "teacher", "doctor"}:
        im.rect(6, 8, 4, 1, accent)
    elif variant == "constable":
        im.rect(5, 2, 6, 2, accent); im.rect(7, 1, 2, 1, accent)
    elif variant == "councillor":
        im.rect(4, 8, 8, 1, PAL["roof_gold"])
    elif variant == "merchant":
        im.rect(3, 7, 2, 5, accent); im.rect(12, 7, 1, 5, accent)
    elif variant == "fisher":
        im.rect(12, 5, 1, 8, PAL["trunk"])
    elif variant == "builder":
        im.rect(12, 8, 2, 2, PAL["stone_a"])
    return im


ACTION_NAMES = [
    "idle", "walk", "sow", "water", "harvest", "chop", "mine", "fish",
    "cook", "bake", "build", "repair", "write", "speak", "carry", "milk",
    "shear", "eat", "rest", "accept", "decline",
]


def action_frame(action, frame):
    # Four compact keyframes: anticipation, contact, recovery, neutral.  The
    # action sheet is intentionally independent of facing; the renderer can
    # flip/select a direction later without changing the action vocabulary.
    im = char_frame("down", frame % 3)
    accent = PAL[VARIANT_COLORS.get("farmer", "roof_green")]
    reach = (frame % 4) - 1
    if action in {"sow", "water", "harvest"}:
        im.rect(12, 6 + max(0, reach), 1, 7, PAL["leaf_a"])
        im.set(13, 13, PAL["dirt_b"])
    elif action in {"chop", "mine", "repair"}:
        im.rect(11 + max(0, reach), 4, 2, 7, PAL["trunk"])
        im.rect(10 + max(0, reach), 3, 4, 3, PAL["stone_a"])
    elif action in {"cook", "bake"}:
        im.rect(2, 11, 12, 2, PAL["stone_b"]); im.rect(5, 8, 6, 3, PAL["floor_b"])
        im.set(7 + max(0, reach), 7, PAL["flower_y"])
    elif action == "build":
        im.rect(12, 5, 2, 7, PAL["trunk"]); im.rect(11, 4, 4, 2, PAL["stone_a"])
    elif action == "write":
        im.rect(10, 9, 4, 3, PAL["trim"]); im.set(12 + max(0, reach), 8, PAL["eye"])
    elif action in {"speak", "accept", "decline"}:
        im.rect(12 + max(0, reach), 5, 2, 2, PAL["trim"])
    elif action == "carry":
        im.rect(1, 9, 4, 4, PAL["floor_b"])
    elif action == "milk":
        im.rect(12, 9, 3, 4, PAL["trim"])
    elif action == "shear":
        im.rect(12, 7, 3, 3, PAL["stone_a"])
    elif action == "eat":
        im.rect(11, 6, 3, 3, accent)
    elif action == "rest":
        im.rect(3, 13, 10, 2, PAL["floor_b"])
    return im


def build_animation_sheets():
    variants = Img(T * 3, T * 4 * len(CHAR_VARIANTS))
    for vi, variant in enumerate(CHAR_VARIANTS):
        for di, direction in enumerate(DIRS):
            for frame in range(3):
                variants.blit(char_variant_frame(variant, direction, frame),
                              frame * T, (vi * 4 + di) * T)
    actions = Img(T * 4, T * len(ACTION_NAMES))
    for row, action in enumerate(ACTION_NAMES):
        for frame in range(4):
            actions.blit(action_frame(action, frame), frame * T, row * T)
    return variants, actions

# ----------------------------------------------------------------------------
# buildings: 48x48, per-institution roof colour + signage motif
# ----------------------------------------------------------------------------
B = 48


# Modular building vocabulary.  These parts are intentionally one terrain
# cell each, so a house can grow from 2x2 to 6x4 without a new baked sprite.
BUILDING_PART_NAMES = [
    "floor", "wall", "roof", "roof_edge", "door", "window", "rug",
    "counter", "bed", "workbench", "crate", "sign",
]


def building_part(name):
    im = Img(T, T)
    if name == "floor":
        im.rect(0, 0, T, T, PAL["floor_a"])
        for y in (3, 11): im.rect(0, y, T, 1, PAL["floor_b"])
    elif name == "wall":
        im.rect(0, 0, T, T, PAL["brick_a"])
        im.rect(0, 0, T, 2, PAL["trim"]); im.rect(0, 14, T, 2, PAL["brick_b"])
    elif name == "roof":
        im.rect(0, 0, T, T, PAL["roof_red"])
        for y in (3, 8, 13): im.rect(0, y, T, 1, PAL["roof_brown"])
        for x in (3, 10): im.rect(x, 1, 1, 13, PAL["roof_brown"])
    elif name == "roof_edge":
        im.rect(0, 0, T, T, PAL["roof_red"])
        im.rect(0, 13, T, 3, PAL["trim"]); im.rect(0, 0, 2, T, PAL["roof_brown"])
    elif name == "door":
        im.rect(0, 0, T, T, PAL["floor_a"])
        im.rect(4, 1, 8, 15, PAL["door"]); im.rect(6, 4, 1, 1, PAL["trim"])
    elif name == "window":
        im.rect(0, 0, T, T, PAL["brick_a"])
        im.rect(2, 2, 12, 10, PAL["win"]); im.rect(7, 2, 1, 10, PAL["trim"])
        im.rect(2, 6, 12, 1, PAL["trim"])
    elif name == "rug":
        im.rect(2, 3, 12, 10, PAL["roof_green"]); im.rect(4, 5, 8, 6, PAL["square_a"])
    elif name == "counter":
        im.rect(1, 5, 14, 8, PAL["trunk"]); im.rect(2, 4, 12, 2, PAL["trim"])
    elif name == "bed":
        im.rect(2, 2, 12, 12, PAL["trunk"]); im.rect(3, 3, 10, 7, PAL["roof_green"])
        im.rect(4, 4, 8, 2, PAL["trim"])
    elif name == "workbench":
        im.rect(1, 7, 14, 4, PAL["trunk"]); im.rect(3, 11, 2, 4, PAL["door"]); im.rect(11, 11, 2, 4, PAL["door"])
    elif name == "crate":
        im.rect(2, 3, 12, 11, PAL["floor_b"]); im.rect(3, 4, 10, 1, PAL["trim"])
        im.rect(7, 3, 1, 11, PAL["door"])
    elif name == "sign":
        im.rect(2, 4, 12, 8, PAL["door"]); im.rect(4, 6, 8, 4, PAL["roof_gold"])
    return im


def building_badge(name):
    """A tiny type marker layered onto a modular building front."""
    im = Img(T, T)
    accent = _name_color(name, [PAL["roof_red"], PAL["roof_blue"], PAL["roof_green"],
                                PAL["roof_gold"], PAL["roof_purple"], PAL["roof_teal"]])
    im.rect(2, 3, 12, 10, PAL["door"])
    im.rect(4, 5, 8, 6, accent)
    value = sum(ord(c) for c in name)
    for i in range(3):
        im.set(5 + (value + i * 3) % 6, 6 + (value + i) % 4, PAL["trim"])
    return im


def _house_base(roof_col):
    im = Img(B, B)
    im.rect(3, B - 3, B - 6, 3, PAL["shadow"])         # ground shadow
    im.rect(6, 20, B - 12, 24, PAL["brick_a"])          # walls
    for y in range(20, 44, 3):
        im.rect(6, y, B - 12, 1, PAL["brick_b"])
    # Timber-frame facade and warm lower shadow give the house a readable
    # upright front when the camera is close, instead of a flat icon.
    im.rect(6, 20, B - 12, 2, PAL["trim"])
    im.rect(8, 23, 2, 20, PAL["brick_b"])
    im.rect(38, 23, 2, 20, PAL["brick_b"])
    im.rect(6, 42, B - 12, 2, PAL["wall_b"])
    # roof (triangleish)
    for i, y in enumerate(range(6, 20)):
        inset = int((y - 6) * (B - 12) / 28)
        im.rect(6 + inset - 4, y, (B - 12) - 2 * inset + 8, 1, PAL[roof_col])
        if y % 3 == 0:
            im.rect(7 + inset - 4, y, max(1, (B - 12) - 2 * inset + 5), 1, PAL["roof_brown"])
    im.rect(4, 19, B - 8, 2, PAL["trim"])               # eave
    # door
    im.rect(B // 2 - 3, 33, 6, 11, PAL["door"])
    im.set(B // 2 + 1, 39, PAL["trim"])
    im.rect(B // 2 - 5, 43, 10, 2, PAL["stone_b"])
    # windows
    im.rect(11, 25, 6, 6, PAL["win"]); im.rect(31, 25, 6, 6, PAL["win"])
    im.rect(11, 25, 6, 1, PAL["trim"]); im.rect(31, 25, 6, 1, PAL["trim"])
    return im


def _house_interior(name):
    """Roof-off companion for a 3x3 building sprite.

    The footprint and anchor intentionally match ``_house_base`` exactly.  A
    scenario can therefore switch roof state without moving the occupants or
    changing the map geometry.
    """
    im = Img(B, B)
    im.rect(3, B - 3, B - 6, 3, PAL["shadow"])
    im.rect(4, 4, B - 8, B - 8, PAL["wall_b"])
    im.rect(7, 7, B - 14, B - 14, PAL["floor_a"])
    for y in range(8, 40, 4):
        im.rect(8, y, 32, 1, PAL["floor_b"])
    # Wall beam and threshold make the open roof read as the same structure.
    im.rect(4, 5, 40, 3, PAL["trunk"])
    im.rect(4, 40, 40, 4, PAL["stone_b"])
    im.rect(22, 36, 4, 8, PAL["door"])
    # A small, deterministic furniture language differentiates interiors and
    # makes roof-off rooms read as playable spaces rather than blank squares.
    im.rect(18, 16, 12, 8, PAL["roof_green"])
    im.rect(20, 18, 8, 4, PAL["square_a"])
    im.rect(9, 11, 9, 5, PAL["door"])
    im.rect(10, 12, 7, 2, PAL["trim"])
    im.rect(31, 25, 7, 5, PAL["floor_b"])
    im.rect(32, 26, 5, 2, PAL["trim"])
    furniture = {
        "granary": (PAL["roof_gold"], (9, 11, 12, 7)),
        "forge": (PAL["stone_b"], (27, 11, 11, 9)),
        "bakery": (PAL["roof_red"], (8, 27, 14, 6)),
        "kitchen": (PAL["roof_red"], (27, 27, 12, 6)),
        "school": (PAL["roof_green"], (9, 12, 30, 4)),
        "records_office": (PAL["roof_blue"], (9, 11, 8, 18)),
        "watchhouse": (PAL["roof_blue"], (30, 11, 8, 18)),
        "dairy": (PAL["trim"], (8, 27, 14, 6)),
        "mill": (PAL["roof_gold"], (27, 10, 10, 10)),
    }
    col, (x, y, w, h) = furniture.get(name, (PAL["floor_b"], (9, 27, 12, 6)))
    im.rect(x, y, w, h, col)
    im.rect(x + 2, y + 2, max(1, w - 4), 2, PAL["trim"])
    if name in {"inn", "house", "townhall", "church"}:
        im.rect(28, 10, 9, 6, PAL["roof_green"] if name == "house" else PAL["roof_brown"])
        im.rect(30, 11, 5, 3, PAL["trim"])
    return im


def _sign(im, col, kind):
    """A small emblem on the roof face so each institution reads at a glance."""
    cx = B // 2
    if kind == "cross":                      # church
        im.rect(cx - 1, 8, 2, 8, PAL["trim"]); im.rect(cx - 3, 11, 6, 2, PAL["trim"])
    elif kind == "clock":                    # townhall
        im.rect(cx - 3, 10, 6, 6, PAL["trim"]); im.set(cx, 13, PAL[col]); im.set(cx, 11, PAL["door"])
    elif kind == "coin":                     # bank
        im.rect(cx - 3, 10, 6, 6, PAL["roof_gold"]); im.rect(cx - 1, 11, 2, 4, PAL["door"])
    elif kind == "stall":                    # market
        im.rect(8, 22, B - 16, 3, PAL["roof_red"])
        for x in range(8, B - 8, 6):
            im.rect(x, 22, 3, 3, PAL["trim"])
    elif kind == "press":                    # newspaper
        im.rect(cx - 4, 24, 8, 8, PAL["trim"])
        im.rect(cx - 3, 26, 6, 1, PAL["door"]); im.rect(cx - 3, 28, 6, 1, PAL["door"])
    elif kind == "board":                    # noticeboard (short)
        im.rect(cx - 8, 26, 16, 12, PAL["door"]); im.rect(cx - 6, 28, 12, 8, PAL["trim"])
    elif kind == "book":                     # school
        im.rect(cx - 5, 24, 10, 7, PAL["trim"]); im.rect(cx, 24, 1, 7, PAL["door"])
    elif kind == "plus":                     # surgery
        im.rect(cx - 1, 24, 2, 8, PAL["flower_r"]); im.rect(cx - 4, 27, 8, 2, PAL["flower_r"])
    elif kind == "mug":                      # inn
        im.rect(cx - 3, 25, 6, 6, PAL["roof_gold"]); im.rect(cx + 3, 26, 2, 3, PAL["trim"])
    elif kind == "grain":                    # granary
        im.rect(cx - 5, 25, 10, 7, PAL["roof_gold"])
        im.rect(cx - 2, 22, 2, 5, PAL["flower_y"]); im.rect(cx + 1, 21, 2, 6, PAL["flower_y"])
    elif kind == "root":                     # root cellar
        im.rect(cx - 7, 29, 14, 5, PAL["stone_b"]); im.rect(cx - 4, 25, 8, 5, PAL["door"])
    elif kind == "well":                     # wellhouse
        im.rect(cx - 5, 28, 10, 5, PAL["stone_a"]); im.rect(cx - 1, 24, 2, 5, PAL["trunk"])
    elif kind == "forge":
        im.rect(cx - 5, 26, 10, 6, PAL["stone_b"]); im.set(cx, 25, PAL["flower_r"])
    elif kind == "fish":
        im.rect(cx - 7, 28, 12, 3, PAL["water_a"]); im.set(cx + 5, 28, PAL["trim"])
    elif kind == "dairy":
        im.rect(cx - 5, 25, 10, 7, PAL["trim"]); im.rect(cx - 2, 22, 4, 4, PAL["floor_b"])
    elif kind == "watch":
        im.rect(cx - 3, 23, 6, 9, PAL["roof_blue"]); im.rect(cx - 1, 20, 2, 4, PAL["trim"])
    elif kind == "record":
        im.rect(cx - 5, 24, 10, 8, PAL["trim"]); im.rect(cx - 2, 26, 1, 4, PAL["roof_blue"])
    elif kind == "wood":
        im.rect(cx - 6, 27, 12, 4, PAL["trunk"]); im.rect(cx - 3, 23, 6, 5, PAL["floor_b"])
    elif kind == "dye":
        im.rect(cx - 4, 25, 8, 7, PAL["roof_purple"]); im.set(cx, 27, PAL["flower_r"])


_BUILDING_BASE = [
    ("house", "roof_red", None), ("townhall", "roof_blue", "clock"),
    ("church", "roof_purple", "cross"), ("bank", "roof_gold", "coin"),
    ("market", "roof_green", "stall"), ("press", "roof_teal", "press"),
    ("noticeboard", "roof_brown", "board"), ("school", "roof_green", "book"),
    ("surgery", "roof_gray", "plus"), ("inn", "roof_brown", "mug"),
]
_BUILDING_EXTRA = [
    "granary", "root_cellar", "wellhouse", "latrine", "compost_yard", "smokehouse",
    "records_office", "watchhouse", "kitchen", "dairy", "wharf", "shambles", "dyehouse",
    "cooperage", "woodshop", "sawpit", "tannery", "cobbler", "tailorshop", "weavery",
    "forge", "bakery", "fishmonger",
]
_ROOFS = ["roof_red", "roof_blue", "roof_green", "roof_gold", "roof_gray", "roof_purple",
          "roof_teal", "roof_brown"]
BUILDINGS = list(_BUILDING_BASE)
for _i, _name in enumerate(_BUILDING_EXTRA):
    if _name not in {name for name, _, _ in BUILDINGS}:
        BUILDINGS.append((_name, _ROOFS[_i % len(_ROOFS)], None))
if E is not None:
    for _i, _name in enumerate(sorted(E.BUILDINGS)):
        if _name not in {name for name, _, _ in BUILDINGS}:
            BUILDINGS.append((_name, _ROOFS[_i % len(_ROOFS)], None))


def build_buildings():
    sign_for = {"granary": "grain", "root_cellar": "root", "wellhouse": "well",
                "forge": "forge", "dairy": "dairy", "wharf": "fish", "fishmonger": "fish",
                "watchhouse": "watch", "records_office": "record", "woodshop": "wood",
                "sawpit": "wood", "dyehouse": "dye", "tannery": "dye"}
    out = []
    for name, roof, sign in BUILDINGS:
        im = _house_base(roof)
        if sign or name in sign_for:
            _sign(im, roof, sign or sign_for[name])
        out.append((name, im))
    return out


# ----------------------------------------------------------------------------
# assemble sheets + manifest
# ----------------------------------------------------------------------------
def main():
    # tileset strip
    tsheet = Img(T * len(TILES), T)
    tindex = {}
    for i, (name, im) in enumerate(TILES):
        tsheet.blit(im, i * T, 0)
        tindex[name] = i
    write_png(tsheet, os.path.join(HERE, "tileset.png"))

    # Transparent life props are kept in their own atlas so terrain remains
    # data-driven: a scenario can place or omit them without repainting the
    # underlying map tiles.
    psheet = Img(T * len(PROP_NAMES), T)
    pindex = {}
    for i, name in enumerate(PROP_NAMES):
        psheet.blit(prop_sprite(name), i * T, 0)
        pindex[name] = i
    write_png(psheet, os.path.join(HERE, "props.png"))

    large_prop_names = ["tree", "bush"]
    lpsheet = Img(32 * len(large_prop_names), 32)
    lpindex = {}
    for i, name in enumerate(large_prop_names):
        lpsheet.blit(large_prop_sprite(name), i * 32, 0)
        lpindex[name] = i
    write_png(lpsheet, os.path.join(HERE, "large_props.png"))

    # character sheet: cols=frames(3) rows=dirs(4)
    csheet = Img(T * 3, T * 4)
    for d, direction in enumerate(DIRS):
        for fr in range(3):
            csheet.blit(char_frame(direction, fr), fr * T, d * T)
    write_png(csheet, os.path.join(HERE, "characters.png"))

    # buildings strip
    blds = build_buildings()
    bsheet = Img(B * len(blds), B)
    bindex = {}
    for i, (name, im) in enumerate(blds):
        bsheet.blit(im, i * B, 0)
        bindex[name] = i
    write_png(bsheet, os.path.join(HERE, "buildings.png"))

    parts_sheet = Img(T * len(BUILDING_PART_NAMES), T)
    part_index = {}
    for i, name in enumerate(BUILDING_PART_NAMES):
        parts_sheet.blit(building_part(name), i * T, 0)
        part_index[name] = i
    write_png(parts_sheet, os.path.join(HERE, "building_parts.png"))

    badges_sheet = Img(T * len(blds), T)
    badge_index = {}
    for i, (name, _im) in enumerate(blds):
        badges_sheet.blit(building_badge(name), i * T, 0)
        badge_index[name] = i
    write_png(badges_sheet, os.path.join(HERE, "building_badges.png"))

    # Roof-off interiors use the same ordered frame list and the same 48px
    # footprint as the roof-on sheet.
    isheet_buildings = Img(B * len(blds), B)
    for i, (name, _im) in enumerate(blds):
        isheet_buildings.blit(_house_interior(name), i * B, 0)
    write_png(isheet_buildings, os.path.join(HERE, "building_interiors.png"))

    # Every canonical item gets a stable icon coordinate.  The atlas is a grid
    # so clients can request icons by name without requiring one file per item.
    isheet, iindex, icols, irows = build_item_sheet()
    write_png(isheet, os.path.join(HERE, "items.png"))

    # Character role/age variants and action keyframes live beside the legacy
    # walk sheet; old consumers can continue using characters.png unchanged.
    vsheet, asheet = build_animation_sheets()
    write_png(vsheet, os.path.join(HERE, "character_variants.png"))
    write_png(asheet, os.path.join(HERE, "actions.png"))

    manifest = {
        "version": "3.0.0",
        "design": {
            "logical_tile": 16,
            "standard_building_footprint": [3, 3],
            "viewport_cells": [52, 40],
            "zoom_range": [0.75, 3.0],
            "anchor": "cell_center_feet_or_building_center",
            "nearest_neighbour": True,
        },
        "palette": "warm cozy (Stardew-esque): greens/browns/soft blues",
        "style_reference": "stardew_like_art_direction.png",
        "style_assets": {
            "source_reference": "style_source_village.png",
            "terrain_source": "style_terrain_atlas_source.png",
            "building_source": "style_building_atlas_source.png",
            "cutaway_source": "style_cutaway_atlas_source.png",
            "character_source": "style_character_walk_atlas_source.png",
            "held_item_source": "style_held_items_atlas_source.png",
            "material_edge_atlas": "style_material_edges.png",
            "path_tile_atlas": "style_path_tiles.png",
            "square_fixture_atlas": "style_square_fixtures.png",
            "manifest": "style_manifest.json",
            "builder": "tools/build_style_assets.py",
            "runtime_note": "the original village scene is reference-only; clients assemble masked material fields, transparent transitions, props, and facades",
        },
        "rendering": {
            "projection": "square_cells_3q_top_down",
            "display_scale": 2,
            "depth_order": "map_row_then_cell_x",
            "facades": "upright_front_facing_buildings",
        },
        "tint_note": "characters.png bodies are drawn LIGHT; recolour at runtime "
                     "by MULTIPLY-compositing the resident's class/role colour.",
        "tileset": {
            "file": "tileset.png", "tile": T, "count": len(TILES),
            "layout": "horizontal strip; frame index = column",
            "tiles": tindex,
        },
        "terrain": {
            "transition_masks": {
                "cardinal_bits": "north=1 east=2 south=4 west=8",
                "path": {str(mask): tindex[f"path_transition_{mask:02d}"]
                         for mask in range(16)},
                "water": {str(mask): tindex[f"water_transition_{mask:02d}"]
                          for mask in range(16)},
            },
            "props_file": "props.png",
            "props_frame": T,
            "props": pindex,
            "large_props_file": "large_props.png",
            "large_props_frame": 32,
            "large_props": lpindex,
        },
        "characters": {
            "file": "characters.png", "frame": T,
            "cols": 3, "rows": 4,
            "frames": {"idle": 0, "stepA": 1, "stepB": 2},
            "directions": {d: i for i, d in enumerate(DIRS)},
            "walk_cycle": [0, 1, 0, 2],
        },
        "buildings": {
            "file": "buildings.png", "frame": B, "count": len(blds),
            "interior_file": "building_interiors.png",
            "roof_states": {"on": "buildings.png", "off": "building_interiors.png"},
            "layout": "horizontal strip; frame index = column",
            "sprites": bindex,
            "parts_file": "building_parts.png", "parts_frame": T,
            "parts": part_index,
            "badges_file": "building_badges.png", "badges_frame": T,
            "badges": badge_index,
        },
        "items": {
            "file": "items.png", "frame": T, "cols": icols, "rows": irows,
            "layout": "16x16 grid; coordinates and frame index are keyed by item name",
            "icons": iindex,
        },
        "character_variants": {
            "file": "character_variants.png", "frame": T, "cols": 3,
            "rows_per_variant": 4, "variants": {
                name: {"index": i, "directions": {d: j for j, d in enumerate(DIRS)}}
                for i, name in enumerate(CHAR_VARIANTS)
            },
            "frames": {"idle": 0, "stepA": 1, "stepB": 2},
        },
        "actions": {
            "file": "actions.png", "frame": T, "frames": 4,
            "layout": "four keyframes per action row",
            "actions": {name: {"row": i, "frames": [0, 1, 2, 3]}
                        for i, name in enumerate(ACTION_NAMES)},
        },
        # how sim tile names / building types / features map onto the assets
        "tile_map": {
            "grass": "grass", "path": "path", "square": "square", "floor": "floor",
            "wall": "wall", "tree": "tree", "water": "water", "dirt": "dirt",
        },
        "building_map": {
            "townhall": "townhall", "church": "church", "bank": "bank",
            "noticeboard": "noticeboard", "press": "press", "school": "school",
            "surgery": "surgery", "inn": "inn", "market": "market", "house": "house",
            "bakery": "bakery", "fishmonger": "fishmonger", "granary": "granary",
            "root_cellar": "root_cellar", "records_office": "records_office",
            "watchhouse": "watchhouse", "forge": "forge", "kitchen": "kitchen",
        },
        "feature_map": {
            "crop": "crop", "forest": "tree", "rocks": "rocks",
            "orchard": "tree", "water": "water", "well": "well",
        },
    }
    with open(os.path.join(HERE, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print("wrote tileset.png props.png characters.png character_variants.png actions.png items.png buildings.png manifest.json")
    print("tiles:", list(tindex), "\nbuildings:", list(bindex), "\nitems:", len(iindex),
          "\nactions:", ACTION_NAMES, "\ncharacter variants:", CHAR_VARIANTS)


if __name__ == "__main__":
    main()
