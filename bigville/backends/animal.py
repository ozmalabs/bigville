"""Species-configured NPC backend for animals."""
from __future__ import annotations

from ..character import CharacterDefinition, HeldState
from .protocol import ActorContext, ActorResponse, ProposedAction
from .psi_can import CANWeightModel


class AnimalNPCBackend:
    """Use the cheap PSI/CAN chooser with an animal-specific setup."""

    kind = "animal_npc"
    communication_mode = "none"
    supports_free_text = False
    requires_conversational_interface = False

    def __init__(self, name: str, species: str, setup: dict | None = None):
        setup = dict(setup or {})
        self.character = CharacterDefinition(
            character_id=str(name), name=str(name),
            identity={"species": str(species), "role": setup.get("role", "animal")},
            personality=dict(setup.get("personality", {})),
        )
        self.species = str(species)
        self.setup = setup
        self.model = CANWeightModel()
        self.last_choice = {}

    def decide(self, context: ActorContext) -> ActorResponse:
        choice = self.model.choose(context, list(context.affordances))
        if choice is None:
            return ActorResponse()
        self.last_choice = dict(choice)
        params = {key: choice[key] for key in ("target", "kind") if key in choice}
        return ActorResponse(ProposedAction(str(choice["action"]), params, "animal_psi_can"))

    def dump_held_state(self) -> HeldState:
        return HeldState(
            character_id=self.character.character_id, backend=self.kind,
            identity=dict(self.character.identity), personality=dict(self.character.personality),
            memories=[], held_frames=[], decision=dict(self.last_choice),
            backend_state={"species": self.species, "setup": dict(self.setup),
                           "decision_model": "psi_can_weighted"},
        )
