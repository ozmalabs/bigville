"""lamplighter.py -- the lamplighter's round for the simple backend (Phase 042; order fixed in Phase 042b).

Lighting and dousing a street lamp is a backend choice. The world offers `light` and `douse`, each acting on the
nearest lamp within the lamplighter's pole reach (DAYNIGHT.lamp_pole_reach, APPROX: a long pole reached a street
lamp from the ground), and a `move` to the station (purpose `station`), which is the market store's cell, where the
lamp oil is drawn. Only a resident who holds the lamplighter job is offered these, so this returns None for everyone
else and the simple policy is unchanged.

The round's order, and why:
1. Near starvation (STARVE_GUARD, below CARE starve_limit 4.0): yield to the ordinary policy, whatever he holds.
2. A meal held and hunger at HUNGER_FIRST: yield, the ordinary policy eats it.
3. Lamp work due in pole reach (light at night, douse by day): do it. This comes before food for a hungry resident
   with no meal, so the round is bounded: it ends when no lamp in reach needs changing.
4. Energy below ROUND_REST_ENERGY: rest by day. At night yield to the ordinary policy, which sleeps at a safe spot.
   Phase 042's round walked on down to e_low, so each walk ended in an `exhausted` refusal and the lamplighter
   never reached a lamp.
5. Station: walk there when lamp work is due, when dusk is near, or when he is away from it. A walk starts only with
   WALK_ENERGY, since a walk from the edge of ROUND_REST_ENERGY ends under it. A hungry resident walks only when due.
6. At the station before dusk or by day: rest until DUSK_READY_ENERGY, so that dusk finds him able to light.
"""
from __future__ import annotations

from .protocol import ActorContinuation

# Hunger at which a held meal comes first. The simple policy's food-first threshold (cheap.HUNGER_BEFORE_SLEEP): one
# unmet meal. A valuation, not a rule.
HUNGER_FIRST = 1.0

# Hunger at or above which the round yields whatever he holds. Below CARE starve_limit (4.0). APPROX valuation.
STARVE_GUARD = 3.0

# Below this energy (0 to 100 scale, the observation `energy`) the round yields to rest and sleep. It equals the simple
# policy's rest_energy_threshold (cheap.SimplePolicy, 35.0). A valuation, not a rule.
ROUND_REST_ENERGY = 35.0

# Energy a walk to the station starts from (APPROX). A walk from the edge of ROUND_REST_ENERGY ends under it, so he
# rests first.
WALK_ENERGY = 60.0

# Energy the lamplighter rests to at the station, so that he can light the lamps at dusk. APPROX valuation.
DUSK_READY_ENERGY = 70.0


def lamplighter_choice(context):
    """(action, params, continuation) for the lamplighter's next move, or None when the ordinary policy decides."""
    offered = [o for o in context.affordances if o.get("lamplighter")]
    if not offered:
        return None
    hunger = float(context.observations.get("hunger", 0.0))
    energy = float(context.observations.get("energy", 100.0))
    night = bool(offered[0].get("night"))
    if hunger >= STARVE_GUARD:
        return None
    if hunger >= HUNGER_FIRST and any(o.get("action") == "eat" for o in context.affordances):
        return None
    for option in offered:
        if option.get("action") in {"light", "douse"}:
            return str(option["action"]), {}, None
    if energy < ROUND_REST_ENERGY:
        # Rest before any more walking. At night the ordinary policy sleeps (its safe-spot rule), so the round yields.
        if night or hunger >= HUNGER_FIRST:
            return None
        return "rest", {}, None
    for option in offered:
        if option.get("action") != "move" or option.get("purpose") != "station":
            continue
        if hunger >= HUNGER_FIRST and not option.get("due"):
            break   # hungry, and no lamp needs changing: the ordinary policy fetches food
        if energy < WALK_ENERGY and not night and hunger < HUNGER_FIRST:
            return "rest", {}, None   # a walk starts with energy to spare: a walk from 35 falls under it (see module)
        continuation = ActorContinuation(destination=option["destination"],
                                         interrupt_on=ActorContinuation.interrupt_on + ("body_down",))
        return "move", {"destination": option["destination"]}, continuation
    if hunger >= HUNGER_FIRST:
        return None
    if energy < DUSK_READY_ENERGY and any(o.get("purpose") in {"dusk_ready", "post"} for o in offered):
        return "rest", {}, None   # at the station before dusk: rest so that dusk finds him able to light
    return None
