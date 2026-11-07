"""map_memory.py -- the fogged map a resident holds (Phase 053).

A fogged resident is one whose backend sets `fogged = True` (the LLM and human backends). Its map is one
MemoryRecord of kind KIND in its own memories, so the character checkpoints it with everything else. The
map is the resident's belief. The world publishes the ground and the places; this module decides what the
resident has learned of them, at three levels:

    0 hidden   nothing known, not even that it exists (absent from the map).
    1 vague    the place, its name and roughly where it is (a band of distance and a compass word, from the
               true position). The paths between known places.
    2 full     the ground cell by cell (the terrain as last seen, and whether people were seen there), and the
               exact place.

The record's content (plain JSON):
    {"type": "map", "cells": {"x,y": {"seen": turn, "terrain": name, "people": n}},
     "places": {name: {"level": 1 or 2, "seen": turn, "cells": [[x, y], ...] (level 2 only)}},
     "routes": [[a, b], ...], "told": [memory_id, ...], "founded": turn}

Functions:
    is_fogged(game, actor)                      the backend's flag
    ensure_map(game, actor)                     the record's content, created at founding from Phase 019
    learn_all(game)                             end of turn: every fogged resident learns (see refresh)
    refresh(game, actor)                        the cells in sight, the places in landmark sight, and any new
                                                place_belief memory (told by speech, or read)
    route_plan(game, actor, plan)               a move's destination, from a bound row or from `toward`
    map_section(game, actor, centre, radius)    the agent view's `map` section (words, levels and labels)
    can_words(game, actor, cell)                how a move to this cell is worded in the view, or None

The world is read only for what the resident holds: a place's true position is used once the resident
holds that place at level 1 or 2. Nothing lowers a level. Remembered detail ages, and the view says how long
ago it was last seen.

Limits: sight occluders (HEARING.sight_occluders) are not applied, so every cell within sight_range is seen.
A place told with a position is marked at level 2 with its cell's terrain as the world has it at that time.
"""
from __future__ import annotations

import math
import re
from collections import deque

from domains.data_view import entities
from domains.pack import load_pack

KIND = "map_memory"
SOURCE = "map_memory"
TELL_KIND = "place_belief"
LEVEL_HIDDEN, LEVEL_VAGUE, LEVEL_FULL = 0, 1, 2
LEVEL_WORDS = {LEVEL_HIDDEN: "hidden", LEVEL_VAGUE: "vague", LEVEL_FULL: "full"}
# The compass sectors, in the order of the angle from east, counter-clockwise (east = 0 degrees).
_SECTORS = ("e", "ne", "n", "nw", "w", "sw", "s", "se")
# Words for a heading typed in full ("north-east") or by code ("ne"), mapped to a unit step.
_STEPS = {"n": (0, -1), "ne": (1, -1), "e": (1, 0), "se": (1, 1), "s": (0, 1), "sw": (-1, 1),
          "w": (-1, 0), "nw": (-1, -1)}
_PLACE_MIN_WORD = 4


# ----------------------------------------------------------------- basics
def is_fogged(game, actor) -> bool:
    """True when the resident's backend holds its knowledge in words (the LLM and human backends)."""
    return bool(getattr(game.backends.get(actor), "fogged", False))


def _key(cell) -> str:
    return f"{int(cell[0])},{int(cell[1])}"


def _cell(value):
    """A cell from a stored position: [x, y], or a building site (x, y, w, h), whose first two values are its cell
    (the world places a building by them)."""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return (int(value[0]), int(value[1]))
        except (TypeError, ValueError):
            return None
    return None


def _chebyshev(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _bounds(world):
    grid = getattr(world, "_map_grid", None)
    if not grid:
        return None
    return len(grid[0]), len(grid)


def _inside(cell, bounds) -> bool:
    return bounds is None or (0 <= cell[0] < bounds[0] and 0 <= cell[1] < bounds[1])


def _sight(world) -> int:
    return int(load_pack(world.data_pack)["HEARING"]["sight_range"])


def _rules(world) -> dict:
    return load_pack(world.data_pack)["FOG_RULES"]


def _terrain(world, cell) -> str:
    """The terrain name of a cell as the world has it. Walls and water are not in the walkable map, so
    their name comes from the grid tile."""
    if cell in world._map_cells:
        return str(world.terrain_state(cell)["terrain"])
    from worlds.bigville_sim_world import TILE_NAME  # the same table the world builds its grid from
    return str(TILE_NAME.get(world.map_tile(cell), "grass"))


def _registry(game) -> dict:
    """Each named place's cells on the founding ground, from the world's layout. This is the world's
    truth. A resident reads it only for a place it holds (see `_cells_of`)."""
    cached = getattr(game, "_fog_registry", None)
    if cached is not None:
        return cached
    world = game.world
    out: dict[str, list] = {}

    def add(name, cell):
        point = _cell(cell)
        if point is None:
            return
        cells = out.setdefault(str(name).lower(), [])
        if point not in cells:
            cells.append(point)

    for name, site in (getattr(world, "_building_sites", None) or {}).items():
        add(name, site)
    layout = getattr(world, "_map_layout", None) or {}
    for name, cell in (layout.get("work") or {}).items():
        add(name, cell)
    for kind, cell in (layout.get("deposits") or {}).items():
        add(kind, cell)
    farms = layout.get("farms") or []
    for cell in farms:
        add("field", cell)
    if farms:
        add("pasture", farms[0])
    registry = {name: sorted(cells) for name, cells in out.items()}
    game._fog_registry = registry
    return registry


def _structures(game) -> set:
    """The names a resident can see from beyond sight: the founding buildings and workplaces, and the public
    landmarks. Deposits and farm ground are not structures."""
    cached = getattr(game, "_fog_structures", None)
    if cached is not None:
        return cached
    world = game.world
    names = set(getattr(world, "_building_sites", None) or {})
    names |= set(((getattr(world, "_map_layout", None) or {}).get("work") or {}))
    names |= set(load_pack(world.data_pack)["FOG_PUBLIC_LANDMARKS"])
    game._fog_structures = names
    return names


def _occupants(world) -> dict:
    """How many living residents stand on each cell (a count only: the view does not name them here)."""
    out: dict = {}
    for name, cell in world._actor_positions.items():
        if cell is not None and world.is_alive(name):
            out[tuple(cell)] = out.get(tuple(cell), 0) + 1
    return out


# ----------------------------------------------------------------- words
def _word(name, pack) -> str:
    """The place's name in words with its article: 'the mill', 'your home'."""
    words = load_pack(pack)["FOG_PLACE_WORDS"]
    if name in words:
        return words[name]
    label = (entities(pack).FOUNDING_PLACE_LABELS or {}).get(name)
    if label:
        text = str(label).lower()
        return "the " + (text[4:] if text.startswith("the ") else text)
    return "the " + str(name).replace("_", " ")


def _bare(name, pack) -> str:
    """The place's name without its article, for 'walk to the <name>': 'mill', 'home'."""
    word = _word(name, pack)
    for article in ("the ", "your "):
        if word.startswith(article):
            return word[len(article):]
    return word


def _sector(dx, dy) -> str:
    """The compass sector of a step, as a code (north is up, so y falls toward north)."""
    angle = math.degrees(math.atan2(-dy, dx)) % 360.0
    return _SECTORS[int(((angle + 22.5) % 360.0) // 45.0)]


def _direction_word(code, pack) -> str:
    for entry in load_pack(pack)["FOG_WORDS"]["directions"]:
        if entry["code"] == code:
            return entry["word"]
    raise KeyError(f"FOG_WORDS has no direction '{code}'")


def _where(here, cells, pack) -> str:
    """Roughly where a place is from the resident: a distance band and a heading, from the true cell nearest
    to the resident. A band with direction false gives the phrase alone (right beside you)."""
    target = min(cells, key=lambda cell: (_chebyshev(here, cell), cell))
    dx, dy = target[0] - here[0], target[1] - here[1]
    distance = max(abs(dx), abs(dy))
    band = next(entry for entry in load_pack(pack)["FOG_WORDS"]["distances"]
                if distance <= int(entry["max_cells"]))
    if not band.get("direction", True) or distance == 0:
        return band["phrase"]
    return f"{band['phrase']} {_direction_word(_sector(dx, dy), pack)}"


def age_phrase(ticks, pack) -> str:
    """How long ago, in words: 'earlier today', 'a season ago'."""
    ticks = max(0, int(ticks))
    for entry in load_pack(pack)["FOG_WORDS"]["ages"]:
        if ticks <= int(entry["max_ticks"]):
            return entry["phrase"]
    return load_pack(pack)["FOG_WORDS"]["ages"][-1]["phrase"]


# ----------------------------------------------------------------- the record
def _new_content(turn) -> dict:
    return {"type": "map", "cells": {}, "places": {}, "routes": [], "told": [], "founded": int(turn)}


def _record(character):
    for memory in character.memories:
        if memory.kind == KIND:
            return memory
    return None


def _see_cell(world, content, cell, turn, bounds):
    if not _inside(cell, bounds):
        return
    content["cells"][_key(cell)] = {"seen": int(turn), "terrain": _terrain(world, cell),
                                    "people": _occupants(world).get(cell, 0)}


def _path(world, start, goal) -> list:
    """The shortest walk on the walkable map between two cells (breadth first, four neighbours)."""
    if start not in world._map_cells or goal not in world._map_cells:
        return []
    came = {start: None}
    queue = deque([start])
    while queue:
        point = queue.popleft()
        if point == goal:
            break
        for step in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (point[0] + step[0], point[1] + step[1])
            if nxt in world._map_cells and nxt not in came:
                came[nxt] = point
                queue.append(nxt)
    if goal not in came:
        return []
    out, point = [], goal
    while point is not None:
        out.append(point)
        point = came[point]
    return out


def _founding_content(game, actor) -> dict:
    """The resident's map at founding, from Phase 019's knowledge of places (their memories) and the public
    landmarks. An exact place is level 2 around its cell, and the routes from home to each routine place are
    level 2. A rough place is level 1. A place the resident does not hold (none) is absent."""
    world = game.world
    pack = world.data_pack
    rules = _rules(world)
    turn = int(world._turn)
    bounds = _bounds(world)
    registry = _registry(game)
    content = _new_content(turn)
    home = world.actor_position(actor)
    for name in load_pack(pack)["FOG_PUBLIC_LANDMARKS"]:
        if name in registry:
            content["places"][name] = {"level": LEVEL_VAGUE, "seen": turn}
    exact, rough = [], []
    for memory in game.characters[actor].memories:
        item = memory.content
        if not (isinstance(item, dict) and item.get("type") == "place" and item.get("aware")):
            continue
        name = str(item.get("name", "")).lower()
        if not name:
            continue
        location = item.get("location", "none")
        if location == "exact":
            cells = [_cell(item.get("position"))] if _cell(item.get("position")) else registry.get(name, [])
            cells = [cell for cell in cells if cell is not None]
            if cells:
                exact.append((name, cells))
        elif location == "roughly":
            rough.append(name)
    if home is not None and all(name != "home" for name, _ in exact):
        exact.insert(0, ("home", [home]))
    for name in rough:
        if name not in content["places"] and name not in dict(exact):
            content["places"][name] = {"level": LEVEL_VAGUE, "seen": turn}
    for name, cells in exact:
        content["places"][name] = {"level": LEVEL_FULL, "seen": turn, "cells": [list(c) for c in cells]}
        for cell in cells:
            for dy in range(-rules["exact_radius"], rules["exact_radius"] + 1):
                for dx in range(-rules["exact_radius"], rules["exact_radius"] + 1):
                    _see_cell(world, content, (cell[0] + dx, cell[1] + dy), turn, bounds)
    if home is not None:
        for name, cells in exact:
            if name == "home" or not cells:
                continue
            goal = min(cells, key=lambda cell: (_chebyshev(home, cell), cell))
            for cell in _path(world, home, goal):
                _see_cell(world, content, cell, turn, bounds)
            content["routes"].append(["home", name])
    return content


def ensure_map(game, actor) -> dict:
    """The resident's map content, created at founding if the resident has none. The content is the record's
    own dict, so changes to it are changes to the record."""
    character = game.characters[actor]
    record = _record(character)
    if record is not None:
        return record.content
    from bigville.character import MemoryRecord  # the character module imports nothing from domains
    content = _founding_content(game, actor)
    character.memories.append(MemoryRecord(
        memory_id=f"map:{actor}", content=content, kind=KIND, source=SOURCE, private=True,
        turn=int(game.world._turn)))
    return content


# ----------------------------------------------------------------- learning
def _observe(game, actor, content):
    """The cells in sight are level 2 and stamped with this turn. A named place whose cell is in sight is level
    2. A named place within landmark_sight, but beyond sight, is at least level 1."""
    world = game.world
    turn = int(world._turn)
    here = world.actor_position(actor)
    if here is None:
        return
    sight, rules, bounds = _sight(world), _rules(world), _bounds(world)
    occupants = _occupants(world)
    for dy in range(-sight, sight + 1):
        for dx in range(-sight, sight + 1):
            cell = (here[0] + dx, here[1] + dy)
            if not _inside(cell, bounds):
                continue
            content["cells"][_key(cell)] = {"seen": turn, "terrain": _terrain(world, cell),
                                            "people": occupants.get(cell, 0)}
    for name, cells in _registry(game).items():
        nearest = min(_chebyshev(here, cell) for cell in cells)
        entry = content["places"].get(name)
        if nearest <= sight:
            known = set(map(tuple, entry.get("cells", []))) if entry and entry["level"] == LEVEL_FULL else set()
            known |= {cell for cell in cells if _chebyshev(here, cell) <= sight}
            content["places"][name] = {"level": LEVEL_FULL, "seen": turn,
                                       "cells": [list(cell) for cell in sorted(known)]}
        elif nearest <= int(rules["landmark_sight"]) and entry is None and name in _structures(game):
            # Beyond sight, only a structure or a public landmark is seen from afar. A deposit (a quarry, a
            # wood) is known by being in sight, or by being told.
            content["places"][name] = {"level": LEVEL_VAGUE, "seen": turn}


def _names_place(text, name, pack) -> bool:
    """Whether a text names a place: its name, or its bare word, as a whole word (short words are not used)."""
    candidates = {name.replace("_", " "), _bare(name, pack).lower()}
    for word in candidates:
        if len(word) >= _PLACE_MIN_WORD and re.search(rf"\b{re.escape(word)}\b", text):
            return True
    return False


def _tell(game, actor, content):
    """A place_belief memory (the resident was told of a place, or read of it) raises that place to level 1, or to
    level 2 when the memory carries the place's position. Each memory is read once."""
    world = game.world
    pack = world.data_pack
    turn = int(world._turn)
    told = set(content["told"])
    registry = _registry(game)
    for memory in game.characters[actor].memories:
        if memory.kind != TELL_KIND or memory.memory_id in told:
            continue
        told.add(memory.memory_id)
        content["told"].append(memory.memory_id)
        item = memory.content
        text = str(item.get("text", "")) if isinstance(item, dict) else str(item)
        position = _cell(item.get("position")) if isinstance(item, dict) else None
        lowered = text.lower()
        for name in registry:
            if not _names_place(lowered, name, pack):
                continue
            entry = content["places"].get(name)
            if position is not None:
                cells = [list(position)]
                if entry is None or entry["level"] < LEVEL_FULL:
                    content["places"][name] = {"level": LEVEL_FULL, "seen": turn, "cells": cells}
                _see_cell(world, content, position, turn, _bounds(world))
            elif entry is None:
                content["places"][name] = {"level": LEVEL_VAGUE, "seen": turn}


def refresh(game, actor):
    """One resident's learning at the current state: the ground in sight, the landmarks, and what it was told.
    Idempotent for an unchanged state, so the view may call it."""
    if not game.world.is_alive(actor) or game.world.actor_position(actor) is None:
        return None
    content = ensure_map(game, actor)
    _observe(game, actor, content)
    _tell(game, actor, content)
    return content


def learn_all(game):
    """End of turn: every fogged resident learns. A game with no fogged resident does nothing."""
    for actor, backend in game.backends.items():
        if getattr(backend, "fogged", False) and actor in game.characters:
            refresh(game, actor)


# ----------------------------------------------------------------- what is known
def _known(content, name) -> int:
    entry = content["places"].get(name)
    return int(entry["level"]) if entry else LEVEL_HIDDEN


def _cells_of(game, content, name):
    """The cells of a place as the resident holds it: its seen cells at level 2, the world's layout at level 1
    (only once the place is held at level 1 or 2)."""
    entry = content["places"].get(name)
    if entry is None:
        return []
    if entry["level"] == LEVEL_FULL and entry.get("cells"):
        return [tuple(cell) for cell in entry["cells"]]
    return list(_registry(game).get(name, []))


def known_cell(game, content, cell) -> bool:
    """Whether the resident knows this cell: it has seen it, or it is a cell of a place the resident holds."""
    if _key(cell) in content["cells"]:
        return True
    return any(cell in _cells_of(game, content, name) for name in content["places"])


def place_at(game, content, cell):
    """The name of a place the resident holds at this cell, or None."""
    for name in content["places"]:
        if _known(content, name) and cell in _cells_of(game, content, name):
            return name
    return None


def can_words(game, actor, cell, trade=None):
    """How a move to a cell is worded for the resident: ('to', place) for a place it knows exactly, ('toward', place)
    for one it knows only roughly, ('spot', None) for ground it has seen, or None for a cell it does not know. A
    shop row (a move with a trade) is worded by its trade when the resident holds that trade's place, since the
    shop is named for its trade wherever on the market it stands. The view offers only the first three."""
    content = ensure_map(game, actor)
    pack = game.world.data_pack
    if trade and known_cell(game, content, cell) and _known(content, str(trade).lower()):
        name = str(trade).lower()
        return ("to" if _known(content, name) == LEVEL_FULL else "toward"), _bare(name, pack)
    name = place_at(game, content, cell)
    if name is not None:
        level = _known(content, name)
        return ("to" if level == LEVEL_FULL else "toward"), _bare(name, pack)
    if known_cell(game, content, cell):
        return "spot", None
    return None


def _explore(world, here, step, steps):
    """The walkable cell a compass heading aims at: `steps` cells along the heading, or the nearest walkable cell
    along it. None if no cell along the heading is walkable."""
    bounds = _bounds(world)
    for k in range(steps, 0, -1):
        cell = (here[0] + step[0] * k, here[1] + step[1] * k)
        if bounds is not None:
            cell = (min(max(cell[0], 0), bounds[0] - 1), min(max(cell[1], 0), bounds[1] - 1))
        if cell != here and cell in world._map_cells:
            return cell
    return None


def _text_matches_place(text, name, pack) -> bool:
    """Whether a typed name (already lower case, without the article's word order issues) is this place."""
    return text in {name.replace("_", " "), _bare(name, pack).lower(), _word(name, pack).lower()}


def resolve_toward(game, actor, content, text):
    """The cell a `toward` names: a compass heading (north, south-east, ne), or a place the resident knows. A
    place it does not know is None, and so is a heading with no walkable cell. The world walks the true
    shortest path to the cell it returns."""
    world = game.world
    pack = world.data_pack
    here = world.actor_position(actor)
    if here is None:
        return None
    key = " ".join(str(text).lower().replace("-", " ").split())
    for entry in load_pack(pack)["FOG_WORDS"]["directions"]:
        if key in (entry["code"], entry["word"].replace("-", " ")):
            return _explore(world, here, _STEPS[entry["code"]], int(_rules(world)["explore_steps"]))
    for name in content["places"]:
        if _known(content, name) and _text_matches_place(key, name, pack):
            cells = _cells_of(game, content, name)
            if cells:
                return min(cells, key=lambda cell: (_chebyshev(here, cell), cell))
    return None


def route_plan(game, actor, plan):
    """A fogged resident's move, made into what the world can walk. A destination from a bound row must be ground
    the resident knows. `toward` is resolved to a destination (resolve_toward). Anything else is refused by the
    world as malformed (a move with no destination). A plan of a simple resident, or of another action, is
    returned as it is."""
    if plan.get("action") != "move" or not is_fogged(game, actor):
        return plan
    content = ensure_map(game, actor)
    out = dict(plan)
    if out.get("destination") is not None:
        cell = _cell(out["destination"])
        if cell is None or not known_cell(game, content, cell):
            return {"action": "move"}
        out["destination"] = cell
        return out
    if out.get("toward") is None:
        return {"action": "move"}
    cell = resolve_toward(game, actor, content, out["toward"])
    if cell is None:
        return {"action": "move"}
    out["destination"] = cell
    return out


# ----------------------------------------------------------------- the view
def _labels(game, content, here, pack, within=None):
    """The places the resident holds, nearest first, each with its word and roughly where (from `here`, the resident's
    own cell), and a letter as its glyph. A place held at level 2 is said to be remembered once it is stale. `within`
    is (centre, radius): only places with a cell inside that window are listed."""
    world = game.world
    rules = _rules(world)
    stale = int(rules["stale_ticks"])
    turn = int(world._turn)
    near_cells = int(rules["near_landmark_cells"])
    rows = []
    for name, entry in content["places"].items():
        level = int(entry["level"])
        cells = _cells_of(game, content, name)
        if level == LEVEL_HIDDEN or not cells:
            continue
        if within is not None and not any(_chebyshev(within[0], cell) <= within[1] for cell in cells):
            continue
        # Nearest first: from the window's centre when the section is a window, else from the resident.
        anchor = within[0] if within is not None else here
        distance = min(_chebyshev(anchor, cell) for cell in cells)
        rows.append((distance, name, level, cells, entry))
    rows.sort(key=lambda row: (row[0], row[1]))
    templates = load_pack(pack)["FOG_WORDS"]
    letters = str(rules["label_letters"])
    shown = rows[:int(rules["max_labels"])]
    labels = []
    for index, (_, name, level, cells, entry) in enumerate(shown):
        where = _where(here, cells, pack)
        word = _word(name, pack)
        if level == LEVEL_VAGUE:
            text = templates["label_rough"].format(word=word, where=where)
        else:
            text = templates["label"].format(word=word, where=where)
            age = turn - int(entry.get("seen", 0))
            if age > stale:
                text += "; " + templates["remembered"].format(age=age_phrase(age, pack))
        for _, other, _, other_cells, _ in shown:
            if other != name and min(_chebyshev(a, b) for a in cells for b in other_cells) <= near_cells:
                text += templates["label_near"].format(place=_word(other, pack))
                break
        labels.append({"glyph": letters[index] if index < len(letters) else "?", "word": text})
    return labels, [name for _, name, _, _, _ in shown]


def map_section(game, actor, centre=None, radius=None):
    """The agent view's `map` section for a fogged resident. Without a centre it is the resident's own map: the sight
    window around the resident, and every place it holds (nearest first, at most max_labels). With a centre and a
    radius it is a window on the map, listing only the places inside it. The level is full when a cell in the window
    is known (the window's rows are drawn), vague when only places are known (labels, no cell detail), and hidden
    when nothing in the window is known (no rows, no labels)."""
    world = game.world
    pack = world.data_pack
    here = world.actor_position(actor)
    if here is None:
        return None
    content = refresh(game, actor)
    if content is None:
        return None
    # A section with no centre is the resident's own map: the sight window around it, and every place it holds.
    # A section with a centre is a window on the map: only the places inside it are listed, so an empty window
    # is hidden. Labels are always worded from the resident's own cell.
    windowed = centre is not None or radius is not None
    centre = here if centre is None else tuple(centre)
    radius = _sight(world) if radius is None else int(radius)
    labels, named = _labels(game, content, here, pack, within=(centre, radius) if windowed else None)
    window = [(centre[0] + dx, centre[1] + dy) for dy in range(-radius, radius + 1)
              for dx in range(-radius, radius + 1)]
    seen = [cell for cell in window if _key(cell) in content["cells"]]
    if seen:
        level = LEVEL_FULL
    elif labels:
        level = LEVEL_VAGUE
    else:
        level = LEVEL_HIDDEN
    rows, legend = [], {}
    if level == LEVEL_FULL:
        glyphs = load_pack(pack)["MAP_GLYPHS"]
        bounds = _bounds(world)
        for dy in range(-radius, radius + 1):
            line = []
            for dx in range(-radius, radius + 1):
                cell = (centre[0] + dx, centre[1] + dy)
                if cell == here:
                    key = "player"
                elif _key(cell) in content["cells"] and _inside(cell, bounds):
                    terrain = str(content["cells"][_key(cell)]["terrain"])
                    key = terrain if terrain in glyphs and not terrain.startswith("_") else "unknown"
                else:
                    key = "unknown"
                legend[glyphs[key]["glyph"]] = glyphs[key]["word"]
                line.append(glyphs[key]["glyph"])
            rows.append("".join(line))
    paths = []
    for a, b in content["routes"]:
        if a in named and b in named and len(paths) < 2:
            paths.append(_path_words(a, b, pack))
    caption_key = {LEVEL_FULL: "map_full", LEVEL_VAGUE: "map_vague", LEVEL_HIDDEN: "map_hidden"}[level]
    return {"level": LEVEL_WORDS[level], "caption": load_pack(pack)["VIEW_WORDS"][caption_key],
            "rows": rows, "legend": dict(sorted(legend.items())), "labels": labels, "paths": paths}


def _path_words(a, b, pack) -> str:
    return load_pack(pack)["FOG_WORDS"]["path_between"].format(a=_word(a, pack), b=_word(b, pack))


def true_patch(game, actor):
    """The referee's overlay: the true terrain of the sight window around the resident, in the same glyphs. It is not
    part of any agent's view."""
    world = game.world
    here = world.actor_position(actor)
    if here is None:
        return None
    sight = _sight(world)
    glyphs = load_pack(world.data_pack)["MAP_GLYPHS"]
    bounds = _bounds(world)
    rows = []
    for dy in range(-sight, sight + 1):
        line = []
        for dx in range(-sight, sight + 1):
            cell = (here[0] + dx, here[1] + dy)
            if cell == here:
                key = "player"
            elif not _inside(cell, bounds):
                key = "unknown"
            else:
                terrain = _terrain(world, cell)
                key = terrain if terrain in glyphs and not terrain.startswith("_") else "unknown"
            line.append(glyphs[key]["glyph"])
        rows.append("".join(line))
    return rows
