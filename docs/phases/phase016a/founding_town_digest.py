"""Digest of the founding town (Phase 016a): one canonical JSON that must not change when the town's
content moves from code into the data pack.

Run with PYTHONHASHSEED=0 from a repository root (the working tree, or an export of HEAD with the
same layout):

    PYTHONHASHSEED=0 python3 docs/phases/phase016a/founding_town_digest.py > out.json

It builds BigvilleWorld.from_town100() and dumps, in canonical form (sorted keys, ints and floats as
JSON writes them): every resident's graph attributes, position, and household; every household,
land record, and farm; the stock; the building sites and places; the map layout (deposits, work
anchors, farms, homes, building sites, square, component size), a hash of the tile grid, the map
affordances, the node-type counts of the whole graph (this includes Kin, Union, and KinTerm nodes),
each resident's held kin terms, a hash of the world RNG state, and the same state again after three
village work ticks (`_village_work_tick` for periods 0, 1, 2) with each tick's return value.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

from worlds.bigville_world import BigvilleWorld  # noqa: E402
from worlds.bigville_town100_world import BigvilleTown100World, build_town_100  # noqa: E402


def _plain(value):
    """JSON-ready copy: tuples become lists, sets become sorted lists, unknown objects become str."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(v) for v in value), key=repr)
    if isinstance(value, float):
        return float(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    return str(value)


def _attrs(world, node):
    return _plain(dict(world.eng.node(node)["attrs"]))


def _state(world):
    out = {}
    out["residents"] = {}
    for name in sorted(world._actors):
        node = world._actors[name]
        out["residents"][name] = {
            "attrs": _attrs(world, node),
            "position": _plain(world._actor_positions.get(name)),
            "household": world._t100_households.get(name),
            "kin_terms_held": _plain(world.kin_terms_held(name)),
        }
    out["households"] = {name: _attrs(world, node) for name, node in sorted(world._households.items())}
    out["household_cells"] = sorted(world._household_cells)
    out["land"] = {name: _attrs(world, node) for name, node in sorted(world._land.items())}
    out["land_cells"] = {name: _plain(world._land_cells.get(name)) for name in sorted(world._land)}
    out["stock"] = {k: round(float(world.qty(k)), 6) for k in sorted(world._stock)}
    out["building_sites"] = {k: _plain(v) for k, v in sorted(world._building_sites.items())}
    out["places"] = sorted(world._places)
    out["map_layout"] = _plain(world._map_layout)
    grid_text = json.dumps(world._map_grid, separators=(",", ":"))
    out["map_grid"] = {"sha256": hashlib.sha256(grid_text.encode()).hexdigest(),
                       "width": len(world._map_grid[0]) if world._map_grid else 0,
                       "height": len(world._map_grid or [])}
    out["map_cells"] = len(world._map_cells)
    out["map_affordances"] = _plain(world._map_affordances)
    out["map_node"] = _attrs(world, world._map_node)
    out["node_types"] = dict(sorted(collections.Counter(
        world.eng.node(n)["type"] for n in world.eng.nodes()).items()))
    index = world._kin_index()
    out["kin_index"] = {k: (len(v) if hasattr(v, "__len__") else str(v)) for k, v in sorted(index.items())}
    out["rng_state_sha256"] = hashlib.sha256(repr(world._rng.getstate()).encode()).hexdigest()
    return out


def main():
    world = BigvilleWorld.from_town100()
    before = _state(world)
    returns = [_plain(world._village_work_tick(period)) for period in range(3)]
    after = _state(world)
    digest = {"founding_town": before, "returns_of_three_village_work_ticks": returns,
              "after_three_village_work_ticks": after,
              "cast100_record": _plain(world._cast100),
              "scenario_character_data": _plain(world._scenario_character_data)}
    # The module-level map builder and the BigvilleTown100World adapter (the 013b digest's surface).
    grid, affordances, layout = build_town_100(305000)
    digest["build_town_100"] = {"grid_sha256": hashlib.sha256(json.dumps(grid).encode()).hexdigest(),
                                "layout": _plain(layout), "affordances": _plain(affordances)}
    adapter = BigvilleTown100World(seed=305000)
    digest["adapter"] = {
        "residents": _plain(adapter.residents),
        "cast": _plain(adapter.cast),
        "deposits": [_attrs(adapter, n) for n in adapter.eng.nodes("Deposit") + adapter.eng.nodes("ResourceDeposit")],
        "shops": [_attrs(adapter, n) for n in adapter.eng.nodes("Shop")],
        "stores": [_attrs(adapter, n) for n in adapter.eng.nodes("Store")],
        "resident_nodes": [_attrs(adapter, n) for n in adapter.eng.nodes("Resident")],
    }
    print(json.dumps(digest, sort_keys=True, indent=1))


if __name__ == "__main__":
    main()
