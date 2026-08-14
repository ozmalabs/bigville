"""BigvilleTown100World -- the 100-resident bigville (blocks 305000-309000):
a full cast pre-seeded with jobs / houses / role-identity / drawn params, on an
EXPANDED map (a bigger grid with houses, workplaces, resource sites and roads).

WHAT THIS DELIVERS (BIGVILLE_CAST100_PREREG.md)
-----------------------------------------------
  * ``build_town_100(seed)`` -- a NEW map builder (build_town() is UNTOUCHED):
    a connected PATH road lattice; a WATER lake / FOREST (TREE) patch / QUARRY
    (WALL) rock face as the three resource bodies; a central market SQUARE; ~20
    named workplace plots; a farm-plot pool; and >=100 home plots. Homes,
    workplaces and deposits are all chosen from the SINGLE LARGEST walkable
    connected component, so mutual reachability is guaranteed by construction.
  * ``generate_cast100(layout, seed)`` -- 100 DISTINCT Pratchett-register
    residents. role_identity is drawn per-resident from Normal(role_mean,role_sd)
    (owners/tradesmen high & sticky, labourers low & mobile -- R4's switching
    friction); personality/emotion params are DRAWN from seeded Normals (never
    cloned); literacy ~ Bernoulli (class-biased); class in {rich,middle,poor}.
  * ``BigvilleTown100World`` -- boots the town on the new map, mints the three
    fish/lumber/stone Deposits + the tradesmen Shops + a Store via the R1-R3
    economy adapter (imported, not copied), and mints the 100 ``Resident`` nodes
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
the 52x40 grid. The small-cast drama nodes coexist harmlessly as separate nodes.

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
    GRASS, PATH, WALL, FLOOR, SQUARE, TREE, WATER, SOLID, TILE_NAME)
from worlds.bigville_trade_world import BigvilleTradeWorld           # noqa: E402

W100, H100 = 52, 40
SEED_DEFAULT = 305000

# resource body -> the tile that IS the body (deposit sits on a walkable cell
# orthogonally adjacent to one of these).
_BODY_TILE = {"fish": WATER, "lumber": TREE, "stone": WALL}

# ---------------------------------------------------------------- the role model
# (role, count, group, ri_mean, ri_sd, workplace_kind). Sums to 100.
ROLE_SPEC = [
    # LOW / labourers -- mobile, low role-identity (R4 switching friction low)
    ("labourer",      25, "low",    0.22, 0.06, "market"),
    ("farm_labourer", 12, "low",    0.20, 0.06, "farm"),
    ("fisher",         8, "low",    0.28, 0.06, "fish"),
    ("forester",       6, "low",    0.28, 0.06, "lumber"),
    ("quarrier",       5, "low",    0.28, 0.06, "stone"),
    ("servant",        5, "low",    0.25, 0.06, "manor"),
    # MIDDLE -- neither gate group
    ("farmer",        12, "middle", 0.60, 0.08, "farm"),
    ("teacher",        2, "middle", 0.65, 0.07, "school"),
    ("reporter",       1, "middle", 0.60, 0.07, "press"),
    ("clerk",          2, "middle", 0.55, 0.07, "townhall"),
    ("councillor",     4, "middle", 0.62, 0.07, "townhall"),
    ("miller",         1, "middle", 0.58, 0.07, "mill"),
    ("constable",      1, "middle", 0.60, 0.07, "watch"),
    ("midwife",        1, "middle", 0.58, 0.07, "surgery"),
    # HIGH / owners + tradesmen -- sticky, high role-identity
    ("fishmonger",     2, "high",   0.88, 0.04, "fishmonger"),
    ("carpenter",      2, "high",   0.90, 0.04, "carpenter"),
    ("mason",          2, "high",   0.90, 0.04, "mason"),
    ("baker",          2, "high",   0.88, 0.04, "bakery"),
    ("innkeeper",      1, "high",   0.85, 0.04, "inn"),
    ("landlord",       1, "high",   0.93, 0.03, "estate"),
    ("banker",         1, "high",   0.93, 0.03, "bank"),
    ("shopkeeper",     1, "high",   0.90, 0.04, "store"),
    ("mayor",          1, "high",   0.92, 0.03, "townhall"),
    ("pastor",         1, "high",   0.82, 0.05, "church"),
    ("doctor",         1, "high",   0.84, 0.05, "surgery"),
]

# drawn personality/emotion params: key -> (mean, sd, lo, hi) (lo/hi=None -> unclipped)
_PARAM_SPEC = {
    "charm_weight":       (0.50, 0.20, 0.0, 1.0),
    "w_supergraph":       (0.50, 0.20, 0.0, 1.0),
    "w_spite":            (0.15, 0.15, 0.0, 1.0),
    "hostile_weight":     (0.40, 0.20, 0.0, 1.0),
    "mood_bias":          (0.30, 0.20, None, None),
    "cred_on":            (1.00, 0.20, 0.0, None),
    "claim_weight":       (1.00, 0.30, 0.0, None),
    "prior_world_safe":   (0.60, 0.20, 0.0, 1.0),
    "prior_others_trust": (0.60, 0.20, 0.0, 1.0),
    "prior_self_worth":   (0.60, 0.20, 0.0, 1.0),
    "valence":            (0.00, 0.30, -1.0, 1.0),
    "arousal":            (0.40, 0.20, 0.0, 1.0),
}

# ---- trait-level causal-belief RESOLUTION (bin COUNT), MIXTURE draw -------
# Grounded in docs/research/Bigville graph runtime/
# CAUSAL_GRANULARITY_POPULATION_DISTRIBUTION_RESEARCH.md sec7 point 4 + sec8:
# "do not expect, or design around, a single unimodal population curve" --
# the real CRT literature (Frederick 2005 combined N=3428; Stieger & Reips
# 2016 N=2137) shows a real population is a MIXTURE of a floor-heavy/naive
# subgroup and a ceiling-heavy/exposed subgroup, not one bell curve. Draw is
# a two-component Normal mixture in CONTINUOUS space (the cross-frame
# generative map, CLAUDE.md "BASE-AS-DIMENSION" frame/continuum invariant),
# then ROUNDED AND CLAMPED to an integer bin count (the in-frame stored
# datum -- the draw is a map, the storage is a lattice value, never a raw
# float). See BIGVILLE_CAN_INTEGRATION_PREREG.md sec3 for the full citation
# chain behind every constant below.
_RES_FLOOR_MEAN, _RES_FLOOR_SD = 3.0, 1.0   # anchors CRT floor / CAN's own
                                             # already-tested "coarse" (3 J
                                             # values) condition
_RES_CEIL_MEAN, _RES_CEIL_SD = 7.5, 2.0     # anchors Miller(1956)/Preston &
                                             # Colman(2000)'s convergent
                                             # optimum (7), reaching toward
                                             # the deliberately-past-ceiling
                                             # 9-12 band
_RES_CEIL_WEIGHT = 0.35                     # inside Frederick's 17% (combined
                                             # sample perfect-score rate) and
                                             # Stieger & Reips' ~33%
                                             # (educated/exposed subgroup
                                             # perfect-score rate) bracket
_RES_LO, _RES_HI = 2, 12                    # research doc sec8 point1's full
                                             # registered crossover-test range


def _draw_resolution_bins(rng):
    """One resident's trait-level causal-belief resolution (bin COUNT,
    integer -- the in-frame stored datum). The draw is a two-component
    mixture in continuous space (the cross-frame generative map); rounding
    and clamping is the map back onto the in-frame integer lattice."""
    if rng.random() < _RES_CEIL_WEIGHT:
        z = rng.normal(_RES_CEIL_MEAN, _RES_CEIL_SD)
    else:
        z = rng.normal(_RES_FLOOR_MEAN, _RES_FLOOR_SD)
    return int(min(_RES_HI, max(_RES_LO, round(z))))

# key roles keep their canonical register identity (coherence with the drama/econ).
_ANCHOR_NAMES = {"mayor": "John", "pastor": "Mary",
                 "baker": "Marjorie Dough", "fishmonger": "Doreen Ferrety",
                 "banker": "Scrooge"}

# Pratchett-register-style name pools (extends bigville_townspeople_30's flavour).
_FIRST = [
    "Prudence", "Bram", "Adelina", "Hogget", "Ida", "Erasmus", "Bettony", "Tobias",
    "Wat", "Cask", "Gristle", "Agnes", "Peony", "Corvin", "Nettie", "Ambrose",
    "Hesper", "Barnaby", "Ferdinand", "Hannah", "Jem", "Verity", "Mordecai",
    "Lettice", "Silas", "Wilhelmina", "Cuthbert", "Dorcas", "Ephraim", "Grizelda",
    "Horace", "Isolde", "Josiah", "Keturah", "Lemuel", "Millicent", "Nathaniel",
    "Ottoline", "Phineas", "Quentin", "Rosamund", "Septimus", "Tamsin", "Ursula",
    "Vernon", "Winifred", "Zebediah", "Bartholomew", "Constance", "Drusilla",
    "Elowen", "Fenwick", "Godfrey", "Henrietta", "Ignatius", "Jerusha", "Kester",
    "Lavinia", "Merrick", "Obadiah", "Prosper", "Radella", "Sorrel", "Thaddeus",
    "Willa", "Alby", "Bryony", "Cobweb", "Dunstan", "Effie", "Garnet", "Hopkin",
]
_LAST = [
    "Bracken", "Mudge", "Ditchwater", "Turnbull", "Hollow", "Wick", "Bramble",
    "Nettle", "Sallow", "Pennyworth", "Ottermole", "Codling", "Hobb", "Grubb",
    "Wold", "Marsh", "Thistlewood", "Oakes", "Ashby", "Rushton", "Bindle",
    "Catchpole", "Furlong", "Harkness", "Kettle", "Larkspur", "Mossop", "Nubbins",
    "Peaseblossom", "Quirke", "Rundle", "Sedge", "Tremble", "Underhill", "Vellum",
    "Wormwood", "Yarrow", "Cobb", "Dabney", "Everdew", "Frittle", "Gorse",
    "Haywain", "Inkpen", "Jubbins", "Kindle", "Lorric", "Muckle", "Norbisham",
    "Puddifoot", "Ramskin", "Sputterfield", "Tallowick", "Wattle", "Brimble",
]


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


def _nearest(cells, target):
    tx, ty = target
    return min(cells, key=lambda c: (c[0] - tx) ** 2 + (c[1] - ty) ** 2)


# workplace name -> (target coordinate) placed coherently around the core.
_WORK_ANCHORS = {
    "townhall":   (23, 13), "church": (31, 14), "school": (16, 24),
    "bank":       (19, 13), "press":  (28, 13), "store":  (23, 23),
    "inn":        (31, 20), "surgery": (16, 20), "estate": (35, 18),
    "watch":      (20, 26), "mill":   (12, 12), "bakery": (28, 24),
    "fishmonger": (11, 8),  "carpenter": (34, 8), "mason": (45, 14),
    "manor":      (41, 30), "market": (23, 18),
}


def build_town_100(seed=SEED_DEFAULT):
    """Return (grid, affordances, layout). Deterministic in `seed`. build_town()
    (the 30x18 town) is untouched -- this is a separate builder."""
    W, H = W100, H100
    grid = [[GRASS for _ in range(W)] for _ in range(H)]

    # --- connected road lattice (guarantees one big walkable component) --------
    hrows = [6, 10, 14, 18, 22, 26, 30, 34]
    vcols = [5, 11, 17, 23, 29, 35, 41, 47]
    for y in hrows:
        _rect(grid, 1, y, W - 2, y, PATH)
    for x in vcols:
        _rect(grid, x, 1, x, H - 2, PATH)

    # --- central market square (walkable) --------------------------------------
    _rect(grid, 18, 15, 28, 21, SQUARE)

    # --- the three resource bodies (SOLID; deposits sit on walkable edges) ------
    _rect(grid, 2, 2, 10, 5, WATER)     # lake (north-west)
    _rect(grid, 30, 2, 40, 5, TREE)     # forest (north-centre/east)
    _rect(grid, 43, 8, 49, 13, WALL)    # quarry rock face (east)
    # a few scattered trees for flavour (occluders; do not disconnect the lattice)
    for (tx, ty) in [(14, 3), (26, 8), (38, 24), (8, 30), (44, 32), (33, 27)]:
        if grid[ty][tx] == GRASS:
            grid[ty][tx] = TREE

    comp = _largest_component(grid)

    # --- deposits: a walkable comp cell adjacent to each body -------------------
    layout = {"w": W, "h": H, "deposits": {}, "work": {}, "farms": [], "homes": []}
    ordered = sorted(comp)
    for kind, tile in _BODY_TILE.items():
        cell = next(c for c in ordered if _adj_body(grid, c[0], c[1], tile))
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
    for name, anchor in _WORK_ANCHORS.items():
        layout["work"][name] = _take(anchor)
    # farm plots (south-east fields)
    for k in range(8):
        layout["farms"].append(_take((36 + (k % 4) * 3, 26 + (k // 4) * 6)))
    # 100 homes (residential -- remaining road-adjacent plots, deterministic order)
    home_pool = [c for c in cand if c not in used]
    assert len(home_pool) >= 100, "not enough home plots: %d" % len(home_pool)
    for c in home_pool[:100]:
        used.add(c)
        grid[c[1]][c[0]] = FLOOR
        layout["homes"].append(c)

    # affordances (viewer-facing landmark list)
    affordances = [{"name": "Market Square", "kind": "square",
                    "x": layout["work"]["market"][0], "y": layout["work"]["market"][1]}]
    _KINDNAME = {"townhall": "Town Hall", "church": "Church", "school": "School",
                 "bank": "Bank", "press": "The Herald", "store": "General Store",
                 "inn": "The Inn", "surgery": "Surgery", "estate": "Estate Office",
                 "watch": "Watch House", "mill": "Mill", "bakery": "Bakery",
                 "fishmonger": "Fishmonger", "carpenter": "Carpenter",
                 "mason": "Mason", "manor": "Manor"}
    for kind, label in _KINDNAME.items():
        cx, cy = layout["work"][kind]
        affordances.append({"name": label, "kind": kind, "x": cx, "y": cy})
    for kind in ("fish", "lumber", "stone"):
        cx, cy = layout["deposits"][kind]
        affordances.append({"name": "%s deposit" % kind, "kind": "deposit_%s" % kind,
                            "x": cx, "y": cy})
    layout["component_size"] = len(comp)
    return grid, affordances, layout


# ============================================================ cast generator
def _draw_clip(rng, mean, sd, lo, hi):
    v = float(rng.normal(mean, sd))
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return round(v, 4)


def _name_pool(n, rng):
    """A deterministic pool of `n` DISTINCT Pratchett-register full names."""
    names, seen = [], set()
    nl = len(_LAST)
    order = rng.permutation(len(_FIRST) * nl)   # shuffle the full first x last product
    for idx in order:
        a, b = int(idx) // nl, int(idx) % nl
        nm = "%s %s" % (_FIRST[a], _LAST[b])
        if nm not in seen:
            seen.add(nm)
            names.append(nm)
            if len(names) >= n:
                return names
    return names


def generate_cast100(layout, seed=SEED_DEFAULT):
    """100 distinct residents as records. Deterministic in `seed`."""
    rng = np.random.default_rng(seed)
    nrng = np.random.default_rng(seed + 7)     # separate stream for names
    rrng = np.random.default_rng(seed + 13)    # separate stream for the
                                                # resolution_bins trait --
                                                # keeps the existing 12
                                                # _PARAM_SPEC draws (and
                                                # every downstream resident's
                                                # values) byte-unchanged on
                                                # regeneration, same isolation
                                                # discipline as nrng above

    # reserve anchor names; fill the rest from the generated pool
    reserved = set(_ANCHOR_NAMES.values())
    pool = [nm for nm in _name_pool(200, nrng) if nm not in reserved]
    pi = 0

    _CLASS_BY_GROUP = {  # (rich_p, middle_p) ; poor = remainder
        "high": (0.65, 0.30), "middle": (0.15, 0.70), "low": (0.02, 0.28)}
    _LIT_BY_CLASS = {"rich": 0.95, "middle": 0.80, "poor": 0.55}

    farms = layout["farms"]
    homes = layout["homes"]
    residents = []
    idx = 0
    farm_cursor = 0
    for role, count, group, ri_mean, ri_sd, wkind in ROLE_SPEC:
        for _ in range(count):
            # name
            if role in _ANCHOR_NAMES and _ANCHOR_NAMES[role] not in \
                    {r["name"] for r in residents}:
                name = _ANCHOR_NAMES[role]
            else:
                name = pool[pi]
                pi += 1
            # role identity (the R4 switching friction) -- drawn, not cloned
            ri = _draw_clip(rng, ri_mean, ri_sd, 0.02, 0.98)
            # class + literacy
            u = float(rng.random())
            rp, mp = _CLASS_BY_GROUP[group]
            klass = "rich" if u < rp else ("middle" if u < rp + mp else "poor")
            literate = 1 if float(rng.random()) < _LIT_BY_CLASS[klass] else 0
            # drawn personality/emotion params
            params = {k: _draw_clip(rng, m, s, lo, hi)
                      for k, (m, s, lo, hi) in _PARAM_SPEC.items()}
            # trait-level causal-belief resolution (bin count) -- a 13th,
            # MIXTURE-drawn param, drawn from its OWN rng stream (rrng, like
            # nrng for names above) so every existing param's value is
            # byte-unchanged on regeneration.
            params["resolution_bins"] = _draw_resolution_bins(rrng)
            # workplace cell
            if wkind == "farm":
                work = farms[farm_cursor % len(farms)]
                farm_cursor += 1
            else:
                work = layout["work"][wkind]
            home = homes[idx]
            residents.append({
                "index": idx, "name": name, "role": role, "group": group,
                "role_identity": ri, "class": klass, "literacy": literate,
                "home_cell": list(home), "workplace_cell": list(work),
                "workplace_kind": wkind, "params": params})
            idx += 1
    assert idx == 100, idx
    return {
        "id": "bigville_cast100", "version": "1.0.0", "self_load_only": True,
        "depends_on": [],
        "description": ("100-resident bigville cast: jobs/houses/role-identity/"
                        "drawn-Normal params on the build_town_100 map (blocks "
                        "305000-309000). Deterministic in seed=%d." % seed),
        "seed": seed,
        "map": {"w": layout["w"], "h": layout["h"],
                "component_size": layout["component_size"],
                "deposits": {k: list(v) for k, v in layout["deposits"].items()}},
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

    # trade -> (input_kind, output_kind), matching the R2 economy vocabulary.
    _TRADE_RECIPE = {"fishmonger": ("fish", "fish_ready"),
                     "carpenter": ("lumber", "furniture"),
                     "mason": ("stone", "blocks"),
                     "bakery": ("grain", "bread")}

    def __init__(self, seed=SEED_DEFAULT, **kw):
        self.t100_seed = seed
        grid, aff, layout = build_town_100(seed)
        self.t100_layout = layout
        # inject the expanded map by rebinding build_town for the super().__init__
        # chain (mechanical world setup; build_town itself is never edited).
        _orig = _sim.build_town
        _sim.build_town = lambda g=grid, a=aff: ([row[:] for row in g], list(a))
        try:
            super().__init__(**kw)
        finally:
            _sim.build_town = _orig

        # --- economy: the three deposits + tradesmen shops + a market store -----
        for kind, cell in layout["deposits"].items():
            self.add_deposit(kind, tuple(cell), stock=60.0, growback=3.0,
                             capacity=120.0)
        self.add_store(tuple(layout["work"]["market"]), ["fish", "lumber", "stone"])
        for trade, (ik, ok) in self._TRADE_RECIPE.items():
            self.add_shop(trade, tuple(layout["work"][trade]),
                          input_kind=ik, output_kind=ok)

        # --- the 100 residents (graph data) -------------------------------------
        self.cast = generate_cast100(layout, seed)
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
