"""Durable, backend-neutral character state for Bigville."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(v) for v in value]
    return value


@dataclass
class MemoryRecord:
    """A resident-owned memory; it is not automatically a town fact."""

    memory_id: str
    content: Any
    kind: str = "episodic"
    source: str = "self"
    confidence: float = 1.0
    salience: float = 0.5
    turn: int = 0
    private: bool = True

    def to_dict(self) -> dict:
        return _plain(asdict(self))


@dataclass
class FrameSeed:
    """A versioned conceptual frame held by one resident."""

    seed: str
    version: str = "1"
    scope: str = "resident"
    provenance: str = "scenario"
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _plain(asdict(self))


@dataclass
class CharacterDefinition:
    """Persistent identity/personality plus resident-owned cognition inputs."""

    character_id: str
    name: str
    identity: dict[str, Any] = field(default_factory=dict)
    personality: dict[str, Any] = field(default_factory=dict)
    memories: list[MemoryRecord] = field(default_factory=list)
    held_frames: list[FrameSeed] = field(default_factory=list)
    backend: dict[str, Any] = field(default_factory=lambda: {"kind": "ocelot"})

    def to_dict(self) -> dict:
        return {
            "character_id": self.character_id,
            "name": self.name,
            "identity": _plain(self.identity),
            "personality": _plain(self.personality),
            "memories": [m.to_dict() for m in self.memories],
            "held_frames": [f.to_dict() for f in self.held_frames],
            "backend": _plain(self.backend),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterDefinition":
        return cls(
            character_id=str(data["character_id"]),
            name=str(data["name"]),
            identity=dict(data.get("identity", {})),
            personality=dict(data.get("personality", {})),
            memories=[MemoryRecord(**m) for m in data.get("memories", [])],
            held_frames=[FrameSeed(**f) for f in data.get("held_frames", [])],
            backend=dict(data.get("backend", {"kind": "ocelot"})),
        )


@dataclass
class HeldState:
    """Read-only reverse-API payload from a cognition implementer."""

    character_id: str
    backend: str
    identity: dict[str, Any]
    personality: dict[str, Any]
    memories: list[dict[str, Any]]
    held_frames: list[dict[str, Any]]
    concepts: list[dict[str, Any]] = field(default_factory=list)
    goals: list[dict[str, Any]] = field(default_factory=list)
    beliefs: list[dict[str, Any]] = field(default_factory=list)
    decision: dict[str, Any] = field(default_factory=dict)
    backend_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return _plain(asdict(self))
