"""Phase 045: the simple backend's dependant policy (a caregiver's feeding and walking).

The world publishes the dependant acts a resident may take (affordances marked `dependant`): a feed for a
caregiver on a hungry dependant's cell, holding food, and a walk to a dependant that no one attends. This
policy chooses between them. It runs before the ordinary choice, and only while the caregiver is not too
hungry to tend anyone itself (DEPENDANTS.caregiver_max_hunger). With the switch off the world publishes no
dependant affordance, so this returns None and the simple backend's choice is unchanged.
"""
from __future__ import annotations

from domains.world_affordances import DEPENDANTS as _DEPENDANTS


def dependant_choice(context) -> tuple[str, dict, str] | None:
    """(action, params, reason) for the caregiver's next dependant act, or None when there is none to take."""
    options = [o for o in (getattr(context, "affordances", None) or []) if o.get("dependant")]
    if not options:
        return None
    hunger = float(context.observations.get("hunger", 0.0))
    if hunger > float(_DEPENDANTS["caregiver_max_hunger"]):
        return None
    feeds = sorted((o for o in options if o.get("action") == "care" and o.get("care_kind") == "feed"),
                   key=lambda o: str(o.get("patient")))
    if feeds:
        return "care", {"patient": feeds[0]["patient"], "care_kind": "feed"}, "feed_dependant"
    walks = sorted((o for o in options if o.get("action") == "move" and o.get("destination") is not None),
                   key=lambda o: str(o.get("dependant")))
    if walks:
        return "move", {"destination": walks[0]["destination"]}, "tend_dependant"
    return None
