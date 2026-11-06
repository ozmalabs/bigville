"""Golden numbers for Phase 050: run before and after the change, compare the output.

Run from the repository root: python3 docs/phases/phase050/golden_before.py
"""
import math
import sys

sys.path.insert(0, ".")
from domains import bigville_entities as E  # noqa: E402
from worlds.bigville_world import BigvilleWorld as World  # noqa: E402


def smith():
    w = World(exhaustion_slow_on=False)
    w.add_tradesperson("Smith", "smith")
    w.eng.set_attr(w._bodies["Smith"], "str_base", 1.3)
    w.set_stock("iron", 10)
    w.set_stock("charcoal", 10)
    x, y, _fw, _fh = w._building_sites["forge"]
    w._move_actor_to("Smith", (x, y))
    return w


def job_spend(name, hunger):
    w = smith()
    w.eng.set_attr(w._actor("Smith"), "hunger", float(hunger))
    start = w.stamina_reserve("Smith")
    minutes = float(next(r for r in E.RECIPES if r["name"] == name)["time_minutes"])
    ticks = int(math.ceil(minutes / float(E.TIME["minutes_per_tick"])))
    w.start("Smith", name)
    for _ in range(ticks):
        w.eng.set_attr(w._actor("Smith"), "hunger", float(hunger))
        w.tick(1)
        if not w.busy("Smith"):
            break
    return round(start - w.stamina_reserve("Smith"), 6), round(w.eng.node(w._actor("Smith"))["attrs"].get("hunger", 0.0), 6)


def instant_spend(name, hunger):
    w = smith()
    w.eng.set_attr(w._actor("Smith"), "hunger", float(hunger))
    start = w.stamina_reserve("Smith")
    w.do("Smith", name)
    return round(start - w.stamina_reserve("Smith"), 6)


def walk_moves(reserve, turns=60):
    w = World(autonomous_actors=False)
    cells = sorted(w._map_cells)
    w.add_actor("Ada", role="hand", home_cell=cells[len(cells) // 2])
    flat = {**dict(E.TERRAIN_MOVEMENT["grass"]), "terrain": "grass", "move_time": 1.0, "stamina_multiplier": 1.0}
    w.terrain_state = lambda cell: dict(flat)
    w._wear_cell_by_traversal = lambda actor, cell: None
    here = w.actor_position("Ada")
    other = next(c for c in sorted(w._map_cells) if c != here and w.distance(here, c) == 1)
    moved = 0
    for _ in range(turns):
        w.eng.set_attr(w._bodies["Ada"], "stamina_reserve", float(reserve))
        w.eng.set_attr(w._actors["Ada"], "hunger", 0.0)
        w.actor_tick("Ada")
        dest = other if w.actor_position("Ada") == here else here
        before = w.actor_position("Ada")
        w.major_action("Ada", "move", destination=dest)
        moved += w.actor_position("Ada") != before
    return moved


if __name__ == "__main__":
    print("plough spend hunger0", job_spend("forge_plough", 0.0))
    print("plough spend hunger2", job_spend("forge_plough", 2.0))
    print("knife spend hunger0", job_spend("forge_knife", 0.0))
    print("knife instant hunger0", instant_spend("forge_knife", 0.0))
    print("knife instant hunger2", instant_spend("forge_knife", 2.0))
    for r in (0.9, 0.5, 0.2):
        print("walk moves reserve", r, walk_moves(r))
    print("contest reference: E.CONTEST base_cost", E.CONTEST["base_cost"])
