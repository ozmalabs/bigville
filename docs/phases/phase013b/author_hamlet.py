"""One-time authoring of packs/test_hamlet/ (Phase 013b).

Writes a standalone pack with every table name the entity modules bind (the pack loader fails on a
missing name), one table per file, in the layout of packs/bigville. Three kinds of content:

  AUTHORED  -- small town content written here: one item set, two recipes, one building, one trade,
               one job, one law, one skill cluster.
  COPIED    -- generic physics and psychology constants copied unchanged from packs/bigville (their
               citations stay in that pack's `_doc`). Terrain, weather, seasons, action vocabulary,
               body and preference distributions. Nothing town-specific is copied.
  EMPTY     -- every other name, present with an empty value of the right type.

Run once from the repository root: `python3 docs/phases/phase013b/author_hamlet.py`. It refuses to run
when packs/test_hamlet/pack.json already exists, so it cannot overwrite edits made later.
"""
from __future__ import annotations

import copy
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from domains.pack import load_pack, to_json  # noqa: E402

PACK_DIR = os.path.join(ROOT, "packs", "test_hamlet")

BIGVILLE = load_pack("bigville")
BIG_FILE = {t["name"]: t["file"] for t in json.load(open(os.path.join(ROOT, "packs", "bigville", "pack.json")))["tables"]}

# Tables copied unchanged from packs/bigville (generic world physics and population distributions).
COPIED = [
    "SCRAP_WEIGHT_FACTOR", "SCRAP_SCARCITY_FACTOR", "SCRAP_DECAY", "NITROGEN", "TERRAIN_MOVEMENT",
    "TERRAIN_WEAR", "WEATHER", "SEASONS", "CARRYING", "CLASS_DECAY", "LABOUR_RATE", "TRAIN_HEADROOM",
    "TRAIN_RATE", "HUNGER_PER_STAMINA", "FREE_ACTIONS", "MAJOR_ACTIONS", "AFFORDANCES",
    "OBSERVATION_TYPES", "SKILL_CLOSENESS", "TRANSFER", "PRACTICE", "APTITUDE_PRACTICE",
    "META_FROM_SKILL", "META_METASKILL", "LIT_FUNCTIONAL", "LIT_EDUCATED", "STATION_EDUCATION",
    "PHYSIQUE", "APTITUDE", "TALENT", "PLAN_HORIZON", "FOOD_NEOPHOBIA", "SSAT_RATE", "NOVELTY_SWING",
    "MERE_EXPOSURE_GAIN", "MERE_EXPOSURE_DECAY", "CILANTRO_SOAPY_FRACTION", "JOB_TARGET_LOAD",
    "ADJECTIVES", "SHOCKS", "HEALTH_CONDITIONS", "LIFE_STAGES",
]

# Town content written here.
ITEMS = {
    "coin": {"class": "material", "bulk": True},
    "water": {"class": "material", "bulk": True, "fluid": True, "weight": 1.0, "volume": 1.0},
    "grain": {"class": "material", "bulk": True},
    "flour": {"class": "material", "bulk": True},
    "bread": {"class": "material", "bulk": True, "weight": 0.5, "volume": 1.0, "food": True},
}
RECIPES = [
    {"name": "mill_flour", "requires": "baker", "in": [["grain", 1]], "out": ["flour", 1],
     "difficulty": 0.5, "time_minutes": 10},
    {"name": "bake_bread", "requires": "baker", "in": [["flour", 1], ["water", 1]], "out": ["bread", 2],
     "difficulty": 1.0, "time_minutes": 30},
]
BUILDINGS = {"bakehouse": {"staff_role": "baker", "provides": "baker", "sheltered": True, "rooms": ["shop"]}}
TRADES = {"baker": {"building": "bakehouse", "tools": [], "base_skill": 0.7}}
JOBS = {"baker": {"trades": ["baker"], "tools": [], "spare": True}}
SKILLS = {"baking": {"kind": "craft"}, "milling": {"kind": "craft"}}
TRADE_SKILLS = {"baker": ["baking", "milling"]}
METASKILLS = {"craftsmanship": {"description": "hand and eye for making things in any material",
                                "g_loading": 0.3}}
SKILL_CLUSTERS = {"food_crafts": {"metaskill": "craftsmanship", "skills": ["baking", "milling"]}}
LOCAL_LAWS = [{
    "name": "hamlet_common_law", "title": "Hamlet Common Law", "kind": "law", "scope": "hamlet",
    "seed_roles": ["baker"],
    "concepts": [{"name": "bread_is_shared_at_fair_price", "abstraction": "principle",
                  "reference": {"subject": "bread", "predicate": "is_sold_at", "object": "fair_price"}}],
}]
# The nitrogen cycle (copied NITROGEN) names a fertiliser input type; the type is a tag only.
INPUT_TYPES = {"fertiliser": {"tag": "nitrogen", "measure": "nitrogen"}}
SCARCITY = {"coin": 1.0, "water": 0.5, "grain": 1.0, "flour": 1.2, "bread": 1.5}
STARTING_STOCK = {"coin": 20.0, "water": 100.0, "grain": 40.0, "flour": 0.0, "bread": 0.0}


def _authored():
    return {
        "ITEMS": ITEMS, "RECIPES": RECIPES, "BUILDINGS": BUILDINGS, "TRADES": TRADES, "JOBS": JOBS,
        "SKILLS": SKILLS, "TRADE_SKILLS": TRADE_SKILLS, "METASKILLS": METASKILLS,
        "SKILL_CLUSTERS": SKILL_CLUSTERS, "LOCAL_LAWS": LOCAL_LAWS, "SCARCITY": SCARCITY,
        "STARTING_STOCK": STARTING_STOCK, "INPUT_TYPES": INPUT_TYPES,
    }


# Empty values, typed. Tuples and sets are restored by the loader from _types.
EMPTY = {
    "CONTAINERS": {}, "SERVING_UTENSILS": {}, "SERVING_EQUIPMENT": (),
    "FOOD_SERVICE": {}, "SOUP_FOODS": set(), "DRINK_FOODS": set(), "PREPARATION_REQUIREMENTS": (),
    "PREPARATION_EQUIPMENT": {}, "PREPARATION_METHODS": {}, "PREPARATION_METHODS_BY_HINT": {},
    "HEATED_FOOD_RECIPES": frozenset(), "FUEL_PER_BATCH": {}, "BUILDING_PROJECTS": {},
    "TOWN_SQUARE_FIXTURES": [], "RESOURCE_DEPOSITS": {}, "SHOP_CHAINS": {}, "SLAUGHTER_PRODUCTS": frozenset(),
    "WASTE_CYCLES": {}, "INFRASTRUCTURE": {},  # no latrine or other infrastructure in a hamlet
    "ANIMALS": {}, "ANIMAL_NPC_SETUP": {}, "FENCE_TYPES": {}, "ENCLOSURE_TYPES": {},
    "ANIMAL_HUSBANDRY": {}, "CROPS": {}, "FIELD_WORK": {}, "ARABLE_ROTATION": {}, "STARTING_CROPS": (),
    "WATER_SOURCES": {}, "FUEL_SOURCES": {}, "SOILS": {}, "LAND_USES": {}, "PASTURE_YIELDS": {},
    "WASTE_CYCLES": {}, "_PERISHABLE_RAW": set(), "RECIPE_EXERTION": {}, "SKILL_LIMITATIONS": {},
    "SKILL_AFFINITY": {}, "APTITUDE_PRACTICE": {}, "LAND_TENURE": {}, "LAND_RECORDS": {},
    "DEED_TYPES": {}, "LAND_DISPUTES": {}, "SHARED_CONCEPTS": [], "LOCAL_POLICIES": [],
    "GIANTVILLE_POLICIES": [], "GIANTVILLE_LAWS": [], "LAWMAKING_PROCEDURES": {},
    "JUSTICE_PROCEDURES": {}, "CHARTERS": [], "CAST_ROLE_TRADES": {}, "HOUSEHOLDS": {},
    "LABOUR_TASKS": {}, "GOVERNANCE_OFFICES": {}, "MIN_SKILL": {}, "SYSTEM_OF_TRADE": {},
    "PREFERENCE_RESEARCH": {}, "BITTER_TASTER_STATUS": {}, "BITTER_LIKING_BY_STATUS": {},
    "COLOUR_PREFERENCE": {}, "TASTE_PREFERENCE": {}, "LIMITATION_PREVALENCE": {}, "BALANCE_SCENARIO": {},
    "JOB_REFERENCE_PER_100": {}, "ANIMAL_SERVICES": frozenset(), "OPEN_RECIPE_SKILLS": {},
}
# Names with a scalar value or a table that holds only the authored content.


def _file_for(name):
    """The file bigville keeps the table in, so the two packs have the same layout."""
    return BIG_FILE[name]


def main():
    if os.path.exists(os.path.join(PACK_DIR, "pack.json")):
        raise SystemExit("packs/test_hamlet/pack.json exists; refusing to overwrite")
    authored = _authored()
    manifest_order = [t["name"] for t in json.load(open(os.path.join(ROOT, "packs", "bigville", "pack.json")))["tables"]]
    # Derived names are compiled, never stored.
    names = [n for n in manifest_order if n not in ("POLICIES", "LAWS", "_SKILL_CLUSTER")]
    values = {}
    for name in names:
        if name in authored:
            values[name] = copy.deepcopy(authored[name])
        elif name in COPIED:
            values[name] = copy.deepcopy(BIGVILLE[name])
        elif name in EMPTY:
            values[name] = copy.deepcopy(EMPTY[name])
        else:
            raise SystemExit(f"no content decided for {name}")
    # Files: one table per file.
    entries, written = [], {}
    for name in names:
        rel = _file_for(name)
        written.setdefault(rel, {})[name] = values[name]
        entries.append({"name": name, "file": rel})
    for rel, tables in written.items():  # one file per bigville file; scalar groups stay grouped
        types_all, out = {}, {}
        for name, value in tables.items():
            types = {}
            out[name] = to_json(value, types)
            if types:
                types_all[name] = types
        doc = (f"Test pack 'test_hamlet' (Phase 013b): {', '.join(sorted(tables))}. Authored, copied, or "
               "empty as recorded in docs/phases/phase013b/PHASE013B_REPORT.md. Copied values keep "
               "their citations in packs/bigville.")
        body = {"_doc": doc, "_types": types_all, "tables": out}
        path = os.path.join(PACK_DIR, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(body, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    manifest = {"format": 1, "name": "test_hamlet", "version": 1,
                "description": "Standalone test pack: a hamlet with one baker, one building, two recipes. "
                               "Does not extend bigville. Every bound table name is present.",
                "extends": None, "tables": entries}
    with open(os.path.join(PACK_DIR, "pack.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("wrote", len(entries), "tables into", len(written), "files")


if __name__ == "__main__":
    main()
