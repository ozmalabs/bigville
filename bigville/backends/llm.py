"""Provider-neutral LLM backend.

No vendor SDK is imported here.  Applications provide a callable or an object
with ``complete(prompt)`` and can add their preferred transport separately.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Protocol

from ..character import CharacterDefinition, HeldState
from .prompts import PromptBuilder
from .protocol import ActorContext, ActorResponse


class LLMProvider(Protocol):
    def complete(self, prompt: dict[str, Any] | str) -> Any:
        ...


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "output_text"):
        value = value.output_text
    if hasattr(value, "text"):
        value = value.text
    if not isinstance(value, str):
        raise TypeError("LLM provider must return a dict or JSON text")
    value = value.strip()
    if value.startswith("```"):
        value = value.strip("`")
        if value.startswith("json"):
            value = value[4:]
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise TypeError("LLM response JSON must be an object")
    return parsed


class LLMBackend:
    kind = "llm"
    communication_mode = "free_text"
    supports_free_text = True
    requires_conversational_interface = False

    def __init__(self, character: CharacterDefinition, provider: LLMProvider,
                 *, prompt_builder: PromptBuilder | None = None):
        self.character = character
        self.provider = provider
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.last_backend_state: dict[str, Any] = {}

    def decide(self, context: ActorContext) -> ActorResponse:
        record = self.prompt_builder.build(context)
        started = time.perf_counter()
        raw = self.provider.complete(record.as_dict())
        parsed = _payload(raw)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        raw_text = json.dumps(parsed, sort_keys=True, default=repr)
        self.last_backend_state = {
            "prompt_schema": record.schema,
            "prompt_hash": hashlib.sha256(record.as_json().encode()).hexdigest(),
            "response_hash": hashlib.sha256(raw_text.encode()).hexdigest(),
            "latency_ms": elapsed_ms,
        }
        return ActorResponse.from_dict(parsed)

    def dump_held_state(self) -> HeldState:
        return HeldState(
            character_id=self.character.character_id,
            backend=self.kind,
            identity=dict(self.character.identity),
            personality=dict(self.character.personality),
            memories=[m.to_dict() for m in self.character.memories],
            held_frames=[f.to_dict() for f in self.character.held_frames],
            backend_state={**self.last_backend_state, "communication": {
                "mode": self.communication_mode,
                "supports_free_text": self.supports_free_text,
                "requires_conversational_interface": self.requires_conversational_interface,
            }},
        )
