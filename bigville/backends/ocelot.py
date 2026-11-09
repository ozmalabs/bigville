"""Adapter for a real Ocelot resident, never the local fallback mind."""
from __future__ import annotations

from importlib import import_module
from ..character import CharacterDefinition, HeldState
from .protocol import ActorContext, ActorResponse, ProposedAction


class OcelotUnavailableError(RuntimeError):
    """Ocelot was selected but its resident provider is unavailable."""


def ocelot_resident_class():
    try:
        adapter = import_module("worlds.bigville_ocelot_adapter")
        resident_type = adapter.BigvilleOcelotResident
        if not callable(resident_type):
            raise TypeError("BigvilleOcelotResident is not callable")
        return resident_type
    except Exception as exc:
        detail = f" ({type(exc).__name__}: {exc})"
        raise OcelotUnavailableError(
            "Ocelot backend requires Ocelot's worlds.bigville_ocelot_adapter "
            "and its dependencies on PYTHONPATH; select 'simple' for local NPCs."
            f" Adapter import failed{detail}"
        ) from exc


class OcelotBackend:
    kind = "ocelot"

    def __init__(self, world, character: CharacterDefinition):
        resident_type = ocelot_resident_class()
        mind = world.actor_mind(character.name)
        if not isinstance(mind, resident_type):
            raise OcelotUnavailableError(
                f"Ocelot backend for {character.name!r} requires a real "
                "BigvilleOcelotResident; construct the world with its cognition_factory."
            )
        self.world = world
        self.character = character
        provider = getattr(mind, "speech_provider", None)
        self.supports_free_text = (
            callable(getattr(provider, "propose_free_text", None))
            or callable(getattr(mind, "propose_free_text", None))
        )
        # Bigville currently exposes heard utterances in the next context but
        # does not route them through a resident speech-ingestion method.
        # Merely finding such a method on a provider would not prove the
        # ordinary game loop calls it, so keep this false until that route is
        # implemented and covered by an end-to-end test.
        self.understands_raw_speech = False
        self.communication_mode = "free_text" if self.supports_free_text else "templated"
        self.requires_conversational_interface = not self.supports_free_text

    def decide(self, context: ActorContext) -> ActorResponse:
        if hasattr(self.world, "resident_plan_from_context"):
            plan = self.world.resident_plan_from_context(self.character.name, context)
        else:
            plan = self.world.resident_plan(self.character.name)
        speech = None
        # Free text belongs to the cognition provider.  Do not call a world
        # language renderer or turn a structured speech kind into a sentence.
        # A real Ocelot integration may implement this hook and return its
        # own {text, raw} proposal; a graph-only adapter may simply remain
        # silent.
        if hasattr(self.world, "resident_free_text_proposal"):
            speech = self.world.resident_free_text_proposal(
                self.character.name, context)
        utterances = [speech] if speech is not None else []
        if plan.get("action") in {"", "none"}:
            return ActorResponse(utterances=utterances)
        # Preserve provider-owned parameters for non-village held frames too.
        # The world still validates/enacts them; this adapter must not discard
        # a board-game cognition choice merely because it is not a farm field.
        params = {k: value for k, value in plan.items()
                  if k not in {"action", "reason"}}
        return ActorResponse(
            ProposedAction(str(plan["action"]), params, "ocelot_decision"),
            utterances=utterances,
        )

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
                held_frames=([f.to_dict() for f in self.character.held_frames]
                             + list(payload.get("held_frames", []))),
                concepts=list(payload.get("concepts", [])),
                goals=list(payload.get("goals", [])),
                beliefs=list(payload.get("beliefs", [])),
                decision=dict(payload.get("decision", {})),
                backend_state=dict(payload.get("backend_state", {})),
            )
            state.backend_state["communication"] = {
                "mode": self.communication_mode,
                "supports_free_text": self.supports_free_text,
                "understands_raw_speech": self.understands_raw_speech,
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
                "understands_raw_speech": self.understands_raw_speech,
                "requires_conversational_interface": self.requires_conversational_interface,
            }},
        )
