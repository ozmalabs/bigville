"""A deterministic, inexpensive backend for standalone game NPCs."""
from __future__ import annotations

from ..character import CharacterDefinition, HeldState
from .protocol import ActorContext, ActorResponse, ProposedAction


class DeterministicBackend:
    """A small NPC policy over the world's already-derived affordances.

    The world still owns all of the detailed rules.  This backend only does the
    inexpensive game-AI part: prefer the highest-scoring actionable option,
    rest when the body actually needs it, and otherwise spend the turn
    observing.  It never schedules work behind the world's action boundary.
    """
    kind = "cheap"
    communication_mode = "templated"
    supports_free_text = False
    requires_conversational_interface = True

    def __init__(self, character: CharacterDefinition):
        self.character = character
        self.last_choice: dict = {}
        self.rest_energy_threshold = 35.0

    def decide(self, context: ActorContext) -> ActorResponse:
        options = [o for o in context.affordances
                   if o.get("action") not in {"rest", ""}]
        choice = max(options, key=self._choice_key, default=None)
        if choice is None:
            rest = next((o for o in context.affordances
                         if o.get("action") == "rest"), None)
            energy = float(context.observations.get("energy", 100.0))
            if rest is not None and energy < self.rest_energy_threshold:
                choice = rest
        if choice is None:
            # A blank response is a valid NPC observation turn.  In particular,
            # do not submit a rest plan that the world will correctly reject
            # for a healthy resident with no other legal work.
            self.last_choice = {}
            return ActorResponse()
        self.last_choice = dict(choice)
        params = {k: choice[k] for k in ("kind", "trade", "recipe", "target") if k in choice}
        return ActorResponse(ProposedAction(str(choice["action"]), params, "cheap_policy"))

    @staticmethod
    def _choice_key(option):
        """Keep choices deterministic while preferring meaningful actions."""
        priority = {
            "eat": 6, "tend_animals": 5, "harvest": 5, "sow": 4,
            "work": 3, "give": 2, "move": 1,
        }
        return (float(option.get("score", 0.0)),
                priority.get(str(option.get("action", "")), 0),
                str(option.get("target", "")),
                str(option.get("kind", "")))

    def dump_held_state(self) -> HeldState:
        return HeldState(
            character_id=self.character.character_id,
            backend=self.kind,
            identity=dict(self.character.identity),
            personality=dict(self.character.personality),
            memories=[m.to_dict() for m in self.character.memories],
            held_frames=[f.to_dict() for f in self.character.held_frames],
            decision=dict(self.last_choice),
            backend_state={"communication": {
                "mode": self.communication_mode,
                "supports_free_text": self.supports_free_text,
                "requires_conversational_interface": self.requires_conversational_interface,
            }},
        )


# Compatibility name used by the first standalone API release.
CheapBackend = DeterministicBackend
