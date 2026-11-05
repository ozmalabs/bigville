"""Phase 016a: write the founding town's content into the data packs.

Run ONCE, from the repository root, while worlds/bigville_town100_world.py still holds the values
(i.e. at HEAD, before the code reads the tables):

    python3 docs/phases/phase016a/author_founding_pack.py

It writes, under packs/bigville/:
    population/founding_cast.json        FOUNDING_ROLES, FOUNDING_CLASS, FOUNDING_ANCHOR_NAMES, FOUNDING_DRAW_BOUNDS
    population/founding_names.json       FOUNDING_FIRST_NAMES, FOUNDING_LAST_NAMES
    population/founding_personality.json FOUNDING_PERSONALITY, FOUNDING_CAUSAL_RESOLUTION
    world/founding_map.json              FOUNDING_MAP, FOUNDING_DEPOSITS
    world/founding_sites.json            FOUNDING_WORKPLACES, FOUNDING_BUILDING_SITES,
                                         FOUNDING_PLACE_LABELS, FOUNDING_ANCHOR_ALIASES
and empty tables of the same names under packs/test_hamlet/ (a pack with no founding town), and
appends the table entries to both pack.json manifests.

Values that the code held inline (inside build_town_100, bigville_world._anchor_for_building, and
populate_town100) are written here as literals copied from those functions. The script then reads the
packs back and compares every table with the Python value it came from, and refuses to write if any
differs. It refuses to run if the founding tables already exist.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

import worlds.bigville_town100_world as T  # noqa: E402  (the HEAD values)

BIG = os.path.join(ROOT, "packs", "bigville")
HAM = os.path.join(ROOT, "packs", "test_hamlet")

TABLE_FILES = {
    "population/founding_cast.json": ["FOUNDING_ROLES", "FOUNDING_CLASS", "FOUNDING_ANCHOR_NAMES",
                                      "FOUNDING_DRAW_BOUNDS"],
    "population/founding_names.json": ["FOUNDING_FIRST_NAMES", "FOUNDING_LAST_NAMES"],
    "population/founding_personality.json": ["FOUNDING_PERSONALITY", "FOUNDING_CAUSAL_RESOLUTION"],
    "world/founding_map.json": ["FOUNDING_MAP", "FOUNDING_DEPOSITS"],
    "world/founding_sites.json": ["FOUNDING_WORKPLACES", "FOUNDING_BUILDING_SITES",
                                  "FOUNDING_PLACE_LABELS", "FOUNDING_ANCHOR_ALIASES"],
}

# ------------------------------------------------------------------ the values
# Cast (from ROLE_SPEC, the anchors, the name pools, _PARAM_SPEC and the resolution mixture).
ROLES = [
    {"role": r, "count": n, "group": g, "role_identity_mean": m, "role_identity_sd": s, "workplace": w}
    for (r, n, g, m, s, w) in T.ROLE_SPEC
]
CLASS = {
    # _CLASS_BY_GROUP inside generate_cast100 (HEAD): (rich_p, middle_p); poor is the remainder.
    "by_group": {
        "high": {"rich": 0.65, "middle": 0.30},
        "middle": {"rich": 0.15, "middle": 0.70},
        "low": {"rich": 0.02, "middle": 0.28},
    },
    "literacy_by_class": {"rich": 0.95, "middle": 0.80, "poor": 0.55},
    # populate_town100 in worlds/bigville_world.py (HEAD)
    "station_by_group": {"low": "labouring", "middle": "middle", "high": "educated"},
}
PERSONALITY = {k: {"mean": m, "sd": s, "lo": lo, "hi": hi} for k, (m, s, lo, hi) in T._PARAM_SPEC.items()}
CAUSAL = {
    "floor": {"mean": T._RES_FLOOR_MEAN, "sd": T._RES_FLOOR_SD},
    "ceiling": {"mean": T._RES_CEIL_MEAN, "sd": T._RES_CEIL_SD},
    "ceiling_weight": T._RES_CEIL_WEIGHT,
    "lo": T._RES_LO,
    "hi": T._RES_HI,
}
# _draw_clip(rng, ri_mean, ri_sd, 0.02, 0.98) inside generate_cast100 (HEAD)
DRAW_BOUNDS = {"role_identity": {"lo": 0.02, "hi": 0.98}}

# Map (inline in build_town_100 at HEAD).
FOUNDING_MAP = {
    "width": T.W100,
    "height": T.H100,
    # _windy_horizontal(grid, y, index % 5) and _windy_vertical(grid, x, (index + 2) % 5)
    "road_rows": [{"row": y, "phase": i % 5} for i, y in enumerate([9, 20, 31])],
    "road_cols": [{"col": x, "phase": (i + 2) % 5} for i, x in enumerate([11, 28, 45])],
    "bend_offsets_horizontal": [-1, 0, 1, 2, 1, 0, -1, -2],
    "bend_offsets_vertical": [1, 0, -1, -2, -1, 0, 1, 2],
    "bend_run": 3,
    "square": {"x": 18, "y": 15, "w": 11, "h": 7, "center": [23, 18], "label": "Market Square"},
    "resource_bodies": [
        {"tile": "water", "rect": [2, 2, 10, 5]},
        {"tile": "tree", "rect": [30, 2, 40, 5]},
        {"tile": "wall", "rect": [43, 8, 49, 13]},
    ],
    "scattered_trees": [[14, 3], [26, 8], [38, 24], [8, 30], [44, 32], [33, 27]],
    "farm_plots": {"origin": [36, 26], "count": 8, "columns": 4, "column_step": 3, "row_step": 6},
}
FOUNDING_DEPOSITS = ["fish", "lumber", "stone"]

WORKPLACES = {k: list(v) for k, v in T._WORK_ANCHORS.items()}
BUILDING_SITES = {k: list(v) for k, v in T._BUILDING_SITES.items()}
PLACE_LABELS = {
    "townhall": "Town Hall", "church": "Church", "school": "School", "bank": "Bank",
    "press": "The Herald", "store": "General Store", "inn": "The Inn", "surgery": "Surgery",
    "estate": "Estate Office", "watch": "Watch House", "mill": "Mill", "bakery": "Bakery",
    "fishmonger": "Fishmonger", "carpenter": "Carpenter", "mason": "Mason", "manor": "Manor",
}
# _anchor_for_building in worlds/bigville_world.py (HEAD)
ANCHOR_ALIASES = {
    "records_office": "townhall", "watchhouse": "watch", "wellhouse": "market",
    "latrine": "market", "compost_yard": "farm", "root_cellar": "farm", "granary": "farm",
    "smokehouse": "bakery", "scriptorium": "press", "shambles": "market", "dyehouse": "press",
    "cooperage": "carpenter", "woodshop": "carpenter", "sawpit": "carpenter", "tannery": "market",
    "cobbler": "market", "tailorshop": "market", "weavery": "market", "forge": "mason",
    "kitchen": "bakery", "dairy": "farm", "wharf": "fish",
}

NAMES = {"FOUNDING_FIRST_NAMES": list(T._FIRST), "FOUNDING_LAST_NAMES": list(T._LAST)}
CAST_TABLES = {
    "FOUNDING_ROLES": ROLES,
    "FOUNDING_CLASS": CLASS,
    "FOUNDING_ANCHOR_NAMES": dict(T._ANCHOR_NAMES),
    "FOUNDING_DRAW_BOUNDS": DRAW_BOUNDS,
}
PERSONALITY_TABLES = {"FOUNDING_PERSONALITY": PERSONALITY, "FOUNDING_CAUSAL_RESOLUTION": CAUSAL}
MAP_TABLES = {"FOUNDING_MAP": FOUNDING_MAP, "FOUNDING_DEPOSITS": FOUNDING_DEPOSITS}
SITE_TABLES = {"FOUNDING_WORKPLACES": WORKPLACES, "FOUNDING_BUILDING_SITES": BUILDING_SITES,
               "FOUNDING_PLACE_LABELS": PLACE_LABELS, "FOUNDING_ANCHOR_ALIASES": ANCHOR_ALIASES}
ALL_TABLES = {**CAST_TABLES, **PERSONALITY_TABLES, **MAP_TABLES, **SITE_TABLES, **NAMES}

DOCS = {
    "population/founding_cast.json": (
        "Founding cast of the 100-resident town (Phase 016a). Moved from worlds/bigville_town100_world.py.\n\n"
        "FOUNDING_ROLES: one row per role of the founding cast. The counts sum to the number of residents "
        "and of founding homes. count, group, role_identity_mean and role_identity_sd are authored design "
        "choices, not census figures (APPROX). workplace is a FOUNDING_WORKPLACES key, a FOUNDING_DEPOSITS "
        "kind (fish, lumber, stone), or 'farm' (the founding farm plots). Phase 016b replaces these counts "
        "with E.seed_jobs (Phase 003).\n\n"
        "FOUNDING_CLASS.by_group: each group's [rich, middle] shares; poor is the remainder (authored, APPROX). "
        "literacy_by_class: the chance of literacy by class (authored, APPROX). station_by_group: the "
        "STATION_EDUCATION key of each group (as populate_town100 used it).\n\n"
        "FOUNDING_ANCHOR_NAMES: role -> the register name of the first resident with that role.\n"
        "FOUNDING_DRAW_BOUNDS.role_identity: the clip range of the role-identity draw."),
    "population/founding_names.json": (
        "Name pools for the founding cast (Phase 016a). Invented Pratchett-register names, authored for the "
        "town; no real-population source. A resident's name is the first unused combination of a seeded "
        "permutation of FIRST x LAST, so list order is part of the draw."),
    "population/founding_personality.json": (
        "FOUNDING_PERSONALITY: mean, sd, lo, hi of each drawn personality and emotion parameter. lo or hi "
        "null means unclipped. The values are authored and have no source (APPROX).\n\n"
        "FOUNDING_CAUSAL_RESOLUTION: the trait-level causal-belief resolution (a bin count), a two-component "
        "mixture. The floor component is the floor-heavy, naive subgroup and the ceiling component is the "
        "ceiling-heavy, exposed subgroup. Sources, as recorded in the code this was moved from: Frederick "
        "2005 (CRT, combined N=3428) and Stieger & Reips 2016 (N=2137). The research basis is "
        "docs/research/Bigville graph runtime/CAUSAL_GRANULARITY_POPULATION_DISTRIBUTION_RESEARCH.md sec 7 "
        "point 4 and sec 8. floor mean 3.0 sd 1.0 anchors the CRT floor and CAN's coarse condition (3 J "
        "values). ceiling mean 7.5 sd 2.0 anchors Miller (1956) and Preston & Colman (2000), whose convergent "
        "optimum is 7, reaching toward the past-ceiling band 9-12. ceiling_weight 0.35 lies inside Frederick's "
        "17% combined perfect-score rate and Stieger & Reips' ~33% educated-subgroup rate. lo 2 and hi 12 are "
        "the registered range of research sec 8 point 1. See BIGVILLE_CAN_INTEGRATION_PREREG.md sec 3. NOTE: the research and prereg files named in this note are not in this checkout (checked at Phase 016a), so these citations are carried over unverified."),
    "world/founding_map.json": (
        "The founding town's map (Phase 016a). Moved from worlds/bigville_town100_world.py.\n\n"
        "FOUNDING_MAP: width and height in cells. road_rows and road_cols give each winding road's line and "
        "the phase of its meander pattern. bend_offsets_* are the meander offsets and bend_run is the number "
        "of cells per pattern step (authored). square is the market square rectangle (x, y, w, h), its centre, "
        "and the label of the landmark. resource_bodies are the solid rectangles, given as inclusive corners "
        "[x0, y0, x1, y1], with the tile each one is. scattered_trees are single tree cells. farm_plots "
        "gives the origin, count, columns, and steps of the field grid. The layout is authored; there is no "
        "real-world source.\n\n"
        "FOUNDING_DEPOSITS: the resource kinds the founding map places. Each sits on a walkable cell beside "
        "the body whose tile RESOURCE_DEPOSITS names for it (world/resource_deposits.json)."),
    "world/founding_sites.json": (
        "Founding workplaces, buildings, labels, and fallbacks (Phase 016a). Moved from "
        "worlds/bigville_town100_world.py and worlds/bigville_world.py.\n\n"
        "FOUNDING_WORKPLACES: each named workplace's anchor cell [x, y] (authored). The map takes the free "
        "road-side plot nearest to each anchor.\n"
        "FOUNDING_BUILDING_SITES: the fixed footprint origin [x, y] of each building that stands at founding "
        "(authored). Every key is a BUILDINGS kind.\n"
        "FOUNDING_PLACE_LABELS: the landmark label of each workplace (authored).\n"
        "FOUNDING_ANCHOR_ALIASES: a building with no fixed site anchors at the workplace named here. A target "
        "that is not a workplace (e.g. 'farm') falls back to the market, as the code did at HEAD."),
}

HAMLET_DOC = ("Test pack 'test_hamlet' (Phase 016a): this pack has no founding town. Every table here is "
              "empty, so E.FOUNDING_ROLES is empty and from_town100 refuses the pack. See "
              "docs/phases/phase016a/PHASE016A_REPORT.md.")


def _write(path, doc, tables):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = {"_doc": doc, "_types": {}, "tables": tables}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _empty_like(value):
    if isinstance(value, dict):
        return {}
    if isinstance(value, list):
        return []
    if isinstance(value, str):
        return ""
    raise TypeError(type(value))


def _manifest_add(pack_dir, entries):
    path = os.path.join(pack_dir, "pack.json")
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    manifest = json.loads(raw)
    if json.dumps(manifest, indent=2, ensure_ascii=False) + "\n" != raw:
        raise SystemExit(f"{path}: manifest does not round-trip; add the entries by hand")
    names = {t["name"] for t in manifest["tables"]}
    if names & set(entries):
        raise SystemExit(f"{path}: founding tables already listed")
    for name, rel in entries.items():
        manifest["tables"].append({"name": name, "file": rel})
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def _verify(pack_dir, expected):
    """Read the pack back (through domains.pack) and compare each table with its Python value,
    including the order of dict keys (the draws walk some dicts in order)."""
    from domains.pack import load_pack
    loaded = load_pack(pack_dir)
    for name, value in expected.items():
        got = loaded[name]
        if json.loads(json.dumps(got)) != json.loads(json.dumps(value)):
            raise SystemExit(f"round trip differs for {name}")
        if isinstance(value, dict) and list(got) != list(value):
            raise SystemExit(f"key order differs for {name}")


def main():
    if os.path.exists(os.path.join(BIG, "population", "founding_cast.json")):
        raise SystemExit("the founding tables already exist; this script runs once")
    manifest_entries = {}
    for rel, names in TABLE_FILES.items():
        _write(os.path.join(BIG, rel), DOCS[rel], {n: ALL_TABLES[n] for n in names})
        _write(os.path.join(HAM, rel), HAMLET_DOC, {n: _empty_like(ALL_TABLES[n]) for n in names})
        for n in names:
            manifest_entries[n] = rel
    _manifest_add(BIG, manifest_entries)
    _manifest_add(HAM, manifest_entries)
    _verify(BIG, ALL_TABLES)
    print(f"wrote {len(manifest_entries)} tables to packs/bigville and empty ones to packs/test_hamlet")


if __name__ == "__main__":
    main()
