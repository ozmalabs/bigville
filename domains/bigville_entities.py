"""bigville_entities.py -- THE SINGLE SOURCE OF TRUTH for bigville world entities, as PURE DATA.

The data lives in three modules, and this module is their combined view (every public name of all
three is available here, so `from domains import bigville_entities as E` keeps working):
  world_affordances -- how the world works: things, recipes, places, land, animals, bodies, actions.
                       Facts about the world, not public knowledge.
  shared_frames     -- what residents can hold in common: skills, trades, jobs, concepts, laws.
  population        -- how a founding population is drawn and seeded into jobs.

No game logic lives in the data -- only the entities and how they combine. This module also holds the
self-tests over all three: check_consistency (cross-references, pipelines, unused items),
analyse_systems (the production DAG, weights, systems, balance), and the job seeding report.
Run `python3 domains/bigville_entities.py` for the printed report (exit status 1 on errors).
"""
from __future__ import annotations

import os as _os
import sys as _sys

if __package__ in (None, ""):          # run as a script: make `domains` importable
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from domains.world_affordances import *       # noqa: E402,F401,F403
from domains.shared_frames import *           # noqa: E402,F401,F403
from domains.population import *              # noqa: E402,F401,F403
from domains.knowledge import *               # noqa: E402,F401,F403
from domains.world_affordances import (     # noqa: E402,F401  private helpers, for a complete view
    _serving_kind, _tag_yield, _type_value_parts,
)
from domains.population import _draw_categorical   # noqa: E402,F401
from domains.world_affordances import (  # noqa: E402
    _balance_flows,
    _recipe_unit_cost,
    _recipes_for,
    _value_parts,
)


# ---------------------------------------------------------------------------
# CONSISTENCY CHECK -- does the data hang together?
# ---------------------------------------------------------------------------
# A pure function over the tables above (no world, no engine). It reports three severities:
#   errors   -- a dangling reference: a table names a kind/recipe/trade/building that does not exist.
#   warnings -- a completeness gap: an item nothing produces, an item nothing uses, a recipe whose
#               inputs can never be obtained, a crop whose seed cannot be replaced, ...
#   info     -- facts worth knowing that are not defects (counts, construction-only trades, ...).
# Run `python3 domains/bigville_entities.py` for the printed report (exit status 1 on errors). It also
# prints analyse_systems(): the production DAG, item/system weights, and the per-period balance.
# Scope: this sees only the data. Behaviour that lives in world code (e.g. reading a newspaper, the
# butcher's slaughter list, set_coin) is invisible here, so a "never used" item may still be used there.


def _item_sources():
    """kind -> sorted list of the ways it comes into existence (not counting recipes)."""
    src = {}

    def add(kind, how):
        src.setdefault(kind, set()).add(how)

    for kind, spec in ITEMS.items():
        if spec.get("imported"):
            add(kind, "import")
        if spec.get("scraps_of"):
            add(kind, f"eating {spec['scraps_of']}")
    for crop, spec in CROPS.items():
        add(spec["harvest"], f"crop {crop}")
        for kind in spec.get("byproducts", {}):
            add(kind, f"byproduct of {crop}")
        if float(spec.get("seed_return", 1.0)) > 0.0:
            add(spec["seed"], f"harvest of {crop}")
    for species, spec in ANIMALS.items():
        for product in spec.get("gives", {}):
            add(product, f"animal {species}")
        if float(spec.get("manure", 0.0)) > 0.0:
            add("manure", f"animal {species}")
    for r in RECIPES:
        for kind in r.get("byproducts", {}):
            add(kind, f"byproduct of {r['name']}")
        for kind, _ in r["in"]:
            if is_input_type(kind):
                for left in INPUT_TYPES[kind].get("byproducts", {}):
                    add(left, f"burning {kind} in {r['name']}")
    for kind in STARTING_STOCK:
        add(kind, "starting stock")
    for kind in RESOURCE_DEPOSITS:
        add(kind, "deposit")
    for trade, chain in SHOP_CHAINS.items():
        add(chain["out"], f"shop {trade}")
    for kind in PASTURE_YIELDS:
        add(kind, "pasture")
    for name, spec in FUEL_SOURCES.items():
        add(spec["fuel"], f"fuel source {name}")
    if WATER_SOURCES:
        add("water", "water source")
    for name, spec in WASTE_CYCLES.items():
        add(spec["output"], f"waste cycle {name}")
    add("coin", "currency")
    return src


def _item_uses():
    """kind -> set of the ways it is consumed or used."""
    use = {}

    def add(kind, how):
        use.setdefault(kind, set()).add(how)

    for r in RECIPES:
        for kind, _ in r["in"]:
            if is_input_type(kind):
                for member, _units in type_members(kind):
                    add(member, f"{kind} for {r['name']}")
            else:
                add(kind, f"input to {r['name']}")
        for tool in r.get("tools", []) + r.get("method_tools", []):
            add(tool, f"tool for {r['name']}")
    for member, _units in type_members(NITROGEN["fertiliser_type"]):
        add(member, "spread on fields (fertilise)")
    for name, spec in FENCE_TYPES.items():
        add(spec["material"], f"builds {name}")
    for trade, spec in TRADES.items():
        for tool in spec.get("tools", []):
            add(tool, f"tool of {trade}")
    for species, spec in ANIMALS.items():
        for kind in feed_kinds(spec.get("eats", "")):
            add(kind, f"feed for {species}")
    for crop, spec in CROPS.items():
        add(spec["seed"], f"sown for {crop}")
    for name, spec in BUILDING_PROJECTS.items():
        for kind in spec.get("inputs", {}):
            add(kind, f"builds {name}")
    for name, spec in INFRASTRUCTURE.items():
        for kind in spec.get("maintenance", []):
            add(kind, f"maintains {name}")
    for trade, chain in SHOP_CHAINS.items():
        add(chain["in"], f"shop {trade}")
        add(chain["out"], f"sold by {trade}")
    for name, spec in LABOUR_TASKS.items():
        for kind in spec.get("inputs", []):
            if kind in ITEMS:
                add(kind, f"labour task {name}")
    for name, spec in FUEL_SOURCES.items():
        add(spec["fuel"], "fuel")
    for kind in SERVING_EQUIPMENT:
        add(kind, "serving equipment")
    for spec in SERVING_UTENSILS.values():
        for kind in spec["alternatives"]:
            add(kind, "serving utensil")
    for spec in CONTAINERS.values():
        for kind in spec.get("alternatives", []):
            add(kind, "serving vessel")
    for kind, spec in ITEMS.items():
        if spec.get("food"):
            add(kind, "eaten")
        if spec.get("garment"):
            add(kind, "worn")
        if spec.get("container"):
            add(kind, "holds goods")
        if spec.get("class") in ("tool", "good", "furniture") and spec.get("verb"):
            add(kind, f"used to {spec['verb']}")
        if spec.get("class") == "component":
            add(kind, f"part of {spec.get('for')}")
        if spec.get("readable"):
            add(kind, "read")
    add("coin", "currency")
    return use


def _check_founding_town(errors, warnings, info):
    """The founding town (Phase 016a): the cast, the map, and the sites that from_town100() builds.

    A pack has all of the required tables or none. A pack with none has no founding town, and the
    self-test reports that as info. Roles are checked against TRADES, JOBS, and CAST_ROLE_TRADES;
    a role in none of them is info, because the cast still seeds it (the world gives it no trades).
    The tile names are those of worlds.bigville_sim_world.TILE_NAME (not imported: this module has
    no world code).
    """
    required = {"FOUNDING_JOBS": FOUNDING_JOBS, "FOUNDING_AGE": FOUNDING_AGE, "FOUNDING_CLASS": FOUNDING_CLASS,
                "FOUNDING_FIRST_NAMES": FOUNDING_FIRST_NAMES, "FOUNDING_LAST_NAMES": FOUNDING_LAST_NAMES,
                "FOUNDING_PERSONALITY": FOUNDING_PERSONALITY,
                "FOUNDING_CAUSAL_RESOLUTION": FOUNDING_CAUSAL_RESOLUTION,
                "FOUNDING_DRAW_BOUNDS": FOUNDING_DRAW_BOUNDS, "FOUNDING_MAP": FOUNDING_MAP,
                "FOUNDING_DEPOSITS": FOUNDING_DEPOSITS, "FOUNDING_WORKPLACES": FOUNDING_WORKPLACES,
                "FOUNDING_BUILDING_SITES": FOUNDING_BUILDING_SITES,
                "FOUNDING_PLACE_LABELS": FOUNDING_PLACE_LABELS}
    empty = sorted(name for name, value in required.items() if not value)
    if len(empty) == len(required):
        info.append("FOUNDING TOWN: none (this pack has no founding town; from_town100 refuses it)")
        return
    if empty:
        errors.append(f"FOUNDING TOWN: {', '.join(empty)} empty while the others are filled; "
                      f"a pack has all of these tables or none")
        return
    tile_names = {"grass", "path", "wall", "floor", "square", "tree", "water"}
    W, H = FOUNDING_MAP.get("width"), FOUNDING_MAP.get("height")
    if not (isinstance(W, int) and isinstance(H, int) and W >= 3 and H >= 3):
        errors.append("FOUNDING_MAP: width and height must be whole numbers of at least 3")
        return

    def inside(x, y):
        return isinstance(x, int) and isinstance(y, int) and 0 <= x < W and 0 <= y < H

    # --- the cast: jobs, staffing, ages, and the classes they are drawn into
    groups = FOUNDING_CLASS.get("by_group", {})
    stations = FOUNDING_CLASS.get("station_by_group", {})
    literacy = FOUNDING_CLASS.get("literacy_by_class", {})
    capability = FOUNDING_CLASS.get("capability_by_literacy", {})
    residents = int(BALANCE_SCENARIO.get("residents", 0))
    roles = set(FOUNDING_JOBS)
    for job in JOBS:
        if job not in FOUNDING_JOBS:
            errors.append(f"FOUNDING_JOBS: JOBS[{job}] has no row, so the job has no workplace or group")
    for job, row in FOUNDING_JOBS.items():
        where = f"FOUNDING_JOBS[{job}]"
        if job not in JOBS:
            errors.append(f"{where}: '{job}' is not a JOBS key")
        if row.get("group") not in groups:
            errors.append(f"{where}.group: '{row.get('group')}' has no FOUNDING_CLASS.by_group entry")
        if row.get("workplace") not in FOUNDING_WORKPLACES and row.get("workplace") not in FOUNDING_DEPOSITS \
                and row.get("workplace") != "farm":
            errors.append(f"{where}.workplace: '{row.get('workplace')}' is not a FOUNDING_WORKPLACES key, a "
                          f"FOUNDING_DEPOSITS kind, or 'farm'")
        mean, sd = row.get("role_identity_mean"), row.get("role_identity_sd")
        if not (isinstance(mean, (int, float)) and 0.0 <= mean <= 1.0):
            errors.append(f"{where}.role_identity_mean: must be between 0 and 1")
        if not (isinstance(sd, (int, float)) and sd >= 0.0):
            errors.append(f"{where}.role_identity_sd: must be zero or more")
    info.append(f"FOUNDING TOWN: {residents} residents in {len(FOUNDING_JOBS)} jobs on a {W}x{H} map")
    if residents < 1:
        errors.append("FOUNDING_JOBS: the cast has no residents (BALANCE_SCENARIO.residents is 0)")
    staffing = check_job_seed(residents)
    if not staffing["ok"]:
        errors.append("FOUNDING TOWN: the jobs do not staff the founding town: " + "; ".join(staffing["issues"]))
    for group in {row.get("group") for row in FOUNDING_JOBS.values()}:
        if group not in stations:
            errors.append(f"FOUNDING_CLASS.station_by_group: group '{group}' has no station")
    for group, shares in groups.items():
        rich, middle = shares.get("rich"), shares.get("middle")
        if not (isinstance(rich, (int, float)) and isinstance(middle, (int, float))
                and 0.0 <= rich and 0.0 <= middle and rich + middle <= 1.0):
            errors.append(f"FOUNDING_CLASS.by_group[{group}]: rich and middle must be shares that sum to at most 1")
    for klass in ("rich", "middle", "poor"):
        if not (isinstance(literacy.get(klass), (int, float)) and 0.0 <= literacy[klass] <= 1.0):
            errors.append(f"FOUNDING_CLASS.literacy_by_class: '{klass}' must be a probability between 0 and 1")
    for key in ("literate", "unlettered"):
        if not (isinstance(capability.get(key), (int, float)) and 0.0 <= capability[key] <= 1.0):
            errors.append(f"FOUNDING_CLASS.capability_by_literacy: '{key}' must be between 0 and 1")
    for group, station in stations.items():
        if station not in STATION_EDUCATION:
            errors.append(f"FOUNDING_CLASS.station_by_group[{group}]: '{station}' is not a STATION_EDUCATION key")
    adult = LIFE_STAGES["adult"]
    age = FOUNDING_AGE
    if not all(field in age for field in ("mean", "sd", "min", "max", "stream")):
        errors.append("FOUNDING_AGE: needs mean, sd, min, max, and stream")
    elif not (adult["age_min"] <= age["min"] <= age["mean"] <= age["max"] <= adult["age_max"] and age["sd"] >= 0):
        errors.append(f"FOUNDING_AGE: founders must be of working age ({adult['age_min']} to {adult['age_max']}); "
                      f"min, mean, and max must lie in that range in order, with sd zero or more")

    # --- names, anchors, and drawn traits
    for role in FOUNDING_ANCHOR_NAMES:
        if role not in roles:
            errors.append(f"FOUNDING_ANCHOR_NAMES[{role}]: no FOUNDING_JOBS row has that job")
    anchor_names = list(FOUNDING_ANCHOR_NAMES.values())
    if len(set(anchor_names)) != len(anchor_names):
        errors.append("FOUNDING_ANCHOR_NAMES: two roles share a name")
    anchored_roles = len({role for role in FOUNDING_ANCHOR_NAMES if role in roles})
    combos = len(FOUNDING_FIRST_NAMES) * len(FOUNDING_LAST_NAMES)
    # The first resident of each anchor role takes its anchor name; every other resident draws a pool
    # name, and the pool excludes the anchor names.
    needed = residents - anchored_roles
    available = combos - len(anchor_names)
    if available < needed:
        errors.append(f"FOUNDING names: {available} names outside the anchors cannot cover the "
                      f"{needed} residents who draw one")
    for key, spec in FOUNDING_PERSONALITY.items():
        if not all(field in spec for field in ("mean", "sd", "lo", "hi")):
            errors.append(f"FOUNDING_PERSONALITY[{key}]: needs mean, sd, lo, and hi")
            continue
        if spec["sd"] < 0:
            errors.append(f"FOUNDING_PERSONALITY[{key}]: sd must be zero or more")
        if spec["lo"] is not None and spec["hi"] is not None and spec["lo"] > spec["hi"]:
            errors.append(f"FOUNDING_PERSONALITY[{key}]: lo is above hi")
    cause = FOUNDING_CAUSAL_RESOLUTION
    for part in ("floor", "ceiling"):
        if not all(field in cause.get(part, {}) for field in ("mean", "sd")):
            errors.append(f"FOUNDING_CAUSAL_RESOLUTION.{part}: needs mean and sd")
    if not (0.0 <= cause.get("ceiling_weight", -1) <= 1.0):
        errors.append("FOUNDING_CAUSAL_RESOLUTION.ceiling_weight: must be between 0 and 1")
    if not (isinstance(cause.get("lo"), int) and isinstance(cause.get("hi"), int) and 1 <= cause["lo"] <= cause["hi"]):
        errors.append("FOUNDING_CAUSAL_RESOLUTION: lo and hi must be whole bin counts, 1 <= lo <= hi")
    bounds = FOUNDING_DRAW_BOUNDS.get("role_identity", {})
    if not (0.0 <= bounds.get("lo", -1) < bounds.get("hi", -1) <= 1.0):
        errors.append("FOUNDING_DRAW_BOUNDS.role_identity: needs 0 <= lo < hi <= 1")

    # --- the map and its resource bodies
    body_tiles = set()
    for body in FOUNDING_MAP.get("resource_bodies", []):
        tile = body.get("tile")
        body_tiles.add(tile)
        if tile not in tile_names:
            errors.append(f"FOUNDING_MAP.resource_bodies: tile '{tile}' is not a map tile")
        x0, y0, x1, y1 = body.get("rect", (0, 0, -1, -1))
        if not (inside(x0, y0) and inside(x1, y1) and x0 <= x1 and y0 <= y1):
            errors.append(f"FOUNDING_MAP.resource_bodies[{tile}]: rect {body.get('rect')} is off the map")
    for kind in FOUNDING_DEPOSITS:
        if kind not in RESOURCE_DEPOSITS:
            errors.append(f"FOUNDING_DEPOSITS: '{kind}' is not a RESOURCE_DEPOSITS kind")
        elif RESOURCE_DEPOSITS[kind]["tile"] not in body_tiles:
            errors.append(f"FOUNDING_DEPOSITS: '{kind}' sits beside a '{RESOURCE_DEPOSITS[kind]['tile']}' body, "
                          f"and FOUNDING_MAP has none")
    if len(set(FOUNDING_DEPOSITS)) != len(FOUNDING_DEPOSITS):
        errors.append("FOUNDING_DEPOSITS: a kind is listed twice")
    square = FOUNDING_MAP.get("square", {})
    if not (inside(square.get("x"), square.get("y")) and inside(square.get("x", 0) + square.get("w", 0) - 1,
                                                                  square.get("y", 0) + square.get("h", 0) - 1)):
        errors.append("FOUNDING_MAP.square: the square is off the map")
    for name in ("road_rows", "road_cols"):
        for road in FOUNDING_MAP.get(name, []):
            line = road.get("row" if name == "road_rows" else "col")
            if not (isinstance(line, int) and (1 <= line <= (H - 2 if name == "road_rows" else W - 2))):
                errors.append(f"FOUNDING_MAP.{name}: {line} is not an interior line of the map")
            if not isinstance(road.get("phase"), int):
                errors.append(f"FOUNDING_MAP.{name}: phase must be a whole number")
    for name in ("bend_offsets_horizontal", "bend_offsets_vertical"):
        if not FOUNDING_MAP.get(name):
            errors.append(f"FOUNDING_MAP.{name}: empty, so the roads cannot bend")
    if not (isinstance(FOUNDING_MAP.get("bend_run"), int) and FOUNDING_MAP["bend_run"] >= 1):
        errors.append("FOUNDING_MAP.bend_run: must be a whole number of at least 1")
    for cell in FOUNDING_MAP.get("scattered_trees", []):
        if not inside(*cell):
            errors.append(f"FOUNDING_MAP.scattered_trees: {cell} is off the map")
    plots = FOUNDING_MAP.get("farm_plots", {})
    if not (isinstance(plots.get("count"), int) and plots["count"] >= 1
            and isinstance(plots.get("columns"), int) and plots["columns"] >= 1):
        errors.append("FOUNDING_MAP.farm_plots: needs a count and a columns value of at least 1")
    elif not inside(*plots.get("origin", (-1, -1))):
        errors.append("FOUNDING_MAP.farm_plots: origin is off the map")

    # --- workplaces, buildings, labels, and fallbacks
    if "market" not in FOUNDING_WORKPLACES:
        errors.append("FOUNDING_WORKPLACES: no 'market' anchor (the square and the store stand there)")
    for name, cell in FOUNDING_WORKPLACES.items():
        if not inside(*cell):
            errors.append(f"FOUNDING_WORKPLACES[{name}]: {cell} is off the map")
    for kind, cell in FOUNDING_BUILDING_SITES.items():
        if kind not in BUILDINGS:
            errors.append(f"FOUNDING_BUILDING_SITES[{kind}]: not a BUILDINGS kind")
        if not inside(*cell):
            errors.append(f"FOUNDING_BUILDING_SITES[{kind}]: {cell} is off the map")
    for kind, label in FOUNDING_PLACE_LABELS.items():
        if kind not in FOUNDING_WORKPLACES:
            errors.append(f"FOUNDING_PLACE_LABELS[{kind}]: not a FOUNDING_WORKPLACES key")
        if not (isinstance(label, str) and label):
            errors.append(f"FOUNDING_PLACE_LABELS[{kind}]: needs a label")
    unresolved = []
    for kind, target in FOUNDING_ANCHOR_ALIASES.items():
        if kind not in BUILDINGS:
            errors.append(f"FOUNDING_ANCHOR_ALIASES[{kind}]: not a BUILDINGS kind")
        if target not in FOUNDING_WORKPLACES and target not in FOUNDING_DEPOSITS:
            unresolved.append(f"{kind}->{target}")
    if unresolved:
        info.append(f"FOUNDING_ANCHOR_ALIASES: {', '.join(sorted(unresolved))} name no workplace, so those "
                    f"buildings fall back to the market anchor (as the code did at HEAD)")


def _knowledge_view():
    """This entity view as a plain namespace (every name the knowledge module reads from its pack)."""
    import types as _types
    return _types.SimpleNamespace(**{k: v for k, v in globals().items() if not k.startswith("__")})


def _check_knowledge(errors, warnings, info):
    """Phase 019: the knowledge specs (references and shape) and, for a pack with a founding town, the
    aware and understanding shares of the seeded cast (see town_knowledge_shares)."""
    from domains.knowledge import check_knowledge, town_knowledge_shares, knowledge_shares_flags
    pack = _knowledge_view()
    check_knowledge(pack, errors, warnings, info)
    if not FOUNDING_JOBS or not FOUNDING_MAP:
        return
    from worlds.bigville_town100_world import build_town_100, generate_cast100
    seed = 305000                       # populate_town100's default founding seed
    _, _, layout = build_town_100(seed, entities=pack)
    cast = generate_cast100(layout, seed, pack)
    shares = town_knowledge_shares(cast, pack, seed=seed)
    info.extend(shares["report"])
    knowledge_shares_flags(shares, pack, errors, warnings)


def check_consistency():
    """Check every cross-reference and production pipeline in the entity data.

    Returns ``{"errors": [...], "warnings": [...], "info": [...], "stats": {...}}``. Each message is
    a plain string naming the table and the offending entry.
    """
    errors, warnings, info = [], [], []
    items = set(ITEMS)
    recipes = {r["name"]: r for r in RECIPES}
    known_places = set(BUILDINGS)

    def ref(kind, where):
        if kind not in items:
            errors.append(f"{where}: '{kind}' is not an item")

    # -- recipes ----------------------------------------------------------------
    seen = set()
    for r in RECIPES:
        name = r["name"]
        if name in seen:
            errors.append(f"RECIPES: duplicate recipe name '{name}'")
        seen.add(name)
        if r.get("requires") not in TRADES:
            errors.append(f"RECIPES[{name}]: requires unknown trade '{r.get('requires')}'")
        for kind, qty in r["in"]:
            if is_input_type(kind):
                if not type_members(kind):
                    errors.append(f"RECIPES[{name}].in: type slot '{kind}' has no member items")
            else:
                ref(kind, f"RECIPES[{name}].in")
            if float(qty) <= 0:
                errors.append(f"RECIPES[{name}].in: non-positive quantity for '{kind}'")
        ref(r["out"][0], f"RECIPES[{name}].out")
        if float(r["out"][1]) <= 0:
            errors.append(f"RECIPES[{name}].out: non-positive quantity")
        for tool in r.get("tools", []):
            ref(tool, f"RECIPES[{name}].tools")
        for tool in r.get("method_tools", []):
            if tool not in items and tool not in PREPARATION_EQUIPMENT:
                errors.append(f"RECIPES[{name}].method_tools: '{tool}' is neither an item nor equipment")
        hard_equipment = sorted(set(r.get("tools", [])) & set(PREPARATION_EQUIPMENT))
        if hard_equipment and name not in HEATED_FOOD_RECIPES and ITEMS.get(r["out"][0], {}).get("food"):
            warnings.append(f"RECIPES[{name}]: hard-requires cooking equipment {hard_equipment} but is not "
                            f"in HEATED_FOOD_RECIPES (so any heat+containment method is not accepted)")
        if r["out"][0] in [k for k, _ in r["in"]]:
            warnings.append(f"RECIPES[{name}]: output '{r['out'][0]}' is also an input")
        for season in r.get("seasons", []):
            if season not in SEASONS:
                errors.append(f"RECIPES[{name}].seasons: unknown season '{season}'")
        for kind in r.get("byproducts", {}):
            ref(kind, f"RECIPES[{name}].byproducts")
        if not r["in"] and not r.get("gathered_from"):
            warnings.append(f"RECIPES[{name}]: has no inputs but does not say where it is gathered_from")
    for type_name, spec in INPUT_TYPES.items():
        if type_name in items:
            errors.append(f"INPUT_TYPES[{type_name}]: type name collides with an item")
        for kind in spec.get("byproducts", {}):
            ref(kind, f"INPUT_TYPES[{type_name}].byproducts")
    for table, keys in (("MIN_SKILL", MIN_SKILL), ("RECIPE_EXERTION", RECIPE_EXERTION),
                        ("HEATED_FOOD_RECIPES", HEATED_FOOD_RECIPES)):
        for name in keys:
            if name not in recipes:
                errors.append(f"{table}: '{name}' is not a recipe")

    # -- items ------------------------------------------------------------------
    for kind, spec in ITEMS.items():
        if spec.get("class") == "component":
            if spec.get("for") not in items:
                errors.append(f"ITEMS[{kind}]: component for unknown item '{spec.get('for')}'")
        if spec.get("scraps_of") and spec["scraps_of"] not in items:
            errors.append(f"ITEMS[{kind}]: scraps of unknown item '{spec['scraps_of']}'")
        if kind.endswith("_seed") and not spec.get("seed"):
            warnings.append(f"ITEMS[{kind}]: looks like a seed but lacks seed: True")
        if spec.get("seed") and not any(c["seed"] == kind for c in CROPS.values()):
            warnings.append(f"ITEMS[{kind}]: seed for no crop")
        if spec.get("container") and float(spec.get("capacity", 0.0)) <= 0:
            errors.append(f"ITEMS[{kind}]: container without a positive capacity")
    for kind in SCARCITY:
        ref(kind, "SCARCITY")
    for kind in STARTING_STOCK:
        ref(kind, "STARTING_STOCK")

    # -- containers and food service --------------------------------------------
    for name, spec in CONTAINERS.items():
        for kind in spec.get("preferred_contents", []):
            ref(kind, f"CONTAINERS[{name}].preferred_contents")
        for kind in spec.get("alternatives", []):
            ref(kind, f"CONTAINERS[{name}].alternatives")
        if name in ITEMS and ITEMS[name].get("capacity") not in (None, spec.get("capacity")):
            errors.append(f"CONTAINERS[{name}]: capacity {spec.get('capacity')} disagrees with "
                          f"ITEMS[{name}] capacity {ITEMS[name].get('capacity')}")
    for name, spec in SERVING_UTENSILS.items():
        for kind in spec["alternatives"]:
            ref(kind, f"SERVING_UTENSILS[{name}]")
    for kind in SERVING_EQUIPMENT:
        ref(kind, "SERVING_EQUIPMENT")
    for kind in sorted(SOUP_FOODS | DRINK_FOODS):
        ref(kind, "SOUP_FOODS/DRINK_FOODS")
        if kind in items and not ITEMS[kind].get("food"):
            errors.append(f"SOUP_FOODS/DRINK_FOODS: '{kind}' is served as food but ITEMS[{kind}] lacks food: True")
    for name, spec in PREPARATION_METHODS.items():
        for eq in spec["equipment"]:
            if eq not in PREPARATION_EQUIPMENT:
                errors.append(f"PREPARATION_METHODS[{name}]: unknown equipment '{eq}'")

    # -- trades, buildings, construction ----------------------------------------
    for trade, spec in TRADES.items():
        building = spec.get("building")
        if building is None:
            if not spec.get("site"):
                errors.append(f"TRADES[{trade}]: no building and no site")
        elif building not in known_places:
            errors.append(f"TRADES[{trade}]: unknown building '{building}'")
        elif not BUILDINGS[building].get("founding", True):
            info.append(f"TRADES[{trade}]: works at '{building}', which must be built first")
        for tool in spec.get("tools", []):
            ref(tool, f"TRADES[{trade}].tools")
    for role, trades in CAST_ROLE_TRADES.items():
        for trade in trades:
            if trade not in TRADES:
                errors.append(f"CAST_ROLE_TRADES[{role}]: unknown trade '{trade}'")
    for name, spec in BUILDING_PROJECTS.items():
        if spec.get("building") not in known_places:
            errors.append(f"BUILDING_PROJECTS[{name}]: unknown building '{spec.get('building')}'")
        for kind in spec.get("inputs", {}):
            ref(kind, f"BUILDING_PROJECTS[{name}].inputs")
    for name, spec in INFRASTRUCTURE.items():
        for kind in spec.get("maintenance", []):
            ref(kind, f"INFRASTRUCTURE[{name}].maintenance")
    for name, spec in BUILDINGS.items():
        if not spec.get("founding", True) and not any(
                p.get("building") == name for p in BUILDING_PROJECTS.values()):
            warnings.append(f"BUILDINGS[{name}]: not standing at founding and no BUILDING_PROJECT raises it")
    trades_with_recipes = {r["requires"] for r in RECIPES}
    service = sorted(t for t in TRADES if t not in trades_with_recipes)
    info.append(f"TRADES with no recipe (service or gathering work): {', '.join(service)}")
    for fixture in TOWN_SQUARE_FIXTURES:
        for kind in fixture.get("goods", []):
            if kind not in items:
                warnings.append(f"TOWN_SQUARE_FIXTURES[{fixture['name']}]: goods label '{kind}' is not an item")

    # -- animals, crops, land ----------------------------------------------------
    for species, spec in ANIMALS.items():
        for field in ("eats", "ration", "starve_limit", "matures", "lifespan", "role"):
            if field not in spec:
                errors.append(f"ANIMALS[{species}]: missing '{field}'")
        for product in spec.get("gives", {}):
            if product not in items and product not in ANIMAL_SERVICES:
                errors.append(f"ANIMALS[{species}].gives: '{product}' is neither an item nor a service")
        for kind in feed_kinds(spec.get("eats", "")):
            ref(kind, f"ANIMALS[{species}].eats")
    for species in ANIMAL_NPC_SETUP:
        if species not in ANIMALS:
            errors.append(f"ANIMAL_NPC_SETUP: unknown species '{species}'")
    for task, spec in ANIMAL_HUSBANDRY.items():
        if spec["species"] not in ANIMALS:
            errors.append(f"ANIMAL_HUSBANDRY[{task}]: unknown species '{spec['species']}'")
        elif spec["product"] not in ANIMALS[spec["species"]].get("gives", {}):
            errors.append(f"ANIMAL_HUSBANDRY[{task}]: {spec['species']} does not give '{spec['product']}'")
    for crop, spec in CROPS.items():
        ref(spec["seed"], f"CROPS[{crop}].seed")
        ref(spec["harvest"], f"CROPS[{crop}].harvest")
        if spec.get("season") not in SEASONS:
            errors.append(f"CROPS[{crop}]: unknown season '{spec.get('season')}'")
        for kind in spec.get("byproducts", {}):
            ref(kind, f"CROPS[{crop}].byproducts")
        if "nitrogen" not in spec:
            warnings.append(f"CROPS[{crop}]: no nitrogen demand -- it never draws on the soil")
    for crop in STARTING_CROPS:
        if crop not in CROPS:
            errors.append(f"STARTING_CROPS: unknown crop '{crop}'")
    for group, crops in ARABLE_ROTATION.items():
        for crop in crops:
            if crop not in CROPS:
                errors.append(f"ARABLE_ROTATION[{group}]: unknown crop '{crop}'")
            elif group == "restorative" and float(CROPS[crop].get("fixes", 0.0)) <= 0.0:
                errors.append(f"ARABLE_ROTATION[restorative]: '{crop}' does not fix nitrogen")
    for soil, spec in SOILS.items():
        if "nitrogen" not in spec:
            errors.append(f"SOILS[{soil}]: no starting nitrogen")
    if NITROGEN["fertiliser_type"] not in INPUT_TYPES:
        errors.append(f"NITROGEN: fertiliser_type '{NITROGEN['fertiliser_type']}' is not an INPUT_TYPE")
    for kind in SLAUGHTER_PRODUCTS:
        ref(kind, "SLAUGHTER_PRODUCTS")
    _flows, _notes, streams = _balance_flows(BALANCE_SCENARIO)
    covered = {}
    for job, spec in JOBS.items():
        for trade in spec["trades"]:
            if trade not in TRADES:
                errors.append(f"JOBS[{job}]: unknown trade '{trade}'")
        for tool in spec.get("tools", []):
            ref(tool, f"JOBS[{job}].tools")
        for stream, share in spec.get("duties", {}).items():
            if stream not in streams:
                errors.append(f"JOBS[{job}].duties: unknown work stream '{stream}'")
            covered[stream] = covered.get(stream, 0.0) + float(share)
    for stream in streams:
        if abs(covered.get(stream, 0.0) - 1.0) > 1e-6:
            errors.append(f"JOBS: work stream '{stream}' is {covered.get(stream, 0.0):.0%} covered by job duties")
    if sum(1 for spec in JOBS.values() if spec.get("spare")) != 1:
        errors.append("JOBS: exactly one job must take the spare residents (spare: True)")
    used_skills = set()
    for trade in TRADES:
        if not TRADE_SKILLS.get(trade):
            errors.append(f"TRADE_SKILLS: trade '{trade}' exercises no skill")
    for trade, skills in TRADE_SKILLS.items():
        if trade not in TRADES:
            errors.append(f"TRADE_SKILLS: unknown trade '{trade}'")
        for skill in skills:
            used_skills.add(skill)
            if skill not in SKILLS:
                errors.append(f"TRADE_SKILLS[{trade}]: unknown skill '{skill}'")
    for name, skill in OPEN_RECIPE_SKILLS.items():
        used_skills.add(skill)
        if name not in recipes:
            errors.append(f"OPEN_RECIPE_SKILLS: '{name}' is not a recipe")
        elif not recipes[name].get("open"):
            errors.append(f"OPEN_RECIPE_SKILLS: '{name}' is not an open recipe")
        if skill not in SKILLS:
            errors.append(f"OPEN_RECIPE_SKILLS[{name}]: unknown skill '{skill}'")
    for r in RECIPES:
        if r.get("open") and r["name"] not in OPEN_RECIPE_SKILLS:
            errors.append(f"RECIPES[{r['name']}]: open recipe names no skill in OPEN_RECIPE_SKILLS")
        if recipe_skill(r) is None:
            errors.append(f"RECIPES[{r['name']}]: exercises no skill")
    for skill in sorted(set(SKILLS) - used_skills):
        warnings.append(f"SKILLS[{skill}]: no trade or open recipe exercises it")
    clustered = {}
    for cluster, spec in SKILL_CLUSTERS.items():
        if spec["metaskill"] not in METASKILLS:
            errors.append(f"SKILL_CLUSTERS[{cluster}]: unknown metaskill '{spec['metaskill']}'")
        for skill in spec["skills"]:
            if skill not in SKILLS:
                errors.append(f"SKILL_CLUSTERS[{cluster}]: unknown skill '{skill}'")
            clustered.setdefault(skill, []).append(cluster)
    for skill in SKILLS:
        if len(clustered.get(skill, [])) != 1:
            errors.append(f"SKILLS[{skill}]: in {len(clustered.get(skill, []))} clusters (must be exactly 1)")
    for skill, spec in SKILLS.items():
        if spec.get("learning") not in LEARNING_KINDS:
            errors.append(f"SKILLS[{skill}]: learning must be 'physical' or 'cognitive' (got {spec.get('learning')!r})")
    for meta, spec in METASKILLS.items():
        if spec.get("learning") not in LEARNING_KINDS:
            errors.append(f"METASKILLS[{meta}]: learning must be 'physical' or 'cognitive' (got {spec.get('learning')!r})")
    for meta, spec in METASKILLS.items():
        if not any(c["metaskill"] == meta for c in SKILL_CLUSTERS.values()):
            warnings.append(f"METASKILLS[{meta}]: no cluster belongs to it")
        if not 0.0 <= float(spec.get("g_loading", -1)) <= 1.0:
            errors.append(f"METASKILLS[{meta}]: g_loading must be between 0 and 1")
    for name, spec in SKILL_LIMITATIONS.items():
        if name not in LIMITATION_PREVALENCE:
            errors.append(f"SKILL_LIMITATIONS[{name}]: no prevalence in population.LIMITATION_PREVALENCE")
        for skill, effect in spec.get("skills", {}).items():
            if skill not in SKILLS:
                errors.append(f"SKILL_LIMITATIONS[{name}]: unknown skill '{skill}'")
        for meta in spec.get("metaskills", {}):
            if meta not in METASKILLS:
                errors.append(f"SKILL_LIMITATIONS[{name}]: unknown metaskill '{meta}'")
        for effect in list(spec.get("skills", {}).values()) + list(spec.get("metaskills", {}).values()):
            if float(effect.get("level", 0.0)) > 0 or not 0 < float(effect.get("learn", 1.0)) <= 1:
                errors.append(f"SKILL_LIMITATIONS[{name}]: a limitation must lower level and slow learning")
    for name, spec in LIMITATION_PREVALENCE.items():
        if name not in SKILL_LIMITATIONS:
            errors.append(f"LIMITATION_PREVALENCE[{name}]: no effects in SKILL_LIMITATIONS")
        for other in spec.get("given", {}):
            if other not in LIMITATION_PREVALENCE:
                errors.append(f"LIMITATION_PREVALENCE[{name}].given: unknown limitation '{other}'")
    for (a, b), value in SKILL_AFFINITY.items():
        if a not in SKILLS or b not in SKILLS:
            errors.append(f"SKILL_AFFINITY[{a}, {b}]: unknown skill")
        if not 0.0 < float(value) < 1.0:
            errors.append(f"SKILL_AFFINITY[{a}, {b}]: closeness {value} must be between 0 and 1")
        if (b, a) in SKILL_AFFINITY:
            errors.append(f"SKILL_AFFINITY[{a}, {b}]: listed in both directions")
    open_recipes = sorted(r["name"] for r in RECIPES if r.get("open"))
    info.append(f"open recipes (anyone capable with the tools): {', '.join(open_recipes)}")
    for name, spec in WASTE_CYCLES.items():
        ref(spec["output"], f"WASTE_CYCLES[{name}].output")
        if spec["treatment"] not in BUILDINGS and spec["treatment"] not in INFRASTRUCTURE:
            errors.append(f"WASTE_CYCLES[{name}]: unknown treatment place '{spec['treatment']}'")
    for kind in PASTURE_YIELDS:
        ref(kind, "PASTURE_YIELDS")
    for name, spec in FENCE_TYPES.items():
        if spec["material"] not in items:
            warnings.append(f"FENCE_TYPES[{name}]: material '{spec['material']}' is not an item")
    for name, spec in ENCLOSURE_TYPES.items():
        if spec["fence"] not in FENCE_TYPES:
            errors.append(f"ENCLOSURE_TYPES[{name}]: unknown fence '{spec['fence']}'")
    for kind in RESOURCE_DEPOSITS:
        ref(kind, "RESOURCE_DEPOSITS")
    for trade, chain in SHOP_CHAINS.items():
        ref(chain["in"], f"SHOP_CHAINS[{trade}].in")
        ref(chain["out"], f"SHOP_CHAINS[{trade}].out")
    for name, spec in FUEL_SOURCES.items():
        ref(spec["fuel"], f"FUEL_SOURCES[{name}]")
    for name, spec in SEASONS.items():
        for w in spec["weather"]:
            if w not in WEATHER:
                errors.append(f"SEASONS[{name}]: unknown weather '{w}'")

    # -- pipelines: sources, sinks, reachability ---------------------------------
    sources = _item_sources()
    made_by = {}
    for r in RECIPES:
        made_by.setdefault(r["out"][0], []).append(r["name"])
    uses = _item_uses()
    no_source = sorted(k for k in items if k not in sources and k not in made_by
                       and ITEMS[k].get("class") == "material")
    for kind in no_source:
        warnings.append(f"PIPELINE no source: '{kind}' (no recipe, crop, animal, deposit, import, "
                        f"or starting stock)")
    not_made = sorted(k for k in items if k not in sources and k not in made_by
                      and ITEMS[k].get("class") != "material")
    founding_tools = {t for r in RECIPES for t in r.get("tools", [])}
    for kind in not_made:
        if kind in founding_tools:
            warnings.append(f"PIPELINE cannot be made: {ITEMS[kind].get('class')} '{kind}' "
                            f"(one is provided at founding; it cannot be replaced)")
        else:
            warnings.append(f"PIPELINE cannot be made: {ITEMS[kind].get('class')} '{kind}' "
                            f"(not made, imported, or provided)")
    for kind in sorted(items - set(uses)):
        warnings.append(f"PIPELINE never used: '{kind}'")

    # Which recipes can run without someone stocking their inputs by hand (a test or scenario
    # set_stock)? Start from everything with a non-recipe source, plus the tools the
    # world provides at founding, then repeatedly add the outputs of recipes whose inputs are all
    # obtainable, until nothing changes.
    obtainable = set(sources) | founding_tools

    def can_get(kind):
        if is_input_type(kind):
            return any(member in obtainable for member, _ in type_members(kind))
        return kind in obtainable

    runnable = set()
    changed = True
    while changed:
        changed = False
        for r in RECIPES:
            if r["name"] in runnable:
                continue
            if all(can_get(k) for k, _ in r["in"]):
                runnable.add(r["name"])
                obtainable.add(r["out"][0])
                changed = True
    for r in RECIPES:
        if r["name"] not in runnable:
            missing = sorted(k for k, _ in r["in"] if not can_get(k))
            warnings.append(f"PIPELINE recipe unreachable from natural sources: '{r['name']}' -- "
                            f"no source for {', '.join(missing)}")

    # Seeds: a crop is only sustainable if its seed can be replaced after the first sowing.
    # Its own harvest cannot supply the first sowing, so a crop also needs some other first source.
    for crop, spec in CROPS.items():
        seed_src = sources.get(spec["seed"], set()) | ({"recipe"} if spec["seed"] in made_by else set())
        first = seed_src - {f"harvest of {crop}"}
        if not first:
            warnings.append(f"PIPELINE crop: '{crop}' can never be sown -- no first source of '{spec['seed']}'")
        if float(spec.get("seed_return", 1.0)) <= 0.0:
            warnings.append(f"PIPELINE crop: '{crop}' is not renewable -- its harvest returns no '{spec['seed']}'")

    # -- world mechanics parameters (Phase 014): the clock, starting state, care, prices, gates -----
    def _num(where, value, lo=None, hi=None):
        try:
            x = float(value)
        except (TypeError, ValueError):
            errors.append(f"{where}: '{value}' is not a number")
            return
        if (lo is not None and x < lo) or (hi is not None and x > hi):
            errors.append(f"{where}: {x} is outside [{lo}, {hi}]")

    clock = TIME
    _num("TIME: minutes_per_tick", clock["minutes_per_tick"], lo=1e-9)
    for key in ("ticks_per_day", "ticks_per_period", "days_per_week", "days_per_year"):
        if not isinstance(clock[key], int) or isinstance(clock[key], bool) or clock[key] < 1:
            errors.append(f"TIME: {key} must be a positive whole number, not {clock[key]!r}")
    _num("TIME: start_hour", clock["start_hour"], lo=0.0, hi=float(clock["hours_per_day"]) - 1e-9)
    starts = list(clock["season_start_day"].values())
    if set(clock["season_start_day"]) != set(SEASONS):
        errors.append(f"TIME: season_start_day names {sorted(clock['season_start_day'])} "
                      f"do not match SEASONS {sorted(SEASONS)}")
    elif starts[0] != 0 or starts != sorted(set(starts)) or starts[-1] >= clock["days_per_year"]:
        errors.append("TIME: season_start_day must begin at day 0, rise strictly, and stay inside days_per_year")
    town = TOWN_INITIAL
    if town.get("season") not in SEASONS:
        errors.append(f"TOWN_INITIAL: season '{town.get('season')}' is not a SEASONS key")
    elif town["season"] != next(iter(clock["season_start_day"])):
        errors.append(f"TOWN_INITIAL: season '{town['season']}' does not match the season of day 0")
    if town.get("weather") not in WEATHER:
        errors.append(f"TOWN_INITIAL: weather '{town.get('weather')}' is not a WEATHER key")
    if float(town.get("hour", -1)) != float(clock["start_hour"]):
        errors.append("TOWN_INITIAL: hour must equal TIME start_hour (the clock starts at tick 0)")

    actor = ACTOR_DEFAULTS
    if actor.get("station") not in STATION_EDUCATION:
        errors.append(f"ACTOR_DEFAULTS: station '{actor.get('station')}' is not a STATION_EDUCATION key")
    if actor.get("life_stage") not in LIFE_STAGES:
        errors.append(f"ACTOR_DEFAULTS: life_stage '{actor.get('life_stage')}' is not a LIFE_STAGES key")
    _num("ACTOR_DEFAULTS: skill", actor["skill"], 0.0, 1.0)
    _num("ACTOR_DEFAULTS: reputation", actor["reputation"], 0.0, 1.0)
    _num("ACTOR_DEFAULTS: health_value", actor["health_value"], 0.0, 1.0)
    _num("ACTOR_DEFAULTS: coin", actor["coin"], 0.0)
    _num("ACTOR_DEFAULTS: age", actor["age"], 0.0)
    _num("ACTOR_DEFAULTS: inventory_capacity", actor["inventory_capacity"], 1e-9)
    _num("ACTOR_DEFAULTS: inventory_max_load", actor["inventory_max_load"], 1e-9)

    for key in ("injury_severity", "treat_health_gain", "treat_health_base", "care_injury_relief",
                "care_health_gain", "daily_injury_recovery", "recovered_injury_below",
                "daily_health_recovery", "disease_health_loss"):
        _num(f"CARE: {key}", CARE[key], 0.0, 1.0)
    _num("CARE: starve_limit", CARE["starve_limit"], 1e-9)

    _num("PRICE_DEFAULTS: shop_price", PRICE_DEFAULTS["shop_price"], 1e-9)
    _num("PRICE_DEFAULTS: stock_price", PRICE_DEFAULTS["stock_price"], 0.0)
    _num("PRICE_DEFAULTS: labour_wage", PRICE_DEFAULTS["labour_wage"], 0.0)
    if PRICE_DEFAULTS["shop_is_open"] not in (0, 1):
        errors.append("PRICE_DEFAULTS: shop_is_open must be 0 or 1")

    for kind, tier in DOCUMENT_LITERACY.items():
        if kind not in ("policy", "law", "charter"):
            errors.append(f"DOCUMENT_LITERACY: '{kind}' is not a written document kind")
        if tier not in ("functional", "educated"):
            errors.append(f"DOCUMENT_LITERACY[{kind}]: '{tier}' is not a literacy tier")

    repo = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    seed_dirs = (_os.path.join(repo, "seeds"), _os.path.join(repo, "bigville", "seeds"))
    for table, ids in (("ENGINE_SEEDS", ENGINE_SEEDS), ("RESIDENT_SEEDS", RESIDENT_SEEDS),
                       ("RESIDENT_CONCEPT_SEEDS", RESIDENT_CONCEPT_SEEDS)):
        if len(set(ids)) != len(ids):
            errors.append(f"{table}: a seed id is listed twice")
        for sid in ids:
            if not any(_os.path.isfile(_os.path.join(d, f"{sid}.json")) for d in seed_dirs):
                errors.append(f"{table}: seed '{sid}' has no file in seeds/ or bigville/seeds/")

    relationship_specs = [(f"RELATIONSHIP_KINDS[{edge}]", spec) for edge, spec in RELATIONSHIP_KINDS.items()]
    relationship_specs.append(("RELATIONSHIP_DEFAULT", RELATIONSHIP_DEFAULT))
    for where, spec in relationship_specs:
        if not spec.get("kind"):
            errors.append(f"{where}: no kind of tie is named")
        _num(f"{where}: strength", spec.get("strength"), -1.0, 1.0)

    # Phase 015: households, registrar offices, labour worker roles, civic-action stages, policy parameters.
    if HOUSEHOLDS:
        fallbacks = [kind for kind, spec in HOUSEHOLDS.items() if spec.get("fallback")]
        if len(fallbacks) != 1:
            errors.append(f"HOUSEHOLDS: exactly one kind must be the fallback (found {len(fallbacks)})")
        claimed_roles, claimed_groups = {}, {}
        for kind, spec in HOUSEHOLDS.items():
            for role in spec.get("roles", []):
                if role in claimed_roles:
                    errors.append(f"HOUSEHOLDS[{kind}]: role '{role}' is also listed by HOUSEHOLDS[{claimed_roles[role]}]")
                claimed_roles[role] = kind
            for group in spec.get("groups", []):
                if group not in ("low", "middle", "high"):
                    errors.append(f"HOUSEHOLDS[{kind}].groups: '{group}' is not a cast group")
                if group in claimed_groups:
                    errors.append(f"HOUSEHOLDS[{kind}]: group '{group}' is also listed by HOUSEHOLDS[{claimed_groups[group]}]")
                claimed_groups[group] = kind
            for role in spec.get("land_roles", []):
                if role not in spec.get("roles", []):
                    errors.append(f"HOUSEHOLDS[{kind}].land_roles: '{role}' is not one of its roles")
    registrars = [role for role, spec in GOVERNANCE_OFFICES.items() if spec.get("registrar")]
    if GOVERNANCE_OFFICES and not registrars:
        errors.append("GOVERNANCE_OFFICES: no office is marked registrar, so the land register has no keeper")
    for role in registrars:
        if GOVERNANCE_OFFICES[role].get("authority") != "records":
            errors.append(f"GOVERNANCE_OFFICES[{role}]: a registrar must have authority 'records'")
    for role, spec in GOVERNANCE_OFFICES.items():
        for target in spec.get("appoints", []):
            if target not in GOVERNANCE_OFFICES:
                errors.append(f"GOVERNANCE_OFFICES[{role}].appoints: '{target}' is not an office")
    for task, spec in LABOUR_TASKS.items():
        if "worker_roles" in spec and not spec["worker_roles"]:
            errors.append(f"LABOUR_TASKS[{task}].worker_roles: empty (list the roles that do the task)")
    civic_actions = {"lawmaking": {"proposal", "meeting", "vote"}, "justice": {"case", "statement"}}
    for key, table, procedures in (("lawmaking", "LAWMAKING_PROCEDURES", LAWMAKING_PROCEDURES),
                                   ("justice", "JUSTICE_PROCEDURES", JUSTICE_PROCEDURES)):
        listed = {}
        for stage, spec in procedures.items():
            for action in spec.get("civic_actions", []):
                if action not in civic_actions[key]:
                    errors.append(f"{table}[{stage}].civic_actions: '{action}' is not a {key} civic action")
                elif action in listed:
                    errors.append(f"{table}[{stage}].civic_actions: '{action}' is also listed by stage '{listed[action]}'")
                listed[action] = stage
    for bundle in POLICIES:
        for key, value in dict(bundle.get("parameters", {})).items():
            _num(f"POLICIES[{bundle['name']}].parameters.{key}", value, 0.0)
    winter = next((bundle for bundle in POLICIES if bundle["name"] == "winter_food_reserve"), None)
    if winter is not None:
        for key in ("minimum_grain", "feed_periods"):
            if key not in winter.get("parameters", {}):
                errors.append(f"POLICIES[winter_food_reserve].parameters: '{key}' is missing (the village reserve reads it)")

    # Phase 009: kin terms, attribution, obligations, the inheritance custom, and the founding household
    # and genealogy draws checked against their cited figures.
    for term, spec in KIN_TERMS.items():
        rec = spec.get("reciprocal")
        if rec not in KIN_TERMS:
            errors.append(f"KIN_TERMS[{term}].reciprocal: '{rec}' is not a kin term")
        elif KIN_TERMS[rec].get("reciprocal") != term:
            errors.append(f"KIN_TERMS[{term}].reciprocal: '{rec}' does not name '{term}' back")
        if spec.get("sex") not in (None, "male", "female"):
            errors.append(f"KIN_TERMS[{term}].sex: '{spec.get('sex')}' is not male, female, or null")
        if not isinstance(spec.get("generation"), int):
            errors.append(f"KIN_TERMS[{term}].generation: must be an integer")
        if spec.get("shared_parents") not in (None, "both", "one"):
            errors.append(f"KIN_TERMS[{term}].shared_parents: must be 'both' or 'one'")
        for path in spec.get("paths", []):
            for token in path:
                if token not in ("parent", "child", "spouse", "sibling"):
                    errors.append(f"KIN_TERMS[{term}].paths: step '{token}' is not parent, child, spouse, or sibling")
        if not spec.get("paths") and not spec.get("attributions"):
            errors.append(f"KIN_TERMS[{term}]: no genealogical path and no attribution, so nothing can hold it")
        for ob in spec.get("obligations", []):
            if ob not in KIN_OBLIGATIONS:
                errors.append(f"KIN_TERMS[{term}].obligations: '{ob}' is not in KIN_OBLIGATIONS")
        for att in spec.get("attributions", []):
            if att not in KIN_ATTRIBUTION:
                errors.append(f"KIN_TERMS[{term}].attributions: '{att}' is not in KIN_ATTRIBUTION")
            elif term not in KIN_ATTRIBUTION[att]["terms"]:
                errors.append(f"KIN_TERMS[{term}].attributions: KIN_ATTRIBUTION[{att}] does not list '{term}'")
    for att, spec in KIN_ATTRIBUTION.items():
        for term in spec["terms"]:
            if term not in KIN_TERMS:
                errors.append(f"KIN_ATTRIBUTION[{att}].terms: '{term}' is not a kin term")
        for ob in spec["obligations"]:
            if ob not in KIN_OBLIGATIONS:
                errors.append(f"KIN_ATTRIBUTION[{att}].obligations: '{ob}' is not in KIN_OBLIGATIONS")
        if not isinstance(spec.get("inherits"), bool):
            errors.append(f"KIN_ATTRIBUTION[{att}].inherits: must be true or false")
    for name, spec in INHERITANCE_CUSTOM["customs"].items():
        if spec.get("spouse") not in ("share", "life_interest"):
            errors.append(f"INHERITANCE_CUSTOM[{name}].spouse: must be 'share' or 'life_interest'")
        if not spec.get("tiers"):
            errors.append(f"INHERITANCE_CUSTOM[{name}].tiers: empty, so no custom ever names an heir")
        for tier in spec.get("tiers", []):
            if tier.get("rule") not in ("equal", "eldest"):
                errors.append(f"INHERITANCE_CUSTOM[{name}].tiers: rule '{tier.get('rule')}' is not equal or eldest")
            for kind in tier.get("kinds", []):
                if kind not in ("child", "parent", "sibling"):
                    errors.append(f"INHERITANCE_CUSTOM[{name}].tiers: kind '{kind}' is not child, parent, or sibling")
    if INHERITANCE_CUSTOM["default"] not in INHERITANCE_CUSTOM["customs"]:
        errors.append(f"INHERITANCE_CUSTOM: default '{INHERITANCE_CUSTOM['default']}' is not a custom")
    for name, spec in KIN_OBLIGATIONS.items():
        if not spec.get("description") or not spec.get("source"):
            errors.append(f"KIN_OBLIGATIONS[{name}]: needs a description and a source (APPROX if unsourced)")
    if abs(sum(HOUSEHOLD_SIZE.values()) - 1.0) > 1e-6:
        errors.append(f"HOUSEHOLD_SIZE: shares sum to {sum(HOUSEHOLD_SIZE.values()):.4f}, not 1")
    if sorted(int(k) for k in HOUSEHOLD_SIZE) != list(range(1, len(HOUSEHOLD_SIZE) + 1)):
        errors.append("HOUSEHOLD_SIZE: sizes must run 1, 2, 3, ... without gaps")
    if abs(sum(EXTENDED_KIN.values()) - 1.0) > 1e-6:
        errors.append(f"EXTENDED_KIN: shares sum to {sum(EXTENDED_KIN.values()):.4f}, not 1")
    for key in ("EXTENDED_FAMILY",):
        _num(f"{key}", EXTENDED_FAMILY, 0.0, 1.0)
    for key, value in KIN_MODEL.items():
        if key not in ("CHILD_SPACING_YEARS", "SIBLING_MAX_GAP_YEARS"):
            _num(f"KIN_MODEL.{key}", value, 0.0, 1.0)
    _num("KIN_MODEL.CHILD_SPACING_YEARS", KIN_MODEL["CHILD_SPACING_YEARS"], 0.5)
    _num("KIN_MODEL.SIBLING_MAX_GAP_YEARS", KIN_MODEL["SIBLING_MAX_GAP_YEARS"], 0.0, 40.0)
    _num("INFANT_SURVIVAL", INFANT_SURVIVAL, 0.0, 1.0)
    kin_draw = describe_household_distribution(10000, seed=1)
    for key, label, measured in (("mean_size", "household size (mean members)", kin_draw["mean_size"]),
                                 ("extended_share", "extended-family share of households", kin_draw["extended_share"])):
        target = HOUSEHOLD_TARGETS[key]
        gap = abs(measured - float(target["value"]))
        line = (f"{label}: sample {measured:.3f} vs {float(target['value']):.3f} "
                f"(tolerance {float(target['tolerance']):.2f}; {target['source']})")
        if gap > float(target["tolerance"]):
            errors.append(f"HOUSEHOLD_TARGETS[{key}]: {line}")
        else:
            info.append(f"HOUSEHOLDS: {line}")
    if FOUNDING_AGE:
        kin_shape = describe_founding_kin(100, seed=305000)
        info.append(f"FOUNDING KIN (100 founders, ages from FOUNDING_AGE, the default town's seed): "
                    f"{kin_shape['with_parent_on_record']:.0%} have a parent on record, "
                    f"{kin_shape['in_a_union']:.0%} are in a union, "
                    f"{kin_shape['with_aunt_or_uncle']:.0%} have an aunt or uncle, "
                    f"{kin_shape['with_cousin']:.0%} have a first cousin; households with a co-resident spouse have "
                    f"{kin_shape['mean_children_with_spouse']:.1f} adult children in the household on average; "
                    f"{kin_shape['households']} households, mean {kin_shape['mean_members']:.2f} founders each "
                    f"(drawn size {kin_shape['mean_drawn_size']:.2f}), {kin_shape['extended_share']:.0%} extended "
                    f"(model shape; see population/household_composition.json)")

    _check_founding_town(errors, warnings, info)
    _check_knowledge(errors, warnings, info)
    stats = {
        "items": len(items), "recipes": len(RECIPES), "runnable_recipes": len(runnable),
        "buildings": len(BUILDINGS), "founding_buildings": len(founding_buildings()),
        "trades": len(TRADES), "crops": len(CROPS), "animals": len(ANIMALS),
        "containers": len(CONTAINERS),
        "items_by_class": {c: sum(1 for s in ITEMS.values() if s.get("class") == c)
                           for c in sorted({s.get("class", "?") for s in ITEMS.values()})},
    }
    return {"errors": errors, "warnings": warnings, "info": info, "stats": stats}

# ---------------------------------------------------------------------------
# PRODUCTION GRAPH, SYSTEMS, AND BALANCE
# ---------------------------------------------------------------------------
# The production graph links every item to the recipes and natural processes (crops, animals,
# deposits, imports, residents, fertilising) that consume and make it. Its cycles (seed -> crop ->
# seed, the nitrogen loop, tools that make tools) are collapsed into strongly connected components,
# leaving a DAG whose depth ("tier") says how many production steps an item sits above raw nature.
# The balance model (world_affordances._balance_flows) runs the founding town's per-period flows
# (population.BALANCE_SCENARIO) through that graph and flags systems that cannot sustain themselves.
_PSEUDO = {"soil_nitrogen", "food"}           # graph nodes that are not items


def _processes():
    """Natural and institutional flows, as recipe-shaped rows: {name, system, in, out}."""
    procs = []
    for crop, spec in CROPS.items():
        outs = [[spec["harvest"], spec["yield"]]] + [[k, q] for k, q in spec.get("byproducts", {}).items()]
        outs.append([spec["seed"], float(spec.get("seed_return", 1.0))])
        ins = [[spec["seed"], 1]]
        grow = float(spec["grow_periods"])
        if spec.get("nitrogen"):
            ins.append(["soil_nitrogen", float(spec["nitrogen"]) * grow])
        if spec.get("fixes"):
            outs.append(["soil_nitrogen", float(spec["fixes"]) * grow])
        procs.append({"name": f"crop:{crop}", "system": "agriculture", "in": ins, "out": outs})
    for species, spec in ANIMALS.items():
        outs = [[k, q] for k, q in spec.get("gives", {}).items() if k in ITEMS]
        if spec.get("manure"):
            outs.append(["manure", spec["manure"]])
        procs.append({"name": f"animal:{species}", "system": "husbandry",
                      "in": [[k, spec.get("ration", 1)] for k in feed_kinds(spec["eats"])[:1]], "out": outs})
    for kind, spec in RESOURCE_DEPOSITS.items():
        procs.append({"name": f"deposit:{kind}", "system": "extraction", "in": [], "out": [[kind, spec["growback"]]]})
    for kind, spec in PASTURE_YIELDS.items():
        procs.append({"name": f"pasture:{kind}", "system": "husbandry", "in": [], "out": [[kind, spec]]})
    for kind, spec in ITEMS.items():
        if spec.get("imported"):
            procs.append({"name": f"import:{kind}", "system": "trade", "in": [["coin", scarcity(kind)]], "out": [[kind, 1]]})
    if "human_waste" in WASTE_CYCLES:   # a pack without a waste cycle has no residents' waste process
        procs.append({"name": "residents", "system": "household", "in": [["food", 1]],
                      "out": [[WASTE_CYCLES["human_waste"]["output"], WASTE_CYCLES["human_waste"]["per_resident"]]]})
    procs.append({"name": "fertilise", "system": "agriculture",
                  "in": [[NITROGEN["fertiliser_type"], 1]], "out": [["soil_nitrogen", 1]]})
    return procs


def build_production_graph():
    """{node: set(successors)} over item/type/recipe/process nodes, plus each node's kind label."""
    succ, kind_of = {}, {}

    def node(name, label):
        succ.setdefault(name, set())
        kind_of[name] = label
        return name

    def item_node(kind):
        if is_input_type(kind):
            t = node(f"type:{kind}", "type")
            for member, _ in type_members(kind):
                succ[node(f"item:{member}", "item")].add(t)
            return t
        if kind == "food":
            t = node("type:food", "type")
            for k, s in ITEMS.items():
                if s.get("food"):
                    succ[node(f"item:{k}", "item")].add(t)
            return t
        return node(f"item:{kind}", "pseudo" if kind in _PSEUDO else "item")

    # recipe rows carry one [kind, qty] output; normalise to the process shape (a list of outputs)
    rows = [dict(r, system=SYSTEM_OF_TRADE.get(r["requires"], "other"), name=f"recipe:{r['name']}",
                 out=[r["out"]] + [[k, q] for k, q in r.get("byproducts", {}).items()])
            for r in RECIPES] + _processes()
    for r in rows:
        step = node(r["name"], "recipe" if r["name"].startswith("recipe:") else "process")
        for kind, _ in r["in"]:
            succ[item_node(kind)].add(step)
        for kind, _ in r["out"]:
            succ[step].add(item_node(kind))
        for kind, _ in r["in"]:
            if is_input_type(kind):
                for left in INPUT_TYPES[kind].get("byproducts", {}):
                    succ[step].add(item_node(left))
    return succ, kind_of, rows


def _strongly_connected(succ):
    """Tarjan's algorithm (iterative). Returns a list of components (sets of nodes)."""
    index, low, on, stack, comps, counter = {}, {}, set(), [], [], [0]
    for root in sorted(succ):
        if root in index:
            continue
        work = [(root, iter(sorted(succ[root])))]
        index[root] = low[root] = counter[0]; counter[0] += 1
        stack.append(root); on.add(root)
        while work:
            v, children = work[-1]
            advanced = False
            for w in children:
                if w not in index:
                    index[w] = low[w] = counter[0]; counter[0] += 1
                    stack.append(w); on.add(w)
                    work.append((w, iter(sorted(succ.get(w, ())))))
                    advanced = True
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp = set()
                while True:
                    w = stack.pop(); on.discard(w); comp.add(w)
                    if w == v:
                        break
                comps.append(comp)
    return comps


def analyse_systems():
    """Build the production DAG, weigh items and systems, and find balance issues.

    Returns {"graph": {...}, "loops": [...], "deepest": [...], "keystones": [...],
             "systems": {...}, "coupling": [...], "flows": {...}, "issues": [...], "notes": [...]}."""
    succ, kind_of, rows = build_production_graph()
    comps = _strongly_connected(succ)
    comp_of = {n: i for i, c in enumerate(comps) for n in c}
    dag = {i: set() for i in range(len(comps))}
    for v, ws in succ.items():
        for w in ws:
            if comp_of[v] != comp_of[w]:
                dag[comp_of[v]].add(comp_of[w])
    preds = {i: set() for i in dag}
    for v, ws in dag.items():
        for w in ws:
            preds[w].add(v)
    # tier = longest path from a source component (Kahn order)
    tier, order, indeg = {}, [], {i: len(preds[i]) for i in dag}
    ready = sorted(i for i, d in indeg.items() if d == 0)
    while ready:
        v = ready.pop(0); order.append(v)
        tier[v] = max((tier[p] + 1 for p in preds[v]), default=0)
        for w in sorted(dag[v]):
            indeg[w] -= 1
            if indeg[w] == 0:
                ready.append(w)
    acyclic = len(order) == len(dag)

    def items_in(comp):
        return sorted(n.split(":", 1)[1] for n in comp if kind_of[n] in ("item", "pseudo"))

    loops = []
    for i, c in enumerate(comps):
        if len(c) > 1:
            members = items_in(c)
            steps = sorted(n for n in c if kind_of[n] in ("recipe", "process"))
            loops.append({"items": members, "steps": len(steps), "size": len(c), "component": i})
    loops.sort(key=lambda l: -l["size"])
    loop_label = {l["component"]: f"[loop {n + 1}: {len(l['items'])} items]" for n, l in enumerate(loops)}

    def label(c):
        if c in loop_label:
            return loop_label[c]
        names = items_in(comps[c])
        return names[0] if names else None

    # depth: items ranked by tier, with one longest chain back to a source
    item_tier = {n.split(":", 1)[1]: tier[comp_of[n]] for n in succ if kind_of[n] == "item"}
    deepest = []
    for kind in sorted(item_tier, key=lambda k: (-item_tier[k], k))[:5]:
        c = comp_of[f"item:{kind}"]
        chain = [label(c)]
        while preds[c]:
            c = max(preds[c], key=lambda p: (tier[p], -p))
            name = label(c)
            if name and name != chain[-1]:
                chain.append(name)
        deepest.append({"item": kind, "tier": item_tier[kind], "chain": list(reversed(chain))})

    # keystones: how many recipes become unreachable if one item vanished from the world
    sources = _item_sources()
    base = set(sources) | {t for r in RECIPES for t in r.get("tools", [])}

    def reachable(removed):
        have = set(base) - {removed}
        ran, changed = set(), True
        while changed:
            changed = False
            for r in RECIPES:
                if r["name"] in ran or r["out"][0] == removed:
                    continue
                if all((any(m in have for m, _ in type_members(k)) if is_input_type(k) else k in have)
                       for k, _ in r["in"]):
                    ran.add(r["name"]); have.add(r["out"][0]); changed = True
        return ran

    everything = reachable(None)
    keystones = []
    for kind in sorted(ITEMS):
        lost = len(everything) - len(reachable(kind))
        if lost:
            keystones.append((kind, lost))
    keystones.sort(key=lambda kv: (-kv[1], kv[0]))

    # systems: size, value made per batch, labour; and which systems feed which
    systems, producer_system = {}, {}
    for r in rows:
        if not r["name"].startswith("recipe:"):
            for k, _ in r["out"]:
                producer_system.setdefault(k, set()).add(r["system"])
    for r in RECIPES:
        sysname = SYSTEM_OF_TRADE.get(r["requires"], "other")
        s = systems.setdefault(sysname, {"recipes": 0, "value": 0.0, "labour": 0.0})
        s["recipes"] += 1
        s["value"] += reference_value(r["out"][0]) * float(r["out"][1])
        s["labour"] += float(r.get("time_minutes", 0.0))
        producer_system.setdefault(r["out"][0], set()).add(sysname)
    coupling = {}
    for r in RECIPES:
        sysname = SYSTEM_OF_TRADE.get(r["requires"], "other")
        for k, q in r["in"]:
            kinds = [m for m, _ in type_members(k)] if is_input_type(k) else [k]
            for kk in kinds[:1]:
                for src in producer_system.get(kk, ()):
                    if src != sysname:
                        weight = (reference_value(kk) * float(q)) if not is_input_type(k) else float(q)
                        coupling[(src, sysname)] = coupling.get((src, sysname), 0.0) + weight
    coupling = sorted(((a, b, round(w, 2)) for (a, b), w in coupling.items()), key=lambda t: -t[2])

    # balance issues
    flows, notes, _work = _balance_flows(BALANCE_SCENARIO)
    issues = []
    for name, (supply, demand) in flows.items():
        if demand <= 0:
            continue
        ratio = supply / demand
        if ratio < 1.0:
            issues.append(f"DEFICIT {name}: supply {supply:.1f} vs demand {demand:.1f} per period "
                          f"({ratio:.0%} covered)")
        elif ratio < 1.15:
            issues.append(f"TIGHT {name}: supply {supply:.1f} vs demand {demand:.1f} per period "
                          f"(only {ratio - 1:.0%} margin)")
        elif ratio > 6.0 and name in ("fuel (heat)", "soil nitrogen", "water"):
            issues.append(f"GLUT {name}: supply {supply:.1f} vs demand {demand:.1f} per period "
                          f"({ratio:.1f}x -- the constraint may be too loose to matter)")
    for crop, spec in CROPS.items():
        if float(spec.get("seed_return", 1.0)) <= 1.0 and crop in BALANCE_SCENARIO.get("beds", {}):
            issues.append(f"BREAK-EVEN seed for {crop}: a harvest returns {spec.get('seed_return', 1.0)} seed per "
                          f"seed sown, so every bed lost to wilting shrinks the seed stock for good")
    # recipes that cost much more than the cheapest way to make the same thing
    for r in RECIPES:
        out, oq = r["out"]
        per = _recipe_unit_cost(r)
        ref = reference_value(out)
        if ref > 0 and per > 1.5 * ref and len(_recipes_for(out)) > 1 and not r.get("fallback"):
            issues.append(f"DOMINATED recipe {r['name']}: {per:.2f}/unit vs {ref:.2f} by the cheapest recipe "
                          f"for {out}")
    for kind, spec in ITEMS.items():
        if spec.get("imported") and _recipes_for(kind):
            m, l = _value_parts(kind)
            if m + l * LABOUR_RATE < scarcity(kind) * 0.5:
                issues.append(f"IMPORT {kind}: making it locally ({m + l * LABOUR_RATE:.2f}) costs under half "
                              f"the import price ({scarcity(kind):.2f}) -- the import is unlikely to be used")
    return {"graph": {"nodes": len(succ), "edges": sum(len(v) for v in succ.values()),
                      "components": len(comps), "tiers": max(tier.values(), default=0) + 1,
                      "acyclic_after_condensing": acyclic},
            "loops": loops, "deepest": deepest, "keystones": keystones[:10],
            "systems": systems, "coupling": coupling[:12], "flows": flows,
            "issues": issues, "notes": notes}


def format_systems_report(analysis=None):
    """Render analyse_systems() as text."""
    a = analysis or analyse_systems()
    g = a["graph"]
    lines = ["PRODUCTION GRAPH",
             f"  {g['nodes']} nodes, {g['edges']} edges -> {g['components']} components; "
             f"{g['tiers']} tiers deep; acyclic after condensing loops: {g['acyclic_after_condensing']}",
             f"  loops ({len(a['loops'])}; a loop is a cycle such as seed -> crop -> seed):"]
    for loop in a["loops"][:6]:
        shown = ", ".join(loop["items"][:12]) + (" ..." if len(loop["items"]) > 12 else "")
        lines.append(f"    - {len(loop['items'])} items / {loop['steps']} steps: {shown}")
    if len(a["loops"]) > 6:
        lines.append(f"    - ... and {len(a['loops']) - 6} smaller loops")
    lines.append("  deepest items (tier: one chain from raw nature):")
    for d in a["deepest"]:
        lines.append(f"    - {d['item']} (tier {d['tier']}): {' -> '.join(d['chain'])}")
    lines.append("  keystone items (recipes that become unreachable without them):")
    lines.append("    " + ", ".join(f"{k} {n}" for k, n in a["keystones"]))
    lines += ["", "SYSTEMS (recipes, reference value made per batch, labour minutes per batch)"]
    total_v = sum(s["value"] for s in a["systems"].values()) or 1.0
    for name, s in sorted(a["systems"].items(), key=lambda kv: -kv[1]["value"]):
        lines.append(f"  {name:<12} {s['recipes']:>3} recipes  value {s['value']:>8.1f} "
                     f"({s['value'] / total_v:>4.0%})  labour {s['labour']:>6.0f}")
    lines.append("  strongest couplings (producer -> consumer: weight of inputs crossing):")
    for src, dst, w in a["coupling"]:
        lines.append(f"    {src} -> {dst}: {w}")
    lines += ["", "BALANCE (per period, BALANCE_SCENARIO)"]
    for name, (supply, demand) in a["flows"].items():
        ratio = supply / demand if demand else float("inf")
        lines.append(f"  {name:<18} supply {supply:>8.1f}  demand {demand:>8.1f}  ratio {ratio:>5.2f}")
    for note in a["notes"]:
        lines.append(f"  note: {note}")
    lines.append(f"  issues ({len(a['issues'])}):")
    lines.extend(f"    - {issue}" for issue in a["issues"]) if a["issues"] else lines.append("    none")
    return "\n".join(lines)


def format_capacity_report(n=10000):
    """Summarise drawn capacities against the published prevalence each is set from."""
    lines = [f"PEOPLE (aptitude, talents, limitations drawn for {n} adults; target = source rate)"]
    for age in (35.0, 75.0):
        d = describe_capacity_distribution(n, age=age)
        lines.append(f"  age {age:.0f}: aptitude mean {d['aptitude_mean']:.3f} (2nd-98th pct "
                     f"{d['aptitude_p02']:.2f}-{d['aptitude_p98']:.2f}); "
                     f"{d['any_limitation']:.0%} have at least one limitation")
        def expected(name):
            """Population rate, both sexes, including any raised rate given a comorbid condition."""
            base = (limitation_rate(name, age=age, sex="male") + limitation_rate(name, age=age, sex="female")) / 2
            for other, conditional in LIMITATION_PREVALENCE[name].get("given", {}).items():
                q = expected(other)
                base = (1 - q) * base + q * max(base, float(conditional))
            return base

        for name, rate in d["limitation_rates"].items():
            target = expected(name)
            lines.append(f"    {name:<36} {rate:>6.1%}   target {target:>6.1%}")
    return "\n".join(lines)


def format_consistency_report(report=None):
    """Render check_consistency() as readable text, warnings grouped by their table/area."""
    report = report or check_consistency()
    s = report["stats"]
    lines = ["bigville entities -- consistency report", "=" * 40,
             f"items {s['items']}  recipes {s['recipes']} ({s['runnable_recipes']} runnable)  "
             f"buildings {s['buildings']} ({s['founding_buildings']} at founding)  trades {s['trades']}",
             f"crops {s['crops']}  animals {s['animals']}  containers {s['containers']}",
             "items by class: " + ", ".join(f"{c} {n}" for c, n in s["items_by_class"].items()), ""]
    for title, key in (("ERRORS", "errors"), ("WARNINGS", "warnings"), ("INFO", "info")):
        msgs = report[key]
        lines.append(f"{title} ({len(msgs)})")
        groups = {}
        for m in msgs:
            groups.setdefault(m.split(":", 1)[0].split("[", 1)[0], []).append(m)
        for group in sorted(groups):
            lines.append(f"  {group} ({len(groups[group])})")
            for m in groups[group]:
                # pipeline groups name the problem; the entry is just the subject
                lines.append(f"    - {m.split(':', 1)[1].strip() if m.startswith('PIPELINE') else m}")
        if not msgs:
            lines.append("  none")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys as _sys
    _report = check_consistency()
    print(format_consistency_report(_report))
    print(format_systems_report(analyse_systems()))
    print()
    print(format_jobs_report())
    print()
    print(format_capacity_report())
    _sys.exit(1 if _report["errors"] else 0)
