"""Structured conversation for cognition backends without free-text output."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..runtime import _realize_meaning


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
    "greeting": "Hello, {target}.",
    "inform": "{content}",
    "request": "Could you {request}?",
    "question": "{question}",
    "answer": "{answer}",
    "offer": "I can offer {item} to {recipient}.",
    "purchase": "Could I buy {quantity} {item} from {seller}?",
    "give": "Here is {quantity} {item} for {recipient}.",
    "put": "I put {item} in {container}.",
    "accept": "Yes, I accept {thing}.",
    "decline": "No, I cannot accept {thing}.",
    "warning": "Be careful, {target}.",
    "share": "{news}",
    "thanks": "Thank you, {target}.",
    "apology": "I am sorry, {target}, about {reason}.",
    "farewell": "Goodbye, {target}.",
    "complaint": "I am unhappy about {subject}.",
    "promise": "I promise to {commitment} for {target}.",
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
        # Ocelot-style agents hand the world a structured communicative
        # meaning alongside the speech act.  A templated recipient cannot
        # consume free text, but it can still receive that meaning rendered as
        # ordinary language.  This is especially important for smalltalk and
        # gossip: ``weather of clear`` is a graph dump, not an utterance.
        if not message.template and not message.template_id and "meaning" in values:
            return _realize_meaning(values["meaning"])
        if template is not None:
            try:
                rendered = template.format(**_format_values(values), act=message.act)
                template_key = message.template_id or message.act
                is_default_template = (
                    message.template is None
                    and template_key in DEFAULT_TEMPLATES
                    and self.templates.get(template_key) == DEFAULT_TEMPLATES[template_key]
                )
                return _finish_sentence(rendered, message.act) if is_default_template else rendered
            except (KeyError, IndexError, ValueError):
                # A custom backend may omit a slot. Preserve the meaning rather
                # than dropping the utterance or raising into the world loop.
                pass
        if message.act == "smalltalk" and "weather" in values:
            return _realize_meaning({"weather": {"of": values["weather"]}})
        return _realize_meaning({message.act: values})

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


def _finish_sentence(value: str, act: str) -> str:
    """Avoid doubled punctuation while keeping custom templates untouched in meaning."""
    value = str(value).strip()
    if not value:
        return value
    if value[-1] in ".!?":
        return value
    return value + ("?" if act in {"question", "request", "purchase"} else ".")
