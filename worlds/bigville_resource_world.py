"""BigvilleResourceWorld -- production-economy R1 (block 300000): the natural-
resource base + extraction, on the nav flood.

WHAT THIS DEMONSTRATES (PRODUCTION_ECONOMY_PLAN.md R1 + BIGVILLE_RESOURCE_PREREG.md)
----------------------------------------------------------------------------------
The town gains STUFF. Fish/lumber/stone Deposit nodes sit on the map; a Labourer
WALKS to a deposit (the nav flood, 291000/292000), extracts raw material into
hand, walks to a Store, and delivers it into the store's per-kind Stock. Deposits
regenerate by Sugarscape GROWBACK. Material is conserved. Balance (steady vs
depletion) is what FALLS OUT of the extraction-vs-growback rates -- not tuned.

ARCHITECTURE-RULE COMPLIANCE
---------------------------
A WORLD ADAPTER on BigvilleMoveWorld. No decision about extract/deliver/growback
-- those are the seed rules (rx_extract/rx_deliver/rx_growback). The adapter only
mints deposits/stores/labourers, bumps the town epoch (the clock, mechanical),
routes each labourer to its current target (deposit when empty-handed, store when
carrying -- a mechanical shuttle, exactly like the reporter walking to the
publisher), arms the extract act on arrival, and reads state.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "runners", "dsl", "python") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "runners", "dsl", "python"))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from substrate.seed_loader import manifest_for                   # noqa: E402
from worlds.bigville_move_world import BigvilleMoveWorld         # noqa: E402


class BigvilleResourceWorld(BigvilleMoveWorld):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.eng.load_seed_manifest(manifest_for("bigville_resource_extract"), None)
        self._rtown = self.eng.add_node("Town", {"name": "Bigville", "epoch": 0.0})
        self._deposits = {}       # kind -> Deposit nid
        self._deposit_cell = {}   # kind -> (x,y)
        self._store = None
        self._store_cell = None
        self._stock = {}          # kind -> Stock nid
        self._labourers = {}      # name -> dict(dep_kind, store)

    # ------------------------------------------------------------------ ingest
    def add_deposit(self, kind, cell, *, stock, growback, capacity):
        assert cell in self._cell_at, f"deposit cell {cell} not walkable"
        d = self.eng.add_node("Deposit", {"kind": kind, "stock": float(stock),
                                          "growback": float(growback),
                                          "capacity": float(capacity),
                                          "grow_epoch": 0.0})
        self.eng.add_edge_unchecked(d, "at_cell", self._cell_at[cell])
        self.eng.add_edge_unchecked(self._rtown, "has_deposit", d)
        self._deposits[kind] = d
        self._deposit_cell[kind] = tuple(cell)
        return d

    def add_store(self, cell, kinds):
        assert cell in self._cell_at, f"store cell {cell} not walkable"
        self._store = self.eng.add_node("Store", {"name": "the store"})
        self.eng.add_edge_unchecked(self._store, "at_cell", self._cell_at[cell])
        self._store_cell = tuple(cell)
        for k in kinds:
            stk = self.eng.add_node("Stock", {"kind": k, "amount": 0.0})
            self.eng.add_edge_unchecked(self._store, "has_stock", stk)
            self._stock[k] = stk
        return self._store

    def add_labourer(self, name, start, *, dep_kind, yield_=1.0):
        m = self.add_mover(name, start, energy=1e12, energy_cost=0.0)
        self.eng.set_attr(m, "carrying", 0.0)
        self.eng.set_attr(m, "carry_kind", "")
        self.eng.set_attr(m, "extract_armed", 0.0)
        self.eng.set_attr(m, "yield", float(yield_))
        self._labourers[name] = dict(dep_kind=dep_kind)
        return m

    # ---------------------------------------------------------------- tick
    def _run(self):
        self.eng.force_all_dirty()
        self._cost_steps += self.eng.run_rules(1000000)

    def step(self, *, move=True):
        """One economic tick: bump the epoch (growback fires once), then shuttle
        each labourer toward its target and arm the extract act on arrival."""
        self.eng.set_attr(self._rtown, "epoch",
                          float(self.eng.node(self._rtown)["attrs"]["epoch"]) + 1.0)
        self._run()                                   # growback + settle
        if not move:
            return
        for name, info in self._labourers.items():
            m = self._movers[name]
            carrying = float(self.eng.node(m)["attrs"].get("carrying", 0.0))
            # empty-handed -> head to the deposit; carrying -> head to the store.
            target = self._store_cell if carrying > 0 else self._deposit_cell[info["dep_kind"]]
            self.set_goal(name, target)
            self.move_one(name)
            if tuple(self.pos[name]) == tuple(target):
                if carrying > 0:
                    self._run()                       # rx_deliver on co-location
                else:
                    self.eng.set_attr(m, "extract_armed", 1.0)
                    self._run()                       # rx_extract on co-location

    def run(self, T=60, *, move=True):
        for _ in range(T):
            self.step(move=move)
        return T

    # ------------------------------------------------- glass-box read-offs
    def deposit_stock(self, kind):
        return float(self.eng.node(self._deposits[kind])["attrs"]["stock"])

    def store_stock(self, kind):
        return float(self.eng.node(self._stock[kind])["attrs"]["amount"])

    def carrying(self, name):
        return float(self.eng.node(self._movers[name])["attrs"].get("carrying", 0.0))
