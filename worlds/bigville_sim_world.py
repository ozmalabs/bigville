"""BigvilleSimWorld -- the BIGVILLE glass-box village SIM LOOP (scaffold).

A MECHANICAL host layer that wraps the PROVEN small-cast political drama (block
245000, ``BigvilleDramaWorld`` + ``seeds/bigville_drama_social.json``) in a
Stardew-style TOP-DOWN GRID world with a PER-AGENT sight/hearing observation
gate, and DUMPS the graph state each step for a web viewer to read.

ARCHITECTURE-RULE COMPLIANCE (standalone Bigville architecture notes)
------------------------------------------------------------------
This file is a WORLD ADAPTER. It does exactly two things around ``settle()``:

  * INGEST -- translate the spatial world into graph observations. The
    grid, the entity positions, and the sight/hearing geometry are MECHANICAL
    I/O (line-of-sight + range + wall-occlusion -- the same "what reaches the
    sensor" translation a camera/eye does). The gate decides only WHAT EACH
    OBSERVER PERCEIVES; it makes NO agent decision. What each perceiver then
    DOES with that observation is a graph rule, unchanged:
      - John GOVERN vs UNDERMINE  = ss_choose_burn (spite_skill, 213000).
      - John's stated public face  = bd_john_public_face (234000 stated!=held).
      - Mary's disposition inference= bd_mary_infers (abductive Argmax-decode).
      - each villager's backing     = bd_villager_backs (credibility rule).
    Not one of those lives here. This adapter only accumulates the OBSERVATION
    COUNTS (seen_benevolent / seen_hostile / heard_claim / observed harm), and
    it accumulates them PER-PERCEIVER, gated by geometry -- so the credibility
    asymmetry becomes a PERCEPTION FACT (a villager who only ever stood in the
    square sees benevolence; the one who witnessed the office sees hostility),
    not a global broadcast + a deception flag.

  * EMIT -- read the graph's decisions back out (``graph_to_dict`` + targeted
    queries) into a viewer-ready JSON: the grid, the affordances, each
    inhabitant's position, WHAT IT CURRENTLY PERCEIVES, and its read-off state
    (held intent, public utterance, relationships, beliefs, goal, backing).

No ``graph_rewrite.run`` / ``gr.run`` / ``_match`` / ``_apply`` / ``make_rule``.
Every conditional here is over WORLD state (positions, geometry, tick) -- never
over an agent's graph valuation. NO Rust; the drama's integer-native seed is
reused byte-for-byte. Small-cast scaffold; the geometry is proximity-LOCAL
(per-observer LOS/earshot), so realized interaction stays ~O(N*k), NOT an
all-pairs sweep -- scale-ready by construction (200-scale needs the separate
scale-verification probe; NOT claimed here).
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "runners", "dsl", "python") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "runners", "dsl", "python"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from worlds.bigville_drama_world import (                     # noqa: E402
    BigvilleDramaWorld, CLAIM_WEIGHT, DIFFICULTY_PENALTY, HOSTILE_WEIGHT)

# The newspaper headline is a TEMPLATE here (cosmetic, like the drama's utterance
# lookup). The syntax-CARRYING composed article is the sibling block 246000
# language faculty (`bigville_lang_`); this scaffold wires the reporter->observe->
# newspaper->propagate MECHANISM and marks the composition seam. Not depended on
# here (that block builds in parallel; its files are untouched).
HEADLINE = {
    "exposure": "MAYOR UNDER SCRUTINY: pastor's claim of hostility toward her draws notice.",
    "capture": "MAYOR SERVES FAITHFULLY: office dismisses pastor's 'needless' grievance.",
}

# THE THREE GLASS-BOX LAYERS -- held (truth) / journal (inward self-story) /
# face (public). The GAPS between them are the drama; self-deception = stated!=held
# pointed INWARD (John's journal rationalizes, it does not confess). The three
# tokens are READ from graph state (held from ss_choose_burn's chosen_burn; face
# from bd_john_public_face's stated_benevolent; the journal mirrors the inward
# presentation) -- the DIVERGENCE is not scripted, it falls out of the psychopath
# knobs. The prose below is a TEMPLATE; the syntax-carrying composition is the
# sibling block 244000/246000 language faculty (seam marked, not depended on).

# ---- tile codes (a Stardew-ish top-down town) -----------------------------
GRASS, PATH, WALL, FLOOR, SQUARE, TREE, WATER = 0, 1, 2, 3, 4, 5, 6
OCCLUDERS = {WALL, TREE}          # block line-of-sight AND muffle hearing
SOLID = {WALL, TREE, WATER}       # not walkable (unused by the static scaffold)

SIGHT_RANGE = 7                   # tiles; Chebyshev, LOS-gated
HEAR_RANGE = 11                   # hearing carries further than sight
TILE_NAME = {GRASS: "grass", PATH: "path", WALL: "wall", FLOOR: "floor",
             SQUARE: "square", TREE: "tree", WATER: "water"}


def _rect(grid, x0, y0, x1, y1, code):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            grid[y][x] = code


def _building(grid, x0, y0, x1, y1, door):
    """A walled building: WALL perimeter, FLOOR interior, one FLOOR door tile."""
    _rect(grid, x0, y0, x1, y1, WALL)
    _rect(grid, x0 + 1, y0 + 1, x1 - 1, y1 - 1, FLOOR)
    dx, dy = door
    grid[dy][dx] = FLOOR          # the door: the only gap in the wall


def build_town():
    """A compact top-down town: a central SQUARE, the mayor's OFFICE (John, top-
    left, enclosed -> his private scheming is OCCLUDED), the CHURCH (Mary,
    right), a couple of houses, and tree clusters as occluders. Returns
    (grid, affordances)."""
    W, H = 30, 18
    grid = [[GRASS for _ in range(W)] for _ in range(H)]
    # central square + paths (the public space)
    _rect(grid, 11, 6, 18, 11, SQUARE)
    _rect(grid, 2, 8, 27, 9, PATH)          # main east-west road
    _rect(grid, 14, 2, 15, 15, PATH)        # main north-south road
    # the mayor's OFFICE (top-left, enclosed; door faces the square-ward path)
    _building(grid, 3, 2, 8, 6, door=(8, 4))
    # the CHURCH (right)
    _building(grid, 22, 3, 27, 7, door=(22, 5))
    # two villager houses (bottom)
    _building(grid, 4, 12, 8, 15, door=(6, 12))
    _building(grid, 20, 11, 24, 14, door=(22, 11))
    # tree clusters (occluders that break line-of-sight in the open)
    for (tx, ty) in [(10, 3), (10, 4), (19, 13), (18, 13), (26, 12), (2, 5)]:
        grid[ty][tx] = TREE
    affordances = [
        {"name": "Mayor's Office", "kind": "office", "x": 5, "y": 4},
        {"name": "Church", "kind": "church", "x": 24, "y": 5},
        {"name": "Town Square", "kind": "square", "x": 14, "y": 8},
        {"name": "House", "kind": "house", "x": 6, "y": 13},
        {"name": "House", "kind": "house", "x": 22, "y": 12},
    ]
    return grid, affordances


def _line(x0, y0, x1, y1):
    """Bresenham grid line from (x0,y0) to (x1,y1), inclusive."""
    pts = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        pts.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
    return pts


class BigvilleSimWorld:
    """The small cast placed SPATIALLY, perceiving the grid through a per-agent
    sight/hearing gate. Wraps the proven ``BigvilleDramaWorld`` graph; the
    decision rules are untouched -- only the OBSERVATION each agent receives is
    geometry-gated here (mechanical ingest)."""

    def __init__(self, john_psychopath=True, mary_tom=True, deception=True,
                 indifferent=False):
        self.grid, self.affordances = build_town()
        self.H = len(self.grid)
        self.W = len(self.grid[0])

        # the proven graph runtime + rules (block 245000), unchanged
        self.d = BigvilleDramaWorld(john_psychopath=john_psychopath,
                                    mary_tom=mary_tom, deception=deception,
                                    indifferent=indifferent)
        self.s = self.d.s
        self.inner = self.d.inner

        # ---- SPATIAL placement of the cast (grounds the political structure) --
        # John's PUBLIC face happens at the square; his PRIVATE scheming is in
        # the enclosed office (occluded). Two event points per tick.
        self.square_pt = (14, 8)
        self.office_pt = (5, 4)          # inside the office (enclosed)
        self.church_pt = (24, 5)
        # positions: John shown at the square (his public presence); Mary at the
        # office door (the pastor who WITNESSES the private scheming); villagers
        # spread -- most in the public square, the zero-charm skeptic near Mary.
        self.pos = {
            "John": self.square_pt,
            "Mary": (9, 4),              # at the office door -> LOS into office
        }
        # villager i -> position. v0 (skeptic, charm 0) posted by the office
        # (perceives the private hostility / hears Mary); the rest in the square.
        vpos = [(9, 5), (13, 9), (15, 7), (16, 10), (17, 8)]
        for i, v in enumerate(self.d.villagers):
            self.pos["villager_%d" % i] = vpos[i % len(vpos)]

        # ---- the REPORTER + the NEWSPAPER (the wide-public credibility channel) --
        # The reporter is ANOTHER Villager node -> the SAME credibility rule
        # (bd_villager_backs) decides its stance, and that stance IS the paper's
        # FRAME: backs John -> 'capture' (media capture, pro-mayor); backs Mary ->
        # 'exposure' (investigative). NOTHING scripts the frame -- it falls out of
        # what the reporter PERCEIVED through the same occlusion gate + its own
        # charm susceptibility. Posted by the office door so it can investigate.
        self.reporter = self.s.add_node("Villager", {
            "name": "reporter", "cred_on": 1.0, "charm_weight": 1.0,
            "claim_weight": float(CLAIM_WEIGHT),
            "difficulty_penalty": float(DIFFICULTY_PENALTY),
            "hostile_weight": float(HOSTILE_WEIGHT),
            "seen_benevolent": 0.0, "seen_hostile": 0.0, "heard_claim": 0.0,
            "backs_mary": -1.0})
        self.inner.add_edge_unchecked(self.d.village, "has_villager", self.reporter)
        self.pos["reporter"] = (10, 4)          # office-door beat -> can witness
        self.distribution_pt = self.square_pt    # the paper is posted in the square
        self.last_paper = None                   # previous tick's Newspaper (read this tick)
        self.newspapers = []                     # minted Newspaper node ids
        self.journals = []                       # minted JournalEntry node ids

        # SEEDED ONCE, WITH HISTORY: the initial condition is a village that has
        # ALREADY lived -- pre-existing relationships + priors (John's charm has
        # worked for years; the pastor's standing already built). Seeded here a
        # SINGLE time; from now on the sim only runs (+ dump/resume), never re-seeds.
        self._seed_history()

        self.tick = 0
        self.frames = []                 # per-tick viewer states

    # -------------------- seeded-once history (initial condition) ----------
    def _seed_history(self):
        """A village WITH a past: pre-existing relationship edges + priors. Pure
        world initial-condition setup (mechanical graph data) -- no decision. John's
        charm has worked for years -> each villager starts already predisposed
        (a prior seen_benevolent proportional to its charm susceptibility); the
        pastor's standing is already built (villager_0, the skeptic, is her ally).
        Sparse ties only (friendships/rivalries) -- NOT an all-pairs graph."""
        d = self.d
        # John's charm already worked (years of a benevolent public face)
        for v in d.villagers:
            a = self.s.node(v)["attrs"]
            prior = 2.0 * a.get("charm_weight", 0.0)
            self.s.set_attr(v, "seen_benevolent", a["seen_benevolent"] + prior)
            self.inner.add_edge_unchecked(d.john, "charmed", v)
        # sparse pre-existing relationships (history), not strangers
        rel = [(d.villagers[0], "allied_with", d.mary),      # skeptic <-> pastor
               (d.villagers[1], "friend_of", d.villagers[2]),
               (d.villagers[3], "friend_of", d.villagers[4]),
               (d.mary, "rival_of", d.john)]                  # long-standing rivalry
        for (a, e, b) in rel:
            self.inner.add_edge_unchecked(a, e, b)
        # the pastor's standing is already built (a prior on her credibility)
        self.s.set_attr(d.mary, "standing_years", 12.0)

    # -------------------- the mechanical perception gate --------------------
    def _occluded(self, a, b):
        """True iff the grid line a->b crosses an occluder BETWEEN the endpoints
        (endpoints themselves excluded, so standing IN a building still lets you
        perceive its interior)."""
        pts = _line(a[0], a[1], b[0], b[1])
        for (x, y) in pts[1:-1]:
            if self.grid[y][x] in OCCLUDERS:
                return True
        return False

    def can_see(self, observer, target_pt):
        o = self.pos[observer]
        if max(abs(o[0] - target_pt[0]), abs(o[1] - target_pt[1])) > SIGHT_RANGE:
            return False
        return not self._occluded(o, target_pt)

    def can_hear(self, observer, source_pt):
        o = self.pos[observer]
        if max(abs(o[0] - source_pt[0]), abs(o[1] - source_pt[1])) > HEAR_RANGE:
            return False
        # walls muffle: a wall on the path blocks the utterance for this scaffold
        return not self._occluded(o, source_pt)

    def perceives(self, observer, pt):
        """An event at ``pt`` is perceived iff seen OR heard."""
        return self.can_see(observer, pt) or self.can_hear(observer, pt)

    # -------------------- the gated sim step --------------------
    def step(self):
        """One tick, mirroring the proven drama's three phases, but with PHASE B
        (what each observer perceives) gated by geometry instead of broadcast."""
        self.tick += 1
        d = self.d

        # PHASE 0 (mechanical): distribute LAST tick's newspaper. A reader who
        # perceives the distribution point (the square) and whose paper CARRIES
        # THE ACCUSATION (an 'exposure' frame) hears Mary's claim via print --
        # the WIDE-PUBLIC channel reaching villagers who were never in earshot.
        # (A 'capture' paper carries no accusation, so it delivers nothing.)
        if self.last_paper is not None and self.last_paper["carries_accusation"]:
            for i, v in enumerate(d.villagers):
                if self.perceives("villager_%d" % i, self.distribution_pt):
                    a = self.s.node(v)["attrs"]
                    self.s.set_attr(v, "heard_claim", a["heard_claim"] + 1.0)

        # PHASE A: John decides + states his public face (in-graph).
        self.inner.settle()
        held = max(0, int(self.s.node(d.jdec)["attrs"]["chosen_burn"]))
        stated = max(0, int(self.s.node(d.jdec)["attrs"]["stated_benevolent"]))
        un = self.s.add_node("PublicUtterance", {
            "by": "John", "tick": float(self.tick),
            "stated_benevolent": float(stated), "held_hostile": float(held),
            "deceptive": 1.0 if (stated == 1 and held == 1) else 0.0})
        self.inner.add_edge_unchecked(d.john, "spoke", un)
        d.utterances.append(un)

        # PHASE B (mechanical, PERCEPTION-GATED):
        #   * the benevolent statement is a SQUARE event; a villager accrues
        #     seen_benevolent only if it perceives the square.
        #   * the hostile intent is an OFFICE event (occluded); an observer
        #     accrues seen_hostile only if it perceives the office interior.
        #   * Mary's harm evidence is gated the same way -- she only counts harm
        #     she WITNESSES (she is posted at the office door).
        mary_sees_office = self.perceives("Mary", self.office_pt)
        n_obs = int(self.s.node(d.tp)["attrs"]["n_obs"]) + 1
        n_harm = int(self.s.node(d.tp)["attrs"]["n_harm"]) + (held if mary_sees_office else 0)
        rate = (100 * n_harm) // max(n_obs, 1)
        self.s.set_attr(d.tp, "n_obs", float(n_obs))
        self.s.set_attr(d.tp, "n_harm", float(n_harm))
        self.s.set_attr(d.tp, "observed_harm_rate", float(rate))
        for g in d.gens:
            self.s.set_attr(g, "observed_harm_rate", float(rate))

        mary_claims = d._mary_has_goal()
        per_villager_percept = {}
        for i, v in enumerate(d.villagers):
            name = "villager_%d" % i
            a = self.s.node(v)["attrs"]
            sees_square = self.perceives(name, self.square_pt)
            sees_office = self.perceives(name, self.office_pt)
            hears_mary = self.perceives(name, self.pos["Mary"])
            if sees_square:
                self.s.set_attr(v, "seen_benevolent", a["seen_benevolent"] + stated)
            if sees_office:
                self.s.set_attr(v, "seen_hostile", a["seen_hostile"] + held)
            if mary_claims and hears_mary:
                self.s.set_attr(v, "heard_claim", a["heard_claim"] + 1.0)
            per_villager_percept[name] = dict(
                sees_square=sees_square, sees_office=sees_office, hears_mary=hears_mary)

        # the REPORTER perceives through the SAME gate (investigative beat).
        ra = self.s.node(self.reporter)["attrs"]
        rep_sees_square = self.perceives("reporter", self.square_pt)
        rep_sees_office = self.perceives("reporter", self.office_pt)
        rep_hears_mary = self.perceives("reporter", self.pos["Mary"])
        if rep_sees_square:
            self.s.set_attr(self.reporter, "seen_benevolent", ra["seen_benevolent"] + stated)
        if rep_sees_office:
            self.s.set_attr(self.reporter, "seen_hostile", ra["seen_hostile"] + held)
        if mary_claims and rep_hears_mary:
            self.s.set_attr(self.reporter, "heard_claim", ra["heard_claim"] + 1.0)

        # PHASE C: observers decide, in-graph (Mary infers/goals/claims; villagers
        # back; the REPORTER's stance is decided by the SAME bd_villager_backs rule).
        self.inner.settle()

        # EMIT the NEWSPAPER: the reporter's decided stance IS the frame (read off
        # backs_mary -- no Python decides it); mint a Newspaper node the reader
        # channel above will propagate next tick. Headline is a template (246000
        # `bigville_lang_` composes the real article; seam marked).
        rb = int(max(0, self.s.node(self.reporter)["attrs"]["backs_mary"]))
        frame = "exposure" if rb == 1 else "capture"
        carries = 1 if frame == "exposure" else 0
        paper = self.s.add_node("Newspaper", {
            "tick": float(self.tick), "frame": frame,
            "carries_accusation": float(carries), "headline": HEADLINE[frame]})
        self.inner.add_edge_unchecked(self.reporter, "published", paper)
        self.newspapers.append(paper)
        self.last_paper = dict(tick=self.tick, frame=frame, carries_accusation=carries,
                               headline=HEADLINE[frame])

        rep_percept = dict(sees_square=rep_sees_square, sees_office=rep_sees_office,
                           hears_mary=rep_hears_mary)
        frame_snap = self.snapshot(per_villager_percept, mary_sees_office, rep_percept)
        # NIGHT / consolidation: each character writes a private journal (the
        # inward layer). Minted as graph nodes -> glass-box + persistence + a plot
        # hook (another agent could later FIND a journal). Done after the day's
        # decisions settle.
        self.night(frame_snap)
        self.frames.append(frame_snap)
        return frame_snap

    def run(self, T=20):
        for _ in range(T):
            self.step()
        return self.frames

    # -------------------- glass-box read-offs (EMIT) --------------------
    def _index(self):
        d = self.s.graph_to_dict()
        nodes = {n["id"]: n for n in d["nodes"]}
        out = {}
        for e in d["edges"]:
            out.setdefault(e["src"], []).append((e["type"], e["tgt"]))
        return nodes, out

    def _neighbour(self, nodes, out, nid, edge_type):
        for (t, tgt) in out.get(nid, []):
            if t == edge_type and tgt in nodes:
                return nodes[tgt]
        return None

    def read_john(self, nodes, out):
        dec = self._neighbour(nodes, out, self.d.john, "has_decision")
        ep = self._neighbour(nodes, out, self.d.john, "has_emotion_params")
        held = int(max(0, dec["attrs"]["chosen_burn"])) if dec else 0
        stated = int(max(0, dec["attrs"]["stated_benevolent"])) if dec else 0
        disfavor = self._neighbour(nodes, out, self.d.john, "disfavors")
        return dict(
            name="John", role="mayor", home="Mayor's Office",
            held_intent=("UNDERMINE Mary" if held == 1 else "GOVERN"),
            public_utterance=("I serve Bigville faithfully -- the pastor stirs "
                              "needless trouble." if stated == 1
                              else "The council should hear my grievance with Mary."),
            stated_benevolent=stated, held_hostile=held,
            deception_gap=bool(stated == 1 and held == 1),
            w_supergraph=(ep["attrs"].get("w_supergraph") if ep else None),
            w_spite=(ep["attrs"].get("w_spite") if ep else None),
            disfavors=(disfavor["attrs"].get("name") if disfavor else None))

    def read_mary(self, nodes, out):
        tp = self._neighbour(nodes, out, self.d.mary, "has_tom_params")
        inf = self._neighbour(nodes, out, self.d.mary, "has_inference")
        goal = self._neighbour(nodes, out, self.d.mary, "has_goal")
        claim = self._neighbour(nodes, out, self.d.mary, "made_claim")
        return dict(
            name="Mary", role="pastor", home="Church",
            tom_on=bool(tp and tp["attrs"].get("tom_on") == 1.0),
            observed_harm_rate=(int(tp["attrs"].get("observed_harm_rate", 0)) if tp else 0),
            inferred_disposition=(inf["attrs"].get("disposition") if inf else None),
            goal=(goal["attrs"].get("kind") if goal else None),
            goal_target=(goal["attrs"].get("target") if goal else None),
            claim=(claim["attrs"].get("content") if claim else None),
            claim_about=(claim["attrs"].get("about") if claim else None))

    def read_villager(self, nodes, out, v, name):
        a = nodes[v]["attrs"]
        return dict(
            name=name, role="villager", home="House",
            charm_weight=int(a.get("charm_weight", 0)),
            seen_benevolent=int(a.get("seen_benevolent", 0)),
            seen_hostile=int(a.get("seen_hostile", 0)),
            heard_claim=int(a.get("heard_claim", 0)),
            backs=("Mary" if int(max(0, a.get("backs_mary", 0))) == 1 else "John"))

    def snapshot(self, per_villager_percept=None, mary_sees_office=None,
                 rep_percept=None):
        """A full viewer frame: grid, affordances, and each inhabitant's position,
        current perception, and read-off graph state, plus the newspaper."""
        nodes, out = self._index()
        inhabitants = []

        # John
        jst = self.read_john(nodes, out)
        inhabitants.append(dict(
            id="John", emoji="\U0001F3A9", x=self.pos["John"][0], y=self.pos["John"][1],
            state=jst,
            perceives=dict(
                sees_square=self.perceives("John", self.square_pt),
                sees_church=self.perceives("John", self.church_pt))))
        # Mary
        mst = self.read_mary(nodes, out)
        inhabitants.append(dict(
            id="Mary", emoji="⛪", x=self.pos["Mary"][0], y=self.pos["Mary"][1],
            state=mst,
            perceives=dict(
                sees_office=(mary_sees_office if mary_sees_office is not None
                             else self.perceives("Mary", self.office_pt)),
                sees_square=self.perceives("Mary", self.square_pt))))
        # villagers
        for i, v in enumerate(self.d.villagers):
            name = "villager_%d" % i
            vst = self.read_villager(nodes, out, v, name)
            perc = (per_villager_percept or {}).get(name, dict(
                sees_square=self.perceives(name, self.square_pt),
                sees_office=self.perceives(name, self.office_pt),
                hears_mary=self.perceives(name, self.pos["Mary"])))
            inhabitants.append(dict(
                id=name, emoji="\U0001F9D1", x=self.pos[name][0], y=self.pos[name][1],
                state=vst, perceives=perc))

        # the reporter (read off the SAME villager rule -> its stance = the frame)
        rst = self.read_villager(nodes, out, self.reporter, "reporter")
        rst["role"] = "reporter"
        rst["home"] = "Town Square (beat)"
        rst["frame"] = "exposure" if rst["backs"] == "Mary" else "capture"
        inhabitants.append(dict(
            id="reporter", emoji="\U0001F4F0", x=self.pos["reporter"][0],
            y=self.pos["reporter"][1], state=rst,
            perceives=(rep_percept or dict(
                sees_square=self.perceives("reporter", self.square_pt),
                sees_office=self.perceives("reporter", self.office_pt),
                hears_mary=self.perceives("reporter", self.pos["Mary"])))))

        # attach the THREE GLASS-BOX LAYERS (held / journal / face) to every
        # inhabitant -- uniformly, no John/Mary special-casing in principle.
        for inh in inhabitants:
            inh["three_layer"] = self._three_layer(inh["state"])

        newspaper = None
        if self.last_paper is not None:
            newspaper = dict(self.last_paper)
            newspaper["composed_by"] = "template (246000 bigville_lang seam)"

        return dict(
            tick=self.tick,
            grid=dict(w=self.W, h=self.H, tiles=self.grid,
                      legend={str(k): v for k, v in TILE_NAME.items()}),
            affordances=self.affordances,
            event_points=dict(square=list(self.square_pt), office=list(self.office_pt),
                              church=list(self.church_pt)),
            sight_range=SIGHT_RANGE, hear_range=HEAR_RANGE,
            newspaper=newspaper,
            inhabitants=inhabitants)

    # -------------------- the three glass-box layers + journals -------------
    def _three_layer(self, s):
        """held (truth) / journal (inward self-story) / face (public), each READ
        from graph state. self_deception = the character's presented token (out AND
        in) contradicting its held truth -- for John it IS the deception_gap
        (stated benevolence over held hostility), which no one scripts; for honest
        characters the three layers agree. Prose is a template (246000 seam)."""
        role = s["role"]
        seam = "template (244000/246000 bigville_lang seam)"
        if role == "mayor":
            benevolent = s.get("stated_benevolent") == 1
            held = ("I moved against Mary today." if s["held_intent"].startswith("UNDERMINE")
                    else "I governed straight today.")
            journal = ("Another day in service of Bigville. The pastor's constant trouble forces "
                       "a firm hand, but the town needs steady leadership." if benevolent
                       else "I told the council plainly where I stand with Mary.")
            face = '"%s"' % s.get("public_utterance", "")
            self_dec = bool(s.get("deception_gap"))
        elif role == "pastor":
            hostile = s.get("inferred_disposition") == "hostile"
            held = ("What I have concluded: John is hostile to me." if hostile
                    else "I have formed no judgement of John yet.")
            journal = ("I am now certain of John's hostility; I must see him answer to the "
                       "council." if hostile else "I keep watching; the evidence is not yet in.")
            face = (("I have told the town: John is %s." % s.get("claim")) if s.get("claim")
                    else "(no public claim yet)")
            self_dec = False
        elif role == "reporter":
            witnessed = s.get("seen_hostile", 0) > 0
            held = ("What I actually saw: the office tells a darker story than the square."
                    if witnessed else "What I actually saw: only the mayor's public generosity.")
            journal = ("I will print what I witnessed at the office door." if s.get("frame") == "exposure"
                       else "The mayor has been generous with his time; the grievance seems thin.")
            face = "Front page frame: %s" % str(s.get("frame", "")).upper()
            # a captured press: printed 'capture' despite having witnessed hostility
            self_dec = bool(s.get("frame") == "capture" and witnessed)
        else:  # villager -- a FULL agent, not a hollow extra
            witnessed = s.get("seen_hostile", 0) > 0
            held = ("In my own eyes I saw the mayor turn hostile." if witnessed
                    else "In my own eyes I saw only the mayor's good works.")
            journal = ("The Herald and the pastor have me worried about the mayor."
                       if s.get("backs") == "Mary"
                       else "The mayor has always been good to this town; I trust him.")
            face = "I back %s." % s.get("backs")
            self_dec = False
        return dict(held=held, journal=journal, face=face,
                    self_deception=self_dec, composed_by=seam)

    def night(self, frame_snap):
        """Consolidation tick: mint a private JournalEntry per inhabitant carrying
        its three layers -- a readable graph node (glass-box + persistence + a
        future plot hook: another agent could FIND a journal). Mechanical emit."""
        owner = {"John": self.d.john, "Mary": self.d.mary, "reporter": self.reporter}
        for i, v in enumerate(self.d.villagers):
            owner["villager_%d" % i] = v
        for inh in frame_snap["inhabitants"]:
            tl = inh["three_layer"]
            j = self.s.add_node("JournalEntry", {
                "by": inh["id"], "tick": float(self.tick), "private": 1.0,
                "held": tl["held"], "journal": tl["journal"], "face": tl["face"],
                "self_deception": 1.0 if tl["self_deception"] else 0.0})
            src = owner.get(inh["id"])
            if src is not None:
                self.inner.add_edge_unchecked(src, "wrote_journal", j)
            self.journals.append(j)

    # -------------------- persistence: seed once -> live -> dump -> resume --
    def dump(self, path):
        """Durable snapshot: the whole graph (graph_to_dict) + the host sim meta
        (positions, tick, last paper). graph_to_dict IS the persistence form."""
        import json
        meta = dict(tick=self.tick, pos={k: list(v) for k, v in self.pos.items()},
                    last_paper=self.last_paper)
        with open(path, "w") as f:
            json.dump(dict(graph=self.s.graph_to_dict(), meta=meta), f)

    @classmethod
    def resume(cls, path, **kw):
        """Rebuild a live sim from a dump: a fresh graph (SAME seed manifests,
        so the RULES are present) with the saved graph overlaid, handles rebound by
        name. Demonstrates seed-once -> dump -> resume with the dynamics intact."""
        import json
        with open(path) as f:
            saved = json.load(f)
        w = cls(**kw)                     # fresh eye + the 3 seed manifests (rules)
        w.inner.graph_from_dict(saved["graph"])   # overlay the saved node/edge state
        # rebind handles by type/name over the loaded graph (each of these types is
        # a singleton except Villager, keyed by name).
        d = w.d
        d.john = next(iter(w.s.nodes("EmotionHub")))
        d.mary = next(iter(w.s.nodes("MaryTom")))
        d.village = next(iter(w.s.nodes("Village")))
        d.jdec = next(iter(w.s.nodes("HarvestDecision")))
        d.tp = next(iter(w.s.nodes("ToMParams")))
        d.gens = list(w.s.nodes("DispositionGenerator"))
        d.villagers = sorted(
            (x for x in w.s.nodes("Villager")
             if w.s.node(x)["attrs"].get("name", "").startswith("villager_")),
            key=lambda x: w.s.node(x)["attrs"]["name"])
        w.reporter = next(x for x in w.s.nodes("Villager")
                          if w.s.node(x)["attrs"].get("name") == "reporter")
        m = saved["meta"]
        w.tick = int(m["tick"])
        w.pos = {k: tuple(v) for k, v in m["pos"].items()}
        w.last_paper = m["last_paper"]
        return w

    def close(self):
        self.d.close()
