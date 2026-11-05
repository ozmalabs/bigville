"""Dump every existing physical placement of the 100-resident town, to compare before and after Phase 004."""
import json
import sys

sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "/home/matt/ozmadev/bigville")
from worlds.bigville_world import BigvilleWorld  # noqa: E402
from worlds.bigville_town100_world import build_town_100  # noqa: E402
from domains.data_view import entities  # noqa: E402

out = {}
E = entities()
grid, aff, layout = build_town_100(305000, E)
out["layout"] = {k: v for k, v in layout.items() if k != "sites"}
out["grid_hash"] = hash(tuple(tuple(r) for r in grid)) if False else sum(
    (i + 1) * (x + 1) * (t + 2) for i, row in enumerate(grid) for x, t in enumerate(row))
w = BigvilleWorld.from_town100(305000)
out["deposits"] = {k: list(map(int, w.map_position_node(n) or (-1, -1)))
                   for k, n in sorted(w._resource_deposits.items())}
out["actor_positions"] = {k: list(v) for k, v in sorted(w._actor_positions.items())}
out["land_cells"] = {k: list(w.map_position_node(v)) for k, v in sorted(w._land_cells.items())}
out["household_cells"] = {k: list(w.map_position_node(v)) for k, v in sorted(w._household_cells.items())}
out["animals"] = {k: str(w.map_position(k)) for k in sorted(w._animals)}
out["places"] = {k: str(w.map_position(k)) for k in sorted(getattr(w, "_places", {}))}
out["building_sites"] = {k: list(v) for k, v in sorted(w._building_sites.items())}
out["shops"] = sorted(str(k) for k in getattr(w, "_shops", {}))
out["infrastructure"] = sorted(str(k) for k in getattr(w, "_infrastructure", {}))
print(json.dumps(out, sort_keys=True, indent=1, default=str))
