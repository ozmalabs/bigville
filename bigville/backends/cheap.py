"""A deterministic, inexpensive backend for standalone game NPCs."""
from __future__ import annotations

from ..character import CharacterDefinition, HeldState
from .protocol import ActorContext, ActorResponse, ProposedAction


class DeterministicBackend:
    kind = "cheap"
    communication_mode = "templated"
    supports_free_text = False
    requires_conversational_interface = True

    def __init__(self, character: CharacterDefinition):
        self.character = character
        self.last_choice: dict = {}

    def decide(self, context: ActorContext) -> ActorResponse:
        options = [o for o in context.affordances if o.get("action") not in {"rest", ""}]
        choice = max(options, key=lambda o: float(o.get("score", 0.0)), default=None)
        if choice is None:
            choice = next((o for o in context.affordances if o.get("action") == "rest"), None)
        if choice is None:
            return ActorResponse()
        self.last_choice = dict(choice)
        params = {k: choice[k] for k in ("kind", "trade", "recipe", "target") if k in choice}
        return ActorResponse(ProposedAction(str(choice["action"]), params, "cheap_policy"))

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
