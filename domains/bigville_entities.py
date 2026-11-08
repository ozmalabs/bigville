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
from domains.world_affordances import _PACK as _WORLD_PACK   # noqa: E402  which pack this view reads
from domains import daynight_check as _daynight_check   # noqa: E402  Phase 042
from domains import generated_seeds as _generated_seeds      # noqa: E402  Phase 017
from domains.world_affordances import (  # noqa: E402
    _balance_flows,
    _recipe_unit_cost,
    _recipes_for,
    _value_parts,
    protein_balance,
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


def _check_gathering_sites(errors, warnings, info):
    """Phase 004: each gathering recipe names a site the pack has, each site is a sane renewable stock, and
    each site has an anchor on the founding map."""
    W, H = FOUNDING_MAP.get("width"), FOUNDING_MAP.get("height")
    gathering = {r["name"]: r for r in RECIPES if r.get("gathered_from")}
    used = {r["gathered_from"] for r in gathering.values()}
    for name, r in gathering.items():
        kind = r["gathered_from"]
        if kind not in GATHERING_SITES:
            errors.append(f"RECIPES[{name}].gathered_from: '{kind}' is not a GATHERING_SITES kind")
            continue
        if r["in"]:
            errors.append(f"RECIPES[{name}]: a gathering recipe takes no inputs, but it has {len(r['in'])}")
        if float(r["out"][1]) > float(GATHERING_SITES[kind]["capacity"]):
            warnings.append(f"RECIPES[{name}]: one batch ({r['out'][1]}) exceeds the {kind} site's capacity, "
                            f"so the site can never supply it")
    for kind, spec in GATHERING_SITES.items():
        where = f"GATHERING_SITES[{kind}]"
        stock, growback, capacity = (float(spec.get(k, -1.0)) for k in ("stock", "growback", "capacity"))
        if capacity <= 0.0:
            errors.append(f"{where}: capacity must be above zero")
        if not 0.0 <= stock <= capacity:
            errors.append(f"{where}: stock must be between 0 and capacity")
        if growback < 0.0:
            errors.append(f"{where}: growback must be zero or more")
        if kind not in used:
            warnings.append(f"{where}: no gathering recipe names this site")
        anchor = spec.get("anchor")
        if not (isinstance(anchor, list) and len(anchor) == 2):
            errors.append(f"{where}: anchor must be a cell [x, y]")
        elif not FOUNDING_MAP:
            info.append(f"{where}: this pack has no founding map, so no site is placed")
        elif not (0 <= anchor[0] < W and 0 <= anchor[1] < H):
            errors.append(f"{where}: anchor {anchor} is off the founding map")


def _check_burial(errors, warnings, info):
    """Phase 010: the graveyard, the dig and bury recipes, and the BURIAL rules. A pack with no BURIAL entries
    has no graveyard and no burial recipe, and this check then has nothing to say."""
    if not BURIAL:
        return
    place = BURIAL.get("place")
    if place not in BUILDINGS:
        errors.append(f"BURIAL.place: '{place}' is not a BUILDINGS kind")
    elif place not in FOUNDING_BUILDING_SITES:
        errors.append(f"BURIAL.place: '{place}' has no FOUNDING_BUILDING_SITES origin, so it does not stand at founding")
    for key in ("body_weight",):
        if float(BURIAL.get(key, 0.0)) <= 0.0:
            errors.append(f"BURIAL.{key}: must be above zero")
    if int(BURIAL.get("risk_after_periods", 0)) != BURIAL.get("risk_after_periods", 0) \
            or int(BURIAL.get("risk_after_periods", 0)) < 1:
        errors.append("BURIAL.risk_after_periods: must be a whole number of periods, at least 1")
    if not 0.0 <= float(BURIAL.get("onset_chance", -1.0)) <= 1.0:
        errors.append("BURIAL.onset_chance: must be between 0 and 1")
    if BURIAL.get("condition") not in HEALTH_CONDITIONS or BURIAL.get("condition") == "healthy":
        errors.append(f"BURIAL.condition: '{BURIAL.get('condition')}' is not an illness in HEALTH_CONDITIONS")
    by_burial = {}
    for r in RECIPES:
        if r.get("burial") is None and r.get("at_building") is None:
            continue
        where = f"RECIPES[{r['name']}]"
        if r.get("burial") not in ("dig", "bury"):
            errors.append(f"{where}.burial: must be 'dig' or 'bury' (got {r.get('burial')!r})")
            continue
        by_burial.setdefault(r["burial"], []).append(r["name"])
        if r.get("at_building") != place:
            errors.append(f"{where}.at_building: a burial recipe works at '{place}' (got {r.get('at_building')!r})")
        if not r.get("open"):
            errors.append(f"{where}: a burial recipe is an open recipe, so anyone may do it")
    for kind in ("dig", "bury"):
        if len(by_burial.get(kind, [])) != 1:
            errors.append(f"BURIAL: exactly one recipe must have burial: '{kind}' "
                          f"(found {by_burial.get(kind, [])})")
    for name in by_burial.get("dig", []):
        r = next(x for x in RECIPES if x["name"] == name)
        if "spade" not in r.get("tools", []):
            errors.append(f"RECIPES[{name}]: digging a grave needs a spade")
    for name in by_burial.get("bury", []):
        r = next(x for x in RECIPES if x["name"] == name)
        if not r["in"]:
            warnings.append(f"RECIPES[{name}]: a burial with no backfill input")
    info.append(f"BURIAL: graveyard '{place}', body weight {BURIAL.get('body_weight')}, unburied risk after "
                f"{BURIAL.get('risk_after_periods')} periods at {BURIAL.get('onset_chance')} a dawn")


def _check_refusal_reasons(errors, warnings, info):
    """Phase 021: the refusal reason table. Codes are snake_case words, each has a description for the
    resident's prompt, and the per-resident refusal log keeps a whole number of entries, at least 1."""
    import re as _re
    for code, spec in REFUSAL_REASONS.items():
        if not _re.fullmatch(r"[a-z]+(_[a-z]+)*", str(code)):
            errors.append(f"REFUSAL_REASONS[{code!r}]: a reason code is a snake_case word")
        if not str(spec.get("description", "")).strip():
            errors.append(f"REFUSAL_REASONS[{code}]: no description (the resident's prompt quotes it)")
    if "not_possible" not in REFUSAL_REASONS:
        errors.append("REFUSAL_REASONS: needs the 'not_possible' catch-all")
    if isinstance(REFUSAL_LOG_LIMIT, bool) or not isinstance(REFUSAL_LOG_LIMIT, int) or REFUSAL_LOG_LIMIT < 1:
        errors.append(f"REFUSAL_LOG_LIMIT: must be a whole number of at least 1, not {REFUSAL_LOG_LIMIT!r}")
    for code in ("asleep", "collapsed"):
        if code not in REFUSAL_REASONS:
            errors.append(f"REFUSAL_REASONS: needs the exhaustion code {code!r} (Phase 024)")


def _check_handovers(errors, warnings, info):
    """Phase 026: the handover kinds and endpoint kinds the world records. Each kind is a snake_case word with
    a description, the endpoint kinds a Handover can name are all described, and the log keeps a whole number
    of Handover facts, at least 1."""
    import re as _re
    for kind, spec in HANDOVER_KINDS.items():
        if not _re.fullmatch(r"[a-z]+(_[a-z]+)*", str(kind)):
            errors.append(f"HANDOVER_KINDS[{kind!r}]: a handover kind is a snake_case word")
        if not str(spec.get("description", "")).strip():
            errors.append(f"HANDOVER_KINDS[{kind}]: no description")
    for endpoint in ("actor", "purse", "container", "store", "merchant"):
        if endpoint not in HANDOVER_ENDPOINTS:
            errors.append(f"HANDOVER_ENDPOINTS: needs the endpoint kind {endpoint!r}")
    for endpoint, spec in HANDOVER_ENDPOINTS.items():
        if not str(spec.get("description", "")).strip():
            errors.append(f"HANDOVER_ENDPOINTS[{endpoint}]: no description")
    if isinstance(HANDOVER_LOG_LIMIT, bool) or not isinstance(HANDOVER_LOG_LIMIT, int) or HANDOVER_LOG_LIMIT < 1:
        errors.append(f"HANDOVER_LOG_LIMIT: must be a whole number of at least 1, not {HANDOVER_LOG_LIMIT!r}")


def _check_locks(errors, warnings, info):
    """Phase 030: keys and the town store's founding lock (packs/*/world/locks.json). The key kind is a snake_case
    word that is not a bulk good, its weight is positive, the store lock names a whole-number lock id of at least 1,
    starts unlocked or locked as a flag, and needs a whole number of keyholders of at least 1. The refusal codes the
    lock and unlock actions use, and both actions, must exist with descriptions."""
    import re as _re
    if not _re.fullmatch(r"[a-z]+(_[a-z]+)*", str(KEY_KIND)):
        errors.append(f"KEY_KIND: a key kind is a snake_case word, not {KEY_KIND!r}")
    if KEY_KIND in ITEMS:
        errors.append(f"KEY_KIND: {KEY_KIND!r} is a bulk good in ITEMS; keys are discrete items")
    if isinstance(KEY_WEIGHT, bool) or not isinstance(KEY_WEIGHT, (int, float)) or KEY_WEIGHT <= 0:
        errors.append(f"KEY_WEIGHT: must be a positive number, not {KEY_WEIGHT!r}")
    lock_id = STORE_LOCK.get("lock_id")
    if isinstance(lock_id, bool) or not isinstance(lock_id, int) or lock_id < 1:
        errors.append(f"STORE_LOCK: lock_id must be a whole number of at least 1, not {lock_id!r}")
    if not isinstance(STORE_LOCK.get("locked"), bool):
        errors.append(f"STORE_LOCK: locked must be true or false, not {STORE_LOCK.get('locked')!r}")
    keys = STORE_LOCK.get("keys_required")
    if isinstance(keys, bool) or not isinstance(keys, int) or keys < 1:
        errors.append(f"STORE_LOCK: keys_required must be a whole number of at least 1, not {keys!r}")
    for code in ("no_lock", "no_key", "already_locked", "already_unlocked", "already_authorised", "store_locked",
                 "container_locked"):
        if code not in REFUSAL_REASONS:
            errors.append(f"REFUSAL_REASONS: needs the lock code {code!r} (Phase 030)")
    for action in ("lock", "unlock"):
        if action not in MAJOR_ACTIONS or not str(MAJOR_ACTIONS[action].get("description", "")).strip():
            errors.append(f"MAJOR_ACTIONS: needs {action!r} with a description (Phase 030)")


def _check_coin_storage(errors, warnings, info):
    """Phase 041: coin stored in containers and purses. COIN_WEIGHT and COIN_VOLUME (packs/*/world/containers.json)
    are numbers of at least 0. Coin is an item kind (ITEMS) so a container's coin pile has a kind. The codes that
    a coin move can refuse with must exist in REFUSAL_REASONS."""
    for name, value in (("COIN_WEIGHT", COIN_WEIGHT), ("COIN_VOLUME", COIN_VOLUME)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            errors.append(f"{name}: must be a number of at least 0, not {value!r} (Phase 041)")
    if "coin" not in ITEMS:
        errors.append("ITEMS: 'coin' is needed for coin stored in containers (Phase 041)")
    for code in ("full", "container_locked", "out_of_stock", "not_in_reach", "unknown_target", "malformed",
                 "slot_used"):
        if code not in REFUSAL_REASONS:
            errors.append(f"REFUSAL_REASONS: needs the coin code {code!r} (Phase 041)")


def _check_doors(errors, warnings, info):
    """Phase 039: a building's door (BUILDINGS[...].door, one per building). The lock is a whole-number lock_id of at
    least 1 that no other door shares and that differs from the store's, so one key opens one lock; `locked` is a
    flag; keys_required is a whole number of at least 1; lock_strength is positive (Phase 050). An entrance, when
    named, is an offset [dx, dy] inside the footprint on its perimeter, so a crossing can be made there. The
    refusal code door_locked exists with a description (both packs)."""
    seen = {}
    allowed = {"lock_id", "locked", "keys_required", "lock_strength", "entrance"}
    for name, spec in BUILDINGS.items():
        door = spec.get("door")
        if door is None:
            continue
        where = f"BUILDINGS[{name}].door"
        if not isinstance(door, dict) or set(door) - allowed:
            errors.append(f"{where}: must be an object with only {sorted(allowed)}")
            continue
        lock_id = door.get("lock_id")
        if isinstance(lock_id, bool) or not isinstance(lock_id, int) or lock_id < 1:
            errors.append(f"{where}: lock_id must be a whole number of at least 1, not {lock_id!r}")
        elif lock_id == STORE_LOCK["lock_id"] or lock_id in seen:
            errors.append(f"{where}: lock_id {lock_id} is shared with {seen.get(lock_id, 'the town store')}; "
                          "one key must open one lock")
        else:
            seen[lock_id] = name
        if not isinstance(door.get("locked"), bool):
            errors.append(f"{where}: locked must be true or false, not {door.get('locked')!r}")
        keys = door.get("keys_required", 1)
        if isinstance(keys, bool) or not isinstance(keys, int) or keys < 1:
            errors.append(f"{where}: keys_required must be a whole number of at least 1, not {keys!r}")
        strength = door.get("lock_strength")
        if isinstance(strength, bool) or not isinstance(strength, (int, float)) or strength <= 0:
            errors.append(f"{where}: lock_strength must be a positive number, not {strength!r}")
        if "entrance" in door:
            footprint = spec.get("footprint", spec.get("size", (3, 3)))
            if isinstance(footprint, (int, float)):
                footprint = (int(footprint), int(footprint))
            width, height = int(footprint[0]), int(footprint[1])
            entrance = door["entrance"]
            if (not isinstance(entrance, (list, tuple)) or len(entrance) != 2
                    or any(isinstance(v, bool) or not isinstance(v, int) for v in entrance)):
                errors.append(f"{where}: entrance must be an [dx, dy] offset, not {entrance!r}")
            else:
                dx, dy = entrance
                inside = 0 <= dx < width and 0 <= dy < height
                if not inside or not (dx in (0, width - 1) or dy in (0, height - 1)):
                    errors.append(f"{where}: entrance {entrance} is not on the perimeter of the "
                                  f"{width}x{height} footprint")
    if "door_locked" not in REFUSAL_REASONS or not str(REFUSAL_REASONS["door_locked"].get("description", "")).strip():
        errors.append("REFUSAL_REASONS: needs the door code 'door_locked' with a description (Phase 039)")
    info.append(f"DOORS: {len(seen)} building door(s)")


def _check_hearing(errors, warnings, info):
    """Phase 028: the speech and sight figures (packs/*/world/hearing.json). Radii are cells and at least 0;
    the normal loudness is the floor of a chosen loudness and sits within the clamp; the sight range is a
    whole number of cells at least 1; occluders are terrain names the map has. A radius of 0 is allowed (touch
    only), a sight range of 0 is not (nobody could witness)."""
    h = HEARING
    required = {"flat_radius", "normal_loudness", "max_loudness", "sight_range", "sight_occluders",
                "hear_occluders"}
    missing = sorted(required - set(h))
    if missing:
        errors.append(f"HEARING: missing {missing}")
        return
    for name in ("flat_radius", "normal_loudness", "max_loudness"):
        value = h[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            errors.append(f"HEARING[{name}]: a non-negative number, not {value!r}")
    numeric = all(isinstance(h[n], (int, float)) and not isinstance(h[n], bool)
                  for n in ("normal_loudness", "max_loudness"))
    if numeric and h["normal_loudness"] > h["max_loudness"]:
        errors.append(f"HEARING: normal_loudness {h['normal_loudness']} is above max_loudness {h['max_loudness']}")
    sight = h["sight_range"]
    if isinstance(sight, bool) or not isinstance(sight, int) or sight < 1:
        errors.append(f"HEARING[sight_range]: a whole number of cells of at least 1, not {sight!r}")
    terrain_names = set(TERRAIN_MOVEMENT)
    for channel in ("sight_occluders", "hear_occluders"):
        names = h[channel]
        if not isinstance(names, list):
            errors.append(f"HEARING[{channel}]: a list of terrain names")
            continue
        for name in names:
            if name not in terrain_names:
                errors.append(f"HEARING[{channel}]: {name!r} is not a terrain name in TERRAIN_MOVEMENT")
    if not h["sight_occluders"] and not h["hear_occluders"]:
        warnings.append("HEARING: no occluders on either channel; occlusion is off everywhere")
    info.append(f"HEARING: sight {sight} cells, hearing flat {h['flat_radius']}, "
                f"loudness {h['normal_loudness']} to {h['max_loudness']}")


def _check_exhaustion(errors, warnings, info):
    """Phase 024: the EXHAUSTION table. Reserve bands fall from e_high to e_low, their moves per tick fall
    from the full budget to zero, and the collapse, sleep and wake thresholds keep their order: a collapse
    wakes weaker than a proper sleep leaves you, and both wake points sit above the collapse point."""
    ex = EXHAUSTION
    fractions = [ex["e_high"], ex["e_mid"], ex["e_low"]]
    for name, value in (("e_high", ex["e_high"]), ("e_mid", ex["e_mid"]), ("e_low", ex["e_low"]),
                        ("e_collapse", ex["e_collapse"]), ("rest_cap", ex["rest_cap"]),
                        ("collapse_cap", ex["collapse_cap"])):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
            errors.append(f"EXHAUSTION[{name}]: a reserve fraction in [0, 1], not {value!r}")
    if not fractions[0] > fractions[1] > fractions[2] > 0.0:
        errors.append(f"EXHAUSTION: e_high > e_mid > e_low > 0 is required, not {fractions}")
    if not ex["e_low"] > ex["e_collapse"] >= 0.0:
        errors.append("EXHAUSTION: e_low > e_collapse >= 0 is required (movement stops before a collapse)")
    if not ex["e_collapse"] < ex["collapse_cap"] < ex["rest_cap"] <= 1.0:
        errors.append("EXHAUSTION: e_collapse < collapse_cap < rest_cap <= 1 is required")
    for name in ("rest_gain", "collapse_gain", "rest_recovery_per_unit"):
        if isinstance(ex[name], bool) or not isinstance(ex[name], (int, float)) or ex[name] <= 0.0:
            errors.append(f"EXHAUSTION[{name}]: must be a positive number, not {ex[name]!r}")
    if ex["collapse_gain"] > ex["rest_gain"]:
        errors.append("EXHAUSTION: collapse_gain must not exceed rest_gain (a collapse sleep is not restorative)")
    moves = ex["moves_per_tick"]
    # Phase 049: the last count is the slowest rate below e_low (walking slows until a collapse; it no longer stops).
    if (len(moves) != 4 or moves[-1] <= 0 or any(moves[i] < moves[i + 1] for i in range(3))
            or moves[0] <= 0 or any(isinstance(m, bool) or not isinstance(m, (int, float)) for m in moves)):
        errors.append(f"EXHAUSTION[moves_per_tick]: four counts, falling, the last above 0, not {moves!r}")
    if not isinstance(ex["slow_on"], bool):
        errors.append(f"EXHAUSTION[slow_on]: a boolean switch, not {ex['slow_on']!r}")
    hours = (ex["night_start_hour"], ex["night_end_hour"])
    if not all(0.0 <= float(h) < 24.0 for h in hours):
        errors.append(f"EXHAUSTION: night hours must lie in [0, 24), not {hours}")


def _check_health(errors, warnings, info):
    """Phase 037: the HEALTH table. One health variable (health_value, 0 to 1) with its causes, the chronic
    age decline and the acute fragility by life stage, and the harms and recovery rates. The causes must
    name the seven routes the phase brief lists, and the per-stage tables must cover every LIFE_STAGES key."""
    h = HEALTH
    if isinstance(h["max_health"], bool) or not 0.0 < float(h["max_health"]) <= 1.0:
        errors.append(f"HEALTH[max_health]: must lie in (0, 1], not {h['max_health']!r}")
    causes = list(h["causes"])
    for needed in ("age", "illness", "injury", "starvation", "exhaustion", "violence", "intoxication"):
        if needed not in causes:
            errors.append(f"HEALTH[causes]: '{needed}' is missing")
    if len(set(causes)) != len(causes) or not all(isinstance(c, str) and c for c in causes):
        errors.append(f"HEALTH[causes]: unique, non-empty names, not {causes!r}")
    for table in ("age_rate", "fragility"):
        if set(h[table]) != set(LIFE_STAGES):
            errors.append(f"HEALTH[{table}]: must give one value per LIFE_STAGES key, not {sorted(h[table])}")
    for stage, rate in h["age_rate"].items():
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate < 0.0:
            errors.append(f"HEALTH[age_rate][{stage}]: a decline per year, >= 0, not {rate!r}")
    for stage, mult in h["fragility"].items():
        if isinstance(mult, bool) or not isinstance(mult, (int, float)) or mult <= 0.0:
            errors.append(f"HEALTH[fragility][{stage}]: a positive multiplier, not {mult!r}")
    if float(h["starve_harm"]) <= 0.0:
        errors.append(f"HEALTH[starve_harm]: must be positive, not {h['starve_harm']!r}")
    if not 0.0 <= float(h["illness_harm"]) <= 1.0:
        errors.append(f"HEALTH[illness_harm]: must lie in [0, 1], not {h['illness_harm']!r}")
    for name in ("rest_health_gain", "exhaustion_harm"):
        if float(h[name]) < 0.0:
            errors.append(f"HEALTH[{name}]: must not be negative, not {h[name]!r}")
    for name in ("exhaustion_free_collapses", "exhaustion_window_periods"):
        if isinstance(h[name], bool) or not isinstance(h[name], int) or h[name] < 0:
            errors.append(f"HEALTH[{name}]: a whole number >= 0, not {h[name]!r}")
    elder = float(h["age_rate"].get("elder", 0.0))
    if elder > 0.0:
        info.append(f"HEALTH: a healthy elder declines to 0 in {float(h['max_health']) / elder:.1f} years "
                    f"of elder age (age_rate {elder} a year, APPROX)")
    info.append(f"HEALTH: starvation kills a healthy adult {-(-float(h['max_health']) // float(h['starve_harm'])):.0f} "
                f"period(s) past starve_limit (starve_harm {h['starve_harm']}, APPROX)")


def _check_marks(errors, warnings, info):
    """Phase 063: MARKS (the visible surface states) and the causes that raise them. Every route of harm
    (HEALTH causes) has a MARK_HARM row, even an empty one, so a cause that leaves no mark is said so on
    purpose. Each recipe, shock and event that names a mark names a kind in MARKS."""
    rules = MARK_RULES
    if not 0.0 < float(rules["max_level"]) <= 1.0:
        errors.append(f"MARK_RULES[max_level]: must lie in (0, 1], not {rules['max_level']!r}")
    for name in ("wash_water", "wet_gain"):
        if float(rules[name]) < 0.0:
            errors.append(f"MARK_RULES[{name}]: must not be negative, not {rules[name]!r}")
    if not 0.0 < float(rules["wash_drop"]) <= 1.0:
        errors.append(f"MARK_RULES[wash_drop]: must lie in (0, 1], not {rules['wash_drop']!r}")
    top = float(rules["max_level"])
    for kind, spec in MARKS.items():
        where = f"MARKS[{kind}]"
        if not str(spec.get("label", "")).strip():
            errors.append(f"{where}: needs a label (the word a view shows)")
        if not isinstance(spec.get("washable"), bool):
            errors.append(f"{where}[washable]: true or false, not {spec.get('washable')!r}")
        for name in ("decay", "rain_wash"):
            if float(spec[name]) < 0.0:
                errors.append(f"{where}[{name}]: must not be negative, not {spec[name]!r}")
        if spec.get("washable") is False and float(spec["rain_wash"]) > 0.0:
            errors.append(f"{where}: a mark that washing cannot take must not be washed by rain")
        if not 0.0 <= float(spec["clothes_change_drop"]) <= 1.0:
            errors.append(f"{where}[clothes_change_drop]: must lie in [0, 1], not {spec['clothes_change_drop']!r}")
        if not 0.0 < float(spec["visible_level"]) <= top:
            errors.append(f"{where}[visible_level]: must lie in (0, max_level], not {spec['visible_level']!r}")
        if isinstance(spec["see_range"], bool) or not isinstance(spec["see_range"], int) or spec["see_range"] < 0:
            errors.append(f"{where}[see_range]: a whole number of cells >= 0, not {spec['see_range']!r}")
        if not 0.0 <= float(spec["see_light"]) <= 1.0:
            errors.append(f"{where}[see_light]: must lie in [0, 1], not {spec['see_light']!r}")
        skill = spec.get("notice_skill")
        if skill is not None and skill not in SKILLS:
            errors.append(f"{where}[notice_skill]: '{skill}' is not a SKILLS name")
    causes = list(HEALTH["causes"])
    for cause in causes:
        if cause not in MARK_HARM:
            errors.append(f"MARK_HARM: HEALTH cause '{cause}' has no row (use {{}} for a cause that leaves no mark)")
    for cause in MARK_HARM:
        if cause not in causes:
            errors.append(f"MARK_HARM[{cause}]: not a HEALTH cause")

    def _known_marks(row, where):
        for kind, gain in row.items():
            if kind not in MARKS:
                errors.append(f"{where}: '{kind}' is not a MARKS kind")
            if isinstance(gain, bool) or not isinstance(gain, (int, float)) or gain <= 0.0:
                errors.append(f"{where}[{kind}]: a gain above 0, not {gain!r}")

    for cause, row in MARK_HARM.items():
        _known_marks(row, f"MARK_HARM[{cause}]")
    for event, row in MARK_EVENTS.items():
        _known_marks(row, f"MARK_EVENTS[{event}]")
    causes_of = {kind: 0 for kind in MARKS}
    for r in RECIPES:
        if "marks" in r:
            _known_marks(r["marks"], f"RECIPES[{r['name']}].marks")
            for kind in r["marks"]:
                causes_of[kind] = causes_of.get(kind, 0) + 1
    for name, spec in SHOCKS.items():
        if "marks" in spec:
            _known_marks(spec["marks"], f"SHOCKS[{name}].marks")
            for kind in spec["marks"]:
                causes_of[kind] = causes_of.get(kind, 0) + 1
    for row in list(MARK_HARM.values()) + list(MARK_EVENTS.values()):
        for kind in row:
            causes_of[kind] = causes_of.get(kind, 0) + 1
    for kind, count in causes_of.items():
        if count == 0 and kind != "wetness":          # wetness comes from rain (MARK_RULES.wet_gain)
            warnings.append(f"MARKS[{kind}]: no recipe, shock, harm or event raises it")
    info.append(f"MARKS: {len(MARKS)} kinds, {sum(1 for r in RECIPES if 'marks' in r)} recipes and "
                f"{sum(1 for s in SHOCKS.values() if 'marks' in s)} shocks name a mark (APPROX levels)")


def _check_intoxication(errors, warnings, info):
    """Phase 034: the INTOXICATION table and the alcohol on the drinks. The bands rise from 0 to pass_out (at most 1),
    wake_below sits under pass_out, and sober_per_tick equals the hourly fall over one clock tick. Every item with
    alcohol is a food in the drink group, and every recipe whose output is a drink yields alcohol."""
    t = INTOXICATION
    b = t["bands"]
    if not 0.0 < float(b["tipsy"]) < float(b["drunk"]) < float(b["stupefied"]) < float(t["pass_out"]) <= 1.0:
        errors.append(f"INTOXICATION: 0 < tipsy < drunk < stupefied < pass_out <= 1 is required, not {b} "
                      f"and pass_out {t['pass_out']!r}")
    if not 0.0 <= float(t["wake_below"]) < float(t["pass_out"]):
        errors.append(f"INTOXICATION[wake_below]: must lie in [0, pass_out), not {t['wake_below']!r}")
    if not 0.0 <= float(t["stagger_above"]) <= 1.0 or not 0.0 < float(t["stagger_speed"]) <= 1.0:
        errors.append("INTOXICATION: stagger_above in [0, 1] and stagger_speed in (0, 1] are required")
    for name in ("coordination_rate", "focus_rate", "social_bonus", "effortful_penalty"):
        if float(t[name]) < 0.0:
            errors.append(f"INTOXICATION[{name}]: must not be negative, not {t[name]!r}")
    if not 0.0 < float(t["widmark_r"]) < 1.0 or float(t["reference_kg"]) <= 0.0 or float(t["full_bac_percent"]) <= 0.0:
        errors.append("INTOXICATION: widmark_r in (0, 1), reference_kg and full_bac_percent positive are required")
    per_hour = float(t["elimination_bac_per_hour"]) / float(t["full_bac_percent"])
    if abs(float(t["sober_per_hour"]) - per_hour) > 1e-9:
        errors.append(f"INTOXICATION: sober_per_hour must equal elimination_bac_per_hour / full_bac_percent "
                      f"({per_hour:.6f}), not {t['sober_per_hour']!r}")
    for kind, spec in ITEMS.items():
        if spec.get("alcohol") is None:
            continue
        if not isinstance(spec["alcohol"], (int, float)) or isinstance(spec["alcohol"], bool) or spec["alcohol"] <= 0:
            errors.append(f"ITEMS[{kind}][alcohol]: grams per serving, > 0, not {spec['alcohol']!r}")
        if not spec.get("food") or spec.get("food_group") != "drink":
            errors.append(f"ITEMS[{kind}]: an item with alcohol must be a food in the drink group")
    for recipe in RECIPES:
        out = recipe.get("out")
        kind = out[0] if isinstance(out, (list, tuple)) and out else None
        if kind and ITEMS.get(kind, {}).get("food_group") == "drink" and not ITEMS[kind].get("alcohol"):
            errors.append(f"recipe {recipe['name']}: makes the drink {kind} with no alcohol on it")
    ale = intoxication_gain(alcohol("ale")) if alcohol("ale") else 0.0
    if ale:
        info.append(f"INTOXICATION: one serving of ale ({alcohol('ale'):g} g) raises a 70 kg body by {ale:.3f} of the "
                    f"0 to 1 scale, and the level falls by {sober_per_tick():g} a tick")


def _check_aftereffects(errors, warnings, info):
    """Phase 036: the alcohol aftereffect keys of INTOXICATION (tolerance, craving and withdrawal, hangover, poisoning,
    speech clarity and the simple coping policy). Rates and shares lie in [0, 1]; the thresholds sit on the scale of
    the bands; the duration is a whole number of ticks. Both packs carry the same INTOXICATION table, so every key is
    required in each."""
    t = INTOXICATION
    keys = ("tolerance_per_drink", "tolerance_max", "tolerance_relief", "tolerance_fade_per_tick",
            "dependence_tolerance", "craving_rise_per_tick", "craving_relief_per_drink", "withdrawal_above",
            "withdrawal_skill", "withdrawal_stamina", "hangover_above", "hangover_ticks", "hangover_skill",
            "hangover_recovery", "poison_above", "poison_harm", "clarity_distance_loss", "coping_bonus",
            "distress_below")
    missing = [k for k in keys if k not in t]
    if missing:
        errors.append(f"INTOXICATION: alcohol aftereffect keys missing: {missing}")
        return
    for name in ("tolerance_per_drink", "tolerance_fade_per_tick", "craving_rise_per_tick", "craving_relief_per_drink",
                 "withdrawal_skill", "withdrawal_stamina", "hangover_skill", "hangover_recovery", "tolerance_relief",
                 "clarity_distance_loss", "distress_below", "withdrawal_above"):
        if not 0.0 <= float(t[name]) <= 1.0:
            errors.append(f"INTOXICATION[{name}]: must lie in [0, 1], not {t[name]!r}")
    if not 0.0 < float(t["tolerance_max"]) <= 1.0 or not 0.0 < float(t["dependence_tolerance"]) <= float(t["tolerance_max"]):
        errors.append("INTOXICATION: 0 < dependence_tolerance <= tolerance_max <= 1 is required")
    if float(t["poison_harm"]) < 0.0 or float(t["coping_bonus"]) < 0.0:
        errors.append("INTOXICATION: poison_harm and coping_bonus must not be negative")
    if not float(t["bands"]["tipsy"]) < float(t["hangover_above"]) <= 1.0:
        errors.append(f"INTOXICATION[hangover_above]: must lie above the tipsy band and at most 1, not "
                      f"{t['hangover_above']!r}")
    if not float(t["bands"]["stupefied"]) <= float(t["poison_above"]) <= 1.0:
        errors.append(f"INTOXICATION[poison_above]: must lie from the stupefied band to 1, not {t['poison_above']!r}")
    hangover = t["hangover_ticks"]
    if not isinstance(hangover, int) or isinstance(hangover, bool) or hangover < 0:
        errors.append(f"INTOXICATION[hangover_ticks]: a whole number of ticks, 0 or more, not {hangover!r}")
    info.append(f"INTOXICATION: a hangover lasts {hangover} ticks, about {hangover * float(TIME['minutes_per_tick']) / 60:g} "
                f"hours; dependence forms at tolerance {float(t['dependence_tolerance']):g}")


def _check_illness(errors, warnings, info):
    """Phase 043: the DISEASE and MEDICAL_CARE tables. Each disease is a HEALTH_CONDITIONS key that is not
    healthy, with a daily onset chance for every season and a multiplier for every life stage, and drops in
    [0, 1]. MEDICAL_CARE gives whole-day durations, the natural and treated recovery rates, and the skills each
    act needs, which must exist in SKILLS. An empty pair (test_hamlet) is valid: the switch then has no rules."""
    if not DISEASE and not MEDICAL_CARE:
        info.append("illness: DISEASE and MEDICAL_CARE are empty in this pack (no illness rules)")
        return
    seasons = set(SEASONS)
    for name, d in DISEASE.items():
        if name not in HEALTH_CONDITIONS or name == "healthy":
            errors.append(f"DISEASE[{name}]: must be an illness in HEALTH_CONDITIONS, not {name!r}")
        rates = d.get("onset_per_day", {})
        if set(rates) != seasons:
            errors.append(f"DISEASE[{name}][onset_per_day]: one rate per season {sorted(seasons)}, not {sorted(rates)}")
        for season, rate in rates.items():
            if not 0.0 <= float(rate) <= 1.0:
                errors.append(f"DISEASE[{name}][onset_per_day][{season}]: a chance per day in [0, 1], not {rate!r}")
        risks = d.get("stage_risk", {})
        if set(risks) != set(LIFE_STAGES):
            errors.append(f"DISEASE[{name}][stage_risk]: one multiplier per LIFE_STAGES key, not {sorted(risks)}")
        for stage, mult in risks.items():
            if float(mult) <= 0.0:
                errors.append(f"DISEASE[{name}][stage_risk][{stage}]: a positive multiplier, not {mult!r}")
        for key in ("severity", "progression", "treat_relief"):
            if float(d.get(key, -1.0)) < 0.0:
                errors.append(f"DISEASE[{name}][{key}]: must not be negative, not {d.get(key)!r}")
        if float(d.get("severity", 0.0)) <= 0.0:
            errors.append(f"DISEASE[{name}][severity]: must be positive, not {d.get('severity')!r}")
        course = d.get("course_days")
        if not isinstance(course, int) or isinstance(course, bool) or course < 1:
            errors.append(f"DISEASE[{name}][course_days]: a whole number of days >= 1, not {course!r}")
        else:
            expected = (sum(float(r) for r in rates.values()) * float(TIME["days_per_year"]) / max(1, len(seasons))
                        * float(risks.get("adult", 1.0)))
            info.append(f"DISEASE[{name}]: about {expected:.2f} onsets per resident-year at adult risk "
                        f"(onset_per_day summed over the year, APPROX)")
    m = MEDICAL_CARE
    for key in ("screen_days", "treated_days", "well_baby_days"):
        value = m.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            errors.append(f"MEDICAL_CARE[{key}]: a whole number of days >= 1, not {value!r}")
    for key in ("natural_care", "treated_heal"):
        if not 0.0 <= float(m.get(key, -1.0)) <= 1.0:
            errors.append(f"MEDICAL_CARE[{key}]: a daily recovery in [0, 1], not {m.get(key)!r}")
    if float(m.get("infant_fragility", -1.0)) < 0.0:
        errors.append(f"MEDICAL_CARE[infant_fragility]: must not be negative, not {m.get('infant_fragility')!r}")
    if float(m.get("medicine_per_treatment", 0.0)) <= 0.0:
        errors.append(f"MEDICAL_CARE[medicine_per_treatment]: must be positive, not {m.get('medicine_per_treatment')!r}")
    skills = m.get("skills", {})
    if set(skills) != {"checkup", "treat", "well_baby"}:
        errors.append(f"MEDICAL_CARE[skills]: must name checkup, treat and well_baby, not {sorted(skills)}")
    for act, names in skills.items():
        if not names:
            errors.append(f"MEDICAL_CARE[skills][{act}]: at least one skill is needed")
        for skill in names:
            if skill not in SKILLS:
                errors.append(f"MEDICAL_CARE[skills][{act}]: '{skill}' is not a skill in SKILLS")


def _check_resolution(errors, warnings, info):
    """Phase 050: the resolution core's tables. Each verb names a primitive the world implements, a skill that
    exists, and a closeness in [0, 1] for each tool verb. Each material has the four figures, and every material an
    item names is in MATERIALS. The RESOLUTION numbers are in range, every lockable kind and the town store have a
    lock strength, and the pure function is monotone in capability (checked numerically on a grid)."""
    for verb, spec in VERBS.items():
        primitive = spec.get("primitive")
        if primitive not in ("damage", "open", "displace", "native"):
            errors.append(f"VERBS[{verb}]: primitive must be damage, open, displace or native, not {primitive!r}")
        if primitive == "native":
            # A verb the world already has routes to its own action (or to none: refused as unsupported).
            route = spec.get("route")
            if route is not None and route not in MAJOR_ACTIONS and route not in ("move", "eat", "sleep", "rest",
                                                                                 "sow", "harvest"):
                errors.append(f"VERBS[{verb}]: route {route!r} is not a major action")
        else:
            # A null skill means the verb needs none (technique is then 1.0). Otherwise the skill must exist.
            if spec.get("skill") is not None and spec.get("skill") not in SKILLS:
                errors.append(f"VERBS[{verb}]: skill {spec.get('skill')!r} is not in SKILLS")
            # Phase 048: a verb names the physical work it needs; a tool's closeness is read against it in TOOL_FIT.
            if str(spec.get("work", "")).strip() == "" or spec.get("work") not in TOOL_FIT["verbs"]:
                errors.append(f"VERBS[{verb}]: 'work' must name a verb in TOOL_FIT, not {spec.get('work')!r}")
        if primitive == "displace":
            # Phase 050b: a displace verb says whether the world runs it yet; an unimplemented one is refused.
            if not isinstance(spec.get("implemented"), bool):
                errors.append(f"VERBS[{verb}]: a displace verb needs 'implemented' (true or false)")
        elif "implemented" in spec:
            errors.append(f"VERBS[{verb}]: only a displace verb carries 'implemented'")
        if not str(spec.get("description", "")).strip():
            errors.append(f"VERBS[{verb}]: needs a description")
    if "attempt" not in MAJOR_ACTIONS or not str(MAJOR_ACTIONS["attempt"].get("description", "")).strip():
        errors.append("MAJOR_ACTIONS: needs 'attempt' with a description (Phase 050)")
    for code in ("unsupported", "destroyed", "not_in_reach", "no_lock"):
        if code not in REFUSAL_REASONS:
            errors.append(f"REFUSAL_REASONS: '{code}' is missing (Phase 050)")
    for name, spec in MATERIALS.items():
        for field in ("hardness", "toughness", "fragility", "noise"):
            value = spec.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 0.0:
                errors.append(f"MATERIALS[{name}][{field}]: a figure >= 0, not {value!r}")
        for field in ("hardness", "toughness", "fragility"):
            if isinstance(spec.get(field), (int, float)) and not 0.0 <= float(spec[field]) <= 1.0:
                errors.append(f"MATERIALS[{name}][{field}]: must lie in [0, 1], not {spec[field]!r}")
    for kind, spec in ITEMS.items():
        if spec.get("material") is not None and spec["material"] not in MATERIALS:
            errors.append(f"MATERIALS: item {kind!r} is made of {spec['material']!r}, which has no entry")
    for name in (RESOLUTION["default_material"], RESOLUTION["lock_material"]):
        if name not in MATERIALS:
            errors.append(f"RESOLUTION: material {name!r} is not in MATERIALS")
    rs = RESOLUTION
    if float(rs["attempt_cap_rate"]) < 1.0:
        errors.append(f"RESOLUTION[attempt_cap_rate]: must be at least 1 (the reference), not {rs['attempt_cap_rate']!r}")
    if float(rs["progress_exponent"]) <= 0.0:
        errors.append(f"RESOLUTION[progress_exponent]: must be positive, not {rs['progress_exponent']!r}")
    if not 0.0 <= float(rs["technique_floor"]) <= 1.0:
        errors.append(f"RESOLUTION[technique_floor]: must lie in [0, 1], not {rs['technique_floor']!r}")
    if float(rs["floor"]) > float(rs["effort_cap"]):
        errors.append("RESOLUTION: floor must not exceed effort_cap")
    if float(rs["max_intensity"]) < 1.0:
        errors.append("RESOLUTION[max_intensity]: must be at least 1.0 (the normal intensity)")
    if not 0.0 < float(rs["i_safe"]) <= float(rs["max_intensity"]):
        errors.append("RESOLUTION[i_safe]: must lie in (0, max_intensity]")
    # Phase 049: the consequence shares of a skill shortfall, an off-season gather, a poor serving, and a leak.
    for name in ("unrelated_fit", "hands_fit", "skill_ruin_ratio", "off_season_yield", "unserved_waste",
                 "leak_per_period"):
        if not 0.0 <= float(rs[name]) <= 1.0:
            errors.append(f"RESOLUTION[{name}]: must lie in [0, 1], not {rs[name]!r}")
    if float(rs["strain_limit"]) <= 0.0 or float(rs["accident_harm"]) < 0.0:
        errors.append("RESOLUTION: strain_limit must be positive and accident_harm not negative")
    if "accident" not in HEALTH["causes"]:
        errors.append("HEALTH[causes]: 'accident' is missing (Phase 050 strain)")
    for kind, spec in CONTAINERS.items():
        if spec.get("lockable") and float(spec.get("lock_strength", 0.0)) <= 0.0:
            errors.append(f"CONTAINERS[{kind}]: a lockable kind needs a positive lock_strength (Phase 050)")
    if float(STORE_LOCK.get("lock_strength", 0.0)) <= 0.0:
        errors.append("STORE_LOCK: needs a positive lock_strength (Phase 050)")
    from worlds import resolution as R
    grid = [i / 10.0 for i in range(0, 31)]
    for d in (0.5, 1.0, 2.0):
        progress = [R.progress_rate(R.rho(c, d), RESOLUTION["attempt_cap_rate"], RESOLUTION["progress_exponent"])
                    for c in grid]
        cost = [R.cost_ratio(d, c, RESOLUTION["floor"], RESOLUTION["effort_cap"]) for c in grid]
        strain = [R.strain(R.cost_ratio(d, c, 0.0, 1.0), R.rho(c, d)) for c in grid]
        if any(b < a - 1e-12 for a, b in zip(progress, progress[1:])):
            errors.append(f"RESOLUTION: progress must not fall as capability rises (demand {d})")
        if any(b > a + 1e-12 for a, b in zip(cost, cost[1:])):
            errors.append(f"RESOLUTION: cost must not rise as capability rises (demand {d})")
        if any(b > a + 1e-12 for a, b in zip(strain, strain[1:])):
            errors.append(f"RESOLUTION: strain must not rise as capability rises (demand {d})")
    # Phase 050b: recipe pace, the trivial and slot thresholds, strain recovery, and displacement.
    for name in ("haste_cap", "care_cap"):
        value = rs.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 1.0:
            errors.append(f"RESOLUTION[{name}]: a pace cap of at least 1.0, not {value!r}")
    for name, hi in (("haste_penalty", None), ("haste_yield_loss", 1.0), ("ruin_below", 1.0),
                     ("trivial_below", 1.0), ("slot_above", 1.0), ("strain_sleep_recovery", None),
                     ("push_cells_per_surplus", None)):
        value = rs.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 0.0 \
                or (hi is not None and float(value) > hi):
            errors.append(f"RESOLUTION[{name}]: out of range, not {value!r}")
    if not isinstance(rs.get("push_mass_unit"), (int, float)) or float(rs["push_mass_unit"]) <= 0.0:
        errors.append(f"RESOLUTION[push_mass_unit]: must be positive, not {rs.get('push_mass_unit')!r}")
    if isinstance(rs.get("push_max_cells"), bool) or not isinstance(rs.get("push_max_cells"), int) \
            or rs["push_max_cells"] < 0:
        errors.append(f"RESOLUTION[push_max_cells]: a whole number of cells, not {rs.get('push_max_cells')!r}")
    if float(rs["trivial_below"]) > float(rs["slot_above"]):
        errors.append("RESOLUTION: trivial_below must not exceed slot_above (a trivial cost is below the slot line)")
    pace_grid = [i / 10.0 for i in range(1, 31)]
    quality = [R.pace_quality(0.8, p, rs["haste_penalty"]) for p in pace_grid]
    yields = [R.pace_yield(p, rs["haste_yield_loss"]) for p in pace_grid]
    if any(b > a + 1e-12 for a, b in zip(quality, quality[1:])):
        errors.append("RESOLUTION: quality must not rise as the recipe pace rises")
    if any(b > a + 1e-12 for a, b in zip(yields, yields[1:])):
        errors.append("RESOLUTION: yield must not rise as the recipe pace rises")
    if "set_intensity" not in FREE_ACTIONS:
        errors.append("FREE_ACTIONS: needs 'set_intensity' (Phase 050b: change a running job's pace)")
    info.append(f"RESOLUTION: {len(VERBS)} verbs, {len(MATERIALS)} materials; attempt cap {rs['attempt_cap_rate']}, "
                f"max intensity {rs['max_intensity']}, i_safe {rs['i_safe']} (APPROX)")
    _check_tool_fit(errors, warnings, info)
    _check_object_force(errors, warnings, info)


def _check_object_force(errors, warnings, info):
    """Phase 040: the OBJECT_FORCE table (what an object held in a hand does when swung or thrown). Every key is a finite
    number in its range, the shape claims hold on a grid (heavier harms more and carries less; harder harms more; a
    fragile container breaks at a lower fragility), the throw's cross-references exist, and the throw verb routes to a
    major action that is in MAJOR_ACTIONS."""
    import math
    from worlds import resolution as R
    of = OBJECT_FORCE
    required = ("harm_scale", "weight_reference", "weight_exponent", "weight_term_min", "weight_term_max",
                "hardness_reference", "unknown_hardness", "edge_bonus", "throw_harm", "throw_demand_unit",
                "range_base", "range_max", "distance_reference", "accuracy_intensity_loss", "passive_defence",
                "unwieldy_above", "container_fragility", "any_fragility")
    missing = [name for name in required if name not in of]
    if missing:
        errors.append(f"OBJECT_FORCE: missing {', '.join(missing)}")
        return
    for name in required:
        value = of[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or abs(value) == float("inf"):
            errors.append(f"OBJECT_FORCE[{name}]: must be a finite number, not {value!r}")
    if errors and any(e.startswith("OBJECT_FORCE[") for e in errors):
        return
    for name in ("harm_scale", "weight_reference", "weight_term_min", "weight_term_max", "hardness_reference",
                 "throw_harm", "throw_demand_unit", "range_base", "distance_reference", "passive_defence",
                 "unwieldy_above"):
        if float(of[name]) <= 0.0:
            errors.append(f"OBJECT_FORCE[{name}]: must be positive, not {of[name]}")
    if float(of["weight_term_max"]) < float(of["weight_term_min"]):
        errors.append("OBJECT_FORCE: weight_term_max must not be below weight_term_min")
    if not 0.0 < float(of["weight_exponent"]) <= 1.0:
        errors.append(f"OBJECT_FORCE[weight_exponent]: must lie in (0, 1] (diminishing returns), not {of['weight_exponent']}")
    for name in ("unknown_hardness", "container_fragility", "any_fragility"):
        if not 0.0 <= float(of[name]) <= 1.0:
            errors.append(f"OBJECT_FORCE[{name}]: must lie in [0, 1], not {of[name]}")
    for name in ("edge_bonus", "accuracy_intensity_loss"):
        if float(of[name]) < 0.0:
            errors.append(f"OBJECT_FORCE[{name}]: must not be negative, not {of[name]}")
    if not isinstance(of["range_max"], int) or isinstance(of["range_max"], bool) or of["range_max"] < 1:
        errors.append(f"OBJECT_FORCE[range_max]: a whole number of cells of at least 1, not {of['range_max']!r}")
    # Shape claims on a grid (Phase 040's acceptance): heavier harms more (and never less), range falls with weight,
    # and a harder material harms more.
    weights = [i / 10.0 for i in range(1, 51)]
    terms = [float(_object_weight_term_of(of, w)) for w in weights]
    if any(b < a - 1e-12 for a, b in zip(terms, terms[1:])):
        errors.append("OBJECT_FORCE: the weight term must not fall as the weight rises")
    ranges = [math.floor(float(of["range_base"]) / max(1.0, w / float(of["weight_reference"]))) for w in weights]
    if any(b > a for a, b in zip(ranges, ranges[1:])):
        errors.append("OBJECT_FORCE: the throw range must not rise as the weight rises")
    hard = [R.clamp(h / 10.0 / float(of["hardness_reference"]), 0.0, 2.0) for h in range(0, 11)]
    if any(b < a - 1e-12 for a, b in zip(hard, hard[1:])):
        errors.append("OBJECT_FORCE: a harder material must not harm less (hardness term)")
    # The throw verb and its action.
    spec = VERBS.get("throw")
    if spec is not None and spec.get("implemented"):
        route = spec.get("route")
        if route != "throw" or "throw" not in MAJOR_ACTIONS or not str(MAJOR_ACTIONS["throw"].get("description", "")).strip():
            errors.append("VERBS[throw]: an implemented throw must route to the 'throw' major action, which needs a description")
        if "fighting" not in SKILLS:
            errors.append("VERBS[throw]: skill 'fighting' is not in SKILLS")
    for name in ("throw", "strike"):
        if name in MAJOR_ACTIONS and not str(MAJOR_ACTIONS[name].get("description", "")).strip():
            errors.append(f"MAJOR_ACTIONS: {name!r} needs a description (Phase 040)")
    info.append(f"OBJECT_FORCE: harm scale {of['harm_scale']}, throw range {of['range_base']} cells for a reference "
                f"object, range_max {of['range_max']}, breakage at fragility {of['container_fragility']} for "
                f"containers and {of['any_fragility']} for any object (APPROX)")


def _object_weight_term_of(of, weight):
    """The weight term of OBJECT_FORCE at `weight` (the same formula as the world's _object_weight_term)."""
    from worlds import resolution as R
    ratio = max(0.0, float(weight)) / float(of["weight_reference"])
    return R.clamp(ratio ** float(of["weight_exponent"]), float(of["weight_term_min"]), float(of["weight_term_max"]))


def _check_tool_fit(errors, warnings, info):
    """Phase 048: the tool-fitness table. Every verb a tool or an attempt names is in TOOL_FIT's vocabulary, so each
    recipe's tool slot has a closeness row (a verb and its pairs). Pairs, rows and the edge, weight and hardness
    figures are in range, and the rows name real tool kinds. The fit falls as effort rises, and a harder tool never
    fits worse."""
    tf = TOOL_FIT
    verbs = set(tf["verbs"])
    for a, b, value in tf["pairs"]:
        if a not in verbs or b not in verbs:
            errors.append(f"TOOL_FIT[pairs]: {a!r}/{b!r} is not in TOOL_FIT[verbs]")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
            errors.append(f"TOOL_FIT[pairs]: closeness of {a!r}/{b!r} must lie in [0, 1], not {value!r}")
    for name in ("edge_verbs", "weight_verbs"):
        for verb in tf[name]:
            if verb not in verbs:
                errors.append(f"TOOL_FIT[{name}]: {verb!r} is not in TOOL_FIT[verbs]")
    tool_kinds = {kind for kind, spec in ITEMS.items() if spec.get("class") == "tool"}
    for kind in tf["edged_kinds"]:
        if kind not in tool_kinds:
            errors.append(f"TOOL_FIT[edged_kinds]: {kind!r} is not a tool item")
    for kind, rows in tf["rows"].items():
        if kind not in tool_kinds:
            errors.append(f"TOOL_FIT[rows]: {kind!r} is not a tool item")
        for row in rows:
            if row.get("verb") not in verbs:
                errors.append(f"TOOL_FIT[rows][{kind}]: verb {row.get('verb')!r} is not in TOOL_FIT[verbs]")
            mult = row.get("mult")
            if isinstance(mult, bool) or not isinstance(mult, (int, float)) or not 0.0 <= float(mult) <= 1.0:
                errors.append(f"TOOL_FIT[rows][{kind}]: mult must lie in [0, 1], not {mult!r}")
            effort = row.get("effort")
            if isinstance(effort, bool) or not isinstance(effort, (int, float)) or float(effort) < 0.0:
                errors.append(f"TOOL_FIT[rows][{kind}]: effort must be at least 0, not {effort!r}")
    for kind, spec in ITEMS.items():
        if spec.get("class") == "tool" and spec.get("verb") not in verbs:
            errors.append(f"TOOL_FIT[verbs]: tool {kind!r} has verb {spec.get('verb')!r}, which is not listed")
    for recipe in RECIPES:
        for kind in recipe.get("tools", []):
            spec = ITEMS.get(kind, {})
            if spec.get("verb") not in verbs:
                errors.append(f"RECIPES[{recipe['name']}].tools: {kind!r} has no closeness row for its verb "
                              f"{spec.get('verb')!r} (Phase 048)")
    for name in ("same_verb", "no_edge"):
        value = tf[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
            errors.append(f"TOOL_FIT[{name}]: must lie in [0, 1], not {value!r}")
    if float(tf["min_weight"]) <= 0.0 or float(tf["hardness_zero_gap"]) <= 0.0:
        errors.append("TOOL_FIT: min_weight and hardness_zero_gap must be positive")
    for name in ("fit_quality_loss", "waste_below"):
        if not 0.0 <= float(RESOLUTION[name]) <= 1.0:
            errors.append(f"RESOLUTION[{name}]: must lie in [0, 1], not {RESOLUTION[name]!r}")
    if "stop" not in FREE_ACTIONS:
        errors.append("FREE_ACTIONS: needs 'stop' (Phase 048: abandon a timed job)")
    from worlds import resolution as R
    grid = [i / 10.0 for i in range(0, 11)]
    effort = [R.effort_multiplier(f, RESOLUTION["effort_cap"]) for f in grid[1:]]
    if any(b > a + 1e-12 for a, b in zip(effort, effort[1:])):
        errors.append("RESOLUTION: the effort of a tool must not rise as its fit rises (Phase 048)")
    hard = [R.hardness_term(h / 10.0, 0.9, tf["hardness_zero_gap"]) for h in range(0, 11)]
    if any(b < a - 1e-12 for a, b in zip(hard, hard[1:])):
        errors.append("TOOL_FIT: a harder tool must not fit worse (Phase 048)")
    info.append(f"TOOL_FIT: {len(tf['verbs'])} verbs, {len(tf['pairs'])} pairs, {len(tf['rows'])} authored tools (APPROX)")


def _check_births(errors, warnings, info):
    """Phase 044: the BIRTHS table. Conception rates cover every fertile age with a rate in [0, 1]; gestation and the
    postpartum block are whole days; the pregnancy's work and food, the delivery risks and the midwife's factor are in
    their ranges; the first-year death is the complement of INFANT_SURVIVAL (Phase 009's table); and 'childbirth' is a
    HEALTH cause with a MARK_HARM row. The arithmetic (domains/fertility_check.py) reports the completed family of a
    union woman entering at the cited age at first union, against the cited CHILDREN_PER_UNION mean (APPROX). The
    growth of the town is not checked here: a village run is needed for that (see the Phase 044 report)."""
    from domains import fertility_check as _fc
    b = BIRTHS
    required = ("fertile_age_min", "fertile_age_max", "conception_per_year", "gestation_days",
                "postpartum_block_days", "pregnancy_food", "pregnancy_load", "stillbirth", "maternal_death",
                "midwife_factor", "infant_first_year_death", "nursed_hunger", "midwife_reach")
    missing = [key for key in required if key not in b]
    for key in missing:
        errors.append(f"BIRTHS[{key}]: missing")
    if missing:
        return
    lo, hi = int(b["fertile_age_min"]), int(b["fertile_age_max"])
    if not 0 < lo < hi:
        errors.append(f"BIRTHS[fertile_age]: need 0 < min < max, not {lo}..{hi}")
    bands = sorted(b["conception_per_year"], key=lambda band: float(band["age_min"]))
    for band in bands:
        if float(band["age_min"]) > float(band["age_max"]) or not 0.0 <= float(band["rate"]) <= 1.0:
            errors.append(f"BIRTHS[conception_per_year]: a band needs age_min <= age_max and a rate in [0, 1], not {band!r}")
    for prev, nxt in zip(bands, bands[1:]):
        if float(nxt["age_min"]) <= float(prev["age_max"]):
            errors.append(f"BIRTHS[conception_per_year]: bands overlap at {nxt['age_min']}")
    for age in range(lo, hi + 1):
        if not any(float(x["age_min"]) <= age <= float(x["age_max"]) for x in bands):
            errors.append(f"BIRTHS[conception_per_year]: no band covers fertile age {age}")
            break
    for key in ("gestation_days", "postpartum_block_days", "midwife_reach"):
        value = b[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"BIRTHS[{key}]: a whole number of days (or cells) >= 0, not {value!r}")
    if int(b["gestation_days"]) < 1:
        errors.append("BIRTHS[gestation_days]: must be at least 1 day")
    if float(b["pregnancy_food"]) < 0.0:
        errors.append(f"BIRTHS[pregnancy_food]: must not be negative, not {b['pregnancy_food']!r}")
    load = b["pregnancy_load"]
    if not 0.0 <= float(load["from_term"]) < 1.0 or not 0.0 <= float(load["max_load"]) <= 1.0:
        errors.append(f"BIRTHS[pregnancy_load]: from_term in [0, 1) and max_load in [0, 1], not {load!r}")
    for key in ("stillbirth", "maternal_death", "infant_first_year_death"):
        if not 0.0 <= float(b[key]) <= 1.0:
            errors.append(f"BIRTHS[{key}]: a chance in [0, 1], not {b[key]!r}")
    if abs(float(b["infant_first_year_death"]) - (1.0 - float(INFANT_SURVIVAL))) > 1e-9:
        errors.append(f"BIRTHS[infant_first_year_death]: must be 1 - INFANT_SURVIVAL ({1.0 - float(INFANT_SURVIVAL)}), "
                      f"not {b['infant_first_year_death']!r}")
    if not 0.0 < float(b["midwife_factor"]) <= 1.0:
        errors.append(f"BIRTHS[midwife_factor]: in (0, 1], not {b['midwife_factor']!r}")
    if float(b["nursed_hunger"]) < 0.0:
        errors.append(f"BIRTHS[nursed_hunger]: must not be negative, not {b['nursed_hunger']!r}")
    if "midwifery" not in SKILLS:
        info.append("BIRTHS: this pack has no midwifery skill, so no resident can attend a birth as a midwife")
    if "childbirth" not in HEALTH["causes"]:
        errors.append("BIRTHS: 'childbirth' is not a HEALTH cause")
    if "childbirth" not in MARK_HARM:
        errors.append("BIRTHS: 'childbirth' has no MARK_HARM row")
    days = float(TIME["days_per_year"])
    entry = float(AGE_AT_FIRST_UNION["female"]["mean"])
    family = _fc.completed_family(bands, gestation_days=int(b["gestation_days"]),
                                  postpartum_days=int(b["postpartum_block_days"]), entry_age=entry,
                                  end_age=float(hi) + 1.0, days_per_year=days)
    cited = float(CHILDREN_PER_UNION["mean"])
    info.append(f"BIRTHS: a union woman entering at {entry:g} has {family:.2f} children by {hi + 1} "
                f"(table) against CHILDREN_PER_UNION mean {cited:g} (APPROX, Wrigley and Schofield 1981)")
    if abs(family - cited) > 1.0:
        errors.append(f"BIRTHS: completed family {family:.2f} is more than 1.0 from CHILDREN_PER_UNION {cited:g}")
    for age in (25, 30, 35):
        per_year = _fc.births_per_union_year(bands, age=age, days_per_year=days,
                                             gestation_days=int(b["gestation_days"]),
                                             postpartum_days=int(b["postpartum_block_days"]))
        info.append(f"BIRTHS: a union woman aged {age} has {per_year:.3f} births a year on average (table)")


def _check_dependants(errors, warnings, info):
    """Phase 045: the DEPENDANTS table. Dependant stages are life stages below the adult age and include the
    infant (the refusal applies to it); each has a whole-day neglect span; the neglect cause is a HEALTH cause
    with a MARK_HARM row; 'infant' is a refusal reason; the growth fractions and work factors are in range.
    Reports the growth curve and the switch state."""
    from domains.dependants import growth_fraction as _growth_fraction
    d = DEPENDANTS
    stages = list(d["stages"])
    adult = LIFE_STAGES["adult"]
    if not stages or len(set(stages)) != len(stages):
        errors.append(f"DEPENDANTS[stages]: a non-empty list of unique stages, not {stages!r}")
    for stage in stages:
        if stage not in LIFE_STAGES:
            errors.append(f"DEPENDANTS[stages]: {stage!r} is not a LIFE_STAGES key")
            continue
        if float(LIFE_STAGES[stage]["age_max"]) >= float(adult["age_min"]):
            errors.append(f"DEPENDANTS[stages]: {stage!r} reaches the adult age ({adult['age_min']})")
        if not 0.0 <= float(LIFE_STAGES[stage]["care"]) <= 1.0 or not 0.0 <= float(LIFE_STAGES[stage]["work_fraction"]) <= 1.0:
            errors.append(f"DEPENDANTS[stages]: {stage!r} needs care and work_fraction in [0, 1]")
    if "infant" not in stages:
        errors.append("DEPENDANTS[stages]: 'infant' must be a dependant stage (the major-action refusal applies to it)")
    if not isinstance(d["enabled"], bool):
        errors.append(f"DEPENDANTS[enabled]: a boolean, not {d['enabled']!r}")
    spans = d["neglect_after_days"]
    if set(spans) != set(stages):
        errors.append(f"DEPENDANTS[neglect_after_days]: one span per dependant stage, not {sorted(spans)}")
    for stage, days in spans.items():
        if isinstance(days, bool) or not isinstance(days, int) or days < 0:
            errors.append(f"DEPENDANTS[neglect_after_days][{stage}]: a whole number of days >= 0, not {days!r}")
    if float(d["neglect_harm"]) < 0.0:
        errors.append(f"DEPENDANTS[neglect_harm]: must not be negative, not {d['neglect_harm']!r}")
    reach = d["reach_cells"]
    if isinstance(reach, bool) or not isinstance(reach, int) or reach < 0:
        errors.append(f"DEPENDANTS[reach_cells]: a whole number of cells >= 0, not {reach!r}")
    if float(d["caregiver_max_hunger"]) < 0.0:
        errors.append(f"DEPENDANTS[caregiver_max_hunger]: must not be negative, not {d['caregiver_max_hunger']!r}")
    growth = d["growth"]
    for key in ("strength_start", "stamina_start"):
        if not 0.0 < float(growth[key]) <= 1.0:
            errors.append(f"DEPENDANTS[growth][{key}]: in (0, 1], not {growth[key]!r}")
    if float(growth["exponent"]) <= 0.0:
        errors.append(f"DEPENDANTS[growth][exponent]: must be positive, not {growth['exponent']!r}")
    if "neglect" not in HEALTH["causes"]:
        errors.append("DEPENDANTS: 'neglect' is not a HEALTH cause")
    if "neglect" not in MARK_HARM:
        errors.append("DEPENDANTS: 'neglect' has no MARK_HARM row")
    if "infant" not in REFUSAL_REASONS:
        errors.append("DEPENDANTS: 'infant' is not a REFUSAL_REASONS code")
    adult_age = float(adult["age_min"])
    bands = sorted(LIFE_STAGES.values(), key=lambda s: float(s["age_min"]))
    gaps = [f"{float(a['age_max']):g} to {float(b['age_min']):g}" for a, b in zip(bands, bands[1:])
            if float(b["age_min"]) > float(a["age_max"])]
    info.append(f"DEPENDANTS: the LIFE_STAGES bands leave gaps ({', '.join(gaps) or 'none'}); an age in a gap reads as "
                "elder with the switch off (HEAD) and as the band below it with the switch on")
    state = "on" if d["enabled"] else "off"
    for age in (0, 4, 12, 18):
        strength = _growth_fraction(age, float(growth["strength_start"]), adult_age, float(growth["exponent"]))
        stamina = _growth_fraction(age, float(growth["stamina_start"]), adult_age, float(growth["exponent"]))
        info.append(f"DEPENDANTS: at age {age} strength is {strength:.3f} and stamina {stamina:.3f} of the adult "
                    f"base (switch {state})")


def _check_contest(errors, warnings, info):
    """Phase 029: the CONTEST table (a contested take: force, cost, margins, reactions) and the SIZE table it
    draws body size from. Fractions stay in range, the margins and reaction bands keep their order, and the
    reasons, action, handover kinds and the fighting skill that the contest uses exist in their tables."""
    ct = CONTEST
    expected = ("size_exponent", "life_stage_force", "base_cost", "grip", "technique_weight", "min_efficiency",
                "trivial_below", "slot_above", "decisive_margin", "narrow_margin", "redirect_gap", "overextend",
                "reaction_floor", "late_penalty", "late_options", "busy_factor", "overloaded_factor",
                "baseline_level", "practice_minutes", "log_limit", "strike_harm", "attack_cost", "redirect_harm")
    for name in expected:
        if name not in ct:
            errors.append(f"CONTEST: missing {name!r}")
    if errors and any(name not in ct for name in expected):
        return

    def number(name):
        value = ct[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"CONTEST[{name}]: a number, not {value!r}")
            return None
        return float(value)

    values = {name: number(name) for name in expected if name not in ("life_stage_force", "late_options", "log_limit")}
    if values.get("size_exponent") is not None and values["size_exponent"] <= 0.0:
        errors.append(f"CONTEST[size_exponent]: must be positive, not {values['size_exponent']}")
    for name, lo, hi in (("grip", 0.0, 1.0), ("min_efficiency", 0.0, 1.0), ("redirect_gap", 0.0, 1.0),
                         ("reaction_floor", 0.0, 1.0), ("late_penalty", 0.0, 1.0), ("busy_factor", 0.0, 1.0),
                         ("overloaded_factor", 0.0, 1.0), ("baseline_level", 0.0, 1.0),
                         ("decisive_margin", 0.0, 1.0), ("narrow_margin", 0.0, 1.0)):
        value = values.get(name)
        if value is not None and not (lo < value <= hi if name in ("grip", "min_efficiency", "late_penalty",
                                                                   "busy_factor", "overloaded_factor",
                                                                   "reaction_floor", "decisive_margin")
                                      else lo <= value <= hi):
            errors.append(f"CONTEST[{name}]: out of range, not {value}")
    for name in ("base_cost", "slot_above", "practice_minutes", "strike_harm", "attack_cost"):
        value = values.get(name)
        if value is not None and value <= 0.0:
            errors.append(f"CONTEST[{name}]: must be positive, not {value}")
    for name in ("technique_weight", "trivial_below", "overextend", "redirect_harm"):
        value = values.get(name)
        if value is not None and value < 0.0:
            errors.append(f"CONTEST[{name}]: must not be negative, not {value}")
    if (values.get("decisive_margin") is not None and values.get("narrow_margin") is not None
            and not values["decisive_margin"] > values["narrow_margin"] >= 0.0):
        errors.append("CONTEST: decisive_margin > narrow_margin >= 0 is required (the goods fall in between)")
    if isinstance(ct["log_limit"], bool) or not isinstance(ct["log_limit"], int) or ct["log_limit"] < 1:
        errors.append(f"CONTEST[log_limit]: a whole number of at least 1, not {ct['log_limit']!r}")
    for stage, factor in ct["life_stage_force"].items():
        if stage not in LIFE_STAGES:
            errors.append(f"CONTEST[life_stage_force]: unknown life stage {stage!r}")
        if isinstance(factor, bool) or not isinstance(factor, (int, float)) or not 0.0 < float(factor) <= 1.5:
            errors.append(f"CONTEST[life_stage_force][{stage}]: a factor in (0, 1.5], not {factor!r}")
    if sorted(ct["late_options"]) != sorted(set(ct["late_options"])) or not set(ct["late_options"]) <= {"yield", "brace"}:
        errors.append(f"CONTEST[late_options]: a subset of yield and brace, not {ct['late_options']!r}")
    if "yield" not in ct["late_options"]:
        errors.append("CONTEST[late_options]: a late reaction must always allow yield")
    for code in ("held", "evaded", "dropped"):
        if code not in REFUSAL_REASONS:
            errors.append(f"REFUSAL_REASONS: needs the contest code {code!r} (Phase 029)")
    if "take" not in MAJOR_ACTIONS or not str(MAJOR_ACTIONS["take"].get("description", "")).strip():
        errors.append("MAJOR_ACTIONS: needs 'take' with a description (Phase 029)")
    if "strike" not in MAJOR_ACTIONS or not str(MAJOR_ACTIONS["strike"].get("description", "")).strip():
        errors.append("MAJOR_ACTIONS: needs 'strike' with a description (Phase 038)")
    for action in ("restrain", "release", "struggle"):
        if action not in MAJOR_ACTIONS or not str(MAJOR_ACTIONS[action].get("description", "")).strip():
            errors.append(f"MAJOR_ACTIONS: needs {action!r} with a description (Phase 033)")
    for code in ("restrained", "holding", "already_holding", "already_restrained", "not_holding", "not_restrained",
                 "slipped", "pinned"):
        if code not in REFUSAL_REASONS:
            errors.append(f"REFUSAL_REASONS: needs the restraint code {code!r} (Phase 033)")
    if "violence" not in HEALTH["causes"]:
        errors.append("HEALTH[causes]: 'violence' is missing (Phase 038 strikes)")
    for kind in ("take", "yield"):
        if kind not in HANDOVER_KINDS:
            errors.append(f"HANDOVER_KINDS: needs the contest kind {kind!r} (Phase 029)")
    if "fighting" not in SKILLS or SKILLS["fighting"].get("learning") != "physical":
        errors.append("SKILLS[fighting]: the contest skill must exist and be learned physically (Phase 029)")
    if "fighting" not in SKILLS or not any("fighting" in c["skills"] for c in SKILL_CLUSTERS.values()):
        errors.append("SKILL_CLUSTERS: no cluster holds 'fighting' (Phase 029)")
    sz = SIZE
    for name in ("sd", "floor"):
        if isinstance(sz.get(name), bool) or not isinstance(sz.get(name), (int, float)) or float(sz[name]) < 0:
            errors.append(f"SIZE[{name}]: a non-negative number, not {sz.get(name)!r}")
    if not 0.0 < float(sz["floor"]) <= 1.0:
        errors.append(f"SIZE[floor]: in (0, 1], not {sz['floor']!r}")
    points = sz["mean_by_age"]
    starts = [float(start) for start, _ in points]
    if not points or starts[0] != 0.0 or starts != sorted(set(starts)) or any(float(m) <= 0.0 for _, m in points):
        errors.append(f"SIZE[mean_by_age]: points from age 0, ascending, with positive means, not {points!r}")
    info.append(f"CONTEST: reaction floor {ct['reaction_floor']}, decisive margin {ct['decisive_margin']}, "
                f"base cost {ct['base_cost']}; SIZE mean at age 18 {points[-1][1] if points else 'n/a'}")


def _check_joint_tasks(errors, warnings, info):
    """Phase 047: the joint-action tables. JOINT_TASKS holds exactly the carry and crew tasks, with in-range numbers.
    The carry load unit is one adult's carrying capacity (ACTOR_DEFAULTS.inventory_max_load). A group's summed force
    rises with each member by less than the one before, and a crewed recipe's crew field is 1 <= min <= max; a lone
    worker crawls below two, and a further worker adds less than a full worker's labour."""
    from worlds import joint as J
    for name in ("carry", "crew"):
        if name not in JOINT_TASKS:
            errors.append(f"JOINT_TASKS: the {name!r} task is missing")
    for name in JOINT_TASKS:
        if name not in ("carry", "crew"):
            errors.append(f"JOINT_TASKS: unknown task {name!r}")
    if any(name not in JOINT_TASKS for name in ("carry", "crew")):
        return
    carry, crew = JOINT_TASKS["carry"], JOINT_TASKS["crew"]
    loss, relief = float(carry["coordination_loss"]), float(carry["skill_relief"])
    if not 0.0 <= loss < 1.0:
        errors.append(f"JOINT_TASKS[carry][coordination_loss]: must lie in [0, 1), not {loss!r}")
    if not 0.0 <= relief <= 1.0:
        errors.append(f"JOINT_TASKS[carry][skill_relief]: must lie in [0, 1], not {relief!r}")
    if float(carry["load_unit"]) != float(ACTOR_DEFAULTS["inventory_max_load"]):
        errors.append("JOINT_TASKS[carry][load_unit]: must equal ACTOR_DEFAULTS.inventory_max_load (one adult's capacity)")
    if not isinstance(carry["max_members"], int) or carry["max_members"] < 2:
        errors.append(f"JOINT_TASKS[carry][max_members]: a whole number of at least 2, not {carry['max_members']!r}")
    if not isinstance(carry["reach"], int) or carry["reach"] < 1:
        errors.append(f"JOINT_TASKS[carry][reach]: a whole number of cells of at least 1, not {carry['reach']!r}")
    if not isinstance(carry["pace_cap"], int) or carry["pace_cap"] < 1:
        errors.append(f"JOINT_TASKS[carry][pace_cap]: a whole number of cells of at least 1, not {carry['pace_cap']!r}")
    if float(carry["load_unit"]) <= 0.0:
        errors.append("JOINT_TASKS[carry][load_unit]: must be positive")
    penalty = float(crew["crew_penalty"])
    if not 0.0 < penalty <= 1.0:
        errors.append(f"JOINT_TASKS[crew][crew_penalty]: must lie in (0, 1], not {penalty!r}")
    # The summed force of n people (times coordination) rises with each person, by less each time.
    cap = int(carry["max_members"])
    totals = [n * J.coordination(n, 0.0, loss, relief) for n in range(1, cap + 1)]
    steps = [b - a for a, b in zip(totals, totals[1:])]
    if any(step <= 0.0 for step in steps):
        errors.append("JOINT_TASKS: the summed force of a group must rise with each member")
    if any(later > earlier + 1e-12 for earlier, later in zip(steps, steps[1:])):
        errors.append("JOINT_TASKS: each added member must add no more than the one before (coordination)")
    # Crewed recipes: the crew field is 1 <= min <= max, and the crew factor crawls alone and adds less than a worker.
    crewed = [row for row in RECIPES if "crew" in row]
    for row in crewed:
        field = row["crew"]
        mn, mx = field.get("min"), field.get("max")
        if not isinstance(mn, int) or not isinstance(mx, int) or not 1 <= mn <= mx:
            errors.append(f"RECIPES[{row['name']}][crew]: needs whole numbers with 1 <= min <= max, not {field!r}")
            continue
        factors = [J.crew_factor(n, penalty, 0.0, loss, relief) for n in range(1, mx + 1)]
        if mx >= 2 and not factors[0] < factors[1]:
            errors.append(f"RECIPES[{row['name']}][crew]: a lone worker must progress more slowly than two")
        for n in range(2, mx):
            if factors[n] - factors[n - 1] >= 1.0:
                errors.append(f"RECIPES[{row['name']}][crew]: worker {n + 1} adds a full worker's labour or more")
    info.append(f"JOINT_TASKS: carry load unit {carry['load_unit']} up to {cap} people; crew on {len(crewed)} recipe(s)")


def _check_training(errors, warnings, info):
    """Phase 032: TRAIN_HEADROOM and TRAIN_RATE (seed bd_train_strength, bd_train_stamina) and the body they
    build. A recipe's strength requirement must be reachable by training from the founding body (base x
    (1 + TRAIN_HEADROOM)); otherwise no resident could ever attempt it. Also records the time-to-train line
    for the plough: how long a founding labourer takes to reach the plough's strength requirement."""
    headroom, rate = TRAIN_HEADROOM, TRAIN_RATE
    if isinstance(headroom, bool) or not isinstance(headroom, (int, float)) or not 0.0 <= headroom <= 1.0:
        errors.append(f"TRAIN_HEADROOM: a fraction in [0, 1], not {headroom!r}")
        return
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0.0 < rate <= 1.0:
        errors.append(f"TRAIN_RATE: a fraction in (0, 1], not {rate!r}")
        return
    base = float(ACTOR_DEFAULTS["body"]["str_base"])
    reach = base * (1.0 + float(headroom))
    for name, (strength_req, stamina_cost) in RECIPE_EXERTION.items():
        if float(stamina_cost) < 0.0:
            errors.append(f"RECIPE_EXERTION[{name}]: stamina cost must not be negative, not {stamina_cost}")
        if float(strength_req) > reach + 1e-12:
            errors.append(f"RECIPE_EXERTION[{name}]: strength {strength_req} is above what training can reach "
                          f"from the founding body ({reach}); no resident could attempt it")
    if "forge_plough" in RECIPE_EXERTION:
        req, cost = RECIPE_EXERTION["forge_plough"]
        minutes = next((float(r["time_minutes"]) for r in RECIPES if r["name"] == "forge_plough"), None)
        efforts = efforts_to_train(base, req, cost)
        if efforts is None:
            errors.append("TRAINING: a founding labourer cannot reach the plough's strength by training")
        else:
            hours = efforts * minutes / 60.0 if minutes else float("nan")
            info.append(f"TRAINING time-to-train: a founding labourer (strength {base}, health 1.0) reaches the "
                        f"plough's strength {req} in {efforts} efforts of {cost} stamina each, one per forge_plough "
                        f"batch of {minutes:g} minutes: {hours:.1f} hours of forging "
                        f"(TRAIN_RATE {rate}, TRAIN_HEADROOM {headroom}; ceiling {reach:g})")


def _check_food_grading(errors, warnings, info):
    """Phase 027: every food item has a `feeds` value in loaf-equivalents (0 < feeds <= 1.5), a raw food that
    needs preparation is a food, and the FOOD_GRADING constants are fractions. Derived scraps carry no feeds
    (they are animal feed), so they are skipped."""
    for kind, spec in ITEMS.items():
        if not spec.get("food") or spec.get("scraps_of"):
            continue
        feeds_value = spec.get("feeds")
        if isinstance(feeds_value, bool) or not isinstance(feeds_value, (int, float)):
            errors.append(f"ITEMS[{kind}]: a food needs a numeric 'feeds' value, not {feeds_value!r}")
        elif not 0.0 < float(feeds_value) <= 1.5:
            errors.append(f"ITEMS[{kind}].feeds: loaf-equivalents in (0, 1.5], not {feeds_value!r}")
        if "needs_prep" in spec and not isinstance(spec["needs_prep"], bool):
            errors.append(f"ITEMS[{kind}].needs_prep: a boolean, not {spec['needs_prep']!r}")
    for kind, spec in ITEMS.items():
        if spec.get("needs_prep") and not spec.get("food"):
            errors.append(f"ITEMS[{kind}]: needs_prep is only meaningful on a food")
    raw = FOOD_GRADING.get("raw_penalty")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not 0.0 < float(raw) <= 1.0:
        errors.append(f"FOOD_GRADING[raw_penalty]: a multiplier in (0, 1], not {raw!r}")
    for name in ("rot_illness", "raw_illness"):
        value = FOOD_GRADING.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
            errors.append(f"FOOD_GRADING[{name}]: a risk in [0, 1], not {value!r}")


def _check_nutrition(errors, warnings, info):
    """Phase 035: every food carries a protein (grams per unit, 0 or more) and a taste (0 to 1). The NUTRITION
    constants are in range, and each spice kind names an item. The founding staple's protein is reported against
    the need in the info lines (the balance check that flags a shortfall is in the balance section below)."""
    for kind, spec in ITEMS.items():
        if not spec.get("food") or spec.get("scraps_of"):
            continue
        protein_value = spec.get("protein")
        if isinstance(protein_value, bool) or not isinstance(protein_value, (int, float)) or float(protein_value) < 0.0:
            errors.append(f"ITEMS[{kind}]: a food needs a protein (grams per unit, 0 or more), not {protein_value!r}")
        taste_value = spec.get("taste")
        if isinstance(taste_value, bool) or not isinstance(taste_value, (int, float)) or not 0.0 <= float(taste_value) <= 1.0:
            errors.append(f"ITEMS[{kind}].taste: a rating in [0, 1], not {taste_value!r}")
    n = NUTRITION
    for name in ("protein_retain", "deficiency_rate", "deficiency_recovery", "monotony_cap", "monotony_retain",
                 "pleasure_retain", "spice_bonus"):
        value = n.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
            errors.append(f"NUTRITION[{name}]: a fraction in [0, 1], not {value!r}")
    for name in ("monotony_rise", "mood_rate"):
        value = n.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 < float(value) <= 1.0:
            errors.append(f"NUTRITION[{name}]: a rate in (0, 1], not {value!r}")
    need = n.get("protein_need")
    if isinstance(need, bool) or not isinstance(need, (int, float)) or float(need) <= 0.0:
        errors.append(f"NUTRITION[protein_need]: grams per resident per period, above 0, not {need!r}")
    for kind in n.get("spice_kinds", []):
        if kind not in ITEMS:
            errors.append(f"NUTRITION[spice_kinds]: {kind!r} is not an item")
    if isinstance(need, (int, float)) and not isinstance(need, bool) and float(need) > 0.0:
        pb = protein_balance(BALANCE_SCENARIO)
        if pb is not None:
            info.append(f"protein: the founding staple gives {pb[0] / float(BALANCE_SCENARIO['residents']):.1f} g "
                        f"per resident per period against a need of {float(need):.1f} g")


def _check_prompt_instructions(errors, warnings, info):
    """Phase 018: the LLM prompt tables and speech lexicon. Each action has a description, the response
    fields are the ones the backend parses, the selection caps are positive, the standing types and gist
    keys name real item types, and the chatter and weather templates keep their placeholder."""
    # The response keys ActorResponse.from_dict reads (bigville/backends/protocol.py).
    _RESPONSE_FIELDS = {"major_action", "continuation", "utterances", "memory_updates", "waiting"}
    for table in ("MAJOR_ACTIONS", "FREE_ACTIONS"):
        for name, spec in globals()[table].items():
            if not str(spec.get("description", "")).strip():
                errors.append(f"{table}[{name}]: no description (the LLM prompt lists it)")
    premise = WORLD_PREMISE
    if not str(premise.get("name", "")).strip() or not str(premise.get("premise", "")).strip():
        errors.append("WORLD_PREMISE: needs a name and a premise")
    unknown = [f for f in PROMPT_RESPONSE_FIELDS if f not in _RESPONSE_FIELDS]
    if unknown or not PROMPT_RESPONSE_FIELDS:
        errors.append(f"PROMPT_RESPONSE_FIELDS: not response fields the backend reads: {unknown}")
    for name in ("PROMPT_BOUNDARY_RULES", "PROMPT_CONTINUATION_RULES"):
        if not globals()[name] or not all(str(rule).strip() for rule in globals()[name]):
            errors.append(f"{name}: needs at least one non-empty rule")
    caps = {k: v for k, v in PROMPT_SELECTION.items() if not k.startswith("_") and k not in ("standing_types",)}
    for key, value in caps.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            errors.append(f"PROMPT_SELECTION[{key}]: must be a positive integer, not {value!r}")
    item_types = {"law", "policy", "charter", "concept", "kin_term", "office", "procedure", "animal",
                  "good", "recipe", "place", "resident"}
    for kind in PROMPT_SELECTION.get("standing_types", []):
        if kind not in item_types:
            errors.append(f"PROMPT_SELECTION.standing_types: '{kind}' is not a knowledge item type")
    for kind in sorted(item_types):
        if kind not in MEMORY_GIST:
            warnings.append(f"MEMORY_GIST: no gist for item type '{kind}' (the default gist is used)")
    if "default" not in MEMORY_GIST:
        errors.append("MEMORY_GIST: needs a 'default' gist")
    chatter, weather = SPEECH_CHATTER, SPEECH_WEATHER
    if "{trade}" not in chatter["work_template"]:
        errors.append("SPEECH_CHATTER.work_template: needs the {trade} placeholder")
    if "{weather}" not in weather["template"]:
        errors.append("SPEECH_WEATHER.template: needs the {weather} placeholder")
    for key in weather["phrases"]:
        if key not in WEATHER:
            errors.append(f"SPEECH_WEATHER[{key}]: not a WEATHER name")
    unused = sorted(key for key in chatter["phrases"] if key not in TRADES)
    if unused:
        info.append(f"SPEECH_CHATTER: phrases for names that are not trades in this pack (never used): "
                    f"{', '.join(unused)}")


def _check_generated_seeds(errors):
    """Phase 017: the generated Ocelot seeds in bigville/seeds/ are what the bigville pack produces now.
    Only the canonical pack is checked; a child or test pack has no canonical directory."""
    if _WORLD_PACK.name != _generated_seeds.CANONICAL_PACK:
        return
    for problem in _generated_seeds.check_seeds(_WORLD_PACK, _generated_seeds.CANONICAL_SEED_DIR):
        errors.append(f"generated seeds: {problem}")


def check_fiscal(institutions, backend_owned, purses, actions, errors, warnings, info, *,
                 offices=(), jobs=(), seed_dir=None):
    """Phase 011: the fiscal tables, as pure data (no world).

    Every rule of the seed files named by the institutions appears exactly once, either in an institution's
    `seed_rules` or in `backend_owned`; the rules in a seed file are the ones mapped to it. Purse holders and
    the roles an institution names are offices or jobs. A purse an institution names exists. Each backend-owned
    rule says why. `seed_dir` (None to skip) is where the seed files are read."""
    import json as _json
    roles = set(offices) | set(jobs)
    for name, spec in purses.items():
        if spec.get("holder_role") not in roles:
            errors.append(f"FISCAL_PURSES[{name}].holder_role: '{spec.get('holder_role')}' is not an office or a job")
        opening = spec.get("opening_coin", 0)
        if not isinstance(opening, (int, float)) or isinstance(opening, bool) or opening < 0 or float(opening) % 1:
            errors.append(f"FISCAL_PURSES[{name}].opening_coin: must be a whole number of coins, 0 or more")
        if not str(spec.get("description", "")).strip():
            errors.append(f"FISCAL_PURSES[{name}]: no description")
    for name, spec in actions.items():
        if not str(spec.get("description", "")).strip():
            errors.append(f"FISCAL_ACTIONS[{name}]: no description (the LLM prompt lists it)")
    mapped = {}
    for name, spec in institutions.items():
        where = f"FISCAL_INSTITUTIONS[{name}]"
        for key in ("title", "kind", "payers", "payees", "schedule", "purse", "agent_role", "requires_colocation",
                    "on_missed", "seeds", "seed_rules", "knowledge"):
            if key not in spec:
                errors.append(f"{where}: missing '{key}'")
        if spec.get("purse") is not None and spec.get("purse") not in purses:
            errors.append(f"{where}.purse: '{spec.get('purse')}' is not a FISCAL_PURSES entry")
        if spec.get("agent_role") is not None and spec.get("agent_role") not in roles:
            errors.append(f"{where}.agent_role: '{spec.get('agent_role')}' is not an office or a job")
        for role in spec.get("payee_roles", []):
            if role not in roles:
                errors.append(f"{where}.payee_roles: '{role}' is not an office or a job")
        if not isinstance(spec.get("requires_colocation"), bool):
            errors.append(f"{where}.requires_colocation: must be true or false")
        if not spec.get("seeds") or not spec.get("seed_rules"):
            errors.append(f"{where}: needs the seed files and seed rules it came from")
        for rule in spec.get("seed_rules", []):
            mapped.setdefault(rule, []).append(f"{name}")
    for row in backend_owned:
        rule = row.get("rule", "")
        if row.get("owner") != "backend":
            errors.append(f"FISCAL_BACKEND_OWNED[{rule}]: owner must be 'backend'")
        if not str(row.get("reason", "")).strip():
            errors.append(f"FISCAL_BACKEND_OWNED[{rule}]: no reason")
        mapped.setdefault(rule, []).append("backend")
    for rule, where in sorted(mapped.items()):
        if len(where) > 1:
            errors.append(f"FISCAL rule '{rule}' is mapped more than once: {', '.join(where)}")
    if seed_dir is None:
        return
    seeds = {s for spec in institutions.values() for s in spec.get("seeds", [])}
    seeds |= {row.get("seed", "") for row in backend_owned}
    in_files = set()
    for seed in sorted(seeds):
        path = _os.path.join(seed_dir, f"{seed}.json")
        if not _os.path.isfile(path):
            errors.append(f"FISCAL seed file missing: {seed}.json in {seed_dir}")
            continue
        with open(path, encoding="utf-8") as fh:
            rules = [r["name"] for r in _json.load(fh).get("rules", [])]
        for rule in rules:
            in_files.add(rule)
            if rule not in mapped:
                errors.append(f"FISCAL seed {seed}: rule '{rule}' is not mapped to an institution or backend-owned")
    for rule in sorted(mapped):
        if rule not in in_files:
            errors.append(f"FISCAL rule '{rule}' is mapped but is not in any seed file read")
    info.append(f"FISCAL: {len(institutions)} institutions, {len(mapped)} seed rules mapped "
                f"({len(backend_owned)} backend-owned), {len(purses)} purses")


def _check_fiscal(errors, warnings, info):
    """Phase 011: the canonical pack's fiscal tables, with its seed files read from bigville/seeds/."""
    seed_dir = _generated_seeds.CANONICAL_SEED_DIR if _WORLD_PACK.name == _generated_seeds.CANONICAL_PACK else None
    check_fiscal(FISCAL_INSTITUTIONS, FISCAL_BACKEND_OWNED, FISCAL_PURSES, FISCAL_ACTIONS, errors, warnings, info,
                 offices=GOVERNANCE_OFFICES, jobs=JOBS, seed_dir=seed_dir)


def check_consistency():
    """Check every cross-reference and production pipeline in the entity data.

    Returns ``{"errors": [...], "warnings": [...], "info": [...], "stats": {...}}``. Each message is
    a plain string naming the table and the offending entry.
    """
    errors, warnings, info = [], [], []
    items = set(ITEMS)
    recipes = {r["name"]: r for r in RECIPES}
    known_places = set(BUILDINGS)
    _daynight_check.check(errors, warnings, info, daynight=DAYNIGHT, lamps=DAYNIGHT_LAMPS, weather=WEATHER,
                          jobs=JOBS, labour_tasks=LABOUR_TASKS, items=ITEMS, major_actions=MAJOR_ACTIONS,
                          founding_map=FOUNDING_MAP, time=TIME)   # Phase 042

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
        if r.get("burial") == "bury":
            # Phase 010: a burial yields no product, so its out row is the empty kind with quantity 0.
            if list(r["out"]) != ["", 0]:
                errors.append(f"RECIPES[{name}].out: a burial yields no product, so it must be ['', 0]")
        else:
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
        if not r["in"] and not r.get("gathered_from") and not r.get("at_building"):
            warnings.append(f"RECIPES[{name}]: has no inputs but does not say where it is gathered_from "
                            f"or built")
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
        if spec.get("founding_sex") not in ("male", "female"):
            errors.append(f"ANIMALS[{species}]: founding_sex must be 'male' or 'female'")
        if not isinstance(spec.get("breeds"), bool):
            errors.append(f"ANIMALS[{species}]: 'breeds' must be true or false")
        if float(spec.get("lifespan", 0)) <= float(spec.get("matures", 0)):
            errors.append(f"ANIMALS[{species}]: lifespan must be longer than matures")
        life_fields = ("gestation_days", "litter", "breeding_interval_days", "birth_male_share")
        if spec.get("breeds"):
            for field in life_fields:
                if field not in spec:
                    errors.append(f"ANIMALS[{species}]: a breeding species needs '{field}'")
            if all(field in spec for field in life_fields):
                if float(spec["gestation_days"]) < 1:
                    errors.append(f"ANIMALS[{species}]: gestation_days must be at least 1")
                if int(spec["litter"]) != spec["litter"] or spec["litter"] < 1:
                    errors.append(f"ANIMALS[{species}]: litter must be a whole number of at least 1")
                if float(spec["breeding_interval_days"]) < float(spec["gestation_days"]):
                    errors.append(f"ANIMALS[{species}]: breeding_interval_days is shorter than gestation_days")
                if not 0.0 <= float(spec["birth_male_share"]) <= 1.0:
                    errors.append(f"ANIMALS[{species}]: birth_male_share must be between 0 and 1")
            approx = spec.get("approx", [])
            if not isinstance(approx, list) or any(field not in life_fields for field in approx):
                errors.append(f"ANIMALS[{species}]: 'approx' must list only life-cycle fields {list(life_fields)}")
        else:
            present = [field for field in life_fields + ("approx",) if field in spec]
            if present:
                errors.append(f"ANIMALS[{species}]: a species that does not breed has no {present}")
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
    # Phase 005: a household's heating burns the typed fuel slot, which must have members to burn (a pack
    # with no fuel economy sets base_burn 0 and need not name one).
    if float(HEATING["base_burn"]) > 0 and (HEATING["fuel_type"] not in INPUT_TYPES or not type_members(HEATING["fuel_type"])):
        errors.append(f"HEATING: fuel_type '{HEATING['fuel_type']}' is not an INPUT_TYPE with any member item")
    if float(HEATING["base_burn"]) < 0 or float(HEATING["unheated_chill"]) < 0:
        errors.append("HEATING: base_burn and unheated_chill must not be negative")
    # Phase 006: the household-work scoring table. Its thresholds and weights are non-negative, and its
    # night-soil kind is an item that any open recipe consuming it names (so a pack with no night soil
    # and no such recipe is still clean).
    for key in ("fuel_low_units", "night_soil_high_units"):
        if float(HOUSEHOLD_WORK[key]) <= 0:
            errors.append(f"HOUSEHOLD_WORK: {key} must be above zero")
    for key, weight in HOUSEHOLD_WORK["weights"].items():
        if float(weight) < 0:
            errors.append(f"HOUSEHOLD_WORK: weight '{key}' must not be negative")
    if set(HOUSEHOLD_WORK["weights"]) != {"fuel_cold", "fuel_low", "night_soil_high"}:
        errors.append("HOUSEHOLD_WORK: weights must name fuel_cold, fuel_low and night_soil_high")
    for r in RECIPES:
        if r.get("open") and any(kind == HOUSEHOLD_WORK["night_soil_kind"] for kind, _ in r["in"]) \
                and HOUSEHOLD_WORK["night_soil_kind"] not in ITEMS:
            errors.append(f"HOUSEHOLD_WORK: night_soil_kind '{HOUSEHOLD_WORK['night_soil_kind']}' "
                          f"is not an ITEM, but open recipe '{r['name']}' consumes it")
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
    _check_gathering_sites(errors, warnings, info)
    _check_burial(errors, warnings, info)
    _check_prompt_instructions(errors, warnings, info)
    _check_refusal_reasons(errors, warnings, info)
    _check_handovers(errors, warnings, info)
    _check_hearing(errors, warnings, info)
    _check_exhaustion(errors, warnings, info)
    _check_health(errors, warnings, info)
    from domains.interoception_check import check_interoception  # Phase 069: the body's feelings (anatomy, sounds, sources)
    check_interoception(_WORLD_PACK.path, errors, warnings, info)
    _check_marks(errors, warnings, info)   # Phase 063: visible marks and their causes
    _check_intoxication(errors, warnings, info)
    _check_aftereffects(errors, warnings, info)
    _check_illness(errors, warnings, info)
    _check_births(errors, warnings, info)   # Phase 044: pregnancy and birth (BIRTHS)
    _check_dependants(errors, warnings, info)   # Phase 045: infants, dependants and growth (DEPENDANTS)
    from domains.detraining_check import check_detraining  # Phase 046: DETRAIN and BODY_AGE
    check_detraining(_WORLD_PACK.path, errors, warnings, info)
    _check_contest(errors, warnings, info)
    _check_resolution(errors, warnings, info)
    _check_joint_tasks(errors, warnings, info)
    _check_training(errors, warnings, info)
    _check_locks(errors, warnings, info)
    _check_coin_storage(errors, warnings, info)   # Phase 041: coin stored in containers and purses
    _check_doors(errors, warnings, info)   # Phase 039: building doors (BUILDINGS[...].door)
    _check_food_grading(errors, warnings, info)
    _check_nutrition(errors, warnings, info)
    _check_generated_seeds(errors)
    _check_fiscal(errors, warnings, info)
    from domains.lexicon_check import check_lexicon      # Phase 051: the words for numbers and statuses
    check_lexicon(_WORLD_PACK.path, errors, warnings, info)
    from domains.prompt_packet_check import check_prompt_packet  # Phase 054: the LLM prompt packet and reply schema
    check_prompt_packet(_WORLD_PACK.path, errors, warnings, info)
    from domains.persona_check import check_persona      # Phase 058: routines, traits, founding ties
    check_persona(_WORLD_PACK.path, errors, warnings, info)
    from domains.autopilot_check import check_autopilot  # Phase 059: the autopilot's consult rules
    check_autopilot(_WORLD_PACK.path, errors, warnings, info)
    from domains.agent_view_check import check_agent_view  # Phase 052: the agent view's whitelist and words
    check_agent_view(_WORLD_PACK.path, errors, warnings, info)
    from domains.narration_check import check_narration  # Phase 057: the terminal interface's sentence templates
    check_narration(_WORLD_PACK.path, errors, warnings, info)
    from domains.tui_check import check_tui  # Phase 067: the terminal modes' map art and text sentences
    check_tui(_WORLD_PACK.path, errors, warnings, info)
    from domains.fog_check import check_fog  # Phase 053: the fog of the map, in three levels
    check_fog(_WORLD_PACK.path, errors, warnings, info)
    from domains.speech_acts_check import check_speech_acts  # Phase 060: the speech acts and their templates
    check_speech_acts(_WORLD_PACK.path, errors, warnings, info)
    from domains.perception_check import check_perception  # Phase 062: the perceiver's tiers, gates and switch
    check_perception(_WORLD_PACK.path, errors, warnings, info)
    from domains.reading_check import check_reading  # Phase 064: the reading and numeracy tables
    check_reading(_WORLD_PACK.path, errors, warnings, info)
    from domains.impairment_check import check_impairment  # Phase 065: the impairment sources, rows and neighbours
    check_impairment(_WORLD_PACK.path, errors, warnings, info)
    from domains.speech_parser_check import check_speech_parser  # Phase 061: the speech parser table and its prefix
    check_speech_parser(_WORLD_PACK.path, errors, warnings, info)
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
    protein = protein_balance(BALANCE_SCENARIO)
    if protein is not None and protein[1] > 0 and protein[0] < protein[1]:
        issues.append(f"DEFICIT protein: the staple supplies {protein[0]:.1f} g per period against a need of "
                      f"{protein[1]:.1f} g ({protein[0] / protein[1]:.0%} covered)")
    for crop, spec in CROPS.items():
        if float(spec.get("seed_return", 1.0)) <= 1.0 and crop in BALANCE_SCENARIO.get("beds", {}):
            issues.append(f"BREAK-EVEN seed for {crop}: a harvest returns {spec.get('seed_return', 1.0)} seed per "
                          f"seed sown, so every bed lost to wilting shrinks the seed stock for good")
    # recipes that cost much more than the cheapest way to make the same thing
    for r in RECIPES:
        out, oq = r["out"]
        if float(oq) <= 0:
            continue                        # Phase 010: a burial has no product, so it has no unit cost
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
