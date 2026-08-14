"""BigvilleMoveWorld -- bigville R1 (block 249000): graph-native MOVEMENT + ENERGY
on the proven small-cast drama scaffold.

WHAT THIS ADDS (spec BIGVILLE_MOVEMENT_ECONOMY_SPEC.md sec 3 R1)
---------------------------------------------------------------
Agents NAVIGATE the bigville grid to a seeded goal via a graph-native flood over
a persistent map-belief, and each move DEPLETES a per-agent energy budget so the
agent SLOWS as it tires. The headline coupling: once an agent MOVES, WHO WITNESSES
WHAT becomes contingent on WHERE it goes -- a villager that moves onto a
line-of-sight to John's enclosed office begins witnessing the scheme it could not
see from its seed position, and the proven 245 witness->credibility rule
(bd_villager_backs) flips its backing. Perception becomes DYNAMIC.

ARCHITECTURE-RULE COMPLIANCE (experiments/gamma-substrate/CLAUDE.md)
-------------------------------------------------------------------
This is a WORLD ADAPTER. It subclasses the scaffold (BigvilleSimWorld) by IMPORT,
edits no tracked file, and holds NO agent decision:

  * Movement runs in an ISOLATED movement substrate (`substrate_rs.Substrate`)
    loading two new SEED manifests (bigville_move_nav / bigville_move_energy).
    EVERY movement decision is a RULE there:
      - `mv_relax`      : the BELLMAN flood (a rule; run_rules fixpoint = BFS
                          distance-to-goal field over the walkable map-belief).
      - `mv_pick_hop`   : THE movement decision (an Argmin rule descending the
                          gdist gradient to an adjacent walkable cell).
      - `mv_energy_budget`: THE slow-down decision (the per-tick move budget is a
                          graded step function of energy).
      - `mv_deplete`    : per-hop energy spend (hunger-modulated).
    None of those lives in Python.
  * This adapter only does mechanical I/O: build the walkable cell graph from the
    grid (ingest), seed a goal, APPLY the rule-chosen position delta to the
    scaffold's `self.pos` (the same host channel the scaffold perceives through),
    and read state. The per-tick loop repeats a hop the RULE-computed
    `move_budget` many times -- a mechanical count, exactly like the scaffold's
    "for each villager" loops; the direction, the how-many, and the stop-at-goal
    are all rule verdicts. No `if`/`else` over agent state selects a move.

Isolation (movement substrate separate from the drama substrate) means the nav/
energy fixpoint never cross-fires the drama rules; the ONLY bridge is `self.pos`.
No new Rust: both seeds compose existing DSL Terms.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "runners", "dsl", "python") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "runners", "dsl", "python"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import substrate_rs                                        # noqa: E402
from substrate.seed_loader import manifest_for             # noqa: E402
from worlds.bigville_sim_world import BigvilleSimWorld, SOLID  # noqa: E402

BIG = 1000000.0

# per-character energy defaults (population variation via `energy` start / thresholds)
ENERGY_DEFAULTS = dict(
    energy=100.0, e_high=70.0, e_mid=40.0, e_low=15.0,
    energy_cost=8.0, hunger=0.0, slow_on=1.0, budget_flat=3.0,
    move_budget=0.0, has_next=0.0, next_cx=-1.0, next_cy=-1.0,
    do_deplete=0.0, active=0.0)


class BigvilleMoveWorld(BigvilleSimWorld):
    def __init__(self, **kw):
        super().__init__(**kw)
        # ---- the ISOLATED movement substrate + its two seed manifests --------
        self.eng = substrate_rs.Substrate()._inner
        self.eng.load_seed_manifest(manifest_for("bigville_move_nav"), None)
        self.eng.load_seed_manifest(manifest_for("bigville_move_energy"), None)
        # block 292000: FRONTIER-INCREMENTAL predicate retraction for the
        # Bellman-Ford flood (mv_relax). SCOPED to `_flood_and_budget` (below),
        # NOT global. Why scoped: predicate retraction routes EXTERNAL attr
        # writes through the PRECISE dirtier (mark_node_predicate_dirty) — a
        # rule wakes only if it READS the written key. That is exactly right for
        # the flood (mv_relax is driven by the gdist writes it reads), but the
        # hop loop kicks `mv_pick_hop` with a `has_next` write it does NOT read;
        # that kick only lands under the default BLANKET dirtier. So the flag is
        # armed around the flood run_rules and disarmed before the hop loop. A
        # droppable, byte-identical perf mirror (gate: the gdist field is
        # bit-identical off vs on; the unsound arm diverges; mv_pick_hop — an
        # Argmin over Neighbours reading gdist off-frontier — is engine-excluded
        # from eligibility, so even under the flag it full-scans, byte-identical).
        self._use_pred_retract = True         # perf mirror; False = byte-identity gate

        # ---- INGEST: the persistent map-belief (walkable cells + adjacency) ---
        # A MoveCell per WALKABLE grid tile; `adj` edges only between walkable
        # orthogonal neighbours -> the flood routes AROUND walls/solids by
        # construction (unknown = absence). Mechanical translation of the grid.
        self._cell_at = {}                    # (cx,cy) -> cell nid  (perf cache)
        for y in range(self.H):
            for x in range(self.W):
                if self.grid[y][x] not in SOLID:
                    self._cell_at[(x, y)] = self.eng.add_node(
                        "MoveCell", {"cx": float(x), "cy": float(y), "gdist": BIG})
        for (x, y), c in self._cell_at.items():
            for (nx, ny) in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                n = self._cell_at.get((nx, ny))
                if n is not None:
                    self.eng.add_edge_unchecked(c, "adj", n)

        self._movers = {}                     # name -> Mover nid
        self._field_owner = None              # (gcx,gcy) goal the live gdist field holds
        self._field_cache = {}                # goal cell -> {cell nid: gdist}; the map
                                              # is STATIC, so a goal's BFS field is valid
                                              # forever -> flood once, restore thereafter.
        self._use_field_cache = True          # perf mirror; set False to force a fresh
                                              # flood every goal-switch (byte-identity gate)
        self._cost_steps = 0                  # cumulative rule-fire steps (cost meter)
        self._floods = 0                      # cumulative full re-floods (cost meter)

    # ------------------------------------------------------------------ ingest
    def add_mover(self, name, start, goal=None, **energy):
        """Register a mover at a walkable `start`, optionally seeking `goal`.
        `name` keys into the scaffold's `self.pos` (a scaffold inhabitant moves)."""
        assert start in self._cell_at, f"start {start} is not walkable"
        attrs = dict(ENERGY_DEFAULTS); attrs.update(energy)
        m = self.eng.add_node("Mover", attrs)
        self.eng.add_edge_unchecked(m, "is_at", self._cell_at[start])
        self._movers[name] = m
        self.pos[name] = tuple(start)         # host bridge to perception
        if goal is not None:
            self.set_goal(name, goal)
        return m

    def set_goal(self, name, goal):
        """(Re)seed the mover's spatial goal (a `seeks` edge). Mechanical."""
        assert goal in self._cell_at, f"goal {goal} is not walkable"
        m = self._movers[name]
        for g in list(self.eng.neighbours(m, "seeks")):
            self.eng.remove_edge_unchecked(m, "seeks", g)
        self.eng.add_edge_unchecked(m, "seeks", self._cell_at[goal])
        self._field_owner = None              # goal changed -> field is stale

    # ------------------------------------------------- rule-driven movement
    def _set_only_active(self, m):
        # `active` gates the shared gdist flood + pick to the ONE mover being
        # advanced (1 on it, 0 on all others), so the field holds THIS mover's goal.
        for other in self._movers.values():
            self.eng.set_attr(other, "active", 1.0 if other == m else 0.0)

    def _flood_and_budget(self, name, m):
        """Ensure the gdist field holds THIS mover's goal, and the budget rule has
        run. The gdist field is a per-cell BFS distance to the goal cell; the map is
        STATIC (walls never move), so a goal's field is valid for the WHOLE run and
        for every mover heading there. So: cache each goal's field the first time it
        is flooded, and RESTORE it (O(cells) writes) instead of re-running the
        Bellman-Ford flood (O(cells x passes) rule-fires) on every goal-switch. This
        is a droppable, byte-identical perf mirror -- it removes a re-derivation, not
        a decision (the restored field == a fresh flood; mv_relax then finds fixpoint
        immediately). The cache key is the GOAL CELL, not the mover (the field is
        goal-centric)."""
        gs = list(self.eng.neighbours(m, "seeks"))
        goal_key = None
        if gs:
            ga = self.eng.node(gs[0])["attrs"]
            goal_key = (int(ga["cx"]), int(ga["cy"]))
        # Arm frontier-incremental retraction JUST for the flood: the gdist
        # field-clear / restore writes and the flood's run_rules. Disarmed in
        # `finally` so the hop loop's `has_next` kick keeps the blanket dirtier.
        if self._use_pred_retract:
            self.eng.set_predicate_retraction(True)
        self._set_only_active(m)
        if goal_key is not None and self._field_owner != goal_key:
            cached = self._field_cache.get(goal_key) if self._use_field_cache else None
            if cached is not None:
                for nid, gd in cached.items():        # RESTORE the static-map field
                    self.eng.set_attr(nid, "gdist", gd)
            else:
                for nid in self._cell_at.values():    # clear -> run_rules floods it
                    self.eng.set_attr(nid, "gdist", BIG)
                self._floods += 1
            self._field_owner = goal_key
        self._cost_steps += self.eng.run_rules(1000000)  # seed goal + flood + budget
        if self._use_field_cache and goal_key is not None \
                and goal_key not in self._field_cache:
            self._field_cache[goal_key] = {              # snapshot for reuse
                nid: float(self.eng.node(nid)["attrs"]["gdist"])
                for nid in self._cell_at.values()}
        # Disarm: the hop loop (move_one) needs the BLANKET dirtier so its
        # `has_next` kick wakes mv_pick_hop (which does not read has_next).
        if self._use_pred_retract:
            self.eng.set_predicate_retraction(False)

    def _apply_hop(self, name, m, dest):
        """Mechanical position update: move the is_at edge and the host position."""
        cur = list(self.eng.neighbours(m, "is_at"))
        for c in cur:
            self.eng.remove_edge_unchecked(m, "is_at", c)
        self.eng.add_edge_unchecked(m, "is_at", self._cell_at[dest])
        self.pos[name] = tuple(dest)

    def move_one(self, name):
        """Advance one mover this tick by its RULE-decided budget. Returns the list
        of cells stepped onto (its trajectory this tick). Decisions are all rules;
        this loop only applies the rule-computed budget count + rule-chosen hops."""
        m = self._movers[name]
        self._flood_and_budget(name, m)
        budget = int(self.eng.node(m)["attrs"].get("move_budget", 0.0))
        traj = []
        for _ in range(budget):
            self.eng.set_attr(m, "has_next", 0.0)
            self._cost_steps += self.eng.run_rules(1000000)   # mv_pick_hop decides
            a = self.eng.node(m)["attrs"]
            if a.get("has_next", 0.0) != 1.0:
                break                                          # at goal / unreachable
            dest = (int(a["next_cx"]), int(a["next_cy"]))
            self._apply_hop(name, m, dest)
            self.eng.set_attr(m, "do_deplete", 1.0)
            self._cost_steps += self.eng.run_rules(1000000)   # mv_deplete spends energy
            traj.append(dest)
        return traj

    def energy_of(self, name):
        return float(self.eng.node(self._movers[name])["attrs"].get("energy", 0.0))

    def budget_of(self, name):
        return int(self.eng.node(self._movers[name])["attrs"].get("move_budget", 0.0))

    # ------------------------------------------------------------------ step
    def step(self, move=True):
        """Movement phase (updates self.pos via rules) THEN the scaffold drama step,
        which re-runs its occlusion-gated perception at the NEW positions."""
        self._tick_traj = {}
        if move:
            for name in self._movers:
                self._tick_traj[name] = self.move_one(name)
        return super().step()

    def run(self, T=20, move=True):
        for _ in range(T):
            self.step(move=move)
        return self.frames

    # ------------------------------------------------- glass-box read-offs
    def backs_of(self, name):
        """Read a moving villager's backing off the DRAMA graph (245 rule output)."""
        for i, v in enumerate(self.d.villagers):
            if "villager_%d" % i == name:
                a = self.s.node(v)["attrs"]
                return dict(
                    name=name, pos=self.pos[name],
                    seen_hostile=int(a.get("seen_hostile", 0)),
                    seen_benevolent=int(a.get("seen_benevolent", 0)),
                    heard_claim=int(a.get("heard_claim", 0)),
                    backs=("Mary" if int(max(0, a.get("backs_mary", 0))) == 1 else "John"))
        return None

    def cost_report(self):
        return dict(rule_fire_steps=self._cost_steps, full_refloods=self._floods,
                    cells=len(self._cell_at), ticks=self.tick)
