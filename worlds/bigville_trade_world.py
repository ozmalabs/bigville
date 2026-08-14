"""BigvilleTradeWorld -- production-economy R2 (block 301000): production CONSUMES
raw material; tradesmen TRANSFORM raw -> goods; the fishmonger can't sell fish
nobody caught.

Chain (all on the nav flood + R1 extraction): a labourer extracts fish from a
Deposit and delivers it to the FISHMONGER's input Stock (R1's rx_deliver, the shop
plays the store role); the shop TRANSFORMS fish -> fish_ready (tf_transform); a
co-located customer BUYS a fish_ready for coin (tf_sell). Cut the fish supply and
the whole chain stalls: no input -> no output -> no sale. Same shape for the
carpenter (lumber->furniture) and mason (stone->blocks).

ARCHITECTURE-RULE COMPLIANCE: a WORLD ADAPTER on BigvilleResourceWorld. No
decision about transform/sale -- those are the seed rules. The adapter mints
shops/customers, routes labourers to their shop, arms the sale act, and reads
state.
"""
from __future__ import annotations

from bigville.runtime import manifest_for
from worlds.bigville_resource_world import BigvilleResourceWorld  # noqa: E402


class BigvilleTradeWorld(BigvilleResourceWorld):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.eng.load_seed_manifest(manifest_for("bigville_trades"), None)
        self._shops = {}          # trade -> dict(nid, cell, in_stk, out_stk)
        self._customers = {}      # name -> Customer nid
        self._deliver_cell = {}   # labourer name -> shop cell to deliver to

    # ------------------------------------------------------------------ ingest
    def add_shop(self, trade, cell, *, input_kind, output_kind,
                 recipe_in=1.0, recipe_out=1.0, price=2.0, is_open=1):
        assert cell in self._cell_at, f"shop cell {cell} not walkable"
        shop = self.eng.add_node("Shop", {
            "trade": trade, "input_kind": input_kind, "output_kind": output_kind,
            "recipe_in": float(recipe_in), "recipe_out": float(recipe_out),
            "price": float(price), "open": float(is_open), "coin": 0.0})
        self.eng.add_edge_unchecked(shop, "at_cell", self._cell_at[cell])
        in_stk = self.eng.add_node("Stock", {"kind": input_kind, "amount": 0.0})
        self.eng.add_edge_unchecked(shop, "has_stock", in_stk)     # R1 delivery target
        out_stk = self.eng.add_node("Stock", {"kind": output_kind, "amount": 0.0})
        self.eng.add_edge_unchecked(shop, "has_output", out_stk)
        self._shops[trade] = dict(nid=shop, cell=tuple(cell), in_stk=in_stk, out_stk=out_stk)
        return shop

    def add_supplier(self, name, start, *, dep_kind, to_trade, yield_=2.0):
        """A labourer who extracts `dep_kind` and delivers to `to_trade`'s shop."""
        self.add_labourer(name, start, dep_kind=dep_kind, yield_=yield_)
        self._deliver_cell[name] = self._shops[to_trade]["cell"]
        return self._movers[name]

    def add_customer(self, name, trade, *, coin=100.0):
        """A customer stationed at `trade`'s shop who will buy its output."""
        cell = self._shops[trade]["cell"]
        cust = self.eng.add_node("Customer", {"name": name, "coin": float(coin),
                                              "bought": 0.0, "sale_armed": 0.0})
        self.eng.add_edge_unchecked(cust, "is_at", self._cell_at[cell])
        self._customers[name] = cust
        return cust

    # ---------------------------------------------------------------- tick
    def step(self, *, move=True, sell=True):
        """One economic tick: growback + transform settle; labourers shuttle
        deposit->shop delivering raw; transform again (input just arrived); then
        customers buy."""
        self.eng.set_attr(self._rtown, "epoch",
                          float(self.eng.node(self._rtown)["attrs"]["epoch"]) + 1.0)
        self._run()                                   # growback + transform
        if move:
            for name, info in self._labourers.items():
                m = self._movers[name]
                carrying = float(self.eng.node(m)["attrs"].get("carrying", 0.0))
                target = (self._deliver_cell[name] if carrying > 0
                          else self._deposit_cell[info["dep_kind"]])
                self.set_goal(name, target)
                self.move_one(name)
                if tuple(self.pos[name]) == tuple(target):
                    if carrying > 0:
                        self._run()                   # rx_deliver -> shop input
                    else:
                        self.eng.set_attr(m, "extract_armed", 1.0)
                        self._run()                   # rx_extract
            self._run()                               # tf_transform on delivered input
        if sell:
            for cust in self._customers.values():
                self.eng.set_attr(cust, "sale_armed", 1.0)
            self._run()                               # tf_sell (only if output>0)

    def run(self, T=60, **kw):
        for _ in range(T):
            self.step(**kw)
        return T

    # ------------------------------------------------- glass-box read-offs
    def input_stock(self, trade):
        return float(self.eng.node(self._shops[trade]["in_stk"])["attrs"]["amount"])

    def output_stock(self, trade):
        return float(self.eng.node(self._shops[trade]["out_stk"])["attrs"]["amount"])

    def shop_coin(self, trade):
        return float(self.eng.node(self._shops[trade]["nid"])["attrs"]["coin"])

    def bought(self, name):
        return float(self.eng.node(self._customers[name])["attrs"]["bought"])

    def customer_coin(self, name):
        return float(self.eng.node(self._customers[name])["attrs"]["coin"])
