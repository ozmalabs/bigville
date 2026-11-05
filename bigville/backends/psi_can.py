"""Small deterministic PSI/CAN-style decision model for game NPCs."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from domains.world_affordances import HOUSEHOLD_WORK as _HOUSEHOLD_WORK


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def open_work_governed(option: dict[str, Any]) -> bool:
    """True for an open recipe whose offer depends on the household-work need (Phase 006): its option carries
    a fuel or night-soil read-off. Other open recipes (baking bread at home, spinning) keep their prior
    behaviour, with no read-off and no need."""
    return (option.get("action") == "work" and bool(option.get("open_recipe"))
            and ("fuel_held" in option or "night_soil_held" in option))


def open_work_need(option: dict[str, Any], table: dict[str, Any] | None = None) -> float:
    """Points an open (household) work option earns from its physical read-offs (Phase 006).

    The world publishes quantities on the option (worlds/bigville_world.py `_open_work_read_offs`); this rule
    turns them into points with the pack's HOUSEHOLD_WORK thresholds and weights:
      fuel_cold: fuel_cold weight x household_fuel_short (the household's felt unmet heating share, 0 to 1).
      fuel_low: fuel_low weight, once, when fuel_held plus fuel_store (when perceived) is below fuel_low_units.
      night_soil_high: night_soil_high weight, once, when night_soil_held plus night_soil_store (when perceived)
        reaches night_soil_high_units.
    An option that is not an open recipe earns nothing. The caller offers an open recipe only above zero."""
    if option.get("action") != "work" or not option.get("open_recipe"):
        return 0.0
    table = _HOUSEHOLD_WORK if table is None else table
    weights = table["weights"]
    need = 0.0
    if "fuel_held" in option:
        fuel = float(option.get("fuel_held", 0.0)) + float(option.get("fuel_store", 0.0))
        need += float(weights["fuel_cold"]) * _clamp(float(option.get("household_fuel_short", 0.0)))
        if fuel < float(table["fuel_low_units"]):
            need += float(weights["fuel_low"])
    if "night_soil_held" in option:
        soil = float(option.get("night_soil_held", 0.0)) + float(option.get("night_soil_store", 0.0))
        if soil >= float(table["night_soil_high_units"]):
            need += float(weights["night_soil_high"])
    return round(need, 4)


@dataclass(frozen=True)
class PsiState:
    """Compressed motivational state used as CAN input."""

    hunger: float = 0.0
    fatigue: float = 0.0
    illness: float = 0.0
    insecurity: float = 0.0
    social: float = 0.0
    arousal: float = 0.4

    @classmethod
    def from_context(cls, context) -> "PsiState":
        observations = getattr(context, "observations", {}) or {}
        hunger = _clamp(float(observations.get("hunger", 0.0)) / 4.0)
        energy = observations.get("energy")
        # Bigville publishes energy on a 0-100 scale.
        energy = float(energy) if energy is not None else None
        fatigue = _clamp(1.0 - energy / 100.0) if energy is not None else 0.0
        health = observations.get("health", "healthy")
        illness = _clamp(float(observations.get("illness", 0.0)))
        if health not in {"healthy", "well", 1, 1.0, True}:
            illness = max(illness, 0.6)
        personality = getattr(getattr(context, "character", None), "personality", {}) or {}
        arousal = _clamp(float(observations.get("arousal", personality.get("arousal", 0.4))))
        return cls(
            hunger=hunger, fatigue=fatigue, illness=illness,
            insecurity=_clamp(float(observations.get("insecurity", 0.0))),
            social=_clamp(float(observations.get("social_pressure", 0.0))),
            arousal=arousal,
        )

    def as_dict(self) -> dict[str, float]:
        return {key: round(float(value), 4) for key, value in self.__dict__.items()}


class CANWeightModel:
    """A compact causal-attitude network over already-admissible actions."""

    ACTION_CONCEPTS = {
        "eat": ("survival",), "give": ("social", "survival"),
        "move": ("goal", "security"), "rest": ("comfort", "survival"),
        "work": ("competence", "duty"), "start": ("competence", "duty"),
        "fetch": ("duty", "survival"), "put": ("duty", "security"),
        "water": ("duty", "survival"), "harvest": ("duty", "survival"),
        "sow": ("duty", "future"), "fertilise": ("duty", "future"), "tend_animals": ("duty", "care"),
        "build": ("competence", "security"), "maintain": ("security", "duty"),
        "care": ("care", "social"), "sell_labor": ("survival", "social"),
        "graze": ("survival", "comfort"), "herd": ("duty", "care"),
        "stay": ("comfort", "security"), "drink": ("survival",),
        "sleep": ("comfort", "survival"),
    }
    EDGES = {
        "hunger": {"survival": 1.6, "duty": 0.25},
        "fatigue": {"comfort": 1.5, "survival": 0.4, "duty": -0.35},
        "illness": {"care": 1.5, "survival": 0.7, "duty": -0.2},
        "insecurity": {"security": 1.4, "survival": 0.5},
        "social": {"social": 1.2},
        "arousal": {"goal": 0.25, "social": 0.2},
    }

    def activations(self, psi: PsiState, personality=None, identity=None):
        personality = personality or {}
        identity = identity or {}
        concepts = {concept for edges in self.EDGES.values() for concept in edges}
        activations = {name: 0.0 for name in concepts}
        for pressure, edges in self.EDGES.items():
            for concept, weight in edges.items():
                activations[concept] += float(getattr(psi, pressure)) * weight
        activations["comfort"] = activations.get("comfort", 0.0) + max(0.0, float(personality.get("mood_bias", 0.0)))
        activations["duty"] = activations.get("duty", 0.0) + float(personality.get("role_identity", identity.get("role_identity", 0.0)))
        activations["social"] = activations.get("social", 0.0) + (float(personality.get("charm_weight", 0.5)) - 0.5) * 0.6
        activations["security"] = activations.get("security", 0.0) + float(personality.get("prior_world_safe", 0.6)) - 0.5
        activations["care"] = activations.get("care", 0.0) + max(0.0, 0.5 - float(personality.get("w_spite", 0.15))) * 0.25
        return {key: round(float(value), 4) for key, value in activations.items()}

    def score(self, option: dict[str, Any], context):
        psi = PsiState.from_context(context)
        character = getattr(context, "character", None)
        personality = getattr(character, "personality", {}) or {}
        identity = getattr(character, "identity", {}) or {}
        activations = self.activations(psi, personality, identity)
        action = str(option.get("action", ""))
        concepts = tuple(option.get("concepts") or self.ACTION_CONCEPTS.get(action, ()))
        if option.get("drive"):
            concepts += (str(option["drive"]),)
        can = {concept: round(float(activations.get(concept, 0.0)), 4) for concept in concepts}
        weighted = float(option.get("score", 0.0)) + 6.0 * sum(can.values())
        weighted += max(psi.hunger, psi.illness) * (12.0 if "survival" in concepts else 0.0)
        weighted += open_work_need(option)
        result = dict(option)
        result.update(weighted_score=round(weighted, 4), psi=psi.as_dict(), can=can,
                      can_concepts=list(concepts))
        return result

    @staticmethod
    def tie_break(character_id, turn, option):
        payload = f"{character_id}:{int(turn)}:{option.get('action', '')}:{option.get('target', '')}"
        return int.from_bytes(hashlib.blake2b(payload.encode(), digest_size=4).digest(), "big")

    def choose(self, context, options):
        # A fuel or night-soil open recipe is a candidate only when its read-offs give it a need. Without one,
        # the resident has no reason to start that household work. Other options are unchanged.
        options = [option for option in options
                   if not open_work_governed(option) or open_work_need(option) > 0.0]
        if not options:
            return None
        scored = [self.score(option, context) for option in options]
        character = getattr(context, "character", None)
        character_id = str(getattr(character, "character_id", getattr(character, "name", "npc")))
        chosen = max(scored, key=lambda option: (
            float(option.get("weighted_score", 0.0)),
            self.tie_break(character_id, getattr(context, "turn", 0), option)))
        chosen["decision_model"] = "psi_can_weighted"
        return chosen
