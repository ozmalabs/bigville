"""lamplighter.py -- the lamplighter's round for the simple backend (Phase 042).

Lighting and dousing a street lamp is a backend choice. The world offers the actions (`light`, `douse`) on a lamp's
cell, and a `move` to a lamp that needs changing, only to a resident who holds the lamplighter job. This module
picks among them. Hunger at or above HUNGER_FIRST comes first, as food does for every resident.

Options carry `lamplighter: True`; a resident without that flag never sees a lamp option, so this returns None
for everyone else and the simple policy is unchanged.
"""
from __future__ import annotations

from .protocol import ActorContinuation

# The simple policy's food-first threshold (cheap.HUNGER_BEFORE_SLEEP): one unmet meal. A valuation, not a rule.
HUNGER_FIRST = 1.0


def lamplighter_choice(context):
    """(action, params, continuation) for the lamplighter's next move, or None when there is no lamp work to do now."""
    offered = [o for o in context.affordances if o.get("lamplighter")]
    if not offered:
        return None
    if float(context.observations.get("hunger", 0.0)) >= HUNGER_FIRST:
        return None
    for option in offered:
        if option.get("action") in {"light", "douse"}:
            return str(option["action"]), {}, None
    for option in offered:
        if option.get("action") == "move" and option.get("destination") is not None:
            continuation = ActorContinuation(destination=option["destination"],
                                             interrupt_on=ActorContinuation.interrupt_on + ("body_down",))
            return "move", {"destination": option["destination"]}, continuation
    return None
