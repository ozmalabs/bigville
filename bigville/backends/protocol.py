"""The cognition/backend boundary. Backends propose; the world validates."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..character import CharacterDefinition, HeldState


@dataclass
class ProposedAction:
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass
class ActorResponse:
    major_action: ProposedAction | None = None
    utterances: list[dict[str, Any]] = field(default_factory=list)
    memory_updates: list[dict[str, Any]] = field(default_factory=list)
    backend_state: dict[str, Any] = field(default_factory=dict)
    waiting: bool = False


@dataclass
class ActorContext:
    character: CharacterDefinition
    turn: int
    observations: dict[str, Any]
    affordances: list[dict[str, Any]]
    backend_state: dict[str, Any] = field(default_factory=dict)
    recipient_interfaces: dict[str, dict[str, Any]] = field(default_factory=dict)


class CognitionBackend(Protocol):
    """Any cognition provider that can drive a resident."""

    kind: str
    communication_mode: str
    supports_free_text: bool
    requires_conversational_interface: bool

    def decide(self, context: ActorContext) -> ActorResponse:
        ...

    def dump_held_state(self) -> HeldState:
        """Reverse API: expose the provider's resident-held state read-only."""
        ...


def communication_capabilities(backend) -> dict[str, Any]:
    """Return the stable capability marker exposed to worlds and clients."""
    supports = bool(getattr(backend, "supports_free_text", True))
    mode = str(getattr(backend, "communication_mode", "free_text" if supports else "templated"))
    return {
        "mode": mode,
        "supports_free_text": supports,
        "requires_conversational_interface": bool(
            getattr(backend, "requires_conversational_interface", not supports)),
    }
