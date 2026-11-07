"""daynight.py -- the sky, the lamps and seeing in the dark (Phase 042), as world facts.

The world publishes the physical facts here: where the street lamps stand and whether they burn, how much
oil is in each reservoir and in the town's store, which residents stand indoors, in lamplight or in the dark,
and what the light does to sight, to work on the fitness path, and to travel. The world decides none of
the choices: `light` and `douse` are offered to any resident who stands on a lamp, and the lamplighter's
round is a backend choice (bigville/backends/lamplighter.py). The sky itself is the pure function in
domains/daynight.py.

Every consequence is behind DAYNIGHT.enabled, which defaults to false. Off, each function here returns what
the world did before day and night existed: sight is the HEARING range, work and travel run at full speed,
lateness is the hour's, and the tick writes nothing. `switch_on(world)` turns the consequences on for one
world. It places the lamps, seeds the lamp oil in the store, and appoints the lamplighter.
"""
from __future__ import annotations

from domains import daynight as D

ACTIONS = ("light", "douse")


def on(w):
    """True once `switch_on` has run for this world (or the pack switch was on at construction)."""
    return bool(getattr(w, "_dn_on", False))


def install(w):
    """Called at world construction, after the square's fixtures. The pack switch decides whether to switch on."""
    w._dn_on = False
    w._dn_lamps = {}
    if bool(w.E.DAYNIGHT["enabled"]):
        switch_on(w)


def switch_on(w):
    """Turn day and night on for this world (idempotent): lamps, oil, lamplighter."""
    if on(w):
        return
    dn = w.E.DAYNIGHT
    w._dn_on = True
    w._dn_lamps = {}
    square = (w._map_layout or {}).get("square", {}) if w._map_layout else {}
    center = tuple(square.get("center", ()))
    if len(center) == 2:
        for spec in w.E.DAYNIGHT_LAMPS:
            ox, oy = spec["offset"]
            cell = (int(center[0]) + int(ox), int(center[1]) + int(oy))
            node = w.eng.add_node("StreetLamp", {
                "name": spec["name"], "x": float(cell[0]), "y": float(cell[1]), "lit": 0.0, "fuel": 0.0,
                "fuel_capacity": float(dn["lamp_fuel_capacity"]),
                "burn_per_tick": float(dn["lamp_burn_per_tick"]),
            })
            w.eng.add_edge_unchecked(w._square, "has_lamp", node)
            if cell in w._map_cells:
                w.eng.add_edge_unchecked(node, "at_cell", w._map_cells[cell])
            w._dn_lamps[cell] = node
    oil = dn["oil_item"]
    w.set_stock(oil, w.qty(oil) + float(dn["starting_oil"]))
    appoint_lamplighters(w)


def _jobs(w, actor):
    attrs = w.eng.node(w._actors[actor])["attrs"]
    return {job for job in str(attrs.get("jobs", "")).split(",") if job}


def appoint_lamplighters(w):
    """Give the job to the first living adults in the founding order, up to DAYNIGHT.lamplighters holders."""
    job = w.E.DAYNIGHT["lamplighter_job"]
    need = int(w.E.DAYNIGHT["lamplighters"]) - sum(
        1 for a in w._actors if w.is_alive(a) and job in _jobs(w, a))
    for actor in w._actors:
        if need <= 0:
            break
        attrs = w.eng.node(w._actors[actor])["attrs"]
        if not w.is_alive(actor) or attrs.get("role") == "child" or job in _jobs(w, actor):
            continue
        held = sorted(_jobs(w, actor) | {job})
        w.eng.set_attr(w._actors[actor], "jobs", ",".join(held))
        need -= 1


def lamplighters(w):
    """The living residents who hold the lamplighter job."""
    job = w.E.DAYNIGHT["lamplighter_job"]
    return [a for a in w._actors if w.is_alive(a) and job in _jobs(w, a)]


# ------------------------------------------------------------------ the sky (read-offs; pure)

def sky(w):
    """The sky now: sunrise, sunset, is_night, moon_illum, cloud and light_level. Always available (a physical fact)."""
    a = w.eng.node(w._town)["attrs"]
    return D.sky(float(a.get("clock", 0.0)), str(a.get("weather", "clear")), w.E.WEATHER, w.E.TIME, w.E.DAYNIGHT)


def light_level(w):
    """The light now at the town (0 pitch dark to 1 full sun): moonlight at night, sunlight by day, through the cloud."""
    return round(float(sky(w)["light_level"]), 4)


def is_night(w):
    return bool(sky(w)["is_night"])


def moon_illum(w):
    return round(float(sky(w)["moon_illum"]), 4)


def tick(w):
    """Each clock tick, once day and night are on: write the sky to the town and burn the lamps and held candles."""
    if not on(w):
        return
    s = sky(w)
    town = w._town
    w.eng.set_attr(town, "sky_light", float(s["light_level"]))
    w.eng.set_attr(town, "sky_night", 1.0 if s["is_night"] else 0.0)
    w.eng.set_attr(town, "sky_moon", float(s["moon_illum"]))
    w.eng.set_attr(town, "sky_cloud", float(s["cloud"]))
    w.eng.set_attr(town, "sky_sunrise", float(s["sunrise"]))
    w.eng.set_attr(town, "sky_sunset", float(s["sunset"]))
    _burn_lamps(w)
    _burn_candles(w)


def _burn_lamps(w):
    for node in w._dn_lamps.values():
        attrs = w.eng.node(node)["attrs"]
        if float(attrs.get("lit", 0.0)) != 1.0:
            continue
        fuel = max(0.0, float(attrs.get("fuel", 0.0)) - float(attrs.get("burn_per_tick", 0.0)))
        w.eng.set_attr(node, "fuel", fuel)
        if fuel <= 0.0:
            w.eng.set_attr(node, "lit", 0.0)           # the oil is gone: the lamp goes out


def _burn_candles(w):
    kinds = w.E.DAYNIGHT["carried_lights"]
    burn = float(w.E.DAYNIGHT["candle_burn_per_tick"])
    for actor in w._actors:
        for kind in kinds:
            item = w._held_tool(actor, kind)
            if item is None:
                continue
            attrs = w.eng.node(item)["attrs"]
            if float(attrs.get("lit", 0.0)) != 1.0:
                continue
            fuel = max(0.0, float(attrs.get("fuel", 0.0)) - burn)
            w.eng.set_attr(item, "fuel", fuel)
            if fuel <= 0.0:
                w.eng.set_attr(item, "lit", 0.0)       # the candle has burned down


# ------------------------------------------------------------------ what a resident can see

def indoors(w, cell):
    """True when the cell lies inside a building's footprint."""
    if cell is None:
        return False
    for site in w._building_sites.values():
        x, y, width, height = site[:4]
        if x <= cell[0] < x + width and y <= cell[1] < y + height:
            return True
    return False


def lit_lamp_near(w, cell):
    """A lit street lamp within DAYNIGHT.lamp_reach cells (Chebyshev) of the cell, with oil in it."""
    if cell is None:
        return False
    reach = int(w.E.DAYNIGHT["lamp_reach"])
    for lamp_cell, node in w._dn_lamps.items():
        attrs = w.eng.node(node)["attrs"]
        if float(attrs.get("lit", 0.0)) != 1.0 or float(attrs.get("fuel", 0.0)) <= 0.0:
            continue
        if max(abs(lamp_cell[0] - cell[0]), abs(lamp_cell[1] - cell[1])) <= reach:
            return True
    return False


def carried_light(w, actor):
    """A lit candle the resident holds (DAYNIGHT.carried_lights), or None."""
    for kind in w.E.DAYNIGHT["carried_lights"]:
        item = w._held_tool(actor, kind)
        if item is not None and float(w.eng.node(item)["attrs"].get("lit", 0.0)) == 1.0:
            return item
    return None


def sees_dark(w, actor):
    """Phase 042's `sees_dark`: outdoors, unsheltered, with no lit lamp or candle beside them, and light below see_threshold.

    Indoors never. False when day and night are off, or the actor is not in the world."""
    if not on(w) or actor not in w._actors:
        return False
    cell = w.actor_position(actor)
    if cell is None or indoors(w, cell) or lit_lamp_near(w, cell) or carried_light(w, actor) is not None:
        return False
    return D.sees_dark_level(light_level(w), w.E.DAYNIGHT["see_threshold"])


def view_light(w, actor):
    """The light a resident sees, as a lexicon key: 'day', 'dim', 'dark' or 'lamplight' (no number). None when off."""
    if not on(w) or actor not in w._actors:
        return None
    cell = w.actor_position(actor)
    if cell is None:
        return None
    if lit_lamp_near(w, cell) or carried_light(w, actor) is not None:
        return "lamplight"
    if indoors(w, cell):
        return "lamplight" if is_night(w) else "day"
    if sees_dark(w, actor):
        return "dark"
    return "dim" if is_night(w) else "day"


def sight_range(w, observer, default):
    """The witnessing radius of an observer (Phase 028 HEARING.sight_range): shorter when the observer sees dark."""
    if on(w) and sees_dark(w, observer):
        return min(int(default), int(w.E.DAYNIGHT["dark_sight_range"]))
    return default


def work_visibility(w, actor):
    """The factor a resident's tools and skill keep on the job fitness path (Phase 048): 1.0 with light, dark_work_fit in the dark."""
    if not on(w):
        return 1.0
    return D.visibility_factor(sees_dark(w, actor), w.E.DAYNIGHT["dark_work_fit"])


def travel_factor(w, actor):
    """The multiplier on a step's interval in the dark (DAYNIGHT.travel_dark_factor, a table factor; 1.0 is the seed)."""
    if not on(w) or not sees_dark(w, actor):
        return 1.0
    return float(w.E.DAYNIGHT["travel_dark_factor"])


def lateness(w, seed_hours):
    """Phase 024's `lateness`: hours past the real sunset while it is night, else 0. Off, the seed's hour-based value."""
    if not on(w):
        return seed_hours
    s = sky(w)
    if not s["is_night"]:
        return 0.0
    hour, sunset = float(s["hour"]), float(s["sunset"])
    if hour >= sunset:
        return hour - sunset
    return hour + 24.0 - sunset


# ------------------------------------------------------------------ the actions

def act(w, actor, action, kwargs, args):
    """`light` and `douse` (major actions). Returns True when enacted, else the world's refusal (False)."""
    if not on(w):
        return w._refuse("unsupported")
    named = kwargs.get("item", args[0] if args else None)
    if named is not None:
        kind = w._as_key(named)
        if kind is None:
            return w._refuse("malformed")
        if kind not in w.E.DAYNIGHT["carried_lights"]:
            return w._refuse("unsupported")
        return _carried(w, actor, kind, action)
    cell = w.actor_position(actor)
    node = w._dn_lamps.get(cell)
    if node is None:
        return w._refuse("not_at_site")
    if action == "light":
        return _light_lamp(w, actor, node)
    return _douse(w, node)


def _light_lamp(w, actor, node):
    attrs = w.eng.node(node)["attrs"]
    if float(attrs.get("lit", 0.0)) == 1.0:
        return w._refuse("not_possible")
    if not w._store_open(actor):
        return w._refuse("store_locked")
    oil = w.E.DAYNIGHT["oil_item"]
    fuel = float(attrs.get("fuel", 0.0))
    take = min(max(0.0, float(attrs.get("fuel_capacity", 0.0)) - fuel), float(w.qty(oil)))
    if take > 0.0:
        w.set_stock(oil, float(w.qty(oil)) - take)
        fuel += take
        w.eng.set_attr(node, "fuel", fuel)
    if fuel <= 0.0:
        return w._refuse("out_of_stock")
    w.eng.set_attr(node, "lit", 1.0)
    w._run()
    return True


def _douse(w, node):
    if float(w.eng.node(node)["attrs"].get("lit", 0.0)) != 1.0:
        return w._refuse("not_possible")
    w.eng.set_attr(node, "lit", 0.0)
    w._run()
    return True


def _carried(w, actor, kind, action):
    item = w._held_tool(actor, kind)
    if item is None:
        return w._refuse("not_held")
    attrs = w.eng.node(item)["attrs"]
    lit = float(attrs.get("lit", 0.0)) == 1.0
    if action == "douse":
        if not lit:
            return w._refuse("not_possible")
        w.eng.set_attr(item, "lit", 0.0)
        w._run()
        return True
    if lit:
        return w._refuse("not_possible")
    fuel = float(attrs.get("fuel", w.E.DAYNIGHT["candle_fuel"]))
    if fuel <= 0.0:
        return w._refuse("not_possible")
    w.eng.set_attr(item, "fuel", fuel)
    w.eng.set_attr(item, "lit", 1.0)
    w._run()
    return True


# ------------------------------------------------------------------ what the lamplighter is offered

def _restrained(w, actor):
    """True when the resident is held or is holding someone (Phase 033). Worlds without restraint have neither."""
    holder = getattr(w, "holder_of", None)
    holding = getattr(w, "holding_of", None)
    return (holder is not None and holder(actor) is not None) or (holding is not None and holding(actor) is not None)


def lamp_options(w, actor):
    """Options a lamplighter is offered for the lamps: light or douse where they stand, and a move to a lamp that needs it.

    Non-lamplighters are offered nothing here, so the simple policy's choices are unchanged for them. The option
    names what is physically true (the lamp's cell, lit or not, and whether it is night); it chooses nothing."""
    if not on(w) or actor not in w._actors or w.E.DAYNIGHT["lamplighter_job"] not in _jobs(w, actor):
        return []
    if _restrained(w, actor):   # a restrained resident walks nowhere
        return []
    night = is_night(w)
    here = w.actor_position(actor)
    # A backend's walk below e_low is refused (Phase 049), so the round offers no walk to a resident that exhausted.
    walk_ok = not w._exhaustion_band(actor)["below_e_low"]
    out = []
    for cell, node in w._dn_lamps.items():
        lit = float(w.eng.node(node)["attrs"].get("lit", 0.0)) == 1.0
        needs = (night and not lit) or (not night and lit)
        if cell == here:
            if needs:
                out.append({"action": "light" if not lit else "douse",
                            "lamp": w.eng.node(node)["attrs"]["name"],
                            "lamplighter": True, "night": night, "lit": lit})
        elif needs and walk_ok:
            out.append({"action": "move", "destination": cell, "lamplighter": True, "night": night,
                        "purpose": "light" if not lit else "douse"})
    return out
