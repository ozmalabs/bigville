"""Package 14: complementary actors move crop output through real turns."""
from __future__ import annotations

from dataclasses import replace

from bigville.api import create_game
from bigville.backends import SimplePolicy, register_simple_profile
from bigville.scenarios import load_scenario


class _RoleChoice:
    def __init__(self, role):
        self.role = role
        self.grain_delivered = False
        self.carries_output_bread = False
        self.bread_delivered = False

    def score_adjustment(self, backend, context, option):
        action = option.get("action")
        if self.role == "farmer":
            if action == "eat" and option.get("kind") == "bread" and context.observations.get("hunger", 0) > 0:
                return 4000
            return {"water": 3000, "harvest": 2000, "sow": 1000}.get(action, -1000)
        if self.role == "carrier":
            cargo = context.observations.get("inventory", {})
            previous = getattr(backend, "last_choice", {})
            if (previous.get("action") == "fetch" and previous.get("kind") == "bread"
                    and self.grain_delivered):
                self.carries_output_bread = True
            if (previous.get("action") == "transfer" and previous.get("recipient") == "Eater"):
                if previous.get("kind") == "grain":
                    self.grain_delivered = True
                    backend.policy = replace(backend.policy, stock_fetch_kinds=("bread",))
                elif previous.get("kind") == "bread":
                    self.bread_delivered = True
                    self.carries_output_bread = False
                    backend.policy = replace(backend.policy, allow_stock_fetches=False)
            if self.grain_delivered and not self.bread_delivered:
                at_store = context.observations.get("position") == (2, 1)
                backend.policy = replace(backend.policy,
                                         allow_travel=self.carries_output_bread or not at_store)
            if action == "eat" and option.get("kind") == "bread" and context.observations.get("hunger", 0) > 0:
                return (-1000 if self.carries_output_bread
                        else 4000 if not cargo.get("grain", 0) and not cargo.get("bread", 0)
                        else -1000)
            if (action == "fetch" and option.get("kind") == "grain"
                    and not self.grain_delivered
                    and cargo.get("grain", 0) < 1):
                return 3000
            if (action == "fetch" and option.get("kind") == "bread"
                    and self.grain_delivered and not self.bread_delivered
                    and cargo.get("bread", 0) < 1):
                return 5000
            inventory = cargo
            if (action == "move" and option.get("destination") == (2, 1)
                    and not inventory.get("grain", 0)
                    and (not self.grain_delivered or not self.carries_output_bread)
                    and not self.bread_delivered):
                return 5000
            if (action == "move" and option.get("recipient") == "Eater"
                    and ((not self.grain_delivered and inventory.get("grain", 0) >= 1)
                         or (self.grain_delivered and self.carries_output_bread
                             and not self.bread_delivered))):
                return 5000
            if (action == "transfer" and option.get("kind") == "grain"
                    and option.get("recipient") == "Eater" and not self.grain_delivered):
                return 6000
            if (action == "transfer" and option.get("kind") == "bread"
                    and option.get("recipient") == "Eater" and self.grain_delivered
                    and self.carries_output_bread and not self.bread_delivered):
                return 6000
            return -1000
        if self.role == "miller":
            if action == "eat" and option.get("kind") == "bread" and context.observations.get("hunger", 0) > 0:
                return 3000
            return 4000 if action == "work" and option.get("recipe") == "grind_flour" else -1000
        if self.role == "baker":
            if action == "eat" and option.get("kind") == "bread" and context.observations.get("hunger", 0) > 0:
                return 3000
            return 4000 if action == "work" and option.get("recipe") == "bake_bread" else -1000
        if action == "eat" and option.get("kind") == "grain":
            return 3000
        if action == "eat" and option.get("kind") == "bread" and context.observations.get("hunger", 0) > 0:
            return 4000
        return -1000


def _game(*, seed=1414, water=6, participants=True):
    register_simple_profile("pkg14.farmer", SimplePolicy(hook=_RoleChoice("farmer"),
                                                          allow_travel=False,
                                                          allow_work=False), replace=True)
    register_simple_profile("pkg14.carrier", SimplePolicy(hook=_RoleChoice("carrier"),
                                                          allow_transfers=True,
                                                          allow_stock_fetches=True,
                                                          stock_fetch_kinds=("grain",),
                                                          allow_work=False), replace=True)
    register_simple_profile("pkg14.eater", SimplePolicy(hook=_RoleChoice("eater"),
                                                         allow_travel=False,
                                                         allow_work=False), replace=True)
    register_simple_profile("pkg14.miller", SimplePolicy(hook=_RoleChoice("miller"),
                                                          allow_travel=False), replace=True)
    register_simple_profile("pkg14.baker", SimplePolicy(hook=_RoleChoice("baker"),
                                                         allow_travel=False), replace=True)
    definition = load_scenario("work_food_exchange").to_dict()
    definition["actors"] = [dict(actor, **({"simple_profile": "pkg14.eater"}
                                             if actor["name"] == "Eater" else {}))
                            for actor in definition["actors"]]
    if not participants:
        definition["actors"] = [actor for actor in definition["actors"]
                                if actor["name"] not in {"Carrier", "Miller", "Baker"}]
    rations = ({"Farmer": 8.0, "Carrier": 24.0, "Eater": 12.0,
                "Miller": 12.0, "Baker": 12.0}
               if participants else {"Farmer": 3.0, "Eater": 3.0})
    definition["stocks"] = {"wheat_seed": 1, "water": water + 1,
                             "bread": sum(rations.values())}
    game = create_game(scenario=definition, seed=seed, autonomous=True, ticks_per_period=2)
    game.world.add_land("farm_plot_00", use="arable", soil="loam", cell=(1, 1))
    # Finite startup bread keeps the initial workers alive until the crop and
    # the grain-to-flour-to-bread work path can supply food.
    for actor in game.backends:
        game.world._move_stock_to_inventory(actor, "bread", rations[actor])
    return game


def _snapshot(world):
    return {
        "grain_stock": world.qty("grain"),
        "flour_stock": world.qty("flour"),
        "bread_stock": world.qty("bread"),
        "seed": world.qty("wheat_seed"),
        "water": world.qty("water"),
        "farmer": world.inventory_qty("Farmer", "grain"),
        "carrier": world.inventory_qty("Carrier", "grain") if "Carrier" in world._actors else 0,
        "eater": world.inventory_qty("Eater", "grain"),
        "eater_bread": world.inventory_qty("Eater", "bread"),
    }


def _trace(game, turns=28):
    world = game.world
    trace = []
    for _ in range(turns):
        contexts = {name: game._context(name) for name in game.backends}
        before = _snapshot(world)
        result = game.step()
        selected = {}
        for name, response in game.last_responses.items():
            proposal = response.major_action
            selected[name] = ({"action": proposal.action, "params": proposal.params,
                               "reason": proposal.reason} if proposal else None)
        trace.append({"turn": world._turn,
                      "period": float(world.eng.node(world._town)["attrs"].get("period", 0)),
                      "observations": {name: context.observations for name, context in contexts.items()},
                      "affordances": {name: context.affordances for name, context in contexts.items()},
                      "selected_actions": selected,
                      "results": dict(game.last_results), "status": result["status"],
                      "before": before, "after": _snapshot(world)})
    return trace


def test_work_food_and_exchange_trace_physical_provenance_and_shortage_control():
    game = _game()
    trace = _trace(game)
    world = game.world
    selected = lambda row, actor: row["selected_actions"].get(actor) or {}
    assert any(selected(row, "Farmer").get("action") == "sow" for row in trace)
    assert any(selected(row, "Farmer").get("action") == "harvest" for row in trace)
    assert any(selected(row, "Carrier").get("action") == "fetch" for row in trace)
    # Acquisition is a cognition choice over a reachable, capacity-safe town
    # stock affordance. It moves the existing grain rather than allocating it.
    fetch_rows = [row for row in trace
                  if selected(row, "Carrier").get("action") == "fetch"
                  and selected(row, "Carrier").get("params", {}).get("kind") == "grain"]
    assert fetch_rows
    assert any(any(option.get("action") == "move" and option.get("destination") == (2, 1)
                   for option in row["affordances"]["Carrier"]) for row in trace)
    assert sum(max(0.0, row["before"]["grain_stock"] - row["after"]["grain_stock"])
               for row in trace) == 7.0  # one delivery plus two three-grain milling batches
    assert any(selected(row, "Carrier").get("action") == "move"
               and selected(row, "Carrier").get("params", {}).get("recipient") == "Eater"
               for row in trace)
    assert any(selected(row, "Carrier").get("action") == "transfer"
               and selected(row, "Carrier").get("params", {}).get("recipient") == "Eater"
               for row in trace)
    assert (trace[-1]["after"]["grain_stock"] + trace[-1]["after"]["carrier"]
            + trace[-1]["after"]["eater"] + 6.0 == 8.0)
    # The Farmer remains at the plot, outside the mapped store; an explicit
    # fetch still fails at the physical reach check and leaves stock unchanged.
    assert world.actor_position("Farmer") != world.map_position_node(world._store)
    stock_before_failed_fetch = world.qty("grain")
    assert not world.fetch("Farmer", "grain")
    assert world.qty("grain") == stock_before_failed_fetch
    assert any(selected(row, "Carrier").get("action") == "transfer" for row in trace)
    assert any(selected(row, "Miller").get("action") == "work"
               and selected(row, "Miller").get("params", {}).get("recipe") == "grind_flour"
               for row in trace)
    assert any(selected(row, "Baker").get("action") == "work"
               and selected(row, "Baker").get("params", {}).get("recipe") == "bake_bread"
               for row in trace)
    bread_output_turn = next(row["turn"] for row in trace
                             if row["after"]["bread_stock"] > row["before"]["bread_stock"])
    bread_fetch_turn = next(row["turn"] for row in trace
                            if selected(row, "Carrier").get("action") == "fetch"
                            and selected(row, "Carrier").get("params", {}).get("kind") == "bread")
    bread_delivery_turn = next(row["turn"] for row in trace
                               if selected(row, "Carrier").get("action") == "transfer"
                               and selected(row, "Carrier").get("params", {}).get("kind") == "bread")
    assert bread_output_turn < bread_fetch_turn < bread_delivery_turn
    assert any(row["turn"] > bread_delivery_turn
               and selected(row, "Eater").get("action") == "eat"
               and selected(row, "Eater").get("params", {}).get("kind") == "bread"
               for row in trace)
    assert world.qty("grain") == 1.0
    assert world.inventory_qty("Farmer", "grain") == 0
    assert world.inventory_qty("Carrier", "grain") == 0
    assert world.inventory_qty("Eater", "grain") == 1.0
    # One sowed seed returns and produces eight grain: the carrier delivers
    # one, the miller processes two three-grain batches into four flour, and
    # one grain remains in town stock.
    assert any(row["after"]["seed"] == 1.0 for row in trace)
    assert any(row["turn"] > next(row["turn"] for row in trace
                                   if row["after"]["seed"] == 1.0)
               and selected(row, "Farmer").get("action") == "sow" for row in trace)
    assert world.qty("wheat_seed") == 0.0
    assert sum(max(0.0, row["after"]["grain_stock"] - row["before"]["grain_stock"])
               for row in trace) == 8.0
    assert world.qty("flour") == 2.0
    assert world.qty("bread") == 2.0
    assert world.inventory_qty("Eater", "bread") == 0.0
    assert all(row["after"]["grain_stock"] >= 0 for row in trace)

def test_shortage_control_without_carrier_leaves_harvest_in_town_stock():
    # Without the carrier, harvesting still creates only physical town stock;
    # no actor is silently allocated the output and the hungry consumer starves.
    control = _game(seed=1414, water=6, participants=False)
    control_trace = _trace(control, turns=18)
    assert control.world.qty("grain") == 8.0
    assert control.world.inventory_qty("Eater", "grain") == 0.0
    assert not any((row["selected_actions"].get("Eater") or {}).get("action") == "eat"
                   and (row["selected_actions"].get("Eater") or {}).get("params", {}).get("kind") == "grain"
                   for row in control_trace)
    assert control.world.hunger("Eater") > 0
    assert any("fetch" not in [option.get("action") for option in row["affordances"]["Eater"]]
               for row in control_trace)
