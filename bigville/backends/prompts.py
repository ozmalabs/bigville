"""Versioned prompt construction for external cognition providers.

Prompt construction is deliberately outside the world.  A provider receives
the character's durable identity and private held state plus the public world
context and legal affordances supplied by :class:`ActorContext`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .protocol import ActorContext


PROMPT_SCHEMA = "bigville/prompt/1"


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(v) for v in value]
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


@dataclass(frozen=True)
class PromptRecord:
    schema: str
    system: str
    context: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "system": self.system,
                "context": _plain(self.context)}

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


class PromptBuilder:
    """Build stable, replayable prompts from an actor context."""

    def __init__(self, *, schema: str = PROMPT_SCHEMA):
        self.schema = schema

    def build(self, context: ActorContext) -> PromptRecord:
        character = context.character
        private = {
            "identity": _plain(character.identity),
            "personality": _plain(character.personality),
            "memories": [_plain(m.to_dict()) for m in character.memories],
            "held_frames": [_plain(f.to_dict()) for f in character.held_frames],
            "backend": _plain(character.backend),
        }
        public = {
            "turn": int(context.turn),
            "observations": _plain(context.observations),
            "legal_affordances": _plain(context.affordances),
            "recipient_interfaces": _plain(context.recipient_interfaces),
        }
        system = (
            "You are one resident of Bigville. Choose at most one major action "
            "from legal_affordances. Communication is separate and may be free. "
            "The world validates every proposal; never invent an action, item, "
            "fact, or transaction. You may include an optional continuation with "
            "a physical destination or repeatable task. Cognition is queried "
            "again at arrival or for its interrupt_on events; set poll_each_turn "
            "true when reactive behavior is needed. Return JSON with "
            "major_action, continuation, utterances, memory_updates, and waiting."
        )
        return PromptRecord(self.schema, system, {"private": private, "public": public})


def build_prompt(context: ActorContext) -> PromptRecord:
    return PromptBuilder().build(context)
