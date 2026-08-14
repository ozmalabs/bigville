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
class ActorContinuation:
    """An optional plan that can run between cognition queries.

    ``destination`` is a physical map destination (normally a coordinate
    supplied by an affordance).  ``task`` is a world-facing action proposal
    to repeat or continue.  The game still validates every replayed proposal;
    this object only controls when the backend is asked to think again.

    ``interrupt_on`` names unexpected observations that should cause a fresh
    backend decision.  ``poll_each_turn`` disables the optimisation for this
    continuation while keeping the same response shape.
    """

    destination: Any = None
    task: ProposedAction | None = None
    interrupt_on: tuple[str, ...] = (
        "encounter", "hunger_threshold", "energy_threshold", "world_event",
        "task_failed",
    )
    expected_events: tuple[str, ...] = ()
    hunger_threshold: float = 2.0
    energy_threshold: float = 35.0
    poll_each_turn: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "task": ({"action": self.task.action, "params": dict(self.task.params),
                       "reason": self.task.reason} if self.task is not None else None),
            "interrupt_on": list(self.interrupt_on),
            "expected_events": list(self.expected_events),
            "hunger_threshold": self.hunger_threshold,
            "energy_threshold": self.energy_threshold,
            "poll_each_turn": self.poll_each_turn,
        }

    @classmethod
    def from_value(cls, value: Any) -> "ActorContinuation | None":
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise TypeError("continuation must be an object")
        task_value = value.get("task")
        task = None
        if isinstance(task_value, ProposedAction):
            task = task_value
        elif isinstance(task_value, dict) and task_value.get("action"):
            task = ProposedAction(str(task_value["action"]),
                                  dict(task_value.get("params", {})),
                                  str(task_value.get("reason", "")))
        return cls(
            destination=value.get("destination"),
            task=task,
            interrupt_on=tuple(str(item) for item in value.get(
                "interrupt_on", cls.__dataclass_fields__["interrupt_on"].default)),
            expected_events=tuple(str(item) for item in value.get("expected_events", ())),
            hunger_threshold=float(value.get("hunger_threshold", 2.0)),
            energy_threshold=float(value.get("energy_threshold", 35.0)),
            poll_each_turn=bool(value.get("poll_each_turn", False)),
        )


@dataclass
class ActorResponse:
    major_action: ProposedAction | None = None
    utterances: list[dict[str, Any]] = field(default_factory=list)
    memory_updates: list[dict[str, Any]] = field(default_factory=list)
    backend_state: dict[str, Any] = field(default_factory=dict)
    waiting: bool = False
    continuation: ActorContinuation | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ActorResponse":
        action = value.get("major_action")
        proposal = None
        if isinstance(action, dict) and action.get("action"):
            proposal = ProposedAction(str(action["action"]),
                                      dict(action.get("params", {})),
                                      str(action.get("reason", "")))
        return cls(major_action=proposal,
                   utterances=list(value.get("utterances", [])),
                   memory_updates=list(value.get("memory_updates", [])),
                   backend_state=dict(value.get("backend_state", {})),
                   waiting=bool(value.get("waiting", False)),
                   continuation=ActorContinuation.from_value(value.get("continuation")))


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
