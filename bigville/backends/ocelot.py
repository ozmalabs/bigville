"""Optional graph-cognition adapter.

The name is retained as a compatibility label for callers that select an
Ocelot-style backend.  This package does not import or bundle Ocelot; an
external provider can replace this adapter through the backend factory API.
"""
from __future__ import annotations

from ..character import CharacterDefinition, HeldState
from .protocol import ActorContext, ActorResponse, ProposedAction


class OcelotBackend:
    kind = "ocelot"
    communication_mode = "free_text"
    supports_free_text = True
    requires_conversational_interface = False

    def __init__(self, world, character: CharacterDefinition):
        self.world = world
        self.character = character

    def decide(self, context: ActorContext) -> ActorResponse:
        plan = self.world.resident_plan(self.character.name)
        if plan.get("action") in {"", "none"}:
            return ActorResponse()
        params = {k: plan[k] for k in ("kind", "trade", "recipe", "target") if k in plan}
        return ActorResponse(ProposedAction(str(plan["action"]), params, "ocelot_decision"))

    def dump_held_state(self) -> HeldState:
        mind = self.world.actor_mind(self.character.name)
        if hasattr(mind, "dump_held_state"):
            payload = mind.dump_held_state()
            state = HeldState(
                character_id=self.character.character_id,
                backend=self.kind,
                identity=dict(self.character.identity),
                personality=dict(self.character.personality),
                memories=[m.to_dict() for m in self.character.memories],
                held_frames=[f.to_dict() for f in self.character.held_frames],
                concepts=list(payload.get("concepts", [])),
                goals=list(payload.get("goals", [])),
                beliefs=list(payload.get("beliefs", [])),
                decision=dict(payload.get("decision", {})),
                backend_state=dict(payload.get("backend_state", {})),
            )
            state.backend_state["communication"] = {
                "mode": self.communication_mode,
                "supports_free_text": self.supports_free_text,
                "requires_conversational_interface": self.requires_conversational_interface,
            }
            return state
        return HeldState(
            character_id=self.character.character_id,
            backend=self.kind,
            identity=dict(self.character.identity),
            personality=dict(self.character.personality),
            memories=[m.to_dict() for m in self.character.memories],
            held_frames=[f.to_dict() for f in self.character.held_frames],
            backend_state={"communication": {
                "mode": self.communication_mode,
                "supports_free_text": self.supports_free_text,
                "requires_conversational_interface": self.requires_conversational_interface,
            }},
        )
