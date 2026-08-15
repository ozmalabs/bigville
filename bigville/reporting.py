"""Population and economic reporting for the standalone Bigville simulation.

The simulator has access to the complete population and physical graph, so the
reporter can publish both an exact census and the estimates a real village
enumerator might obtain from a sample.  Reporting only reads world state; it
does not choose actions, alter beliefs, or create economic activity.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import copy
import math
import random
from statistics import median
from typing import Any

from domains import bigville_entities as E


def _round(value: float, places: int = 4) -> float:
    return round(float(value), places)


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None,
                "max": None, "p10": None, "p90": None}
    ordered = sorted(float(value) for value in values)

    def percentile(p: float) -> float:
        if len(ordered) == 1:
            return _round(ordered[0])
        position = (len(ordered) - 1) * p
        lower, upper = math.floor(position), math.ceil(position)
        if lower == upper:
            return _round(ordered[lower])
        fraction = position - lower
        return _round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)

    return {"n": len(ordered), "mean": _round(sum(ordered) / len(ordered)),
            "median": _round(median(ordered)), "min": _round(ordered[0]),
            "max": _round(ordered[-1]), "p10": percentile(0.10),
            "p90": percentile(0.90)}


def _counts(values: list[Any]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def _rate(numerator: int, denominator: int) -> float:
    return _round(numerator / denominator) if denominator else 0.0


def _gini(values: list[float]) -> float:
    values = sorted(max(0.0, float(value)) for value in values)
    if not values or sum(values) == 0.0:
        return 0.0
    total = sum(values)
    weighted = sum((index + 1) * value for index, value in enumerate(values))
    return _round((2.0 * weighted) / (len(values) * total) - (len(values) + 1) / len(values))


class SimulationReporter:
    """Read-only census, survey, economy, and social reporting over a world."""

    def __init__(self, world):
        self.world = world

    def _actor_rows(self) -> list[dict[str, Any]]:
        rows = []
        for name, node in sorted(self.world._actors.items()):
            attrs = self.world.eng.node(node)["attrs"]
            rows.append({
                "name": name,
                "role": attrs.get("role", ""),
                "group": attrs.get("group", ""),
                "class": attrs.get("klass", ""),
                "life_stage": attrs.get("life_stage", "adult"),
                "age": float(attrs.get("age", 0.0)),
                "alive": float(attrs.get("alive", 1.0)) == 1.0,
                "literate": float(attrs.get("literacy", 0.0)) >= E.LIT_FUNCTIONAL,
                "literacy": float(attrs.get("literacy", 0.0)),
                "coin": float(attrs.get("coin", 0.0)),
                "hunger": float(attrs.get("hunger", 0.0)),
                "health": attrs.get("health", "healthy"),
                "household": attrs.get("household", ""),
                "workplace": attrs.get("workplace_kind", attrs.get("role", "")),
                "employed": bool(attrs.get("work_x") is not None or
                                  list(self.world.eng.neighbours(node, "works_at"))),
            })
        return rows

    def _sample(self, rows: list[dict[str, Any]], sample_size: int | None, seed: int) -> dict[str, Any]:
        if not rows:
            return {"method": "sample", "frame_size": 0, "sample_size": 0,
                    "seed": int(seed), "estimates": {}}
        size = min(len(rows), max(1, int(sample_size or min(30, len(rows)))))
        chosen = random.Random(int(seed)).sample(rows, size)
        finite = math.sqrt(max(0.0, (len(rows) - size) / max(1, len(rows) - 1)))

        def proportion(key: str) -> dict[str, float | int]:
            values = [1.0 if row[key] else 0.0 for row in chosen]
            estimate = sum(values) / size
            se = math.sqrt(max(0.0, estimate * (1.0 - estimate) / size)) * finite
            return {"estimate": _round(estimate), "standard_error": _round(se),
                    "sample_size": size}

        def mean_estimate(key: str) -> dict[str, float | int]:
            values = [float(row[key]) for row in chosen]
            avg = sum(values) / size
            variance = sum((value - avg) ** 2 for value in values) / max(1, size - 1)
            return {"estimate": _round(avg),
                    "standard_error": _round(math.sqrt(variance / size) * finite),
                    "sample_size": size}

        return {"method": "simple_random_sample", "frame_size": len(rows),
                "sample_size": size, "seed": int(seed), "estimates": {
                    "alive_rate": proportion("alive"),
                    "literacy_rate": proportion("literate"),
                    "employment_rate": proportion("employed"),
                    "mean_age": mean_estimate("age"),
                    "mean_coin": mean_estimate("coin"),
                    "mean_hunger": mean_estimate("hunger"),
                    "class_share": {
                        key: _round(sum(row["class"] == key for row in chosen) / size)
                        for key in sorted({row["class"] for row in rows})},
                    "role_share": {
                        key: _round(sum(row["role"] == key for row in chosen) / size)
                        for key in sorted({row["role"] for row in rows})},
                }}

    def population(self, *, sample_size: int | None = 30, seed: int = 0) -> dict[str, Any]:
        rows = self._actor_rows()
        alive = [row for row in rows if row["alive"]]
        households = Counter(row["household"] for row in rows if row["household"])
        employed = [row for row in alive if row["employed"]]
        hungry = [row for row in alive if row["hunger"] > 0.0]
        exact = {
            "method": "census",
            "total": len(rows), "alive": len(alive), "deceased": len(rows) - len(alive),
            "alive_rate": _rate(len(alive), len(rows)),
            "literate": sum(row["literate"] for row in alive),
            "literacy_rate": _rate(sum(row["literate"] for row in alive), len(alive)),
            "hungry": len(hungry), "hunger_rate": _rate(len(hungry), len(alive)),
            "employed": len(employed), "employment_rate": _rate(len(employed), len(alive)),
            "by_role": _counts([row["role"] for row in alive]),
            "by_group": _counts([row["group"] for row in alive]),
            "by_class": _counts([row["class"] for row in alive]),
            "by_life_stage": _counts([row["life_stage"] for row in alive]),
            "by_workplace": _counts([row["workplace"] for row in employed]),
            "age": _summary([row["age"] for row in alive]),
            "coin": _summary([row["coin"] for row in alive]),
            "coin_gini": _gini([row["coin"] for row in alive]),
            "hunger": _summary([row["hunger"] for row in alive]),
            "households": {"count": len(households), "size": _summary(list(households.values())),
                           "members_without_household": len(rows) - sum(households.values())},
        }
        exact["sample_estimate"] = self._sample(rows, sample_size, seed)
        return exact

    def economy(self) -> dict[str, Any]:
        stock = {}
        total_value = 0.0
        food_qty = 0.0
        for kind, node in sorted(self.world._stock.items()):
            if kind == "none":
                continue
            attrs = self.world.eng.node(node)["attrs"]
            qty = max(0.0, float(attrs.get("qty", 0.0)))
            try:
                unit_value = float(E.reference_value(kind))
            except (KeyError, TypeError, ValueError):
                unit_value = 0.0
            value = qty * unit_value
            stock[kind] = {"quantity": _round(qty), "condition": _round(attrs.get("condition", 1.0)),
                           "perishable": bool(attrs.get("perishable", 0.0)),
                           "unit_reference_value": _round(unit_value), "reference_value": _round(value)}
            total_value += value
            if self.world._item_specs.get(kind, {}).get("food"):
                food_qty += qty

        resident_inventory_value = 0.0
        resident_food_qty = 0.0
        for actor in self.world._actors:
            for kind, qty in self.world.inventory(actor).items():
                try:
                    unit_value = float(E.reference_value(kind))
                except (KeyError, TypeError, ValueError):
                    unit_value = 0.0
                resident_inventory_value += float(qty) * unit_value
                if self.world._item_specs.get(kind, {}).get("food"):
                    resident_food_qty += float(qty)

        transactions = [self.world.eng.node(node)["attrs"] for node in self.world._transactions.values()]
        by_kind = defaultdict(lambda: {"count": 0, "quantity": 0.0, "value": 0.0})
        by_good = defaultdict(lambda: {"count": 0, "quantity": 0.0, "value": 0.0})
        for transaction in transactions:
            kind = str(transaction.get("kind", "unknown"))
            good = str(transaction.get("good", "unknown"))
            quantity = float(transaction.get("quantity", 0.0))
            value = float(transaction.get("value", 0.0))
            for bucket in (by_kind[kind], by_good[good]):
                bucket["count"] += 1; bucket["quantity"] += quantity; bucket["value"] += value
        for bucket in list(by_kind.values()) + list(by_good.values()):
            bucket["quantity"] = _round(bucket["quantity"]); bucket["value"] = _round(bucket["value"])

        shops = {}
        for trade, node in sorted(self.world._shops.items()):
            attrs = self.world.eng.node(node)["attrs"]
            workers = [row["name"] for row in self._actor_rows()
                       if row["alive"] and (row["workplace"] == trade or row["role"] == trade)]
            shops[trade] = {"input": attrs.get("input_kind", ""), "output": attrs.get("output_kind", ""),
                            "price": _round(attrs.get("price", 0.0)), "coin": _round(attrs.get("coin", 0.0)),
                            "workers": workers, "location": self.world.shop_position(trade)}

        storage = defaultdict(lambda: {"containers": 0, "quantity": 0.0})
        for name, (node, inners) in self.world._containers.items():
            attrs = self.world.eng.node(node)["attrs"]
            kind = str(attrs.get("kind", "carrier"))
            if kind == "carrier":
                continue
            storage[kind]["containers"] += 1
            storage[kind]["quantity"] += sum(float(self.world.eng.node(inner)["attrs"].get("qty", 0.0))
                                               for inner in inners.values())
        for bucket in storage.values():
            bucket["quantity"] = _round(bucket["quantity"])
        land = defaultdict(lambda: {"parcels": 0, "area": 0.0})
        for node in self.world._land.values():
            attrs = self.world.eng.node(node)["attrs"]
            use = str(attrs.get("use", "unknown"))
            land[use]["parcels"] += 1; land[use]["area"] += float(attrs.get("area", 0.0))
        for bucket in land.values():
            bucket["area"] = _round(bucket["area"])
        crops = Counter(self.world.eng.node(crop)["attrs"].get("crop", "unknown")
                        for crop in self.world._living_crops())
        animals = Counter(self.world.eng.node(node)["attrs"].get("species", "unknown")
                          for node in self.world._animals.values()
                          if float(self.world.eng.node(node)["attrs"].get("alive", 1.0)) == 1.0)
        return {"stock": stock, "stock_reference_value": _round(total_value),
                "resident_inventory_reference_value": _round(resident_inventory_value),
                "total_physical_reference_value": _round(total_value + resident_inventory_value),
                "food_quantity_in_stock": _round(food_qty),
                "food_quantity_held": _round(resident_food_qty),
                "food_quantity": _round(food_qty + resident_food_qty),
                "food_per_alive_resident": _round(
                    (food_qty + resident_food_qty) / max(1, sum(row["alive"] for row in self._actor_rows()))),
                "transactions": {"count": len(transactions), "value": _round(
                    sum(float(t.get("value", 0.0)) for t in transactions)),
                    "by_kind": dict(sorted(by_kind.items())), "by_good": dict(sorted(by_good.items()))},
                "shops": shops, "storage": dict(sorted(storage.items())),
                "land": dict(sorted(land.items())), "living_crops": dict(sorted(crops.items())),
                "living_animals": dict(sorted(animals.items())),
                "registered_land": len(self.world._titles),
                "unregistered_land": len(set(self.world._land) - set(self.world._titles))}

    def social(self) -> dict[str, Any]:
        bonds = [self.world.eng.node(node)["attrs"] for node in self.world._relationships.values()]
        relationship_kinds = _counts([bond.get("kind", "unknown") for bond in bonds])
        conversations = list(self.world._conversations.values())
        speech = list(self.world._speech_events)
        utterances = list(self.world._utterances.values())
        utterance_attrs = [self.world.eng.node(node)["attrs"] for node in utterances]
        notes = list(self.world._notes.values())
        requests = list(self.world._requests.values())
        return {
            "relationships": {"directed_bonds": len(bonds), "by_kind": relationship_kinds,
                              "mean_strength": _round(sum(float(b.get("strength", 0.0)) for b in bonds) / len(bonds)) if bonds else 0.0,
                              "mean_reliability": _round(sum(float(b.get("reliability", 0.0)) for b in bonds) / len(bonds)) if bonds else 0.0},
            "conversation": {"conversations": len(conversations), "utterances": len(utterances),
                              "speech_events": len(speech),
                              "heard_rate": _rate(sum(bool(event.get("heard")) for event in utterance_attrs),
                                                  len(utterance_attrs)),
                              "speakers": len({event.get("speaker") for event in utterance_attrs}),
                              "targets": len({event.get("target") for event in utterance_attrs
                                               if event.get("target")})},
            "public_life": {"events": len(self.world._events), "notes": len(notes), "requests": len(requests),
                            "articles": len(self.world._articles), "editions": len(self.world._editions),
                            "newspaper_copies": len(self.world._newspaper_copies),
                            "births": len(self.world._births), "deaths": len(self.world._deaths),
                            "land_disputes": len(self.world._land_disputes),
                            "law_proposals": len(self.world._proposals),
                            "justice_cases": len(self.world._cases)},
        }

    def ecology(self) -> dict[str, Any]:
        return {"animals": {"total": len(self.world._animals), "alive": sum(
                    float(self.world.eng.node(node)["attrs"].get("alive", 1.0)) == 1.0
                    for node in self.world._animals.values()),
                    "by_species": self.economy()["living_animals"]},
                "crops": {"beds": len(self.world._crops), "living": len(self.world._living_crops()),
                          "by_kind": self.economy()["living_crops"]},
                "land": self.economy()["land"]}

    def _series_metrics(self, report: dict[str, Any]) -> dict[str, float]:
        return {"alive": float(report["population"]["alive"]),
                "population_coin": float(report["population"]["coin"]["mean"] or 0.0),
                "food_quantity": float(report["economy"]["food_quantity"]),
                "stock_reference_value": float(report["economy"]["stock_reference_value"]),
                "transaction_value": float(report["economy"]["transactions"]["value"]),
                "transactions": float(report["economy"]["transactions"]["count"]),
                "relationships": float(report["social"]["relationships"]["directed_bonds"]),
                "utterances": float(report["social"]["conversation"]["utterances"])}

    def report(self, *, sample_size: int | None = 30, seed: int | None = None) -> dict[str, Any]:
        if seed is None:
            seed = int(getattr(self.world, "t100_seed", 305000)) + int(getattr(self.world, "_turn", 0))
        population = self.population(sample_size=sample_size, seed=seed)
        economy = self.economy()
        social = self.social()
        report = {"schema": "bigville/report/1", "clock": dict(self.world.calendar()),
                  "population": population, "economy": economy, "social": social,
                  "ecology": self.ecology(), "measurement": {
                      "population": "complete_census", "economy": "complete_physical_and_transaction_readout",
                      "social": "complete_recorded_graph_events", "sample_estimate": "simple_random_sample_with_fpc"}}
        current = self._series_metrics(report)
        history = getattr(self.world, "_report_history", [])
        report["series"] = {"current": current, "snapshots": len(history),
                             "history": self.history()}
        if history:
            previous = history[-1]["metrics"]
            report["changes_since_snapshot"] = {key: _round(value - float(previous.get(key, 0.0)))
                                                 for key, value in current.items()}
        else:
            report["changes_since_snapshot"] = {}
        return report

    def record_snapshot(self, *, label: str | None = None,
                        sample_size: int | None = 30, seed: int | None = None) -> dict[str, Any]:
        report = self.report(sample_size=sample_size, seed=seed)
        sequence = len(getattr(self.world, "_report_history", [])) + 1
        snapshot = {"id": sequence, "label": label or f"snapshot:{sequence}",
                    "clock": dict(report["clock"]), "metrics": report["series"]["current"]}
        self.world._report_history.append(snapshot)
        report["snapshot"] = snapshot
        report["series"]["snapshots"] = len(self.world._report_history)
        report["series"]["history"] = self.history()
        return report

    def history(self) -> list[dict[str, Any]]:
        return copy.deepcopy(getattr(self.world, "_report_history", []))
