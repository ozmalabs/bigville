"""duty.py -- a job's standing duty as a drive for the simple backend (Phase 042c).

A resident who holds a job with a duty (DUTIES, world/duty.json) has a task the world can see is due. The world
publishes the physical facts on the job's offers as `duty`: how many lamps need the change and the hours until the
change is due (negative once it is due), for each of light and douse. This module reads those facts and turns them
into one urgency on the same 0-to-1 scale as the needs:

* due level (0 to 1) from the facts and the duty's valuations: 0 when nothing is pending; before the due time, a
  level that rises from 0 over lead_hours to due_floor; at the due time due_floor; then rising to 1 over ramp_hours.
* duty urgency = role_identity (the resident's drawn personality trait, 0 to 1, psi_can) x due level. A lax
  resident (low role_identity) has a low urgency whatever is due.
* need urgencies: hunger / starve_limit (CARE, 1.0 at starvation), and tiredness from energy, (100 - energy) over
  the span from full to collapse (EXHAUSTION e_collapse, 1.0 at collapse).

When the duty urgency is above the larger need urgency, the duty holds: it is the whole choice, and food, rest and
sleep wait (a dutiful resident forgoes a meal or a sleep). Otherwise the duty's options compete in the ordinary
weighting, each with a bonus of urgency x (score_weight, plus in_place_bonus for an act needing no walk). Starvation
and collapse end a duty because their urgencies reach 1.0, which no duty exceeds.

Nothing here is lamplighter-specific: any job in DUTIES with offers carrying `duty` is driven this way. With no such
offer (day and night off, or no duty due) `duty_drive` returns None and the backend's choice is unchanged.
"""
from __future__ import annotations

from typing import Any

from domains.world_affordances import CARE as _CARE, DUTIES as _DUTIES, EXHAUSTION as _EXHAUSTION
from .protocol import ActorContinuation

# The duty's own act names: a light or a douse needs no destination; a walk carries one.
_ACTS = ("light", "douse")


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def due_level(pending: float, hours_to_due: float, spec: dict[str, Any]) -> float:
    """The due level (0 to 1) of one task: `pending` things need the change, `hours_to_due` is negative once due."""
    if float(pending) <= 0.0:
        return 0.0
    lead = float(spec["lead_hours"])
    floor = float(spec["due_floor"])
    hours = float(hours_to_due)
    if hours > lead:
        return 0.0
    if hours > 0.0:
        return floor * (lead - hours) / lead
    return min(1.0, floor + (1.0 - floor) * (-hours) / float(spec["ramp_hours"]))


def need_urgencies(observations: dict[str, Any]) -> tuple[float, float]:
    """(hunger urgency, tiredness urgency), each 0 to 1 and 1 at starvation or collapse."""
    hunger = float(observations.get("hunger", 0.0))
    energy = float(observations.get("energy", 100.0))
    starve = float(_CARE["starve_limit"])
    collapse = 100.0 * float(_EXHAUSTION["e_collapse"])
    hunger_u = _clamp(hunger / starve) if starve > 0.0 else 0.0
    tired_u = _clamp((100.0 - energy) / (100.0 - collapse)) if collapse < 100.0 else 0.0
    return hunger_u, tired_u


def _role_identity(character) -> float:
    # The same read as psi_can.CANWeightModel.activations: the personality trait, else the identity's copy.
    personality = getattr(character, "personality", {}) or {}
    identity = getattr(character, "identity", {}) or {}
    return _clamp(float(personality.get("role_identity", identity.get("role_identity", 0.0))))


class DutyDrive:
    """The duty of one resident this turn: its job, due level, urgency, the needs it weighs against, and its offers."""

    def __init__(self, job, spec, level, role, need, offers):
        self.job = job
        self.spec = spec
        self.level = float(level)
        self.role = float(role)
        self.urgency = self.role * self.level
        self.need = float(need)
        self.offers = offers
        self.holds = self.level > 0.0 and self.urgency > self.need

    def bonus(self, option: dict[str, Any]) -> float:
        """The score this duty adds to one of its offers (0 for any other option)."""
        if not isinstance(option.get("duty"), dict) or self.urgency <= 0.0:
            return 0.0
        in_place = "destination" not in option
        bonus = float(self.spec["score_weight"]) + (float(self.spec["in_place_bonus"]) if in_place else 0.0)
        return self.urgency * bonus

    def scored(self) -> list[dict[str, Any]]:
        """The duty's offers with their duty bonus in the score: the choice when the duty holds."""
        return [{**dict(option), "score": float(option.get("score", 0.0)) + self.bonus(option)}
                for option in self.offers]

    def trace(self) -> dict[str, Any]:
        return {"job": self.job, "level": round(self.level, 4), "role_identity": round(self.role, 4),
                "urgency": round(self.urgency, 4), "need": round(self.need, 4), "holds": self.holds}


def duty_drive(context, character) -> DutyDrive | None:
    """The duty this resident has now, or None when no offer carries a duty for a job in DUTIES. Every offer of a
    job carries the same facts (the world's lamp state and clock), so the first offer's facts are read."""
    offers = [o for o in (getattr(context, "affordances", None) or []) if isinstance(o.get("duty"), dict)]
    offers = [o for o in offers if str(o["duty"].get("job", "")) in _DUTIES]
    if not offers:
        return None
    facts = offers[0]["duty"]
    job = str(facts["job"])
    spec = _DUTIES[job]
    level = max(due_level(facts.get(f"{act}_pending", 0.0), facts.get(f"{act}_hours", 0.0), spec)
                for act in _ACTS)
    if level <= 0.0:
        return None
    observations = getattr(context, "observations", {}) or {}
    hunger_u, tired_u = need_urgencies(observations)
    return DutyDrive(job, spec, level, _role_identity(character), max(hunger_u, tired_u), offers)


def duty_action(choice: dict[str, Any]):
    """(action, params, continuation) for a duty choice. A walk carries its destination and a continuation."""
    action = str(choice["action"])
    if action == "move" and choice.get("destination") is not None:
        destination = choice["destination"]
        continuation = ActorContinuation(destination=destination,
                                         interrupt_on=ActorContinuation.interrupt_on + ("body_down",))
        return action, {"destination": destination}, continuation
    return action, {}, None
