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
        # Urgency and species-specific duties are animal motivations. The
        # world only supplies actions that are physically available.
        hunger = max(0.0, float((context.observations or {}).get("hunger", 0.0)))
        insecurity = max(0.0, float((context.observations or {}).get("insecurity", 0.0)))
        observations = context.observations or {}
        current = observations.get("position")
        enclosure_cells = [tuple(cell) for cell in observations.get("enclosure_cells", ())]
        preferred_targets = set(self.setup.get("preferred_targets", ()))
        options = []
        for option in context.affordances:
            option = dict(option)
            if option.get("action") == "eat":
                option["score"] = 30.0 * min(1.0, hunger / 2.0)
            elif option.get("action") == "move":
                option["score"] = 35.0 * min(1.0, insecurity)
                # Pick among legal adjacent steps using observed enclosure
                # geometry; the world does not choose a recovery destination.
                target = tuple(option.get("target", ()))
                if insecurity and target and enclosure_cells:
                    current_distance = min(abs(current[0] - x) + abs(current[1] - y)
                                           for x, y in enclosure_cells) if current else 0
                    next_distance = min(abs(target[0] - x) + abs(target[1] - y)
                                        for x, y in enclosure_cells)
                    option["score"] += 12.0 * (current_distance - next_distance)
            elif option.get("action") == "herd":
                # A working dog is more likely to tend its preferred stock,
                # especially when it observes an animal beyond an intact pen.
                preferred = option.get("target_species") in preferred_targets
                target_pos = option.get("target_position")
                target_pen = {tuple(cell) for cell in option.get("enclosure_cells", ())}
                escaped = bool(
                    option.get("enclosure_intact")
                    and target_pos is not None
                    and tuple(target_pos) not in target_pen
                )
                option["score"] = (24.0 if (preferred and escaped) else -4.0)
                if preferred and escaped:
                    option["score"] += 24.0
            options.append(option)
        choice = self.model.choose(context, options)
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
