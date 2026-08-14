"""Structured conversation for cognition backends without free-text output."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ConversationMessage:
    """A backend-neutral speech meaning with an optional surface template."""

    act: str = "inform"
    slots: dict[str, Any] = field(default_factory=dict)
    template_id: str | None = None
    template: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_value(cls, value: Any, *, fallback_content: str = ""):
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            slots = dict(value.get("slots", {}))
            if "content" in value and "content" not in slots:
                slots["content"] = value["content"]
            return cls(
                act=str(value.get("act", value.get("kind", "inform"))),
                slots=slots,
                template_id=value.get("template_id"),
                template=value.get("template"),
                payload=dict(value.get("payload", {})),
            )
        return cls(slots={"content": str(value or fallback_content)})

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_TEMPLATES = {
    "greeting": "greeting {target}",
    "inform": "inform {content}",
    "request": "request {request}",
    "question": "question {question}",
    "answer": "answer {answer}",
    "offer": "offer {item} {quantity}",
    "purchase": "purchase {quantity} {item} from {seller}",
    "give": "give {quantity} {item} to {recipient}",
    "put": "put {item} in {container}",
    "accept": "accept {thing}",
    "decline": "decline {thing}",
    "warning": "warning {target}",
    "share": "share {news}",
}


class TemplateConversationInterface:
    """Render structured conversation while retaining arbitrary slot payloads."""

    mode = "templated"
    supports_free_text = False
    requires_conversational_interface = True

    def __init__(self, templates: dict[str, str] | None = None):
        self.templates = dict(DEFAULT_TEMPLATES)
        self.templates.update(templates or {})

    def render(self, message: ConversationMessage) -> str:
        template = message.template or self.templates.get(message.template_id or message.act)
        values = dict(message.payload)
        values.update(message.slots)
        if template is not None:
            try:
                return template.format(**_format_values(values), act=message.act)
            except (KeyError, IndexError, ValueError):
                # A custom backend may omit a slot. Preserve the meaning rather
                # than dropping the utterance or raising into the world loop.
                pass
        parts = [message.act]
        for key in sorted(values):
            parts.append(f"{key}={_format_value(values[key])}")
        return " ".join(parts)

    def envelope(self, message: ConversationMessage, *, original_content="") -> dict:
        rendered = self.render(message)
        return {
            "content": rendered,
            "communication_mode": self.mode,
            "template_id": message.template_id or message.act,
            "conversation": message.to_dict(),
            "original_content": str(original_content),
        }


def _format_value(value: Any) -> str:
    if isinstance(value, dict):
        return ",".join(f"{k}={_format_value(value[k])}" for k in sorted(value))
    if isinstance(value, (list, tuple, set, frozenset)):
        return ",".join(_format_value(v) for v in value)
    return str(value)


def _format_values(values: dict[str, Any]) -> dict[str, str]:
    return {key: _format_value(value) for key, value in values.items()}
