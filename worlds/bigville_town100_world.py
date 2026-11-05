"""BigvilleTown100World -- the founding town's map and cast: the 100-resident bigville (blocks
305000-309000), a full cast pre-seeded with jobs / houses / role-identity / drawn params, on an
EXPANDED map (a bigger grid with houses, workplaces, resource sites and roads).

ALL FOUNDING CONTENT IS DATA (Phase 016a). The pack of the world supplies it:
  * population/founding_cast.json, founding_names.json, founding_personality.json -- the roles and
    their counts, class and literacy shares, anchor names, name pools, personality ranges, and the
    causal-resolution mixture, each with its source or an APPROX mark.
  * world/founding_map.json, world/founding_sites.json -- the map's roads, resource bodies, square,
    farm plots, workplace anchors, building sites, place labels, and anchor fallbacks, plus the
    deposits the map places.
This module keeps the mechanics only. A pack with no founding town (empty tables) has no map here.

WHAT THIS DELIVERS (BIGVILLE_CAST100_PREREG.md)
-----------------------------------------------
  * ``build_town_100(seed, entities)`` -- a map builder (build_town() is UNTOUCHED): a connected PATH
    road lattice; a WATER lake / FOREST (TREE) patch / QUARRY (WALL) rock face as the three resource
    bodies; a central market SQUARE; named workplace plots; a farm-plot pool; and one home plot per
    founding resident. Homes, workplaces and deposits are all chosen from the SINGLE LARGEST walkable
    connected component, so mutual reachability is guaranteed by construction.
  * ``generate_cast100(layout, seed, entities)`` -- DISTINCT Pratchett-register residents. role_identity
    is drawn per-resident from Normal(role_mean,role_sd) (owners/tradesmen high & sticky, labourers low
    & mobile -- R4's switching friction); personality/emotion params are DRAWN from seeded Normals
    (never cloned); literacy ~ Bernoulli (class-biased); class in {rich,middle,poor}.
  * ``BigvilleTown100World`` -- boots the town on the new map, mints the deposits, the tradesmen Shops
    and a Store via the R1-R3 economy adapter (imported, not copied), and mints the ``Resident`` nodes
    with ``home_at`` / ``works_at`` edges to nav cells.

ARCHITECTURE-RULE COMPLIANCE (standalone Bigville architecture notes)
-------------------------------------------------------------------
Pure SEED-BUILDER + WORLD-ADAPTER work: the cast and the map are graph DATA
(nodes/edges/tiles). There is NO agent decision logic here -- no rule engine, no
if/else over an agent's graph valuation. The Deposit/Shop/growback/extract/
transform behaviour all lives in the economy's seed rules; this file only mints
data and reads it back. The expanded map is injected by temporarily rebinding the
module-level ``build_town`` symbol during super().__init__ (mechanical world setup;
``build_town`` itself is never edited), so the whole nav/economy stack builds on
the founding map. The small-cast drama nodes coexist harmlessly as separate nodes.

Deterministic: every draw comes from ``numpy.default_rng(seed)`` streams.
No Rust; no .so rebuild.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "runners", "dsl", "python") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "runners", "dsl", "python"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import worlds.bigville_sim_world as _sim                              # noqa: E402
from worlds.bigville_sim_world import (                              # noqa: E402
    GRASS, PATH, FLOOR, SQUARE, TREE, SOLID, TILE_NAME)
from worlds.bigville_trade_world import BigvilleTradeWorld           # noqa: E402
from domains.data_view import entities as _entities_view           # noqa: E402
from bigville.scenarios import load_scenario                        # noqa: E402
from worlds.bigville_world import requested_data_pack               # noqa: E402

SEED_DEFAULT = 305000

# Names drawn from the seeded permutation before the anchor names are excluded (the cast of 100 needs
# fewer; the draw size is part of the stream, so it is code, not data).
NAME_POOL_DRAW = 200

# resource body -> the tile that IS the body (deposit sits on a walkable cell
# orthogonally adjacent to one of these), from the entity data's RESOURCE_DEPOSITS.
_TILE_BY_NAME = {name: tile for tile, name in TILE_NAME.items()}


def _body_tile(entities, kind):
    """The map tile that is the resource body of deposit `kind`, from one pack's RESOURCE_DEPOSITS."""
    return _TILE_BY_NAME[entities.RESOURCE_DEPOSITS[kind]["tile"]]


def _founding_view(entities, what):
    """The entity view to build from: the given one, or the default pack's. Raises if the pack has no
    founding town (its founding tables are empty), because there is no town to build."""
    view = entities if entities is not None else _entities_view()
    if not view.FOUNDING_JOBS or not view.FOUNDING_MAP:
        raise ValueError(f"{what} builds a founding town, and this data pack has none "
                         f"(FOUNDING_JOBS or FOUNDING_MAP is empty)")
    return view


# ============================================================ map builder
def _rect(grid, x0, y0, x1, y1, code):
    for y in range(max(0, y0), min(len(grid), y1 + 1)):
        for x in range(max(0, x0), min(len(grid[0]), x1 + 1)):
            grid[y][x] = code


def _walkable(grid, x, y):
    return 0 <= x < len(grid[0]) and 0 <= y < len(grid) and grid[y][x] not in SOLID


def _largest_component(grid):
    """The single largest orthogonally-connected set of walkable cells."""
    seen, best = set(), set()
    H, W = len(grid), len(grid[0])
    for sy in range(H):
        for sx in range(W):
            if not _walkable(grid, sx, sy) or (sx, sy) in seen:
                continue
            comp, stack = set(), [(sx, sy)]
            seen.add((sx, sy))
            while stack:
                cx, cy = stack.pop()
                comp.add((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if _walkable(grid, nx, ny) and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            if len(comp) > len(best):
                best = comp
    return best


def _largest_surface_component(grid, surfaces):
    """Return the largest 4-connected component of a named road surface."""
    seen, best = set(), set()
    H, W = len(grid), len(grid[0])
    for sy in range(H):
        for sx in range(W):
            if grid[sy][sx] not in surfaces or (sx, sy) in seen:
                continue
            comp, stack = set(), [(sx, sy)]
            seen.add((sx, sy))
            while stack:
                cx, cy = stack.pop()
                comp.add((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if (0 <= nx < W and 0 <= ny < H and grid[ny][nx] in surfaces
                            and (nx, ny) not in seen):
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            if len(comp) > len(best):
                best = comp
    return best


def _adj_road(grid, x, y):
    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if 0 <= nx < len(grid[0]) and 0 <= ny < len(grid) and grid[ny][nx] in (PATH, SQUARE):
            return True
    return False


def _adj_body(grid, x, y, tile):
    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if 0 <= nx < len(grid[0]) and 0 <= ny < len(grid) and grid[ny][nx] == tile:
            return True
    return False


def _carve_path(grid, x, y):
    """Put one road cell down without erasing a solid resource body."""
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x] not in SOLID:
        grid[y][x] = PATH


def _windy_horizontal(grid, target_y, phase, offsets, run):
    """Carve a gently meandering east/west route and return x->y positions. `offsets` is the
    meander pattern (one step per `run` cells, starting `phase` steps into it)."""
    route, y = {}, target_y
    for x in range(1, len(grid[0]) - 1):
        previous_y = y
        desired = target_y + offsets[((x // run) + phase) % len(offsets)]
        if desired > y:
            y += 1
        elif desired < y:
            y -= 1
        y = max(1, min(len(grid) - 2, y))
        # A bend must contain an orthogonal elbow.  Without this, a one-cell
        # drift from (x-1, previous_y) to (x, y) touches only at a corner and
        # breaks both walking connectivity and the rendered path continuity.
        for corner_y in range(min(previous_y, y), max(previous_y, y) + 1):
            _carve_path(grid, x, corner_y)
        route[x] = y
    return route


def _windy_vertical(grid, target_x, phase, offsets, run):
    """Carve a gently meandering north/south route and return y->x positions. `offsets` is the
    meander pattern (one step per `run` cells, starting `phase` steps into it)."""
    route, x = {}, target_x
    for y in range(1, len(grid) - 1):
        previous_x = x
        desired = target_x + offsets[((y // run) + phase) % len(offsets)]
        if desired > x:
            x += 1
        elif desired < x:
            x -= 1
        x = max(1, min(len(grid[0]) - 2, x))
        for corner_x in range(min(previous_x, x), max(previous_x, x) + 1):
            _carve_path(grid, corner_x, y)
        route[y] = x
    return route


def _link_path_cells(grid, start, end):
    """Join two nearby route cells with a short orthogonal dogleg."""
    x, y = start
    target_x, target_y = end
    step = 1 if target_x >= x else -1
    while x != target_x:
        _carve_path(grid, x, y)
        x += step
    step = 1 if target_y >= y else -1
    while y != target_y:
        _carve_path(grid, x, y)
        y += step
    _carve_path(grid, x, y)


def _nearest(cells, target):
    tx, ty = target
    return min(cells, key=lambda c: (c[0] - tx) ** 2 + (c[1] - ty) ** 2)


def build_town_100(seed=SEED_DEFAULT, entities=None):
    """Return (grid, affordances, layout). Deterministic in `seed` and in the founding map of
    `entities` (default: the default pack). build_town() (the 30x18 town) is untouched -- this is a
    separate builder."""
    E = _founding_view(entities, "build_town_100")
    M = E.FOUNDING_MAP
    W, H = M["width"], M["height"]
    run = M["bend_run"]
    grid = [[GRASS for _ in range(W)] for _ in range(H)]

    # --- connected winding road network ---------------------------------------
    # Keep the roads as a small set of useful village routes rather than a
    # near-grid of surfaced cells. Each run drifts by a few cells and is linked
    # at near-intersections, leaving the surrounding plots and commons legible.
    hrows = [route["row"] for route in M["road_rows"]]
    vcols = [route["col"] for route in M["road_cols"]]
    horizontal_routes = [
        _windy_horizontal(grid, route["row"], route["phase"], M["bend_offsets_horizontal"], run)
        for route in M["road_rows"]
    ]
    vertical_routes = [
        _windy_vertical(grid, route["col"], route["phase"], M["bend_offsets_vertical"], run)
        for route in M["road_cols"]
    ]
    # Link the nearest points around each nominal junction. The junctions are
    # deliberately short doglegs rather than a second rigid lattice.
    for hroute, hrow in zip(horizontal_routes, hrows):
        for vroute, vcol in zip(vertical_routes, vcols):
            _link_path_cells(grid, (vcol, hroute[vcol]),
                             (vroute[hrow], hrow))

    # --- central market square (walkable) --------------------------------------
    sq = M["square"]
    _rect(grid, sq["x"], sq["y"], sq["x"] + sq["w"] - 1, sq["y"] + sq["h"] - 1, SQUARE)

    # --- the resource bodies (SOLID; deposits sit on walkable edges) -------------
    for body in M["resource_bodies"]:
        x0, y0, x1, y1 = body["rect"]
        _rect(grid, x0, y0, x1, y1, _TILE_BY_NAME[body["tile"]])
    # a few scattered trees for flavour (occluders; do not disconnect the lattice)
    for (tx, ty) in M["scattered_trees"]:
        if grid[ty][tx] == GRASS:
            grid[ty][tx] = TREE

    # A resource body can interrupt a route at the edge of the map.  Keep the
    # intentional road network as one 4-connected surface and discard only
    # isolated stubs; this prevents diagonal-only or floating path fragments.
    road = _largest_surface_component(grid, {PATH, SQUARE})
    for y, row in enumerate(grid):
        for x, tile in enumerate(row):
            if tile == PATH and (x, y) not in road:
                grid[y][x] = GRASS

    comp = _largest_component(grid)

    # --- deposits: a walkable comp cell adjacent to each body -------------------
    layout = {"w": W, "h": H, "deposits": {}, "work": {}, "farms": [], "homes": [],
              "building_sites": {k: tuple(v) for k, v in E.FOUNDING_BUILDING_SITES.items()},
              "square": {"x": sq["x"], "y": sq["y"], "w": sq["w"], "h": sq["h"],
                         "center": tuple(sq["center"])}}
    ordered = sorted(comp)
    for kind in E.FOUNDING_DEPOSITS:
        cell = next(c for c in ordered if _adj_body(grid, c[0], c[1], _body_tile(E, kind)))
        layout["deposits"][kind] = cell
        layout["work"][kind] = cell            # fisher/forester/quarrier work here

    # --- candidate plots: road-adjacent GRASS cells in the big component --------
    cand = [c for c in ordered
            if grid[c[1]][c[0]] == GRASS and _adj_road(grid, c[0], c[1])]
    used = set(layout["deposits"].values())

    def _take(target):
        pool = [c for c in cand if c not in used]
        c = _nearest(pool, target)
        used.add(c)
        grid[c[1]][c[0]] = FLOOR
        return c

    # named workplaces (near their anchors, coherent core)
    for name, anchor in E.FOUNDING_WORKPLACES.items():
        layout["work"][name] = _take(tuple(anchor))
    # farm plots (the founding field grid)
    fp = M["farm_plots"]
    for k in range(fp["count"]):
        layout["farms"].append(_take((fp["origin"][0] + (k % fp["columns"]) * fp["column_step"],
                                      fp["origin"][1] + (k // fp["columns"]) * fp["row_step"])))
    # one home per founding resident (residential -- remaining road-adjacent plots, deterministic order)
    n_homes = len(E.plan_founding_town(seed)["kin"]["households"])   # one home per household
    home_pool = [c for c in cand if c not in used]
    if len(home_pool) < n_homes:
        raise ValueError("not enough home plots: %d for %d residents" % (len(home_pool), n_homes))
    for c in home_pool[:n_homes]:
        used.add(c)
        grid[c[1]][c[0]] = FLOOR
        layout["homes"].append(c)

    # affordances (viewer-facing landmark list)
    market = layout["work"]["market"]
    affordances = [{"name": sq["label"], "kind": "square", "x": market[0], "y": market[1]}]
    for kind, label in E.FOUNDING_PLACE_LABELS.items():
        cx, cy = layout["work"][kind]
        affordances.append({"name": label, "kind": kind, "x": cx, "y": cy})
    for kind in layout["deposits"]:          # the deposits the founding map placed
        cx, cy = layout["deposits"][kind]
        affordances.append({"name": "%s deposit" % kind, "kind": "deposit_%s" % kind,
                            "x": cx, "y": cy})
    layout["component_size"] = len(comp)
    return grid, affordances, layout


# ============================================================ cast generator
# The real precision this whole generator ever commits to for a drawn
# trait -- named so any downstream consumer (e.g. ocelot's affect-coupling
# log-weight SCALE derivation) can read the ACTUAL source precision
# instead of restating "4" as its own separate, driftable literal.
DRAW_CLIP_DECIMALS = 4


def _personality_spec(entities=None):
    """{key: (mean, sd, lo, hi)} from a pack's FOUNDING_PERSONALITY: the tuple shape the cast generator
    used before Phase 016a. The generator reads the pack table. This view exists for callers that read
    the private name (the Ocelot adapter's affect-coupling references, and other checkouts)."""
    E = entities if entities is not None else _entities_view()
    return {k: (s["mean"], s["sd"], s["lo"], s["hi"]) for k, s in E.FOUNDING_PERSONALITY.items()}


_PARAM_SPEC = _personality_spec()     # compatibility view of the default pack


def _draw_clip(rng, mean, sd, lo, hi):
    v = float(rng.normal(mean, sd))
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return round(v, DRAW_CLIP_DECIMALS)


def _name_pool(n, rng, first=None, last=None):
    """A deterministic pool of `n` DISTINCT full names from the first x last product. The name lists
    default to the default pack's founding names."""
    if first is None or last is None:
        E = _entities_view()
        first = E.FOUNDING_FIRST_NAMES if first is None else first
        last = E.FOUNDING_LAST_NAMES if last is None else last
    names, seen = [], set()
    nl = len(last)
    order = rng.permutation(len(first) * nl)   # shuffle the full first x last product
    for idx in order:
        a, b = int(idx) // nl, int(idx) % nl
        nm = "%s %s" % (first[a], last[b])
        if nm not in seen:
            seen.add(nm)
            names.append(nm)
            if len(names) >= n:
                return names
    return names


def _draw_resolution_bins(rng, mixture=None):
    """One resident's trait-level causal-belief resolution (bin COUNT,
    integer -- the in-frame stored datum). The draw is a two-component
    mixture in continuous space (the cross-frame generative map); rounding
    and clamping is the map back onto the in-frame integer lattice. The
    mixture's constants and their sources are FOUNDING_CAUSAL_RESOLUTION
    (population/founding_personality.json); None means the default pack's.
    """
    if mixture is None:
        mixture = _entities_view().FOUNDING_CAUSAL_RESOLUTION
    if rng.random() < mixture["ceiling_weight"]:
        z = rng.normal(mixture["ceiling"]["mean"], mixture["ceiling"]["sd"])
    else:
        z = rng.normal(mixture["floor"]["mean"], mixture["floor"]["sd"])
    return int(min(mixture["hi"], max(mixture["lo"], round(z))))


def generate_cast100(layout, seed=SEED_DEFAULT, entities=None):
    """The founding cast as records, one per founding resident. Deterministic in `seed` and in the
    founding pack of `entities` (default: the default pack).

    Phase 016b: the roles and their counts come from E.seed_jobs (a resident's role is their first job),
    and the ages, households, and genealogy from E.plan_founding_town (one seed, its own streams). Each
    household shares one home cell. Names, class, literacy, and personality params draw from their own
    streams, as at HEAD. A job's workplace, group, and role identity come from its FOUNDING_JOBS row."""
    E = _founding_view(entities, "generate_cast100")
    rng = np.random.default_rng(seed)
    nrng = np.random.default_rng(seed + 7)     # separate stream for names
    rrng = np.random.default_rng(seed + 13)    # separate stream for the resolution_bins trait (see
                                                # DRAW_CLIP_DECIMALS): the other params stay byte-unchanged

    plan = E.plan_founding_town(seed)
    staffing = plan["staffing"]["residents"]
    ages = plan["ages"]
    households = plan["kin"]["households"]
    membership = {}
    for hh in households:
        for member in hh["members"]:
            if member == hh["head"]:
                membership[member] = (hh["index"], "head")
            elif member == hh["spouse"]:
                membership[member] = (hh["index"], "spouse")
            elif member in hh["children"]:
                membership[member] = (hh["index"], "child")
            else:
                membership[member] = (hh["index"], "sibling")

    # reserve anchor names; fill the rest from the generated pool
    anchor_names = E.FOUNDING_ANCHOR_NAMES                 # job -> name
    reserved = set(anchor_names.values())
    pool = [nm for nm in _name_pool(NAME_POOL_DRAW, nrng, E.FOUNDING_FIRST_NAMES, E.FOUNDING_LAST_NAMES)
            if nm not in reserved]
    pi = 0

    by_group = E.FOUNDING_CLASS["by_group"]          # group -> {rich, middle}; poor is the remainder
    lit_by_class = E.FOUNDING_CLASS["literacy_by_class"]
    cap_by_literacy = E.FOUNDING_CLASS["capability_by_literacy"]
    ri_bounds = E.FOUNDING_DRAW_BOUNDS["role_identity"]

    farms = layout["farms"]
    homes = layout["homes"]
    residents = []
    named_jobs = set()
    farm_cursor = 0
    for idx, staff in enumerate(staffing):
        job = staff["jobs"][0]
        row = E.FOUNDING_JOBS[job]
        group, wkind = row["group"], row["workplace"]
        # name: the anchor for the job's first holder, else the next pooled name
        if job in anchor_names and job not in named_jobs:
            name = anchor_names[job]
            named_jobs.add(job)
        else:
            if pi >= len(pool):
                raise ValueError("the founding name pool is too small for the cast")
            name = pool[pi]
            pi += 1
        # role identity (the R4 switching friction) -- drawn, not cloned
        ri = _draw_clip(rng, row["role_identity_mean"], row["role_identity_sd"],
                        ri_bounds["lo"], ri_bounds["hi"])
        # class + literacy
        u = float(rng.random())
        rp, mp = by_group[group]["rich"], by_group[group]["middle"]
        klass = "rich" if u < rp else ("middle" if u < rp + mp else "poor")
        literate = 1 if float(rng.random()) < lit_by_class[klass] else 0
        # drawn personality/emotion params
        params = {k: _draw_clip(rng, s["mean"], s["sd"], s["lo"], s["hi"])
                  for k, s in E.FOUNDING_PERSONALITY.items()}
        # trait-level causal-belief resolution (bin count) -- a 13th, MIXTURE-drawn param, from its own stream
        params["resolution_bins"] = _draw_resolution_bins(rrng, E.FOUNDING_CAUSAL_RESOLUTION)
        # workplace cell
        if wkind == "farm":
            work = farms[farm_cursor % len(farms)]
            farm_cursor += 1
        else:
            work = layout["work"][wkind]
        # skill: the job's first trade's base skill (TRADES), the default where the trade has none
        skill_trade = E.JOBS[job]["trades"][0]
        skill = float(E.TRADES.get(skill_trade, {}).get("base_skill", E.ACTOR_DEFAULTS["skill"]))
        hh_index, hh_role = membership[idx]
        residents.append({
            "index": idx, "name": name, "role": job, "group": group,
            "role_identity": ri, "class": klass, "literacy": literate,
            "age": ages[idx], "jobs": list(staff["jobs"]),
            "trades": [t for t in E.JOBS[job]["trades"] if t != job],
            "skill": skill,
            "capability": float(cap_by_literacy["literate" if literate else "unlettered"]),
            "household": hh_index, "household_role": hh_role,
            "home_cell": list(homes[hh_index]), "workplace_cell": list(work),
            "workplace_kind": wkind, "params": params})
    household_records = []
    for hh in households:
        household_records.append({
            "index": hh["index"], "head": residents[hh["head"]]["name"],
            "members": [residents[m]["name"] for m in hh["members"]],
            "home_cell": list(homes[hh["index"]]),
            "size_drawn": hh["size_drawn"], "extended_drawn": hh["extended_drawn"],
            "kin_drawn": hh["kin_drawn"], "extended": hh["extended"]})
    return {
        "id": "bigville_cast100", "version": "1.0.0", "self_load_only": True,
        "depends_on": [],
        "description": ("100-resident bigville cast: jobs (E.seed_jobs), ages, households and "
                        "drawn-Normal params on the build_town_100 map. Deterministic in seed=%d." % seed),
        "seed": seed,
        "map": {"w": layout["w"], "h": layout["h"],
                "component_size": layout["component_size"],
                "deposits": {k: list(v) for k, v in layout["deposits"].items()}},
        "households": household_records,
        "residents": residents}


def write_cast_seed(path=None, seed=SEED_DEFAULT):
    """Emit the committed cast seed JSON. Deterministic -- regenerating and
    re-writing produces a byte-identical file."""
    if path is None:
        path = os.path.join(_ROOT, "seeds", "bigville_cast100.json")
    _, _, layout = build_town_100(seed)
    cast = generate_cast100(layout, seed)
    with open(path, "w") as f:
        json.dump(cast, f, indent=1, sort_keys=True)
        f.write("\n")
    return path


# ============================================================ the world
class BigvilleTown100World(BigvilleTradeWorld):
    """Boots the 100-resident town on the expanded map + mints deposits/shops/
    residents. A world adapter -- data + I/O only, no agent decision."""

    def __init__(self, seed=SEED_DEFAULT, *, data_pack=None, **kw):
        self.t100_seed = seed
        # The town's entity data comes from one pack (the constructor's data_pack, or the scenario's).
        # The map's bodies are read from it before super().__init__, which builds the base worlds
        # (none of which read entity tables).
        scenario = kw.get("scenario")
        scenario_data = load_scenario(scenario).to_dict() if scenario is not None else None
        self.data_pack = requested_data_pack(data_pack, scenario_data)
        self.E = _entities_view(self.data_pack)
        if not self.E.FOUNDING_JOBS or not self.E.FOUNDING_MAP:
            raise ValueError(f"BigvilleTown100World builds a pack's founding town; data pack "
                             f"'{self.data_pack}' has none (FOUNDING_JOBS or FOUNDING_MAP is empty)")
        # The map places these deposits and the town's fixed workplaces (see build_town_100).
        # A pack without them cannot host this town.
        missing = [kind for kind in self.E.FOUNDING_DEPOSITS if kind not in self.E.RESOURCE_DEPOSITS]
        if missing:
            raise ValueError(f"BigvilleTown100World places the deposits {list(self.E.FOUNDING_DEPOSITS)}; "
                             f"data pack '{self.data_pack}' has no {missing}")
        grid, aff, layout = build_town_100(seed, self.E)
        self.t100_layout = layout
        # inject the expanded map by rebinding build_town for the super().__init__
        # chain (mechanical world setup; build_town itself is never edited).
        _orig = _sim.build_town
        _sim.build_town = lambda g=grid, a=aff: ([row[:] for row in g], list(a))
        try:
            super().__init__(**kw)
        finally:
            _sim.build_town = _orig

        # --- economy: the founding deposits + tradesmen shops + a market store -----
        for kind, cell in layout["deposits"].items():
            deposit = self.E.RESOURCE_DEPOSITS[kind]
            self.add_deposit(kind, tuple(cell), stock=float(deposit["stock"]),
                             growback=float(deposit["growback"]), capacity=float(deposit["capacity"]))
        self.add_store(tuple(layout["work"]["market"]), list(self.E.FOUNDING_DEPOSITS))
        for trade, chain in self.E.SHOP_CHAINS.items():
            self.add_shop(trade, tuple(layout["work"][trade]),
                          input_kind=chain["in"], output_kind=chain["out"])

        # --- the residents (graph data) -------------------------------------------
        self.cast = generate_cast100(layout, seed, self.E)
        self.residents = {}          # name -> Resident nid
        for r in self.cast["residents"]:
            attrs = {"name": r["name"], "role": r["role"], "group": r["group"],
                     "role_identity": float(r["role_identity"]),
                     "klass": r["class"], "literacy": float(r["literacy"]),
                     "home_x": float(r["home_cell"][0]), "home_y": float(r["home_cell"][1]),
                     "work_x": float(r["workplace_cell"][0]),
                     "work_y": float(r["workplace_cell"][1]),
                     "workplace_kind": r["workplace_kind"]}
            attrs.update({k: float(v) for k, v in r["params"].items()})
            nid = self.eng.add_node("Resident", attrs)
            hc = self._cell_at.get(tuple(r["home_cell"]))
            wc = self._cell_at.get(tuple(r["workplace_cell"]))
            if hc is not None:
                self.eng.add_edge_unchecked(nid, "home_at", hc)
            if wc is not None:
                self.eng.add_edge_unchecked(nid, "works_at", wc)
            self.residents[r["name"]] = nid

    # ------------------------------------------------- glass-box read-offs
    def resident_records(self):
        return list(self.cast["residents"])

    def reachable(self, a, b):
        """BFS over the walkable nav graph (self._cell_at adjacency): is `b`
        reachable from `a`? Mechanical query (no decision)."""
        a, b = tuple(a), tuple(b)
        if a not in self._cell_at or b not in self._cell_at:
            return False
        seen, stack = {a}, [a]
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) == b:
                return True
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if (nx, ny) in self._cell_at and (nx, ny) not in seen:
                    seen.add((nx, ny))
                    stack.append((nx, ny))
        return b in seen
