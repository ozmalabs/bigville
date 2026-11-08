"""Phase 044: residents the world adds after a game starts (newborns), at the game level.

The world adds a newborn to its own graph (worlds/births.py calls birth()). The game keeps a character
and a backend for every resident, so a newborn needs both. The backend here is a dependent backend: it
proposes nothing. Phase 045 gives dependants their acts (an infant is refused major actions, a child
acts at its work fraction). Until then a newborn is a resident the world feeds (nursing) and the game
does not move.

BigvilleGame calls attach_newborns() at the start of each step, so a newborn added during a period has
a character and a backend by the next turn. A game restored from a checkpoint attaches its newborns the
same way. game_persistence does not yet know this backend's kind (see the Phase 044 report).
"""
from __future__ import annotations

from typing import Any

from bigville.backends.protocol import ActorResponse
from bigville.character import HeldState


class DependentBackend:
    """A resident who does not act yet. decide() returns an empty response, so the game's turn passes them by."""

    kind = "dependent"
    communication_mode = "none"
    supports_free_text = False
    requires_conversational_interface = False

    def __init__(self, character: Any):
        self.character = character
        self.last_choice: dict[str, Any] = {}

    def decide(self, context: Any) -> ActorResponse:
        return ActorResponse()

    def dump_held_state(self) -> HeldState:
        return HeldState(
            character_id=self.character.character_id, backend=self.kind,
            identity=dict(self.character.identity), personality=dict(self.character.personality),
            memories=[m.to_dict() for m in self.character.memories], held_frames=[],
            decision=dict(self.last_choice), backend_state={"proposes": "nothing"},
        )


def attach_resident(game: Any, name: str) -> bool:
    """Give one resident the world has added a character and a DependentBackend. True when attached, False when
    the game already has a character for the name."""
    if name in game.characters:
        return False
    if name not in game.world._actors:
        raise KeyError(f"the world has no resident named {name!r}")
    fresh = game._characters_from_world()
    game.characters[name] = fresh[name]
    game.backends[name] = DependentBackend(fresh[name])
    game._sync_backend_metadata()
    return True


def attach_newborns(game: Any) -> list[str]:
    """Attach every resident the world has and the game lacks. Returns the names attached (none in a fixed town)."""
    missing = [name for name in game.world._actors if name not in game.characters]
    if not missing:
        return []
    fresh = game._characters_from_world()
    for name in missing:
        game.characters[name] = fresh[name]
        game.backends[name] = DependentBackend(fresh[name])
    game._sync_backend_metadata()
    return missing
