"""worlds/arc — thin ARC-AGI-3 world adapter (host-layer I/O).

Translates each ARC ``Frame`` into substrate mutations (a ``Game`` node + one
``CellC<v>`` per non-empty cell + per-cell value transitions) and applies the
agent's chosen actions. The seed-booted agent does ALL reasoning; this only
translates external I/O — the legitimate world-adapter layer (CLAUDE.md). It
replaces ``domains/arc3_thin`` (scheduled for deletion); the live env it wraps
(``scripts/arc3_live_env``) is the network connection.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from arc3_env import (  # noqa: E402
    GameState, ACTION1, ACTION2, ACTION3, ACTION4, ACTION5, ACTION6,
)
from substrate import ConsistencyChecker, Grammar, Substrate, TypedGraph  # noqa: E402

SELF_ID = "agent_self"
# The human controller is LABELLED (arrow keys + on-screen CLICK/SELECT on the
# game page). Give the agent the SAME affordances — the buttons carry their human
# labels, not opaque a1..a5 — so it reads "Up"/"Click" the way a person does and
# can ground them via language + confirm via agency. (Up/Down/Left/Right ↔
# ACTION1-4 confirmed by agency: ACTION1 moves the body up, etc.)
_ACTION_MAP = {"Up": ACTION1, "Down": ACTION2, "Left": ACTION3,
               "Right": ACTION4, "Select": ACTION5}

# The ACTUAL ARC-AGI-3 grid palette — the exact value->hex map the page renders
# from (the `m={0:"#FFFFFFFF",1:"#CCCCCCFF",...}` table in the game JS chunk), so
# the eye sees EXACTLY what a human sees. NOTE: ARC-AGI-3 is NOT the canonical ARC
# colour order — it is a GREY RAMP for 0-5 (white->black) then the hues for 6-15.
# Verified against a live ls20 frame: value 4 (#333) is the dark-grey field/walls,
# value 3 (#666) the lighter-grey rooms, 9 blue + 11 yellow the player.
_PALETTE = [
    (255, 255, 255),  # 0  white       #FFFFFF
    (204, 204, 204),  # 1  light-grey  #CCCCCC
    (153, 153, 153),  # 2  grey        #999999
    (102, 102, 102),  # 3  mid-grey    #666666
    (51, 51, 51),     # 4  dark-grey   #333333
    (0, 0, 0),        # 5  black       #000000
    (229, 58, 163),   # 6  magenta     #E53AA3
    (255, 123, 204),  # 7  pink        #FF7BCC
    (249, 60, 49),    # 8  red         #F93C31
    (30, 147, 255),   # 9  blue        #1E93FF
    (136, 216, 241),  # 10 azure       #88D8F1
    (255, 220, 0),    # 11 yellow      #FFDC00
    (255, 133, 27),   # 12 orange      #FF851B
    (146, 18, 49),    # 13 maroon      #921231
    (79, 204, 48),    # 14 green       #4FCC30
    (163, 86, 214),   # 15 violet      #A356D6
]
_SCREEN_MAX = 192


def _render_screen(grid, h, w):
    """Grid -> (H,W,3) uint8 RGB, each cell a colour block (largest side <= 192).
    Mechanical render so the eye has real edges to perceive shapes from."""
    import numpy as np
    cell_px = max(2, _SCREEN_MAX // max(h, w, 1))
    img = np.zeros((max(1, h) * cell_px, max(1, w) * cell_px, 3), dtype=np.uint8)
    for r in range(h):
        for c in range(w):
            img[r * cell_px:(r + 1) * cell_px, c * cell_px:(c + 1) * cell_px] = \
                _PALETTE[int(grid[r][c]) % len(_PALETTE)]
    return img


def recover_grid_from_render(screen):
    """SEEING, not oracle — recover the integer cell grid from the RENDERED RGB
    pixels ALONE. The exact inverse of ``_render_screen`` (the analysis-by-synthesis
    render/quantize pair, cf. StrokeRender/StrokeQuantize): a lossless block render
    round-trips back to its grid. Mechanical pixel->palette->grid I/O — NO read of
    the oracle integer grid, no decision over graph state (like ``ingest_speech``
    translating bytes). Three mechanical steps:

      (a) QUANTIZE every pixel to the nearest of the 16 palette entries (RGB L2) —
          recovers colour and denoises in one step. The oracle grid is never read.
      (b) REGISTER the cell lattice — cell_px is the LARGEST divisor of the image
          size whose p×p blocks are (near-)pure (one palette index each). No
          coherence assumption, so a lone single-cell feature registers too; the
          oracle H/W is never consulted.
      (c) SAMPLE each cell's value as the MAJORITY palette index over its block
          (robust to a few noise-flipped pixels; exact on a clean block render).

    Returns a list-of-rows integer grid — the same value grid the carve segments,
    but derived from what the eye SEES, not handed by the oracle."""
    import numpy as np
    from math import gcd as _gcd
    img = np.asarray(screen)
    if img.ndim != 3 or img.shape[2] < 3:
        raise ValueError("render must be a (H, W, 3) RGB array")
    Himg, Wimg = int(img.shape[0]), int(img.shape[1])
    pal = np.asarray(_PALETTE, dtype=np.int64)                       # (16, 3)

    # (a) QUANTIZE every pixel to the nearest palette index — recovers the colour
    #     AND denoises in one step (small render noise leaves a pixel on the same
    #     palette entry). `idx` is the per-pixel palette map the rest reads.
    px = img[..., :3].astype(np.int64).reshape(-1, 3)
    dist = ((px[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2)     # (npx, 16)
    idx = dist.argmin(axis=1).reshape(Himg, Wimg)

    # (b) REGISTER the cell period WITHOUT any coherence assumption: cell_px is the
    #     LARGEST divisor of the image size whose p×p blocks are ALL pure — one
    #     palette index per block (the MINIMUM block purity, not the mean, so a
    #     single sparse fine feature still vetoes a too-coarse tiling). A finer
    #     divisor that straddles a cell edge is impure; a coarser divisor that spans
    #     two differing cells is impure; only the true cell size (and its own
    #     sub-divisors) tile into all-pure blocks, and the LARGEST such is cell_px.
    #     Because pixels are palette-quantized FIRST, min-purity stays 1.0 under
    #     render noise until the noise actually flips an index (the palette-step
    #     limit — the honest frontier); past that it falls back to argmax min-purity.
    G = _gcd(Himg, Wimg)
    divisors = sorted((d for d in range(2, G + 1) if G % d == 0), reverse=True)

    def _min_purity(p):
        Hb, Wb = Himg // p, Wimg // p
        blk = idx.reshape(Hb, p, Wb, p).transpose(0, 2, 1, 3).reshape(Hb, Wb, p * p)
        best = np.zeros((Hb, Wb), dtype=np.int64)
        for v in range(len(_PALETTE)):
            best = np.maximum(best, (blk == v).sum(axis=2))
        return float(best.min()) / (p * p)

    cell_px = 0
    purities = {}
    for p in divisors:                                              # largest-first
        purities[p] = _min_purity(p)
        if purities[p] >= 0.999:                                    # every block pure
            cell_px = p
            break
    if cell_px == 0:                                                # noisy: best available
        cell_px = (max(divisors, key=lambda p: (purities.get(p) if p in purities
                                                else _min_purity(p), p))
                   if divisors else max(1, min(Himg, Wimg)))
    H = max(1, Himg // cell_px); W = max(1, Wimg // cell_px)

    # (c) SAMPLE — each cell's value is the MAJORITY (mode) palette index over its
    #     block (robust to a few noise-flipped pixels; exact on a clean block).
    Hb, Wb = Himg // cell_px, Wimg // cell_px
    blk = idx[:Hb * cell_px, :Wb * cell_px].reshape(
        Hb, cell_px, Wb, cell_px).transpose(0, 2, 1, 3).reshape(Hb, Wb, cell_px * cell_px)
    counts = np.zeros((Hb, Wb, len(_PALETTE)), dtype=np.int64)
    for v in range(len(_PALETTE)):
        counts[..., v] = (blk == v).sum(axis=2)
    grid_arr = counts.argmax(axis=2)
    grid = grid_arr.tolist()
    return grid


# The dim_types the ShapeDecode signature below carries: slot 0 is the predicate
# ("cell"), slots 1/2 are the INTEGER-LATTICE coordinates (row, col — the
# "in-frame is integer" native path; DimInfer's rotation90/reflection generators
# act on these), slot 3 is the palette VALUE (recolour is a subst on this dim).
# The SAME dim_types the general dim_infer instrument uses (scripts/dim_infer_args
# .py::DT) and the ARC-miniature transform test (test_transform_decode_migrated's
# ["cell", r, c, v] story) — nothing ls20-specific.
SHAPE_DIM_TYPES = ["pred", "coord:r", "coord:c", "val"]


def cells_to_signature(cells):
    """[(row, col, value), ...] -> [["cell", r, c, v], ...] — the ShapeDecode
    relation-system signature the GENERAL TransformDecode/DimInfer consume.

    Mechanical translation ONLY (one ``cell`` relation per occupied lattice cell),
    the SEEN-shape twin of ``recover_grid_from_render``'s pixel->grid step: it turns
    a set of perceived cells into the relation form the shape core reads, with NO
    decision over graph state and NO ls20-special-casing. The recognition of WHICH
    transformation relates two such signatures is the general decode's, not this
    function's — this only hands the eye's Regions to the shape core in its own
    language (cf. StrokeQuantize handing ink to the same core as ``seg`` relations).
    Row/col are the integer lattice (coordinates — where rotation/reflection/
    translation act). The value is a CATEGORICAL colour SIGN, emitted as a token
    ``"v<index>"`` rather than a raw integer ON PURPOSE: the ls20 palette is not an
    ordered magnitude (a grey ramp then unrelated hues), so a recolour is a
    categorical SUBSTITUTION (9->8), never an arithmetic shift on a value axis — and
    a categorical token makes `TransformDecode` read it as a `subst` delta (matching
    the ARC-miniature ``["cell", r, c, "red"]`` story), which is also what lets a
    MULTI-colour recolour resolve as several independent swaps rather than demanding
    one impossible uniform shift. "Colour is a later sparse categorical sign, not a
    dense channel." A value already a string is kept as-is. Returns the signature."""
    return [["cell", int(r), int(c),
             v if isinstance(v, str) else f"v{int(v)}"]
            for (r, c, v) in cells]


def region_signature(sub, region_ids):
    """Region node(s) from the pixel eye -> ShapeDecode signature. Mechanical graph
    read: each ``Region`` (from ``_perceive_regions`` / native ``segment_and_track``)
    owns its cells via ``cell -within-> region`` edges, each cell a ``WorldInstance``
    carrying integer ``row``/``col``; the region carries a single ``rvalue`` (the
    carve is 4-connected equal-value, so a region is monochrome). Reads those back
    into ``[["cell", r, c, v], ...]`` via ``cells_to_signature``.

    ``region_ids`` may be a single id or an iterable — passing several GROUPS them
    (cell-set union, each cell keeping its own region's value) so a MULTI-COLOUR
    symbol (an ls20 two-colour avatar is >1 Region — the named 216000 residual) is
    handed to the shape core as ONE shape. Grouping is a mechanical union, not a
    decision. This is the eye->shape bridge the ls20 plan named missing; the
    transformation between two perceived symbols is recognised by the general decode
    downstream, never here."""
    if not isinstance(region_ids, (list, tuple, set, frozenset)):
        region_ids = [region_ids]
    cells = []
    for rid in region_ids:
        v = int(round(float(sub.node(rid)["attrs"].get("rvalue", 0))))
        for cid in sub.in_neighbours(rid, "within"):
            a = sub.node(cid)["attrs"]
            if "row" in a and "col" in a:
                cells.append((int(a["row"]), int(a["col"]), v))
    return cells_to_signature(cells)


def build_world(frame, prev_grid, label="live", frame_num=0, action_name=None, render=False):
    """Frame -> Substrate{Game, Body, CellC<v> per occupied cell} + value
    transitions. Pure mechanical translation; no decisions over graph state.

    `frame_num` (a monotone counter the adapter holds) is stamped on the Game so
    the agent can tell frames apart; each cell_value_change is minted as a
    ChangeEvent node and the just-applied action as an Action node — input the
    agent's avatar-discovery rules read (which figure moved between frame_num-1
    and frame_num under which action). All mechanical; the agent decides."""
    g = TypedGraph()
    grid = frame.grid
    h = len(grid)
    w = len(grid[0]) if h else 0
    won = frame.state == GameState.WIN
    over = frame.state == GameState.GAME_OVER
    # world_signal = how many grid cells the LAST action changed (the raw "the world responded"
    # magnitude). The agent's curiosity (action_effect: note_outcome) reads its SURPRISE vs a learned
    # baseline off this — not the reward. Mechanical measurement, stamped on the Game node as input.
    world_signal = 0
    if prev_grid is not None:
        for r in range(min(len(prev_grid), h)):
            prow, row = prev_grid[r], grid[r]
            for c in range(min(len(prow), w)):
                if row[c] != prow[c]:
                    world_signal += 1
    # The world hands the agent its CONTEXT, the same a human is given: which
    # framework this is and the game's name. Input, not a decision — the agent
    # reads `framework`/`name` to know it is playing an ARC-AGI-3 game called
    # <label> and to recall what that implies (genre, affordances, that RESET is
    # a penalty-free retry). The agent decides what to DO with that; the world
    # only states it.
    game = g._insert_node("Game", {"id": "game", "name": str(label),
                                   "framework": "ARC-AGI-3", "medium": "game",
                                   "frame": int(frame_num),
                                   "score": int(frame.score),
                                   "world_signal": int(world_signal),
                                   "last_action": str(action_name) if action_name else "",
                                   "won": won, "over": over, "h": h, "w": w})
    body = g._insert_node("Body", {"id": SELF_ID, "score": int(frame.score),
                                   "won": won, "over": over})
    g._insert_edge(body, "inhabits", game)
    # AFFORDANCES — the action repertoire a player is handed (the buttons). Published ONCE on the cold
    # frame (the agent's graph persists them; re-emitting would re-zero `tried` each ingest). These are
    # the directly-applicable interaction actions the agent BABBLES through (action_effect.babble_interaction
    # cycles untried interaction Actions to discover what each CAUSES). The agent decides WHICH to try and
    # what it means; the world only states that these buttons exist. Reset is a real affordance too — a
    # penalty-free restart (the agent keeps what it learned), so it can test a hypothesis without cost;
    # whether/when to use it is the agent's call, not withheld here. (Per-cell clicks are a richer affordance
    # added later — they need a target choice; these are concrete and need no realisation.)
    if prev_grid is None:
        for i, nm in enumerate(("Up", "Down", "Left", "Right", "Select", "Reset")):
            an = g._insert_node("Action", {"id": f"affordance_{nm}", "name": nm,
                                           "interaction": 1.0, "idx": float(i), "tried": 0.0})
            g._insert_edge(game, "has_action", an)
    occ: set = set()
    ctype: dict = {}
    changes: list = []
    _cell_at: dict = {}
    # INCREMENTAL INGEST (the delta-emitter). On frame 0 (prev_grid is None) emit the
    # WHOLE grid once — every cell node, its has_cell + neighbour lattice. On every
    # LATER frame the cells PERSIST in the agent's graph (ingest dedups by (type,id),
    # cells are position-stable id="{r}_{c}"), so re-emitting all ~4096 cells + their
    # neighbour edges every frame is pure waste — it made ingest O(cells) (~3.4s/frame)
    # while the agent's tick is already O(changed) (~0ms). So after frame 0 we emit ONLY
    # the cells whose value CHANGED: ingest updates just those `value` attrs in place,
    # the persistent nodes/edges/`within` memberships survive untouched, and the
    # ChangeEvents below drive the agent's has_change-anchored perception. The occ/ctype
    # occupancy maps (the vision/return path) are still built for every position — cheap
    # Python dict ops, no substrate I/O. This is mechanical I/O translation (emit the
    # delta the agent already reasons over), not a relevance/figure-ground decision.
    cold = prev_grid is None
    for r in range(h):
        prow = prev_grid[r] if (prev_grid is not None and r < len(prev_grid)) else None
        for c in range(w):
            v = int(grid[r][c])
            pv = int(prow[c]) if prow is not None else None
            occ.add((c, r))
            ctype[(c, r)] = "Cell"
            changed = prow is not None and pv != v
            if cold or changed:
                cell = g._insert_node("Cell", {"id": f"{r}_{c}", "row": r, "col": c, "value": v,
                                               "colour": _ARC_COLOUR.get(v, str(v))})
                g._insert_edge(game, "has_cell", cell)
                _cell_at[(r, c)] = cell
            if changed:
                changes.append({"kind": "cell_value_change",
                                "frm": (f"CellC{pv}" if pv else None),
                                "to": (f"CellC{v}" if v else None), "x": c, "y": r})
    # The lattice — the faithful spatial structure of the grid input. A grid IS a
    # lattice; emitting `neighbour` between orthogonally-adjacent cells states that
    # structure (input), it makes no decision. The agent builds its SpatialLocation
    # map over this (its own rules mark which cells are floor); the world just hands
    # over how the cells are laid out. Emitted ONCE on the cold frame — the neighbour
    # graph is static, so later frames inherit it from the persistent cells.
    if cold:
        for (r, c), cell in _cell_at.items():
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = _cell_at.get((r + dr, c + dc))
                if nb is not None:
                    g._insert_edge(cell, "neighbour", nb)
    # Mint the frame's transitions as ChangeEvent nodes (input the agent reasons
    # over) and the just-applied action as an Action node with `took` from the
    # Body. Both carry `id`, so ingest mirrors them into the agent's graph.
    for ch in changes:
        ce = g._insert_node("ChangeEvent", {
            "id": f"chg_{frame_num}_{ch['y']}_{ch['x']}",
            "row": ch["y"], "col": ch["x"], "frame": int(frame_num),
            "frm": ch["frm"] or "", "to": ch["to"] or ""})
        g._insert_edge(game, "has_change", ce)
        # Wire the change to the cell it happened at, so the agent's incremental
        # perception rules can find the changed cell in O(changed) (match
        # [game has_change ce][ce at_cell cell]) instead of scanning has_cell. The
        # cell node is position-stable (id="{r}_{c}"); this is a faithful "this
        # change is at this cell" statement, not a relevance judgment.
        _ch_cell = _cell_at.get((ch["y"], ch["x"]))
        if _ch_cell is not None:
            g._insert_edge(ce, "at_cell", _ch_cell)
    if action_name is not None:
        # The EXPERIENCED action repertoire — one ActionKind per action the agent
        # has actually TRIED, linked game -has_action_kind-> kind, ACCUMULATING via
        # ingest's (type,id) dedup. This is the denominator for the agent's control
        # discriminator: a controlled element responds under a PROPER SUBSET of the
        # tried repertoire; the environment responds under all of it. The repertoire
        # GROWS with every move, so the manifold narrows move by move — the world
        # states which control was used, not which element it drives.
        kind = g._insert_node("ActionKind",
                              {"id": f"kind_{action_name}", "akid": str(action_name)})
        g._insert_edge(game, "has_action_kind", kind)
        act = g._insert_node("Action", {"id": f"act_{frame_num}",
                                        "name": str(action_name),
                                        "frame": int(frame_num)})
        g._insert_edge(body, "took", act)
        g._insert_edge(act, "of_kind", kind)   # the selectivity signal
    sub = Substrate(graph=g, checker=ConsistencyChecker(Grammar([])))
    sub.arc3_self_ids = [body, game]
    sub.arc3_cell_changes = changes
    sub.arc3_cell_type_at = ctype
    # Hand the eye the raw value grid directly, so _perceive_regions reads cell VALUES
    # from here (one numpy array) instead of scanning ~4096 substrate nodes per frame
    # (the 2nd-biggest cost). Cell POSITIONS are stable, so the eye caches the cell->node
    # index once; only the values change, and they're right here.
    sub.arc3_grid = [list(row) for row in grid]
    # VISION side-channel — OPT-IN. The eye now segments the grid into regions/shapes
    # directly (WorldAdapter._perceive_regions, cv2 on the value grid), so the RGB
    # screen render + GraphEye optic pass is redundant for region/agency perception and
    # was the single biggest per-frame cost (~2.6ms on 64x64). Render only when a caller
    # explicitly wants the optic-path percepts (set build_world(..., render=True)).
    if render:
        cell_px = max(2, _SCREEN_MAX // max(h, w, 1))
        sub.vision_screen = _render_screen(grid, h, w)
        sub.vision_calibration = {"depth_scale": 1.0, "wall_clearance": 0.0,
                                  "modality": "grid", "cell_px": cell_px,
                                  "grid_shape": (h, w)}
    return sub, occ, ctype


class ArcWorld:
    """A 3-call world over a live ARC env: reset / legal_actions / apply."""

    def __init__(self, env):
        self.env = env
        self.prev = None
        self.frame = 0                       # monotone frame counter (input the agent reads)
        self.label = getattr(env, "game_id", "live")

    def _ctx(self, f, occ, ct):
        return {"frame": f, "score": int(f.score),
                "won": f.state == GameState.WIN,
                "over": f.state == GameState.GAME_OVER,
                "occupied": occ, "cell_type_at": ct}

    def reset(self):
        f = self.env.reset()
        self.prev = None
        self.frame = 0
        sub, occ, ct = build_world(f, None, self.label, frame_num=0)
        self.prev = [row[:] for row in f.grid]
        return sub, self._ctx(f, occ, ct)

    def legal_actions(self, ctx):
        # the same affordances a human is handed: the directional/select controls,
        # a click on any occupied cell, and RESET (restart — the agent keeps what it
        # learned, so it can test a hypothesis without penalty).
        acts = [("Up",), ("Down",), ("Left",), ("Right",), ("Select",), ("Reset",)]
        ct = ctx.get("cell_type_at", {})
        for (x, y) in ctx.get("occupied", ()):
            acts.append((f"Click@{ct.get((x, y), 'CellC')}@{x}@{y}",))
        return acts

    def apply(self, action, reasoning=None):
        name = action[0]
        if name == "Reset":                     # restart for a penalty-free retest
            f = self.env.reset()
            self.prev = [row[:] for row in f.grid]
            self.frame = 0
            sub, occ, ct = build_world(f, None, self.label, frame_num=0,
                                       action_name="Reset")
            return sub, self._ctx(f, occ, ct)
        if name in _ACTION_MAP:
            ea, coord = _ACTION_MAP[name], None
        else:                                   # Click@<type>@<x>@<y>
            p = name.split("@")
            ea, coord = ACTION6, (int(p[-2]), int(p[-1]))
        f = self.env.step(ea, coord, reasoning=reasoning)
        self.frame += 1
        # perceived change = how many grid cells differ from the previous frame (the raw "the world
        # responded" signal the agent's prediction-error curiosity reads — not the reward).
        changed = 0
        if self.prev is not None:
            for r in range(len(f.grid)):
                row, prow = f.grid[r], self.prev[r]
                for c in range(len(row)):
                    if row[c] != prow[c]:
                        changed += 1
        sub, occ, ct = build_world(f, self.prev, self.label,
                                   frame_num=self.frame, action_name=name)
        self.prev = [row[:] for row in f.grid]
        ctx = self._ctx(f, occ, ct)
        ctx["changed"] = changed
        return sub, ctx

    # --- ORDER-4 self-authoring seam: the agent authors a RETAINING VISUAL CORTEX -----------------------
    # When the agent's frontier reaches a perception/units gap it cannot address with the segmenting eye,
    # _self_extend_reflex calls world.author_faculty(keys, approach). For the arc world that means EXTEND THE
    # EYE: track perceived objects by VALUE-PRESERVING TRANSLATION (object permanence + predictive coding — the
    # method the concepts it grounded from Wikipedia name) so identity survives motion, and KEEP it only if it
    # actually TRACKS (the vision effect-gate). This is the same shape as speech's author_faculty (extend the
    # ear, keep iff it lifts) — the agent decides to author; the world realises + the effect-gate validates.

    def _capture_grids(self, n=18):
        """A short grid sequence to test a tracking method on. Reset after — penalty-free retest (the agent
        keeps what it learns), so trying the faculty costs the game nothing."""
        grids = []
        f = self.env.reset(); grids.append([r[:] for r in f.grid])
        for i in range(n):
            ea = _ACTION_MAP.get(("Up", "Down", "Left", "Right")[i % 4], ACTION1)
            f = self.env.step(ea, None); grids.append([r[:] for r in f.grid])
        self.env.reset()
        return grids

    def _avatar_value(self, grids):
        """The avatar's value = the small NON-background body that translates across frames (it is the thing
        that moves coherently). Discovered, not assumed."""
        import numpy as np
        g0 = np.asarray(grids[0])
        bg = {int(g0[0, 0]), int(np.bincount(g0.ravel()).argmax())}      # border + dominant (floor)
        vals, cnts = np.unique(g0, return_counts=True)
        cand = [int(v) for v, c in zip(vals, cnts) if 4 <= int(c) <= 30 and int(v) not in bg]
        best, best_moved = None, 0
        for V in cand:
            moved = 0
            for k in range(1, min(5, len(grids))):
                a, b = np.asarray(grids[k - 1]), np.asarray(grids[k])
                ca = set(map(tuple, np.argwhere(a == V).tolist()))
                cb = set(map(tuple, np.argwhere(b == V).tolist()))
                if ca and cb and ca != cb:
                    moved += 1
            if moved > best_moved:
                best, best_moved = V, moved
        return best

    def _retaining_track(self, grids, V):
        """Value-preserving translation: the centroid of the value-V body each frame. The whole body persists
        (object permanence) and moves as one, so identity survives the eye's region split/merge."""
        import numpy as np
        out = []
        for g in grids:
            ys, xs = np.where(np.asarray(g) == V)
            out.append((float(ys.mean()), float(xs.mean())) if len(ys) else None)
        return out

    @staticmethod
    def _track_consistency(positions):
        """The vision effect-gate: fraction of steps where the object is PRESENT and moved SMOOTHLY (no drop
        = object permanence held, no jump = identity held). A retaining cortex tracks consistently."""
        ok = tot = 0
        for p, q in zip(positions, positions[1:]):
            tot += 1
            if p is not None and q is not None and abs(p[0] - q[0]) + abs(p[1] - q[1]) <= 8:
                ok += 1
        return ok / max(tot, 1)

    def author_faculty(self, capability_keys, approach=""):
        """Author a retaining visual cortex (value-preserving translation) and KEEP it iff it tracks the body
        consistently. Returns a runnable operator spec, or None (then the impasse ladder climbs past order-4)."""
        try:
            grids = self._capture_grids(18)
            V = self._avatar_value(grids)
            if V is None:
                return None
            cons = self._track_consistency(self._retaining_track(grids, V))
        except Exception:
            return None
        if cons >= 0.9:                          # the authored eye tracks the body -> KEEP
            return {"runner": "retaining_tracker", "metric": "track_consistency", "target": 0.9,
                    "name": "retaining_visual_cortex", "track_value": float(V),
                    "consistency": float(cons),
                    "approach": approach or "value-preserving translation (object permanence + predictive coding)"}
        return None


import json as _json
_SHAPE_TERMS = None
_ARC_COLOUR = {0:"white",1:"light-grey",2:"grey",3:"mid-grey",4:"dark-grey",5:"black",6:"magenta",
               7:"pink",8:"red",9:"blue",10:"azure",11:"yellow",12:"orange",13:"maroon",14:"green",15:"violet"}


def _shape_terms():
    """The jabberwock's persisted shape concepts (shape_signature/same_shape/is_cross),
    loaded from its seed once. Returns {} if the seed isn't present (no narration)."""
    global _SHAPE_TERMS
    if _SHAPE_TERMS is None:
        p = Path(__file__).resolve().parent.parent / "seeds" / "shape_sense.json"
        try:
            _SHAPE_TERMS = {c["name"]: c["definition"] for c in _json.load(open(p))["concepts"]}
        except Exception:
            _SHAPE_TERMS = {}
    return _SHAPE_TERMS


import math as _math2
_LIBRARY = None


def _shape_library():
    """The jabberwock's shape library: {name: descriptor vector}. Extensible — add a
    ShapePrototype to the seed and it knows a new shape. {} if not built yet."""
    global _LIBRARY
    if _LIBRARY is None:
        p = Path(__file__).resolve().parent.parent / "seeds" / "shape_library.json"
        try:
            d = _json.load(open(p))
            _LIBRARY = {n["attrs"]["name"]: _json.loads(n["attrs"]["descriptor"]) for n in d["nodes"]}
        except Exception:
            _LIBRARY = {}
    return _LIBRARY


def _article(word):
    """'a' or 'an' by SOUND, including single letters spoken with a leading vowel
    (L='ell'→an, T='tee'→a). Words: 'an' before a vowel letter."""
    w = (word or "").strip()
    if not w:
        return "a"
    if len(w) == 1 or (len(w) <= 4 and w.replace("-", "").isupper()):  # a letter / acronym
        return "an" if w[0].lower() in "aefhilmnorsx" else "a"
    return "an" if w[0].lower() in "aeiou" else "a"


def _named(word):
    return f"{_article(word)} {word}"


def name_shape(desc, radius=0.28):
    """Name a shape by its NEAREST prototype within a confidence radius — graded, not
    confidently wrong: far from all → 'unknown shape'; two prototypes about equally near →
    'X or Y' (uncertain). Returns the BARE label (no article — callers apply 'a'/'an' where
    the sentence is built). Recognition by the agent's descriptor; the library is the agent's."""
    lib = _shape_library()
    if not lib or desc is None:
        return None
    ranked = sorted(((nm, _math2.dist(desc, v)) for nm, v in lib.items()), key=lambda t: t[1])
    if ranked[0][1] > radius:
        return "unknown shape"
    nm0 = ranked[0][0].replace("_shape", "")
    if len(ranked) > 1 and ranked[1][1] < radius and ranked[1][1] < ranked[0][1] * 1.4 + 0.02:
        return f"{nm0} or {ranked[1][0].replace('_shape', '')}"
    return nm0


_SCENE = None


def _scene_grammar():
    """The scene-narration grammar the jabberwock authored (figure render rule +
    statement wordings). {} if not authored yet."""
    global _SCENE
    if _SCENE is None:
        p = Path(__file__).resolve().parent.parent / "seeds" / "scene_prose.json"
        try:
            _SCENE = _json.load(open(p))
        except Exception:
            _SCENE = {}
    return _SCENE


def _ensure_scene(agent):
    """Install the agent's relations renderer + its authored FigNode rule (once)."""
    g = _scene_grammar()
    if g and not getattr(agent, "_scene_rules", False):
        agent.install_relations_renderer()
        agent.install_render_rule("relations", "FigNode",
            template=agent._spec_to_renderer_term(g["figure_template"]),
            binding_pattern=g["figure_binding"])
        agent._scene_rules = True
    return g


def _say(agent, form, left, right, bag):
    """Render one statement through the agent's OWN engine: left FORM right.
    left/right are graph nodes (a FigNode or a Term.Leaf). No Python sentence here."""
    rel = agent.s.add_node("Term.Relation", {"form": form}); bag.append(rel)
    agent.inner.add_edge_unchecked(rel, "child.left", left)
    agent.inner.add_edge_unchecked(rel, "child.right", right)
    return agent._render_node(rel)


def _fig_node(agent, f, bag):
    n = agent.s.add_node("FigNode", {"colour": f["col"], "row": int(f["cy"]), "col": int(f["cx"])})
    bag.append(n); return n


def _leaf(agent, text, bag):
    n = agent.s.add_node("Term.Leaf", {"form": text}); bag.append(n); return n


def say_self_test(agent, body, landmark):
    """The self/landmark conclusion, rendered by the agent's engine (body/landmark
    are {col,cy,cx} dicts). Returns (body_sentence, landmark_sentence)."""
    g = _ensure_scene(agent)
    if not g:
        return None, None
    bag = []
    bs = _say(agent, g["form_body"], _fig_node(agent, body, bag), _leaf(agent, g["leaf_body"], bag), bag)
    ls = _say(agent, g["form_cross"], _fig_node(agent, landmark, bag), _leaf(agent, g["leaf_cross"], bag), bag)
    for n in bag:
        agent.inner.remove_node(n)
    return bs, ls



_ACTGRAM = None


def _action_grammar():
    global _ACTGRAM
    if _ACTGRAM is None:
        p = Path(__file__).resolve().parent.parent / "seeds" / "action_prose.json"
        try:
            _ACTGRAM = _json.load(open(p))
        except Exception:
            _ACTGRAM = {}
    return _ACTGRAM


def _ensure_action(agent):
    g = _action_grammar()
    if g and not getattr(agent, "_act_rules", False):
        agent.install_relations_renderer()
        agent.install_render_rule("relations", "ActExplain",
            template=agent._spec_to_renderer_term(g["explain_template"]),
            binding_pattern=g["explain_binding"])
        agent._act_rules = True
    return g


def explain_action(agent, action):
    """The agent's OWN first-person prose for WHAT it is doing + WHY, rendered by its
    engine over the register it authored. The reason is chosen from its persistent
    state (does it know its body? is there a landmark it wants?) — its situation, not
    a fixed string. Returns the prose (or None if the register isn't authored)."""
    g = _ensure_action(agent)
    if not g:
        return None
    verb = str(action[0]).split("@")[0]
    body_known = bool(agent.inner.neighbours(agent.agent, "is_embodied_as"))
    landmark = any(agent.s.node(n)["attrs"].get("name", "").startswith("landmark_cross")
                   for n in agent.s.nodes("Concept"))
    key = ("reason_seek" if (body_known and landmark) else
           "reason_move_body" if body_known else "reason_observe")
    bag = []
    node = agent.s.add_node("ActExplain", {"verb": verb, "connector": g["connector"]}); bag.append(node)
    reason = agent.s.add_node("Term.Leaf", {"form": g[key]}); bag.append(reason)
    agent.inner.add_edge_unchecked(node, "child.reason", reason)
    s = agent._render_node(node)
    for n in bag:
        agent.inner.remove_node(n)
    return s


def arc_handle(env, agent=None):
    """The 4-callable world handle the agent's own loops (`live_gamma`,
    `choose_action`) consume: reset / legal_actions / interpret_acts_on /
    apply_action. The agent observes + grows + decides; this only translates I/O.

    When `agent` is given, every action carries the agent's OWN rendered prose for
    what it is doing and why, routed into the ARC-AGI API `reasoning` field (the
    'thinking' recorded in replays). Generating the words is the agent's; sending
    them is this boundary's job."""
    w = ArcWorld(env)

    def reset():
        return w.reset()

    def legal_actions(sub, ctx):
        return w.legal_actions(ctx)

    def interpret_acts_on(sub, ctx, action):
        nm = action[0]
        return [nm.split("@")[1]] if nm.startswith("Click@") else []

    def apply_action(sub, ctx, action):
        reasoning = explain_action(agent, action) if agent is not None else None
        if reasoning:
            print(f"  [thinks] {reasoning}", flush=True)
        return w.apply(action, reasoning=reasoning)

    return {"reset": reset, "legal_actions": legal_actions,
            "interpret_acts_on": interpret_acts_on, "apply_action": apply_action}
