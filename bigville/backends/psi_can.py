"""Small deterministic PSI/CAN-style decision model for game NPCs."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


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
        fatigue = _clamp(1.0 - float(energy)) if energy is not None else 0.0
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
        "sow": ("duty", "future"), "tend_animals": ("duty", "care"),
        "build": ("competence", "security"), "maintain": ("security", "duty"),
        "care": ("care", "social"), "sell_labor": ("survival", "social"),
        "graze": ("survival", "comfort"), "herd": ("duty", "care"),
        "stay": ("comfort", "security"), "drink": ("survival",),
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
        result = dict(option)
        result.update(weighted_score=round(weighted, 4), psi=psi.as_dict(), can=can,
                      can_concepts=list(concepts))
        return result

    @staticmethod
    def tie_break(character_id, turn, option):
        payload = f"{character_id}:{int(turn)}:{option.get('action', '')}:{option.get('target', '')}"
        return int.from_bytes(hashlib.blake2b(payload.encode(), digest_size=4).digest(), "big")

    def choose(self, context, options):
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
