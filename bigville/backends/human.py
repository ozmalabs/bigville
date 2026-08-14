"""Human player backend: queue a response from a CLI, web UI, or websocket."""
from __future__ import annotations

from collections import deque
from typing import Callable

from ..character import CharacterDefinition, HeldState
from .protocol import ActorContext, ActorResponse


class HumanBackend:
    kind = "human"
    communication_mode = "free_text"
    supports_free_text = True
    requires_conversational_interface = False

    def __init__(self, character: CharacterDefinition,
                 chooser: Callable[[ActorContext], ActorResponse] | None = None):
        self.character = character
        self.chooser = chooser
        self._responses = deque()
        self.last_context: ActorContext | None = None

    def submit(self, response: ActorResponse):
        self._responses.append(response)

    def decide(self, context: ActorContext) -> ActorResponse:
        self.last_context = context
        if self.chooser is not None:
            return self.chooser(context)
        if self._responses:
            return self._responses.popleft()
        return ActorResponse(waiting=True)

    def dump_held_state(self) -> HeldState:
        return HeldState(
            character_id=self.character.character_id,
            backend=self.kind,
            identity=dict(self.character.identity),
            personality=dict(self.character.personality),
            memories=[m.to_dict() for m in self.character.memories],
            held_frames=[f.to_dict() for f in self.character.held_frames],
            backend_state={"queued_responses": len(self._responses), "communication": {
                "mode": self.communication_mode,
                "supports_free_text": self.supports_free_text,
                "requires_conversational_interface": self.requires_conversational_interface,
            }},
        )
