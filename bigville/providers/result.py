"""What one provider call returned, in full (Phase 066).

``ProviderResult`` is a ``str`` whose value is the reply's ``content``, so every caller that expects text (the
Phase 031 validator, the Phase 055 transcript) keeps working. The rest of the response is on ``.result``, a
``CallResult``. Nothing in it reaches the world or the packet. The backend writes it to the LLM log only.

Fields that are not in a response are None (or an empty value). ``reasoning_content``, ``reasoning`` and
``reasoning_details`` are copied from ``message`` (or the choice) wherever the response puts them, unchanged.
``body`` is the whole parsed response, with the API key redacted, so a field this module does not name is kept.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CallResult:
    content: str
    reasoning_content: Any = None
    reasoning: Any = None
    reasoning_details: Any = None
    finish_reason: str | None = None
    model: str | None = None
    response_id: str | None = None
    request_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    cost: float | None = None
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
    request: dict[str, Any] = field(default_factory=dict)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    started_at: str | None = None
    latency_ms: float = 0.0
    json_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderResult(str):
    """The reply text, carrying the whole call on ``.result``. Equal to, and usable as, the content string."""

    result: CallResult

    def __new__(cls, result: CallResult):
        value = str.__new__(cls, result.content)
        value.result = result
        return value

    def __reduce__(self):  # keep the subclass picklable with its call record
        return (ProviderResult, (self.result,))
