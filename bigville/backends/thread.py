"""Continued sessions for LLM residents (Phase 066).

A resident's thread is the list of messages its model has seen and answered: the system text once, then per consult
a user message (the full packet, or the changes since the last consult) and the model's reply. The reply is the
content only. Thinking is never fed back into the thread.

Rules, all in ``bigville/backends/llm.py``:

* The first consult of a thread sends the full packet. Later consults send the changes since the last consult
  (``state_changes``), and the full packet again every ``full_every`` consults.
* When the thread would pass ``thread_chars``, a new thread starts: the system text, then a first message with the
  full packet (persona, usual day, lessons and notes, which are the resident's held memories). Its session id
  changes with it (``session``), and it is stable for the thread's life.
* A failed consult changes nothing: the thread is committed only when a reply is accepted. A repaired reply
  commits its repair request (one user message of fixed errors) with the reply it led to. The failed reply is not
  committed, as Phase 031 requires: no model output goes back to the model.

The two budgets are APPROX: characters are a stand-in for tokens, and nothing here is measured against a tokenizer.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

DEFAULT_THREAD_CHARS = 60000      # APPROX: about 15,000 tokens of text at four characters a token
DEFAULT_FULL_EVERY = 6            # APPROX: a full packet every sixth consult of a thread
REPLY_RESERVE_CHARS = 2000        # APPROX: room kept for the reply when deciding whether to compact
# Packet sections that are bookkeeping, not state: they change on every consult and are not sent as changes.
NOT_STATE = ("sizes", "omitted")
STATE_SECTIONS = ("private", "public")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def message_text(raw: Any) -> str:
    """The text of a reply as the thread stores it: the content string, or a dict's JSON."""
    if isinstance(raw, str):
        return str(raw)
    if isinstance(raw, dict):
        return json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
    return str(raw)


def state_changes(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """What changed between two packet contexts, section by section and key by key.

    Returns ``{"changes": {"private": {...}, "public": {...}}, "removed": ["public.x", ...]}``. A changed key is sent
    whole (its new value). A key present before and absent now is listed in ``removed``. Only keys whose canonical
    JSON differs are sent, so an unchanged section contributes nothing."""
    changes: dict[str, dict[str, Any]] = {}
    removed: list[str] = []
    for section in STATE_SECTIONS:
        before = previous.get(section) or {}
        after = current.get(section) or {}
        out: dict[str, Any] = {}
        for key in sorted(set(before) | set(after)):
            if key not in after:
                removed.append(f"{section}.{key}")
            elif key not in before or canonical(before[key]) != canonical(after[key]):
                out[key] = after[key]
        if out:
            changes[section] = out
    return {"changes": changes, "removed": removed}


@dataclass
class ConsultThread:
    """One resident's thread. ``messages[0]`` is the system text. ``last_state`` is the packet context the model was
    last sent in full or by changes, so the next delta is measured from what the model has."""

    resident: str
    index: int = 0
    messages: list[dict[str, str]] = field(default_factory=list)
    consults: int = 0
    since_full: int = 0
    last_state: dict[str, Any] | None = None
    started_turn: int | None = None
    full_consults: int = 0
    delta_consults: int = 0
    chars_max: int = 0

    def session(self) -> str:
        """The x-opencode-session id for this thread (the provider adds the run id). Stable for the thread's life."""
        return self.resident if self.index == 0 else f"{self.resident}-t{self.index}"

    def thread_id(self) -> str:
        return f"{self.resident}/t{self.index}"

    def chars(self) -> int:
        return sum(len(item["content"]) for item in self.messages)

    def copy(self) -> "ConsultThread":
        return copy.deepcopy(self)

    def to_dict(self) -> dict[str, Any]:
        return {"resident": self.resident, "index": self.index, "messages": copy.deepcopy(self.messages),
                "consults": self.consults, "since_full": self.since_full,
                "last_state": copy.deepcopy(self.last_state), "started_turn": self.started_turn,
                "full_consults": self.full_consults, "delta_consults": self.delta_consults,
                "chars_max": self.chars_max}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConsultThread":
        return cls(resident=str(data["resident"]), index=int(data["index"]),
                   messages=[{"role": str(m["role"]), "content": str(m["content"])} for m in data["messages"]],
                   consults=int(data["consults"]), since_full=int(data["since_full"]),
                   last_state=copy.deepcopy(data["last_state"]),
                   started_turn=None if data["started_turn"] is None else int(data["started_turn"]),
                   full_consults=int(data["full_consults"]), delta_consults=int(data["delta_consults"]),
                   chars_max=int(data["chars_max"]))
